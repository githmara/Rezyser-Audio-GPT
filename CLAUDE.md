# ŚRODOWISKO I ARCHITEKTURA (WXPYTHON)
- Projekt jest w pełni oparty o framework wxPython (natywne GUI desktopowe), z naciskiem na maksymalną dostępność dla czytników ekranu (A11y, np. NVDA). Punkt wejścia to `main.py`.
- KOD OBIEKTOWY: Logika podzielona na klasy dziedziczące po `wx.Frame` (`main.py`) i `wx.Panel` (`gui_*.py`). Unikaj kodu proceduralnego.
- ACCESSIBILITY FIRST: Zawsze dbaj o intuicyjną nawigację z klawiatury. Używaj Sizerów i wstrzymuj się z tworzeniem własnych, niestandardowych kontrolek, jeśli systemowe spełniają zadanie.
- PLIKI METADANYCH PROJEKTÓW: Folder `runtime/skrypty/` przechowuje pliki `.mode`. Ukrywa to pliki konfiguracyjne przed zwykłymi użytkownikami końcowymi. W folderze `dictionaries` są zapisywane reguły fonetyczne i szyfrujące.
- KOMUNIKACJA Z UŻYTKOWNIKIEM (A11y): Krótkie jednorazowe powiadomienia (sukcesy, błędy) → `wx.MessageBox`. Długie komunikaty techniczne → dialog `wx.Dialog` z `wx.TextCtrl` (TE_READONLY) i przyciskiem „Zamknij". Unikaj wzorca „aktualizuj etykietę i ustaw fokus" jako głównego sposobu notyfikowania użytkownika.

# ZARZĄDZANIE TERMINALEM I TESTOWANIEM (BASH & A11y)
- Masz pełny dostęp do terminala (Git Bash) i plików. Możesz swobodnie korzystać ze składni uniksowej, ale MUSISZ przestrzegać poniższych reguł:
1. ŚRODOWISKO WIRTUALNE (BASH): Bash nie honoruje automatycznej aktywacji `.venv` przez VS Code. Zawsze używaj pełnej ścieżki uniksowej do interpretera venv: `.venv/Scripts/python -c "..."` albo `.venv/Scripts/python -m pytest ...`. Analogicznie dla menedżera pakietów: `.venv/Scripts/pip install ...`.
2. ZAKAZ BLOKOWANIA TERMINALA (KRYTYCZNE A11y): Pod żadnym pozorem nie uruchamiaj aplikacji GUI w sposób ciągły (np. z aktywnym `app.MainLoop()`). Spowoduje to całkowite zawieszenie procesu i zablokuje nawigację czytnikiem ekranu. Testuj logikę wykonując izolowane fragmenty, które kończą się natychmiast.
3. BEZPIECZNE TESTY WXPYTHON (BEZ MAINLOOP): Żeby sprawdzić interfejs bez blokowania terminala, stosuj wzorzec z obejściem pętli zdarzeń : `app = wx.App(False)`, wywołaj konstruktor, a następnie użyj `frame.Destroy()`. Omija to `MainLoop()` i okno zamyka się natychmiastowo po sprawdzeniu struktury.
4. KRYTYCZNE ZABEZPIECZENIE: Masz CAŁKOWITY ZAKAZ uruchamiania czegokolwiek z folderu `runtime/` do testowania kodu.
5. FLAGA `--no-pager` W GIT (KRYTYCZNE A11y): Komendy git, które mogą uruchomić stronicowanie (np. `git diff`, `git log`, `git show`), ZAWSZE wykonuj z flagą `--no-pager`. Brak tej flagi uruchamia tryb interaktywny, blokujący terminal i generujący artefakty niedostępne dla NVDA.
6. GIT STATUS PRZED COMMITEM: Przed każdym commitowaniem i dodawaniem plików ZAWSZE uruchom `git status`, aby zobaczyć pełny stan repozytorium.

# ZARZĄDZANIE LIMITAMI KONTEKSTU (TOKENY)
- Narzędzie może się bezgłośnie zamrozić przy próbie nadpisania zbyt wielkiego pliku.
1. PRACA ETAPOWA: Nigdy nie próbuj przepisać całego pliku w jednym kroku.
2. DELTA UPDATES: Przy niewielkich zmianach używaj precyzyjnych narzędzi edycji zamiast wypisywać plik w całości na nowo.
3. Duży refaktor dziel etapami (np. krok 1: klasa/UI, krok 2: zdarzenia, krok 3: skomplikowana logika).

