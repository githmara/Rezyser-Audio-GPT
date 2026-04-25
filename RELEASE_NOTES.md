# Release Notes — Reżyser Audio GPT 13.1 „Wersja Wydawnicza"

*Punkt wyjścia: V13.0-RC (22 IV 2026) → 19 commitów → V13.1.*
*Motyw przewodni: pełna warstwa wielojęzyczności od fundamentu po menu, bez wyprzedzania harmonogramu.*

---

## TL;DR

13.1 jest pierwszym wydaniem, w którym **interfejs aplikacji potrafi mówić w różnych językach naraz** (polski, angielski, fiński, rosyjski, islandzki, włoski) — choć dziś użytkownik widzi to tylko jako *przygotowanie pod 13.2*. Cały tekst widoczny w GUI i obie instrukcje (`docs/manual.pl.txt`, `docs/dictionaries.pl.txt`) zostały oderwane od kodu Pythona i przeniesione do plików YAML w `dictionaries/<kod>/gui/`. Powstała infrastruktura wyboru języka interfejsu zapisywana w `wx.Config` (cross‑platform), z dialogiem pierwszego uruchomienia i menu w pasku menubar. Zaostrzono też definicję „obsługiwanego języka" — dziś w komunikatach widnieje tylko polski, jako jedyny, w którym silnik faktycznie potrafi cokolwiek zrobić; kolejne języki będą się dorzucały *organicznie* w miarę dodawania pełnych pakietów akcentów i szyfrów.

---

## Co nowego dla użytkownika końcowego

### Wybór języka interfejsu (przygotowane, ujawni się w 13.2)

- **Pierwsze uruchomienie:** gdy w `dictionaries/` znajdzie się ≥ 2 w pełni wdrożone języki, aplikacja wita użytkownika oknem dialogowym `Choose your language` (treść hardkodowana po angielsku, neutralnie i bez ryzyka wykluczenia kogokolwiek). Lista to natywne nazwy (Polski, English, Suomi, Íslenska, Italiano, Русский) posortowane po ISO. Cancel = polski jako fallback.
- **Menu „Język interfejsu"** w pasku menu z radio‑items dla każdego języka. Aktywny zaznaczony, zmiana po prostu zapisuje wybór do `wx.Config` i prosi o restart aplikacji (świadoma decyzja: dynamiczny re‑render wszystkich kontrolek wxPython byłby ryzykiem regresji w czytniku ekranu — prościej jest zamknąć i otworzyć ponownie).
- **Trwałe zapamiętanie wyboru:** `wx.Config` używa rejestru Windows (`HKCU\Software\RezyserAudioGPT`), pliku INI w `~` na Linuksie i `~/Library/Preferences/...` na macOS. Per‑user, nie wymaga uprawnień administratora.
- **Silent init dla starych instalacji:** jeśli kompletny jest tylko jeden język (stan w 13.1: tylko polski), dialog się nie pojawia — aplikacja milcząco zapisuje polski i lecimy dalej. Żadnych pytań w które nie ma czego wpisać.

### Komunikat ostrzegający o niewspieranym języku tekstu źródłowego

- Lista *„obsługiwanych języków"* w ostrzeżeniu jest budowana **dynamicznie** ze skanu folderów `dictionaries/<kod>/podstawy.yaml`, nie hardkodowana. Każdy nowy folder z pełnym pakietem dorzuca pozycję sam — bez edycji żadnego stringa.
- **Język interfejsu użytkownika idzie pierwszy.** Polski użytkownik widzi „Polski, …", angielski zobaczy „English, Polski, …" — porządek odzwierciedla kontekst, w którym pracuje (czytniki ekranu czytają od początku, więc to liczy się dla A11y).

### Higiena dokumentacji end‑user

- Stara dwoistość `instrukcja.txt` w roocie + `dictionaries/instrukcja.txt` została skasowana (797 linii). Jedynym kanonicznym źródłem dokumentacji są teraz `docs/manual.pl.txt` i `docs/dictionaries.pl.txt`, generowane przez nowy `generuj_dokumentacje.py` z szablonów YAML. Dla zagranicznych użytkowników GitHuba nazwy plików po angielsku, kod ISO w rozszerzeniu.
- Numer wersji ma teraz **jedno źródło prawdy** — `dictionaries/pl/gui/ui.yaml::app.wersja`. Tytuł okna, paczki releasu, dokumentacja — wszystko czyta to samo. Koniec ze synchronizacją literówek typu „v1**O**.1" zamiast „v10.1".

### Build releasu

