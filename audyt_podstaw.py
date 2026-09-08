#!/usr/bin/env python
"""audyt_podstaw.py — bramka na kanon Lingui (`jezyki_lingua.py`).

Geneza (v18.29.0, etap 2 standardu „zero ciszy"). `jezyki_lingua.KANON` jest
LUSTREM enuma `lingua.Language`, a nie źródłem — i lustro bez kontroli po
cichu się starzeje: `pip install -U lingua-language-detector` może dodać język,
a wtedy kanon zaczyna KŁAMAĆ. Kłamie w najgorszy możliwy sposób, bo
`czy_w_lingua()` odpowiada „nie" o języku, który detektor obsługuje — i paczka
bez pola `lingua:` przestaje być usterką, choć nią jest.

Bramka nie ma BASELINE'U i to jest świadome odstępstwo od rodziny
`audyt_leakow`/`audyt_ciszy`. Tam baseline istnieje, bo trafienia są sądem
o TREŚCI (zastany dług bywa legalny). Tu trafienie znaczy „kanon nie jest
lustrem", a taki stan nie ma dopuszczalnej postaci: albo się zgadza 1:1, albo
jest zepsuty. Naprawa to jedna linia w `jezyki_lingua.py`, nie negocjacja.

Kontrolowanych jest sześć klas:

  * ``brak-w-kanonie``   — biblioteka zna język, którego kanon nie ma (typowo:
    aktualizacja `lingui`). Skutek: `czy_w_lingua()` mówi „nie" o obsługiwanym
    języku, a szablon Managera Reguł każe zakomentować pole, które POWINNO być
    wypełnione.
  * ``nadwyzka-kanonu`` — kanon zna kod, którego biblioteka nie zna (literówka
    albo język WYCOFANY z `lingui`). Skutek: prefill w szablonie podaje nazwę,
    której detektor odrzuci.
  * ``rozjazd-enuma``   — ten sam kod ISO, inna nazwa enuma. Najgroźniejsza
    klasa, bo wszystko wygląda poprawnie: to dokładnie te cztery pułapki
    nazewnicze, których kanon ma nas pozbawić (`NORWEGIAN` → `BOKMAL`/
    `NYNORSK`, `SLOVENIAN` → `SLOVENE`, `FLEMISH` → `DUTCH`, `FILIPINO` →
    `TAGALOG`).
  * ``duplikat-enuma``  — dwa kody ISO wskazują jedną nazwę enuma, więc mapa
    odwrotna (`iso_dla_enuma`) po cichu gubi jeden z nich.
  * ``kolizja-nazwy``   — dwie polskie nazwy foldują się do jednej nazwy pliku
    akcentu (`norweski` dla `nb` i `nn`). Dwa języki o jednym pliku to nie
    kosmetyka: `dictionaries/<paczka>/akcenty/<nazwa>.yaml` jest
    IDENTYFIKATOREM i drugi język nadpisałby pierwszy.
  * ``zla-forma-nazwy`` — polska nazwa foldem nie schodzi do samych ASCII-liter
    (spacja, nawias, cyfra), więc nie nadaje się na nazwę pliku.

Fold liczy `buduj_wielojezyczne_akcenty.nazwa_pliku_akcentu` — TA SAMA funkcja,
którą ścieżka generująca nazywa nowe pary, sprawdzona na 72 istniejących.
Bramka nie ma prawa mieć własnej kopii folda; kopia mogłaby przepuścić nazwę,
na której realny generator się wywróci.

Łagodna degradacja jak w całej rodzinie: bez `lingui` w środowisku bramka NIE
BLOKUJE (kontrybutor bez pełnego dev-env), tylko melduje, że się nie wykonała.
Maintainer robiący kanoniczny release `lingui` MA, więc dostaje pełną kontrolę.

Użycie:
  python audyt_podstaw.py            # raport kanonu (zero API, zero sieci)
  python audyt_podstaw.py --bramka   # GATE: exit 1 na jakimkolwiek trafieniu
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import audyt_leakow as al
import buduj_wielojezyczne_akcenty as bwa
import dev_konsola
import jezyki_lingua

dev_konsola.skonfiguruj_stdout()

ROOT = Path(__file__).resolve().parent

# Klucz raportu i baseline-podobnej mapy `WynikBramki.nowe`. Kanon jest JEDNYM
# bytem (nie plikiem per język), więc wszystkie jego trafienia lądują pod jedną
# etykietą — czytelną w wyjściu `build_release`.
ZAKRES_KANON = "jezyki_lingua.KANON"


@dataclass
class Znalezisko:
    """Jedno trafienie bramki podstaw."""
    zakres: str      # `jezyki_lingua.KANON` (etap 2) albo kod paczki
    klasa: str       # brak-w-kanonie | nadwyzka-kanonu | rozjazd-enuma | …
    szczegol: str    # opis po angielsku (contributor-facing)

    def __str__(self) -> str:
        return f"{self.klasa}: {self.szczegol}"


def _kanon_biblioteki() -> dict[str, str]:
    """{ISO 639-1: NAZWA_ENUMA} wprost z zainstalowanej `lingui`.

    Import jest LENIWY i nieopakowany: `ImportError` ma wyjść na wołającego
    (`bramka`), który dopiero decyduje o łagodnej degradacji. Enuma nie da się
    iterować przez `list(Language)` (`TypeError: 'type' object is not
    iterable`) — jedyne wejście to `Language.all()` (zmierzone na 2.1.1).
    """
    from lingua import Language

    return {jezyk.iso_code_639_1.name.lower(): jezyk.name
            for jezyk in Language.all()}


def sprawdz_kanon() -> list[Znalezisko]:
    """Porównuje `jezyki_lingua.KANON` z zainstalowaną biblioteką (sześć klas).

    Rzuca `ImportError`, gdy `lingui` nie ma w środowisku — patrz `bramka`.
    """
    biblioteka = _kanon_biblioteki()
    kanon = jezyki_lingua.KANON
    znaleziska: list[Znalezisko] = []

    def dodaj(klasa: str, szczegol: str) -> None:
        znaleziska.append(Znalezisko(ZAKRES_KANON, klasa, szczegol))

    for iso in sorted(set(biblioteka) - set(kanon)):
        dodaj("brak-w-kanonie",
              f"`{iso}` ({biblioteka[iso]}) is known to the installed lingua but "
              f"missing from KANON — add the entry (ISO, enum name, traditional "
              f"Polish name of the language)")
    for iso in sorted(set(kanon) - set(biblioteka)):
        dodaj("nadwyzka-kanonu",
              f"`{iso}` ({kanon[iso][0]}) is in KANON but unknown to the installed "
              f"lingua — a typo, or the language was dropped from the library")
    for iso in sorted(set(kanon) & set(biblioteka)):
        if kanon[iso][0] != biblioteka[iso]:
            dodaj("rozjazd-enuma",
                  f"`{iso}`: KANON says `{kanon[iso][0]}`, the library says "
                  f"`{biblioteka[iso]}`")

    po_enumie: dict[str, list[str]] = {}
    po_pliku: dict[str, list[str]] = {}
    for iso, (nazwa_enuma, nazwa_pl) in sorted(kanon.items()):
        po_enumie.setdefault(nazwa_enuma, []).append(iso)
        forma = bwa.nazwa_pliku_akcentu(nazwa_pl)
        po_pliku.setdefault(forma, []).append(iso)
        if not forma or not forma.isascii() or not forma.isalpha():
            dodaj("zla-forma-nazwy",
                  f"`{iso}`: the Polish name „{nazwa_pl}” folds to „{forma}”, which "
                  f"is not a plain ASCII-letter accent file name")
    for nazwa_enuma, kody in sorted(po_enumie.items()):
        if len(kody) > 1:
            dodaj("duplikat-enuma",
                  f"`{nazwa_enuma}` is claimed by {', '.join(kody)} — "
                  f"`iso_dla_enuma` can only return one of them")
    for forma, kody in sorted(po_pliku.items()):
        if len(kody) > 1:
            nazwy = ", ".join(f"{k} („{kanon[k][1]}”)" for k in kody)
            dodaj("kolizja-nazwy",
                  f"{nazwy} all fold to the accent file name „{forma}” — give them "
                  f"distinct Polish names (cf. `nb` norweski / `nn` nynorski)")
    return znaleziska


def zbierz() -> dict[str, list[str]]:
    """Trafienia jako `{"<zakres>": ["<klasa>|<szczegol>", …]}` — kanon raportu."""
    wynik: dict[str, list[str]] = {}
    for z in sprawdz_kanon():
        wynik.setdefault(z.zakres, []).append(f"{z.klasa}|{z.szczegol}")
    return {k: sorted(v) for k, v in wynik.items()}


def bramka() -> al.WynikBramki:
    """Bramka podstaw. BEZ baseline'u — każde trafienie blokuje.

    Zwraca ten sam typ, co pozostałe bramki rodziny (`al.WynikBramki`), więc
    `build_release` konsumuje ją tym samym wzorcem: `pominieto` = bramki nie
    udało się uruchomić (brak `lingui`), `czysto` = kanon jest lustrem.
    """
    try:
        aktualne = zbierz()
    except ImportError as exc:
        return al.WynikBramki(True, {}, True, f"lingua not available ({exc})")
    return al.WynikBramki(not aktualne, aktualne, False, "")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(
        description="Gate over the language-pack foundations: verify that "
                    "`jezyki_lingua.KANON` is a 1:1 mirror of the installed "
                    "lingua-language-detector (same ISO codes, same enum names, "
                    "no surplus, no gaps, unique accent file names).",
    )
    parser.add_argument("--bramka", action="store_true",
                        help="CI/build GATE: exit 1 on any hit (this gate has no "
                             "baseline — the canon either mirrors the library or "
                             "it is broken).")
    args = parser.parse_args()

    if args.bramka:
        wynik = bramka()
        print("========== FOUNDATIONS GATE (lingua canon) ==========")
        if wynik.pominieto:
            print(f"⚠️  Gate SKIPPED: {wynik.powod_pominiecia}. Install "
                  f"`lingua-language-detector` to run it.")
            print("=====================================================")
            return 0
        if wynik.czysto:
            print(f"✅ KANON mirrors the installed lingua 1:1 "
                  f"({len(jezyki_lingua.KANON)} languages).")
            print("=====================================================")
            return 0
        ile = sum(len(v) for v in wynik.nowe.values())
        print(f"❌ {ile} canon defect(s):")
        for zakres, powody in sorted(wynik.nowe.items()):
            for p in powody:
                klasa, _, szczegol = p.partition("|")
                print(f"  • {zakres} [{klasa}]: {szczegol}")
        print("Fix: edit `jezyki_lingua.KANON` — it is a MIRROR of the library "
              "enum, so the library always wins. After a lingua upgrade that adds "
              "a language, add the entry together with the traditional Polish name "
              "of that language (an adjective only where Polish actually uses one).")
        print("=====================================================")
        return 1

    try:
        znaleziska = sprawdz_kanon()
    except ImportError as exc:
        print(f"⚠️  `lingua` not available ({exc}) — there is nothing to compare "
              f"the canon against. Install `lingua-language-detector`.")
        return 0
    print(f"🔎 Kanon Lingui: {len(jezyki_lingua.KANON)} wpisów w "
          f"`jezyki_lingua.KANON`.")
    if not znaleziska:
        print("✅ Kanon jest lustrem zainstalowanej biblioteki 1:1 "
              "(kody, nazwy enumów, unikalne nazwy plików akcentów).")
        return 0
    licznik: dict[str, int] = {}
    for z in znaleziska:
        licznik[z.klasa] = licznik.get(z.klasa, 0) + 1
    print(f"❌ {len(znaleziska)} canon defect(s):\n")
    for z in znaleziska:
        print(f"   · {z}")
    print("\n========== TOTAL: "
          + ", ".join(f"{k} {v}" for k, v in sorted(licznik.items()))
          + " ==========")
    return 1


if __name__ == "__main__":
    sys.exit(main())
