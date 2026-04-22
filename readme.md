# 🎬 Reżyser Audio GPT

**Hybrydowe Studio Nagraniowe dla Słuchowisk i Audiobooków**

Zestaw przenośnych narzędzi napędzanych przez AI do automatycznego pisania, planowania, formatowania i tłumaczenia obszernych skryptów. Projekt jest natywną aplikacją desktopową (wxPython) zaprojektowaną od podstaw z myślą o pełnej dostępności dla czytników ekranu (NVDA, VoiceOver) i współpracy z profesjonalnymi syntezatorami mowy (TTS). Działa bez przeglądarki i bez lokalnego serwera — uruchamia się jako zwykłe okno programu.

---

## 🚀 Główne Moduły

Zestaw składa się z głównego studia (Reżyseria), narzędzia do tłumaczeń i akcentów (Poliglota), narzędzia do budowania struktury pliku (Architekt Audiobooków) oraz — od wersji 13.0 — Managera Reguł, w którym lingwista bez znajomości Pythona może dodać nowy akcent, szyfr albo tryb twórczy wprost z GUI. Wszystkie cztery narzędzia dostępne są w jednym oknie programu i przełączane przyciskami na pasku narzędzi lub skrótami klawiaturowymi (Ctrl+1 / Ctrl+2 / Ctrl+3 / Ctrl+4).


### 1. Reżyseria (Kreator AI)
* **Wieloprojektowa Księga Świata:** System automatycznie ładuje w tle dedykowane zasady uniwersum (`.md`) na podstawie aktywnego pliku źródłowego, zapewniając pełną izolację (zero-click context loading).
* **Akumulator Fabuły:** Algorytm "nieskończonej pamięci". Gdy wskaźnik pamięci wejdzie w stan czerwonego alarmu, system automatycznie generuje streszczenie fabuły i zapisuje je do pola Pamięci Długotrwałej.
* **Tryby Generacji:** Obsługa formatu słuchowiska (tagi `[SFX]` i `[Postać]`) oraz tradycyjnej, gęstej prozy literackiej. 

### 2. Poliglota (AI Translator & TTS Accents)
* **Bezpieczny Tłumacz:** Długie teksty są automatycznie dzielone na bloki do 10 000 znaków i tłumaczone sekwencyjnie. Każdy blok jest natychmiast zapisywany do ukrytego pliku `.jsonl`. Wznowienie po wyczerpaniu limitów API jest w pełni automatyczne.
* **Automatyzacja NVDA:** Tłumaczenia zapisywane są jako gotowe pliki `.html` z wbudowanym tagiem językowym lub pliki `.docx` z tagami wstrzykniętymi bezpośrednio do struktury XML. 
* **Lokalne Akcenty:** Możliwość celowego wymuszania łamanego akcentu dla lokalnych syntezatorów (Vocalizer, eSpeak, OneCore) dzięki zaawansowanym regułom regex. Obsługiwane akcenty: angielski, rosyjski (z transliteracją na cyrylicę), francuski, niemiecki, hiszpański, włoski, fiński, islandzki.
* **Naprawiacz Tagów:** Bezinwazyjnie wstrzykuje podany dwuliterowy kod języka ISO do istniejących plików.

### 3. Konwerter / Architekt Audiobooków
* Przetwarza surowe pliki `.txt` lub `.docx` pod kątem nawigacji klawiszowej dla NVDA i systemów takich jak ElevenLabs.
* Automatycznie konwertuje słowa kluczowe (Akt, Rozdział, Prolog) na nagłówki "Heading 1" w dokumencie Word, a także czyści zbędne tagi HTML i znaczniki Markdown.

### 4. Manager Reguł (nowość w 13.0, Ctrl+4)
* **Eksplorator słowników bez Pythona:** Wizualne drzewo wszystkich plików YAML w folderze [`dictionaries/`](dictionaries/README.md) — akcenty fonetyczne, szyfry i tryby twórcze Reżysera. Lingwista lub tłumacz może przeglądać, duplikować, edytować i usuwać reguły wprost z GUI, bez otwierania Eksploratora plików i bez znajomości języka Python.
* **Kreator nowych reguł:** Formularz z wyborem typu (akcent, szyfr czystych zamian, tryb Reżysera, nowy język bazowy, szyfr algorytmiczny) tworzący gotowy szablon YAML, a dla trudniejszych przypadków generujący sformatowany prompt do wklejenia w ChatGPT / Claude.
* **Refaktor 13.0 — reguły w YAML-ach:** Wszystkie akcenty, szyfry i tryby pracy Reżysera, które do wersji 12.0 żyły jako „zaszyte" stałe w kodzie Pythona, zostały przeniesione do deklaratywnych plików `.yaml` wczytywanych dynamicznie przy starcie aplikacji. Każdy, kto potrafi obsłużyć Notatnik, może dostroić akcent (np. zamienić `sz → sh` na `sz → sch`), dodać nowy język, a nawet zmienić brzmienie prompta systemowego dla AI — bez kompilowania kodu. Pełna dokumentacja formatu: **[`dictionaries/README.md`](dictionaries/README.md)**.

---

## 🧠 Architektura AI i Użyte Modele