- `buduj_wydanie.py` przestał pytać o numer wersji przez `input()` (single point of failure: literówka prowadziła do desynchronizacji paczki z tytułem aplikacji). Skrypt teraz auto‑detekcję z `ui.yaml` i blokuje nadpisanie istniejących paczek `Rezyser_Audio_v<wersja>_*` — chroni archiwum buildów.
- Instalator EXE (Inno Setup) i portable ZIP są teraz w **parity**: oba wykluczają surowe szablony z `dictionaries/<kod>/gui/dokumentacja/` (użytkownik dostaje wygenerowane `docs/*.txt`, nie YAML‑e z placeholderami).
- Naprawa `sys.stdout.reconfigure(encoding="utf-8")` na Windowsie — emoji w printach buildu nie wywalają już procesu.

---

## Pod maską

### Warstwa tłumaczeń UI (`i18n.py`)

- Nowy moduł `i18n.py`: cienki loader YAML‑ów z cache w pamięci, API `t("klucz", **params)`, fallback na polski przy brakującym kluczu. Obsługa zagnieżdżonych kluczy przez kropkę (`t("main.menu.zakoncz")`).
- Hardkodowane stringi w `main.py`, `gui_konwerter.py`, `gui_manager_regul.py`, `gui_poliglota.py`, `gui_rezyser.py` zostały zmigrowane: 441 kluczy w 8 sekcjach (`app`, `common`, `main`, `home`, `rezyser`, `poliglota`, `konwerter`, `manager`). Smoke test 440 kluczy w kodzie kontra YAML — 0 brakujących.
- Manager Reguł dostał **czwartą kategorię** w drzewie: `gui/` obok `akcenty/`, `szyfry/`, `rezyser/`. Kreator nowego języka tworzy podfolder `gui/` automatycznie.
- Konwerter zapisuje teraz metadane `author` w `.docx` przez `t()` — wcześniej hardkodowane „Reżyser" pokazywałoby się obcojęzycznemu użytkownikowi NVDA w dymkach Eksploratora.

### Wielojęzyczne tłumaczenia UI (5 języków)

- Nowy `buduj_wielojezyczne_ui.py`: autotłumacz oparty o `ruamel.yaml` round‑trip (komentarze sekcyjne zachowane bit‑w‑bit) + JSON batched przez `gpt-4o`.
- **Tokenizacja dwuwarstwowa** chroni strukturę: `⟦P{n}⟧` dla `{placeholderów}` (`{nazwa_pliku}`, `{liczba_znakow}`), `⟦S{n}⟧` dla skrótów klawiaturowych (`\tCtrl+1`). Akcelerator `&` celowo nietokenizowany — LLM dostaje go widocznego z explicit instrukcją relokacji na sensowną literę docelową języka.
- Walidacje per‑leaf: parity tokenów + count(`'&'`) + kompletność id‑ów. Auto‑retry dla problematycznych liści (fiński zgubił raz `&` — retry naprawił bez interwencji człowieka).
- Chunking po 150 liści + `max_tokens=16_384` + `finish_reason` guard (gpt‑4o w jednym requeście nie pomieścił 450 liści cyrylicy).
- Wynik: `dictionaries/{en,fi,ru,is,it}/gui/ui.yaml` — 450 liści/język, ~41–45 kB każdy.
- Surgical update: nowa flaga `--klucz` w `buduj_wielojezyczne_ui.py` filtruje liście do prefiksu i iniekuje wybrane wartości w istniejący ui.yaml zachowując bit‑w‑bit pozostałe liście — koszt 5 mikro‑requestów zamiast 15 pełnych chunków.

### Wielojęzyczne tłumaczenia dokumentacji

- Nowy `buduj_wielojezyczne_docs.py` + szablony `dictionaries/<kod>/gui/dokumentacja/manual.yaml`. Skrypt zamraża placeholdery `{...}` przed wysyłką do LLM i scala je z odpowiedzią — model nie ma jak zaszkodzić strukturze.
- Parametryzacja „żywych etykiet GUI" w manual.yaml: 25 wystąpień literałów (15 unikalnych kluczy GUI) zamienionych na placeholdery `{main.menu.zakoncz}` itp. Dzięki temu cytaty w instrukcji nie rozjeżdżają się z rzeczywistym GUI po retłumaczeniu.

### Treści języków bazowych

- Nowe pliki `dictionaries/{en,fi,ru,is,it}/podstawy.yaml` z natywnymi alfabetami: en (26), fi (29 z Å, Ä, Ö), ru (33 cyrylicy z Ё), is (32 z Þ, Ð, Æ), it (21 rodzimych bez J, K, W, X, Y).
- Pole `polskie_znaki: []` (puste — w 13.x transliteracja PL→łacina nie dotyczy innych języków). Klucz historyczny, manager reguł oczekuje jego obecności.
- Pola `opis: |` i komentarze nagłówkowe **w językach natywnych** (refresh w 13.1): suomi po fińsku, íslenska po islandzku, русский po rosyjsku itd.

