# ŚRODOWISKO I ARCHITEKTURA (WXPYTHON)
- Projekt jest w pełni oparty o framework wxPython (natywne GUI desktopowe), z naciskiem na maksymalną dostępność dla czytników ekranu (A11y, np. NVDA). Punkt wejścia to `main.py`.
- KOD OBIEKTOWY: Logika podzielona na klasy dziedziczące po `wx.Frame` (`main.py`) i `wx.Panel` (`gui_*.py`). Unikaj kodu proceduralnego.
- ACCESSIBILITY FIRST: Zawsze dbaj o intuicyjną nawigację z klawiatury. Używaj Sizerów i wstrzymuj się z tworzeniem własnych, niestandardowych kontrolek, jeśli systemowe spełniają zadanie.
- SEED vs USER DATA (od 15.3): `dictionaries/` to seed (single source dla silnika, commitowana, wchodzi do paczki release). `runtime/`, `skrypty/`, `opowiesci/` (root), `*.env` to user data — gitignored, poza paczką release. `runtime/skrypty/*.mode` to per-projekt metadane (ukryte przed end-userem).
- KOMUNIKACJA Z UŻYTKOWNIKIEM (A11y): Krótkie jednorazowe powiadomienia (sukcesy, błędy) → `wx.MessageBox`. Długie komunikaty techniczne → dialog `wx.Dialog` z `wx.TextCtrl` (TE_READONLY) i przyciskiem „Zamknij". Unikaj wzorca „aktualizuj etykietę i ustaw fokus" jako głównego sposobu notyfikowania użytkownika.

