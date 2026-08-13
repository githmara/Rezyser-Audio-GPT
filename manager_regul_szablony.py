"""
manager_regul_szablony.py – Szablony i prompty dla Managera Reguł.

Moduł trzyma gotowe teksty YAML-i do utworzenia (szablony) oraz prompty
(po angielsku — język roboczy agentów kodujących) dla agentów AI, które
wygenerują trudne merytorycznie reguły zamiast zwykłego Kowalskiego.

Szablony (``yaml``) i prompty (``prompt``) są budowane bezpośrednio tutaj.
Jedyny element lokalizowany to ``uwagi`` (notatka „Dalsze kroki" widoczna
w GUI) — od E2 składana z kluczy ``manager.uwagi.*`` w
``dictionaries/<kod>/gui/ui.yaml`` przez :func:`_uwagi`, więc moduł importuje
:mod:`i18n` (i podąża za językiem UI aplikacji).

Używany przez ``gui_manager_regul.ManagerRegulPanel`` podczas akcji
„Nowy…". Dla każdego typu reguły funkcja zwraca słownik:

    {
        "tryb":     "SZABLON" | "PROMPT" | "SZABLON_I_PROMPT",
        "yaml":     "<tekst szablonu YAML>"     (gdy dostępny),
        "prompt":   "<tekst promptu dla AI>"    (gdy dostępny),
        "docelowy": "<ścieżka względna w dictionaries/>",
        "uwagi":    "<krótki opis dla użytkownika>",
    }

Teksty bazowe są wzorowane NA POLSKICH PLIKACH z ``dictionaries/pl/``
(stan na wersję 13.0). Jeśli zmieniasz polskie reguły – warto
zsynchronizować szablony tutaj.
"""

from __future__ import annotations

import re
import sys

import yaml

import i18n
import sciezki


# =============================================================================
# Pomocnicze: składanie notatki „Dalsze kroki" (uwagi) z kluczy i18n
# =============================================================================
def _czy_frozen() -> bool:
    """``True`` w paczce PyInstaller (zainstalowana apka), ``False`` ze źródła.

    Wzorzec spójny z ``sciezki._wyznacz_baze`` i ``main._on_aktualizacja_dostepna``
    — jedynym wiarygodnym sygnałem „to skompilowana paczka" jest ``sys.frozen``.
    """
    return bool(getattr(sys, "frozen", False))


def _uwagi(klucz_typu: str, **kwargs: str) -> str:
    """Składa lokalizowaną notatkę „Dalsze kroki" dla :class:`WynikKreatoraDialog`.

    Trzy akapity (klucze ``manager.uwagi.*`` w ``ui.yaml``):
      1. nota specyficzna dla typu reguły (``klucz_typu``),
      2. ``jezyk_agenta`` — prompt jest po angielsku, język wyjścia natywny,
      3. akapit środowiskowy: ``srodowisko_frozen`` (zainstalowana paczka) albo
         ``srodowisko_zrodlo`` (uruchomienie ze źródła repo) — wg :func:`_czy_frozen`.

    ``kwargs`` (``jezyk_bazowy``, ``id_pliku``) trafiają do ``str.format`` w
    :func:`i18n.t`; nadmiarowe klucze są ignorowane, więc bezpiecznie podajemy
    je do wszystkich trzech wywołań.
    """
    srodowisko = "srodowisko_frozen" if _czy_frozen() else "srodowisko_zrodlo"
    return "\n\n".join((
        i18n.t(f"manager.uwagi.{klucz_typu}", **kwargs),
        i18n.t("manager.uwagi.jezyk_agenta", **kwargs),
        i18n.t(f"manager.uwagi.{srodowisko}", **kwargs),
    ))


# =============================================================================
# Pomocnicze stałe – lista typów obsługiwanych przez kreator
# =============================================================================
TYP_JEZYK_BAZOWY         = "jezyk_bazowy"
TYP_AKCENT               = "akcent"             # fonetyczny cross-language
TYP_AKCENT_OCZYSZCZENIE  = "akcent_oczyszczenie"  # preprocessor bez fonetyki
TYP_AKCENT_NAPRAWIACZ    = "akcent_naprawiacz"    # wstrzykuje ISO do HTML/DOCX
TYP_SZYFR_ZAMIANY        = "szyfr_zamiany"
TYP_SZYFR_ALGORYTM       = "szyfr_algorytm"
TYP_TRYB_REZYSERA        = "tryb_rezysera"
TYP_TRYB_OPOWIESCI       = "tryb_opowiesci"   # PROMPT-only: wymaga okablowania w Pythonie
TYP_POSTPRODUKCJA        = "postprodukcja"

# Kolejność typów w ComboBox-ie kreatora (= priorytet A11y). Etykiety i opisy
# NIE są tu hardkodowane — rezydują w i18n pod kluczami `manager.typ.<id>.etykieta`
# i `manager.typ.<id>.opis` (patrz dictionaries/<kod>/gui/ui.yaml). GUI rozwija je
# przez `t()` w momencie budowy dialogu, gdy język jest już załadowany (lista jest
# stałą modułową, więc `t()` na poziomie importu byłoby przedwczesne).
LISTA_TYPOW: list[str] = [
    TYP_AKCENT,
    TYP_AKCENT_OCZYSZCZENIE,
    TYP_AKCENT_NAPRAWIACZ,
    TYP_SZYFR_ZAMIANY,
    TYP_TRYB_REZYSERA,
    TYP_TRYB_OPOWIESCI,
    TYP_POSTPRODUKCJA,
    TYP_JEZYK_BAZOWY,
    TYP_SZYFR_ALGORYTM,
]


# =============================================================================
# Natywne dane językowe — ODCZYT DYNAMICZNY z dictionaries/ (od v18.5)
# =============================================================================
# Do v18.4 te wartości żyły jako zhardkodowane słowniki (`_NATYWNE_*`,
# `_PACZKI_WDROZONE`), które trzeba było SYNCHRONIZOWAĆ RĘCZNIE w Pythonie przy
# każdym nowym języku. Okazało się, że WSZYSTKIE są wyłącznie cache danych
# leżących już w paczce na dysku:
#   * endonim (np. „Deutsch")     → <kod>/podstawy.yaml::etykieta (prefiks),
#   * forma odmieniona („polsku")  → <kod>/rezyser/*.yaml::jezyk_odpowiedzi,
#   * słowa „streszczenie"         → <kod>/rezyser/tryb_audiobook.yaml::
#                                     slowa_wyzwalajace.streszczenie,
#   * lista paczek referencyjnych  → skan dictionaries/.
# Czytamy je więc w locie (spójnie z dynamicznym dispatchem akcentów od v17.5).
# Dodanie języka NIE wymaga już edycji tego pliku.
#
# Gdy danej nie ma jeszcze na dysku (świeża paczka) — zwracamy marker
# „<FILL NATIVELY…>", dokładnie jak wcześniej dla niewdrożonych kodów; wykonawca
# (AI/lingwista) go uzupełnia, a każdy KOLEJNY szablon czyta już realną wartość
# zapisaną w YAML-u (samo-naprawa chicken-and-egg).
#
# Moduł jest importowany przez GUI także w zamrożonej apce — odczyt idzie przez
# `sciezki.KATALOG_BAZOWY` (= katalog exe), więc działa offline i bez API.
# =============================================================================
_DICT_DIR = sciezki.KATALOG_BAZOWY / "dictionaries"

# Separator endonimu w `etykieta` (np. „Suomi – foneettiset perusteet”) —
# en-dash / em-dash / zwykły myślnik z otaczającymi spacjami (jak w
# `core_poliglota.natywna_nazwa` i `refresh_languages`).
_RE_SEPARATOR_ETYKIETY = re.compile(r"\s+[–—-]\s+")


