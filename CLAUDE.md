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
7. KLUCZ OPENAI DOSTĘPNY: `golden_key.env` w roocie repo jest gitignorowany, ale fizycznie obecny u dewelopera. Skrypty `buduj_wielojezyczne_ui.py`, `buduj_wielojezyczne_docs.py`, `tlumacz_ai.py` ładują klucz przez `python-dotenv` → `os.environ["OPENAI_API_KEY"]`. Agent **może i powinien** odpalać te skrypty bezpośrednio — nie przekazuj tego kroku użytkownikowi „bo nie masz API". Stop tylko gdy skrypt zwróci „❌ Brak prawidłowego OPENAI_API_KEY" lub HTTP 401/429 (rate limit / brak kredytów) — wtedy poproś usera o uzupełnienie. Po auto-tłumaczeniach ZAWSZE manualny review halucynacji (LLM wymyśla niezaszyfrowane przykłady szyfrów lub bezsensowne sklejki — porównuj z zatwierdzonymi szablonami w innym języku jako wzorcem stylu).
8. KOPIOWANIE Z TERMINALA NIE JEST WIARYGODNE (KRYTYCZNE A11y). Accessibility buffer VS Code tokenizuje treść tnąc ją na fragmenty i powtarzając ciągi znaków — dotyczy nawet krótkich HEREDOC commit messages. Reguły:
   - **Długie treści (commit messages, release notes, drafty odpowiedzi, diakrytyczne fragmenty) ZAPISUJ DO PLIKU** i poproś użytkownika żeby otworzył plik w edytorze VS Code (Ctrl+P → nazwa pliku). Edytor ma natywne A11y, panel Terminal nie. Wzorce nazw: `pending_answer.md` (drafty odpowiedzi na issue), `release.txt` (Release description), `commit_msg.txt` (commit message do wklejenia).
   - **NIE proś o skopiowanie tekstu z output'u terminala** — nawet jeśli wygląda krótko. Zawsze pisz do pliku i wskazuj ścieżkę.
   - **CAŁKOWITY ZAKAZ AskUserQuestion i wszelkich interaktywnych menu wyboru w CLI** (potwierdzone 2026-05-18): psuje accessibility buffer VS Code+NVDA, miesza opcje, tokenizuje treść. Pytania zadawaj WYŁĄCZNIE otwartym tekstem — bullet lista propozycji w wiadomości jest OK, użytkownik odpowie tekstem. Jeśli musisz zadać kilka pytań naraz, wylistuj wszystkie w jednej wiadomości z propozycjami i krótkimi opisami konsekwencji, a przy braku krytycznej odpowiedzi przypomnij i poproś ponownie przed kontynuacją.

# ZARZĄDZANIE LIMITAMI KONTEKSTU (TOKENY)
- Narzędzie może się bezgłośnie zamrozić przy próbie nadpisania zbyt wielkiego pliku.
1. PRACA ETAPOWA: Nigdy nie próbuj przepisać całego pliku w jednym kroku.
2. DELTA UPDATES: Przy niewielkich zmianach używaj precyzyjnych narzędzi edycji zamiast wypisywać plik w całości na nowo.
3. Duży refaktor dziel etapami (np. krok 1: klasa/UI, krok 2: zdarzenia, krok 3: skomplikowana logika).

**AUTOKONTROLA ROZMIARU CLAUDE.MD (KRYTYCZNE)**
Agent MUSI proaktywnie monitorować rozmiar tego pliku przed każdą jego modyfikacją. Jeśli rozmiar pliku zbliży się do progu 35-40 tysięcy znaków, natychmiast uruchom procedurę CLEANUP przed kontynuowaniem jakichkolwiek innych zadań:
1. **Zidentyfikuj historię:** Znajdź sekcje zawierające zamknięte historie wdrożeń, rozwiązane problemy z poprzednich wersji (np. obszerne logi z v15.2.7) i przestarzałe obejścia.
2. **Zarchiwizuj:** Przenieś te historyczne dane do osobnego pliku `claude_archive.md`.
3. **Odchudź główny plik:** W `CLAUDE.md` pozostaw tylko absolutnie krytyczne reguły A11y, wytyczne architektury wxPython, zasady terminala, procedurę release i krótką informację: "Zarchiwizowane procedury znajdują się w `claude_archive.md`".
4. **Zgłoś do weryfikacji:** Po wykonaniu archiwizacji zapisz raport z tego, co zostało przeniesione, do pliku `cleanup_report.md` i poproś użytkownika o zatwierdzenie zmian w architekturze pamięci, zanim wrócisz do kodowania.

