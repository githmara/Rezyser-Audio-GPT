# Release Notes — Reżyser Audio GPT 13.2 „Wersja Wydawnicza"

*Punkt wyjścia: V13.1 (db5b2d2) → 5 commitów WIP + commit zamykający → V13.2.*
*Motyw przewodni: fundamenty wielojęzyczności faktycznie wielojęzyczne — koniec polskiego hardkodu w sercu pipeline'u.*

---

## TL;DR

13.2 nie dorzuca jeszcze pełnej paczki językowej — robi coś ważniejszego: **przebudowuje fundament tak, żeby kolejne paczki dało się dorzucać bez ruszania kodu Pythona**. Tłumacz AI, Reżyser AI i Poliglota przestają zakładać, że językiem projektu jest polski. Manager Reguł dostaje filtr języka (czysty widok dla NVDA + tryb „pokaż wszystko" dla autorów paczek). Brakujące reguły reżysera dla danego języka miękko fallbackują do angielskiego (neutralny język bootstrap'u), brakujące akcenty i szyfry — twardo wyłączają odpowiednie kontrolki z komunikatem A11y, bo to reguły fonetyczne ściśle związane z językiem źródłowym. Pełna paczka angielska (akcenty + szyfry + smoke test) przesuwa się na 13.3.

---

## Co nowego dla użytkownika końcowego

### Reżyser AI w innym języku interfejsu = angielskie tryby zamiast polskich

- Gdy użytkownik włączy interfejs angielski, fiński czy islandzki, panel Reżysera nie pokazuje już „Burza Mózgów / Skrypt / Audiobook" po polsku. Tryby ładowane są z `dictionaries/<jezyk_ui>/rezyser/`, a gdy folder dla danego języka jeszcze nie istnieje — z `dictionaries/en/rezyser/` (pełen przekład 4 trybów AI dorzucony w 13.2).
- **Twardego polskiego fallbacku już nie ma.** Gdyby ktoś usunął oba foldery (UI i EN), panel pokazuje placeholder w RadioBox + jednorazowy `wx.MessageBox` A11y z wyjaśnieniem, jak naprawić — a nie podsuwa cicho polskie etykiety obcojęzycznemu użytkownikowi NVDA.

### Poliglota wykrywa język tekstu po wczytaniu pliku

- Po wczytaniu pliku panel Poligloty woła `core_poliglota.wykryj_jezyk_zrodlowy()` (z walidacją wobec kompletnych folderów w `dictionaries/`) i przełącza pipeline na wykryty język. Akcenty, szyfry i zakres SpinCtrl szyfru Cezara odświeżają się automatycznie.
- Gdy w wykrytym języku nie ma jeszcze reguł — `wx.ComboBox` akcentów lub szyfrów zostaje wyłączony, tooltip A11y informuje wprost: „Dla języka »fi« nie zainstalowano akcentów fonetycznych. Reguły są ściśle związane z językiem źródłowym i nie mogą być pożyczane z innych folderów dictionaries/." Świadomy kompromis: lepiej zablokować przycisk niż udawać, że polskie reguły fonetyczne zadziałają na fiński tekst.

### Manager Reguł — dropdown „Język" u góry panelu

- Domyślny widok = język interfejsu. Czytnik ekranu nie ślizga się już po obcojęzycznych wpisach, których użytkownik nie rozumie.
- Ostatnia opcja w liście to „🌍 Wszystkie języki" — przeznaczona dla autorów paczek językowych, którzy chcą porównywać foldery obok siebie podczas tworzenia nowej paczki. Akcelerator `&Język:` / `&Language:` ustawiony na pasującą literę w obu UI.
- Lista języków pochodzi z faktycznych folderów w `dictionaries/`, a nie tylko z kompletnych — bo manager służy też do **tworzenia** paczek od zera.

---

## Pod maską

### Tłumacz AI: prompt systemowy zneutralizowany

- `tlumacz_ai._PROMPT_SYSTEMOWY_TEMPLATE` przepisany na angielski i wyniesiony do stałej modułowej. Powód: tłumacz to wewnętrzne narzędzie bootstrap'owe dla autorów paczek językowych — nie user-facing. Polski prompt wprowadzał bias modelu w stronę polskiego źródła i był nieczytelny dla nie-polskiego współautora.
- Świadomie **nie** wynosimy promptu do YAML-a — to byłoby over-engineering. Lokalna stała w module wystarcza, ekstrakcja możliwa w 14.x jeśli pojawi się realna potrzeba (np. modele lokalne preferujące inny język systemowy).

### Reżyser AI: fallback do EN + 4 nowe YAML-e

- `gui_rezyser.py:109` — twardy `pr.lista_trybow("pl")` zamieniony na łańcuch z fallbackiem: `lista_trybow(jezyk_ui) or lista_trybow("en")`. Analogicznie dla `zaladuj_przepis("tytuly", ...)`.
- Folder `dictionaries/en/rezyser/` z czterema plikami: `tryb_audiobook.yaml`, `tryb_burza.yaml`, `tryb_skrypt.yaml`, `postprod_tytuly.yaml`. Pełne tłumaczenia etykiet, promptów systemowych, sufiksów i przypomnień.
- **Zachowano klucze techniczne:** `kategoria: tryb`/`postprodukcja` (porównywane literalnie w `przepisy_rezysera.py`), tagi `<STRESZCZENIE>` i `[ODRZUCENIE_AI]` (parsowane regexami w `rezyser_ai.py`), `id` plików.
- **Zlokalizowano elementy w języku projektu:** `slowa_wyzwalajace.streszczenie` (`summarize/summary/recap`), `regex_podzial_rozdzialow` (`Prologue|Chapter \d+|Epilogue`), pole `jezyk_odpowiedzi` (`English`).
- `_jezyk_kompletny()` wciąż celowo pomija folder `rezyser/` — wymóg przesunięty na 14.x zgodnie z istniejącym komentarzem w `core_poliglota.py:307-310`.

### Poliglota: stała → pole instancji

- `JEZYK_BAZOWY = "pl"` (modułowa stała) usunięta. Zastąpiona przez `self._jezyk_aktywny` ustawianą w konstruktorze na `JEZYK_DOMYSLNY = "pl"` i podmienianą po wczytaniu pliku przez nowy helper `_odswiez_warianty()`.
- `_odswiez_warianty()` przeładowuje `self._akcenty`/`self._szyfry`, odświeża zawartość obu `wx.ComboBox` (`SetSelection(0)`, `Enable()`) lub — gdy lista pusta — wyłącza kontrolkę i ustawia tooltip A11y z komunikatem braku reguł.
- Funkcja `_maybe_ostrzez_o_jezyku_zrodla()` przepisana z bezpośredniego `langdetect.detect()` na `core_poliglota.wykryj_jezyk_zrodlowy()` (tak jak zapowiadał TODO w kodzie). `langdetect` przestał być importowany w warstwie GUI — został tylko w `core_poliglota`, gdzie ma sens.
- Wszystkie wywołania `core_poliglota.przetworz/kod_iso/sufiks_nazwy_pliku/wariant_po_*` używają teraz `self._jezyk_aktywny` zamiast modułowej stałej.

### Manager Reguł: filtr języka i sentinel `_OPCJA_WSZYSTKIE`

- `wx.Choice` u góry panelu zbudowany z dynamicznej listy folderów w `dictionaries/` + ostatnia pozycja „Wszystkie języki" (sentinel `__all__`, nie zderzający się z żadnym kodem ISO).
- `_zaladuj_drzewo()` filtruje pętlę `for jezyk in sorted(os.listdir(...))` przez aktywny filtr — pojedynczy `if filtr != _OPCJA_WSZYSTKIE and jezyk != filtr: continue`.
- Helper `_dostepne_kody_jezykow()` zwraca **wszystkie** foldery (nie tylko kompletne), bo manager służy też do tworzenia paczek od zera dla nowego języka.

### 8 nowych kluczy i18n (PL + EN)

| Sekcja      | Klucz                              | Użycie                                         |
|-------------|-------------------------------------|------------------------------------------------|
| `rezyser`   | `brak_trybow_dla_jezyka`            | komunikat A11y, gdy fallback EN też pusty      |
| `rezyser`   | `brak_trybow_tytul`                 | tytuł `wx.MessageBox`                          |
| `rezyser`   | `placeholder_brak_trybow`           | label w pustym `wx.RadioBox`                   |
| `poliglota` | `brak_akcentow_dla_jezyka`          | tooltip wyłączonego `combo_akcent`             |
| `poliglota` | `brak_szyfrow_dla_jezyka`           | tooltip wyłączonego `combo_szyfr`              |
| `manager`   | `dropdown_jezyk_label`              | etykieta `wx.Choice` (z akceleratorem `&`)     |
| `manager`   | `dropdown_jezyk_tooltip`            | tooltip wyjaśniający domyślny widok i tryb All |
| `manager`   | `opcja_wszystkie_jezyki`            | etykieta sentinela `__all__`                   |

---

## Strategia wdrażania (rozłączenie infrastruktury od zawartości)

### Co znaczy „13.2 = fundament infrastruktury, nie pakiet językowy"?

Pierwotny plan w `TODO_skrotowce_wielojezyczne.md` zakładał: *13.2 = pierwszy w pełni nowy język (np. fiński z pełnym pakietem akcentów i szyfrów)*. Audyt kodu po wydaniu 13.1 ujawnił trzy poważne luki, których ten pakiet nie zamknąłby:

1. `gui_rezyser.py` ładował tryby twardo z `pl/rezyser/` — angielski użytkownik widziałby polskie etykiety w `wx.RadioBox`.
2. `gui_poliglota.py` miał stałą modułową `JEZYK_BAZOWY = "pl"` użytą w 9 miejscach pipeline'u — pakiet fiński działałby tylko w teorii.
3. `tlumacz_ai._prompt_systemowy()` był po polsku i wprowadzał bias modelu.

Bez tych trzech łatek pakiet językowy byłby *false advertising*. 13.2 łata wszystkie trzy. Pełna paczka angielska (akcenty z kompromisami fonetycznymi + szyfry przepisane + smoke test sekcji 6 TODO) trafia do 13.3.

### Co przyniesie 13.3 i dalej

13.3 dostarczy **pierwszy w pełni nowy język** (angielski) plus dwie krytyczne łatki silnika ujawnione podczas audytu 13.2:

- **`odswiez_rezysera.OBSLUGIWANE_JEZYKI` z hardkodu na skan dynamiczny.** Generator wrapperów `akcent_*` musi automatycznie podchwytywać nowe foldery `dictionaries/<kod>/akcenty/` zgodnie z duchem projektu „nowy język = nowy folder".
- **Słowo „akcent" w `dictionaries/<kod>/podstawy.yaml` (lista synonimów).** `core_rezyser.py:146` parsuje Księgę Świata regexem `r"akcent\s+([a-zńśźżćłó]+)..."` — twardy hardkod polskiego słowa i polskiego alfabetu. W 13.3 pole `slowo_akcent: ["akcent"]` (PL) / `["accent", "accented"]` (EN), a alfabet `[a-zńśźżćłó]+` przechodzi na `\w+` z flagą Unicode (skandynawskie/niemieckie/francuskie diakrytyki przestają psuć parsowanie).
- `dictionaries/en/akcenty/` — komplet akcentów z notatki autora (z kompromisami fonetycznymi: nie wszystko da się odwzorować z polskiego na angielski 1:1).
- `dictionaries/en/szyfry/` — sześć algorytmów (cezar/jakanie/odwracanie/samogloskowiec/typoglikemia/wąż) plus rozwinięcia skrótowców `e.g./i.e./etc./Dr./Mr./...` z `TODO § 3.1`.
- `dictionaries/en/podstawy.yaml::polskie_znaki: []` (z definicji puste — angielski nie ma diakrytyków do transliteracji).

Każdy minor 13.x dorzuca **jeden** w pełni wdrożony język (od 13.3 zamiast od 13.2 — przesunięte zgodnie z faktem, że 13.2 zjadł budżet na infrastrukturę). Gdy plik `TODO_skrotowce_wielojezyczne.md` zostanie wyczerpany, następny release to **14.0**.

### Co działa „samoczynnie" od 13.3 (en z pełnym pakietem)

Bez edycji jednej linii Pythona — siatka jest już gotowa:

- `dostepne_jezyki_bazowe()` zwróci `["en", "pl"]`.
- Menu „Język interfejsu" pokaże 2 radio-items (Polski, English).
- `wykryj_jezyk_zrodlowy()` zwróci `"en"` dla angielskiego pliku → Poliglota auto-przełączy pipeline.
- Reżyser dla użytkownika z UI=EN załaduje już pełne `en/rezyser/` (zamiast fallbacku) — bo same pliki YAML w `13.2/dictionaries/en/rezyser/` są kompletne.
- Manager Reguł domyślnie pokaże tylko `en/` w drzewie, dropdown „Wszystkie języki" pozostaje dostępny.

---

## Breaking changes / migracja

- **`JEZYK_BAZOWY` jako modułowa stała w `gui_poliglota.py` została usunięta.** Zewnętrzne skrypty importujące `gui_poliglota.JEZYK_BAZOWY` przestaną działać. Zastąpiona przez `JEZYK_DOMYSLNY` (wartość domyślna) oraz pole instancji `PoliglotaPanel._jezyk_aktywny`. Migracja: nikt zewnętrzny nie powinien o tej stałej wiedzieć — była detalem implementacji.
- **`from langdetect import detect, LangDetectException` w `gui_poliglota.py` usunięty.** Sam pakiet `langdetect` pozostaje w `requirements.txt` — używa go `core_poliglota.wykryj_jezyk_zrodlowy()`. Nie odinstalowywać z venv ani runtime.
- **Polski hardkod w `pr.lista_trybow("pl")` w `gui_rezyser.py` zamieniony na fallback chain.** Aplikacja w UI=PL zachowuje się identycznie (PL ma własne tryby), w UI≠PL wcześniej widać było polski miks etykiet — teraz spójna paczka EN lub komunikat.
- **Numer wersji w obu `ui.yaml` bumpniętym na `13.2`.** Tytuł okna, paczki releasu, dokumentacja czytają stąd — efekt automatyczny.

---

*Notes wygenerowane na podstawie 5 commitów WIP (810eb28..d28767c) + commit zamykający. Pełna lista: `git log V13.1..HEAD --oneline`.*
