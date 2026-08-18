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

AUDYT PRZYKŁADÓW (`--audyt`, od v18.20, zero API): docsowa odmiana bramki G6
z brata akcentów — każda para „X → Y" w `gui/dokumentacja/*.yaml` liczona
FAKTYCZNYM silnikiem (szyfry przez niezmienniki algorytmu, akcenty przez
tablicę `zamiany`). Powstała, bo v18.19 znalazł RĘCZNIE, że akapit
o Samogłoskowcu kłamie w ośmiu podręcznikach, a bramki plików REGUŁ tego nie
widzą — to inny folder. Operację rozstrzygamy w paczce `pl` i przenosimy po
POZYCJI punktu listy; szczegóły i kalibracja przy sekcji „AUDYT PRZYKŁADÓW".

Użycie:
  python buduj_wielojezyczne_docs.py --audyt                      # 9 paczek, zero API
  python buduj_wielojezyczne_docs.py --audyt --jezyki pl,de
  python buduj_wielojezyczne_docs.py --audyt --raport skrypty/audyt.md
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

Wymaga: `ANTHROPIC_API_KEY` w środowisku (to samo konto co GUI Poliglota).
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

import core_llm as cl
import przeglad_tlumaczen
import tlumacz_bramki
from tlumacz_ai import sciezka_cache_tlumaczenia, tlumacz_dlugi_tekst


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
# Mini-prompt: skrótowce dla języka BEZ ręcznej tabeli (od 2026-06-16)
# ---------------------------------------------------------------------------
# Kontrybutor dodający język nie zna polskiego rdzenia i nie dopisze tabeli
# `ABBREV_BY_LANG`. Zamiast zostawiać blok ODWRACACZ bez skrótowców (polskie
# m.in./np. leakują do tłumaczenia), generujemy 5 typowych skrótowców języka
# docelowego JEDNYM tanim wywołaniem LLM — wynik wpada w ten sam slot
# `{abbreviation_list}` co tabela, więc reszta bloku (w tym recompute „.nim")
# działa bez zmian. Cache per kod: jedno wywołanie na język na cały przebieg.
_CACHE_SKROTOWCE_LLM: dict[str, list[tuple[str, str]]] = {}

# Usuwa wiodący numer/punktor listy ("1. ", "2) ", "- ", "* ") BEZ ruszania kropek
# wewnątrz samego skrótowca (np. „e.g." zaczyna się od litery → nie pasuje;
# numeracja wymaga `.`/`)`, punktor wymaga spacji po znaku — więc „- " łapiemy,
# a myślnik wewnątrz „c.-à-d." już nie, bo nie jest na początku linii).
_RE_PUNKTOR_LISTY = re.compile(r"^\s*(?:\d+[.)]\s*|[-*•]\s+)")


def _wygeneruj_skrotowce_llm(
    klient: Any, kod: str, nazwa_natywna: str, model: str,
) -> list[tuple[str, str]]:
    """Generuje ≤5 typowych skrótowców języka docelowego (gdy brak `ABBREV_BY_LANG`).

    Zwraca listę (skrót, rozwinięcie) — format identyczny z wpisem tabeli. Pusta
    lista przy błędzie sieci / niezdatnym formacie → wołający pominie blok
    ODWRACACZ (degradacja jak sprzed mini-promptu, nie crash). Prompt po angielsku
    (spójnie z resztą promptów narzędzia); `temperature=0` dla determinizmu.
    """
    prompt = (
        f"List exactly 5 of the most common WRITTEN abbreviations in {nazwa_natywna} "
        f"(ISO language code: {kod}) that are normally written WITH periods — "
        f"analogous to English 'e.g.', 'i.e.', 'etc.'. Context: a text-reversal cipher "
        f"expands such dotted abbreviations before reversing a sentence, so they must be "
        f"real, period-bearing abbreviations of {nazwa_natywna}.\n"
        f"Output EXACTLY 5 lines, each STRICTLY in the format:\n"
        f"abbreviation | full expansion\n"
        f"No numbering, no commentary, no blank lines. If {nazwa_natywna} rarely uses "
        f"dotted abbreviations, give the closest common written shortenings anyway."
    )
    try:
        surowa_raw, _stop = cl.wywolaj_llm(
            klient,
            model=model,
            system="",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=256,
            temperature=0.0,
            timeout=60.0,
        )
        surowa = surowa_raw.strip()
    except Exception as exc:  # noqa: BLE001 — fail-soft: brak skrótowców → blok pominięty
        print(f"⚠️  {kod}: LLM abbreviation generation failed ({exc}); "
              f"the Odwracacz block will be skipped.")
        return []

    pary: list[tuple[str, str]] = []
    widziane: set[str] = set()
    for linia in surowa.splitlines():
        if "|" not in linia:
            continue
        lewa, prawa = linia.split("|", 1)
        skr = _RE_PUNKTOR_LISTY.sub("", lewa).strip().strip('"').strip()
        exp = prawa.strip().strip('"').strip()
        # Odrzuć degeneraty: model dla języka BEZ kropkowanych skrótowców (np.
        # chiński logograficzny) zwraca „暂无此类缩写 | 暂无此类缩写" (brak/echo) —
        # wstrzyknięcie tego zaśmieciłoby manual. skrót==rozwinięcie lub duplikat
        # skrótu = bezużyteczne. 0 czystych par ⟹ wołający pominie blok ODWRACACZ.
        if not skr or not exp or skr == exp or skr in widziane:
            continue
        widziane.add(skr)
        pary.append((skr, exp))
    return pary[:5]


def _skrotowce_dla_jezyka(
    klient: Any, kod: str, nazwa_natywna: str, model: str,
) -> list[tuple[str, str]]:
    """Skrótowce dla języka: ręczna tabela `ABBREV_BY_LANG`, a gdy brak — generacja LLM (cache)."""
    tabela = ABBREV_BY_LANG.get(kod)
    if tabela is not None:
        return tabela
    if kod in _CACHE_SKROTOWCE_LLM:
        return _CACHE_SKROTOWCE_LLM[kod]
    wynik = _wygeneruj_skrotowce_llm(klient, kod, nazwa_natywna, model)
    if wynik:
        podglad = ", ".join(f'{s}→{e}' for s, e in wynik)
        print(f"🔤 {kod}: brak tabeli ABBREV_BY_LANG — wygenerowano {len(wynik)} "
              f"skrótowców przez LLM: {podglad}")
    _CACHE_SKROTOWCE_LLM[kod] = wynik
    return wynik


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

The env-key placeholder PASTE_YOUR_KEY_HERE is a literal token the app writes
verbatim into golden_key.env (ANTHROPIC_API_KEY=PASTE_YOUR_KEY_HERE /
OPENAI_API_KEY=PASTE_YOUR_KEY_HERE), identical in every UI language. KEEP it 1:1 —
do NOT translate it into a {nazwa_natywna} phrase for "paste your key here"; the reader
must see the exact string that exists in the file.

### Frozen markers ⟦i⟧
Every ⟦N⟧ marker is a frozen placeholder. Copy character-for-character; do not
translate, do not renumber, do not insert new ones.

### Markdown structure (since v18.8 the templates are Markdown rendered to HTML)
Preserve the Markdown skeleton EXACTLY:
  * a leading "# " / "## " heading marker stays at the start of the same line
    (translate the heading TEXT, keep the marker and its level),
  * backtick code spans (`like_this`) keep their backticks; their inner text is
    a technical literal covered by the rules above — copy it 1:1,
  * do not introduce new heading markers, bold/italic emphasis or code spans
    that the source section does not have.\
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
# Model recenzji (od refaktoru 18.x): KAŻDE tłumaczenie ląduje jako DRAFT z
# checklistą `przeglad_tlumaczen` — bez pętli feedbacku LLM. Dawne tryby
# --input/--retry oraz maszyneria META (`===META===` + output.log) ZNIESIONE:
# gryzły się z chunkowaniem (wiele markerów META po podziale sekcji na bloki)
# i z modelami openai_compat. Recenzent poprawia draft ręcznie → `--finalizuj`.
# ---------------------------------------------------------------------------


