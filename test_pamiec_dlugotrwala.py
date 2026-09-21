"""
test_pamiec_dlugotrwala.py - Paczka z DWOMA narzedziami pamieci (v19.4.2).

v18.14 dopuszcza wprost kilka przepisow z rola `pamiec_dlugotrwala` w jednej
paczce („osobna pamiec pod siebie i osobna pod AI", docstring
`przepisy_pamieci_dlugotrwalej`). Przeglad edge-case'ow 2026-09-19 sprawdzil, co
sie stanie, GDY ta hipoteza stanie sie faktem - i znalazl dwa defekty, oba
uspione, bo dzis zadna z dziewieciu paczek drugiego takiego przepisu nie ma:

  1. `_rozstrzygnij_pamiec` przy JEDNYM pliku na dysku przemianowywal go na
     sufiks GLOWNY, jesli lezal pod innym. Migracja powstala dla sufiksow
     LOKALIZOWANYCH (plik z paczki `de` u usera z UI `pl`) i nie odrozniala
     „sufiks obcej paczki" od „sufiks drugiego narzedzia TEJ paczki" - wiec
     pamiec swiadomie zapisana narzedziem B wracala pod nazwe narzedzia A.
  2. Automat progu ALARM (`_spawn_auto_pamiec`) bral ZAWSZE pierwszy przepis,
     wiec przy dwoch narzedziach czytal wejscie rekoncyliacji z pliku
     wybranego przez rezysera, a wynik zapisywal do cudzego: nadpisywal bez
     pytania pamiec, o ktora nikt nie prosil, i zostawial te wybrana z anchorem
     sprzed automatu (nastepna rekoncyliacja wciagnelaby material juz
     skompresowany).

Testy sa REGRESJA na obu naraz, a przy okazji pilnuja, ze lekarstwo nie zjadlo
migracji, dla ktorej ten kod powstal (plik `_overview` / historyczny
`_streszczenie` / plik z paczki, ktorej user nie ma - nadal migruje).

Uruchom:  .venv/Scripts/python -m pytest test_pamiec_dlugotrwala.py -q
Albo jako skrypt (deleguje do pytesta): .venv/Scripts/python test_pamiec_dlugotrwala.py
"""

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import core_rezyser as cr
import gui_rezyser
import przepisy_rezysera as pr

# Paczka hipotetyczna: A = „pamiec pod siebie" (glowna), B = „pod AI".
SUF_A = "_streszczenie"
SUF_B = "_pamiec_ai"
KANDYDACI = [SUF_A, SUF_B, "_overview"]
NARZEDZIA = [SUF_A, SUF_B]


def _projekt(kandydaci=KANDYDACI, narzedzia=NARZEDZIA) -> tuple[cr.ProjektRezysera, Path]:
    tmp = Path(tempfile.mkdtemp(prefix="pamiec_"))
    (tmp / "skrypty").mkdir()
    (tmp / "runtime" / "skrypty").mkdir(parents=True)
    projekt = cr.ProjektRezysera(app_dir=str(tmp))
    projekt.ustaw_kandydatow_pamieci(kandydaci, narzedzia)
    return projekt, tmp


def _pisz(tmp: Path, rel: str, tresc: str) -> None:
    sciezka = tmp / rel
    sciezka.parent.mkdir(parents=True, exist_ok=True)
    sciezka.write_text(tresc, encoding="utf-8")


def _pamiec(tmp: Path, nazwa: str, sufiks: str, tresc: str, anchor: str) -> None:
    """Para plik + meta, czyli Pamiec Dlugotrwala tak, jak zapisuje ja silnik."""
    _pisz(tmp, f"skrypty/{nazwa}{sufiks}.txt", tresc)
    _pisz(tmp, f"runtime/skrypty/{nazwa}{sufiks}_meta.json",
          json.dumps({"marker_naglowek_tekst": anchor}))


def _pliki(tmp: Path) -> tuple[list[str], list[str]]:
    return (sorted(p.name for p in (tmp / "skrypty").iterdir()),
            sorted(p.name for p in (tmp / "runtime" / "skrypty").iterdir()))


# ---------------------------------------------------------------------------
# 1. Migracja: co wolno przemianowac, a czego nie
# ---------------------------------------------------------------------------
def test_plik_drugiego_narzedzia_nie_jest_przemianowywany():
    """Pamiec zapisana narzedziem B zostaje pod sufiksem B."""
    projekt, tmp = _projekt()
    _pamiec(tmp, "kroniki", SUF_B, "PAMIEC POD AI", "Rozdział 7")

    odrzucona = projekt._rozstrzygnij_pamiec("kroniki")

    assert not odrzucona
    assert projekt.sufiks_streszczenia == SUF_B, (
        f"rozstrzygnieto {projekt.sufiks_streszczenia!r} zamiast {SUF_B!r} - "
        f"plik drugiego narzedzia pamieci jest pamiecia projektu, nie kandydatem "
        f"do migracji")
    tresc, meta = _pliki(tmp)
    assert tresc == [f"kroniki{SUF_B}.txt"], (
        f"plik zostal przemianowany: {tresc} - rozroznienie „pamiec pod siebie / "
        f"pod AI" f" przepadloby po jednym wczytaniu projektu")
    assert meta == [f"kroniki{SUF_B}_meta.json"], meta