# ZARZĄDZANIE TERMINALEM I TESTOWANIEM (BASH & A11y)
- Masz pełny dostęp do terminala (Git Bash) i plików. Możesz swobodnie korzystać ze składni uniksowej, ale MUSISZ przestrzegać poniższych reguł:
1. ŚRODOWISKO WIRTUALNE (BASH): Bash nie honoruje automatycznej aktywacji `.venv` przez VS Code. Zawsze używaj pełnej ścieżki uniksowej do interpretera venv: `.venv/Scripts/python -c "..."` albo `.venv/Scripts/python -m pytest ...`. Analogicznie dla menedżera pakietów: `.venv/Scripts/pip install ...`.
2. ZAKAZ BLOKOWANIA TERMINALA (KRYTYCZNE A11y): Pod żadnym pozorem nie uruchamiaj aplikacji GUI w sposób ciągły (np. z aktywnym `app.MainLoop()`). Spowoduje to całkowite zawieszenie procesu i zablokuje nawigację czytnikiem ekranu. Testuj logikę wykonując izolowane fragmenty, które kończą się natychmiast.
3. BEZPIECZNE TESTY WXPYTHON (BEZ MAINLOOP): Żeby sprawdzić interfejs bez blokowania terminala, stosuj wzorzec z obejściem pętli zdarzeń : `app = wx.App(False)`, wywołaj konstruktor, a następnie użyj `frame.Destroy()`. Omija to `MainLoop()` i okno zamyka się natychmiastowo po sprawdzeniu struktury.
4. KRYTYCZNE ZABEZPIECZENIE: Masz CAŁKOWITY ZAKAZ uruchamiania czegokolwiek z folderu `runtime/` do testowania kodu.
5. FLAGA `--no-pager` W GIT (KRYTYCZNE A11y): Komendy git, które mogą uruchomić stronicowanie (np. `git diff`, `git log`, `git show`), ZAWSZE wykonuj z flagą `--no-pager`. Brak tej flagi uruchamia tryb interaktywny, blokujący terminal i generujący artefakty niedostępne dla NVDA.
6. GIT STATUS PRZED COMMITEM: Przed każdym commitowaniem i dodawaniem plików ZAWSZE uruchom `git status`, aby zobaczyć pełny stan repozytorium.
7. KLUCZ OPENAI DOSTĘPNY: `golden_key.env` w roocie repo jest gitignorowany, ale fizycznie obecny u dewelopera. Skrypty `buduj_wielojezyczne_ui.py`, `buduj_wielojezyczne_docs.py`, `tlumacz_ai.py` ładują klucz przez `python-dotenv` → `os.environ["OPENAI_API_KEY"]`. Agent **może i powinien** odpalać te skrypty bezpośrednio — nie przekazuj tego kroku użytkownikowi „bo nie masz API". Stop tylko gdy skrypt zwróci „❌ Brak prawidłowego OPENAI_API_KEY" lub HTTP 401/429 — wtedy poproś usera o uzupełnienie. Po auto-tłumaczeniach ZAWSZE manualny review halucynacji — generyczne sanity checki + szczegółowe hotspoty per szyfr/sekcja w [[reguly_tlumaczen]].
8. KOMUNIKACJA Z UŻYTKOWNIKIEM (od 2026-06-02 — czysty PowerShell, A11y). Pełne reguły → [[reguly_architektury]]. Skrót:
   - **Pytania są MILE WIDZIANE** — dziel proces na kroki z punktami decyzyjnymi, pytaj otwartym tekstem. AskUserQuestion dozwolone (stary „całkowity zakaz" z czasów zepsutego accessibility buffer VS Code został ZNIESIONY 2026-06-02; domyślnie i tak preferuj pytania otwartym tekstem, chyba że user wprost poprosi o menu).
   - **Terminal = tylko krótkie treści** (próg ≈2500 znaków): podsumowania + pytania o zgodę na kolejny krok. Długie raporty / plany / duże bloki kodu → `skrypty/ai_odpowiedz.txt` (Write/Edit), w terminalu zostaw notę „zaktualizowałem plik" (user otworzy w edytorze VS Code z natywnym A11y).
   - **Drafty odpowiedzi na issue** → `pending_answer.md`; commit message / release notes do wklejenia → `commit_msg.txt`. Nie proś o kopiowanie z output'u terminala — pisz do pliku i wskazuj ścieżkę.

# ZARZĄDZANIE LIMITAMI KONTEKSTU (TOKENY)
- Narzędzie może się bezgłośnie zamrozić przy próbie nadpisania zbyt wielkiego pliku.
1. PRACA ETAPOWA: Nigdy nie próbuj przepisać całego pliku w jednym kroku.
2. DELTA UPDATES: Przy niewielkich zmianach używaj precyzyjnych narzędzi edycji zamiast wypisywać plik w całości na nowo.
3. Duży refaktor dziel etapami (np. krok 1: klasa/UI, krok 2: zdarzenia, krok 3: skomplikowana logika).

**TRÓJWARSTWOWY MODEL PAMIĘCI AGENTA (KRYTYCZNE)**
Pamięć agenta jest podzielona na trzy warstwy z różnymi celami i sposobami ładowania:
- **CLAUDE.md = Konstytucja** (ten plik): żelazne zasady środowiskowe (A11y, wxPython, terminal), główny cykl wydawniczy (happy path) i drogowskazy do pozostałych warstw. Ładowany przy KAŻDYM, najmniejszym zadaniu. MUSI być jak najlżejszy — bezwzględny limit miękki 25k znaków, twardy 35k.
- **`claude_archive.md` = Muzeum**: grube post-mortemy, długie historie incydentów (np. halucynacja fi/manual.yaml 2026-05-15, incydent #13 GitHub auto-close 2026-05-16), pełne zapisy starych obejść (np. heurystyka force-push tag v15.2.7 sprzed atomic-reset) oraz zarchiwizowane roadmapy zamkniętych wydań (13.7 → v16.0). Śledzony w repo. **ŻELAZNA ZASADA: `claude_archive.md` to ZAMKNIĘTE archiwum historyczne. MASZ KATEGORYCZNY ZAKAZ ładowania go do kontekstu i czytania jego zawartości na start — chyba że użytkownik wyda bezpośredni rozkaz „przeszukaj archiwum".** Zapis (dopisywanie zarchiwizowanych sekcji) jest dozwolony bez tego rozkazu; zakaz dotyczy CZYTANIA.
- **`memory/*.md` = Podświadomość**: techniczne niuanse, lessons learned, ścieżki awaryjne — skonsolidowane w **4 tematycznych filarach**: [[reguly_tlumaczen]] (autotłumacz/halucynacje/literały/słowniki), [[reguly_github_bot]] (boty, atomic-reset, zakaz auto-close), [[reguly_git_workflow]] (direct-to-main, force-push tagów, iteracyjne patche), [[reguly_architektury]] (prompty YAML, kolejność akcentów, runtime niewidoczny, model per tryb, staging, komunikacja). Lokalne pliki narzędzia (poza repo), `MEMORY.md` ładowany automatycznie jako indeks tych filarów, podpliki czytane po referencji `[[name]]`. **ŻELAZNA ZASADA ANTY-ROZMNAŻANIA: nowy lesson learned DOPISUJ jako sekcję `##` do pasującego filaru — NIE twórz nowych mikro-plików `feedback_*.md`. Nowy filar zakładaj tylko gdy temat nie mieści się w żadnym z czterech, i wtedy dodaj jego link do `MEMORY.md`.**

**Autokontrola rozmiaru CLAUDE.md:** monitoruj rozmiar przed każdą modyfikacją. Przy zbliżeniu do 25k znaków (miękki) / 35k (twardy) uruchom CLEANUP: (1) klasyfikuj sekcje — post-mortemy → `claude_archive.md`, fixy/lessons learned/CI-CD niuanse → DOPISZ jako sekcję `##` do pasującego filaru `memory/reguly_*.md` (zgodnie z zasadą anty-rozmnażania — NIE twórz nowych mikro-plików), reguły A11y/wxPython/release happy path → zostają; (2) przenieś zachowując treść 1:1; (3) `MEMORY.md` aktualizuj tylko gdy powstał nowy filar; (4) w miejscu przeniesionych sekcji zostaw drogowskaz (`patrz [[reguly_<filar>]]` lub `→ claude_archive.md`); (5) krótki raport co/gdzie/dlaczego + poproś usera o zatwierdzenie PRZED commitem.

# NUMER WERSJI APLIKACJI (od 13.4)
- POJEDYNCZE źródło prawdy: plik `VERSION` w roocie repozytorium (plain text, np. `13.4-WIP` lub `13.4`). Bumpa robisz **wyłącznie tam** — wszystkie inne miejsca rozwijają tę wartość automatycznie.
- W każdym `dictionaries/<kod>/gui/ui.yaml::app.wersja` siedzi templated string typu `"{numer_wersji} – Wersja Wydawnicza"`. Per-language tłumaczysz tylko natywny sufiks (Wersja Wydawnicza / Release Edition / Julkaisuversio / Útgáfuútgáfa / Versione di Rilascio / Издательская версия) — **nie dotykasz numeru** ani placeholdera.
- Mechanizm: `i18n.t()` auto-wstrzykuje kwarg `numer_wersji=` z pliku VERSION przy każdym wywołaniu, a `generuj_dokumentacje._rozwin_placeholdery` robi ten sam replace dla docs/. `build_release.odczytaj_wersje()` czyta `VERSION` plain-textem i podaje go do `iscc /DMyAppVersion=...`.
- Jeśli zobaczysz w GUI „?" zamiast numeru — brakuje pliku VERSION (przy jego braku `i18n.NUMER_WERSJI` fallbackuje na `"?"`, żeby aplikacja nie wywaliła się przy starcie).

# WIELOJĘZYCZNOŚĆ I TŁUMACZENIA INTERFEJSU
- Stan post-14.0: 9 w pełni wdrożonych paczek językowych w `dictionaries/`: `pl en de es fi fr is it ru`. Roadmapa wielojęzycznościowa zamknięta — historia wdrożeń (13.3 EN → 14.0 ES, jeden język na minor) jest w `git log` + commitach release'owych.
- Bezpieczna kolejność wdrażania nowego języka (gdyby pojawił się 10. język w 15.x+): najpierw paczka treściowa (`podstawy.yaml` + `akcenty/` + `szyfry/` + `rezyser/` + `opowiesci/`, to ostatnie ręcznie bez batch — [[reguly_architektury]]), potem `gui/ui.yaml` (autotłumacz), potem `gui/dokumentacja/*.yaml` (autotłumacz), na końcu release.
- Reguła natywności (parytet paczek; N=9 wdrożonych): `akcenty/` = `N-1` obcych + 3 narzędzia (`oczyszczenie`, `oczyszczenie_bez_liczb`, `naprawiacz_tagow`) = **N+2 plików** (dziś 11). `szyfry/` 6, `rezyser/` 4, `opowiesci/` 8 (`baza`, `cinematic_warning`, `streszczenie`, `tryb_burza`, `tryb_mniejsze_zlo`, `tryb_swobodny`, `tryb_wyborow`, `zaczatki`) — niezmienne od N. Silnik nie egzekwuje liczb (≥1 per podfolder + crosscheck pl/en, patrz niżej), ale parytet trzymaj — np. szwedzki (N=10) wymusza akcent `sv` w 9 starych paczkach + 9 obcych w `sv/akcenty/` = 12 plików per paczka.
- WYMÓG SILNIKA (`core_poliglota._jezyk_kompletny`; 13.9, rozszerzony 15.3): `<kod>/` wymaga `podstawy.yaml` + `gui/ui.yaml` + min. **1 pliku** w każdym z czterech podfolderów językowych (`akcenty/`, `szyfry/`, `rezyser/`, `opowiesci/` — `opowiesci/` dodany w 15.3 razem z `_zaladuj_przepis` fallbackiem pl→en). Bazy referencyjne **pl i en** dodatkowo crosscheckują zestaw plików 1:1 (poza akcentami obcojęzycznymi — z natury per-natywność różne); rozjazd → oba filtrowane, system krytycznie niekompletny. Patrz [[reguly_tlumaczen]]. Stuby filtruje `dostepne_jezyki_bazowe()`. Po zmianie pliku w `rezyser/` lub `akcenty/` uruchom `odswiez_rezysera.py`.
- Tłumaczenia interfejsu rezydują w dedykowanym pliku: `dictionaries/<kod>/gui/ui.yaml`. ZAKAZ hardkodowania etykiet GUI w kodzie źródłowym Pythona.
- Parametry dynamiczne takie jak `{nazwa_projektu}`, `{liczba_znakow}`, `{min_przesuniecie}` pozostaw w tłumaczeniach nienaruszone. Nie tłumacz literałów technicznych i rozszerzeń (np. `.md`, `skrypty/`) ani nie usuwaj emoji zachowując ich ścisłą pozycję.
- Konwencje wxPython w i18n:
 * Akceleratory (Znak `&`): Należy zachować i przesunąć na dostępną literę pasującą w danym języku.
 * Skróty klawiszowe w menu (`\tCtrl+...`): Zachowaj je w oryginale we wszystkich językach bez dokonywania lokalizacji terminów jak Shift czy Alt.
 * Długie komunikaty błędów zachowują bezwzględnie wszystkie białe znaki (`\n`), co warunkuje właściwe łamanie tekstu.
 * Rozróżniaj klucze: Tooltip i etykieta to dwa osobne klucze dla jednego obiektu.
- Skrypt autotłumaczący z użyciem modelu (`tlumacz_ai.py`) zamraża podmieniane zmienne `{...}`, aby LLM nie naruszył struktury programu.
- Manager Reguł skanuje pliki YAML z folderów `akcenty`, `szyfry`, `rezyser`, `opowiesci` i `gui` (piąty `opowiesci/` od 15.2.4). Tworzenie nowego języka generuje wszystkie cztery podfoldery językowe naraz — dispatch silnika nie wystartuje bez `rezyser/` (wymóg ≥1 trybu).
- Pułapka kolejności w `akcenty/<kod>.yaml` (silnik aplikuje `zamiany:` SEKWENCYJNIE przez `str.replace`): patrz [[reguly_architektury]].

# ZAMYKANIE RELEASU — DOKUMENTACJA (KRYTYCZNE)
`build_release.py` wywołuje `generuj_dokumentacje.generuj()` wewnętrznie, co zostawia niezcommitowane `docs/*.txt` w repo po buildzie. Żeby tego uniknąć — wygeneruj i zcommituj docs **ręcznie** przed commit'em release'u. Stosuj przy każdej zmianie z listy: nowy język, nowa funkcja w manualach, zmiana liczby akcentów/szyfrów/trybów, bump VERSION.

## Procedura (w tej kolejności)

### Krok 0a — Bump VERSION (KRYTYCZNE: PRZED jakąkolwiek regeneracją docs!)
Zaktualizuj `VERSION` w roocie (np. 13.9 → 14.0). `generuj_dokumentacje.py` rozwija `{numer_wersji}` z VERSION przy KAŻDYM wywołaniu — bez tego kroku `build_release.py` wewnętrznie regeneruje docs z docelowym numerem i zostawia niezcommitowany diff `modified: docs/manual.<iso>.txt × 8`. Sam VERSION zcommitujesz razem z release commit'em w Kroku 4.

### Krok 0b — Odśwież reżysera (ZAWSZE po dodaniu/usunięciu pliku akcent*.yaml)
`.venv/Scripts/python odswiez_rezysera.py` skanuje `dictionaries/*/akcenty/` i regeneruje dwa bloki: `core_poliglota.py` (docstringi wrapperów `akcent_*`) i `core_rezyser.py` (importy + słownik `_AKCENT_FUNCS`). Bez tego Poliglota działa (czyta YAML), ale Reżyser nakładający akcenty po regexach Księgi Świata — nie (dispatch nie zna nowych plików). Sprawdź output: każdy nowy akcent musi pojawić się na liście. Jeśli `core_poliglota.py` / `core_rezyser.py` mają zmiany — zcommituj przed Krokiem 1.

### Krok 1 — Przejrzyj i zaktualizuj szablony źródłowe
Szablony `dictionaries/<kod>/gui/dokumentacja/*.yaml` dla każdego z 9 wdrożonych języków. Istniejące szablony edytuj **ręcznie w danym języku** — autotłumacza NIE uruchamiaj na plikach które już istnieją (koszt API + halucynacje LLM).

Dla każdego szablonu sprawdź: opis nowych funkcji aktualny i przetłumaczony, stare „w przyszłości pojawi się X" usunięte, liczby (`liczba_akcentow_jezykowych`) są placeholderami nie hardkodami, usunięte/przemianowane elementy GUI nie mają już akapitów. Wzorzec edycji: najpierw `pl/`, potem ta sama zmiana w każdym obcym z zachowaniem istniejącego stylu.

**Autotłumacz (`buduj_wielojezyczne_docs.py`) — TYLKO dla zupełnie nowych plików szablonów**. Po AI-tłumaczeniu obowiązkowy review halucynacji: generyczne sanity checki + szczegółowe hotspoty w [[reguly_tlumaczen]].

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
`build_release.py` wywołuje `generuj()` wewnętrznie (paczka ZIP zawsze ma świeże docs). Po prawidłowym pre-commicie (Krok 0a → 2 → 4) `git status` po buildzie pokaże „nothing to commit". Jeśli pokazuje `modified: docs/manual.<iso>.txt` — Krok 0a (bump VERSION przed regeneracją) został pominięty; zrób fixup commit „docs: bump numer wersji w docs/".

# WORKFLOW RELEASE — direct-to-main, bez PR-ów (od v15.2.5)
Solo-dev + A11y first: commit prosto na main, tag tworzony atomowo przez web Release UI (lub bota `draft-release.yml`). PR/branch flow porzucone w v15.2.5 [[reguly_git_workflow]]. `RELEASE_NOTES.md` = single source of truth dla treści Release description (NIE GitHub auto-generator `Full Changelog: …compare/X...Y` — nasza ręczna narracja z diagnozą bugów + tradeoff'ami jest cenniejsza).

## Procedura release (każdy patch X.Y.(Z+1))
1. Krok 0a-0b z `# ZAMYKANIE RELEASU` (bump VERSION + odśwież reżysera).
2. Edytuj `RELEASE_NOTES.md`: zaktualizuj numer wersji w nagłówku (linia 1), dodaj nowy `*Patch v<wersja>: ...*` jako pierwszy paragraph streszczeń przed `---`, dodaj sekcję `## <wersja> — patch release ...` po `---` (przed poprzednią). Struktura: TL;DR (3-4 akapity narracyjne) → Co nowego → Pod maską → Co nie weszło → Walidacja.
3. Regeneracja + commit docs (Kroki 1-3 z `# ZAMYKANIE RELEASU`). Single release commit (docs/ + RELEASE_NOTES.md + VERSION + szablony + opcjonalnie kod) preferowany dla zwykłych patchy — czytelniejsza historia.
4. Commit message: `v<wersja>: <jednolinijkowy opis>` w nagłówku, body bullet list głównych zmian. Wzorzec: `git --no-pager show <ostatni tag> --stat | head -5` dla podobnego patcha. **KRYTYCZNE: ZAKAZ GitHub auto-close keywords + `#N`** w commit message (`fix #N`, `closes #N`, itd.) gdy issue ma być zamknięte przez bot workflow `issue-closure.yml` — patrz [[reguly_github_bot]] (lista keywordów + bezpieczne alternatywy: `(re: #N)`, `(addresses #N)`, „mentions #N").
5. `git push origin main`.
6. Web GitHub → Actions → workflow „Draft Release (auto-tag + RELEASE_NOTES.md sekcja → draft)" → Run workflow → input `potwierdz=tak` → Run. Bot odczytuje VERSION, sprawdza brak duplikatu tagu, tworzy tag na HEAD origin/main, wyciąga sekcję `## <wersja>` z `RELEASE_NOTES.md` i tworzy draft Release z tytułem „Reżyser Audio GPT, wersja <wersja>". Workflow zatrzymuje się na draftcie — Publish dopiero po upload EXE w kroku 7. Szyba bezpieczeństwa: input `potwierdz` musi być dokładnie „tak". Alternatywnie agent: `gh workflow run draft-release.yml -f potwierdz=tak` [[reguly_git_workflow]].
7. Web GitHub → Releases → wybierz draft → upload `Rezyser_Audio_v<wersja>_Installer.exe` → Publish. Agent: `gh release upload v<wersja> <plik.exe>` + `gh release edit v<wersja> --draft=false`.

## Force push w tym repo — co dozwolone
Force push do MAIN/MASTER przez maintainera = zakazany. Dwa dopuszczalne wyjątki:
- **(a) tag-only post-publish** jako fallback gdy bot answer-flow musiał użyć cleanup commit zamiast atomic-reset — patrz [[reguly_git_workflow]].
- **(b) branch-only przez `github-actions[bot]`** w `issue-closure.yml` przy atomic-reset `pending_answer.md` (warunki konieczne) — patrz [[reguly_github_bot]].

## Czego nie robić
- NIE twórz feature branchy dla zwykłych patchy. Wszystko bezpośrednio na main. Rzadkie wyjątki (duży refaktor wielo-patchowy, eksperymentalna gałąź, PR od kontrybutora zewnętrznego) → `claude_archive.md`.
- NIE używaj `gh pr create/merge` / `git tag` lokalnie do TWORZENIA tagów. Nowe tagi powstają WYŁĄCZNIE przez web Release UI atomowo z Release (wyjątek: force-push tag-only fallback z [[reguly_git_workflow]]).
- NIE polegaj na `PULL_REQUEST_COMMENTS.md` (usunięty v15.2.5). Komentarze recenzentskie trafiają wprost do `RELEASE_NOTES.md::<wersja>::Co nie weszło` lub do konwersacji z agentem.

## Klauzula awaryjna: bug-issue ma pierwszeństwo nad planowaną treścią
Nowy bug-issue od prawdziwego usera = **priorytet** nad planowaną treścią. Procedura: odłóż feature na następny cykl (przepisz `RELEASE_NOTES.md::Co nie weszło`), bumpuj X.Y.(Z+1) [[reguly_git_workflow]], patch rozwiązuje TYLKO bug (lub grupę powiązanych z jednego obszaru), po Release nadaj etykietę `fixed-in-release` przez web UI (bot zamyka). Wyjątek: bug niewykonalny w jednym patchu (wymaga refaktoru) → przeetykietuj `bug` → `enhancement` z komentarzem wyjaśniającym workaround + plan strukturalny.

# OBIEG ZGŁOSZEŃ Z POŁUDNIA NA PÓŁNOC — INTERPRETACJA PROMPTU SAMI (od v15.2.8 trójsekcyjny)
Sami (`.github/scripts/issue_intake_sami.py`, etap Południe) odbiera każde nowe GitHub Issue (eventy `opened` lub `labeled` z akceptowalną etykietą — patrz `LABELS_ACCEPT` / `LABELS_IGNORE` w skrypcie) i wysyła do Centrum mail w plain text o standardowej **trójsekcyjnej** strukturze:

1. **PROMPT DLA AGENTA AI** — wygenerowany przez `gpt-4o-mini` wg `SAMI_SYSTEM_PROMPT`. Format zależy od etykiet:
   * **TRYB A — question / help wanted** (etykiety zawierają TYLKO `question` i/lub `help wanted`, BEZ `bug`/`enhancement`/`documentation`):
     dokładnie 2 sekcje: `## Cel pytania` + `## Co agent powinien zrobić`. Agent czyta i odpowiada przez `pending_answer.md` (patrz `# ODPOWIEDZI NA ISSUE`).
   * **TRYB B — zmiana w kodzie** (etykiety zawierają `bug`, `enhancement`, `documentation` lub `invalid`, nawet w kombinacji z question/help wanted):
     dokładnie 4 sekcje: `## Cel` + `## Kontekst techniczny` + `## Kryteria akceptacji` + `## Pułapki do uniknięcia`. Agent implementuje fix.

2. **ORYGINALNY TEKST ZGŁOSZENIA (do weryfikacji)** — surowy `title + body` z GitHub. ZAWSZE porównuj prompt z oryginałem przed implementacją — oryginał = źródło prawdy, prompt = sugestia LLM.

3. **OTWARTE ISSUES W REPO (snapshot z momentu intake)** — output `gh issue list --state open --limit 50` (od v15.2.8). Użycie: detekcja duplikatów, scalanie powiązanych bugów w jeden patch (klauzula awaryjna `# WORKFLOW RELEASE`), priorytet vs planowany feature.

## Sygnał rozpoznawczy
Input maintainera otwierający się od `## Cel pytania` / `## Cel` z 2 lub 4 sekcjami, potem separator `==========…` i `ORYGINALNY TEKST ZGŁOSZENIA`, potem separator i `OTWARTE ISSUES W REPO` — to obieg „Z Południa na Północ". Twoja rola = **Centrum**. Decyzja TRYB A vs TRYB B z liczby sekcji + etykiet (linia „Etykiety:" w nagłówku maila).

## Pułapki interpretacji
Trzy non-obvious'y (halucynacja LLM w sekcji „Pułapki do uniknięcia", tryb FALLBACK bez TRYB A/B, pusta sekcja OTWARTE ISSUES) → [[reguly_github_bot]].

# ODPOWIEDZI NA ISSUE — question-flow z pliku (FILE mode + atomic-reset)
Maintainer zapisuje draft jako `pending_answer.md` (Write/Edit, bez kopiowania z terminala), pushuje atomowo na main, nadaje etykietę `answered`. Bot (`issue_closure_north.py`) wczytuje Z PLIKU (eliminuje race condition trzeciego komentującego), opakowuje w wrapper Lumi/Vieno/Katla, publikuje + zamyka + lockuje issue, wymazuje draft z historii przez atomic-reset (`git reset --hard HEAD~1` + `git push --force-with-lease`). Warunek atomic-reset: HEAD = commit dodający DOKŁADNIE jeden plik `pending_answer.md`. Niespełniony → fallback cleanup commit boota. Historia ewolucji v15.2.6→v15.2.7→v15.2.8 → `claude_archive.md`.

## Procedura — flow czystego question (issue NIE wymaga release)
1. Stwórz/zaktualizuj `pending_answer.md` w roocie repo — czysta odpowiedź merytoryczna w języku oryginalnego zgłoszenia (markdown OK), BEZ podpisu maintainera (wrapper dopisuje swój).
2. `git add pending_answer.md && git commit -m "answer: draft odpowiedzi na #<N>" && git push origin main`. **KRYTYCZNE: ten commit musi być ATOMOWY** (TYLKO `pending_answer.md`). Inne zmiany (np. lessons learned w CLAUDE.md) zcommituj PRZED `pending_answer.md` jako osobny commit.
3. Web GitHub UI → nadaj etykietę `answered` na issue #N. Workflow `issue-closure.yml` (job `zamknij_z_polnocy`) odpala się przez webhook `issues.labeled`.
4. Bot wykrywa `pending_answer.md` → tryb FILE: wczytuje, opakowuje w persona-template per język, `gh issue comment/close/lock`. Następnie sprawdza atomowość HEAD: atomowy → atomic-reset (draft wymazany z historii), nieatomowy → fallback cleanup commit (autor `github-actions[bot]`).
5. Lokalnie po workflow: `git fetch origin && git reset --hard origin/main` (NIE `git pull` — atomic-reset rewrite'uje historię origin, `git pull` zacznie histeryzować non-fast-forward).

## Sub-procedury bug+answer (release-then-answer, release-with-answer)
Gdy issue wymaga release'u + komentarza/dolepka osobistej wiadomości — wybór ścieżki:
- **release-then-answer**: bug fix + osobny komentarz BEZ linku do Release. Zamykane przez `answered`. Release commit i `pending_answer.md` commit są ROZBITE na osobne pushe, między nimi publikacja Release (tag wskazuje na czysty release commit). Rzadkie.
- **release-with-answer** (od v15.2.8): bug-issue + dolepek osobistej wiadomości (tip o recovery, przeprosiny). Zamykane przez `fixed-in-release` z FILE mode boota (dolepia treść `pending_answer.md` pod TEMPLATES separatorem `---`). KRYTYCZNE: tag musi wskazywać na release commit, NIE na pending_answer.md commit — sprawdź SHA w Web UI.

Pełne procedury obu sub-flow'ów (kroki + komendy) → `claude_archive.md`.

## Sytuacje brzegowe
3 warunki konieczne dla preferowanej ścieżki atomic-reset (atomowość HEAD, `fetch-depth: 2`, `contents: write`), równoległość issues, etykiety disjunktywne `answered`/`fixed-in-release`, edge case'y pliku w trybach FILE/COMMENT, fail force-with-lease, fail push bota → [[reguly_github_bot]]. Pełne sub-procedury release-then-answer i release-with-answer z komendami → `claude_archive.md`.

# SPRZĄTANIE (HIGIENA REPOZYTORIUM)
- Zawsze po skończonej weryfikacji usuwaj wszystkie pliki tymczasowe (np. pliki z logami lub testami jednostkowymi).
- Weryfikuj porządek przez komendę `git status` patrząc na nieśledzone pliki (Untracked files).
- Commity pośrednie: Możesz, a nawet powinieneś, wykonywać commity po zakończeniu poprawnie działającego małego podetapu dużej rewizji z tagiem "WIP".
- ZAWSZE zrób review (`git --no-pager diff`) zanim zapiszesz stan na stałe w repozytorium.

# DROGOWSKAZY DO POZOSTAŁYCH WARSTW PAMIĘCI

**`claude_archive.md` (Muzeum, w repo)** — grube post-mortemy, pełne stare obejścia i zarchiwizowane roadmapy zamkniętych wydań (13.7 → v16.0). Główne sekcje: incydent halucynacji fi/manual.yaml (2026-05-15), incydent #13 GitHub auto-close keywords (2026-05-16), pełna heurystyka „cleanup commit boota = force-push tag" (v15.2.7 fallback), ewolucja question-flow v15.2.6 → v15.2.8, sub-procedury release-then-answer i release-with-answer, edge case'y `pending_answer.md`, wyjątki feature-branch workflowu, przykład empiryczny ES `ñ → nj`, CMENTARZYSKO ROADMAP. **KATEGORYCZNY ZAKAZ czytania/ładowania na start — sięgaj tam WYŁĄCZNIE na bezpośredni rozkaz użytkownika „przeszukaj archiwum".**

**`MEMORY.md` + `memory/*.md` (Podświadomość, poza repo, auto-load)** — techniczne niuanse, lessons learned, ścieżki awaryjne w 4 filarach. Indeks w `MEMORY.md`, filary czytane po referencji `[[name]]`:
- [[reguly_tlumaczen]] — autotłumacz, review halucynacji (Caesar/Tipoglicemia/fiolka/PL-leak), generyczne sanity-checki, literały kod-vs-`ui.yaml`, idiomatyczna lokalizacja nazw, pl/en bazy referencyjne, review marki w templatkach.
- [[reguly_github_bot]] — atomic-reset (3 warunki + edge case'y answer-flow), ZAKAZ auto-close keywords (fix/closes/resolves przed #N), env-zamiast-argv w workflowach, interpretacja promptu Sami.
- [[reguly_git_workflow]] — direct-to-main, hotfix = patch tag, iteracyjny patch przez force-push rewrite, force-push tag-only post-publish, gh CLI release-flow.
- [[reguly_architektury]] — prompty LLM w YAML (ręcznie), sekwencyjność `str.replace` w akcentach, `runtime/` niewidoczny, model per tryb Opowieści, staging + maskowanie, komunikacja (pytania mile widziane).