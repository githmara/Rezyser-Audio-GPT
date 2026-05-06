# TODO: Wielojęzyczność (notatka robocza)

> **Status pliku:** Osobista notatka autora projektu. Plik nie trafia do
> paczek releasowych – `buduj_wydanie.py` i `skrypt_instalatora.iss`
> globalnie ignorują wszystkie `*.md` poza tym, co świadomie włączyły,
> więc użytkownik końcowy tego pliku nigdy nie zobaczy.

## 1. Kontekst

Punkt wyjścia do rozbudowy Odwracacza Tekstu (`dictionaries/pl/szyfry/odwracanie.yaml`)
o inne języki to **zewnętrzny notebook analityczny od autora projektu**
(niebędący częścią tego repozytorium). Zawiera gotowy słownik `ABBREV_BY_LANG`
z regexami skrótowców dla **6 języków**:

| Język       | Kod ISO | Źródło regexów                       |
|-------------|---------|--------------------------------------|
| polski      | `pl`    | notebook + ten projekt (zrobione ✅) |
| rosyjski    | `ru`    | notebook (zrobione ✅ 13.5)           |
| angielski   | `en`    | notebook (zrobione ✅ 13.3)           |
| włoski      | `it`    | notebook                             |
| fiński      | `fi`    | notebook (zrobione ✅ 13.4)           |
| islandzki   | `is`    | notebook (zrobione ✅ 13.6)           |

Reguły polskie już są w `dictionaries/pl/szyfry/odwracanie.yaml`
(sekcja `rozwiniecia`). Pozostałe języki – do dopisania, gdy i jeśli
pojawi się na nie zapotrzebowanie (np. przez zgłoszony Pull Request).

## 2. Kluczowa różnica: rozwinięcia vs poprawki

Notebook z którego pochodzą regexy **normalizuje** skrótowce (sprowadza
je do jednej formy, bo autor notebooka karmi nimi spaCy / TF-IDF, które
nie lubią różnych zapisów tego samego skrótu):

```python
# Notebook: poprawka pisowni (normalizacja)
(r"\bm\.\s*in\.?,?\b",  "m.in.")          # "m. in." → "m.in."
(r"\bmi\.in\.?\b",      "m.in.")          # "mi.in."  → "m.in."
```

Tutaj Odwracacz Tekstu robi **coś odwrotnego**: **rozwija** skrótowce do
pełnej formy, żeby po odwróceniu zdania wspak tekst nadal brzmiał
sensownie (patrz `_algo_odwracanie` w `core_poliglota.py`):

```yaml
# Reżyser: rozwinięcie do pełnego brzmienia (nie normalizacja)
- { wzor: '\bm\.\s*in\.?,?\b', zamiana: "między innymi" }
- { wzor: '\bmi\.in\.?\b',     zamiana: "między innymi" }
```

**Przy adaptacji trzeba podmienić prawą stronę pary** – zamiast
„znormalizowanego skrótu" podać pełne rozwinięcie słowne w danym
języku. Wzorce (lewa strona) przenoszą się 1:1 z notebooka.

## 3. Co dałoby się dopisać

### 3.1 Języki mające regexy w notebooku

Dla każdego z poniższych języków trzeba założyć folder
`dictionaries/<kod>/szyfry/` z plikiem `odwracanie.yaml` – schemat
1:1 jak polski:

* `id: odwracanie`
* `iso: <kod>`
* `rozwiniecia` – wzorce z notebooka + rozwinięcie do pełnej formy.

Nowy język bazowy wymaga też pliku `dictionaries/<kod>/podstawy.yaml`
(alfabet + ewentualna tabela transliteracji). Silnik autodetekuje
nowe foldery przez `dostepne_jezyki_bazowe()` w `core_poliglota.py`.

- [x] **Rosyjski (`ru`)** – wdrożone w 13.5 (paczka kompletna: 8 akcentów + 6 szyfrów + 4 reżyserów + GUI):
  - [x] `т.е.` → `то есть`
  - [x] `т.д.` → `так далее`
  - [x] `т.п.` → `тому подобное`
  - [x] `т.к.` → `так как`
  - [x] `т.н.` → `так называемый`
  - [x] `и.о.` → `исполняющий обязанности`
  - [x] `с.г.` → `сего года`
  - [x] `н.э.` → `нашей эры`
  - [x] `в.т.ч.` → `в том числе`
  - [x] `и т.д.` / `и т.п.` → `и так далее` / `и тому подобное`
  - [x] `проф.` → `профессор`
  - [x] `акад.` → `академик`
  - [x] `доц.` → `доцент`
  - [x] `ул.` → `улица`
  - [x] `пр.` → `проспект`
  - [x] `пер.` → `переулок`

