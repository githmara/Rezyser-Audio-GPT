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
        "Plik w <jezyk>/szyfry/. Prosty szablon z listą par wzor→zamiana. "
        "Nie wymaga kontaktu z programistą.",
    ),
    (
        TYP_TRYB_REZYSERA,
        "Nowy tryb Reżysera (tryb twórczy)",
        "Plik w <jezyk>/rezyser/tryb_*.yaml. Szablon oparty o tryb "
        "Audiobooka – dalej wystarczy zmienić prompt systemowy.",
    ),
    (
        TYP_POSTPRODUKCJA,
        "Nowa postprodukcja (iteracja po rozdziałach)",
        "Plik w <jezyk>/rezyser/postprod_*.yaml. Szablon z polami na "
        "prompt, regex i parametry iteracji.",
    ),
    (
        TYP_JEZYK_BAZOWY,
        "Nowy język bazowy (np. en, de, fr)",
        "Tworzy folder <jezyk>/ z pustym podstawy.yaml oraz podfolderami "
        "akcenty/ i szyfry/. Dane fonetyczne wygeneruje AI z promptu.",
    ),
    (
        TYP_SZYFR_ALGORYTM,
        "Nowy szyfr algorytmiczny (WYMAGA PROGRAMISTY)",
        "Algorytmy (np. odwracanie, typoglikemia) wymagają funkcji w "
        "core_poliglota.py. Manager daje tylko prompt dla AI z opisem zadania.",
    ),
]


# =============================================================================
# SZABLON 1: Akcent fonetyczny (wzorowany na dictionaries/pl/akcenty/finski.yaml)
# =============================================================================
def szablon_akcent(id_pliku: str, etykieta: str, iso: str) -> str:
    """Zwraca tekst YAML szablonu akcentu – gotowy do zapisu na dysk."""
    # UWAGA: trzymamy format 1-do-1 z istniejącymi plikami, żeby silnik
    # (core_poliglota.py) bez modyfikacji wciągnął akcent.
    return f"""# -----------------------------------------------------------------------------
#  AKCENT: {etykieta}
#  (szablon wygenerowany przez Manager Reguł – uzupełnij listę zamian)
# -----------------------------------------------------------------------------
id: {id_pliku}
etykieta: "{etykieta}"
opis: |
  <UZUPEŁNIJ>: opisz krótko, pod jaki syntezator TTS przeznaczony jest
  ten akcent (np. „dla syntezatora szwedzkiego Alva / Oskar").
iso: {iso}
kategoria: akcent
kolejnosc: 100

# --- Pipeline przetwarzania (true/false) ---
# czysc_tekst_tts        – usuwa bełkot („khh", gwiazdki, hashtagi)
# normalizuj_liczby      – zamienia cyfry na słowa (123 → sto dwadzieścia trzy)
# usun_polskie_znaki     – ą→on, ę→en, ł→l, ó→u, ś→s, ć→c, ń→n, ż→z, ź→z
# skleja_pojedyncze_litery – scala wiszące litery („w y s" → „wys")
czysc_tekst_tts: true
normalizuj_liczby: true
usun_polskie_znaki: true
skleja_pojedyncze_litery: true

# --- Właściwe zamiany fonetyczne ---
# ZŁOTA ZASADA: dwuznaki (ch, cz, sz, rz) PRZED jednoznakami (c, s, z, r),
# bo inaczej „c → ts" rozwali zapis „ch", „cz" itd.
#
# Dla wzorów będących wyrażeniami regularnymi dodaj „regex: true".
zamiany:
  - {{ wzor: "ch", zamiana: "h"  }}
  - {{ wzor: "Ch", zamiana: "H"  }}
  # <UZUPEŁNIJ>: dodaj kolejne pary specyficzne dla języka docelowego.
  # Poproś AI promptem z Managera Reguł o pełną listę zamian.
"""