def _zbuduj_prompt_dodatkowy(
    kod: str, nazwa_natywna: str, tresc_sekcji: str = "",
    abbrev: list[tuple[str, str]] | None = None,
) -> str:
    """Buduje custom system-prompt dla pary (kod_docelowy, nazwa_natywna).

    Teza 3 (2026-06-16): bloki AKCENTY/ODWRACACZ/TYPOGLIKEMIA wstrzykiwane
    WARUNKOWO — tylko gdy `tresc_sekcji` faktycznie zawiera dany artefakt
    (lista akcentów / ".nim" / Typoglikemia). CORE (kontekst + literały) zawsze.
    `tresc_sekcji=""` (wywołanie bez treści, np. ad-hoc) = zachowawczy fallback:
    wstrzykuje WSZYSTKIE bloki (stare zachowanie monolitu sprzed tezy 3).

    Fix bramki (2026-06-16): brak skrótowców blokuje WYŁĄCZNIE blok ODWRACACZ
    (jedyny, który potrzebuje `{abbreviation_list}`) — NIE cały prompt. Do tej
    pory `if not abbrev: return ""` zerowało też CORE-kontekst, akcenty,
    Typoglikemię i ochronę literałów, choć te od skrótowców nie zależą.

    `abbrev`: skrótowce do bloku ODWRACACZ. ``None`` (wywołanie ad-hoc) → fallback
    na ręczną tabelę `ABBREV_BY_LANG[kod]`. Wołający z pętli tłumaczenia podaje
    listę rozwiązaną przez `_skrotowce_dla_jezyka` — tabela LUB skrótowce
    wygenerowane mini-promptem LLM (język kontrybutora bez wpisu w tabeli).
    Pusta lista/``None`` bez tabeli → blok ODWRACACZ pominięty.
    """
    if abbrev is None:
        abbrev = ABBREV_BY_LANG.get(kod)

    nieznana = not tresc_sekcji  # brak treści ⟹ nie wiemy, więc wstrzyknij wszystko
    czesci = [_PROMPT_CORE_KONTEKST.format(kod=kod, nazwa_natywna=nazwa_natywna)]

    if nieznana or _sekcja_ma_liste_akcentow(tresc_sekcji):
        czesci.append(_PROMPT_AKCENTY.format(nazwa_natywna=nazwa_natywna))
    # ODWRACACZ wymaga tabeli skrótowców — bez `abbrev` blok pomijamy (nie da się
    # zbudować {abbreviation_list}); reszta wytycznych leci niezależnie.
    if abbrev and (nieznana or _sekcja_ma_odwracacz(tresc_sekcji)):
        bullety = "\n".join(f'     - "{skr}" → "{exp}"' for skr, exp in abbrev)
        czesci.append(_PROMPT_ODWRACACZ.format(
            nazwa_natywna=nazwa_natywna, abbreviation_list=bullety,
        ))
    if nieznana or _sekcja_ma_typoglikemie(tresc_sekcji):
        czesci.append(_PROMPT_TYPOGLIKEMIA.format(nazwa_natywna=nazwa_natywna))

    # Anty-meta-skip (v18.16, wspólny `tlumacz_bramki`) — BEZWARUNKOWO, wbrew
    # oszczędności teza-3. Powód: ryzyko nie ogranicza się do sekcji opisujących
    # prompty. Manual jest pisany w trybie rozkazującym do CZŁOWIEKA („wpisz klucz
    # i naciśnij…"), a model tłumaczący potrafi się w takim tekście rozpoznać jako
    # adresat i zacząć go wykonywać/odpowiadać — dokładnie to zdarzyło się
    # 2026-05-19 na `opowiesci/baza.yaml` (is/ru: pierwsza sekcja wracała po
    # polsku). Blok waży ~180 tokenów, monolit sprzed teza-3 ważył 1 286.
    czesci.append(tlumacz_bramki.blok_anty_meta_skip(przewaga_promptow=False))

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
    # UWAGA (18.12): opis formatu CELOWO bez literalnych przykładów tokenów —
    # claude-sonnet-5 „zachowywał" przykładowe markery z instrukcji, wstawiając
    # je do tłumaczenia (walidacja parzystości ubijała sekcję).
    "Poniższy tekst zawiera markery: liczba ujęta w podwójne nawiasy\n"
    "matematyczne (znaki U+27E6 i U+27E7). To są zamrożone placeholdery\n"
    "programowe. Skopiuj je do odpowiedzi DOSŁOWNIE, znak w znak — nie\n"
    "zmieniaj cyfr, nie zmieniaj nawiasów, nie tłumacz. Każdy marker musi\n"
    "wystąpić w odpowiedzi dokładnie tyle samo razy, co w oryginale (skrypt\n"
    "nadrzędny weryfikuje parzystość po zakończeniu). NIE dodawaj żadnych\n"
    "markerów, których nie ma w oryginale.\n"
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


# Kształt linii markera w DOWOLNYM języku: cała linia jest jednym nawiasem
# kwadratowym z tekstem wersalikowym. Nasz prefix to dokładnie dwie takie linie
# (otwarcie + zamknięcie). Próg 15 znaków trzyma z daleka krótkie tagi-kotwice
# (`[CEL SCENY]`, `[ODRZUCENIE_AI]`), gdyby kiedyś stanęły w osobnej linii.
_RE_LINIA_MARKERA = re.compile(r"^\s*\[([^\]\n]{15,})\]\s*$")


def _czy_linia_markera(linia: str) -> bool:
    m = _RE_LINIA_MARKERA.match(linia)
    return bool(m) and m.group(1) == m.group(1).upper()


def utnij_prefix_z_wyniku(wynik: str) -> str:
    """Usuwa prefix-instrukcję z odpowiedzi LLM (jeśli nie usunął sam).

    Ścieżka podstawowa: szukamy polskiego :data:`MARKER_KONCA_PREFIXU`.

    Ścieżka awaryjna (v18.16): marker jest polską PROZĄ, więc model potrafi go
    PRZETŁUMACZYĆ — wtedy `find` zwraca -1, dawna wersja uznawała to za „model
    posłuchał i usunął blok" i wpuszczała całą instrukcję do szablonu. Tak
    powstał osad w `es/dictionaries::co_to_tryb_rezysera`: dwie linie
    „[INSTRUCCIÓN TÉCNICA…]" / „[FIN DE LA INSTRUCCIÓN…]" pojechały do wydanej
    dokumentacji i renderowały się w `docs/dictionaries.es.html`. Znalazła to
    dopiero bramka odcisku struktury (`tlumacz_bramki`, reguła „tłumaczenie
    zaczyna się artefaktem"). Bramka zostaje jako siatka bezpieczeństwa, ale
    ubijanie opłaconej sekcji jest gorsze niż zdjęcie dwóch linii tutaj.
    """
    idx = wynik.find(MARKER_KONCA_PREFIXU)
    if idx != -1:
        return wynik[idx + len(MARKER_KONCA_PREFIXU):].lstrip()

    linie = wynik.lstrip("\n").split("\n")
    zdjete = 0
    while linie and zdjete < 2 and _czy_linia_markera(linie[0]):
        linie.pop(0)
        zdjete += 1
    if zdjete:
        print(f"⚠️  Model PRZETŁUMACZYŁ blok instrukcji technicznej zamiast go "
              f"usunąć — zdjęto {zdjete} wiodące linie markera.")
    return "\n".join(linie).lstrip()


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