def _wczytaj_yaml(sciezka) -> dict:
    """Bezpiecznie wczytuje plik YAML jako dict (pusty dict, gdy brak/zły)."""
    try:
        dane = yaml.safe_load(sciezka.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return {}
    return dane if isinstance(dane, dict) else {}


def _pliki_rezyser(kod: str) -> list:
    """Pliki trybów Reżysera danej paczki — `tryb_audiobook.yaml` na początku.

    Audiobook jest kanonicznym źródłem `jezyk_odpowiedzi` i listy słów
    streszczenia, ale każdy tryb paczki niesie tę samą natywną formę — więc
    pozostałe pliki służą jako fallback, gdy audiobooka jeszcze nie ma.
    """
    rez = _DICT_DIR / kod / "rezyser"
    if not rez.is_dir():
        return []
    audiobook = rez / "tryb_audiobook.yaml"
    reszta = sorted(p for p in rez.glob("*.yaml") if p.name != "tryb_audiobook.yaml")
    return ([audiobook] if audiobook.is_file() else []) + reszta


def _natywne_jezyk_odpowiedzi(kod: str) -> str:
    """Natywna wartość pola ``jezyk_odpowiedzi`` (np. ``"polsku"``, ``"Deutsch"``).

    Czyta pierwszy dostępny ``<kod>/rezyser/*.yaml::jezyk_odpowiedzi``
    (audiobook w pierwszej kolejności). Gdy żaden tryb jeszcze nie istnieje
    (świeża paczka) — zwraca marker do uzupełnienia.

    Returns:
        ``"polsku"``, ``"Deutsch"``, ``"по-русски"`` itp. dla wdrożonych paczek
        lub ``"'<FILL NATIVELY: …>'"`` dla świeżych. Marker jest owinięty w
        apostrofy YAML, żeby ``<...>`` nie zostało wzięte za tag YAML i żeby
        parsowanie szablonu nie wybuchało (real-world: user i tak go zastąpi).
    """
    for p in _pliki_rezyser(kod):
        v = _wczytaj_yaml(p).get("jezyk_odpowiedzi")
        if isinstance(v, str) and v.strip():
            return v.strip()
    return "'<FILL NATIVELY: the form appropriate for the prompt, e.g. polsku / Deutsch / italiano>'"


def _natywne_streszczenie_yaml(kod: str) -> str:
    """Zwraca blok YAML z natywnymi słowami wyzwalającymi streszczenie.

    Czyta ``slowa_wyzwalajace.streszczenie`` z pierwszego trybu Reżysera, który
    je ma (audiobook w pierwszej kolejności). Format dopasowany do
    bezpośredniego wstrzyknięcia w ``szablon_tryb_rezysera``. Dla świeżej paczki
    (brak trybów na dysku) zwraca pojedynczy marker do uzupełnienia.
    """
    for p in _pliki_rezyser(kod):
        sw = _wczytaj_yaml(p).get("slowa_wyzwalajace")
        if isinstance(sw, dict):
            streszcz = sw.get("streszczenie")
            if isinstance(streszcz, list) and streszcz:
                return "\n".join(f"    - {slowo}" for slowo in streszcz)
    return "    - <FILL NATIVELY: 4 words like 'streszcz'/'summarize'/'fasse zusammen'>"


def _natywna_nazwa_jezyka(kod: str) -> str:
    """Endonim języka — np. ``"Deutsch"`` dla ``"de"``.

    Czyta prefiks ``<kod>/podstawy.yaml::etykieta`` (jak
    ``core_poliglota.natywna_nazwa``, ale samowystarczalnie — bez importu
    ciężkiego silnika). Fallback na sam kod ISO, gdy paczka nie ma jeszcze
    ``podstawy.yaml`` (świeży język) — identycznie jak dawny słownik zwracał
    kod dla nieznanego wpisu.
    """
    etyk = _wczytaj_yaml(_DICT_DIR / kod / "podstawy.yaml").get("etykieta", "")
    if isinstance(etyk, str) and etyk.strip():
        nazwa = _RE_SEPARATOR_ETYKIETY.split(etyk.strip(), maxsplit=1)[0].strip()
        if nazwa:
            return nazwa
    return kod


def _paczki_referencyjne(jezyk_bazowy: str) -> str:
    """Zwraca CSV kodów paczek obecnych na dysku (z ``podstawy.yaml``) BEZ bazowej.

    Podpowiedź dla agenta „otwórz `dictionaries/<jedna z tych>/<typ>/<plik>.yaml`,
    żeby zobaczyć konwencję stylu". Wykluczamy paczkę bazową, bo gdyby agent miał
    ją czytać, mógłby trafić na pustą/powstającą strukturę. Skan zastąpił dawną
    ręcznie synchronizowaną krotkę `_PACZKI_WDROZONE`.
    """
    inne = []
    if _DICT_DIR.is_dir():
        for p in sorted(_DICT_DIR.iterdir()):
            if p.is_dir() and p.name != jezyk_bazowy and (p / "podstawy.yaml").is_file():
                inne.append(p.name)
    return ", ".join(inne) if inne else "(brak — projekt ma tylko tę paczkę)"


# =============================================================================
# SZABLON 1: Akcent fonetyczny (wzorowany na dictionaries/pl/akcenty/finski.yaml)
# =============================================================================
def szablon_akcent(id_pliku: str, etykieta: str, iso: str,
                   jezyk_bazowy: str = "pl") -> str:
    """Zwraca tekst YAML szablonu akcentu – gotowy do zapisu na dysk.

    Format trzymany 1-do-1 z istniejącymi plikami, żeby silnik
    (``core_poliglota.py``) bez modyfikacji wciągnął akcent. Komentarze
    pozostawione w neutralnej formie z markerami ``<FILL NATIVELY>``
    — finalna wersja powinna mieć je w języku paczki bazowej (DE, IT itd.).
    """
    natywna_baza = _natywna_nazwa_jezyka(jezyk_bazowy)
    return f"""# -----------------------------------------------------------------------------
#  <FILL NATIVELY in {natywna_baza}: AKZENT {etykieta} / ACCENTO {etykieta} / ...>
#  <A short header describing the accent's purpose; model:
#   dictionaries/{jezyk_bazowy}/akcenty/<any>.yaml>
# -----------------------------------------------------------------------------
id: {id_pliku}
etykieta: "{etykieta}"
opis: |
  <FILL NATIVELY in {natywna_baza}: 2-4 sentences on which TTS synthesizer
  this accent targets and which phonetic phenomena it forces (devoicing,
  sibilant softening, transliteration, etc.).>
iso: {iso}
kategoria: akcent
kolejnosc: 100

# --- Processing pipeline (true/false) ---
# czysc_tekst_tts        – removes gibberish („khh", asterisks, hashtags)
# normalizuj_liczby      – turns digits into words (per {natywna_baza} grammar)
# usun_polskie_znaki     – strips the base-language ({jezyk_bazowy}) diacritics per
#                          the map in `dictionaries/{jezyk_bazowy}/podstawy.yaml::polskie_znaki`
# skleja_pojedyncze_litery – joins dangling single letters („w y s" → „wys")
czysc_tekst_tts: true
normalizuj_liczby: true
usun_polskie_znaki: true
skleja_pojedyncze_litery: true

# --- The actual phonetic replacements ---
# GOLDEN RULE #1 (size): trigraphs/digraphs (sch, tsch, ch, cz, sz, rz) BEFORE
# single letters (c, s, z, r), otherwise „c → ts" breaks the „ch", „cz" spellings.
#
# GOLDEN RULE #2 (sequencing — CRITICAL): the engine applies the `zamiany:`
# list SEQUENTIALLY via `str.replace` (or `re.sub` when `regex: true`); each
# rule operates on the OUTPUT of the previous one. If rule A introduces a
# character that a later rule B has as its `wzor`, B WILL EAT A's result.
# Classic trap: `ñ → nj` BEFORE `j → x` yields `ñ → nx` (not `nj`!), because
# the new „j" introduced by the first rule gets caught by the second.
# Ordering rule: FIRST replace the TARGET (a letter later used as a `zamiana`
# in other rules) with something safe, ONLY THEN introduce the SOURCE that
# produces that target. For ES: first `j → x`, then `ñ → nj`. Test: a sentence
# containing BOTH letters must show both accents in the result (for ES
# „Niño de paja juega" → must carry both the ñ and the j accent).
#
# For regex patterns add `regex: true`.
zamiany:
  - {{ wzor: "ch", zamiana: "h"  }}
  - {{ wzor: "Ch", zamiana: "H"  }}
  # <FILL IN: further pairs specific to the target language.
  # Copy the prompt from Manager Reguł to an AI for the full replacement list
  # — the prompt knows the {jezyk_bazowy} pack context and produces native comments.>
"""


# =============================================================================
# PROMPT 1: Akcent fonetyczny – poproś AI o pełną listę zamian
# =============================================================================
def prompt_akcent(id_pliku: str, etykieta: str, iso: str,
                  jezyk_bazowy: str) -> str:
    natywna_baza = _natywna_nazwa_jezyka(jezyk_bazowy)
    inne_paczki = _paczki_referencyjne(jezyk_bazowy)
    return f"""# ROLE
You are an AI agent with access to the files of the „Reżyser Audio GPT"
project (wxPython + Anthropic). You have tools: Read, Write, Edit, Glob, Grep,
Bash. Your job: create a phonetic rule inside the project tree.

# PROJECT CONTEXT
- `core_poliglota.py` — the phonetic engine. Accents are loaded from
  `dictionaries/<code>/akcenty/*.yaml` DYNAMICALLY (since v17.5): the
  Director mode dispatches by accent id on the fly, with no
  code-generation step — dropping in a YAML file is enough.
- Deployed packs (as of 13.9): {inne_paczki} — these are your reference for
  style and phonetics for similar goals (e.g. the Finnish accent exists in
  each of them).
- Base pack for this task: `dictionaries/{jezyk_bazowy}/`
  (language {natywna_baza}). Manager Reguł already created the structure.

# TASK
Create the file `dictionaries/{jezyk_bazowy}/akcenty/{id_pliku}.yaml` —
a phonetic accent **{etykieta}** that makes text written in
**{natywna_baza}** resemble the pronunciation of the language with ISO
code **{iso}** (the target TTS synthesizer).

# SCENARIO VALIDATION (before you write anything)
Check that `iso` ({iso}) differs from `jezyk_bazowy` ({jezyk_bazowy}).
If `iso == jezyk_bazowy` or `iso` is empty — this file is NOT a phonetic
accent but a utility preprocessor (`kategoria: oczyszczenie`) or a tag
fixer (`kategoria: naprawiacz`). STOP and ask the user to run Manager
Reguł with the right subtype („Akcent czyszczący" or „Naprawiacz tagów"
instead of „Akcent fonetyczny"). You cannot meaningfully write a
`zamiany:` list that makes a language resemble itself.

# REFERENCE FILES (open before writing)
1. `dictionaries/{jezyk_bazowy}/podstawy.yaml` — the alphabet and the
   `polskie_znaki` diacritics map of the base pack. Your replacement
   patterns MUST operate on the text after `usun_polskie_znaki: true`
   (i.e. after the transliteration described in that file).
2. `dictionaries/<another pack>/akcenty/<any>.yaml` — a style reference.
   Pick the pack whose base is closest in character to {natywna_baza}
   (Latin/Cyrillic alphabet, presence/absence of diacritics). The glob
   `dictionaries/*/akcenty/*.yaml` shows everything you have at hand.
3. (Optional) `dictionaries/<any>/akcenty/<same id>.yaml` — if an accent
   with the same `id` exists in another pack, check how its `zamiany`
   list was adapted to that pack's base. Useful for identifiers like
   `finski`, `szwedzki`, `oczyszczenie` that usually exist in every
   deployed pack.

# STRUCTURE REQUIREMENTS
1. Fields `id`, `etykieta`, `iso`, `kategoria: akcent`, `kolejnosc`.
2. Pipeline (boolean): `czysc_tekst_tts`, `normalizuj_liczby`,
   `usun_polskie_znaki`, `skleja_pojedyncze_litery`. Default `true`
   for typical phonetic accents.
3. The `zamiany:` list ordered: TRIGRAPHS → DIGRAPHS → SINGLE LETTERS
   (otherwise `c → ts` breaks the `ch` / `cz` spellings). Each
   digraph/trigraph in a `lowercase` + `Capitalized` variant; for
   languages that use frequent ALL-CAPS forms (e.g. German SCH, CH) add a
   third variant.
4. Regex: add `regex: true` on the replacement row.
5. **The `usun_polskie_znaki: true` flag** (despite its historical name!)
   strips the diacritics of language {jezyk_bazowy} per the map in
   `dictionaries/{jezyk_bazowy}/podstawy.yaml::polskie_znaki`. Your
   patterns MUST work ON THE TEXT AFTER that transliteration — i.e.
   operate on the ASCII (or diacritic-free) equivalent of the
   {natywna_baza} alphabet.

# NATIVE-LANGUAGE REQUIREMENTS
- `etykieta`, `opis`, the file header, the YAML comments — everything in
  **{natywna_baza}**. Mixing Polish with the native language is an ERROR
  (e.g. for the FR pack „Akcent finski" is wrong; it should be
  „Accent finlandais" or equivalent).

# PROCEDURE
1. Open the reference files (Read).
2. Design a `zamiany:` list appropriate to the {etykieta} accent, using the
   style convention of the pack you take as a model.
3. Save the file `dictionaries/{jezyk_bazowy}/akcenty/{id_pliku}.yaml`
   (Write).
4. Validate that the file parses as YAML using whatever YAML tooling you
   have available (any YAML loader/linter — do not assume a particular
   shell or that Python is on PATH).
5. (Optional) Enable the sequential-`zamiany:` loop check: run the app from
   source with `REZYSER_VALIDATE_ZAMIANY=1` — the engine prints warnings to
   the console if rules feed into each other through `str.replace`. No code
   regeneration is needed — the accent is detected dynamically once the
   file is added.
6. In your reply report: how many pairs `zamiany:` has and which pack you
   took as the style model.
"""


# =============================================================================
# SZABLON 1B: Akcent oczyszczający (preprocessor — bez fonetyki)
# =============================================================================
def szablon_oczyszczenie(id_pliku: str, etykieta: str,
                         jezyk_bazowy: str) -> str:
    """Szablon dla `kategoria: oczyszczenie`.

    Struktura jest stała we wszystkich 7 wdrożonych paczkach: pipeline ON
    (czysc_tekst_tts + normalizuj_liczby), pozostałe OFF, brak listy zamian.
    Zmienne między paczkami: tylko etykieta, opis i komentarze (natywne).
    """
    natywna_baza = _natywna_nazwa_jezyka(jezyk_bazowy)
    # Heurystyka: oczyszczenie_bez_liczb wyłącza normalizację cyfr na słowa.
    bez_liczb = "bez_liczb" in id_pliku
    normalizuj_liczby = "false" if bez_liczb else "true"
    return f"""# -----------------------------------------------------------------------------
#  <FILL NATIVELY in {natywna_baza}: file header, e.g. for DE:
#   „TEXTBEREINIGUNG MIT ZAHLENNORMALISIERUNG"; for IT: „PULIZIA DEL TESTO
#   CON NORMALIZZAZIONE DEI NUMERI">
#  Default „no accent" variant — cleans the text for a screen reader.
# -----------------------------------------------------------------------------
id: {id_pliku}
etykieta: "{etykieta}"
opis: |
  <FILL NATIVELY in {natywna_baza}: 2-4 sentences explaining that this
  „accent" applies no phonetics and only runs TTS cleaning (removes
  gibberish like „khh", asterisks, hashtags, dots) {"and turns digits into words" if not bez_liczb else "(WITHOUT number normalization — useful for books with many dates/numbers)"}.>
iso: {jezyk_bazowy}
kategoria: oczyszczenie
kolejnosc: 20
czysc_tekst_tts: true
normalizuj_liczby: {normalizuj_liczby}
usun_polskie_znaki: false
skleja_pojedyncze_litery: false
zamiany: []
"""


# =============================================================================
# PROMPT 1B: Akcent oczyszczający — tłumaczenie etykiety/opisu na natywny
# =============================================================================
def prompt_oczyszczenie(id_pliku: str, etykieta: str,
                        jezyk_bazowy: str) -> str:
    natywna_baza = _natywna_nazwa_jezyka(jezyk_bazowy)
    inne_paczki = _paczki_referencyjne(jezyk_bazowy)
    return f"""# ROLE
You are an AI agent with access to the files of the „Reżyser Audio GPT"
project. You have tools: Read, Write, Edit, Glob, Grep, Bash. Task: adapt a
„cleaning accent" file (a TTS preprocessor) to a new language pack.

# PROJECT CONTEXT
- „Cleaning" accents (`kategoria: oczyszczenie`) apply NO phonetics — they
  run only the `czysc_tekst_tts` pipeline plus optionally
  `normalizuj_liczby` (digits → words). The `zamiany:` list is empty.
- The structure of these files is IDENTICAL across all 7 deployed packs
  ({inne_paczki}); ONLY the label, description and YAML comments differ —
  all native.
- Each pack ships two variants: `oczyszczenie.yaml` (with number
  normalization) and `oczyszczenie_bez_liczb.yaml` (without — for books
  with many dates, page numbers etc.).

# TASK
Create the file `dictionaries/{jezyk_bazowy}/akcenty/{id_pliku}.yaml` —
a cleaning accent in the {natywna_baza} pack, GUI-visible label:
**{etykieta}**.

# REFERENCE FILES (open before writing)
1. `dictionaries/<any deployed>/akcenty/{id_pliku}.yaml` — a ready-made
   style model (structure, kolejnosc, pipeline). The only things you change
   are the label + description + comments translated into {natywna_baza}.
2. `dictionaries/{jezyk_bazowy}/podstawy.yaml` — to check the YAML comment
   style convention of the base pack.

# STRUCTURE REQUIREMENTS
1. `kategoria: oczyszczenie` (the engine treats such files as a
   preprocessor, not a phonetic accent).
2. `iso: {jezyk_bazowy}` (operates on the base-pack text).
3. Pipeline:
   - `oczyszczenie` (with number normalization): `czysc_tekst_tts: true`,
     `normalizuj_liczby: true`, `usun_polskie_znaki: false`,
     `skleja_pojedyncze_litery: false`.
   - `oczyszczenie_bez_liczb`: as above but `normalizuj_liczby: false`.
4. `zamiany: []` (empty list — this is not a phonetic accent).
5. `kolejnosc: 20` (places it above the phonetic accents in the GUI).

# NATIVE-LANGUAGE REQUIREMENTS
`etykieta`, `opis`, the file header, the YAML comments — everything in
{natywna_baza}. Note the label convention of the deployed packs:
- PL: „Żaden (Czyszczenie Z normalizacją liczb)"
- DE: „Keiner (Bereinigung MIT Zahlennormalisierung)"
- IT: „Nessuno (Pulizia CON normalizzazione numeri)"
The first word is „no accent" in {natywna_baza}, with a short note in
parentheses describing exactly what the pipeline does.

# PROCEDURE
1. Open `dictionaries/<deployed>/akcenty/{id_pliku}.yaml` (Read).
2. Open `dictionaries/{jezyk_bazowy}/podstawy.yaml` to see the comment
   convention of the base pack.
3. Save the file `dictionaries/{jezyk_bazowy}/akcenty/{id_pliku}.yaml`
   (Write) with the same structure but native text in the text fields.
4. Validate that the file parses as YAML using whatever YAML tooling you
   have available (any YAML loader/linter — do not assume a particular
   shell or that Python is on PATH).
5. Done — the cleaning accent is detected dynamically on app start, with no
   code regeneration.
6. In your reply report: which pack you took as the model.
"""


# =============================================================================
# SZABLON 1C: Naprawiacz tagów (wstrzykuje ISO do HTML/DOCX, bez modyfikacji)
# =============================================================================
def szablon_naprawiacz(id_pliku: str, etykieta: str,
                       jezyk_bazowy: str) -> str:
    """Szablon dla `kategoria: naprawiacz`.

    Tryb specjalny: wszystkie flagi pipeline OFF, `zamiany: []`,
    `iso: ""` (kod podaje user w GUI). Plik istnieje raz na paczkę.
    """
    natywna_baza = _natywna_nazwa_jezyka(jezyk_bazowy)
    return f"""# -----------------------------------------------------------------------------
#  <FILL NATIVELY in {natywna_baza}: file header, e.g. for DE:
#   „TAG-REPARATEUR (Sondermodus)"; for IT: „RIPARATORE DI TAG (modalità
#   speciale)"; for RU: „ВОССТАНОВИТЕЛЬ ТЕГОВ (специальный режим)">
#  Does NOT modify the content — it ONLY injects the language ISO code into
#  the output file (HTML <html lang>, DOCX <w:lang>).
# -----------------------------------------------------------------------------
id: {id_pliku}
etykieta: "{etykieta}"
opis: |
  <FILL NATIVELY in {natywna_baza}: 2-4 sentences:
  - This „accent" does NOT modify the text content or phonetics.
  - It injects the language ISO code into the output file:
      HTML: the lang="..." attribute on the <html> tag
      DOCX: a <w:lang w:val="..."/> element for every text run
  - A screen reader (NVDA/JAWS) then switches the synthesizer voice correctly.
  - The ISO code is supplied by the user in the „Kod ISO" GUI field — `iso:` is empty.>
iso: ""
kategoria: naprawiacz
kolejnosc: 100

# Special mode — runs NO text-processing stage.
czysc_tekst_tts: false
normalizuj_liczby: false
usun_polskie_znaki: false
skleja_pojedyncze_litery: false
zamiany: []
"""


# =============================================================================
# PROMPT 1C: Naprawiacz tagów — tłumaczenie etykiety/opisu na natywny
# =============================================================================
def prompt_naprawiacz(id_pliku: str, etykieta: str,
                      jezyk_bazowy: str) -> str:
    natywna_baza = _natywna_nazwa_jezyka(jezyk_bazowy)
    inne_paczki = _paczki_referencyjne(jezyk_bazowy)
    return f"""# ROLE
You are an AI agent with access to the files of the „Reżyser Audio GPT"
project. You have tools: Read, Write, Edit, Glob, Grep, Bash. Task: adapt a
„tag fixer" file to a new language pack.

# PROJECT CONTEXT
- The tag fixer (`kategoria: naprawiacz`) is a SPECIAL MODE: it does NOT
  modify the text content or its phonetics. It only injects the language
  ISO code into the output files:
    * HTML: the `lang="..."` attribute on the `<html>` tag
    * DOCX: a `<w:lang w:val="..."/>` element for every text run
  This lets a screen reader (NVDA/JAWS) switch the synthesizer voice to the
  correct language.
- The ISO code is supplied by the user in the GUI (the „Kod ISO" field) —
  the `iso:` value in the file is empty (`iso: ""`).
- The file structure is IDENTICAL across all 7 deployed packs
  ({inne_paczki}); ONLY the label, description and YAML comments differ —
  all native.

# TASK
Create the file `dictionaries/{jezyk_bazowy}/akcenty/{id_pliku}.yaml` —
a tag fixer in the {natywna_baza} pack, GUI-visible label:
**{etykieta}**.

# REFERENCE FILES (open before writing)
1. `dictionaries/<any deployed>/akcenty/naprawiacz_tagow.yaml` — a
   ready-made style model. The only things you change: label + description
   + comments translated into {natywna_baza}.

# STRUCTURE REQUIREMENTS (engine)
1. `kategoria: naprawiacz` — the engine detects the special mode by this
   value.
2. `iso: ""` (empty string — the code is supplied by the user in the GUI).
3. All pipeline flags `false`: `czysc_tekst_tts`,
   `normalizuj_liczby`, `usun_polskie_znaki`, `skleja_pojedyncze_litery`.
4. `zamiany: []` (empty list — the engine applies no replacements).
5. `kolejnosc: 100` (at the end of the GUI list).

# NATIVE-LANGUAGE REQUIREMENTS
`etykieta`, `opis`, the file header, the YAML comments — everything in
{natywna_baza}. The label convention of the deployed packs (with the 🔧
emoji):
- PL: „🔧 Naprawiacz Tagów (Tylko wstrzyknięcie kodu ISO)"
- DE: „🔧 Tag-Reparateur (Nur ISO-Code-Injektion)"
- IT: „🔧 Riparatore di tag (solo iniezione del codice ISO)"

# PROCEDURE
1. Open `dictionaries/<deployed>/akcenty/naprawiacz_tagow.yaml` (Read).
2. Save the file `dictionaries/{jezyk_bazowy}/akcenty/{id_pliku}.yaml`
   (Write) with the same structure and native text in the text fields.
3. Validate that the file parses as YAML using whatever YAML tooling you
   have available (any YAML loader/linter — do not assume a particular
   shell or that Python is on PATH).
4. Done — the tag fixer is detected dynamically on app start, with no code
   regeneration.
5. In your reply report: which pack you took as the model.
"""


# =============================================================================
# SZABLON 2: Szyfr „czyste zamiany" (wzorowany na akcencie, bez algorytmu)
# =============================================================================
def szablon_szyfr_zamiany(id_pliku: str, etykieta: str,
                          jezyk_bazowy: str = "pl") -> str:
    natywna_baza = _natywna_nazwa_jezyka(jezyk_bazowy)
    return f"""# -----------------------------------------------------------------------------
#  <FILL NATIVELY in {natywna_baza}: file header, e.g. „CHIFFRE: {etykieta}"
#   (DE) / „CIFRARIO: {etykieta}" (IT) / „ШИФР: {etykieta}" (RU)>
#  „Pure replacements" template – needs no Python code.
# -----------------------------------------------------------------------------
id: {id_pliku}
etykieta: "{etykieta}"
opis: |
  <FILL NATIVELY in {natywna_baza}: describe the text effect this cipher
  produces (e.g. „every »a« becomes »@«, every »o« becomes »0«").
  Ciphers of this kind work like an accent but without the phonetic
  pipeline — they use only the `zamiany` list.>
iso: {jezyk_bazowy}
kategoria: szyfr
kolejnosc: 100

# Pipeline – for ciphers usually everything OFF except the replacements list.
czysc_tekst_tts: false
normalizuj_liczby: false
usun_polskie_znaki: false
skleja_pojedyncze_litery: false

# The actual replacements. The list is applied SEQUENTIALLY (str.replace) —
# each rule operates on the OUTPUT of the previous one. Two consequences:
#   1. digraphs/trigraphs BEFORE single letters (e.g. „ch" before „c"),
#      otherwise the single-letter rule breaks the digraph spelling;
#   2. watch for chains — if a rule introduces a character that a LATER rule
#      has as its `wzor`, that character will be replaced too.
# The leet pairs below (a→@, o→0) are order-independent (disjoint single
# letters); order only starts to matter with multi-character patterns. For
# regex patterns add `regex: true`.
zamiany:
  - {{ wzor: "a", zamiana: "@" }}
  - {{ wzor: "o", zamiana: "0" }}
  # <FILL IN: further pairs producing the effect described in the `opis:` field.
  # Copy the prompt from Manager Reguł to an AI for the full list and native description.>
"""


# =============================================================================
# PROMPT 4: Szyfr „czyste zamiany" — opis efektu + lista par + natywne komentarze
# =============================================================================
def prompt_szyfr_zamiany(id_pliku: str, etykieta: str,
                         jezyk_bazowy: str) -> str:
    natywna_baza = _natywna_nazwa_jezyka(jezyk_bazowy)
    inne_paczki = _paczki_referencyjne(jezyk_bazowy)
    return f"""# ROLE
You are an AI agent with access to the files of the „Reżyser Audio GPT"
project. You have tools: Read, Write, Edit, Glob, Grep, Bash. Task: create
a „pure replacements" cipher file inside the project tree.

# PROJECT CONTEXT
- `core_poliglota.py` — the phonetic engine. „Pure replacements" ciphers
  work like accents without the phonetic pipeline: only the `zamiany:`
  list is applied to the text.
- CRITICAL about reference models: ALL 6 ciphers deployed in the packs
  (cezar, jakanie, odwracanie, samogloskowiec, typoglikemia, waz) are
  ALGORITHMIC ciphers — they have an `algorytm:` field and do NOT contain a
  `zamiany:` list. Do NOT take them as a structure model. The only files in
  the project using the `kategoria` + `zamiany:` list format are ACCENTS
  (`akcenty/*.yaml`) — and those are your STRUCTURE model for this cipher.
- Deployed packs (as of 13.9): {inne_paczki}. Their `cezar.yaml` files are
  useful ONLY as a model of the LANGUAGE STYLE of the metadata
  (native label/description/comments), not of the structure.
- Pack for this task: `dictionaries/{jezyk_bazowy}/`
  (language {natywna_baza}).

# TASK
Create the file `dictionaries/{jezyk_bazowy}/szyfry/{id_pliku}.yaml` —
a „pure replacements" cipher named **{etykieta}**.

# REFERENCE FILES (open before writing)
1. `dictionaries/<another pack>/akcenty/<any phonetic>.yaml` — the STRUCTURE
   model for the `zamiany:` list (`wzor`→`zamiana` pairs, digraphs before
   single letters, optional `regex: true`). An accent has the phonetic
   pipeline ENABLED — in a cipher you leave it disabled (see below).
   Glob: `dictionaries/*/akcenty/*.yaml`.
2. `dictionaries/{jezyk_bazowy}/szyfry/cezar.yaml` — the model for the
   metadata STYLE of a cipher in the base pack (native
   label/description/comments, file header). Do NOT copy its body — it is
   an algorithmic cipher (`algorytm: cezar`), with no `zamiany:` list.
3. `dictionaries/{jezyk_bazowy}/podstawy.yaml` — the alphabet and
   diacritics of the base pack (useful if the cipher effect should also act
   on letters with diacritics).

# STRUCTURE REQUIREMENTS
1. Fields: `id`, `etykieta`, `opis`, `iso: {jezyk_bazowy}`,
   `kategoria: szyfr`, `kolejnosc`.
2. Pipeline (typically all OFF for ciphers):
   `czysc_tekst_tts: false`, `normalizuj_liczby: false`,
   `usun_polskie_znaki: false`, `skleja_pojedyncze_litery: false`.
3. The `zamiany:` list ordered: digraphs/trigraphs BEFORE single letters.
   For each pattern consider a `lowercase` and a `Capitalized` variant. If
   the effect should also act on diacritics (à, é, ä, ё), include them
   explicitly or add a pattern with `regex: true`.

# NATIVE-LANGUAGE REQUIREMENTS
`etykieta`, `opis`, the file header, the YAML comments — in
**{natywna_baza}**. The model for the deployed packs is visible in each
pack's `cezar.yaml` (German / Italian / Russian etc. comments).

# PROCEDURE
1. Open the reference files (Read).
2. Design a `zamiany:` list that produces the {etykieta} effect.
3. Save the file `dictionaries/{jezyk_bazowy}/szyfry/{id_pliku}.yaml`
   (Write).
4. Validate that the file parses as YAML using whatever YAML tooling you
   have available (any YAML loader/linter — do not assume a particular
   shell or that Python is on PATH).
5. Ciphers are loaded dynamically — there is no extra script to run.
   „Odśwież drzewo" in the Manager GUI + restart the app.
6. In your reply report: how many pairs `zamiany:` has and which pack you
   took as the style model.
"""


# =============================================================================
# SZABLON 3: Tryb Reżysera (wzorowany na dictionaries/pl/rezyser/tryb_audiobook.yaml)
# =============================================================================
def szablon_tryb_rezysera(id_pliku: str, etykieta: str,
                          jezyk_bazowy: str = "pl") -> str:
    natywna_baza = _natywna_nazwa_jezyka(jezyk_bazowy)
    natywny_jezyk_odp = _natywne_jezyk_odpowiedzi(jezyk_bazowy)
    natywne_streszcz = _natywne_streszczenie_yaml(jezyk_bazowy)
    return f"""# -----------------------------------------------------------------------------
#  <FILL NATIVELY in {natywna_baza}: file header, e.g. „MODUS HÖRBUCH"
#   (DE) / „MODALITÀ AUDIOLIBRO" (IT) / „РЕЖИМ АУДИОКНИГА" (RU)>
#  Template based on the Audiobook mode – fill in the role, rules and prompt.
# -----------------------------------------------------------------------------
id: {id_pliku}
etykieta: "{etykieta}"
kategoria: tryb
kolejnosc: 40

# --- Mode behavior (data-driven; REUSING an existing value needs NO Python) ---
# struktura: how the project .txt is segmented into memory anchor points AND
#   which structure buttons appear in the GUI:
#     rozdzialy  – flat chapter list (prose; like Audiobook)  ← default here
#     akty_sceny – Acts with nested Scenes (read-theatre; like Skrypt)
#     brak       – no file structure (planning / ephemeral modes)
#   A NEW header type (beyond Prolog/Akt/Scena/Rozdział/Epilog) needs CODE.
# format_wyjscia: how the engine parses the AI reply:
#     tekst       – plain prose, no JSON                       ← default here
#     skrypt_json – {{"tury":[{{mowca,tekst}}]}} (reuses the Script parser)
#     burza_json  – 3 plot options (reuses the Brainstorm parser, no file save)
#   A NEW JSON schema (other than the two above) needs CODE (a parser in
#   rezyser_ai.py) — and therefore source access, like a Story (Opowieści) mode.
#   WHY A JSON format_wyjscia MATTERS (since v18.5.1): skrypt_json / burza_json
#   make the engine REQUEST structured output (response_format=json_object) when
#   the user points the app at an OpenAI-compatible endpoint
#   (LLM_PROVIDER=openai_compat) — that is what keeps the reply parseable on
#   non-Anthropic models. The default Anthropic path ignores the flag and
#   enforces the schema through the prompt instead. So: if this mode emits JSON,
#   pick skrypt_json/burza_json (NOT tekst), and DOUBLE the braces of any literal
#   JSON example in prompt_systemowy — see the system-prompt note below.
struktura: rozdzialy
format_wyjscia: tekst

# --- AI model parameters ---
model: claude-sonnet-5
temperatura: 0.85
jezyk_odpowiedzi: {natywny_jezyk_odp}

# Should the response be saved to the project file (.txt)?
zapis_do_pliku: true

# --- System prompt ---
# Placeholders: {{world_context}}, {{jezyk_odpowiedzi}}
# NOTE: the entire system prompt MUST be in {natywna_baza}.
# Use `dictionaries/{jezyk_bazowy}/rezyser/tryb_audiobook.yaml` as a model.
# JSON TRAP: if this is a JSON mode (format_wyjscia above) and you paste a
# literal JSON example here, write its braces DOUBLED ({{{{ }}}}). A single {{ }}
# is read as a format field by str.format_map, which then silently returns the
# RAW template — and {{world_context}}/{{jezyk_odpowiedzi}} never reach the model.
prompt_systemowy: |
  # <FILL NATIVELY in {natywna_baza}: Rola/Rolle/Ruolo: THE AI ROLE NAME>

  <FILL NATIVELY: the first sentence with the instruction „You write ONLY
  in {{jezyk_odpowiedzi}}".>

  <FILL NATIVELY: a description of the mode and the expected output format.>

  ### 🌍 <FILL NATIVELY: a header like „Iron Rules of the World"
  / „Eiserne Regeln der Welt" / „Regole Ferree del Mondo">:
  {{world_context}}

  ### 📖 <FILL NATIVELY: a header like „Rules of this mode"
  / „Regeln des Modus" / „Regole della modalità">:
  1. <FILL NATIVELY: the first rule (style, format constraints)>.
  2. <FILL NATIVELY: the second rule>.
  3. **<FILL NATIVELY: a header „SCENE CLOSING" / „SZENENABSCHLUSS"
     / „CHIUSURA DELLE SCENE">:** - <NATIVELY: „DEFAULT (ANTI-CLOSURE):
     Cut off mid-action.">
     - <NATIVELY: „EXCEPTION (FINALE/EPILOGUE): If this is the ending, close
       the scene naturally.">

# --- Contextual suffixes (optional) ---
# Empty {{}} means „the engine appends no memory-state-dependent suffix".
# If you want to add suffixes – see tryb_burza.yaml as a model.
sufiksy: {{}}

# --- Reminder appended to the user instruction ---
# Also NATIVELY in {natywna_baza}.
przypomnienie_uzytkownika: |


  (<FILL NATIVELY: REMINDER / ERINNERUNG / RICORDO: a short recap of the
  mode's key rules in 1-2 sentences>.)

# --- Application-side validation ---
# „Summary" trigger words — native in {natywna_baza} (the comparison is
# lower-case, so usually type them in lowercase).
slowa_wyzwalajace:
  streszczenie:
{natywne_streszcz}

# Should the phonetic engine run on the response?
# true  – required if the mode generates dialogue with character tags.
# false – for literary prose without tags.
stosuj_akcenty_fonetyczne: false
"""


# =============================================================================
# PROMPT 5: Tryb Reżysera — pełne tłumaczenie/zaadaptowanie na język bazowy
# =============================================================================
def prompt_tryb_rezysera(id_pliku: str, etykieta: str,
                         jezyk_bazowy: str) -> str:
    natywna_baza = _natywna_nazwa_jezyka(jezyk_bazowy)
    natywny_jezyk_odp = _natywne_jezyk_odpowiedzi(jezyk_bazowy)
    inne_paczki = _paczki_referencyjne(jezyk_bazowy)
    return f"""# ROLE
You are an AI agent with access to the files of the „Reżyser Audio GPT"
project. You have tools: Read, Write, Edit, Glob, Grep, Bash. Task: create
a new Director mode (system prompt + trigger-word validation).

# PROJECT CONTEXT
- `core_rezyser.py` — the AI-mode engine (assembles the prompt from
  `world_context` + `prompt_systemowy` + the user instruction).
- `przepisy_rezysera.py` — the YAML loader for `dictionaries/<code>/rezyser/`.
  Modes are loaded dynamically; there is no extra script to run after
  adding a file.
- Deployed packs (as of 13.9): {inne_paczki} — each has 4 files in
  `rezyser/` (3 modes: audiobook/burza/skrypt + 1 postproduction). These
  are your reference for the style and convention of prompt_systemowy.
- Pack for this task: `dictionaries/{jezyk_bazowy}/`
  (language {natywna_baza}).

# DATA-DRIVEN VS CODE — read before you start
A Director mode has THREE axes. Two are now data-driven via YAML fields, so a
new mode that REUSES existing values is a pure YAML drop (works in the frozen
app, no source needed). Picking a value the engine does NOT already implement
needs CODE + source access — exactly like a Story (Opowieści) mode.
- `struktura` (file segmentation + structure buttons): REUSE `rozdzialy`
  (flat chapters, prose) or `akty_sceny` (acts+scenes) or `brak` (none). A NEW
  header type beyond Prolog/Akt/Scena/Rozdział/Epilog → CODE (regex in
  `core_rezyser._znajdz_naglowki`).
- `format_wyjscia` (reply parsing): REUSE `tekst` (plain prose), `skrypt_json`
  ({{"tury":…}}) or `burza_json` (plot options). A NEW JSON schema → CODE (a
  parser in `rezyser_ai.py`). A `tekst` mode that emits raw JSON is REFUSED at
  send time (the engine will not write JSON garbage to the file).
- `id` IDENTITY: the `id` MUST be unique in the pack. **NEVER reuse `skrypt`,
  `audiobook` or `burza`** — those ids carry bespoke panels (ElevenLabs bridge,
  screen-reader export, AI chapter titles, option buttons) and the project's
  `.mode` persistence keys off the id. A duplicate id is skipped by the loader.
  If you think „Script is the right base", do NOT clone its id — create a new id
  and set `format_wyjscia: skrypt_json` to reuse its parser.

# TASK
Create the file `dictionaries/{jezyk_bazowy}/rezyser/tryb_{id_pliku}.yaml` —
a creative AI mode named **{etykieta}** (id stem `{id_pliku}` — must be NEW).

# REFERENCE FILES (open before writing)
1. `dictionaries/{jezyk_bazowy}/rezyser/tryb_audiobook.yaml` — if it
   exists, the best style model for prompt_systemowy in {natywna_baza}.
   If the pack is only being created, use a model from another deployed pack.
2. `dictionaries/<another pack>/rezyser/tryb_audiobook.yaml` — a convention
   reference: section headers with emoji (🌍, 📖), the
   `**RULE TITLE:** description` format for numbered rules, a label with a
   native parenthetical („Hörbuch (Prosa, Kapitel, DATEI SCHREIBEN)" DE,
   „Аудиокнига (Проза, главы, ЗАПИСЫВАЕТ В ФАЙЛ)" RU).
3. `dictionaries/<another pack>/rezyser/tryb_burza.yaml` or
   `tryb_skrypt.yaml` — alternative models for modes other than literary
   prose.

# STRUCTURE REQUIREMENTS (engine)
1. Identifying fields: `id` (NEW, unique — see DATA-DRIVEN VS CODE),
   `etykieta`, `kategoria: tryb`, `kolejnosc` (int 10-90; 30 = audiobook,
   40 = brainstorm, 50 = script). Behavior fields: `struktura`
   (`rozdzialy`/`akty_sceny`/`brak`) and `format_wyjscia`
   (`tekst`/`skrypt_json`/`burza_json`) — REUSE existing values unless you are
   also adding the matching code (then you need source access).
2. AI model parameters: `model: claude-sonnet-5`,
   `temperatura` (0.7-0.9 for literary, 0.5 for scripting),
   `jezyk_odpowiedzi: {natywny_jezyk_odp}` (already matched to the pack),
   `zapis_do_pliku: true`.
3. **`prompt_systemowy:`** appended to every AI call. It MUST contain
   the placeholders `{{world_context}}` and `{{jezyk_odpowiedzi}}` (the
   engine substitutes them). The first line ALWAYS contains the phrase
   „ONLY in {{jezyk_odpowiedzi}}" in the appropriate idiom form
   (DE: „AUSSCHLIESSLICH auf"; IT: „ESCLUSIVAMENTE in"; RU: „ИСКЛЮЧИТЕЛЬНО на").
4. **`przypomnienie_uzytkownika:`** a short 1-2 sentence recap of the
   mode's key rules, appended to the user instruction.
5. **`slowa_wyzwalajace.streszczenie:`** a list of 3-5 native words
   typically used in {natywna_baza} when someone asks the AI for a summary.
   Lowercase (the engine does a lower-case comparison).
6. **`stosuj_akcenty_fonetyczne:`** `true` for modes that generate dialogue
   with character tags, `false` for literary prose.
7. `sufiksy: {{}}` (empty — unless the `tryb_burza.yaml` model shows
   memory-state-dependent suffixes that are useful for this mode).

# NATIVE-LANGUAGE REQUIREMENTS
All „human-facing" text in the file — label, header, YAML comments,
`prompt_systemowy`, `przypomnienie_uzytkownika`, the
`slowa_wyzwalajace.streszczenie` list — in **{natywna_baza}**.

# PROCEDURE
1. Open the reference files (Read).
2. Design `prompt_systemowy` — the AI role, the style rules, the
   scene-closing formula (DEFAULT anti-closure / EXCEPTION finale).
3. Save the file
   `dictionaries/{jezyk_bazowy}/rezyser/tryb_{id_pliku}.yaml` (Write).
4. Validate that the file parses as YAML using whatever YAML tooling you
   have available (any YAML loader/linter — do not assume a particular
   shell or that Python is on PATH).
5. Director modes are loaded dynamically — there is no extra script.
   „Odśwież drzewo" in the Manager + restart the app.
6. In your reply report: the model, the temperature, how many summary
   trigger words, and which pack you took as the model.
"""


# =============================================================================
# PROMPT 5B: Nowy tryb Opowieści — WYMAGA PROGRAMISTY (prompt-only)
# =============================================================================
# Tryby Opowieści są znacznie głębiej sprzężone z Pythonem niż tryby Reżysera:
# sama duplikacja pliku YAML to MARTWY KOD (nie pojawi się w GUI ani nie
# zadziała). Dlatego — analogicznie do szyfru algorytmicznego — Manager NIE
# zapisuje szablonu udającego, że działa; generuje kompletny prompt dla agenta
# AI / programisty z pełną listą punktów zaczepienia w kodzie.
# =============================================================================
def prompt_tryb_opowiesci(id_pliku: str, etykieta: str,
                          jezyk_bazowy: str) -> str:
    natywna_baza = _natywna_nazwa_jezyka(jezyk_bazowy)
    natywny_jezyk_odp = _natywne_jezyk_odpowiedzi(jezyk_bazowy)
    inne_paczki = _paczki_referencyjne(jezyk_bazowy)
    return f"""# ROLE
You are an AI agent with access to the files of the „Reżyser Audio GPT"
project (wxPython + Anthropic). You have tools: Read, Write, Edit, Glob, Grep,
Bash. Task: add a new INTERACTIVE STORY mode (Opowieści). Unlike Director
modes, a Story mode is NOT data-driven — it requires BOTH a YAML file AND
several wiring changes in Python. Dropping in a YAML file alone is dead code.

# WHY THIS NEEDS CODE (the core difference vs Director modes)
Story modes are identified by hard-coded INTEGER constants and the engine
branches on them in many places. A new mode must be threaded through every
one of those places, or it will not appear in the GUI and will crash on load.

# PROJECT CONTEXT
- `opowiesci_ai.py` — the Story engine + the mode constants and per-mode
  recipe loader (`_zaladuj_przepis`, with a pl→en fallback).
- `gui_opowiesci.py` — the Story panel: the mode RadioBox, the per-turn
  loop, the model selection, the choice-buttons logic, bespoke mechanics
  (e.g. the „fiolka" in the „Mniejsze Zło" mode).
- Recipe YAMLs live in `dictionaries/<code>/opowiesci/*.yaml`
  (baza.yaml + tryb_*.yaml + zaczatki.yaml + streszczenie.yaml + …).
- Deployed packs (as of 13.9): {inne_paczki}.
- Pack for this task: `dictionaries/{jezyk_bazowy}/` (language {natywna_baza}).

# TASK
Add an interactive Story mode **{etykieta}** (id stem: `{id_pliku}`),
creating `dictionaries/{jezyk_bazowy}/opowiesci/tryb_{id_pliku}.yaml` AND
wiring it into the Python engine + GUI.

# REFERENCE FILES (open before writing)
1. `dictionaries/{jezyk_bazowy}/opowiesci/tryb_swobodny.yaml` — the simplest
   model (free narration, no choice buttons). Best starting point for a new
   mode without bespoke mechanics.
2. `dictionaries/{jezyk_bazowy}/opowiesci/tryb_wyborow.yaml` — model for a
   mode that presents A–E choice buttons.
3. `dictionaries/{jezyk_bazowy}/opowiesci/tryb_mniejsze_zlo.yaml` — model for
   a choice mode with a bespoke mechanic (the „fiolka").
4. `opowiesci_ai.py` — the constants block and `_NAZWA_PLIKU_PER_TRYB`.
5. `gui_opowiesci.py` — the RadioBox builder, `_model_dla_trybu`, the
   choice-area activation, and the fiolka block.

# WIRING CHECKLIST (every item is mandatory — grep to find the exact lines)
1. **New integer constant** in `opowiesci_ai.py` (near `TRYB_BURZA=0`,
   `TRYB_SWOBODNY=3`, `TRYB_WYBOROW=4`, `TRYB_MNIEJSZE_ZLO=5`). APPEND the
   next free integer (e.g. `TRYB_{id_pliku.upper()} = 6`). Do NOT renumber
   the existing constants — they are persisted verbatim in each project's
   `runtime/skrypty/<nazwa>.mode`, so changing them breaks saved games.
2. **`_NAZWA_PLIKU_PER_TRYB`** in `opowiesci_ai.py`: add
   `TRYB_{id_pliku.upper()}: "tryb_{id_pliku}"`. Missing entry → `KeyError`
   when the engine loads the recipe.
3. **`_MAPA_TRYB_RB_NA_INT`** in `gui_opowiesci.py` (RadioBox index → int):
   APPEND the new constant at the END of the tuple. Appending keeps the
   existing indices (and thus old `.mode` files) intact.
4. **RadioBox labels** in `gui_opowiesci.py` (`_zbuduj_radiobox_trybu`): add
   a `t("opowiesci.tryb_{id_pliku}")` entry, in the SAME order as
   `_MAPA_TRYB_RB_NA_INT`. Then add the key `opowiesci.tryb_{id_pliku}` to
   `dictionaries/<code>/gui/ui.yaml` for EVERY deployed pack (use
   `buduj_wielojezyczne_ui.py` for the non-pl languages, or add by hand and
   proofread).
5. **`_model_dla_trybu`** in `gui_opowiesci.py`: since v18.1 every mode runs
   on one model — the method returns `oai.MODEL_NARRACJA` (`claude-sonnet-5`)
   unconditionally (the per-mode OpenAI tiers `MODEL_QUALITY`/`MODEL_DOMYSLNY`
   were retired). A new mode needs NO change here; leave it as is unless you
   deliberately want a different model for this mode.
6. **Choice buttons** (`gui_opowiesci.py`, the `_aktywuj_obszar_wyborow` /
   visibility condition `tryb in (TRYB_WYBOROW, TRYB_MNIEJSZE_ZLO)`): if the
   new mode shows A–E option buttons, add the constant to that condition.
   Otherwise leave it — the choice area stays hidden.
7. **Bespoke mechanics**: if the mode has a special mechanic like the fiolka
   (currently gated by `if tryb == TRYB_MNIEJSZE_ZLO`), that logic is pure
   Python — model it on the fiolka block, gate it on the new constant.

# RECIPE YAML STRUCTURE (`tryb_{id_pliku}.yaml`)
Copy the field set from the model file (tryb_swobodny / tryb_wyborow):
`prompt_systemowy` (placeholders such as `{{world_context}}`,
`{{jezyk_odpowiedzi}}` — keep them DOUBLED `{{ }}` if the prompt also
contains a literal JSON example, so `str.format_map` does not eat them),
`jezyk_odpowiedzi: {natywny_jezyk_odp}`, plus any per-mode keys the model
uses. All human-facing text in **{natywna_baza}**.

# NATIVE-LANGUAGE REQUIREMENTS
`prompt_systemowy`, the RadioBox label and all human-facing strings in
**{natywna_baza}**. The English checklist above is for the agent only.

# PROCEDURE
1. Read the reference files; pick the closest model (free vs choice).
2. Write `dictionaries/{jezyk_bazowy}/opowiesci/tryb_{id_pliku}.yaml`.
3. Apply the WIRING CHECKLIST edits (constant, two maps, RadioBox, model,
   choices, mechanics). Append, never renumber.
4. Add the `opowiesci.tryb_{id_pliku}` i18n key to every pack's `ui.yaml`.
5. Validate the YAML parses (any YAML loader/linter — do not assume a
   particular shell or that Python is on PATH).
6. Sanity-check `.mode` back-compat: an old saved game with mode 3/4/5 must
   still load (the integers did not move).
7. In your reply report: which integer you assigned, the model you chose,
   whether the mode uses choice buttons / bespoke mechanics, and the list of
   files you edited.
"""


# =============================================================================
# SZABLON 4: Postprodukcja (wzorowany na postprod_tytuly.yaml)
# =============================================================================
def szablon_postprodukcja(id_pliku: str, etykieta: str,
                          jezyk_bazowy: str = "pl") -> str:
    natywna_baza = _natywna_nazwa_jezyka(jezyk_bazowy)
    natywny_jezyk_odp = _natywne_jezyk_odpowiedzi(jezyk_bazowy)
    return f"""# -----------------------------------------------------------------------------
#  <FILL NATIVELY in {natywna_baza}: file header, e.g. „NACHBEARBEITUNG"
#   (DE) / „POSTPRODUZIONE" (IT) / „ПОСТОБРАБОТКА" (RU)>
#  Template based on postprod_tytuly.yaml — iteration over chapters.
# -----------------------------------------------------------------------------
id: {id_pliku}
etykieta: "{etykieta}"
kategoria: postprodukcja
kolejnosc: 20

# --- Visibility & processing (v18.12) ---
# Creative modes offering this tool (list of mode ids from tryb_*.yaml).
# Empty/omitted = every mode that writes to the project file.
dla_trybow: [audiobook]

# Processing scope:
#   per_rozdzial – the engine iterates chapter by chapter (this template),
#   calosc       – ONE call with the whole project file (report-style
#                  tools; see the commented variant at the bottom).
zakres: per_rozdzial

# Max output tokens per AI call (defaults: 256 per_rozdzial / 8000 calosc).
max_tokens_wyjscia: 256

# Optional: save the result to skrypty/<project><suffix>.txt (the GUI asks
# before overwriting). Empty/omitted = result shown only in a dialog.
# sufiks_pliku_wyniku: "_raport"

# --- AI model parameters ---
model: claude-sonnet-5
temperatura: 0.7
jezyk_odpowiedzi: {natywny_jezyk_odp}

# --- System prompt ---
# NOTE: the entire prompt MUST be in {natywna_baza}.
prompt_systemowy: |
  <FILL NATIVELY in {natywna_baza}: the AI role + a one-sentence
  output-format instruction (e.g. „You are an audiobook editor. You reply
  with a single sentence containing only the chapter title.").>

# --- User instruction template (role=user) ---
# Placeholders: {{naglowek}}, {{probka}}
prompt_uzytkownika_szablon: |
  <FILL NATIVELY in {natywna_baza}: a fragment with the {{naglowek}}
  placeholder, then the instruction for the AI, ending with the block:
    CONTENT:
    {{probka}}>

# --- Project-file iteration parameters ---
# Regex matching chapter headers. Adapt the PATTERN to the language:
#   PL: "(?i)\\\\n*(Prolog|Rozdział \\\\d+|Epilog)\\\\n*"
#   DE: "(?i)\\\\n*(Prolog|Kapitel \\\\d+|Epilog)\\\\n*"
#   IT: "(?i)\\\\n*(Prologo|Capitolo \\\\d+|Epilogo)\\\\n*"
#   EN: "(?i)\\\\n*(Prologue|Chapter \\\\d+|Epilogue)\\\\n*"
regex_podzial_rozdzialow: '<FILL IN: regex matching chapter headers in {natywna_baza}>'
min_dlugosc_fragmentu: 50
max_dlugosc_probki: 6000

# Messages shown to the user in the results window (NATIVELY in {natywna_baza}):
etykieta_fragment_zbyt_krotki: '<FILL NATIVELY: e.g. (Fragment too short)>'
etykieta_bled_brak_kredytow: '<FILL NATIVELY: e.g. (Error – no API credits)>'

# =============================================================================
# VARIANT `zakres: calosc` (v18.12) — single call with the WHOLE project file
# (report-style tools, e.g. an audit). Replace the fields above with:
#
# zakres: calosc
# max_tokens_wyjscia: 8000
# sufiks_pliku_wyniku: "_audyt"
#
# # User template uses the {{tresc}} placeholder (whole file) instead of
# # {{naglowek}}/{{probka}}; omit the field to send the raw file content
# # (the instruction then lives entirely in prompt_systemowy).
# prompt_uzytkownika_szablon: |
#   <FILL NATIVELY: header line, then the {{tresc}} placeholder,
#    then the closing instruction>
#
# # Optional World Book block ({{ksiega}} = skrypty/<project>.md content),
# # prepended BEFORE the content when that file exists:
# prompt_ksiegi_szablon: |
#   <FILL NATIVELY: header line for the World Book context block>
#   {{ksiega}}
#
# # Iteration fields (regex_podzial_rozdzialow, min_dlugosc_fragmentu,
# # max_dlugosc_probki, etykieta_*) are NOT used by `calosc`.
# =============================================================================
"""


# =============================================================================
# PROMPT 6: Postprodukcja — pełne tłumaczenie/zaadaptowanie na język bazowy
# =============================================================================
def prompt_postprodukcja(id_pliku: str, etykieta: str,
                         jezyk_bazowy: str) -> str:
    natywna_baza = _natywna_nazwa_jezyka(jezyk_bazowy)
    natywny_jezyk_odp = _natywne_jezyk_odpowiedzi(jezyk_bazowy)
    inne_paczki = _paczki_referencyjne(jezyk_bazowy)
    return f"""# ROLE
You are an AI agent with access to the files of the „Reżyser Audio GPT"
project. You have tools: Read, Write, Edit, Glob, Grep, Bash. Task: create
a postproduction (an AI tool processing the saved project file).

# PROJECT CONTEXT
- `core_rezyser.py` + `przepisy_rezysera.py` — the AI-mode engine; it loads
  postproductions from `dictionaries/<code>/rezyser/postprod_*.yaml`.
- Since v18.12 a postproduction has TWO processing scopes (`zakres:`):
  * `per_rozdzial` — the engine splits the project file (.txt) by
    `regex_podzial_rozdzialow` and sends each chunk to the AI with
    `prompt_systemowy` + `prompt_uzytkownika_szablon` (placeholders
    `{{naglowek}}` and `{{probka}}`);
  * `calosc` — ONE call with the whole file (`prompt_uzytkownika_szablon`
    with the `{{tresc}}` placeholder; optional `prompt_ksiegi_szablon`
    with `{{ksiega}}` prepends the World Book `skrypty/<project>.md`).
- Visibility: `dla_trybow:` (list of mode ids) decides in which creative
  modes the GUI offers the tool; empty/omitted = all modes that write to
  the project file. Optional `sufiks_pliku_wyniku:` (e.g. "_audyt") saves
  the result to `skrypty/<project><suffix>.txt` besides the dialog.
- Deployed packs (as of 13.9): {inne_paczki} — each has 1 postproduction
  (`postprod_tytuly.yaml`, scope per_rozdzial). A style model.
- Pack for this task: `dictionaries/{jezyk_bazowy}/`
  (language {natywna_baza}).

# TASK
Create the file `dictionaries/{jezyk_bazowy}/rezyser/postprod_{id_pliku}.yaml` —
a postproduction named **{etykieta}**.

# REFERENCE FILES (open before writing)
1. `dictionaries/{jezyk_bazowy}/rezyser/postprod_tytuly.yaml` — if it
   exists, a ready-made convention model in {natywna_baza}.
2. `dictionaries/<another pack>/rezyser/postprod_tytuly.yaml` — a
   convention reference for the deployed packs (PL/DE/IT/RU/FI/IS/EN). Note
   the native `regex_podzial_rozdzialow` (PL: Rozdział, DE: Kapitel,
   IT: Capitolo, RU: Глава, EN: Chapter).
3. (Optional) The user's `.txt` project files — if you have access to
   examples, open one to verify how chapter headers are actually named in
   {natywna_baza}.

# STRUCTURE REQUIREMENTS (engine)
1. Fields: `id`, `etykieta`, `kategoria: postprodukcja`, `kolejnosc`
   (int 10-90, e.g. 20 for a title generator). The `id` must be unique
   among postproductions and must NOT reuse a creative-mode id
   (audiobook/skrypt/burza or any `tryb_*.yaml` id) — keep identifiers
   unambiguous across the pack.
2. **`dla_trybow:`** list of creative-mode ids the tool belongs to (e.g.
   `[audiobook]`); empty/omitted = every mode that writes to the file.
   **`zakres:`** `per_rozdzial` or `calosc` — pick per the task's nature
   (short per-chapter output vs one report over the whole file). ONLY these
   two values are valid — a typo makes the engine SKIP the whole file.
   **`max_tokens_wyjscia:`** output budget per call (defaults: 256 for
   per_rozdzial, 8000 for calosc). Optional **`sufiks_pliku_wyniku:`**
   (e.g. "_audyt") — no path separators or Windows-special characters.
3. AI model parameters: `model: claude-sonnet-5`,
   `temperatura` 0.5-0.8 (we want stability),
   `jezyk_odpowiedzi: {natywny_jezyk_odp}`.
4. **`prompt_systemowy:`** the AI role, 1-2 sentences on the expected
   output format. PL model: „Jesteś redaktorem audiobooków. Twoja odpowiedź
   zawiera WYŁĄCZNIE tytuł rozdziału — jedno zdanie, bez komentarzy."
5. **`prompt_uzytkownika_szablon:`**
   - per_rozdzial: MUST contain both placeholders `{{naglowek}}` (the
     engine inserts the header) and `{{probka}}` (the chapter content);
   - calosc: uses the `{{tresc}}` placeholder (whole file); omit the field
     to send the raw file content (instruction lives in prompt_systemowy).
     Optional `prompt_ksiegi_szablon:` with `{{ksiega}}` prepends the
     World Book block when `skrypty/<project>.md` exists.
6. **`regex_podzial_rozdzialow:`** (per_rozdzial only) matched to how
   chapters are named in the project .txt files in {natywna_baza}.
   Patterns per language:
     - PL: `(?i)\\n*(Prolog|Rozdział \\d+|Epilog)\\n*`
     - DE: `(?i)\\n*(Prolog|Kapitel \\d+|Epilog)\\n*`
     - IT: `(?i)\\n*(Prologo|Capitolo \\d+|Epilogo)\\n*`
     - EN: `(?i)\\n*(Prologue|Chapter \\d+|Epilogue)\\n*`
     - RU: `(?i)\\n*(Пролог|Глава \\d+|Эпилог)\\n*`
7. `min_dlugosc_fragmentu` (per_rozdzial; typically 50 chars — shorter
   chunks are skipped with the `etykieta_fragment_zbyt_krotki` message).
8. `max_dlugosc_probki` (per_rozdzial; typically 4000-8000 chars — the
   context budget sent to the API).

# NATIVE-LANGUAGE REQUIREMENTS
All „human-facing" text in the file — label, header, YAML comments,
`prompt_systemowy`, `prompt_uzytkownika_szablon`, `prompt_ksiegi_szablon`,
the message fields (`etykieta_fragment_zbyt_krotki`,
`etykieta_bled_brak_kredytow`) — in **{natywna_baza}**.

# PROCEDURE
1. Open the reference files (Read).
2. Design `prompt_systemowy` and `prompt_uzytkownika_szablon` appropriate
   to the {etykieta} task.
3. Save the file
   `dictionaries/{jezyk_bazowy}/rezyser/postprod_{id_pliku}.yaml` (Write).
4. Validate that the file parses as YAML using whatever YAML tooling you
   have available (any YAML loader/linter — do not assume a particular
   shell or that Python is on PATH).
5. Postproductions are loaded dynamically — „Odśwież drzewo" in the Manager
   + restart the app.
6. In your reply report: the chosen `zakres` and `dla_trybow`, the model,
   the temperature, the `regex_podzial_rozdzialow` you used (per_rozdzial)
   and whether `prompt_uzytkownika_szablon` contains the placeholders
   required by that scope (`{{naglowek}}`+`{{probka}}` vs `{{tresc}}`).
"""


# =============================================================================
# SZABLON 5: podstawy.yaml dla nowego języka bazowego (minimum do startu)
# =============================================================================
def szablon_podstawy(kod_jezyka: str, etykieta_jezyka: str) -> str:
    natywna = _natywna_nazwa_jezyka(kod_jezyka)
    return f"""# =============================================================================
#  <FILL NATIVELY: file header in {natywna}, e.g. for DE:
#  „GRUNDLAGEN DER DEUTSCHEN SPRACHE"; for IT: „FONDAMENTI DELLA LINGUA ITALIANA">
# =============================================================================
#  Base file for `dictionaries/{kod_jezyka}/`. Manager Reguł already created
#  the four subfolders (akcenty/, szyfry/, rezyser/, gui/) — your work is
#  limited to filling in the sections below.
#
#  Sections required by the engine (`core_poliglota._jezyk_kompletny`):
#    1. lingua          – the `lingua.Language` enum name for the detector
#                         (POLISH/GERMAN/FRENCH/...). List:
#                         https://github.com/pemistahl/lingua-py
#    2. polskie_znaki   – mapping of the „{kod_jezyka}" language diacritics
#                         to ASCII letters (used by `usun_polskie_znaki:
#                         true` in accents).
#    3. alfabet         – the full uppercase alphabet (used by the Caesar
#                         cipher). NOTE: letters that grow under `.upper()`
#                         (e.g. ß→SS) do NOT enter the alphabet.
#    4. slowo_akcent    – native words that trigger the accent parser in
#                         Director mode (since 13.3+).
#
#  Write the comments and descriptions in this file in {natywna} — compare
#  with `dictionaries/de/podstawy.yaml` or `dictionaries/it/podstawy.yaml`
#  if you get stuck while filling it in.
# =============================================================================

id: podstawy
jezyk: {kod_jezyka}
# The `lingua.Language` enum name (uppercase, no prefix).
# Leaving it out drops the language from the detector — it can be chosen
# manually in the GUI, but mixed fragments will not be recognized.
lingua: <FILL_IN_ENUM_NAME_E_G_GERMAN>
# The label MUST be 100% in the native language {natywna}.
# Models from the deployed packs: PL: „Polski – podstawy fonetyczne"; DE:
# „Deutsch – phonetische Grundlagen"; IT: „Italiano – fondamenti
# fonetici"; RU: „Русский – фонетические основы"; FI: „Suomi –
# foneettiset perusteet"; IS: „Íslenska – hljóðfræðilegur grunnur".
etykieta: '<FILL NATIVELY: endonym + suffix in {natywna}, e.g. {natywna} – phonetische Grundlagen / fondamenti fonetici>'
opis: |
  <FILL NATIVELY in {natywna}: 2-4 sentences on what this file describes.
  PL model:
    Base rules for the <native name> language:
      1. Transliteration of diacritics (...) — stripped by
         `usun_polskie_znaki: true` in accents.
      2. Alphabet (<N> letters, uppercase) — used by the Caesar cipher.>

polskie_znaki:
  # Pairs {{ wzor: "<diacritic>", zamiana: "<ASCII>" }} — lower and upper variant.
  # <FILL IN: at minimum the diacritics of {natywna}, plus optionally other
  # European ones (e.g. Polish ąęłóśćńżź) — model: dictionaries/de/podstawy.yaml>
  - {{ wzor: "?", zamiana: "?" }}

# Full uppercase alphabet, no whitespace. Use the NATIVE alphabet in its
# NATIVE ORDER. An accented letter enters the alphabet ONLY if it is a
# distinct letter in that language — and it sits where the native order puts
# it, NOT automatically at the end (e.g. FI „...XYZÅÄÖ" — Å Ä Ö are native and
# end the Finnish alphabet; ES Ñ sits between N and O). Accented forms that
# are NOT distinct letters (e.g. FR é/à, IT à/è) do NOT enter the alphabet —
# they pass through the Caesar cipher like digits. Letters that grow under
# `.upper()` (e.g. ß→SS) are always omitted.
alfabet: '<FILL IN: native alphabet in uppercase, in native order>'

# -----------------------------------------------------------------------------
# Words that trigger the accent parser in Director mode (since 13.3+).
# core_rezyser.zastosuj_akcenty_uniwersalne builds a regex from this list that
# catches phrases „<word> X" or „X <word>" (e.g. for PL „akcent włoski" /
# „włoski akcent"). Entries MUST be in the native language, lowercase.
# Models: PL ["akcent"]; IT ["accento", "accentato"]; RU ["акцент",
# "акцентом", "говор"]; DE ["akzent", "aussprache"].
# -----------------------------------------------------------------------------
slowo_akcent:
  - "<FILL NATIVELY: at least 1 word, e.g. 'akzent'/'accento'/'akcent'>"
"""


# =============================================================================
# PROMPT 2: Nowy język bazowy – pełny pakiet (podstawy + zestaw akcentów)
# =============================================================================
def prompt_jezyk_bazowy(kod_jezyka: str, etykieta_jezyka: str) -> str:
    natywna = _natywna_nazwa_jezyka(kod_jezyka)
    inne_paczki = _paczki_referencyjne(kod_jezyka)
    return f"""# ROLE
You are an AI agent with access to the files of the „Reżyser Audio GPT"
project (wxPython + Anthropic). You have tools: Read, Write, Edit, Glob, Grep,
Bash. Your job: create the base file for a new language and prepare the
pack for engine verification.

# PROJECT CONTEXT
- `core_poliglota.py` — the phonetic engine (accents + ciphers).
  The `_jezyk_kompletny(code)` function filters packs: it requires
  `podstawy.yaml` + 4 subfolders (`akcenty/`, `szyfry/`, `rezyser/`,
  `gui/`), each with ≥1 `*.yaml` file.
- Deployed packs (as of 13.9): {inne_paczki} — these are your style models.
- Pack being created: `dictionaries/{kod_jezyka}/` — Manager Reguł already
  created the four subfolders. Your task is ONLY `podstawy.yaml`.
  You generate accents, ciphers, Director modes and the UI translation with
  separate Manager prompts, or copy them from existing packs.

# TASK
Create the file `dictionaries/{kod_jezyka}/podstawy.yaml` for the language
**{etykieta_jezyka}** (ISO 639-1 code: `{kod_jezyka}`, endonym:
**{natywna}**).

# REFERENCE FILES (open before writing)
- `dictionaries/de/podstawy.yaml` — the richest model: contains ß, umlauts,
  the full set of European diacritics (á/à/â/ã/é/í/ñ/ó/ø/ú/ý/ÿ).
- `dictionaries/it/podstawy.yaml` — a Latin model with minimal diacritics.
- `dictionaries/ru/podstawy.yaml` — a model for a non-Latin alphabet.
- `dictionaries/pl/podstawy.yaml` — the minimal reference, the base pack.
Pick the model closest in character to {natywna} (Latin/Cyrillic alphabet,
presence/absence of diacritics such as ä/ö/ç/ß).

# STRUCTURE REQUIREMENTS (engine)
1. **`id: podstawy`** and **`jezyk: {kod_jezyka}`** — identifying fields.
2. **`lingua:`** — the `lingua.Language` enum name in UPPERCASE English,
   without prefix. List (74 languages):
   https://github.com/pemistahl/lingua-py.
   Most common: POLISH, ENGLISH, GERMAN, FRENCH, SPANISH, PORTUGUESE,
   ITALIAN, RUSSIAN, FINNISH, ICELANDIC, JAPANESE, CHINESE.
   If the language is missing, write `# BRAK_W_LINGUA` in a comment above
   the field and leave the field commented out (the engine falls back to
   manual selection).
3. **`polskie_znaki:`** — a list of `{{ wzor, zamiana }}` pairs describing
   the diacritics of language {kod_jezyka} → ASCII. Each diacritic in both
   variants: lower + upper. Letters that grow under `.upper()` (e.g. ß→SS)
   ALWAYS go here, NEVER in `alfabet`.
4. **`alfabet:`** — a string of UPPERCASE letters with no spaces. Use the
   NATIVE alphabet of the language in its NATIVE ORDER. Accented letters go
   into the alphabet ONLY if they are genuinely distinct letters in that
   language's order — and they belong wherever that order places them, not
   automatically at the end (e.g. FI Å Ä Ö are native, so they sit at the
   end as in Finnish; ES Ñ sits between N and O; IS keeps its full native
   sequence). Accented forms that are NOT distinct letters (e.g. FR é/à, IT
   à/è) do NOT enter `alfabet` at all — they pass through the Caesar cipher
   unchanged, like digits. And any letter that grows under `.upper()`
   (ß→SS) is omitted regardless. Used by the Caesar cipher.
5. **`slowo_akcent:`** (13.3+ contract) — a list of native words that
   trigger the accent parser in Director mode. All entries lowercase.
   Models: PL `["akcent"]`; DE `["akzent", "aussprache"]`;
   IT `["accento", "accentato"]`; RU `["акцент", "акцентом", "говор"]`.
   For inflecting languages add the 2-3 most common forms.

# NATIVE-LANGUAGE REQUIREMENTS
You write the `etykieta:` and `opis:` fields and all YAML comments in the
file in **{natywna}**. The label model from the 7 deployed packs:
- pl: „Polski – podstawy fonetyczne"
- en: „English – phonetic basics"
- de: „Deutsch – phonetische Grundlagen"
- it: „Italiano – fondamenti fonetici"
- ru: „Русский – фонетические основы"
- fi: „Suomi – foneettiset perusteet"
- is: „Íslenska – hljóðfræðilegur grunnur"
Mixing Polish phrases with native ones (e.g. „French – podstawy fonetyczne")
is a CRITICAL error.

# PROCEDURE
1. Open the reference files (Read).
2. Design the contents of `podstawy.yaml` — a complete `polskie_znaki`
   section (all diacritics of language {natywna} in both cases), the full
   `alfabet`, the `slowo_akcent` list.
3. Save the file at `dictionaries/{kod_jezyka}/podstawy.yaml` (Write).
4. Validate that the file parses as YAML using whatever YAML tooling you
   have available (any YAML loader/linter — do not assume a particular
   shell or that Python is on PATH).
5. Confirm completeness: loading `core_poliglota._jezyk_kompletny(
   '{kod_jezyka}')` returns `False` until the pack has accents/ciphers/modes.
   That is expected at this stage; report to the user that further Manager
   Reguł prompts are needed.
6. In your reply report: how many entries `polskie_znaki` has, how many
   letters `alfabet` has, and the values you set for `lingua`, `etykieta`,
   `slowo_akcent`.
"""


# =============================================================================
# PROMPT 3: Szyfr algorytmiczny – poproś AI o specyfikację + zmianę kodu
# =============================================================================
def prompt_szyfr_algorytm(id_pliku: str, etykieta: str,
                          opis_efektu: str,
                          jezyk_bazowy: str = "pl") -> str:
    natywna_baza = _natywna_nazwa_jezyka(jezyk_bazowy)
    return f"""# ROLE
You are an AI agent with access to the files of the „Reżyser Audio GPT"
project. You have tools: Read, Write, Edit, Glob, Grep, Bash. Task: add a
new algorithmic cipher to the project — this requires **two** changes: a
YAML file + a Python function in `core_poliglota.py`.

# PROJECT CONTEXT
- `core_poliglota.py` — the phonetic engine + algorithm dispatcher. The
  `_ALGORYTMY` map maps a cipher `id` to the Python function implementing
  the algorithm. A `kategoria: szyfr` YAML file with an `algorytm: <id>`
  field tells the engine to call `_algorytm_<id>` instead of a `zamiany:`
  list.
- Existing algorithms (reference): odwracanie, typoglikemia, jakanie,
  samogloskowiec, waz. All in `core_poliglota.py` as `_algorytm_*`.
- Pack for this task: `dictionaries/{jezyk_bazowy}/`
  (language {natywna_baza}).

# TASK
Design and implement the algorithmic cipher **{etykieta}** (id: `{id_pliku}`).

EFFECT DESCRIPTION (from the user):
> {opis_efektu}

# REFERENCE FILES (open before writing)
1. `core_poliglota.py` — look for the `_algorytm_*` functions (e.g.
   `_algorytm_odwracanie`, `_algorytm_typoglikemia`) and the `_ALGORYTMY`
   map. Note the signature `(tekst: str, regula: dict) -> str` and how
   `random` is used.
2. `dictionaries/pl/szyfry/odwracanie.yaml` — the model for the
   `rozwiniecia:` convention (regexes expanding abbreviations „itd." → „i
   tak dalej" BEFORE the main processing). Rules: word boundaries
   `\\b...\\b`, optional dot `\\.?`, optional comma `,?`, two variants for
   common typos („m.in." vs „mi.in."), a space after the expansion.
3. `dictionaries/{jezyk_bazowy}/szyfry/cezar.yaml` — the YAML style model
   for the base pack (native comments).

# YAML STRUCTURE REQUIREMENTS
```yaml
id: {id_pliku}
etykieta: "{etykieta}"
opis: |
  <2-4 sentences in {natywna_baza} — what the cipher does>.
iso: {jezyk_bazowy}
kategoria: szyfr
kolejnosc: 100
algorytm: {id_pliku}

# <Optional parameters read from regula['<key>'] by the Python function>
# parametr_1: value
```

# PYTHON CODE REQUIREMENTS (`core_poliglota.py`)
1. A function `_algorytm_{id_pliku}(tekst: str, regula: dict) -> str` —
   the same signature as the existing algorithms.
2. An entry in the `_ALGORYTMY` map: `"{id_pliku}": _algorytm_{id_pliku}`.
3. **Idempotence**: running twice with the same seed returns the same
   result (unless randomness is intentional — then document it).
4. Operate char-by-char or word-by-word, **preserve** whitespace and
   punctuation (unless the effect requires changing them).
5. Randomness: use `random` (already imported in core_poliglota.py).
6. Do **NOT** introduce new external dependencies.

# NATIVE-LANGUAGE REQUIREMENTS
`etykieta`, `opis`, the YAML comments in {natywna_baza}. The comments and
docstring in `core_poliglota.py` stay in Polish (per the engine convention
— Polish is the project's development language).

# PROCEDURE
1. Open the reference files (Read).
2. Design the algorithm in your head + any YAML-configurable parameters.
3. Edit `core_poliglota.py` — add the `_algorytm_{id_pliku}` function and
   the `_ALGORYTMY` entry.
4. Write `dictionaries/{jezyk_bazowy}/szyfry/{id_pliku}.yaml`.
5. Validate that the YAML file parses using whatever YAML tooling you have
   available (any YAML loader/linter — do not assume a particular shell or
   that Python is on PATH).
6. Confirm the dispatch wiring: `{id_pliku}` must be present as a key in
   `core_poliglota._ALGORYTMY` (load the module with your Python tooling and
   check, or grep the `_ALGORYTMY` map literal).
7. Consider writing a unit test (idempotence, whitespace preservation).
8. In your reply report: how many lines of code you added in
   `core_poliglota.py`, the algorithm parameters, and the idempotence test
   result (if you ran one).

# HINT: THE `rozwiniecia:` CONVENTION (if you use it)
If the algorithm performs text substitutions BEFORE the main processing
(e.g. expanding abbreviations „itd." into „i tak dalej"), follow
`dictionaries/pl/szyfry/odwracanie.yaml::rozwiniecia` — keep the rules
(word boundaries, optional dot/comma, specific-before-general ordering, no
`regex: true` in `rozwiniecia` — regex is the default there). Without these
rules the regex catches word fragments (e.g. „tj" inside „atakujący") and
creates artifacts.
"""


# =============================================================================
# Diagnostyka: wykrywanie liter „rosnących" przy .upper()
# =============================================================================
def problematic_letters_in_alphabet(alfabet: str) -> list[str]:
    """Zwraca listę liter, które w Unicode rosną podczas `.upper()`.

    Tło problemu
    ------------
    Szyfr Cezara (``core_poliglota.py``) operuje na wielkich literach
    alfabetu. Niektóre znaki Unicode przy ``.upper()`` rozbijają się
    na WIĘCEJ niż jeden znak (ß→SS, ĳ→ĲIJ, ﬀ→FF, ﬃ→FFI), przez co
    indeksowanie listy liter w Cezarze wywraca się. Takie litery NIE
    powinny trafiać do pola ``alfabet`` w ``podstawy.yaml`` — patrz
    „Zasada żelazna nr 5" w ``prompt_jezyk_bazowy``.

    Args:
        alfabet: ciąg znaków (np. ``"ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÜß"``).

    Returns:
        Lista liter problematycznych (w kolejności pojawiania się).
        Pusta lista = alfabet bezpieczny dla szyfru Cezara.

    Example:
        >>> problematic_letters_in_alphabet("ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÜß")
        ['ß']
        >>> problematic_letters_in_alphabet("ABCDEFGHIJKLMNOPQRSTUVWXYZÅÄÖ")
        []
    """
    return [ch for ch in alfabet if len(ch.upper()) != 1]


# =============================================================================
# API: jedno wejście dla GUI
# =============================================================================
def zbuduj_wynik(
    typ: str,
    *,
    id_pliku: str,
    etykieta: str,
    iso: str = "",
    jezyk_bazowy: str = "pl",
    opis_efektu: str = "",
) -> dict:
    """Buduje pakiet (yaml + prompt + docelowa ścieżka) dla kreatora.

    Args:
        typ:           jedna ze stałych TYP_* zdefiniowanych powyżej.
        id_pliku:      identyfikator (walidacja w GUI: ASCII lower_snake).
        etykieta:      nazwa wyświetlana użytkownikowi (swobodny tekst).
        iso:           dwuliterowy kod docelowego języka (dla akcentu
                       i `podstawy`).
        jezyk_bazowy:  folder w dictionaries/, w którym ma powstać plik
                       (dla jezyk_bazowy = nowy kod).
        opis_efektu:   opis efektu dla szyfru algorytmicznego.

    Returns:
        Słownik z kluczami: tryb, yaml, prompt, docelowy, uwagi.
    """
    if typ == TYP_AKCENT_OCZYSZCZENIE:
        return {
            "tryb":     "SZABLON_I_PROMPT",
            "yaml":     szablon_oczyszczenie(id_pliku, etykieta, jezyk_bazowy),
            "prompt":   prompt_oczyszczenie(id_pliku, etykieta, jezyk_bazowy),
            "docelowy": f"{jezyk_bazowy}/akcenty/{id_pliku}.yaml",
            "uwagi": _uwagi("akcent_oczyszczenie",
                            jezyk_bazowy=jezyk_bazowy, id_pliku=id_pliku),
        }

    if typ == TYP_AKCENT_NAPRAWIACZ:
        return {
            "tryb":     "SZABLON_I_PROMPT",
            "yaml":     szablon_naprawiacz(id_pliku, etykieta, jezyk_bazowy),
            "prompt":   prompt_naprawiacz(id_pliku, etykieta, jezyk_bazowy),
            "docelowy": f"{jezyk_bazowy}/akcenty/{id_pliku}.yaml",
            "uwagi": _uwagi("akcent_naprawiacz",
                            jezyk_bazowy=jezyk_bazowy, id_pliku=id_pliku),
        }

    if typ == TYP_AKCENT:
        return {
            "tryb":     "SZABLON_I_PROMPT",
            "yaml":     szablon_akcent(id_pliku, etykieta, iso, jezyk_bazowy),
            "prompt":   prompt_akcent(id_pliku, etykieta, iso, jezyk_bazowy),
            "docelowy": f"{jezyk_bazowy}/akcenty/{id_pliku}.yaml",
            "uwagi": _uwagi("akcent",
                            jezyk_bazowy=jezyk_bazowy, id_pliku=id_pliku),
        }

    if typ == TYP_SZYFR_ZAMIANY:
        return {
            "tryb":     "SZABLON_I_PROMPT",
            "yaml":     szablon_szyfr_zamiany(id_pliku, etykieta, jezyk_bazowy),
            "prompt":   prompt_szyfr_zamiany(id_pliku, etykieta, jezyk_bazowy),
            "docelowy": f"{jezyk_bazowy}/szyfry/{id_pliku}.yaml",
            "uwagi": _uwagi("szyfr_zamiany",
                            jezyk_bazowy=jezyk_bazowy, id_pliku=id_pliku),
        }

    if typ == TYP_TRYB_REZYSERA:
        # Konwencja: tryby Reżysera mają prefix `tryb_` w nazwie pliku.
        nazwa_pliku = f"tryb_{id_pliku}" if not id_pliku.startswith("tryb_") \
                      else id_pliku
        return {
            "tryb":     "SZABLON_I_PROMPT",
            "yaml":     szablon_tryb_rezysera(id_pliku, etykieta, jezyk_bazowy),
            "prompt":   prompt_tryb_rezysera(id_pliku, etykieta, jezyk_bazowy),
            "docelowy": f"{jezyk_bazowy}/rezyser/{nazwa_pliku}.yaml",
            "uwagi": _uwagi("tryb_rezysera",
                            jezyk_bazowy=jezyk_bazowy, id_pliku=id_pliku),
        }

    if typ == TYP_TRYB_OPOWIESCI:
        # Prompt-only (jak szyfr algorytmiczny): tryb Opowieści wymaga
        # okablowania w Pythonie (stała int + dwie mapy + RadioBox + model),
        # więc Manager NIE zapisuje szablonu udającego, że działa.
        nazwa_pliku = f"tryb_{id_pliku}" if not id_pliku.startswith("tryb_") \
                      else id_pliku
        return {
            "tryb":     "PROMPT",
            "yaml":     "",
            "prompt":   prompt_tryb_opowiesci(id_pliku, etykieta, jezyk_bazowy),
            "docelowy": f"{jezyk_bazowy}/opowiesci/{nazwa_pliku}.yaml",
            "uwagi": _uwagi("tryb_opowiesci",
                            jezyk_bazowy=jezyk_bazowy, id_pliku=id_pliku),
        }

    if typ == TYP_POSTPRODUKCJA:
        nazwa_pliku = f"postprod_{id_pliku}" if not id_pliku.startswith("postprod_") \
                      else id_pliku
        return {
            "tryb":     "SZABLON_I_PROMPT",
            "yaml":     szablon_postprodukcja(id_pliku, etykieta, jezyk_bazowy),
            "prompt":   prompt_postprodukcja(id_pliku, etykieta, jezyk_bazowy),
            "docelowy": f"{jezyk_bazowy}/rezyser/{nazwa_pliku}.yaml",
            "uwagi": _uwagi("postprodukcja",
                            jezyk_bazowy=jezyk_bazowy, id_pliku=id_pliku),
        }

    if typ == TYP_JEZYK_BAZOWY:
        return {
            "tryb":     "SZABLON_I_PROMPT",
            "yaml":     szablon_podstawy(id_pliku, etykieta),
            "prompt":   prompt_jezyk_bazowy(id_pliku, etykieta),
            "docelowy": f"{id_pliku}/podstawy.yaml",
            "uwagi": _uwagi("jezyk_bazowy",
                            jezyk_bazowy=jezyk_bazowy, id_pliku=id_pliku),
        }

    if typ == TYP_SZYFR_ALGORYTM:
        return {
            "tryb":     "PROMPT",
            "yaml":     "",
            "prompt":   prompt_szyfr_algorytm(id_pliku, etykieta, opis_efektu, jezyk_bazowy),
            "docelowy": f"{jezyk_bazowy}/szyfry/{id_pliku}.yaml",
            "uwagi": _uwagi("szyfr_algorytm",
                            jezyk_bazowy=jezyk_bazowy, id_pliku=id_pliku),
        }

    raise ValueError(f"Nieznany typ reguły: {typ!r}")
