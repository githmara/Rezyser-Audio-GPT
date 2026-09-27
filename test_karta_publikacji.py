"""
test_karta_publikacji.py - Regresja: karta publikacyjna po pierwszym bojowym tescie (19.8.1).

Trzy usterki znalezione na prawdziwym projekcie (sztuka: Prolog, Akt 1-7 po
kilka scen, Epilog):

  1. `Sample chapters: Scena 1; Scena 2; Scena 3`. Most ElevenLabs robi rozdzial
     tylko z naglowka Prolog/Akt/Rozdzial/Epilog - scena to h1 WEWNATRZ
     rozdzialu, a "Scena 1" stala w siedmiu aktach. Model dostaje teraz liste
     rozdzialow mostu (`{rozdzialy}`), a walidator sprawdza wybor wobec niej.
  2. Tytul na okladce inny niz pole `Title:` (skrocony do czesci przed
     dwukropkiem). Walidator zada tytulu i autora w prompcie okladki.
  3. Licznik w naglowku opisu: model podal 612, opis mial 701 znakow. Liczbe
     nadpisuje Python; nowe linie licza sie do limitu (pole jest wielowierszowe).

Uruchom:  .venv/Scripts/python -m pytest test_karta_publikacji.py -q
Albo jako skrypt (deleguje do pytesta): .venv/Scripts/python test_karta_publikacji.py
"""

import dataclasses
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import core_elevenlabs as ce
import core_llm as cl
import przepisy_rezysera as pr
import rezyser_ai as rai

SZTUKA = """Prolog

[Johanna] Witajcie na pokladzie.

Akt 1

Scena 1

[Narrator] Deszcz nad Helsinkami.

Scena 2

[Hans] Skad te towary?

Akt 2

Scena 1

[Narrator] Kuchnia hotelu.

Epilog

[Johanna] Stacja koncowa.
"""

OPIS = "Pierwszy akapit opisu.\n\nDrugi akapit opisu."


def _karta(probki="Prolog; Akt 1", tytul="Kontynent Marzen: Sledztwo",
           napis='"KONTYNENT MARZEN: SLEDZTWO"', autor="Mara",
           napis_autora='"Mara"', licznik="12"):
    return (
        f"Title: {tytul}\n"
        "Subtitle: —\n"
        "\n"
        f"Description ({licznik}/1000 characters):\n"
        f"{OPIS}\n"
        "\n"
        "Genres: Fantasy; Detective and Crime\n"
        "Target audience: Adult\n"
        "Mature content: No — bez drastycznych scen.\n"
        f"Sample chapters: {probki}\n"
        "\n"
        "Cover image prompt (1200x1800 px, English):\n"
        f"Vertical cover, title text {napis} at the top, "
        f"author name {napis_autora} at the bottom.\n"
        "\n"
        "Publisher: [do uzupelnienia recznie]\n"
        "ISBN: [do uzupelnienia recznie]\n"
        f"Author profile: {autor}\n"
    )


@pytest.fixture(scope="module")
def przepis():
    p = pr.zaladuj_przepis("publikacja", "pl", kategoria="postprodukcja")
    assert p is not None and p.gatunki_dozwolone and p.limit_znakow_opisu
    return p


ROZDZIALY = ["Prolog", "Akt 1", "Akt 2", "Epilog"]


def test_rozdzialy_mostu_pomijaja_sceny():
    assert ce.nazwy_rozdzialow(SZTUKA) == ROZDZIALY


def test_rozdzialy_mostu_zgodne_z_buduj_chapters():
    assert ce.nazwy_rozdzialow(SZTUKA) == [
        ch["name"] for ch in ce.buduj_chapters(SZTUKA, {ce.NARRATOR_KEY: "v"})]


def test_tresc_przed_pierwszym_rozdzialem_to_rozdzial_domyslny():
    assert ce.nazwy_rozdzialow("[Narrator] Wstep.\n\nAkt 1\n\n[Narrator] X.\n") \
        == ["1", "Akt 1"]


def test_karta_zgodna_nie_ma_ostrzezen(przepis):
    assert rai.waliduj_karte_publikacji(przepis, _karta(), ROZDZIALY) == []


def test_sceny_jako_probki_daja_ostrzezenie(przepis):
    uwagi = rai.waliduj_karte_publikacji(
        przepis, _karta(probki="Scena 1; Scena 2; Akt 1"), ROZDZIALY)
    assert len(uwagi) == 1
    assert "Scena 1; Scena 2" in uwagi[0] and "Akt 2" in uwagi[0]


def test_probki_bez_listy_rozdzialow_nie_sa_sprawdzane(przepis):
    assert rai.waliduj_karte_publikacji(
        przepis, _karta(probki="Scena 1"), None) == []


