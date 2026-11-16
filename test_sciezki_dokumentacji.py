"""
test_sciezki_dokumentacji.py — gdzie generator dokumentacji zapisuje pliki (2026-11-16).

Do 2026-11-16 `KONFIG_SZABLONOW["readme"]["katalog"] = ROOT`: przebieg do katalogu
tymczasowego albo na testowych słownikach NADPISYWAŁ `readme*.md` w korzeniu repo.
Teraz README idzie do korzenia projektu, którego słowniki czytamy (domyślnie korzeń
repo, przy słownikach testowych — korzeń wskazanego katalogu), a docs domyślnie
do `docs/` w tym samym korzeniu.

Uruchom:  .venv/Scripts/python -m pytest test_sciezki_dokumentacji.py -q
Albo jako skrypt (deleguje do pytesta): .venv/Scripts/python test_sciezki_dokumentacji.py
"""

import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import generuj_dokumentacje as gd  # noqa: E402


def test_domyslnie_readme_w_korzeniu_repo_a_docs_w_docs():
    assert gd._korzen_projektu() == gd.ROOT
    assert gd._sciezka_wyjscia("readme", "en", gd.DOCS_DIR) == gd.ROOT / "readme.md"
    assert gd._sciezka_wyjscia("readme", "pl", gd.DOCS_DIR) == gd.ROOT / "readme.pl.md"
    assert gd._sciezka_wyjscia("manual", "pl", gd.DOCS_DIR) == gd.DOCS_DIR / "manual.pl.html"


def test_przebieg_porownawczy_nie_pisze_do_korzenia_repo(tmp_path):
    assert gd._sciezka_wyjscia("readme", "pl", tmp_path) == tmp_path / "readme.pl.md"
    assert gd._sciezka_wyjscia("manual", "pl", tmp_path) == tmp_path / "manual.pl.html"


@pytest.mark.parametrize("podfolder", ["dictionaries", ""])
def test_slowniki_testowe_maja_swoj_korzen(tmp_path, monkeypatch, podfolder):
    slowniki = tmp_path / podfolder if podfolder else tmp_path
    monkeypatch.setattr(gd, "DICT_DIR", slowniki)
    assert gd._korzen_projektu() == tmp_path
    # Nawet jawny katalog wyjścia nie przenosi README z korzenia testowego.
    assert gd._sciezka_wyjscia("readme", "en", tmp_path / "inne") == tmp_path / "readme.md"


def test_generuj_na_slownikach_testowych_pisze_tylko_w_ich_korzeniu(tmp_path, monkeypatch):
    zrodlo = gd.ROOT / "dictionaries" / "en" / "gui"
    cel = tmp_path / "dictionaries" / "en" / "gui"
    shutil.copytree(zrodlo / gd.FOLDER_DOKUMENTACJA, cel / gd.FOLDER_DOKUMENTACJA)
    shutil.copy2(zrodlo / gd.NAZWA_UI, cel / gd.NAZWA_UI)
    monkeypatch.setattr(gd, "DICT_DIR", tmp_path / "dictionaries")

    pliki = gd.generuj(cicho=True)

    assert tmp_path / "readme.md" in pliki
    assert tmp_path / "docs" / "manual.en.html" in pliki
    assert all(p.is_relative_to(tmp_path) for p in pliki), pliki


# Uruchomienie jako skrypt — deleguje do pytesta (kanon v19.2.1).
if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
