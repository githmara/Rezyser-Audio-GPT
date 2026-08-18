# Reżyser Audio GPT

**Hybrydowe Studio Nagraniowe dla Słuchowisk, Audiobooków i Interaktywnych Opowieści**

**Inne wersje językowe / Other languages:** [English](readme.md) · [Deutsch](readme.de.md) · [Español](readme.es.md) · [Suomi](readme.fi.md) · [Français](readme.fr.md) · [Íslenska](readme.is.md) · [Italiano](readme.it.md) · [Polski](readme.pl.md) · [Русский](readme.ru.md)


Zestaw samowystarczalnych narzędzi napędzanych przez AI do automatycznego pisania, planowania, formatowania i tłumaczenia obszernych skryptów oraz prowadzenia interaktywnych gier tekstowych. Projekt jest natywną aplikacją desktopową (wxPython) zaprojektowaną od podstaw z myślą o pełnej dostępności dla czytników ekranu (NVDA, VoiceOver) i współpracy z profesjonalnymi syntezatorami mowy (TTS). Działa bez przeglądarki i bez lokalnego serwera — uruchamia się jako zwykłe okno programu.

Wersja: **18.19.0** · Wspierane języki natywnie (9): Polski, Deutsch, English, Español, Suomi, Français, Íslenska, Italiano, Русский.


## Główne moduły

Aplikacja łączy w jednym oknie pięć narzędzi przełączanych skrótami klawiaturowymi (Ctrl+1 / Ctrl+2 / Ctrl+3 / Ctrl+4 / Ctrl+5) lub przyciskami na pasku narzędzi. Każdy moduł działa niezależnie, ale wszystkie współdzielą paczki słowników z folderu `dictionaries/` (akcenty, szyfry, tryby twórcze AI) i centralne ustawienia.


### 1. Reżyseria (Ctrl+1)

Główne studio do pisania słuchowisk i audiobooków. Wybierasz tryb — Burza Mózgów, Skrypt (z tagami `[SFX]`/`[Postać: emocja]`), Audiobook (tradycyjna proza) — i kierujesz dialog z modelem przez pole Instrukcji + Księgi Świata + Pamięci Długotrwałej:

* **Wieloprojektowa Księga Świata:** System automatycznie ładuje w tle dedykowane zasady uniwersum (`.md`) na podstawie aktywnego pliku źródłowego, zapewniając pełną izolację (zero-click context loading).
* **Akumulator Fabuły:** Algorytm „nieskończonej pamięci". Streszczenie fabuły generuje osobne narzędzie postprodukcji (od v18.13), a gdy wskaźnik pamięci wejdzie w stan czerwonego alarmu, system uruchamia je sam i zapisuje wynik do pliku oraz do pola Pamięci Długotrwałej. Kolejne streszczenia są przyrostowe — model dostaje poprzednią pamięć i tylko nową część narracji.
* **Przepisy Reżysera (liczba plików: 6):** Każdy z plików w `dictionaries/<jzk>/rezyser/` opisuje osobną „personalność" reżysera AI (Burza Mózgów, Skrypt, Audiobook) albo narzędzie postprodukcji (Tytuły Rozdziałów, Pamięć Długotrwała). Możesz dostroić ich brzmienie bez programowania — patrz Manager Reguł niżej.


### 2. Opowieści (Ctrl+5, drugi główny tryb od v15.0)

Interaktywne gry tekstowe prowadzone przez AI w roli silnika narracyjnego. W odróżnieniu od Reżyserii (gdzie generujesz gotowy audiobook), Opowieści to tura-po-turze dynamiczna fabuła:

