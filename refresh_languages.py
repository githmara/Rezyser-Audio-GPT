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
       * DODAJE języki obecne na dysku, a brakujące w rejestrze (nazwa =
         polska nazwa języka z kanonu `jezyki_lingua.py`; dla języka poza
         kanonem — natywna `etykieta` z `podstawy.yaml` plus głośna nota,
         dlaczego to nie jest nazwa polska),
       * USUWA wpisy, których folder/`podstawy.yaml` już nie istnieje
         (auto-sprzątanie po skasowaniu paczki),
       * ZACHOWUJE istniejące wpisy bez zmian — w tym ręcznie dopieszczone
         nazwy (możesz w pliku zmienić „Chinese" na „简体中文", refresh nie
         nadpisze). Synchronizuje WYŁĄCZNIE zbiór kluczy, nie wartości.

Język źródłowy `pl` jest celowo pomijany (to źródło, nie cel tłumaczenia).

Narzędzie jest SAMOWYSTARCZALNE — czyta YAML-e wprost (`pyyaml` przez
`dev_yaml`), nie importuje silnika (`core_poliglota` ciągnie `python-docx`), więc działa nawet
w okrojonym środowisku kontrybutora.

ZEPSUTY PLIK = STOP (standard `dev_yaml`, od v18.28.0). Do v18.27.0 oba loadery
tego narzędzia miały cichy `return`, a przy pliku rejestru był to defekt z
utratą danych: nieczytelny `jezyki_docelowe.yaml` wracał jako `{}`, więc każdy
język wyglądał na „do dodania" i narzędzie NADPISYWAŁO plik nazwami z
`podstawy.yaml` — wraz z ręcznie dopieszczonymi wartościami, których obiecuje
nie ruszać. Dziś nieczytelny albo niebędący mapą rejestr przerywa pracę i mówi,
co poprawić; BRAK pliku zostaje stanem normalnym (pierwszy przebieg), ale
narzędzie o nim głośno melduje.

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

import dev_konsola
import dev_yaml
import jezyki_lingua

# STDOUT UTF-8 (natywne nazwy: cyrylica, 中文, Þ/Æ — cmd.exe domyślnie cp1250).
# Wspólna implementacja dev-tooli od v18.25 → `dev_konsola`.
dev_konsola.skonfiguruj_stdout()

NARZEDZIE = "refresh_languages"
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
#   * DODAJE nowe paczki (nazwa = polska nazwa języka z kanonu
#     `jezyki_lingua.py`, a poza kanonem — natywna `etykieta` z podstawy.yaml),
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


def nazwa_dla_rejestru(kod: str) -> tuple[str, str]:
    """Nazwa nowego wpisu rejestru + NOTA po angielsku (pusta = bez uwag).

    Do v18.28.0 nowy wpis dostawał zawsze nazwę NATYWNĄ (`sv: Svenska`) i był
    to defekt z konsekwencją poza tym plikiem: `buduj_wielojezyczne_akcenty`
    czytał ten sam rejestr, OCZEKUJĄC polskiej nazwy, więc dla dziesiątego
    języka nazwałby pliki akcentów `svenska.yaml` zamiast `szwedzki.yaml`.
    Nazwa pliku akcentu ma od v18.29.0 własne źródło (kanon → patrz
    `buduj_wielojezyczne_akcenty.rozstrzygnij_nazwe_pliku`), a rejestr
    dostaje wartość spójną z ośmioma zastanymi wpisami: polską nazwę języka
    z :mod:`jezyki_lingua`.

    Dla języka POZA kanonem Lingui polskiej nazwy nie ma skąd wziąć bez
    pytania modelu, a rejestr jest plikiem, który człowiek i tak dopieszcza
    ręcznie (refresh nie nadpisuje wartości). Wpisujemy więc endonim i mówimy
    GŁOŚNO, dlaczego to nie jest polska nazwa — cichy endonim w kolumnie
    polskich nazw wyglądałby na decyzję redakcyjną, a jest brakiem danych.
    """
    z_kanonu = jezyki_lingua.nazwa_polska(kod)
    if z_kanonu:
        return z_kanonu, ""
    endonim = natywna_nazwa(kod)
    return endonim, (
        f"`{kod}` is outside the lingua canon (`jezyki_lingua.py`), so the "
        f"Polish name of this language is unknown here — the endonym „{endonim}” "
        f"went in instead. The docs autotranslator gets this value as the TARGET "
        f"LANGUAGE NAME and its prompt is English, so a native name works; edit "
        f"the value by hand if you prefer the Polish one (refresh never "
        f"overwrites existing values)."
    )


