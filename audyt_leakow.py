#!/usr/bin/env python
"""audyt_leakow.py — detektor nieprzetłumaczonych fragmentów (PL-leak) w docs.

Problem (v17.0): batchowy autotłumacz dokumentacji (`buduj_wielojezyczne_docs.py`)
sporadycznie ZOSTAWIA polski tekst w wynikowych szablonach `dictionaries/<kod>/
gui/dokumentacja/*.yaml`. Dwie klasy leaków, każda niewidoczna dla drugiego
detektora:

  A. DRYF CAŁEJ LINII — model przepisał akapit/nagłówek po polsku zamiast
     przetłumaczyć (np. fi nagłówek „Zasilanie API (Klucz OpenAI)", it „Możesz
     wczytać plik"). Wykrywalne `lingua` per-linia (cała linia → POLISH),
     ALE detektor znaków `[ąęłńśćźż]` to przegapia, gdy fraza jest w bazowej
     łacinie (Możesz, Klucz, się).

  B. OSADZONA NAZWA MODUŁU — w skądinąd poprawnym zdaniu docelowego języka
     siedzi polska nazwa modułu/persony („Reżyser einingar" w islandzkim
     zdaniu, „Księga Świata", „Manager Reguł"). `lingua` per-linia tego NIE
     złapie (całe zdanie wykrywa jako język docelowy), więc potrzebny jest
     kuratorski skan PL-terminów + `[ąęłńśćźż]`.

Detektor łączy obie metody. Whitelista (marka „Reżyser Audio GPT", fizyczne
nazwy plików/folderów, markery ⟦i⟧, placeholdery {x.y}, nazwy głosów TTS) jest
MASKOWANA przed detekcją `lingua` — inaczej „podstawy.yaml" → POLISH 0.99 i
marka → POLISH 0.47 generują false-positives (empirycznie potwierdzone).

Dwa zastosowania:
  1. CLI mapa audytu (bez API):
       python audyt_leakow.py --wszystkie
       python audyt_leakow.py --jezyki is,fi --szczegoly
  2. Import przez `buduj_wielojezyczne_docs.py --retry`: funkcja
     :func:`leaki_per_sekcja` zwraca leaki pogrupowane po kluczu sekcji,
     które retry-prompt wstrzykuje do LLM jako „te fragmenty zostały
     niedotłumaczone — przetłumacz je w całości".

Nie zależy od wxPython ani OpenAI — czysty CLI/CI.
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# STDOUT UTF-8 (spójnie z generuj_dokumentacje.py / buduj_wielojezyczne_docs.py)
# ---------------------------------------------------------------------------
if sys.platform == "win32":
    for _strumien in (sys.stdout, sys.stderr):
        try:
            _strumien.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass

ROOT = Path(__file__).resolve().parent
DICT_DIR = ROOT / "dictionaries"
FOLDER_GUI = "gui"
FOLDER_DOKUMENTACJA = "dokumentacja"
KOD_ZRODLOWY = "pl"

# Kody docelowe (bez pl — to źródło). Mapowanie na enum lingua robione lazy
# w `_zbuduj_detektor`, żeby import modułu nie ciągnął modeli językowych.
KODY_DOCELOWE = ["en", "de", "es", "fi", "fr", "is", "it", "ru"]

# Nazwa lingua.Language per kod (string — rozwijany lazy na enum).
_NAZWA_LINGUA = {
    "en": "ENGLISH", "de": "GERMAN", "es": "SPANISH", "fi": "FINNISH",
    "fr": "FRENCH", "is": "ICELANDIC", "it": "ITALIAN", "ru": "RUSSIAN",
}

# ---------------------------------------------------------------------------
# Whitelista — maskowana PRZED detekcją lingua (inaczej false-positives)
# ---------------------------------------------------------------------------
MARKA = "Reżyser Audio GPT"

# Markery zamrożone ⟦i⟧ i placeholdery {klucz.zagniezdzony}.
RE_MARKER = re.compile(r"⟦\d+⟧")
RE_PLACEHOLDER = re.compile(r"\{[a-zA-Z_][a-zA-Z0-9_.]*\}")

# Fizyczne nazwy plików (rozszerzenia projektu) i ścieżki folderów — zostają 1:1
# we wszystkich językach, więc nie mogą wpadać do detekcji jako „polski".
RE_PLIK = re.compile(r"\b[\w]+\.(?:yaml|yml|txt|md|exe|py|env|mode|jsonl|iss|bat|spec|ico)\b")
RE_FOLDER = re.compile(
    r"\b(?:skrypty|opowiesci|runtime|rezyser|akcenty|szyfry|dictionaries|gui|"
    r"dokumentacja|dist|build|docs)/"
)

# Nazwy głosów TTS (product names) — zachowywane 1:1 (z PROMPT_TEMPLATE_DOKUMENTACJA).
GLOSY = (
    "Samantha Mark Markus Hedda Heidi Gudrun Milena Irina Pavel Yuri Satu Mikko "
    "Thomas Amelie Julie Stefan Katja Jorge Monica Helena Alice Luca Elsa Zira "
    "Hazel Ewa Paulina Vocalizer OneCore Maged"
).split()
RE_GLOSY = re.compile(r"\b(?:" + "|".join(re.escape(g) for g in GLOSY) + r")\b")

# ---------------------------------------------------------------------------
# Klasa B — kuratorskie PL-terminy (osadzone w zdaniach docelowego języka).
# Keyowane na DOKŁADNYCH polskich formach, żeby nie kolidować z poprawnymi
# wyrazami obcymi (it „Poliglotta" ≠ pl „Poliglota"; de „Architektur" ≠
# pl „Architektura"). Marka maskowana wcześniej, więc samo „Reżyser" tu = leak.
# ---------------------------------------------------------------------------
PL_TERMINY = [
    # persona/moduł Reżyser + polskie odmiany (marka już zdjęta maskowaniem)
    "Reżyserowi", "Reżyserem", "Reżyserze", "Reżyserów", "Reżysera", "Reżyser",
    "REŻYSER",
    # Poliglota + odmiany PL + hybrydy autotłumacza (np. „Poligloti" celownik).
    # UWAGA: NIE dodawać bazowego „Poliglot" — kolidowałby z włoskim „Poliglotta".
    "Poliglotów", "Poligloty", "Poliglocie", "Poliglotę", "Poliglotą",
    "Poliglotami", "Poliglotom", "Poliglotem",
    "Poligloti", "Poliglota",
    # Manager Reguł + Księga Świata + odmiany
    "Managera Reguł", "Manager Reguł", "Managerze Reguł",
    "Księgę Świata", "Księgi Świata", "Księgą Świata", "Księdze Świata",
    "Księga Świata",
    # nagłówki kroków (powinny być SCHRITT/ÉTAPE/PASSO/VAIHE/SKREF/STEP/ШАГ/PASO)
    "KROK",
    # zmyślony transliterat halucynacji (is manual:468 „Ważar" zamiast „Mikilvæg")
    "Ważar",
]
RE_PL_TERMINY = re.compile(
    r"(?<![\wąęółńśćźżĄĘÓŁŃŚĆŹŻ])(?:"
    + "|".join(re.escape(t) for t in PL_TERMINY)
    + r")(?![\wąęółńśćźżĄĘÓŁŃŚĆŹŻ])"
)

# Klasa B' — polskie znaki diakrytyczne (ó wykluczone: pokrywa się z islandzkim).
RE_PL_ZNAKI = re.compile(r"[ąęłńśćźżĄĘŁŃŚĆŹŻ]")

# Minimalna liczba liter w (zamaskowanej) linii, by puszczać ją do lingua —
# krótsze fragmenty (1-2 słowa) lingua myli; klasę B i tak łapiemy osobno.
_MIN_LITER_LINGUA = 16


@dataclass
class Leak:
    """Pojedynczy wykryty leak w jednej linii sekcji."""
    linia_nr: int          # numer linii w obrębie sekcji (1-based)
    tekst: str             # surowa treść linii (przycięta)
    powod: str             # „lingua:PL 0.93" | „termin:Reżysera" | „znak-PL:ł"
    fragment: str          # konkretny winny fragment (cała linia dla lingua)


def _maskuj_whiteliste(linia: str) -> str:
    """Usuwa z linii whitelistę (marka, pliki, foldery, markery, głosy).

    Zwraca tekst do detekcji `lingua`. NIE używać do raportu — to tylko bufor
    detekcyjny. Maska = spacja (zachowuje granice słów dla lingua).
    """
    txt = linia.replace(MARKA, " ")
    for rx in (RE_MARKER, RE_PLACEHOLDER, RE_PLIK, RE_FOLDER, RE_GLOSY):
        txt = rx.sub(" ", txt)
    return txt


def _zbuduj_detektor(kod: str):
    """Buduje lingua-detektor ograniczony do {target, POLISH, ENGLISH}.

    Restrykcja kandydatów drastycznie tnie szum (model nie zgaduje czeskiego
    czy chorwackiego dla krótkich islandzkich linii). Import lazy.
    """
    from lingua import Language, LanguageDetectorBuilder

    nazwy = {_NAZWA_LINGUA[kod], "POLISH", "ENGLISH"}
    jezyki = [getattr(Language, n) for n in nazwy]
    return LanguageDetectorBuilder.from_languages(*jezyki).build()


def wykryj_leaki_w_tekscie(
    tekst: str,
    kod: str,
    detektor=None,
    *,
    prog_lingua: float = 0.70,
) -> list[Leak]:
    """Skanuje wielolinijkowy `tekst` pod kątem PL-leaków dla języka `kod`.

    Łączy obie klasy:
      * A (lingua per-linia): zamaskowana linia z ≥ _MIN_LITER_LINGUA liter,
        wykryta jako POLISH z pewnością ≥ `prog_lingua` → leak „dryf linii".
      * B (kuratorskie terminy + znaki PL): skan na SUROWEJ (niezamaskowanej)
        linii — łapie osadzone nazwy modułów i diakrytykę.

    `detektor` można podać z zewnątrz (reużycie między sekcjami — budowa
    detektora ładuje modele i jest kosztowna). Gdy None — budujemy lokalnie.
    """
    if kod == KOD_ZRODLOWY:
        return []
    if detektor is None:
        detektor = _zbuduj_detektor(kod)

    leaki: list[Leak] = []
    for nr, linia in enumerate(tekst.split("\n"), start=1):
        surowa = linia.strip()
        if not surowa:
            continue

        # --- Klasa A: dryf całej linii (lingua na zamaskowanej treści) ---
        zamaskowana = _maskuj_whiteliste(surowa)
        litery = sum(ch.isalpha() for ch in zamaskowana)
        if litery >= _MIN_LITER_LINGUA:
            cv = detektor.compute_language_confidence_values(zamaskowana)
            if cv:
                top = cv[0]
                if top.language.name == "POLISH" and top.value >= prog_lingua:
                    leaki.append(Leak(
                        linia_nr=nr,
                        tekst=surowa[:160],
                        powod=f"lingua:PL {top.value:.2f}",
                        fragment=surowa[:160],
                    ))
                    # Dryf całej linii — terminy w niej są skutkiem, nie dorzucamy.
                    continue

        # --- Klasa B: osadzone PL-terminy (marka zdjęta, by „Reżyser Audio GPT"
        #     nie łapał się jako termin:Reżyser — standalone „Reżyser" zostaje) ---
        bez_marki = surowa.replace(MARKA, " ")
        for m in RE_PL_TERMINY.finditer(bez_marki):
            leaki.append(Leak(
                linia_nr=nr,
                tekst=surowa[:160],
                powod=f"termin:{m.group(0)}",
                fragment=m.group(0),
            ))
        # --- Klasa B': polskie znaki (gdy nie złapane wyżej) ---
        if not RE_PL_TERMINY.search(bez_marki):
            znaki = RE_PL_ZNAKI.findall(bez_marki)
            if znaki:
                leaki.append(Leak(
                    linia_nr=nr,
                    tekst=surowa[:160],
                    powod=f"znak-PL:{''.join(sorted(set(znaki)))}",
                    fragment=surowa[:160],
                ))
    return leaki


def _wczytaj_sekcje_docelowe(kod: str, nazwa_pliku: str) -> dict[str, str]:
    """Wczytuje `tresc` z docelowego YAML jako dict sekcji (lub {} gdy brak)."""
    plik = DICT_DIR / kod / FOLDER_GUI / FOLDER_DOKUMENTACJA / nazwa_pliku
    if not plik.is_file():
        return {}
    try:
        with open(plik, "r", encoding="utf-8") as fh:
            dane = yaml.safe_load(fh)
    except (OSError, yaml.YAMLError):
        return {}
    if not isinstance(dane, dict):
        return {}
    tresc = dane.get("tresc")
    if isinstance(tresc, str):
        return {"_legacy": tresc}
    if isinstance(tresc, dict):
        return {k: v for k, v in tresc.items() if isinstance(v, str)}
    return {}


def leaki_per_sekcja(
    kod: str,
    nazwa_pliku: str,
    detektor=None,
    *,
    prog_lingua: float = 0.70,
) -> dict[str, list[Leak]]:
    """Zwraca {klucz_sekcji: [Leak, ...]} dla docelowego pliku (tylko sekcje z leakami).

    Most do `buduj_wielojezyczne_docs.py --retry`: pozwala zbudować retry-prompt
    listujący konkretne niedotłumaczone fragmenty per sekcja.
    """
    if detektor is None:
        detektor = _zbuduj_detektor(kod)
    wynik: dict[str, list[Leak]] = {}
    for klucz, tresc in _wczytaj_sekcje_docelowe(kod, nazwa_pliku).items():
        leaki = wykryj_leaki_w_tekscie(tresc, kod, detektor, prog_lingua=prog_lingua)
        if leaki:
            wynik[klucz] = leaki
    return wynik


# ---------------------------------------------------------------------------
# CLI — mapa audytu (bez API)
# ---------------------------------------------------------------------------
def _szablony_docelowe(kod: str) -> list[str]:
    folder = DICT_DIR / kod / FOLDER_GUI / FOLDER_DOKUMENTACJA
    if not folder.is_dir():
        return []
    return sorted(p.name for p in folder.glob("*.yaml"))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Detektor PL-leaków w dictionaries/<kod>/gui/dokumentacja/*.yaml "
                    "(lingua per-linia + kuratorskie PL-terminy + znaki PL).",
    )
    grupa = parser.add_mutually_exclusive_group(required=True)
    grupa.add_argument("--jezyki", type=str, default="",
                       help=f"CSV kodów ISO (np. is,fi). Dozwolone: {', '.join(KODY_DOCELOWE)}.")
    grupa.add_argument("--wszystkie", action="store_true",
                       help="Skanuj wszystkie języki docelowe.")
    parser.add_argument("--szczegoly", action="store_true",
                        help="Wypisz każdą linię-leak (domyślnie: licznik per sekcja).")
    parser.add_argument("--prog", type=float, default=0.70,
                        help="Próg pewności lingua dla klasy A (domyślnie 0.70).")
    args = parser.parse_args()

    if args.wszystkie:
        kody = list(KODY_DOCELOWE)
    else:
        kody = [k.strip() for k in args.jezyki.split(",") if k.strip()]
        nieznane = [k for k in kody if k not in KODY_DOCELOWE]
        if nieznane:
            print(f"❌ Nieznane kody: {', '.join(nieznane)}. Dozwolone: {', '.join(KODY_DOCELOWE)}.")
            return 2

    suma_leakow = 0
    for kod in kody:
        detektor = _zbuduj_detektor(kod)
        print(f"\n========== {kod.upper()} ==========")
        leakow_jez = 0
        for nazwa_pliku in _szablony_docelowe(kod):
            per_sekcja = leaki_per_sekcja(kod, nazwa_pliku, detektor, prog_lingua=args.prog)
            if not per_sekcja:
                continue
            ile = sum(len(v) for v in per_sekcja.values())
            leakow_jez += ile
            print(f"  📄 {nazwa_pliku}: {ile} leak(ów) w {len(per_sekcja)} sekcji")
            for klucz, leaki in per_sekcja.items():
                powody = ", ".join(sorted({l.powod.split(':')[0] for l in leaki}))
                print(f"     • {klucz}: {len(leaki)}× [{powody}]")
                if args.szczegoly:
                    for l in leaki:
                        print(f"        L{l.linia_nr} ({l.powod}): {l.tekst}")
        if leakow_jez == 0:
            print("  ✅ czysto")
        suma_leakow += leakow_jez

    print(f"\n========== RAZEM: {suma_leakow} leak(ów) w {len(kody)} języku/ach ==========")
    return 1 if suma_leakow else 0


if __name__ == "__main__":
    sys.exit(main())