- [x] **Angielski (`en`)** – wdrożone w 13.3:
  - [x] `e.g.` / `e. g.` → `for example`
  - [x] `i.e.` / `i. e.` → `that is`
  - [x] `U.S.` / `U. S.` → `United States` (z negative lookahead `(?![A-Z])`,
        chroni `U.S.A` przed fałszywym dopasowaniem do `U.S.` + leftover `A`)
  - [x] `U.S.A.` → `United States of America` (greedy guard PRZED `U.S.`)
  - [x] `U.K.` / `U. K.` → `United Kingdom`
  - [x] `etc.` → `et cetera`
  - [x] `vs.` → `versus`
  - [x] `cf.` → `confer`
  - [x] `Dr.` → `Doctor`
  - [x] `Mr.` → `Mister`
  - [x] `Mrs.` → `Missus`
  - [x] `Ms.` → `Miss`
  - [x] `Prof.` → `Professor`
  - [x] `St.` → `Saint` (wybrany wariant; "Street" do rozważenia per-projekt)
  - [x] `Fig.` → `Figure`
  - [x] `No.` → `Number`
  - [x] `pp.` → `pages` (greedy guard PRZED `p.`)
  - [x] `p.` → `page`

- [x] **Włoski (`it`)** – wdrożone w 13.7 (paczka kompletna: 8 akcentów + 6 szyfrów + 4 reżyserów + GUI):
  - [x] `ad es.` → `ad esempio`
  - [x] `ecc.` → `eccetera`
  - [x] `dott.` → `dottore`
  - [x] `prof.` → `professore`
  - [x] `pag.` / `pagg.` → `pagina` / `pagine`
  - [x] `sig.` → `signore`
  - [x] `sig.ra` → `signora`
  - [x] `art.` → `articolo`
  - [x] `cap.` → `capitolo`
  - [x] `n.` / `n.ro` → `numero`
  - [x] `cfr.` → `confronta`
  - [x] `vol.` → `volume`

- [x] **Fiński (`fi`)** – wdrożone w 13.4 (paczka kompletna: 8 akcentów + 6 szyfrów + GUI):
  - [ ] `esim.` → `esimerkiksi`
  - [x] `jne.` → `ja niin edelleen`
  - [ ] `ym.` → `ynnä muuta`
  - [x] `ns.` → `niin sanottu`
  - [ ] `tms.` → `tai muuta sellaista`
  - [x] `ko.` → `kyseinen`
  - [ ] `po.` → `pitää olla` (lub kontekst. `pohjoiseen`)
  - [ ] `vt.` → `virkaa tekevä`
  - [x] `prof.` → `professori` (opcjonalna kropka: `prof\.?\s`)
  - [x] `dr.` → `tohtori` (opcjonalna kropka: `dr\.?\s`)
  - [ ] `os.` → `osasto` (YAML ma błędnie: `omaa sukua` — wymaga korekty)
  - [x] `v.` → `vuosi` (jako `vuonna` przed cyfrą: `v\.?\s(?=\d)`)
  - [x] `n.` → `noin` (dodane w 13.4: `\bn\.\s`)

- [x] **Islandzki (`is`)** – z notebooka: ✅ wdrożone w 13.6
  - [x] `t.d.` → `til dæmis`
  - [x] `þ.e.` → `það er`
  - [x] `m.a.` → `meðal annars`
  - [x] `u.þ.b.` → `um það bil`
  - [x] `o.s.frv.` → `og svo framvegis`
  - [x] `dr.` → `doktor`
  - [x] `prof.` → `prófessor`
  - [x] `bls.` → `blaðsíða`
  - [x] `skv.` → `samkvæmt`
  - [x] `fh.` → `fyrir hönd`

### 3.2 Języki bez regexów w notebooku

W tym projekcie istnieją polskie akcenty dla tych języków, ale notebook
nie podał dla nich regexów skrótowców. Gdyby miały dostać Odwracacz,
trzeba by dopisać regexy od zera. Wstępne podpowiedzi:

- [ ] **Francuski (`fr`)** – typowe skrótowce:
  - [ ] `p. ex.` → `par exemple`
  - [ ] `c.-à-d.` → `c'est-à-dire`
  - [ ] `etc.` → `et cetera`
  - [ ] `M.` / `Mme` / `Mlle` → `Monsieur` / `Madame` / `Mademoiselle`
  - [ ] `Dr` / `Pr` → `Docteur` / `Professeur`
  - [ ] `No` / `n°` → `numéro`
  - [ ] `p.` → `page`
  - [ ] `cf.` → `confer`

- [ ] **Niemiecki (`de`)** – typowe skrótowce:
  - [ ] `z. B.` → `zum Beispiel`
  - [ ] `d. h.` → `das heißt`
  - [ ] `u. a.` → `unter anderem`
  - [ ] `usw.` → `und so weiter`
  - [ ] `u. Ä.` → `und Ähnliches`
  - [ ] `bzw.` → `beziehungsweise`
  - [ ] `Hr.` / `Fr.` → `Herr` / `Frau`
  - [ ] `Dr.` / `Prof.` → `Doktor` / `Professor`
  - [ ] `Str.` → `Straße`
  - [ ] `S.` / `Nr.` → `Seite` / `Nummer`