Aplikacja inteligentnie rozdziela zadania, optymalizując koszty i szybkość działania API OpenAI:
* **GPT-4o:** Główny silnik napędzający aplikację. Odpowiada za ciężkie zadania generatywne: reżyserowanie skryptów, pisanie tradycyjnej prozy (Audiobook), generowanie streszczeń oraz zaawansowane tłumaczenia z zachowaniem kontekstu wieloblokowego.
* **GPT-4o-mini:** Szybki, lekki model pomocniczy. Używany w tle do mikrozadań wymagających dużej szybkości, takich jak iteracyjne nadawanie literackich tytułów wygenerowanym rozdziałom czy ekstrakcja kodów ISO.

### ⚠️ Znane Ograniczenia Modeli (Anti-Closure)
Pomimo zaimplementowania rygorystycznych dyrektyw systemowych nakazujących ucinanie akcji w momentach napięcia (tzw. dyrektywa Anti-Closure), współczesne modele LLM posiadają silną, wrodzoną tendencję do "zamykania" historii. Skutkuje to częstym wplataniem niechcianych konkluzji, morałów lub fałszywych "happy endów", szczególnie w Trybie Tradycyjnego Audiobooka. 

Jest to fundamentalne ograniczenie obecnej generacji sztucznej inteligencji. Z tego powodu aplikacja zapisuje projekty w zwykłych, łatwych do edycji plikach tekstowych (`.txt`). Wymaga to od użytkownika przyjęcia roli żywego montażysty – okazjonalnego, ręcznego usunięcia ostatnich, "zamykających" zdań wygenerowanych przez AI, przed wczytaniem pliku ponownie i kontynuacją pracy.

---

## 🛠️ Instalacja i Uruchomienie

Aplikacja jest w pełni przenośna i gotowa do działania na systemach Windows bez konieczności globalnej instalacji środowiska.

1. Sklonuj repozytorium lub pobierz paczkę ZIP.
2. Uruchom plik `Uruchom_Rezysera.bat`. Otworzy się krótkotrwałe okno terminala (znika automatycznie), a po chwili pojawi się główne okno programu. Nie musisz otwierać żadnej przeglądarki.
3. **Konfiguracja API:** Przy pierwszym uruchomieniu aplikacja zasygnalizuje brak klucza w sekcji System Check. Kliknij widoczny przycisk, by wygenerować plik `golden_key.env`, otwórz go w edytorze tekstu i wklej swój klucz (zaczynający się od `sk-proj-`).

---

## 📖 Pełna Dokumentacja i Obieg Pracy

Niniejszy dokument to jedynie zarys architektoniczny projektu. Aby poznać zaawansowane techniki powstrzymywania halucynacji AI, instrukcje instalacji kompatybilnych syntezatorów mowy dla Windows i Apple oraz kompletny poradnik obsługi, **zapoznaj się z plikiem `instrukcja.txt`**.

### Dla programistów (Jak zacząć pracę z kodem)

**Windows:**
1. Sklonuj repozytorium na swój dysk.
2. Uruchom plik `skonfiguruj_dev.bat`, aby automatycznie utworzyć wirtualne środowisko i pobrać zależności.
3. Uruchom aplikację komendą `python main.py` lub przez plik `uruchom_rezysera_dev.bat`.

**macOS / Linux:**
1. Sklonuj repozytorium i otwórz terminal w jego folderze.
2. Wykonaj komendę `chmod +x *.sh`, aby nadać skryptom uprawnienia do uruchamiania.
3. Wykonaj komendę `./skonfiguruj_dev.sh`, aby automatycznie utworzyć wirtualne środowisko i pobrać zależności.
4. Uruchom aplikację komendą `python main.py` lub `./uruchom_rezysera.sh`.

---

### Dla użytkowników końcowych (Zwykłe użytkowanie)

**Windows:**
1. Pobierz najnowsze wydanie z zakładki Releases (paczka oznaczona jako *Latest*).
2. Wypakuj pobrany plik ZIP: kliknij go prawym przyciskiem myszy (lub użyj klawisza aplikacji), wybierz "Wyodrębnij wszystkie..." (lub "Wypakuj pliki", zależnie od programu) i pozostaw domyślne ustawienia, aby utworzył się nowy folder. Możesz też pobrać i uruchomić instalator, aby wypakować pliki automatycznie do wybranego folderu.
3. Wejdź do wypakowanego folderu, przeczytaj plik `instrukcja.txt` i uruchom `Uruchom_Rezysera.bat`. Miłej zabawy!

**macOS / Linux:**
Z powodu różnic w architekturze systemów, proces instalacji wygląda identycznie jak dla programistów. Pobierz kod źródłowy projektu (jako ZIP lub klonując repozytorium), otwórz terminal w pobranym folderze, nadaj uprawnienia (`chmod +x *.sh`) i użyj skryptów `.sh` do pierwszej instalacji oraz późniejszego uruchamiania.

> **Ważna uwaga dla deweloperów:** Skrypty do automatycznego budowania wydań (`buduj_wydanie.py` oraz pliki `.iss`) służą wyłącznie do tworzenia paczek dla systemu Windows. Wymagają one specjalnego folderu `runtime/` z przenośną wersją Pythona. Folder ten celowo nie jest częścią tego repozytorium.