# NUMER WERSJI APLIKACJI (od 13.4)
- POJEDYNCZE źródło prawdy: plik `VERSION` w roocie repozytorium (plain text, np. `13.4-WIP` lub `13.4`). Bumpa robisz **wyłącznie tam** — wszystkie inne miejsca rozwijają tę wartość automatycznie.
- W każdym `dictionaries/<kod>/gui/ui.yaml::app.wersja` siedzi templated string typu `"{numer_wersji} – Wersja Wydawnicza"`. Per-language tłumaczysz tylko natywny sufiks (Wersja Wydawnicza / Release Edition / Julkaisuversio / Útgáfuútgáfa / Versione di Rilascio / Издательская версия) — **nie dotykasz numeru** ani placeholdera.
- Mechanizm: `i18n.t()` auto-wstrzykuje kwarg `numer_wersji=` z pliku VERSION przy każdym wywołaniu, a `generuj_dokumentacje._rozwin_placeholdery` robi ten sam replace dla docs/. `build_release.odczytaj_wersje()` czyta `VERSION` plain-textem i podaje go do `iscc /DMyAppVersion=...`.
- Jeśli zobaczysz w GUI „?" zamiast numeru — brakuje pliku VERSION (przy jego braku `i18n.NUMER_WERSJI` fallbackuje na `"?"`, żeby aplikacja nie wywaliła się przy starcie).

# WIELOJĘZYCZNOŚĆ I TŁUMACZENIA INTERFEJSU
- Stan post-14.0: 9 w pełni wdrożonych paczek językowych w `dictionaries/`: `pl en de es fi fr is it ru`. Roadmapa wielojęzycznościowa zamknięta — historia wdrożeń (13.3 EN → 14.0 ES, jeden język na minor) jest w `git log` + commitach release'owych.
- Bezpieczna kolejność wdrażania nowego języka (gdyby pojawił się 10. język w 15.x+): najpierw paczka treściowa (`podstawy.yaml` + `akcenty/` + `szyfry/` + `rezyser/`), potem `gui/ui.yaml` (autotłumacz), potem `gui/dokumentacja/*.yaml` (autotłumacz), na końcu release.
- Reguła natywności: każdy język otrzymuje standardowe 6 szyfrów + 8 akcentów obcojęzycznych (akcenty 9 wdrożonych języków minus własny natywny) + 3 narzędzia czyszczenia (`oczyszczenie`, `oczyszczenie_bez_liczb`, `naprawiacz_tagow`) = 11 plików w `akcenty/` + 4 tryby w `rezyser/`. To wzorzec wzięty z kompletu istniejących paczek; nie jest egzekwowany przez silnik (silnik wymaga ≥1 plik per podfolder, patrz niżej), ale dla parytetu z resztą paczek trzymaj się tego.
- WYMÓG SILNIKA (`core_poliglota._jezyk_kompletny`, od 13.9): folder `<kod>/` jest skanowany pod kątem `podstawy.yaml` + minimum **1 pliku** w każdym z czterech podfolderów (`akcenty/`, `szyfry/`, `rezyser/`, `gui/ui.yaml`). Stuby są filtrowane przez `dostepne_jezyki_bazowe()`. Po dodaniu/usunięciu pliku w `rezyser/` lub `akcenty/` uruchom `odswiez_rezysera.py`, żeby zaktualizować dispatch (`core_rezyser._AKCENT_FUNCS` + docstringi `core_poliglota.akcent_*`).
- Tłumaczenia interfejsu rezydują w dedykowanym pliku: `dictionaries/<kod>/gui/ui.yaml`. ZAKAZ hardkodowania etykiet GUI w kodzie źródłowym Pythona.
- Parametry dynamiczne takie jak `{nazwa_projektu}`, `{liczba_znakow}`, `{min_przesuniecie}` pozostaw w tłumaczeniach nienaruszone. Nie tłumacz literałów technicznych i rozszerzeń (np. `.md`, `skrypty/`) ani nie usuwaj emoji zachowując ich ścisłą pozycję.
- Konwencje wxPython w i18n:
 * Akceleratory (Znak `&`): Należy zachować i przesunąć na dostępną literę pasującą w danym języku.
 * Skróty klawiszowe w menu (`\tCtrl+...`): Zachowaj je w oryginale we wszystkich językach bez dokonywania lokalizacji terminów jak Shift czy Alt.
 * Długie komunikaty błędów zachowują bezwzględnie wszystkie białe znaki (`\n`), co warunkuje właściwe łamanie tekstu.
 * Rozróżniaj klucze: Tooltip i etykieta to dwa osobne klucze dla jednego obiektu.
- Skrypt autotłumaczący z użyciem modelu (`tlumacz_ai.py`) zamraża podmieniane zmienne `{...}`, aby LLM nie naruszył struktury programu.
- Manager Reguł skanuje pliki YAML z folderów `akcenty`, `szyfry`, `rezyser` i `gui`. Tworzenie nowego języka generuje wszystkie cztery podfoldery na raz — dispatch silnika nie wystartuje bez `rezyser/` (wymóg ≥1 trybu).
- Pułapka kolejności w plikach `akcenty/<kod>.yaml`: silnik aplikuje listę `zamiany:` SEKWENCYJNIE (każda reguła operuje na wyjściu poprzedniej, `str.replace`). Reguły, które wprowadzają literę używaną później jako wzorzec, mogą wpaść w pętlę nadpisań — komentuj kolejność w YAML, żeby przyszły reviewer nie zamienił. Przykład empiryczny ES (`ñ → nj` przed `j → <coś>`) w `claude_archive.md`.

