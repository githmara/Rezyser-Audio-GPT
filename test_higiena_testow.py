"""test_higiena_testow.py - bramka "test zostawia swiat taki, jaki zastal" (v19.20.0).

Dynamiczna polowa bramki siedzi w `conftest.py` (migawka przed / porownanie
po KAZDYM tescie); tu sa jej statyczne polowy na realnym repo i dowody
bojowe, ze detektory lapia defekt i puszczaja kanon. Uzasadnienie
i zakres: docstring `higiena_testow.py`.

Uruchom:  .venv/Scripts/python -m pytest test_higiena_testow.py -q
Albo jako skrypt (deleguje do pytesta): .venv/Scripts/python test_higiena_testow.py
"""

import ast
import os
import stat
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import higiena_testow as ht

KORZEN = Path(__file__).parent


# ---------------------------------------------------------------------------
# 1. Kanon na realnym repo
# ---------------------------------------------------------------------------
def test_conftest_wpina_bramke_dla_kazdego_testu():
    """Bez autouse fixture'ow bramka istnialaby tylko na papierze."""
    drzewo = ast.parse((KORZEN / "conftest.py").read_text(encoding="utf-8"))
    autouse = set()
    for fn in drzewo.body:
        if isinstance(fn, ast.FunctionDef):
            for dek in fn.decorator_list:
                if isinstance(dek, ast.Call) and any(
                        kw.arg == "autouse" and getattr(kw.value, "value", False)
                        for kw in dek.keywords):
                    autouse.add(fn.name)
    assert {"_higiena_testu", "_higiena_pliku", "_sledz_mkdtemp"} <= autouse, autouse


def test_testy_nie_tlumia_bledow_sprzatania():
    """`rmtree(ignore_errors=True)` zostawial repo git w %TEMP% - uzyj `ht.usun_katalog`."""
    trafienia = [f"{p.name}:{l}" for p in sorted(KORZEN.glob("test_*.py"))
                 for l in ht.tlumione_sprzatanie(p.read_text(encoding="utf-8"))]
    assert not trafienia, (
        f"silent cleanup in {trafienia} - a directory that fails to delete stays "
        f"behind without a word; use higiena_testow.usun_katalog")


def test_kod_pisze_tylko_do_zapewnionego_katalogu():
    """Zapis pliku = `mkdir`/`makedirs` w tej samej funkcji albo wpis z powodem."""
    znalezione = {f"{p.name}:{fn}"
                  for p in sorted(KORZEN.glob("*.py"))
                  if not p.name.startswith(("test_", "conftest"))
                  for fn in ht.zapisy_bez_ensure(p.read_text(encoding="utf-8"))}
    nowe = sorted(znalezione - set(ht.ZAPISY_BEZ_ENSURE))
    assert not nowe, (
        f"{nowe} write a file without making sure its directory exists - add "
        f"mkdir(parents=True, exist_ok=True) or a reasoned entry in "
        f"higiena_testow.ZAPISY_BEZ_ENSURE")
    martwe = sorted(set(ht.ZAPISY_BEZ_ENSURE) - znalezione)
    assert not martwe, f"{martwe} no longer apply - remove them from ZAPISY_BEZ_ENSURE"


def test_wyjatki_globali_wskazuja_istniejace_pola():
    for (modul, nazwa), powod in ht.DOZWOLONE_ZMIANY_GLOBALI.items():
        assert powod.strip(), (modul, nazwa)
        assert nazwa in vars(__import__(modul)), f"{modul}.{nazwa} does not exist"


# ---------------------------------------------------------------------------
# 2. Dowod bojowy detektorow
# ---------------------------------------------------------------------------
def test_wyciek_globala_wykryty_a_leniwa_inicjalizacja_nie():
    mod = types.ModuleType("modul_probny")
    mod.KATALOG = "repo/dictionaries"
    mod._DETEKTOR = None
    przed = ht.migawka_globali({"modul_probny": mod})
    mod._DETEKTOR = object()                       # leniwa inicjalizacja: legalna
    assert ht.zmiany_globali(przed, {"modul_probny": mod}) == []
    mod.KATALOG = "C:/Temp/tmp123/dictionaries"    # wyciek: blad
    zmiany = ht.zmiany_globali(przed, {"modul_probny": mod})
    assert len(zmiany) == 1 and "modul_probny.KATALOG" in zmiany[0]


def test_srodowisko_nigdy_nie_drukuje_wartosci():
    """Pierwsza wersja bramki wydrukowala klucze z golden_key.env."""
    zmiany = ht.zmiany_srodowiska({"A": "x"}, {"A": "x", "KLUCZ": "sk-ant-TAJNE",
                                               "PYTEST_CURRENT_TEST": "t"})
    assert zmiany == ["KLUCZ: unset -> set (12 chars)"]
    assert "TAJNE" not in " ".join(zmiany)


def test_migawka_danych_widzi_smiec(tmp_path):
    (tmp_path / "runtime" / "skrypty").mkdir(parents=True)
    przed = ht.migawka_danych(tmp_path)
    (tmp_path / "runtime" / "skrypty" / "x_meta.json").write_text("{}", encoding="utf-8")
    (tmp_path / "skrypty").mkdir()
    roznice = ht.opisz_roznice(przed, ht.migawka_danych(tmp_path))
    assert "+ runtime/skrypty/x_meta.json" in roznice and "+ skrypty/" in roznice


def test_usun_katalog_zdejmuje_read_only_i_nie_milczy(tmp_path):
    kat = tmp_path / "repo" / ".git" / "objects"
    kat.mkdir(parents=True)
    plik = kat / "ab"
    plik.write_text("x", encoding="utf-8")
    os.chmod(plik, stat.S_IREAD)                  # jak obiekty gita na Windows
    ht.usun_katalog(tmp_path / "repo")
    assert not (tmp_path / "repo").exists()
    ht.usun_katalog(tmp_path / "nie_ma")          # brak katalogu to nie blad


def test_detektor_zapisu_bez_ensure():
    zly = "def f(p):\n    open(p, 'w').write('x')\n"
    dobry = ("def f(p):\n    os.makedirs(os.path.dirname(p), exist_ok=True)\n"
             "    open(p, 'w').write('x')\n")
    odczyt = "def f(p):\n    return open(p).read()\n"
    path = "def f(p):\n    p.write_text('x')\n"
    assert ht.zapisy_bez_ensure(zly) == ["f"]
    assert ht.zapisy_bez_ensure(dobry) == []
    assert ht.zapisy_bez_ensure(odczyt) == []
    assert ht.zapisy_bez_ensure(path) == ["f"]


def test_detektor_tlumionego_sprzatania():
    assert ht.tlumione_sprzatanie("shutil.rmtree(k, ignore_errors=True)") == [1]
    assert ht.tlumione_sprzatanie("shutil.rmtree(k, ignore_errors=False)") == []
    assert ht.tlumione_sprzatanie("shutil.rmtree(k, onexc=f)") == []


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
