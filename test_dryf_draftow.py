"""
test_dryf_draftow.py - bramka dryfu: draft zmienia przeklad, choc zrodlo PL nie (v19.20.0).

Dlug 19.18.0, zmierzony: rerun brata przepisal wyrecenzowane brzmienie takze
poza celem zmiany (`[taytetaan kasin]` -> `[taytettava kasin]`). Baza
porownania to commit, ktory ostatni dotknal pliku docelowego; jednostka jest
"nieruszona", gdy jej wartosc PL w tym commicie rowna sie dzisiejszej.

Uruchom:  .venv/Scripts/python -m pytest test_dryf_draftow.py -q
Albo jako skrypt (deleguje do pytesta): .venv/Scripts/python test_dryf_draftow.py
"""

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import przeglad_tlumaczen
import tlumacz_rdzen as tr

KORZEN = Path(__file__).parent


def _j(sciezka: tuple, cel: str, zrodlo: str = "") -> tr.Jednostka:
    j = tr.Jednostka(0, "pole", "proza", ("sciezka", *sciezka), zrodlo)
    j.cel = cel
    return j


def test_logika_dryfu():
    pl_bazy = {"a": "stare PL", "b": "zmienione PL", "c": "PL"}
    pl_dzis = {"a": "stare PL", "b": "NOWE PL", "c": "PL"}
    cel_bazy = {"a": "[täytetään käsin]", "b": "vanha", "c": "sama"}
    jednostki = [_j(("a",), "[täytettävä käsin]"),     # PL ten sam, przeklad inny -> dryf
                 _j(("b",), "uusi"),                    # PL zmienione -> legalne
                 _j(("c",), "sama"),                    # bez zmian
                 _j(("d",), "nowy klucz")]              # brak w bazie -> pomijamy
    assert tr.dryf_jednostek(jednostki, pl_bazy, cel_bazy, pl_dzis) == [
        ("a", "[täytetään käsin]", "[täytettävä käsin]")]


def _git(katalog: Path, *argumenty: str) -> None:
    subprocess.run(["git", *argumenty], cwd=katalog, check=True, capture_output=True)


def test_na_repo_gita(tmp_path, capsys):
    (tmp_path / "pl").mkdir()
    (tmp_path / "fi").mkdir()
    pl, fi = tmp_path / "pl" / "x.yaml", tmp_path / "fi" / "x.yaml"
    pl.write_text("a: jeden\nb: dwa\n", encoding="utf-8")
    fi.write_text("a: yksi\nb: kaksi\n", encoding="utf-8")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@example.invalid")
    _git(tmp_path, "config", "user.name", "t")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "baza")
    # Zmiana PL tylko w `b`; draft przepisuje oba klucze.
    pl.write_text("a: jeden\nb: dwa i pol\n", encoding="utf-8")
    fi.write_text("a: yksi kappale\nb: kaksi ja puoli\n", encoding="utf-8")
    wynik = tr.zbierz_dryf_niezmienionych(
        {("fi", "x.yaml"): [_j(("a",), "yksi kappale"), _j(("b",), "kaksi ja puoli")]},
        {("fi", "x.yaml"): (pl, fi)}, tmp_path)
    assert wynik == {("fi", "x.yaml"): [("a", "yksi", "yksi kappale")]}
    assert "1 unit(s) reworded" in capsys.readouterr().out
    tekst = przeglad_tlumaczen._tekst_promptu("buduj_wielojezyczne_tryby.py",
                                              [("fi", "x.yaml")], None, wynik)
    assert "Reworded although the Polish source did not change" in tekst


def test_plik_bez_historii_jest_pomijany(tmp_path):
    _git(tmp_path, "init", "-q")
    cel = tmp_path / "nowy.yaml"
    cel.write_text("a: x\n", encoding="utf-8")
    assert tr.zbierz_dryf_niezmienionych(
        {("fi", "nowy.yaml"): [_j(("a",), "x")]},
        {("fi", "nowy.yaml"): (cel, cel)}, tmp_path) == {}


def test_docs_na_zywym_repo_bez_zmian_nie_ma_dryfu():
    """Draft identyczny z commitem = zero dryfu (kontrola odwrotna na prawdziwym pliku)."""
    if not (KORZEN / ".git").exists():
        pytest.skip("source archive without git")
    import buduj_wielojezyczne_docs as bd
    cel = bd.DICT_DIR / "fi" / bd.FOLDER_GUI / bd.FOLDER_DOKUMENTACJA / "manual.yaml"
    wynik_git = subprocess.run(["git", "diff", "--quiet", "--", str(cel)], cwd=KORZEN)
    if wynik_git.returncode != 0:
        pytest.skip("fi/manual.yaml has local changes")
    assert bd._dryf_draftow([("fi", "manual.yaml")]) == {}


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
