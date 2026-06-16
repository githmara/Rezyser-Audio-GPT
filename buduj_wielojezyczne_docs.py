#!/usr/bin/env python
"""
buduj_wielojezyczne_docs.py — Batchowy autotłumacz dokumentacji (i18n, Etap 5/5).

Czyta WSZYSTKIE szablony z `dictionaries/pl/gui/dokumentacja/*.yaml`
(13.4: ``manual.yaml``, ``dictionaries.yaml``, każdy kolejny YAML wrzucony
do tego folderu w przyszłości), przepuszcza pole `tresc` przez silnik
OpenAI (`tlumacz_ai.py`) z zamrożeniem placeholderów `{klucz.zagniezdzony}`
(np. `{app.wersja}`, `{rezyser.btn_prolog_label}`) i zapisuje wynik jako
`dictionaries/<kod>/gui/dokumentacja/<plik>.yaml` dla każdego języka
docelowego — z zachowaniem oryginalnej nazwy pliku PL.

Architektura (decyzja 13.1 — Etap 5):

  1. Parsujemy źródło `yaml.safe_load`-em i wyciągamy pole `tresc`.
     Nagłówkowe komentarze `#` w pliku PL (notatki autora, ~60 linii)
     są IGNOROWANE — to nie jest treść dla użytkownika końcowego.

  2. TOKENIZACJA: każdy `{klucz}` → unikalny token Unicode `⟦i⟧`.
     Tokeny są neutralne — LLM nie rozpoznaje ich jako „etykieta do
     przetłumaczenia", w przeciwieństwie do `{english_looking_key}`.
     Mapa `i → oryginał` przechowywana w pamięci na czas tłumaczenia.

  3. PREFIX-INSTRUKCJA dla tłumacza (pas+szelki): kilka linii w nawiasach
     kwadratowych przed treścią — przypomina modelowi, żeby markery
     `⟦i⟧` kopiował 1:1. `_prompt_systemowy` w `tlumacz_ai.py` NIE jest
     modyfikowany (reguła projektowa 13.1 Etap 5).

  4. Tłumaczenie przez `tlumacz_dlugi_tekst` — reużywamy chunking, cache
     wznawiania (`runtime/temp_*.jsonl`), callbacki postępu. Z modułu
     nie dostajemy nic więcej niż reszta aplikacji (GUI Poligloty).

  5. WALIDACJA PARZYSTOŚCI tokenów — multiset `⟦i⟧` przed i po musi być
     identyczny. Mismatch = błąd krytyczny, plik NIE jest zapisywany,
     wypisujemy diagnostykę i przechodzimy do kolejnego języka.

  6. DETOKENIZACJA: każdy `⟦i⟧` → oryginalny `{klucz}` z mapy.
     Wynik to bezpieczny Polak-LLM-Polak round-trip: placeholdery
     wracają bit w bit, niezależnie od kreatywności modelu.

  7. Zapis `dictionaries/<kod>/gui/dokumentacja/manual.yaml` — nagłówek
     komentarza informujący, że plik jest wygenerowany automatycznie
     (nie edytować ręcznie), plus `id: manual` + `tresc: |` z 2-spacyjnym
     wcięciem block-scalar. Encoding UTF-8 + LF (tak jak `generuj_dokumentacje.py`).

Użycie:
  python buduj_wielojezyczne_docs.py --wszystkie                 # en, fi, ru, is, it
  python buduj_wielojezyczne_docs.py --jezyki en                 # tylko angielski
  python buduj_wielojezyczne_docs.py --jezyki en,fi --skip-existing
  python buduj_wielojezyczne_docs.py --jezyki en --dry-run       # sama tokenizacja, zero API
  python buduj_wielojezyczne_docs.py --wszystkie --szablony dictionaries
                                                                # tylko jeden szablon
                                                                # (np. gdy manual.yaml jest
                                                                #  już przetłumaczony i nie
                                                                #  chcesz spalać API-billa
                                                                #  na rerun)

Wymaga: `OPENAI_API_KEY` w środowisku (to samo konto co GUI Poliglota).
Moduł NIE zależy od wxPython — uruchamialny w CLI / CI bez inicjalizacji GUI.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

import przeglad_tlumaczen
from tlumacz_ai import tlumacz_dlugi_tekst


# ---------------------------------------------------------------------------
# STDOUT UTF-8 (spójnie z `generuj_dokumentacje.py` — cmd.exe vs cp1250)
# ---------------------------------------------------------------------------
if sys.platform == "win32":
    for strumien in (sys.stdout, sys.stderr):
        try:
            strumien.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass


# ---------------------------------------------------------------------------
# Stałe ścieżek (wszystko względem pliku skryptu — tak samo jak generuj_docs)
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
DICT_DIR = ROOT / "dictionaries"
RUNTIME_DIR = ROOT / "runtime"

# v17.0: META-komentarze + pętla feedbacku (--input). Logi w skrypty/ (user data).
SKRYPTY_DIR = ROOT / "skrypty"
OUTPUT_LOG = SKRYPTY_DIR / "output.log"
INPUT_LOG = SKRYPTY_DIR / "input.log"
# Separator META w odpowiedzi LLM (treść po nim = komentarz, nie tłumaczenie).
META_MARKER = "===META==="

FOLDER_GUI = "gui"
FOLDER_DOKUMENTACJA = "dokumentacja"
KOD_ZRODLOWY = "pl"

# 13.4: skrypt obsługuje WSZYSTKIE szablony z ``dictionaries/pl/gui/dokumentacja/``
# (manual.yaml + dictionaries.yaml + przyszłe). Wcześniej wpis ``NAZWA_MANUAL``
# zamykał generację na jednym pliku; teraz iterujemy po katalogu — dorzucenie
# nowego YAML-a do paczki PL zaowocuje automatycznym tłumaczeniem we wszystkich
# językach docelowych przy najbliższym ``--wszystkie`` (bez zmian w kodzie).

# Regex placeholdera — 1:1 jak w `generuj_dokumentacje.py`, żeby siatka
# {klucz.zagniezdzony} była definiowana w jednym kanonicznym miejscu
# semantycznym (jak go poszerzymy tam, poszerzamy i tu).
PLACEHOLDER_REGEX = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_.]*)\}")

# Tokeny zamrożone. Unicode brackety ⟦ ⟧ (U+27E6, U+27E7) — nie kolidują
# z treścią (nie występują w manualu ani w żadnym naturalnym języku),
# LLM traktuje je jako znaczniki techniczne, nie jako placeholder do
# przetłumaczenia. Indeks monotoniczny od 0.
TOKEN_FORMAT = "⟦{}⟧"
TOKEN_REGEX = re.compile(r"⟦(\d+)⟧")


# ---------------------------------------------------------------------------
# Mapa języków docelowych — ładowana z `jezyki_docelowe.yaml` (od 2026-06-16)
# ---------------------------------------------------------------------------
# Rejestr ISO→nazwa NIE jest już hard-kodem Pythona. Mieszka w `jezyki_docelowe.yaml`
# (root repo), utrzymywanym przez dev tool `refresh_languages.py`. Dzięki temu
# kontrybutor dodaje nowy język BEZ dotykania Pythona (zasada „dodanie języka
# nie wymaga Pythona") — wrzuca `dictionaries/<kod>/`, odpala refresh, gotowe.
#
# Nazwa = `jezyk_docelowy` podawany modelowi ("Translate ... into **{jezyk_docelowy}**").
# Bazowy prompt jest po angielsku, więc nazwa polska („fiński") i natywna („Suomi")
# działają identycznie. `_FALLBACK_JEZYKOW` = ostatnia deska ratunku, gdy pliku
# rejestru brak (np. świeży checkout przed pierwszym refresh) — 8 języków z v17.x.
_REJESTR_JEZYKOW = ROOT / "jezyki_docelowe.yaml"
_FALLBACK_JEZYKOW: dict[str, str] = {
    "en": "angielski", "fi": "fiński", "ru": "rosyjski", "is": "islandzki",
    "it": "włoski", "de": "niemiecki", "fr": "francuski", "es": "hiszpański",
}


def _wczytaj_mape_jezykow() -> dict[str, str]:
    """Wczytuje rejestr ISO→nazwa z `jezyki_docelowe.yaml` (fallback: wbudowane 8).

    Filtruje wpisy nie-stringowe i język źródłowy `pl` (gdyby ktoś go dopisał) —
    `pl` jest źródłem, nie celem tłumaczenia.
    """
    if not _REJESTR_JEZYKOW.is_file():
        return dict(_FALLBACK_JEZYKOW)
    try:
        with open(_REJESTR_JEZYKOW, "r", encoding="utf-8") as fh:
            dane = yaml.safe_load(fh)
    except (OSError, yaml.YAMLError):
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
# 13.4: tabela skrótowców per język docelowy (do custom system promptu)
# ---------------------------------------------------------------------------
# Tabela skrótowców per język (notatki autora projektu — dawniej w nieistniejącym
# już `TODO_wielojezycznosc.md`, dziś trzymana inline tutaj jako single source).
# Po 5 najpopularniejszych pozycji per język — nie chcemy obciążać promptu
# pełnymi tabelami (10-16 pozycji), bo to zwiększa koszt każdego call'a API
# bez znaczącej poprawy wyniku. Lista służy LLM jako konkretne dane do
# wstrzyknięcia w sekcję „Cipher: Text Reverser" wynikowego dokumentu —
# zastępują polskie m.in./np./tzw./tzn./dr.
ABBREV_BY_LANG: dict[str, list[tuple[str, str]]] = {
    "en": [
        ("e.g.",   "for example"),
        ("i.e.",   "that is"),
        ("etc.",   "et cetera"),
        ("U.S.",   "United States"),
        ("U.K.",   "United Kingdom"),
    ],
    "ru": [
        ("т.е.",   "то есть"),
        ("т.д.",   "так далее"),
        ("т.н.",   "так называемый"),
        ("т.к.",   "так как"),
        ("и.о.",   "исполняющий обязанности"),
    ],
    "it": [
        ("ad es.", "ad esempio"),
        ("ecc.",   "eccetera"),
        ("dott.",  "dottore"),
        ("prof.",  "professore"),
        ("pag.",   "pagina"),
    ],
    "fi": [
        ("esim.",  "esimerkiksi"),
        ("jne.",   "ja niin edelleen"),
        ("ym.",    "ynnä muuta"),
        ("ns.",    "niin sanottu"),
        ("tms.",   "tai muuta sellaista"),
    ],
    "is": [
        ("t.d.",      "til dæmis"),
        ("þ.e.",      "það er"),
        ("m.a.",      "meðal annars"),
        ("u.þ.b.",    "um það bil"),
        ("o.s.frv.",  "og svo framvegis"),
    ],
    "de": [
        ("z.B.",   "zum Beispiel"),
        ("d.h.",   "das heißt"),
        ("usw.",   "und so weiter"),
        ("bzw.",   "beziehungsweise"),
        ("ggf.",   "gegebenenfalls"),
    ],
    "fr": [
        ("p. ex.",   "par exemple"),
        ("c.-à-d.",  "c'est-à-dire"),
        ("etc.",     "et cetera"),
        ("M.",       "Monsieur"),
        ("Dr",       "Docteur"),
    ],
}


# ---------------------------------------------------------------------------
# 13.4 / teza-3 (2026-06-16): MODULARNY system-prompt per (kod, nazwa, sekcja)
# ---------------------------------------------------------------------------
# Dokleja się do `_PROMPT_SYSTEMOWY_TEMPLATE` z `tlumacz_ai.py` przez parametr
# `prompt_dodatkowy`. Do 2026-06-16 był to JEDEN monolit (~1 286 tok) doklejany
# do KAŻDEJ z 68 sekcji — także ~59, które nie mają nic wspólnego z akcentami
# ani szyframi. Pomiar (skrypty/ai_odpowiedz.md): instrukcja zżerała 68% budżetu
# treści, rozpraszając atencję modelu na reguły nieistotne dla danej sekcji.
#
# Teza 3 — składamy prompt z bloków, wstrzykiwanych WARUNKOWO wg treści sekcji:
#   * CORE_KONTEKST + CORE_LITERALY — ZAWSZE (kontekst projektu + ochrona nazw
#     plików/folderów/placeholderów/głosów + markery ⟦i⟧).
#   * AKCENTY      — tylko gdy sekcja zawiera wyliczoną listę akcentów
#                    (≥ _PROG_GLOSOW nazw głosów): podmiana pozycji języka
#                    docelowego (no-op dla natywnego) na akcent polski Ewa/Paulina.
#   * ODWRACACZ    — tylko gdy sekcja opisuje szyfr Odwracacz (artefakt ".nim").
#   * TYPOGLIKEMIA — tylko gdy sekcja opisuje szyfr Typoglikemia.
# Bias detekcji: false-positive (zbędny blok) = stracone tokeny (nieszkodliwe);
# false-negative (brak bloku w sekcji szyfru/akcentu) = leak polskiego przykładu
# → detektory są raczej zachłanne. CORE_LITERALY ląduje NA KOŃCU (recency:
# najbliżej tłumaczonego tekstu są najważniejsze zakazy ochrony literałów).
_PROMPT_CORE_KONTEKST = """\
## Project context (CRITICAL — read carefully)
This documentation describes "Reżyser Audio GPT", a Polish desktop tool for writers
and voice-over creators. The translation is for a {nazwa_natywna} user who already
has the "dictionaries/{kod}/" package installed and complete in version 13.4.
DO NOT write that {nazwa_natywna} support is "coming in a future version" — it is
already shipped and the user is reading these docs in {nazwa_natywna} right now.