# =============================================================================
# PROMPT 1: Akcent fonetyczny – poproś AI o pełną listę zamian
# =============================================================================
def prompt_akcent(id_pliku: str, etykieta: str, iso: str,
                  jezyk_bazowy: str) -> str:
    return f"""Jesteś ekspertem w fonetyce i transliteracji międzyjęzykowej.
Tworzysz regułę fonetyczną dla aplikacji „Reżyser Audio GPT" (moduł Poliglota).

## CEL
Wygeneruj kompletny plik YAML akcentu `{id_pliku}.yaml`, który upodobni
tekst w języku **{jezyk_bazowy}** (język źródłowy) do wymowy w języku
o kodzie ISO **{iso}** (język docelowy syntezatora TTS).
Nazwa akcentu widoczna dla użytkownika: **{etykieta}**.

## FORMAT WYJŚCIOWY (DOSŁOWNIE TEN SZABLON)
```yaml
id: {id_pliku}
etykieta: "{etykieta}"
opis: |
  <2-4 zdania: pod jaki syntezator TTS jest przeznaczony akcent,
  jakie zjawiska fonetyczne wymusza (np. ubezdźwięcznienie,
  tłumienie syczenia, zmiana „w" na „v")>
iso: {iso}
kategoria: akcent
kolejnosc: 100
czysc_tekst_tts: true
normalizuj_liczby: true
usun_polskie_znaki: true
skleja_pojedyncze_litery: true
zamiany:
  - {{ wzor: "ch", zamiana: "h" }}
  - {{ wzor: "Ch", zamiana: "H" }}
  # ...kolejne pary...
```

## ZASADY ŻELAZNE
1. Lista `zamiany` MUSI być uporządkowana: DWUZNAKI (ch, cz, sz, rz, dz, dź)
   ZAWSZE przed JEDNOZNAKAMI (c, s, z, r, d). W przeciwnym razie zamiana
   „c → ts" rozwali zapis „ch" / „cz".
2. Każdy dwuznak występuje dwa razy: wariant małych liter i wariant
   z wielką pierwszą literą (np. „Cz" → „Ts").
3. Jeśli potrzebujesz regexa, dodaj do wiersza `regex: true`. Przykład:
   `- {{ wzor: 'ci(?=[aąeęoóuy])', zamiana: "ć", regex: true }}`.
4. Bazą jest polski alfabet i polskie diakrytyki (są usuwane w kroku
   `usun_polskie_znaki`), więc zamiany wykonuj NA TEKŚCIE BEZ POLSKICH
   ZNAKÓW (tzn. operujesz na „a, e, l, u, s, c, n, z" zamiast „ą, ę, ł, …").
5. Zwróć TYLKO treść pliku YAML – żadnego dodatkowego komentarza,
   żadnych bloków ``` wokół, żadnych wstępów ani podsumowań.

## PRZYKŁAD POPRAWNEGO WYNIKU (fiński)
Poniższy plik istnieje już w aplikacji – posłuż się nim jako wzorcem,
ale NIE kopiuj go, tylko dostosuj do `{iso}`:

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
  - {{ wzor: "sz", zamiana: "s"  }}
  - {{ wzor: "Sz", zamiana: "S"  }}
  - {{ wzor: "rz", zamiana: "r"  }}
  - {{ wzor: "Rz", zamiana: "R"  }}
  - {{ wzor: "c",  zamiana: "ts" }}
  - {{ wzor: "C",  zamiana: "Ts" }}
  - {{ wzor: "w",  zamiana: "v"  }}
  - {{ wzor: "W",  zamiana: "V"  }}
  - {{ wzor: "b",  zamiana: "p"  }}
  - {{ wzor: "B",  zamiana: "P"  }}
  - {{ wzor: "d",  zamiana: "t"  }}
  - {{ wzor: "D",  zamiana: "T"  }}
  - {{ wzor: "g",  zamiana: "k"  }}
  - {{ wzor: "G",  zamiana: "K"  }}
```

Zwróć gotowy YAML dla akcentu **{etykieta}** (ISO `{iso}`, język źródłowy
`{jezyk_bazowy}`). Po otrzymaniu odpowiedzi użytkownik wklei ją do
pliku `dictionaries/{jezyk_bazowy}/akcenty/{id_pliku}.yaml` i uruchomi
w aplikacji przycisk „Odśwież akcenty Reżysera".
"""


