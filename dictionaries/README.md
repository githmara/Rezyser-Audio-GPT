# Słowniki i reguły językowe – Poliglota AI

Folder zawiera reguły **fonetyczne**, **szyfrujące** i **bazowe** modułu
Poliglota AI (część aplikacji *Reżyser Audio GPT*).

## Po co to jest?

Aby **lingwiści nieznający Pythona** mogli samodzielnie:

- Dostrajać istniejące akcenty fonetyczne
  (np. zmienić zamianę *„sz → sh”* na *„sz → sch”*).
- Dodawać nowe akcenty dla polskiego
  (np. po duńsku, po szwedzku, po rosyjsku).
- Dodawać reguły dla innych języków bazowych
  (np. angielski jako język źródłowy → akcent polski na angielskim tekście).

Silnik programu (`core_poliglota.py`) **sam wczyta** każdy nowy plik `.yaml`
położony w poprawnym miejscu i doda go do listy wyboru w GUI – **bez
przekompilowywania aplikacji**.

## Struktura katalogu

```
dictionaries/
├── README.md                        (ten plik)
└── <kod_języka_bazowego>/           np. "pl", w przyszłości "en", "de", …
    ├── podstawy.yaml                 transliteracja + alfabet danego języka
    ├── akcenty/                      Tryb Reżysera – fonetyka pod TTS
    │   ├── <nazwa_akcentu>.yaml
    │   └── …
    └── szyfry/                       Tryb Szyfranta – zabawy tekstem
        ├── <nazwa_szyfru>.yaml
        └── …
```

**Kod języka bazowego** = kod ISO 639-1 języka tekstu źródłowego
(czyli „co wczytujemy i przetwarzamy”), np. `pl`, `en`, `de`, `fr`, …

## Jak dodać nowy akcent fonetyczny?

1. Wejdź do katalogu `dictionaries/pl/akcenty/`.
2. Skopiuj dowolny istniejący plik, np. `islandzki.yaml`,
   pod nową nazwą (bez polskich znaków, np. `szwedzki.yaml`).
3. Otwórz plik w dowolnym edytorze tekstu i zmień:
   - `id` – identyfikator techniczny (bez polskich znaków, bez spacji),
   - `etykieta` – nazwa widoczna w programie (tu mogą być polskie znaki),
   - `opis` – kilka zdań dla użytkownika końcowego,
   - `iso` – dwuliterowy kod języka docelowego (np. `sv`),
   - `zamiany` – listę par `wzor → zamiana`.
4. Uruchom aplikację – nowy akcent pojawi się automatycznie
   w liście wyboru w Trybie Reżysera.

## Jak działa pipeline akcentu?

Każdy plik akcentu może włączyć lub wyłączyć cztery etapy przetwarzania:

| Flaga                          | Co robi                                                       |
|--------------------------------|---------------------------------------------------------------|
| `czysc_tekst_tts`              | usuwa bełkot typu „khh”, „ahh”, pojedyncze gwiazdki, hashtagi |
| `normalizuj_liczby`            | zamienia cyfry na słowa (np. `123` → `sto dwadzieścia trzy`)  |
| `usun_polskie_znaki`           | ą→on, ę→en, ł→l, ó→u, ś→s, ć→c, ń→n, ż→z, ź→z                 |
| `zamiany`                      | właściwe reguły fonetyczne danego akcentu                     |
| `skleja_pojedyncze_litery`     | scala wiszące pojedyncze litery (np. „w y s o k i” → „wysoki”)|

Etapy wykonywane są w takiej kolejności, w jakiej stoją w tabeli.

## Format listy zamian

```yaml
zamiany:
  - { wzor: "ch", zamiana: "h"  }          # dwuznak → jednoznak
  - { wzor: "Ch", zamiana: "H"  }          # wariant z wielką literą
  - { wzor: "cz", zamiana: "ts" }
  - { wzor: "c",  zamiana: "ts" }          # jednoznaki PO dwuznakach!
  - { wzor: "w",  zamiana: "v"  }
```

**Złota zasada:** dwuznaki PRZED jednoznakami, bo inaczej zamiana „c → ts”
rozwali zapis „ch”, „cz”, itd.

Jeśli wzór jest wyrażeniem regularnym (regex), dodaj `regex: true`:

```yaml
zamiany:
  - { wzor: 'ci(?=[aąeęoóuy])', zamiana: "ć", regex: true }
```

## Jak dodać nowy szyfr / zabawę tekstową?

Szyfry dzielą się na dwa rodzaje:

- **Czyste zamiany** (jak akcenty) – tylko lista par `wzor → zamiana`
  i gotowe. Nie wymagają żadnego kodu Pythona.
- **Algorytmy** (np. mieszanie liter, losowe powtórzenia) – wymagają
  funkcji w `core_poliglota.py`. W pliku YAML ustaw `algorytm: <nazwa>`
  oraz podaj parametry. Dostępne algorytmy:
  - `odwracanie`      – czyta zdania wspak
  - `typoglikemia`    – miesza środek słów
  - `samogloskowiec`  – zamienia wszystkie samogłoski na `o`
  - `jakanie`         – dokleja zająknięcia na początku słowa
  - `waz`             – wydłuża syczenie (`s`, `z`, `sz`)
  - `cezar`           – szyfr Cezara na alfabecie danego języka

Każdy algorytm ma własny zestaw parametrów – patrz komentarze
w istniejących plikach `.yaml` w `pl/szyfry/`.

## Plik `podstawy.yaml`

Zawiera **wspólne dane** dla wszystkich akcentów i szyfrów danego
języka bazowego:

- `polskie_znaki` – mapowanie diakrytyków na wersje łacińskie
  (używane przez każdy akcent z flagą `usun_polskie_znaki: true`).
- `alfabet` – kompletny alfabet języka (używany przez szyfr Cezara
  i do podobnych celów).

## Dodanie NOWEGO języka bazowego (np. angielski)

1. Utwórz folder `dictionaries/en/`.
2. Skopiuj do niego `dictionaries/pl/podstawy.yaml` i dostosuj
   listę diakrytyków oraz alfabet.
3. Utwórz podfoldery `en/akcenty/` i `en/szyfry/`.
4. Wypełnij je plikami `.yaml` wg tej samej konwencji.

Silnik **sam wykryje** nowy język przy starcie aplikacji.