### Definicja „kompletnego" języka

Wprowadzono nowe kryterium w `core_poliglota._jezyk_kompletny()`:

```
✓ podstawy.yaml          (alfabet + transliteracja)
✓ gui/ui.yaml            (tłumaczenie interfejsu)
✓ akcenty/*.yaml ≥ 1     (tryb Reżysera)
✓ szyfry/*.yaml  ≥ 1     (tryb Szyfranta)
```

`dostepne_jezyki_bazowe()` zwraca dziś tylko `["pl"]`. 5 stubów (en/fi/is/it/ru) jest filtrowanych — silnik nie umiałby przetwarzać tekstu w żadnym z nich, więc nie powinny się pojawiać w komunikatach typu „obsługiwane języki" ani w selektorze języka interfejsu. Folder `rezyser/` świadomie pominięty w kryterium — zawiera dziś PL‑specyficzne prompty `gpt-4o`, nie kontrakt każdego języka.

### Migracja na Claude Code

- `chore: gruntowny refaktor zasad projektu i migracja na Claude Code (Bash)` — odejście od `.clinerules` (Cline + PowerShell) na rzecz `CLAUDE.md` (Claude Code + Git Bash). Wszystkie wewnętrzne odwołania do `.clinerules` w plikach projektowych (m.in. `TODO_skrotowce_wielojezyczne.md`) przetłumaczone na nowe sekcje `CLAUDE.md`.

---

## Strategia wdrażania (zmiana tempa)

### Co znaczy „13.1 = wersja porządkowa"?

Pierwotna intencja `TODO_skrotowce_wielojezyczne.md` zakładała: *13.1 = pierwszy w pełni nowy język*. W praktyce, etapy 1–5/5 i18n wdrożyły **infrastrukturę i tłumaczenia** dla pięciu języków na raz, wyprzedzając pierwszy krok schematu z TODO § 4 (treści języka bazowego). 13.1 ten dług naprawia: refresh polski podstawy.yaml, dopracowanie `opis` i komentarzy w językach natywnych, plus gridowanie infrastruktury wyboru języka interfejsu (`wx.Config` + menu + ostrzeżenie). **Bez wciągania niedokończonych języków do widoku użytkownika.**

### Co przyniesie 13.2 i dalej

Każdy minor 13.x dorzuca **jeden** w pełni wdrożony język:
- `dictionaries/<kod>/akcenty/` — komplet akcentów minus akcent natywny tego języka
- `dictionaries/<kod>/szyfry/` — sześć algorytmów (cezar/jakanie/odwracanie/samogloskowiec/typoglikemia/wąż), z rozwinięciami skrótowców z TODO § 3.1
- smoke test sekcji 6 TODO

Gdy plik TODO zostanie wyczerpany (wszystkie języki z § 3.1 + 3.2 zamknięte), następny release to **14.0**.

### Co działa „samoczynnie" od 13.2 (fi z pełnym pakietem)

Bez edycji jednej linii Pythona — siatka jest gotowa:
- `dostepne_jezyki_bazowe()` zwróci `["fi", "pl"]`
- Menu „Język interfejsu" pojawi się w pasku menu z 2 radio‑items (Polski, Suomi)
- First‑run dialog zacznie wyskakiwać dla nowych instalacji
- Lista w ostrzeżeniu dla użytkownika z interfejsem fińskim zacznie się od „Suomi, Polski"

---

## Breaking changes / migracja

- **Numer wersji zniknął z `main.py`.** Atrybut `MainFrame.VERSION` w 13.1 nie istnieje — wersja siedzi wyłącznie w `dictionaries/pl/gui/ui.yaml::app.wersja`. Ewentualne zewnętrzne skrypty muszą czytać stamtąd.
- **Stare `instrukcja.txt` (root) i `dictionaries/instrukcja.txt` zostały usunięte.** Nowe lokalizacje: `docs/manual.pl.txt` i `docs/dictionaries.pl.txt`. Linki w bookmarkach/skryptach do zaktualizowania.
- **Lista „obsługiwanych języków" w ostrzeżeniu skróciła się z 6 do 1.** Świadoma regresja kosmetyczna — wcześniejsza lista (etap 5/5) była *false advertising*: langdetect przepuszczał stuby, ale silnik w żadnym z 5 języków nie miał akcentów ani szyfrów. Po 13.2+ lista znów rośnie, organicznie i uczciwie.
- **Nowa zależność:** `ruamel.yaml` w `requirements.txt` (potrzebne tylko dla skryptów buildu wielojęzycznych UI; sama aplikacja działa z `pyyaml`).

---

*Notes wygenerowane na podstawie 19 commitów od `V13.0-RC` do `d911c60` (HEAD). Pełna lista commitów: `git log V13.0-RC..HEAD --oneline`.*
