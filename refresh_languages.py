#!/usr/bin/env python
"""
refresh_languages.py — dev tool: synchronizuje rejestr języków docelowych
doc-autotłumacza (`jezyki_docelowe.yaml`) z zawartością folderu `dictionaries/`.

Geneza (2026-06-16): do tej pory lista języków akceptowanych przez
`buduj_wielojezyczne_docs.py` żyła jako hard-kod `MAPA_JEZYKOW` w Pythonie.
Zagraniczny kontrybutor dodający nowy język musiałby edytować kod o polskim
rdzeniu — łamiąc zasadę „dodanie języka NIE wymaga Pythona". To narzędzie
(zangielszczony spadkobierca dawnego `odswiez_rezysera.py`, wycofanego w v17.5,
gdy dispatch akcentów stał się dynamiczny) zdejmuje tę barierę:

  1. Kontrybutor wrzuca paczkę `dictionaries/<kod>/` (z `podstawy.yaml`).
  2. Uruchamia `python refresh_languages.py`.
  3. Narzędzie aktualizuje `jezyki_docelowe.yaml`:
       * DODAJE języki obecne na dysku, a brakujące w rejestrze
         (nazwa = natywna `etykieta` z `podstawy.yaml`),
       * USUWA wpisy, których folder/`podstawy.yaml` już nie istnieje
         (auto-sprzątanie po skasowaniu paczki),
       * ZACHOWUJE istniejące wpisy bez zmian — w tym ręcznie dopieszczone
         nazwy (możesz w pliku zmienić „Chinese" na „简体中文", refresh nie
         nadpisze). Synchronizuje WYŁĄCZNIE zbiór kluczy, nie wartości.

Język źródłowy `pl` jest celowo pomijany (to źródło, nie cel tłumaczenia).

Narzędzie jest SAMOWYSTARCZALNE — czyta YAML-e wprost (tylko `pyyaml`), nie
importuje silnika (`core_poliglota` ciągnie `python-docx`), więc działa nawet
w okrojonym środowisku kontrybutora.

Użycie:
  python refresh_languages.py            # synchronizuj + zapisz + raport
  python refresh_languages.py --dry-run  # tylko pokaż diff, nie zapisuj
  python refresh_languages.py --strict    # exit 1, gdy cokolwiek wymaga zmiany
                                          # (przydatne w CI / pre-commit guard)
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import yaml

import dev_konsola

# STDOUT UTF-8 (natywne nazwy: cyrylica, 中文, Þ/Æ — cmd.exe domyślnie cp1250).
# Wspólna implementacja dev-tooli od v18.25 → `dev_konsola`.
dev_konsola.skonfiguruj_stdout()

ROOT = Path(__file__).resolve().parent
DICT_DIR = ROOT / "dictionaries"
REJESTR = ROOT / "jezyki_docelowe.yaml"
KOD_ZRODLOWY = "pl"  # język źródłowy doc-autotłumacza — nie jest celem

# Separator natywnej nazwy w `etykieta` (np. „Suomi – foneettiset perusteet”).
# Tolerujemy en-dash / em-dash / zwykły myślnik z otaczającymi spacjami.
_RE_SEPARATOR_ETYKIETY = re.compile(r"\s+[–—-]\s+")

NAGLOWEK = """\
# =============================================================================
# jezyki_docelowe.yaml — rejestr języków docelowych doc-autotłumacza
# =============================================================================
# Mapa: kod ISO → nazwa języka podawana modelowi jako cel tłumaczenia
# (`jezyk_docelowy` w `tlumacz_ai._PROMPT_SYSTEMOWY_TEMPLATE`).
#
# Ten plik jest UTRZYMYWANY przez `refresh_languages.py` (dev tool) — kontrybutor
# dodający nowy język NIE edytuje Pythona: wrzuca `dictionaries/<kod>/` (z
# `podstawy.yaml`), uruchamia `python refresh_languages.py`, a narzędzie:
#   * DODAJE nowe paczki (nazwa = natywna `etykieta` z podstawy.yaml),
#   * USUWA wpisy, których folder/podstawy.yaml już nie ma,
#   * ZACHOWUJE istniejące wpisy (w tym ręcznie dopieszczone nazwy — możesz
#     zmienić „Chinese" na „简体中文" itp., refresh tego nie nadpisze).
#
# `buduj_wielojezyczne_docs.py` czyta ten plik jako `MAPA_JEZYKOW`. Gdy pliku
# brak — używa wbudowanego fallbacku. `pl` to język ŹRÓDŁOWY (nie cel) i celowo
# NIE występuje tutaj. NIE edytuj kluczy ręcznie — od tego jest refresh; nazwy
# (wartości) możesz zmieniać dowolnie.
# =============================================================================
"""


def natywna_nazwa(kod: str) -> str:
    """Natywna nazwa języka z `dictionaries/<kod>/podstawy.yaml::etykieta`.

    Bierze prefiks przed separatorem ` – ` (jak `core_poliglota.natywna_nazwa`,
    ale samowystarczalnie). Fallback na sam kod ISO, gdy brak etykiety.
    """
    p = DICT_DIR / kod / "podstawy.yaml"
    try:
        dane = yaml.safe_load(p.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return kod
    etyk = (dane or {}).get("etykieta", "") if isinstance(dane, dict) else ""
    if isinstance(etyk, str) and etyk.strip():
        nazwa = _RE_SEPARATOR_ETYKIETY.split(etyk.strip(), maxsplit=1)[0].strip()
        if nazwa:
            return nazwa
    return kod


def skanuj_jezyki() -> list[str]:
    """Kody języków obecnych na dysku (folder z `podstawy.yaml`, poza `pl`)."""
    if not DICT_DIR.is_dir():
        return []
    kody = []
    for p in sorted(DICT_DIR.iterdir()):
        if p.is_dir() and p.name != KOD_ZRODLOWY and (p / "podstawy.yaml").is_file():
            kody.append(p.name)
    return kody


def wczytaj_rejestr() -> dict[str, str]:
    """Wczytuje istniejący `jezyki_docelowe.yaml` (pusty dict, gdy brak/zły)."""
    if not REJESTR.is_file():
        return {}
    try:
        dane = yaml.safe_load(REJESTR.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return {}
    if not isinstance(dane, dict):
        return {}
    return {str(k): str(v) for k, v in dane.items() if isinstance(k, str)}


def zapisz_rejestr(mapa: dict[str, str]) -> None:
    """Zapisuje rejestr: nagłówek-komentarz + wpisy `kod: nazwa` (sort po kodzie)."""
    linie = [NAGLOWEK]
    for kod in sorted(mapa):
        linie.append(f"{kod}: {mapa[kod]}")
    REJESTR.write_text("\n".join(linie) + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Synchronize jezyki_docelowe.yaml with the dictionaries/ folder.",
    )
    ap.add_argument("--dry-run", action="store_true",
                    help="Only show the diff, do not write the file.")
    ap.add_argument("--strict", action="store_true",
                    help="Return exit 1 when the registry needs updating (CI / pre-commit guard).")
    args = ap.parse_args()

    obecne = set(skanuj_jezyki())
    rejestr = wczytaj_rejestr()
    zarejestrowane = set(rejestr)

    do_dodania = sorted(obecne - zarejestrowane)
    do_usuniecia = sorted(zarejestrowane - obecne)

    nowy = {k: v for k, v in rejestr.items() if k in obecne}  # usuń znikłe
    for kod in do_dodania:
        nowy[kod] = natywna_nazwa(kod)                        # dodaj nowe (natywna nazwa)

    print(f"📁 Na dysku (dictionaries/, poza pl): {sorted(obecne)}")
    print(f"📒 W rejestrze przed synchronizacją:  {sorted(zarejestrowane)}")
    if do_dodania:
        print("➕ DODAJĘ: " + ", ".join(f"{k} → „{nowy[k]}”" for k in do_dodania))
    if do_usuniecia:
        print("➖ USUWAM (brak folderu/podstawy): " + ", ".join(do_usuniecia))
    if not do_dodania and not do_usuniecia:
        print("✅ Registry is already in sync — no changes.")

    zmiana = bool(do_dodania or do_usuniecia)
    if args.strict and zmiana:
        print("❌ --strict: registry needs updating (run without --strict).")
        return 1
    if zmiana and not args.dry_run:
        zapisz_rejestr(nowy)
        print(f"💾 Saved {REJESTR.name} ({len(nowy)} target languages).")
    elif zmiana and args.dry_run:
        print("ℹ️  --dry-run: nothing was written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