* **Tryb Wyborów:** każda tura kończy się 3-5 ponumerowanymi opcjami A-E. Najbardziej intuicyjny tryb dla niewidomych graczy — NVDA czyta opcje, klikasz Tab i Enter.
* **Tryb Mniejsze Zło:** jak Wybory, ale każda opcja jest niekorzystna moralnie, fizycznie lub strategicznie. Od v15.2 dodatkowa „fiolka" — reusable ZERO-numerowana opcja desperackiego ratunku, której efekty są pseudolosowe (60% szkodliwe / 30% zaburzające percepcję / 10% rzadko-korzystne, rozkład wymuszany Pythonem, LLM nie ma jak wymyślić zbawiennego skutku).
* **Tryb Swobodny:** dowolna akcja wolnym tekstem („spróbuję otworzyć drzwi"), silnik proponuje 1-3 sugestie ale nie wymusza wyboru.
* **Jeden model AI dla wszystkich trybów:** od v18.1 wszystkie tryby Opowieści korzystają z tego samego, wspólnego modelu (domyślnie i zalecanie Anthropic Claude Sonnet 5) — mocniejszy model rygorystycznie trzyma się zasad świata (kluczowe zwłaszcza w trybie Mniejsze Zło, gdzie każda opcja musi być realnie niekorzystna).


### 3. Poliglota (Ctrl+2, Tłumacz AI + Akcenty TTS)

* **Bezpieczny Tłumacz:** Długie teksty są automatycznie dzielone na bloki mierzone w tokenach modelu (bezpieczne także dla języków o gęstym zapisie, np. chińskiego) i tłumaczone sekwencyjnie; ucięta odpowiedź modelu jest wykrywana i ponawiana na mniejszych fragmentach. Każdy blok jest natychmiast zapisywany do ukrytego pliku `.jsonl`. Wznowienie po wyczerpaniu limitów API jest w pełni automatyczne.
* **Automatyzacja NVDA:** Tłumaczenia zapisywane są jako gotowe pliki `.html` z wbudowanym tagiem językowym lub pliki `.docx` z tagami wstrzykniętymi bezpośrednio do struktury XML.
* **8 lokalnych akcentów:** Możliwość celowego wymuszania łamanego akcentu dla lokalnych syntezatorów (Tiflotecnia Voices, eSpeak, OneCore) dzięki zaawansowanym regułom regex. Obsługiwane akcenty obcojęzyczne: angielski, rosyjski (z transliteracją na cyrylicę), francuski, niemiecki, hiszpański, włoski, fiński, islandzki.
* **Tryb Szyfrant:** 6 lokalnych algorytmów zniekształcających tekst — od czytania wspak, przez typoglikemię, po klasyczny szyfr Cezara. Każdy z lokalnym alfabetem paczki językowej (np. szyfr Cezara na 35-znakowym alfabecie PL z diakrytykami).
* **Naprawiacz Tagów:** Bezinwazyjnie wstrzykuje podany kod języka ISO — także regionalny, np. pt-BR czy zh-CN — do istniejących plików.


### 4. Konwerter / Architekt Audiobooków (Ctrl+3)

* Przetwarza surowe pliki `.txt` lub `.docx` pod kątem nawigacji klawiszowej dla NVDA i systemów takich jak ElevenLabs.
* Automatycznie konwertuje słowa kluczowe (Akt, Rozdział, Prolog) na nagłówki „Heading 1" w dokumencie Word, a także czyści zbędne tagi HTML i znaczniki Markdown.
* Od v15.1 grupowanie 5 tur w sceny z nagłówkami H1 (auto-detekcja Opowieści) — przygotowuje plik wygenerowany przez tryb Opowieści do tradycyjnej publikacji audiobookowej.


### 5. Manager Reguł (Ctrl+4, nowość od v13.0)

* **Eksplorator słowników bez Pythona:** Wizualne drzewo wszystkich plików YAML w folderze `dictionaries/` — akcenty fonetyczne, szyfry, tryby twórcze Reżysera i Opowieści. Lingwista lub tłumacz może przeglądać, duplikować, edytować i usuwać reguły wprost z GUI.
* **Kreator nowych reguł:** Formularz z wyborem typu (akcent, szyfr czystych zamian, tryb Reżysera, nowy język bazowy, szyfr algorytmiczny) tworzący gotowy szablon YAML, a dla trudniejszych przypadków generujący sformatowany prompt do wklejenia w ChatGPT / Claude.
* **Refaktor v13.0 — reguły w YAML-ach:** Wszystkie akcenty, szyfry i tryby AI, które do wersji 12.0 żyły jako „zaszyte" stałe w kodzie Pythona, zostały przeniesione do deklaratywnych plików `.yaml` wczytywanych dynamicznie przy starcie aplikacji. Każdy, kto potrafi obsłużyć Notatnik, może dostroić akcent (np. zamienić `sz → sh` na `sz → sch`), dodać nowy język, a nawet zmienić brzmienie prompta systemowego dla AI — bez kompilowania kodu.


## Wielojęzyczność (9 języków natywnie)

Od v14.0 aplikacja wspiera natywnie 9 języków bazowych: Polski, Deutsch, English, Español, Suomi, Français, Íslenska, Italiano, Русский. Każda paczka `dictionaries/<kod>/` zawiera diakrytyki, alfabet i reguły fonetyczne operujące na tekście w tym konkretnym języku — aplikacja wykrywa język źródła automatycznie przez lingua-language-detector (per akapit) i ładuje odpowiednią paczkę dla każdego fragmentu osobno.

Cały interfejs GUI, dokumentacja (`docs/manual.<iso>.html`) oraz większość komunikatów systemowych dostępne są natywnie w każdym ze wspieranych języków. Prompty systemowe AI w trybach Reżysera i Opowieści są napisane w językach docelowych (ręcznie, nie autotłumaczone — patrz `dictionaries/<kod>/rezyser/` i `dictionaries/<kod>/opowiesci/`).


## Architektura AI i użyte modele

Zalecanym i domyślnym dostawcą AI jest Anthropic (Claude) — wszystkie prompty systemowe są pod niego dostrojone, więc to on daje najwyższą jakość narracji, najlepsze trzymanie się zasad świata i najbardziej naturalną prozę. Konsolidacja na Claude przebiegła etapami (Reżyser w v18.0, Opowieści w v18.1, Poliglota i postprodukcja w v18.2) — wynikła z empirycznie potwierdzonej przewagi w trzymaniu się zasad świata, naturalności prozy i unikaniu klisz.

* **Anthropic Claude Sonnet 5 (domyślny filar jakości):** Silnik CAŁEJ inteligencji aplikacji. Odpowiada za narrację twórczą (reżyserowanie skryptów, pisanie tradycyjnej prozy Audiobooka, Burzę Mózgów oraz WSZYSTKIE tryby Opowieści — Wybory, Mniejsze Zło, Swobodny — wraz z generowaniem streszczeń i przerywników Cinematic), zaawansowane tłumaczenia z zachowaniem kontekstu wieloblokowego (Poliglota), a także mikrozadania: iteracyjne nadawanie literackich tytułów rozdziałom oraz wykrywanie kodu języka treści.

* **Własny endpoint zgodny z OpenAI (opcja zaawansowana, od v18.4):** Zamiast Anthropic można wskazać dowolny endpoint zgodny z API OpenAI (OpenRouter, Groq, Fireworks, DeepSeek, lokalne Ollama, OpenAI-compatible Gemini i inne) — jedną, wspólną ścieżką kodu, bez osobnej integracji per dostawca. Konfiguracja w pliku `golden_key.env` (`LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_MODEL`, `OPENAI_API_KEY`); pełna instrukcja w głównym manualu (KROK 2B). Inne modele mogą dać niższą jakość niż Claude, pod którego stroione są prompty — to świadomy wybór koszt↔jakość po stronie użytkownika.


### Znane ograniczenia modeli (Anti-Closure)

Pomimo zaimplementowania rygorystycznych dyrektyw systemowych nakazujących ucinanie akcji w momentach napięcia (tzw. dyrektywa Anti-Closure), współczesne modele LLM posiadają silną, wrodzoną tendencję do „zamykania" historii. Skutkuje to częstym wplataniem niechcianych konkluzji, morałów lub fałszywych „happy endów", szczególnie w Trybie Tradycyjnego Audiobooka.

Jest to fundamentalne ograniczenie obecnej generacji sztucznej inteligencji. Z tego powodu aplikacja zapisuje projekty w zwykłych, łatwych do edycji plikach tekstowych (`.txt`). Wymaga to od użytkownika przyjęcia roli żywego montażysty — okazjonalnego, ręcznego usunięcia ostatnich, „zamykających" zdań wygenerowanych przez AI, a następnie zsynchronizowania pamięci z poprawionym plikiem przyciskiem „Odśwież z dysku" i kontynuacji pracy.


## Instalacja i uruchomienie

### Dla użytkowników końcowych (Windows)

1. Pobierz najnowsze wydanie z zakładki **Releases** (paczka oznaczona jako *Latest*) — plik `Rezyser_Audio_v<numer>_Installer.exe`. Uruchom go dwukrotnym kliknięciem. Instalator domyślnie ląduje w katalogu lokalnym Twojego konta (`%LocalAppData%\Programs\Reżyser Audio GPT`) i nie wymaga praw administratora; możesz wybrać własną ścieżkę przyciskiem „Przeglądaj". Po zakończeniu tworzy skróty w Menu Start i na pulpicie, a opcjonalnie otwiera instrukcję obsługi w domyślnym edytorze plików `.txt`.
2. **Konfiguracja API Anthropic:** Przy pierwszym uruchomieniu aplikacja zasygnalizuje brak klucza w sekcji System Check. Kliknij widoczny przycisk, by wygenerować plik `golden_key.env`, otwórz go w edytorze tekstu i wklej swój klucz Anthropic (zaczynający się od `sk-ant-`).
3. **Pierwsze kroki:** Otwórz plik `docs/manual.pl.html` (lub w innym języku) w folderze instalacji — to pełna instrukcja obsługi pisana językiem dostępnym dla każdego użytkownika, nie tylko deweloperów.


### Dla deweloperów (clone + setup)

1. Sklonuj repozytorium na swój dysk.
2. Uruchom plik `setup_dev.bat`, aby automatycznie utworzyć wirtualne środowisko (`.venv/`) i pobrać zależności z `requirements.txt`.
3. Uruchom aplikację komendą `python main.py` lub przez plik `run_dev.bat`.

Skrypty `.sh` dla macOS/Linux zostały usunięte w v13.1 — środowisko developerskie skoncentrowane jest na Windows ze względu na specyfikę testów dostępności NVDA. Praca z kodem na innych systemach jest możliwa, ale wymaga ręcznego setupu: `python -m venv .venv && .venv/bin/pip install -r requirements.txt`.

**Skrypty buildujące paczki release** (`build_release.py`, `rezyser_audio.spec`, `installer.iss`) służą wyłącznie do tworzenia paczek dla Windows. Od wersji 17.0 `build_release.py` zamraża aplikację PyInstallerem (onedir + windowed) wg `rezyser_audio.spec` — produkuje `dist/` z natywnym `.exe` i folderem bundla `runtime/` (interpreter + biblioteki). Nie jest już potrzebny żaden przenośny Python wgrany ręcznie do repozytorium; katalogi `dist/` i `build/` są w `.gitignore`.


## Pełna dokumentacja

Niniejszy README to jedynie zarys architektoniczny projektu. Aby poznać zaawansowane techniki powstrzymywania halucynacji AI, instrukcje instalacji kompatybilnych syntezatorów mowy (Tiflotecnia Voices, OneCore, eSpeak, Apple Voices), pełen opis trybów Opowieści z fiolką, oraz kompletny poradnik obsługi, zapoznaj się z plikami w folderze `docs/`:

* `docs/manual.<iso>.html` — główna instrukcja obsługi (pisana dla użytkownika końcowego).
* `docs/tales.<iso>.html` — manual trybu Opowieści (interaktywne gry tekstowe).
* `docs/dictionaries.<iso>.html` — instrukcja dla lingwistów bez Pythona, jak dodawać własne akcenty/szyfry/tryby AI.

Każdy z tych plików dostępny jest w 9 językach — sufiks `.<iso>.html` (np. `manual.pl.html`, `manual.en.html`, `manual.de.html`).


## Licencja

Projekt jest udostępniony na licencji **MIT** — pełna treść w pliku [`LICENSE`](LICENSE) w katalogu głównym repozytorium. W skrócie: możesz swobodnie używać, kopiować, modyfikować i rozpowszechniać oprogramowanie (także komercyjnie), pod warunkiem zachowania noty o prawach autorskich. Oprogramowanie dostarczane jest „tak jak jest", bez jakiejkolwiek gwarancji.