def test_plik_obcej_paczki_nadal_migruje():
    """Lekarstwo nie zjada migracji, dla ktorej ten kod powstal (v18.14)."""
    projekt, tmp = _projekt()
    # `_overview` to sufiks MIEDZYNARODOWY, nie narzedzie tej paczki - plik
    # przyszedl z innej maszyny albo z paczki, ktorej user juz nie ma.
    _pamiec(tmp, "kroniki", "_overview", "PAMIEC Z OBCEJ PACZKI", "Rozdział 3")

    assert not projekt._rozstrzygnij_pamiec("kroniki")
    assert projekt.sufiks_streszczenia == SUF_A, (
        f"obcy sufiks mial zmigrowac do glownego, a jest "
        f"{projekt.sufiks_streszczenia!r}")
    tresc, meta = _pliki(tmp)
    assert tresc == [f"kroniki{SUF_A}.txt"], tresc
    assert meta == [f"kroniki{SUF_A}_meta.json"], (
        f"meta ma jechac z plikiem - anchor rekoncyliacji jest para do tresci: {meta}")


def test_dwa_pliki_pyta_usera_i_nie_rusza_nazw():
    """Przy dwoch kandydatach decyduje rezyser, a pliki zostaja, gdzie sa."""
    projekt, tmp = _projekt()
    _pamiec(tmp, "kroniki", SUF_A, "POD SIEBIE", "Rozdział 1")
    _pamiec(tmp, "kroniki", SUF_B, "POD AI", "Rozdział 7")

    pokazane: list[list[str]] = []

    def wybor(kandydaci):
        pokazane.append([s for s, _ in kandydaci])
        return 1                                   # rezyser wybiera B

    assert not projekt._rozstrzygnij_pamiec("kroniki", wybor_pamieci=wybor)
    assert pokazane == [[SUF_A, SUF_B]], pokazane
    assert projekt.sufiks_streszczenia == SUF_B
    tresc, _ = _pliki(tmp)
    assert set(tresc) == {f"kroniki{SUF_A}.txt", f"kroniki{SUF_B}.txt"}, tresc


def test_kandydaci_bez_narzedzi_zachowuja_stary_zbior():
    """`ustaw_kandydatow_pamieci` bez drugiego argumentu nie kasuje wiedzy."""
    projekt, _tmp = _projekt()
    projekt.ustaw_kandydatow_pamieci([SUF_B, SUF_A])
    assert projekt.sufiksy_narzedzi_pamieci == set(NARZEDZIA), (
        "pominiety argument ma ZOSTAWIC poprzedni zbior narzedzi, a nie "
        "wyzerowac go - inaczej migracja sadzilaby o nowej paczce po starej")


# ---------------------------------------------------------------------------
# 2. Automat progu ALARM celuje w plik rozstrzygniety dla projektu
# ---------------------------------------------------------------------------
def _przepis(id_: str, sufiks: str, kolejnosc: int) -> pr.PrzepisRezysera:
    return pr.PrzepisRezysera(
        id=id_, etykieta=id_, kategoria=pr.KATEGORIA_POSTPROD,
        kolejnosc=kolejnosc, zakres=pr.ZAKRES_REKONCYLIACJA,
        rola=pr.ROLA_PAMIEC_DLUGOTRWALA, sufiks_pliku_wyniku=sufiks,
    )


class _AtrapaPanelu:
    """Tyle panelu, ile czyta `_przepis_pamieci_dla_projektu` (bez `wx.App`)."""

    def __init__(self, sufiks_rozstrzygniety: str, przepisy=None) -> None:
        self._postprodukcje = przepisy if przepisy is not None else [
            _przepis("streszczenie", SUF_A, 20),
            _przepis("pamiec_ai", SUF_B, 30),
        ]

        class _Projekt:
            sufiks_streszczenia = sufiks_rozstrzygniety

        self._projekt = _Projekt()


def _wybierz(sufiks: str, przepisy=None):
    return gui_rezyser.RezyserPanel._przepis_pamieci_dla_projektu(
        _AtrapaPanelu(sufiks, przepisy))


def test_automat_bierze_przepis_pliku_wybranego_przez_rezysera():
    """Rozstrzygniety sufiks B → automat uruchamia narzedzie B, nie pierwsze."""
    wybrany = _wybierz(SUF_B)
    assert wybrany is not None and wybrany.sufiks_pliku_wyniku == SUF_B, (
        f"automat wzialby {wybrany and wybrany.id!r} - czytalby wejscie "
        f"rekoncyliacji z pliku B, a wynik zapisywal do A (nadpisujac pamiec, "
        f"o ktorej nadpisanie nikt nie prosil)")


def test_automat_bez_dopasowania_bierze_pierwszy():
    """Sufiks z paczki, ktorej panel nie wyswietla → zachowanie jak przy kliknieciu."""
    wybrany = _wybierz("_yhteenveto")
    assert wybrany is not None and wybrany.sufiks_pliku_wyniku == SUF_A, wybrany


def test_brak_narzedzia_pamieci_to_cichy_no_op():
    """User skasowal YAML → automat nie ma czego uruchomic i nie moze rzucic."""
    assert _wybierz(SUF_A, przepisy=[]) is None


# Uruchomienie jako skrypt — deleguje do pytesta: jeden mechanizm, jedno
# raportowanie (kanon v19.2.1). Własny harness łapał wyłącznie `AssertionError`,
# więc `pytest.skip` wywracał mu cały przebieg, a fixture i `parametrize` były
# dla niego niewidzialne.

if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
