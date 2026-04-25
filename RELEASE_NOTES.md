# Release Notes — Reżyser Audio GPT 13.3 „Wersja Wydawnicza"

*Punkt wyjścia: V13.2 (4f1d91d) → 11 commitów (10× WIP + 1× release) → V13.3.*
*Motyw przewodni: pierwszy w pełni wdrożony obcy język (angielski) + standardyzacja silnika dla wszystkich kolejnych.*

---

## TL;DR

13.3 to release, w którym **angielski przestaje być stubem** — paczka `dictionaries/en/` zyskuje pełen pakiet 6 algorytmów szyfrów, 8 akcentów obcojęzycznych dla anglojęzycznego mówcy oraz 3 narzędzia czyszczenia/naprawiacza tagów. Każdy z 8 akcentów (islandzki/fiński/rosyjski/niemiecki/włoski/francuski/hiszpański/polski) został zaprojektowany pod natywny TTS swojego języka (Guðrún/Satu/Milena/Hedda/Lucia/Hortense/Helena/Ewa) — z konkretnymi markerami fonetycznymi, świadomymi kompromisami i komediowymi stereotypami, które rozpoznaje każdy native speaker. Silnik dostał trzy istotne usprawnienia: wielojęzyczna delegacja w pipeline'ie reżysera (`zastosuj_akcenty_uniwersalne(jezyk_projektu)`), elastyczny parser akcentów oparty o dynamiczne `slowo_akcent` z `podstawy.yaml` (zamiast hardkodowanej polskiej listy), oraz `num2words` przekazujące prawidłowy locale (koniec polskich „sto dwadzieścia trzy" w angielskim tekście). W ramach standaryzacji łatany został też subtelny bug Cezara, który przepuszczał diakrytyki spoza alfabetu paczki („Pokémon" + Cezar+3 → wcześniej „Srnéprq", teraz „Srnhprq").

---

## Co nowego dla użytkownika końcowego

### Pierwszy w pełni wdrożony obcy język: angielski

- **6 szyfrów** w `dictionaries/en/szyfry/`: Cezar (alfabet 26 liter, ±25 przesunięcia), Jąkanie (samogłoski `aeiouy`), Samogłoskowiec (Krok 3 jedyny — angielski nie ma polskich miękczeń), Typoglikemia (algorytm neutralny), Wąż (uproszczony regex `(s|z)` — `sh` zostawiony, żeby zachować naturalne brzmienie), Odwracacz tekstu z 18 wzorcami rozwijania skrótowców (e.g./i.e./etc./vs./cf./U.S./U.K./U.S.A./Dr./Mr./Mrs./Ms./Prof./St./Fig./No./pp./p.).