# NUMER WERSJI APLIKACJI (od 13.4)
- POJEDYNCZE źródło prawdy: plik `VERSION` w roocie repozytorium (plain text, np. `13.4-WIP` lub `13.4`). Bumpa robisz **wyłącznie tam** — wszystkie inne miejsca rozwijają tę wartość automatycznie.
- W każdym `dictionaries/<kod>/gui/ui.yaml::app.wersja` siedzi templated string typu `"{numer_wersji} – Wersja Wydawnicza"`. Per-language tłumaczysz tylko natywny sufiks (Wersja Wydawnicza / Release Edition / Julkaisuversio / Útgáfuútgáfa / Versione di Rilascio / Издательская версия) — **nie dotykasz numeru** ani placeholdera.
- Mechanizm: `i18n.t()` auto-wstrzykuje kwarg `numer_wersji=` z pliku VERSION przy każdym wywołaniu, a `generuj_dokumentacje._rozwin_placeholdery` robi ten sam replace dla docs/. `build_release.odczytaj_wersje()` czyta `VERSION` plain-textem i podaje go do `iscc /DMyAppVersion=...`.
- Jeśli zobaczysz w GUI „?" zamiast numeru — brakuje pliku VERSION (przy jego braku `i18n.NUMER_WERSJI` fallbackuje na `"?"`, żeby aplikacja nie wywaliła się przy starcie).

# WIELOJĘZYCZNOŚĆ I TŁUMACZENIA INTERFEJSU
- Wersjonowanie: Projekt zaczyna wersjonowanie od 13.0 (język polski), każdy kolejny język to wydanie minor (13.1, 13.2).
- Bezpieczna kolejność wdrażania: Najpierw język bazowy z szyframi, potem tłumaczenie interfejsu (ui.yaml), skrypt autotłumaczący dokumentację, i na koniec wydanie releasu.
- Reguła natywności: Każdy język otrzymuje standardowe 6 szyfrów, a także wszystkie akcenty z wyjątkiem własnego natywnego.
- DEFINICJA KOMPLETNOŚCI JĘZYKA (aktualna do wyczerpania TODO_wielojezycznosc.md): Język jest w 100% gotowy do releasu, gdy jego folder `dictionaries/<kod>/` zawiera dokładnie:
  * `gui/ui.yaml` — tłumaczenia interfejsu
  * `rezyser/` — **4 pliki** trybów Reżysera AI
  * `szyfry/` — **6 plików** szyfrów (cezar, jakanie, odwracanie, samogloskowiec, typoglikemia, waz)
  * `akcenty/` — **11 plików**: 8 akcentów fonetycznych obcojęzycznych + 3 narzędzia czyszczenia (oczyszczenie, oczyszczenie_bez_liczb, naprawiacz_tagow)
  Weryfikacja: `ls dictionaries/<kod>/akcenty/*.yaml | wc -l` (→ 11), analogicznie dla szyfry (→ 6) i rezyser (→ 4). Dla zupełnie nowych języków (de/es/fr) stosuj bezpieczną kolejność z TODO_wielojezycznosc.md. UWAGA: Ta reguła traci aktualność po wyczerpaniu TODO_wielojezycznosc.md — wtedy należy ją usunąć z CLAUDE.md.
- Tłumaczenia interfejsu rezydują w dedykowanym pliku: `dictionaries/<kod>/gui/ui.yaml`. ZAKAZ hardkodowania etykiet GUI w kodzie źródłowym Pythona.
- Parametry dynamiczne takie jak `{nazwa_projektu}`, `{liczba_znakow}`, `{min_przesuniecie}` pozostaw w tłumaczeniach nienaruszone. Nie tłumacz literałów technicznych i rozszerzeń (np. `.md`, `skrypty/`) ani nie usuwaj emoji zachowując ich ścisłą pozycję.
- Konwencje wxPython w i18n:
 * Akceleratory (Znak `&`): Należy zachować i przesunąć na dostępną literę pasującą w danym języku.
 * Skróty klawiszowe w menu (`\tCtrl+...`): Zachowaj je w oryginale we wszystkich językach bez dokonywania lokalizacji terminów jak Shift czy Alt.
 * Długie komunikaty błędów zachowują bezwzględnie wszystkie białe znaki (`\n`), co warunkuje właściwe łamanie tekstu.
 * Rozróżniaj klucze: Tooltip i etykieta to dwa osobne klucze dla jednego obiektu.
- Skrypt autotłumaczący z użyciem modelu (`tlumacz_ai.py`) zamraża podmieniane zmienne `{...}`, aby LLM nie naruszył struktury programu.
- Manager reguł skanuje pliki YAML z folderów `akcenty`, `szyfry`, `rezyser` i nowo dodanego folderu tłumaczeń `gui`. Proces kreacji nowego języka buduje wymaganą dla tych komponentów strukturę katalogów.

# ZAMYKANIE RELEASU — DOKUMENTACJA (KRYTYCZNE)
`build_release.py` wywołuje `generuj_dokumentacje.generuj()` wewnętrznie, przez co po jego uruchomieniu w repo pojawiają się niezcommitowane zmiany w `docs/*.txt`. Żeby tego uniknąć, dokumentację należy wygenerować i zcommitować **ręcznie** przed commitem release'u, według poniższego schematu.

## Kiedy stosować
Przy każdym release commicie, jeśli w danym cyklu zmieniło się cokolwiek z listy: nowy język, nowa funkcja opisana w manualach, zmiana liczby akcentów/szyfrów/trybów, zmiana numeru wersji (VERSION).