# =============================================================================
# SZABLON 2: Szyfr „czyste zamiany" (wzorowany na akcencie, bez algorytmu)
# =============================================================================
def szablon_szyfr_zamiany(id_pliku: str, etykieta: str) -> str:
    return f"""# -----------------------------------------------------------------------------
#  SZYFR: {etykieta}
#  (szablon „czyste zamiany" – nie wymaga kodu Pythona)
# -----------------------------------------------------------------------------
id: {id_pliku}
etykieta: "{etykieta}"
opis: |
  <UZUPEŁNIJ>: opisz efekt tekstowy, jaki uzyskuje ten szyfr
  (np. „każde »a« staje się »@«, każde »o« staje się »0«"). Szyfry tego
  typu działają jak akcent, tylko bez pipeline'u fonetycznego – używają
  wyłącznie listy `zamiany`.
iso: pl
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
  # <UZUPEŁNIJ>: dopisz kolejne pary.
"""


# =============================================================================
# SZABLON 3: Tryb Reżysera (wzorowany na dictionaries/pl/rezyser/tryb_audiobook.yaml)
# =============================================================================
def szablon_tryb_rezysera(id_pliku: str, etykieta: str) -> str:
    return f"""# -----------------------------------------------------------------------------
#  TRYB REŻYSERA: {etykieta}
#  (szablon oparty o tryb Audiobook – uzupełnij rolę i zasady)
# -----------------------------------------------------------------------------
id: {id_pliku}
etykieta: "{etykieta}"
kategoria: tryb
kolejnosc: 40

# --- Parametry OpenAI ---
model: gpt-4o
temperatura: 0.85
jezyk_odpowiedzi: polsku

# Czy odpowiedź zapisywać do pliku projektu (.txt)?
zapis_do_pliku: true

# --- Prompt systemowy ---
# Placeholdery: {{world_context}}, {{jezyk_odpowiedzi}}
prompt_systemowy: |
  # Rola: <UZUPEŁNIJ NAZWĘ ROLI AI>

  Piszesz **WYŁĄCZNIE po {{jezyk_odpowiedzi}}**. <UZUPEŁNIJ: opis trybu
  i oczekiwanego formatu wyjściowego.>

  ### 🌍 Żelazne Zasady Świata:
  {{world_context}}

  ### 📖 Zasady tego trybu:
  1. <UZUPEŁNIJ: pierwsza zasada (np. styl, ograniczenia formatu)>.
  2. <UZUPEŁNIJ: druga zasada>.
  3. **DOMYKANIE SCEN:** - DOMYŚLNIE (ANTI-CLOSURE): Urwij w środku akcji.
     - WYJĄTEK (FINAŁ/EPILOG): Jeśli to zakończenie, domknij scenę naturalnie.

# --- Sufiksy kontekstowe (opcjonalne) ---
# Puste {{}} oznacza „silnik nie dokleja żadnego sufiksu zależnego od stanu
# pamięci". Jeśli chcesz dodać sufiksy – patrz tryb_burza.yaml jako wzorzec.
sufiksy: {{}}

# --- Przypomnienie doklejane do instrukcji użytkownika ---
przypomnienie_uzytkownika: |


  (PRZYPOMNIENIE: <UZUPEŁNIJ krótkie przypomnienie kluczowych zasad tego trybu>.)

# --- Walidacja po stronie aplikacji ---
slowa_wyzwalajace:
  streszczenie:
    - streszcz
    - streść
    - podsumuj
    - podsumowanie

# Czy uruchamiać silnik fonetyczny na odpowiedzi?
# true  – wymagane, jeśli tryb generuje dialogi z tagami postaci.
# false – dla prozy literackiej bez tagów.
stosuj_akcenty_fonetyczne: false
"""