- **8 akcentów obcojęzycznych** w `dictionaries/en/akcenty/`. Każdy karmi natywny TTS swojego języka, który dokłada własną fonetykę:

  | Akcent | TTS | Marker'y |
  |---|---|---|
  | Islandzki | Guðrún / eSpeak is | wh→v, w→v, sh→s, ch→k, th→t, j→y |
  | Fiński | Satu / Mikko / Heidi | b/d/g→p/t/k, f/ph→v, z→s, sh→s, th→t, c→k, j→y, w→v |
  | Rosyjski | Milena / Yuri / Pavel | transliteracja EN→cyrylica + ubezdźwięcznianie końcówek (bag→бак) |
  | Niemiecki | Hedda / Stefan | v→f, w→v, th→z, j→y, Auslautverhärtung (b/d/g→p/t/k na końcu) |
  | Włoski | Lucia / Cosimo | silent H, sh→s, th→t, w→v, y\b→i, **epenteza końcowa** po klastrach rk/st/nd/kt/pt/ft (work→worka, fast→fasta) |
  | Francuski | Hortense / Paul | silent H, th→z (klasyk „zis is ze"), ch→sh, w→v |
  | Hiszpański | Helena / Pablo | sh→ch (Despacito), th→t, ph→f, z→s, \bv→b, **prosthetic E** (Spain→Espain, stop→estop) |
  | Polski | Paulina / Adam (Vocalizer Ewa/Zosia) | w/wh→ł (magic mapping), sh→sz, ch→cz, th→d, **blokada miękczeń** (szi/czi/si/ci/zi/ni→szy/czy/sy/cy/zy/ny — Ewa nie sepleni!), final-E truncation w słowach ≥4 znaków |

- **3 narzędzia uniwersalne** w `dictionaries/en/akcenty/`: Czyszczenie tekstu (z/bez normalizacji liczb) i Naprawiacz tagów (wstrzyknięcie kodu ISO). Trzy wzorce skopiowane do en/fi/is/it/ru z natywną lokalizacją etykiet — autor każdej paczki widzi już kompletny kontrakt struktury.

### Stub-paczki dostają „lokalizowane place-holdery"

- `dictionaries/{fi,is,it,ru}/akcenty/` — wcześniej puste folderze. Po 13.3 każdy zawiera 3 narzędzia czyszczenia z natywną lokalizacją („Ei mitään / Engin / Nessuno / Никакой"). Manager Reguł od razu pokazuje 3 dodatkowe pliki dla każdej paczki, autor paczki widzi pełen kontrakt struktury.
- `_jezyk_kompletny()` pozostaje rygorystyczny: paczka jest „kompletna" tylko gdy ma akcenty fonetyczne (kategoria `akcent`) **plus** szyfry. fi/is/it/ru wciąż mają stub-status do czasu dorzucenia szyfrów (planowane 13.4+). Listę „obsługiwanych języków" wciąż widnieje tylko polski + angielski.

### Łatka Cezara dla diakrytyki europejskich

- Cezar wcześniej przepuszczał znaki spoza alfabetu paczki nieszyfrowane: „Pokémon" + Cezar(3) → „Srnéprq" (é zostało nieszyfrowane). Realny bug zauważony przez native speakera. Naprawa w 13.3: pole `polskie_znaki` w `podstawy.yaml` rozszerzone o pełen zestaw europejskich diakrytyków (`é/à/ç/ñ/ö/ø/þ/ð/æ/œ/ß/...`), `_przetworz_szyfrant` normalizuje je przed wywołaniem algorytmu.
- Po naprawie: „Pokémon" → „Srnhprq", „café" → „fdih", „naïve" → „qdlyh", „façade" → „idfdgh", „Schrödinger" → „Vfkurglqjhu" — każda litera szyfrowana spójnie.
- Każda paczka deklaruje *swoje* znaki natywne (np. fi zachowuje `Å/Ä/Ö` jako natywne, is zachowuje `Á/É/Í/Ó/Ú/Ý/Þ/Æ/Ö/Ð`) — silnik to honoruje. Akcenty z flagą `usun_polskie_znaki: true` automatycznie korzystają z tej samej listy, więc „Łódź" + akcent_polski(en) → „Lodz" przed nałożeniem reguł fonetycznych.

---

## Pod maską

### Wielojęzyczna delegacja w pipeline'ie reżysera

- `core_poliglota.akcent_<id>(tekst, jezyk: str = "pl")` — wszystkie wrappery generowane przez `odswiez_rezysera.py` przyjmują teraz opcjonalny argument języka. Default `"pl"` zachowuje pełną wsteczną kompatybilność dla zewnętrznych importów. Ten sam wrapper `akcent_islandzki()` daje 100% inny wynik dla `pl` vs `en` — bo silnik ładuje inne reguły YAML w zależności od argumentu.
- `core_rezyser.zastosuj_akcenty_uniwersalne(tekst, lore_text, jezyk_projektu="pl")` — nowy 3-ci argument przepuszczany do dispatchera `_AKCENT_FUNCS[nazwa](fragment, jezyk_projektu)`. Wywołujący w `rezyser_ai.py` na razie używa default `"pl"` — pełne wykorzystanie czeka na pole „język projektu" w stanie reżysera (planowane razem z multi-language Księgą Świata).
- `odswiez_rezysera.OBSLUGIWANE_JEZYKI = ("pl",)` zastąpione funkcją `odkryj_obslugiwane_jezyki()` skanującą `dictionaries/`. Generator zbiera unię id-ów akcentów po wszystkich folderach z deduplikacją — dodanie `dictionaries/en/akcenty/` nie wymagało zmiany kodu Pythona, tylko ponownego uruchomienia odświerzacza.

### Elastyczny parser akcentów (regex + `slowo_akcent`)

- `core_rezyser.zastosuj_akcenty_uniwersalne` parsował Księgę Świata regexem `r"akcent\s+([a-zńśźżćłó]+)..."` — twardy hardkod polskiego słowa „akcent" plus polskiego alfabetu. Po 13.3 regex budowany dynamicznie z `slowa_akcentu(jezyk_projektu)` — listy słów-wyzwalaczy z `podstawy.yaml`:
  - PL: `["akcent"]`
  - EN: `["accent", "accented"]`
  - FI: `["aksentti", "korostus"]`
  - IS: `["hreimur", "áhersla"]`
  - IT: `["accento", "accentato"]`
  - RU: `["акцент", "акцентом", "говор"]`
- Alfabet `[a-zńśźżćłó]+` przeniesiony na `\w+` z flagą `re.UNICODE` — skandynawskie/niemieckie/francuskie/cyrylica nie blokują parsowania. Reguły lore-ad-hoc (`'w' na 'v'`) też używają `\w` (łącznik „na" wciąż polski; wielojęzyczne łączniki to TODO 13.x+).

### `num2words` z prawidłowym locale w pipeline'ie

- `core_poliglota.normalizuj_liczby` miało `lang="pl"` na sztywno. Konsekwencja: angielski tekst „I have 123 apples" po normalizacji stawał się „I have sto dwadzieścia trzy apples" — polskie słowa wstrzykiwane w angielski skrypt, czytane przez TTS docelowy jako bełkot. Bug istniał od początku obsługi wielojęzyczności, ale dopóki `en/akcenty/` nie istniało, nikt go nie odpalał na innym języku niż pl.
- Naprawa: parametr `jezyk` propagowany przez 5 funkcji łańcucha (`normalizuj_liczby` → `oczysc_tekst_tts` → `_aplikuj_akcent_z_yaml` → `_przetworz_rezyser` / `_przetworz_szyfrant` → `zastosuj_reguly_fonetyczne`). Default `"pl"` wszędzie zachowuje pełną wsteczną kompatybilność.
- Smoke test 9 języków (pl/en/fi/is/it/ru/de/fr/es): „123" → poprawnie zlokalizowane słowa w każdym (`one hundred and twenty-three / satakaksikymmentäkolme / eitt hundrað tuttugu og þrír / centoventitre / сто двадцать три / einhundertdreiundzwanzig / cent vingt-trois / ciento veintitrés`).

### Refaktor `_przetworz_szyfrant` dla normalizacji diakrytyki

- Cezar i pozostałe szyfry wcześniej operowały bezpośrednio na tekście wejściowym — diakrytyki spoza alfabetu paczki przepuszczane. W 13.3 `_przetworz_szyfrant` wywołuje `_usun_polskie_znaki(tekst, podstawy)` przed `oczysc_tekst_tts` i przed wybranym algorytmem. Każdy szyfr (cezar/jakanie/odwracanie/samogloskowiec/typoglikemia/waz) automatycznie zyskuje normalizację.
- Akcenty z flagą `usun_polskie_znaki: true` korzystają z tej samej listy w `podstawy.yaml` — autor paczki definiuje normalizację JEDEN raz, silnik honoruje konsekwentnie w każdym pipelinie.
- `dictionaries/en/akcenty/*.yaml` — flaga `usun_polskie_znaki: false → true` zmieniona w 8 plikach (wcześniej argumentowałem „English source has nothing to transliterate" — niesłuszne, bo angielski tekst często zawiera loanwords z diakrytyką: „résumé", „Pokémon", „café").

### Pakiet czyszczenia uniwersalny w 5 paczkach

- 15 nowych plików: 3 wzorce (oczyszczenie, oczyszczenie_bez_liczb, naprawiacz_tagow) skopiowane do każdej paczki językowej z lokalizacją etykiet i opisów na język natywny. Wartości techniczne identyczne z PL — algorytmy czyszczenia są językowo neutralne, tylko etykiety wymagały lokalizacji.
- Korzyść: gdy w przyszłości któraś z paczek dostanie własne szyfry (13.4+), tryby Czyszczenia/Naprawiacza już TAM SĄ z poprawną lokalizacją. Manager Reguł od razu pokazuje 3 dodatkowe pliki dla każdej paczki — autor paczki widzi pełen kontrakt struktury.
- Maska kompletności pozostaje nienaruszona: `_jezyk_kompletny` wymaga akcenty/ z **kategorią `akcent`** plus szyfry/. Czyszczenia (`kategoria: oczyszczenie`) i naprawiacz (`kategoria: naprawiacz`) nie liczą się do testu kompletności — fi/is/it/ru wciąż stuby do czasu dorzucenia akcentów fonetycznych i szyfrów.

---

## Strategia wdrażania (jeden język na release)

### Co znaczy „13.3 = pierwszy w pełni nowy język"?

Pierwotny plan w `TODO_wielojezycznosc.md` zakładał: *13.2 = pierwszy w pełni nowy język*. Audyt po 13.1 ujawnił trzy luki silnika, które 13.2 musiało zamknąć (polski hardkod w `gui_rezyser`, modułowa stała `JEZYK_BAZOWY` w `gui_poliglota`, polski prompt systemowy w `tlumacz_ai`). Pełna paczka angielska przesunęła się na **13.3**, wraz z dwiema dodatkowymi łatkami silnika ujawnionymi po drodze: dynamiczny skan w `odswiez_rezysera` i dynamiczne `slowo_akcent` w `podstawy.yaml`.

13.3 wykonało więc **podwójny krok**: pełna paczka angielska *plus* fundamenty pod każdą kolejną paczkę. Każdy następny język (fi/is/it/ru/de/es/...) nie wymaga już zmian w kodzie Pythona — wystarczy dorzucić foldery i pliki YAML.

### Co przyniesie 13.4 i dalej

Każdy minor 13.x dorzuca **jeden** w pełni wdrożony język (od 13.4 wzwyż). Oczekiwane następne paczki:

- **fiński (`fi`)** — najbliższy kandydat (klasyczne komediowe markery, fanostwo skandynawskie wśród autorów audiobooków),
- **rosyjski (`ru`)** — wymaga rozwiązania kwestii podwójnego skryptu (sekcja 7.5 TODO),
- **islandzki (`is`)** — nisza, ale fundamenty już są (paczka stub),
- **włoski (`it`)** — popularny dla rolnych RPG słuchowiskowych.

Strategia per paczka: kopia `pl/szyfry/` z lokalizacją regexów skrótowców (TODO § 3.1), kopia akcentów obcojęzycznych z mapowaniami pod natywną fonetykę (8 akcentów minus akcent natywny tego języka), smoke test sekcji 6.x TODO. Gdy plik `TODO_wielojezycznosc.md` zostanie wyczerpany, następny release to **14.0**.

### Co działa „samoczynnie" od 13.3 (en z pełnym pakietem)

Bez edycji jednej linii Pythona — siatka jest gotowa:

- `dostepne_jezyki_bazowe()` zwraca `["en", "pl"]`.
- Menu „Język interfejsu" pokazuje 2 radio-items (Polski, English).
- `wykryj_jezyk_zrodlowy()` zwraca `"en"` dla angielskiego pliku → Poliglota auto-przełącza pipeline.
- Reżyser dla użytkownika z UI=EN ładuje już pełne `en/rezyser/` (zamiast fallbacku z 13.2) — bo same pliki YAML w `dictionaries/en/rezyser/` są kompletne (od 13.2).
- Manager Reguł domyślnie pokazuje tylko `en/` w drzewie, dropdown „Wszystkie języki" pozostaje dostępny dla autorów paczek.

---

## Breaking changes / migracja

- **Sygnatura `core_rezyser.zastosuj_akcenty_uniwersalne` rozszerzona.** Trzeci argument `jezyk_projektu="pl"` z domyślną wartością. Stare wywołania 2-arg wciąż działają. Nowi wywołujący przekazują kod języka projektu.
- **`core_poliglota.normalizuj_liczby` rozszerzona.** Drugi argument `jezyk="pl"` z domyślną wartością. Stare wywołania 1-arg zachowują polski locale.
- **`odswiez_rezysera.OBSLUGIWANE_JEZYKI` usunięta.** Zastąpiona funkcją `odkryj_obslugiwane_jezyki()`. Zewnętrzne skrypty importujące tę krotkę przestaną działać — była jednak detalem implementacji generatora, nikt z zewnątrz nie powinien o niej wiedzieć.
- **Pole `polskie_znaki` w `dictionaries/<jezyk>/podstawy.yaml` rozszerzone w 5 paczkach.** EN/FI/IS/IT teraz zawierają pełen zestaw europejskich diakrytyków → ASCII. Paczki user-tworzonych języków, które dziedziczyły pusty `polskie_znaki: []`, nadal działają — pełen zestaw nie jest wymagany, tylko zalecany.
- **Numer wersji w obu `ui.yaml` bumpniętym na `13.3`.** Tytuł okna, paczki releasu, dokumentacja czytają stąd — efekt automatyczny.

---

*Notes wygenerowane na podstawie 10 commitów WIP od `V13.2` do `af17e4e` + commit zamykający. Pełna lista: `git log V13.2..HEAD --oneline`.*
