"""Testy `.github/scripts/cykl_wersji.py` — jawne otwarcie cyklu wydania.

Każdy test buduje mini-repo gita w katalogu tymczasowym: `main.py` importuje
`silnik.py` (runtime), `narzedzie.py` jest dev-toolingiem. Bliźniak:
`.github/scripts/test_cykl_wersji.py` w accessible_text_analyst.

Uruchom:  .venv/Scripts/python -m pytest test_cykl_wersji.py -q
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_KORZEN = Path(__file__).parent
sys.path.insert(0, str(_KORZEN / ".github" / "scripts"))

import cykl_wersji as cw  # noqa: E402


def _git(katalog: Path, *argumenty: str) -> None:
    subprocess.run(["git", *argumenty], cwd=katalog, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@example.invalid")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "main.py").write_text("import silnik\n", encoding="utf-8")
    (tmp_path / "silnik.py").write_text("X = 1\n", encoding="utf-8")
    (tmp_path / "narzedzie.py").write_text("Y = 1\n", encoding="utf-8")
    (tmp_path / "VERSION").write_text("1.2.0\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "v1.2.0")
    _git(tmp_path, "tag", "v1.2.0")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_spoczynek_po_wydaniu(repo):
    assert cw.stan_cyklu()["stan"] == "wydany"


def test_dev_tooling_nie_otwiera_cyklu(repo):
    (repo / "narzedzie.py").write_text("Y = 2\n", encoding="utf-8")
    assert cw.stan_cyklu()["stan"] == "wydany"


def test_zmiana_runtime_bez_wip_to_blad(repo):
    """Sedno: niezacommitowana zmiana runtime przy VERSION = tag."""
    (repo / "silnik.py").write_text("X = 2\n", encoding="utf-8")
    stan = cw.stan_cyklu()
    assert stan["stan"] == "nieotwarty"
    assert any("silnik.py" in w for w in stan["winowajcy"])
    assert cw.main([]) == 1


def test_nowy_niesledzony_plik_wydania_bez_wip_to_blad(repo):
    """Audyt 19.19: `git diff <tag>` nie widzi plików nieśledzonych — nowy plik
    treści wydania (tu spec PyInstallera) przechodził jako „wydany”."""
    (repo / "nowy.spec").write_text("a = 1\n", encoding="utf-8")
    stan = cw.stan_cyklu()
    assert stan["stan"] == "nieotwarty"
    assert any("nowy.spec" in w for w in stan["winowajcy"])


def test_zacommitowana_zmiana_danych_bez_wip_to_blad(repo):
    (repo / "dictionaries").mkdir()
    (repo / "dictionaries" / "a.yaml").write_text("a: 1\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "dane")
    assert cw.stan_cyklu()["stan"] == "nieotwarty"


@pytest.mark.parametrize("wersja,typ", [("1.3.0-WIP", "minor/major"), ("1.3-WIP", "minor/major"),
                                        ("2.0.0-WIP", "minor/major"), ("1.2.1-WIP", "patch")])
def test_wip_otwiera_cykl(repo, wersja, typ):
    (repo / "silnik.py").write_text("X = 2\n", encoding="utf-8")
    (repo / "VERSION").write_text(wersja + "\n", encoding="utf-8")
    stan = cw.stan_cyklu()
    assert (stan["stan"], stan["typ"]) == ("wip", typ)
    assert cw.main([]) == 0


def test_wip_wydanej_wersji_to_blad(repo):
    (repo / "VERSION").write_text("1.2.0-WIP\n", encoding="utf-8")
    assert cw.stan_cyklu()["stan"] == "wip_wydanej"


def test_zamykanie_cyklu(repo):
    (repo / "VERSION").write_text("1.3.0\n", encoding="utf-8")
    assert cw.stan_cyklu()["stan"] == "zamykanie"


def test_bez_tagow_nie_wiadomo(repo):
    _git(repo, "tag", "-d", "v1.2.0")
    (repo / "VERSION").write_text("1.3.0\n", encoding="utf-8")
    assert cw.stan_cyklu()["stan"] == "nieznany"


def test_zly_format_version(repo):
    (repo / "VERSION").write_text("dziewietnascie\n", encoding="utf-8")
    assert cw.stan_cyklu()["stan"] == "nieznany"


def test_prawdziwe_repo_ma_czytelny_stan():
    """Na żywym repo stan musi dać się orzec (nie `nieznany`) — inaczej hak startu milczy."""
    if not (_KORZEN / ".git").exists():
        pytest.skip("source archive without git")
    import os
    stary = os.getcwd()
    os.chdir(_KORZEN)
    try:
        if not cw._git("tag", "--list", "v*")[1]:
            pytest.skip("clone without tags (CI checkout)")
        assert cw.stan_cyklu()["stan"] != "nieznany"
    finally:
        os.chdir(stary)


# Uruchomienie jako skrypt — deleguje do pytesta (kanon v19.2.1).
if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
