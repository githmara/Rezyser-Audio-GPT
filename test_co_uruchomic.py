"""
test_co_uruchomic.py - narzedzie "co ruszyles -> co ma przedmiot" (v19.20.0).

`co_uruchomic.py` nie trzyma kopii tabeli - parsuje ja z CONTRIBUTING.md.
Testy pilnuja dwoch rzeczy: (1) tabela w realnym pliku nadal sie parsuje
i kazdy jej wiersz ma co najmniej jeden wzorzec (wiersz bez wzorca nigdy
niczego nie dopasuje - cicha dziura); (2) semantyka dopasowania czytana tak,
jak czyta ja czlowiek: koncowka sciezki, "other" = reszta, "new" = dodane.

Uruchom:  .venv/Scripts/python -m pytest test_co_uruchomic.py -q
Albo jako skrypt (deleguje do pytesta): .venv/Scripts/python test_co_uruchomic.py
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import co_uruchomic as cu

KORZEN = Path(__file__).parent


def _tabela():
    return cu.wczytaj_tabele((KORZEN / "CONTRIBUTING.md").read_text(encoding="utf-8"))


def test_realna_tabela_sie_parsuje_i_kazdy_wiersz_ma_wzorzec():
    wiersze = _tabela()
    assert len(wiersze) >= 15
    bez = [w.opis for w in wiersze if not w.wzorce]
    assert not bez, f"rows that can never match anything: {bez}"


def test_semantyka_dopasowania():
    wiersze = _tabela()
    pliki = ["core_pdf.py", "dictionaries/fi/gui/ui.yaml",
             "dictionaries/fi/akcenty/finski.yaml", "test_nowy.py", "test_stary.py",
             "nieznany_modul.py"]
    bez = cu.dopasuj(wiersze, pliki, nowe={"test_nowy.py"})
    po_opisie = {w.opis: w.pliki for w in wiersze if w.pliki}
    ui = next(o for o in po_opisie if "gui/ui.yaml" in o)
    inne = next(o for o in po_opisie if "any other" in o)
    nowy_test = next(o for o in po_opisie if "a new `test_*.py`" in o)
    assert po_opisie[ui] == ["dictionaries/fi/gui/ui.yaml"]          # koncowka sciezki
    assert po_opisie[inne] == ["dictionaries/fi/akcenty/finski.yaml"]  # "other" = reszta
    assert po_opisie[nowy_test] == ["test_nowy.py"]                    # "new" = dodane
    assert "nieznany_modul.py" in bez and "core_pdf.py" not in bez


def test_lista_reczna_traktuje_pliki_jako_nowe():
    wiersze = _tabela()
    cu.dopasuj(wiersze, ["test_cos.py"], nowe=None)
    assert any(w.pliki == ["test_cos.py"] for w in wiersze if w.tylko_nowe)


def test_main_na_liscie_recznej(capsys):
    assert cu.main(["--pliki", "core_pdf.py"]) == 0
    out = capsys.readouterr().out
    assert "test_core_pdf.py" in out and ".venv/Scripts/python -m pytest" in out


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
