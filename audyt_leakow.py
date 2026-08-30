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
import ast
import json
import re
import sys
from collections import Counter
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

# Mapa {kod ISO: nazwa enum lingua} budowana DYNAMICZNIE ze
# `dictionaries/<kod>/podstawy.yaml::lingua` (bez źródłowego pl) — nowy język =
# nowy folder, zero edycji tutaj. Spójne z `core_poliglota._zbuduj_mapowanie_lingua`
# i `bot_i18n.mapa_iso_na_lingua` (lekka kopia: ten dev-tool celowo trzyma deps
# wąsko — sam `yaml` + lazy `lingua`, bez ciągnięcia silnika z docx/num2words).
# Mapowanie na enum robione lazy w `_zbuduj_detektor` (string → getattr).
def _skanuj_lingua_z_podstaw() -> dict[str, str]:
    """{kod ISO: NAZWA_ENUMA} z podstawy.yaml::lingua (pomija źródłowe pl).

    Paczka z `podstawy.yaml`, która NIE mapuje się na lingua (brak pola,
    literówka `lingva:`, nieparsowalny YAML), jest błędem FATALNYM, a nie
    powodem do cichego pominięcia (v18.9). Wcześniej taka paczka po prostu
    wypadała z `KODY_DOCELOWE` — bramka leaków przestawała ją skanować i
    raportowała „czysto", mimo że nikt jej nie sprawdził.
    """
    if not DICT_DIR.is_dir():
        return {}
    wynik: dict[str, str] = {}
    problemy: list[str] = []
    for p in sorted(DICT_DIR.iterdir()):
        if not p.is_dir() or p.name == KOD_ZRODLOWY:
            continue
        plik = p / "podstawy.yaml"
        if not plik.is_file():
            continue   # folder bez podstawy.yaml to nie paczka językowa
        try:
            dane = yaml.safe_load(plik.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            problemy.append(f"{p.name}: podstawy.yaml nieczytelny ({exc})")
            continue
        wartosc = dane.get("lingua") if isinstance(dane, dict) else None
        if isinstance(wartosc, str) and wartosc.strip():
            wynik[p.name] = wartosc.strip().upper()
        else:
            problemy.append(f"{p.name}: brak pola `lingua:` w podstawy.yaml")
    if problemy:
        raise SystemExit(
            "❌ audyt_leakow: language packs with no lingua mapping — the leak "
            "gate would SKIP them:\n  - " + "\n  - ".join(problemy)
        )
    return wynik


_NAZWA_LINGUA = _skanuj_lingua_z_podstaw()
KODY_DOCELOWE = sorted(_NAZWA_LINGUA)

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
    # moduł Opowieści + odmiany PL (domknięcie „Co nie weszło" v18.6.1 — brakował
    # na liście obok Reżyser/Poliglota/Księga Świata/KROK)
    "Opowieściami", "Opowieściach", "Opowieściom", "Opowieścią",
    "Opowieści", "Opowieść",
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
    """Wczytuje `tresc` z docelowego YAML jako dict sekcji (lub {} gdy brak).

    Brak pliku = legalnie pusty wynik (nie każda paczka ma każdy szablon), ale
    plik ISTNIEJĄCY i nieczytelny to błąd FATALNY (v18.9): zwrócenie ``{}``
    dawało bramce „zero sekcji = zero leaków = czysto", czyli zielone światło
    dla pliku, którego nikt nie zeskanował.
    """
    plik = DICT_DIR / kod / FOLDER_GUI / FOLDER_DOKUMENTACJA / nazwa_pliku
    if not plik.is_file():
        return {}
    try:
        with open(plik, "r", encoding="utf-8") as fh:
            dane = yaml.safe_load(fh)
    except (OSError, yaml.YAMLError) as exc:
        raise SystemExit(
            f"❌ audyt_leakow: cannot read {plik} ({exc}) — a scan of this file "
            f"would be falsely \"clean\"."
        ) from exc
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
# Skan ui.yaml (od v18.5.3) — rozszerzenie detektora PL-leak na stringi GUI
# ---------------------------------------------------------------------------
# Odłożony z v18.5.2 razem z bramką: te same klasy leaków (osadzona PL nazwa
# modułu, dryf linii) trafiają też do `dictionaries/<kod>/gui/ui.yaml` —
# komunikaty błędów, opisy, etykiety. `safe_load` GUBI komentarze, więc skanujemy
# WYŁĄCZNIE wartości (polskie nagłówki sekcji `# REZYSER …` to dev-komentarze,
# obecne identycznie we wszystkich paczkach — NIE leaki, i tak niewidoczne tu).
#
# OGRANICZENIE (świadome): detektor jest PL-leak. NIE łapie niespójności kanonu
# w obrębie języka docelowego — np. włoskie „Storie" zamiast kanonicznego
# „Racconti" (oba włoskie) ani angielskiej literówki „Poliglot" zamiast
# „Polyglot". To nie polski tekst i nie kanon innego języka — żadna ogólna reguła
# tego nie wykryje bez hardkodowanej listy wariantów (generującej FP). Ta klasa
# pozostaje human-caught (skan `nazwy_narzedzi` + grep, jak w v18.5.2/18.5.3).
NAZWA_UI = "ui.yaml"


def _splaszcz_ui(dane, prefiks: str = "") -> dict[str, str]:
    """Spłaszcza zagnieżdżony ui.yaml do `{klucz.kropkowany: wartosc_str}` (liście-stringi).

    Listy adresowane `[i]`. Pomija nie-stringi (liczby, bool, None) — leak to zawsze
    tekst user/LLM-facing. Klucz kropkowany = czytelny adres w raporcie i stabilny
    identyfikator baseline (odporny na przesunięcie linii, w przeciwieństwie do nr).
    """
    wynik: dict[str, str] = {}
    if isinstance(dane, dict):
        iterator = dane.items()
    elif isinstance(dane, list):
        iterator = ((f"[{i}]", v) for i, v in enumerate(dane))
    else:
        return wynik
    for k, v in iterator:
        klucz = f"{prefiks}.{k}" if (prefiks and not str(k).startswith("[")) else f"{prefiks}{k}" if prefiks else str(k)
        if isinstance(v, str):
            wynik[klucz] = v
        elif isinstance(v, (dict, list)):
            wynik.update(_splaszcz_ui(v, klucz))
    return wynik


def leaki_ui_per_klucz(
    kod: str,
    detektor=None,
    *,
    prog_lingua: float = 0.70,
) -> dict[str, list[Leak]]:
    """Zwraca `{klucz.kropkowany: [Leak, ...]}` dla `dictionaries/<kod>/gui/ui.yaml`.

    Analogon `leaki_per_sekcja` dla docs, ale jednostką jest pojedyncza wartość
    ui.yaml (komunikat/etykieta), nie sekcja manuala. Skanuje tylko sekcje z leakami.
    """
    if detektor is None:
        detektor = _zbuduj_detektor(kod)
    sciezka = DICT_DIR / kod / FOLDER_GUI / NAZWA_UI
    if not sciezka.is_file():
        return {}
    try:
        dane = yaml.safe_load(sciezka.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return {}
    wynik: dict[str, list[Leak]] = {}
    for klucz, wartosc in _splaszcz_ui(dane).items():
        leaki = wykryj_leaki_w_tekscie(wartosc, kod, detektor, prog_lingua=prog_lingua)
        if leaki:
            wynik[klucz] = leaki
    return wynik


# ===========================================================================
# CANON-CHECK — niespójność nazwy modułu w obrębie języka (od v18.5.4)
# ===========================================================================
# Domknięcie „Co nie weszło" v18.5.3: detektor PL-leak jest z natury ślepy na
# niespójność KANONU w obrębie języka docelowego — włoskie „Storie" zamiast
# kanonicznego „Racconti" (oba włoskie), angielska literówka „Poliglot" zamiast
# „Polyglot". To nie polski tekst ani kanon innego języka, więc żadna OGÓLNA
# reguła tego nie wykryje. Jedyne tractable podejście = KURATORSKA mapa znanych
# form-dryfu → kanon (z `main.nazwy_narzedzi`), skanowana po ui.yaml + docs.
#
# Filozofia identyczna jak PL-leak: LEJEK over-reportujący + BASELINE. „Storie"/
# „Storia" to też zwykłe włoskie słowo (proza „Storia corrente in memoria",
# „Storia caricata") → te trafienia są FP wchłanianym przez baseline; NOWE
# „Storie"-jako-moduł (np. w dodanej sekcji) pada na bramce. Mapa jest jawnie
# wąska (tylko UDOKUMENTOWANE klasy dryfu), bo szeroka „każdy obcy kanon w złym
# pliku" generowałaby lawinę FP. Nowy język/wariant = dopisanie wpisu tutaj.
#
# Canon-check jest WPIĘTY w `zbierz_wszystkie_leaki` (ten sam baseline + bramka co
# PL-leak), więc `bramka_docs()` — a przez nią `generuj_dokumentacje --waliduj`
# i `build_release` — pilnują go automatycznie. Powód ma stabilny kształt
# „canon:<wariant>→<kanon>" (bez floata), więc jest jednoznaczny w baseline.
DRIFT_VARIANTS: dict[str, dict[str, str]] = {
    # it: moduł Opowieści — kanon „Racconti" (nazwy_narzedzi.opowiesci). Autotłumacz
    # historycznie zostawiał „Storie"/„Storia" (= zwykłe włoskie słowo). Proza
    # („Storia corrente", „Storia '…' caricata") = FP → baseline; NOWE „Storie"-moduł = blok.
    "it": {"Storie": "Racconti", "Storia": "Racconti"},
    # en: literówka kanonu „Polyglot" (nazwy_narzedzi.poliglota). „Poliglot" (bez „y")
    # nie jest ani polski, ani innym kanonem — detektor PL-leak go z natury nie złapie.
    "en": {"Poliglot": "Polyglot"},
}


def _re_canon(warianty: dict[str, str]) -> re.Pattern[str]:
    """Buduje case-sensitive regex form-dryfu z granicą liter łacińskich (z diakrytyką).

    Granica `(?<![A-Za-zÀ-ÿ])…(?![A-Za-zÀ-ÿ])` chroni przed trafieniem w wyrazy
    pochodne: „Storie" NIE złapie się w „Storielle", „Storia" w „Storica".
    """
    return re.compile(
        r"(?<![A-Za-zÀ-ÿ])(?:"
        + "|".join(re.escape(w) for w in sorted(warianty, key=len, reverse=True))
        + r")(?![A-Za-zÀ-ÿ])"
    )


def _canon_powody(rx: re.Pattern[str], warianty: dict[str, str], tekst: str) -> list[str]:
    """Posortowany multiset powodów „canon:<wariant>→<kanon>" dla wszystkich trafień."""
    return sorted(f"canon:{m.group(0)}→{warianty[m.group(0)]}" for m in rx.finditer(tekst))


def leaki_canon_dla_jezyka(kod: str) -> dict[str, list[str]]:
    """`{"<kod>/<plik>/<klucz>": [powod_canon]}` dla docs+ui — niespójność kanonu nazwy.

    Zwraca {} dla języka spoza `DRIFT_VARIANTS` (brak znanych klas dryfu). Klucze
    identyczne jak w `zbierz_wszystkie_leaki` (docs: `<plik>/<sekcja>`; ui: `ui.yaml/
    <kropkowany>`), żeby powody dało się scalić z PL-leakami w jednym kluczu baseline.
    """
    warianty = DRIFT_VARIANTS.get(kod)
    if not warianty:
        return {}
    rx = _re_canon(warianty)
    wynik: dict[str, list[str]] = {}
    for nazwa_pliku in _szablony_docelowe(kod):
        for klucz, tresc in _wczytaj_sekcje_docelowe(kod, nazwa_pliku).items():
            powody = _canon_powody(rx, warianty, tresc)
            if powody:
                wynik[f"{kod}/{nazwa_pliku}/{klucz}"] = powody
    sciezka = DICT_DIR / kod / FOLDER_GUI / NAZWA_UI
    if sciezka.is_file():
        try:
            dane = yaml.safe_load(sciezka.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            dane = None
        if dane is not None:
            for klucz, wartosc in _splaszcz_ui(dane).items():
                powody = _canon_powody(rx, warianty, wartosc)
                if powody:
                    wynik[f"{kod}/{NAZWA_UI}/{klucz}"] = powody
    return wynik


# ===========================================================================
# BRAMKA CI/BUILD — baseline zaakceptowanych leaków (od v18.5.3)
# ===========================================================================
# Odłożony z v18.5.2 („Co nie weszło"): wpięcie detektora leaków jako BRAMKA do
# `generuj_dokumentacje --waliduj`/`build_release` (dotąd strażniki sprawdzały
# tylko nagłówek finalizacji + placeholdery, NIE leaki — stąd polski tekst mógł
# dożyć „sfinalizowanego" wydania).
#
# Problem: detektor to LEJEK over-reportujący (filozofia jak skaner `.py` wyżej) —
# na czystym drzewie raportuje ~75 trafień, w 100% triaged FP / treść intencjonalna:
#   * `termin:KROK` — odroczona lokalizacja nagłówków „KROK" (osobny dług),
#   * `znak-PL` dydaktyczne — `co_to_akcent` (uczy „ą/ę/ł"), `changelog_*`
#     (fonem „[dż]", omówienie „ź/ż"), `krok_2_*` (polskie nazwy własne:
#     Saska Kępa, Świętokrzyskie), `krok_4_*` (przykład [dż]),
#   * `lingua` — linie alfabetu Cezara (`co_to_szyfr`), nazwy głosów TTS.
# Surowy lejek jako twarda bramka blokowałby KAŻDY build już dziś. Stąd wzorzec
# BASELINE (jak mypy/eslint baseline na legacy): commitujemy snapshot obecnych
# trafień do `audyt_leakow_baseline.json`, a bramka pada TYLKO na trafienia SPOZA
# baseline (nowy/przesunięty leak). Naprawa starych leaków (ElevenLabs, KROK,
# ui.yaml) kurczy baseline; regeneracja po LEGALNej zmianie treści: `--zapisz-baseline`.
BASELINE_PATH = ROOT / "audyt_leakow_baseline.json"
# Skan źródeł `.py` to INNA powierzchnia (kod, nie tłumaczenia) → własny baseline.
BASELINE_PY_PATH = ROOT / "audyt_leakow_py_baseline.json"
# Kontrakt CONTRIBUTING w dev-toolach (v18.24) — TRZECIA powierzchnia, własny plik.
BASELINE_KONTRAKT_PATH = ROOT / "audyt_leakow_kontrakt_baseline.json"

# Powód lingua niesie ZMIENNY float pewności („lingua:PL 0.98") — normalizujemy
# go do „lingua:PL", inaczej drobne wahanie modelu rozjeżdżałoby baseline. Inne
# klasy (`znak-PL:ćś`, `termin:Manager Reguł`) są stabilne i zostają 1:1
# (UWAGA: termin bywa wielowyrazowy, więc NIE wolno ciąć po pierwszej spacji).
_RE_POWOD_LINGUA = re.compile(r" \d+\.\d+$")


def _normalizuj_powod(powod: str) -> str:
    """„lingua:PL 0.98" → „lingua:PL"; pozostałe powody bez zmian (stabilne klucze)."""
    return _RE_POWOD_LINGUA.sub("", powod)


def zbierz_wszystkie_leaki(
    kody: list[str] | None = None,
    *,
    prog_lingua: float = 0.70,
) -> dict[str, list[str]]:
    """Zbiera leaki ze szablonów docs ORAZ ui.yaml jako `{"<kod>/<plik>/<sekcja>": [powod_norm]}`.

    Dwie powierzchnie (od v18.5.3): `dictionaries/<kod>/gui/dokumentacja/*.yaml`
    (sekcja = klucz) i `dictionaries/<kod>/gui/ui.yaml` (sekcja = kropkowany klucz
    wartości). Klucz identyfikuje sekcję (nie linię — numery linii dryfują przy edycji);
    wartość to posortowana LISTA znormalizowanych powodów (multiset — duplikaty
    znaczące, np. 2× znak-PL w jednej sekcji). To kanon zarówno baseline'u
    (`zapisz_baseline`), jak i bieżącego skanu bramki (`bramka_docs`).

    Buduje detektor `lingua` raz na język (kosztowny — reużywany między plikami).
    Rzuca `ImportError`, gdy `lingua` jest niedostępna — wołający (bramka) łapie
    to i degraduje łagodnie (skip z ostrzeżeniem), spójnie z `core_poliglota`
    lazy-importem w generatorze.
    """
    if kody is None:
        kody = list(KODY_DOCELOWE)
    wynik: dict[str, list[str]] = {}
    for kod in kody:
        detektor = _zbuduj_detektor(kod)
        # (1) Szablony docs: dictionaries/<kod>/gui/dokumentacja/*.yaml
        for nazwa_pliku in _szablony_docelowe(kod):
            per_sekcja = leaki_per_sekcja(kod, nazwa_pliku, detektor, prog_lingua=prog_lingua)
            for klucz_sekcji, leaki in per_sekcja.items():
                klucz = f"{kod}/{nazwa_pliku}/{klucz_sekcji}"
                wynik[klucz] = sorted(_normalizuj_powod(l.powod) for l in leaki)
        # (2) Stringi GUI: dictionaries/<kod>/gui/ui.yaml (od v18.5.3)
        for klucz_ui, leaki in leaki_ui_per_klucz(kod, detektor, prog_lingua=prog_lingua).items():
            klucz = f"{kod}/{NAZWA_UI}/{klucz_ui}"
            wynik[klucz] = sorted(_normalizuj_powod(l.powod) for l in leaki)
        # (3) Canon-check (od v18.5.4): niespójność kanonu nazwy modułu (it/en).
        # Scala powody w TEN SAM klucz co PL-leak (jedna wartość mogła mieć oba) —
        # multiset-różnica w bramce działa wtedy poprawnie na połączonej liście.
        for klucz, powody in leaki_canon_dla_jezyka(kod).items():
            wynik[klucz] = sorted(wynik.get(klucz, []) + powody)
    return wynik


def wczytaj_baseline(path: Path = BASELINE_PATH) -> dict[str, list[str]]:
    """Wczytuje baseline JSON (`path`, domyślnie docs/ui) lub {} przy braku/uszkodzeniu.

    Brak pliku traktujemy jako pusty baseline — wtedy KAŻDE trafienie jest „nowe"
    (bramka maksymalnie restrykcyjna). Świadomie: lepiej zablokować build przy
    zgubionym baseline niż przepuścić leaki po cichu. `path` parametryzuje plik,
    bo skan źródeł `.py` ma WŁASNY baseline (inna powierzchnia, inny plik).
    """
    if not path.is_file():
        return {}
    try:
        dane = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(dane, dict):
        return {}
    # Normalizacja typu wartości (lista stringów) — odporność na ręczną edycję.
    return {k: list(v) for k, v in dane.items() if isinstance(v, list)}


def zapisz_baseline(dane: dict[str, list[str]], path: Path = BASELINE_PATH) -> None:
    """Zapisuje baseline do `path` (UTF-8, posortowany, LF).

    `sort_keys` + `indent=2` → deterministyczny, czytelny w diffie plik. `ensure_ascii
    =False` → polskie znaki w powodach (znak-PL:ćś) zostają czytelne, nie `\\uXXXX`.
    """
    tresc = json.dumps(dane, ensure_ascii=False, indent=2, sort_keys=True)
    path.write_text(tresc + "\n", encoding="utf-8")


def roznica_wzgledem_baseline(
    aktualne: dict[str, list[str]],
    baseline: dict[str, list[str]],
) -> dict[str, list[str]]:
    """Multiset-różnica: `{klucz: [powody]}` obecne PONAD baseline (= nowe leaki).

    `Counter - Counter` zostawia tylko dodatnie nadwyżki, więc:
      * nowa sekcja (brak w baseline) → wszystkie jej powody jako nowe,
      * dodatkowy leak w znanej sekcji (count rośnie) → nadwyżka jako nowy,
      * usunięty/naprawiony leak (count maleje) → NIE raportowany (baseline może
        zostać „za szeroki" — to OK, kurczymy go osobno przez `--zapisz-baseline`).
    """
    nowe: dict[str, list[str]] = {}
    for klucz, powody in aktualne.items():
        nadwyzka = Counter(powody) - Counter(baseline.get(klucz, []))
        if nadwyzka:
            nowe[klucz] = sorted(nadwyzka.elements())
    return nowe


@dataclass
class WynikBramki:
    """Wynik bramki leaków dla docs (konsumowany przez waliduj() i build_release)."""
    czysto: bool                 # True = brak leaków ponad baseline
    nowe: dict[str, list[str]]   # {"<kod>/<plik>/<sekcja>": [powod_norm]} ponad baseline
    pominieto: bool              # True = bramki nie udało się uruchomić (np. brak lingua)
    powod_pominiecia: str        # krótki opis EN, gdy `pominieto`


def bramka_docs(*, prog_lingua: float = 0.70) -> WynikBramki:
    """Uruchamia bramkę leaków na szablonach docs względem baseline'u.

    Łagodna degradacja: gdy `lingua` jest niedostępna (kontrybutor bez pełnego
    dev-env), zwraca `pominieto=True, czysto=True` — bramka się NIE wykonała, ale
    NIE blokuje (analogia lazy-importu `core_poliglota` w generatorze). Maintainer
    robiący kanoniczny release MA `lingua`, więc dostaje pełną bramkę.
    """
    try:
        aktualne = zbierz_wszystkie_leaki(prog_lingua=prog_lingua)
    except ImportError as exc:
        return WynikBramki(True, {}, True, f"lingua not available ({exc})")
    nowe = roznica_wzgledem_baseline(aktualne, wczytaj_baseline())
    return WynikBramki(not nowe, nowe, False, "")


# ===========================================================================
# SKANER ŹRÓDEŁ .py — user-facing / LLM-facing PL hard-kod (od v17.11.0)
# ===========================================================================
# Odłożony z v17.10.0 („Co nie weszło"): narzędzie wykrywające polski hard-kod
# w źródłach Pythona, które trafia do USERA (etykiety/komunikaty GUI) lub do
# MODELU (payload LLM) z pominięciem i18n (`t()`) / przepisów YAML. Filozofia
# jak docs-detektor wyżej: LEJEK over-reportujący + ręczny triaż, NIE zero-FP.
#
# Świadomie NIE łapane (żeby lejek był użyteczny, nie zalany szumem):
#   * komentarze `#` i docstringi — dev-facing PL jest OK (pomijane przez AST),
#   * literały `detal=...` — techniczny opis błędu (wzorzec mostka i18n: GUI
#     bierze `klucz_i18n`, `detal` to log EN/PL — patrz tlumacz_ai/bledy_ai),
#   * argumenty `_dev_log_runtime(...)` — konsola dewelopera (runtime niewidoczny),
#   * argumenty `t(...)`/`_(...)` — to KLUCZE i18n, nie treść,
#   * całe dev-toole (PL `print` jest tam OK) — lista DEV_TOOLE.
#
# Triaż dwustopniowy (jak LIKELY/POSSIBLE w docs `--draft`):
#   LIKELY   — string-arg trafia do sinka user-facing (wx Set*/MessageBox/…),
#              do callbacku postępu, albo do payloadu LLM (kwarg content /
#              dict z kluczem role|content). Niemal pewny leak.
#   POSSIBLE — dowolny inny PL-string-literał poza komentarzem/docstringiem.
#              Bywa FP (np. regex dopasowujący polską treść wejściową) → triaż.

# Dev-toole odpalane WYŁĄCZNIE ze źródła przez maintainera — polski tekst (w tym
# `print`) jest tam świadomy i poprawny (logi po PL dla polskiego dev-toola).
DEV_TOOLE = {
    "build_release.py", "generuj_dokumentacje.py",
    "audyt_leakow.py", "przeglad_tlumaczen.py", "odpowiedz_lokalnie.py",
    # Wspólne moduły rodziny `buduj_wielojezyczne_*` (v18.16 bramki, v18.17
    # rdzeń). Ta sama klasa co `przeglad_tlumaczen.py` — polskie diagnostyki dla
    # polskiego maintainera, zero powierzchni user-facing. Whitelista jest tu
    # czystsza niż baseline (wzorzec `_dev_log` z v18.5.4).
    #
    # WYPISANE JAWNIE, a nie objęte prefiksem `tlumacz_`, i to jest ważne:
    # `tlumacz_ai.py` NOSI ten sam prefiks, ale dev-toolem NIE JEST — chodzi
    # w runtime za GUI Poligloty, więc polski hard-kod jest tam realnym leakiem
    # i plik MUSI zostać skanowany.
    "tlumacz_bramki.py", "tlumacz_rdzen.py",
    "test_core_updater.py",
}

# Prefiks rodziny autotłumaczy. Każdy `buduj_wielojezyczne_*.py` jest z definicji
# dev-only: chodzi wyłącznie ze źródła, u maintainera, i NIE wchodzi do bundla
# PyInstallera — jego polskie `print` są świadome.
#
# Reguła prefiksowa, nie kolejna nazwa na liście, bo ten sam błąd popełniliśmy
# już dwa razy: `buduj_wielojezyczne_tryby.py` dopisano dopiero w patchu sanity
# po v18.15, a `buduj_wielojezyczne_opowiesci.py` wywrócił bramkę hard-kodów
# w buildzie v18.17. Roadmapa planuje jeszcze dwóch braci (Poliglota, akcenty)
# — mają być wykluczeni w chwili powstania, bez pamiętania o tej liście.
PREFIKS_AUTOTLUMACZY = "buduj_wielojezyczne_"


def czy_dev_tool(nazwa_pliku: str) -> bool:
    """Czy ten plik `.py` jest dev-toolem wyłączonym ze skanu hard-kodów?"""
    return nazwa_pliku in DEV_TOOLE or nazwa_pliku.startswith(PREFIKS_AUTOTLUMACZY)

# Metody wx (i pochodne), których string-argument widzi user wprost.
SINKI_USER_FACING = {
    "SetValue", "SetLabel", "SetLabelText", "SetName", "SetTitle", "SetHint",
    "SetToolTip", "SetStatusText", "SetHelpText", "SetPageText", "SetItemLabel",
    "MessageBox", "AppendText", "ShowMessage", "SetMessage",
}
# Lokalne callbacki postępu/statusu — string-arg jest user-facing (pasek/etykieta).
SINKI_POSTEP = {"on_postep", "on_status", "_update_progress_label"}
# Kontekst payloadu LLM: kwarg `content=`/`system=` albo dict z kluczem role|content.
KWARG_LLM = {"content", "system"}
KLUCZE_DICT_LLM = {"role", "content"}
# Funkcje, których string-arg NIE jest user-facing PL (i18n-klucz / dev-log).
# `_dev_log` (core_llm/rezyser_ai) i `_dev_log_runtime` (core_rezyser) to strażowane
# dev-printy na stdout dewelopera (w paczce release stdout=None → milczą) — PL tekst
# tam jest świadomy i poprawny, jak w dev-toolach.
FUNC_POMIJANE = {"t", "_", "_dev_log_runtime", "_dev_log"}
# Kwargi przenoszące KLUCZ i18n / techniczny detal — nie treść user-facing.
KWARG_POMIJANE = {"detal", "klucz_i18n", "klucz_tytul", "klucz"}

# Diacritic-free polskie słowa-sygnały (czasowniki/komunikaty) — uzupełniają
# detekcję znakową dla linii bez ą/ę/ł…, ale BEZ generycznych rzeczowników
# („plik", „kod"), które jako identyfikatory/klucze dawały false-positives.
PL_SLOWA = [
    "Podaj", "Wykryto", "Kontynuuj", "Wysyłanie", "Przetwarzanie", "Budowanie",
    "Gotowe", "Pomijam", "Zapisano", "Wczytaj", "Zapisz", "Anuluj", "Tłumaczenie",
    "Generowanie", "Inicjowanie", "Zachowaj", "Odpowiedź", "Błąd", "Postęp",
    "Wystąpił",
]
RE_PL_SLOWA = re.compile(
    r"(?<![\wąęółńśćźżĄĘÓŁŃŚĆŹŻ])(?:"
    + "|".join(re.escape(s) for s in PL_SLOWA)
    + r")(?![\wąęółńśćźżĄĘÓŁŃŚĆŹŻ])",
    re.IGNORECASE,
)


@dataclass
class LeakPy:
    """Pojedynczy podejrzany PL-string-literał w źródle `.py`."""
    plik: str
    linia: int
    poziom: str            # „LIKELY" | „POSSIBLE"
    powod: str             # „znak-PL:ł" | „slowo-PL:Podaj"
    kontekst: str          # nazwa wywołania/kwargu („SetValue", „content=", „—")
    tekst: str             # treść literału (przycięta)


def _detektor_pl_en():
    """Buduje lingua-detektor PL↔EN (lazy) dla diacritic-free polskich literałów.

    Skan `.py` nie ma „języka docelowego" jak docs — interesuje nas tylko, czy
    literał jest polski. Restrykcja do {POLISH, ENGLISH} tnie szum (większość
    literałów aplikacji to PL albo EN: prompty, detale błędów).
    """
    from lingua import Language, LanguageDetectorBuilder
    return LanguageDetectorBuilder.from_languages(
        Language.POLISH, Language.ENGLISH,
    ).build()


def _sygnal_pl(tekst: str, detektor=None, *, prog_lingua: float = 0.70) -> str:
    """Zwraca krótki powód, gdy tekst wygląda na polski; inaczej ''.

    Trzy warstwy (jak docs-detektor): znaki diakrytyczne → kuratorskie słowa →
    `lingua` dla dłuższych literałów (łapie diacritic-free PL typu „Blok 1/2
    odzyskany z pliku zapisu", którego dwie pierwsze warstwy przepuszczają).
    """
    znaki = RE_PL_ZNAKI.findall(tekst)
    if znaki:
        return f"znak-PL:{''.join(sorted(set(znaki)))}"
    m = RE_PL_SLOWA.search(tekst)
    if m:
        return f"slowo-PL:{m.group(0)}"
    if detektor is not None:
        # f-string placeholdery {…} mylą lingua — liczymy litery po ich usunięciu.
        czysty = tekst.replace("{…}", " ")
        # Tylko PROZA (≥1 spacja) — odsiewa snake_case klucze i18n / identyfikatory,
        # które lingua myli z polskim (np. „ai_ostrzezenie_iso").
        if " " not in czysty.strip():
            return ""
        if sum(ch.isalpha() for ch in czysty) >= _MIN_LITER_LINGUA:
            cv = detektor.compute_language_confidence_values(czysty)
            if cv and cv[0].language.name == "POLISH" and cv[0].value >= prog_lingua:
                return f"lingua:PL {cv[0].value:.2f}"
    return ""


def _tekst_literalu(node: ast.AST) -> str:
    """Rozwija ``ast.Constant``(str) i ``ast.JoinedStr`` (f-string) do tekstu.

    Dla f-stringa części `{...}` zastępowane są markerem `{…}` — wystarcza do
    detekcji sygnału PL w częściach literalnych i do czytelnego raportu.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        czesci: list[str] = []
        for v in node.values:
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                czesci.append(v.value)
            else:
                czesci.append("{…}")
        return "".join(czesci)
    return ""


def _nazwa_funkcji(func: ast.AST) -> str:
    """Ostatni człon wywoływanej funkcji: ``obj.SetValue`` → „SetValue", ``t`` → „t"."""
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def _kontekst_wezla(node: ast.AST) -> tuple[str | None, set[str], str]:
    """Wspina się po rodzicach: (nazwa_kwargu, klucze_dict, nazwa_wywołania).

    Zatrzymuje się na pierwszym ``ast.Call`` (sink). Po drodze zapamiętuje
    nazwę kwargu (``content=``) i klucze najbliższego dict-a (payload LLM).
    """
    kwarg: str | None = None
    klucze: set[str] = set()
    func = ""
    cur = getattr(node, "_parent", None)
    gleb = 0
    while cur is not None and gleb < 8:
        if isinstance(cur, ast.keyword) and cur.arg and kwarg is None:
            kwarg = cur.arg
        elif isinstance(cur, ast.Dict) and not klucze:
            klucze = {
                k.value for k in cur.keys
                if isinstance(k, ast.Constant) and isinstance(k.value, str)
            }
        elif isinstance(cur, ast.Call):
            func = _nazwa_funkcji(cur.func)
            break
        cur = getattr(cur, "_parent", None)
        gleb += 1
    return kwarg, klucze, func


def _analizuj_plik(sciezka: Path, detektor=None) -> list[LeakPy]:
    """Skanuje jeden plik `.py` pod kątem PL-string-literałów (poza docstring/komentarz)."""
    try:
        zrodlo = sciezka.read_text(encoding="utf-8")
        drzewo = ast.parse(zrodlo, filename=str(sciezka))
    except (OSError, SyntaxError):
        return []

    # Wskaźniki na rodzica (AST ich nie trzyma) — potrzebne do klasyfikacji.
    for rodzic in ast.walk(drzewo):
        for dziecko in ast.iter_child_nodes(rodzic):
            dziecko._parent = rodzic  # type: ignore[attr-defined]

    # Docstringi (pierwszy statement modułu/klasy/funkcji) — pomijane.
    docstringi: set[int] = set()
    for w in ast.walk(drzewo):
        if isinstance(w, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            ciało = getattr(w, "body", [])
            if (ciało and isinstance(ciało[0], ast.Expr)
                    and isinstance(ciało[0].value, ast.Constant)
                    and isinstance(ciało[0].value.value, str)):
                docstringi.add(id(ciało[0].value))

    leaki: list[LeakPy] = []
    for w in ast.walk(drzewo):
        if isinstance(w, ast.JoinedStr):
            wezel: ast.AST = w
        elif isinstance(w, ast.Constant) and isinstance(w.value, str):
            if id(w) in docstringi:
                continue
            # Constanty wewnątrz f-stringa obsługujemy przez JoinedStr (jako całość).
            if isinstance(getattr(w, "_parent", None), (ast.JoinedStr, ast.FormattedValue)):
                continue
            wezel = w
        else:
            continue

        tekst = _tekst_literalu(wezel)
        powod = _sygnal_pl(tekst, detektor)
        if not powod:
            continue

        kwarg, klucze, func = _kontekst_wezla(wezel)
        if kwarg in KWARG_POMIJANE or func in FUNC_POMIJANE:
            continue

        if func in SINKI_USER_FACING or func in SINKI_POSTEP:
            poziom, opis = "LIKELY", (func or "—")
        elif kwarg in KWARG_LLM or (klucze & KLUCZE_DICT_LLM):
            poziom, opis = "LIKELY", (f"{kwarg}=" if kwarg else "LLM-dict")
        else:
            opis = func or (f"{kwarg}=" if kwarg else "—")
            poziom = "POSSIBLE"

        leaki.append(LeakPy(
            plik=sciezka.name,
            linia=getattr(wezel, "lineno", 0),
            poziom=poziom,
            powod=powod,
            kontekst=opis,
            tekst=" ".join(tekst.split())[:120],
        ))
    return leaki


def skanuj_zrodla_py(root: Path = ROOT) -> list[LeakPy]:
    """Skanuje moduły aplikacji (`*.py` w roocie, bez dev-tooli — :func:`czy_dev_tool`)."""
    detektor = _detektor_pl_en()
    leaki: list[LeakPy] = []
    for sciezka in sorted(root.glob("*.py")):
        if czy_dev_tool(sciezka.name):
            continue
        leaki.extend(_analizuj_plik(sciezka, detektor))
    return leaki


# ---------------------------------------------------------------------------
# BRAMKA `.py` — baseline zaakceptowanych hard-kodów (od v18.5.4)
# ---------------------------------------------------------------------------
# Skan `.py` to LEJEK over-reportujący (jak docs/ui): na czystym drzewie ~92
# trafienia POSSIBLE, w 100% triaged jako by-design (wyjątki-inwarianty, regexy
# wielojęzyczne, stałe alfabetu, dev-printy, prompty-szablony Managera, fallbacki
# recipe YAML, sentinele, tagi-kotwice payloadu). Surowy lejek jako twarda bramka
# blokowałby każdy build, więc — ten sam wzorzec BASELINE co PL-leak: snapshot
# zaakceptowanych trafień w `audyt_leakow_py_baseline.json`, bramka pada TYLKO na
# nadwyżkę (nowy hard-kod, zwł. KAŻDE LIKELY = string do sinka user/LLM-facing).
def zbierz_leaki_py(root: Path = ROOT) -> dict[str, list[str]]:
    """Zbiera skan `.py` jako `{"<plik>": ["<poziom>|<powod_norm>|<tekst>", ...]}`.

    Klucz = nazwa pliku (STABILNA — bez numeru linii, odporna na przesunięcia).
    Wartość = posortowany multiset wpisów kodujących poziom + znormalizowany powód
    + treść literału; treść w powodzie rozróżnia różne hard-kody w jednym pliku.
    Float pewności lingua znormalizowany (`_normalizuj_powod`), inaczej drobne
    wahanie modelu rozjeżdżałoby baseline. Rzuca `ImportError` bez `lingua`
    (wołający `bramka_py` łapie i degraduje łagodnie).
    """
    wynik: dict[str, list[str]] = {}
    for l in skanuj_zrodla_py(root):
        wpis = f"{l.poziom}|{_normalizuj_powod(l.powod)}|{l.tekst}"
        wynik.setdefault(l.plik, []).append(wpis)
    return {k: sorted(v) for k, v in wynik.items()}


# ---------------------------------------------------------------------------
# BRAMKA KONTRAKTU CONTRIBUTING w dev-toolach (v18.24)
# ---------------------------------------------------------------------------
# `czy_dev_tool()` wyłącza CAŁĄ rodzinę dev-tooli ze skanu hard-kodów — słusznie,
# bo ich polski `print` postępu jest świadomy i dozwolony. Ale ten sam wyłącznik
# przez wydania ukrywał 60 polskich helpów CLI i ~118 polskich linii ❌/⚠️, wbrew
# `CONTRIBUTING.md` („anything that tells you what a tool does, how to run it, or
# why it failed is in English"). Ta bramka patrzy WYŁĄCZNIE na kategorie objęte
# kontraktem, więc nie wraca do pilnowania chatteru:
#
#   * teksty argparse: `help=`, `description=`, `epilog=`, `metavar=`,
#   * literały z `❌` albo `⚠️` (legenda emoji: error / warning),
#   * banery `==========` (nagłówki bloków werdyktu).
#
# CELOWO NIEOBJĘTE: linie `✅`/`⏭️`/`ℹ️`. Werdykt („✅ Success: 3/8") i chatter
# („✅ fi/plik.yaml: OK") są mechanicznie NIEROZRÓŻNIALNE, a kontrakt dopuszcza
# polski chatter — bramka, która by je zrównała, produkowałaby fałszywe alarmy
# w liczbie, po której nikt by jej nie czytał. Werdykty pilnuje przegląd, nie skan.
#
# Bramka jest OSTRZEGAJĄCA (exit 0 nawet przy nadwyżce). Nowy polski help to
# usterka kosmetyczna, nie zepsuta paczka — blokowanie builda byłoby nieproporcjonalne.
_KWARGI_CLI = {"help", "description", "epilog", "metavar"}

# Dev-toole POZA kontraktem — narzędzia, których kontrybutor nie uruchomi.
# `odpowiedz_lokalnie.py` wymaga zalogowanego `gh` CLI maintainera i domyka
# issue jego głosem; dla kogokolwiek innego jest martwe, więc jego polskie
# helpy nie są barierą wejścia. Whitelista, nie baseline — decyzja o roli
# pliku, nie snapshot jego treści (ten sam argument, co przy `DEV_TOOLE`).
POZA_KONTRAKTEM = {"odpowiedz_lokalnie.py"}

# Repozytorium jest polskojęzyczne, więc angielskie zdanie dev-toola RUTYNOWO
# cytuje polskie IDENTYFIKATORY: nazwy flag (`--tylko-walidacja`), nazwy plików
# (`finski,rosyjski`), stałe (`KLASY_POL`, `BATCH_MAX_ZNAKOW`). Bez zamaskowania
# ich `lingua` orzeka „POLISH" o zdaniu w rodzaju „========== SUMMARY
# (--finalizuj) ==========" i baseline puchnie od wpisów, w których nie ma nic
# do naprawienia — a wtedy nikt go nie czyta i realny regres przechodzi.
# Maskujemy WYŁĄCZNIE w tym skanie; `_sygnal_pl` zostaje nietknięty, bo od jego
# zachowania zależą dwa istniejące baseline'y.
_RE_MASKA_IDENTYFIKATOROW = re.compile(
    r"`[^`]*`"                      # `literał techniczny` / `--flaga` / ścieżka
    r"|--?[a-z][a-z0-9-]*"          # --tylko-walidacja, -f
    r"|\b[A-Z][A-Z0-9_]{3,}\b"      # KLASY_POL, BATCH_MAX_ZNAKOW
    r"|\b\w+\.(?:yaml|py|json|env|txt|html|md)\b"   # nazwa_pliku.yaml
)


def _literaly_kontraktu(sciezka: Path, detektor=None) -> list[LeakPy]:
    """Polskie literały łamiące kontrakt CONTRIBUTING w JEDNYM dev-toolu.

    Różnica wobec :func:`_analizuj_plik`, poza zawężeniem do kategorii: ten skan
    ZAGLĄDA DO ZAGNIEŻDŻEŃ f-stringów. Pomijamy tylko literalne segmenty samego
    f-stringa (rodzic = ``JoinedStr``), a nie wszystko pod ``FormattedValue`` —
    bo `buduj_wielojezyczne_docs` trzymał polskie „❌ Błędów:" właśnie tam,
    w zagnieżdżonym f-stringu wewnątrz wyrażenia warunkowego, i pierwszy przebieg
    sprzątania v18.24 je z tego powodu przeoczył.
    """
    try:
        zrodlo = sciezka.read_text(encoding="utf-8")
        drzewo = ast.parse(zrodlo, filename=str(sciezka))
    except (OSError, SyntaxError):
        return []

    for rodzic in ast.walk(drzewo):
        for dziecko in ast.iter_child_nodes(rodzic):
            dziecko._parent = rodzic  # type: ignore[attr-defined]

    docstringi: set[int] = set()
    for w in ast.walk(drzewo):
        if isinstance(w, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            ciało = getattr(w, "body", [])
            if (ciało and isinstance(ciało[0], ast.Expr)
                    and isinstance(ciało[0].value, ast.Constant)
                    and isinstance(ciało[0].value.value, str)):
                docstringi.add(id(ciało[0].value))

    trafienia: list[LeakPy] = []
    for w in ast.walk(drzewo):
        if isinstance(w, ast.JoinedStr):
            wezel: ast.AST = w
        elif isinstance(w, ast.Constant) and isinstance(w.value, str):
            if id(w) in docstringi:
                continue
            # Segmenty literalne f-stringa raportuje sam `JoinedStr` (jako całość).
            if isinstance(getattr(w, "_parent", None), ast.JoinedStr):
                continue
            wezel = w
        else:
            continue

        tekst = _tekst_literalu(wezel)
        if not tekst:
            continue
        kwarg, _klucze, _func = _kontekst_wezla(wezel)
        if kwarg in _KWARGI_CLI:
            kategoria = f"cli:{kwarg}"
        elif "❌" in tekst:
            kategoria = "blad"
        elif "⚠️" in tekst:
            kategoria = "ostrzezenie"
        elif "=====" in tekst:
            kategoria = "baner"
        else:
            continue
        powod = _sygnal_pl(_RE_MASKA_IDENTYFIKATOROW.sub(" ", tekst), detektor)
        if not powod:
            continue
        trafienia.append(LeakPy(
            plik=sciezka.name,
            linia=getattr(wezel, "lineno", 0),
            poziom=kategoria,
            powod=powod,
            kontekst=(kwarg + "=") if kwarg else "print",
            tekst=" ".join(tekst.split())[:120],
        ))
    return trafienia


def skanuj_kontrakt(root: Path = ROOT) -> list[LeakPy]:
    """Skan kontraktu po dev-toolach — czyli po plikach, które `--bramka-py` POMIJA."""
    detektor = _detektor_pl_en()
    trafienia: list[LeakPy] = []
    for sciezka in sorted(root.glob("*.py")):
        if not czy_dev_tool(sciezka.name) or sciezka.name in POZA_KONTRAKTEM:
            continue
        trafienia.extend(_literaly_kontraktu(sciezka, detektor))
    return trafienia


def zbierz_leaki_kontraktu(root: Path = ROOT) -> dict[str, list[str]]:
    """Skan kontraktu jako `{"<plik>": ["<kategoria>|<powod_norm>|<tekst>", ...]}`.

    Klucz = nazwa pliku (bez numeru linii — odporny na przesunięcia), wartość =
    multiset wpisów. Ten sam kanon co :func:`zbierz_leaki_py`.
    """
    wynik: dict[str, list[str]] = {}
    for t in skanuj_kontrakt(root):
        wynik.setdefault(t.plik, []).append(
            f"{t.poziom}|{_normalizuj_powod(t.powod)}|{t.tekst}")
    return {k: sorted(v) for k, v in wynik.items()}


def bramka_kontraktu() -> WynikBramki:
    """Bramka kontraktu CONTRIBUTING względem `audyt_leakow_kontrakt_baseline.json`.

    Łagodna degradacja bez `lingua` (jak pozostałe bramki). Wołający traktuje
    nadwyżkę jako OSTRZEŻENIE — patrz komentarz sekcji.
    """
    try:
        aktualne = zbierz_leaki_kontraktu()
    except ImportError as exc:
        return WynikBramki(True, {}, True, f"lingua not available ({exc})")
    nowe = roznica_wzgledem_baseline(
        aktualne, wczytaj_baseline(BASELINE_KONTRAKT_PATH))
    return WynikBramki(not nowe, nowe, False, "")


def bramka_py() -> WynikBramki:
    """Bramka skanu źródeł `.py` względem `audyt_leakow_py_baseline.json`.

    Łagodna degradacja bez `lingua` (jak `bramka_docs`): zwraca `pominieto=True,
    czysto=True` — nie blokuje kontrybutora bez pełnego dev-env. `nowe` to wpisy
    PONAD baseline (nowy hard-kod / przesunięty poziom-powód-tekst).
    """
    try:
        aktualne = zbierz_leaki_py()
    except ImportError as exc:
        return WynikBramki(True, {}, True, f"lingua not available ({exc})")
    nowe = roznica_wzgledem_baseline(aktualne, wczytaj_baseline(BASELINE_PY_PATH))
    return WynikBramki(not nowe, nowe, False, "")


# ---------------------------------------------------------------------------
# CLI — mapa audytu (bez API)
# ---------------------------------------------------------------------------
def _szablony_docelowe(kod: str) -> list[str]:
    folder = DICT_DIR / kod / FOLDER_GUI / FOLDER_DOKUMENTACJA
    if not folder.is_dir():
        return []
    return sorted(p.name for p in folder.glob("*.yaml"))


def _main_py() -> int:
    """Tryb `--py`: skan źródeł aplikacji, raport pogrupowany per plik (LIKELY first)."""
    leaki = skanuj_zrodla_py()
    if not leaki:
        print("✅ Skan źródeł `.py`: brak podejrzanych PL hard-kodów (poza dev-toolami).")
        return 0

    per_plik: dict[str, list[LeakPy]] = {}
    for l in leaki:
        per_plik.setdefault(l.plik, []).append(l)

    likely = sum(1 for l in leaki if l.poziom == "LIKELY")
    possible = len(leaki) - likely
    print(f"🔎 Skan źródeł `.py`: {likely} LIKELY + {possible} POSSIBLE "
          f"w {len(per_plik)} plik(ach). LIKELY = niemal pewny leak; POSSIBLE = do triażu.\n")

    for plik in sorted(per_plik):
        pozycje = sorted(per_plik[plik], key=lambda l: (l.poziom != "LIKELY", l.linia))
        ile_l = sum(1 for l in pozycje if l.poziom == "LIKELY")
        print(f"📄 {plik}: {len(pozycje)} ({ile_l} LIKELY)")
        for l in pozycje:
            flaga = "❗" if l.poziom == "LIKELY" else "·"
            print(f"   {flaga} L{l.linia} [{l.kontekst}] ({l.powod}): {l.tekst}")
        print()

    print(f"========== TOTAL: {likely} LIKELY + {possible} POSSIBLE ==========")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="PL-leak detector for dictionaries/<code>/gui/dokumentacja/*.yaml "
                    "(per-line lingua + curated PL terms + PL characters).",
    )
    grupa = parser.add_mutually_exclusive_group(required=True)
    grupa.add_argument("-l", "--jezyki", type=str, default="",
                       help=f"CSV of ISO codes (e.g. is,fi). Allowed: {', '.join(KODY_DOCELOWE)}.")
    grupa.add_argument("-a", "--wszystkie", action="store_true",
                       help="Scan every target language (docs YAML).")
    grupa.add_argument("--py", action="store_true",
                       help="Scan the application sources `*.py` for PL hard-coding "
                            "(user-facing / LLM-facing), dev tools excluded.")
    grupa.add_argument("--bramka", action="store_true",
                       help="CI/build GATE: scans all docs against the baseline "
                            f"({BASELINE_PATH.name}). Exit 1 ONLY on leaks above "
                            "the baseline (new/shifted). Clean false positives "
                            "already in the baseline do not block.")
    grupa.add_argument("--zapisz-baseline", dest="zapisz_baseline", action="store_true",
                       help="Regenerate the baseline from the current hits (after a "
                            "LEGITIMATE docs content change). Overwrites "
                            f"{BASELINE_PATH.name} — review the diff before committing.")
    grupa.add_argument("--bramka-py", dest="bramka_py", action="store_true",
                       help="CI/build GATE for the `.py` sources against the baseline "
                            f"({BASELINE_PY_PATH.name}). Exit 1 on hard-coding "
                            "above the baseline (new, LIKELY especially).")
    grupa.add_argument("--zapisz-baseline-py", dest="zapisz_baseline_py", action="store_true",
                       help="Regenerate the `.py` baseline from the current source scan. "
                            f"Overwrites {BASELINE_PY_PATH.name} — review the diff before committing.")
    grupa.add_argument("--bramka-kontrakt", dest="bramka_kontrakt", action="store_true",
                       help="WARNING-ONLY gate on the CONTRIBUTING language contract in the "
                            "dev tools (argparse help/description/epilog/metavar, ❌/⚠️ lines "
                            f"and `====` banners) against {BASELINE_KONTRAKT_PATH.name}. "
                            "Always exits 0 — a Polish help text is cosmetic, not a broken "
                            "pack. Polish progress chatter is allowed and NOT checked.")
    grupa.add_argument("--zapisz-baseline-kontrakt", dest="zapisz_baseline_kontrakt",
                       action="store_true",
                       help="Regenerate the contract baseline from the current scan (use it "
                            "for legitimate exceptions, e.g. Polish CODE IDENTIFIERS quoted "
                            f"inside a message). Overwrites {BASELINE_KONTRAKT_PATH.name} — "
                            "review the diff before committing.")
    parser.add_argument("--szczegoly", action="store_true",
                        help="Print every leaking line (default: a counter per section).")
    parser.add_argument("--prog", type=float, default=0.70,
                        help="Lingua confidence threshold for class A (default 0.70).")
    args = parser.parse_args()

    if args.py:
        return _main_py()

    if args.zapisz_baseline_kontrakt:
        try:
            aktualne = zbierz_leaki_kontraktu()
        except ImportError as exc:
            print(f"❌ Cannot build the contract baseline — `lingua` is missing ({exc}).")
            return 2
        zapisz_baseline(aktualne, BASELINE_KONTRAKT_PATH)
        ile = sum(len(v) for v in aktualne.values())
        print(f"✅ Saved the contract baseline: {ile} hit(s) in {len(aktualne)} file(s) → "
              f"{BASELINE_KONTRAKT_PATH.name}. Review the diff before committing.")
        return 0

    if args.bramka_kontrakt:
        wynik = bramka_kontraktu()
        print("\n========== CONTRIBUTING CONTRACT GATE (dev tools) ==========")
        if wynik.pominieto:
            print(f"⚠️  Gate skipped: {wynik.powod_pominiecia}. "
                  "Install `lingua` to run it (maintainer/CI).")
            return 0
        if wynik.czysto:
            print(f"✅ No Polish CLI text or ❌/⚠️ line above the baseline "
                  f"({BASELINE_KONTRAKT_PATH.name}).")
            print("============================================================")
            return 0
        ile = sum(len(v) for v in wynik.nowe.values())
        print(f"⚠️  {ile} contract violation(s) ABOVE the baseline in "
              f"{len(wynik.nowe)} file(s):")
        for klucz, powody in sorted(wynik.nowe.items()):
            for p in powody:
                print(f"  • {klucz}: {p}")
        print("Fix: write the line in English (CONTRIBUTING: anything saying what a "
              "tool does, how to run it, or why it failed). If the Polish fragment is "
              "a CODE IDENTIFIER quoted inside the message — regenerate the baseline: "
              f"`python {Path(__file__).name} --zapisz-baseline-kontrakt`.")
        print("============================================================")
        return 0   # OSTRZEŻENIE, nie bramka blokująca — patrz komentarz sekcji

    if args.zapisz_baseline_py:
        try:
            aktualne = zbierz_leaki_py()
        except ImportError as exc:
            print(f"❌ Cannot build the `.py` baseline — `lingua` is missing ({exc}).")
            return 2
        zapisz_baseline(aktualne, BASELINE_PY_PATH)
        ile = sum(len(v) for v in aktualne.values())
        print(f"✅ Saved the `.py` baseline: {ile} hit(s) in {len(aktualne)} file(s) → "
              f"{BASELINE_PY_PATH.name}. Review the diff before committing.")
        return 0

    if args.bramka_py:
        wynik = bramka_py()
        print("========== HARD-CODED PL GATE `.py` (vs baseline) ==========")
        if wynik.pominieto:
            print(f"⚠️  Gate skipped: {wynik.powod_pominiecia}. "
                  "Install `lingua` to run it (maintainer/CI).")
            return 0
        if wynik.czysto:
            print(f"✅ No hard-coded strings above the baseline ({BASELINE_PY_PATH.name}).")
            return 0
        ile = sum(len(v) for v in wynik.nowe.values())
        print(f"❌ {ile} hard-coded string(s) ABOVE the baseline in {len(wynik.nowe)} "
              "file(s) (new or shifted):")
        for klucz, powody in sorted(wynik.nowe.items()):
            for p in powody:
                print(f"  • {klucz}: {p}")
        print("Fix: move the string into i18n (`t()`) or a YAML recipe. If it is a "
              "DELIBERATE, by-design hard-code — regenerate the baseline: "
              f"`python {Path(__file__).name} --zapisz-baseline-py` and commit the diff.")
        print("============================================================")
        return 1

    if args.zapisz_baseline:
        try:
            aktualne = zbierz_wszystkie_leaki(prog_lingua=args.prog)
        except ImportError as exc:
            print(f"❌ Cannot build the baseline — `lingua` is missing ({exc}).")
            return 2
        zapisz_baseline(aktualne)
        ile = sum(len(v) for v in aktualne.values())
        print(f"✅ Saved the baseline: {ile} hit(s) in {len(aktualne)} section(s) → "
              f"{BASELINE_PATH.name}. Review the diff before committing.")
        return 0

    if args.bramka:
        wynik = bramka_docs(prog_lingua=args.prog)
        print("========== DOCS LEAK GATE (vs baseline) ==========")
        if wynik.pominieto:
            print(f"⚠️  Gate skipped: {wynik.powod_pominiecia}. "
                  "Install `lingua` to run it (maintainer/CI).")
            return 0
        if wynik.czysto:
            print(f"✅ No leaks above the baseline ({BASELINE_PATH.name}).")
            return 0
        ile = sum(len(v) for v in wynik.nowe.values())
        print(f"❌ {ile} leak(s) ABOVE the baseline in {len(wynik.nowe)} section(s) "
              "(new or shifted fragment):")
        for klucz, powody in sorted(wynik.nowe.items()):
            print(f"  • {klucz}: {', '.join(powody)}")
        print("Fix: translate the leak in the template. If this is a DELIBERATE, "
              "legitimate content change — regenerate the baseline: "
              f"`python {Path(__file__).name} --zapisz-baseline` and commit the diff.")
        print("==================================================")
        return 1

    if args.wszystkie:
        kody = list(KODY_DOCELOWE)
    else:
        kody = [k.strip() for k in args.jezyki.split(",") if k.strip()]
        nieznane = [k for k in kody if k not in KODY_DOCELOWE]
        if nieznane:
            print(f"❌ Unknown codes: {', '.join(nieznane)}. Allowed: {', '.join(KODY_DOCELOWE)}.")
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
        # ui.yaml (od v18.5.3) — ta sama powierzchnia co bramka
        per_ui = leaki_ui_per_klucz(kod, detektor, prog_lingua=args.prog)
        if per_ui:
            ile = sum(len(v) for v in per_ui.values())
            leakow_jez += ile
            print(f"  📄 {NAZWA_UI}: {ile} leak(ów) w {len(per_ui)} kluczu/ach")
            for klucz, leaki in per_ui.items():
                powody = ", ".join(sorted({l.powod.split(':')[0] for l in leaki}))
                print(f"     • {klucz}: {len(leaki)}× [{powody}]")
                if args.szczegoly:
                    for l in leaki:
                        print(f"        L{l.linia_nr} ({l.powod}): {l.tekst}")
        if leakow_jez == 0:
            print("  ✅ czysto")
        suma_leakow += leakow_jez

    print(f"\n========== TOTAL: {suma_leakow} leak(s) in {len(kody)} language(s) ==========")
    return 1 if suma_leakow else 0


if __name__ == "__main__":
    sys.exit(main())
