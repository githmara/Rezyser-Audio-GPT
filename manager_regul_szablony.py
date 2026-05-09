"""
manager_regul_szablony.py – Szablony i prompty dla Managera Reguł.

Moduł CZYSTO DEKLARATYWNY: trzyma gotowe teksty YAML-i do utworzenia
(szablony) oraz prompty dla chatbotów AI (ChatGPT / Claude), które
wygenerują trudne merytorycznie reguły zamiast zwykłego Kowalskiego.

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
    "fr": "Français",     # planowane wdrożenie 13.10
    "es": "Español",      # planowane wdrożenie 13.11
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
# Pomocnicze: lista paczek wdrożonych (stan na 13.9 — synchronizować ręcznie
# przy każdym pełnym wdrożeniu nowego języka). Używane w promptach agentowych
# jako podpowiedź „skąd brać wzorzec stylu".
# =============================================================================
_PACZKI_WDROZONE: tuple[str, ...] = ("pl", "en", "de", "fi", "is", "it", "ru")


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
# ZŁOTA ZASADA: trigramy/dwuznaki (sch, tsch, ch, cz, sz, rz) PRZED
# jednoznakami (c, s, z, r), bo inaczej „c → ts" rozwali zapis „ch", „cz".
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
    return f"""# ROLA
Jesteś agentem AI z dostępem do plików projektu „Reżyser Audio GPT"
(wxPython + OpenAI). Masz narzędzia: Read, Write, Edit, Glob, Grep, Bash.
Twoja praca: utworzyć regułę fonetyczną w drzewie projektu.

# KONTEKST PROJEKTU
- `core_poliglota.py` — silnik fonetyczny. Akcenty są ładowane z
  `dictionaries/<kod>/akcenty/*.yaml`; dispatcher (`_AKCENT_FUNCS`
  w `core_rezyser.py`) jest generowany automatycznie przez
  `odswiez_rezysera.py` po dodaniu/usunięciu pliku.
- Paczki wdrożone (stan 13.9): {inne_paczki} — to Twoje wzorce stylu
  i fonetyki dla podobnych celów (np. akcent finski jest w każdej z nich).
- Paczka bazowa tego zadania: `dictionaries/{jezyk_bazowy}/`
  (język {natywna_baza}). Manager Reguł utworzył już strukturę.

# ZADANIE
Utwórz plik `dictionaries/{jezyk_bazowy}/akcenty/{id_pliku}.yaml` —
akcent fonetyczny **{etykieta}**, który upodobni tekst pisany w języku
**{natywna_baza}** do wymowy w języku o kodzie ISO **{iso}** (docelowy
syntezator TTS).