def _kanoniczny_naglowek(kod_jezyka: str, nazwa_pliku: str) -> str:
    """Kanoniczny nagłówek „NIE edytuj ręcznie" dla wynikowego docs-YAML.

    Wydzielony z :func:`zbuduj_yaml_wynikowy`, żeby tryb ``--finalizuj`` mógł
    podmienić nagłówek draftu na ten BEZ ponownego tłumaczenia (jedno źródło
    prawdy dla brzmienia nagłówka).
    """
    sciezka_rel = f"dictionaries/{kod_jezyka}/gui/dokumentacja/{nazwa_pliku}"
    zrodlo_rel = f"dictionaries/{KOD_ZRODLOWY}/gui/dokumentacja/{nazwa_pliku}"
    return (
        "# =============================================================================\n"
        f"# {sciezka_rel}\n"
        "#\n"
        "# Plik wygenerowany automatycznie przez buduj_wielojezyczne_docs.py\n"
        f"# ze źródła {zrodlo_rel}\n"
        f"# (język bazowy PL, wersja 13.x). {przeglad_tlumaczen.MARKER_KANONICZNY} — zmiany wprowadzaj\n"
        "# w pliku źródłowym PL i uruchom ponownie skrypt tłumacza.\n"
        "#\n"
        "# Silnik: Anthropic Claude (tlumacz_ai.py). Placeholdery {klucz.zagniezdzony}\n"
        "# zostały zamrożone tokenami ⟦i⟧ na czas tłumaczenia i odtworzone 1:1\n"
        "# po weryfikacji parzystości multisetu markerów.\n"
        "# =============================================================================\n"
        "\n"
    )


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
        naglowek = _kanoniczny_naglowek(kod_jezyka, nazwa_pliku)

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
        raise FileNotFoundError(f"Missing PL source folder: {folder}")

    szablony: list[tuple[str, str, dict[str, str]]] = []
    for plik in sorted(folder.glob("*.yaml")):
        with open(plik, "r", encoding="utf-8") as fh:
            dane = yaml.safe_load(fh)
        if not isinstance(dane, dict):
            print(f"⚠️  Skipping {plik.name}: does not parse into a YAML dictionary.")
            continue
        id_szablonu = dane.get("id")
        if not isinstance(id_szablonu, str):
            print(f"⚠️  Skipping {plik.name}: missing string field `id`.")
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
                    print(f"⚠️  {plik.name}: section '{k}' is not a string — skipping.")
            if not sekcje:
                print(f"⚠️  Skipping {plik.name}: dict `tresc` has no string sections.")
                continue
        else:
            print(f"⚠️  Skipping {plik.name}: `tresc` must be a string or a dict.")
            continue
        szablony.append((plik.name, id_szablonu, sekcje))

    if not szablony:
        raise ValueError(
            f"Folder {folder} contains no valid *.yaml template."
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
def _cache_key_sekcji(rdzen: str, klucz_sekcji: str, kod: str) -> str:
    """Klucz cache'u wznawiania dla jednej sekcji (single source of truth).

    Używany i przy tłumaczeniu, i przy sprzątaniu cache'ów po udanym zapisie
    pliku (18.9) — dlatego wydzielony, żeby oba miejsca nie mogły się rozjechać.
    """
    if klucz_sekcji != KLUCZ_LEGACY:
        return f"{rdzen}_{klucz_sekcji}_{KOD_ZRODLOWY}_to_{kod}"
    return f"{rdzen}_{KOD_ZRODLOWY}_to_{kod}"


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

    # Sekcja bez placeholderów → BEZ prefix-instrukcji o markerach. Empiryczne
    # (18.12, claude-sonnet-5): przy zerze tokenów w źródle model potrafił
    # „zachować" przykładowe ⟦0⟧/⟦12⟧/⟦47⟧ z samej instrukcji, wstawiając je
    # do tłumaczenia — walidacja parzystości ubijała sekcję deterministycznie.
    payload = (PREFIX_INSTRUKCJA + tresc_tok) if liczba_ph else tresc_tok
    blad_kryt: dict[str, Any] = {"msg": None, "partial": None}
    cache_key = _cache_key_sekcji(rdzen, klucz_sekcji, kod)
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
        prompt_dodatkowy=prompt_dodatkowy,
        # 18.9: cache sekcji NIE ginie po jej sukcesie — plik wynikowy powstaje
        # dopiero po WSZYSTKICH sekcjach, więc błąd sekcji 40/68 kasował dotąd
        # 39 opłaconych cache'ów i rerun płacił za nie ponownie. Sprzątamy je
        # w `tlumacz_szablon` dopiero po faktycznym zapisie pliku.
        zachowaj_cache=True,
        # Domyślne chunkowanie (~2 500 tok/blok): duża sekcja może rozpaść się
        # na wiele bloków — bezpieczne, bo nie ma już META, której wielokrotny
        # marker po podziale psułby sklejkę (dawny override 4 000 wymuszał
        # „sekcja = jeden blok" wyłącznie pod META; zniesiony razem z META).
    )
    if wynik is None:
        komunikat = blad_kryt["msg"] or "unknown error from the tlumacz_ai.py engine"
        print(f"❌  {kod}/{nazwa_pliku}{sufiks}: translation aborted.\n    {komunikat.splitlines()[0]}")
        return False, None

    tekst_wy = utnij_prefix_z_wyniku(wynik.tekst)
    ok, problemy = sprawdz_parzystosc(tresc_tok, tekst_wy)
    if not ok:
        print(f"❌  {kod}/{nazwa_pliku}{sufiks}: BROKEN parity of ⟦i⟧ markers.")
        for diag in problemy[:10]:
            print(f"     {diag}")
        if len(problemy) > 10:
            print(f"     ... (+{len(problemy) - 10} more)")
        return False, None

    # Odcisk struktury (v18.16) — druga bramka tej samej klasy co parzystość, tylko
    # na KSZTAŁCIE: szablony docs są Markdownem od v18.8, więc liczba nagłówków
    # `#`/`##` i punktów numerowanych jest kontraktem (pilnuje jej też renderer).
    # Model, który zamiast przetłumaczyć sekcję WYKONAŁ jej instrukcje albo ją
    # streścił, gubi ten szkielet — a parzystość ⟦i⟧ tego nie widzi.
    # TWARDE naruszenia ubijają sekcję; MIĘKKIE (pogrubienia, liczba linii,
    # stosunek długości) tylko ostrzegają: w prozie manuala przełamanie akapitu
    # i dłuższy niemiecki są legalne.
    twarde, miekkie = tlumacz_bramki.waliduj_odcisk(tresc_tok, tekst_wy)
    if twarde:
        print(f"❌  {kod}/{nazwa_pliku}{sufiks}: BROKEN structural fingerprint "
              f"(the model may have executed the text instead of translating it).")
        for diag in twarde:
            print(f"     {diag}")
        return False, None
    if miekkie:
        print(f"⚠️  {kod}/{nazwa_pliku}{sufiks}: shape drift (review, not blocking):")
        for diag in miekkie:
            print(f"     {diag}")

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

    # Status finalizacji (od refaktoru 18.x): KAŻDE tłumaczenie — pełne ORAZ
    # chirurgiczne (--klucz) — ZAWSZE ląduje jako draft. Świeży maszynowy przekład
    # (choćby jednej sekcji) wymaga recenzji halucynacji; kanoniczny nagłówek
    # zdobywa się WYŁĄCZNIE przez --finalizuj po przeglądzie wg checklisty.
    tryb_draft = True

    # SURGICAL: filtruj sekcje + wczytaj istniejący plik docelowy do scalenia
    sekcje_do_tlumaczenia: dict[str, str] = sekcje_pl
    sekcje_istniejace: dict[str, str] | None = None
    if klucze_filtru is not None:
        nieznane = [k for k in klucze_filtru if k not in sekcje_pl]
        if nieznane:
            print(f"❌ {kod}/{nazwa_pliku}: unknown keys in PL: {nieznane}")
            print(f"   Available PL keys: {sorted(sekcje_pl.keys())}")
            return False
        sekcje_do_tlumaczenia = {k: sekcje_pl[k] for k in klucze_filtru}
        sekcje_istniejace = wczytaj_istniejacy_docelowy(cel)
        if sekcje_istniejace is None:
            print(f"❌ {kod}/{nazwa_pliku}: no existing target file — run first without --klucz.")
            return False
        if KLUCZ_LEGACY in sekcje_istniejace:
            print(
                f"❌ {kod}/{nazwa_pliku}: target file in the old schema (string tresc).\n"
                f"   Surgical update is impossible — run first without --klucz to migrate to the dict schema."
            )
            return False

    rdzen = nazwa_pliku.rsplit(".", 1)[0]

    # Skrótowce Odwracacza: ręczna tabela ABBREV_BY_LANG, a gdy jej brak (język
    # kontrybutora bez polskiego rdzenia) — generacja LLM (mini-prompt, raz na
    # język, cache). Leniwie: tylko gdy któraś tłumaczona sekcja faktycznie zawiera
    # Odwracacz (artefakt ".nim") i nie ma tabeli. dry_run: zero API → fallback do
    # tabeli (None ⟹ brak bloku), bez generacji.
    abbrev = ABBREV_BY_LANG.get(kod)
    if (
        abbrev is None
        and not dry_run
        and any(_sekcja_ma_odwracacz(t) for t in sekcje_do_tlumaczenia.values())
    ):
        abbrev = _skrotowce_dla_jezyka(klient, kod, nazwa_natywna, model)

    # Tłumaczenie sekcja-po-sekcji
    sekcje_przetlumaczone: dict[str, str] = {}
    for klucz, tresc_pl in sekcje_do_tlumaczenia.items():
        # Teza 3: prompt budujemy PER SEKCJĘ z jej treści — bloki szyfrów/akcentów
        # wstrzykiwane tylko gdy sekcja faktycznie ich dotyczy (vs dawny monolit
        # doklejany do wszystkich 68 sekcji). `abbrev` rozwiązane wyżej (tabela
        # albo skrótowce z mini-promptu LLM) — steruje blokiem ODWRACACZ.
        prompt_sekcji = _zbuduj_prompt_dodatkowy(kod, nazwa_natywna, tresc_pl, abbrev=abbrev)
        ok, tekst = _tlumacz_pojedyncza_sekcje(
            kod, nazwa_pl, klient, nazwa_pliku, rdzen, klucz, tresc_pl,
            dry_run=dry_run, model=model, prompt_dodatkowy=prompt_sekcji,
        )
        if not ok:
            print(f"❌  {kod}/{nazwa_pliku}: section '{klucz}' failed — NOT writing the file.")
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

    # 18.9: DOPIERO teraz — po fizycznym zapisie pliku — kasujemy cache'e
    # wznawiania wszystkich sekcji (tłumaczone były z `zachowaj_cache=True`).
    # Przerwanie w połowie zostawia je na dysku, więc rerun wznawia za darmo.
    for klucz_sekcji in sekcje_przetlumaczone:
        sciezka_cache = sciezka_cache_tlumaczenia(
            str(RUNTIME_DIR), _cache_key_sekcji(rdzen, klucz_sekcji, kod), nazwa_pl,
        )
        try:
            os.remove(sciezka_cache)
        except OSError:
            pass   # brak pliku = nic do sprzątania (np. sekcja z cache'u wznowiona)

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
            print(f"⚠️  audyt_leakow skipped for {kod}/{nazwa_pliku}: {exc}")
            continue
        if per_sekcja:
            wynik[(kod, nazwa_pliku)] = per_sekcja
    return wynik


