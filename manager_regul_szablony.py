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
TYP_AKCENT               = "akcent"
TYP_SZYFR_ZAMIANY        = "szyfr_zamiany"
TYP_SZYFR_ALGORYTM       = "szyfr_algorytm"
TYP_TRYB_REZYSERA        = "tryb_rezysera"
TYP_POSTPRODUKCJA        = "postprodukcja"

# Metadane prezentowane w ComboBox-ie kreatora (kolejność = priorytet A11y)
LISTA_TYPOW: list[tuple[str, str, str]] = [
    # (id, etykieta, krótki opis)
    (
        TYP_AKCENT,
        "Nowy akcent fonetyczny (np. duński, szwedzki)",
        "Plik w <jezyk>/akcenty/. Manager tworzy szablon + prompt dla AI, "
        "który wygeneruje listę zamian fonetycznych.",
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
    return f"""Jesteś ekspertem w fonetyce i transliteracji międzyjęzykowej.
Tworzysz regułę fonetyczną dla aplikacji „Reżyser Audio GPT" (moduł Poliglota).

## CEL
Wygeneruj kompletny plik YAML akcentu `{id_pliku}.yaml`, który upodobni
tekst w języku **{natywna_baza}** (`{jezyk_bazowy}`, język źródłowy paczki)
do wymowy w języku o kodzie ISO **{iso}** (język docelowy syntezatora TTS).
Nazwa akcentu widoczna dla użytkownika: **{etykieta}**.

## ZASADA NATYWNOŚCI (KRYTYCZNA)
Pole `opis:` oraz wszystkie komentarze YAML pisz w języku
**{natywna_baza}** — tym samym, w którym pisana jest cała paczka
`dictionaries/{jezyk_bazowy}/`. Wzoruj się na komentarzach z
`dictionaries/{jezyk_bazowy}/akcenty/<dowolny>.yaml`, jeśli paczka ma
już akcenty (DE, IT, RU, FI, IS, EN, PL — mają). Mieszanie polskiego
z natywnym (np. „Akcent finski" zamiast „Suomi-aksentti") jest BŁĘDEM.

## FORMAT WYJŚCIOWY (DOSŁOWNIE TEN SZABLON)
```yaml
# <Nagłówek natywnie w {natywna_baza}: nazwa akcentu + jego cel>

id: {id_pliku}
etykieta: "{etykieta}"
opis: |
  <Opis natywnie w {natywna_baza}, 2-4 zdania: pod jaki syntezator TTS
  jest przeznaczony akcent (np. „dla syntezatora finskiego Satu/Mikko"),
  jakie zjawiska fonetyczne wymusza (ubezdźwięcznienie, tłumienie
  syczenia, transliteracja umlautów itp.).>
iso: {iso}
kategoria: akcent
kolejnosc: 100
czysc_tekst_tts: true
normalizuj_liczby: true
usun_polskie_znaki: true
skleja_pojedyncze_litery: true
zamiany:
  # <Komentarze sekcyjne natywnie: „Trigramme zuerst" / „Trigrammi prima" / itp.>
  - {{ wzor: "ch", zamiana: "h" }}
  - {{ wzor: "Ch", zamiana: "H" }}
  # ...kolejne pary...
```

## ZASADY ŻELAZNE
1. Lista `zamiany` MUSI być uporządkowana: TRIGRAMY (sch, tsch) PRZED
   DWUZNAKAMI (ch, cz, sz, rz), DWUZNAKI PRZED JEDNOZNAKAMI (c, s, z, r).
   Inaczej zamiana „c → ts" rozwali zapis „ch" / „cz" wcześniej.
2. Każdy dwuznak/trigram występuje w dwóch wariantach: małymi i z wielką
   pierwszą literą (np. „Cz" → „Ts", „Sch" → „S"). Dla niektórych języków
   warto dodać też wariant ALL-CAPS (np. „SCH" → „S" w niemieckim).
3. Jeśli potrzebujesz regexa, dodaj `regex: true` w wierszu. Przykład:
   `- {{ wzor: 'ci(?=[aąeęoóuy])', zamiana: "ć", regex: true }}`.
4. **Baza pipeline'u zależy od `jezyk_bazowy = {jezyk_bazowy}`.** Flaga
   `usun_polskie_znaki: true` (mimo nazwy historycznej!) usuwa diakrytyki
   języka **{jezyk_bazowy}** zgodnie z mapą w
   `dictionaries/{jezyk_bazowy}/podstawy.yaml::polskie_znaki`. Dla:
     - PL: usuwa ą/ę/ł/ó/ś/ć/ń/ż/ź → operujesz na „aelusсcnzz"
     - DE: usuwa ä/ö/ü/ß + polskie diakrytyki → operujesz na 26 ASCII liter
       + „ss" zamiast „ß" + „ae"/„oe"/„ue" jeśli paczka tak zdecydowała
     - RU: usuwa ё → operujesz na 32 cyrylickich literach
     - IT: usuwa à/è/é/ì/ò/ù → operujesz na 21 ASCII literach
   Twoje wzory `wzor:` MUSZĄ działać NA TEKŚCIE PO usun_polskie_znaki,
   tzn. operuj na ASCII odpowiednikach języka {jezyk_bazowy}.
5. Pole `opis:` i wszystkie komentarze YAML w języku **{natywna_baza}**
   (zasada natywności wyżej).
6. Zwróć TYLKO treść pliku YAML – żadnego dodatkowego komentarza,
   żadnych bloków ``` wokół, żadnych wstępów ani podsumowań.

## WZORZEC POPRAWNEGO WYNIKU
Wybierz wzorzec dopasowany do paczki bazowej:

- Jeśli `jezyk_bazowy = pl` → wzorcuj się na
  `dictionaries/pl/akcenty/finski.yaml` (komentarze po polsku).
- Jeśli `jezyk_bazowy = de` → `dictionaries/de/akcenty/finski.yaml`
  (komentarze po niemiecku, zamiany dostosowane do bazy DE: „sch", „tsch",
  „ch", Umlauty, ß).
- Jeśli `jezyk_bazowy = it` → `dictionaries/it/akcenty/finski.yaml`
  (komentarze po włosku).
- Jeśli `jezyk_bazowy = ru` → `dictionaries/ru/akcenty/finski.yaml`
  (komentarze po rosyjsku, zamiany na cyrylicy).
- Pozostałe paczki (en/fi/is) — analogicznie: szukaj odpowiadającego
  pliku `dictionaries/{jezyk_bazowy}/akcenty/<dowolny>.yaml` i zachowaj
  konwencje stylu.

Wzorzec PL (do podejrzenia struktury, nie do skopiowania języka):
```yaml
id: finski
etykieta: "Fiński (np. Satu / Mikko / Heidi)"
opis: |
  Upodabnia polski tekst do fińskiej wymowy: ubezdźwięcznia spółgłoski
  (b→p, d→t, g→k), tłumi syczenie, zamienia „w" na „v".
iso: fi
kategoria: akcent
kolejnosc: 90
czysc_tekst_tts: true
normalizuj_liczby: true
usun_polskie_znaki: true
skleja_pojedyncze_litery: true
zamiany:
  - {{ wzor: "ch", zamiana: "h"  }}
  - {{ wzor: "Ch", zamiana: "H"  }}
  - {{ wzor: "cz", zamiana: "ts" }}
  - {{ wzor: "Cz", zamiana: "Ts" }}
  # ... reszta par ...
```

Zwróć gotowy YAML dla akcentu **{etykieta}** (ISO `{iso}`, język źródłowy
**{natywna_baza}** = `{jezyk_bazowy}`). Po otrzymaniu odpowiedzi
użytkownik wklei ją do `dictionaries/{jezyk_bazowy}/akcenty/{id_pliku}.yaml`,
a następnie uruchomi `odswiez_rezysera.py` (aktualizacja dispatchera) i
przycisk „Odśwież akcenty Reżysera" w GUI.
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
    return f"""Jesteś projektantem regułowych transformacji tekstu.
Tworzysz szyfr typu „czyste zamiany" dla aplikacji „Reżyser Audio GPT"
(moduł Poliglota, paczka `dictionaries/{jezyk_bazowy}/`).

## CEL
Wygeneruj kompletny plik `dictionaries/{jezyk_bazowy}/szyfry/{id_pliku}.yaml`
realizujący efekt tekstowy o nazwie **{etykieta}**.

## ZASADA NATYWNOŚCI (KRYTYCZNA)
Pole `opis:`, nagłówek pliku oraz wszystkie komentarze YAML pisz w języku
**{natywna_baza}**. Wzorzec konwencji: dowolny plik z
`dictionaries/{jezyk_bazowy}/szyfry/`, szczególnie `cezar.yaml` (komentarze
po niemiecku/włosku/rosyjsku itd. dla wdrożonych paczek).

## FORMAT WYJŚCIOWY (DOSŁOWNIE TEN SZABLON)
```yaml
# <Nagłówek natywnie w {natywna_baza}: nazwa szyfru + jednozdaniowy opis>

id: {id_pliku}
etykieta: "{etykieta}"
opis: |
  <Opis natywnie, 2-4 zdania: co dokładnie robi ten szyfr na poziomie znaków,
  jaki uzyskuje efekt percepcyjny dla słuchacza (np. „tekst brzmi jak hacker
  speak", „symuluje seplenienie"), kiedy ma sens go włączyć.>
iso: {jezyk_bazowy}
kategoria: szyfr
kolejnosc: 100

# Pipeline – dla szyfrów zwykle wszystko OFF poza listą zamian.
czysc_tekst_tts: false
normalizuj_liczby: false
usun_polskie_znaki: false
skleja_pojedyncze_litery: false

zamiany:
  # <Komentarz natywnie sekcyjny: „— Cyfry zamiast samogłosek —" / itp.>
  - {{ wzor: "<wzor>", zamiana: "<zamiana>" }}
  # ...kolejne pary...
```

## ZASADY ŻELAZNE
1. **Lista `zamiany`** uporządkowana: dwuznaki/trigramy PRZED pojedynczymi
   znakami. Dla każdego wzoru rozważ wariant małych i wielkich liter.
2. **Wzór ASCII vs natywny**: dla `iso: {jezyk_bazowy}` szyfr operuje na
   znakach języka {natywna_baza}. Jeśli efekt ma działać też na literach
   z diakrytykami (à, é, ä, ё), uwzględnij je explicit lub dodaj wzór regex.
3. **Regex**: jeśli używasz wyrażenia regularnego, dodaj `regex: true`
   w wierszu zamiany.
4. **`iso: {jezyk_bazowy}`** — szyfr przypisany do paczki bazowej.
5. **`opis:` i komentarze** w języku **{natywna_baza}** (zasada natywności).
6. **Zwróć TYLKO treść pliku YAML** — żadnego dodatkowego komentarza,
   bez bloków ```, bez wstępów.

## WZORCOWY FRAGMENT (tylko struktura, treść tłumacz na {natywna_baza})
```yaml
id: hacker_speak
etykieta: "Hacker Speak (l33t)"
opis: |
  Każda samogłoska zostaje podmieniona na cyfrę o podobnym kształcie
  (a→4, e→3, i→1, o→0, s→5). Spółgłoski pozostają nietknięte.
  Efekt: tekst wygląda jak post z forum z lat 2000.
iso: pl
kategoria: szyfr
kolejnosc: 100
czysc_tekst_tts: false
normalizuj_liczby: false
usun_polskie_znaki: false
skleja_pojedyncze_litery: false
zamiany:
  - {{ wzor: "a", zamiana: "4" }}
  - {{ wzor: "A", zamiana: "4" }}
  - {{ wzor: "e", zamiana: "3" }}
  - {{ wzor: "E", zamiana: "3" }}
  # ... reszta ...
```

Zwróć gotowy plik dla szyfru **{etykieta}** w paczce **{natywna_baza}**.
Po otrzymaniu odpowiedzi użytkownik zapisze ją w
`dictionaries/{jezyk_bazowy}/szyfry/{id_pliku}.yaml` i odświeży drzewo
w Managerze Reguł.
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
    return f"""Jesteś projektantem promptów AI dla aplikacji „Reżyser Audio GPT".
Tworzysz nowy tryb Reżysera dla paczki `dictionaries/{jezyk_bazowy}/`
(język bazowy: **{natywna_baza}**).

## CEL
Wygeneruj kompletny plik
`dictionaries/{jezyk_bazowy}/rezyser/tryb_{id_pliku}.yaml`
realizujący tryb twórczy o nazwie **{etykieta}**.

## ZASADA NATYWNOŚCI (KRYTYCZNA)
Wszystkie teksty pisane „dla człowieka" — `etykieta`, nagłówek pliku,
komentarze YAML, `prompt_systemowy`, `przypomnienie_uzytkownika` —
i listy słów wyzwalających MUSZĄ być w języku **{natywna_baza}**.

Pole `jezyk_odpowiedzi:` ustaw na `{natywny_jezyk_odp}` (forma używana
przez prompt systemowy w idiomie języka {natywna_baza}; wzorzec z paczek
wdrożonych: PL „polsku", EN „English", DE „Deutsch", IT „italiano",
RU „по-русски", FI „suomeksi", IS „á íslensku").

Najlepszy wzorzec konwencji:
`dictionaries/{jezyk_bazowy}/rezyser/tryb_audiobook.yaml` — pokazuje
gotowy prompt systemowy po {natywna_baza}, natywne słowa wyzwalające
streszczenie, formatowanie nagłówków sekcji emoji.

## FORMAT WYJŚCIOWY (DOSŁOWNIE TEN SZABLON)
```yaml
# <Nagłówek natywnie w {natywna_baza}: nazwa trybu + jednoliniowy opis>

id: {id_pliku}
etykieta: "{etykieta}"
kategoria: tryb
kolejnosc: <int 10-90, np. 30 dla audiobook, 50 dla scenariusza>

model: gpt-4o
temperatura: <0.0-1.0, np. 0.85 dla literackich, 0.5 dla skryptowych>
jezyk_odpowiedzi: {natywny_jezyk_odp}
zapis_do_pliku: true

prompt_systemowy: |
  # <Rola w {natywna_baza}, np. „Rolle: Bestseller-Autor (Klassische Prosa)">

  <Pierwsze zdanie w {natywna_baza}, ZAWSZE zawiera frazę „WYŁĄCZNIE po
  {{jezyk_odpowiedzi}}" w odpowiedniej formie idiomu (DE: „AUSSCHLIESSLICH
  auf {{jezyk_odpowiedzi}}"; IT: „ESCLUSIVAMENTE in {{jezyk_odpowiedzi}}";
  RU: „ИСКЛЮЧИТЕЛЬНО на {{jezyk_odpowiedzi}}").>

  <Opis trybu w {natywna_baza}: 2-4 zdania o tym, jak ma pisać AI.>

  ### 🌍 <Nagłówek natywnie typu „Żelazne Zasady Świata">:
  {{world_context}}

  ### 📖 <Nagłówek natywnie typu „Zasady trybu X">:
  1. **<Tytuł zasady NATYWNIE>:** <opis zasady NATYWNIE>.
  2. **<Tytuł zasady NATYWNIE>:** <opis zasady NATYWNIE>.
  3. **<Domykanie scen NATYWNIE>:** - <DOMYŚLNIE: opis NATYWNIE>.
     - <WYJĄTEK (FINAŁ/EPILOG): opis NATYWNIE>.

sufiksy: {{}}

przypomnienie_uzytkownika: |


  (<PRZYPOMNIENIE NATYWNIE: krótka 1-2-zdaniowa rekapitulacja kluczowych
  zasad trybu, w {natywna_baza}>.)

slowa_wyzwalajace:
  streszczenie:
    - <natywne 1>
    - <natywne 2>
    - <natywne 3>
    - <natywne 4>

stosuj_akcenty_fonetyczne: false
```

## ZASADY ŻELAZNE
1. **Sekcja `prompt_systemowy:`** jest doklejana do każdego promptu
   wysyłanego do OpenAI. MUSI zawierać placeholder `{{world_context}}`
   (silnik wstawia wczytaną Księgę Świata) i `{{jezyk_odpowiedzi}}` (silnik
   wstawia wartość z pola `jezyk_odpowiedzi:`).
2. **Lista `slowa_wyzwalajace.streszczenie`** zawiera 3-5 natywnych słów
   typowo używanych przez użytkowników mówiących {natywna_baza}, gdy proszą
   AI o streszczenie. Wszystkie wpisy MAŁYMI literami (silnik robi
   lower-case porównanie).
3. **`stosuj_akcenty_fonetyczne`** ustaw na `true` dla trybów generujących
   dialogi z tagami postaci, `false` dla prozy literackiej bez tagów.
4. **`temperatura:`** typowo 0.7-0.9 dla trybów twórczych; niższa dla
   trybów strukturalnych (skrypt, postprodukcja).
5. **`kolejnosc:`** określa pozycję w dropdownie GUI (rosnąco). 30 =
   audiobook, 40 = burza mózgów, 50 = skrypt.
6. **Komentarze YAML** w {natywna_baza}.
7. **Zwróć TYLKO treść pliku YAML** — bez bloków ```, bez wstępów.

## WZORZEC GOTOWEGO PLIKU
Najlepszy gotowy wzorzec do podejrzenia:
`dictionaries/{jezyk_bazowy}/rezyser/tryb_audiobook.yaml`. Zachowaj:
- styl nagłówków sekcji z emoji (🌍, 📖) w prompcie systemowym,
- format `**TYTUŁ ZASADY:** opis` dla zasad numerowanych,
- konwencję natywnego nawiasu w etykiecie (np. „Hörbuch (Prosa, Kapitel,
  DATEI SCHREIBEN)" DE, „Аудиокнига (Проза, главы, ЗАПИСЫВАЕТ В ФАЙЛ)" RU).

Zwróć gotowy plik dla trybu **{etykieta}** w paczce **{natywna_baza}**.
Po otrzymaniu odpowiedzi użytkownik zapisze ją w
`dictionaries/{jezyk_bazowy}/rezyser/tryb_{id_pliku}.yaml`. Tryby
Reżysera są ładowane dynamicznie przez `przepisy_rezysera.py` — wystarczy
„Odśwież drzewo" w Managerze i restart aplikacji.
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
    return f"""Jesteś projektantem promptów AI dla aplikacji „Reżyser Audio GPT".
Tworzysz nową postprodukcję (iteracyjne przetwarzanie pliku rozdział-po-
rozdziale) dla paczki `dictionaries/{jezyk_bazowy}/`
(język bazowy: **{natywna_baza}**).

## CEL
Wygeneruj kompletny plik
`dictionaries/{jezyk_bazowy}/rezyser/postprod_{id_pliku}.yaml`
realizujący zadanie postprodukcyjne o nazwie **{etykieta}**.

## ZASADA NATYWNOŚCI (KRYTYCZNA)
Wszystkie teksty „dla człowieka" — `etykieta`, nagłówek pliku, komentarze,
`prompt_systemowy`, `prompt_uzytkownika_szablon`,
`etykieta_fragment_zbyt_krotki`, `etykieta_bled_brak_kredytow` — MUSZĄ
być w języku **{natywna_baza}**.

Pole `jezyk_odpowiedzi:` ustaw na `{natywny_jezyk_odp}`.

Najlepszy wzorzec konwencji:
`dictionaries/{jezyk_bazowy}/rezyser/postprod_tytuly.yaml`.

## FORMAT WYJŚCIOWY (DOSŁOWNIE TEN SZABLON)
```yaml
# <Nagłówek natywnie w {natywna_baza}: nazwa zadania postprodukcyjnego>

id: {id_pliku}
etykieta: "{etykieta}"
kategoria: postprodukcja
kolejnosc: <int 10-90, np. 20 dla generatora tytułów>

model: gpt-4o-mini
temperatura: <0.0-1.0, typowo 0.5-0.8>
jezyk_odpowiedzi: {natywny_jezyk_odp}

prompt_systemowy: |
  <Rola AI w {natywna_baza}, 1-2 zdania o oczekiwanym formacie wyjścia.
  Przykład PL: „Jesteś redaktorem audiobooków. Twoja odpowiedź zawiera
  WYŁĄCZNIE tytuł rozdziału — jedno zdanie, bez komentarzy.">

prompt_uzytkownika_szablon: |
  <Tekst w {natywna_baza} z placeholderami {{naglowek}} i {{probka}}.
  Format:
    Oto fragment tekstu ({{naglowek}}). <natywne polecenie dla AI>.

    TREŚĆ:
    {{probka}}>

regex_podzial_rozdzialow: "<regex łapiący nagłówki w {natywna_baza}>"
min_dlugosc_fragmentu: 50
max_dlugosc_probki: 6000

etykieta_fragment_zbyt_krotki: "<NATYWNIE: np. '(Fragment zbyt krótki)'>"
etykieta_bled_brak_kredytow: "<NATYWNIE: np. '(Błąd — brak kredytów API)'>"
```

## ZASADY ŻELAZNE
1. **`prompt_uzytkownika_szablon:`** MUSI zawierać oba placeholdery
   `{{naglowek}}` (silnik wstawia tytuł rozdziału) i `{{probka}}` (silnik
   wstawia treść rozdziału).
2. **`regex_podzial_rozdzialow:`** dopasowany do tego, jak rozdziały są
   nazwane w plikach projektu w {natywna_baza}. Przykładowe wzorce:
     - PL: `"(?i)\\\\n*(Prolog|Rozdział \\\\d+|Epilog)\\\\n*"`
     - DE: `"(?i)\\\\n*(Prolog|Kapitel \\\\d+|Epilog)\\\\n*"`
     - IT: `"(?i)\\\\n*(Prologo|Capitolo \\\\d+|Epilogo)\\\\n*"`
     - EN: `"(?i)\\\\n*(Prologue|Chapter \\\\d+|Epilogue)\\\\n*"`
     - RU: `"(?i)\\\\n*(Пролог|Глава \\\\d+|Эпилог)\\\\n*"`.
3. **`min_dlugosc_fragmentu:`** — minimalna długość fragmentu (znaki) dla
   którego wywołujemy AI. Krótsze fragmenty pomijamy z komunikatem
   `etykieta_fragment_zbyt_krotki`.
4. **`max_dlugosc_probki:`** — maksimum znaków wysyłanych do API
   (kontekstowy budżet). Dla gpt-4o-mini sensowne 4000-8000.
5. **`temperatura:`** typowo 0.5-0.8 dla zadań postprodukcyjnych
   (nieliterackich; chcemy stabilności wyjścia).
6. **Komentarze YAML** w {natywna_baza}.
7. **Zwróć TYLKO treść pliku YAML** — bez bloków ```, bez wstępów.

## WZORZEC GOTOWEGO PLIKU
Najlepszy wzorzec do podejrzenia:
`dictionaries/{jezyk_bazowy}/rezyser/postprod_tytuly.yaml`.

Zwróć gotowy plik dla postprodukcji **{etykieta}** w paczce
**{natywna_baza}**. Po otrzymaniu odpowiedzi użytkownik zapisze ją w
`dictionaries/{jezyk_bazowy}/rezyser/postprod_{id_pliku}.yaml`.
Postprodukcje są ładowane dynamicznie — wystarczy „Odśwież drzewo"
w Managerze i restart aplikacji.
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
    return f"""Jesteś ekspertem w fonetyce i typologii językowej.
Pomagasz dodać nowy język bazowy do aplikacji „Reżyser Audio GPT"
(moduł Poliglota).

## CEL
Wygeneruj zawartość pliku `dictionaries/{kod_jezyka}/podstawy.yaml`
dla języka **{etykieta_jezyka}** (kod ISO 639-1: `{kod_jezyka}`,
endonim: **{natywna}**).

## KONTEKST ARCHITEKTURY (od 13.9)
Manager Reguł utworzył już cztery podfoldery: `akcenty/`, `szyfry/`,
`rezyser/`, `gui/`. Twoje zadanie to TYLKO pełna treść `podstawy.yaml`.
Pozostałe pliki (akcenty, szyfry, tryby Reżysera, tłumaczenie UI)
generuje się osobno przez kolejne akcje Managera lub dedykowane skrypty.

## ZASADA NATYWNOŚCI (KRYTYCZNA)
Wszystkie pola tekstowe w pliku — `etykieta`, `opis`, komentarze YAML —
MUSZĄ być w języku **{natywna}**. Nigdy nie miksuj polskiego z natywnym
(np. „French – podstawy fonetyczne" jest BŁĘDEM; powinno być
„Français – fondements phonétiques"). Wzorce z 7 wdrożonych paczek:

| kod | etykieta                                          |
|-----|---------------------------------------------------|
| pl  | „Polski – podstawy fonetyczne"                    |
| en  | „English – phonetic basics"                       |
| de  | „Deutsch – phonetische Grundlagen"                |
| it  | „Italiano – fondamenti fonetici"                  |
| ru  | „Русский – фонетические основы"                   |
| fi  | „Suomi – foneettiset perusteet"                   |
| is  | „Íslenska – hljóðfræðilegur grunnur"              |

## FORMAT WYJŚCIOWY (DOSŁOWNIE TEN SZABLON)
```yaml
# =============================================================================
#  <NAGŁÓWEK NATYWNIE: np. „GRUNDLAGEN DER DEUTSCHEN SPRACHE">
# =============================================================================
#  <Krótki opis natywnie: rola tego pliku w paczce języka {natywna}.
#   Wzoruj się na komentarzach w dictionaries/de/podstawy.yaml lub
#   dictionaries/it/podstawy.yaml.>
# =============================================================================

id: podstawy
jezyk: {kod_jezyka}
# <Komentarz natywnie: rola pola lingua, link do listy enum-ów>
lingua: <NAZWA_ENUMA_LINGUA_LANGUAGE>
etykieta: "{natywna} – <natywny sufiks „phonetic basics" / „phonetische Grundlagen" / itp.>"
opis: |
  <Opis natywnie, 2-4 zdania: lista najważniejszych sekcji pliku
   (transliteracja diakrytyków, alfabet, słowa wyzwalające).>

polskie_znaki:
  # <Komentarz natywnie: rola sekcji — usuwanie diakrytyków języka {kod_jezyka}>
  - {{ wzor: "<mała_z_diakrytykiem>", zamiana: "<ASCII>" }}
  - {{ wzor: "<WIELKA_Z_DIAKRYTYKIEM>", zamiana: "<ASCII>" }}
  # … wszystkie pary dla języka {natywna} …

# <Komentarz natywnie: rola pola alfabet, ostrzeżenie o literach rosnących>
alfabet: "<WIELKIE_LITERY_ALFABETU_BEZ_SPACJI>"

# <Komentarz natywnie: rola pola slowo_akcent, opis parsera>
slowo_akcent:
  - "<natywne słowo wyzwalające, małymi, np. 'akzent'>"
  # … kolejne wpisy, jeśli język ma synonimy …
```

## ZASADY ŻELAZNE
1. **Pole `lingua`** to identyfikator detektora `lingua-language-detector`.
   ZAWSZE WIELKIMI LITERAMI, ZAWSZE po angielsku, bez prefiksu i kropek:
     - polski → `POLISH`, niemiecki → `GERMAN`, hiszpański → `SPANISH`,
       francuski → `FRENCH`, portugalski → `PORTUGUESE`, rosyjski → `RUSSIAN`,
       fiński → `FINNISH`, islandzki → `ICELANDIC`, włoski → `ITALIAN`,
       chiński → `CHINESE`, japoński → `JAPANESE`, angielski → `ENGLISH`.
   Pełna lista (74 języki): https://github.com/pemistahl/lingua-py.
   Jeśli języka brak na liście lingua, zwróć na początku odpowiedzi
   `# BRAK_W_LINGUA: {kod_jezyka}` i pomiń pole.

2. **Sekcja `polskie_znaki`** (mimo nazwy!) opisuje diakrytyki języka
   `{kod_jezyka}`. Każdy diakrytyk PODAJ W PARZE wariant mały + wielki
   (np. „ä → a" oraz „Ä → A"). Jeśli język nie ma diakrytyków, zostaw
   pustą listę `polskie_znaki: []`. Najlepszy wzorzec do podejrzenia
   konwencji: `dictionaries/de/podstawy.yaml` (zawiera ß, Umlauty, plus
   pełen zestaw europejskich diakrytyków typu á/à/â/ã/é/í/ñ/ó/ø/ú/ý/ÿ).

3. **`alfabet`** to ciąg WIELKICH LITER, kolejność standardowa dla języka,
   bez spacji i znaków specjalnych. Diakrytyki, które nie rosną przy
   `.upper()`, mogą trafiać NA KONIEC alfabetu. Przykłady:
     - angielski: `"ABCDEFGHIJKLMNOPQRSTUVWXYZ"` (26)
     - niemiecki: `"ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÜ"` (29; ß NIE wchodzi)
     - fiński/szwedzki: `"ABCDEFGHIJKLMNOPQRSTUVWXYZÅÄÖ"` (29)
     - polski: `"AĄBCĆDEĘFGHIJKLŁMNŃOÓPQRSTUVWXYZŹŻ"`
     - rosyjski: `"АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ"` (33).

4. **⚠️ LITERY „ROSNĄCE" PRZY `.upper()` — TRAKTUJ PO SZWAJCARSKU.**
   Szyfr Cezara operuje na wielkich literach przez `str.upper()`. Litery
   rozszerzające się na 2+ znaki rozwalają indeksowanie:
     - niemieckie „ß" → „SS" (2 znaki)
     - holenderski dwuznak „ĳ" → „ĲIJ"
     - tureckie „ı" → „I" (locale-zależne)
     - ligatury typograficzne „ﬀ" → „FF"
   Takich liter NIE wpisuj do `alfabet`. Zamiast tego dodaj je do
   `polskie_znaki` jako transliteracje (`ß → ss`, `ĳ → ij` itd.).
   Tak robi już DE i to świadoma decyzja przyjęta jako standard projektu.

5. **Sekcja `slowo_akcent`** (od 13.3+, kontraktowo wymagana) zawiera
   natywne słowa wyzwalające parser akcentów w trybie Reżysera. Format
   z wdrożonych paczek:
     - PL: `["akcent"]`
     - DE: `["akzent", "aussprache"]`
     - IT: `["accento", "accentato"]`
     - RU: `["акцент", "акцентом", "говор"]`
     - FI: `["aksentti", "ääntäminen"]` (przykład — sprawdź lokalnie)
   Wszystkie wpisy MAŁYMI LITERAMI (parser robi lower-case porównanie).
   Dla idiomów z odmianą fleksyjną (jak RU) dodaj 2-3 najczęstsze formy.

6. **Komentarze i opisy** w pliku (każda linia zaczynająca się `#` plus
   pole `opis:`) MUSZĄ być w języku **{natywna}**. Stylem wzoruj się na
   `dictionaries/de/podstawy.yaml` lub `dictionaries/it/podstawy.yaml`.

7. **Zwróć TYLKO treść pliku YAML** — żadnego dodatkowego komentarza,
   żadnych bloków ``` wokół, żadnych wstępów ani podsumowań.

## WZORCOWY FRAGMENT (PL — referencja struktury)
Tylko jako wzorzec STRUKTURY — w odpowiedzi pisz w języku {natywna}, nie
po polsku.
```yaml
id: podstawy
jezyk: pl
lingua: POLISH
etykieta: "Polski – podstawy fonetyczne"
opis: |
  Bazowe reguły dla języka polskiego: ... (skrócone)
polskie_znaki:
  - {{ wzor: "ą", zamiana: "on" }}
  - {{ wzor: "ę", zamiana: "en" }}
  # … wielkie warianty + pozostałe pary …
alfabet: "AĄBCĆDEĘFGHIJKLŁMNŃOÓPQRSTUVWXYZŹŻ"
slowo_akcent:
  - "akcent"
```

Zwróć gotowy plik dla języka **{etykieta_jezyka}** (`{kod_jezyka}`,
endonim **{natywna}**). Po otrzymaniu odpowiedzi użytkownik zapisze ją
w `dictionaries/{kod_jezyka}/podstawy.yaml`. Foldery `akcenty/`, `szyfry/`,
`rezyser/`, `gui/` są już utworzone — kolejne pliki (akcenty, szyfry,
tryby Reżysera) generujesz osobnymi promptami z Managera Reguł.
"""


# =============================================================================
# PROMPT 3: Szyfr algorytmiczny – poproś AI o specyfikację + zmianę kodu
# =============================================================================
def prompt_szyfr_algorytm(id_pliku: str, etykieta: str,
                          opis_efektu: str) -> str:
    return f"""Jesteś doświadczonym programistą Pythona i eksperty od NLP.
Pomagasz rozszerzyć aplikację „Reżyser Audio GPT" (moduł Poliglota)
o nowy szyfr algorytmiczny. Uwaga: to zadanie WYMAGA INGERENCJI
w kod `core_poliglota.py` – nie wystarczy sam plik YAML.

## CEL
Zaprojektuj algorytm tekstowy o nazwie **{etykieta}**
(identyfikator techniczny: `{id_pliku}`).

OPIS EFEKTU (wg użytkownika):
    {opis_efektu}

## ZWRÓĆ TRZY ELEMENTY

### 1. Zawartość pliku YAML `dictionaries/<jezyk>/szyfry/{id_pliku}.yaml`:
```yaml
id: {id_pliku}
etykieta: "{etykieta}"
opis: |
  <2-4 zdania opisu efektu widocznego dla użytkownika>.
iso: pl
kategoria: szyfr
kolejnosc: 100
algorytm: {id_pliku}

# <Ewentualne parametry czytane z YAML przez Twoją funkcję Pythona:>
# parametr_1: wartosc
# parametr_2: wartosc
```

### 2. Kod funkcji Pythona do dopisania w `core_poliglota.py`:
```python
def _algorytm_{id_pliku}(tekst: str, regula: dict) -> str:
    \"\"\"Implementacja szyfru „{etykieta}".

    Args:
        tekst:  tekst wejściowy (UTF-8).
        regula: słownik ze wczytanego YAML (klucze = pola z pliku).

    Returns:
        Przetworzony tekst.
    \"\"\"
    # <UZUPEŁNIJ implementację>
    return tekst
```

### 3. Wpis w mapie `_ALGORYTMY` w `core_poliglota.py`:
```python
_ALGORYTMY = {{
    # ... istniejące wpisy ...
    "{id_pliku}": _algorytm_{id_pliku},
}}
```

## ZASADY ŻELAZNE
1. Algorytm MUSI być IDEMPOTENTNY na poziomie testu jednostkowego
   (uruchomienie dwukrotnie z tym samym seedem daje ten sam wynik,
   chyba że efekt jest z definicji losowy – wtedy udokumentuj to).
2. Operuj znak-po-znaku albo słowo-po-słowie, ale ZACHOWUJ białe znaki
   i interpunkcję (chyba że efekt wymaga ich zmiany – wtedy zaznacz to).
3. Jeśli algorytm korzysta z losowości – użyj `random` z modułu Pythona
   (jest już zaimportowany w core_poliglota.py).
4. NIE wprowadzaj nowych zależności zewnętrznych.
5. ⚠️ REGEX-Y ROZWIJAJĄCE SKRÓTOWCE — WZORUJ SIĘ NA ODWRACACZU.
   Jeżeli Twój algorytm dokonuje podstawień tekstowych PRZED właściwym
   przetwarzaniem (np. rozwija „itd." w „i tak dalej", żeby kropka nie
   pocięła zdania), trzymaj się KONWENCJI z pliku istniejącego szyfru
   `dictionaries/pl/szyfry/odwracanie.yaml`:

   ```yaml
   rozwiniecia:
     - {{ wzor: '\\bm\\.\\s*in\\.?,?\\b', zamiana: "między innymi"     }}
     - {{ wzor: '\\bmi\\.in\\.?\\b',      zamiana: "między innymi"     }}
     - {{ wzor: '\\bnp\\.?,?\\s',         zamiana: "na przykład "      }}
     - {{ wzor: '\\bn\\.\\s*p\\.\\b',     zamiana: "na przykład"       }}
     - {{ wzor: '\\btzw\\.?,?\\s',        zamiana: "tak zwany "        }}
     - {{ wzor: '\\bitd\\.?,?\\b',        zamiana: "i tak dalej"       }}
   ```

   KLUCZOWE ZASADY DLA KAŻDEJ PARY `rozwiniecia`:
   a) ZAWSZE granice słowa `\\b...\\b` na początku i końcu – bez nich
      regex złapie skrót W ŚRODKU słowa (np. „tj" w słowie „atakujący").
   b) KROPKA OPCJONALNA `\\.?` – użytkownicy często ją pomijają
      („itd" bez kropki to równie częste jak „itd.").
   c) PRZECINEK OPCJONALNY `,?` – czasem zostaje po skrócie
      („m.in., Warszawa" → regex musi pochłonąć przecinek tylko
      jeśli istnieje).
   d) DWA WARIANTY DLA CZĘSTYCH TYPO – np. „m.in." (poprawne) oraz
      „mi.in." (błąd z przestawioną kropką) jako OSOBNE wiersze.
      Podobnie „np." vs „n.p." (błąd z kropką w środku).
   e) SPACJA PO ROZWINIĘCIU – jeżeli skrót kończy się w `\\s` (np. „np. "),
      WŁĄCZ spację do wzoru i do zamiany („na przykład "), żeby nie
      zostały zbitki typu „na przykładPan".
   f) KOLEJNOŚĆ MA ZNACZENIE – najpierw bardziej szczegółowe wzory
      (warianty z typo), potem ogólne. Python regex idzie lista-góra-dół.
   g) Nie dodawaj flagi `regex: true` w wierszu `rozwiniecia` –
      tam regex jest DOMYŚLNY (w przeciwieństwie do `zamiany`
      w akcentach, gdzie domyślnie jest zwykły string).

   Dzięki tym zasadom rozwinięcia działają na „normalnych zdaniach"
   bez tworzenia artefaktów typu „.nim" (zamiast „m.in." wspak).

Po otrzymaniu Twojej odpowiedzi użytkownik przekaże ją programiście
projektu, który wpisze kod do `core_poliglota.py` i zapisze plik YAML
w odpowiednim miejscu.
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
    if typ == TYP_AKCENT:
        return {
            "tryb":     "SZABLON_I_PROMPT",
            "yaml":     szablon_akcent(id_pliku, etykieta, iso),
            "prompt":   prompt_akcent(id_pliku, etykieta, iso, jezyk_bazowy),
            "docelowy": f"{jezyk_bazowy}/akcenty/{id_pliku}.yaml",
            "uwagi": (
                "Utworzony szablon ma pusty pipeline zamian fonetycznych. "
                "Skopiuj prompt do ChatGPT / Claude, zastąp sekcję `zamiany:` "
                "odpowiedzią modelu i zapisz plik. Po zapisie kliknij "
                '„Odśwież akcenty Reżysera" na Stronie głównej.'
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
                "Uzupełnij listę `zamiany:` parami {wzor, zamiana}; jeśli "
                "potrzebujesz pomocy, skopiuj prompt poniżej do AI — "
                "wygeneruje pełną listę i przetłumaczy komentarze na "
                "język natywny paczki."
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
                "Najważniejsze do uzupełnienia: `prompt_systemowy` "
                "(definicja roli AI w języku natywnym), "
                "`przypomnienie_uzytkownika` i `slowa_wyzwalajace`. "
                "Skopiuj prompt poniżej do AI, żeby przetłumaczył wszystko "
                "na język natywny zgodnie ze stylem `tryb_audiobook.yaml`."
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
                f"`{jezyk_bazowy}/`). Uzupełnij `prompt_systemowy`, "
                "`prompt_uzytkownika_szablon` (placeholdery `{naglowek}`, "
                "`{probka}`) i `regex_podzial_rozdzialow` dopasowany do "
                "języka natywnego. Prompt poniżej generuje wszystko za AI."
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
                f"ma puste miejsca – skopiuj prompt do AI, aby otrzymać dane fonetyczne. "
                f"Tłumaczenie interfejsu (`gui/ui.yaml`) generuje skrypt "
                f"`buduj_wielojezyczne_ui.py` – nie twórz go ręcznie. Tryby Reżysera "
                f"(`rezyser/tryb_*.yaml`) skopiuj z `pl/rezyser/` – silnik wymaga "
                f"co najmniej jednego trybu, żeby uznać język za kompletny."
            ),
        }

    if typ == TYP_SZYFR_ALGORYTM:
        return {
            "tryb":     "PROMPT",
            "yaml":     "",
            "prompt":   prompt_szyfr_algorytm(id_pliku, etykieta, opis_efektu),
            "docelowy": f"{jezyk_bazowy}/szyfry/{id_pliku}.yaml",
            "uwagi": (
                "UWAGA: szyfry algorytmiczne wymagają funkcji w "
                "`core_poliglota.py`. Manager NIE tworzy żadnego pliku – "
                "wygenerowany prompt zawiera 3 sekcje (YAML, kod Pythona, "
                "wpis w mapie `_ALGORYTMY`). Odpowiedź AI przekaż "
                "programiście projektu."
            ),
        }

    raise ValueError(f"Nieznany typ reguły: {typ!r}")
