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

import sys

import i18n


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
TYP_POSTPRODUKCJA        = "postprodukcja"

# Metadane prezentowane w ComboBox-ie kreatora (kolejność = priorytet A11y)
LISTA_TYPOW: list[tuple[str, str, str]] = [
    # (id, etykieta, krótki opis)
    (
        TYP_AKCENT,
        "Akcent fonetyczny (cross-language, np. szwedzki, fiński)",
        "Plik w <jezyk>/akcenty/<id>.yaml z `kategoria: akcent`. Tekst paczki "
        "bazowej (jezyk_bazowy) jest transliterowany pod wymowę docelowego "
        "syntezatora (iso != jezyk_bazowy). Manager tworzy szablon + prompt "
        "dla agenta AI, który zaprojektuje listę `zamiany:`.",
    ),
    (
        TYP_AKCENT_OCZYSZCZENIE,
        "Akcent czyszczący (preprocessor, bez fonetyki)",
        "Plik w <jezyk>/akcenty/<id>.yaml z `kategoria: oczyszczenie`. "
        "Czyści tekst pod TTS (usuwa bełkot, normalizuje liczby) BEZ zmiany "
        "fonetyki. iso == jezyk_bazowy. Manager tworzy szablon (gotowy "
        "wzorzec) + prompt do tłumaczenia etykiety/opisu na natywny.",
    ),
    (
        TYP_AKCENT_NAPRAWIACZ,
        "Naprawiacz tagów (wstrzykuje ISO do HTML/DOCX)",
        "Plik w <jezyk>/akcenty/<id>.yaml z `kategoria: naprawiacz`. NIE "
        "modyfikuje treści — wstrzykuje kod ISO języka do plików wynikowych "
        "(<html lang>, <w:lang>). iso pusty (kod podaje user w GUI). Manager "
        "tworzy szablon + prompt do tłumaczenia etykiety/opisu na natywny.",
    ),
    (
        TYP_SZYFR_ZAMIANY,
        'Nowy szyfr typu „czyste zamiany"',
        "Plik w <jezyk>/szyfry/. Manager tworzy szablon + prompt dla AI, "
        "który przetłumaczy etykiety/komentarze na język natywny paczki "
        "i wygeneruje listę par wzor→zamiana.",
    ),
    (
        TYP_TRYB_REZYSERA,
        "Nowy tryb Reżysera (tryb twórczy)",
        "Plik w <jezyk>/rezyser/tryb_*.yaml. Szablon oparty o tryb "
        "Audiobook + prompt dla AI tłumaczący prompt_systemowy, "
        "przypomnienie_uzytkownika i slowa_wyzwalajace na język natywny "
        "paczki bazowej.",
    ),
    (
        TYP_POSTPRODUKCJA,
        "Nowa postprodukcja (iteracja po rozdziałach)",
        "Plik w <jezyk>/rezyser/postprod_*.yaml. Szablon z polami na "
        "prompt, regex i parametry iteracji + prompt dla AI generujący "
        "natywny prompt_systemowy i regex_podzial_rozdzialow.",
    ),
    (
        TYP_JEZYK_BAZOWY,
        "Nowy język bazowy (np. en, de, fr)",
        "Tworzy folder <jezyk>/ z podstawy.yaml i podfolderami akcenty/, szyfry/, "
        "rezyser/, gui/. Dane fonetyczne generuje AI z promptu; tłumaczenie UI – "
        "buduj_wielojezyczne_ui.py; tryby Reżysera kopiuje się z pl/rezyser/ "
        "(wymagany ≥1 plik tryb_*.yaml, żeby silnik uznał język za kompletny).",
    ),
    (
        TYP_SZYFR_ALGORYTM,
        "Nowy szyfr algorytmiczny (WYMAGA PROGRAMISTY)",
        "Algorytmy (np. odwracanie, typoglikemia) wymagają funkcji w "
        "core_poliglota.py. Manager daje tylko prompt dla AI z opisem zadania.",
    ),
]


# =============================================================================
# Helpery natywności (od 13.9): w ramach audytu promptów po wdrożeniu siedmiu
# kompletnych paczek (pl/en/fi/is/it/ru/de) szablony i prompty zaczynają
# zwracać domyślne wartości w języku bazowym, jeśli ten jest już w projekcie.
# Dla nieobecnych paczek (np. fr/es) szablon dostaje marker
# „<UZUPEŁNIJ NATYWNIE: …>", żeby AI lub user świadomie domknęli temat.
# =============================================================================
_NATYWNE_JEZYK_ODPOWIEDZI: dict[str, str] = {
    # forma zależna od idiomu prompta — tak jak istnieje w paczce po wdrożeniu
    "pl": "polsku",
    "en": "English",
    "fi": "suomeksi",
    "is": "á íslensku",
    "it": "italiano",
    "ru": "по-русски",
    "de": "Deutsch",
    "fr": "français",
    "es": "español",
}

