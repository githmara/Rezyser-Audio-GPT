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

# Mapa {kod ISO: nazwa enum lingua} budowana DYNAMICZNIE ze
# `dictionaries/<kod>/podstawy.yaml::lingua` (bez źródłowego pl) — nowy język =
# nowy folder, zero edycji tutaj. Spójne z `core_poliglota._zbuduj_mapowanie_lingua`
# i `bot_i18n.mapa_iso_na_lingua` (lekka kopia: ten dev-tool celowo trzyma deps
# wąsko — sam `yaml` + lazy `lingua`, bez ciągnięcia silnika z docx/num2words).
# Mapowanie na enum robione lazy w `_zbuduj_detektor` (string → getattr).
def _skanuj_lingua_z_podstaw() -> dict[str, str]:
    """{kod ISO: NAZWA_ENUMA} z podstawy.yaml::lingua (pomija pl, puste, błędne)."""
    if not DICT_DIR.is_dir():
        return {}
    wynik: dict[str, str] = {}
    for p in sorted(DICT_DIR.iterdir()):
        if not p.is_dir() or p.name == KOD_ZRODLOWY:
            continue
        plik = p / "podstawy.yaml"
        if not plik.is_file():
            continue
        try:
            dane = yaml.safe_load(plik.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            continue
        if isinstance(dane, dict):
            wartosc = dane.get("lingua")
            if isinstance(wartosc, str) and wartosc.strip():
                wynik[p.name] = wartosc.strip().upper()
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
    "buduj_wielojezyczne_docs.py", "buduj_wielojezyczne_ui.py",
    "audyt_leakow.py", "przeglad_tlumaczen.py", "odpowiedz_lokalnie.py",
    "test_core_updater.py",
}

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
FUNC_POMIJANE = {"t", "_", "_dev_log_runtime"}
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
    """Skanuje wszystkie moduły aplikacji (`*.py` w roocie, bez DEV_TOOLE)."""
    detektor = _detektor_pl_en()
    leaki: list[LeakPy] = []
    for sciezka in sorted(root.glob("*.py")):
        if sciezka.name in DEV_TOOLE:
            continue
        leaki.extend(_analizuj_plik(sciezka, detektor))
    return leaki


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

    print(f"========== RAZEM: {likely} LIKELY + {possible} POSSIBLE ==========")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Detektor PL-leaków w dictionaries/<kod>/gui/dokumentacja/*.yaml "
                    "(lingua per-linia + kuratorskie PL-terminy + znaki PL).",
    )
    grupa = parser.add_mutually_exclusive_group(required=True)
    grupa.add_argument("--jezyki", type=str, default="",
                       help=f"CSV kodów ISO (np. is,fi). Dozwolone: {', '.join(KODY_DOCELOWE)}.")
    grupa.add_argument("--wszystkie", action="store_true",
                       help="Skanuj wszystkie języki docelowe (docs YAML).")
    grupa.add_argument("--py", action="store_true",
                       help="Skanuj źródła aplikacji `*.py` pod kątem PL hard-kodu "
                            "(user-facing / LLM-facing), z pominięciem dev-tooli.")
    parser.add_argument("--szczegoly", action="store_true",
                        help="Wypisz każdą linię-leak (domyślnie: licznik per sekcja).")
    parser.add_argument("--prog", type=float, default=0.70,
                        help="Próg pewności lingua dla klasy A (domyślnie 0.70).")
    args = parser.parse_args()

    if args.py:
        return _main_py()

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
