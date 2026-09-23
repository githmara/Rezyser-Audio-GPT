"""
test_znaki_niewidoczne.py - Bramka: pliki czytane przez SILNIK nie maja niewidocznych znakow (19.8).

Miekki lacznik (U+00AD), spacja zerowej szerokosci i pokrewne dziela slowo tam,
gdzie oko go nie widzi. W pliku, ktory silnik dopasowuje literalnie (kotwice,
slowa-wyzwalacze, `zamiany:` akcentow) albo wysyla modelowi jako prompt, to
usterka bez objawu. Zmierzone 19.8: `buduj_wielojezyczne_tryby` oddal
`is/tryb_audiobook` z U+00AD wewnatrz slowa, a dwa takie znaki siedzialy juz
w paczce `fi/opowiesci/` od dawna - zadna bramka ich nie widziala.

Zakres: `dictionaries/**/*.yaml` BEZ `gui/dokumentacja/` - szablony podrecznika
ida do HTML, gdzie miekki lacznik jest legalna typografia dzielenia wyrazow.
Lista znakow i jej uzasadnienie: `tlumacz_bramki.ZNAKI_NIEWIDOCZNE`.

Uruchom:  .venv/Scripts/python -m pytest test_znaki_niewidoczne.py -q
Albo jako skrypt (deleguje do pytesta): .venv/Scripts/python test_znaki_niewidoczne.py
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import tlumacz_bramki

DICT_DIR = Path(__file__).parent / "dictionaries"


def _pliki_silnika() -> list[Path]:
    return sorted(
        p for p in DICT_DIR.rglob("*.yaml")
        if "dokumentacja" not in p.relative_to(DICT_DIR).parts
    )


def test_zakres_nie_jest_pusty():
    """Bramka, ktora nic nie skanuje, ma sie wywrocic, a nie swiecic na zielono."""
    assert len(_pliki_silnika()) > 100, len(_pliki_silnika())


def test_brak_znakow_niewidocznych():
    usterki = []
    for plik in _pliki_silnika():
        for diag in tlumacz_bramki.znaki_niewidoczne(
                plik.read_text(encoding="utf-8")):
            usterki.append(f"{plik.relative_to(DICT_DIR)}: {diag}")
    assert not usterki, "\n".join(usterki)


def test_funkcja_widzi_miekki_lacznik():
    """Kontrola przeciwna: bramka nie jest slepa na znak, ktory ja powolal."""
    assert tlumacz_bramki.znaki_niewidoczne("ná­kvæmlega")
    assert tlumacz_bramki.znaki_niewidoczne("zwykły tekst — «cytat»") == []


# Uruchomienie jako skrypt - deleguje do pytesta (kanon v19.2.1, §6.11).
if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