The application supports MULTIPLE source languages (today: Polish and English; more
in 13.4+). Each "dictionaries/<source>/" folder is a self-contained rule pack that
operates on input text written in that source language. The application uses
langdetect to pick the right pack automatically — you must NOT claim that the rules
apply to Polish source only.\
"""

_PROMPT_AKCENTY = """\
### Accent list — REPLACE the native accent
The docs include a list of available accents like:
  - English (Samantha/Mark in Vocalizer, Zira/Hazel in OneCore)
  - Finnish (Satu/Mikko in Vocalizer, Heidi in OneCore)
  - Italian (Alice/Luca in Vocalizer, Elsa in OneCore)
  ...

One entry matches the TARGET language ({nazwa_natywna}). That entry is meaningless
for this reader — applying e.g. an English accent to text already in English is a
no-op. REPLACE the {nazwa_natywna} entry with a POLISH accent entry, using these
voice names:
    Polish (Ewa in Vocalizer, Paulina in OneCore)

Keep ALL OTHER entries (translate language NAMES to {nazwa_natywna}, but preserve
voice names like Samantha, Markus, Heidi, Gudrun, Milena 1:1 — product names).\
"""

_PROMPT_ODWRACACZ = """\
### Cipher: Text Reverser — replace abbreviations with target-language equivalents
The Reverser cipher section lists Polish abbreviations (m.in., np., tzw., tzn., dr.)
that the script expands BEFORE reversing the sentence — without expansion, dotted
abbreviations would reverse into phonetic nonsense (Polish example: ".nim").

You MUST localize this:
  1. REPLACE the 5 Polish abbreviations with these {nazwa_natywna} equivalents:
{abbreviation_list}
  2. RE-COMPUTE the nonsense example (".nim" in Polish): take the FIRST abbreviation
     from your replacement list, reverse it character-by-character, and present that
     as the new nonsense example for the target language.\
"""

_PROMPT_TYPOGLIKEMIA = """\
### Cipher: Typoglycemia — DECODE, TRANSLATE, RE-SCRAMBLE
The Typoglycemia section contains an example sentence that is ITSELF an output of
the cipher (Polish, scrambled middles):
   "Nie meossż peyrzcztać tkstueu w trkirej klojoinseęci letir, jśeli pszeriwa i
    otsnatia leritea są na wscłaoyicwh mscjaieh"

The unscrambled meaning is roughly: "You can read text in any letter order as long
as the first and last letters of each word are in the right place."

You MUST:
  1. RECOGNIZE that the example is itself scrambled — do NOT copy it verbatim.
  2. TRANSLATE the unscrambled meaning into {nazwa_natywna} naturally.
  3. RE-SCRAMBLE the translation: keep the FIRST and LAST character of every word
     longer than 3 characters; randomly permute the middle characters. Words of 3
     or fewer characters stay unchanged.

For English, a well-known canonical version exists you can use as a reference:
   "Aoccdrnig to a rscheearch at Cmabrigde Uinervtisy, it deosn't mttaer in waht
    oredr the ltteers in a wrod are, the olny iprmoatnt tihng is taht the frist
    and lsat ltteer be at the rghit pclae."

For other languages, generate an equivalent in the same spirit.\
"""

_PROMPT_CORE_LITERALY = """\
### Filenames, folders, placeholders and voice names — KEEP 1:1
Polish filenames (angielski.yaml, cezar.yaml, podstawy.yaml, finski.yaml, islandzki.yaml,
naprawiacz_tagow.yaml, oczyszczenie.yaml, oczyszczenie_bez_liczb.yaml, rosyjski.yaml,
wloski.yaml, niemiecki.yaml, francuski.yaml, hiszpanski.yaml, polski.yaml) are PHYSICAL
filenames in the package — keep them verbatim, do NOT translate.

Physical FOLDER names are literal identifiers on disk, NOT words to translate:
skrypty/, opowiesci/, runtime/, rezyser/, akcenty/, szyfry/, dictionaries/, golden_key.env,
etc. KEEP the Polish spelling (e.g. do NOT render "opowiesci/" with a {nazwa_natywna} word
for "stories", do NOT render "szyfry/" with a word for "ciphers").

Angle-bracket placeholders such as <nazwa>, <kod>, <name> are template tokens: copy the
brackets and the inner text character-for-character, do NOT translate the inner word
(e.g. do NOT render <nazwa> with a {nazwa_natywna} word for "name").

Voice product names (Samantha, Mark, Markus, Hedda, Heidi, Gudrun, Milena, Irina,
Pavel, Yuri, Satu, Mikko, Thomas, Amelie, Julie, Stefan, Katja, Jorge, Monica, Helena,
Alice, Luca, Elsa, Zira, Hazel, Ewa, Paulina) are product names — keep 1:1.

