"""
test_audio_tagi_v4.py - zlozone audio-tagi Eleven v4 nie sa brane za mowce
(v19.10).

Eleven v4 przyjmuje w jednym nawiasie kilka dyrektyw po przecinku, czesc
w wolnej formie: `[whispers, holding back tears]`. Do v19.9 oba miejsca, ktore
odrozniaja audio-tag od mowcy, porownywaly CALA tresc nawiasu z
`core_rezyser.AUDIO_TAGS`, wiec taki tag:

  * w silniku akcentow (`zastosuj_akcenty_uniwersalne`) zostawal nowym mowca
    i dalsza czesc kwestii tracila akcent postaci;
  * w wersji dla czytnikow ekranu (`_usun_audio_tagi`) nie byl usuwany,
    wiec NVDA czytal go na glos.

Oba miejsca korzystaja teraz z `core_rezyser.czy_audio_tag`.

Uruchom:  .venv/Scripts/python -m pytest test_audio_tagi_v4.py -q
Albo jako skrypt (deleguje do pytesta): .venv/Scripts/python test_audio_tagi_v4.py
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import core_rezyser as cr
import core_screen_reader as csr


@pytest.mark.parametrize("tresc", [
    "whispers",
    "Whispers",
    "whispers, holding back tears",
    "holding back tears, whispers",
    " sighs ,  trembling ",
    "through gritted teeth, furious",
])
def test_tag_prosty_i_zlozony_jest_tagiem(tresc):
    assert cr.czy_audio_tag(tresc)


@pytest.mark.parametrize("tresc", [
    "Narrator",
    "Olaf",
    "Pani Halina",
    "holding back tears",   # w calosci wolna forma: swiadomie nierozpoznany
])
def test_mowca_nie_jest_tagiem(tresc):
    assert not cr.czy_audio_tag(tresc)


def test_czytnik_ekranu_usuwa_tag_zlozony():
    wynik = csr._usun_audio_tagi(
        "[whispers, holding back tears] Nie odchodz. [sighs] Prosze."
    )
    assert wynik == "Nie odchodz. Prosze.", wynik


# Tagi z zywej proby Sonneta na prompcie v4 (helsinki_story, 2026-10-06):
# 14 z 18 bylo spoza `AUDIO_TAGS`. Rozpoznanie idzie po POZYCJI, nie slowniku.
TAGI_Z_PROBY = [
    "softly", "firmly", "awkwardly", "flustered", "barely audible",
    "voice thick", "faint smile", "a short, bitter laugh",
    "stiffly, but warmer", "clearing his throat, earnest",
]


@pytest.mark.parametrize("tag", TAGI_Z_PROBY)
def test_czytnik_ekranu_usuwa_tag_spoza_slownika(tag):
    wynik = csr._usun_audio_tagi(f"[{tag}] Jutro tam pojde.")
    assert wynik == "Jutro tam pojde.", wynik


def test_html_dla_nvda_bez_tagow_z_proby():
    skrypt = "".join(
        f"[Hans] [{tag}] Kwestia {i}.\n" for i, tag in enumerate(TAGI_Z_PROBY)
    )
    html = csr.generuj_html(skrypt, "", jezyk_projektu="pl")
    for tag in TAGI_Z_PROBY:
        assert f"[{tag}]" not in html, tag
    assert html.count("<strong>Hans:</strong>") == len(TAGI_Z_PROBY)


@pytest.mark.parametrize("tag", TAGI_Z_PROBY)
def test_tag_spoza_slownika_w_srodku_nie_resetuje_akcentu(tag):
    lore = "[Marek] - ma akcent francuski\n"
    wzorzec = cr.zastosuj_akcenty_uniwersalne(
        "[Marek] Wielka szansa.\n", lore, "pl"
    )
    zakcentowane = wzorzec[len("[Marek] "):]
    wynik = cr.zastosuj_akcenty_uniwersalne(
        f"[Marek] [{tag}] Wielka szansa.\n", lore, "pl"
    )
    assert wynik == f"[Marek] [{tag}] " + zakcentowane, wynik


def test_nawias_na_poczatku_kolejnej_linii_to_nowy_mowca():
    """Druga linia nalezy do Ewy (bez akcentu) — mowca zmienia sie po `\\n`."""
    lore = "[Marek] - ma akcent francuski\n"
    wynik = cr.zastosuj_akcenty_uniwersalne(
        "[Marek] [softly] Wielka szansa.\n  [Ewa] Wielka szansa.\n", lore, "pl"
    )
    assert wynik.endswith("  [Ewa] Wielka szansa.\n"), wynik
    assert not wynik.startswith("[Marek] [softly] Wielka szansa.\n"), wynik


def test_tag_zlozony_nie_resetuje_akcentu_mowcy():
    """Akcent postaci obejmuje tez tekst PO tagu zlozonym."""
    lore = "[Marek] - ma akcent francuski\n"
    wzorzec = cr.zastosuj_akcenty_uniwersalne(
        "[Marek] Wielka szansa.\n", lore, "pl"
    )
    assert wzorzec != "[Marek] Wielka szansa.\n", "akcent nie zadzialal"
    zakcentowane = wzorzec[len("[Marek] "):]

    wynik = cr.zastosuj_akcenty_uniwersalne(
        "[Marek] [whispers, holding back tears] Wielka szansa.\n", lore, "pl"
    )
    assert wynik == (
        "[Marek] [whispers, holding back tears] " + zakcentowane
    ), wynik


# Uruchomienie jako skrypt — deleguje do pytesta: jeden mechanizm, jedno
# raportowanie (kanon v19.2.1). Własny harness łapał wyłącznie `AssertionError`,
# więc `pytest.skip` wywracał mu cały przebieg, a fixture i `parametrize` były
# dla niego niewidzialne.

if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
