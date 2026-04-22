# Słowniki i reguły językowe – Poliglota + Reżyser AI

> 📘 **Dwa poziomy dokumentacji.** Ten plik (`README.md`) jest
> **techniczną** specyfikacją formatu YAML dla lingwistów znających
> podstawy programowania oraz dla deweloperów — z tabelą flag,
> regex-ami, polami pipeline'u i pełną listą algorytmów. Jeśli szukasz
> wersji **dla zwykłych użytkowników** (prostym językiem, z anegdotami
> i pomysłami na zabawę z dziećmi), zajrzyj do `instrukcja.txt` w tym
> samym folderze. Ta druga wersja jest celowo dołączona do paczek
> wydaniowych z zakładki Releases, podczas gdy niniejszy README.md
> jest wykluczony z paczki (budowanie ZIP-a filtruje pliki Markdown,
> bo do paczki nie mogą trafić użytkownikowi np. prywatne Księgi
> Świata w formacie `.md`).

Folder zawiera reguły **fonetyczne** (akcenty Poligloty), **szyfrujące**
(zabawy tekstowe) oraz **tryby twórcze Reżysera** (Burza Mózgów / Skrypt /
Audiobook / postprodukcja) — wszystko w deklaratywnych plikach YAML
wczytywanych dynamicznie przez aplikację *Reżyser Audio GPT*.

> 💡 **Tip dla użytkowników GUI:** Od wersji 13.0 masz wbudowany graficzny
> edytor tych plików — **Manager Reguł** (Ctrl+4 lub przycisk „📚 Otwórz
> Manager Reguł" na Stronie głównej). Pozwala przeglądać drzewo plików,
> tworzyć nowe z szablonu, duplikować istniejące i otwierać je w edytorze
> tekstu — bez wchodzenia w Eksploratora plików. Ten dokument opisuje
> format plików, jeśli wolisz edytować je ręcznie lub chcesz zrozumieć,
> co generuje kreator.


## Po co to jest?

Aby **lingwiści, tłumacze i pisarze nieznający Pythona** mogli samodzielnie:

- Dostrajać istniejące akcenty fonetyczne
  (np. zmienić zamianę *„sz → sh”* na *„sz → sch”*).
- Dodawać nowe akcenty dla polskiego
  (np. po duńsku, po szwedzku, po rosyjsku).
- Dodawać reguły dla innych języków bazowych
  (np. angielski jako język źródłowy → akcent polski na angielskim tekście).
- Zmieniać brzmienie promptów systemowych w trybach twórczych Reżysera
  (np. dostosować „dyrektywę Anti-Closure" w Trybie Audiobooka pod własny
  styl narracji).

Silniki programu (`core_poliglota.py`, `przepisy_rezysera.py`) **same wczytują**
każdy nowy plik `.yaml` położony w poprawnym miejscu i dodają go do
odpowiedniej listy w GUI – **bez przekompilowywania aplikacji**.

## Struktura katalogu

```
dictionaries/
├── README.md                        (ten plik)
└── <kod_języka_bazowego>/           np. "pl", w przyszłości "en", "de", …
    ├── podstawy.yaml                 transliteracja + alfabet danego języka
    ├── akcenty/                      Tryb Reżysera Poligloty – fonetyka pod TTS
    │   ├── <nazwa_akcentu>.yaml
    │   └── …
    ├── szyfry/                       Tryb Szyfranta – zabawy tekstem
    │   ├── <nazwa_szyfru>.yaml
    │   └── …
    └── rezyser/                      Tryby twórcze Reżysera (nowość w 13.0)
        ├── tryb_burza.yaml           prompt i zasady Burzy Mózgów
        ├── tryb_skrypt.yaml          prompt Trybu Surowego Skryptu
        ├── tryb_audiobook.yaml       prompt Trybu Tradycyjnego Audiobooka
        └── postprod_tytuly.yaml      postprodukcja: nadawanie tytułów rozdziałom

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

## Tryby twórcze Reżysera (folder `rezyser/`, nowość w 13.0)

Podfolder `<jezyk>/rezyser/` zawiera pliki YAML opisujące tryby pracy
Głównego Studia Reżyserskiego:

- **`tryb_burza.yaml`** – prompt systemowy dla Burzy Mózgów
  (planowanie fabuły, 3 opcje + szkic promptu, dyrektywa Anti-Closure
  dla scenariusza serialu wielosezonowego).

- **`tryb_skrypt.yaml`** – prompt dla Trybu Surowego Skryptu
  (tagi `[SFX]`, `[Speaker N: Imię – emocja]`, akcenty fonetyczne postaci).
- **`tryb_audiobook.yaml`** – prompt dla Trybu Tradycyjnego Audiobooka
  (czysta proza literacka, zakaz patetycznych domknięć).
- **`postprod_tytuly.yaml`** – prompt modułu postprodukcji, który
  iteruje po rozdziałach i nadaje im literackie tytuły.

Każdy plik trybu zawiera m.in.:

- `id`, `etykieta`, `opis` – metadane widoczne w GUI (RadioBox wyboru trybu).
- `prompt_systemowy` – pełny tekst instrukcji dla modelu GPT-4o.
- `zapis_do_pliku` – flaga `true`/`false` decydująca, czy odpowiedź AI
  zostanie dopisana do pliku projektu (Skrypt/Audiobook = `true`;
  Burza = `false`, bo generuje tylko opcje fabularne).
- `stosuj_akcenty_fonetyczne` – flaga decydująca, czy przed wysłaniem do AI
  silnik ma wypatrywać tagów postaci z akcentem w Księdze Świata i
  preparować odpowiedni pre-prompt.
- `slowa_wyzwalajace` – słowniki słów kluczowych (np. „streszczenie”,
  „podsumowanie”) uruchamiających tryby ratunkowe (np. automatyczne
  streszczenie przy przepełnieniu pamięci).
- `sufiksy_kontekstowe` – dodatkowe wstawki doklejane do prompta w
  zależności od stanu projektu (np. ostatni fragment historii przy
  kontynuacji po wczytaniu streszczenia).

**Uwaga:** Dodanie CAŁKOWICIE nowego trybu twórczego przez Manager Reguł
tworzy gotowy plik YAML — ale kolejność trybów w RadioBoxie (Burza /
Skrypt / Audiobook) jest obecnie ustalona w kodzie Pythona. Lingwista
może bezpiecznie modyfikować istniejące pliki lub dodawać nowe
postprodukcje (iteracje po rozdziałach), ale dodanie zupełnie nowego
czwartego trybu ZAPISU do pliku może wymagać konsultacji z programistą.

## Dodanie NOWEGO języka bazowego (np. angielski)

1. Utwórz folder `dictionaries/en/`.
2. Skopiuj do niego `dictionaries/pl/podstawy.yaml` i dostosuj
   listę diakrytyków oraz alfabet.
3. Utwórz podfoldery `en/akcenty/` i `en/szyfry/` (oraz opcjonalnie
   `en/rezyser/`, jeśli chcesz zlokalizować tryby Reżysera).
4. Wypełnij je plikami `.yaml` wg tej samej konwencji.

Silnik **sam wykryje** nowy język przy starcie aplikacji. Najszybszą
drogą jest użycie Managera Reguł (Ctrl+4) → przycisk „Nowy plik
reguł…" → opcja „Nowy język bazowy" — kreator wygeneruje prompt dla
chatbota AI z pełną listą wymaganych danych (diakrytyki, alfabet),
który wystarczy wkleić do ChatGPT/Claude.