_NATYWNE_STRESZCZENIE: dict[str, list[str]] = {
    # 4 słowa wyzwalające „streszczenie" — synchronizowane z
    # dictionaries/<kod>/rezyser/tryb_audiobook.yaml::slowa_wyzwalajace
    "pl": ["streszcz", "streść", "podsumuj", "podsumowanie"],
    "en": ["summarize", "summarise", "summary", "recap"],
    "fi": ["tiivistä", "tee yhteenveto", "yhteenveto", "kertaa"],
    "is": ["samantekt", "dragðu saman", "gerðu samantekt", "endurtaktu"],
    "it": ["riassumi", "riassunto", "sintetizza", "sommario"],
    "ru": ["обобщи", "сделай резюме", "резюме", "подытожь"],
    "de": ["fasse zusammen", "Zusammenfassung", "zusammenfassen", "Überblick"],
    "fr": ["résume", "résumé", "résumer", "vue d'ensemble"],
    "es": ["resume", "resumen", "resumir", "sinopsis"],
}

_NATYWNA_NAZWA_JEZYKA: dict[str, str] = {
    # Endonim — tak jak człowiek z danego kraju nazwie własny język.
    # Używane w prompcie, żeby pokazać AI „jaki ma być sufiks etykiety".
    "pl": "Polski",
    "en": "English",
    "fi": "Suomi",
    "is": "Íslenska",
    "it": "Italiano",
    "ru": "Русский",
    "de": "Deutsch",
    "fr": "Français",
    "es": "Español",
}


def _natywne_jezyk_odpowiedzi(kod: str) -> str:
    """Zwraca natywną wartość pola ``jezyk_odpowiedzi`` lub marker do uzupełnienia.

    Args:
        kod: kod ISO języka bazowego paczki (folder w ``dictionaries/``).

    Returns:
        ``"polsku"``, ``"Deutsch"``, ``"по-русски"`` itp. dla wdrożonych paczek
        lub ``"<UZUPEŁNIJ NATYWNIE: forma typu 'polsku'/'Deutsch'>"`` dla nowych
        kodów (fr/es itp.) — komunikuje, że AI musi wybrać właściwą formę
        gramatyczną sama.
    """
    # Fallback owinięty w apostrofy YAML, żeby `<...>` nie zostało
    # zinterpretowane jako tag YAML i żeby parsowanie szablonu nie wybuchało
    # w testach (real-world: i tak user MUSI zastąpić marker natywną wartością).
    return _NATYWNE_JEZYK_ODPOWIEDZI.get(
        kod,
        "'<UZUPEŁNIJ NATYWNIE: forma odpowiednia dla prompta, np. polsku / Deutsch / italiano>'",
    )


def _natywne_streszczenie_yaml(kod: str) -> str:
    """Zwraca blok YAML z natywnymi słowami wyzwalającymi streszczenie.

    Format dopasowany do bezpośredniego wstrzyknięcia w ``szablon_tryb_rezysera``
    pod kluczem ``slowa_wyzwalajace.streszczenie``. Dla nieobecnych paczek
    zwraca pojedynczy marker do uzupełnienia.
    """
    slowa = _NATYWNE_STRESZCZENIE.get(kod)
    if slowa is None:
        return "    - <UZUPEŁNIJ NATYWNIE: 4 słowa typu 'streszcz'/'summarize'/'fasse zusammen'>"
    return "\n".join(f"    - {slowo}" for slowo in slowa)


def _natywna_nazwa_jezyka(kod: str) -> str:
    """Endonim języka — np. ``"Deutsch"`` dla ``"de"``."""
    return _NATYWNA_NAZWA_JEZYKA.get(kod, kod)


# =============================================================================
# Pomocnicze: lista paczek wdrożonych (stan na 14.0 — synchronizować ręcznie
# przy każdym pełnym wdrożeniu nowego języka). Używane w promptach agentowych
# jako podpowiedź „skąd brać wzorzec stylu".
# =============================================================================
_PACZKI_WDROZONE: tuple[str, ...] = ("pl", "en", "de", "es", "fi", "fr", "is", "it", "ru")