### Frozen markers ⟦i⟧
Every ⟦N⟧ marker is a frozen placeholder. Copy character-for-character; do not
translate, do not renumber, do not insert new ones.\
"""


# Nazwy głosów TTS z listy akcentów — sygnał detekcji sekcji „wyliczona lista
# akcentów". ≥ _PROG_GLOSOW różnych nazw w sekcji ⟹ to lista do podmiany, a nie
# mimochodem wspomniany pojedynczy głos (np. „VoiceOver z Vocalizerem").
_GLOSY_AKCENTOW = frozenset({
    "Samantha", "Mark", "Zira", "Hazel", "Milena", "Irina", "Pavel", "Yuri",
    "Thomas", "Amelie", "Julie", "Markus", "Stefan", "Hedda", "Katja", "Jorge",
    "Monica", "Helena", "Gudrun", "Alice", "Luca", "Elsa", "Satu", "Mikko", "Heidi",
})
_PROG_GLOSOW = 3


def _sekcja_ma_liste_akcentow(tresc: str) -> bool:
    """True, gdy sekcja zawiera wyliczoną listę akcentów (≥ _PROG_GLOSOW głosów)."""
    return sum(1 for g in _GLOSY_AKCENTOW if g in tresc) >= _PROG_GLOSOW


def _sekcja_ma_odwracacz(tresc: str) -> bool:
    """True, gdy sekcja opisuje szyfr Odwracacz (artefakt ".nim" = odwrócony skrótowiec)."""
    return ".nim" in tresc


def _sekcja_ma_typoglikemie(tresc: str) -> bool:
    """True, gdy sekcja opisuje szyfr Typoglikemia (manual i dictionaries mają różne przykłady)."""
    return "typoglik" in tresc.lower()


# ---------------------------------------------------------------------------
# v17.0: RETRY — blok korekcji leaków (doklejany per-sekcja w trybie --retry)
# ---------------------------------------------------------------------------
# Zwykły surgical retranslate (--klucz) NIE naprawia leaków — empiryczny dowód
# z v17.0 (sekcja Polish-naming: 3× re-tłumaczenie zostawiało polski, bo LLM ma
# blind spot przy treściach które same wspominają „zostaw po polsku"). Ten blok
# jest analogiem self-correction z rezyser_ai/opowiesci_ai („YOUR PREVIOUS OUTPUT
# FAILED VALIDATION...") — wstrzykujemy KONKRETNE polskie fragmenty wykryte przez
# audyt_leakow w istniejącym tłumaczeniu i każemy je zlikwidować. Angielski (jak
# PROMPT_TEMPLATE_DOKUMENTACJA) — neutralny dla każdej pary językowej.
RETRY_BLOK_TEMPLATE = """\
## RETRY — LEAK CORRECTION (CRITICAL)
A previous automatic translation of THIS section into {nazwa_natywna} LEFT POLISH
TEXT UNTRANSLATED — a defect you must now fix. You are re-translating from the
Polish source. Translate EVERY word into {nazwa_natywna}, WITH the following strict
exceptions that you must COPY VERBATIM — translating any of them is itself a defect,
because it hands the reader a path, token or term that does not exist in the running
application:
  - the frozen ⟦N⟧ markers;
  - the brand name "Reżyser Audio GPT";
  - physical file AND FOLDER names — these are literal identifiers on disk, NOT
    words to translate: skrypty/, opowiesci/, runtime/, rezyser/, akcenty/, szyfry/,
    dictionaries/, podstawy.yaml, golden_key.env, etc. KEEP the Polish spelling
    (e.g. do NOT render "opowiesci/" with a {nazwa_natywna} word for "stories");
  - angle-bracket placeholders such as <nazwa>, <kod>, <name>: copy the brackets
    and the inner text character-for-character, do NOT translate <nazwa>;
  - voice product names (Samantha, Heidi, Markus, ...);
  - the deliberately-Polish DIDACTIC cipher examples (Vowelizer/Reverser/
    Typoglycemia) — those you LOCALIZE per the rules above, you do NOT leave them
    in Polish.

CRITICAL — module/persona names: the Polish source uses "Reżyser" (Director),
"Poliglota" (Polyglot), "Manager Reguł" (Rule Manager), "Księga Świata" (World
Book). Render them with the established {nazwa_natywna} terms and INFLECT them
grammatically as the sentence requires — Polish case forms like "Reżysera",
"Reżyserowi", "Poligloty", "Księgę Świata" are NOT to be copied; use the correct
{nazwa_natywna} declension of the {nazwa_natywna} term instead.

The previous attempt specifically left these Polish fragments — NONE of them may
appear in Polish in your output (localize/inflect, do not copy):
{lista_leakow}\
"""


def _zbuduj_retry_blok(leaki: list[Any], nazwa_natywna: str) -> str:
    """Buduje blok RETRY z unikalnych polskich fragmentów wykrytych w sekcji.

    Zwraca pusty string, gdy brak leaków — wtedy retry degraduje do zwykłego
    surgical retranslate (bez nacisku). Deduplikacja zachowuje kolejność
    wystąpień; limit 40 pozycji (prompt nie ma puchnąć w nieskończoność).
    """
    widziane: list[str] = []
    for leak in leaki:
        frag = leak.fragment.strip()
        if frag and frag not in widziane:
            widziane.append(frag)
    if not widziane:
        return ""
    lista = "\n".join(f"     - {frag}" for frag in widziane[:40])
    return RETRY_BLOK_TEMPLATE.format(nazwa_natywna=nazwa_natywna, lista_leakow=lista)


# ---------------------------------------------------------------------------
# v17.0: META-komentarze (zawsze-on) — LLM dokleja `===META===` + komentarz
# ---------------------------------------------------------------------------
# Doklejane do system-promptu KAŻDEGO tłumaczenia sekcji (doc-autotłumacz).
# GUI Poliglota NIE jest dotknięte (woła tlumacz_dlugi_tekst bez tego dodatku).
# Treść po `===META===` jest wycinana przed walidacją tokenów i zapisem YAML,
# a logowana do skrypty/output.log jako „### kod/plik/klucz\n<komentarz>".
# Cel: widoczność rozumowania LLM (co/dlaczego, konflikty instrukcji) → user
# czyta i może odpowiedzieć krytyką przez input.log (tryb --input).
META_INSTRUKCJA = (
    "## META COMMENTARY (required, appended AFTER the translation)\n"
    "After the COMPLETE translated text, output a line containing EXACTLY "
    f"`{META_MARKER}` and then 1–4 sentences (in English) describing: notable "
    "translation/terminology choices for THIS section, and ESPECIALLY any conflict, "
    "ambiguity or impossible requirement you noticed in the instructions. Everything "
    f"after `{META_MARKER}` is stripped before saving — do NOT place any translated "
    f"content there. Output `{META_MARKER}` exactly ONCE, at the very end."
)


def rozdziel_meta(tekst: str) -> tuple[str, str]:
    """Dzieli odpowiedź LLM na (tłumaczenie, meta-komentarz) po `===META===`.

    Split na PIERWSZYM markerze (sekcje doc są jednoblokowe — patrz jawny
    `max_tokenow_na_blok=4_000` przy wywołaniu `tlumacz_dlugi_tekst`; meta
    pojawia się raz, na końcu). Brak markera → ("", tekst, "")
    tzn. całość to tłumaczenie, meta puste.
    """
    if META_MARKER in tekst:
        tlum, meta = tekst.split(META_MARKER, 1)
        return tlum.rstrip(), meta.strip()
    return tekst, ""


def _dopisz_meta_log(kod: str, nazwa_pliku: str, klucz: str, meta: str) -> None:
    """Dopisuje meta-komentarz do skrypty/output.log („### kod/plik/klucz")."""
    if not meta:
        return
    SKRYPTY_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_LOG, "a", encoding="utf-8") as fh:
        fh.write(f"### {kod}/{nazwa_pliku}/{klucz}\n{meta}\n\n")


# ---------------------------------------------------------------------------
# v17.0: tryb --input — krytyka usera per-klucz z skrypty/input.log
# ---------------------------------------------------------------------------
# Osobny workflow od --retry (auto-leaki). User czyta output.log, pisze krytykę
# w TYM SAMYM formacie do input.log, odpala --input. Bot retłumaczy TYLKO klucze
# wskazane w input.log, wstrzykując krytykę. Bez auto-detekcji leaków.
INPUT_BLOK_TEMPLATE = """\
## REVIEWER FEEDBACK — TARGETED CORRECTION (CRITICAL)
A human reviewer examined your PREVIOUS translation of THIS section and left the
correction note below. Re-translate from the Polish source and apply this note
precisely; it overrides your earlier choices where they conflict. Keep all the
KEEP-1:1 rules above (markers ⟦N⟧, brand, filenames/folders, placeholders, voices).

Reviewer note:
{krytyka}\
"""


def _zbuduj_input_blok(krytyka: str) -> str:
    """Buduje blok korekty z notatki recenzenta (input.log) dla jednej sekcji."""
    krytyka = (krytyka or "").strip()
    if not krytyka:
        return ""
    return INPUT_BLOK_TEMPLATE.format(krytyka=krytyka)


def parsuj_input_log(sciezka: Path) -> dict[str, str]:
    """Parsuje input.log → {„kod/plik/klucz": krytyka}. Format „### nagłówek\\n<treść>".

    Ten sam format co output.log (meta), żeby było jasne co punktujemy dla którego
    klucza. Nagłówek = linia zaczynająca się od „### ". Treść = linie do następnego
    „### " (puste linie brzegowe przycinane).
    """
    if not sciezka.is_file():
        return {}
    wpisy: dict[str, str] = {}
    biezacy: str | None = None
    bufor: list[str] = []

    def _zamknij() -> None:
        if biezacy is not None:
            tresc = "\n".join(bufor).strip()
            if tresc:
                wpisy[biezacy] = tresc

    with open(sciezka, "r", encoding="utf-8") as fh:
        for linia in fh:
            if linia.startswith("### "):
                _zamknij()
                biezacy = linia[4:].strip()
                bufor = []
            elif biezacy is not None:
                bufor.append(linia.rstrip("\n"))
    _zamknij()
    return wpisy


