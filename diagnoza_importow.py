#!/usr/bin/env python
"""
diagnoza_importow.py — ostrzeżenia PyInstallera i import każdego modułu (v19.20.0).

Dług 19.0.0: `Hidden import "tzdata" not found!` było widać tylko przy
uważnym czytaniu logu buildu, a `warn-<spec>.txt` ma ~350 wpisów „missing
module”, prawie wszystkie z bibliotek trzecich (zmierzone 2026-11-15: 354).
Sygnał tonął w szumie, więc nikt go nie czytał. Narzędzie odwraca pytanie:
nie „co PyInstaller zgłosił”, tylko „co zgłosił O NASZYM kodzie, czego nie
znamy” — i odpowiada w trzech trybach:

  * ``--moduly``  — importuje KAŻDY moduł projektu w osobnym procesie (ze
    źródła, bez buildu) i zgłasza błąd importu oraz ostrzeżenia rzucone przy
    imporcie. Ta część działa w każdym projekcie uruchamianym ze źródła —
    dlatego plik jest samą biblioteką standardową i ma być bliźniakiem dla
    accessible_text_analyst (tam bez buildu, tylko ten tryb).
  * ``--warn [PLIK]`` / ``--log PLIK`` — z raportu PyInstallera tylko wpisy,
    w których importującym jest NASZ moduł, i linie ``Hidden import … not
    found``; minus :data:`ZNANE` (każde z powodem).
  * ``--kto MODUL`` — który nasz moduł REALNIE wciąga wskazany moduł (import
    w osobnym procesie, sprawdzenie ``sys.modules``). To jest odruch z
    CONTRIBUTING („Hidden import X not found” mówi o HOOKU, nie o naszym
    kodzie): zanim doinstalujesz X, ustal, kto i czy po naszych ścieżkach.

`build_release.py` zapisuje log PyInstallera do ``build/pyinstaller_log.txt``
i po buildzie woła :func:`raport_buildu` — wyłącznie ostrzega, nie blokuje.

Uruchom:
    .venv/Scripts/python diagnoza_importow.py --moduly
    .venv/Scripts/python diagnoza_importow.py --warn --log build/pyinstaller_log.txt
    .venv/Scripts/python diagnoza_importow.py --kto tzdata
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

KORZEN = Path(__file__).resolve().parent
WARN_DOMYSLNY = KORZEN / "build" / "rezyser_audio" / "warn-rezyser_audio.txt"
LOG_DOMYSLNY = KORZEN / "build" / "pyinstaller_log.txt"

# Znane ostrzeżenia: klucz = brakujący moduł, wartość = DLACZEGO to nie usterka.
# Wpis bez powodu się nie liczy — to lista decyzji, nie zbiór wyciszeń.
ZNANE: dict[str, str] = {
    "tzdata": "hidden import from the zoneinfo hook (pulled by pydantic); nothing "
              "here has a ZoneInfo-typed field, so the 1.7 MiB package would serve "
              "an unreachable path (decision 19.0, CONTRIBUTING)",
    "collections.abc": "PyInstaller 6.x misreports this stdlib submodule as missing "
                       "for every importer on Python 3.14; the frozen app imports "
                       "it fine (every release since 19.0 starts)",
}

_RE_BRAK = re.compile(r"^missing module named '?([^' ]+)'? - imported by (.*)$")
_RE_IMPORTER = re.compile(r"([A-Za-z0-9_.]+) \(([^)]*)\)")
_RE_HIDDEN = re.compile(r"Hidden import ['\"]([^'\"]+)['\"] not found")


def moduly_projektu(korzen: Path = KORZEN) -> list[str]:
    """Moduły w korzeniu projektu (bez testów) — „nasz kod” dla raportu."""
    return sorted(p.stem for p in korzen.glob("*.py") if not p.stem.startswith("test_"))


def parsuj_warn(tekst: str) -> dict[str, list[tuple[str, str]]]:
    """``{brakujący: [(importujący, rodzaje), …]}`` z ``warn-<spec>.txt``."""
    wynik: dict[str, list[tuple[str, str]]] = {}
    for linia in tekst.splitlines():
        m = _RE_BRAK.match(linia.strip())
        if m:
            wynik[m.group(1)] = _RE_IMPORTER.findall(m.group(2))
    return wynik


def ostrzezenia_naszego_kodu(warn: dict[str, list[tuple[str, str]]], nasze: set[str],
                             znane: dict[str, str] = ZNANE) -> dict[str, list[str]]:
    """Brakujące moduły importowane przez NASZ moduł, poza listą znanych."""
    wynik: dict[str, list[str]] = {}
    for brak, importerzy in warn.items():
        if brak in znane or brak.split(".")[0] in nasze:
            continue
        # `from fontTools.ttLib import TTFont` → PyInstaller sprawdza, czy
        # `TTFont` nie jest podmodułem, i zgłasza „missing module” (zmierzone
        # 2026-11-15: TTFont, lingua.Language, lingua.LanguageDetectorBuilder).
        # Człon z wielkiej litery przy pakiecie, którego NIE ma na liście
        # brakujących, to klasa — nie usterka bundla.
        rodzic, _, czlon = brak.rpartition(".")
        if rodzic and czlon[:1].isupper() and rodzic not in warn:
            continue
        nasi = [f"{imp} ({rodzaj})" for imp, rodzaj in importerzy
                if imp.split(".")[0] in nasze]
        if nasi:
            wynik[brak] = nasi
    return wynik


def hidden_z_logu(tekst: str, znane: dict[str, str] = ZNANE) -> list[str]:
    """Nieznane ``Hidden import … not found`` z logu PyInstallera."""
    return sorted({m.group(1) for m in _RE_HIDDEN.finditer(tekst)} - set(znane))


_SONDA_IMPORTU = (
    "import json, sys, warnings\n"
    "warnings.simplefilter('always')\n"
    "with warnings.catch_warnings(record=True) as w:\n"
    "    import importlib; importlib.import_module(sys.argv[1])\n"
    "print(json.dumps({'ostrzezenia': sorted({f'{x.category.__name__}: {x.message}' "
    "for x in w}), 'moduly': sorted(sys.modules)}))\n"
)


def importuj(modul: str, korzen: Path = KORZEN, python: str = sys.executable) -> dict:
    """Import jednego modułu w osobnym procesie: błąd, ostrzeżenia, sys.modules."""
    try:
        wynik = subprocess.run([python, "-c", _SONDA_IMPORTU, modul], cwd=korzen,
                               capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=120)
    except subprocess.TimeoutExpired:
        return {"blad": "timeout after 120 s (does the module run code on import?)"}
    if wynik.returncode != 0:
        ostatnia = (wynik.stderr.strip().splitlines() or ["?"])[-1]
        return {"blad": ostatnia}
    try:
        return json.loads(wynik.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"blad": f"unreadable probe output: {wynik.stdout[-200:]!r}"}


def raport_buildu(warn: Path | None = WARN_DOMYSLNY, log: Path | None = LOG_DOMYSLNY) -> bool:
    """Raport po buildzie; True = czysto. Brak plików = głośna nota, nie zielone.

    ``None`` = tego źródła nie sprawdzaj i nie raportuj (tryb, o który CLI nie
    poproszono — audyt 19.20: samo ``--log`` kończyło się fałszywą czerwienią)."""
    czysto = True
    nasze = set(moduly_projektu())
    if warn is None:
        pass
    elif warn.is_file():
        nowe = ostrzezenia_naszego_kodu(parsuj_warn(warn.read_text(encoding="utf-8",
                                                                   errors="replace")), nasze)
        for brak, kto in sorted(nowe.items()):
            czysto = False
            print(f"⚠️  PyInstaller: missing module {brak!r} imported by OUR code: "
                  f"{', '.join(kto)}")
    else:
        czysto = False
        print(f"⚠️  PyInstaller warnings not checked: {warn} does not exist.")
    if log is None:
        pass
    elif log.is_file():
        for brak in hidden_z_logu(log.read_text(encoding="utf-8", errors="replace")):
            czysto = False
            print(f"⚠️  PyInstaller: new 'Hidden import {brak} not found' — find who "
                  f"pulls it before installing it: python diagnoza_importow.py --kto {brak}")
    else:
        czysto = False
        print(f"⚠️  Hidden-import warnings not checked: {log} does not exist.")
    if czysto:
        print(f"✅ PyInstaller: nothing about our code beyond the {len(ZNANE)} known "
              f"warning(s) ({', '.join(sorted(ZNANE))}).")
    return czysto


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(
        description="PyInstaller warnings that concern OUR code, and an import probe "
                    "of every project module (works from source, no build needed).")
    parser.add_argument("--moduly", action="store_true",
                        help="Import every project module in its own process and report "
                             "import errors and warnings raised on import.")
    parser.add_argument("--warn", nargs="?", const=str(WARN_DOMYSLNY), metavar="FILE",
                        help="Check PyInstaller's warn-<spec>.txt (default: the last build).")
    parser.add_argument("--log", metavar="FILE",
                        help="Check a saved PyInstaller log for 'Hidden import ... not found'.")
    parser.add_argument("--kto", metavar="MODULE",
                        help="Which project module actually imports MODULE.")
    args = parser.parse_args(argv)
    if not (args.moduly or args.warn or args.log or args.kto):
        parser.error("choose at least one of --moduly, --warn, --log, --kto")

    kod = 0
    if args.warn or args.log:
        if not raport_buildu(Path(args.warn) if args.warn else None,
                             Path(args.log) if args.log else None):
            kod = 1
    if args.moduly or args.kto:
        moduly = moduly_projektu()
        print(f"Importing {len(moduly)} project module(s), one process each…")
        kto: list[str] = []
        for m in moduly:
            w = importuj(m)
            if "blad" in w:
                kod = 1
                print(f"❌ {m}: {w['blad']}")
                continue
            if args.moduly:
                for o in w["ostrzezenia"]:
                    print(f"⚠️  {m}: {o}")
            if args.kto and any(x == args.kto or x.startswith(args.kto + ".")
                                for x in w["moduly"]):
                kto.append(m)
        if args.kto:
            print(f"{args.kto!r} is imported by: {', '.join(kto) or 'NO project module'}")
    return kod


if __name__ == "__main__":
    sys.exit(main())
