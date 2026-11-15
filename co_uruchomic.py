#!/usr/bin/env python
"""
co_uruchomic.py — „co ruszyłeś → co ma przedmiot” jako narzędzie (v19.20.0).

Dług 19.2.1: tabela w CONTRIBUTING.md („What you touched → what has an
object”) była tylko tabelą. Dziś pełny `pytest test_*.py` trwa półtorej
minuty, więc tabela jest wygodą — ale z każdym nowym plikiem testów rośnie
koszt pełnego przebiegu i rośnie pokusa, żeby uruchomić „to, co pamiętam”.

Narzędzie NIE trzyma własnej kopii tabeli: parsuje ją z CONTRIBUTING.md przy
każdym uruchomieniu, więc dopisanie wiersza tam = nowa reguła tutaj. Pierwsza
kolumna to opis po angielsku z wzorcami w backtickach (`core_pdf.py`,
`dictionaries/**/gui/ui.yaml`, `buduj_wielojezyczne_*.py`); wzorzec bez `/`
i bez `*` dopasowuje nazwę pliku w dowolnym katalogu. Wiersz ze słowem
„other” („any other `dictionaries/**`”) bierze tylko pliki, których nie
złapał żaden wcześniejszy wiersz — dokładnie tak, jak czyta go człowiek.

Zakres zmian: `git diff --name-only <baza>` (commity od bazy + drzewo robocze)
plus pliki nieśledzone. Baza domyślnie = ostatni tag (`git describe`), czyli
„wszystko od ostatniego wydania”.

Uruchom:
    .venv/Scripts/python co_uruchomic.py               # od ostatniego tagu
    .venv/Scripts/python co_uruchomic.py --baza HEAD   # tylko niezacommitowane
    .venv/Scripts/python co_uruchomic.py --pliki a.py b.yaml
"""

from __future__ import annotations

import argparse
import fnmatch
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import dev_konsola

KORZEN = Path(__file__).resolve().parent
NAGLOWEK_TABELI = "### What you touched → what has an object"
_RE_KOD = re.compile(r"`([^`]+)`")
_RE_TEST = re.compile(r"\btest_[a-z0-9_]+\.py\b")


@dataclass
class Wiersz:
    opis: str
    uruchom: str
    wzorce: list[str]
    tylko_reszta: bool
    tylko_nowe: bool = False
    pliki: list[str] = field(default_factory=list)


def _komorki(linia: str) -> list[str]:
    srodek = linia.strip()[1:-1]
    return [k.strip() for k in re.split(r"(?<!\\)\|", srodek)]


def _wzorce(opis: str) -> list[str]:
    """Wzorce plików z backticków opisu; reszta (np. `modul.STALA`) odpada sama."""
    wynik = []
    for kod in _RE_KOD.findall(opis):
        kod = kod.strip()
        if " " in kod:
            continue
        if kod == ".py":                 # „a new or renamed `.py` in the repo root”
            wynik.append("*.py")
        elif "/" in kod or "*" in kod or re.search(r"\.[a-z]{2,4}$", kod):
            wynik.append(kod)
    return wynik


def wczytaj_tabele(tekst: str) -> list[Wiersz]:
    """Wiersze tabeli spod :data:`NAGLOWEK_TABELI` (bez nagłówka i separatora)."""
    linie = tekst.splitlines()
    try:
        start = linie.index(NAGLOWEK_TABELI)
    except ValueError:
        return []
    wiersze: list[Wiersz] = []
    w_tabeli = False
    for linia in linie[start + 1:]:
        if linia.startswith("|"):
            w_tabeli = True
            komorki = _komorki(linia)
            if len(komorki) != 2 or set(komorki[1]) <= {"-", " "} or komorki[0] == "you changed":
                continue
            opis = f" {komorki[0]} "
            wiersze.append(Wiersz(komorki[0], komorki[1], _wzorce(komorki[0]),
                                  " other " in opis, " new " in opis))
        elif w_tabeli:
            break
    return wiersze


def _pasuje(plik: str, wzorzec: str) -> bool:
    if "/" not in wzorzec and "*" not in wzorzec:
        return plik.rsplit("/", 1)[-1] == wzorzec
    if wzorzec == "*.py":
        return "/" not in plik and plik.endswith(".py")
    if wzorzec.endswith("/"):            # katalog: `dictionaries/**/rezyser/`
        wzorzec += "*"
    # `gui/ui.yaml` w opisie znaczy „ten plik w dowolnej paczce” — końcówka ścieżki.
    return (fnmatch.fnmatchcase(plik, wzorzec)
            or fnmatch.fnmatchcase(plik, "*/" + wzorzec))