# WALIDACJA SCENARIUSZA (zanim cokolwiek napiszesz)
Sprawdź, czy `iso` ({iso}) różni się od `jezyk_bazowy` ({jezyk_bazowy}).
Jeśli `iso == jezyk_bazowy` lub `iso` jest puste — ten plik NIE jest
akcentem fonetycznym, tylko narzędziowym preprocessorem
(`kategoria: oczyszczenie`) lub naprawiaczem tagów (`kategoria:
naprawiacz`). PRZERWIJ pracę i poproś usera, żeby uruchomił Manager
Reguł z odpowiednim podtypem („Akcent czyszczący" lub „Naprawiacz tagów"
zamiast „Akcent fonetyczny"). Nie da się sensownie napisać listy
`zamiany:` upodabniającej język do samego siebie.

# PLIKI REFERENCYJNE (otwórz przed pisaniem)
1. `dictionaries/{jezyk_bazowy}/podstawy.yaml` — alfabet i mapa
   diakrytyków `polskie_znaki` paczki bazowej. Twoje wzory zamian MUSZĄ
   operować na tekście po `usun_polskie_znaki: true` (czyli po
   transliteracji opisanej w tym pliku).
2. `dictionaries/<inna paczka>/akcenty/<dowolny>.yaml` — wzorzec stylu.
   Wybierz paczkę, której baza ma najbliższy charakter do {natywna_baza}
   (alfabet łaciński/cyrylicki, obecność/brak diakrytyków). Glob
   `dictionaries/*/akcenty/*.yaml` pokaże wszystko, co masz pod ręką.
3. (Opcjonalnie) `dictionaries/<dowolna>/akcenty/<ten sam id>.yaml` —
   jeśli akcent o tym samym `id` istnieje w innej paczce, sprawdź jak
   tam dostosowano listę `zamiany` do bazy tej paczki. Pomocne dla
   identyfikatorów typu `finski`, `szwedzki`, `oczyszczenie` które
   zwykle istnieją we wszystkich wdrożonych paczkach.

# WYMAGANIA STRUKTURY
1. Pola `id`, `etykieta`, `iso`, `kategoria: akcent`, `kolejnosc`.
2. Pipeline (boolean): `czysc_tekst_tts`, `normalizuj_liczby`,
   `usun_polskie_znaki`, `skleja_pojedyncze_litery`. Domyślnie `true`
   dla typowych akcentów fonetycznych.
3. Lista `zamiany:` uporządkowana: TRIGRAMY → DWUZNAKI → JEDNOZNAKI
   (inaczej `c → ts` rozwali zapis `ch` / `cz`). Każdy dwuznak/trigram
   w wariancie `mały` + `Wielką pierwszą`; dla języków używających ALL-CAPS
   częstych skrótów (np. niemieckie SCH, CH) dodaj trzeci wariant.
4. Regex: dodaj `regex: true` w wierszu zamiany.
5. **Flaga `usun_polskie_znaki: true`** (mimo nazwy historycznej!) usuwa
   diakrytyki języka {jezyk_bazowy} zgodnie z mapą w
   `dictionaries/{jezyk_bazowy}/podstawy.yaml::polskie_znaki`. Twoje
   wzory MUSZĄ działać NA TEKŚCIE PO tej transliteracji — czyli operuj
   na ASCII (lub bezdiakrytycznym) odpowiedniku alfabetu {natywna_baza}.

# WYMAGANIA NATYWNOŚCI
- `etykieta`, `opis`, nagłówek pliku, komentarze YAML — wszystko w języku
  **{natywna_baza}**. Mieszanie polskiego z natywnym jest BŁĘDEM (np.
  dla paczki FR „Akcent finski" jest błędem; powinno być
  „Accent finlandais" lub równoważnie).

# PROCEDURA
1. Otwórz pliki referencyjne (Read).
2. Zaprojektuj listę `zamiany:` adekwatną do akcentu {etykieta}, używając
   konwencji stylu paczki, z której bierzesz wzorzec.
3. Zapisz plik `dictionaries/{jezyk_bazowy}/akcenty/{id_pliku}.yaml`
   (Write).
4. Zweryfikuj parsowalność:
   `python -c "import yaml; yaml.safe_load(open('dictionaries/{jezyk_bazowy}/akcenty/{id_pliku}.yaml', encoding='utf-8'))"`.
5. Uruchom `python odswiez_rezysera.py` (Bash) — skrypt dopisze do
   `core_poliglota.akcent_*` docstring listę plików źródłowych
   i do `core_rezyser._AKCENT_FUNCS` wpis dispatchera. Output zawiera
   czerwone ostrzeżenia, jeśli akcent o tym samym id ma niespójną
   strukturę między paczkami.
6. W odpowiedzi raportuj: ile par ma `zamiany:`, którą paczkę wzięto
   za wzorzec stylu, i czy `odswiez_rezysera.py` wyrzucił ostrzeżenia.
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
    return f"""# ROLA
Jesteś agentem AI z dostępem do plików projektu „Reżyser Audio GPT".
Masz narzędzia: Read, Write, Edit, Glob, Grep, Bash. Zadanie: zaadaptować
plik „akcentu czyszczącego" (preprocessor TTS) do nowej paczki językowej.

# KONTEKST PROJEKTU
- Akcenty „czyszczące" (`kategoria: oczyszczenie`) NIE nakładają fonetyki —
  uruchamiają wyłącznie pipeline `czysc_tekst_tts` + ewentualnie
  `normalizuj_liczby` (cyfry → słowa). Lista `zamiany:` jest pusta.
- Struktura tych plików jest IDENTYCZNA we wszystkich 7 wdrożonych
  paczkach ({inne_paczki}); różni się TYLKO treść etykiety, opisu
  i komentarzy YAML — wszystko natywne.
- Każda paczka zawiera dwa warianty: `oczyszczenie.yaml` (z normalizacją
  liczb) i `oczyszczenie_bez_liczb.yaml` (bez — dla książek z datami,
  numerami stron itp.).

# ZADANIE
Utwórz plik `dictionaries/{jezyk_bazowy}/akcenty/{id_pliku}.yaml` —
akcent czyszczący w paczce {natywna_baza}, etykieta widoczna w GUI:
**{etykieta}**.

# PLIKI REFERENCYJNE (otwórz przed pisaniem)
1. `dictionaries/<dowolna z wdrożonych>/akcenty/{id_pliku}.yaml` — gotowy
   wzorzec stylu (struktura, kolejnosc, pipeline). Jedyne, co zmieniasz,
   to etykieta + opis + komentarze przekładane na {natywna_baza}.
2. `dictionaries/{jezyk_bazowy}/podstawy.yaml` — sprawdzenie konwencji
   stylu komentarzy YAML w paczce bazowej.

# WYMAGANIA STRUKTURY
1. `kategoria: oczyszczenie` (silnik traktuje takie pliki jako
   preprocessor, nie fonetyczny akcent).
2. `iso: {jezyk_bazowy}` (operuje na tekście paczki bazowej).
3. Pipeline:
   - `oczyszczenie` (z normalizacją liczb): `czysc_tekst_tts: true`,
     `normalizuj_liczby: true`, `usun_polskie_znaki: false`,
     `skleja_pojedyncze_litery: false`.
   - `oczyszczenie_bez_liczb`: jak wyżej, ale `normalizuj_liczby: false`.
4. `zamiany: []` (pusta lista — to nie fonetyczny akcent).
5. `kolejnosc: 20` (umieszcza w GUI nad fonetycznymi).

# WYMAGANIA NATYWNOŚCI
`etykieta`, `opis`, nagłówek pliku, komentarze YAML — wszystko
w {natywna_baza}. Zwróć uwagę na konwencję etykiety wdrożonych paczek:
- PL: „Żaden (Czyszczenie Z normalizacją liczb)"
- DE: „Keiner (Bereinigung MIT Zahlennormalisierung)"
- IT: „Nessuno (Pulizia CON normalizzazione numeri)"
Pierwsze słowo to „brak akcentu" w {natywna_baza}, w nawiasie krótka
charakterystyka co dokładnie robi pipeline.

# PROCEDURA
1. Otwórz `dictionaries/<wdrożona>/akcenty/{id_pliku}.yaml` (Read).
2. Otwórz `dictionaries/{jezyk_bazowy}/podstawy.yaml` żeby zobaczyć
   konwencję komentarzy paczki bazowej.
3. Zapisz plik `dictionaries/{jezyk_bazowy}/akcenty/{id_pliku}.yaml`
   (Write) z tą samą strukturą, ale natywną treścią pól tekstowych.
4. Zweryfikuj parsowalność:
   `python -c "import yaml; yaml.safe_load(open('dictionaries/{jezyk_bazowy}/akcenty/{id_pliku}.yaml', encoding='utf-8'))"`.
5. Uruchom `python odswiez_rezysera.py` (Bash) — dispatcher zauważy
   plik. W ostrzeżeniach silnika nie powinno być info o niespójnościach
   (struktura jest standardowa).
6. W odpowiedzi raportuj: którą paczkę wzięto za wzorzec i ostrzeżenia
   `odswiez_rezysera.py`.
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
    return f"""# ROLA
Jesteś agentem AI z dostępem do plików projektu „Reżyser Audio GPT".
Masz narzędzia: Read, Write, Edit, Glob, Grep, Bash. Zadanie: zaadaptować
plik „naprawiacza tagów" do nowej paczki językowej.

# KONTEKST PROJEKTU
- Naprawiacz tagów (`kategoria: naprawiacz`) to TRYB SPECJALNY: NIE
  modyfikuje treści tekstu ani jego fonetyki. Wstrzykuje wyłącznie kod
  ISO języka do plików wynikowych:
    * HTML: atrybut `lang="..."` w znaczniku `<html>`
    * DOCX: element `<w:lang w:val="..."/>` dla każdego biegu tekstu
  Dzięki temu czytnik ekranu (NVDA/JAWS) poprawnie przełącza głos
  syntezatora na właściwy język.
- Kod ISO podaje user ręcznie w GUI (pole „Kod ISO") — wartość `iso:`
  w pliku jest pusta (`iso: ""`).
- Struktura pliku jest IDENTYCZNA we wszystkich 7 wdrożonych paczkach
  ({inne_paczki}); różni się TYLKO treść etykiety, opisu i komentarzy
  YAML — wszystko natywne.

# ZADANIE
Utwórz plik `dictionaries/{jezyk_bazowy}/akcenty/{id_pliku}.yaml` —
naprawiacz tagów w paczce {natywna_baza}, etykieta widoczna w GUI:
**{etykieta}**.

# PLIKI REFERENCYJNE (otwórz przed pisaniem)
1. `dictionaries/<dowolna z wdrożonych>/akcenty/naprawiacz_tagow.yaml` —
   gotowy wzorzec stylu. Jedyne, co zmieniasz: etykieta + opis +
   komentarze przekładane na {natywna_baza}.

# WYMAGANIA STRUKTURY (silnik)
1. `kategoria: naprawiacz` — silnik wykrywa tryb specjalny po tej wartości.
2. `iso: ""` (pusty string — kod podawany przez user w GUI).
3. Wszystkie flagi pipeline `false`: `czysc_tekst_tts`,
   `normalizuj_liczby`, `usun_polskie_znaki`, `skleja_pojedyncze_litery`.
4. `zamiany: []` (pusta lista — silnik nie aplikuje żadnych zamian).
5. `kolejnosc: 100` (na końcu listy w GUI).

# WYMAGANIA NATYWNOŚCI
`etykieta`, `opis`, nagłówek pliku, komentarze YAML — wszystko
w {natywna_baza}. Konwencja etykiety wdrożonych paczek (z emoji 🔧):
- PL: „🔧 Naprawiacz Tagów (Tylko wstrzyknięcie kodu ISO)"
- DE: „🔧 Tag-Reparateur (Nur ISO-Code-Injektion)"
- IT: „🔧 Riparatore di tag (solo iniezione del codice ISO)"

# PROCEDURA
1. Otwórz `dictionaries/<wdrożona>/akcenty/naprawiacz_tagow.yaml` (Read).
2. Zapisz plik `dictionaries/{jezyk_bazowy}/akcenty/{id_pliku}.yaml`
   (Write) z tą samą strukturą, natywną treścią pól tekstowych.
3. Zweryfikuj parsowalność:
   `python -c "import yaml; yaml.safe_load(open('dictionaries/{jezyk_bazowy}/akcenty/{id_pliku}.yaml', encoding='utf-8'))"`.
4. Uruchom `python odswiez_rezysera.py` (Bash) — dispatcher dorzuci
   plik do mapy.
5. W odpowiedzi raportuj: którą paczkę wzięto za wzorzec i ewentualne
   ostrzeżenia z `odswiez_rezysera.py`.
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

# Właściwe zamiany (ZŁOTA ZASADA: dwuznaki PRZED jednoznakami).
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
    return f"""# ROLA
Jesteś agentem AI z dostępem do plików projektu „Reżyser Audio GPT".
Masz narzędzia: Read, Write, Edit, Glob, Grep, Bash. Zadanie: utworzyć
plik szyfru „czyste zamiany" w drzewie projektu.

# KONTEKST PROJEKTU
- `core_poliglota.py` — silnik fonetyczny. Szyfry typu „czyste zamiany"
  działają jak akcenty bez pipeline'u fonetycznego: tylko lista
  `zamiany:` jest aplikowana do tekstu.
- Paczki wdrożone (stan 13.9): {inne_paczki} — mają każda po 6 szyfrów
  (cezar, jakanie, odwracanie, samogloskowiec, typoglikemia, waz).
  Wzorcuj się na tych plikach.
- Paczka tego zadania: `dictionaries/{jezyk_bazowy}/`
  (język {natywna_baza}).

# ZADANIE
Utwórz plik `dictionaries/{jezyk_bazowy}/szyfry/{id_pliku}.yaml` —
szyfr „czyste zamiany" o nazwie **{etykieta}**.

# PLIKI REFERENCYJNE (otwórz przed pisaniem)
1. `dictionaries/<inna paczka>/szyfry/jakanie.yaml` lub `samogloskowiec.yaml`
   — wzorzec stylu szyfru opartego na zamianach (komentarze natywne dla
   tej paczki). Glob: `dictionaries/*/szyfry/*.yaml`.
2. `dictionaries/{jezyk_bazowy}/podstawy.yaml` — alfabet i diakrytyki
   paczki bazowej (przydatne, jeśli efekt szyfru ma działać też na
   literach z diakrytykami).

# WYMAGANIA STRUKTURY
1. Pola: `id`, `etykieta`, `opis`, `iso: {jezyk_bazowy}`,
   `kategoria: szyfr`, `kolejnosc`.
2. Pipeline (typowo wszystko OFF dla szyfrów):
   `czysc_tekst_tts: false`, `normalizuj_liczby: false`,
   `usun_polskie_znaki: false`, `skleja_pojedyncze_litery: false`.
3. Lista `zamiany:` uporządkowana: dwuznaki/trigramy PRZED jednoznakami.
   Dla każdego wzoru rozważ warianty `mały` i `Wielki`. Jeśli efekt ma
   działać też na diakrytykach (à, é, ä, ё), uwzględnij je explicit lub
   dodaj wzór z `regex: true`.

# WYMAGANIA NATYWNOŚCI
`etykieta`, `opis`, nagłówek pliku, komentarze YAML — w języku
**{natywna_baza}**. Wzorzec dla wdrożonych paczek widać w `cezar.yaml`
każdej paczki (komentarze niemieckie / włoskie / rosyjskie itd.).

# PROCEDURA
1. Otwórz pliki referencyjne (Read).
2. Zaprojektuj listę `zamiany:` realizującą efekt {etykieta}.
3. Zapisz plik `dictionaries/{jezyk_bazowy}/szyfry/{id_pliku}.yaml` (Write).
4. Zweryfikuj parsowalność:
   `python -c "import yaml; yaml.safe_load(open('dictionaries/{jezyk_bazowy}/szyfry/{id_pliku}.yaml', encoding='utf-8'))"`.
5. Szyfry są ładowane dynamicznie — nie ma dodatkowego skryptu do
   uruchomienia. „Odśwież drzewo" w GUI Managera + restart aplikacji.
6. W odpowiedzi raportuj: ile par ma `zamiany:` i którą paczkę wzięto
   za wzorzec stylu.
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
    return f"""# ROLA
Jesteś agentem AI z dostępem do plików projektu „Reżyser Audio GPT".
Masz narzędzia: Read, Write, Edit, Glob, Grep, Bash. Zadanie: utworzyć
nowy tryb Reżysera (prompt systemowy + walidacja słów wyzwalających).

# KONTEKST PROJEKTU
- `core_rezyser.py` — silnik trybów AI (sklejanie promptu z `world_context`
  + `prompt_systemowy` + instrukcji użytkownika).
- `przepisy_rezysera.py` — loader YAML-i z `dictionaries/<kod>/rezyser/`.
  Tryby ładowane dynamicznie; nie ma dodatkowego skryptu do uruchomienia
  po dodaniu pliku.
- Paczki wdrożone (stan 13.9): {inne_paczki} — każda ma 4 pliki w
  `rezyser/` (3 tryby: audiobook/burza/skrypt + 1 postprodukcja). To
  Twoje wzorce stylu i konwencji prompt_systemowy.
- Paczka tego zadania: `dictionaries/{jezyk_bazowy}/`
  (język {natywna_baza}).

# ZADANIE
Utwórz plik `dictionaries/{jezyk_bazowy}/rezyser/tryb_{id_pliku}.yaml` —
tryb twórczy AI o nazwie **{etykieta}**.

# PLIKI REFERENCYJNE (otwórz przed pisaniem)
1. `dictionaries/{jezyk_bazowy}/rezyser/tryb_audiobook.yaml` — jeśli
   istnieje, najlepszy wzorzec stylu prompt_systemowy w {natywna_baza}.
   Jeśli paczka jest dopiero tworzona, użyj wzorca z innej wdrożonej.
2. `dictionaries/<inna paczka>/rezyser/tryb_audiobook.yaml` — referencja
   konwencji: nagłówki sekcji z emoji (🌍, 📖), format
   `**TYTUŁ ZASADY:** opis` dla zasad numerowanych, etykieta z natywnym
   nawiasem („Hörbuch (Prosa, Kapitel, DATEI SCHREIBEN)" DE,
   „Аудиокнига (Проза, главы, ЗАПИСЫВАЕТ В ФАЙЛ)" RU).
3. `dictionaries/<inna paczka>/rezyser/tryb_burza.yaml` lub
   `tryb_skrypt.yaml` — alternatywne wzorce dla trybów innych niż
   literacka proza.

# WYMAGANIA STRUKTURY (silnik)
1. Pola identyfikujące: `id`, `etykieta`, `kategoria: tryb`, `kolejnosc`
   (int 10-90; 30 = audiobook, 40 = burza mózgów, 50 = skrypt).
2. Parametry OpenAI: `model: gpt-4o` (lub `gpt-4o-mini` dla szybkich
   trybów), `temperatura` (0.7-0.9 dla literackich, 0.5 dla skryptowych),
   `jezyk_odpowiedzi: {natywny_jezyk_odp}` (już dopasowane do paczki),
   `zapis_do_pliku: true`.
3. **`prompt_systemowy:`** doklejany do każdego callu OpenAI. MUSI
   zawierać placeholdery `{{world_context}}` i `{{jezyk_odpowiedzi}}`
   (silnik je podstawia). Pierwsza linia ZAWSZE zawiera frazę
   „WYŁĄCZNIE po {{jezyk_odpowiedzi}}" w odpowiedniej formie idiomu
   (DE: „AUSSCHLIESSLICH auf"; IT: „ESCLUSIVAMENTE in"; RU: „ИСКЛЮЧИТЕЛЬНО на").
4. **`przypomnienie_uzytkownika:`** krótka 1-2-zdaniowa rekapitulacja
   kluczowych zasad trybu, doklejana do instrukcji użytkownika.
5. **`slowa_wyzwalajace.streszczenie:`** lista 3-5 natywnych słów typowo
   używanych w {natywna_baza} gdy ktoś prosi AI o streszczenie. Małymi
   literami (silnik robi lower-case porównanie).
6. **`stosuj_akcenty_fonetyczne:`** `true` dla trybów generujących
   dialogi z tagami postaci, `false` dla prozy literackiej.
7. `sufiksy: {{}}` (puste — chyba że wzorzec z `tryb_burza.yaml` pokazuje
   sufiksy zależne od stanu pamięci jako użyteczne dla tego trybu).

# WYMAGANIA NATYWNOŚCI
Wszystkie teksty „dla człowieka" w pliku — etykieta, nagłówek, komentarze
YAML, `prompt_systemowy`, `przypomnienie_uzytkownika`, lista
`slowa_wyzwalajace.streszczenie` — w języku **{natywna_baza}**.

# PROCEDURA
1. Otwórz pliki referencyjne (Read).
2. Zaprojektuj `prompt_systemowy` — rola AI, zasady stylu, formuła
   domykania scen (DOMYŚLNIE anti-closure / WYJĄTEK finał).
3. Zapisz plik
   `dictionaries/{jezyk_bazowy}/rezyser/tryb_{id_pliku}.yaml` (Write).
4. Zweryfikuj parsowalność:
   `python -c "import yaml; yaml.safe_load(open('dictionaries/{jezyk_bazowy}/rezyser/tryb_{id_pliku}.yaml', encoding='utf-8'))"`.
5. Tryby Reżysera są ładowane dynamicznie — nie ma dodatkowego skryptu.
   „Odśwież drzewo" w Managerze + restart aplikacji.
6. W odpowiedzi raportuj: model, temperatura, ile słów wyzwalających
   streszczenie, którą paczkę wzięto za wzorzec.
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
    return f"""# ROLA
Jesteś agentem AI z dostępem do plików projektu „Reżyser Audio GPT".
Masz narzędzia: Read, Write, Edit, Glob, Grep, Bash. Zadanie: utworzyć
postprodukcję (iteracyjne przetwarzanie pliku rozdział-po-rozdziale).

# KONTEKST PROJEKTU
- `core_rezyser.py` + `przepisy_rezysera.py` — silnik trybów AI; ładuje
  postprodukcje z `dictionaries/<kod>/rezyser/postprod_*.yaml`.
- Postprodukcja iteruje po pliku projektu (.txt) — silnik dzieli go po
  `regex_podzial_rozdzialow` i wysyła każdy fragment do AI z
  `prompt_systemowy` + `prompt_uzytkownika_szablon` (placeholdery
  `{{naglowek}}` i `{{probka}}`).
- Paczki wdrożone (stan 13.9): {inne_paczki} — każda ma 1 postprodukcję
  (`postprod_tytuly.yaml`). Wzorzec stylu.
- Paczka tego zadania: `dictionaries/{jezyk_bazowy}/`
  (język {natywna_baza}).

# ZADANIE
Utwórz plik `dictionaries/{jezyk_bazowy}/rezyser/postprod_{id_pliku}.yaml` —
postprodukcja o nazwie **{etykieta}**.

# PLIKI REFERENCYJNE (otwórz przed pisaniem)
1. `dictionaries/{jezyk_bazowy}/rezyser/postprod_tytuly.yaml` — jeśli
   istnieje, gotowy wzorzec konwencji w {natywna_baza}.
2. `dictionaries/<inna paczka>/rezyser/postprod_tytuly.yaml` — referencja
   konwencji dla wdrożonych paczek (PL/DE/IT/RU/FI/IS/EN). Zwróć uwagę
   na natywne `regex_podzial_rozdzialow` (PL: Rozdział, DE: Kapitel,
   IT: Capitolo, RU: Глава, EN: Chapter).
3. (Opcjonalnie) Pliki projektowe użytkownika `.txt` — jeśli masz dostęp
   do przykładów, otwórz jeden żeby zweryfikować jak realnie nazwane są
   nagłówki rozdziałów w {natywna_baza}.

# WYMAGANIA STRUKTURY (silnik)
1. Pola: `id`, `etykieta`, `kategoria: postprodukcja`, `kolejnosc`
   (int 10-90, np. 20 dla generatora tytułów).
2. Parametry OpenAI: `model: gpt-4o-mini` (lub `gpt-4o` jeśli zadanie
   wymaga rozumowania), `temperatura` 0.5-0.8 (chcemy stabilności),
   `jezyk_odpowiedzi: {natywny_jezyk_odp}`.
3. **`prompt_systemowy:`** rola AI, 1-2 zdania o oczekiwanym formacie
   wyjścia. Wzorzec PL: „Jesteś redaktorem audiobooków. Twoja odpowiedź
   zawiera WYŁĄCZNIE tytuł rozdziału — jedno zdanie, bez komentarzy."
4. **`prompt_uzytkownika_szablon:`** MUSI zawierać oba placeholdery:
   `{{naglowek}}` (silnik wstawia tytuł) i `{{probka}}` (treść rozdziału).
5. **`regex_podzial_rozdzialow:`** dopasowany do tego, jak rozdziały są
   nazwane w plikach .txt projektu w {natywna_baza}. Wzorce per język:
     - PL: `(?i)\\n*(Prolog|Rozdział \\d+|Epilog)\\n*`
     - DE: `(?i)\\n*(Prolog|Kapitel \\d+|Epilog)\\n*`
     - IT: `(?i)\\n*(Prologo|Capitolo \\d+|Epilogo)\\n*`
     - EN: `(?i)\\n*(Prologue|Chapter \\d+|Epilogue)\\n*`
     - RU: `(?i)\\n*(Пролог|Глава \\d+|Эпилог)\\n*`
6. `min_dlugosc_fragmentu` (typowo 50 znaków, krótsze fragmenty pomijane
   z komunikatem `etykieta_fragment_zbyt_krotki`).
7. `max_dlugosc_probki` (typowo 4000-8000 znaków dla gpt-4o-mini —
   kontekstowy budżet wysyłany do API).

# WYMAGANIA NATYWNOŚCI
Wszystkie teksty „dla człowieka" w pliku — etykieta, nagłówek, komentarze
YAML, `prompt_systemowy`, `prompt_uzytkownika_szablon`, oba pola
komunikatu (`etykieta_fragment_zbyt_krotki`, `etykieta_bled_brak_kredytow`)
— w języku **{natywna_baza}**.

# PROCEDURA
1. Otwórz pliki referencyjne (Read).
2. Zaprojektuj `prompt_systemowy` i `prompt_uzytkownika_szablon` adekwatne
   do zadania {etykieta}.
3. Zapisz plik
   `dictionaries/{jezyk_bazowy}/rezyser/postprod_{id_pliku}.yaml` (Write).
4. Zweryfikuj parsowalność:
   `python -c "import yaml; yaml.safe_load(open('dictionaries/{jezyk_bazowy}/rezyser/postprod_{id_pliku}.yaml', encoding='utf-8'))"`.
5. Postprodukcje ładowane dynamicznie — „Odśwież drzewo" w Managerze
   + restart aplikacji.
6. W odpowiedzi raportuj: model, temperatura, regex_podzial_rozdzialow
   którego użyłeś, czy `prompt_uzytkownika_szablon` zawiera oba
   placeholdery.
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

# Pełny alfabet wielkich liter, bez znaków białych. Diakrytyki, które nie
# rosną przy `.upper()`, mogą być DOŁĄCZONE NA KOŃCU (np. „...XYZÄÖÜ" dla DE).
alfabet: '<UZUPEŁNIJ: ABCDEFGHIJKLMNOPQRSTUVWXYZ + ewentualne diakrytyki na końcu>'

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
    return f"""# ROLA
Jesteś agentem AI z dostępem do plików projektu „Reżyser Audio GPT"
(wxPython + OpenAI). Masz narzędzia: Read, Write, Edit, Glob, Grep, Bash.
Twoja praca: utworzyć plik bazowy nowego języka i przygotować paczkę do
weryfikacji silnika.

# KONTEKST PROJEKTU
- `core_poliglota.py` — silnik fonetyczny (akcenty + szyfry).
  Funkcja `_jezyk_kompletny(kod)` filtruje paczki: wymaga `podstawy.yaml`
  + 4 podfoldery (`akcenty/`, `szyfry/`, `rezyser/`, `gui/`), każdy
  z ≥1 plikiem `*.yaml`.
- Paczki wdrożone (stan 13.9): {inne_paczki} — to Twoje wzorce stylu.
- Paczka tworzona: `dictionaries/{kod_jezyka}/` — Manager Reguł utworzył
  już cztery podfoldery. Twoje zadanie to TYLKO `podstawy.yaml`.
  Akcenty, szyfry, tryby Reżysera i tłumaczenie UI generujesz
  oddzielnymi promptami z Managera lub kopiujesz z istniejących paczek.

# ZADANIE
Utwórz plik `dictionaries/{kod_jezyka}/podstawy.yaml` dla języka
**{etykieta_jezyka}** (kod ISO 639-1: `{kod_jezyka}`, endonim:
**{natywna}**).

# PLIKI REFERENCYJNE (otwórz przed pisaniem)
- `dictionaries/de/podstawy.yaml` — najbogatszy wzorzec: zawiera ß, Umlauty,
  pełen zestaw europejskich diakrytyków (á/à/â/ã/é/í/ñ/ó/ø/ú/ý/ÿ).
- `dictionaries/it/podstawy.yaml` — wzorzec łaciński z minimalnymi diakrytykami.
- `dictionaries/ru/podstawy.yaml` — wzorzec dla alfabetu niełacińskiego.
- `dictionaries/pl/podstawy.yaml` — referencja minimalna, bazowa paczka.
Wybierz wzorzec najbliższy charakterystyce języka {natywna} (alfabet
łaciński/cyrylicki, obecność/brak diakrytyków typu ä/ö/ç/ß).

# WYMAGANIA STRUKTURY (silnik)
1. **`id: podstawy`** i **`jezyk: {kod_jezyka}`** — pola identyfikacyjne.
2. **`lingua:`** — nazwa enuma `lingua.Language` WIELKIMI LITERAMI po
   angielsku, bez prefiksu. Lista (74 języki):
   https://github.com/pemistahl/lingua-py.
   Najczęstsze: POLISH, ENGLISH, GERMAN, FRENCH, SPANISH, PORTUGUESE,
   ITALIAN, RUSSIAN, FINNISH, ICELANDIC, JAPANESE, CHINESE.
   Jeśli język brakuje, w komentarzu nad polem zapisz `# BRAK_W_LINGUA`
   i zostaw pole zakomentowane (silnik fallbackuje na ręczny wybór).
3. **`polskie_znaki:`** — lista par `{{ wzor, zamiana }}` opisująca
   diakrytyki języka {kod_jezyka} → ASCII. Każdy diakrytyk w obu
   wariantach: mały + wielki. Litery rosnące przy `.upper()` (np. ß→SS)
   ZAWSZE tu, NIGDY w `alfabet`.
4. **`alfabet:`** — ciąg WIELKICH LITER bez spacji. Diakrytyki nieroskie
   (np. Ä, Ö, Ü, Å) mogą trafiać NA KONIEC alfabetu. Używany przez Cezara.
5. **`slowo_akcent:`** (kontrakt 13.3+) — lista natywnych słów
   wyzwalających parser akcentów w trybie Reżysera. Wszystkie wpisy
   małymi literami. Wzorce: PL `["akcent"]`; DE `["akzent", "aussprache"]`;
   IT `["accento", "accentato"]`; RU `["акцент", "акцентом", "говор"]`.
   Dla idiomów z fleksją dodaj 2-3 najczęstsze formy.

# WYMAGANIA NATYWNOŚCI
Pole `etykieta:`, `opis:` i wszystkie komentarze YAML w pliku piszesz
w języku **{natywna}**. Wzorzec etykiety z 7 wdrożonych paczek:
- pl: „Polski – podstawy fonetyczne"
- en: „English – phonetic basics"
- de: „Deutsch – phonetische Grundlagen"
- it: „Italiano – fondamenti fonetici"
- ru: „Русский – фонетические основы"
- fi: „Suomi – foneettiset perusteet"
- is: „Íslenska – hljóðfræðilegur grunnur"
Mieszanie polskich fraz z natywnymi (np. „French – podstawy fonetyczne")
jest BŁĘDEM krytycznym.

# PROCEDURA
1. Otwórz pliki referencyjne (Read).
2. Zaprojektuj zawartość `podstawy.yaml` — kompletna sekcja
   `polskie_znaki` (wszystkie diakrytyki języka {natywna} obu wielkości),
   pełen `alfabet`, lista `slowo_akcent`.
3. Zapisz plik w `dictionaries/{kod_jezyka}/podstawy.yaml` (Write).
4. Zweryfikuj: `python -c "import yaml; yaml.safe_load(open('dictionaries/{kod_jezyka}/podstawy.yaml', encoding='utf-8'))"`
   nie wyrzuca wyjątku.
5. Zweryfikuj: `python -c "import core_poliglota; print(core_poliglota._jezyk_kompletny('{kod_jezyka}'))"` —
   zwróci `False`, dopóki paczka nie ma akcentów/szyfrów/trybów. To
   oczekiwane na tym etapie; raportuj userowi że potrzebne są kolejne
   prompty z Managera Reguł.
6. W odpowiedzi raportuj: ile pozycji ma `polskie_znaki`, ile liter ma
   `alfabet`, jakie wartości ustawiłeś dla `lingua`, `etykieta`, `slowo_akcent`.
"""


# =============================================================================
# PROMPT 3: Szyfr algorytmiczny – poproś AI o specyfikację + zmianę kodu
# =============================================================================
def prompt_szyfr_algorytm(id_pliku: str, etykieta: str,
                          opis_efektu: str,
                          jezyk_bazowy: str = "pl") -> str:
    natywna_baza = _natywna_nazwa_jezyka(jezyk_bazowy)
    return f"""# ROLA
Jesteś agentem AI z dostępem do plików projektu „Reżyser Audio GPT".
Masz narzędzia: Read, Write, Edit, Glob, Grep, Bash. Zadanie: dodać do
projektu nowy szyfr algorytmiczny — wymaga to **dwóch** zmian: pliku YAML
+ funkcji Python w `core_poliglota.py`.

# KONTEKST PROJEKTU
- `core_poliglota.py` — silnik fonetyczny + dispatcher algorytmów. Mapa
  `_ALGORYTMY` mapuje `id` szyfru na funkcję Pythona implementującą
  algorytm. Plik YAML `kategoria: szyfr` z polem `algorytm: <id>` mówi
  silnikowi, żeby zamiast listy `zamiany:` wywołać funkcję `_algorytm_<id>`.
- Istniejące algorytmy (referencja): odwracanie, typoglikemia, jakanie,
  samogloskowiec, waz. Wszystkie w `core_poliglota.py` jako `_algorytm_*`.
- Paczka tego zadania: `dictionaries/{jezyk_bazowy}/`
  (język {natywna_baza}).

# ZADANIE
Zaprojektuj i wdroż szyfr algorytmiczny **{etykieta}** (id: `{id_pliku}`).

OPIS EFEKTU (od użytkownika):
> {opis_efektu}

# PLIKI REFERENCYJNE (otwórz przed pisaniem)
1. `core_poliglota.py` — szukaj funkcji `_algorytm_*` (np. `_algorytm_odwracanie`,
   `_algorytm_typoglikemia`) i mapy `_ALGORYTMY`. Zwróć uwagę na sygnaturę
   `(tekst: str, regula: dict) -> str` i na sposób korzystania z `random`.
2. `dictionaries/pl/szyfry/odwracanie.yaml` — wzorzec konwencji
   `rozwiniecia:` (regexy podstawiające skrótowce „itd." → „i tak dalej"
   PRZED właściwym przetwarzaniem). Zasady: granice słowa `\\b...\\b`,
   kropka opcjonalna `\\.?`, przecinek opcjonalny `,?`, dwa warianty dla
   częstych typo („m.in." vs „mi.in."), spacja po rozwinięciu.
3. `dictionaries/{jezyk_bazowy}/szyfry/cezar.yaml` — wzorzec stylu YAML
   dla paczki bazowej (komentarze natywne).

# WYMAGANIA STRUKTURY YAML
```yaml
id: {id_pliku}
etykieta: "{etykieta}"
opis: |
  <2-4 zdania w języku {natywna_baza} — co robi szyfr>.
iso: {jezyk_bazowy}
kategoria: szyfr
kolejnosc: 100
algorytm: {id_pliku}

# <Opcjonalne parametry czytane z regula['<klucz>'] przez funkcję Python>
# parametr_1: wartosc
```

# WYMAGANIA KODU PYTHON (`core_poliglota.py`)
1. Funkcja `_algorytm_{id_pliku}(tekst: str, regula: dict) -> str` —
   sygnatura jak istniejące algorytmy.
2. Wpis w mapie `_ALGORYTMY`: `"{id_pliku}": _algorytm_{id_pliku}`.
3. **Idempotentność**: dwukrotne uruchomienie z tym samym seedem zwraca
   ten sam wynik (chyba że losowość jest celowa — wtedy udokumentuj).
4. Operuj znak-po-znaku lub słowo-po-słowie, **zachowuj** białe znaki
   i interpunkcję (chyba że efekt wymaga ich zmiany).
5. Losowość: użyj `random` (już zaimportowany w core_poliglota.py).
6. **NIE** wprowadzaj nowych zależności zewnętrznych.

# WYMAGANIA NATYWNOŚCI
`etykieta`, `opis`, komentarze YAML w {natywna_baza}. Komentarze
i docstring w `core_poliglota.py` po polsku (zgodnie z konwencją silnika
— polski jest językiem deweloperskim projektu).

# PROCEDURA
1. Otwórz pliki referencyjne (Read).
2. Zaprojektuj algorytm w głowie + ewentualne parametry konfigurowalne
   z YAML.
3. Edit `core_poliglota.py` — dopisz funkcję `_algorytm_{id_pliku}`
   i wpis w `_ALGORYTMY`.
4. Write `dictionaries/{jezyk_bazowy}/szyfry/{id_pliku}.yaml`.
5. Zweryfikuj parsowalność:
   `python -c "import yaml; yaml.safe_load(open('dictionaries/{jezyk_bazowy}/szyfry/{id_pliku}.yaml', encoding='utf-8'))"`.
6. Zweryfikuj import: `python -c "import core_poliglota; print('{id_pliku}' in core_poliglota._ALGORYTMY)"` — powinno zwrócić `True`.
7. Rozważ napisanie testu jednostkowego (idempotentność, zachowanie
   białych znaków).
8. W odpowiedzi raportuj: ile linii kodu dodałeś w `core_poliglota.py`,
   parametry algorytmu i wynik testu idempotentności (jeśli zrobiłeś).

# WSKAZÓWKA: KONWENCJA `rozwiniecia:` (jeśli używasz)
Jeśli algorytm dokonuje podstawień tekstowych PRZED właściwym
przetwarzaniem (np. rozwija skrótowce „itd." w „i tak dalej"), wzoruj się
na `dictionaries/pl/szyfry/odwracanie.yaml::rozwiniecia` — zachowaj
zasady (granice słowa, kropka/przecinek opcjonalne, kolejność szczegółowe
przed ogólnymi, brak `regex: true` w `rozwiniecia` — regex tam jest
domyślny). Bez tych zasad regex łapie fragmenty słów (np. „tj"
w „atakujący") i tworzy artefakty.
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
            "uwagi": (
                f"Akcent czyszczący w paczce `{jezyk_bazowy}/` "
                "(`kategoria: oczyszczenie`). Struktura plików tego typu "
                "jest identyczna we wszystkich wdrożonych paczkach — "
                "różni się TYLKO etykieta + opis + komentarze (natywne). "
                "Skopiuj prompt do agenta AI z dostępem do projektu — "
                "agent otworzy gotowy wzorzec z innej paczki, przetłumaczy "
                "tekstowe pola na język natywny i zapisze plik."
            ),
        }

    if typ == TYP_AKCENT_NAPRAWIACZ:
        return {
            "tryb":     "SZABLON_I_PROMPT",
            "yaml":     szablon_naprawiacz(id_pliku, etykieta, jezyk_bazowy),
            "prompt":   prompt_naprawiacz(id_pliku, etykieta, jezyk_bazowy),
            "docelowy": f"{jezyk_bazowy}/akcenty/{id_pliku}.yaml",
            "uwagi": (
                f"Naprawiacz tagów w paczce `{jezyk_bazowy}/` "
                "(`kategoria: naprawiacz`). Tryb specjalny — wstrzykuje kod "
                "ISO do plików wynikowych (HTML/DOCX), nie modyfikuje "
                "treści. Skopiuj prompt do agenta AI z dostępem do projektu "
                "— agent otworzy gotowy wzorzec z innej paczki, przetłumaczy "
                "tekstowe pola na język natywny i zapisze plik."
            ),
        }

    if typ == TYP_AKCENT:
        return {
            "tryb":     "SZABLON_I_PROMPT",
            "yaml":     szablon_akcent(id_pliku, etykieta, iso, jezyk_bazowy),
            "prompt":   prompt_akcent(id_pliku, etykieta, iso, jezyk_bazowy),
            "docelowy": f"{jezyk_bazowy}/akcenty/{id_pliku}.yaml",
            "uwagi": (
                "Szablon ma pusty pipeline zamian fonetycznych. Skopiuj "
                "prompt do agenta AI z dostępem do projektu (Claude Code, "
                "Cursor, Aider) — agent otworzy pliki referencyjne, "
                f"zaprojektuje listę `zamiany:`, zapisze plik w "
                f"`dictionaries/{jezyk_bazowy}/akcenty/{id_pliku}.yaml` i uruchomi "
                "`odswiez_rezysera.py` (aktualizuje dispatcher). Potem "
                'kliknij „Odśwież akcenty Reżysera" na Stronie głównej.'
            ),
        }

    if typ == TYP_SZYFR_ZAMIANY:
        return {
            "tryb":     "SZABLON_I_PROMPT",
            "yaml":     szablon_szyfr_zamiany(id_pliku, etykieta, jezyk_bazowy),
            "prompt":   prompt_szyfr_zamiany(id_pliku, etykieta, jezyk_bazowy),
            "docelowy": f"{jezyk_bazowy}/szyfry/{id_pliku}.yaml",
            "uwagi": (
                f"Szablon gotowy do edycji w paczce `{jezyk_bazowy}/`. "
                "Skopiuj prompt do agenta AI z dostępem do projektu "
                "(Claude Code, Cursor, Aider) — agent otworzy wzorce stylu "
                "z innych paczek, zaprojektuje listę `zamiany:` realizującą "
                "efekt i zapisze plik w lokalizacji docelowej."
            ),
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
            "uwagi": (
                f"Szablon oparty o tryb Audiobook (paczka `{jezyk_bazowy}/`). "
                "Skopiuj prompt do agenta AI z dostępem do projektu (Claude "
                "Code, Cursor, Aider) — agent otworzy `tryb_audiobook.yaml` "
                "z innej wdrożonej paczki, zaprojektuje `prompt_systemowy`, "
                "`przypomnienie_uzytkownika` i `slowa_wyzwalajace` w języku "
                "natywnym i zapisze plik w lokalizacji docelowej."
            ),
        }

    if typ == TYP_POSTPRODUKCJA:
        nazwa_pliku = f"postprod_{id_pliku}" if not id_pliku.startswith("postprod_") \
                      else id_pliku
        return {
            "tryb":     "SZABLON_I_PROMPT",
            "yaml":     szablon_postprodukcja(id_pliku, etykieta, jezyk_bazowy),
            "prompt":   prompt_postprodukcja(id_pliku, etykieta, jezyk_bazowy),
            "docelowy": f"{jezyk_bazowy}/rezyser/{nazwa_pliku}.yaml",
            "uwagi": (
                f"Szablon postprodukcji iteruje po rozdziałach (paczka "
                f"`{jezyk_bazowy}/`). Skopiuj prompt do agenta AI z dostępem "
                "do projektu — agent zaprojektuje `prompt_systemowy`, "
                "`prompt_uzytkownika_szablon` (z placeholderami `{naglowek}`, "
                "`{probka}`) i `regex_podzial_rozdzialow` dopasowany do "
                "natywnych nazw rozdziałów (Rozdział/Kapitel/Capitolo/Глава/...)."
            ),
        }

    if typ == TYP_JEZYK_BAZOWY:
        return {
            "tryb":     "SZABLON_I_PROMPT",
            "yaml":     szablon_podstawy(id_pliku, etykieta),
            "prompt":   prompt_jezyk_bazowy(id_pliku, etykieta),
            "docelowy": f"{id_pliku}/podstawy.yaml",
            "uwagi": (
                f"Manager utworzy folder `dictionaries/{id_pliku}/` z podfolderami "
                f"`akcenty/`, `szyfry/`, `rezyser/` i `gui/`. Szablon `podstawy.yaml` "
                f"ma markery `<UZUPEŁNIJ NATYWNIE>`. Skopiuj prompt do agenta AI "
                f"z dostępem do projektu (Claude Code, Cursor, Aider) — agent "
                f"otworzy `dictionaries/de/podstawy.yaml` lub `it/podstawy.yaml` "
                f"jako wzorzec i zapisze kompletną zawartość. Tłumaczenie UI "
                f"(`gui/ui.yaml`) generuje `buduj_wielojezyczne_ui.py`. Tryby "
                f"Reżysera (`rezyser/tryb_*.yaml`) skopiuj z `pl/rezyser/` lub "
                f"poproś agenta o przetłumaczenie ich na język natywny — silnik "
                f"wymaga ≥1 pliku w `rezyser/`, żeby uznać język za kompletny."
            ),
        }

    if typ == TYP_SZYFR_ALGORYTM:
        return {
            "tryb":     "PROMPT",
            "yaml":     "",
            "prompt":   prompt_szyfr_algorytm(id_pliku, etykieta, opis_efektu, jezyk_bazowy),
            "docelowy": f"{jezyk_bazowy}/szyfry/{id_pliku}.yaml",
            "uwagi": (
                "UWAGA: szyfry algorytmiczne wymagają funkcji w "
                "`core_poliglota.py`. Manager NIE tworzy żadnego pliku — "
                "skopiuj prompt do agenta AI z dostępem do projektu "
                "(Claude Code, Cursor, Aider). Agent doda funkcję do "
                "`core_poliglota.py` + wpis w mapie `_ALGORYTMY` + plik YAML "
                f"w `dictionaries/{jezyk_bazowy}/szyfry/{id_pliku}.yaml`."
            ),
        }

    raise ValueError(f"Nieznany typ reguły: {typ!r}")
