"""
przelicznik_testow.py — liczby testów cytowane w CONTRIBUTING.md (v19.15).

CONTRIBUTING.md mówił „thirteen regression test files (179 assertions, ~13 s)”,
gdy repo miało 44 pliki `test_*.py` i 850 testów (zmierzone 2026-10-20): liczba
słowem i czas w prozie nie mają żadnej bramki, więc rozjeżdżają się po cichu.
To narzędzie liczy pliki i ZEBRANE testy (`pytest --collect-only -q` — bez
uruchamiania, bez sieci) i porównuje je ze zdaniem w CONTRIBUTING.md:

    There are <N> regression test files (<M> tests, ...

Czasu NIE liczy: zależy od maszyny, a prawdziwy przebieg kosztuje minutę —
proza mówi o nim tylko zaokrąglenie, którego narzędzie nie udaje, że sprawdza.

Dodatkowo: każdy `test_*.py` wymieniony w TABELI CONTRIBUTING.md musi istnieć
(tabela „What you touched → what has an object”).

Uruchom:
    .venv/Scripts/python przelicznik_testow.py            # raport
    .venv/Scripts/python przelicznik_testow.py --sprawdz  # kod 1 przy rozjeździe
    .venv/Scripts/python przelicznik_testow.py --zapisz   # wpisuje liczby

Bramka: `test_kanon_testow.py` (ten sam plik, który CONTRIBUTING każe uruchomić
po dodaniu nowego `test_*.py`).
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

KORZEN = Path(__file__).parent
CONTRIBUTING = KORZEN / "CONTRIBUTING.md"
ZDANIE = re.compile(r"There are (\d+) regression test files \((\d+) tests")
WZMIANKA = re.compile(r"\btest_\w+\.py\b")


def pliki_testowe() -> list[Path]:
    return sorted(KORZEN.glob("test_*.py"))


def zebrane_testy() -> int:
    """Liczba testów zebranych przez pytesta (bez uruchamiania)."""
    wynik = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider",
         *[p.name for p in pliki_testowe()]],
        cwd=KORZEN, capture_output=True, text=True, encoding="utf-8", errors="replace")
    trafienie = re.search(r"(\d+) tests? collected", wynik.stdout)
    if wynik.returncode != 0 or not trafienie:
        raise RuntimeError("pytest --collect-only failed:\n" + wynik.stdout[-2000:] + wynik.stderr[-2000:])
    return int(trafienie.group(1))


def sprawdz(tekst: str, pliki: int, testy: int) -> list[str]:
    """Lista rozjazdów (pusta = zgodnie)."""
    bledy = []
    trafienia = ZDANIE.findall(tekst)
    if len(trafienia) != 1:
        bledy.append(f"CONTRIBUTING.md: expected exactly one sentence matching "
                     f"'{ZDANIE.pattern}', found {len(trafienia)}")
    else:
        n, m = map(int, trafienia[0])
        if n != pliki:
            bledy.append(f"CONTRIBUTING.md says {n} test files, the repo has {pliki}")
        if m != testy:
            bledy.append(f"CONTRIBUTING.md says {m} tests, pytest collects {testy}")
    istniejace = {p.name for p in pliki_testowe()}
    # Tylko wiersze tabel: proza ma przykłady w rodzaju `test_something.py`.
    tabele = "\n".join(w for w in tekst.splitlines() if w.lstrip().startswith("|"))
    for nazwa in sorted(set(WZMIANKA.findall(tabele)) - istniejace):
        bledy.append(f"a table in CONTRIBUTING.md names {nazwa}, which does not exist")
    return bledy


def zapisz(tekst: str, pliki: int, testy: int) -> str:
    nowy, ile = ZDANIE.subn(f"There are {pliki} regression test files ({testy} tests", tekst)
    if ile != 1:
        raise RuntimeError(f"expected exactly one sentence matching '{ZDANIE.pattern}', found {ile}")
    return nowy


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Recount test files and collected tests quoted in CONTRIBUTING.md.")
    tryb = parser.add_mutually_exclusive_group()
    tryb.add_argument("--sprawdz", action="store_true", help="exit 1 when CONTRIBUTING.md has drifted")
    tryb.add_argument("--zapisz", action="store_true", help="write the current numbers into CONTRIBUTING.md")
    args = parser.parse_args(argv)

    pliki, testy = len(pliki_testowe()), zebrane_testy()
    surowy = CONTRIBUTING.read_bytes().decode("utf-8")
    print(f"Test files: {pliki}, collected tests: {testy}")
    if args.zapisz:
        CONTRIBUTING.write_bytes(zapisz(surowy, pliki, testy).encode("utf-8"))
        print("✅ CONTRIBUTING.md updated.")
    bledy = sprawdz(CONTRIBUTING.read_bytes().decode("utf-8"), pliki, testy)
    for b in bledy:
        print("❌ " + b)
    if not bledy:
        print("✅ CONTRIBUTING.md matches the repository.")
    return 1 if bledy and (args.sprawdz or args.zapisz) else 0


if __name__ == "__main__":
    sys.exit(main())