def dopasuj(wiersze: list[Wiersz], pliki: list[str],
            nowe: set[str] | None = None) -> list[str]:
    """Wypełnia `Wiersz.pliki`; zwraca pliki bez żadnego wiersza.

    `nowe` = pliki dodane (dla wierszy „a new …”); `None` = traktuj każdy
    plik jako nowy (lista podana ręcznie — wolimy pokazać za dużo niż za mało).
    """
    zlapane: set[str] = set()
    for w in wiersze:
        w.pliki = [p for p in pliki
                   if any(_pasuje(p, wz) for wz in w.wzorce)
                   and not (w.tylko_reszta and p in zlapane)
                   and not (w.tylko_nowe and nowe is not None and p not in nowe)]
        zlapane.update(w.pliki)
    return [p for p in pliki if p not in zlapane]


def _git(*argumenty: str) -> tuple[int, str]:
    wynik = subprocess.run(["git", *argumenty], cwd=KORZEN, capture_output=True,
                           text=True, encoding="utf-8", errors="replace")
    return wynik.returncode, wynik.stdout


def zmienione(baza: str | None) -> tuple[str, list[str], set[str]]:
    """(baza, wszystkie zmienione, dodane) — dodane = status A + nieśledzone."""
    if baza is None:
        kod, wyjscie = _git("describe", "--tags", "--abbrev=0")
        baza = wyjscie.strip() if kod == 0 and wyjscie.strip() else "HEAD"
    kod, roznica = _git("diff", "--name-status", baza)
    if kod != 0:
        raise SystemExit(f"❌ git diff --name-status {baza} failed — is `{baza}` a valid revision?")
    pliki: set[str] = set()
    nowe: set[str] = set()
    for linia in roznica.splitlines():
        czesci = linia.split("\t")
        if len(czesci) < 2:
            continue
        sciezka = czesci[-1].strip()      # przy R/C ostatnia kolumna = nowa nazwa
        pliki.add(sciezka)
        if czesci[0][:1] in ("A", "R", "C"):
            nowe.add(sciezka)
    _kod, nieslezone = _git("ls-files", "--others", "--exclude-standard")
    for p in nieslezone.splitlines():
        if p.strip():
            pliki.add(p.strip())
            nowe.add(p.strip())
    return baza, sorted(pliki), nowe


def main(argv: list[str] | None = None) -> int:
    dev_konsola.skonfiguruj_stdout()
    parser = argparse.ArgumentParser(
        description="Reads the 'What you touched -> what has an object' table from "
                    "CONTRIBUTING.md and prints what to run for the files you changed "
                    "(since the last tag by default, uncommitted and untracked files "
                    "included).")
    parser.add_argument("--baza", metavar="REV",
                        help="Compare against this revision instead of the last tag "
                             "(e.g. HEAD for uncommitted work only).")
    parser.add_argument("--pliki", nargs="+", metavar="PATH",
                        help="Use these repo-relative paths instead of asking git.")
    args = parser.parse_args(argv)

    wiersze = wczytaj_tabele((KORZEN / "CONTRIBUTING.md").read_text(encoding="utf-8"))
    if not wiersze:
        print(f"❌ CONTRIBUTING.md has no table under {NAGLOWEK_TABELI!r} — "
              f"nothing to map the changes to.")
        return 1
    if args.pliki:
        baza, pliki = "(given)", sorted(p.replace(chr(92), "/") for p in args.pliki)
        nowe = None
    else:
        baza, pliki, nowe = zmienione(args.baza)
    if not pliki:
        print(f"✅ No changes against {baza}.")
        return 0
    bez_wiersza = dopasuj(wiersze, pliki, nowe)

    print(f"===== WHAT TO RUN ({len(pliki)} changed file(s) against {baza}) =====")
    testy: list[str] = []
    for w in wiersze:
        if not w.pliki:
            continue
        print(f"• {w.opis}")
        print(f"    files: {', '.join(w.pliki[:6])}"
              + (f" (+{len(w.pliki) - 6})" if len(w.pliki) > 6 else ""))
        print(f"    run:   {w.uruchom}")
        for t in _RE_TEST.findall(w.uruchom):
            if t not in testy:
                testy.append(t)
    # Zmieniony plik testów jest swoim własnym przedmiotem.
    for p in pliki:
        if "/" not in p and _RE_TEST.fullmatch(p) and p not in testy:
            testy.append(p)
    if testy:
        print("\nAll the pytest files above in one command:")
        print("    .venv/Scripts/python -m pytest " + " ".join(testy))
    kod_bez = [p for p in bez_wiersza if p.endswith(".py") and not _RE_TEST.fullmatch(p)]
    if kod_bez:
        print(f"\nℹ️  {len(kod_bez)} changed .py file(s) have no row in the table "
              f"(run the whole suite, or add a row): {', '.join(kod_bez[:10])}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