# =============================================================================
# SZABLON 4: Postprodukcja (wzorowany na postprod_tytuly.yaml)
# =============================================================================
def szablon_postprodukcja(id_pliku: str, etykieta: str) -> str:
    return f"""# -----------------------------------------------------------------------------
#  POSTPRODUKCJA: {etykieta}
#  (szablon oparty o postprod_tytuly.yaml)
# -----------------------------------------------------------------------------
id: {id_pliku}
etykieta: "{etykieta}"
kategoria: postprodukcja
kolejnosc: 20

# --- Parametry OpenAI ---
model: gpt-4o-mini
temperatura: 0.7
jezyk_odpowiedzi: polsku

# --- Prompt systemowy ---
prompt_systemowy: |
  <UZUPEŁNIJ: rola AI + jednozdaniowa instrukcja formatu odpowiedzi.>

# --- Szablon instrukcji użytkownika (role=user) ---
# Placeholdery: {{naglowek}}, {{probka}}
prompt_uzytkownika_szablon: |
  Oto fragment tekstu ({{naglowek}}). <UZUPEŁNIJ: polecenie dla AI>.

  TREŚĆ:
  {{probka}}

# --- Parametry iteracji po pliku projektu ---
regex_podzial_rozdzialow: "(?i)\\\\n*(Prolog|Rozdział \\\\d+|Epilog)\\\\n*"
min_dlugosc_fragmentu: 50
max_dlugosc_probki: 6000

# Komunikaty widoczne dla użytkownika w oknie wyników:
etykieta_fragment_zbyt_krotki: "(Fragment zbyt krótki)"
etykieta_bled_brak_kredytow: "(Błąd – brak kredytów API)"
"""


# =============================================================================
# SZABLON 5: podstawy.yaml dla nowego języka bazowego (minimum do startu)
# =============================================================================
def szablon_podstawy(kod_jezyka: str, etykieta_jezyka: str) -> str:
    return f"""# =============================================================================
#  PODSTAWY JĘZYKA {etykieta_jezyka.upper()}
# =============================================================================
#  Szablon wygenerowany przez Manager Reguł. Uzupełnij obie sekcje:
#   1. polskie_znaki – mapowanie diakrytyków języka „{kod_jezyka}" na litery
#      łacińskie (używane przez flagę `usun_polskie_znaki: true` akcentów).
#   2. alfabet – pełny alfabet wielkich liter (używany przez szyfr Cezara).
#
#  Aby szybko wygenerować obie sekcje, poproś AI promptem z Managera Reguł.
# =============================================================================

id: podstawy
jezyk: {kod_jezyka}
etykieta: "{etykieta_jezyka} – podstawy fonetyczne"
opis: |
  Bazowe reguły dla języka {etykieta_jezyka.lower()}:
    1. Transliteracja diakrytyków (<UZUPEŁNIJ> np. ä→a, ö→o, å→a).
    2. Alfabet (<N> liter, wielkie) – używany przez szyfr Cezara.

polskie_znaki:
  # <UZUPEŁNIJ>: pary {{ wzor: "<litera z diakrytykiem>", zamiana: "<łacińska>" }}
  # Wariant mały i wielki (np. "ä" → "a" oraz "Ä" → "A").
  - {{ wzor: "?", zamiana: "?" }}

# Pełny alfabet wielkich liter, bez znaków białych.
alfabet: "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
"""