# ---------------------------------------------------------------------------
# --finalizuj: lokalna podmiana nagłówka DRAFT → kanoniczny (zero API)
# ---------------------------------------------------------------------------
def _rozdziel_naglowek(yaml_str: str) -> tuple[list[str], str]:
    """Dzieli zawartość YAML na (linie_nagłówka_komentarza, reszta_bez_separatora).

    Nagłówek = ciągły blok wiodących linii `#` + (opcjonalnie) jedna pusta linia
    separatora. Body docs (`id:` / `tresc: |`) nie zawiera komentarzy inline,
    więc cięcie jest bezpieczne. Reużywa tej samej logiki co `podmien_top_comment`
    w builderze UI.
    """
    linie = yaml_str.split("\n")
    i = 0
    while i < len(linie) and linie[i].lstrip().startswith("#"):
        i += 1
    naglowek = linie[:i]
    if i < len(linie) and linie[i].strip() == "":
        i += 1
    return naglowek, "\n".join(linie[i:])


def finalizuj_naglowek_docs(cel: Path, kod: str, nazwa_pliku: str) -> str:
    """Podmienia nagłówek DRAFT na kanoniczny BEZ retłumaczenia. Zwraca status.

    Status: ``"ok"`` (podmieniono), ``"brak"`` (plik nie istnieje),
    ``"nie-draft"`` (brak markera draftu — plik już kanoniczny / ręcznie
    sfinalizowany; idempotentny no-op). Treść (z poprawkami recenzenta) NIE jest
    tknięta — przepisujemy tylko blok nagłówkowy.
    """
    if not cel.is_file():
        return "brak"
    with open(cel, "r", encoding="utf-8") as fh:
        tresc = fh.read()
    naglowek_linie, body = _rozdziel_naglowek(tresc)
    if przeglad_tlumaczen.MARKER_DRAFTU not in "\n".join(naglowek_linie):
        return "nie-draft"
    nowy = _kanoniczny_naglowek(kod, nazwa_pliku) + body
    with open(cel, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(nowy)
    return "ok"


# ---------------------------------------------------------------------------
# AUDYT PRZYKŁADÓW W PODRĘCZNIKACH (`--audyt`, zero API) — v18.20
# ---------------------------------------------------------------------------
# Docsowa odmiana bramki G6 z brata akcentów (v18.19): każdą parę „X → Y"
# z `gui/dokumentacja/*.yaml` przelicz FAKTYCZNYM silnikiem. Powód wprost
# z v18.19: akapit o Samogłoskowcu kłamał w OŚMIU podręcznikach (obietnica
# „zachowania polskich zmiękczeń" w paczkach bez tego kroku, pięć cytowało
# przykład niezgodny z silnikiem), a bramki plików REGUŁ tego nie widzą, bo to
# inny folder. Podręcznik czyta każdy użytkownik, pliki reguł prawie nikt.
#
# TRZY RÓŻNICE WOBEC G6 — wszystkie wymuszone materiałem, nie gustem:
#
#  1. **Kotwica nie może iść po etykiecie reguły.** Proza podręczników ma WŁASNĄ
#     terminologię, rozjechaną z `szyfry/*.yaml::etykieta`: docs `de` mówią
#     „Vokalisierer", etykieta „Vokaloid"; is „Sérhljóðari", ru „Гласновик",
#     it „Vocalizzatore". Kotwiczymy więc w paczce `pl` (tam proza i etykiety
#     się zgadzają, bo obie pisane ręcznie) i przenosimy rozstrzygnięcie do
#     ośmiu pozostałych paczek PO POZYCJI PUNKTU LISTY w tej samej sekcji.
#     Klucze sekcji są identyczne we wszystkich paczkach, a struktura listy
#     zmierzona 9/9 zgodna — to ten sam kanon „pl jako baza referencyjna".
#  2. **Zakres wynika z danych, nie z listy wyjątków.** Sekcja wchodzi do bramki
#     tylko wtedy, gdy jej PL-owy punkt listy NAZYWA operację silnika. Dzięki
#     temu dydaktyka HIPOTETYCZNA („dodajesz do akcentu dwie reguły: `ñ → nj`,
#     `j → x`" w `krok_7b_manager_regul_kolejnosc_zamian`) i ścieżki nawigacji
#     w cudzysłowach („pl" → „akcenty" = rozwijanie drzewa plików) wypadają
#     SAME, bez utrzymywania czarnej listy w dziewięciu językach. Pary poza
#     zakresem trafiają do podsumowania jako LICZBA — nowa sekcja z przykładami
#     nie zniknie po cichu.
#  3. **Czwarty werdykt: „to wynik INNEJ operacji tej paczki".** Proza cytuje
#     przykłady przez KONTRAST („w przeciwieństwie do pozostałych akcentów,
#     które tylko psują litery łacińskie — np. „sz" → „sh"") i wtedy para
#     należy do innego narzędzia niż punkt listy. Zamiast listy markerów
#     kontrastu w dziewięciu językach pytamy silnik: czy któraś INNA operacja
#     tego samego rodzaju daje ten wynik? Jeśli tak — uwaga z nazwą tej
#     operacji (recenzent widzi, czy to kontrast, czy pomylone narzędzie).
KODY_AUDYTU: tuple[str, ...] = (KOD_ZRODLOWY, *MAPA_JEZYKOW)

# Ile znaków CZOŁA punktu listy przeszukujemy pod nazwę operacji. Kalibracja na
# paczce pl: nazwa narzędzia stoi w TYTULE punktu, czyli w pierwszych kilkunastu
# znakach po punktorze („- Samogłoskowiec (Wszystko dudni na „O") — każda
# samogłoska…", „- Akcent rosyjski w Poliglocie (NOWOŚĆ…)"). Okno 90 znaków
# z pierwszej wersji łapało jeszcze nazwę PLIKU cytowaną w instrukcji
# („rozwiń „pl" → „akcenty" i kliknij „francuski.yaml"") i przypisywało
# ścieżkę nawigacji do akcentu francuskiego — 8 fałszywych oskarżeń.
GLOWA_PUNKTU = 40

# Szyfry, których NIE pytamy „czy to Twój wynik?" w werdykcie kontrastu — patrz
# :func:`_inna_operacja_zgodna`.
SZYFRY_POZA_KONTRASTEM = ("cezar",)


def _rodzenstwo_audytu() -> tuple[Any, Any]:
    """Leniwy import dwóch braci: tylko audyt potrzebuje silnika Poligloty.

    Ścieżka tłumacząca nie płaci za `core_poliglota` (docx, num2words) ani za
    `ruamel` — dokładnie tym samym argumentem, co lazy import `natywna_nazwa`
    w :func:`main`.
    """
    import buduj_wielojezyczne_akcenty as bwa
    import buduj_wielojezyczne_poliglota as bwp
    return bwa, bwp


def _bez_zawijania(tekst: str) -> str:
    """Skleja zawinięte wiersze punktu w jedną linię (spacje do jednej).

    Konieczne, bo `tresc` podręcznika to block scalar ZAWIJANY na ~72 znakach:
    cytat „Good morning, welcome madam" potrafi mieć w środku znak nowej linii,
    a ekstraktor par (dzielony z bratem akcentów) celowo nie wpuszcza `\\n`
    do cytatu — tam `opis` jest krótki i zawijanie nie występuje. Bez tej
    normalizacji bramka MILCZAŁABY o zawiniętych przykładach, co jest gorsze
    od fałszywego alarmu: pierwszy przebieg przeoczył tak angielski przykład
    Samogłoskowca („Goo mornong, woltom modom" — niezgodny z silnikiem).
    """
    return re.sub(r"\s+", " ", tekst).strip()


def _punkty_listy(tekst: str) -> list[str]:
    """Punkty listy sekcji, w kolejności występowania.

    Jednostką bramki jest PUNKT LISTY, a nie akapit: pomiar na 9 paczkach dał
    identyczną liczbę punktów w każdej audytowanej sekcji (6 szyfrów, 8 akcentów,
    14 pozycji changelogu), przy czym liczba samych akapitów potrafi się różnić
    (ru/`co_to_akcent` ma 13 wobec 12) — więc wyrównanie po akapitach byłoby
    kruche tam, gdzie po punktach jest dokładne.
    """
    punkty: list[str] = []
    for akapit in re.split(r"\n\s*\n", tekst or ""):
        for kandydat in re.split(r"\n(?=\s*(?:[-*•]|\d+[.)])\s)", akapit):
            if kandydat.strip() and _RE_PUNKTOR_LISTY.match(kandydat):
                punkty.append(kandydat)
    return punkty


def nazwy_operacji_pl(bwa: Any) -> dict[str, tuple[str, str]]:
    """Nazwa operacji z paczki `pl` → (`szyfry`|`akcenty`, id pliku).

    Źródłem nazw jest `etykieta` reguły (człon przed nawiasem, rozbity po „/" —
    „Zepsuty Telefon / Wężowy dialekt" to dwie nazwy jednego szyfru) plus sam
    `id`. Trzy narzędzia z `akcenty/` pomijamy: nie są akcentami fonetycznymi
    i nie mają czego obiecywać w prozie.
    """
    nazwy: dict[str, tuple[str, str]] = {}
    for folder in ("szyfry", "akcenty"):
        katalog = DICT_DIR / KOD_ZRODLOWY / folder
        if not katalog.is_dir():
            continue
        for plik in sorted(katalog.glob("*.yaml")):
            if plik.name in bwa.NARZEDZIA_AKCENTOW:
                continue
            try:
                with open(plik, "r", encoding="utf-8") as fh:
                    dane = yaml.safe_load(fh) or {}
            except (OSError, yaml.YAMLError):
                continue
            glowa = str(dane.get("etykieta") or "").split("(")[0]
            kandydaci = [czlon.strip() for czlon in glowa.split("/")]
            kandydaci.append(plik.stem)
            for nazwa in kandydaci:
                if len(nazwa) > 3:
                    nazwy[nazwa.lower()] = (folder, plik.stem)
    return nazwy


def _operacje_punktow_pl(
    tekst_pl: str, nazwy: dict[str, tuple[str, str]],
) -> dict[int, tuple[str, str]]:
    """Indeks punktu listy → operacja, rozstrzygnięta w paczce `pl`.

    Punkt, którego czoło nazywa DWIE różne operacje, zostaje nierozstrzygnięty:
    lepiej stracić przykład niż przypisać go nie temu narzędziu (ta sama zasada,
    co „bramka ma prawo powiedzieć «nie rozstrzygam»" z v18.19).
    """
    wynik: dict[int, tuple[str, str]] = {}
    for indeks, punkt in enumerate(_punkty_listy(tekst_pl)):
        czolo = _bez_zawijania(punkt)[:GLOWA_PUNKTU].lower()
        # Nazwa PLIKU reguły (`francuski.yaml`) nie jest tytułem punktu, a
        # cytatem z instrukcji — punkt „kliknij «francuski.yaml»" opisuje
        # nawigację, nie akcent francuski.
        trafione = {
            operacja for nazwa, operacja in nazwy.items()
            if re.search(r"(?<!\w)" + re.escape(nazwa) + r"(?!\.ya?ml)", czolo)
        }
        if len(trafione) == 1:
            wynik[indeks] = trafione.pop()
    return wynik


def _wczytaj_regule(kod: str, folder: str, nazwa: str) -> dict:
    """`dictionaries/<kod>/<folder>/<nazwa>.yaml` (pusty dict przy braku)."""
    plik = DICT_DIR / kod / folder / f"{nazwa}.yaml"
    try:
        with open(plik, "r", encoding="utf-8") as fh:
            dane = yaml.safe_load(fh)
    except (OSError, yaml.YAMLError):
        return {}
    return dane if isinstance(dane, dict) else {}


def _operacja_zgodna(
    kod: str, folder: str, nazwa: str, src: str, oczekiwane: str,
    cp: Any, bwa: Any, bwp: Any,
) -> str | None:
    """Czy operacja `<folder>/<nazwa>` paczki `kod` produkuje `oczekiwane`?

    Zwraca ``None``, gdy tak (albo gdy nie ma czego policzyć), a opis rozjazdu,
    gdy nie. Dla szyfrów pytamy o NIEZMIENNIKI (algorytmy jąkania, typoglikemii
    i węża losują — patrz `sprawdz_pare_przykladu` u brata Poligloty), dla
    akcentów o dokładny wynik tablicy `zamiany`.
    """
    if folder == "szyfry":
        cfg = _wczytaj_regule(kod, folder, nazwa)
        if not cfg:
            return f"paczka nie ma pliku `szyfry/{nazwa}.yaml`"
        algorytm = str(cfg.get("algorytm") or nazwa)
        return bwp.sprawdz_pare_przykladu(
            algorytm, src, oczekiwane, cfg, bwa.podstawy_paczki(kod))
    if not (DICT_DIR / kod / folder / f"{nazwa}.yaml").is_file():
        return f"paczka nie ma pliku `akcenty/{nazwa}.yaml`"
    wynik = bwa.zastosuj(cp, src, kod, nazwa)
    if wynik is None:
        return "silnik nie policzył tego przykładu (zła reguła?)"
    if wynik == oczekiwane:
        return None
    return f"{src!r} → obiecuje {oczekiwane!r}, a silnik daje {wynik!r}"


def _inna_operacja_zgodna(
    kod: str, folder: str, nazwa: str, src: str, oczekiwane: str,
    cp: Any, bwa: Any, bwp: Any,
) -> str | None:
    """Nazwa INNEJ operacji tego samego rodzaju, która daje ten wynik (albo None).

    Bramka pyta o to zamiast utrzymywać listę markerów kontrastu w dziewięciu
    językach. Trafienie NIE jest rozgrzeszeniem — jest uwagą: albo proza
    świadomie cytuje inne narzędzie („w przeciwieństwie do pozostałych
    akcentów…"), albo pomyliła narzędzia, a to już defekt do ręki recenzenta.

    Szyfr Cezara jest z tego pytania WYŁĄCZONY (kalibracja pierwszego przebiegu):
    jego kontrola jest EGZYSTENCJALNA — „czy ISTNIEJE przesunięcie dające ten
    wynik" — więc dla dowolnej pary równej długości odpowiada „tak" i tłumaczy
    wszystko. Sześć realnych rozjazdów Samogłoskowca (pl, es, fr, it, ru)
    zeszło z jego łaski z błędu na uwagę, zamiast się wyświetlić.
    """
    katalog = DICT_DIR / kod / folder
    if not katalog.is_dir():
        return None
    for plik in sorted(katalog.glob("*.yaml")):
        if (plik.stem == nazwa or plik.name in bwa.NARZEDZIA_AKCENTOW
                or plik.stem in SZYFRY_POZA_KONTRASTEM):
            continue
        if _operacja_zgodna(kod, folder, plik.stem, src, oczekiwane,
                            cp, bwa, bwp) is None:
            return plik.stem
    return None


def audytuj_przyklady(
    kody: list[str] | None = None,
    nazwy_plikow: list[str] | None = None,
) -> tuple[list[Any], dict[str, Any]]:
    """Bramki D1 i D2 na `dictionaries/<kod>/gui/dokumentacja/*.yaml`.

    * **D1 struktura** — liczba punktów listy w sekcji rozjechana z paczką `pl`
      (uwaga, nie błąd: bramka przestaje wtedy wyrównywać przykłady tej sekcji,
      ale sam rozjazd bywa redakcją, np. akapit dopisany w jednym języku).
    * **D2 przykłady** — para „X → Y" niezgodna z faktycznym silnikiem.

    Zwraca ``(znaleziska, statystyki)``; statystyki mają liczbę par w zakresie
    i poza nim (per sekcja), żeby żadne obcięcie pokrycia nie było ciche.
    """
    bwa, bwp = _rodzenstwo_audytu()
    cp = bwa.ustaw_silnik()
    nazwy = nazwy_operacji_pl(bwa)
    szablony_pl = wczytaj_szablony_pl()
    if nazwy_plikow:
        szablony_pl = [s for s in szablony_pl if s[0] in nazwy_plikow]
    zakres_kodow = [k for k in KODY_AUDYTU if not kody or k in kody]

    znaleziska: list[Any] = []
    staty: dict[str, Any] = {
        "par": 0, "w_zakresie": 0, "poza_zakresem": Counter(), "sekcji": 0,
    }
    for nazwa_pliku, _id, sekcje_pl in szablony_pl:
        for klucz_sekcji, tekst_pl in sekcje_pl.items():
            operacje = _operacje_punktow_pl(tekst_pl, nazwy)
            punkty_pl = len(_punkty_listy(tekst_pl))
            if operacje:
                staty["sekcji"] += 1
            for kod in zakres_kodow:
                cel = DICT_DIR / kod / FOLDER_GUI / FOLDER_DOKUMENTACJA / nazwa_pliku
                sekcje = (wczytaj_istniejacy_docelowy(cel) or {}
                          if kod != KOD_ZRODLOWY else sekcje_pl)
                tekst = sekcje.get(klucz_sekcji)
                if not tekst:
                    continue
                punkty = _punkty_listy(tekst)
                pary_sekcji = bwa.lancuchy_z_opisu(
                    _bez_zawijania(tekst), dopusc_frazy=True)
                staty["par"] += len(pary_sekcji)
                etykieta = f"{kod}/{nazwa_pliku}::{klucz_sekcji}"
                if operacje and len(punkty) != punkty_pl:
                    znaleziska.append(bwa.Znalezisko(
                        etykieta, "D1",
                        f"punktów listy jest {len(punkty)}, a w paczce "
                        f"`{KOD_ZRODLOWY}` {punkty_pl} — bramka NIE wyrównuje "
                        f"przykładów tej sekcji (sprawdź ją ręcznie)",
                        blad=False))
                    staty["poza_zakresem"][f"{nazwa_pliku}::{klucz_sekcji}"] += \
                        len(pary_sekcji)
                    continue
                # Pary liczymy per punkt listy, bo tylko punkt ma kotwicę.
                w_punktach = 0
                for indeks, punkt in enumerate(punkty):
                    operacja = operacje.get(indeks)
                    pary = bwa.lancuchy_z_opisu(
                        _bez_zawijania(punkt), dopusc_frazy=True)
                    w_punktach += len(pary)
                    if operacja is None:
                        staty["poza_zakresem"][
                            f"{nazwa_pliku}::{klucz_sekcji}"] += len(pary)
                        continue
                    folder, nazwa_reguly = operacja
                    for src, oczekiwane, kontekst in pary:
                        staty["w_zakresie"] += 1
                        znalezisko = _werdykt_przykladu(
                            etykieta, folder, nazwa_reguly, kod, src,
                            oczekiwane, kontekst, cp, bwa, bwp)
                        if znalezisko is not None:
                            znaleziska.append(znalezisko)
                # Pary spoza punktów listy (proza wprowadzająca, akapit
                # podsumowujący) — poza zakresem, ale policzone.
                staty["poza_zakresem"][f"{nazwa_pliku}::{klucz_sekcji}"] += \
                    max(0, len(pary_sekcji) - w_punktach)
    return znaleziska, staty


def _werdykt_przykladu(
    etykieta: str, folder: str, nazwa_reguly: str, kod: str, src: str,
    oczekiwane: str, kontekst: str, cp: Any, bwa: Any, bwp: Any,
) -> Any | None:
    """Jedna para „X → Y" wobec silnika. ``None`` = zgoda, inaczej znalezisko."""
    rozjazd = _operacja_zgodna(kod, folder, nazwa_reguly, src, oczekiwane,
                               cp, bwa, bwp)
    if rozjazd is None:
        return None
    opis_reguly = f"{folder}/{nazwa_reguly}"

    inna = _inna_operacja_zgodna(kod, folder, nazwa_reguly, src, oczekiwane,
                                 cp, bwa, bwp)

    # Werdykt „paczka nie ma tej reguły": w prozie changelogu bywa uczciwy
    # (`ru` opisuje akcent rosyjski, którego rosyjska paczka z natury nie ma —
    # to parytet natywności, nie defekt; sama przepisała wpis na akcent
    # LUSTRZANY, czyli polski), więc uwaga, nie błąd. Nazwa realnej operacji
    # oszczędza recenzentowi szukania, o czym ta paczka właściwie mówi.
    if rozjazd.startswith("paczka nie ma pliku"):
        trop = (f", a ten wynik daje `{folder}/{inna}` — najpewniej paczka "
                f"opisuje tę regułę" if inna else " — bramka NIE ROZSTRZYGA")
        return bwa.Znalezisko(
            etykieta, "D2",
            f"przykład {src!r} → {oczekiwane!r} przypisany (po pozycji punktu "
            f"w paczce `{KOD_ZRODLOWY}`) do `{opis_reguly}`, ale {rozjazd}"
            f"{trop}", blad=False)

    if inna is not None:
        return bwa.Znalezisko(
            etykieta, "D2",
            f"przykład {src!r} → {oczekiwane!r} stoi w punkcie o "
            f"`{opis_reguly}`, a taki wynik daje `{folder}/{inna}` — sprawdź, "
            f"czy proza cytuje inne narzędzie przez KONTRAST, czy je pomyliła",
            blad=False)

    pozycyjna = folder == "akcenty" and bwa.regex_uczestniczyl(
        _wczytaj_regule(kod, folder, nazwa_reguly), src)
    miekkie = pozycyjna or bwa.zastrzezone(kontekst)
    powod = ""
    if pozycyjna:
        powod = (" — w wyniku uczestniczy reguła pozycyjna `regex: true`, więc "
                 "bramka NIE ROZSTRZYGA: sprawdź ten przykład na całym słowie")
    elif miekkie:
        powod = " (proza zastrzeżona warunkiem albo cytuje anty-przykład)"
    return bwa.Znalezisko(etykieta, "D2",
                          f"[{opis_reguly}] {rozjazd}{powod}", blad=not miekkie)


def raport_audytu_markdown(znaleziska: list[Any], staty: dict[str, Any],
                           bwa: Any) -> str:
    """Raport audytu do pliku (długa treść nie idzie do terminala)."""
    bledy = [z for z in znaleziska if z.blad]
    uwagi = [z for z in znaleziska if not z.blad]
    linie = [
        "# Audyt przykładów w podręcznikach",
        "",
        f"Par „X → Y” w dokumentacji: **{staty['par']}**, w zakresie bramki: "
        f"**{staty['w_zakresie']}** (sekcji z kotwicą w `pl`: "
        f"{staty['sekcji']}). Błędów: **{len(bledy)}**, uwag: **{len(uwagi)}**.",
        "",
        "Bramki: D1 struktura punktów listy wobec paczki `pl` · "
        "D2 przykład przeliczony SILNIKIEM (szyfry — niezmienniki algorytmu, "
        "akcenty — dokładny wynik tablicy `zamiany`).",
        "",
    ]
    for tytul, zbior in (("Błędy (blokują)", bledy), ("Uwagi (triaż)", uwagi)):
        linie += [f"## {tytul}", ""]
        if not zbior:
            linie += ["Brak.", ""]
            continue
        for bramka, lista in sorted(bwa.grupuj(zbior).items()):
            linie += [f"### {bramka} ({len(lista)})", ""]
            linie += [f"- `{z.para}` — {z.opis}" for z in lista]
            linie.append("")
    linie += ["## Pary poza zakresem bramki (per sekcja)", ""]
    poza = staty["poza_zakresem"]
    if not poza:
        linie += ["Brak.", ""]
    else:
        linie += [
            "Sekcje bez kotwicy w paczce `pl` (dydaktyka hipotetyczna, ścieżki "
            "nawigacji, nazwy pól) albo pary spoza punktów listy. Lista jest tu "
            "po to, żeby NOWA sekcja z przykładami nie zniknęła po cichu:", "",
        ]
        linie += [f"- `{sekcja}` — {ile}"
                  for sekcja, ile in sorted(poza.items()) if ile]
        linie.append("")
    return "\n".join(linie)


def wypisz_podsumowanie_audytu(znaleziska: list[Any], staty: dict[str, Any],
                               bwa: Any) -> None:
    bledy = [z for z in znaleziska if z.blad]
    uwagi = [z for z in znaleziska if not z.blad]
    poza = sum(staty["poza_zakresem"].values())
    print(f"\n========== AUDYT PRZYKŁADÓW DOCS "
          f"({staty['w_zakresie']} par w zakresie, {poza} poza) ==========")
    for bramka, lista in sorted(bwa.grupuj(znaleziska).items()):
        ile_b = sum(1 for z in lista if z.blad)
        print(f"  {bramka}: {len(lista)} trafień ({ile_b} błędów)")
    print(f"{'✅ Bez zastrzeżeń.' if not bledy else f'❌ Błędów: {len(bledy)}'}"
          f"  (uwag: {len(uwagi)})")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _parsuj_argumenty() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Batch auto-translator of the manual.yaml documentation into target "
            f"languages ({', '.join(MAPA_JEZYKOW)}). Uses tlumacz_ai.py, freezing "
            "placeholders with unique Unicode tokens ⟦i⟧."
        ),
    )
    # Grupa jest OPCJONALNA od v18.20: `--audyt` domyślnie bierze wszystkie
    # dziewięć paczek (razem z `pl`, która sama okazała się kłamać o
    # Samogłoskowcu), więc wymuszanie wyboru języka byłoby tu tylko szumem.
    # Ścieżka TŁUMACZĄCA nadal wymaga jawnego wyboru — sprawdzenie niżej.
    grupa = parser.add_mutually_exclusive_group(required=False)
    grupa.add_argument(
        "-l", "--jezyki",
        type=str,
        default="",
        help=f"Comma-separated list of ISO codes (e.g. `en,fi`). "
             f"Allowed: {', '.join(MAPA_JEZYKOW)}.",
    )
    grupa.add_argument(
        "-a", "--wszystkie",
        action="store_true",
        help=f"Translate into all languages ({', '.join(MAPA_JEZYKOW)}).",
    )
    parser.add_argument(
        "-t", "--szablony",
        type=str,
        default="",
        help="CSV of template names to translate (e.g. `dictionaries.yaml` "
             "or bare-name `dictionaries`; the `.yaml` extension is "
             "appended automatically). Empty value = all templates "
             "from `dictionaries/pl/gui/dokumentacja/`. Useful when some "
             "templates already have up-to-date translations on disk and you "
             "don't want to burn the API bill again (e.g. `--szablony dictionaries` when "
             "`manual.yaml` is already translated in all languages).",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip TEMPLATES for which "
             "`dictionaries/<kod>/gui/dokumentacja/<plik>.yaml` already exists "
             "(idempotent rerun at the single-file level — when you add a "
             "new template to PL, just run `--wszystkie --skip-existing` to "
             "translate only the missing entries without re-billing the API on "
             "manual.yaml).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Tokenization + placeholder-map preview only. Zero API calls.",
    )
    parser.add_argument(
        "--model",
        default="claude-sonnet-5",
        help="Anthropic Claude model for the main translation (default: claude-sonnet-5).",
    )
    parser.add_argument(
        "-k", "--klucz",
        type=str,
        default=None,
        metavar="KLUCZ[,KLUCZ...]",
        help="Translate ONLY the listed section keys (e.g. `krok_5_vocalizer,krok_5_alarm_nvda_2026`), "
             "the rest of the file stays from the existing translation. "
             "Requires the target `<kod>/gui/dokumentacja/<plik>.yaml` to already exist IN THE NEW SCHEMA "
             "(dict `tresc:` with sections) — first run a FULL translation without --klucz, "
             "so the file adopts the new schema. A surgical update is cheaper API-wise: "
             "you translate e.g. only the Vocalizer section (~2 kB) instead of the whole manual (~68 kB).",
    )
    # NB (od refaktoru 18.x): flagi `--draft`, `--retry`, `--input` ZNIESIONE
    # (krucha pętla feedbacku + META gryzły się z chunkowaniem i openai_compat).
    # KAŻDE tłumaczenie — pełne i `--klucz` — ZAWSZE ląduje jako draft do recenzji
    # + emituje checklistę `skrypty/przeglad_docs.md`. Kanoniczny nagłówek
    # „do NOT edit by hand" zdobywa się WYŁĄCZNIE przez --finalizuj po recenzji.
    parser.add_argument(
        "-f", "--finalizuj",
        action="store_true",
        help="DRAFT FINALIZATION (zero API, zero re-translation). For the selected "
             "languages/templates it swaps the working \"WORKING DRAFT\" header to the "
             "canonical \"do NOT edit by hand\", PRESERVING all content (including the reviewer's "
             "manual hallucination fixes). Files without a draft marker are skipped "
             "(idempotent). This is the proper step after review acceptance — instead of "
             "the destructive \"regenerate without --draft\".",
    )
    parser.add_argument(
        "--audyt",
        action="store_true",
        help="AUDIT of examples in the manuals (zero API). Recomputes every "
             "„X → Y” pair from `dictionaries/<code>/gui/dokumentacja/*.yaml` "
             "with the ACTUAL engine — ciphers via the algorithm's invariants, "
             "accents via the `zamiany` table. Default scope: all nine packages "
             "including `pl` (narrow it with --jezyki). Long report goes to "
             "--raport, the terminal gets a summary.",
    )
    parser.add_argument(
        "--raport",
        type=str,
        default="",
        help="Path for the full markdown audit report (used with --audyt).",
    )
    args = parser.parse_args()
    if args.audyt and (args.klucz or args.skip_existing or args.dry_run
                       or args.finalizuj):
        parser.error("--audyt is a read-only local check (zero API) — "
                     "do not combine with --klucz/--skip-existing/--dry-run/"
                     "--finalizuj.")
    if not args.audyt and not (args.jezyki or args.wszystkie):
        parser.error("one of the arguments -l/--jezyki -a/--wszystkie "
                     "is required (not needed only for --audyt).")
    if args.klucz and args.skip_existing:
        parser.error("--klucz and --skip-existing are mutually exclusive "
                     "(--klucz deliberately overwrites the selected sections in an existing file).")
    if args.finalizuj and (args.klucz or args.skip_existing or args.dry_run):
        parser.error("--finalizuj is a purely local header swap (zero API) — "
                     "do not combine with --klucz/--skip-existing/--dry-run. "
                     "Select languages via --jezyki/--wszystkie "
                     "(optionally narrow with --szablony).")
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
            f"❌ Unknown templates: {nieznane}.\n"
            f"   Available in dictionaries/{KOD_ZRODLOWY}/{FOLDER_GUI}/{FOLDER_DOKUMENTACJA}/: "
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
            f"❌ Unknown language codes: {', '.join(nieznane)}.\n"
            f"   Allowed: {', '.join(MAPA_JEZYKOW)}."
        )
    return kody


