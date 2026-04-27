# Release Notes — Reżyser Audio GPT 13.4.1 „Wersja Wydawnicza"

*System auto-aktualizacji przez GitHub Releases. Wielojęzyczny instalator.*

---

## 13.4.1 — patch release (motyw przewodni: auto-aktualizacja)

*Punkt wyjścia: V13.4 (432179b) → commity WIP + commit release → V13.4.1.*

### TL;DR

13.4.1 wprowadza **system auto-aktualizacji oparty o GitHub Releases API**. Przy każdym starcie aplikacja odpytuje GitHub w wątku tła — jeśli dostępna jest nowsza wersja, zachowanie zależy od środowiska: użytkownik Windows z paczką instalatora dostaje `wx.ProgressDialog` z pobieraniem `.exe` i automatycznym zamknięciem aplikacji przed instalacją; deweloper lub użytkownik macOS/Linux widzi `wx.MessageBox` z bezpośrednim linkiem do strony wydania. Obsługa jest w pełni dostępna dla czytników ekranu (A11y: wszystkie dialogi natywne wxPython, `wx.CallAfter` do wątku GUI). Instalator Inno Setup dostał sekcję `[Languages]` dla wszystkich 6 obsługiwanych języków.

---

## Co nowego dla użytkownika końcowego

### Automatyczne aktualizacje

