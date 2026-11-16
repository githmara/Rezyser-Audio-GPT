"""
test_diagnoza_importow.py - ostrzezenia PyInstallera o NASZYM kodzie (v19.20.0).

`warn-<spec>.txt` ma ~350 wpisow, prawie wszystkie z bibliotek trzecich;
`Hidden import ... not found` zyje tylko w logu. `diagnoza_importow` wyciaga
z obu to, co dotyczy naszych modulow, minus lista znanych (z powodami).
Testy ida na syntetycznym tekscie w formacie PyInstallera i na jednym
prawdziwym imporcie w osobnym procesie.

Uruchom:  .venv/Scripts/python -m pytest test_diagnoza_importow.py -q
Albo jako skrypt (deleguje do pytesta): .venv/Scripts/python test_diagnoza_importow.py
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import diagnoza_importow as di

WARN = (
    "missing module named pwd - imported by posixpath (delayed, conditional, optional), shutil (delayed, optional)\n"
    "missing module named 'collections.abc' - imported by typing (top-level), gui_wczytanie_pdf (top-level)\n"
    "missing module named fontTools.ttLib.TTFont - imported by core_pdf (delayed, optional)\n"
    "missing module named brakujacy_modul - imported by core_pdf (top-level), requests (optional)\n"
    "missing module named pakiet.Klasa - imported by core_llm (top-level)\n"
    "missing module named pakiet - imported by core_llm (top-level)\n"
)
NASZE = {"core_pdf", "core_llm", "gui_wczytanie_pdf"}


def test_parsuj_warn():
    w = di.parsuj_warn(WARN)
    assert w["pwd"] == [("posixpath", "delayed, conditional, optional"),
                        ("shutil", "delayed, optional")]
    assert "collections.abc" in w


def test_tylko_nasz_kod_poza_znanymi_i_klasami():
    nowe = di.ostrzezenia_naszego_kodu(di.parsuj_warn(WARN), NASZE)
    # pwd: nie nasz importer; collections.abc: znane; TTFont: klasa przy
    # obecnym pakiecie. Klasa przy BRAKUJACYM pakiecie zostaje.
    assert set(nowe) == {"brakujacy_modul", "pakiet.Klasa", "pakiet"}
    assert nowe["brakujacy_modul"] == ["core_pdf (top-level)"]


def test_hidden_z_logu():
    log = ('123 WARNING: Hidden import "tzdata" not found!\n'
           "124 WARNING: Hidden import 'nowy_modul' not found!\n")
    assert di.hidden_z_logu(log) == ["nowy_modul"]


def test_kazdy_znany_ma_powod():
    assert all(len(p) > 40 for p in di.ZNANE.values())


def test_import_w_osobnym_procesie():
    w = di.importuj("jezyki_lingua")
    assert "blad" not in w, w
    assert "jezyki_lingua" in w["moduly"] and w["ostrzezenia"] == []
    assert "blad" in di.importuj("modul_ktorego_nie_ma_zz")


def test_brak_plikow_buildu_nie_jest_zielony(tmp_path, capsys):
    assert di.raport_buildu(tmp_path / "brak.txt", tmp_path / "brak.log") is False
    assert "not checked" in capsys.readouterr().out


def test_sam_log_bez_warn_nie_daje_falszywej_czerwieni(tmp_path, capsys):
    """Audyt 19.20: `--log PLIK` bez `--warn` konczylo sie kodem 1 o pliku-atrapie."""
    log = tmp_path / "pyinstaller_log.txt"
    log.write_text("INFO: building\n", encoding="utf-8")
    assert di.main(["--log", str(log)]) == 0
    assert "not checked" not in capsys.readouterr().out


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