def _zainicjuj_klienta() -> Any:
    """Buduje klienta LLM (`core_llm`) z `golden_key.env`.

    Od v18.4 provider-agnostic: domyślnie Anthropic Claude (`ANTHROPIC_API_KEY`,
    `sk-ant-`), a przy `LLM_PROVIDER=openai_compat` dowolny endpoint zgodny z OpenAI.
    Ten sam silnik co Poliglota runtime (`tlumacz_ai` wymaga `core_llm.KlientLLM`).
    """
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

    klient = cl.zbuduj_klienta(cl.wczytaj_konfiguracje())
    if klient is None:
        raise SystemExit(
            "❌ Brak prawidłowej konfiguracji LLM w `golden_key.env`.\n"
            "   Anthropic (domyślnie): ustaw ANTHROPIC_API_KEY (sk-ant-…).\n"
            "   OpenAI-compat: LLM_PROVIDER=openai_compat + LLM_BASE_URL\n"
            "   + OPENAI_API_KEY + LLM_MODEL.\n"
            "   Ten sam plik, którego używa GUI (System Check w trybie Reżysera)."
        )
    return klient


def _tryb_audytu(args: argparse.Namespace) -> int:
    """`--audyt`: bramki D1/D2 na dokumentacji, zero API. Exit 1 przy błędzie."""
    kody = [k.strip() for k in args.jezyki.split(",") if k.strip()]
    nieznane = [k for k in kody if k not in KODY_AUDYTU]
    if nieznane:
        print(f"❌ Nieznane kody paczek: {', '.join(nieznane)}.\n"
              f"   Dozwolone: {', '.join(KODY_AUDYTU)}.")
        return 2
    try:
        wszystkie = wczytaj_szablony_pl()
    except (FileNotFoundError, ValueError) as exc:
        print(f"❌ {exc}")
        return 2
    nazwy_plikow = [s[0] for s in _filtruj_szablony(wszystkie, args.szablony)]

    bwa, _bwp = _rodzenstwo_audytu()
    znaleziska, staty = audytuj_przyklady(kody or None, nazwy_plikow)
    if args.raport:
        sciezka = Path(args.raport)
        sciezka.parent.mkdir(parents=True, exist_ok=True)
        sciezka.write_text(raport_audytu_markdown(znaleziska, staty, bwa),
                           encoding="utf-8", newline="\n")
        print(f"📋 Raport audytu → {sciezka}")
    else:
        for z in znaleziska:
            print(("❌ " if z.blad else "⚠️  ") + str(z))
    wypisz_podsumowanie_audytu(znaleziska, staty, bwa)
    return 1 if any(z.blad for z in znaleziska) else 0


