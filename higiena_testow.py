"""higiena_testow.py - test zostawia swiat taki, jaki zastal (v19.20.0).

Dlug 19.20: zestaw zielony w kolejnosci alfabetycznej padal w odwrotnej
(36 porazek + 14 bledow), bo testy zostawialy po sobie stan, z ktorego
korzystal nastepny plik. Przebieg w odwrotnej kolejnosci znajduje tylko te
wycieki, ktore akurat trafia na czytelnika; decyzja maintainera 2026-11-16:
zamiast tego KAZDY wyciek ma byc bledem samego testu, ktory go zrobil.

Zasada: test (z fixture'ami) konczy sie w tym samym swiecie, w ktorym zaczal.
`conftest.py` robi migawke przed i porownanie po; ten modul trzyma czyste
funkcje migawek, zeby dalo sie je przetestowac bez uruchamiania pytesta
w pytescie (`test_higiena_testow.py`).

Co jest swiatem:
  * katalog roboczy procesu i zmienne srodowiskowe;
  * globalne SKALARY modulow projektu (str/int/float/bool/None/Path) -
    tak wyciekal `core_poliglota.DICTIONARIES_DIR` wskazujacy skasowany
    katalog tymczasowy;
  * zawartosc repo: pliki nieśledzone (`git status`, per plik testowy -
    70 ms) i katalogi danych ignorowane przez git (per test);
  * katalogi z `tempfile.mkdtemp` (takze wewnatrz `TemporaryDirectory`),
    ktore po tescie nadal istnieja - niepelne sprzatanie, czesto `rmtree`
    z `ignore_errors=True` na repo git z plikami tylko do odczytu.

Druga strona tej samej dziury - kod, ktory pisze do katalogu, nie upewniajac
sie, ze katalog istnieje - ma bramke STATYCZNA (`zapisy_bez_ensure` +
`ZAPISY_BEZ_ENSURE`, sprawdzana w `test_higiena_testow.py`): zapis pliku
wymaga `mkdir`/`makedirs` w tej samej funkcji albo wpisu z powodem. Ciche
sprzatanie w testach (`rmtree(ignore_errors=True)`) tez jest bledem kanonu -
zamiast niego `usun_katalog`.

Wyjatki od regul (`DOZWOLONE_ZMIANY_GLOBALI`) wymagaja powodu w komentarzu:
to globale, ktore z zalozenia ucza sie raz na proces (leniwa inicjalizacja).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path, PurePath

KORZEN = Path(__file__).resolve().parent

_SKALARY = (str, int, float, bool, type(None), PurePath)

# Katalogi danych ignorowane przez git, ktore testy moga zasmiecic. Listowane
# rekurencyjnie per test (male); `skrypty/` tylko pierwszy poziom - siedzi tam
# m.in. 40 tys. plikow innego projektu (`skrypty/bgt`).
_DANE_REKURENCYJNIE = ("runtime", "opowiesci")
_DANE_PLYTKO = ("skrypty",)

# (modul, nazwa) -> powod. Globale, ktore ZGODNIE Z PROJEKTEM zmieniaja sie raz
# na proces; kazdy wpis musi miec powod, a wpis martwy zglasza test.
DOZWOLONE_ZMIANY_GLOBALI: dict[tuple[str, str], str] = {}


# nazwa modulu -> czy z korzenia repo. `Path.resolve()` na Windows jest drogie,
# a `sys.modules` liczy tysiace pozycji: bez pamieci przebieg trwal 12 min
# zamiast 1,5 (zmierzone 2026-11-16).
_CZY_PROJEKTU: dict[str, bool] = {}
_KORZEN_STR = os.path.normcase(str(KORZEN))


def _z_korzenia(nazwa: str, modul: object) -> bool:
    wynik = _CZY_PROJEKTU.get(nazwa)
    if wynik is None:
        plik = getattr(modul, "__file__", None)
        wynik = (bool(plik) and not nazwa.startswith(("test_", "conftest"))
                 and nazwa != __name__
                 and os.path.normcase(os.path.dirname(os.path.abspath(plik))) == _KORZEN_STR)
        _CZY_PROJEKTU[nazwa] = wynik
    return wynik


# ---------------------------------------------------------------------------
# Druga strona: kod piszacy plik bez upewnienia sie, ze katalog istnieje
# ---------------------------------------------------------------------------
# Funkcja, ktora pisze plik (`open` w trybie w/a/x, `write_text`,
# `write_bytes`), musi w tym samym ciele wolac `mkdir`/`makedirs` - albo stac
# tu z powodem. Zmierzone przy wprowadzeniu bramki (2026-11-16): 53 funkcje
# piszace, 23 bez ensure, w tym `audyt_zaleznosci.zamroz` piszacy do
# gitignorowanego `skrypty/` (swiezy klon = FileNotFoundError) - naprawione.
# Klucz: "plik.py:funkcja".
ZAPISY_BEZ_ENSURE: dict[str, str] = {
    "audyt_leakow.py:zapisz_baseline": "baseline w korzeniu repo (sledzony)",
    "generuj_dokumentacje.py:zapisz_baseline_bliskich": "baseline w korzeniu repo (sledzony)",
    "przelicznik_testow.py:main": "CONTRIBUTING.md w korzeniu repo",
    "refresh_languages.py:zapisz_rejestr": "jezyki_docelowe.yaml w korzeniu repo",
    "bledy_ai.py:zapisz_diagnostyke": "error_log.txt w KATALOG_BAZOWY (katalog exe/repo)",
    "main.py:_zapisz_log_bledu": "error_log.txt w KATALOG_BAZOWY (katalog exe/repo)",
    "main.py:_on_action_btn": "golden_key.env w KATALOG_BAZOWY (katalog exe/repo)",
    "buduj_wielojezyczne_akcenty.py:finalizuj": "nadpisuje plik paczki przeczytany chwile wczesniej",
    "buduj_wielojezyczne_docs.py:finalizuj_naglowek_docs": "nadpisuje plik paczki przeczytany chwile wczesniej",
    "buduj_wielojezyczne_opowiesci.py:main": "nadpisuje plik paczki przeczytany chwile wczesniej",
    "buduj_wielojezyczne_poliglota.py:_tryb_finalizuj": "nadpisuje plik paczki przeczytany chwile wczesniej",
    "buduj_wielojezyczne_tryby.py:main": "nadpisuje plik paczki przeczytany chwile wczesniej",
    "buduj_wielojezyczne_ui.py:finalizuj_naglowek_ui": "nadpisuje plik paczki przeczytany chwile wczesniej",
    "gui_opowiesci.py:_on_edytuj_stan": "nadpisuje plik stanu przeczytany chwile wczesniej",
    "gui_manager_regul.py:_on_duplikuj": "kopia obok istniejacego pliku reguly (ten sam katalog)",
    "tlumacz_ai.py:uniewaznij_cache_tlumaczenia": "obcina ISTNIEJACY plik, ktorego nie dalo sie skasowac",
    "tlumacz_ai.py:tlumacz_dlugi_tekst": "katalog zapewnia `_sciezka_pliku_tymczasowego` (makedirs)",
    "core_poliglota.py:zapisz_wynik": "katalog pliku zrodlowego wybranego przez usera",
    "core_updater.py:pobierz_instalator": "tempfile.gettempdir() istnieje z definicji",
    "build_release.py:main": "dist/ i installer.iss istnieja po kroku PyInstallera",
}


def _jest_zapisem(wezel) -> bool:
    import ast
    f = wezel.func
    nazwa = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
    if nazwa in ("write_text", "write_bytes"):
        return True
    if nazwa != "open":
        return False
    tryb = None
    if len(wezel.args) >= 2 and isinstance(wezel.args[1], ast.Constant):
        tryb = wezel.args[1].value
    for kw in wezel.keywords:
        if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
            tryb = kw.value.value
    return isinstance(tryb, str) and any(c in tryb for c in "wax")


def zapisy_bez_ensure(tekst: str) -> list[str]:
    """Nazwy funkcji, ktore pisza plik i nie wolaja `mkdir`/`makedirs`."""
    import ast
    wynik = []
    for fn in ast.walk(ast.parse(tekst)):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        wywolania = [w for w in ast.walk(fn) if isinstance(w, ast.Call)]
        if not any(_jest_zapisem(w) for w in wywolania):
            continue
        if not any(getattr(w.func, "attr", getattr(w.func, "id", "")) in ("mkdir", "makedirs")
                   for w in wywolania):
            wynik.append(fn.name)
    return wynik


def tlumione_sprzatanie(tekst: str) -> list[int]:
    """Linie `rmtree(..., ignore_errors=<prawda>)` - ciche, niepelne sprzatanie."""
    import ast
    linie = []
    for w in ast.walk(ast.parse(tekst)):
        if (isinstance(w, ast.Call)
                and getattr(w.func, "attr", getattr(w.func, "id", "")) == "rmtree"
                and any(kw.arg == "ignore_errors"
                        and not (isinstance(kw.value, ast.Constant) and not kw.value.value)
                        for kw in w.keywords)):
            linie.append(w.lineno)
    return linie


def usun_katalog(katalog: os.PathLike | str) -> None:
    """Usuwa katalog tymczasowy testu W CALOSCI albo rzuca - nigdy po cichu.

    `shutil.rmtree(..., ignore_errors=True)` na repo git zostawial na Windows
    katalog z read-only `.git/objects` i milczal (zmierzone: 5 z 6 repo
    w `%TEMP%` po dwoch seriach). Tu flaga read-only jest zdejmowana
    (`onexc`, nie `onerror` - ten wypadl w Pythonie 3.14), a blad, ktorego
    to nie naprawi, leci do testu. Kanon testow zabrania `ignore_errors=True`.
    """
    import shutil
    import stat

    def _odblokuj(func, sciezka, _wyjatek):
        os.chmod(sciezka, stat.S_IWRITE)
        func(sciezka)

    if os.path.exists(katalog):
        shutil.rmtree(katalog, onexc=_odblokuj)


def moduly_projektu() -> dict[str, object]:
    """Zaimportowane moduly z korzenia repo (bez testow i conftestu)."""
    return {n: m for n, m in list(sys.modules.items()) if _z_korzenia(n, m)}


def migawka_globali(moduly: dict[str, object]) -> dict[tuple[str, str], object]:
    """Skalarne globale modulow: (modul, nazwa) -> wartosc."""
    wynik = {}
    for nazwa_mod, modul in moduly.items():
        for nazwa, wartosc in list(vars(modul).items()):
            if nazwa.startswith("__"):
                continue
            if isinstance(wartosc, _SKALARY):
                wynik[(nazwa_mod, nazwa)] = wartosc
    return wynik


def zmiany_globali(przed: dict, moduly_po: dict[str, object]) -> list[str]:
    """Globale z migawki `przed`, ktorych wartosc sie zmienila."""
    zmiany = []
    for (nazwa_mod, nazwa), stara in przed.items():
        if (nazwa_mod, nazwa) in DOZWOLONE_ZMIANY_GLOBALI:
            continue
        modul = moduly_po.get(nazwa_mod)
        if modul is None:
            continue
        nowa = vars(modul).get(nazwa, "<usuniety>")
        if stara is None and not isinstance(nowa, _SKALARY):
            continue   # leniwa inicjalizacja (detektor, cache wzorcow): None -> obiekt
        if type(nowa) is not type(stara) or nowa != stara:
            zmiany.append(f"{nazwa_mod}.{nazwa}: {stara!r} -> {nowa!r}")
    return zmiany


def migawka_danych(korzen: Path = KORZEN) -> frozenset[str]:
    """Pliki i katalogi w ignorowanych katalogach danych (sciezki wzgledne)."""
    wynik: set[str] = set()
    for nazwa in _DANE_REKURENCYJNIE:
        baza = korzen / nazwa
        if baza.is_dir():
            wynik.add(nazwa + "/")
            for sciezka, katalogi, pliki in os.walk(baza):
                katalogi[:] = [k for k in katalogi if k != "__pycache__"]
                rel = Path(sciezka).relative_to(korzen).as_posix()
                wynik.update(f"{rel}/{k}/" for k in katalogi)
                wynik.update(f"{rel}/{p}" for p in pliki)
    for nazwa in _DANE_PLYTKO:
        baza = korzen / nazwa
        if baza.is_dir():
            wynik.add(nazwa + "/")
            wynik.update(f"{nazwa}/{p.name}" for p in baza.iterdir()
                         if p.name != "__pycache__")
    return frozenset(wynik)


def migawka_git(korzen: Path = KORZEN) -> frozenset[str]:
    """`git status --porcelain -uall` bez `__pycache__` (import go tworzy)."""
    try:
        wynik = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=korzen, capture_output=True, text=True, encoding="utf-8",
            timeout=30, check=True)
    except (OSError, subprocess.SubprocessError):
        return frozenset()
    return frozenset(l for l in wynik.stdout.splitlines()
                     if l.strip() and "__pycache__" not in l)


def opisz_roznice(przed: frozenset[str], po: frozenset[str]) -> list[str]:
    nowe = sorted(po - przed)
    znikniete = sorted(przed - po)
    return ([f"+ {s}" for s in nowe] + [f"- {s}" for s in znikniete])


# Zmienne, ktore ustawia sam pytest w trakcie testu.
_ENV_PYTESTA = frozenset({"PYTEST_CURRENT_TEST"})


def zmiany_srodowiska(przed: dict[str, str], po: dict[str, str]) -> list[str]:
    zmiany = []
    for klucz in sorted((set(przed) | set(po)) - _ENV_PYTESTA):
        if przed.get(klucz) != po.get(klucz):
            # Tylko CZY ustawiona, nigdy wartosc: wyciekiem bywa `load_dotenv`
            # z `golden_key.env`, a raport testow trafia do logow i transkryptow
            # (zmierzone 2026-11-16 - pierwsza wersja bramki drukowala klucze).
            zmiany.append(f"{klucz}: {_stan(przed.get(klucz))} -> {_stan(po.get(klucz))}")
    return zmiany


def _stan(wartosc: str | None) -> str:
    return "unset" if wartosc is None else f"set ({len(wartosc)} chars)"
