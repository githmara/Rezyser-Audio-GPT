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
7. KLUCZ OPENAI DOSTĘPNY (Plik `golden_key.env` w roocie repo jest i zawsze był gitignorowany (`.gitignore` ma wpisy `*.env` i `golden_key.env`), ale **fizycznie obecny na dysku** dewelopera, więc skrypty `buduj_wielojezyczne_ui.py`, `buduj_wielojezyczne_docs.py`, `tlumacz_ai.py` (oraz każda część kodu używająca `tlumacz_ai`) ładują z niego klucz przez `python-dotenv` (`load_dotenv(ROOT / "golden_key.env")` → `os.environ["OPENAI_API_KEY"]`). Agent **może i powinien** odpalać te skrypty bezpośrednio, kiedy tylko zadanie wymaga LLM — nie przekazuj tego kroku użytkownikowi „bo nie masz API". Procedura: jeśli skrypt zwróci błąd „❌ Brak prawidłowego OPENAI_API_KEY" lub błąd HTTP 401 / 429 (rate limit / brak kredytów), **wtedy** zatrzymaj się i poproś użytkownika o uzupełnienie konta (a nie z góry zakładaj). Po wygenerowaniu auto-tłumaczeń ZAWSZE rób manualny review halucynacji (LLM lubi wymyślać niezaszyfrowane przykłady szyfrów albo bezsensowne sklejki — porównuj z zatwierdzonymi szablonami w innym języku jako wzorcem stylu).
8. KOPIOWANIE Z TERMINALA NIE JEST WIARYGODNE (KRYTYCZNE A11y, lessons learned po smoke teście v15.2.7). Accessibility buffer VS Code (mechanizm pośredniczący między terminalem a NVDA) **tokenizuje treść tnąc ją na fragmenty i powtarzając ciągi znaków** — dotyczy to nawet krótkich wzorców typu HEREDOC commit message (potwierdzone empirycznie 2026-05-16). Praktyczne reguły dla agenta:
   - **Długie treści (commit messages, release notes, drafty odpowiedzi, hiszpańskie/niemieckie/inne diakrytyczne fragmenty) ZAPISUJ DO PLIKU** i poproś użytkownika żeby otworzył plik w edytorze VS Code (Ctrl+P → nazwa pliku) — edytor pliku ma natywne A11y wsparcie, w przeciwieństwie do panelu Terminal. Wzorce: `pending_answer.md` dla draftów odpowiedzi na issue, `release.txt` dla Release description, `commit_msg.txt` w sytuacjach kiedy musisz dostarczyć użytkownikowi gotowy tekst commit messaga do skopiowania.
   - **NIE proś użytkownika żeby skopiował tekst z Twojego output'u w terminalu** — nawet jeśli wygląda krótko. Zawsze pisz do pliku i wskazuj ścieżkę.
   - **AskUserQuestion w CLI ma znany bug renderowania bloków pytań przy multi-question** (potwierdzone 2026-05-16): pierwsze pytanie renderuje się poprawnie, kolejne mają **sklejone treści opcji** (treść opcji 1 z poprzedniego pytania miesza się z opcjami nowego pytania, bałagan w accessibility buffer). Praktyczne workaround'y:
     * **Preferuj 1 pytanie per turn** — zadawaj wieloetapowo, sekwencyjnie, niż w jednym wywołaniu wielopytaniowym.
     * Jeśli MUSZ zadać kilka pytań naraz (np. zależne decyzje projektowe), pisz w label'ach opcji **wyraźny prefix kontekstowy** typu „[Plik] pending_answer.md w roocie" zamiast samego „pending_answer.md w roocie" — to redukuje confuse'u w accessibility buffer, bo NVDA czyta prefix przed potencjalną sklejką.
     * Po AskUserQuestion zawsze powtórz w tekście odpowiedzi co user wybrał („User wybrał: pending_answer.md w roocie + Bot automatycznie") żeby zweryfikować że Twoje rozumienie zgadza się z odpowiedzią faktyczną.

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
- Pułapka kolejności w plikach `akcenty/<kod>.yaml`: silnik aplikuje listę `zamiany:` SEKWENCYJNIE (każda reguła operuje na wyjściu poprzedniej, `str.replace`). Reguły, które wprowadzają literę używaną później jako wzorzec, mogą wpaść w pętlę nadpisań. Klasyczny przypadek przy źródle ES: `ñ → nj` ORAZ `j → <coś>` — jeśli `ñ → nj` idzie pierwsze, nowa „j" zostanie złapana przez `j → <coś>`. Reguła: najpierw `j → <substytut>`, potem `ñ → nj` i `ll → j`. Komentuj kolejność w pliku YAML, żeby przyszły reviewer nie zamienił.

# ZAMYKANIE RELEASU — DOKUMENTACJA (KRYTYCZNE)
`build_release.py` wywołuje `generuj_dokumentacje.generuj()` wewnętrznie, przez co po jego uruchomieniu w repo pojawiają się niezcommitowane zmiany w `docs/*.txt`. Żeby tego uniknąć, dokumentację należy wygenerować i zcommitować **ręcznie** przed commitem release'u, według poniższego schematu.

## Kiedy stosować
Przy każdym release commicie, jeśli w danym cyklu zmieniło się cokolwiek z listy: nowy język, nowa funkcja opisana w manualach, zmiana liczby akcentów/szyfrów/trybów, zmiana numeru wersji (VERSION).

## Procedura (w tej kolejności)

### Krok 0a — Bump VERSION (KRYTYCZNE: PRZED jakąkolwiek regeneracją docs!)
```bash
# zaktualizuj plik VERSION w roocie repo, np. 13.9 → 14.0
```
**Dlaczego TUTAJ, a nie w commicie release'u?** `generuj_dokumentacje.py` rozwija placeholder `{numer_wersji}` z pliku VERSION przy KAŻDYM wywołaniu. Jeśli zwalidujesz docs (Krok 2) jeszcze ze starym numerem, zcommitujesz docs ze starym numerem, a potem dopiero bumpniesz VERSION w commicie release'u — `build_release.py` zadziała: wewnątrz wywoła `generuj()` z nowym VERSION, regeneruje wszystkie 16 plików `docs/*.txt` z nowym tytułem („Version 14.0" zamiast „Version 13.9") i wygeneruje **niezcommitowany diff** zaraz po buildzie. Symptom: `git status` po `build_release.py` pokazuje `modified: docs/manual.<iso>.txt × 8` — co kontradyktuje obietnicy „dokumentacja zcommitowana ręcznie przed release'em".

Zasada: **najpierw bump VERSION, potem regeneracja docs, potem release commit z VERSION + RELEASE_NOTES** (sam VERSION można zcommitować z release commitem — chodzi o to, żeby docs były generowane już z docelowym numerem). Plik VERSION jest mały (jedna linia) i bumpa robisz raz na release — nie ma kosztu „o, zapomniałem zacommitować VERSION zanim odpaliłem `--waliduj`", bo Krok 4 i tak go scali.

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

**Pułapka po autotłumaczeniu: halucynacja wstrzykuje treść SPOZA źródła pl.** Znaleziono 2026-05-15 w trakcie audytu pre-15.2.5: `dictionaries/fi/gui/dokumentacja/manual.yaml::naglowek` zawierał ~30 dodatkowych linii rozdziałów (`## Akcenty`, `## Szyfr: Odwracacz Tekstu`, `## Szyfr: Typoglycemia`, `## Pliki i głosy`) z treścią mieszaną fińsko-polską („Dostępne akcenty to:" w polszczyźnie, lista głosów typu „Englanti (Samantha/Mark…)"), wstrzykniętą prawdopodobnie z sąsiedniej paczki `dictionaries.yaml` lub z fragmentów dialogowych — `pl/manual.yaml::naglowek` nigdy nie miał takich nagłówków. Mechanizm: model widzi całą paczkę dokumentacji w kontekście treningowym i przy słabej walidacji potrafi dosypać „logicznie pasujący" rozdział, którego nie ma w polskim źródle. Skutek: fiński manual w `docs/` zawierał polskie zwroty i listy techniczne nieistniejące w żadnym innym języku.

Sanity check po `buduj_wielojezyczne_docs.py` lub `tlumacz_ai.py` (PRZED commit'em obcojęzycznego szablonu):
- **Porównaj liczbę linii każdej wartości tekstowej** `dictionaries/<iso>/gui/dokumentacja/<plik>.yaml` vs odpowiadającego klucza w `pl/`. Różnica >40% to silny sygnał halucynacji (autotłumaczenie sensowne podtrzymuje rozmiar 1:1 ± kilka linii na różnice składniowe).
- **Polskie pozostałości w obcojęzycznych szablonach**: `.venv/Scripts/python -c "import pathlib,re; [print(p,':',i+1,l) for p in pathlib.Path('dictionaries').glob('*/gui/dokumentacja/*.yaml') if p.parts[1]!='pl' for i,l in enumerate(p.read_text(encoding='utf-8').splitlines()) if re.search(r'\bpolski|polska|polsku|po polsku|dostępne|szyfr:?\s|odwracacz', l, re.IGNORECASE)]"`. Wyjątki dozwolone: nazwy plików technicznych typu `polski.yaml` w sekcjach opisujących strukturę paczki silnika (zwykle w `dictionaries.yaml`, nie w `manual.yaml::naglowek`).
- **Markdown nagłówki `## ` w wartościach `<iso>` których nie ma w `pl`**: niemal pewna halucynacja. Polski oryginał używa zwykłych nagłówków tekstowych bez `##`, więc każde `## ` w obcojęzycznym szablonie zasługuje na manualną weryfikację.

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
5. `git push origin main`.
6. Wygeneruj `release.txt` (gitignored, w roocie repo) zawierający tylko sekcję `## <wersja>` wyciętą z `RELEASE_NOTES.md`. Wzorcowy skrypt:
   ```
   .venv/Scripts/python -c "import pathlib, re, sys; sys.stdout.reconfigure(encoding='utf-8'); t = pathlib.Path('RELEASE_NOTES.md').read_text(encoding='utf-8'); m = re.search(r'(## <WERSJA> — patch release.*?)(?=\n## )', t, re.DOTALL); pathlib.Path('release.txt').write_text(m.group(1).rstrip()+chr(10), encoding='utf-8'); print(f'release.txt: {len(m.group(1))} znaków')"
   ```
   Płaska nazwa BEZ numeru wersji — plik jest nadpisywany przy każdym kolejnym patchu, nie ma potrzeby aktualizować `.gitignore`.
7. Web GitHub → nowy Release. „Create new tag: v<wersja> on publish" (Twój ustalony wybór: tagi tworzone WYŁĄCZNIE przez web Release UI, atomowo z Release, brak dryfu między tagiem a publikacją). Otwórz `release.txt` w Notatniku (`start release.txt` w PowerShellu), Ctrl+A → Ctrl+C, wklej w polu Description (markdown renderuje 1:1 w GitHub Release UI). Upload artefaktu `Rezyser_Audio_v<wersja>_Installer.exe`. Publish. Po wklejeniu `release.txt` możesz usunąć z dysku — jest gitignored, więc nie zaśmieca historii, a przy następnym patchu i tak zostanie wygenerowany od nowa.

## Heurystyka „cleanup commit boota = force-push tag" (od v15.2.7)
Jeśli release zawiera draft trybu FILE w question-flow (`pending_answer.md` zcommitowany razem z release commit'em — patrz sekcja `# ODPOWIEDZI NA ISSUE`), archive Release v<wersja> z punktu 7 zawiera ten plik jako kosmetyczny artefakt. Po nadaniu etykiety `answered` i zakończeniu workflow boota (`Issue Closure (North)`), na origin/main pojawia się cleanup commit `chore(answer-bot): cleanup pending_answer.md po odpowiedzi na #<N>`. Wtedy między tagiem v<wersja> a origin/main HEAD jest DOKŁADNIE 1 commit (cleanup boota) — to sygnał że można force-push tagu na HEAD, żeby archive Release UI auto-regenerated był już czysty.

### Kiedy zastosować
- Tag v<wersja> wskazuje na release commit zawierający `pending_answer.md`.
- Workflow boota zakończył się sukcesem (issue zamknięte + zalockowane + cleanup commit boota na origin/main).
- `git log --oneline v<wersja>..origin/main` pokazuje DOKŁADNIE 1 commit (cleanup boota, autor `github-actions[bot]`). Jeśli więcej commit'ów — nie force-pushuj, są inne post-release zmiany do osobnej analizy.

### Kiedy NIE zastosować
- Release wynika z bug-flow (`fixed-in-release`, nie `answered`) — wtedy cleanup boota nie istnieje (bug-flow nie używa `pending_answer.md`), tag jest atomowy z release commit'em zgodnie z normalną procedurą.
- Między tagiem a HEAD jest 0 commit'ów (workflow boota jeszcze nie odpalił, lub user jeszcze nie nadał etykiety `answered`) — wtedy force-push byłby NO-OP.
- Między tagiem a HEAD jest >1 commit (cleanup boota + jakiś inny commit) — analizuj zawartość każdego commit'a; jeśli wszystkie są refinement'em release (np. dodatkowy fix-up CLAUDE.md z lessons learned, jak v15.2.7), tag może wskazywać na HEAD, ale ZAWSZE eksplicytnie zweryfikuj `git --no-pager log --stat` przed force push.

### Procedura
```bash
# 1. Zweryfikuj liczbę commit'ów między tagiem a HEAD
git --no-pager log --oneline v<wersja>..origin/main
# 2. Jeśli OK, lokalny tag move
git tag -d v<wersja>          # usuń stary lokalny tag
git tag v<wersja> HEAD        # nowy tag na aktualnym HEAD
# 3. Force push tagu na origin (-f / --force tag-only, NIE branch!)
git push origin v<wersja> --force
```

Po force push tag'a, web GitHub Release UI auto-regeneruje source-code archive z nowego SHA — bez potrzeby edytować Release description ani re-uploadować Installer EXE. Release artefakty (Installer) zachowują się niezależnie od tag'a (są attachment'ami).

UWAGA: force push do MAIN/MASTER pozostaje zakazany. Force push **tag-only** jest dopuszczalny w tym repo dla scenariusza fix-up post-publish — wzorzec udokumentowany w memory `[[project_v15_2_roadmap]]`.

## Czego nie robić
- NIE twórz feature branchy dla zwykłych patchy. Wszystko bezpośrednio na main.
- NIE używaj `gh pr create/merge` / `git tag` lokalnie do TWORZENIA tagów. Nowe tagi powstają WYŁĄCZNIE przez web Release UI atomowo z Release. **Wyjątek**: force-push tag-only post-publish dla cleanup commit'a boota — patrz `## Heurystyka „cleanup commit boota = force-push tag"` wyżej w tej sekcji.
- NIE polegaj na `PULL_REQUEST_COMMENTS.md` — plik usunięty z repo w v15.2.5 fix-up commicie. Komentarze recenzentskie (jeśli pojawią się) trafiają wprost do `RELEASE_NOTES.md::<wersja>::Co nie weszło` jako TODO do następnego cyklu, albo do konwersacji z agentem.

## Wyjątki (kiedy feature branch ma sens)
- Refaktor większy niż jeden patch (np. planowany v15.3+ split user-data vs seed-data dla `dictionaries/`): feature branch jako logiczna izolacja etapowa, lokalne commity per etap. Finalizujący merge przez `git merge --ff-only` do main BEZ PR-u, web Release standardową ścieżką po merge. Procedura sprzątania po merge zachowana z czasów PR-flow: `git fetch --prune; git checkout main; git pull; git branch -d <gałąź>` (`-d` nie `-D` — `-d` odmówi jeśli nie zmergowane, co jest bezpieczne).
- Eksperymentalna gałąź (np. port Linux) którą możesz porzucić: feature branch + ewentualne `git branch -D` po decyzji o porzuceniu.
- Kontrybutor zewnętrzny: oni robią PR, Ty mergujesz przez web (rzadki przypadek, fork-based, nie wymaga zmian po naszej stronie).

## Klauzula awaryjna: bug-issue ma pierwszeństwo nad planowaną treścią
Jeśli pomiędzy ostatnim Release a planowaną treścią kolejnego patcha (z `RELEASE_NOTES.md::<wersja>::Co nie weszło` lub z agent memory) pojawi się nowe issue z etykietą `bug` od prawdziwego usera — **bug ma pierwszeństwo**. Workflow „Z Południa na Północ" z v15.2.4 zakłada, że każde otwarte issue zostaje zamknięte przez `fixed-in-release`; odkładanie buga na „następny-następny" patch rozjeżdża workflow (issue wisi otwarte, user czeka, Lumi/Vieno/Katla nie mają czego zamknąć).

Procedura przy konflikcie planów:
1. Odłóż planowaną pracę feature na kolejny cykl — przepisz wpis z `RELEASE_NOTES.md::<wersja>::Co nie weszło` jako fakt do następnego patcha.
2. Bumpuj VERSION X.Y.(Z+1) (patch tag, [[feedback_hotfix_release]]).
3. Patch rozwiązuje TYLKO bug-issue (lub grupę powiązanych bug-issues z jednego obszaru — można scalić w jeden patch jeśli leżą blisko siebie tematycznie i nie wymagają osobnych testów regresji).
4. W `RELEASE_NOTES.md::<wersja>::Co nowego` wymień zamknięte issues (numery + krótkie streszczenie), w `Co nie weszło` przepisz wpisy z poprzedniego cyklu (przeniesienie na kolejny patch).
5. Po publikacji Release nadaj zamkniętym issues etykietę `fixed-in-release` przez web GitHub UI — workflow `issue-closure.yml` (Lumi/Vieno/Katla) automatycznie skomentuje i zamknie je w języku oryginalnego zgłoszenia z linkiem do nowego Release.

Wyjątek: jeśli bug jest niewykonalny w pojedynczym patchu (wymaga większego refaktoru, np. issue sugerujące split user-data vs seed-data dla `dictionaries/` z roadmapy v15.3+) — przeetykietuj go z `bug` na `enhancement` z komentarzem wyjaśniającym dlaczego ten konkretny bug nie jest blokerem (np. „obejście istnieje przez backup dictionaries/ przed update, opisane w manualu sekcja Automatyczne aktualizacje; pełne rozwiązanie wymaga split architektury zaplanowanego na v15.3+"). Po przeetykietowaniu Sami przerobi to normalnym workflowem na feature-issue dla kolejnego cyklu, bez naruszania reguły „bug = priorytet".

# ODPOWIEDZI NA ISSUE — question-flow z pliku (od v15.2.7)
Wcześniejszy question-flow (v15.2.6) miał dwa problemy: (1) maintainer-NVDA-user musiał wkleić długą odpowiedź przez web GitHub UI, ale kopiowanie z terminala VS Code zawodzi w accessibility buffer (powtarza ciągi znaków); (2) gdyby ktoś trzeci skomentował między napisaniem odpowiedzi a nadaniem etykiety `answered`, bot wciągnął JEGO komentarz zamiast odpowiedzi maintainera (race condition na chronologii komentarzy).

Tryb FILE rozwiązuje obie sprawy: maintainer zapisuje draft jako `pending_answer.md` w roocie repo (Write/Edit tools, bez kopiowania z terminala), pushuje na main, nadaje etykietę `answered`. Bot wczytuje treść Z PLIKU (nie z komentarzy), opakowuje w wrapper Lumi/Vieno/Katla, publikuje, zamyka i lockuje issue, oraz usuwa plik commit-em własnego autora (`github-actions[bot]`).

## Procedura (per issue z question)
1. Stwórz/zaktualizuj `pending_answer.md` w roocie repo — czysta odpowiedź merytoryczna w języku oryginalnego zgłoszenia (markdown OK), BEZ podpisu maintainera (wrapper Lumi/Vieno/Katla dopisuje swój podpis).
2. `git add pending_answer.md && git commit -m "answer: draft odpowiedzi na #<N>" && git push origin main`.
3. Na web GitHub UI nadaj etykietę `answered` na issue #N. Workflow `issue-closure.yml` (job `zamknij_z_polnocy`) odpali się przez webhook `issues.labeled`.
4. Bot (skrypt `issue_closure_north.py`) wykrywa obecność `pending_answer.md` → tryb FILE: wczytuje treść, opakowuje w persona-template w wykrytym języku, woła `gh issue comment`, `gh issue close`, `gh issue lock --reason resolved`, potem `git rm pending_answer.md && git commit && git push` z autorem `github-actions[bot]`.
5. Po zakończeniu workflow `git pull` lokalnie (żeby pobrać cleanup commit boota) i `git log` — zobaczysz dwa commity: maintainer-add + bot-rm.

## Sytuacje brzegowe
- **`pending_answer.md` istnieje, ale jest pusty (whitespace-only)**: bot loguje warning i spada do trybu COMMENT. Mało prawdopodobne w praktyce — pisz draft od razu z treścią.
- **`pending_answer.md` NIE istnieje przy `answered`**: bot spada do trybu COMMENT (obecny od v15.2.6 mechanizm: wciąga ostatni komentarz). Wstecz-kompatybilne — jeśli komuś pasuje stary flow, może go używać.
- **Bot cleanup `git push` fail (np. race z innym pushem na main między checkoutem boota a jego pushem, lub brak `contents: write`)**: komentarz/close/lock już przeszły (issue zamknięty user-facing). Plik wisi w repo — usuń ręcznie: `git rm pending_answer.md && git commit -m "cleanup answer-bot fail" && git push`.
- **Równoległe issue z question**: bot trzyma jeden plik per repo, więc obsługuj jedno question-issue na raz. Drugie czeka aż pierwsze się zamknie (cleanup boota zwolni plik).
- **Bug-issue zamknięte przez question-flow przez pomyłkę**: nie. Bug-issue ma flag `bug` i workflow `patch-bot` (`tiflotecnia-patch`) lub `issue-closure` (`fixed-in-release`). Question-flow wyzwala TYLKO `answered`. Etykiety są disjunktywne — nie nadawaj `answered` na bug-issue.

# SPRZĄTANIE (HIGIENA REPOZYTORIUM)
- Zawsze po skończonej weryfikacji usuwaj wszystkie pliki tymczasowe (np. pliki z logami lub testami jednostkowymi).
- Weryfikuj porządek przez komendę `git status` patrząc na nieśledzone pliki (Untracked files).
- Commity pośrednie: Możesz, a nawet powinieneś, wykonywać commity po zakończeniu poprawnie działającego małego podetapu dużej rewizji z tagiem "WIP".
- ZAWSZE zrób review (`git --no-pager diff`) zanim zapiszesz stan na stałe w repozytorium.