def _zbuduj_prompt_dodatkowy(
    kod: str, nazwa_natywna: str, tresc_sekcji: str = ""
) -> str:
    """Buduje custom system-prompt dla pary (kod_docelowy, nazwa_natywna).

    Zwraca pusty string, gdy nie mamy tabeli skrótowców dla danego języka —
    wtedy autotłumacz korzysta z bazowego promptu z `tlumacz_ai.py` bez modyfikacji.

    Teza 3 (2026-06-16): bloki AKCENTY/ODWRACACZ/TYPOGLIKEMIA wstrzykiwane
    WARUNKOWO — tylko gdy `tresc_sekcji` faktycznie zawiera dany artefakt
    (lista akcentów / ".nim" / Typoglikemia). CORE (kontekst + literały) zawsze.
    `tresc_sekcji=""` (wywołanie bez treści, np. ad-hoc) = zachowawczy fallback:
    wstrzykuje WSZYSTKIE bloki (stare zachowanie monolitu sprzed tezy 3).
    """
    abbrev = ABBREV_BY_LANG.get(kod)
    if not abbrev:
        return ""

    nieznana = not tresc_sekcji  # brak treści ⟹ nie wiemy, więc wstrzyknij wszystko
    czesci = [_PROMPT_CORE_KONTEKST.format(kod=kod, nazwa_natywna=nazwa_natywna)]

    if nieznana or _sekcja_ma_liste_akcentow(tresc_sekcji):
        czesci.append(_PROMPT_AKCENTY.format(nazwa_natywna=nazwa_natywna))
    if nieznana or _sekcja_ma_odwracacz(tresc_sekcji):
        bullety = "\n".join(f'     - "{skr}" → "{exp}"' for skr, exp in abbrev)
        czesci.append(_PROMPT_ODWRACACZ.format(
            nazwa_natywna=nazwa_natywna, abbreviation_list=bullety,
        ))
    if nieznana or _sekcja_ma_typoglikemie(tresc_sekcji):
        czesci.append(_PROMPT_TYPOGLIKEMIA.format(nazwa_natywna=nazwa_natywna))

    czesci.append(_PROMPT_CORE_LITERALY.format(nazwa_natywna=nazwa_natywna))
    return "\n\n".join(czesci)


# ---------------------------------------------------------------------------
# Prefix-instrukcja dla LLM (dokleja się do samej treści, nie do systemu)
# ---------------------------------------------------------------------------
# `_prompt_systemowy` w tlumacz_ai.py NIE jest modyfikowany (reguła 13.1).
# Ten prefix jest doklejany jako pierwszy fragment user-promptu. Po stronie
# wyniku szukamy końcowego markera — jeżeli model go usunął (zgodnie
# z instrukcją „Zwróć WYŁĄCZNIE przetłumaczony tekst"), bierzemy wynik
# w całości. Jeżeli zostawił — utniemy prefix ręcznie.
MARKER_KONCA_PREFIXU = "[KONIEC INSTRUKCJI — TŁUMACZENIE ZACZYNA SIĘ PONIŻEJ]"

PREFIX_INSTRUKCJA = (
    "[INSTRUKCJA TECHNICZNA — USUŃ TEN BLOK Z ODPOWIEDZI, NIE TŁUMACZ GO]\n"
    "Poniższy tekst zawiera markery w formacie ⟦liczba⟧ (np. ⟦0⟧, ⟦12⟧, ⟦47⟧).\n"
    "To są zamrożone placeholdery programowe. Skopiuj je do odpowiedzi DOSŁOWNIE,\n"
    "znak w znak — nie zmieniaj cyfr, nie zmieniaj nawiasów, nie tłumacz.\n"
    "Każdy marker musi wystąpić w odpowiedzi dokładnie tyle samo razy,\n"
    "co w oryginale (skrypt nadrzędny weryfikuje parzystość po zakończeniu).\n"
    f"{MARKER_KONCA_PREFIXU}\n\n"
)


# ---------------------------------------------------------------------------
# Tokenizacja / detokenizacja / walidacja parzystości
# ---------------------------------------------------------------------------
def tokenizuj(tekst: str) -> tuple[str, dict[int, str]]:
    """Zastępuje każdy `{klucz}` unikalnym `⟦i⟧`. Zwraca (tekst, mapa i→oryginał)."""
    mapa: dict[int, str] = {}
    licznik = 0

    def _zamien(match: re.Match[str]) -> str:
        nonlocal licznik
        idx = licznik
        mapa[idx] = match.group(0)   # całość, razem z nawiasami klamrowymi
        licznik += 1
        return TOKEN_FORMAT.format(idx)

    tekst_tok = PLACEHOLDER_REGEX.sub(_zamien, tekst)
    return tekst_tok, mapa


def detokenizuj(tekst: str, mapa: dict[int, str]) -> str:
    """Przywraca `{klucz}` pod każdym `⟦i⟧`. Nieznane indeksy zostawia jak są."""
    def _zamien(match: re.Match[str]) -> str:
        idx = int(match.group(1))
        return mapa.get(idx, match.group(0))

    return TOKEN_REGEX.sub(_zamien, tekst)


def sprawdz_parzystosc(
    tekst_we: str, tekst_wy: str
) -> tuple[bool, list[str]]:
    """Porównuje multiset tokenów ⟦i⟧ na wejściu i wyjściu.

    Zwraca ``(True, [])`` przy pełnej zgodności. W przeciwnym razie
    ``(False, lista_diagnostyk)`` — każda linia diagnostyki raportuje
    jeden problematyczny token (ile wystąpień mniej/więcej).
    """
    we = Counter(TOKEN_REGEX.findall(tekst_we))
    wy = Counter(TOKEN_REGEX.findall(tekst_wy))
    if we == wy:
        return True, []

    problemy: list[str] = []
    wszystkie = set(we) | set(wy)
    for idx in sorted(wszystkie, key=int):
        ile_we, ile_wy = we.get(idx, 0), wy.get(idx, 0)
        if ile_we != ile_wy:
            problemy.append(
                f"⟦{idx}⟧ — wejście: {ile_we}×, wyjście: {ile_wy}×"
            )
    return False, problemy


def utnij_prefix_z_wyniku(wynik: str) -> str:
    """Usuwa prefix-instrukcję z odpowiedzi LLM (jeśli nie usunął sam)."""
    idx = wynik.find(MARKER_KONCA_PREFIXU)
    if idx == -1:
        # Model posłuchał i usunął blok META — zostawiamy wynik w całości.
        return wynik.lstrip()
    return wynik[idx + len(MARKER_KONCA_PREFIXU):].lstrip()


# ---------------------------------------------------------------------------
# Budowanie wynikowego YAML-a (block scalar `|` + nagłówek-komentarz)
# ---------------------------------------------------------------------------
def _wcetnij_blok_scalar(tresc: str, wciecie: int = 2) -> list[str]:
    """Wcina każdą linię o `wciecie` spacji, pust linie zostawia jako puste."""
    linie = tresc.split("\n")
    # Usuń ostatnią pustą linię (artefakt rstrip + "\n" w buduj sekcji)
    if linie and linie[-1] == "":
        linie = linie[:-1]
    prefix = " " * wciecie
    return [prefix + l if l.strip() else "" for l in linie]


def zbuduj_yaml_wynikowy(
    kod_jezyka: str,
    id_szablonu: str,
    tresc: str | dict[str, str],
    nazwa_pliku: str,
    *,
    tryb_draft: bool = False,
) -> str:
    """Składa ``dictionaries/<kod>/gui/dokumentacja/<plik>.yaml`` do zapisu.

    Nie używamy `yaml.dump` — nie gwarantuje on block-scalar stylu `|`
    w ładnej formie, zwłaszcza dla treści z nawiasami klamrowymi
    (wymusiłby cudzysłowy). Budujemy ręcznie.

    Tresc może być:
      * stringiem — stary schemat z jednego block-scalar `|`. Wynik:
        ``id: <id>\\ntresc: |\\n  <treść wcięta 2 spacjami>``.
      * słownikiem ``{klucz_sekcji: tresc_sekcji}`` — nowy schemat (v15.2+).
        Każda wartość zapisana jako osobny block-scalar `|` wcięty 4 spacjami
        (klucz sekcji wcięty 2 spaceami pod `tresc:`).
    """
    sciezka_rel = f"dictionaries/{kod_jezyka}/gui/dokumentacja/{nazwa_pliku}"
    zrodlo_rel = f"dictionaries/{KOD_ZRODLOWY}/gui/dokumentacja/{nazwa_pliku}"
    if tryb_draft:
        # Tryb roboczy: neutralny nagłówek zachęcający do edycji (review
        # halucynacji przez osobę trzecią / agenta bez naszej konstytucji).
        naglowek = przeglad_tlumaczen.naglowek_roboczy(
            sciezka_rel, zrodlo_rel, "buduj_wielojezyczne_docs.py",
        )
    else:
        naglowek = (
            "# =============================================================================\n"
            f"# {sciezka_rel}\n"
            "#\n"
            "# Plik wygenerowany automatycznie przez buduj_wielojezyczne_docs.py\n"
            f"# ze źródła {zrodlo_rel}\n"
            "# (język bazowy PL, wersja 13.x). NIE edytuj ręcznie — zmiany wprowadzaj\n"
            "# w pliku źródłowym PL i uruchom ponownie skrypt tłumacza.\n"
            "#\n"
            "# Silnik: OpenAI (tlumacz_ai.py). Placeholdery {klucz.zagniezdzony}\n"
            "# zostały zamrożone tokenami ⟦i⟧ na czas tłumaczenia i odtworzone 1:1\n"
            "# po weryfikacji parzystości multisetu markerów.\n"
            "# =============================================================================\n"
            "\n"
        )

    if isinstance(tresc, str):
        # Stary schemat: jeden block-scalar `|`
        wciete = _wcetnij_blok_scalar(tresc, wciecie=2)
        cialo = f"id: {id_szablonu}\ntresc: |\n" + "\n".join(wciete)
        if not cialo.endswith("\n"):
            cialo += "\n"
        return naglowek + cialo

    if isinstance(tresc, dict):
        # Nowy schemat: tresc jako dict sekcji. Każda sekcja to osobny `|` scalar.
        cialo = f"id: {id_szablonu}\ntresc:\n"
        for klucz, sekcja in tresc.items():
            cialo += f"  {klucz}: |\n"
            wciete = _wcetnij_blok_scalar(sekcja, wciecie=4)
            for linia in wciete:
                cialo += linia + "\n"
        return naglowek + cialo

    raise TypeError(f"`tresc` musi być stringiem albo dict-em, dostałem {type(tresc).__name__}")


