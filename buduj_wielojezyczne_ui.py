#!/usr/bin/env python
"""
buduj_wielojezyczne_ui.py — Batchowy autotłumacz interfejsu (i18n, Etap 2/5).

Czyta kanoniczne źródło `dictionaries/pl/gui/ui.yaml`, tłumaczy WYŁĄCZNIE
wartości stringowe (klucze nienaruszone) na języki docelowe i zapisuje
wynik w `dictionaries/<kod>/gui/ui.yaml` z zachowaniem komentarzy
sekcyjnych z oryginału.

Architektura (decyzja 13.1 — Etap 2):

  1. Wczytanie przez `ruamel.yaml.YAML(typ='rt')` (round-trip mode) —
     komentarze sekcyjne (np. `# COMMON – elementy wielokrotnego użytku`)
     i style block-scalar (`|-`, `|`) są zachowane bit w bit. Nagłówek
     z konwencjami PL jest podmieniany na auto-generowaną notkę
     „plik wygenerowany — nie edytuj ręcznie", analogicznie do `manual.yaml`.

  2. Walker drzewa zbiera wszystkie liście stringowe wraz z dotted-path
     (`app.nazwa`, `main.menu.narzedzia`, ...). Klucze, integery i listy
     są pomijane — w obecnym ui.yaml nie występują, ale walker nie
     przewraca się, gdy się pojawią (przejdzie obok).

  3. TOKENIZACJA dwuwarstwowa per-liść:
       * `{nazwa_parametru}` (placeholder dynamiczny) → `⟦P{i}⟧`
       * `\\t(?:Ctrl|Alt|Shift|Cmd)+...` (skrót wxPython)  → `⟦S{j}⟧`
     Znak `&` (akcelerator menu) jest CELOWO niezatokenizowany —
     LLM dostaje go widocznego, z explicit instrukcją relokacji
     (zob. `_PROMPT_SYSTEMOWY`). Tokenizacja `&` byłaby błędem —
     model nie miałby jak przesunąć ampersanda na sensowną literę.

  4. Liście trafiają do Anthropic Messages API (`messages.create`) w
     porcjach po `BATCH_SIZE`, ze STRUKTURALNYM wyjściem
     `output_config={"format": {"type": "json_schema", "schema": SCHEMA_TLUMACZENIA}}`
     — gwarancja mocniejsza niż OpenAI `json_object` (wymusza schemat
     `{"translations": [{"id", "target"}]}`, nie tylko poprawny JSON).
     Ucięcie odpowiedzi (`stop_reason == "max_tokens"`) przerywa CAŁY
     batch (sygnał: zmniejsz `BATCH_SIZE`).

  5. WALIDACJE per-liść (przed iniekcją):
       * Multiset tokenów `⟦P\\d+⟧` i `⟦S\\d+⟧` w `tgt` musi być
         identyczny jak w `src` (parity check — reuzywamy semantykę
         z `buduj_wielojezyczne_docs.py`).
       * `tgt.count('&') == src.count('&')` — akcelerator nie może
         zniknąć ani się zduplikować.
       * Wszystkie id z requestu MUSZĄ być w odpowiedzi (no missing,
         no extra). Każda niezgodność blokuje zapis pliku.

  6. DETOKENIZACJA + ITERACYJNE NADPISANIE liści w drzewie ruamel
     (set_path po dotted-path). Dump przez `ruamel.yaml.dump()` →
     StringIO, podmiana topowego comment-block na auto-nagłówek,
     zapis UTF-8 + LF.

Użycie:
  python buduj_wielojezyczne_ui.py --wszystkie                 # en, fi, ru, is, it
  python buduj_wielojezyczne_ui.py --jezyki en                 # tylko angielski
  python buduj_wielojezyczne_ui.py --jezyki en,fi --skip-existing
  python buduj_wielojezyczne_ui.py --jezyki en --dry-run       # tokenizacja, zero API

Wymaga: `ANTHROPIC_API_KEY` w środowisku (to samo konto co GUI Poliglota /
`buduj_wielojezyczne_docs.py`). Moduł NIE zależy od wxPython —
uruchamialny w CLI / CI bez inicjalizacji GUI.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

import przeglad_tlumaczen


# ---------------------------------------------------------------------------
# STDOUT UTF-8 (spójnie z resztą skryptów buildowych — cmd.exe vs cp1250)
# ---------------------------------------------------------------------------
if sys.platform == "win32":
    for strumien in (sys.stdout, sys.stderr):
        try:
            strumien.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass


# ---------------------------------------------------------------------------
# Stałe ścieżek (analogicznie do buduj_wielojezyczne_docs.py)
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
DICT_DIR = ROOT / "dictionaries"

FOLDER_GUI = "gui"
NAZWA_UI = "ui.yaml"
KOD_ZRODLOWY = "pl"

# Chunking — Claude Sonnet 4.6 (konsolidacja v18.x). MAX_TOKENS_OUT poniżej progu
# non-streaming SDK Anthropic (~16k → brak ryzyka HTTP-timeoutu). Sformatowany JSON
# `{"translations": [...]}` dla całego ui.yaml (~450 liści) przekraczałby limit
# wyjścia, więc tniemy na porcje po BATCH_SIZE liści. Zmniejszone ze 150 → 80
# (migracja na Anthropic): structured outputs dokłada narzut schematu, a języki
# rozwlekłe/cyrylica puchną — 80 krótkich liści UI ≈ kilka k tokenów outputu,
# bezpiecznie. Ucięcie (`stop_reason="max_tokens"`) przerywa CAŁY batch (sygnał:
# zejdź jeszcze niżej z BATCH_SIZE), a nie tylko bieżący chunk/język.
BATCH_SIZE = 80
MAX_TOKENS_OUT = 16_000

# Schemat structured-outputs (Anthropic `output_config.format`). Gwarantuje kształt
# odpowiedzi na poziomie API (mocniej niż OpenAI `json_object`). Ograniczenia JSON
# Schema strukturalnych wyjść: brak min/maxLength, każdy obiekt z
# `additionalProperties: false`. `id`+`target` 1:1 z payloadem `items`.
SCHEMA_TLUMACZENIA = {
    "type": "object",
    "properties": {
        "translations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "target": {"type": "string"},
                },
                "required": ["id", "target"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["translations"],
    "additionalProperties": False,
}


# ---------------------------------------------------------------------------
# Tokenizacja — dwa typy markerów
# ---------------------------------------------------------------------------
# Placeholder dynamiczny `{nazwa_parametru}` — semantyka tożsama z
# `buduj_wielojezyczne_docs.py` (`PLACEHOLDER_REGEX` tam vs. tu).
PLACEHOLDER_REGEX = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_.]*)\}")

# Skrót klawiszowy wxPython w etykietach menu: tabulator + modyfikator(y) +
# klawisz, np. `\tCtrl+1`, `\tAlt+F4`, `\tCtrl+Shift+P`. wxPython parsuje
# ten suffix automatycznie i NIE wyświetla go w GUI (zamienia na natywny
# accelerator OS), ale string MUSI dotrzeć do wxPython 1:1 — modyfikatory
# `Ctrl`, `Alt`, `Shift` nie są lokalizowane (`.clinerules`).
SHORTCUT_REGEX = re.compile(
    r"\t(?:Ctrl|Alt|Shift|Cmd|Super)(?:\+(?:Ctrl|Alt|Shift|Cmd|Super))*\+\S+"
)

TOKEN_PH = "⟦P{}⟧"   # tokenizowany placeholder (n.p. ⟦P0⟧)
TOKEN_SC = "⟦S{}⟧"   # tokenizowany skrót klawiszowy (n.p. ⟦S0⟧)
# Wspólny regex do walidacji parzystości — łapie obie klasy markerów.
TOKEN_PARITY_REGEX = re.compile(r"⟦([PS]\d+)⟧")


# ---------------------------------------------------------------------------
# Mapa języków docelowych — ładowana z `jezyki_docelowe.yaml` (od 2026-06-16)
# ---------------------------------------------------------------------------
# WSPÓLNY rejestr z `buduj_wielojezyczne_docs.py` (single source): oba siostrzane
# narzędzia czytają TEN SAM plik `jezyki_docelowe.yaml` (root repo), utrzymywany
# przez dev tool `refresh_languages.py`. Kontrybutor dodaje język raz (wrzuć
# `dictionaries/<kod>/` + refresh) i działa zarówno dla UI, jak i dla docs — bez
# edycji Pythona. `_FALLBACK_JEZYKOW` = safety net, gdy pliku brak (świeży checkout
# przed pierwszym refresh). Czyta przez ruamel (ten sam YAML co reszta narzędzia).
_REJESTR_JEZYKOW = ROOT / "jezyki_docelowe.yaml"
_FALLBACK_JEZYKOW: dict[str, str] = {
    "en": "angielski", "fi": "fiński", "ru": "rosyjski", "is": "islandzki",
    "it": "włoski", "de": "niemiecki", "fr": "francuski", "es": "hiszpański",
}


def _wczytaj_mape_jezykow() -> dict[str, str]:
    """Wczytuje rejestr ISO→nazwa z `jezyki_docelowe.yaml` (fallback: wbudowane 8).

    Single source spójny z `buduj_wielojezyczne_docs.py`. Filtruje wpisy
    nie-stringowe i język źródłowy `pl` (źródło, nie cel tłumaczenia).
    """
    if not _REJESTR_JEZYKOW.is_file():
        return dict(_FALLBACK_JEZYKOW)
    try:
        with open(_REJESTR_JEZYKOW, "r", encoding="utf-8") as fh:
            dane = YAML(typ="safe").load(fh)
    except Exception:  # noqa: BLE001 — fail-soft: zły/niedostępny rejestr → fallback
        return dict(_FALLBACK_JEZYKOW)
    if not isinstance(dane, dict):
        return dict(_FALLBACK_JEZYKOW)
    mapa = {
        str(k): str(v)
        for k, v in dane.items()
        if isinstance(k, str) and isinstance(v, str) and k != KOD_ZRODLOWY
    }
    return mapa or dict(_FALLBACK_JEZYKOW)


MAPA_JEZYKOW: dict[str, str] = _wczytaj_mape_jezykow()


# ---------------------------------------------------------------------------
# Natywna nazwa języka docelowego (do promptu — zamiast polskiego „fiński")
# ---------------------------------------------------------------------------
# Separator natywnej nazwy w `etykieta` (np. „Suomi – foneettiset perusteet”).
# Tolerujemy en-dash / em-dash / zwykły myślnik z otaczającymi spacjami.
_RE_SEP_ETYKIETY = re.compile(r"\s+[–—-]\s+")


def _natywna_nazwa(kod: str) -> str:
    """Natywna nazwa języka z `dictionaries/<kod>/podstawy.yaml::etykieta`.

    Bierze prefiks przed separatorem ` – ` (jak `core_poliglota.natywna_nazwa`
    i `refresh_languages.natywna_nazwa`, ale samowystarczalnie). Fallback na sam
    kod ISO. Powód użycia: prompt podaje cel NATYWNIE („Suomi"/„中文") zamiast
    po polsku („fiński") — jedna z kotwic PL zidentyfikowanych w audycie.
    """
    p = DICT_DIR / kod / "podstawy.yaml"
    try:
        with open(p, "r", encoding="utf-8") as fh:
            dane = YAML(typ="safe").load(fh)
    except Exception:  # noqa: BLE001 — fail-soft: brak/zły podstawy.yaml → kod ISO
        return kod
    etyk = (dane or {}).get("etykieta", "") if isinstance(dane, dict) else ""
    if isinstance(etyk, str) and etyk.strip():
        nazwa = _RE_SEP_ETYKIETY.split(etyk.strip(), maxsplit=1)[0].strip()
        if nazwa:
            return nazwa
    return kod


# ---------------------------------------------------------------------------
# Prompt systemowy dla LLM — ANGIELSKI (audyt 2026-06-16)
# ---------------------------------------------------------------------------
# Prompt jest po ANGIELSKU, spójnie z docs/`tlumacz_ai._PROMPT_SYSTEMOWY_TEMPLATE`
# (udokumentowana decyzja: „EN neutralny dla wszystkich par językowych, nie
# wprowadza biasu modelu w stronę języka źródłowego"). Audyt UI-tłumacza wykazał,
# że poprzedni PL-prompt + 150 polskich liści + polska nazwa celu = ~100% polski
# payload → surowy model zakotwiczał się w PL i produkował kalki (RELEASE_NOTES:
# „German/Russian/Spanish/Italian IT-jargon calques"). Stąd EN framing + blok
# reguł naturalności (których PL-prompt w ogóle nie miał) + cel podany natywnie.
# Słowo "JSON" w prompcie nieobowiązkowe na Claude (structured outputs egzekwuje
# schemat `SCHEMA_TLUMACZENIA` na poziomie API), ale zostaje dla czytelności.
def _PROMPT_SYSTEMOWY(nazwa_celu: str, kod: str, *, persona_hint: bool = False) -> str:
    # Warunkowy blok „głos person" wstrzykiwany TYLKO gdy bieżący chunk zawiera
    # liście `bot.*` (komunikaty bohaterek obiegu zgłoszeń). Bez niego model
    # kotwiczy się na „krótkich etykietach UI" i spłaszcza literacki głos person
    # (audyt usera 2026-06-18: Lumi „Stay frosty!"→„Frosty greetings!", Vieno
    # „ritual/manifest"→„materialized", Katla „glowing"→„hot", Sami „zooms off"→
    # „passes on"). Reguła Sami `Ciao!`/`A presto!` (freeze marki) też tu siedzi.
    persona_blok = (
        "## Persona voice (applies ONLY to keys under `bot.*` — in-world messages)\n"
        "Some items are NOT short UI labels but LONG in-world messages from named "
        "characters of the issue-handling flow. Translate them as LITERARY PROSE, "
        "preserving each character's tone, metaphors and flair — a literal or "
        "watered-down rendering is WRONG here:\n"
        "- **Lumi** — icy, snowy, blunt with dry humour. Keep frost/snow/cold imagery "
        "and her crisp sign-offs (e.g. EN \"Stay frosty!\", not \"Frosty greetings!\").\n"
        "- **Vieno** — shamanic, misty, ritual register. Keep the rite/ritual, visions "
        "that \"manifest\" and closing \"circles\" — NOT a technical \"materialized\".\n"
        "- **Katla** — volcanic, scorching. Keep \"glowing\"/\"white-hot\" intensity — "
        "NOT a flat \"hot\".\n"
        "- **Sami** — energetic, fast, smiling Italian dispatcher. She \"zooms/darts "
        "off\" with the report — NOT merely \"passes it on\". Keep the Italian "
        "catchphrases `Ciao!` and `A presto!` VERBATIM in Italian in EVERY language "
        "(her brand — never \"Hi!\"/\"See you soon!\"/\"Stay tuned!\").\n"
        "Render the imagery and energy IDIOMATICALLY in the target language — match the "
        "force of the source, do not neutralize it.\n\n"
    ) if persona_hint else ""

    return (
        "# Role\n"
        "You are a professional UI localizer for a desktop wxPython application. "
        "You translate ONLY the values — JSON keys and structure are immutable.\n\n"
        "## Task\n"
        "You receive a JSON object with an `items` field — a list of "
        "`{\"id\": int, \"source\": str}` objects. The `source` strings are in Polish.\n"
        f"Translate each `source` into the target language: **{nazwa_celu}** "
        f"(ISO 639 code: {kod}).\n"
        "Return JSON of the shape:\n"
        "  `{\"translations\": [{\"id\": int, \"target\": str}, ...]}`\n"
        "Each object MUST carry exactly the same `id` as the input. Skipping ids, "
        "adding new ones, or changing their order is not allowed.\n\n"
        "## Localization quality (CRITICAL — these labels are read by real users)\n"
        "- Translate NATURALLY and IDIOMATICALLY, the way a native-speaking software "
        "product would phrase it — NOT word-for-word.\n"
        "- Do NOT calque Polish word order, grammar or phrasing. Reformulate so the "
        "result reads as if it had been written originally in the target language.\n"
        "- Use the target language's ESTABLISHED software/UI and IT terminology and "
        "conventions (button verbs, menu wording, error-message register, the "
        "screen-reader / accessibility vocabulary native speakers actually use).\n"
        "- Render the FUNCTION of each label, not a literal gloss of the Polish words.\n\n"
        "## Technical rules (CRITICAL — a violation blocks the file from being saved)\n"
        "1. **Markers ⟦P{n}⟧ and ⟦S{n}⟧** are frozen program fragments "
        "(placeholders and keyboard shortcuts). Copy them into `target` VERBATIM — "
        "letter for letter, digit for digit. The count of each marker in `target` "
        "must be identical to `source` (a parent script verifies parity).\n"
        "2. **The `&` character** is a wxPython menu accelerator (Alt+letter). Keep "
        "EXACTLY THE SAME NUMBER of ampersands as in `source` (usually 0 or 1). Move "
        "`&` before a letter that gives a sensible mnemonic in the target language — "
        "prefer the first letter of the main word. Accelerator collisions within a "
        "menu are not your concern (review resolves them).\n"
        "3. **Emoji** (🎬 📄 📚 🌍 ✅ ⚠️ 🚨 ℹ️ ✂️ 🎭 🔄 📝 📋 🧠 🎙️ 🔐 🎛️ 🏁 📜 📖) "
        "— copy 1:1 and keep their position relative to the rest of the text.\n"
        "4. **Technical literals** — do NOT translate: file names (`golden_key.env`, "
        "`.docx`, `.exe`), paths (`dictionaries/`, `runtime/`), AI model names "
        "(`claude-sonnet-4-6`, `Anthropic`, `gpt-4o`, `OpenAI`), product names "
        "(`NVDA`, `Vocalizer`, `Microsoft Word`), "
        "key prefixes (`sk-`), and Ctrl/Alt/Shift inside keyboard shortcuts.\n"
        "5. **Whitespace** — preserve every `\\n`, double space and indentation. Line "
        "breaks in messages are deliberately tuned to the dialog width.\n"
        "6. **Application version** — in a value like `\"13.1 – Wersja Wydawnicza\"` "
        "keep the number (digits + dot) and the dash, but translate the Polish phrase "
        "'Wersja Wydawnicza' into the target-language equivalent "
        "(e.g. 'Release Edition' / 'Julkaisuversio').\n\n"
        + persona_blok +
        "## Response format\n"
        "Return ONLY valid JSON `{\"translations\": [...]}`. No code fences, no "
        "preamble, no summary."
    )


# ---------------------------------------------------------------------------
# Walker po drzewie ruamel — zbiera (dotted_path, str_value)
# ---------------------------------------------------------------------------
def zbierz_liscie(node: Any, prefix: str = "") -> list[tuple[str, str]]:
    """Rekurencyjnie zbiera wszystkie liście stringowe z dotted-path.

    ruamel `CommentedMap` dziedziczy po `dict`, więc `isinstance(_, dict)`
    łapie zarówno czyste dicty, jak i ruamel-owe round-trip mapy.
    Listy są obsługiwane symbolicznie (`[i]` w path), choć w obecnym
    ui.yaml nie występują — zostawiamy zaczepienie na przyszłość.
    """
    out: list[tuple[str, str]] = []
    if isinstance(node, dict):
        for k in list(node.keys()):
            sub = f"{prefix}.{k}" if prefix else str(k)
            out += zbierz_liscie(node[k], sub)
    elif isinstance(node, list):
        for idx, v in enumerate(node):
            out += zbierz_liscie(v, f"{prefix}[{idx}]")
    elif isinstance(node, str):
        out.append((prefix, node))
    # Inne typy (int, bool, None) ignorujemy — nie ma czego tłumaczyć.
    return out


def ustaw_po_sciezce(node: Any, sciezka: str, nowa_wartosc: str) -> None:
    """Nadpisuje liść w drzewie po dotted-path (mutuje `node` w miejscu).

    Wspiera notację `[i]` dla indeksu listy (zobacz `zbierz_liscie`).
    Rzuca `KeyError`/`IndexError` przy niezgodnej strukturze — to celowo
    twardy błąd (oznacza, że LLM zwrócił path niepasujący do wejścia).
    """
    # Rozkład path-a na segmenty: "a.b[0].c" → ["a", "b", "[0]", "c"]
    segmenty = re.findall(r"[^.\[\]]+|\[\d+\]", sciezka)
    if not segmenty:
        raise ValueError(f"Pusta ścieżka: {sciezka!r}")
    for seg in segmenty[:-1]:
        if seg.startswith("[") and seg.endswith("]"):
            node = node[int(seg[1:-1])]
        else:
            # Auto-twórz brakującą gałąź mapowania w trybie UPDATE (--klucz):
            # gdy do obcego pliku dochodzi CAŁKIEM NOWY klucz (np. sekcja
            # `bot:` dodana w PL, której obce ui.yaml jeszcze nie mają),
            # `node[seg]` rzuciłby KeyError. Tworzymy pusty dict, by iniekcja
            # nowych liści zadziałała bez pełnego regenu całego pliku. Indeksy
            # list NIE są auto-tworzone (brak sensownej semantyki rozmiaru).
            if seg not in node:
                node[seg] = {}
            node = node[seg]
    ostatni = segmenty[-1]
    if ostatni.startswith("[") and ostatni.endswith("]"):
        node[int(ostatni[1:-1])] = nowa_wartosc
    else:
        node[ostatni] = nowa_wartosc


# ---------------------------------------------------------------------------
# Tokenizacja per-liść (placeholder + shortcut, niezależne liczniki)
# ---------------------------------------------------------------------------
def tokenizuj_liscia(tekst: str) -> tuple[str, dict[str, str]]:
    """Zamienia `{...}` na `⟦P{i}⟧` i `\\tCtrl+...` na `⟦S{j}⟧`.

    Zwraca (tekst_tok, mapa). Klucze mapy mają prefix `P`/`S` —
    np. `mapa["P0"] = "{nazwa_aplikacji}"`, `mapa["S3"] = "\\tCtrl+1"`.
    """
    mapa: dict[str, str] = {}

    licznik_p = 0
    def _zamien_ph(match: re.Match[str]) -> str:
        nonlocal licznik_p
        klucz = f"P{licznik_p}"
        mapa[klucz] = match.group(0)
        licznik_p += 1
        return TOKEN_PH.format(licznik_p - 1)

    licznik_s = 0
    def _zamien_sc(match: re.Match[str]) -> str:
        nonlocal licznik_s
        klucz = f"S{licznik_s}"
        mapa[klucz] = match.group(0)
        licznik_s += 1
        return TOKEN_SC.format(licznik_s - 1)

    # Skróty NAJPIERW — bo zawierają znaki, które mogłyby zostać
    # niechcący zinterpretowane jako placeholder, gdyby ktoś dał
    # `\tCtrl+{X}` (dziś nie występuje, ale tańsza wersja regexa
    # placeholdera nie szuka po tabulatorze, więc kolizji i tak nie ma).
    tekst_tok = SHORTCUT_REGEX.sub(_zamien_sc, tekst)
    tekst_tok = PLACEHOLDER_REGEX.sub(_zamien_ph, tekst_tok)
    return tekst_tok, mapa


def detokenizuj_liscia(tekst: str, mapa: dict[str, str]) -> str:
    """Zamienia wszystkie `⟦P{i}⟧` i `⟦S{j}⟧` z powrotem na oryginały."""
    def _zamien(match: re.Match[str]) -> str:
        klucz = match.group(1)   # np. "P3" / "S1"
        return mapa.get(klucz, match.group(0))
    return TOKEN_PARITY_REGEX.sub(_zamien, tekst)


def waliduj_liscia(src_tok: str, tgt: str) -> tuple[bool, list[str]]:
    """Sprawdza parity tokenów + count('&'). Zwraca (ok, lista_problemow)."""
    problemy: list[str] = []

    we = Counter(TOKEN_PARITY_REGEX.findall(src_tok))
    wy = Counter(TOKEN_PARITY_REGEX.findall(tgt))
    if we != wy:
        wszystkie = set(we) | set(wy)
        for klucz in sorted(wszystkie):
            if we.get(klucz, 0) != wy.get(klucz, 0):
                problemy.append(
                    f"token ⟦{klucz}⟧ — src: {we.get(klucz, 0)}×, "
                    f"tgt: {wy.get(klucz, 0)}×"
                )

    # Akcelerator wxPython — liczba ampersandów musi być zachowana.
    # Tokenizacja nie zaczepia `&`, więc liczymy bezpośrednio na src/tgt.
    src_oryg = src_tok   # tokenizacja nie modyfikuje `&`
    if src_oryg.count("&") != tgt.count("&"):
        problemy.append(
            f"akcelerator `&` — src: {src_oryg.count('&')}×, "
            f"tgt: {tgt.count('&')}×"
        )

    return (len(problemy) == 0), problemy


# ---------------------------------------------------------------------------
# Inicjalizacja klienta Anthropic (kopia 1:1 z buduj_wielojezyczne_docs.py)
# ---------------------------------------------------------------------------
def _zainicjuj_klienta_anthropic() -> Any:
    try:
        import anthropic
    except ImportError as exc:
        raise SystemExit(
            "❌ Missing `anthropic` module. Install (project venv):\n"
            "   .venv/Scripts/pip install anthropic"
        ) from exc

    try:
        from dotenv import load_dotenv
        env_path = ROOT / "golden_key.env"
        if env_path.is_file():
            load_dotenv(env_path)
    except ImportError:
        pass

    klucz = os.environ.get("ANTHROPIC_API_KEY")
    if not klucz or not klucz.startswith("sk-ant-"):
        raise SystemExit(
            "❌ Missing or invalid ANTHROPIC_API_KEY.\n"
            "   Check `golden_key.env` in the project directory (the same file\n"
            "   used by the GUI — System Check in Director mode)."
        )
    return anthropic.Anthropic(api_key=klucz)


# ---------------------------------------------------------------------------
# Wywołanie LLM (chunk, Anthropic structured outputs — output_config json_schema)
# ---------------------------------------------------------------------------
def wywolaj_llm(
    klient: Any,
    model: str,
    nazwa_celu: str,
    kod: str,
    liscie_tok: list[tuple[int, str]],
    *,
    persona_hint: bool = False,
) -> dict[int, str]:
    """Wysyła JEDEN chunk, zwraca mapę id → tgt.

    Structured outputs (`output_config.format` ze :data:`SCHEMA_TLUMACZENIA`)
    gwarantują kształt `{"translations": [{"id", "target"}]}` na poziomie API —
    mocniej niż OpenAI `json_object`. Walidacje semantyczne (parity markerów, `&`)
    robimy dalej, po naszej stronie.

    Rzuca `RuntimeError` przy nieparowalnej odpowiedzi lub strukturze, której nie
    umiemy zinterpretować — wyżej (w `tlumacz_jezyk`) złapane jako MIĘKKI błąd
    danego języka, reszta języków leci dalej. NATOMIAST ucięcie limitem wyjścia
    (`stop_reason == "max_tokens"`) rzuca `SystemExit` — przerywa CAŁY batch (nie
    łapie go `except RuntimeError`/`except Exception`), bo to sygnał konfiguracyjny
    „zmniejsz BATCH_SIZE", nie wpadka pojedynczego języka.
    """
    # Klucze payloadu po ANGIELSKU (audyt 2026-06-16) — kolejna kotwica PL
    # usunięta. Surowy model widzi teraz EN prompt + EN klucze; jedynym polskim
    # elementem są same stringi `source` (czyli to, co MA tłumaczyć).
    payload = {
        "target_language": nazwa_celu,
        "items": [{"id": i, "source": s} for i, s in liscie_tok],
    }

    resp = klient.messages.create(
        model=model,
        max_tokens=MAX_TOKENS_OUT,
        temperature=0.0,
        thinking={"type": "disabled"},
        system=_PROMPT_SYSTEMOWY(nazwa_celu, kod, persona_hint=persona_hint),
        messages=[{
            "role": "user",
            "content": (
                "Here is the JSON with items to translate. Return JSON with a "
                "`translations` field.\n\n"
                + json.dumps(payload, ensure_ascii=False, indent=2)
            ),
        }],
        output_config={
            "format": {"type": "json_schema", "schema": SCHEMA_TLUMACZENIA},
        },
    )

    # Ucięcie limitem wyjścia → JSON niekompletny. PRZERYWAMY CAŁY batch przez
    # SystemExit (NIE RuntimeError): `except RuntimeError` w pętli per-chunk/jezyk
    # by to schował, a to jest sygnał dla całego przebiegu (zmniejsz BATCH_SIZE).
    if getattr(resp, "stop_reason", None) == "max_tokens":
        raise SystemExit(
            f"❌ {kod}: model hit the max_tokens={MAX_TOKENS_OUT} limit — response "
            f"truncated, JSON incomplete. Reduce BATCH_SIZE (currently {BATCH_SIZE}) "
            f"and run again. Aborted the ENTIRE batch."
        )

    surowa = "".join(
        b.text for b in resp.content if getattr(b, "type", None) == "text"
    )
    try:
        dane = json.loads(surowa)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Odpowiedź LLM nie jest poprawnym JSON: {exc}\n"
            f"Pierwsze 200 znaków: {surowa[:200]!r}"
        ) from exc

    # Tolerancja drobnych wariacji nazwy korzenia: `translations` (nowy, EN),
    # `tlumaczenia` (wstecz, sprzed audytu 2026-06-16), lub bezpośrednio
    # lista/słownik na top-levelu.
    arr: Any
    if isinstance(dane, dict):
        arr = (
            dane.get("translations")
            or dane.get("tlumaczenia")
            or dane.get("results")
            or dane
        )
    else:
        arr = dane

    mapa_tgt: dict[int, str] = {}
    if isinstance(arr, list):
        for item in arr:
            if not isinstance(item, dict):
                continue
            if "id" not in item:
                continue
            # `target` (nowy, EN) z tolerancją `tgt` (wstecz).
            wartosc = item.get("target", item.get("tgt"))
            if wartosc is None:
                continue
            try:
                mapa_tgt[int(item["id"])] = str(wartosc)
            except (TypeError, ValueError):
                continue
    elif isinstance(arr, dict):
        # Wariant degradacyjny: `{"0": "...", "1": "..."}`
        for k, v in arr.items():
            if not isinstance(v, str):
                continue
            try:
                mapa_tgt[int(k)] = v
            except (TypeError, ValueError):
                continue

    if not mapa_tgt:
        raise RuntimeError(
            f"Nie udało się sparsować żadnego id→tgt z odpowiedzi.\n"
            f"Pierwsze 400 znaków surowej: {surowa[:400]!r}"
        )

    return mapa_tgt


# ---------------------------------------------------------------------------
# Podmiana topowego comment-block na auto-nagłówek
# ---------------------------------------------------------------------------
def _auto_naglowek(kod_jezyka: str, *, tryb_draft: bool = False) -> str:
    """Buduje top-of-file komentarz dla wynikowego ui.yaml danego języka.

    ``tryb_draft=True`` → neutralny nagłówek zachęcający do edycji (paczka
    do przeglądu halucynacji); inaczej kanoniczny „NIE edytuj ręcznie".
    """
    sciezka_rel = f"dictionaries/{kod_jezyka}/gui/ui.yaml"
    zrodlo_rel = f"dictionaries/{KOD_ZRODLOWY}/gui/ui.yaml"
    if tryb_draft:
        return przeglad_tlumaczen.naglowek_roboczy(
            sciezka_rel, zrodlo_rel, "buduj_wielojezyczne_ui.py",
        )
    return (
        "# =============================================================================\n"
        f"# {sciezka_rel}\n"
        "#\n"
        "# Plik wygenerowany automatycznie przez buduj_wielojezyczne_ui.py\n"
        f"# ze źródła {zrodlo_rel}\n"
        "# (język bazowy PL, wersja 13.x). NIE edytuj ręcznie — zmiany\n"
        "# wprowadzaj w pliku źródłowym PL i uruchom ponownie skrypt.\n"
        "#\n"
        "# Tłumaczone są WYŁĄCZNIE wartości; klucze, struktura, komentarze\n"
        "# sekcyjne i style block-scalar (`|-`, `|`) są zachowane przez\n"
        "# round-trip ruamel.yaml. Placeholdery {nazwa} i skróty \\tCtrl+...\n"
        "# zostały zamrożone tokenami ⟦P{i}⟧/⟦S{j}⟧ na czas tłumaczenia,\n"
        "# odtworzone 1:1 po weryfikacji parzystości multisetu markerów.\n"
        "# =============================================================================\n"
        "\n"
    )


def podmien_top_comment(yaml_str: str, kod_jezyka: str, *, tryb_draft: bool = False) -> str:
    """Usuwa nagłówkowy blok komentarzy i wstawia auto-nagłówek.

    Top-of-file w PL ui.yaml ma strukturę:
      [komentarze nagłówkowe / konwencje]
      <pusta linia>
      [komentarz sekcyjny # APP – ...]
      app: ...

    Pierwsza pusta linia jest separatorem nagłówka — STOP tam, żeby
    zachować sekcyjny komentarz `# APP – ...` (i jego separator).
    Bez tego stop-warunku zjadalibyśmy też pierwszy sekcyjny komentarz,
    a kolejne 7 (zaczepione do węzłów podrzędnych przez ruamel) zostają.
    """
    linie = yaml_str.split("\n")
    i = 0
    while i < len(linie) and linie[i].lstrip().startswith("#"):
        i += 1
    # Pomiń ewentualną pojedynczą pustą linię — separator nagłówka.
    # Auto-nagłówek ma już własną pustą linię na końcu, więc nie
    # gubimy formatowania.
    if i < len(linie) and linie[i].strip() == "":
        i += 1
    reszta = "\n".join(linie[i:])
    return _auto_naglowek(kod_jezyka, tryb_draft=tryb_draft) + reszta


def finalizuj_naglowek_ui(cel: Path, kod: str) -> str:
    """Podmienia nagłówek DRAFT ui.yaml na kanoniczny BEZ retłumaczenia.

    Zwraca status: ``"ok"`` (podmieniono), ``"brak"`` (plik nie istnieje),
    ``"nie-draft"`` (brak markera draftu — plik już kanoniczny; idempotentny
    no-op). Treść (z ręcznymi poprawkami recenzenta) NIE jest tknięta — reużywa
    `podmien_top_comment` (strip wiodących `#` + 1 pusta → kanoniczny nagłówek),
    który zachowuje sekcyjny komentarz `# APP – ...` i resztę pliku 1:1.
    """
    if not cel.is_file():
        return "brak"
    with open(cel, "r", encoding="utf-8") as fh:
        tresc = fh.read()
    # Marker sprawdzamy WYŁĄCZNIE w wiodącym bloku komentarza (nie w całym pliku),
    # żeby przypadkowe wystąpienie frazy w treści nie udawało draftu.
    naglowek_linie: list[str] = []
    for linia in tresc.split("\n"):
        if linia.lstrip().startswith("#"):
            naglowek_linie.append(linia)
        else:
            break
    if przeglad_tlumaczen.MARKER_DRAFTU not in "\n".join(naglowek_linie):
        return "nie-draft"
    nowy = podmien_top_comment(tresc, kod, tryb_draft=False)
    with open(cel, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(nowy)
    return "ok"


# ---------------------------------------------------------------------------
# Pipeline dla jednego języka
# ---------------------------------------------------------------------------
def tlumacz_jezyk(
    kod: str,
    nazwa_pl: str,
    klient: Any,
    drzewo_pl: Any,
    liscie_pl: list[tuple[str, str]],
    yaml_io: YAML,
    *,
    skip_existing: bool,
    dry_run: bool,
    model: str,
    klucze: list[str] | None = None,
    tryb_draft: bool = False,
) -> bool:
    """Pełen pipeline dla jednego języka. Zwraca True przy sukcesie.

    Tryb FULL (`klucze=None`): tłumaczy wszystkie liście, klonuje drzewo PL
    do iniekcji, nadpisuje cały plik `<kod>/gui/ui.yaml`.

    Tryb UPDATE (`klucze=[...]`): tłumaczy TYLKO podane klucze (lub całe
    poddrzewa, gdy klucz wskazuje na gałąź), wczytuje już istniejący
    `<kod>/gui/ui.yaml` jako bazę iniekcji, nadpisuje wybrane liście —
    pozostałe są zachowane bit w bit. Wymaga, żeby plik docelowy istniał
    (najpierw FULL, potem UPDATE). Kilka kluczy = jeden request per chunk.
    """
    cel = DICT_DIR / kod / FOLDER_GUI / NAZWA_UI
    if klucze is None and cel.exists() and skip_existing:
        print(f"⏭️  {kod}: {cel.relative_to(ROOT)} już istnieje — pomijam (--skip-existing).")
        return True
    if klucze is not None and not cel.exists():
        print(f"❌ {kod}: missing {cel.relative_to(ROOT)} — run first without --klucz.")
        return False

    # --- Krok 1: tokenizacja per-liść -----------------------------------------
    liscie_tok: list[tuple[int, str]] = []
    mapy_per_id: dict[int, dict[str, str]] = {}
    statystyki_p = 0
    statystyki_s = 0
    for idx, (path, wartosc) in enumerate(liscie_pl):
        wartosc_tok, mapa = tokenizuj_liscia(wartosc)
        liscie_tok.append((idx, wartosc_tok))
        mapy_per_id[idx] = mapa
        statystyki_p += sum(1 for k in mapa if k.startswith("P"))
        statystyki_s += sum(1 for k in mapa if k.startswith("S"))

    print(
        f"ℹ️  {kod}: {len(liscie_pl)} liści, "
        f"zamrożono {statystyki_p} placeholderów + {statystyki_s} skrótów."
    )

    if dry_run:
        # Podgląd kilku pierwszych mapowań (sanity check tokenizacji)
        print(f"    Podgląd 5 pierwszych liści:")
        for idx, src_tok in liscie_tok[:5]:
            path, oryg = liscie_pl[idx]
            mapa = mapy_per_id[idx]
            print(f"      [{idx}] {path}")
            print(f"          oryg: {oryg[:80]!r}")
            print(f"          tok:  {src_tok[:80]!r}")
            if mapa:
                print(f"          mapa: {mapa}")
        # Sanity: zlicz `&` w całym pliku — pomocna metryka
        n_amp = sum(s.count("&") for _, s in liscie_pl)
        print(f"    Łączna liczba akceleratorów `&`: {n_amp}")
        print(f"    (dry-run) Nie wywołuję API.")
        return True

    # --- Krok 2: wywołania LLM (chunked po BATCH_SIZE liści) ------------------
    # Chunking gwarantuje, że żadna pojedyncza odpowiedź nie przekroczy
    # MAX_TOKENS_OUT (16 000, pod progiem non-streaming Anthropic). Wyniki łączymy w jedną mapę id→tgt
    # — id-y są unikalne globalnie, bo pochodzą z `enumerate(liscie_pl)`.
    total = len(liscie_tok)
    n_chunkow = (total + BATCH_SIZE - 1) // BATCH_SIZE
    mapa_tgt: dict[int, str] = {}
    # Cel podawany modelowi NATYWNIE (audyt 2026-06-16) — „Suomi"/„中文" zamiast
    # polskiego „fiński"; `nazwa_pl` zostaje tylko do logu konsoli dewelopera.
    nazwa_cel = _natywna_nazwa(kod)
    print(f"🌍 {kod}: {model} (cel: {nazwa_cel}), {n_chunkow} chunków po max {BATCH_SIZE} liści...")
    for nr, start in enumerate(range(0, total, BATCH_SIZE), start=1):
        chunk = liscie_tok[start:start + BATCH_SIZE]
        # Warunkowa uwaga „głos person" — tylko gdy chunk zawiera liście `bot.*`.
        persona_hint = any(liscie_pl[idx][0].startswith("bot.") for idx, _ in chunk)
        print(f"   {kod}: chunk {nr}/{n_chunkow} (id {chunk[0][0]}..{chunk[-1][0]}, "
              f"{len(chunk)} liści{', +persona' if persona_hint else ''})...")
        try:
            mapa_tgt.update(wywolaj_llm(klient, model, nazwa_cel, kod, chunk,
                                        persona_hint=persona_hint))
        except RuntimeError as exc:
            print(f"❌ {kod}: LLM error in chunk {nr}/{n_chunkow} — {exc}")
            return False

    # --- Krok 3: walidacja kompletności + parity per-liść ---------------------
    oczekiwane = set(idx for idx, _ in liscie_tok)
    otrzymane = set(mapa_tgt.keys())
    brakujace = oczekiwane - otrzymane
    nadmiarowe = otrzymane - oczekiwane
    if brakujace or nadmiarowe:
        print(f"❌ {kod}: mismatched set of ids in the response.")
        if brakujace:
            print(f"     missing: {sorted(brakujace)[:20]} (total {len(brakujace)})")
        if nadmiarowe:
            print(f"     extra: {sorted(nadmiarowe)[:20]} (total {len(nadmiarowe)})")
        return False

    porazki: list[tuple[int, list[str]]] = []
    src_po_idx = {idx: src for idx, src in liscie_tok}
    for idx, src_tok in liscie_tok:
        tgt = mapa_tgt[idx]
        ok, problemy = waliduj_liscia(src_tok, tgt)
        if not ok:
            porazki.append((idx, problemy))

    # --- Krok 3.5: jednorazowy RETRY dla problematycznych liści ---------------
    # LLM bywa kreatywny w pojedynczych przypadkach (np. zgubi `&`, zmieni
    # token). Drugie podejście z czystym kontekstem (tylko same problematyczne
    # liście, mniejszy batch) zwykle to naprawia. Bez tego sieć by traciła
    # pełen plik z powodu jednej wpadki na 450 stringach.
    if porazki:
        print(f"⚠️  {kod}: {len(porazki)} leaves need a retry...")
        do_retry = [(idx, src_po_idx[idx]) for idx, _ in porazki]
        persona_hint_retry = any(liscie_pl[idx][0].startswith("bot.") for idx, _ in do_retry)
        try:
            retry_tgt = wywolaj_llm(klient, model, nazwa_cel, kod, do_retry,
                                    persona_hint=persona_hint_retry)
        except RuntimeError as exc:
            print(f"❌ {kod}: retry failed — {exc}")
            return False
        mapa_tgt.update(retry_tgt)

        porazki_v2: list[tuple[int, list[str]]] = []
        for idx, _ in porazki:
            tgt = mapa_tgt.get(idx, "")
            ok, problemy = waliduj_liscia(src_po_idx[idx], tgt)
            if not ok:
                porazki_v2.append((idx, problemy))

        if porazki_v2:
            print(f"❌ {kod}: after retry {len(porazki_v2)} leaves are still invalid. NOT saving.")
            for idx, problemy in porazki_v2[:10]:
                path, _ = liscie_pl[idx]
                print(f"     [{idx}] {path}")
                for diag in problemy:
                    print(f"       • {diag}")
            if len(porazki_v2) > 10:
                print(f"     ... (+{len(porazki_v2) - 10} more)")
            return False
        print(f"✅ {kod}: retry fixed all {len(porazki)} problematic leaves.")

    # --- Krok 4: detokenizacja + iniekcja w drzewo ruamel ---------------------
    # Tryb FULL: klonujemy drzewo PL przez round-trip dump+load — bazą
    #            jest pełna struktura PL ze wszystkimi komentarzami.
    # Tryb UPDATE: wczytujemy istniejące <kod>/gui/ui.yaml — tłumaczenia
    #              pozostałych liści są zachowane, podmieniamy tylko wybrane.
    if klucze is not None:
        with open(cel, "r", encoding="utf-8") as fh:
            drzewo_kopia = yaml_io.load(fh)
    else:
        buf_clone = io.StringIO()
        yaml_io.dump(drzewo_pl, buf_clone)
        drzewo_kopia = yaml_io.load(buf_clone.getvalue())

    for idx, src_tok in liscie_tok:
        path, _ = liscie_pl[idx]
        tgt_raw = mapa_tgt[idx]
        tgt = detokenizuj_liscia(tgt_raw, mapy_per_id[idx])
        ustaw_po_sciezce(drzewo_kopia, path, tgt)

    # --- Krok 5: dump + podmiana topowego komentarza + zapis ------------------
    buf = io.StringIO()
    yaml_io.dump(drzewo_kopia, buf)
    yaml_str = buf.getvalue()
    yaml_str = podmien_top_comment(yaml_str, kod, tryb_draft=tryb_draft)

    cel.parent.mkdir(parents=True, exist_ok=True)
    with open(cel, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(yaml_str)

    znacznik_draft = " DRAFT" if tryb_draft else ""
    print(
        f"✅ {kod}: zapisano {cel.relative_to(ROOT)}{znacznik_draft} "
        f"({len(liscie_pl)} liści OK, {len(yaml_str):,} znaków)."
    )
    return True


# ---------------------------------------------------------------------------
# CLI (symetryczne do buduj_wielojezyczne_docs.py)
# ---------------------------------------------------------------------------
def _parsuj_argumenty() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Batch auto-translator of the ui.yaml interface into target languages "
            f"({', '.join(MAPA_JEZYKOW)}). Preserves section comments "
            "(ruamel.yaml round-trip), tokenizes placeholders and keyboard "
            "shortcuts, and verifies marker parity + the `&` accelerator."
        ),
    )
    grupa = parser.add_mutually_exclusive_group(required=True)
    grupa.add_argument(
        "--jezyki",
        type=str,
        default="",
        help=f"Comma-separated list of ISO codes (e.g. `en,fi`). "
             f"Allowed: {', '.join(MAPA_JEZYKOW)}.",
    )
    grupa.add_argument(
        "--wszystkie",
        action="store_true",
        help=f"Translate into all languages ({', '.join(MAPA_JEZYKOW)}).",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip languages for which `dictionaries/<kod>/gui/ui.yaml` "
             "already exists (idempotent rerun).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Walk + tokenization + preview only. Zero API calls.",
    )
    parser.add_argument(
        "--model",
        default="claude-sonnet-4-6",
        help="Anthropic Claude model used for translation (default: claude-sonnet-4-6).",
    )
    parser.add_argument(
        "--draft",
        action="store_true",
        help="WORKING DRAFT FOR REVIEW mode. Instead of the canonical \"do not edit "
             "manually\" header, injects a neutral header encouraging edits and, after "
             "the run, emits a review checklist to `skrypty/przeglad_ui.md`. "
             "Use case: a new-language contribution package sent to a third party / "
             "agent for review. Files land in the normal path — after approval "
             "and manual corrections, run `--finalizuj` (swaps the header to the "
             "canonical one WITHOUT retranslating). Do NOT regenerate without --draft — a full "
             "translation would overwrite the file and revert the corrections.",
    )
    parser.add_argument(
        "--finalizuj",
        action="store_true",
        help="FINALIZE a draft (zero API, zero retranslation). For the selected "
             "languages, swaps the working \"WORKING DRAFT\" header in "
             "`<kod>/gui/ui.yaml` for the canonical \"do not edit manually\" one, PRESERVING "
             "all content (including the reviewer's manual corrections). Files without a "
             "draft marker are skipped (idempotent). This is the proper step after a "
             "review is approved — instead of the destructive \"regenerate without --draft\".",
    )
    parser.add_argument(
        "--klucz",
        type=str,
        default=None,
        metavar="KLUCZ[,KLUCZ...]",
        help="Translate ONLY the given keys (dotted-path), leaving the rest of the file unchanged. "
             "You can pass multiple comma-separated keys: "
             "`manager.kreator_jezyk_bazowy_etykieta_hint,manager.kreator_blad_nazwa_jezyka`. "
             "A key matches a leaf exactly OR an entire subtree (prefix + '.children'). "
             "Requires that `<kod>/gui/ui.yaml` already exists — full translation first, "
             "then a surgical update of the selected keys.",
    )
    args = parser.parse_args()
    if args.klucz and args.skip_existing:
        parser.error("--klucz and --skip-existing are mutually exclusive "
                     "(--klucz deliberately overwrites selected leaves in an existing file).")
    if args.finalizuj and (args.draft or args.klucz or args.skip_existing or args.dry_run):
        parser.error("--finalizuj is a purely local header swap (zero API) — "
                     "do not combine it with --draft/--klucz/--skip-existing/--dry-run. "
                     "Select languages via --jezyki/--wszystkie.")
    return args


def _wybierz_jezyki(args: argparse.Namespace) -> list[str]:
    if args.wszystkie:
        return list(MAPA_JEZYKOW.keys())
    kody = [k.strip() for k in args.jezyki.split(",") if k.strip()]
    nieznane = [k for k in kody if k not in MAPA_JEZYKOW]
    if nieznane:
        raise SystemExit(
            f"❌ Unknown language codes: {', '.join(nieznane)}.\n"
            f"   Allowed: {', '.join(MAPA_JEZYKOW)}."
        )
    return kody


def main() -> int:
    args = _parsuj_argumenty()
    kody = _wybierz_jezyki(args)

    # --finalizuj: czysto lokalna podmiana nagłówka DRAFT → kanoniczny. Zero API,
    # zero retłumaczenia, zero potrzeby wczytywania źródła PL — załatwiamy i wracamy.
    if args.finalizuj:
        zmienione = 0
        nie_drafty = 0
        braki = 0
        for kod in kody:
            cel = DICT_DIR / kod / FOLDER_GUI / NAZWA_UI
            status = finalizuj_naglowek_ui(cel, kod)
            if status == "ok":
                zmienione += 1
                print(f"✅ {kod}/{NAZWA_UI}: nagłówek DRAFT → kanoniczny (treść nietknięta).")
            elif status == "nie-draft":
                nie_drafty += 1
                print(f"⏭️  {kod}/{NAZWA_UI}: brak markera draftu — pomijam (już kanoniczny).")
            else:
                braki += 1
                print(f"⚠️  {kod}/{NAZWA_UI}: plik nie istnieje — pomijam.")
        print("\n========== SUMMARY (--finalizuj) ==========")
        print(f"✅ Finalized: {zmienione} | ⏭️ already canonical: {nie_drafty} | ⚠️ file missing: {braki}")
        return 0

    # Wczytanie źródła PL przez ruamel round-trip (komentarze zachowane).
    # `width=10**9` zapobiega zawijaniu długich linii (welcome_text itp.).
    yaml_io = YAML(typ="rt")
    yaml_io.preserve_quotes = True
    yaml_io.width = 10 ** 9
    yaml_io.indent(mapping=2, sequence=4, offset=2)

    sciezka_pl = DICT_DIR / KOD_ZRODLOWY / FOLDER_GUI / NAZWA_UI
    if not sciezka_pl.is_file():
        print(f"❌ Missing PL source file: {sciezka_pl}")
        return 2
    with open(sciezka_pl, "r", encoding="utf-8") as fh:
        drzewo_pl = yaml_io.load(fh)

    liscie_pl = zbierz_liscie(drzewo_pl)
    if not liscie_pl:
        print(f"❌ File {sciezka_pl} contains no string leaves.")
        return 2
    print(f"📄 Wczytano {sciezka_pl.relative_to(ROOT)}: {len(liscie_pl)} liści.")

    # Filtr `--klucz`: zostaw tylko liście, których dotted-path dokładnie
    # pasuje do jednego z podanych kluczy LUB zaczyna się od niego + "."
    # (poddrzewo). Kilka kluczy oddzielonych przecinkiem → unia zbiorów.
    klucze_filtru: list[str] | None = None
    if args.klucz:
        klucze_filtru = [k.strip() for k in args.klucz.split(",") if k.strip()]
        przed = len(liscie_pl)
        liscie_pl = [
            (p, v) for p, v in liscie_pl
            if any(p == k or p.startswith(k + ".") for k in klucze_filtru)
        ]
        if not liscie_pl:
            print(
                f"❌ No leaves for keys {klucze_filtru} in {sciezka_pl.relative_to(ROOT)}.\n"
                f"   Check the dotted-path (e.g. `manager.kreator_jezyk_bazowy_etykieta_hint`)."
            )
            return 2
        print(
            f"🔎 Filtr --klucz ({len(klucze_filtru)} kluczy): "
            f"{len(liscie_pl)}/{przed} liści. "
            f"Istniejące pliki ui.yaml zostaną zaktualizowane w miejscu."
        )

    klient: Any = None if args.dry_run else _zainicjuj_klienta_anthropic()

    sukcesy: list[str] = []
    porazki: list[str] = []
    wytworzone_drafty: list[tuple[str, str]] = []
    for kod in kody:
        nazwa_pl = MAPA_JEZYKOW[kod]
        print(f"\n========== {kod.upper()} ({nazwa_pl}) ==========")
        ok = tlumacz_jezyk(
            kod,
            nazwa_pl,
            klient,
            drzewo_pl,
            liscie_pl,
            yaml_io,
            skip_existing=args.skip_existing,
            dry_run=args.dry_run,
            model=args.model,
            klucze=klucze_filtru,
            tryb_draft=args.draft,
        )
        (sukcesy if ok else porazki).append(kod)
        if ok and args.draft and not args.dry_run:
            wytworzone_drafty.append((kod, NAZWA_UI))

    if args.draft and not args.dry_run:
        sciezka_prompt = przeglad_tlumaczen.zapisz_prompt_przegladu(
            "buduj_wielojezyczne_ui.py", wytworzone_drafty, ROOT,
        )
        if sciezka_prompt is not None:
            print(f"\n📋 DRAFT: checklista przeglądu zapisana → "
                  f"{sciezka_prompt.relative_to(ROOT)} "
                  f"({len(wytworzone_drafty)} plik(ów) do recenzji).")

    print("\n========== SUMMARY ==========")
    print(f"✅ Succeeded: {len(sukcesy)}/{len(kody)}  ({', '.join(sukcesy) or '—'})")
    if porazki:
        print(f"❌ Failed: {', '.join(porazki)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
