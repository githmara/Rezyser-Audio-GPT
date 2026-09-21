"""
test_audyt_kreatora.py - dowod bojowy bramki synchronizacji tekstow kreatora.

Bramka `audyt_kreatora` pilnuje, ze szablony i prompty Managera Regul opisuja
silnik, ktory ISTNIEJE. Zielona bramka na czystym repo nie dowodzi niczego -
tak samo zielona bylaby bramka, ktora nie sprawdza nic. Dlatego kazda z osmiu
klas dostaje tu WSTRZYKNIETY defekt i musi zostac zlapana po nazwie klasy.

Uruchom:  .venv/Scripts/python -m pytest test_audyt_kreatora.py -q
Albo jako skrypt (deleguje do pytesta): .venv/Scripts/python test_audyt_kreatora.py
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import audyt_kreatora as ak
import manager_regul_szablony as mrs

_YAML_BAZOWY = (
    "id: zzsonda\n"
    'etykieta: "Zzsonda"\n'
    "opis: |\n  opis\n"
    "iso: pl\n"
    "kategoria: szyfr\n"
    "kolejnosc: 100\n"
    "zamiany: []\n"
)

_PROMPT_BAZOWY = (
    "Fields `id`, `etykieta`, `opis`, `iso`, `kategoria`, `kolejnosc`, "
    "`zamiany`."
)


def _klasy(pakiet: dict, typ: str = "sonda") -> set[str]:
    """Klasy trafien, ktore detektory zglaszaja dla podanego pakietu."""
    trafienia: list[tuple[str, str]] = []

    def zglos(klasa: str, szczegol: str) -> None:
        trafienia.append((klasa, szczegol))

    pliki = ak._pliki_paczki_referencyjnej()
    for pole in ("yaml", "prompt"):
        tekst = pakiet.get(pole) or ""
        if tekst:
            ak._sprawdz_cytaty(typ, pole, tekst, pliki, zglos)
    ak._sprawdz_szablon(typ, pakiet, zglos)
    return {k for k, _ in trafienia}


def _pakiet_bazowy(**nadpisz) -> dict:
    """Minimalny, POPRAWNY pakiet kreatora - punkt odniesienia dla mutacji."""
    pakiet = {
        "yaml": _YAML_BAZOWY,
        "prompt": _PROMPT_BAZOWY,
        "docelowy": "pl/szyfry/zzsonda.yaml",
    }
    pakiet.update(nadpisz)
    return pakiet


# ---------------------------------------------------------------------------
# 0. Stan repozytorium
# ---------------------------------------------------------------------------
def test_bramka_na_repozytorium_jest_zielona():
    """Wszystkie dziewiec typow renderuje sie i nie klamie o silniku."""
    wynik = ak.bramka()
    assert wynik.czysto, wynik.nowe


def test_pakiet_bazowy_testu_jest_czysty():
    """Punkt odniesienia mutacji sam nie moze produkowac trafien."""
    assert _klasy(_pakiet_bazowy()) == set()


# ---------------------------------------------------------------------------
# 1. Osiem klas, kazda ze wstrzyknietym defektem
# ---------------------------------------------------------------------------
def test_lapie_render_blad(monkeypatch):
    """Typ, ktorego nie da sie wystawic w GUI - np. klamra w f-stringu."""

    def wybuchowy(*a, **kw):
        raise ValueError("Invalid format specifier")

    monkeypatch.setattr(mrs, "zbuduj_wynik", wybuchowy)
    wynik = ak.zbierz()
    assert wynik, "bramka przepuscila typ, ktory w ogole sie nie renderuje"
    klasy = {p.split("|")[0] for powody in wynik.values() for p in powody}
    assert klasy == {"render-blad"}, klasy


def test_lapie_szablon_ktory_nie_jest_yamlem():
    """Szablon musi sie parsowac - inaczej uzytkownik dostaje zepsuty plik."""
    assert "render-blad" in _klasy(_pakiet_bazowy(yaml="id: [niedomkniete\n"))


def test_lapie_modul_nieznany():
    zepsuty = _pakiet_bazowy(
        prompt="Open `core_nieistniejacy.py` before writing. " + _PROMPT_BAZOWY)
    assert "modul-nieznany" in _klasy(zepsuty)


def test_lapie_symbol_nieznany():
    zepsuty = _pakiet_bazowy(
        prompt="See `core_poliglota.NIE_MA_TAKIEJ_STALEJ`. " + _PROMPT_BAZOWY)
    assert "symbol-nieznany" in _klasy(zepsuty)


def test_symbol_istniejacy_nie_jest_zglaszany():
    """Kontrola odwrotna: prawdziwy symbol nie moze produkowac trafienia."""
    czysty = _pakiet_bazowy(
        prompt="See `core_poliglota._ALGORYTMY_SZYFROW`. " + _PROMPT_BAZOWY)
    assert "symbol-nieznany" not in _klasy(czysty)


def test_lapie_plik_paczki_nieznany():
    """Prompt odsylajacy do wzorca, ktorego w paczce referencyjnej nie ma."""
    zepsuty = _pakiet_bazowy(
        prompt="Open `dictionaries/pl/szyfry/nie_ma_mnie.yaml`. " + _PROMPT_BAZOWY)
    assert "plik-paczki-nieznany" in _klasy(zepsuty)


def test_lapie_sciezke_nieznana():
    zepsuty = _pakiet_bazowy(
        prompt="Look in `dictionaries/xx/akcenty`. " + _PROMPT_BAZOWY)
    assert "sciezka-nieznana" in _klasy(zepsuty)


def test_lapie_pole_nieznane():
    """Szablon zapisujacy pole, ktorego silnik dla tej sciezki nie czyta."""
    zepsuty = _pakiet_bazowy(
        yaml=_YAML_BAZOWY + "pole_ktorego_nie_ma: 1\n",
        prompt=_PROMPT_BAZOWY + " Also `pole_ktorego_nie_ma`.")
    assert "pole-nieznane" in _klasy(zepsuty)


def test_lapie_pole_poza_promptem():
    """Rdzen synchronizacji: szablon pisze pole, prompt o nim milczy."""
    zepsuty = _pakiet_bazowy(
        prompt="Fields `id`, `etykieta`, `opis`, `iso`, `kategoria`, "
               "`kolejnosc`.")
    assert "pole-poza-promptem" in _klasy(zepsuty)


def test_lapie_wartosc_nielegalna():
    zepsuty = _pakiet_bazowy(
        yaml=_YAML_BAZOWY.replace("kategoria: szyfr", "kategoria: szyfrowanie"))
    assert "wartosc-nielegalna" in _klasy(zepsuty)


# ---------------------------------------------------------------------------
# 2. Sonda nie moze udawac defektu
# ---------------------------------------------------------------------------
def test_sciezka_pliku_do_utworzenia_nie_jest_defektem():
    """Prompty cytuja plik, ktory uzytkownik ma DOPIERO napisac."""
    czysty = _pakiet_bazowy(
        prompt=f"Write `dictionaries/pl/szyfry/{ak.SONDA_ID}.yaml`. "
               + _PROMPT_BAZOWY)
    assert "sciezka-nieznana" not in _klasy(czysty)


def test_nowa_paczka_sondy_nie_jest_defektem():
    """Kreator jezyka bazowego pisze do paczki, ktorej jeszcze nie ma."""
    czysty = _pakiet_bazowy(
        prompt=f"Write `dictionaries/{ak.SONDA_ISO}/podstawy.yaml`. "
               + _PROMPT_BAZOWY)
    assert "sciezka-nieznana" not in _klasy(czysty)


# ---------------------------------------------------------------------------
# 3. Zrodla prawdy sa zrodlami, nie kopiami
# ---------------------------------------------------------------------------
def test_wartosci_enumeratywne_ida_z_kodu():
    """Bramka pyta silnik o legalne wartosci, nie trzyma wlasnej listy."""
    import core_poliglota as cp
    import przepisy_rezysera as pr

    legalne = ak._wartosci_enumeratywne()
    assert legalne["zakres"] == set(pr.ZAKRESY_DOZWOLONE)
    assert legalne["format_wyjscia"] == set(pr.FORMATY_WYJSCIA)
    assert legalne["struktura"] == set(pr.STRUKTURY)
    assert legalne["algorytm"] == set(cp._ALGORYTMY_SZYFROW)


def test_szablon_trybu_cytuje_pelne_zbiory_wartosci():
    """Szablon i prompt trybu wyliczaja DOKLADNIE to, co dispatch silnika."""
    import przepisy_rezysera as pr

    pakiet = mrs.zbuduj_wynik(mrs.TYP_TRYB_REZYSERA, id_pliku="zzsonda",
                              etykieta="Zzsonda")
    for wartosc in (*pr.STRUKTURY, *pr.FORMATY_WYJSCIA):
        assert wartosc in pakiet["yaml"], f"szablon nie zna `{wartosc}`"
        assert wartosc in pakiet["prompt"], f"prompt nie zna `{wartosc}`"


# Uruchomienie jako skrypt — deleguje do pytesta: jeden mechanizm, jedno
# raportowanie (kanon v19.2.1). Własny harness łapał wyłącznie `AssertionError`,
# więc `pytest.skip` wywracał mu cały przebieg, a fixture i `parametrize` były
# dla niego niewidzialne.

if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