# ---------------------------------------------------------------------------
# Wczytanie źródła PL
# ---------------------------------------------------------------------------
# Klucz „_legacy" dla starych yaml-ów (string tresc): pakujemy do dict z jednym
# kluczem, żeby downstream miał spójny interfejs. Dict z jednym kluczem
# „_legacy" odpowiada zachowaniu sprzed v15.2 (jedno wywołanie LLM dla całości).
KLUCZ_LEGACY = "_legacy"


def wczytaj_szablony_pl() -> list[tuple[str, str, dict[str, str]]]:
    """Zwraca listę ``(nazwa_pliku, id, sekcje)`` z PL-owej dokumentacji.

    Od v15.2 (task #3) szablony PL mają ``tresc`` jako dict sekcji
    (``{krok_1: |..., krok_2: |..., ...}``) — pozwala to na surgical update
    pojedynczej sekcji (``--klucz`` w CLI) zamiast retłumaczania całego
    manuala 8 razy przy każdej drobnej zmianie.

    Backward-compat: jeśli ``tresc`` jest stringiem (stary schemat z v15.1
    i wcześniej), opakowujemy w dict z jednym kluczem ``_legacy``. Downstream
    nie musi rozróżniać — ten sam pipeline tokenizacji + tłumaczenia.

    Returns:
        Lista trójek (nazwa pliku jak ``manual.yaml``, id szablonu, dict sekcji).
        Posortowana alfabetycznie po nazwie pliku, żeby kolejność tłumaczenia
        była deterministyczna (cache wznawiania w runtime/ jest po niej kluczowany).
    """
    folder = DICT_DIR / KOD_ZRODLOWY / FOLDER_GUI / FOLDER_DOKUMENTACJA
    if not folder.is_dir():
        raise FileNotFoundError(f"Brak folderu źródłowego PL: {folder}")

    szablony: list[tuple[str, str, dict[str, str]]] = []
    for plik in sorted(folder.glob("*.yaml")):
        with open(plik, "r", encoding="utf-8") as fh:
            dane = yaml.safe_load(fh)
        if not isinstance(dane, dict):
            print(f"⚠️  Pomijam {plik.name}: nie parsuje się do słownika YAML.")
            continue
        id_szablonu = dane.get("id")
        if not isinstance(id_szablonu, str):
            print(f"⚠️  Pomijam {plik.name}: brak stringowego pola `id`.")
            continue
        tresc = dane.get("tresc")
        if isinstance(tresc, str):
            sekcje = {KLUCZ_LEGACY: tresc}
        elif isinstance(tresc, dict):
            # Filtruj tylko stringowe wartości (inne typy — pomiń z ostrzeżeniem)
            sekcje = {}
            for k, v in tresc.items():
                if isinstance(v, str):
                    sekcje[k] = v
                else:
                    print(f"⚠️  {plik.name}: sekcja '{k}' nie jest stringiem — pomijam.")
            if not sekcje:
                print(f"⚠️  Pomijam {plik.name}: dict `tresc` nie ma żadnych stringowych sekcji.")
                continue
        else:
            print(f"⚠️  Pomijam {plik.name}: `tresc` musi być stringiem albo dictem.")
            continue
        szablony.append((plik.name, id_szablonu, sekcje))

    if not szablony:
        raise ValueError(
            f"Folder {folder} nie zawiera żadnego poprawnego szablonu *.yaml."
        )
    return szablony


def wczytaj_istniejacy_docelowy(plik_docelowy: Path) -> dict[str, str] | None:
    """Wczytuje istniejący <kod>/gui/dokumentacja/<plik>.yaml jako dict sekcji.

    Używane przez tryb ``--klucz`` (surgical update): tłumaczymy TYLKO wybrane
    sekcje, reszta zostaje z istniejącego pliku docelowego. Zwraca dict sekcji
    lub None, gdy plik nie istnieje / nie da się sparsować.

    Konwersja starego schematu (string tresc) → dict: opakowujemy w
    ``{_legacy: str}`` — to znaczy że plik docelowy jest w starym schemacie.
    Surgical update na pojedynczy klucz z dictu PL nie zadziała w takim
    przypadku (klucz PL nie istnieje w docelowym), więc wywołujący musi
    poradzić sobie z fallback-iem (najczęściej: retłumacz cały plik bez --klucz).
    """
    if not plik_docelowy.is_file():
        return None
    try:
        with open(plik_docelowy, "r", encoding="utf-8") as fh:
            dane = yaml.safe_load(fh)
    except (OSError, yaml.YAMLError):
        return None
    if not isinstance(dane, dict):
        return None
    tresc = dane.get("tresc")
    if isinstance(tresc, str):
        return {KLUCZ_LEGACY: tresc}
    if isinstance(tresc, dict):
        return {k: v for k, v in tresc.items() if isinstance(v, str)}
    return None


# ---------------------------------------------------------------------------
# Pipeline dla jednego języka docelowego
# ---------------------------------------------------------------------------
def _tlumacz_pojedyncza_sekcje(
    kod: str,
    nazwa_pl: str,
    klient: Any,
    nazwa_pliku: str,
    rdzen: str,
    klucz_sekcji: str,
    tresc_pl: str,
    *,
    dry_run: bool,
    model: str,
    prompt_dodatkowy: str,
    retry: bool = False,
) -> tuple[bool, str | None]:
    """Tłumaczy pojedynczą sekcję (tokenizacja + LLM + walidacja + detokenizacja).

    Zwraca (success, przetłumaczona_tresc). Cache wznawiania w runtime/ jest
    kluczowany przez `{rdzen}_{klucz_sekcji}_{KOD_ZRODLOWY}_to_{kod}` —
    dzięki temu temp_manual_krok_5_vocalizer_pl_to_en_*.jsonl żyje obok
    temp_manual_krok_5_onecore_pl_to_en_*.jsonl, a częściowy progres jednej
    sekcji nie psuje drugiej.
    """
    tresc_tok, mapa = tokenizuj(tresc_pl)
    liczba_ph = len(mapa)
    sufiks = f" ({klucz_sekcji})" if klucz_sekcji != KLUCZ_LEGACY else ""
    print(
        f"ℹ️  {kod}/{nazwa_pliku}{sufiks}: zamrożono {liczba_ph} placeholderów → "
        f"tokeny ⟦0..{max(liczba_ph - 1, 0)}⟧, {len(tresc_pl):,} znaków źródła."
    )
    if dry_run:
        oryginalne = Counter(PLACEHOLDER_REGEX.findall(tresc_pl))
        ok_sanity = sum(oryginalne.values()) == liczba_ph
        marker = "✅" if ok_sanity else "⚠️"
        print(f"    {marker} Sanity check: {sum(oryginalne.values())} wystąpień ph, mapa {liczba_ph}.")
        return True, None

    payload = PREFIX_INSTRUKCJA + tresc_tok
    blad_kryt: dict[str, Any] = {"msg": None, "partial": None}
    cache_key = (
        f"{rdzen}_{klucz_sekcji}_{KOD_ZRODLOWY}_to_{kod}"
        if klucz_sekcji != KLUCZ_LEGACY
        else f"{rdzen}_{KOD_ZRODLOWY}_to_{kod}"
    )
    if retry:
        # Świeża przestrzeń cache + wymuszone czyszczenie: retry MUSI ominąć
        # stary, zaleakowany temp_*.jsonl (inaczej tlumacz_dlugi_tekst odtworzy
        # zaleakowany blok z dysku zamiast tłumaczyć z naciskiem na leaki).
        from tlumacz_ai import zbuduj_nazwe_bazowa
        cache_key += "_retry"
        base = zbuduj_nazwe_bazowa(cache_key, nazwa_pl)
        temp = RUNTIME_DIR / f"temp_{base}.jsonl"
        try:
            temp.unlink()
        except OSError:
            pass

    def _on_postep(info: Any) -> None:
        # `info` to InfoPostepu — str() zwraca czytelny `detal` (mostek i18n
        # nieistotny dla CLI dev-toola; liczy się log z procentem).
        sys.stderr.write(f"   [{kod}/{rdzen}{sufiks} {info.procent:3d}%] {info}\n")

    def _on_blad_krytyczny(info: Any, partial: str) -> None:
        # `info` to InfoBleduTlumaczenia — str() zwraca techniczny detal EN
        # (mostek i18n nieistotny dla CLI dev-toola; liczy się czytelny log).
        blad_kryt["msg"] = str(info)
        blad_kryt["partial"] = partial

    def _on_blad_miekki(info: Any) -> None:
        print(f"⚠️  {kod}/{nazwa_pliku}{sufiks}: {str(info).splitlines()[0]}")

    # META zawsze-on (doc-autotłumacz): LLM dokleja `===META===` + komentarz.
    prompt_z_meta = (prompt_dodatkowy + "\n\n" + META_INSTRUKCJA).strip()

    wynik = tlumacz_dlugi_tekst(
        tresc=payload,
        jezyk_docelowy=nazwa_pl,
        klient=klient,
        runtime_dir=str(RUNTIME_DIR),
        oryginalna_nazwa=cache_key,
        on_postep=_on_postep,
        on_blad_krytyczny=_on_blad_krytyczny,
        on_blad_miekki=_on_blad_miekki,
        model_tlumacz=model,
        prompt_dodatkowy=prompt_z_meta,
        # Jawnie ponad domyślne 2 500: sekcje doc MUSZĄ być jednoblokowe
        # (inaczej `===META===` wylądowałby w środku sklejki — patrz
        # `rozdziel_meta`). 4 000 tokenów ≈ stary limit znakowy 14-16k;
        # bezpieczne, bo docs tłumaczymy wyłącznie na języki łacińskie
        # i cyrylicę (nie token-gęste CJK).
        max_tokenow_na_blok=4_000,
    )
    if wynik is None:
        komunikat = blad_kryt["msg"] or "nieznany błąd silnika tlumacz_ai.py"
        print(f"❌  {kod}/{nazwa_pliku}{sufiks}: przerwano tłumaczenie.\n    {komunikat.splitlines()[0]}")
        return False, None

    tekst_po_prefiksie = utnij_prefix_z_wyniku(wynik.tekst)
    tekst_wy, meta = rozdziel_meta(tekst_po_prefiksie)
    if meta:
        _dopisz_meta_log(kod, nazwa_pliku, klucz_sekcji, meta)
        print(f"   📝 {kod}/{nazwa_pliku}{sufiks}: meta → output.log ({len(meta)} zn.)")
    ok, problemy = sprawdz_parzystosc(tresc_tok, tekst_wy)
    if not ok:
        print(f"❌  {kod}/{nazwa_pliku}{sufiks}: NARUSZONA parzystość markerów ⟦i⟧.")
        for diag in problemy[:10]:
            print(f"     {diag}")
        if len(problemy) > 10:
            print(f"     ... (+{len(problemy) - 10} kolejnych)")
        return False, None

    tekst_final = detokenizuj(tekst_wy, mapa)
    return True, tekst_final