def main() -> int:
    args = _parsuj_argumenty()
    if args.audyt:
        return _tryb_audytu(args)
    kody = _wybierz_jezyki(args)

    try:
        wszystkie_szablony = wczytaj_szablony_pl()
    except (FileNotFoundError, ValueError) as exc:
        print(f"❌ {exc}")
        return 2

    szablony = _filtruj_szablony(wszystkie_szablony, args.szablony)
    if not szablony:
        print("❌ The `--szablony` filter left an empty list — nothing to do.")
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

    # --finalizuj: czysto lokalna podmiana nagłówka DRAFT → kanoniczny. Zero API,
    # zero retłumaczenia — załatwiamy od razu i wychodzimy (przed inicjalizacją
    # klienta Anthropic, bo nie jest potrzebny).
    if args.finalizuj:
        zmienione = 0
        nie_drafty = 0
        braki = 0
        for kod in kody:
            for nazwa_pliku, _id, _sekcje in szablony:
                cel = DICT_DIR / kod / FOLDER_GUI / FOLDER_DOKUMENTACJA / nazwa_pliku
                status = finalizuj_naglowek_docs(cel, kod, nazwa_pliku)
                if status == "ok":
                    zmienione += 1
                    print(f"✅ {kod}/{nazwa_pliku}: nagłówek DRAFT → kanoniczny (treść nietknięta).")
                elif status == "nie-draft":
                    nie_drafty += 1
                    print(f"⏭️  {kod}/{nazwa_pliku}: brak markera draftu — pomijam (już kanoniczny).")
                else:
                    braki += 1
                    print(f"⚠️  {kod}/{nazwa_pliku}: file does not exist — skipping.")
        print("\n========== SUMMARY (--finalizuj) ==========")
        print(f"✅ Finalized: {zmienione} | ⏭️ already canonical: {nie_drafty} | ⚠️ missing file: {braki}")
        return 0

    klient: Any = None if args.dry_run else _zainicjuj_klienta()

    # 13.4: import lazy — `core_poliglota` dorzuca docx/num2words. Skrypt
    # uruchamiany w czystym kontekście CLI nie powinien płacić za to przy
    # imporcie modułu, tylko gdy faktycznie idzie tłumaczyć.
    from core_poliglota import natywna_nazwa

    sukcesy: list[str] = []
    porazki: list[str] = []
    wytworzone_drafty: list[tuple[str, str]] = []

    klucze_filtru: list[str] | None = None
    if args.klucz:
        klucze_filtru = [k.strip() for k in args.klucz.split(",") if k.strip()]
        if not klucze_filtru:
            print("❌ Flag --klucz given, but the CSV is empty.")
            return 2
        print(f"🔎 Filtr --klucz ({len(klucze_filtru)} klucz/y): {klucze_filtru}")
        print(f"   Surgical update — pozostałe sekcje zostaną z istniejących tłumaczeń.")

    for kod in kody:
        nazwa_pl = MAPA_JEZYKOW[kod]
        nazwa_natywna = natywna_nazwa(kod)
        print(f"\n========== {kod.upper()} ({nazwa_pl} / {nazwa_natywna}) ==========")
        wszystko_ok = True
        for nazwa_pliku, id_szablonu, sekcje_pl in szablony:
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
                klucze_filtru=klucze_filtru,
            )
            if not ok:
                wszystko_ok = False
            elif not args.dry_run:
                wytworzone_drafty.append((kod, nazwa_pliku))
        (sukcesy if wszystko_ok else porazki).append(kod)

    if not args.dry_run:
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

    print("\n========== SUMMARY ==========")
    print(f"✅ Success: {len(sukcesy)}/{len(kody)}  ({', '.join(sukcesy) or '—'})")
    if porazki:
        print(f"❌ Failures (≥1 template failed): {', '.join(porazki)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