# ZAMYKANIE RELEASU — DOKUMENTACJA (KRYTYCZNE)
`build_release.py` wywołuje `generuj_dokumentacje.generuj()` wewnętrznie, przez co po jego uruchomieniu w repo pojawiają się niezcommitowane zmiany w `docs/*.txt`. Żeby tego uniknąć, dokumentację należy wygenerować i zcommitować **ręcznie** przed commitem release'u, według poniższego schematu.

## Kiedy stosować
Przy każdym release commicie, jeśli w danym cyklu zmieniło się cokolwiek z listy: nowy język, nowa funkcja opisana w manualach, zmiana liczby akcentów/szyfrów/trybów, zmiana numeru wersji (VERSION).

## Procedura (w tej kolejności)

### Krok 0a — Bump VERSION (KRYTYCZNE: PRZED jakąkolwiek regeneracją docs!)
Zaktualizuj plik `VERSION` w roocie repo (np. 13.9 → 14.0). Zasada: **najpierw bump VERSION, potem regeneracja docs, potem release commit**. `generuj_dokumentacje.py` rozwija `{numer_wersji}` z pliku VERSION przy KAŻDYM wywołaniu — jeśli zwalidujesz docs ze starym numerem i zcommitujesz, `build_release.py` wewnętrznie wywoła `generuj()` z nowym VERSION i wygeneruje niezcommitowany diff `modified: docs/manual.<iso>.txt × 8` zaraz po buildzie. Sam VERSION można zcommitować razem z release commit'em (Krok 4) — chodzi tylko o to, żeby docs były generowane już z docelowym numerem.

### Krok 0b — Odśwież reżysera (ZAWSZE po dodaniu/usunięciu pliku akcent*.yaml)
```bash
.venv/Scripts/python odswiez_rezysera.py
```
Skrypt skanuje `dictionaries/*/akcenty/` i aktualizuje dwa bloki generowane w kodzie:
- `core_poliglota.py` — docstringi wrapperów `akcent_*` (lista plików źródłowych per akcent)
- `core_rezyser.py` — blok importów i słownik `_AKCENT_FUNCS` (dispatch reżysera)

**Bez tego kroku samo nakładanie akcentów w Poliglocie działa** (czyta YAML bezpośrednio), ale **dynamiczne nakładanie akcentów w Reżyserze na podstawie regexów Księgi Świata — nie** (dispatch nie zna nowych plików). Sprawdź output: każdy nowy akcent/język musi pojawić się na liście wykrytych. Jeśli `core_poliglota.py` lub `core_rezyser.py` ma zmiany — zcommituj je przed przejściem do kroku 1.

### Krok 1 — Przejrzyj i zaktualizuj szablony źródłowe
Szablony to `dictionaries/<kod>/gui/dokumentacja/*.yaml` dla **każdego** z 9 wdrożonych języków z osobna (`pl`, `en`, `de`, `es`, `fi`, `fr`, `is`, `it`, `ru`). Istniejące szablony edytuj **ręcznie w danym języku** — nie uruchamiaj autotłumacza na plikach, które już istnieją. Powody: koszt API OpenAI + podatność LLM na halucynacje (niezaszyfrowane przykłady szyfrów, bezsensowne sklejki zdań po przeklejonej informacji).

Dla każdego istniejącego szablonu sprawdź:
- Czy opis nowych funkcji (nowy język, nowa funkcja silnika) jest aktualny i przetłumaczony na język szablonu?
- Czy stare „w przyszłości pojawi się X" zostało usunięte, skoro X już działa?
- Czy liczby (`liczba_akcentow_jezykowych` itp.) są placeholderami, nie zahardkodowanymi wartościami?
- Czy usunięte / przemianowane elementy GUI nie mają już swoich akapitów?

Wzorzec edycji: najpierw zaktualizuj `pl/` (język bazowy), potem otwórz analogiczny fragment w każdym języku obcym i wprowadź tę samą zmianę treści, zachowując istniejące tłumaczenie otoczenia jako wzorzec stylu.

**Autotłumacz (`buduj_wielojezyczne_docs.py`) — TYLKO dla zupełnie nowych plików szablonów**, tzn. gdy dany `*.yaml` w danym `<kod>/gui/dokumentacja/` w ogóle nie istnieje (np. nowy język bazowy albo nowy szablon dodany do `pl/` bez odpowiednika w `en/fi/...`). Po AI-tłumaczeniu obowiązkowo przejrzyj wyniki i popraw halucynacje używając już zatwierdzonych szablonów jako wzorca.

**Pułapka po autotłumaczeniu: halucynacja wstrzykuje treść SPOZA źródła pl.** Mechanizm: model widzi całą paczkę dokumentacji w kontekście treningowym i przy słabej walidacji potrafi dosypać „logicznie pasujący" rozdział, którego nie ma w polskim źródle. Pełny opis incydentu fi/manual.yaml z 2026-05-15 — `claude_archive.md`.

