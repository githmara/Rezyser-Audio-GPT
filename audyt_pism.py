#!/usr/bin/env python
"""audyt_pism.py — bramka na SŁOWO Z DWÓCH PISM w danych paczek (v19.16).

Geneza. Autotłumacz co jakiś czas wstawia fragment słowa w nie tym alfabecie:
`ru/gui/dokumentacja/manual.yaml` miał od v18.24.2 „donастроить" (PL „dostroić",
łacińskie „don" zamiast „до") i przeszedł do wydanego `docs/manual.ru.html`,
a w paczce Manaboomu ta sama usterka trafiła w fiński tekst cyrylicą. Tekst jest
poprawnym Unicode, więc żadna wcześniejsza bramka go nie widziała, a czytelnik
i syntezator widzą w obu pismach to samo „a"/„o"/„e".

Dlaczego słowo, a nie „obce pismo w paczce". Rozpoznanie 2026-10-26: legalna
cyrylica stoi w KAŻDEJ paczce (akcent `akcenty/rosyjski.yaml`, „Русский" w
przełączniku języków README, przykład naprawy kodowania w podręczniku, przykłady
reguł w `podstawy.yaml`), a greka to litery IPA (/θ/, /β/). Żadnej z nich nie da
się przepisać na coś neutralnego bez utraty treści. Słowo, w którym stoją litery
dwóch pism NARAZ, nie ma za to w danych ani jednego legalnego wystąpienia — poza
dwoma wyjątkami konstrukcyjnymi, które ta bramka zna:

  * pole `alfabet` (`podstawy.yaml`) — ciąg liter szyfru, w `ru` z definicji
    cyrylica sklejona z łacinką;
  * sekwencje regexa (`\\b`, `\\s`) — w polu `wzor:` backslash stoi tuż przed
    literą słowa; detektor je wycina (`tlumacz_bramki.slowa_mieszanego_pisma`).

Skan idzie po SPARSOWANYM YAML-u (wartości, nie komentarze ani klucze): komentarz
nie wchodzi ani do silnika, ani do podręcznika, a surowy tekst dawałby fałszywe
trafienia na `\\nЕсли` w każdym dłuższym napisie `ui.yaml`.

Wzorzec rodziny `audyt_ciszy`: BASELINE (`audyt_pism_baseline.json`) blokuje
wyłącznie trafienia NOWE. Wchodzi do repo pusty — legalnego słowa mieszanego
pisma dziś nie ma, więc wpis tam to świadoma decyzja (np. transkrypcja IPA
z greckim θ w polu opisu), nie zastany dług. Zero `lingui`, zero sieci.

Użycie:
  python audyt_pism.py                    # raport (zero API)
  python audyt_pism.py --bramka           # GATE: exit 1 na trafieniach ponad baseline
  python audyt_pism.py --zapisz-baseline  # regeneracja baseline'u (przeczytaj diff!)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Iterator

import audyt_leakow as al
import dev_konsola
import dev_yaml
import tlumacz_bramki

dev_konsola.skonfiguruj_stdout()

ROOT = Path(__file__).resolve().parent
DICT_DIR = ROOT / "dictionaries"
BASELINE_PATH = ROOT / "audyt_pism_baseline.json"
NARZEDZIE = "audyt_pism"

# Klucze, których wartość jest z definicji mieszanką pism (patrz docstring).
KLUCZE_WYJETE = {"alfabet"}


def pliki_skanu(katalog: Path = DICT_DIR) -> list[Path]:
    """Wszystkie pliki YAML paczek, z podręcznikami (z nich powstaje `docs/`)."""
    return sorted(katalog.rglob("*.yaml"))


def _napisy(dane: Any, sciezka: str = "") -> Iterator[tuple[str, str]]:
    """Pary (ścieżka klucza, napis) dla każdej wartości tekstowej drzewa."""
    if isinstance(dane, dict):
        for klucz, wartosc in dane.items():
            if klucz in KLUCZE_WYJETE:
                continue
            yield from _napisy(wartosc, f"{sciezka}.{klucz}" if sciezka else str(klucz))
    elif isinstance(dane, list):
        for i, wartosc in enumerate(dane):
            yield from _napisy(wartosc, f"{sciezka}[{i}]")
    elif isinstance(dane, str):
        yield sciezka, dane


def skanuj_plik(plik: Path, katalog: Path = DICT_DIR) -> list[tuple[str, str]]:
    """Trafienia pliku jako pary (ścieżka klucza, słowo mieszanego pisma)."""
    dane = dev_yaml.wczytaj_lub_padnij(plik, narzedzie=NARZEDZIE,
                                       oczekiwany=(dict, list))
    return [
        (sciezka, slowo)
        for sciezka, napis in _napisy(dane)
        for slowo in tlumacz_bramki.slowa_mieszanego_pisma(napis)
    ]


def zbierz(katalog: Path = DICT_DIR) -> dict[str, list[str]]:
    """Skan jako `{"<plik>": ["<ścieżka klucza>|<słowo>", …]}` — kanon baseline'u.

    Klucz bez numeru linii (odporny na przesunięcia), wartość to multiset —
    ten sam kanon co pozostałe baseline'y rodziny.
    """
    wynik: dict[str, list[str]] = {}
    for plik in pliki_skanu(katalog):
        trafienia = skanuj_plik(plik, katalog)
        if trafienia:
            nazwa = plik.relative_to(katalog.parent).as_posix()
            wynik[nazwa] = sorted(f"{s}|{w}" for s, w in trafienia)
    return wynik


def bramka(katalog: Path = DICT_DIR,
           baseline: Path = BASELINE_PATH) -> al.WynikBramki:
    """Bramka względem `audyt_pism_baseline.json`. Pusty zakres = błąd, nie „czysto"."""
    if not pliki_skanu(katalog):
        raise SystemExit(f"❌ {NARZEDZIE}: no YAML file under {katalog} — a gate "
                         "that scanned nothing must not report clean.")
    aktualne = zbierz(katalog)
    nowe = al.roznica_wzgledem_baseline(aktualne, al.wczytaj_baseline(baseline))
    return al.WynikBramki(not nowe, nowe)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(
        description="Gate against a MIXED-SCRIPT word in the language packs: one "
                    "word holding letters of two scripts (Latin / Cyrillic / "
                    "Greek), e.g. 'donастроить'. Scans parsed YAML values of "
                    "dictionaries/**; the `alfabet` field and regex escapes are "
                    "exempt by construction.",
    )
    grupa = parser.add_mutually_exclusive_group()
    grupa.add_argument("--bramka", action="store_true",
                       help="CI/build GATE: exit 1 on hits above the baseline "
                            f"({BASELINE_PATH.name}).")
    grupa.add_argument("--zapisz-baseline", dest="zapisz_baseline", action="store_true",
                       help="Regenerate the baseline from the current scan. Overwrites "
                            f"{BASELINE_PATH.name} — review the diff before committing.")
    args = parser.parse_args()

    if args.zapisz_baseline:
        aktualne = zbierz()
        al.zapisz_baseline(aktualne, BASELINE_PATH)
        ile = sum(len(v) for v in aktualne.values())
        print(f"✅ Saved the mixed-script baseline: {ile} hit(s) in {len(aktualne)} "
              f"file(s) → {BASELINE_PATH.name}. Review the diff before committing.")
        return 0

    if args.bramka:
        wynik = bramka()
        print("========== MIXED-SCRIPT WORD GATE (vs baseline) ==========")
        if wynik.czysto:
            print(f"✅ No mixed-script word above the baseline ({BASELINE_PATH.name}).")
            print("==========================================================")
            return 0
        ile = sum(len(v) for v in wynik.nowe.values())
        print(f"❌ {ile} mixed-script word(s) ABOVE the baseline in "
              f"{len(wynik.nowe)} file(s):")
        for plik, powody in sorted(wynik.nowe.items()):
            for p in powody:
                print(f"  • {plik}: {p}")
        print("Fix: retype the word in ONE script (a translator wrote part of it in "
              "the wrong alphabet). If the word is genuinely legitimate — regenerate "
              f"the baseline: `python {Path(__file__).name} --zapisz-baseline` and "
              "commit the diff.")
        print("==========================================================")
        return 1

    aktualne = zbierz()
    if not aktualne:
        print(f"✅ Skan pism: {len(pliki_skanu())} plików YAML, żadnego słowa "
              "z liter dwóch pism.")
        return 0
    ile = sum(len(v) for v in aktualne.values())
    print(f"🔎 Skan pism: {ile} słów mieszanego pisma w {len(aktualne)} plik(ach).\n")
    for plik, powody in sorted(aktualne.items()):
        print(f"📄 {plik}")
        for p in powody:
            print(f"   · {p}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