# =============================================================================
# PROMPT 2: Nowy język bazowy – pełny pakiet (podstawy + zestaw akcentów)
# =============================================================================
def prompt_jezyk_bazowy(kod_jezyka: str, etykieta_jezyka: str) -> str:
    return f"""Jesteś ekspertem w fonetyce i typologii językowej.
Pomagasz dodać nowy język bazowy do aplikacji „Reżyser Audio GPT"
(moduł Poliglota).

## CEL
Wygeneruj zawartość pliku `dictionaries/{kod_jezyka}/podstawy.yaml`
dla języka **{etykieta_jezyka}** (kod ISO 639-1: `{kod_jezyka}`).

## FORMAT WYJŚCIOWY (DOSŁOWNIE TEN SZABLON)
```yaml
id: podstawy
jezyk: {kod_jezyka}
etykieta: "{etykieta_jezyka} – podstawy fonetyczne"
opis: |
  Bazowe reguły dla języka {etykieta_jezyka.lower()}:
    1. Transliteracja diakrytyków (<krótko opisz co→na co>).
    2. Alfabet (<N> liter, wielkie) – używany przez szyfr Cezara.

polskie_znaki:
  - {{ wzor: "<mała_z_diakrytykiem>", zamiana: "<łacińska>" }}
  - {{ wzor: "<WIELKA_Z_DIAKRYTYKIEM>", zamiana: "<ŁACIŃSKA>" }}
  # … wszystkie pary dla języka {etykieta_jezyka} …

alfabet: "<WIELKIE_LITERY_ALFABETU_BEZ_SPACJI>"
```

## ZASADY ŻELAZNE
1. Sekcja `polskie_znaki` (mimo nazwy!) opisuje DIAKRYTYKI JĘZYKA
   `{kod_jezyka}`. Jeśli `{etykieta_jezyka}` nie ma diakrytyków, zostaw
   pustą listę `polskie_znaki: []`.
2. Dla każdego diakrytyka PODAJ PARĘ: wariant mały i wielki
   (np. „ä → a" i „Ä → A").
3. `alfabet` to ciąg WIELKICH LITER w kolejności standardowej dla danego
   języka, BEZ spacji i BEZ znaków specjalnych (tylko litery alfabetu).
   Przykłady:
   - angielski: `"ABCDEFGHIJKLMNOPQRSTUVWXYZ"` (26 liter)
   - niemiecki: `"ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÜ"` (29 liter – diakrytyki
     NA KOŃCU, bo szyfr Cezara ma działać predictably; UWAGA: `ß` NIE
     trafia do alfabetu – patrz zasada nr 5).
   - fiński: `"ABCDEFGHIJKLMNOPQRSTUVWXYZÅÄÖ"` (29 liter)
   - szwedzki: `"ABCDEFGHIJKLMNOPQRSTUVWXYZÅÄÖ"` (29 liter)
4. Zwróć TYLKO treść pliku YAML – żadnego komentarza, żadnych bloków
   ``` wokół, żadnych wyjaśnień.
5. ⚠️ LITERY „ROSNĄCE" PRZY .upper() — TRAKTUJ PO SZWAJCARSKU!
   Szyfr Cezara w aplikacji operuje na WIELKICH literach alfabetu przez
   `str.upper()`. Niektóre litery w Unicode rozbijają się przy tej
   operacji na WIĘCEJ niż 1 znak i **rozwalają mapowanie** Cezara:
     - niemieckie „ß" → „SS" (2 znaki)
     - holenderski dwuznak „ĳ" → „ĲIJ" (!)
     - tureckie „ı" → „I" (różna długość w locale PL vs TR)
     - ligatury typograficzne „ﬀ" → „FF", „ﬃ" → „FFI"
   Takich liter **NIE WPISUJ do pola `alfabet`**. Zamiast tego obsłuż je
   w sekcji `polskie_znaki` jako pary transliteracji, np. dla niemieckiego:
   ```yaml
   polskie_znaki:
     - {{ wzor: "ß", zamiana: "ss" }}
     - {{ wzor: "ẞ", zamiana: "SS" }}   # wielkie ẞ formalne od 2017
     - {{ wzor: "ä", zamiana: "a"  }}
     - {{ wzor: "Ä", zamiana: "A"  }}
     # … reszta …
   ```
   Efektywnie „po szwajcarsku" (Szwajcarzy od dawna piszą „ss" zamiast „ß").
   Gdy użytkownik włączy flagę `usun_polskie_znaki: true` w akcentach,
   transliteracja zadziała poprawnie; szyfr Cezara ominie te litery bo
   nie ma ich w `alfabet` (zostaną nietknięte w tekście) – to świadoma
   decyzja, dopóki nie przepiszemy silnika na lower-case w wersji 13.1.

## WZORZEC: plik `dictionaries/pl/podstawy.yaml`
```yaml
id: podstawy
jezyk: pl
etykieta: "Polski – podstawy fonetyczne"
opis: |
  Bazowe reguły dla języka polskiego: ... (skrócone)
polskie_znaki:
  - {{ wzor: "ą", zamiana: "on" }}
  - {{ wzor: "ę", zamiana: "en" }}
  - {{ wzor: "ł", zamiana: "l"  }}
  - {{ wzor: "ó", zamiana: "u"  }}
  - {{ wzor: "ś", zamiana: "s"  }}
  - {{ wzor: "ć", zamiana: "c"  }}
  - {{ wzor: "ń", zamiana: "n"  }}
  - {{ wzor: "ż", zamiana: "z"  }}
  - {{ wzor: "ź", zamiana: "z"  }}
  # (wielkie warianty pominięte dla zwięzłości)
alfabet: "AĄBCĆDEĘFGHIJKLŁMNŃOÓPQRSTUVWXYZŹŻ"
```

Zwróć gotowy plik dla języka **{etykieta_jezyka}** (`{kod_jezyka}`).
Po otrzymaniu odpowiedzi użytkownik zapisze ją do
`dictionaries/{kod_jezyka}/podstawy.yaml` i utworzy puste podfoldery
`akcenty/` oraz `szyfry/`.
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
            "tryb":     "SZABLON",
            "yaml":     szablon_szyfr_zamiany(id_pliku, etykieta),
            "prompt":   "",
            "docelowy": f"{jezyk_bazowy}/szyfry/{id_pliku}.yaml",
            "uwagi": (
                "Szablon gotowy do edycji – uzupełnij listę `zamiany:` "
                "parami {wzor, zamiana}. Ten typ szyfru nie wymaga "
                "kontaktu z programistą."
            ),
        }

    if typ == TYP_TRYB_REZYSERA:
        # Konwencja: tryby Reżysera mają prefix `tryb_` w nazwie pliku.
        nazwa_pliku = f"tryb_{id_pliku}" if not id_pliku.startswith("tryb_") \
                      else id_pliku
        return {
            "tryb":     "SZABLON",
            "yaml":     szablon_tryb_rezysera(id_pliku, etykieta),
            "prompt":   "",
            "docelowy": f"{jezyk_bazowy}/rezyser/{nazwa_pliku}.yaml",
            "uwagi": (
                "Szablon oparty o tryb Audiobook. Najważniejsze do "
                "uzupełnienia: `prompt_systemowy` (definicja roli AI) "
                "oraz `przypomnienie_uzytkownika`. Reszta pól ma sensowne "
                "wartości domyślne."
            ),
        }

    if typ == TYP_POSTPRODUKCJA:
        nazwa_pliku = f"postprod_{id_pliku}" if not id_pliku.startswith("postprod_") \
                      else id_pliku
        return {
            "tryb":     "SZABLON",
            "yaml":     szablon_postprodukcja(id_pliku, etykieta),
            "prompt":   "",
            "docelowy": f"{jezyk_bazowy}/rezyser/{nazwa_pliku}.yaml",
            "uwagi": (
                "Szablon postprodukcji iteruje po rozdziałach zapisanego "
                "projektu. Uzupełnij `prompt_systemowy` i `prompt_uzytkownika_szablon` "
                "(placeholdery `{naglowek}` i `{probka}`)."
            ),
        }

    if typ == TYP_JEZYK_BAZOWY:
        return {
            "tryb":     "SZABLON_I_PROMPT",
            "yaml":     szablon_podstawy(id_pliku, etykieta),
            "prompt":   prompt_jezyk_bazowy(id_pliku, etykieta),
            "docelowy": f"{id_pliku}/podstawy.yaml",
            "uwagi": (
                "Manager utworzy folder `dictionaries/{kod}/` oraz "
                "podfoldery `akcenty/` i `szyfry/`. Szablon `podstawy.yaml` "
                "ma puste miejsca – skopiuj prompt do AI, aby otrzymać "
                "pełne dane fonetyczne dla nowego języka."
            ).replace("{kod}", id_pliku),
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