Sanity check po `buduj_wielojezyczne_docs.py` lub `tlumacz_ai.py` (PRZED commit'em obcojęzycznego szablonu):
- **Porównaj liczbę linii każdej wartości tekstowej** `dictionaries/<iso>/gui/dokumentacja/<plik>.yaml` vs odpowiadającego klucza w `pl/`. Różnica >40% to silny sygnał halucynacji (autotłumaczenie sensowne podtrzymuje rozmiar 1:1 ± kilka linii na różnice składniowe).
- **Polskie pozostałości w obcojęzycznych szablonach**: zgrep po `dictionaries/*/gui/dokumentacja/*.yaml` (z wykluczeniem `pl/`) na wzorce `polski|polska|polsku|po polsku|dostępne|szyfr:|odwracacz`. Wyjątki: nazwy plików technicznych typu `polski.yaml` w opisach struktury paczki silnika.
- **Markdown nagłówki `## ` w wartościach `<iso>` których nie ma w `pl`**: niemal pewna halucynacja. Polski oryginał używa nagłówków tekstowych bez `##`, więc każde `## ` w obcojęzycznym szablonie zasługuje na manualną weryfikację.

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
git commit -m "docs: regeneracja po 14.X — <krótki opis zmian>"
```
Dopiero po tym robi się commit release'u (VERSION wraz z RELEASE_NOTES — sam plik VERSION był już zaktualizowany w Kroku 0a i czeka jako unstaged change w `git status`, więc `git add VERSION RELEASE_NOTES.md && git commit` zamknie release jednym commitem).

### Uwaga o build_release.py — sanity check
`build_release.py` i tak wywołuje `generuj()` wewnętrznie — to jest celowe (paczka ZIP zawsze ma świeże docs). Po prawidłowym pre-commicie (Krok 0a → 2 → 4 w tej kolejności) `git status` po buildzie pokaże „nothing to commit" zamiast zmienionych plików, bo wygenerowana treść będzie identyczna z tą w repo. Jeśli `git status` po buildzie pokazuje `modified: docs/manual.<iso>.txt`, to znaczy że Krok 0a (bump VERSION przed regeneracją) został pominięty albo VERSION zmieniony pomiędzy Krokiem 2 a release commitem — diff pokaże stary numer wersji w nagłówkach i należy zrobić fixup commit `docs: bump numer wersji w docs/ po regeneracji`.

# WORKFLOW RELEASE — direct-to-main, bez PR-ów (od v15.2.5)
Workflow PR/branch został świadomie porzucony w v15.2.5. Solo-dev + A11y first: Release UI to jedna prosta strona, PR UI to znacznie więcej do nawigacji NVDA i więcej miejsc gdzie coś można pominąć („zapomniałem stworzyć PR" jest objawem, nie wyjątkiem). `RELEASE_NOTES.md` jest single source of truth dla treści Release description — auto-generator GitHub-owy (`Full Changelog: ...compare/X...Y`) jest GORSZY niż nasza ręczna narracja (długie akapity z konkretną diagnozą bugów, lista naprawionych halucynacji, tradeoff-y), więc go nie używamy.

## Procedura release (każdy patch X.Y.(Z+1))
1. Krok 0a-0b z sekcji `# ZAMYKANIE RELEASU — DOKUMENTACJA` (bump VERSION + odśwież reżysera).
2. Edytuj `RELEASE_NOTES.md`: na górze pliku zaktualizuj numer wersji w nagłówku (linia 1), dodaj nowy paragraph `*Patch v<wersja>: ...*` jako pierwszy w bloku streszczeń przed `---`, dodaj nową sekcję `## <wersja> — patch release ...` zaraz po `---` separatorze (przed istniejącą sekcją poprzedniej wersji). Wzorzec struktury: TL;DR (3-4 akapity narracyjne) → Co nowego dla użytkownika końcowego → Pod maską (techniczne) → Co nie weszło → Walidacja przed commit'em.
3. Regeneracja + commit docs (Kroki 1-3 z `# ZAMYKANIE RELEASU — DOKUMENTACJA`). Możesz zcommitować docs/ + RELEASE_NOTES.md + VERSION + edytowane szablony YAML + (opcjonalnie) kod razem jako single release commit, albo rozbić na dwa commity (docs + release). Single commit preferowany dla zwykłych patchy — czytelniejsza historia.
4. Commit message: `v<wersja>: <jednolinijkowy opis>` w nagłówku, body bullet list głównych zmian. Wzorzec: `git --no-pager show <ostatni tag> --stat | head -5` dla podobnego patcha.
   **KRYTYCZNE: ZAKAZ GitHub auto-close keywords + `#N`** w commit message (nagłówku ANI body), gdy issue ma być zamknięte przez bot workflow `issue-closure.yml`. Zakazane słowa (case-insensitive, GitHub keywords) przed `#N`: `close`, `closes`, `closed`, `fix`, `fixes`, `fixed`, `resolve`, `resolves`, `resolved`. Wykonują się przy push do main **lub** przy publikacji Release wskazującej na commit zawierający keyword. Plus: dla issues zamkniętych przez auto-close keyword GitHub od ~2025 ukrył/usunął przycisk „Reopen". Bezpieczne alternatywy: `(re: #N)`, `(addresses #N)`, `(per #N)`, `(scope: #N)`, „mentions #N" / „relates to #N" / „context: #N" — żadne z nich nie jest GitHub keyword. Pełna narracja incydentu #13 (2026-05-16) w `claude_archive.md`.
5. `git push origin main`.
6. **Preferowana (od v15.2.9)**: odpal workflow `draft-release.yml` przez Web GitHub → Actions → „Draft Release (auto-tag + RELEASE_NOTES.md sekcja → draft)" → Run workflow → input `potwierdz=tak` → Run. Bot wykonuje:
   - odczytuje VERSION z roota repo,
   - sprawdza czy tag `v<wersja>` już istnieje (lokalnie + na origin) → fail jeśli tak (bump VERSION lub usuń tag),
   - tworzy tag `v<wersja>` na obecnym HEAD origin/main + pushuje,
   - wyciąga sekcję `## <wersja>` z `RELEASE_NOTES.md` (regex identyczny jak w ręcznym skrypcie poniżej),
   - tworzy draft Release z tytułem „Reżyser Audio GPT, wersja <wersja>" + treścią z wyciętej sekcji.

   Eliminuje user errors: literówka w numerze wersji, błędny commit-target tagu, pomyłka treści notes, duplikat tagu, pominięcie tytułu, zapomnienie o Installerze (workflow zatrzymuje się na draftcie — Publish dopiero po upload EXE). Workflow ma szybę bezpieczeństwa: input `potwierdz` musi być dokładnie „tak" — inaczej no-op.

   **Fallback ręczny** (gdy bot zawiedzie lub workflow_dispatch niedostępne): wygeneruj `release.txt` (gitignored, w roocie repo) zawierający tylko sekcję `## <wersja>` wyciętą z `RELEASE_NOTES.md`. Wzorcowy skrypt:
   ```
   .venv/Scripts/python -c "import pathlib, re, sys; sys.stdout.reconfigure(encoding='utf-8'); t = pathlib.Path('RELEASE_NOTES.md').read_text(encoding='utf-8'); m = re.search(r'(## <WERSJA> — patch release.*?)(?=\n## )', t, re.DOTALL); pathlib.Path('release.txt').write_text(m.group(1).rstrip()+chr(10), encoding='utf-8'); print(f'release.txt: {len(m.group(1))} znaków')"
   ```
   Płaska nazwa BEZ numeru wersji — plik jest nadpisywany przy każdym kolejnym patchu, nie ma potrzeby aktualizować `.gitignore`.
7. **Po workflow `draft-release.yml`**: Web GitHub → Releases → wybierz nowy draft (tytuł „Reżyser Audio GPT, wersja <wersja>") → upload artefaktu `Rezyser_Audio_v<wersja>_Installer.exe` → Publish.

   **Fallback ręczny** (gdy używasz `release.txt` z kroku 6 fallback): Web GitHub → nowy Release. „Create new tag: v<wersja> on publish". Otwórz `release.txt` w Notatniku (`start release.txt` w PowerShellu), Ctrl+A → Ctrl+C, wklej w polu Description (markdown renderuje 1:1 w GitHub Release UI). Upload artefaktu `Rezyser_Audio_v<wersja>_Installer.exe`. Publish. Po wklejeniu `release.txt` możesz usunąć z dysku — jest gitignored, więc nie zaśmieca historii, a przy następnym patchu i tak zostanie wygenerowany od nowa.

## Heurystyka „cleanup commit boota = force-push tag" — fallback edge case
Od v15.2.8 happy path = atomic-reset boota (patrz `# ODPOWIEDZI NA ISSUE`). Jeśli bot nie mógł użyć atomic-reset (HEAD nieatomowy albo `--force-with-lease` odrzucony) i dorobił cleanup commit, dopuszczalny jest force-push **tag-only** post-publish na HEAD, żeby archive Release UI auto-regenerated był czysty. Pełna procedura (warunki kontrolne, kiedy NIE stosować, komendy) — `claude_archive.md`.

UWAGA: force push do MAIN/MASTER przez MAINTAINERA pozostaje zakazany. Dopuszczalne wyjątki w tym repo: (a) force push **tag-only** post-publish dla scenariusza fix-up (wzorzec udokumentowany w memory `[[project_v15_2_roadmap]]`); (b) force push **branch-only** przez `github-actions[bot]` w workflow `issue-closure.yml` przy atomic-reset commit'a `pending_answer.md` (od v15.2.8) — bot ma `contents: write` i działa wyłącznie gdy HEAD = single-file commit z samym `pending_answer.md`, więc force-push nie może niczego innego zniszczyć.

## Czego nie robić
- NIE twórz feature branchy dla zwykłych patchy. Wszystko bezpośrednio na main.
- NIE używaj `gh pr create/merge` / `git tag` lokalnie do TWORZENIA tagów. Nowe tagi powstają WYŁĄCZNIE przez web Release UI atomowo z Release. **Wyjątek**: force-push tag-only post-publish dla cleanup commit'a boota — patrz `## Heurystyka „cleanup commit boota = force-push tag"` wyżej w tej sekcji.
- NIE polegaj na `PULL_REQUEST_COMMENTS.md` — plik usunięty z repo w v15.2.5 fix-up commicie. Komentarze recenzentskie (jeśli pojawią się) trafiają wprost do `RELEASE_NOTES.md::<wersja>::Co nie weszło` jako TODO do następnego cyklu, albo do konwersacji z agentem.

## Wyjątki (kiedy feature branch ma sens)
Rzadkie scenariusze (duży refaktor wielo-patchowy, eksperymentalna gałąź do porzucenia, PR od kontrybutora zewnętrznego) — opisane w `claude_archive.md`.

## Klauzula awaryjna: bug-issue ma pierwszeństwo nad planowaną treścią
Jeśli między ostatnim Release a planowaną treścią kolejnego patcha pojawi się nowe issue z etykietą `bug` od prawdziwego usera — **bug ma pierwszeństwo**. Workflow „Z Południa na Północ" zakłada, że każde otwarte issue zamyka się przez `fixed-in-release`; odkładanie rozjeżdża workflow.

Procedura: (1) odłóż feature na następny cykl (przepisz `Co nie weszło` → następny patch), (2) bumpuj X.Y.(Z+1) [[feedback_hotfix_release]], (3) patch rozwiązuje TYLKO bug-issue (lub grupę powiązanych z jednego obszaru), (4) w `RELEASE_NOTES.md::Co nowego` wymień zamknięte issues, w `Co nie weszło` przepisz poprzedni cykl, (5) po Release nadaj etykietę `fixed-in-release` przez web UI — workflow boota zamyka.

Wyjątek: bug niewykonalny w jednym patchu (wymaga większego refaktoru, np. split user-data/seed-data z roadmapy v15.3+) — przeetykietuj `bug` → `enhancement` z komentarzem wyjaśniającym workaround + plan strukturalny. Sami przerobi na feature-issue.

# OBIEG ZGŁOSZEŃ Z POŁUDNIA NA PÓŁNOC — INTERPRETACJA PROMPTU SAMI (od v15.2.8 trójsekcyjny)
Sami (`.github/scripts/issue_intake_sami.py`, etap Południe) odbiera każde nowe GitHub Issue (eventy `opened` lub `labeled` z akceptowalną etykietą — patrz `LABELS_ACCEPT` / `LABELS_IGNORE` w skrypcie) i wysyła do Centrum mail w plain text o standardowej **trójsekcyjnej** strukturze:

1. **PROMPT DLA AGENTA AI** — wygenerowany przez `gpt-4o-mini` wg `SAMI_SYSTEM_PROMPT`. Format zależy od etykiet:
   * **TRYB A — question / help wanted** (etykiety zawierają TYLKO `question` i/lub `help wanted`, BEZ `bug`/`enhancement`/`documentation`):
     dokładnie 2 sekcje: `## Cel pytania` + `## Co agent powinien zrobić`. Agent czyta i odpowiada przez `pending_answer.md` (patrz `# ODPOWIEDZI NA ISSUE`).
   * **TRYB B — zmiana w kodzie** (etykiety zawierają `bug`, `enhancement`, `documentation` lub `invalid`, nawet w kombinacji z question/help wanted):
     dokładnie 4 sekcje: `## Cel` + `## Kontekst techniczny` + `## Kryteria akceptacji` + `## Pułapki do uniknięcia`. Agent implementuje fix.

2. **ORYGINALNY TEKST ZGŁOSZENIA (do weryfikacji)** — surowy `title + body` z GitHub. KRYTYCZNE: ZAWSZE porównuj prompt z oryginałem zanim zaczniesz implementować. LLM `gpt-4o-mini` bywa kreatywny i potrafi:
   - wpisać nieistniejący moduł (np. „prawdopodobnie `core_translator.py`" gdy takiego pliku nie ma w repo),
   - zmyślić kroki reprodukcji których nie ma w treści usera,
   - nadać zgłoszeniu fałszywą diagnozę („to bug w X" gdy user pyta o coś innego).
   Oryginał jest źródłem prawdy — prompt to sugestia agenta-LLM, nie wyrocznia.

3. **OTWARTE ISSUES W REPO (snapshot z momentu intake)** — surowy output `gh issue list --state open --limit 50` (od v15.2.8). Zastępuje konieczność lokalnego `gh issue list` po stronie maintainera (`gh` CLI nie zawsze w PATH agenta Centrum — Git Bash + PowerShell maintainera empirycznie 2026-05-16 nie miały). Użycie:
   - sprawdź czy bieżące zgłoszenie nie jest duplikatem otwartego issue,
   - wykryj powiązane bugi z tego samego obszaru (można scalić w jeden patch wg „klauzuli awaryjnej" `# WORKFLOW RELEASE`),
   - zorientuj się w backlogu zanim zdecydujesz o priorytecie (np. czy nowy bug ma pierwszeństwo nad planowanym enhancement'em z poprzedniego cyklu).

## Sygnał rozpoznawczy
Jeśli widzisz w sesji input maintainera otwierający się od `## Cel pytania` / `## Cel` z dalszymi sekcjami w jednej z dwóch struktur (2 lub 4 sekcje), potem separator `==========…` i `ORYGINALNY TEKST ZGŁOSZENIA`, potem separator i `OTWARTE ISSUES W REPO` — **to obieg „Z Południa na Północ"**. Maintainer wkleił do sesji całość z maila Sami; Twoja rola to **Centrum**. Decyzja ścieżki (TRYB A vs TRYB B) wynika z liczby sekcji promptu i etykiet wymienionych w nagłówku maila (linia „Etykiety: ...").

Plik `skrypty/issue.txt` (tymczasowy bufor maintainera na treść maila) jest gitignorowany (`skrypty/` w `.gitignore`) i usuwany ręcznie po zbudowaniu promptu — nie wpływa na stan repo, ślad istnieje tylko w sesji agenta.

## Pułapki przy interpretacji
- **Halucynacja LLM w sekcji „Pułapki do uniknięcia"** (TRYB B): Sami czasem wkleja generyczne reguły z CLAUDE.md nieadekwatne do zgłoszenia („pamiętaj o `.venv/Scripts/python`" gdy issue dotyczy wyłącznie YAML-a workflowa). Filtruj — implementuj fix wg merytorycznej treści `## Cel` + `## Kontekst techniczny`. „Pułapki" to przypomnienia, nie wymóg blokujący.
- **Tryb FALLBACK** (gdy OpenAI zawiodło — brak kredytów, 401/429, timeout): mail ma w temacie `[Sami (fallback)]` zamiast `[Sami (LLM)]`, a sekcja PROMPT = surowy `title + body` z notatką „(Sami chwilowo nie pomogła z przeredagowaniem...)". W fallbacku NIE MA podziału na TRYB A/B — Centrum sam decyduje ścieżkę na podstawie etykiet (wymienione zaraz pod linkiem do issue w nagłówku maila).
- **Pusta sekcja OTWARTE ISSUES**: komunikat `(brak otwartych issues)` lub `(gh ... zfailowało: ...)` / `(gh CLI nie znalezione w PATH workflow runner'a)`. Pierwsze = backlog czysty, drugie = workflow runner miał transient problem z `gh`, ale zgłoszenie nadal idzie do realizacji (sekcja jest informacyjna, nie blokuje obiegu).

# ODPOWIEDZI NA ISSUE — question-flow z pliku (FILE mode + atomic-reset)
Maintainer zapisuje draft jako `pending_answer.md` w roocie repo (Write/Edit tools, bez kopiowania z terminala), pushuje na main atomowo, nadaje etykietę `answered`. Bot (`issue_closure_north.py`) wczytuje treść Z PLIKU (nie z komentarzy — to eliminuje race condition trzeciego komentującego), opakowuje w wrapper Lumi/Vieno/Katla, publikuje, zamyka i lockuje issue, oraz wymazuje draft z historii main przez atomic-reset: `git reset --hard HEAD~1` + `git push --force-with-lease`. Warunek atomic-reset: HEAD na origin/main MUSI być commit'em dodającym DOKŁADNIE jeden plik `pending_answer.md`. Jeśli warunek niespełniony — bot fallbackuje do cleanup commit'a (patrz heurystyka force-push tag w `# WORKFLOW RELEASE` + szczegóły w `claude_archive.md`). Historia ewolucji v15.2.6 → v15.2.7 → v15.2.8 — `claude_archive.md`.

## Procedura — flow czystego question (issue NIE wymaga release)
1. Stwórz/zaktualizuj `pending_answer.md` w roocie repo — czysta odpowiedź merytoryczna w języku oryginalnego zgłoszenia (markdown OK), BEZ podpisu maintainera (wrapper Lumi/Vieno/Katla dopisuje swój podpis).
2. `git add pending_answer.md && git commit -m "answer: draft odpowiedzi na #<N>" && git push origin main`. **KRYTYCZNE:** ten commit musi być ATOMOWY (TYLKO `pending_answer.md`, żadnych innych plików). Atomowość = warunek konieczny dla preferowanej ścieżki atomic-reset boota. Jeśli zapomniałeś jakichś zmian (np. lessons learned w CLAUDE.md), zcommituj je PRZED `pending_answer.md` jako osobny commit — wtedy `pending_answer.md` zostaje na HEAD jako atomowy.
3. Na web GitHub UI nadaj etykietę `answered` na issue #N. Workflow `issue-closure.yml` (job `zamknij_z_polnocy`) odpali się przez webhook `issues.labeled`.
4. Bot (skrypt `issue_closure_north.py`) wykrywa obecność `pending_answer.md` → tryb FILE: wczytuje treść, opakowuje w persona-template w wykrytym języku, woła `gh issue comment`, `gh issue close`, `gh issue lock --reason resolved`. Następnie sprawdza atomowość HEAD:
   * **Atomowy** (HEAD = tylko `pending_answer.md`): `git reset --hard HEAD~1` + `git push --force-with-lease`. Draft wymazany z historii, brak cleanup commit'a.
   * **Nieatomowy** (HEAD zawiera inne pliki): `git rm pending_answer.md && git commit && git push` z autorem `github-actions[bot]` (fallback v15.2.7 cleanup commit).
5. Po zakończeniu workflow lokalnie zrób `git fetch origin && git reset --hard origin/main` (NIE zwykłe `git pull`! Atomic-reset rewrite'uje historię na origin — `git pull` z domyślnym merge wykryje rozjazd i zacznie histeryzować przy non-fast-forward; `git reset --hard origin/main` po fetchu po prostu synchronizuje lokalny ref z aktualnym remote, niezależnie czy bot użył atomic-reset czy cleanup commit'a). `git log` pokaże 0 commit'ów (atomic-reset) lub 2 commity maintainer-add + bot-rm (fallback).

## Sub-procedury bug+answer (release-then-answer, release-with-answer)
Gdy issue wymaga release'u + komentarza/dolepka osobistej wiadomości — wybór ścieżki:
- **release-then-answer**: bug fix + osobny komentarz BEZ linku do Release. Zamykane przez `answered`. Release commit i `pending_answer.md` commit są ROZBITE na osobne pushe, między nimi publikacja Release (tag wskazuje na czysty release commit). Rzadkie.
- **release-with-answer** (od v15.2.8): bug-issue + dolepek osobistej wiadomości (tip o recovery, przeprosiny). Zamykane przez `fixed-in-release` z FILE mode boota (dolepia treść `pending_answer.md` pod TEMPLATES separatorem `---`). KRYTYCZNE: tag musi wskazywać na release commit, NIE na pending_answer.md commit — sprawdź SHA w Web UI.

Pełne procedury obu sub-flow'ów (kroki + komendy) → `claude_archive.md`.

## Sytuacje brzegowe — kluczowe
- **Workflow YAML wymóg `fetch-depth: 2`** na `actions/checkout@v4` w `issue-closure.yml` — bez tego HEAD~1 nie istnieje lokalnie i atomic-reset failuje na każdym issue.
- **Równoległe issue z question**: bot trzyma jeden plik per repo, więc obsługuj jedno question-issue na raz. Drugie czeka aż pierwsze się zamknie.
- **Bug-issue ≠ question-flow**: etykiety disjunktywne. `answered` TYLKO na question. `fixed-in-release` na bug. Od v15.2.8 bug-issue MOŻE mieć dolepek (release-with-answer), ale wciąż przez `fixed-in-release`, nie przez `answered`.

Pozostałe edge case'y (pusty `pending_answer.md`, brak pliku przy `answered`/`fixed-in-release`, nieatomowy HEAD, `--force-with-lease` odrzucony, push fail bota) → `claude_archive.md`.

# SPRZĄTANIE (HIGIENA REPOZYTORIUM)
- Zawsze po skończonej weryfikacji usuwaj wszystkie pliki tymczasowe (np. pliki z logami lub testami jednostkowymi).
- Weryfikuj porządek przez komendę `git status` patrząc na nieśledzone pliki (Untracked files).
- Commity pośrednie: Możesz, a nawet powinieneś, wykonywać commity po zakończeniu poprawnie działającego małego podetapu dużej rewizji z tagiem "WIP".
- ZAWSZE zrób review (`git --no-pager diff`) zanim zapiszesz stan na stałe w repozytorium.

# ARCHIWUM HISTORYCZNE
Zarchiwizowane procedury, incydenty i fallbackowe ścieżki znajdują się w `claude_archive.md` (gitignored — patrz `.gitignore` jeśli nie). Zawartość archiwum: incydent halucynacji autotłumaczenia fi/manual.yaml (2026-05-15), incydent #13 GitHub auto-close keywords (2026-05-16), pełna heurystyka „cleanup commit boota = force-push tag" (v15.2.7 fallback), ewolucja question-flow v15.2.6 → v15.2.7 → v15.2.8, sub-procedury release-then-answer i release-with-answer (kompletne), edge case'y `pending_answer.md` w question-flow, wyjątki feature-branch workflowu, przykład empiryczny pułapki kolejności w `akcenty/es.yaml`. Sięgaj tam gdy debugujesz post-mortem albo gdy główny CLAUDE.md odsyła frazą „pełna procedura w `claude_archive.md`".