## Procedura (w tej kolejności)

### Krok 0 — Odśwież reżysera (ZAWSZE po dodaniu/usunięciu pliku akcent*.yaml)
```bash
.venv/Scripts/python odswiez_rezysera.py
```
Skrypt skanuje `dictionaries/*/akcenty/` i aktualizuje dwa bloki generowane w kodzie:
- `core_poliglota.py` — docstringi wrapperów `akcent_*` (lista plików źródłowych per akcent)
- `core_rezyser.py` — blok importów i słownik `_AKCENT_FUNCS` (dispatch reżysera)

**Bez tego kroku samo nakładanie akcentów w Poliglocie działa** (czyta YAML bezpośrednio), ale **dynamiczne nakładanie akcentów w Reżyserze na podstawie regexów Księgi Świata — nie** (dispatch nie zna nowych plików). Sprawdź output: każdy nowy akcent/język musi pojawić się na liście wykrytych. Jeśli `core_poliglota.py` lub `core_rezyser.py` ma zmiany — zcommituj je przed przejściem do kroku 1.

### Krok 1 — Przejrzyj i zaktualizuj szablony źródłowe
Szablony to `dictionaries/<kod>/gui/dokumentacja/*.yaml` dla **każdego** języka z osobna (`pl`, `en`, `fi`, `is`, `it`, `ru`). Istniejące szablony edytuj **ręcznie w danym języku** — nie uruchamiaj autotłumacza na plikach, które już istnieją. Powody: koszt API OpenAI + podatność LLM na halucynacje (niezaszyfrowane przykłady szyfrów, bezsensowne sklejki zdań po przeklejonej informacji).

Dla każdego istniejącego szablonu sprawdź:
- Czy opis nowych funkcji (nowy język, nowa funkcja silnika) jest aktualny i przetłumaczony na język szablonu?
- Czy stare „w przyszłości pojawi się X" zostało usunięte, skoro X już działa?
- Czy liczby (`liczba_akcentow_jezykowych` itp.) są placeholderami, nie zahardkodowanymi wartościami?
- Czy usunięte / przemianowane elementy GUI nie mają już swoich akapitów?

Wzorzec edycji: najpierw zaktualizuj `pl/` (język bazowy), potem otwórz analogiczny fragment w każdym języku obcym i wprowadź tę samą zmianę treści, zachowując istniejące tłumaczenie otoczenia jako wzorzec stylu.

**Autotłumacz (`buduj_wielojezyczne_docs.py`) — TYLKO dla zupełnie nowych plików szablonów**, tzn. gdy dany `*.yaml` w danym `<kod>/gui/dokumentacja/` w ogóle nie istnieje (np. nowy język bazowy albo nowy szablon dodany do `pl/` bez odpowiednika w `en/fi/...`). Po AI-tłumaczeniu obowiązkowo przejrzyj wyniki i popraw halucynacje używając już zatwierdzonych szablonów jako wzorca.

### Krok 2 — Wygeneruj + zwaliduj
```bash
.venv/Scripts/python generuj_dokumentacje.py --waliduj
```
- `--waliduj` generuje wszystkie `docs/*.txt` i sprawdza czy żaden `{placeholder}` nie pozostał nierozwinięty (brakujący klucz w `ui.yaml`). Exit 0 = OK, Exit 1 = błąd który **blokuje build**.
- Bez flagi generuje cicho; używaj `--waliduj` zawsze przed commitem.

### Krok 3 — Przejrzyj wygenerowane pliki
```bash
git --no-pager diff docs/
git --no-pager status   # sprawdź czy nie ma nowych plików (np. docs/manual.fi.txt)
```
Zweryfikuj czy zmiany są sensowne: numer wersji zaktualizowany, lista języków poprawna, nowe rozdziały obecne, stare „w przyszłości" usunięte.

### Krok 4 — Zcommituj docs przed release commitem
```bash
git add docs/
git commit -m "docs: regeneracja po 13.X — <krótki opis zmian>"
```
Dopiero po tym robi się commit release'u (VERSION, RELEASE_NOTES, TODO).

### Uwaga o build_release.py
`build_release.py` i tak wywołuje `generuj()` wewnętrznie — to jest celowe (paczka ZIP zawsze ma świeże docs). Po pre-commicie przez Ciebie `git status` po buildzie pokaże „nothing to commit" zamiast zmienionych plików, bo wygenerowana treść będzie identyczna z tą w repo.

# SPRZĄTANIE (HIGIENA REPOZYTORIUM)
- Zawsze po skończonej weryfikacji usuwaj wszystkie pliki tymczasowe (np. pliki z logami lub testami jednostkowymi).
- Weryfikuj porządek przez komendę `git status` patrząc na nieśledzone pliki (Untracked files).
- Commity pośrednie: Możesz, a nawet powinieneś, wykonywać commity po zakończeniu poprawnie działającego małego podetapu dużej rewizji z tagiem "WIP".
- ZAWSZE zrób review (`git --no-pager diff`) zanim zapiszesz stan na stałe w repozytorium.