def endonim_z_etykiety(etykieta: object) -> str:
    """Prefiks `etykieta` przed separatorem ` – ` albo ``""``.

    Wydzielone z :func:`natywna_nazwa` w v18.29.0, żeby bramka podstaw
    (`audyt_podstaw`) rozcinała etykietę TĄ SAMĄ regułą, a nie drugą kopią
    regexu separatora. Czysta funkcja na łańcuchu — nie dotyka dysku, więc
    wołający może ją użyć na już wczytanych danych i sam odpowiada za to,
    skąd je wziął.
    """
    if not isinstance(etykieta, str) or not etykieta.strip():
        return ""
    return _RE_SEPARATOR_ETYKIETY.split(etykieta.strip(), maxsplit=1)[0].strip()


def natywna_nazwa(kod: str) -> str:
    """Natywna nazwa języka z `dictionaries/<kod>/podstawy.yaml::etykieta`.

    Bierze prefiks przed separatorem ` – ` (jak `core_poliglota.natywna_nazwa`,
    ale samowystarczalnie). Fallback na sam kod ISO, gdy pole `etykieta` jest
    puste — to jedyna dopuszczalna cichość w tej funkcji, bo świeża paczka
    legalnie jeszcze go nie ma i marker do uzupełnienia wpisze człowiek.

    Sam PLIK musi się jednak dać przeczytać: `skanuj_jezyki` wybrało ten kod
    właśnie po jego obecności, więc plik nieczytelny albo niebędący mapą to
    zepsuta paczka, nie „język bez nazwy" (`dev_yaml`).
    """
    dane = dev_yaml.wczytaj_lub_padnij(
        DICT_DIR / kod / "podstawy.yaml", narzedzie=NARZEDZIE)
    return endonim_z_etykiety(dane.get("etykieta", "")) or kod


def skanuj_jezyki() -> list[str]:
    """Kody języków obecnych na dysku (folder z `podstawy.yaml`, poza `pl`)."""
    if not DICT_DIR.is_dir():
        raise SystemExit(
            f"❌ {NARZEDZIE}: no `dictionaries/` folder next to this script "
            f"({DICT_DIR}) — the registry would be emptied of every language."
        )
    kody = []
    for p in sorted(DICT_DIR.iterdir()):
        if p.is_dir() and p.name != KOD_ZRODLOWY and (p / "podstawy.yaml").is_file():
            kody.append(p.name)
    return kody


def wczytaj_rejestr() -> dict[str, str]:
    """Wczytuje istniejący `jezyki_docelowe.yaml` (pusty dict TYLKO gdy brak pliku).

    Nieczytelny albo niebędący mapą rejestr przerywa pracę (`dev_yaml`), bo
    inaczej narzędzie skasowałoby ręcznie dopieszczone nazwy — patrz docstring
    modułu. Brak pliku to normalny pierwszy przebieg; woła o nim `main`.
    """
    dane = dev_yaml.wczytaj_jesli_jest(REJESTR, narzedzie=NARZEDZIE)
    if dane is None:
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
    noty: list[str] = []
    for kod in do_dodania:
        nowy[kod], nota = nazwa_dla_rejestru(kod)             # kanon → endonim
        if nota:
            noty.append(nota)

    if not REJESTR.is_file():
        print(f"ℹ️  {REJESTR.name} does not exist yet — building it from scratch "
              f"(first run).")

    print(f"📁 Na dysku (dictionaries/, poza pl): {sorted(obecne)}")
    print(f"📒 W rejestrze przed synchronizacją:  {sorted(zarejestrowane)}")
    if do_dodania:
        print("➕ DODAJĘ: " + ", ".join(f"{k} → „{nowy[k]}”" for k in do_dodania))
    for nota in noty:
        print(f"⚠️  {nota}")
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