def _paczki_referencyjne(jezyk_bazowy: str) -> str:
    """Zwraca CSV listę kodów paczek wdrożonych BEZ paczki bazowej.

    Używane w prompcie agentowym, gdzie podpowiadamy agentowi „otwórz
    `dictionaries/<jedna z tych>/<typ>/<plik>.yaml`, żeby zobaczyć
    konwencję stylu". Wykluczamy paczkę bazową, bo gdyby agent miał ją
    czytać, znalazłby pusty folder (paczka dopiero powstaje).
    """
    inne = [k for k in _PACZKI_WDROZONE if k != jezyk_bazowy]
    return ", ".join(inne) if inne else "(brak — projekt ma tylko tę paczkę)"


# =============================================================================
# SZABLON 1: Akcent fonetyczny (wzorowany na dictionaries/pl/akcenty/finski.yaml)
# =============================================================================
def szablon_akcent(id_pliku: str, etykieta: str, iso: str,
                   jezyk_bazowy: str = "pl") -> str:
    """Zwraca tekst YAML szablonu akcentu – gotowy do zapisu na dysk.

    Format trzymany 1-do-1 z istniejącymi plikami, żeby silnik
    (``core_poliglota.py``) bez modyfikacji wciągnął akcent. Komentarze
    pozostawione w neutralnej formie z markerami ``<UZUPEŁNIJ NATYWNIE>``
    — finalna wersja powinna mieć je w języku paczki bazowej (DE, IT itd.).
    """
    natywna_baza = _natywna_nazwa_jezyka(jezyk_bazowy)
    return f"""# -----------------------------------------------------------------------------
#  <UZUPEŁNIJ NATYWNIE w {natywna_baza}: AKZENT {etykieta} / ACCENTO {etykieta} / ...>
#  <Krótki nagłówek o przeznaczeniu akcentu, wzorzec:
#   dictionaries/{jezyk_bazowy}/akcenty/<dowolny>.yaml>
# -----------------------------------------------------------------------------
id: {id_pliku}
etykieta: "{etykieta}"
opis: |
  <UZUPEŁNIJ NATYWNIE w {natywna_baza}: 2-4 zdania o tym, pod jaki
  syntezator TTS przeznaczony jest ten akcent i jakie zjawiska fonetyczne
  wymusza (ubezdźwięcznienie, tłumienie syczenia, transliteracja itd.).>
iso: {iso}
kategoria: akcent
kolejnosc: 100

# --- Pipeline przetwarzania (true/false) ---
# czysc_tekst_tts        – usuwa bełkot („khh", gwiazdki, hashtagi)
# normalizuj_liczby      – zamienia cyfry na słowa (zgodnie z gramatyką {natywna_baza})
# usun_polskie_znaki     – usuwa diakrytyki języka bazowego ({jezyk_bazowy}) wg
#                          mapowania w `dictionaries/{jezyk_bazowy}/podstawy.yaml::polskie_znaki`
# skleja_pojedyncze_litery – scala wiszące pojedyncze litery („w y s" → „wys")
czysc_tekst_tts: true
normalizuj_liczby: true
usun_polskie_znaki: true
skleja_pojedyncze_litery: true

# --- Właściwe zamiany fonetyczne ---
# ZŁOTA ZASADA #1 (rozmiar): trigramy/dwuznaki (sch, tsch, ch, cz, sz, rz) PRZED
# jednoznakami (c, s, z, r), bo inaczej „c → ts" rozwali zapis „ch", „cz".
#
# ZŁOTA ZASADA #2 (sekwencyjność — KRYTYCZNE): silnik aplikuje listę
# `zamiany:` SEKWENCYJNIE przez `str.replace` (lub `re.sub` przy `regex: true`),
# każda reguła operuje na WYJŚCIU poprzedniej. Jeśli reguła A wprowadza znak,
# który reguła B (późniejsza) ma jako `wzor`, B ZJE wynik A.
# Klasyczna pułapka: `ñ → nj` PRZED `j → x` daje `ñ → nx` (nie `nj`!), bo
# nowe „j" wprowadzone przez pierwszą regułę zostaje złapane przez drugą.
# Reguła kolejności: NAJPIERW zamień TARGET (literę używaną później jako
# `zamiana` w innych regułach) na coś bezpiecznego, DOPIERO POTEM wprowadzaj
# SOURCE wprowadzającą ten target. Dla przykładu ES: najpierw `j → x`,
# potem `ñ → nj`. Test: zdanie zawierające OBIE litery musi mieć oba akcenty
# w wyniku (dla ES „Niño de paja juega" → musi mieć i akcent ñ, i akcent j).
#
# Dla wzorów regex dodaj `regex: true`.
zamiany:
  - {{ wzor: "ch", zamiana: "h"  }}
  - {{ wzor: "Ch", zamiana: "H"  }}
  # <UZUPEŁNIJ: kolejne pary specyficzne dla języka docelowego.
  # Skopiuj prompt z Managera Reguł do AI po pełną listę zamian
  # — prompt zna kontekst paczki {jezyk_bazowy} i wygeneruje natywne komentarze.>
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
project (wxPython + OpenAI). You have tools: Read, Write, Edit, Glob, Grep,
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
#  <UZUPEŁNIJ NATYWNIE w {natywna_baza}: nagłówek pliku, np. dla DE:
#   „TEXTBEREINIGUNG MIT ZAHLENNORMALISIERUNG"; dla IT: „PULIZIA DEL TESTO
#   CON NORMALIZZAZIONE DEI NUMERI">
#  Domyślny wariant „Żaden akcent" — sprząta tekst pod czytnik ekranu.
# -----------------------------------------------------------------------------
id: {id_pliku}
etykieta: "{etykieta}"
opis: |
  <UZUPEŁNIJ NATYWNIE w {natywna_baza}: 2-4 zdania o tym, że ten „akcent"
  nie nakłada fonetyki, a tylko uruchamia czyszczenie pod TTS (usuwa
  bełkot typu „khh", gwiazdki, hashtagi, kropki) {"oraz zamienia cyfry na słowa" if not bez_liczb else "(BEZ normalizacji liczb — przydatne dla książek z dużą liczbą dat/numerów)"}.>
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
#  <UZUPEŁNIJ NATYWNIE w {natywna_baza}: nagłówek pliku, np. dla DE:
#   „TAG-REPARATEUR (Sondermodus)"; dla IT: „RIPARATORE DI TAG (modalità
#   speciale)"; dla RU: „ВОССТАНОВИТЕЛЬ ТЕГОВ (специальный режим)">
#  NIE modyfikuje treści — wstrzykuje TYLKO kod ISO języka do pliku
#  wynikowego (HTML <html lang>, DOCX <w:lang>).
# -----------------------------------------------------------------------------
id: {id_pliku}
etykieta: "{etykieta}"
opis: |
  <UZUPEŁNIJ NATYWNIE w {natywna_baza}: 2-4 zdania:
  - Ten „akcent" NIE modyfikuje treści ani fonetyki tekstu.
  - Wstrzykuje kod ISO języka do pliku wynikowego:
      HTML: atrybut lang="..." w znaczniku <html>
      DOCX: element <w:lang w:val="..."/> dla każdego biegu tekstu
  - Czytnik ekranu (NVDA/JAWS) poprawnie przełącza głos syntezatora.
  - Kod ISO podaje user ręcznie w polu „Kod ISO" w GUI — `iso:` jest puste.>
iso: ""
kategoria: naprawiacz
kolejnosc: 100

# Tryb specjalny — NIE uruchamia żadnego etapu przetwarzania tekstu.
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
#  <UZUPEŁNIJ NATYWNIE w {natywna_baza}: nagłówek pliku, np. „CHIFFRE: {etykieta}"
#   (DE) / „CIFRARIO: {etykieta}" (IT) / „ШИФР: {etykieta}" (RU)>
#  Szablon „czyste zamiany" – nie wymaga kodu Pythona.
# -----------------------------------------------------------------------------
id: {id_pliku}
etykieta: "{etykieta}"
opis: |
  <UZUPEŁNIJ NATYWNIE w {natywna_baza}: opisz efekt tekstowy, jaki uzyskuje
  ten szyfr (np. „każde »a« staje się »@«, każde »o« staje się »0«").
  Szyfry tego typu działają jak akcent, tylko bez pipeline'u fonetycznego —
  używają wyłącznie listy `zamiany`.>
iso: {jezyk_bazowy}
kategoria: szyfr
kolejnosc: 100

# Pipeline – dla szyfrów zwykle wszystko OFF poza listą zamian.
czysc_tekst_tts: false
normalizuj_liczby: false
usun_polskie_znaki: false
skleja_pojedyncze_litery: false

# Właściwe zamiany. Lista jest aplikowana SEKWENCYJNIE (str.replace) — każda
# reguła operuje na WYJŚCIU poprzedniej. Dwa wnioski:
#   1. dwuznaki/trigramy PRZED jednoznakami (np. „ch" przed „c"), inaczej
#      reguła jednoznaku rozbije zapis dwuznaku;
#   2. uważaj na łańcuchy — jeśli reguła wprowadza znak, który PÓŹNIEJSZA
#      reguła ma jako `wzor`, ten znak też zostanie zamieniony.
# Pary leet poniżej (a→@, o→0) są od kolejności niezależne (rozłączne
# jednoznaki); kolejność zaczyna mieć znaczenie dopiero przy wzorach
# wieloznakowych. Dla wzorów regex dodaj `regex: true`.
zamiany:
  - {{ wzor: "a", zamiana: "@" }}
  - {{ wzor: "o", zamiana: "0" }}
  # <UZUPEŁNIJ: kolejne pary realizujące efekt opisany w polu `opis:`.
  # Skopiuj prompt z Managera Reguł do AI po pełną listę i natywny opis.>
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
#  <UZUPEŁNIJ NATYWNIE w {natywna_baza}: nagłówek pliku, np. „MODUS HÖRBUCH"
#   (DE) / „MODALITÀ AUDIOLIBRO" (IT) / „РЕЖИМ АУДИОКНИГА" (RU)>
#  Szablon oparty o tryb Audiobook – uzupełnij rolę, zasady i prompt.
# -----------------------------------------------------------------------------
id: {id_pliku}
etykieta: "{etykieta}"
kategoria: tryb
kolejnosc: 40

# --- Parametry OpenAI ---
model: gpt-4o
temperatura: 0.85
jezyk_odpowiedzi: {natywny_jezyk_odp}

# Czy odpowiedź zapisywać do pliku projektu (.txt)?
zapis_do_pliku: true

# --- Prompt systemowy ---
# Placeholdery: {{world_context}}, {{jezyk_odpowiedzi}}
# UWAGA: cały prompt systemowy MUSI być w języku {natywna_baza}.
# Wzorcuj się na `dictionaries/{jezyk_bazowy}/rezyser/tryb_audiobook.yaml`.
prompt_systemowy: |
  # <UZUPEŁNIJ NATYWNIE w {natywna_baza}: Rola/Rolle/Ruolo: NAZWA ROLI AI>

  <UZUPEŁNIJ NATYWNIE: pierwsze zdanie z instrukcją „Piszesz WYŁĄCZNIE
  po {{jezyk_odpowiedzi}}".>

  <UZUPEŁNIJ NATYWNIE: opis trybu i oczekiwanego formatu wyjściowego.>

  ### 🌍 <UZUPEŁNIJ NATYWNIE: nagłówek typu „Żelazne Zasady Świata"
  / „Eiserne Regeln der Welt" / „Regole Ferree del Mondo">:
  {{world_context}}

  ### 📖 <UZUPEŁNIJ NATYWNIE: nagłówek typu „Zasady tego trybu"
  / „Regeln des Modus" / „Regole della modalità">:
  1. <UZUPEŁNIJ NATYWNIE: pierwsza zasada (styl, ograniczenia formatu)>.
  2. <UZUPEŁNIJ NATYWNIE: druga zasada>.
  3. **<UZUPEŁNIJ NATYWNIE: nagłówek „DOMYKANIE SCEN" / „SZENENABSCHLUSS"
     / „CHIUSURA DELLE SCENE">:** - <NATYWNIE: „DOMYŚLNIE (ANTI-CLOSURE):
     Urwij w środku akcji.">
     - <NATYWNIE: „WYJĄTEK (FINAŁ/EPILOG): Jeśli to zakończenie, domknij
       scenę naturalnie.">

# --- Sufiksy kontekstowe (opcjonalne) ---
# Puste {{}} oznacza „silnik nie dokleja żadnego sufiksu zależnego od stanu
# pamięci". Jeśli chcesz dodać sufiksy – patrz tryb_burza.yaml jako wzorzec.
sufiksy: {{}}

# --- Przypomnienie doklejane do instrukcji użytkownika ---
# Również NATYWNIE w {natywna_baza}.
przypomnienie_uzytkownika: |


  (<UZUPEŁNIJ NATYWNIE: PRZYPOMNIENIE / ERINNERUNG / RICORDO: krótka
  rekapitulacja kluczowych zasad tego trybu w 1-2 zdaniach>.)

# --- Walidacja po stronie aplikacji ---
# Słowa wyzwalające „streszczenie" — natywne w {natywna_baza} (porównanie
# robione lower-case, więc wpisuj zwykle małymi).
slowa_wyzwalajace:
  streszczenie:
{natywne_streszcz}

# Czy uruchamiać silnik fonetyczny na odpowiedzi?
# true  – wymagane, jeśli tryb generuje dialogi z tagami postaci.
# false – dla prozy literackiej bez tagów.
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

# TASK
Create the file `dictionaries/{jezyk_bazowy}/rezyser/tryb_{id_pliku}.yaml` —
a creative AI mode named **{etykieta}**.

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
1. Identifying fields: `id`, `etykieta`, `kategoria: tryb`, `kolejnosc`
   (int 10-90; 30 = audiobook, 40 = brainstorm, 50 = script).
2. OpenAI parameters: `model: gpt-4o` (or `gpt-4o-mini` for fast modes),
   `temperatura` (0.7-0.9 for literary, 0.5 for scripting),
   `jezyk_odpowiedzi: {natywny_jezyk_odp}` (already matched to the pack),
   `zapis_do_pliku: true`.
3. **`prompt_systemowy:`** appended to every OpenAI call. It MUST contain
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
# SZABLON 4: Postprodukcja (wzorowany na postprod_tytuly.yaml)
# =============================================================================
def szablon_postprodukcja(id_pliku: str, etykieta: str,
                          jezyk_bazowy: str = "pl") -> str:
    natywna_baza = _natywna_nazwa_jezyka(jezyk_bazowy)
    natywny_jezyk_odp = _natywne_jezyk_odpowiedzi(jezyk_bazowy)
    return f"""# -----------------------------------------------------------------------------