- [ ] **Hiszpański (`es`)** – typowe skrótowce:
  - [ ] `p. ej.` → `por ejemplo`
  - [ ] `es dec.` → `es decir`
  - [ ] `etc.` → `etcétera`
  - [ ] `Sr.` / `Sra.` / `Srta.` → `Señor` / `Señora` / `Señorita`
  - [ ] `Dr.` / `Prof.` → `Doctor` / `Profesor`
  - [ ] `núm.` → `número`
  - [ ] `pág.` → `página`

## 4. Strategia wdrażania (spójna z `CLAUDE.md`)

Dla każdego nowego języka stosujemy 5-etapowy schemat — ten sam, który
opisuje sekcja „WIELOJĘZYCZNOŚĆ I TŁUMACZENIA INTERFEJSU" w `CLAUDE.md`
(akapit „Bezpieczna kolejność wdrażania"). Kolejność
jest nieprzypadkowa: najpierw weryfikujemy, że treści w nowym języku
w ogóle działają w silniku Poligloty, a dopiero potem inwestujemy czas
(i tokeny LLM) w tłumaczenie warstwy UI i dokumentacji.

1. **Język bazowy — treści.** Utwórz komplet plików w `dictionaries/<kod>/`:
   ```
   dictionaries/<kod>/
   ├── podstawy.yaml               # alfabet + ewentualna transliteracja
   ├── akcenty/                    # WSZYSTKIE akcenty poza natywnym
   │   ├── angielski.yaml          #   (dla <kod>=fi: pl/en/ru/... ALE NIE fi)
   │   ├── polski.yaml
   │   └── ...
   ├── szyfry/                     # te same 6 algorytmów co dictionaries/pl/szyfry/
   │   ├── cezar.yaml
   │   ├── jakanie.yaml
   │   ├── odwracanie.yaml         # <- tutaj rozwinięcia skrótowców z notebooka
   │   ├── samogloskowiec.yaml
   │   ├── typoglikemia.yaml
   │   └── waz.yaml
   └── gui/                        # tłumaczenia UI (dodawane w etapie 2 i 3)
       ├── ui.yaml                 #   etykiety przycisków, menu, tooltipów
       └── dokumentacja/           #   przetłumaczona instrukcja / readme
   ```
   Bez `podstawy.yaml` silnik nie wykryje języka (autodetekcja w
   `core_poliglota.py::dostepne_jezyki_bazowe`). Podfolder `gui/` w etapie 1
   może być jeszcze pusty — wypełniamy go w kolejnych etapach. Zakończ etap
   **smoke testem** z sekcji 6 tego pliku — puść wybrane zdania przez
   `_algo_odwracanie` i zweryfikuj, czy wynik pokrywa się z kolumną
   „oczekiwany wynik silnika".

2. **Tłumaczenie interfejsu.** Dodaj `dictionaries/<kod>/gui/ui.yaml`
   (etykiety przycisków, nagłówki paneli, komunikaty walidacji) — ten sam
   schemat kluczy co `dictionaries/pl/gui/ui.yaml`, tylko przetłumaczone
   wartości. Tłumaczenia UI mieszkają obok reszty warstwy językowej
   (`akcenty/`, `szyfry/`, `rezyser/`), dzięki czemu dodanie nowego języka
   to jeden folder `dictionaries/<kod>/` — nie dwa. Parametry dynamiczne
   (`{numer_rozdzialu}`, `{nazwa_pliku}`, `{liczba_znakow}`, …) zostają
   bez zmian — patrz `CLAUDE.md` sekcja „WIELOJĘZYCZNOŚĆ I TŁUMACZENIA INTERFEJSU".

3. **Tłumaczenie dokumentacji/instrukcji.** Uruchom skrypt
   autotłumaczący (`tlumacz_ai.py` lub dedykowany batch) — ma
   **zamrozić** parametry `{…}` przed wysyłką do LLM i scalić je
   z odpowiedzią po tłumaczeniu. Wynik trafia do `dictionaries/<kod>/gui/`
   (obok `ui.yaml`).

4. **Odznaczenie języka w tym pliku.** Przekreśl pozycje w sekcjach
   3.1 / 3.2 oraz odhacz odpowiednie zdania smoketestowe w sekcji 6.
   To sygnał, że język jest w pełni wdrożony.

5. **Release** jako kolejna wersja **13.x**: jeden nowy w pełni wdrożony
   język na release (od 13.3 wzwyż). Gdy ten plik zostanie wyczerpany
   (wszystkie języki z sekcji 3.1 i 3.2 zamknięte), następny release to
   **14.0**, a plik `TODO_wielojezycznosc.md` można usunąć
   z repozytorium.

   > **Uwaga o numeracji 13.1 i 13.2.** Wbrew pierwotnemu założeniu
   > „13.1 = pierwszy w pełni nowy język" release 13.1 stał się commitem
   > porządkowym dla istniejących stubów językowych: refresh pól
   > `opis: |` i komentarzy nagłówkowych w `dictionaries/<kod>/podstawy.yaml`
   > (en/fi/is/it/ru) na języki natywne, bez dorzucania `akcenty/` ani
   > `szyfry/`. Release **13.2** też nie przyniósł pełnej paczki językowej —
   > zamiast tego załatał trzy luki w fundamencie ujawnione podczas audytu
   > po 13.1: polski hardkod w `gui_rezyser.py`, modułową stałą
   > `JEZYK_BAZOWY` w `gui_poliglota.py` (używaną w 9 miejscach pipeline'u)
   > oraz polski prompt systemowy w `tlumacz_ai.py`. Plus przekład 4 trybów
   > Reżysera AI na angielski (jako miękki fallback) i dropdown filtra
   > języka w Managerze Reguł. Bez tych łatek pakiet językowy byłby
   > *false advertising* — fiński user widziałby polski miks etykiet
   > zaraz po przełączeniu UI.
   >
   > Pełen pakiet każdego języka (akcenty + szyfry + smoke test sekcji 6)
   > trafia więc od **13.3** (przesunięte z 13.2) — jeden język na release,
   > zgodnie z „Jeden język na raz" w Uwagach operacyjnych poniżej. 13.3
   > otwiera angielski, plus dwie krytyczne łatki silnika ujawnione przy
   > 13.2: dynamiczny skan języków w `odswiez_rezysera.py` (zamiast
   > `OBSLUGIWANE_JEZYKI = ("pl",)`) i pole `slowo_akcent` w `podstawy.yaml`
   > (regex `[a-zńśźżćłó]+` w `core_rezyser.py:146` przechodzi na `\w+`
   > z flagą Unicode, żeby skandynawskie/niemieckie/francuskie diakrytyki
   > w Księdze Świata przestały psuć parsowanie).

### Uwagi operacyjne

- **Jeden język na raz.** Wrzucenie kilkunastu YAML-i w jednym commicie
  utrudnia przegląd i testowanie. Lepiej dokładać pojedynczo (najlepiej
  z krótkim smoke testem przed merge do `main`).
- **Autodetekcja.** Silnik wykryje nowy folder `dictionaries/<kod>/`
  automatycznie przez `dostepne_jezyki_bazowe()` — nie trzeba ręcznie
  dopisywać niczego do kodu Pythona.
- **Manager Reguł — opcjonalne rozszerzenie.** `gui_manager_regul.py` już dziś
  skanuje `dictionaries/*/` i pokazuje trzy kategorie (`akcenty/`, `szyfry/`,
  `rezyser/`) w drzewie plików. Dodanie czwartej kategorii `gui/` to czysto
  kosmetyczna zmiana (stała `FOLDER_GUI`, wpis w `_ETYKIETA_KATEGORII`,
  rozszerzenie jednej krotki w pętli) — może wejść w dowolnym releasie 13.x,
  nie blokuje pierwszego wydania z tłumaczonym interfejsem. Patrz
  `CLAUDE.md` sekcja „WIELOJĘZYCZNOŚĆ I TŁUMACZENIA INTERFEJSU"
  (uwaga o `gui_manager_regul.py` skanującym `dictionaries/*/`).
- **Szybki sprawdzian w GUI.** Po zamknięciu etapów 1 i 2 odpal
  `python main.py`, wejdź w Poliglota → Tryb Szyfranta → wybierz nowy
  język bazowy. Odwracacz powinien rozwinąć skrótowce, kod ISO w pliku
  wynikowym musi być właściwy, a etykiety przycisków — w nowym języku.

## 5. Powiązane artefakty

* `dictionaries/pl/szyfry/odwracanie.yaml` – wzorzec (rozwinięcia,
  nie normalizacja).
* `core_poliglota.py::_algo_odwracanie` – silnik, który czyta
  `rozwiniecia` i aplikuje je przez `re.sub(..., flags=re.IGNORECASE)`.
* `core_poliglota.py::dostepne_jezyki_bazowe` – autodetekcja nowych
  folderów `dictionaries/<kod>/`.

---

## 6. Przykłady smoketestowe (błędy redakcyjne w skrótowcach)

> Gotowe zdania testowe do weryfikacji silnika `_algo_odwracanie` dla każdego
> nowego języka. Każde zawiera **celowy błąd pisowni skrótowca** — taki, jaki
> przecieka przez korektę redakcyjną (literówka, brak kropki, nieprawidłowa
> spacja wewnątrz skrótu). Kolumna „oczekiwany wynik" pokazuje, czy silnik
> **powinien** rozwinąć skrót (✅ pokrywa regex) czy go **zostawić**
> (⚠️ poza zasięgiem — warto rozważyć, czy rozszerzyć wzorzec).

### 6.1 Polski (`pl`)

| Wejście (zdanie ze skrótowcem)                                          | Błąd redakcyjny              | Oczekiwany wynik silnika                         |
|-------------------------------------------------------------------------|------------------------------|--------------------------------------------------|
| `Byli obecni m.in przedstawiciele czterech mediów.`                     | brak końcowej `.`            | ⚠️ nie rozwinięte (`m\.in\.` wymaga obu kropek) |
| `Kupił tzt. wszystko, co było potrzebne na targi.`                      | literówka `tzt.`             | ⚠️ nie rozwinięte (brak wzorca dla `tzt\.`)     |
| `To był n.p. największy błąd w całym projekcie.`                        | `n.p.` zamiast `np.`         | ⚠️ nie rozwinięte (niepoprawna forma skrótu)     |
| `Projekt zakończono tj. w czerwcu ubiegłego roku.`                      | forma poprawna               | ✅ rozwinięte → `to jest`                        |
| `Wyniki były b.dobre, tj. na poziomie 98 procent.`                      | `b.` bez spacji i rozwinięcia | ⚠️ `b.` — bez rozwinięcia; `tj.` → ✅ `to jest` |
| `Przybyło ok 400 uczestników, w tym wielu z zagranicy.`                 | brak `.` po `ok`             | ⚠️ nie rozwinięte (regex: `ok\.`)               |

### 6.2 Angielski (`en`) ✅ zwalidowane w 13.3

| Wejście                                                                 | Błąd redakcyjny              | Oczekiwany wynik silnika                         |
|-------------------------------------------------------------------------|------------------------------|--------------------------------------------------|
| `The results were positive, e.g faster loading times than before.`      | brak końcowej `.`            | ⚠️ nie rozwinięte (regex: `e\.g\.`)             |
| `She called her boss, ie. the director, to inform him directly.`        | przestawiona `.` (`ie.`)     | ⚠️ nie rozwinięte (`ie\.` ≠ `i\.e\.`)           |
| `We brought snacks, ect. for everyone at the conference.`               | literówka `ect.`             | ⚠️ nie rozwinięte (brak wzorca dla `ect\.`)     |
| `Dr Smith confirmed the diagnosis in the morning.`                      | brak `.` po `Dr`             | ⚠️ nie rozwinięte (regex: `Dr\.`)               |
| `He studied in the U.S.A without any financial support.`                | brak końcowej `.`            | ⚠️ nie rozwinięte (regex: `U\.S\.A\.`)          |
| `See p 14 for more details on this topic.`                              | brak `.` po `p`              | ⚠️ nie rozwinięte (regex: `p\.` / `pp\.`)       |

### 6.3 Rosyjski (`ru`) ✅ zwalidowane w 13.5

| Wejście                                                                 | Błąd redakcyjny              | Oczekiwany wynik silnika                         |
|-------------------------------------------------------------------------|------------------------------|--------------------------------------------------|
| `Результаты были т.е не такими, как предполагалось изначально.`         | brak końcowej `.`            | ⚠️ nie rozwinięte (regex: `т\.е\.`)             |
| `Взяли всё необходимое, и т.д без каких-либо исключений.`               | brak końcowej `.`            | ⚠️ nie rozwinięte (regex: `т\.д\.`)             |
| `Заведующий кафедрой проф Иванов выступил первым на конференции.`       | brak `.` po `проф`           | ⚠️ nie rozwinięte (regex: `проф\.`)             |
| `На ул Пушкина состоялся митинг жителей квартала.`                      | brak `.` po `ул`             | ⚠️ nie rozwinięte (regex: `ул\.`)               |
| `Мероприятие прошло в т.ч при участии зарубежных делегаций.`            | brak końcowej `.` (`в т.ч`)  | ⚠️ nie rozwinięte (regex: `в\.т\.ч\.`)          |

### 6.4 Włoski (`it`) ✅ zwalidowane w 13.7

| Wejście                                                                 | Błąd redakcyjny              | Oczekiwany wynik silnika (13.7)                          |
|-------------------------------------------------------------------------|------------------------------|----------------------------------------------------------|
| `Ha acquistato diversi articoli, ecc tra cui libri e riviste.`          | brak `.` po `ecc`            | ✅ rozwinięte (`\.?` — kropka opcjonalna)               |
| `Il sig Rossi ha firmato il contratto nella tarda mattinata.`           | brak `.` po `sig`            | ✅ rozwinięte (`\.?` — kropka opcjonalna)               |
| `Vedi pagg 14–16 per ulteriori dettagli sulla questione.`               | brak `.` po `pagg`           | ✅ rozwinięte (`\.?` — kropka opcjonalna)               |
| `Il dott Bianchi ha presentato i risultati dello studio.`               | brak `.` po `dott`           | ✅ rozwinięte (`\.?` — kropka opcjonalna)               |
| `Per maggiori informazioni cfr il capitolo precedente.`                 | brak `.` po `cfr`            | ✅ rozwinięte (`\.?` — kropka opcjonalna)               |

> **Uwaga (13.7):** Implementacja używa wzorców `\.?` (kropka opcjonalna), więc silnik łapie **wszystkie 5 form z brakującą kropką** — lepiej niż zakładała tabela (która bazowała na ścisłych wzorcach z notebooka). 14/14 testów pozytywnych (poprawnie zapisane skrótowce) zaliczonych. Formy z brakującą kropką to bonus `\.?`, nie cofnięcie.

### 6.5 Fiński (`fi`) ✅ zwalidowane w 13.4

| Wejście                                                                 | Błąd redakcyjny              | Oczekiwany wynik silnika                         |
|-------------------------------------------------------------------------|------------------------------|--------------------------------------------------|
| `Hänellä oli useita tehtäviä, esim kirjoittaa raportti ennen kokousta.` | brak `.` po `esim`           | ⚠️ nie rozwinięte (regex: `esim\.`)             |
| `Ostimme ruokaa, jn.e. kaikkea tarpeellista ennen matkaa.`              | przestawienie: `jn.e.`       | ⚠️ nie rozwinięte (regex: `jne\.`)              |
| `Hän oli nss. tunnettu asiantuntija omalla alallaan.`                   | podwójne `s`: `nss.`         | ⚠️ nie rozwinięte (regex: `ns\.`)               |
| `Johtaja, prof Mäkinen, piti avauspuheen konferenssissa.`               | brak `.` po `prof`           | ⚠️ nie rozwinięte (regex: `prof\.`)             |
| `Projekti kesti n. kaksi vuotta ennen valmistumistaan.`                 | forma poprawna               | ✅ rozwinięte → `noin`                           |

### 6.6 Islandzki (`is`)

| Wejście                                                                 | Błąd redakcyjny              | Oczekiwany wynik silnika                         |
|-------------------------------------------------------------------------|------------------------------|--------------------------------------------------|
| `Hann keypti margt, t.d bækur og tónlist á vefsíðunni.`                 | brak końcowej `.`            | ⚠️ nie rozwinięte (regex: `t\.d\.`)             |
| `Þetta er þ.e. besta mögulega lausn á vandanum.`                        | forma poprawna               | ✅ rozwinięte → `það er`                         |
| `Hún skrifaði undir skv lögum um opinberar skrár.`                      | brak `.` po `skv`            | ⚠️ nie rozwinięte (regex: `skv\.`)              |
| `Verðið var u.þ.b 50 þúsund krónur á hvern einstakling.`                | brak końcowej `.`            | ⚠️ nie rozwinięte (regex: `u\.þ\.b\.`)          |
| `Fundarmaður fh ráðherra mætti á fundinn í stað hans.`                  | brak `.` po `fh`             | ⚠️ nie rozwinięte (regex: `fh\.`)               |

> **Uwaga do sekcji 6.7–6.9:** poniższe języki (`fr`, `de`, `es`) nie mają
> regexów w notebooku źródłowym (sekcja 3.2 tego pliku). Smoketesty są więc
> scenariuszami **docelowymi** — zadziałają dopiero, gdy dopiszemy
> `dictionaries/<kod>/szyfry/odwracanie.yaml` z propozycjami rozwinięć z 3.2.
> Do tego czasu silnik zwróci „⚠️ nie rozwinięte" także dla form poprawnych.

### 6.7 Francuski (`fr`)

| Wejście                                                                 | Błąd redakcyjny              | Oczekiwany wynik silnika                         |
|-------------------------------------------------------------------------|------------------------------|--------------------------------------------------|
| `Il a acheté plusieurs livres, p. ex des romans et des essais.`         | brak końcowej `.`            | ⚠️ nie rozwinięte (regex: `p\. ex\.`)           |
| `Le directeur, c.-a-d. Monsieur Dupont, a validé la décision.`          | `a` bez akcentu (`c.-a-d.`)  | ⚠️ nie rozwinięte (regex wymaga `c\.-à-d\.`)    |
| `M Dupont a signé le contrat hier après-midi à la mairie.`              | brak `.` po `M`              | ⚠️ nie rozwinięte (regex: `M\.`)                |
| `Le Dr Martin a confirmé le diagnostic rapidement au patient.`          | forma poprawna (w fr bez `.`) | ✅ rozwinięte → `Docteur` (regex: `Dr\b`)       |
| `Consultez la page no 42 pour plus de détails sur le sujet.`            | `no` zamiast `n°`            | ⚠️ nie rozwinięte (regex: `n°`)                 |
| `On a visité etc des musées, mais aussi des parcs historiques.`         | `etc` bez końcowej `.`       | ⚠️ nie rozwinięte (regex: `etc\.`)              |

### 6.8 Niemiecki (`de`)

| Wejście                                                                 | Błąd redakcyjny              | Oczekiwany wynik silnika                         |
|-------------------------------------------------------------------------|------------------------------|--------------------------------------------------|
| `Er brachte Geschenke mit, z.B Schokolade und Blumen für alle Gäste.`   | brak spacji i `.` (`z.B`)    | ⚠️ nie rozwinięte (regex: `z\. B\.`)            |
| `Das Projekt endete, d. h am letzten Freitag des Monats pünktlich.`     | brak końcowej `.`            | ⚠️ nie rozwinięte (regex: `d\. h\.`)            |
| `Herr Dr Müller leitete die Sitzung souverän bis zum Abend.`            | brak `.` po `Dr`             | ⚠️ nie rozwinięte (regex: `Dr\.`)               |
| `Die Veranstaltung war erfolgreich, u. a wegen der Musikauswahl.`       | brak końcowej `.` (`u. a`)   | ⚠️ nie rozwinięte (regex: `u\. a\.`)            |
| `Wir fahren zur Hauptstr 15 im Zentrum der Altstadt morgen früh.`       | brak `.` po `Hauptstr`       | ⚠️ nie rozwinięte (regex: `Str\.`)              |
| `Siehe S. 42 und Nr. 7 des Anhangs für weitere Informationen.`          | forma poprawna               | ✅ rozwinięte → `Seite` / `Nummer`              |

### 6.9 Hiszpański (`es`)

| Wejście                                                                 | Błąd redakcyjny              | Oczekiwany wynik silnika                         |
|-------------------------------------------------------------------------|------------------------------|--------------------------------------------------|
| `Trajo varias frutas, p. ej manzanas y peras frescas del mercado.`      | brak końcowej `.`            | ⚠️ nie rozwinięte (regex: `p\. ej\.`)           |
| `El Sr Pérez firmó el contrato por la mañana en la notaría central.`    | brak `.` po `Sr`             | ⚠️ nie rozwinięte (regex: `Sr\.`)               |
| `La Sra. Gómez llegó tarde a la reunión directiva del consejo.`         | forma poprawna               | ✅ rozwinięte → `Señora`                         |
| `Véase pág 12 para más información sobre el tema tratado.`              | brak `.` po `pág`            | ⚠️ nie rozwinięte (regex: `pág\.`)              |
| `El núm 5 de la colección es el más buscado por los lectores.`          | brak `.` po `núm`            | ⚠️ nie rozwinięte (regex: `núm\.`)              |
| `El Dr. Ramírez presentó los resultados ante el comité científico.`     | forma poprawna               | ✅ rozwinięte → `Doctor`                         |

---

## 7. Otwarte zadania silnika (post-13.3)

Notatki ujawnione podczas wdrażania pełnej paczki angielskiej. Nie blokują
żadnego kolejnego języka z sekcji 3 — to są usprawnienia jakościowe, które
można wdrożyć w dowolnej kolejności w 13.x+, gdy któreś okaże się
problemem w realnym użyciu.

### 7.1 Łącznik „na" w regułach lore-ad-hoc (`core_rezyser.py:~165`)

Reguły ad-hoc w Księdze Świata zapisuje się dziś po polsku:

```
[Geralt: zamień 'w' na 'v', 'r' na 'rr']
```

Regex w `core_rezyser.zastosuj_akcenty_uniwersalne` szuka literału `na`
między cudzysłowami. Po angielsku autor Księgi napisałby naturalnie
`'w' to 'v'` lub `'w' becomes 'v'`, a parser tego nie złapie. Rozwiązanie
analogiczne do `slowo_akcent` z 13.3:

* nowe pole `slowo_zamiany: ["na"]` (PL) / `["to", "becomes"]` (EN) /…
  w `dictionaries/<jezyk>/podstawy.yaml`,
* `core_poliglota.slowa_zamiany(jezyk)` — publiczny helper z fallbackiem,
* regex w `core_rezyser` budowany dynamicznie analogicznie do
  `wzorzec_akcentu`.

Nie ma realnego pilnego przypadku — domyślne reguły akcentów w YAML-ach
wystarczają w 99 % scenariuszy, ad-hoc Lore to backdoor dla specjalnych
przypadków. Wystarczy 13.x+ kiedyś.

### 7.2 Heurystyka stop-words dla regexa parsera akcentów

Regex `(?:slowo)\s+(\w+)|(\w+)\s+(?:slowo)` z 13.3 łapie sąsiada
**bezpośrednio** przylegającego do słowa-wyzwalacza. W gramatykach
przylegających (PL: „francuski akcent" — przymiotnik tuż przed
rzeczownikiem) to działa naturalnie. W angielskim zdania typu
„heavily accented French" gubią się na przysłówku: regex chwyci
„heavily" zamiast „French".

Możliwe rozwiązania:

* **Lista stop-words per język** w `podstawy.yaml`
  (`stop_slowa_akcentu: ["heavily", "barely", "thickly", ...]`) —
  parser pomija sąsiadów z tej listy i bierze następny kandydat.
* **Backup heurystyka**: gdy „lewy sąsiad" pasuje do listy stop-words,
  parser bierze jeszcze jedno słowo wstecz (lub w prawo, jeśli
  istnieje pasujący kandydat po słowie-wyzwalaczu).
* **Workaround dla użytkownika** (już dziś): pisać Księgę Świata prosto
  („French accent", nie „heavily accented French"). Udokumentować
  w paczce dokumentacji EN.

W 13.3 idziemy z workaround'em w dokumentacji. Jeśli realni użytkownicy
zaczną zgłaszać problem — dorobić konfigurowalną listę stop-words w
13.x+.

### 7.3 Konfigurowalna trailing-letter w silniku węża (`_algo_waz`)

Silnik ma twardy `if znak.lower() == "sz": syk = "s" * ile + "z"`.
Polski dwuznak `sz` zachowuje końcowe `z`. Dla angielskiego `sh` ten
sam mechanizm wymaga dodatkowej gałęzi — w 13.3 obeszliśmy to
upraszczając regex do `(?i)(s|z)` (`sh` rozpada się na rozciągnięte
`s` + zachowane `h`). Dla pełnej elastyczności (np. niemieckie `sch`,
szwedzkie `sj`):

* nowe pole `dwuznaki_sykow: [{wzor: "sz", trailing: "z"}, {wzor: "sch",
  trailing: "ch"}, ...]` w `dictionaries/<jezyk>/szyfry/waz.yaml`,
* refaktor `_algo_waz` na pętlę po dwuznakach + fallback na pojedynczy
  znak.

Niski priorytet — polski `sz` jest jedynym użytym dwuznakiem, kompromis
EN brzmi naturalnie.

### 7.4 Wymagane `regex: true` przy regex-paternach w YAML-ach

Silnik `core_poliglota._zastosuj_zamiany` używa `str.replace` domyślnie,
a `re.sub` TYLKO gdy w wpisie YAML jest `regex: true`. Wpadek typu:

```yaml
- { wzor: '\by', zamiana: "й" }   # ZŁE: \b traktowane jako literał
- { wzor: '\by', zamiana: "й", regex: true }   # OK
```

Ujawnione przy 13.3 podczas wdrażania `\b`-paternów w `en/akcenty/rosyjski.yaml`
(word-boundary `y` na cyrylicę + ubezdźwięcznianie końcówek). Naprawione,
ale wartoby dorzucić walidację w Manager Reguł albo skrypt sanity-check
który ostrzega gdy `wzor` zawiera meta-znaki regex bez flagi `regex: true`.
Lista podejrzanych meta-znaków: `\b \w \W \d \D \s \S ( ) [ ] { } | ^ $ + * ?`.

Niski priorytet do czasu, aż druga osoba zacznie pisać paczki językowe.

### 7.5 Normalizacja podwójnego skryptu w paczce ru/ ✅ zamknięte w 13.5

Wybrano **ścieżkę B** (rozszerzony alfabet). `dictionaries/ru/podstawy.yaml::alfabet`
to teraz 59-znakowy ciąg `АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯABCDEFGHIJKLMNOPQRSTUVWXYZ`,
więc każdy znak (cyrylica i łacinka) jest szyfrowany w obrębie tego samego
pierścienia. Round-trip działa: "Apple это марка iPhone" + Cezar(7) →
"Hwwsl eщх ужчсж pWovul" → Cezar(-7) wraca do oryginału. Granica między
skryptami jest przekraczana naturalnie (np. „Я"+3 = „C"; „X"+3 = „А") —
to normalna własność szyfru Cezara z poszerzonym alfabetem, decoder
wraca do oryginału przez `-N`.

Dodatkowo `polskie_znaki` w `ru/podstawy.yaml` rozszerzono na pełną listę
łacińskich diakrytyków → ASCII (`Pokémon` → `Pokemon`, `Müller` → `Muller`,
`naïve` → `naive`), żeby akcenty obcojęzyczne dla rosyjskiego z flagą
`usun_polskie_znaki: true` widziały spójną, bezdiakrytyczną łacinkę
zanim wykonają transliterację cyrylica → łacinka docelowa. Cyrylica
natywna nigdy nie jest dotykana przez `polskie_znaki` (lista zawiera tylko
wzorce łacińskie).

Ścieżki A i C nieużywane — ścieżka B okazała się minimalna (zero kodu
Pythona, jedna linia w YAML-u), a ścieżka A wymagałaby destrukcyjnej
transliteracji nazw własnych przed Cezarem.