def tlumacz_szablon(
    kod: str,
    nazwa_pl: str,
    nazwa_natywna: str,
    klient: Any,
    nazwa_pliku: str,
    id_szablonu: str,
    sekcje_pl: dict[str, str],
    *,
    skip_existing: bool,
    dry_run: bool,
    model: str,
    klucze_filtru: list[str] | None = None,
    retry: bool = False,
    input_krytyki: dict[str, str] | None = None,
    tryb_draft: bool = False,
) -> bool:
    """Pełny przebieg tłumaczenia jednego pliku-szablonu na jeden język.

    Od v15.2 (task #3) przyjmuje ``sekcje_pl`` jako dict (zamiast pojedynczego
    stringa). Każda sekcja przepuszczana osobno przez tlumacz_ai z osobnym
    cache wznawiania w ``runtime/``. Argument ``nazwa_natywna`` wchodzi do
    customowego system-promptu z :func:`_zbuduj_prompt_dodatkowy`.

    Tryby pracy:

      * **FULL** (``klucze_filtru=None``): tłumaczy wszystkie sekcje z ``sekcje_pl``
        i zapisuje cały plik na nowo (overwrite). To tradycyjne zachowanie
        przed v15.2 + obsługa nowego dict-schematu.

      * **SURGICAL** (``klucze_filtru=['krok_5_vocalizer', ...]``): tłumaczy
        TYLKO wskazane klucze, wczytuje istniejący plik docelowy, podmienia
        w nim wskazane sekcje i zapisuje całość. Wymaga, by plik docelowy
        już istniał W NOWYM SCHEMACIE (dict tresc). Stare pliki ze stringiem
        tresc nie obsłużą surgical update — najpierw FULL retłumacz.
    """
    cel = DICT_DIR / kod / FOLDER_GUI / FOLDER_DOKUMENTACJA / nazwa_pliku
    if klucze_filtru is None and cel.exists() and skip_existing:
        print(f"⏭️  {kod}/{nazwa_pliku}: już istnieje — pomijam (--skip-existing).")
        return True

    # SURGICAL: filtruj sekcje + wczytaj istniejący plik docelowy do scalenia
    sekcje_do_tlumaczenia: dict[str, str] = sekcje_pl
    sekcje_istniejace: dict[str, str] | None = None
    if klucze_filtru is not None:
        nieznane = [k for k in klucze_filtru if k not in sekcje_pl]
        if nieznane:
            print(f"❌ {kod}/{nazwa_pliku}: nieznane klucze w PL: {nieznane}")
            print(f"   Dostępne klucze PL: {sorted(sekcje_pl.keys())}")
            return False
        sekcje_do_tlumaczenia = {k: sekcje_pl[k] for k in klucze_filtru}
        sekcje_istniejace = wczytaj_istniejacy_docelowy(cel)
        if sekcje_istniejace is None:
            print(f"❌ {kod}/{nazwa_pliku}: brak istniejącego pliku docelowego — uruchom najpierw bez --klucz.")
            return False
        if KLUCZ_LEGACY in sekcje_istniejace:
            print(
                f"❌ {kod}/{nazwa_pliku}: docelowy plik w starym schemacie (string tresc).\n"
                f"   Surgical update niemożliwy — uruchom najpierw bez --klucz, żeby przemigrować na dict-schemat."
            )
            return False

    rdzen = nazwa_pliku.rsplit(".", 1)[0]

    # RETRY: detektor budujemy raz na plik (ładowanie modeli lingua jest drogie),
    # reużywamy między sekcjami. sekcje_istniejace jest gwarantowane (retry ⟹
    # surgical ⟹ wczytano docelowy plik wyżej).
    detektor_leakow = None
    if retry:
        import audyt_leakow
        detektor_leakow = audyt_leakow._zbuduj_detektor(kod)

    # Tłumaczenie sekcja-po-sekcji
    swiezy_cache = retry or (input_krytyki is not None)  # oba wymuszają świeże tłumaczenie
    sekcje_przetlumaczone: dict[str, str] = {}
    for klucz, tresc_pl in sekcje_do_tlumaczenia.items():
        # Teza 3: prompt budujemy PER SEKCJĘ z jej treści — bloki szyfrów/akcentów
        # wstrzykiwane tylko gdy sekcja faktycznie ich dotyczy (vs dawny monolit
        # doklejany do wszystkich 68 sekcji).
        prompt_dodatkowy = _zbuduj_prompt_dodatkowy(kod, nazwa_natywna, tresc_pl)
        prompt_sekcji = prompt_dodatkowy
        if retry:
            import audyt_leakow
            istniejaca = (sekcje_istniejace or {}).get(klucz, "")
            leaki = audyt_leakow.wykryj_leaki_w_tekscie(istniejaca, kod, detektor_leakow)
            retry_blok = _zbuduj_retry_blok(leaki, nazwa_natywna)
            if retry_blok:
                prompt_sekcji = (prompt_dodatkowy + "\n\n" + retry_blok).strip()
                fragmenty = sorted({l.fragment.strip() for l in leaki if l.fragment.strip()})
                print(f"♻️  {kod}/{nazwa_pliku} '{klucz}': RETRY z naciskiem na "
                      f"{len(fragmenty)} unikalny/ch leak(ów): {fragmenty[:8]}"
                      f"{' …' if len(fragmenty) > 8 else ''}")
            else:
                print(f"♻️  {kod}/{nazwa_pliku} '{klucz}': RETRY — detektor nie wykrył "
                      f"leaków w istniejącym tłumaczeniu; retłumaczę bez retry-bloku.")
        elif input_krytyki is not None:
            input_blok = _zbuduj_input_blok(input_krytyki.get(klucz, ""))
            if input_blok:
                prompt_sekcji = (prompt_dodatkowy + "\n\n" + input_blok).strip()
                print(f"📨  {kod}/{nazwa_pliku} '{klucz}': INPUT — krytyka recenzenta wstrzyknięta.")
            else:
                print(f"📨  {kod}/{nazwa_pliku} '{klucz}': INPUT — pusta krytyka, retłumaczę bez bloku.")
        ok, tekst = _tlumacz_pojedyncza_sekcje(
            kod, nazwa_pl, klient, nazwa_pliku, rdzen, klucz, tresc_pl,
            dry_run=dry_run, model=model, prompt_dodatkowy=prompt_sekcji,
            retry=swiezy_cache,
        )
        if not ok:
            print(f"❌  {kod}/{nazwa_pliku}: sekcja '{klucz}' nie udała się — NIE zapisuję pliku.")
            return False
        if not dry_run:
            sekcje_przetlumaczone[klucz] = tekst or ""

    if dry_run:
        print(f"    (dry-run) Nie wywołuję API, nie zapisuję {kod}/{nazwa_pliku}.")
        return True

    # Złóż wynikowy dict: SURGICAL = scal z istniejącymi, FULL = same przetłumaczone
    if sekcje_istniejace is not None:
        wynikowy_dict = dict(sekcje_istniejace)
        wynikowy_dict.update(sekcje_przetlumaczone)
    else:
        wynikowy_dict = sekcje_przetlumaczone

    # Decyzja schematu zapisu:
    # * Jeśli to legacy (jeden klucz _legacy) → zapisz jako string (stary schemat).
    # * W przeciwnym razie → zapisz jako dict.
    if list(wynikowy_dict.keys()) == [KLUCZ_LEGACY]:
        tresc_do_zapisu: str | dict[str, str] = wynikowy_dict[KLUCZ_LEGACY]
    else:
        tresc_do_zapisu = wynikowy_dict

    zawartosc_yaml = zbuduj_yaml_wynikowy(
        kod, id_szablonu, tresc_do_zapisu, nazwa_pliku, tryb_draft=tryb_draft,
    )
    cel.parent.mkdir(parents=True, exist_ok=True)
    with open(cel, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(zawartosc_yaml)

    tryb = "SURGICAL" if klucze_filtru else "FULL"
    if tryb_draft:
        tryb += " DRAFT"
    n_sekcji = len(sekcje_przetlumaczone)
    print(
        f"✅  {kod}/{nazwa_pliku}: zapisano {cel.relative_to(ROOT)} "
        f"({tryb}, {n_sekcji} sekcji przetłumaczonych, {len(zawartosc_yaml):,} znaków)."
    )
    return True


def _zbierz_leaki_draftow(
    wytworzone: list[tuple[str, str]],
) -> dict[tuple[str, str], dict]:
    """Post-processor draftów: skan `audyt_leakow` per wytworzony plik.

    Zwraca ``{(kod, plik): {sekcja: [Leak]}}`` (tylko pliki z leakami) do
    doklejenia jako appendix checklisty przeglądu (`przeglad_tlumaczen`).
    Detektor budujemy raz na język (ładowanie modeli lingua jest drogie) i
    reużywamy między plikami. Fail-open — błąd skanu (np. brak `lingua`) NIE
    wywraca buildu draftów; appendix to wygoda dla recenzenta, nie część krytyczna.
    """
    import audyt_leakow
    wynik: dict[tuple[str, str], dict] = {}
    detektory: dict[str, object] = {}
    for kod, nazwa_pliku in wytworzone:
        try:
            detektor = detektory.get(kod)
            if detektor is None:
                detektor = audyt_leakow._zbuduj_detektor(kod)
                detektory[kod] = detektor
            per_sekcja = audyt_leakow.leaki_per_sekcja(kod, nazwa_pliku, detektor)
        except Exception as exc:   # lingua brak / błąd modelu — nie wywracaj buildu
            print(f"⚠️  audyt_leakow pominięty dla {kod}/{nazwa_pliku}: {exc}")
            continue
        if per_sekcja:
            wynik[(kod, nazwa_pliku)] = per_sekcja
    return wynik


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _parsuj_argumenty() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Batchowy autotłumacz dokumentacji manual.yaml na języki docelowe "
            f"({', '.join(MAPA_JEZYKOW)}). Używa tlumacz_ai.py z zamrożeniem "
            "placeholderów przez unikalne tokeny Unicode ⟦i⟧."
        ),
    )
    grupa = parser.add_mutually_exclusive_group(required=True)
    grupa.add_argument(
        "--jezyki",
        type=str,
        default="",
        help=f"Lista kodów ISO oddzielona przecinkami (np. `en,fi`). "
             f"Dozwolone: {', '.join(MAPA_JEZYKOW)}.",
    )
    grupa.add_argument(
        "--wszystkie",
        action="store_true",
        help=f"Tłumacz na wszystkie języki ({', '.join(MAPA_JEZYKOW)}).",
    )
    parser.add_argument(
        "--szablony",
        type=str,
        default="",
        help="CSV nazw szablonów do przetłumaczenia (np. `dictionaries.yaml` "
             "lub bare-name `dictionaries`; rozszerzenie `.yaml` jest "
             "dosztukowywane automatycznie). Pusta wartość = wszystkie szablony "
             "z `dictionaries/pl/gui/dokumentacja/`. Sensowne, gdy część "
             "szablonów ma już aktualne tłumaczenia na dysku i nie chcesz "
             "ponownie spalać API-billa (np. `--szablony dictionaries`, gdy "
             "`manual.yaml` jest już przetłumaczony we wszystkich językach).",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Pomiń SZABLONY, dla których "
             "`dictionaries/<kod>/gui/dokumentacja/<plik>.yaml` już istnieje "
             "(idempotentny rerun na poziomie pojedynczego pliku — gdy dorzucisz "
             "nowy szablon do PL, wystarczy `--wszystkie --skip-existing`, żeby "
             "dotłumaczyć tylko brakujące pozycje bez ponownego API-billingu na "
             "manual.yaml).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Tylko tokenizacja + podgląd mapy placeholderów. Zero wywołań API.",
    )
    parser.add_argument(
        "--model",
        default="gpt-4o",
        help="Model OpenAI do głównego tłumaczenia (domyślnie: gpt-4o).",
    )
    parser.add_argument(
        "--klucz",
        type=str,
        default=None,
        metavar="KLUCZ[,KLUCZ...]",
        help="Tłumacz TYLKO wskazane klucze sekcji (np. `krok_5_vocalizer,krok_5_alarm_nvda_2026`), "
             "reszta pliku zostaje z istniejącego tłumaczenia. "
             "Wymaga, by docelowy `<kod>/gui/dokumentacja/<plik>.yaml` już istniał W NOWYM SCHEMACIE "
             "(dict `tresc:` z sekcjami) — najpierw zrób FULL tłumaczenie bez --klucz, "
             "żeby plik nabrał nowego schematu. Surgical update jest tańszy API-wise: "
             "tłumaczysz np. tylko sekcję Vocalizer (~2 kB) zamiast całego manuala (~68 kB).",
    )
    parser.add_argument(
        "-r", "--retry",
        action="store_true",
        help="Tryb KOREKCJI LEAKÓW. Dla każdej sekcji z --klucz wczytuje ISTNIEJĄCE "
             "tłumaczenie docelowe, wykrywa w nim polskie fragmenty (audyt_leakow: "
             "lingua + kuratorskie terminy) i wstrzykuje je do prompta jako „te "
             "fragmenty zostały po polsku — przetłumacz/odmień je w całości”, po czym "
             "retłumaczy sekcję z PL źródła. Omija cache temp_*.jsonl (świeże "
             "tłumaczenie). Zwykły --klucz NIE naprawia leaków (blind spot LLM) — "
             "ta flaga to analog self-correction z rezyser_ai. WYMAGA --klucz.",
    )
    parser.add_argument(
        "--draft",
        action="store_true",
        help="Tryb ROBOCZY DO PRZEGLĄDU. Zamiast kanonicznego nagłówka „NIE edytuj "
             "ręcznie” wstrzykuje neutralny nagłówek zachęcający do edycji i po "
             "przebiegu emituje checklistę przeglądu halucynacji do "
             "`skrypty/przeglad_docs.md`. Użycie: paczka kontrybucji nowego języka "
             "wysyłana osobie trzeciej / agentowi do recenzji (recenzent bez naszej "
             "konstytucji nie dostaje sprzecznego rozkazu). Pliki lądują w normalnej "
             "ścieżce — po akceptacji regeneruj bez --draft (kanoniczny nagłówek).",
    )
    parser.add_argument(
        "--input",
        action="store_true",
        help="Tryb FEEDBACKU RECENZENTA (osobny workflow od --retry). Parsuje "
             "`skrypty/input.log` (format „### kod/plik/klucz\\n<krytyka>”, ten sam co "
             "output.log), ustala których kluczy dotyczy, sprawdza czy AI generowało dla "
             "nich output w ostatniej turze, i retłumaczy TYLKO te klucze z PL źródła z "
             "wstrzykniętą krytyką recenzenta — BEZ auto-detekcji leaków. Selektor kluczy "
             "bierze z input.log (nie z --klucz). Po przebiegu input.log jest kasowany "
             "(pętla ograniczona). Wyklucza się z --klucz/--retry.",
    )
    args = parser.parse_args()
    if args.klucz and args.skip_existing:
        parser.error("--klucz i --skip-existing wzajemnie się wykluczają "
                     "(--klucz celowo nadpisuje wybrane sekcje w istniejącym pliku).")
    if args.retry and not args.klucz:
        parser.error("--retry wymaga --klucz (CSV sekcji do korekcji) — bez wskazania "
                     "sekcji nie ma czego retłumaczyć z naciskiem na leaki.")
    if args.input and (args.klucz or args.retry or args.skip_existing):
        parser.error("--input to OSOBNY workflow (krytyka z input.log) — nie łącz z "
                     "--klucz/--retry/--skip-existing. Selektor kluczy bierze z input.log.")
    if args.input and not args.szablony:
        parser.error("--input wymaga --szablony <plik> (np. `--szablony tales`), żeby "
                     "wiedzieć z którego pliku brać sekcje wskazane w input.log.")
    return args