def test_przecinek_w_nazwie_rozdzialu_i_jako_separator(przepis):
    rozdzialy = ["Rozdzial 1: Ogien, woda", "Rozdzial 2", "Rozdzial 3"]
    assert rai.waliduj_karte_publikacji(przepis, _karta(
        probki='"Rozdzial 1: Ogien, woda"; Rozdzial 2'), rozdzialy) == []
    assert rai.waliduj_karte_publikacji(przepis, _karta(
        probki="Rozdzial 2, Rozdzial 3"), rozdzialy) == []


def test_okladka_ze_skroconym_tytulem_daje_ostrzezenie(przepis):
    uwagi = rai.waliduj_karte_publikacji(
        przepis, _karta(napis='"KONTYNENT MARZEN"'), ROZDZIALY)
    assert len(uwagi) == 1 and "Kontynent Marzen: Sledztwo" in uwagi[0]


def test_okladka_bez_autora_daje_ostrzezenie(przepis):
    uwagi = rai.waliduj_karte_publikacji(
        przepis, _karta(napis_autora="(none)"), ROZDZIALY)
    assert len(uwagi) == 1 and "Mara" in uwagi[0]


def test_autor_do_uzupelnienia_nie_jest_szukany_na_okladce(przepis):
    assert rai.waliduj_karte_publikacji(przepis, _karta(
        autor="[do uzupelnienia recznie]", napis_autora="(none)"),
        ROZDZIALY) == []


def test_brak_tytulu_daje_ostrzezenie(przepis):
    karta = _karta().replace("Title: Kontynent Marzen: Sledztwo\n", "")
    uwagi = rai.waliduj_karte_publikacji(przepis, karta, ROZDZIALY)
    assert len(uwagi) == 1 and rai.KOTWICA_TYTUL in uwagi[0]


def test_licznik_opisu_nadpisany_faktyczna_dlugoscia_z_nowymi_liniami():
    karta = rai._popraw_licznik_opisu(_karta(licznik="612"))
    assert f"Description ({len(OPIS)}/1000 characters):" in karta
    # dwa znaki nowej linii miedzy akapitami wliczone do limitu
    assert len(OPIS) == len("Pierwszy akapit opisu.") + 2 + len("Drugi akapit opisu.")


def test_postprodukcja_podaje_rozdzialy_i_poprawia_licznik(przepis, monkeypatch):
    wyslane = {}

    def _falszywy_llm(klient, **kw):
        wyslane["user"] = kw["messages"][0]["content"]
        return _karta(probki="Scena 1; Scena 2", licznik="612"), "end_turn"

    monkeypatch.setattr(cl, "wywolaj_llm", _falszywy_llm)
    z_placeholderem = dataclasses.replace(
        przepis, prompt_uzytkownika_szablon="{rozdzialy}\n\n{tresc}")
    wynik = rai.wykonaj_postprodukcje_calosc(None, z_placeholderem, SZTUKA)

    assert wyslane["user"].startswith("- Prolog\n- Akt 1\n- Akt 2\n- Epilog")
    assert f"Description ({len(OPIS)}/1000" in wynik.tekst
    assert "Scena 1; Scena 2" in wynik.ostrzezenie


JEZYKI = sorted(p.parent.parent.name for p in
                Path(__file__).parent.glob("dictionaries/*/rezyser/postprod_publikacja.yaml"))


def test_zakres_paczek():
    assert len(JEZYKI) >= 9


@pytest.mark.parametrize("kod", JEZYKI)
def test_paczka_niesie_kontrakt_karty(kod):
    """Placeholder listy rozdziałów, licznik `0` do nadpisania, nowe pole."""
    p = pr.zaladuj_przepis("publikacja", kod, kategoria="postprodukcja")
    assert p is not None
    user = pr.buduj_prompt_uzytkownika(p, tresc="X", rozdzialy="- Akt 1")
    assert "- Akt 1" in user and "{" not in user
    system = pr.buduj_prompt_systemowy(p)
    assert "Description (0/" in system
    assert "Primary language:" in system and "`Title`" in system


@pytest.mark.parametrize("kod", JEZYKI)
def test_jedna_wartosc_do_uzupelnienia_w_paczce(kod):
    """Reguła 9, reguła 10 i pole Publisher mówią o TEJ SAMEJ wartości.

    Pełna retranslacja `_tryby` (19.8.1) tłumaczy tę wartość od nowa
    (`[manuell zu ergänzen]` zamiast `[manuell auszufüllen]`), więc przy
    SKŁADANIU paczki jako `HEAD` + nowe reguły z draftu reguła okładki niesie
    inną wartość niż pole Publisher — model widziałby dwie różne „puste"
    wartości. Sam draft jest wewnętrznie spójny; ten test pilnuje składania.
    """
    tekst = (Path(__file__).parent / "dictionaries" / kod / "rezyser"
             / "postprod_publikacja.yaml").read_text(encoding="utf-8")
    publisher = rai._fragment_po_kotwicy(tekst, rai.KOTWICA_WYDAWCA)
    w_regulach = set(re.findall(r"`(\[[^\]`]+\])`", tekst)) - {"[OBECNA FABUŁA]"}
    assert w_regulach == {publisher}


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