#  <UZUPEŁNIJ NATYWNIE w {natywna_baza}: nagłówek pliku, np. „NACHBEARBEITUNG"
#   (DE) / „POSTPRODUZIONE" (IT) / „ПОСТОБРАБОТКА" (RU)>
#  Szablon oparty o postprod_tytuly.yaml — iteracja po rozdziałach.
# -----------------------------------------------------------------------------
id: {id_pliku}
etykieta: "{etykieta}"
kategoria: postprodukcja
kolejnosc: 20

# --- Parametry OpenAI ---
model: gpt-4o-mini
temperatura: 0.7
jezyk_odpowiedzi: {natywny_jezyk_odp}

# --- Prompt systemowy ---
# UWAGA: cały prompt MUSI być w języku {natywna_baza}.
prompt_systemowy: |
  <UZUPEŁNIJ NATYWNIE w {natywna_baza}: rola AI + jednozdaniowa instrukcja
  formatu odpowiedzi (np. „Jesteś redaktorem audiobooków. Odpowiadasz
  jednym zdaniem zawierającym tylko tytuł rozdziału.").>

# --- Szablon instrukcji użytkownika (role=user) ---
# Placeholdery: {{naglowek}}, {{probka}}
prompt_uzytkownika_szablon: |
  <UZUPEŁNIJ NATYWNIE w {natywna_baza}: fragment z placeholderem {{naglowek}},
  potem polecenie dla AI, na końcu blok:
    TREŚĆ:
    {{probka}}>

# --- Parametry iteracji po pliku projektu ---
# Regex łapiący nagłówki rozdziałów. WZORZEC dopasuj do języka:
#   PL: "(?i)\\\\n*(Prolog|Rozdział \\\\d+|Epilog)\\\\n*"
#   DE: "(?i)\\\\n*(Prolog|Kapitel \\\\d+|Epilog)\\\\n*"
#   IT: "(?i)\\\\n*(Prologo|Capitolo \\\\d+|Epilogo)\\\\n*"
#   EN: "(?i)\\\\n*(Prologue|Chapter \\\\d+|Epilogue)\\\\n*"
regex_podzial_rozdzialow: '<UZUPEŁNIJ: regex łapiący nagłówki rozdziałów w {natywna_baza}>'
min_dlugosc_fragmentu: 50
max_dlugosc_probki: 6000

# Komunikaty widoczne dla użytkownika w oknie wyników (NATYWNIE w {natywna_baza}):
etykieta_fragment_zbyt_krotki: '<UZUPEŁNIJ NATYWNIE: np. (Fragment zbyt krótki)>'
etykieta_bled_brak_kredytow: '<UZUPEŁNIJ NATYWNIE: np. (Błąd – brak kredytów API)>'
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
a postproduction (iterative chapter-by-chapter file processing).

# PROJECT CONTEXT
- `core_rezyser.py` + `przepisy_rezysera.py` — the AI-mode engine; it loads
  postproductions from `dictionaries/<code>/rezyser/postprod_*.yaml`.
- A postproduction iterates over the project file (.txt) — the engine
  splits it by `regex_podzial_rozdzialow` and sends each chunk to the AI
  with `prompt_systemowy` + `prompt_uzytkownika_szablon` (placeholders
  `{{naglowek}}` and `{{probka}}`).
- Deployed packs (as of 13.9): {inne_paczki} — each has 1 postproduction
  (`postprod_tytuly.yaml`). A style model.
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
   (int 10-90, e.g. 20 for a title generator).
2. OpenAI parameters: `model: gpt-4o-mini` (or `gpt-4o` if the task
   requires reasoning), `temperatura` 0.5-0.8 (we want stability),
   `jezyk_odpowiedzi: {natywny_jezyk_odp}`.
3. **`prompt_systemowy:`** the AI role, 1-2 sentences on the expected
   output format. PL model: „Jesteś redaktorem audiobooków. Twoja odpowiedź
   zawiera WYŁĄCZNIE tytuł rozdziału — jedno zdanie, bez komentarzy."
4. **`prompt_uzytkownika_szablon:`** MUST contain both placeholders:
   `{{naglowek}}` (the engine inserts the title) and `{{probka}}` (the
   chapter content).
5. **`regex_podzial_rozdzialow:`** matched to how chapters are named in the
   project .txt files in {natywna_baza}. Patterns per language:
     - PL: `(?i)\\n*(Prolog|Rozdział \\d+|Epilog)\\n*`
     - DE: `(?i)\\n*(Prolog|Kapitel \\d+|Epilog)\\n*`
     - IT: `(?i)\\n*(Prologo|Capitolo \\d+|Epilogo)\\n*`
     - EN: `(?i)\\n*(Prologue|Chapter \\d+|Epilogue)\\n*`
     - RU: `(?i)\\n*(Пролог|Глава \\d+|Эпилог)\\n*`
6. `min_dlugosc_fragmentu` (typically 50 chars; shorter chunks are skipped
   with the `etykieta_fragment_zbyt_krotki` message).
7. `max_dlugosc_probki` (typically 4000-8000 chars for gpt-4o-mini — the
   context budget sent to the API).

# NATIVE-LANGUAGE REQUIREMENTS
All „human-facing" text in the file — label, header, YAML comments,
`prompt_systemowy`, `prompt_uzytkownika_szablon`, both message fields
(`etykieta_fragment_zbyt_krotki`, `etykieta_bled_brak_kredytow`) — in
**{natywna_baza}**.

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
6. In your reply report: the model, the temperature, the
   `regex_podzial_rozdzialow` you used, and whether
   `prompt_uzytkownika_szablon` contains both placeholders.
"""


# =============================================================================
# SZABLON 5: podstawy.yaml dla nowego języka bazowego (minimum do startu)
# =============================================================================
def szablon_podstawy(kod_jezyka: str, etykieta_jezyka: str) -> str:
    natywna = _natywna_nazwa_jezyka(kod_jezyka)
    return f"""# =============================================================================
#  <UZUPEŁNIJ NATYWNIE: nagłówek pliku w języku {natywna}, np. dla DE:
#  „GRUNDLAGEN DER DEUTSCHEN SPRACHE"; dla IT: „FONDAMENTI DELLA LINGUA ITALIANA">
# =============================================================================
#  Plik bazowy dla `dictionaries/{kod_jezyka}/`. Manager Reguł utworzył już
#  cztery podfoldery (akcenty/, szyfry/, rezyser/, gui/) — Twoja praca
#  ogranicza się do uzupełnienia poniższych sekcji.
#
#  Sekcje wymagane przez silnik (`core_poliglota._jezyk_kompletny`):
#    1. lingua          – nazwa enum-a `lingua.Language` dla detektora
#                         (POLISH/GERMAN/FRENCH/...). Lista:
#                         https://github.com/pemistahl/lingua-py
#    2. polskie_znaki   – mapowanie diakrytyków języka „{kod_jezyka}" na
#                         litery ASCII (używane przez `usun_polskie_znaki:
#                         true` w akcentach).
#    3. alfabet         – pełny alfabet wielkich liter (używany przez szyfr
#                         Cezara). UWAGA: litery rosnące przy `.upper()`
#                         (np. ß→SS) NIE wchodzą do alfabetu.
#    4. slowo_akcent    – natywne słowa wyzwalające parser akcentów
#                         w trybie Reżysera (od 13.3+).
#
#  Komentarze i opisy w tym pliku piszemy w języku {natywna} — porównaj
#  z `dictionaries/de/podstawy.yaml` lub `dictionaries/it/podstawy.yaml`,
#  jeśli zatrzymałeś się przy uzupełnianiu.
# =============================================================================

id: podstawy
jezyk: {kod_jezyka}
# Nazwa enum-a `lingua.Language` (wielkimi, bez prefiksu).
# Brak wyłącza język z detektora — w GUI wybierze się ręcznie,
# ale fragmenty mieszane nie będą rozpoznawane.
lingua: <UZUPEŁNIJ_NAZWE_ENUMA_NP_GERMAN>
# Etykieta MUSI być w 100% w języku natywnym {natywna}.
# Wzorce z wdrożonych paczek: PL: „Polski – podstawy fonetyczne"; DE:
# „Deutsch – phonetische Grundlagen"; IT: „Italiano – fondamenti
# fonetici"; RU: „Русский – фонетические основы"; FI: „Suomi –
# foneettiset perusteet"; IS: „Íslenska – hljóðfræðilegur grunnur".
etykieta: '<UZUPEŁNIJ NATYWNIE: endonim + sufiks po {natywna}, np. {natywna} – phonetische Grundlagen / fondamenti fonetici>'
opis: |
  <UZUPEŁNIJ NATYWNIE w języku {natywna}: 2-4 zdania o tym, co opisuje
  ten plik. Wzorzec PL:
    Bazowe reguły dla języka <natywna nazwa>:
      1. Transliteracja diakrytyków (...) — usuwana przez
         `usun_polskie_znaki: true` w akcentach.
      2. Alfabet (<N> liter, wielkie) — używany przez szyfr Cezara.>

polskie_znaki:
  # Pary {{ wzor: "<diakrytyk>", zamiana: "<ASCII>" }} — wariant mały i wielki.
  # <UZUPEŁNIJ: minimum diakrytyki języka {natywna}, plus opcjonalnie inne
  # europejskie (np. polskie ąęłóśćńżź) — wzorzec: dictionaries/de/podstawy.yaml>
  - {{ wzor: "?", zamiana: "?" }}

# Pełny alfabet wielkich liter, bez znaków białych. Użyj NATYWNEGO alfabetu
# w jego NATYWNEJ kolejności. Litera akcentowana wchodzi do alfabetu TYLKO,
# jeśli jest w danym języku osobną literą — i stoi tam, gdzie stawia ją
# natywna kolejność, NIE automatycznie na końcu (np. FI „...XYZÅÄÖ" — Å Ä Ö
# są natywne i kończą fiński alfabet; ES Ñ stoi między N a O). Formy
# akcentowane, które NIE są osobnymi literami (np. FR é/à, IT à/è), do
# alfabetu NIE wchodzą — przechodzą przez Cezara jak cyfry. Litery rosnące
# przy `.upper()` (np. ß→SS) są pomijane zawsze.
alfabet: '<UZUPEŁNIJ: natywny alfabet wielkimi literami w natywnej kolejności>'

# -----------------------------------------------------------------------------
# Słowa wyzwalające parser akcentów w trybie Reżysera (od 13.3+).
# core_rezyser.zastosuj_akcenty_uniwersalne tworzy z tej listy regex łapiący
# frazy „<słowo> X" lub „X <słowo>" (np. dla PL „akcent włoski" / „włoski
# akcent"). Wpisy MUSZĄ być w języku natywnym, małymi literami.
# Wzorce: PL ["akcent"]; IT ["accento", "accentato"]; RU ["акцент",
# "акцентом", "говор"]; DE ["akzent", "aussprache"].
# -----------------------------------------------------------------------------
slowo_akcent:
  - "<UZUPEŁNIJ NATYWNIE: minimum 1 słowo, np. 'akzent'/'accento'/'akcent'>"
"""


# =============================================================================
# PROMPT 2: Nowy język bazowy – pełny pakiet (podstawy + zestaw akcentów)
# =============================================================================
def prompt_jezyk_bazowy(kod_jezyka: str, etykieta_jezyka: str) -> str:
    natywna = _natywna_nazwa_jezyka(kod_jezyka)
    inne_paczki = _paczki_referencyjne(kod_jezyka)
    return f"""# ROLE
You are an AI agent with access to the files of the „Reżyser Audio GPT"
project (wxPython + OpenAI). You have tools: Read, Write, Edit, Glob, Grep,
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