def _filtruj_szablony(
    wszystkie: list[tuple[str, str, str]],
    wybor_csv: str,
) -> list[tuple[str, str, str]]:
    """Zostawia tylko te szablony PL, których nazwy figurują w ``wybor_csv``.

    Pusty CSV = brak filtrowania (zachowanie domyślne — wszystkie szablony).
    Akceptuje zarówno pełne nazwy plików (``manual.yaml``), jak i bare-names
    (``manual``); rozszerzenie ``.yaml`` jest dosztukowywane automatycznie.

    Twardy SystemExit, gdy CSV referuje do nieistniejącego szablonu — lepiej
    wcześnie wywalić niż cicho zrobić nic, bo użytkownik mógł pomylić nazwę.
    """
    if not wybor_csv.strip():
        return wszystkie

    wybrane: set[str] = set()
    for pozycja in wybor_csv.split(","):
        nazwa = pozycja.strip()
        if not nazwa:
            continue
        if not nazwa.endswith((".yaml", ".yml")):
            nazwa += ".yaml"
        wybrane.add(nazwa)

    dostepne = {s[0] for s in wszystkie}
    nieznane = sorted(wybrane - dostepne)
    if nieznane:
        raise SystemExit(
            f"❌ Nieznane szablony: {nieznane}.\n"
            f"   Dostępne w dictionaries/{KOD_ZRODLOWY}/{FOLDER_GUI}/{FOLDER_DOKUMENTACJA}/: "
            f"{sorted(dostepne)}"
        )

    return [s for s in wszystkie if s[0] in wybrane]


