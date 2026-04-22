# TODO: Wielojęzyczne skrótowce (notatka robocza)

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
| rosyjski    | `ru`    | notebook                             |
| angielski   | `en`    | notebook                             |
| włoski      | `it`    | notebook                             |
| fiński      | `fi`    | notebook                             |
| islandzki   | `is`    | notebook                             |

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

- [ ] **Rosyjski (`ru`)** – z notebooka:
  - [ ] `т.е.` → `то есть`
  - [ ] `т.д.` → `так далее`
  - [ ] `т.п.` → `тому подобное`
  - [ ] `т.к.` → `так как`
  - [ ] `т.н.` → `так называемый`
  - [ ] `и.о.` → `исполняющий обязанности`
  - [ ] `с.г.` → `сего года`
  - [ ] `н.э.` → `нашей эры`
  - [ ] `в.т.ч.` → `в том числе`
  - [ ] `и т.д.` / `и т.п.` → `и так далее` / `и тому подобное`
  - [ ] `проф.` → `профессор`
  - [ ] `акад.` → `академик`
  - [ ] `доц.` → `доцент`
  - [ ] `ул.` → `улица`
  - [ ] `пр.` → `проспект`
  - [ ] `пер.` → `переулок`

- [ ] **Angielski (`en`)** – z notebooka:
  - [ ] `e.g.` / `e. g.` / `e.g,` → `for example`
  - [ ] `i.e.` / `i. e.` / `i.e,` → `that is`
  - [ ] `U.S.` / `U. S.` → `United States`
  - [ ] `U.K.` / `U. K.` → `United Kingdom`
  - [ ] `etc.` / `etc .` → `et cetera`
  - [ ] `vs.` → `versus`
  - [ ] `Dr.` → `Doctor`
  - [ ] `Mr.` → `Mister`
  - [ ] `Mrs.` → `Missus`
  - [ ] `Prof.` → `Professor`
  - [ ] `St.` → `Saint` lub `Street` (wybrać jeden wariant; kontekstu tu nie ma)
  - [ ] `Fig.` → `Figure`
  - [ ] `No.` → `Number`
  - [ ] `p.` / `pp.` → `page` / `pages`

- [ ] **Włoski (`it`)** – z notebooka:
  - [ ] `ad es.` → `ad esempio`
  - [ ] `ecc.` → `eccetera`
  - [ ] `dott.` → `dottore`
  - [ ] `prof.` → `professore`
  - [ ] `pag.` / `pagg.` → `pagina` / `pagine`
  - [ ] `sig.` → `signore`
  - [ ] `sig.ra` → `signora`
  - [ ] `art.` → `articolo`
  - [ ] `cap.` → `capitolo`
  - [ ] `n.` / `n.ro` → `numero`
  - [ ] `cfr.` → `confronta`
  - [ ] `vol.` → `volume`

- [ ] **Fiński (`fi`)** – z notebooka:
  - [ ] `esim.` → `esimerkiksi`
  - [ ] `jne.` → `ja niin edelleen`
  - [ ] `ym.` → `ynnä muuta`
  - [ ] `ns.` → `niin sanottu`
  - [ ] `tms.` → `tai muuta sellaista`
  - [ ] `ko.` → `kyseinen`
  - [ ] `po.` → `pitää olla` (lub kontekst. `pohjoiseen`)
  - [ ] `vt.` → `virkaa tekevä`
  - [ ] `prof.` → `professori`
  - [ ] `dr.` → `tohtori`
  - [ ] `os.` → `osasto`
  - [ ] `v.` → `vuosi` (lub `versus`)

- [ ] **Islandzki (`is`)** – z notebooka:
  - [ ] `t.d.` → `til dæmis`
  - [ ] `þ.e.` → `það er`
  - [ ] `m.a.` → `meðal annars`
  - [ ] `u.þ.b.` → `um það bil`
  - [ ] `o.s.frv.` → `og svo framvegis`
  - [ ] `dr.` → `doktor`
  - [ ] `prof.` → `prófessor`
  - [ ] `bls.` → `blaðsíða`
  - [ ] `skv.` → `samkvæmt`
  - [ ] `fh.` → `fyrir hönd`

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

## 4. Strategia wdrażania

1. **Jeden język na raz.** Wrzucenie kilkunastu YAML-i w jednym commicie
   utrudnia przegląd i testowanie. Lepiej dokładać pojedynczo (najlepiej
   z krótkim smoke testem przed merge do `main`).

2. **Pełna struktura folderu języka:**
   ```
   dictionaries/<kod>/
   ├── podstawy.yaml           # alfabet + (ew.) transliteracja diakrytyków
   ├── akcenty/                # placeholder, może być pusty
   └── szyfry/
       └── odwracanie.yaml     # <- tutaj żyją rozwinięcia
   ```
   Bez `podstawy.yaml` silnik nie wykryje języka.

3. **Szybki sprawdzian w GUI.** Po dodaniu języka `python main.py`,
   Poliglota → Tryb Szyfranta → wybór nowego języka bazowego.
   Ma się pojawić Odwracacz, rozwinięcia mają zadziałać, kod ISO
   w pliku wynikowym ma być poprawny.

## 5. Powiązane artefakty

* `dictionaries/pl/szyfry/odwracanie.yaml` – wzorzec (rozwinięcia,
  nie normalizacja).
* `core_poliglota.py::_algo_odwracanie` – silnik, który czyta
  `rozwiniecia` i aplikuje je przez `re.sub(..., flags=re.IGNORECASE)`.
* `core_poliglota.py::dostepne_jezyki_bazowe` – autodetekcja nowych
  folderów `dictionaries/<kod>/`.