- Przy starcie aplikacja sprawdza w tle (wątek daemon, brak blokowania MainLoop), czy na GitHubie jest dostępna nowsza wersja.
- **Użytkownicy Windows z instalatorem** (plik `runtime/python.exe` obecny): `wx.MessageBox` TAK/NIE → `wx.ProgressDialog` z pobieraniem → `subprocess.Popen` instalatora → `ExitMainLoop()`. Projekty i klucz API nienaruszone.
- **Deweloperzy i użytkownicy macOS/Linux** (brak `runtime/python.exe`): `wx.MessageBox` z informacją o nowej wersji i bezpośrednim linkiem do strony wydania na GitHubie (archiwum „Source code" lub `git pull`).
- Wszystkie dialogi natywne wxPython — NVDA odczytuje tytuł, treść i pasek postępu bez dodatkowej konfiguracji.

### Wielojęzyczny instalator

- `installer.iss` dostał sekcję `[Languages]` obejmującą wszystkie 6 obsługiwanych języków (`english`, `polish`, `italian`, `russian`, `finnish`, `icelandic`). Inno Setup automatycznie dobiera język instalatora do systemu użytkownika.
- Etykiety w sekcji `[Tasks]` (skrót na pulpicie) zamienione na wbudowane stałe Inno Setup (`{cm:CreateDesktopIcon}`, `{cm:AdditionalIcons}`), które lokalizują się automatycznie.

---

## Pod maską

### core_updater.py — izolowany moduł sieciowy

- Nowy moduł `core_updater.py` (bez zależności od wxPython) odpytuje `https://api.github.com/repos/githmara/Rezyser-Audio-GPT/releases/latest`.
- `_normalizuj_wersje()` — konwersja `"v13.4.1"` / `"13.5-WIP"` na krotkę `(13, 4, 1)` / `(13, 5, 0)` do porównania.
- `sprawdz_aktualizacje(token=None)` — łapie wszystkie wyjątki sieciowe, zwraca `None` zamiast rzucać; opcjonalny `GITHUB_TOKEN` dla prywatnych repozytoriów.
- `pobierz_instalator(info, callback)` — pobiera asset `.exe` do `%TEMP%` chunkami 64 KB; `callback(pobrane, total)` wywoływany po każdym chunku (użyj `wx.CallAfter` w GUI).

### Integracja z main.py (A11y)

- `_start_update_check()` startuje wątek daemon natychmiast po `self.Show()` — okno jest już widoczne dla NVDA zanim sprawdzenie wróci.
- `_on_postep_pobierania()` — `dlg.Update(min(procent, 99))` zamiast 100, żeby `wx.PD_AUTO_HIDE` nie ukrył dialogu przed jawnym `Destroy()`.
- Rozgałęzienie środowisko: `os.path.isfile("runtime/python.exe")` — ten sam plik sprawdza `build_release.py` przy budowaniu paczki.

### Tłumaczenia UI i dokumentacja

- Sekcja `updater:` w `dictionaries/*/gui/ui.yaml` × 6 języków (9 kluczy: `nowa_wersja_tytul`, `nowa_wersja_tresc`, `pobieranie_tytul`, `pobieranie_tresc`, `instalacja_tytul`, `instalacja_tresc`, `blad_pobierania_tytul`, `blad_pobierania_tresc`, `blad_uruchomienia_tytul`, `blad_uruchomienia_tresc`, `dev_info_tresc`).
- Sekcja „Automatyczne aktualizacje" dodana do `dictionaries/*/gui/dokumentacja/manual.yaml` × 6 języków — między KROK 1 a KROK 2.

### build_release.py

- Usunięto `input("Also build the .exe installer? (y/n)")` — instalator jest zawsze budowany, bo GitHub Releases auto-updater go wymaga.

---

## Breaking changes / migracja

Brak — zmiana w pełni addytywna.

---

## 13.4 — pełen release (motyw przewodni: fiński — kompletna paczka językowa)

*Punkt wyjścia: V13.3.1 (fc82669) → 9 commitów WIP + 1 commit release → V13.4.*

### TL;DR

13.4 zamyka paczkę `dictionaries/fi/` jako **drugi w pełni wdrożony obcy język** — fiński dołącza do angielskiego z kompletem 8 akcentów fonetycznych (obcojęzyczne TTS czytające fiński tekst z charakterystycznym akcentem), 6 szyfrów, trybów Reżysera AI i przetłumaczonego GUI. Szczególnie wyraziste są dwa nowe akcenty: **saksalainen** (*Hedda* gardle-rolls każde `r` i sybiluje `s→z`, fiński `y` zamieniony na `ü` dla poprawnego /y/) i **venäläinen** (pełna transliteracja FI→cyrylica: `y→ю`, `ä→э`, `ö→ё` — rosyjski TTS brzmi jak Rosjanin mówiący po fińsku). Infrastruktura dostała **single source of truth dla numeru wersji** (plik `VERSION` w rocie, koniec sześciu-plikowych bumpów), **zgodę A11Y na zmianę języka pipeline'u** (MessageBox YES/NO zamiast cichego przełączania) oraz **wieloszablonowy autotłumacz dokumentacji** z dynamicznymi placeholderami i custom system-promptem.

---

## Co nowego dla użytkownika końcowego

### Drugi w pełni wdrożony obcy język: fiński

- **8 akcentów obcojęzycznych** w `dictionaries/fi/akcenty/`. Każdy przerabia fiński tekst pod natywny TTS swojego języka:

  | Akcent | TTS | Kluczowe markery |
  |---|---|---|
  | Angielski | David / Zira | j→y (en-j = /dʒ/), ä→a, ö→e |
  | Polski | Paulina / Ewa | j→y (de-kompatybilny), ä→a, ö→e |
  | Islandzki | Guðrún / eSpeak is | y→u, ä→e (ö zostaje — is TTS ma /ø/) |
  | Francuski | Hortense / Paul | y→u (fr u=/y/ — idealnie!), j→y, ö→eu |
  | Hiszpański | Helena / Pablo | y→u, j→y, ä→a, ö→o |
  | Włoski | Lucia / Cosimo | j→y, ä→e, ö→e (h milknie automatycznie) |
  | **Saksalainen** | **Hedda / Stefan** | **y→ü (krytyczne), v→w (krytyczne)** |
  | **Venäläinen** | **Milena / Yuri** | **pełna FI→cyrylica: y→ю, ä→э, ö→ё** |

- **Akcent saksalainen** — dwie reguły, reszta dzieje się sama: TTS DE gardle-rolls każde `r` do /ʁ/, przed samogłoskami czyta `s` jako /z/ (`sana`→`zana`). `ä` i `ö` obsługuje natywnie (Niemcy mają te litery). Jedyne korekty: `y→ü` (niem. TTS bez tego czyta /j/) i `v→w` (niem. `v`=/f/, `w`=/v/).

- **Akcent venäläinen** — pełna transliteracja fińskiej łacinki na cyrylicę, z czterema fińskimi wyzwaniami: `y→ю` (/y/ → /ju/, silny efekt akcentu!), `ä→э` (twarde e, bez palatalizacji konsonantów), `ö→ё` (palatalizacja = przybliżenie frontowej /ø/), `e→э` zamiast `е` (fiński `e` nie palatalizuje — to ważna różnica od polskiego). Jotyzacja: `ja→я`, `je→е`, `jo→ё`, `ju→ю`; pozostałe `j→й`, potem vokal mapowany osobno.

- **6 szyfrów** w `dictionaries/fi/szyfry/`: Cezar (alfabet fi + ä/ö/å), Jąkanie (vokale fińskie), Samogłoskowiec, Typoglikemia, Wąż, Odwracacz tekstu (14 wzorców skrótowców: jne./ns./ko./prof./dr./em./ao./yo./puh./vs./jms./v.+liczba/s.+liczba/n.=noin).

- **Tryby Reżysera AI** dla fińskiego — pełne tłumaczenia trybów na język fiński.

- `n. kaksi vuotta` → `noin kaksi vuotta` — brakująca reguła w `fi/szyfry/odwracanie.yaml` dodana w tym releasie (smoke test 6.5 pełny).

### Zgoda A11Y na przełączenie języka pipeline'u

- Poliglota startuje teraz z języka interfejsu (gdy paczka ma pełny zestaw reguł), zamiast hardkodowanego `pl`. Użytkownik z UI=FI nie zobaczy polskich etykiet akcentów przy pierwszym wejściu do panelu.
- Po wczytaniu obcojęzycznego pliku pojawia się `wx.MessageBox YES_NO` (NVDA odczyta zmianę) z pytaniem o przełączenie pipeline'u — zamiast cichego działania w tle.

---

## Pod maską

### Single source of truth dla numeru wersji

- **Przed 13.4:** bump wersji wymagał edycji 6 plików `dictionaries/<kod>/gui/ui.yaml`. W 13.3.1 hotfixował błąd, gdy fi/is/it/ru tkwiło na 13.1 dwa wydania.
- **Od 13.4:** jeden plik `VERSION` w rocie repozytorium (plain text, np. `13.4`). Wszystkie `ui.yaml` używają templated string `"{numer_wersji} – <natywny sufiks>"`. `i18n.py` wstrzykuje `numer_wersji=` automatycznie przy każdym `t()`; `build_release.odczytaj_wersje()` czyta `VERSION` bezpośrednio.
- Efekt: następny bump = zmiana jednej linii w jednym pliku.

### Wieloszablonowy autotłumacz dokumentacji

- `buduj_wielojezyczne_docs.py` iteruje teraz po **wszystkich** `*.yaml` w `dictionaries/pl/gui/dokumentacja/` (manual + dictionaries + przyszłe szablony) zamiast jednego pliku. Flaga `--szablony` pozwala przetłumaczyć tylko wybrany podzbiór bez ponownego API-billu.
- Dynamiczne placeholdery w `dictionaries.yaml`: liczby akcentów/szyfrów/trybów i lista kompletnych języków obliczane ze stanu dysku (`_zbuduj_placeholdery_globalne()`). Dodanie nowej paczki językowej automatycznie aktualizuje dokumentację we wszystkich językach.
- Custom system-prompt autotłumacza: trzy kluczowe instrukcje eliminujące typowe błędy LLM (1. nie pisać „w przyszłości"; 2. podmienić akcent natywny na pl; 3. zlokalizować przykłady szyfrów pod fonetykę docelową).

### Batchowe tłumaczenia `dictionaries.yaml`

- Pliki `dictionaries/<kod>/gui/dokumentacja/dictionaries.yaml` (opis słowników widoczny w panelu pomocy) przetłumaczone na en/fi/is/it/ru z ręcznymi fixami po review. Użytkownik fińskojęzyczny widzi opisy szyfrów i akcentów po fińsku.

---

## Breaking changes / migracja

- **`VERSION`** — plik w rocie jest nowym single source of truth. Skrypty zewnętrzne odczytujące numer wersji z `ui.yaml` należy przepiąć na `VERSION`.
- **`build_release.odczytaj_wersje_z_ui_yaml()`** usunięta, zastąpiona przez `odczytaj_wersje()`. Sygnatura i typ zwracany bez zmian.
- **`i18n.NUMER_WERSJI`** — nowa publiczna stała (string), dostępna po `import i18n`. Fallback do `"?"` gdy `VERSION` brak (aplikacja nie wywala się przy starcie).

---

*Notes wygenerowane na podstawie 8 commitów WIP od `V13.3.1` do `2e57fd3` + commit zamykający. Pełna lista: `git log V13.3.1..HEAD --oneline`.*

---

# Release Notes — Reżyser Audio GPT 13.3.1 „Wersja Wydawnicza"

*Hotfix dla 13.3 — uzupełnienie brakujących tłumaczeń wielojęzycznych w głównym GUI.*

---

## 13.3.1 — hotfix tłumaczeń (patch)

W 13.3 paczki `dictionaries/{en,fi,is,it,ru}/gui/ui.yaml` nie zawierały czterech kluczy używanych przez `main.py`:

- `main.menu.jezyk_interfejsu` — pozycja menu „Język interfejsu" w menubarze (Alt)
- `main.menu_status.jezyk_interfejsu` — opis tej pozycji w pasku stanu
- `main.dialog.zmiana_jezyka_tytul` + `main.dialog.zmiana_jezyka_tresc` — tytuł i treść MessageBoxa o konieczności restartu (z parametrem `{nazwa_jezyka}`)

Fallback z `i18n.t()` automatycznie podstawiał polskie wartości, więc każdy nie-polski użytkownik widział w pasku menu polską pozycję obok przetłumaczonego „File"/„Tools" oraz polski tekst dialogu po wyborze nowego języka. Po stronie kodu Pythona (`main.py::_build_menu`, `main.py::_on_zmien_jezyk`) wszystko było już od początku obsłużone przez `t(...)` — buga było wyłącznie w słownikach.

Przy okazji zsynchronizowane zostało pole `app.wersja` w paczkach `fi/is/it/ru`, które tkwiło na „13.1" od dwóch wydań — teraz wszystkie sześć paczek zgodnie raportuje „13.3.1" w pasku tytułu.

Brak zmian w kodzie Pythona, brak zmian w kontrakcie API, brak migracji danych. Patch bezpieczny do natychmiastowego wdrożenia.

---

## 13.3 — pełen release (motyw przewodni: pierwszy w pełni wdrożony obcy język)

*Punkt wyjścia: V13.2 (4f1d91d) → 11 commitów (10× WIP + 1× release) → V13.3.*

### TL;DR

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