def _wybierz_jezyki(args: argparse.Namespace) -> list[str]:
    if args.wszystkie:
        return list(MAPA_JEZYKOW.keys())
    kody = [k.strip() for k in args.jezyki.split(",") if k.strip()]
    nieznane = [k for k in kody if k not in MAPA_JEZYKOW]
    if nieznane:
        raise SystemExit(
            f"❌ Nieznane kody języków: {', '.join(nieznane)}.\n"
            f"   Dozwolone: {', '.join(MAPA_JEZYKOW)}."
        )
    return kody


def _zainicjuj_klienta_openai() -> Any:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise SystemExit(
            "❌ Brak modułu `openai`. Instalacja (venv projektu):\n"
            "   .venv/Scripts/pip install openai"
        ) from exc

    # Ładujemy `golden_key.env` z roota projektu — ten sam plik, którego
    # używa GUI (`gui_poliglota.py`, `gui_rezyser.py`, `main.py`).
    # Dzięki temu skrypt CLI nie wymaga ręcznego eksportowania zmiennych
    # środowiskowych — działa od razu, jeśli System Check w GUI przechodzi.
    try:
        from dotenv import load_dotenv
        env_path = ROOT / "golden_key.env"
        if env_path.is_file():
            load_dotenv(env_path)
    except ImportError:
        pass   # python-dotenv jest w requirements; fallback i tak ma sens

    klucz = os.environ.get("OPENAI_API_KEY")
    if not klucz or klucz == "TUTAJ_WKLEJ_SWOJ_KLUCZ":
        raise SystemExit(
            "❌ Brak prawidłowego OPENAI_API_KEY.\n"
            "   Sprawdź `golden_key.env` w katalogu projektu (ten sam plik,\n"
            "   którego używa GUI — System Check w trybie Reżysera)."
        )
    return OpenAI(api_key=klucz)


def main() -> int:
    args = _parsuj_argumenty()
    kody = _wybierz_jezyki(args)

    try:
        wszystkie_szablony = wczytaj_szablony_pl()
    except (FileNotFoundError, ValueError) as exc:
        print(f"❌ {exc}")
        return 2

    szablony = _filtruj_szablony(wszystkie_szablony, args.szablony)
    if not szablony:
        print("❌ Filtr `--szablony` zostawił pustą listę — nic do roboty.")
        return 2

    pelna_lista = ", ".join(s[0] for s in wszystkie_szablony)
    wybrana_lista = ", ".join(s[0] for s in szablony)
    if len(szablony) == len(wszystkie_szablony):
        print(f"ℹ️  Szablony PL do przetłumaczenia: {wybrana_lista} (razem {len(szablony)}).")
    else:
        print(
            f"ℹ️  Szablony PL: filtr `--szablony` wybrał {wybrana_lista} "
            f"({len(szablony)}/{len(wszystkie_szablony)} dostępnych: {pelna_lista})."
        )

    klient: Any = None if args.dry_run else _zainicjuj_klienta_openai()

    # 13.4: import lazy — `core_poliglota` dorzuca docx/num2words. Skrypt
    # uruchamiany w czystym kontekście CLI nie powinien płacić za to przy
    # imporcie modułu, tylko gdy faktycznie idzie tłumaczyć.
    from core_poliglota import natywna_nazwa

    # Log lifecycle: output.log świeży na każdy run (meta dopisywane per klucz).
    # W trybie --input czytamy POPRZEDNI output.log (weryfikacja prior-output)
    # PRZED skasowaniem; potem kasujemy, by zebrać nowe meta tego runu.
    prior_output_keys: set[str] = set()
    wpisy_input: dict[str, str] = {}
    if args.input:
        wpisy_input = parsuj_input_log(INPUT_LOG)
        if not wpisy_input:
            print(f"❌ --input: {INPUT_LOG} pusty lub nie istnieje — nic do roboty.")
            return 2
        prior_output_keys = set(parsuj_input_log(OUTPUT_LOG).keys())  # ten sam format
        print(f"📨 Tryb --input: {len(wpisy_input)} wpis(ów) krytyki z {INPUT_LOG.name}; "
              f"poprzedni output.log: {len(prior_output_keys)} kluczy.")
    if not args.dry_run:
        try:
            OUTPUT_LOG.unlink()
        except OSError:
            pass

    sukcesy: list[str] = []
    porazki: list[str] = []
    wytworzone_drafty: list[tuple[str, str]] = []

    klucze_filtru: list[str] | None = None
    if args.klucz:
        klucze_filtru = [k.strip() for k in args.klucz.split(",") if k.strip()]
        if not klucze_filtru:
            print("❌ Flag --klucz podany, ale CSV jest pusty.")
            return 2
        print(f"🔎 Filtr --klucz ({len(klucze_filtru)} klucz/y): {klucze_filtru}")
        print(f"   Surgical update — pozostałe sekcje zostaną z istniejących tłumaczeń.")
        if args.retry:
            print(f"♻️  Tryb --retry: korekcja leaków (audyt_leakow → retry-blok → "
                  f"retłumaczenie z PL, świeży cache).")

    for kod in kody:
        nazwa_pl = MAPA_JEZYKOW[kod]
        nazwa_natywna = natywna_nazwa(kod)
        print(f"\n========== {kod.upper()} ({nazwa_pl} / {nazwa_natywna}) ==========")
        wszystko_ok = True
        for nazwa_pliku, id_szablonu, sekcje_pl in szablony:
            input_krytyki: dict[str, str] | None = None
            kl_filtru = klucze_filtru
            if args.input:
                prefix = f"{kod}/{nazwa_pliku}/"
                input_krytyki = {h[len(prefix):]: c for h, c in wpisy_input.items()
                                 if h.startswith(prefix)}
                if not input_krytyki:
                    continue   # input.log nie ma wpisów dla tego (kod, plik)
                kl_filtru = list(input_krytyki.keys())
                for k in kl_filtru:
                    if f"{prefix}{k}" not in prior_output_keys:
                        print(f"⚠️  {kod}/{nazwa_pliku} '{k}': brak w poprzednim output.log "
                              f"(AI nie generowało dla niego ostatnio) — krytyka mimo to zastosowana.")
            ok = tlumacz_szablon(
                kod,
                nazwa_pl,
                nazwa_natywna,
                klient,
                nazwa_pliku,
                id_szablonu,
                sekcje_pl,
                skip_existing=args.skip_existing,
                dry_run=args.dry_run,
                model=args.model,
                klucze_filtru=kl_filtru,
                retry=args.retry,
                input_krytyki=input_krytyki,
                tryb_draft=args.draft,
            )
            if not ok:
                wszystko_ok = False
            elif args.draft and not args.dry_run:
                wytworzone_drafty.append((kod, nazwa_pliku))
        (sukcesy if wszystko_ok else porazki).append(kod)

    # --input: skonsumowany input.log kasujemy (pętla ograniczona — bez kotka-myszki;
    # output.log zawiera już NOWE meta tego runu do ewentualnej kolejnej rundy).
    if args.input and not args.dry_run:
        try:
            INPUT_LOG.unlink()
            print(f"\n🧹 input.log skonsumowany i usunięty. Nowe meta w output.log "
                  f"(kolejna runda: przeczytaj, dopisz krytykę, --input ponownie).")
        except OSError:
            pass

    if args.draft and not args.dry_run:
        # Post-processor: detektor PL-leaków na świeżych draftach — funnel dla
        # recenzenta (zwł. nie-polskojęzycznego), doklejany do checklisty.
        print("\n🔎 DRAFT: skan audyt_leakow na wytworzonych draftach…")
        leaki_per_plik = _zbierz_leaki_draftow(wytworzone_drafty)
        sciezka_prompt = przeglad_tlumaczen.zapisz_prompt_przegladu(
            "buduj_wielojezyczne_docs.py", wytworzone_drafty, ROOT,
            leaki_per_plik=leaki_per_plik,
        )
        if sciezka_prompt is not None:
            ile_leakow = sum(
                len(v) for per in leaki_per_plik.values() for v in per.values()
            )
            print(f"📋 DRAFT: checklista przeglądu zapisana → "
                  f"{sciezka_prompt.relative_to(ROOT)} "
                  f"({len(wytworzone_drafty)} plik(ów) do recenzji, "
                  f"{ile_leakow} kandydat(ów) na leak).")

    print("\n========== PODSUMOWANIE ==========")
    print(f"✅ Sukces: {len(sukcesy)}/{len(kody)}  ({', '.join(sukcesy) or '—'})")
    if porazki:
        print(f"❌ Porażki (≥1 szablon nie powiódł się): {', '.join(porazki)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
