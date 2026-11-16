"""conftest.py - bramka higieny testow (v19.20.0), logika w `higiena_testow.py`.

Kazdy test musi zostawic swiat taki, jaki zastal: katalog roboczy, zmienne
srodowiskowe, skalarne globale modulow projektu, katalogi danych repo, pliki
nieśledzone i katalogi z `tempfile.mkdtemp`. Naruszenie = ERROR w teardownie
TEGO testu (albo pliku), z lista roznic - nie porazka innego testu w innym
pliku, zalezna od kolejnosci przebiegu.

Naprawa przecieku: `monkeypatch` (setattr/setenv/chdir przywraca sam),
`tmp_path` zamiast `mkdtemp`, `try/finally` wokol podmiany globali.
"""

from __future__ import annotations

import os
import shutil
import tempfile

import pytest

import higiena_testow as ht

_UTWORZONE_TEMP: list[str] = []


@pytest.fixture(autouse=True, scope="session")
def _sledz_mkdtemp():
    """Rejestruje KAZDY katalog z `tempfile.mkdtemp` (takze z `TemporaryDirectory`)."""
    oryginal = tempfile.mkdtemp

    def mkdtemp(*args, **kwargs):
        sciezka = oryginal(*args, **kwargs)
        _UTWORZONE_TEMP.append(os.fspath(sciezka))
        return sciezka

    tempfile.mkdtemp = mkdtemp
    try:
        yield
    finally:
        tempfile.mkdtemp = oryginal


def _poza_repo(request) -> bool:
    """Testy spoza korzenia (np. `skrypty/bgt`, inny projekt z wlasnym
    `pytest.ini`) bramki nie dostaja - ich higiena nie jest nasza sprawa."""
    return request.path.parent.resolve() != ht.KORZEN


@pytest.fixture(autouse=True, scope="module")
def _higiena_pliku(request):
    if _poza_repo(request):
        yield
        return
    przed = ht.migawka_git()
    yield
    roznice = ht.opisz_roznice(przed, ht.migawka_git())
    if roznice:
        pytest.fail(
            f"{request.module.__name__}: the test file left the repository "
            f"changed (git status):\n  " + "\n  ".join(roznice),
            pytrace=False)


@pytest.fixture(autouse=True)
def _higiena_testu(request, _sledz_mkdtemp):
    if _poza_repo(request):
        yield
        return
    cwd = os.getcwd()
    env = dict(os.environ)
    globale = ht.migawka_globali(ht.moduly_projektu())
    dane = ht.migawka_danych()
    temp_od = len(_UTWORZONE_TEMP)
    yield
    problemy: list[str] = []
    if os.getcwd() != cwd:
        problemy.append(f"working directory: {cwd!r} -> {os.getcwd()!r}")
        os.chdir(cwd)
    problemy += [f"env {z}" for z in ht.zmiany_srodowiska(env, dict(os.environ))]
    problemy += [f"global {z}" for z in ht.zmiany_globali(globale, ht.moduly_projektu())]
    problemy += [f"data dir {z}" for z in ht.opisz_roznice(dane, ht.migawka_danych())]
    for sciezka in _UTWORZONE_TEMP[temp_od:]:
        if os.path.exists(sciezka):
            problemy.append(f"mkdtemp left behind: {sciezka}")
            shutil.rmtree(sciezka, ignore_errors=True)
    if problemy:
        pytest.fail(
            f"{request.node.nodeid} did not restore what it changed "
            f"(see conftest.py):\n  " + "\n  ".join(problemy),
            pytrace=False)
