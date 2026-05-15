# Release Notes — Reżyser Audio GPT 15.2.3 „Wersja Wydawnicza"

*Patch v15.2.3: pięć poprawek A11y, jeden breaking change i jedno załatanie luki architektonicznej w pamięci streszczenia. (1) **Prawdziwa ochrona trybu zapisu** w Reżyserze i Opowieściach — od v12.0 manuale deklarowały, że RadioBox blokuje zmianę trybu twórczego w trakcie aktywnego projektu, ale ochrona była udawana: Burza Mózgów (zawsze aktywna jako tryb planowania) była tylną furtką, strzałkami w górę / w dół dało się przejść Audiobook → Burza → Skrypt i odwrotnie, a pierwsze kliknięcie „Wstaw Akt 1" / „Wstaw Rozdział 1" w nowo wybranym trybie nadpisywało plik `.mode` mieszając akty z rozdziałami. Patch wprowadza mirror `.mode` w pamięci panelu (`_zapisany_tryb`) — po utrwaleniu decyzji trybu drugi tryb zapisu jest faktycznie disabled w RadioBoxie. W Opowieściach analogicznie + nowy przycisk „Edytuj tryb gry…" jako furtka awaryjna (modalny dialog z ostrzeżeniem). (2) **Dialog wyboru projektu/gry zamiast wpisywania nazwy z klawiatury** — Reżyser dostaje walk-em po `skrypty/` (eliminacja plików streszczeń), Opowieści walk-em po `runtime/opowiesci/` (kryterium: obecność `.game.json`). Wybór poprzez `wx.SingleChoiceDialog` z listą nazw — NVDA czyta naturalnie, gracz nie musi pamiętać ani przepisywać nazwy. Reżyser zachowuje też ścieżkę eksperta (pole wypełnione + Enter ładuje konkretną nazwę bez dialogu). (3) **Lokalizacja etykiety „Cancel" → „Anuluj"** w obu nowych `SingleChoiceDialog` — wbudowane dialogi wxPython na PL-systemie z polskim UI aplikacji pokazywały angielską etykietę systemową; fix przez `FindWindowById(wx.ID_CANCEL).SetLabel(...)`. (4) **Breaking change — pliki user-facing Opowieści przeniesione ze `skrypty/` do nowego folderu `opowiesci/`**: po fixie (2) dialog wyboru projektu Reżysera widział gry Opowieści (bo zlewały się w jednym folderze), a wczytanie ich dawało fallback `saved_mode` poza zakresem 1/2 → odblokowanie wszystkich trybów Reżysera. Nowy `opowiesci/` w roocie repozytorium, auto-migracja w `ProjektOpowiesci.wczytaj()` przenosi pre-15.2.3 pliki na pierwszym load, manuale w 9 jzk z normalizacją pre-existing halucynacji LLM (folder names typu `scripts/`, `käsikirjoitukset/`, `runtime/historias/` były zlokalizowane zamiast literałów dyskowych). (5) **Załatanie luki architektonicznej w pamięci streszczenia** — przycisk „Otwórz plik narracji…" w pasku pliku Reżysera i obok Zapisz w Opowieściach (analogicznie do `os.startfile(golden_key.env)` w main.py / yamli w manager_regul). Łata scenariusz: gracz wpisał krótką notatkę („AI ostatnio zrobiło coś źle, pomiń ostatnią scenę") w Pamięć Długotrwałą, klika Zapisz Streszczenie, zamyka apkę. Po reload aplikacja PRIORYTETOWO ładuje streszczenie i POMIJA pełną historię — model dostaje tylko Księgę Świata + jednozdaniową notatkę i „głupieje" bez kontekstu tonu i ostatnich scen. Nowy przycisk otwiera plik narracji w Notatniku/TextEdit/xdg-open — gracz może skopiować ostatnie sceny do Pamięci Długotrwałej albo dopisać/edytować końcówkę ręcznie. W Opowieściach przycisk ma dodatkowo modalny dialog ostrzegawczy o ryzyku rozjazdu z `.game.json` (stan postaci, lokacji, ekwipunku — `.txt` to tylko narracja dla TTS, edycja nie aktualizuje stanu). Manuale we wszystkich 9 językach zaktualizowane z przeprosinami za poprzednie wprowadzenie w błąd ws. ochrony trybu + opisem nowego flow wczytywania + nową strukturą folderów + opisem nowego przycisku i luki, którą łata. Patch tag X.Y.(Z+1) zgodnie z [[feedback_hotfix_release]] — artefakty v15.2.2 nietknięte.*

*Patch v15.2.2: wielojęzyczność automatycznego bota `tiflotecnia-patch` w GitHub Actions. Bot do tej pory odpowiadał maili tylko po polsku (jeden szablon hardkodowany), niezależnie od języka issue. Po patchu detektor `lingua-language-detector` rozpoznaje 9 języków zgłoszenia (PL/EN/DE/ES/FI/FR/IS/IT/RU), bot dobiera natywny szablon emaila; nieobsługiwany język lub pusty tekst (sam adres email bez opisu) → fallback EN (najbardziej uniwersalny pojedynczy język wśród niewidomych użytkowników NVDA na świecie). Manual w 9 językach (`krok_5_alarm_detekcja_jezyka`) zachęca do dorzucenia 2-3 zdań opisu w swoim języku, żeby detektor miał na czym pracować. Komentarze workflow na issue (potwierdzenie wysyłki + redact) są bilingual PL/EN. Logika została przetestowana pre-merge (issue testowe ze zduplikowaną wiadomością wykryło bug w workflow trigger — usunięto duplikat akcji `gh issue comment` w starszym commicie bc80c1e). Patch tag X.Y.(Z+1) zgodnie z [[feedback_hotfix_release]] — artefakty v15.2.1 nietknięte, użytkownicy z v15.2.1 dostaną aktualizację do v15.2.2 przez `core_updater.sprawdz_aktualizacje()`.*

*Patch v15.2.1 (znaleziony podczas wizualnej weryfikacji v15.2 zaraz po release): tytuł `docs/manual.<iso>.txt` w 5 z 9 językach (de/fi/fr/is/it) zawierał polski leak — LLM podczas batch retranslate task #4 fazy B potraktował frazę „Podręcznik Reżysera Audio AI - Kompletny Przewodnik" jako brand name product i nie tłumaczył jej. Naprawa ręczna w 5 yamlach, zgodnie z [[feedback_hotfix_release]] (bump X.Y.(Z+1), nie nadpisuj artefaktów istniejącego v15.2 Release).*

*Release v15.2 wielowątkowy domykający ostatnie luki user-facing po 15.0/15.1: (a) **fiolka w trybie Mniejsze Zło** — reusable ZERO-numerowana opcja desperackiego ratunku z pseudolosowym rozkładem 60/30/10 wymuszanym Pythonem (LLM nie ma jak wymyślić zbawiennego skutku, anti-deus-ex-machina); (b) **menu Pomoc** (4-te w menubar) z 3 podmenu otwierającymi `docs/<rdzen>.<iso>.txt` w domyślnym handlerze .txt — koniec z „gdzie jest instrukcja?"; (c) **README wielojęzyczne w 9 językach** (`readme.md` EN jako kanoniczny GitHub landing + 8 wariantów `readme.<iso>.md`) — fair dla nieanglojęzycznych użytkowników; (d) **Inno installer „Otwórz instrukcję obsługi" po instalacji** z automatycznym wyborem ISO z języka instalatora; (e) **rebrand Vocalizer → Tiflotecnia Voices for NVDA** (Cerrence successor) + alarm o krytycznym bugu detekcji języka + automatyczny bot tiflotecnia-patch w GitHub Actions; (f) **JSON prompts Reżysera** (Burza Mózgów zwraca strukturyzowany JSON z 3 opcjami rozwoju fabuły + persystencja w `.brainstorm.json`); (g) **refaktor docs YAML na sekcje + surgical batch translation** (tańsze przyszłe update'y treści — surgical `--klucz` zamiast FULL retranslate całego pliku). Plus dwa porządki: refaktor user-facing `opowiesci.yaml/.txt` → `tales.yaml/.txt` (konwencja braku polskiego w plikach end-userowych jak `manual` / `dictionaries`) i fix bugowego polskiego alfabetu w `pl/podstawy.yaml` (brakujące Ś, alfabet z deklarowanych 35 znaków → faktycznie 35).*

---

## 15.2.3 — patch release (motyw przewodni: prawdziwa ochrona trybu zapisu w Reżyserze i Opowieściach)

*Punkt wyjścia: v15.2.2 (1714766) → diagnoza buga zgłoszona przez użytkownika podczas pracy na projekcie `emilia_heist_audiobook` (pomimo zapisanego trybu Audiobook strzałkami przez Burzę dało się dotrzeć do Skryptu, kliknięcie „Wstaw Akt 1" nadpisało `.mode` na Skrypt i wstrzyknęło do narracji obce nagłówki) → fix Reżysera (`ae1a2eb`) + fix Opowieści z furtką awaryjną (`7e67ffb`) + aktualizacja manuali w 9 językach z przeprosinami za poprzednie wprowadzenie w błąd → v15.2.3.*

### TL;DR

Notka historyczna w manualu od v12.0 obiecywała: „od wersji 12.0 interfejs po prostu blokuje zmianę trybu zapisu, gdy w pamięci jest już historia." Praktyka była mniej kategoryczna. Burza Mózgów (idx=0 w RadioBoxie) — celowo zawsze aktywna jako narzędzie planowania i awaryjnego streszczenia przy przepełnieniu okna kontekstowego — była tylną furtką. Sekwencja Audiobook → strzałka w górę → Burza → strzałka w dół → Skrypt (lub analogicznie w drugą stronę) wprowadzała gracza w stan „przeskoczyłem na inny tryb zapisu, ale aplikacja jeszcze nie wie". Pierwsze kliknięcie „Wstaw Akt 1" lub „Wstaw Rozdział 1" w nowo wybranym trybie nadpisywało `.mode` (bo `_zapisz_tryb_projektu` brał aktualny `_rb_mode.GetSelection()`), a do narracji wpadał nagłówek niezgodny z gatunkiem reszty pliku. ElevenLabs ten rozjazd zachowywał już dla siebie — generował audio bez zająknięcia, ale spis treści wyglądał jak avant-garde.

Patch rozdziela dwa pojęcia, które do tej pory były stopione:

- **Bieżący stan RadioBox-a** (`_rb_mode.GetSelection()`) — gracz może go zmieniać swobodnie, bo Burza musi być dostępna w każdym momencie pracy.
- **Utrwaloną decyzję trybu zapisu** (`_zapisany_tryb` — mirror pliku `.mode` w RAM) — niezmienna od momentu jej zafiksowania (wczytanie projektu, pierwsza wstawiona struktura lub pierwsza udana wysyłka produkcyjna).

Logika `EnableItem` patrzy teraz na `_zapisany_tryb`, nie na `tryb_idx` aktualnie zaznaczony w widgecie. Skutek: po utrwaleniu decyzji (np. Audiobook=2) drugi tryb zapisu (Skrypt=1) jest faktycznie disabled niezależnie od tego, że RadioBox aktualnie wskazuje Burzę (0). Strzałki klawiatury naturalnie pomijają wyłączone pozycje, NVDA czyta tylko enabled — gracz nie ma jak dotrzeć do błędnego stanu UI.

W Opowieściach analogiczny pattern, ale z jedną kluczową różnicą: wszystkie 3 pozycje RadioBox-a są tam trybami zapisu (3=Swobodny, 4=Wyborów, 5=Mniejsze zło) i nie ma odpowiednika „Burzy zawsze enabled" — `/visualize` i auto-streszczenie idą przez slash-komendy, nie przez RadioBox. Po utrwaleniu trybu dwie pozostałe pozycje są disabled. **Furtka awaryjna**: nowy przycisk „Edytuj tryb gry…" obok RadioBox-a otwiera modalny dialog z ostrzeżeniem — typowy use-case to sytuacja, w której AI w trybie Wyborów lub Mniejszego zła uparcie generuje kolejne dylematy zamiast zakończyć historię, a gracz chce przeskoczyć na Swobodny żeby samodzielnie opisać finałową scenę. Bez tej furtki nie dałoby się zamknąć takiej historii bez restartu aplikacji i ręcznej edycji `.mode`.

Dodatkowo: EVT_TEXT na polu nazwy gry odblokowuje RadioBox, gdy gracz wpisuje nazwę różną od aktywnego projektu — dzięki temu można w jednej sesji założyć drugą grę w innej tonacji bez `/koniec` (który i tak zamyka apkę).

### Co nowego dla użytkownika końcowego

#### Reżyser — uczciwe zabezpieczenie trybu

- Burza Mózgów zawsze aktywna jako narzędzie planowania / streszczenia (bez zmian).
- Skrypt i Audiobook: po utrwaleniu trybu w projekcie drugi tryb zapisu jest pomijany przez strzałki klawiatury (faktycznie disabled, nie tylko „niemoralnie aktywny").
- Przyciski struktury (Akt / Scena / Rozdział) widoczne tylko gdy aktualny tryb RadioBox-a zgadza się z utrwalonym `.mode` — nie da się już przypadkowo wstawić „Akt 1" w projekcie zapisanym jako Audiobook.
- Twardy Reset czyści `_zapisany_tryb` (nowy projekt zaczyna od czystej decyzji). Wyczyszczenie pamięci bieżącej (zachowanie streszczenia) — NIE czyści; projekt trwa dalej, decyzja trybu obowiązuje.

#### Opowieści — furtka „Edytuj tryb gry…"

Obok RadioBox-a wyboru trybu pojawia się nowy przycisk „Edytuj tryb gry…" (widoczny tylko gdy gra jest aktywna). Otwiera modalny dialog z trzema częściami:

1. **Ostrzeżenie** (długi tekst u góry, czytany jako pierwszy przez NVDA): wyjaśnia, że zmiana trybu w trakcie aktywnej gry może rozsynchronizować silnik narracyjny, oraz pokazuje typowy use-case (AI uparcie generuje dylematy zamiast zakończyć).
2. **RadioBox z 3 trybami** — zaznaczony na bieżącym trybie projektu.
3. **Przyciski OK / Anuluj** — Anuluj jest `SetDefault()` (bezpieczna akcja domyślna).

Po OK aplikacja zapisuje nowy tryb do `.mode`, aktualizuje `_zapisany_tryb` + `_projekt.tryb`, synchronizuje RadioBox i pokazuje potwierdzenie „Tryb gry zmieniony na X". Stan gry (postacie, świat, dotychczasowa narracja) pozostaje nietknięty — zmienia się tylko sposób generowania kolejnych tur.

Drugi flow odblokowujący RadioBox: gracz wpisuje w polu nazwy gry coś innego niż nazwa aktywnego projektu → aplikacja rozpoznaje, że to przygotowanie nowej gry → RadioBox staje się wolny (wszystkie 3 pozycje enabled). Powrót do nazwy aktywnego projektu z powrotem zamraża. Bez tego mechanizmu nie dałoby się w jednej sesji założyć drugiej gry w innej tonacji niż pierwsza (`/koniec` zamyka apkę).

#### Manuale — szczerość historyczna

Notka „dlaczego tryby są teraz chronione przed przypadkową zmianą" w `manual.<iso>.txt` została przepisana we wszystkich 9 językach: dotychczasowe zapewnienie o ochronie od v12.0 przyznaje, że było udawane (z konkretnym opisem mechanizmu omijania przez Burzę), a prawdziwą ochronę dostajemy dopiero w v15.2.3. Analogicznie w `tales.<iso>.txt` — wzmianka „tryb można zmienić w trakcie gry w jeden klik" została zastąpiona opisem furtki „Edytuj tryb gry…" z explicit wyjaśnieniem use-case'u.

#### Dialog wyboru projektu/gry zamiast wpisywania nazwy z klawiatury

Druga gałąź patcha — wcześniej w Reżyserze przycisk „Wczytaj" wymagał ręcznego wpisania nazwy projektu w polu nad listą; w Opowieściach analogiczny przycisk otwierał systemowy `wx.FileDialog` z filtrem `.game.json`. Niespójność wymagała od niewidomego gracza dwóch różnych nawigacji per moduł. Patch ujednolica:

- **Reżyser**: walk po folderze `skrypty/` zbiera wszystkie `.txt` (z wyłączeniem `_streszczenie.txt` — derived artefaktów per-projekt) i pokazuje `wx.SingleChoiceDialog` z listą czystych nazw projektów. Zachowano ścieżkę eksperta: pole nazwy wypełnione + klik Wczytaj (lub Enter w polu) ładuje bezpośrednio tę konkretną nazwę bez dialogu. Pole puste → dialog. Przycisk Wczytaj nie wymaga już wpisanej nazwy do bycia enabled — wystarczy że pamięć bieżąca jest pusta.
- **Opowieści**: walk po `runtime/opowiesci/` zbiera nazwy z plików `.game.json` (kryterium twarde — to źródło prawdy stanu gry, bez niego load i tak by się nie powiódł). Świeże gry bez `.txt` (przed pierwszą turą) też się pokazują, bo `.game.json` istnieje od momentu „Nowa gra". `wx.FileDialog` z filtrem rozszerzeń znikł — w jego miejsce `wx.SingleChoiceDialog`.

Konsystencja A11y między modułami: w obu narzędziach przycisk „Wczytaj" otwiera ten sam typ dialogu (`SingleChoiceDialog`), NVDA czyta listę naturalnie jako choice items zamiast nawigowania po systemowym dialogu plików z trzema panelami i rozszerzeniami.

Brak projektów / gier → odpowiedni `wx.MessageBox` informacyjny z instrukcją jak zacząć nowy projekt — gracz nie wpada w pusty dialog wyboru.

### Pod maską

- `VERSION`: `15.2.2` → `15.2.3` (patch tag, [[feedback_hotfix_release]] — bez nadpisywania artefaktów v15.2.2 Release).

- `gui_rezyser.py` (commit `ae1a2eb`, 55 inserts / 7 deletes):
  - Nowy atrybut `self._zapisany_tryb: int | None` w `__init__` (linia ~104).
  - `_refresh_ui_state` (linie ~888–944): widoczność `_pnl_struktura` warunkowa od `tryb_idx == _zapisany_tryb OR _zapisany_tryb is None`; `EnableItem(0, True)` (Burza zawsze), pozostałe pozycje zamrożone na `_zapisany_tryb`.
  - `_on_load`: po `SetSelection(wynik.saved_mode)` ustawia `self._zapisany_tryb = wynik.saved_mode` (lub `None` dla starych projektów bez `.mode`).
  - `_zapisz_tryb_projektu`: po `self._projekt.zapisz_tryb_tworczy(tryb_idx)` synchronizuje mirror, jeśli `tryb_idx in (1, 2)` (Burza nigdy nie utrwala decyzji).
  - `_on_wyslij_done_zapis`: nowe wywołanie `self._zapisz_tryb_projektu()` po pierwszej udanej wysyłce produkcyjnej — pokrywa graczy nie używających przycisków struktury (typowy flow eksportu finalnego do ElevenLabs).
  - `_on_hard_reset`: `self._zapisany_tryb = None` (nowy projekt zaczyna od czystej decyzji). `_on_clear_current` CELOWO nie resetuje — projekt trwa dalej z zachowaną decyzją trybu.

- `gui_opowiesci.py` (commit `7e67ffb`, ~125 inserts):
  - Nowy atrybut `self._zapisany_tryb: int | None` w `__init__`.
  - Nowy widget `self._btn_edytuj_tryb` w `_zbuduj_radiobox_trybu`, domyślnie ukryty (`Hide()`), dodany do `row` obok `_btn_zasady_swiata`.
  - `_aktualizuj_uistate`: pętla `EnableItem` na `_rb_tryb` based on `_zapisany_tryb`; `_btn_edytuj_tryb.Show(ma_projekt and utrwalony)` + `Layout()`.
  - Materializacja `_zapisany_tryb`: `_on_nowa_gra` (po `projekt.zapisz_tryb(tryb)`), `_on_wczytaj` (z `wynik.saved_mode` lub fallback `projekt.tryb`), `_on_zapisz` (idempotentne — pokrywa stare gry bez `.mode`).
  - Nowy handler `_on_edytuj_tryb`: tworzy `wx.Dialog` z ostrzeżeniem + RadioBox + OK/Anuluj. Po OK: `projekt.zapisz_tryb(nowy_tryb)`, sync `_zapisany_tryb` + `projekt.tryb`, `_ustaw_rb_z_trybu(nowy_tryb)`, `_aktualizuj_uistate()`, MessageBox „Tryb gry zmieniony".
  - Nowy handler `_on_nazwa_gry_change` (bind EVT_TEXT na `_txt_nazwa_gry`): jeśli nazwa różni się od `_projekt.nazwa_pliku` → `_zapisany_tryb = None` + `_aktualizuj_uistate()` (RadioBox wolny). Powrót do nazwy aktywnego projektu → zamrożenie z powrotem.

- 10 nowych kluczy i18n w `dictionaries/<kod>/gui/ui.yaml` × 9 języków:
  - `btn_edytuj_tryb_label`, `btn_edytuj_tryb_tooltip`
  - `dlg_edytuj_tryb_tytul`, `dlg_edytuj_tryb_ostrzezenie`, `dlg_edytuj_tryb_ostrzezenie_name`
  - `dlg_edytuj_tryb_lbl`, `dlg_edytuj_tryb_name`
  - `dlg_edytuj_tryb_btn_ok`, `dlg_edytuj_tryb_btn_anuluj`
  - `status_tryb_zmieniony` (z placeholderem `{tryb_nazwa}`)
  
  PL ręcznie, EN/DE/ES/FI/FR/IS/IT/RU przez surgical `--klucz` w `buduj_wielojezyczne_ui.py`. Manualny review halucynacji wykrył 1 rozjazd w ES (LLM użył „El menor de dos males" zamiast „Menor mal" z UI) — skorygowane ręcznie. Pozostałe rozjazdy w fleksyjnych językach (DE „kleineren Übel", IT „Il male minore", FI „Pienemmässä pahassa", RU „Меньшем зле") to naturalna odmiana gramatyczna — gracz rozpozna ten sam termin.

- 9 plików `dictionaries/<kod>/gui/dokumentacja/manual.yaml::tresc.notka_historyczna_chronione_tryby`: ostatnie zdanie („Od wersji 12.0…") wymienione na 4-zdaniowy paragraf z przyznaniem luki + wyjaśnieniem nowej ochrony od v15.2.3. PL ręcznie, 8 lokalizacji ręcznie z zachowaniem nazewnictwa Burzy per język (Brainstorming, Tormenta de Ideas, Aivoriihi, Hugstormun, Мозговой Шторм itd.).

- 9 plików `dictionaries/<kod>/gui/dokumentacja/tales.yaml::tresc.krok_1_tryby_gry`: ostatnie zdanie („Tryb można zmienić w trakcie gry…") wymienione na opis furtki „Edytuj tryb gry…" + dodatkowy passus o EVT_TEXT na polu nazwy gry. Zachowano fragment o fiolce.

- `gui_rezyser.py` (druga gałąź patcha, dialog wyboru):
  - Nowy helper `_zbierz_dostepne_projekty()` — `os.listdir(skrypty/)` + filtr na `.txt` minus `_streszczenie` suffix; sortowane alfabetycznie.
  - `_on_load` rozszerzone o dwie ścieżki: pole puste → `wx.SingleChoiceDialog` z listą, brak projektów → MessageBox info; pole wypełnione → bezpośrednia próba load (jak dotąd, kompatybilność z Enter w polu).
  - `_refresh_ui_state`: `_btn_load.Enable(pamiec_pusta)` — usunięty wymóg `nazwa_podana` (przy pustym polu dialog otwiera się przyciskiem).

- `gui_opowiesci.py` (druga gałąź patcha):
  - Nowy helper `_zbierz_dostepne_gry()` — `os.listdir(runtime/opowiesci/)` + filtr na `.game.json` (twarde kryterium stanu gry).
  - `_on_wczytaj` przepisane: `wx.FileDialog` (filtr rozszerzeń) zastąpione `wx.SingleChoiceDialog` z listą nazw. Brak gier → MessageBox info ze wskazówką jak zacząć.

- 8 nowych kluczy i18n × 9 języków w `dictionaries/<kod>/gui/ui.yaml`:
  - Reżyser: `dlg_wybierz_projekt_tytul`, `dlg_wybierz_projekt_lbl`, `brak_projektow_tytul`, `brak_projektow_tresc`
  - Opowieści: `dlg_wybierz_gre_tytul`, `dlg_wybierz_gre_lbl`, `brak_gier_tytul`, `brak_gier_tresc`
  
  PL ręcznie, 8 lokalizacji przez `--klucz` w `buduj_wielojezyczne_ui.py`. Manualny review halucynacji wykrył 3 rozjazdy ([[feedback_batch_retranslate_review]]): (a) EN użył przetłumaczonych nazw folderów `scripts/` i `runtime/stories/` zamiast literalnych `skrypty/` i `runtime/opowiesci/` z dysku → korekta ręczna; (b) DE zostawił polskie „Księga Świata" w środku niemieckiego komunikatu → korekta na canonical „Weltbuch"; (c) IS użył „leikföng" (zabawki) zamiast „leikir" (gry) → korekta gramatyczna. Pierwotny tekst PL też zawierał halucynacyjny cytat fikcyjnej nazwy przycisku — przepisany na opis bez literalnego cytowania nazwy, co poza akuratnością wprowadza future-proofing przy ewentualnej zmianie nazw przycisków.

- Stare klucze i18n `opowiesci.dlg_wczytaj_tytul` i `opowiesci.dlg_wczytaj_filtr` (używane przez wycofany `wx.FileDialog`) usunięte z `pl/gui/ui.yaml`; w pozostałych 8 językach pozostały jako sieroty (nieużywane, nie szkodzą — sprzątnięte zostaną przy okazji następnego pełnego refactora i18n).

- **Cancel → Anuluj (fix lokalizacji wbudowanych dialogów wxPython)**: po wdrożeniu (2) podczas manualnego testu okazało się, że `wx.SingleChoiceDialog` na PL-systemie pokazuje angielską etykietę „Cancel" — wbudowane dialogi wxPython ignorują nasz i18n, używają lokalizacji systemowej Windows. wxPython nie ma metod `SetCancelLabel` / `SetOKCancelLabels` na tej klasie (sprawdzone dynamicznie: `hasattr(dlg, 'SetCancelLabel') == False`), więc fix przez `dlg.FindWindowById(wx.ID_CANCEL).SetLabel(t("common.btn_anuluj"))` po stworzeniu dialogu. Zastosowane w `_on_load` Reżysera i `_on_wczytaj` Opowieści (2 miejsca, ~5 linii każde + komentarz). Alternatywa przez `wx.Locale` byłaby destrukcyjna dla innych wbudowanych dialogów (FileDialog → „Otwórz"/„Open" rozjazd).

- **Breaking change: pliki Opowieści przeniesione do `opowiesci/`**. Bug source: po wdrożeniu (2) dialog wyboru projektu Reżysera (`_zbierz_dostepne_projekty()` skanujący `skrypty/`) widział też pliki `.txt` gier Opowieści, bo do v15.2.2 oba moduły zapisywały do tego samego folderu. Wczytanie gry Opowieści w Reżyserze dawało `saved_mode in (3,4,5)` poza akceptowanym zakresem `(1,2)` Reżysera → fallback `_zapisany_tryb = None` → wszystkie 3 tryby RadioBox enabled (regresja ochrony z fixu nr 1). Decyzja: rozdzielenie domen przez fizyczne wydzielenie folderów (Opcja B w dyskusji architektonicznej, alternatywa A „zrezygnować z .txt na bieżąco, generować na finał" odrzucona — większy refactor + regresja live-preview).

  Zmiany:
  - `core_opowiesci.py`: `_sciezka_txt` i `_sciezka_md` używają `OPOWIESCI_DIR` zamiast `SKRYPTY_DIR`. Dodano `_sciezka_txt_legacy` / `_sciezka_md_legacy` (używane wyłącznie do detekcji starych ścieżek w auto-migracji). `dopisz_do_txt` i `rebuild_ksiega_swiata` tworzą folder `opowiesci/` przez `os.makedirs(..., exist_ok=True)`.
  - `core_opowiesci.ProjektOpowiesci.wczytaj()`: auto-migracja jednorazowa na pierwszy load gry sprzed v15.2.3 — pętla po (`_sciezka_txt`/`_sciezka_md`, legacy fns); jeśli nowy plik nie istnieje, a stary istnieje, i jest `.game.json` (potwierdzenie że to faktycznie gra Opowieści, nie projekt Reżysera o przypadkowej zbieżnej nazwie) → `os.rename`. Cichy `try/except OSError` na wypadek read-only USB / pliku zablokowanego przez Notatnik.
  - `.gitignore`: dodano `opowiesci/`.
  - `build_release.py:618`: dodano `'opowiesci'` do `IGNOROWANE_FOLDERY`.
  - `installer.iss:64`: dodano `opowiesci\*` do `Excludes:` (analogicznie do istniejącego `skrypty\*`).
  - `gui_konwerter.py`: BEZ ZMIAN — używa `wx.FileDialog` z manualną nawigacją gracza, zadziała z dowolnego folderu. Manuale w 9 jzk dostają tylko aktualizację ścieżki w opisie use-case'u (konwerter wczytuje plik Opowieści → ścieżka `opowiesci/<gra>.txt` zamiast `skrypty/<gra>.txt`).

- **Normalizacja pre-existing halucynacji LLM w manualach × 9 jzk**: przy okazji breaking change zostały wykryte pre-existing halucynacje pochodzące z batch retranslate poprzednich wersji — LLM zlokalizował nazwy folderów na dysku (które powinny być literałami PL: `skrypty/`, `runtime/skrypty/`, `runtime/opowiesci/`) na lokalne tłumaczenia: EN `scripts/`, ES `runtime/historias/`, FI `käsikirjoitukset/`, FR `scripts/<nom>`, itp. Te ścieżki nigdy nie wskazywały na rzeczywiste pliki — bug w docs od kilku wersji wstecz. Naprawione jednym przebiegiem regex (`buduj_wielojezyczne_ui` nie umie tego — to dotyczy plików `dokumentacja/*.yaml`, nie `ui.yaml`): w `tales.yaml × 8 jzk` znormalizowano każdy `<dowolny prefix>/<placeholder>.{txt,md}` w kontekście Opowieści → `opowiesci/<placeholder>.{txt,md}`, plus `runtime/<dowolny>/<placeholder>.mode` → `runtime/skrypty/<placeholder>.mode` (literała ścieżka wspólna z Reżyserem), plus `runtime/<dowolny>/<placeholder>.{game.json,story.jsonl}` → `runtime/opowiesci/<placeholder>...`. Łącznie 40 linii × 8 jzk. PL miało już literalne ścieżki, więc tam tylko fix wzmianki o starym `skrypty/` (replace_all). W `manual.yaml × 9 jzk` linia o konwerter+Opowieści (`plik <prefix>/<X>.txt wygenerowany przez moduł Interaktywnych Opowieści`) znormalizowana na `opowiesci/<X>.txt`.

- **Przycisk „Otwórz plik narracji…" (łata luki pamięci streszczenia)**: drugi bug zgłoszony podczas manualnego testu — luka architektoniczna istniejąca od kilku wersji wstecz, ale zauważona dopiero teraz. Mechanizm: `core_rezyser.ProjektRezysera.wczytaj` w linii 458-467 ma logikę „streszczenie eager bije pełną historię" — gdy plik `.summary.txt` istnieje, `full_story = ""` i `czy_historia = False`. To jest CELOWE dla pełnego flow (gracz wygenerował streszczenie z Burzy, świadomie wyczyścił pamięć bieżącą żeby zwolnić okno kontekstu), ale niewystarczająco zabezpieczone na flow degenerowany (gracz wpisał ręczną notatkę w pole Pamięci Długotrwałej i kliknął Zapisz Streszczenie zanim cokolwiek istotnego było w full_story).

  Po reload AI dostaje: Księga Świata + krótka notatka → halucynuje bez kontekstu tonu i ostatnich scen. Bug istnieje od pierwszej publikacji aplikacji — nie ma jak go naprawić w pełni bez większego refactora (priorytet streszczenia jest globalną konwencją). Łata polega na DODANIU recovery flow, nie na zmianie logiki priorytetu: nowy przycisk otwiera istniejący plik `.txt` (pełna narracja wciąż istnieje na dysku — nigdy nie była kasowana, tylko `full_story` w RAM zerowana) w systemowym edytorze. Gracz może z niego skopiować ostatnie sceny do pola Pamięci albo dopisać/edytować końcówkę ręcznie.

  Zmiany w kodzie:
  - `gui_rezyser.py`: nowy `_btn_otworz_narracje` w `_zbuduj_pasek_pliku` (file_row obok Hard Reset). Bind do `_on_otworz_narracje` w `_bind_events`. Enable state w `_refresh_ui_state`: `nazwa_podana` (istnienie pliku sprawdzane w handlerze — cheaper UX). Handler woła helper `_otworz_w_edytorze(sciezka)` (`os.startfile` / `subprocess.Popen open|xdg-open`, wzorzec z `gui_manager_regul._otworz_w_edytorze_tekstu`). Nowy import `platform`, `subprocess`.
  - `gui_opowiesci.py`: analogiczny `_btn_otworz_narracje` w `_zbuduj_pasek_pliku`, ale z modalnym ostrzeżeniem PRZED otwarciem — `.txt` w Opowieściach to TYLKO narracja TTS, źródłem prawdy stanu gry jest `.game.json` (postacie, lokacja, ekwipunek, wątki). Edycja `.txt` może wprowadzić rozjazd: np. gracz opisze że postać zginęła, a w stanie gry nadal żyje. Ostrzeżenie pokazuje dialog YES_NO z NO_DEFAULT (bezpieczna akcja domyślna).
  - 14 nowych kluczy i18n × 9 jzk (Reżyser: `btn_otworz_narracje_label/tooltip`, `blad_otwarcia_tytul/tresc`, `plik_narracji_brak_tytul/tresc`; Opowieści: te same + `otworz_narracje_ostrzezenie_tytul/tresc`). PL ręcznie, 8 lokalizacji przez `--klucz` w `buduj_wielojezyczne_ui.py`. Manualny review halucynacji wykrył lokalizacje nazw folderów w tooltipach (EN `scripts/<name>` zamiast `skrypty/<name>`, DE `skripte/<nazwa>`, etc.) — naprawione tym samym regex-skryptem co poprzednio (34 linie × 8 jzk).
  - Manuale × 9 jzk dostały dodatkową pozycję w liście przycisków paska pliku (Reżyser) i dodatkowy paragraf po opisie pola pełnej narracji (Opowieści, z ostrzeżeniem o ryzyku rozjazdu z `.game.json`). W PL manualu dodatkowo rozszerzony paragraf o Pamięci Długotrwałej z explicit opisem luki architektonicznej i wskazaniem na nowy przycisk jako recovery.

- 27 plików `docs/*.txt` zregenerowanych przez `generuj_dokumentacje.py --waliduj` (3 typy × 9 języków): nowa treść notki historycznej + bump 15.2.2 → 15.2.3 w nagłówkach + zaktualizowany opis przycisku „Wczytaj" w manualu (dwa ścieżki) i `/wczytaj` w tales (nowy dialog wyboru gry zamiast systemowego file pickera).

- 9 plików `readme.<iso>.md` + `readme.md` z bumpem numeru wersji.

- Naprawa lokalnego projektu `emilia_heist_audiobook` (poza repo — `skrypty/` i `runtime/` w `.gitignore`): `.mode` 1 → 2, `skrypty/emilia_heist_audiobook.txt` ucięty 26 bajtów (puste linie + „Akt 1" + „Scena 1" wstrzyknięte przez bug). Po naprawie `ProjektRezysera.wczytaj` raportuje `saved_mode=2`, narracja kończy się czysto na frazie „…myślowym pędem hakerki." + CRLF.

### Test plan

- ✅ Smoke test `RezyserPanel` (5 scenariuszy lifecycle `_zapisany_tryb` przez izolowany `wx.App(False)` bez `MainLoop`): start świeży / Skrypt utrwalony / Audiobook utrwalony / przeskok na Burzę po utrwaleniu / przełączenie przed utrwaleniem — wszystkie scenariusze: EnableItem zgodny z oczekiwaniami, panel struktury widoczny dokładnie wtedy gdy gracz może wstawić markery zgodne z `.mode`.
- ✅ Smoke test `OpowiesciPanel` (6 scenariuszy lifecycle: start bez projektu / utrwalony tryb 4 / pole nazwy zmienione na inną / powrót do bieżącej nazwy / inna nazwa + RB na Swobodny / brak projektu z dowolną nazwą).
- ✅ Smoke test budowy `OpowiesciPanel` we wszystkich 9 językach (PL/EN/DE/ES/FI/FR/IS/IT/RU): wszystkie 10 nowych kluczy i18n obecne, etykieta `_btn_edytuj_tryb` poprawnie przetłumaczona z akceleratorem `&`.
- ✅ Smoke test helpera `_zbierz_dostepne_projekty()` na lokalnej kopii repo: zwraca 2 legit projekty (`emilia_heist_audiobook`, `joanna_joana_conflict`), pomija pliki `_streszczenie.txt`.
- ✅ Smoke test helpera `_zbierz_dostepne_gry()` na lokalnej kopii repo: zwraca 1 grę (`joanna_joana_conflict`).
- ✅ Walidacja `generuj_dokumentacje.py --waliduj` przeszła po regeneracji 27 plików docs — wszystkie placeholdery rozwijają się.
- ✅ Manual ręczny w aplikacji (Reżyser): wczytanie projektu Audiobook, próba nawigacji strzałkami przez Burzę — Skrypt faktycznie pomijany.
- ✅ Manual ręczny SingleChoiceDialog w Reżyserze: wykryty bug Cancel/Anuluj, naprawiony przez `FindWindowById`.
- ✅ Test auto-migracji folderu na rzeczywistej grze `joanna_joana_conflict`: `.txt` + `.md` przeniesione ze `skrypty/` do `opowiesci/`, `ProjektOpowiesci.wczytaj` raportuje `saved_mode=5`, narracja kompletna.
- ✅ Helper `_zbierz_dostepne_projekty()` post-migracja zwraca już tylko `emilia_heist_audiobook` (Reżyser), `_zbierz_dostepne_gry()` zwraca `joanna_joana_conflict` (Opowieści) — czysta separacja domen.
- ⏳ Manual ręczny w aplikacji (Opowieści) — do wykonania post-release (smoke test furtki + EVT_TEXT na polu nazwy + dialog wyboru z Anuluj).

### Migracja z v15.2.2

Brak działań po stronie użytkownika. Aplikacja:
- Stare projekty Reżysera z istniejącym `.mode` (1 lub 2) — `_on_load` ustawi `_zapisany_tryb` z pliku, RadioBox zamknie się natychmiast po wczytaniu.
- Stare projekty Reżysera bez `.mode` (np. gracz nigdy nie kliknął przycisku struktury w starej wersji) — `_zapisany_tryb = None`, RadioBox wolny do pierwszej decyzji.
- Stare gry Opowieści z `.mode` lub `projekt.tryb` w `.game.json` — analogicznie, ze `wynik.saved_mode` lub fallback `projekt.tryb`.
- Stara ścieżka wczytywania w Reżyserze („wpisz nazwę + Enter") pozostaje funkcjonalna jako ścieżka eksperta — nikt z dotychczasowych workflow nie traci dostępu, gracze pamiętający nazwy projektów wczytują tak jak dotąd. Nowa ścieżka (dialog wyboru przy pustym polu) to dodatek dla niewidomych i nowych użytkowników.
- Stara ścieżka wczytywania w Opowieściach (systemowy `wx.FileDialog`) jest zastąpiona dialogiem listy — z punktu widzenia gracza zmiana wizualna, ale nawigacja jest prostsza (Tab + strzałki w liście zamiast 3-panelowego dialogu plików). Nie ma żadnych implikacji dla danych na dysku.
- **Migracja plików Opowieści ze `skrypty/` do `opowiesci/`** odbywa się automatycznie przy pierwszym wczytaniu każdej pre-15.2.3 gry — `ProjektOpowiesci.wczytaj()` wykonuje `os.rename()` z legacy ścieżki na nową. Gracz nie musi nic robić. Jeśli wolisz przyspieszyć — uruchom aplikację, wybierz „Wczytaj" w panelu Opowieści, wybierz po kolei każdą grę. Pliki przeskoczą; po zamknięciu aplikacji folder `skrypty/` zawiera już tylko projekty Reżysera.

Patch jest backward-compatible — auto-migracja pokrywa pre-15.2.3 gry przy pierwszym kontakcie. Nie ma scenariusza wymagającego ręcznej interwencji użytkownika.

---

## 15.2.2 — patch release (motyw przewodni: wielojęzyczność bota tiflotecnia-patch — 9 szablonów email + bilingual komentarze workflow)

*Punkt wyjścia: v15.2.1 (8338f3a) → 1 commit hotfix workflow (bc80c1e: usunięcie duplikatu `gh issue comment` w patch-bot.yml, naprawa logiki bota wysyłającego wiadomość w odpowiedzi na zgłoszenie o patch) → wielojęzyczna refaktoryzacja `send_patch.py` + `patch-bot.yml` → v15.2.2.*

### TL;DR

Wcześniejszy `tiflotecnia-patch` bot odpowiadał użytkownikom wyłącznie po polsku — jeden zahardkodowany szablon `zbuduj_tresc_maila()` z polską treścią, niezależnie od tego czy issue było pisane po angielsku, niemiecku czy fińsku. Dla wielojęzycznej aplikacji wspierającej 9 języków natywnie był to jaskrawy niedopatrzenie user-facing. Patch wprowadza:

1. **Detektor języka `lingua-language-detector`** zacisnięty do 9 wspieranych języków (PL/EN/DE/ES/FI/FR/IS/IT/RU) — `detector.detect_language_of(issue_body)` po usunięciu adresu email z tekstu analizy (żeby `foo@bar.com` nie zaburzał detekcji).
2. **Słownik `TEMPLATES`** z 9 natywnymi szablonami `{subject, body}` — temat i treść maila tłumaczone ręcznie (kompletne tłumaczenie LLM dla 9 krótkich szablonów to przerost; ryzyko halucynacji per [[feedback_batch_retranslate_review]] vs. ~10 min pracy ręcznej). Sufiks „Marek Uram" + link do patcha + numer issue jako placeholdery `{link}` i `{issue_number}` rozwijane przez `str.format()`.
3. **Fallback do ENGLISH** dla języków, których lingua wykryje poza listą 9 wspieranych (lub `None` przy ekstremalnie krótkim tekście, w szczególności gdy user prześle samym adresem email bez opisu) — z warningiem do stderr ułatwiającym debug w GitHub Actions. EN wybrany zamiast PL, bo wśród niewidomych użytkowników NVDA z całego świata znajomość angielskiego jest dużo bardziej powszechna niż polskiego.
4. **Bilingual komentarze workflow** (`patch-bot.yml`): potwierdzenie wysyłki + redact body są w formacie `PL: ... / EN: ...`. Komentarze są dla notyfikacji wątku publicznego — nie ma sensu mnożyć ich na 9 języków, EN + PL pokrywa większość przypadków.
5. **Sprawdź folder Spam** dodane do każdego z 9 szablonów (klasyczny problem nowych adresatów na Gmailu — pierwszy mail z nieznanej domeny często wpada do junk).
6. **Manual w 9 językach uszczelniony** — `dictionaries/<kod>/gui/dokumentacja/manual.yaml::tresc.krok_5_alarm_detekcja_jezyka` dostaje wstawkę zachęcającą do dorzucenia 2-3 zdań opisu w swoim języku w treści issue, z explicit listą 9 wspieranych języków + informacją że bez opisu odpowiedź przyjdzie po angielsku. Wcześniejsze brzmienie sugerowało tylko „adres email w treści" — niewidomy niemiec / włoch / hiszpan otwarłby issue z samym mailem, dostałby polski (lub teraz angielski) mail mimo, że bot wspiera jego natywny język. Tłumaczenia wstawki ręczne per jzk (~15 min pracy, vs. koszt API + ryzyko halucynacji LLM przy tak krótkim fragmencie kontekstu).

### Co nowego dla użytkownika końcowego

#### Mail z patchem w języku zgłoszenia

Jeśli zgłosisz issue z labelem `tiflotecnia-patch` po niemiecku, francusku czy fińsku — odpowiedź bota przyjdzie w tym samym języku. Wcześniej każdy dostawał polską wiadomość niezależnie od języka zgłoszenia, co dla użytkowników nieznających polskiego było całkiem niezrozumiałe (poza linkiem do patcha, który zawsze działał).

Wspierane języki maila (lingua-detected): **polski, angielski, niemiecki, hiszpański, fiński, francuski, islandzki, włoski, rosyjski**. Dla zgłoszeń w pozostałych językach świata, lub w przypadku gdy user prześle samym adresem email bez opisu (przy braku tekstu detektor nie ma czego analizować), bot fallbackuje na angielski.

Manuale w 9 językach (sekcja „Krytyczny haczyk Tiflotecnia Voices: zepsuta detekcja języka") zachęcają do dorzucenia w treści issue 2-3 zdań opisu w swoim języku — to wystarczający kontekst dla detektora, żeby zaklasyfikować poprawnie nawet podobne języki (np. polski vs rosyjski, włoski vs hiszpański). Sam pojedynczy zwrot grzecznościowy + email to za krótko (patrz „Pułapka detekcji" w sekcji „Smoke test detektora pre-merge" niżej).

#### Komentarze w wątku issue — PL/EN

Dwa komentarze, które bot dokleja do issue w trakcie obsługi, są teraz bilingual:

- **Potwierdzenie wysyłki**: `PL: Patch wysłany na podany adres, zgłoszenie zostaje zamknięte. Jeśli nie widzisz wiadomości, sprawdź folder Spam lub Wiadomości-śmieci. / EN: The patch has been sent and the issue is now closed. If you don't see the email, please check your Spam or Junk folder.`
- **Redact body issue** (po wysłaniu patcha kasuje się email z treści): `[redacted by bot — patch wysłany / Patch sent]`

Komentarz awaryjny w przypadku braku emaila w treści też dostał wariant EN: `PL: Nie znalazłem adresu email w treści — uzupełnij proszę. / EN: I couldn't find an email address in the body — please provide one.`

### Pod maską

- `VERSION`: `15.2.1` → `15.2.2` (patch tag, [[feedback_hotfix_release]] — bez nadpisywania artefaktów v15.2.1 Release).
- `.github/scripts/send_patch.py`: 102 linie → ~210 linii. Sekcje:
  - `LANGUAGES` + `LanguageDetectorBuilder.from_languages(*LANGUAGES).build()` jako module-level detector (zbudowany raz na proces — `LinguaLanguageDetector` to ciężki obiekt z modelami statystycznymi per język).
  - `TEMPLATES: dict[Language, dict[str, str]]` — 9 wpisów `{subject, body}` z placeholderami `{issue_number}` i `{link}`.
  - `KOMENTARZ_BRAK_EMAILA` jako bilingual stała.
  - `main()` → wykrywa email regexem (jak dotąd) → strip `recipient_email` z `tekst_do_analizy` → `detector.detect_language_of(tekst_do_analizy)` → fallback do `Language.ENGLISH` jeśli wynik nie w TEMPLATES → render subject + body przez `str.format()` → wysyłka SMTP_SSL na `smtp.gmail.com:465` (bez zmian).
  - Logging do stderr/stdout przywrócony (w poprzednim WIP-diff zostały usunięte) — debug GitHub Actions wymaga konkretnych komunikatów typu „Brak SMTP_USER w env", „gh issue comment zfailowało", „Wykryto język: GERMAN", „Wiadomość wysłana pomyślnie na X".
- 9 plików `dictionaries/<kod>/gui/dokumentacja/manual.yaml::tresc.krok_5_alarm_detekcja_jezyka` — wstawka zachęcająca do opisu w swoim języku, między „etykietą `tiflotecnia-patch` i adresem email w treści" a „Automatyczny bot natychmiast zamknie issue".
- 9 plików `docs/manual.<iso>.txt` zregenerowanych (1 nowe zdanie + bump 15.2.1 → 15.2.2). Wszystkie 27 plików `docs/*.txt` + `readme.<iso>.md` mają bumpa numeru wersji w nagłówku.
- `.github/workflows/patch-bot.yml`: dodano krok `Instalacja zależności: pip install lingua-language-detector` (bo `setup-python@v5` startuje czysty interpreter). Bilingual stringi w komentarzach issue + redact body.
- Naprawa PL szablonu przy okazji: „Jeśli nie widzisz **załącznika**" → „Jeśli nie widzisz **wiadomości** w skrzynce odbiorczej" (link siedzi w treści maila, nie ma żadnego załącznika — dotychczasowa formuła była mylła).

### Smoke test detektora pre-merge

```
pl → POLISH       en → ENGLISH      de → GERMAN
es → SPANISH      fi → FINNISH      fr → FRENCH
is → ICELANDIC    it (≥2 zdania) → ITALIAN
ru → RUSSIAN
```

Pułapka detekcji: ekstremalnie krótki tekst (4-5 słów po włosku typu „Ciao, mandami la patch su X") trafia do GERMAN — to granica możliwości statystycznego detektora przy minimalnym sample. Realne issue body po patchu manuala ma zwykle 1-3 zdania kontekstu („Mam problem z X, proszę o patcha, mój email Y"), bo manual w 9 językach zachęca do dorzucenia opisu w swoim języku. Dla edge case'u „samym adresem email bez opisu" detektor zwróci `None` → fallback ENGLISH. Dla niezdiagnozowanych edge case'ów w przyszłości (np. dwa zdania po włosku idą do GERMAN) do rozważenia: progowanie `compute_language_confidence_values` zamiast top-1 albo dodatkowa heurystyka „jeśli wynik jest GERMAN, ale tekst zawiera typowe IT słowa kluczowe (patch, ciao, mandami), wybierz IT".

### Breaking changes

Subtelne. Bot zachowuje istniejące zachowanie dla zgłoszeń polskich (TEMPLATES[POLISH] zawiera identyczną treść co poprzedni `zbuduj_tresc_maila()` z drobną korektą „załącznik" → „wiadomość"). Zmienia się jednak fallback dla zgłoszeń poza 9 wspieranymi językami: do v15.2.1 dostawały polski mail, od v15.2.2 dostają angielski. W praktyce: niewidomy user z któregoś z pozostałych krajów świata, który wcześniej widziałby polską treść po zaufaniu Google Translate, teraz dostanie angielską (znacznie lepiej dla większości).

### Dependency

Nowa runtime-dependency tylko dla bota w CI (`lingua-language-detector`) — instalowana per-job w `patch-bot.yml`, NIE w `requirements.txt` aplikacji (silnik desktopowy nie potrzebuje detekcji języka — wybiera ją user przez `Język → ...` w menu). Wersja niepinnowana — bot odpala raz na issue z labelem `tiflotecnia-patch`, koszt cold-installa to ~5 sek per uruchomienie, akceptowalnie.

---

## 15.2.1 — patch release (motyw przewodni: naprawa halucynowanego tytułu manuala w de/fi/fr/is/it)

*Punkt wyjścia: V15.2 (9344b61) → patch yamli + regen docs → V15.2.1 (8338f3a).*

### TL;DR

Wizualna weryfikacja v15.2 (uruchomienie installera EXE po sanity check pipeline'u updatera z VERSION lokalnie ustawionym na 15.1, żeby Inno fiński installer otworzył `manual.fi.txt`) wykryła PL leak w pierwszej linii manuala:

  fi: „Podręcznik Reżysera Audio AI - Kompletny Przewodnik (Wersja 15.2 – Julkaisuversio)"

Czyli polski tytuł + tylko sufiks `app.wersja` rozwinął się natywnie (bo to placeholder z `dictionaries/<kod>/gui/ui.yaml::app.wersja` — tłumaczony per jzk w 13.4+ z natywnym sufiksem typu „Julkaisuversio"). Pozostałe 4 jzk (fr/is/it/de) miały analogiczny problem: w pełni PL w fr/is/it, mieszany w de (przetłumaczył „Komplettanleitung", zostawił początek PL). EN/ES/RU zostały przetłumaczone poprawnie podczas tego samego batch retranslate.

### Co nowego dla użytkownika końcowego

#### Tytuł manuala — pełna lokalizacja w 9 jzk

Po patch wszystkie 9 jzk renderują tytuł w native:

- de: „Audio AI Regisseur Handbuch - Komplettanleitung (Version 15.2.1 – Veröffentlichungsversion)"
- fi: „Audio AI -ohjaajan käsikirja - Täydellinen opas (Versio 15.2.1 – Julkaisuversio)"
- fr: „Manuel du Réalisateur Audio AI - Guide complet (Version 15.2.1 – Version de Publication)"
- is: „Handbók Audio AI leikstjórans - Heildarleiðarvísir (Útgáfa 15.2.1 – Útgáfuútgáfa)"
- it: „Manuale del Regista Audio AI - Guida completa (Versione 15.2.1 – Versione di Pubblicazione)"

Konwencja: brand `Audio AI` zostaje literalny (analogicznie do EN „Audio AI Director Manual" — to opisowa nazwa produktu w kontekście manuala, NIE oficjalny `app.nazwa` „Audio Director GPT" z ui.yaml), „Reżyser" tłumaczone na lokalny ekwiwalent (Regisseur/ohjaaja/Réalisateur/leikstjóri/Regista), „Podręcznik" + „Kompletny Przewodnik" tłumaczone idiomatycznie.

### Pod maską

- `VERSION`: `15.2` → `15.2.1` (patch tag, zgodnie z regułą hotfix = X.Y.Z+1, bez nadpisywania artefaktów release'u 15.2 — złoty v15.2 nietknięty, użytkownicy z v15.2 dostaną aktualizację do v15.2.1 przez `core_updater.sprawdz_aktualizacje()` które porównuje semver).
- 5 plików `dictionaries/<kod>/gui/dokumentacja/manual.yaml::tresc.naglowek` z naprawioną pierwszą linią (tłumaczenia ręczne, nie autotłumacz — koszt API + halucynacje LLM przy ponownej iteracji).
- 28 plików `docs/<rdzen>.<iso>.txt` + `readme.<iso>.md` zregenerowanych z bumpniętym numerem wersji (placeholder `{numer_wersji}` w nagłówkach + 1 zmieniona linia tytułu manuala).
- Reguła do `[[feedback_batch_retranslate_review]]` (3-ci powtarzalny hotspot halucynacji LLM): **PL literały w pierwszej linii pliku traktowane jako brand product name** — LLM lubi je zachować 1:1 w obcych jzk, szczególnie gdy fraza zawiera nazwę produktu (np. „Podręcznik Reżysera Audio AI"). Cross-check po batch retranslate: `head -1 docs/manual.<iso>.txt` per każdy obcy jzk, weryfikuj że pierwsze słowo NIE jest polskie.

### Breaking changes

Brak.

---

## 15.2 — minor release (motyw przewodni: domknięcie user-facing — menu Pomoc, README 9 jzk, Inno akcja, fiolka w Mniejszym Złu)

*Punkt wyjścia: v15.1 (62d18fa) → 16 commitów na `main` realizujących dziesięć równoległych wątków: (1) fiolka task #1; (2) JSON prompts Reżysera + persystencja task #2 (4 fazy); (3) refactor docs YAML + autotłumacz `--klucz` task #3; (4) Tiflotecnia Voices content + bot tiflotecnia-patch task #4 + #8; (5) Inno akcja post-install task #5; (6) README wielojęzyczne 9 jzk task #6; (7) migracja dictionaries.yaml na dict-schemat + sekcja Opowieści task #9; (8) menu Pomoc + refaktor opowiesci→tales task #10; (9) bug pl/podstawy.yaml (Ś); (10) fix `.github` exclude z paczki release.*

### TL;DR

15.2 zamyka serię „polish wszystkiego co user-facing", którą zostawiliśmy świadomie po 15.0/15.1 (one koncentrowały się na silniku Opowieści, ten release koncentruje się na codzienności użytkownika):

**Fiolka w trybie Mniejsze Zło** (nowość) — po czterech turach gry w polu wyborów pojawia się dodatkowa ZERO-numerowana opcja „Odkorkuj fiolkę" i zostaje do końca rozgrywki jako reusable wybór. Działanie celowo nieprzewidywalne: ~60% szkodliwe (zatruwa/kaleczy/oślepia), ~30% zaburza percepcję/ducha (halucynacje/zmieniona mowa/panika), ~10% rzadko-korzystne (chwilowe wzmocnienie/pomocny duch/kluczowa informacja). Rozkład wymusza Python (`random.choices` po stronie aplikacji), LLM dostaje gotowy seed `{kategoria, opis}` i jedynie go narracjonalizuje — model nie ma jak „wymyślić" zbawiennego skutku poza losowaniem. Anti-deus-ex-machina: nawet sięgnięcie po fiolkę w momencie skrajnej beznadziei zwykle pogarsza sytuację, czasem po pierwszej z 60%-szkodliwych dawek już nigdy nie wrócisz.

**Menu Pomoc** (czwarte menu w menubar po Narzędzia/Plik/Język) — 3 podmenu otwierające `docs/manual.<iso>.txt` (F1), `docs/tales.<iso>.txt`, `docs/dictionaries.<iso>.txt` w domyślnym handlerze .txt (Notatnik/VS Code/co użytkownik ma skojarzone). ISO wybiera się dynamicznie z `i18n.aktualny_jezyk()` — czyli plik otwiera się w tym języku, w którym aktualnie używasz GUI. Brak pliku → MessageBox z lokalizowanym komunikatem. Akceleratory ALT zlokalizowane per jzk: `Po&moc` (PL Alt+M, nie kolizjuje z `&Plik=Alt+P`), `&Help` (EN), `&Hilfe` (DE), `A&ide` (FR), `Ay&uda` (ES), `&Aiuto` (IT), `&Ohje` (FI), `&Hjálp` (IS), `&Помощь` (RU).

**README wielojęzyczne 9 jzk** — refaktor z prostego dwujęzycznego pliku (PL ręczny + plan na EN mirror) na pełny generowany szablon w 9 językach. `dictionaries/<kod>/gui/dokumentacja/readme.yaml` z 13 sekcjami → `readme.md` (EN, kanoniczny GitHub landing bez sufiksu ISO przez nowy `smart_en` mode w `generuj_dokumentacje.KONFIG_SZABLONOW`) + 8 wariantów `readme.<iso>.md`. Każda wersja ma blok „Other languages:" z linkami markdown do pozostałych 8 jzk. Treść zaktualizowana do v15.2: tryby Opowieści, fiolka, Tiflotecnia Voices, wielojęzyczność (9 jzk), poprawione nazwy plików (run.bat zamiast Uruchom_Rezysera.bat, setup_dev.bat zamiast skonfiguruj_dev.bat, docs/manual.<iso>.txt zamiast instrukcja.txt).

**Inno installer „Otwórz instrukcję obsługi" po instalacji** (`[Tasks] openmanual` + `[Run]` z flagami `shellexec postinstall skipifsilent`). Domyślnie zaznaczone, na ekranie Finish. Plik wybierany dynamicznie funkcją `GetManualISO()` w `[Code]` przez `ActiveLanguage()` — instalator PL → `manual.pl.txt`, instalator DE → `manual.de.txt`, instalator EN → `manual.en.txt`, itd. Wspierane natywnie 8 z 9 wdrożonych jzk (en/pl/de/es/fi/fr/it/ru — wszystkie z oficjalnym `.isl` w pakiecie Inno Setup 6); tylko `is` (islandzki) jest pomijany przez `build_release.py::buduj_wpisy_inno()` z warningiem `⚠ Skipping language 'is'` (brak `Icelandic.isl` w oficjalnym pakiecie). Etykiety menu Inno w 8 jzk (`AdditionalActions` + opis taska + opis runa) w `[CustomMessages]`.

**Rebrand Vocalizer → Tiflotecnia Voices for NVDA** (kontekst: Nuance Vocalizer poszedł do lamusa wraz z 32-bitowymi bibliotekami w NVDA 2026.1; Cerrence przekompilował głosy na 64-bity, Tiflotecnia wydała je pod nową nazwą jako `.nvda-addon` w NVDA Add-on Store). Rozdział „Tiflotecnia Voices for NVDA" w manualu (9 jzk) z procedurą migracji + alarm o krytycznym haczyku detekcji języka (override per-litera wygrywa pierwszym poziomem nad ISO `lang=fi`, w obrębie tego samego alfabetu) + diagnostyczny patch wysłany do deweloperów Tiflotecnia. **Bot tiflotecnia-patch** w GitHub Actions: użytkownik otwiera issue z labelem `tiflotecnia-patch` + emailem w treści, bot wysyła patcha na podany adres, redaktuje body issue (usunięcie emaila), zamyka i locka issue — wszystko z domyślnym `secrets.GITHUB_TOKEN`, bez PAT.

**JSON prompts Reżysera** (refactor inżynierski) — Burza Mózgów zamiast generować free-form tekst z linią „[Reżyserze: rozważ X]" zwraca strukturyzowany JSON `{opcje: [{tytul, opis, cel_sceny}, ...], streszczenie?: str}`. Python dokleja kontekstualnie linie reżyserskie + dyrektywę z `dictionaries/<jzk>/rezyser/tryb_burza.yaml::doklejka_celu_sceny`, LLM nie może ich naruszyć ani wymyślić własnych. Nowy panel opcji Burzy w GUI Reżysera (`_pnl_opcji_burzy` w `gui_rezyser.py`) z 3 przyciskami + opcjonalnym TextCtrl streszczenia; klik wstawia `[CEL SCENY]: <cel_sceny>` + doklejkę do pola Instrukcji + focus, NIE wysyła automatycznie. Persystencja w `runtime/skrypty/<nazwa>.brainstorm.json` (folder współdzielony z `.mode` dla DRY metadanych) — między wygenerowaniem Burzy a wysyłką prompta produkcyjnego (Skrypt/Audiobook), wtedy GUI woła `usun_brainstorm()`. Po wczytaniu projektu `wczytaj_brainstorm()` rebuilduje panel.

**Refaktor docs YAML na sekcje + surgical batch translation** — szablony `dictionaries/<kod>/gui/dokumentacja/*.yaml` od v15.2 mają `tresc: { klucz_sekcji: |\n... }` zamiast jednego wielkiego block-scalar `|`. Manual.yaml ma 25 sekcji, opowiesci/tales.yaml ma 12, dictionaries.yaml ma 13 (nowa sekcja `co_to_tryb_opowiesci` opisująca drugi główny tryb). Nowy flag `--klucz <key1,key2>` w `buduj_wielojezyczne_docs.py` dla surgical update analogicznie do `buduj_wielojezyczne_ui.py` — tłumaczysz tylko zmienioną sekcję (~2 kB) zamiast całego manuala (~68 kB), tańsze API-wise i bez ryzyka regresu już-naprawionych sekcji w innych częściach pliku. Generator `generuj_dokumentacje._scal_tresc_sekcjami` jest backward-compatible (rozpoznaje stary string-schemat i nowy dict-schemat).

**Refaktor `opowiesci` → `tales` w user-facing files** — konwencja braku polskiego w plikach typowo end-userowych (jak `manual.<iso>.txt` i `dictionaries.<iso>.txt` już są EN). 9× `git mv opowiesci.yaml → tales.yaml` + zmiana `id:` + grep podmiana `docs/opowiesci.<iso>.txt` → `docs/tales.<iso>.txt` w sekcji dokumentacja każdego readme.yaml. **NIE rusza wewnętrznych modułów Python** (`gui_opowiesci.py`, `opowiesci_ai.py`, folder `dictionaries/<kod>/opowiesci/` z YAMLami trybów gry, klucz YAML `co_to_tryb_opowiesci` w dictionaries.yaml, etykieta modułu GUI „Opowieści" w menu Narzędzia Ctrl+5).

**Fix bug pl/podstawy.yaml** — alfabet polski miał deklarowane 35 znaków (zgodnie z klasycznym ujęciem PL alfabet + Q,V,X), faktycznie miał 34 (brakowało `Ś`). Dodanie `Ś` po `S`, przed `T` → 35 znaków matchuje deklarację w manualu i fallback w `core_poliglota._algo_cezar`. Plus poprawiono kolejność końca z błędnego `AĄBC…ZŻŹ` na poprawne `AĄBC…ZŹŻ` (Ź przed Ż w polskim alfabecie).

15.2 to release **domykający tematy zaległe po serii 15.x** (fiolka odłożona z 15.0/15.1, menu Pomoc nigdy wcześniej, README wielojęzyczne nigdy wcześniej, Inno akcja nigdy wcześniej, JSON prompts refactor odłożony z 13.x) — następna duża zmiana (v15.3+) jeszcze nieplanowana.

### Co nowego dla użytkownika końcowego

#### Fiolka w trybie Mniejsze Zło
- **Aktywacja**: po `fiolka.prog_aktywacji_tur` (default 4) turach w trybie Mniejsze Zło pojawia się dodatkowa opcja `0. Odkorkuj fiolkę` w polu wyborów. Pozostaje tam do końca rozgrywki — reusable wybór.
- **Rozkład skutków**: ~60% szkodliwy (poison/wound/blind), ~30% perception/spirit disturbance (hallucination/altered speech/panic), ~10% rare_beneficial (temporary boost/helpful spirit/key info). Wagi w `dictionaries/<jzk>/opowiesci/tryb_mniejsze_zlo.yaml::fiolka.wagi_skutkow`, edytowalne bez programowania.
- **Anti-deus-ex-machina**: Python losuje rozkład PRZED wywołaniem LLM-a, model dostaje seed `{kategoria, opis}` jako wskazówkę do narracjonalizacji. Nie może wymyślić zbawiennego skutku, gdy losowanie powiedziało „60% szkodliwy".
- **Stłuczenie fiolki**: decyzja LLM-a w narracji — jeśli ustawi `stan.fiolka.zniszczona=True`, fiolka znika z wyborów do końca gry. Pierwsze otwarcie może być ostatnim.

#### Menu Pomoc (Alt+M w PL)
- **F1** otwiera `docs/manual.<iso>.txt` — główny manual.
- **Tryb Opowieści — przewodnik** otwiera `docs/tales.<iso>.txt`.
- **Słowniki — akcenty, szyfry, tryby AI** otwiera `docs/dictionaries.<iso>.txt` — opis paczki słowników pisany dla lingwistów bez Pythona.
- Plik wybierany dynamicznie z języka GUI (zmiana języka w menu Język interfejsu → następne kliknięcie Pomoc otwiera plik w nowym jzk po restarcie).

#### Inno installer — Otwórz instrukcję obsługi po instalacji
- Checkbox `Otwórz instrukcję obsługi` (lub odpowiednik per jzk instalatora) na ekranie Finish, domyślnie zaznaczony.
- Plik otwierany przez Windows shell association (.txt → Notatnik/VS Code).
- Działa natywnie w 8 wspieranych przez Inno Setup językach (en/pl/de/es/fi/fr/it/ru) — w każdym z nich `GetManualISO()` zwraca odpowiednie ISO, więc kliknięcie Finish otwiera `manual.<iso>.txt`. Islandzki (IS) jest pomijany przez `build_release.py::buduj_wpisy_inno()` z warningiem (brak `Icelandic.isl` w oficjalnym pakiecie Inno Setup), więc instalator nigdy nie wystartuje w trybie 'icelandic'.
- `installer.iss` nie jest wywoływany bezpośrednio przez iscc — `build_release.py` czyta plik, wycina sekcję `[Languages]…[Setup]` i wstawia dynamicznie wygenerowaną listę z `zbierz_jezyki_bazowe()` + `INNO_LANG_MAP`. Sekcja `[Languages]` w repo to placeholder (5 jzk) dla podglądu, faktyczna lista jest zawsze 8 jzk obsługiwanych przez Inno.

#### README wielojęzyczne na GitHubie
- `readme.md` — wersja EN, kanoniczny GitHub landing (renderowany domyślnie na stronie repo).
- `readme.pl.md` / `readme.de.md` / `readme.es.md` / `readme.fi.md` / `readme.fr.md` / `readme.is.md` / `readme.it.md` / `readme.ru.md` — pozostałe 8 wersji.
- Każda wersja ma na początku blok `**Other languages:** [English](readme.md) · [Deutsch](readme.de.md) · ...` z linkami do pozostałych 8 wersji jzk.

#### Tiflotecnia Voices for NVDA
- Rozdział „Tiflotecnia Voices for NVDA" w manualu (9 jzk) opisuje migrację z Vocalizera: instalacja jako `.nvda-addon` w Add-on Store, procedura upgrade w niższej cenie, lista dostępnych głosów (rozszerzenie biblioteki Vocalizera).
- Alarm „Krytyczny haczyk Tiflotecnia Voices: zepsuta detekcja języka" opisuje znaną regresję (override per-litera wygrywa pierwszym poziomem priorytetów nad ISO `lang=fi`, w obrębie tego samego alfabetu).
- **Bot tiflotecnia-patch** w repo (GitHub Actions, label `tiflotecnia-patch`): otwórz issue z labelem + adresem email w treści → bot wysyła patcha na podany adres + redaktuje body issue + zamyka i locka issue (workflow w `.github/workflows/patch-bot.yml`).

#### Refaktor opowiesci → tales w plikach user-facing
- `docs/opowiesci.<iso>.txt` → `docs/tales.<iso>.txt` — konwencja angielska analogicznie do `manual.<iso>.txt` i `dictionaries.<iso>.txt`.
- **NIE rusza** wewnętrznych elementów (folder `dictionaries/<kod>/opowiesci/` z trybami gry, etykieta przycisku/menu „Opowieści" w GUI, klucz YAML `co_to_tryb_opowiesci` w dictionaries.yaml). To zmiana czysto na poziomie nazw plików dokumentacji.

### Pod maską

#### JSON prompts Reżysera
- `opowiesci_ai.generuj_burze()` zwraca `WynikBurzy(opcje: list[OpcjaBurzy], streszczenie: str | None)`. Stary `generuj_fragment()` z free-form tekstem zachowany jako fallback dla przepisów spoza `id="burza"` z `zapis_do_pliku=false`.
- `SCHEMA_BURZA` w `opowiesci_ai.py` definiuje JSON schema: `opcje[1-5]` (yaml mówi 3 ale halucynacja 2 nie powinna blokować GUI), każda opcja ma `tytul` + `opis` + `cel_sceny`. Sufiksy alarm/streszczenie wymuszają opcjonalny klucz `streszczenie` (zastąpił wcześniejszy tag `<STRESZCZENIE>...</STRESZCZENIE>`); sufiks optymalizacja jawnie zakazuje klucza.
- **Persystencja `.brainstorm.json`** w `runtime/skrypty/<nazwa>.brainstorm.json` (DRY z `.mode` w tym samym folderze). Plik istnieje TYLKO między wygenerowaniem Burzy a wysyłką prompta produkcyjnego (Skrypt/Audiobook), wtedy GUI woła `usun_brainstorm()`. Po wczytaniu projektu `wczytaj_brainstorm()` rebuilduje panel opcji w GUI.
- **Dispatch w GUI**: `_wyslij_worker` rozróżnia `przepis.id == "burza"` → `rai.generuj_burze` (zwraca `WynikBurzy`) vs pozostałe → istniejący `rai.generuj_fragment`. Stary `_on_wyslij_done_burza` zachowany jako fallback.
- **GUI**: nowy `_pnl_opcji_burzy` (BLOK E.1b w `gui_rezyser.py`) z 3 przyciskami + opcjonalnym TextCtrl streszczenia. Klik opcji wstawia `[CEL SCENY]: <cel_sceny>\n\n<doklejka>` do pola Instrukcji + focus. NIE wysyła automatycznie — gracz dopisuje własne uwagi reżyserskie w linijce `[Reżyserze: ...]` przed wysyłką.

#### Refactor docs YAML
- `dictionaries/<kod>/gui/dokumentacja/*.yaml::tresc` zmienione ze stringa block-scalar `|` na dict-of-sections `{ klucz: |, ... }`. Generator `generuj_dokumentacje._scal_tresc_sekcjami` rozpoznaje oba schematy (backward-compat dla starych yamlów).
- Granularność sekcji: `manual.yaml` ma 25 (intro + 4 kroki + 12 podsekcji KROK 5 + 3 dalsze kroki + NVDA + 4 changelog), `tales.yaml` ma 12 (KROK 1-10 + intro + problemy), `dictionaries.yaml` ma 13 (8 underline-sekcji + 3 POZIOM 1/2/3 + intro + zakończenie + nowa sekcja `co_to_tryb_opowiesci`).
- **Surgical update przez `--klucz`** w `buduj_wielojezyczne_docs.py`: wczytuje istniejący docelowy yaml, podmienia TYLKO wybrane sekcje, scala z resztą, zapisuje. Wymaga że plik docelowy jest w nowym dict-schemacie (po pierwszym FULL retłumaczeniu). Cache wznawiania per-sekcja w `runtime/` (`temp_manual_krok_5_tiflotecnia_pl_to_en_*.jsonl`) — częściowy progress jednej sekcji nie psuje innych.

#### Generator: KONFIG_SZABLONOW (per-szablon override)
- `generuj_dokumentacje.KONFIG_SZABLONOW` mapuje id_szablonu → `{katalog, rozszerzenie, iso_w_nazwie}`. Default zachowuje `docs/<id>.<iso>.txt`. Wpis dla `readme` przekierowuje na `ROOT/<id>.<iso>.md` z trybem `iso_w_nazwie: smart_en` (en bez sufiksu ISO → `readme.md` jako GitHub landing).
- Nowy placeholder `{liczba_trybow_opowiesci}` w `_zbuduj_placeholdery_globalne` — analogiczny do `{liczba_trybow_rezysera}`, liczy pliki w `dictionaries/pl/opowiesci/`.

#### Bug pl/podstawy.yaml: brakujące Ś
- `dictionaries/pl/podstawy.yaml::alfabet` miał 34 znaki: `AĄBCĆDEĘFGHIJKLŁMNŃOÓPQRSTUVWXYZŹŻ` (brakowało Ś). Manual mówił 35, `core_poliglota._algo_cezar` fallback też miał 34. Dodanie `Ś` po `S`, przed `T` → 35 znaków matchuje deklarację. Plus poprawiono kolejność końca z błędnego `…ZŻŹ` na `…ZŹŻ`.
- Skutek dla użytkownika: jeśli ktoś zaszyfrował tekst polskim Cezarem na starszej wersji aplikacji (alfabet 34) i będzie chciał odszyfrować w v15.2 (alfabet 35), wynik dla tekstów z `Ś` rozjedzie się o jeden indeks. Bardzo wąski edge case (kto trzyma zaszyfrowane teksty z czasów v15.1?), ale warto wiedzieć.

#### Bot tiflotecnia-patch w GitHub Actions
- `.github/workflows/patch-bot.yml` — workflow odpalający się na `issues.opened` + `issues.labeled` jeśli label `tiflotecnia-patch`. Kroki: (1) Python skrypt `send_patch.py` wyciąga email z body issue regexpem, jeśli brak → komentuje issue „Nie znalazłem adresu email — uzupełnij proszę" i zostawia OPEN; (2) jeśli email jest → wysyła patch przez Gmail SMTP_SSL, redaktuje body issue (usunięcie emaila), zamyka, lockuje. Wszystko z domyślnym `secrets.GITHUB_TOKEN` (issues: write) + `secrets.SMTP_USER` + `secrets.SMTP_PASS` (Gmail App Password).
- **Decyzja architektoniczna**: patch Tiflotecnia jest proprietary (`tiflotecnia.com` w manifest.ini, brak GPL/MIT, brak publicznego repo upstream) — redystrybucja zmodyfikowanych plików `.py` jest nielegalna. Dystrybucja przez prywatny email zamiast Gist/repo. Manual wprost mówi „zakładamy że masz ważną licencję, nie weryfikujemy".

#### build_release.py — dynamiczne wstrzykiwanie 3 sekcji do tmp installer.iss
- `installer.iss` w repo to **placeholder z minimalnymi sekcjami EN-only** (sanity check przy `iscc installer.iss` bezpośrednio). Pełne 3 sekcje (`[Languages]`, `[Code]::GetManualISO`, `[CustomMessages]`) są wstrzykiwane do tmp `_installer_tmp.iss` przez `build_release.py::main()` przed wywołaniem `iscc`. Idea: cała logika multi-language w jednym miejscu (Python), dodawanie nowego języka nie wymaga ręcznej edycji `.iss`.
- Wymagania na nowy język: (a) `dictionaries/<kod>/podstawy.yaml` (kryterium `zbierz_jezyki_bazowe`); (b) `dictionaries/<kod>/gui/dokumentacja/manual.yaml` (kryterium `zbierz_jezyki_z_manualem` po regen); (c) wpis w `INNO_LANG_MAP` (mapa kod-ISO → para `(inno_nazwa, .isl)`, pre-populated 30 jzk z oficjalnej dystrybucji Inno Setup 6); (d) wpis w `INNO_MANUAL_MESSAGES_MAP` (pre-populated dla wszystkich 30 jzk z `INNO_LANG_MAP` — zachowawcze tłumaczenia 3 etykiet menu Pomoc per jzk, native speakerzy mogą zgłaszać szlif GitHub issue).
- **Smart filter printowy w `buduj_wpisy_inno`**: warning `⚠ Skipping language 'X': ...` leci TYLKO dla języków, które mają już folder `dictionaries/<kod>/` (czyli paczka istnieje, ale Inno jej nie obsługuje albo brakuje `.isl` w lokalnej instalacji — np. obecne ostrzeżenie dla `is`). Dla 22 jzk obecnych w mapach Pythona ale BEZ paczki w `dictionaries/` — `zbierz_jezyki_bazowe()` ich w ogóle nie zwraca, więc warning by leciał false-positive („pomijam czeski, którego nigdy nie miałeś"). Mapa nadmiarowa żyje cicho, pełni rolę pre-populated future-proof — dodanie czeskiej paczki kiedyś w przyszłości natychmiast aktywuje natywne etykiety Inno bez modyfikacji Python.
- **Kryterium dwustopniowe**: język wchodzi do tmp installer'a tylko gdy ma JEDNOCZEŚNIE (a) folder `dictionaries/<kod>/` + (b) `docs/manual.<iso>.txt` istnieje fizycznie (po regen docs w kroku wcześniejszym buildu). Sam `podstawy.yaml` nie wystarcza — manual musi być w paczce, inaczej akcja „Otwórz instrukcję obsługi" w instalatorze otworzy nieistniejący plik z user-friendly fallback'iem (brzydko).

### Breaking changes / migracja

#### opowiesci → tales w docs/
- `docs/opowiesci.<iso>.txt` przestaje istnieć w paczce v15.2. Zastąpione przez `docs/tales.<iso>.txt`.
- Skrypty użytkowników, które otwierały `docs/opowiesci.pl.txt` przez bezwzględną ścieżkę, muszą zostać zaktualizowane. Skrypty używające menu Pomoc lub Inno installera otwierającego instrukcję — bez zmian (działają z nową nazwą).

#### opowiesci.yaml → tales.yaml w paczce słowników
- `dictionaries/<kod>/gui/dokumentacja/opowiesci.yaml` przestaje istnieć — zastąpione przez `tales.yaml` w każdej z 9 paczek. Lingwiści, którzy fork'owali repo i dorabiali własne tłumaczenia dokumentacji trybu Opowieści, muszą przemianować swoje pliki.

#### Folder `dictionaries/<kod>/opowiesci/` — bez zmian
- Wewnętrzny folder z YAMLami trybów gry (tryb_wyborow.yaml, tryb_mniejsze_zlo.yaml, tryb_swobodny.yaml, tryb_burza.yaml, baza.yaml, cinematic_warning.yaml, streszczenie.yaml, zaczatki.yaml) **nie jest przemianowany** — to pliki konfiguracji silnika narracyjnego, manipulowane przez Manager Reguł, nie pojawiają się w paczce end-userowej jako pliki dokumentacji.

#### docs/dictionaries.<iso>.txt — wskazówka o Cezarze v15.2
- Sekcja „Co to jest szyfr?" → bullet „Cifrado César (klasyczny)" w `dictionaries.<iso>.txt` (9 jzk) ma teraz lokalny alfabet zgodny z faktycznym `<kod>/podstawy.yaml`. Wcześniej (do v15.1) trzymał stary opis „alfabet polski (AĄBCĆ…ZŻŹ, 35 znaków)" wbrew temu, że każda paczka ma własny lokalny alfabet (DE: 29, IT: 21, RU: 59 itd.). Dla użytkownika oznacza to, że szyfrowanie tekstu polskim Cezarem nadal daje wynik na 35-znakowym alfabecie polskim, ale opis w manualu zgadza się ze stanem faktycznym kodu.

---

## 15.1 — minor release (motyw przewodni: dojrzałość modułu Opowieści w 9 językach)

*Punkt wyjścia: V15.0 (37c1cb1) → 15 commitów na gałęzi `v15.1-zasady-swiata` realizujących cztery równoległe wątki: (1) Zasady świata — core + AI + GUI + i18n × 9 jzk; (2) natywne paczki promptów Opowieści dla DE/ES/FI/FR/IS/IT/RU + wzmocnienie PL i EN; (3) model AI per tryb + likwidacja `/ustawienia`; (4) refaktor `core_tokeny` (DRY tiktoken) + bugfixy GUI + konwerter ze sceniczną grupą tur.*

### TL;DR

15.1 dopina trzy luki, które po 15.0 zostały świadomie odłożone:

**Zasady świata** (nowy przycisk „Edytuj zasady świata…" w panelu Opowieści) to opcjonalny tekst, który silnik narracyjny respektuje przez całą grę — niezależnie od dłubiącego się streszczenia kontekstu. Zaprojektowane pod trzy typowe zastosowania: reguły fonetyczne (jak TTS ma wymawiać konkretne imię), reguły mechaniczne (prawa fizyki świata — „magia działa tylko w nocy"), reguły dramaturgiczne (długoterminowe napięcia między postaciami). Zapis razem ze stanem gry (`.game.json`), więc po wczytaniu gry zasady są zachowane.

**Natywne prompty 9/9 języków** zamykają temat „fallback do PL przy braku natywnej paczki", którym świadomie żyliśmy w 15.0. Każdy z 7 promptów systemowych (`baza`, `tryb_swobodny`, `tryb_wyborow`, `tryb_mniejsze_zlo`, `tryb_burza`, `streszczenie`, `cinematic_warning`) ma teraz ręcznie zatwierdzone tłumaczenie w `dictionaries/<iso>/opowiesci/*.yaml` dla wszystkich 9 wdrożonych języków (PL/EN/DE/ES/FI/FR/IS/IT/RU). Gracz EN dostaje system prompt po angielsku, gracz RU — po rosyjsku, itd. Jakość narracji w trybach z wyborami zauważalnie wzrasta vs fallback PL (LLM lepiej trzyma się stylu opisowego i konstrukcji moralnych zgodnych z lokalną tradycją kulturową). EN dostał też 5 natywnych Quick Start presetów (PL preset z domyślnym fallbackiem nadal działa, ale gracz EN może wybrać preset osadzony w anglojęzycznym kontekście kulturowym).

**Model AI dobierany twardo z trybu** likwiduje globalny override `/ustawienia` z 15.0. Helper `_model_dla_trybu(tryb)` zwraca `gpt-4o` dla TRYB_WYBOROW / TRYB_MNIEJSZE_ZLO i `gpt-4o-mini` dla TRYB_SWOBODNY / TRYB_BURZA. Powód: gpt-4o-mini regularnie łamał zasady świata w trybach z wyborami (proponował opcje neutralne mimo wymogu „wszystkie wybory niekorzystne", ignorował reguły fonetyczne imion) — narracje często nie nadawały się nawet do drobnej korekty. Wywołania pomocnicze (streszczenie, cinematic, status pamięci) hardkodują tańszy `oai.MODEL_DOMYSLNY` — to operacje meta, mini wystarcza. Usuniete: pole `self._aktualny_model`, metoda `_komenda_ustawienia`, wpisy `/ustawienia`/`/settings` w dispatcherze, 7 kluczy `dlg_ustawienia_*` w 9 plikach `ui.yaml`, akapit `/ustawienia` w 9 manualach Opowieści (zastąpiony brieflinem opisującym auto-wybór).

**Konwerter — auto-grupowanie tur w sceny** (bonus dorzucony przed release'em): jeśli wczytasz do Architekta Audiobooków plik `skrypty/<gra>.txt` wygenerowany przez moduł Opowieści, konwerter rozpoznaje znaczniki `--- Tura N ---` w 9 językach i co 5 tur wstawia H1 „Scena N" (lokalnie nazwana — „Scene N" / „Szene N" / „Сцена N" itd.). Pozostałe znaczniki są strippowane — meta-info „Tura 7" wymówiona przez TTS łamałaby immersję. Wynik: docx z naturalnym podziałem na sceny po kilka minut audio każda, gotowy do importu do ElevenLabs. Mechanizm jest auto-detekcyjny — zwykłe pliki audiobooków bez znaczników tury przetwarzane są tak jak dotąd.

15.1 to release **utrzymujący kierunek z 15.0** (dojrzewanie modułu Opowieści, nie wprowadzanie nowych modułów) — następna potencjalna duża zmiana (Fiolka — system inwentarza z dynamicznie używalnymi przedmiotami) idzie na v15.2 lub dalej, bo jeszcze 4o-mini sobie z nią nie poradzi dynamicznie.

### Co nowego dla użytkownika końcowego

#### Zasady świata — edytowalna mini-księga koncepcji
- **Przycisk „Edytuj zasady świata…"** w panelu Opowieści (skrót: akcelerator z `&E`). Otwiera dialog `wx.Dialog` z polem `wx.TextCtrl` multiline + hint pokazujący 3 przykłady reguł (fonetyczne / mechaniczne / dramaturgiczne).
- **Persystencja**: zasady zapisywane w `runtime/opowiesci/<gra>.game.json` w polu `zasady_swiata: str`. Po wczytaniu gry (przyciskiem albo `/wczytaj`) zasady są przywracane bez utraty.
- **Propagacja do promptu**: silnik narracyjny w `opowiesci_ai.generuj_ture()` doszywa zasady do systemowego promptu pod nagłówkiem oddzielającym (LLM widzi je jako twardą instrukcję, na równi z trybem rozgrywki).
- **Walidacja UX**: kliknięcie przycisku bez aktywnej gry → `wx.MessageBox` „Brak aktywnej gry" (zasady zapisują się razem ze stanem gry, więc grę musisz mieć założoną/wczytaną).
- **Tłumaczenia w 9 jzk**: hint w `dlg_zasady_swiata_hint` ma natywne przykłady w każdym języku (z zachowaniem polskiej fonetyki [dż] jako case-study — żeby reguła była demonstrowalna niezależnie od języka GUI).

#### Natywne prompty Opowieści w 9 językach
- **7 promptów × 7 nowych jzk** (DE/ES/FI/FR/IS/IT/RU): `baza`, `tryb_swobodny`, `tryb_wyborow`, `tryb_mniejsze_zlo`, `tryb_burza`, `streszczenie`, `cinematic_warning`. Ręczne tłumaczenia, nie autotłumacz — żeby uniknąć halucynacji w terminologii narracyjnej.
- **EN — wzmocnienie**: 7 promptów EN doprecyzowane (były bardziej dosłowne tłumaczenia z PL z 15.0); plus EN dostał 5 natywnych Quick Start presetów osadzonych w anglojęzycznym kontekście kulturowym.
- **PL — wzmocnienie**: tryb Mniejsze zło dostał wzmocnienie eskalacji moralnej (LLM bardziej rygorystycznie odrzuca „neutralne" opcje); spójność wyborów A-E poprawiona (mniej halucynacji formatu).

#### Model AI per tryb — bez togglla
- **Wybory + Mniejsze zło** → `gpt-4o` (droższy, ale rygorystycznie trzyma się zasad świata i trybu).
- **Swobodny + Burza** → `gpt-4o-mini` (szybszy i tańszy; gracz steruje fabułą, więc nie wymaga ciężkiej reżyserii).
- **Likwidacja `/ustawienia`**: gracz nie wybiera modelu — system robi to za niego optymalnie dla danego trybu. Mniej decyzji = mniej rozproszenia.
- **Wywołania pomocnicze** (streszczenie kontekstu, cinematic warning, oblicz_status_pamieci) hardkodują `oai.MODEL_DOMYSLNY` = `gpt-4o-mini`. Tania obsługa meta, nie wymaga 4o.

#### Konwerter — grupowanie tur w sceny H1 (auto-detekcja Opowieści)
- **Detekcja** znaczników `--- Tura N ---` przez regex pokrywający 9 wariantów językowych (Tura/Turn/Runde/Turno/Vuoro/Tour/Umferð/Turno/Ход).
- **Grupowanie**: co `TURY_NA_SCENE=5` tur → nowy H1 „Scena N" (etykieta z i18n `konwerter.scena_naglowek_format` per jzk).
- **Strippowanie**: pozostałe znaczniki tury usuwane z wyniku — meta-info nie pojawia się w audiobooku.
- **Auto-detekcyjne**: licznik tur pozostaje 0 dla plików bez znaczników → zwykłe pliki audiobooków bez zmian.

#### Bugfixy GUI Opowieści
- **Skrót Ostatniej tury** (`opowiesci.last_turn` field): cięcie odbywa się na granicy zdania (znak `.`/`!`/`?`/`…`) zamiast w środku słowa — czytniki ekranu nie tną teraz w połowie wyrazu.
- **Persist wyborów po wczytaniu**: tablica `ostatnie_wybory` w `.game.json` (nowe pole, opcjonalne) — po wczytaniu gry przyciski A-E są odtwarzane, gracz nie musi czekać na fresh turę.
- **Klik wyboru nie wysyła**: kliknięcie przycisku wyboru wstawia tekst do pola akcji bez auto-wysyłki. Gracz może edytować/dodać kontekst przed `Wyślij`.

### Architektura — co dokładnie zmienia się w kodzie

#### Nowe pliki
- `core_tokeny.py` (~109 linii): wspólny moduł tiktoken dla Opowieści + Reżysera (DRY). `policz_tokeny(tekst, model="gpt-4o-mini") -> int` z fallbackiem do `o200k_base` przy braku tiktoken-cache. Wspólne `OBLICZ_STATUS_PAMIECI(payload_tokens, MAX_TOKENS=128_000)` z 4 progami (`czysta`/`OK`/`warning`/`alarm`).
- `dictionaries/<iso>/opowiesci/*.yaml` × 7 jzk × 7 promptów = 49 nowych plików (DE/ES/FI/FR/IS/IT/RU). EN dodatkowo dostał `zaczatki.yaml` z 5 presetami.

#### Modyfikowane
- `core_opowiesci.py` — dodane pole `zasady_swiata` w schema `.game.json`; `wczytaj()` defensywnie czyta z `.get("zasady_swiata", "")` dla forward-compat z grami 15.0 (brak pola → puste zasady, zachowanie identyczne z 15.0).
- `core_rezyser.py` — refaktor `policz_tokeny` deleguje do `core_tokeny.policz_tokeny` (DRY).
- `opowiesci_ai.py` — helper `_model_dla_trybu(tryb)` zwraca model per tryb. `generuj_ture()` doszywa `zasady_swiata` do system prompt. Usunięto `MODEL_KEY` settings.
- `gui_opowiesci.py` — nowy widget „Edytuj zasady świata…" z dialogiem. Bugfix `_skroc_ostatnia_ture()` (granica zdania). `_on_wybor_btn()` nie wysyła auto. Persist `ostatnie_wybory` z `.game.json`. Usunięto `_komenda_ustawienia` + dispatcher entries `/ustawienia`/`/settings`.
- `gui_konwerter.py` — `_REGEX_TURA` + `TURY_NA_SCENE=5` + branch w pętli `_on_build` z licznikiem scen.
- `rezyser_ai.py` — `policz_tokeny` deleguje do `core_tokeny` (DRY).
- `dictionaries/<iso>/gui/ui.yaml` × 9 — nowe klucze `btn_zasady_swiata_*`, `dlg_zasady_swiata_*`, `status_zasady_zapisane`, `zasady_bez_gry_*`, `konwerter.scena_naglowek_format`. Usunięte: 7 kluczy `dlg_ustawienia_*` (były tylko w EN i PL z 15.0).
- `dictionaries/<iso>/gui/dokumentacja/opowiesci.yaml` × 9 — nowy KROK 4 „Zasady świata" + przenumerowanie KROK 5-10 + brief auto-wyboru modelu (zamiast `/ustawienia`).
- `dictionaries/<iso>/gui/dokumentacja/manual.yaml` × 9 — akapit „Tryb Opowieści: automatyczne grupowanie tur w sceny" w KROK 6 (Architekt Audiobooków).
- `dictionaries/pl/opowiesci/tryb_mniejsze_zlo.yaml`, `tryb_wyborow.yaml` — wzmocnienie eskalacji moralnej + spójność wyborów.

---

## 15.0 — major release (motyw przewodni: piąty moduł „Interaktywne Opowieści")

*Punkt wyjścia: V14.0 (90b244e) → 9 commitów na gałęzi `v15.0-opowiesci` realizujących sześć faz wdrożenia (housekeeping → szkielet GUI → silnik LLM JSON-schema → lifecycle plików → slash-komendy + tiktoken + cinematic → YAML refaktor + Quick Start PL → batch UI 8 języków → manuał + docs 8 języków → release V15.0).*

### TL;DR

15.0 dodaje **drugi główny tryb aplikacji** obok Reżysera — moduł `Opowieści` (skrót `Ctrl+5`). To interaktywna fikcja drugoosobowa generowana przez OpenAI w roli storytellera w stylu „Tales of Consequence": narracja w drugiej osobie liczby pojedynczej („Idziesz przez mglisty las, czujesz zapach wilgotnych liści…"), gracz reaguje wpisując akcję wolnym tekstem albo klikając jeden z 3-5 przycisków-wyborów. Cały moduł zaprojektowany z myślą o niewidomych graczach: pole narracji to `wx.TextCtrl readonly multiline` (NVDA czyta liniowo), wybory to dynamiczne `wx.Button` z tooltip-ami, w trybie Swobodnym obszar wyborów jest całkowicie ukryty (Tab go pomija, NVDA nie wciąga), każda zakończona tura sygnalizowana `wx.Bell` + autofocus na narrację.

Trzy tryby gry (continuum trudności moralnej): **Swobodny** (free-text, 1-3 sugestie opcjonalne), **Wyborów** (3-5 ponumerowanych opcji A-E per tura), **Mniejsze zło** (jak Wyborów, ale każda opcja niekorzystna — brak neutralnego wyjścia, brak happy endingu). Plus pięć **Quick Start presetów** (po-apokaliptyczne SF / mroczne fantasy / urban fantasy detective / kosmiczny horror / romantyczna komedia obyczajowa) — gracz wybiera świat z dropdown-a, silnik dostaje 1-2 paragrafowy seed. **Slash-komendy** parsowane lokalnie bez API: `/zapisz`/`/save`, `/wczytaj`/`/load`, `/ustawienia`/`/settings` (model picker), `/wizualizuj`/`/visualize` (multisensoryczny opis sceny bez zapisu), `/koniec`/`/quit`.

Inteligentne zarządzanie kontekstem: `tiktoken` mierzy zapełnienie 128k-tokenowego okna gpt-4o, próg 70% triggeruje **auto-streszczenie** w wątku tła (LLM zwija ostatnie tury w jeden kondensat, bufor zwolniony). Po **150. turze** raz per gra silnik wstawia **Cinematic Meta Warning** — przerywnik dramatyczny w osobnym dialogu, NIE appendowany do `.txt` (filter `czysc_meta_warningi` z markerami `⚠️🚨⚠️` i tak by go wyciął — gracz odsłuchujący audiobook nie usłyszy meta-komentarza o własnej grze).

**Bridge Opowieści → Reżyser**: każda tura aktualizuje `skrypty/<gra>.md` z postaciami w formacie `[Imię: cechy]` zgodnym z parserem `core_rezyser.py:199`. Możesz po skończeniu gry otworzyć Reżyser na tej samej nazwie i otrzymać klasyczny audiobook z natywnymi akcentami postaci, które polubiłeś w Opowieściach.

Bump z **14.0 → 15.0** (a nie 14.1) celowo: zamyka epokę wersji 14.x „jeden moduł, wiele paczek językowych" i otwiera 15.x+ jako „funkcje silnika/UX". Roadmapa wielojęzycznościowa zamknięta w 14.0 zostaje aktualna — moduł Opowieści jest dostępny we wszystkich 9 językach (UI + manuał auto-tłumaczone), z fallbackiem promptów systemowych do PL przy braku natywnej paczki promptów (5b/5c TODO na v15.1+).

### Co nowego dla użytkownika końcowego

#### Drugi główny tryb: Opowieści (`Ctrl+5`)
- **Triada modułowa**: `gui_opowiesci.OpowiesciPanel` (interfejs) + `core_opowiesci.ProjektOpowiesci` (lifecycle plików) + `opowiesci_ai` (silnik LLM). Spójna z istniejącym wzorcem Reżysera (`gui_rezyser` + `core_rezyser` + `rezyser_ai`).
- **Pięć ścieżek per gra**:
  - `skrypty/<nazwa>.txt` — narracja, append-only, BEZ meta-warningów (filtrowane).
  - `skrypty/<nazwa>.md` — Księga Świata, idempotentny rebuild z `postacie_aktywne[]` per tura.
  - `runtime/opowiesci/<nazwa>.game.json` — pełen stan (overwrite per tura).
  - `runtime/opowiesci/<nazwa>.story.jsonl` — surowy log tur (request+response JSON, jedna linia per tura).
  - `runtime/skrypty/<nazwa>.mode` — numeracja trybu (3=Swobodny, 4=Wyborów, 5=Mniejsze zło) — folder wspólny z Reżyserem (0=Burza, 1=Reżyser1, 2=Reżyser2 nie kolidują).
- **JSON-schema response** wymuszane DWUKROTNIE: po stronie OpenAI przez `response_format={"type": "json_object"}` (gwarantuje składnię), po naszej przez `jsonschema.validate` (gwarantuje typy + obecność wymaganych pól). Halucynacja struktury → retry max 2× z błędem jako wskazówką dla modelu (self-correction wzorzec z OpenAI cookbook); trzeci błąd → `RuntimeError` z detalami.
- **Wskaźnik pamięci modelu** (`tiktoken` na payloadzie): `🟢 czysta` (0%) → `🟢 OK` (1-69%) → `⚠️ ostrzeżenie` (70-89%, auto-streszczenie w toku) → `🚨 ALARM` (90%+, blokada wysyłki). Kolor labelu (zielony/pomarańczowy/czerwony) zsynchronizowany z poziomem.
- **Lokalizacja idiomatyczna nazw trybów** (zob. `feedback_lokalizacja_nazw.md`): „Mniejsze zło" → EN „Lesser Evil" / DE „Kleineres Übel" / FR „Moindre mal" / IT „Male minore" / ES „Menor mal" / RU „Меньшее зло" / FI „Pienempi paha" / IS „Minna illt". Żadnej kalki literalnej („Smallest Evil" itp.).

#### Quick Start: 5 presetów PL (gotowych światów)
Lingwistyczna paczka PL gotowa do gry od pierwszego klika. Każdy preset: tryb domyślny + 1-2 paragrafowy `seed_swiata` z postaciami i akcentami (kompatybilny z parserem Reżysera) + idiomatyczne motywy kulturowe.
- **Po-apokaliptyczne SF** (tryb 4): 200 lat po Wielkim Spaleniu, kurier Klanu Sztolnia w Górach Świętokrzyskich.
- **Mroczne fantasy** (tryb 5): Inkwizytorka Sióstr Cierniowych na tropie wsi chroniącej dziecko opętane.
- **Urban fantasy detective** (tryb 4): Warszawa 2008, prywatny detektyw widzący duchy, klientka szuka męża zaginionego pod Zamkiem Królewskim.
- **Kosmiczny horror** (tryb 3): rok 2247, stacja badawcza wokół neutronowej gwiazdy, brakujący kapitan o którym nikt nie pamięta.
- **Romantyczna komedia obyczajowa** (tryb 3): kawiarnia na Saskiej Kępie, barista-kelnerka między ratowaniem lokalu a redaktorem-nieśmielym.

Pozostałe 8 języków dostają domyślny preset PL fallback do v15.1, gdy native presety zostaną dopisane ręcznie per język (literatura, motywy kulturowe natywne, nie kalka).

#### YAML-izacja promptów systemowych (anty-spaghetti)
Wszystkie 7 promptów (`baza`, `tryb_swobodny`, `tryb_wyborow`, `tryb_mniejsze_zlo`, `tryb_burza`/visualize, `streszczenie`, `cinematic_warning`) wyniesione z hardkodowanych stałych Pythona do `dictionaries/pl/opowiesci/*.yaml` zgodnie ze wzorcem `dictionaries/pl/rezyser/tryb_*.yaml`. Lingwista edytuje treść bez znajomości Pythona; LRU cache (128 entries) niweluje koszt I/O. Fallback do PL przy braku tłumaczenia w docelowym języku — gracz EN dostaje polski system prompt, ale narracja nadal idzie po angielsku (LLM jest multilingual; zauważalnie niższa jakość vs natywny prompt PL, ale grywalne).

### Architektura — co dokładnie zmienia się w kodzie

#### Nowe pliki
- `gui_opowiesci.py` (~900 linii): `OpowiesciPanel(wx.Panel)` z 7 blokami A-G, daemon thread workers, dispatcher slash-komend (PL+EN fallback), cinematic + streszczenie spawn + handlery, wskaźnik pamięci `tiktoken`.
- `core_opowiesci.py` (~270 linii): `ProjektOpowiesci`, `WynikWczytaniaOpowiesci` (@dataclass), `czysc_meta_warningi(tekst)` z `re.DOTALL`, idempotentny `rebuild_ksiega_swiata()`, hardenowane `wczytaj()` (defensywne `.get(klucz, default)` dla forward-compat).
- `opowiesci_ai.py` (~600 linii): `SnapshotOpowiesci`, `WynikTury`, `StatusPamieci` (@dataclass-y), `inicjalizuj_klienta`, `generuj_ture` z retry, `wygeneruj_wizualizacje`, `policz_tokeny`/`oblicz_status_pamieci` (tiktoken z fallback `o200k_base`), `streszczaj_kontekst`, `generuj_cinematic_warning`, `_zaladuj_przepis` z LRU cache + fallback do PL.
- `dictionaries/pl/opowiesci/` (8 plików YAML): 7 promptów + `zaczatki.yaml` z 5 presetami Quick Start.
- `dictionaries/<jezyk>/gui/dokumentacja/opowiesci.yaml` (9 plików): manuał użytkownika modułu Opowieści (PL ręcznie ~210 linii, 8 obcych przez `buduj_wielojezyczne_docs.py --szablony opowiesci`).
- `notatki_dev/` (NOWY folder, gitignored z release): `instrukcje_modelu.md` + `tales_mechanics.md` jako specyfikacja źródłowa GPT-style „Tales of Consequence" — zachowane do referencji deweloperskiej, wykluczone z paczki end-userowej (`build_release.py::IGNOROWANE_FOLDERY` + `installer.iss::Excludes`).

#### Modyfikowane
- `main.py`: import `OpowiesciPanel`, `ID_TOOL_OPOWIESCI = wx.NewIdRef()`, dispatcher w `_switch_tool` (`elif name == n_opowiesci`), handler `_on_opowiesci`, menu+button+akcelerator+`Ctrl+5`+nazwa narzędzia.
- `dictionaries/<jezyk>/gui/ui.yaml`: 107 nowych kluczy w sekcji `opowiesci.*` + 5 kluczy `main.*.opowiesci` (PL ręcznie, 8 obcych przez `buduj_wielojezyczne_ui.py --klucz opowiesci` surgical update).
- `dictionaries/<jezyk>/gui/dokumentacja/manual.yaml`: linia o liście modułów rozszerzona o piąty moduł — Opowieści (per język ręcznie, idiomatyczne tłumaczenie „pięć / Ctrl+1..Ctrl+5").
- `requirements.txt`: dodane `jsonschema`, `tiktoken`.

#### Decyzje architektoniczne (locked w pamięci projektowej)
- **JSON-schema enforcement**: `response_format=json_object` po stronie OpenAI (gwarancja składni) + `jsonschema.validate` po naszej (gwarancja struktury). Reżyser NIE używał `json_object` (rezyser_ai.py free-form); świadomie wybraliśmy nowszy wzorzec dla Opowieści (jak `buduj_wielojezyczne_ui.py:373`).
- **Brak `/undo`** (chaos kontekstu LLM przy retroaktywnych mutacjach).
- **Cinematic Warning**: trigger Python (próg 150 tur), treść LLM, NIGDY w `.txt` (filtr regex `⚠️🚨⚠️.*?⚠️🚨⚠️` z `re.DOTALL`).
- **Tryb Swobodny**: w GUI ZAWSZE ukrywa obszar wyborów, nawet gdy LLM zwrócił sugestie. Tryby 4/5: pokazuje tylko gdy `len(wybory) > 0` (halucynacja → free-text fallback).
- **Slash-komendy parsowane lokalnie** (bez API call). EN-fallback ZAWSZE aktywny niezależnie od UI lang (gracz angielski w polskim UI nadal pisze `/save`).
- **Late-binding dispatcher** (`getattr(self, nazwa_handlera)`): pozwala mockowi w testach podmienić `_komenda_X = lambda...` bez rebuildowania słownika.

### Migracja z 14.x

Bezbolesna — moduł Opowieści jest **addytywny**, nie modyfikuje żadnego istniejącego flow. Reżyser/Poliglota/Konwerter/Manager Reguł działają identycznie jak w 14.0. Skrót `Ctrl+5` był wcześniej wolny.

Lista artefaktów na dysku po pierwszej grze (samo pojawienie się tych ścieżek nie blokuje innych modułów — folder `runtime/opowiesci/` jest niewidoczny dla zwykłych użytkowników Windows, jak `runtime/skrypty/`):
```
skrypty/<nazwa>.txt          # narracja, czytelne dla TTS
skrypty/<nazwa>.md           # Księga Świata, kompatybilna z Reżyserem
runtime/opowiesci/<nazwa>.game.json
runtime/opowiesci/<nazwa>.story.jsonl
runtime/skrypty/<nazwa>.mode  # tryb 3/4/5
```

### TODO na v15.1+

- **Faza 5b**: prompty systemowe `dictionaries/{en,de,es,fi,fr,is,it,ru}/opowiesci/*.yaml` RĘCZNIE per język (~5-9h pracy, brak skryptu — LLM halucynuje na strukturyzowanych instrukcjach). Native prompty znacząco poprawią jakość narracji vs obecny fallback do PL.
- **Faza 5c**: native zaczatki Quick Start per język (literatura, motywy kulturowe). PL gracz dostaje motywy z polskiej literatury, ES gracz z hiszpańskojęzycznej, itd.
- **v15.1 — mechanika Fiolki/Vial** w trybie Mniejsze zło (referencja `notatki_dev/tales_mechanics.md` od „Tales of Consequence"): gracz może raz na grę odrzucić wszystkie wybory i wziąć fiolkę = redirect fabularny.
- **v15.1 — spójność gramatyczna wyborów** (ujawnione przy real test gry `joanna_joana_conflict`): w trybach Wyborów/Mniejsze zło LLM raz daje opcje w bezokoliczniku („uciec drogą"), raz w trybie rozkazującym („uciekaj drogą"), raz w I osobie („uciekam drogą"). Doprecyzować w `dictionaries/<jezyk>/opowiesci/tryb_wyborow.yaml` + `tryb_mniejsze_zlo.yaml`, że format MUSI być jednolity per język (PL → 2-os. tryb rozkazujący „uciekaj"/„otwórz"/„zapytaj"; EN → imperative „run"/„open"/„ask"). Nie wymusi 100% spójności (LLM bywa kreatywny), ale stanowczy prompt zmniejszy oscylację.
- **v15.1 — wzmocnienie trybu Mniejsze zło** (też ujawnione w real test): pierwsze 2-3 tury LLM generuje opcje „na łatwiznę", przez co fabuła szybko gaśnie i gracz musi obejść mechanikę przez free-text. Doprecyzować prompt: „PIERWSZE 5 TUR: każda z opcji MUSI eskalować ryzyko/dramatyzm scena-do-sceny, ZAKAZ łatwych wyjść (uciec, schować się, zignorować) bez równoczesnej istotnej straty (utrata sojusznika / ujawnienie sekretu / obarczenie konsekwencjami osoby trzeciej)".

### Hotfix po v15.0 (w tym samym tagu)

Problemy znalezione w real testach gry tuż przed pushem v15.0:

- **Brakujące pole „Ostatnia tura"** (zgodne z oryginalną wizją z `notatki_dev/`): nowy `wx.TextCtrl readonly multiline` między wskaźnikiem pamięci a pełną narracją; po każdej turze wartość zastępowana świeżym fragmentem (nie append), żeby NVDA czytał od razu nową scenę bez nawigowania przez setki linii historii. Po wczytaniu gry pole pokazuje skrót ostatniej tury (z `_snapshot.ostatnie_tury[-1].narracja_skrot`, max 400 znaków) z prefixem informującym że pełna narracja jest w polu poniżej. 5 nowych kluczy i18n + zaktualizowane 3 etykiety dot. pełnej narracji („Narracja" → „Pełna narracja" dla odróżnienia), batch translated na 8 języków + manualna naprawa kalki LLM ("shortcut"/"Abkürzung"/"raccourci"/"scorciatoia"/"pikanäppäin"/"flýtileið" → "summary"/"Zusammenfassung"/"résumé"/"riassunto"/"tiivistelmä"/"samantekt" — LLM mylił semantykę polskiego „skrót" jako klawiszowy shortcut, nie summary).
- **Wykluczenie `runtime/opowiesci/` z paczki release**: do paczki end-userowej (ZIP + EXE) deweloperskie pliki gier (.game.json, .story.jsonl) NIE mogą trafić. `.gitignore` już to chronił przed repo, ale `build_release.py::IGNOROWANE_FOLDERY` i `installer.iss::Excludes` wymagały dodania konkretnej ścieżki — proste dodanie `'opowiesci'` do listy folderów byłoby błędne, bo wykluczyłoby też `dictionaries/<kod>/opowiesci/` (paczki promptów MUSZĄ być w paczce end-user). Dodano precyzyjny check: `sciezka.endswith('runtime/opowiesci') or 'runtime/opowiesci/' in sciezka` w `czy_ignorowac` + `runtime\opowiesci\*` w `installer.iss::Excludes`.

---

## 14.0 — major release (motyw przewodni: dziewiąta paczka językowa Español + zamknięcie roadmapy wielojęzycznościowej)

*Punkt wyjścia: V13.9 (31af43f) → paczka ES (`dictionaries/es/`) + dopisanie `es` do `MAPA_JEZYKOW` w obu autotłumaczach + wpis `es`/`fr` do `_NATYWNE_JEZYK_ODPOWIEDZI` + `_NATYWNE_STRESZCZENIE` + aktualizacja `_PACZKI_WDROZONE` (7 → 9) + smoke test akcentów + commit docs + commit release → V14.0.*

### TL;DR

14.0 to **ostatnia paczka językowa z roadmapy** zaplanowanej w `TODO_wielojezycznosc.md`: pełny **Español** (`dictionaries/es/` — 11 akcentów, 6 szyfrów, 4 tryby Reżysera, GUI+dokumentacja). Wraz z dodaniem ES wyczerpana zostaje sekcja 3.1/3.2 TODO i pole „liczba w pełni wdrożonych języków" przechodzi z 8 na 9 (`pl en de es fi fr is it ru`). Plik `TODO_wielojezycznosc.md` zostaje **usunięty z repozytorium** — ostatnie pozycje na liście są zamknięte. Reguła „DEFINICJA KOMPLETNOŚCI JĘZYKA (aktualna do wyczerpania TODO_wielojezycznosc.md)" w `CLAUDE.md` zostaje usunięta zgodnie z jej własnym sunset-clause; reanaliza całego `CLAUDE.md` w stylu komendy `/init` aktualizuje liczniki i odniesienia do stanu post-14.0.

Bump z **13.9 → 14.0** (a nie 13.10) celowo: zamyka epokę wersji 13.x, w której każdy minor był „jeden język na raz" (13.3 EN, 13.4 FI, 13.5 RU, 13.6 IS, 13.7 IT, 13.8 DE, 13.9 FR, 14.0 ES). Tematyka 14.x+ przechodzi na funkcje silnika/UX, nie na nowe paczki.

### Co nowego dla użytkownika końcowego

#### Nowy język bazowy: Español (`es`)
Dziewiąty pełnoprawny język bazowy. Kompletna paczka `dictionaries/es/`:

- **`podstawy.yaml`**: alfabet 27-literowy `ABCDEFGHIJKLMNÑOPQRSTUVWXYZ` (Ñ jako odrębna litera w pozycji kanonicznej między N i O — `.upper()` zachowuje pojedynczy znak, więc indeks Cezara jest spójny). `polskie_znaki` normalizuje 5 hiszpańskich vocales acentuadas (á/é/í/ó/ú) i diéresis ü do form bazowych dla akcentów obcojęzycznych z `usun_polskie_znaki: true`. `lingua: SPANISH`, `slowo_akcent: ["acento", "pronunciación"]`.

- **6 szyfrów**: Cezar (`min/max ±26`, alfabet z Ñ), jakanie (samogłoski `aeiouáéíóúüy`), odwracanie (15 wzorców skrótowców hiszpańskich: `p. ej.` → `por ejemplo`, `es dec.` → `es decir`, `etc.` → `etcétera`, `Srta./Sra./Sr.`, `Dra./Dr./Prof.`, `pág(s).` → `página`, `núm.` → `número`, `cf./cfr.`, `vs.`, `vol./cap./art.`, `a.C./d.C.`), samogłoskowiec (`aeiouáéíóúü`), typoglikemia, wąż.

- **4 tryby Reżysera AI** po hiszpańsku: Lluvia de ideas (Brainstorming), Guion (Radioteatro/Foley), Audiolibro, Postprod (regex `Prólogo|Capítulo \d+|Epílogo`). Słowa-wyzwalacze: `resume`, `resumen`, `resumir`, `sinopsis`. Endonim `Español`, lingua `SPANISH`.

- **11 plików akcenty/**: 8 akcentów fonetycznych obcojęzycznych (angielski, niemiecki, polski, rosyjski, włoski, fiński, francuski, islandzki) + 3 narzędzia czyszczenia (`oczyszczenie`, `oczyszczenie_bez_liczb`, `naprawiacz_tagow`). Akcenty oparte o cechy fonologiczne hiszpańskiego: `ch` /tʃ/ → `cz`/`tsch`/`tš`/`ts`/`ci+vocal`/`tch` (per docelowy TTS, zachowane jako `ch` przy en/ru gdzie /tʃ/ jest natywne), `ñ` /ɲ/ → `ny`/`ń`/`gn`/`nj`, `j` /x/ → `h`/`ch`/`kh`/`gh`, `ll` /ʝ/ → `y`/`j`/`gli`/`ill`, `gu/qu` z u muda → `g`/`k`/`gh`/`ch`, `z` → `s`/`ss`. Krytyczne reguły kolejnościowe (komentowane w plikach): `j → <x>` PRZED `ñ → nj` i `ll → j`, żeby nowe j-podstawienia nie zostały złapane przez tę samą regułę.

- **Pełen przekład UI** (`dictionaries/es/gui/ui.yaml`, 483 klucze, parytet 100% z paczką francuską) + dokumentacja (`dictionaries/es/gui/dokumentacja/manual.yaml` + `dictionaries.yaml` — auto-tłumaczone przez `buduj_wielojezyczne_docs.py` z zamrożeniem placeholderów).

- **Smoke test sec 6.9 z TODO**: 6/6 zdań ze sekcji 6.9 rozwijanych poprawnie (w tym 4 z błędem redakcyjnym typu „brak końcowej kropki" — bonus dzięki `\.?` w regexach).

#### Skrypty autotłumaczy + szablony Managera
- `buduj_wielojezyczne_ui.py` + `buduj_wielojezyczne_docs.py`: dodane `"es": "hiszpański"` do `MAPA_JEZYKOW` (mapowanie ISO → polskie etykiety dla promptów LLM).
- `manager_regul_szablony.py`: `_NATYWNE_JEZYK_ODPOWIEDZI` i `_NATYWNE_STRESZCZENIE` rozszerzone o `fr` (4 słowa: `résume`/`résumé`/`résumer`/`vue d'ensemble`) i `es` (4 słowa: `resume`/`resumen`/`resumir`/`sinopsis`). `_PACZKI_WDROZONE` z 7 → 9 (`pl en de es fi fr is it ru`). Lista paczek referencyjnych w prompcie agentowym Managera teraz pokazuje wszystkie 8 sąsiednich paczek przy tworzeniu nowych reguł.
- Komentarze „planowane wdrożenie 13.10/13.11" przy `fr/es` w `_NATYWNA_NAZWA_JEZYKA` usunięte — paczki wdrożone, komentarze stały się szumem.

### Zamknięcie roadmapy wielojęzyczności

- **`TODO_wielojezycznosc.md` USUNIĘTY**: zgodnie z sekcją 4.5 tego pliku („Gdy ten plik zostanie wyczerpany, [...] plik `TODO_wielojezycznosc.md` można usunąć z repozytorium"). Wszystkie 6 języków z sekcji 3.1 (EN/FI/IS/IT/RU + bazowy PL) i 3 języki z sekcji 3.2 (DE/FR/ES) zamknięte. Smoke testy 6.1–6.9 — odhaczone.
- **`CLAUDE.md` zaktualizowany**: usunięta reguła „DEFINICJA KOMPLETNOŚCI JĘZYKA (aktualna do wyczerpania TODO_wielojezycznosc.md)" — zgodnie z jej własnym sunset-clause. Pełna reanaliza w stylu `/init`: aktualizacja licznika języków (8 → 9), aktualizacja przykładów wersji w komentarzach.

### Migracja 13.9 → 14.0 (dla deweloperów)

Bez breaking changes. Punkty migracji:
1. **Plik `TODO_wielojezycznosc.md` zniknął** — historia jest w git log, pełna mapa drogowa wdrożenia 8 języków (13.3–14.0) zachowana w commitach release'owych.
2. **`CLAUDE.md` przycięty** — sekcja DEFINICJA KOMPLETNOŚCI usunięta. Aktualnym kontraktem jest `core_poliglota._jezyk_kompletny` (5 wymogów: `podstawy.yaml`, `akcenty/` ≥1 plik, `szyfry/` ≥1 plik, `rezyser/` ≥1 plik, `gui/ui.yaml`).
3. **Manager Reguł (kreator nowego języka)** — działa identycznie. Listę 9 paczek widać w komponencie agentowego promptu, ale to dynamiczne (z `_PACZKI_WDROZONE`).

---

## 13.9 — minor release (motyw przewodni: język bazowy FR + audyt kreatora/promptów Managera Reguł)

*Punkt wyjścia: V13.8.1 (17b2e7c) → audyt A11y + kontrakt rezyser/ + audyt promptów + paczka FR + commit docs + commit release → V13.9.*

### TL;DR

13.9 zamyka cztery linie pracy ujawnione podczas wdrażania paczki niemieckiej (13.8): **audyt A11y kreatora nowej reguły** (NVDA czytało niezatytułowane pole edycji), **rozszerzenie kontraktu silnika** o wymóg `rezyser/` (przesunięte z 14.0+ na teraz, bo wzorzec 4 plików per paczka stabilizował się po 7 paczkach), **audyt promptów AI** Managera Reguł (natywność komentarzy, format agentowy zamiast chatbotowego, rozdzielenie 3 podtypów akcentów), oraz **pełną paczkę językową Français** (`dictionaries/fr/`) — ósmy w pełni wdrożony język bazowy.

### Co nowego dla użytkownika końcowego

#### Nowy język bazowy: Français (`fr`)
Ósmy pełnoprawny język bazowy. Kompletna paczka `dictionaries/fr/`:

- **6 szyfrów**: Cezar (alfabet 40-literowy `ABCDEFGHIJKLMNOPQRSTUVWXYZÀÂÇÉÈÊËÎÏÔÙÛÜŸ`, ligatury `œ/æ` decomposowane do `oe/ae` w `polskie_znaki` żeby `.upper()` nie łamał indeksów Cezara), jakanie (samogłoski `aeiouàâéèêëîïôùûüÿy`), odwracanie (15 wzorców skrótowców francuskich: `p. ex.` → `par exemple`, `c.-à-d.` → `c'est-à-dire`, `etc.`, `cf.`, `M.`/`Mme`/`Mlle`, `Dr`/`Pr` (bez kropki, francuska konwencja), `n°`/`No`, `p.`/`pp.`, `av./apr. J.-C.`), samogłoskowiec, typoglikemia, wąż.

- **4 tryby Reżysera AI** po francusku: Brainstorming, Scénario (Pièce radio/Foley), Livre audio, Postprod (regex `Prologue|Chapitre \d+|Épilogue`). Słowa-wyzwalacze: `résume`, `résumé`, `résumer`, `vue d'ensemble`. Endonim `Français`, lingua `FRENCH`.

- **11 plików akcenty/**: 8 akcentów fonetycznych obcojęzycznych (angielski, niemiecki, polski, rosyjski, włoski, fiński, islandzki, hiszpański) + 3 narzędzia czyszczenia (`oczyszczenie`, `oczyszczenie_bez_liczb`, `naprawiacz_tagow`). Akcenty oparte o cechy fonologiczne francuskiego: `ch` /ʃ/ → `sh`/`sch`/`sci`/`š` (per docelowy TTS), `j` /ʒ/ → `zh`/`sch`/`ż`/`gi`/`ll`/`ž`, `ou` /u/ → `oo`/`u`/`uu`/`ú`, `u` /y/ → `ü` (de), `y` (fi), `iu` (it/es), `i` (pl approx), `gn` /ɲ/ → `ny`/`nj`/`ń`/`ñ`, `qu` /k/ → `k`/`kv`, `ç` → `s`/`ss`, nieme `h` usuwane.

- **Pełen przekład UI** (`dictionaries/fr/gui/ui.yaml`, 483 klucze, parytet 100% z paczką włoską) + dokumentacja (`dictionaries/fr/gui/dokumentacja/manual.yaml` + `dictionaries.yaml` — manual auto-tłumaczony przez `buduj_wielojezyczne_docs.py` + ręczna korekta halucynacji LLM, `dictionaries.yaml` napisany ręcznie ze wzorcem stylu z paczki włoskiej).

- **`buduj_wielojezyczne_ui.py` + `buduj_wielojezyczne_docs.py`**: dodane `fr` do `MAPA_JEZYKOW`. `buduj_wielojezyczne_docs.py` ma też wpis `fr` w `ABBREV_BY_LANG` (5 najpopularniejszych skrótowców: `p. ex.`, `c.-à-d.`, `etc.`, `M.`, `Dr`).

#### Manager Reguł — audyt A11y kreatora (commits `41d082d`, `8cc4800`)
- **WynikKreatoraDialog.naglowek** dostał `name=` (NVDA czytało jako gołe „edit"). Klucz `wynik_naglowek_name` × 7 języków.
- **KreatorNowejRegulyDialog._lbl_id** zachowany jako pole klasy i przełączany dynamicznie między „Identyfikator (nazwa pliku)" ↔ „Kod języka (ISO 639-1)" w zależności od wybranego typu reguły. Klucz `kreator_jezyk_bazowy_id_label` × 7 języków.
- **Manager przy nowym języku** tworzy 4 podfoldery (`akcenty/`, `szyfry/`, `rezyser/`, `gui/`) zamiast 3 — kontrakt silnika od 13.9 wymaga ≥1 plik `*.yaml` w `rezyser/`.

#### Manager Reguł — audyt promptów AI (commits `12f692f`, `a9c8ce3`, `17b2e7c`)
- **Helpery natywności**: `_NATYWNE_JEZYK_ODPOWIEDZI` (mapa 7 wdrożonych: PL→polsku, DE→Deutsch, IT→italiano, RU→по-русски, FI→suomeksi, IS→á íslensku, EN→English; `Français` dla zaplanowanego FR), `_NATYWNE_STRESZCZENIE` (4 słowa per język), `_NATYWNA_NAZWA_JEZYKA` (endonim, też `Français`/`Español` dla planowanych).
- **Wszystkie 6 promptów** (`prompt_jezyk_bazowy`, `prompt_akcent`, `prompt_szyfr_zamiany`, `prompt_tryb_rezysera`, `prompt_postprodukcja`, `prompt_szyfr_algorytm`) przepisane na format ROLA → KONTEKST PROJEKTU → ZADANIE → PLIKI REFERENCYJNE → WYMAGANIA → PROCEDURA (Write + Bash z `yaml.safe_load` + `odswiez_rezysera.py`). Plik schudł z ~1170 do ~660 linii (-510): wycięliśmy ~500 linii literalnych przykładów YAML, dodaliśmy struktualne sekcje. Tradeoff: prompt zakłada że AI ma dostęp do projektu (Claude Code, Cursor, Aider), nie zwykły chatbot.
- **Trzy podtypy akcentów** rozdzielone (commit `17b2e7c`): `TYP_AKCENT` (fonetyczny), `TYP_AKCENT_OCZYSZCZENIE`, `TYP_AKCENT_NAPRAWIACZ`. Manager dotąd traktował wszystkie jako fonetyczne — `naprawiacz_tagow` w paczce FR generował absurdalny prompt o transliteracji „Français → fr". Teraz: `kategoria: oczyszczenie` (heurystyka `bez_liczb` w id → `normalizuj_liczby: false`), `kategoria: naprawiacz` (iso pusty, wszystko OFF), `kategoria: akcent` (WALIDACJA SCENARIUSZA — agent przerywa jeśli `iso == jezyk_bazowy` lub iso pusty).

### Pod maską

- `core_poliglota._jezyk_kompletny` (od 13.9): wymóg piąty — ≥1 plik `*.yaml` w `rezyser/` (obok `podstawy.yaml`, `gui/ui.yaml`, `akcenty/` ≥1, `szyfry/` ≥1). Przesunięcie z 14.0+ na teraz: po 7 paczkach (PL, EN, FI, IS, IT, RU, DE) wzorzec 4 plików `rezyser/` per paczka stabilizował się, więc nowe języki są obsługiwane bez zmian w kodzie pod warunkiem `odswiez_rezysera.py`. `dostepne_jezyki_bazowe()` zwraca teraz `['de', 'en', 'fi', 'fr', 'is', 'it', 'pl', 'ru']` (8 języków).
- `core_poliglota.py` zaktualizowany przez `odswiez_rezysera.py` — docstringi wrapperów `akcent_*` zawierają teraz `dictionaries/fr/akcenty/<>.yaml` w listach źródeł (8 z 11 unikalnych nazw plików obecnych w paczce FR).
- `gui_manager_regul._zgadnij_typ_z_zaznaczenia` (od 13.9): rozpoznaje podtyp po prefiksie nazwy (`oczyszczenie*` / `naprawiacz_*`).
- Szablon oczyszczenie: heurystyka `bez_liczb` w id → `normalizuj_liczby: false`. Szablon naprawiacz: iso="", `kategoria: naprawiacz`, wszystko OFF.
- `prompt_akcent` fonetyczny: WALIDACJA SCENARIUSZA — agent przerywa jeśli `iso == jezyk_bazowy` lub iso pusty.
- `CLAUDE.md` rozszerzony o regułę 7 sekcji „ZARZĄDZANIE TERMINALEM" — `golden_key.env` jest gitignorowany ale obecny na dysku, agent **może i powinien** odpalać `buduj_wielojezyczne_*.py` / `tlumacz_ai.py` bezpośrednio (nie odsyłać użytkownika), zatrzymać się dopiero przy 401/429/braku klucza.
- Walidacja docs: `generuj_dokumentacje.py --waliduj` zielona (8 par dictionaries/manual po wszystkie kompletne języki).

### Breaking changes

- `core_poliglota._jezyk_kompletny` ma piąty warunek (`rezyser/` ≥1). Stub-paczki bez tego podfolderu (gdyby istniały, np. niedokończone fr/de/es z 13.7-) byłyby teraz wykluczane z `dostepne_jezyki_bazowe()`. Nie dotyczy żadnej istniejącej paczki — wszystkie 8 wdrożonych języków (PL, EN, FI, IS, IT, RU, DE, FR) ma `rezyser/` z ≥4 plikami.

---

## 13.8.1 — patch release (motyw przewodni: ostrzeżenie o NVDA 2026.1 / Vocalizer)

*Punkt wyjścia: V13.8 (bf6aa0c) → patch docs + commit release → V13.8.1.*

### TL;DR

NVDA 2026.1 (maj 2026) to skok architektoniczny — przejście na Pythona 3.13 i porzucenie 32-bitów. Wszystkie dotychczasowe dodatki Vocalizerowe przestały działać i nie naprawi tego nadpisanie zgodności w NVDA: muszą zostać przekompilowane biblioteki .dll głosów. Do czasu wydania zaktualizowanej paczki przez Tiflotecnia jedyne ścieżki dla użytkowników Poliglocie/Vocalizera to wstrzymanie aktualizacji, downgrade NVDA do 2025.x lub przejście na komercyjną paczkę głosów SAPI5 (z bezwzględnym wymogiem wybrania „Microsoft Speech API wersja 5 — 32 bit", a nie zwykłego „SAPI5").

### Co nowego dla użytkownika końcowego

#### Sekcja „ALARM dla użytkowników Vocalizera: NVDA 2026.1" w manualu (7 języków)

Dodana w `dictionaries/<kod>/gui/dokumentacja/manual.yaml` zaraz po istniejącym akapicie o cyklicznych „API Breaking Changes" w kontekście dodatku „One Core Autolang". Sekcja domyka teoretyczne ostrzeżenie konkretnym przypadkiem 2026.1 i instruuje:

- **Jeśli jeszcze nie aktualizowano NVDA** — wstrzymać aktualizację do oficjalnego komunikatu Tiflotecnia.
- **Jeśli już zaktualizowano i Vocalizer zniknął** — dwie ścieżki:
  1. Downgrade NVDA do 2025.x (najszybszy powrót do działających głosów).
  2. Komercyjna paczka SAPI5 (np. A T Guys, atguys.com) z **krytycznym** wymogiem wybrania w NVDA syntezatora „Microsoft Speech API wersja 5 — **32 bit**", a NIE zwykłego „Microsoft Speech API wersja 5" — w przeciwnym wypadku lista głosów pozostanie pusta.

Tłumaczenia ręczne (CLAUDE.md: nie odpalamy autotłumacza na istniejących szablonach z powodu kosztu API i halucynacji LLM): `pl`, `en`, `de`, `fi`, `is`, `it`, `ru`. Wygenerowane: `docs/manual.<iso>.txt` × 7.

### Pod maską

- `VERSION`: `13.8` → `13.8.1` (patch tag, zgodnie z regułą hotfix = X.Y.Z+1, bez nadpisywania artefaktów release'u 13.8).
- 7 plików `dictionaries/<kod>/gui/dokumentacja/manual.yaml` rozszerzone o sekcję alarmową (treść ręcznie tłumaczona, zachowane konwencje istniejących szablonów).

### Breaking changes

Brak.

---

## 13.8 — minor release (motyw przewodni: język bazowy DE + refaktor Managera Reguł)

*Punkt wyjścia: V13.7 (637281f) → commit Task1 + commit docs + WIP DE + commit docs DE + commit build + commit release → V13.8.*

### TL;DR

13.8 zamyka dwie linie pracy: **pełną paczkę językową Deutsch** (`dictionaries/de/`) oraz **refaktor kreatora nowej reguły** w Managerze Reguł (m.in. przycisk Anuluj przez i18n, ukryte pole ISO dla nowych języków bazowych). Bonus infrastrukturalny: `build_release.py` teraz automatycznie wykrywa języki bazowe i wstrzykuje je do sekcji `[Languages]` skryptu Inno Setup — bez ręcznej edycji `installer.iss` przy każdym nowym języku.

### Co nowego dla użytkownika końcowego

#### Manager Reguł — Kreator nowej reguły
- **Przycisk „Anuluj"** jest teraz tłumaczony przez i18n (wcześniej zawsze po polsku).
- **Pole „Identyfikator ISO"** jest ukryte przy tworzeniu nowego języka bazowego (było widoczne, ale ignorowane — mylące).
- **Etykieta i hint pola Etykieta** zmieniają się dynamicznie w zależności od wybranego typu reguły: dla nowego języka bazowego wyświetlają podpowiedź „Nazwa języka (ojczyście lub po angielsku)", np. „Deutsch, Finnish".
- `manager_regul_szablony.py`: reguła 0 w prompcie AI wymusza angielską nazwę enuma `lingua` (zapobiega błędowi `lingua: DEUTSCH` zamiast `lingua: GERMAN`); sekcja `uwagi` informuje teraz o folderze `gui/` i skrypcie `buduj_wielojezyczne_ui.py`.

#### Nowy język bazowy: Deutsch (`de`)
Siódmy pełnoprawny język bazowy. Kompletna paczka `dictionaries/de/`:

- **6 szyfrów**: Cezar (alfabet 29-literowy ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÜ, bez ß — `ß.upper()=="SS"` łamałoby indeksy), jakanie (samogłoski `aeiouäöüy`), odwracanie (24 wzorce skrótowców: `z.B.`, `d.h.`, `usw.`, `bzw.`, `ggf.`, `bspw.`, `u.a.`, `Dr.`, `Prof.`, `Hr.`, `Fr.` i in.), samogłoskowiec, typoglikemia, wąż.

- **4 tryby Reżysera AI** po niemiecku: Burza Mózgów, Skrypt (Hörspiel/Foley), Audiobook, Postprod. Słowa-wyzwalacze: `fasse zusammen`, `Zusammenfassung`, `zusammenfassen`, `Überblick`. Postprod rozpoznaje nagłówki `Prolog|Kapitel \d+|Epilog`.

- **11 plików akcenty/**: 8 akcentów fonetycznych obcojęzycznych + 3 narzędzia czyszczenia. Akcent angielski: `v`→`f` (DE-TTS czyta `v` jako /f/!); akcent rosyjski: pełna transliteracja cyrylicka z obsługą digrafów `sch`→`ш`, `tsch`→`ч`, `ch`→`х`.

### Pod maską

- `dictionaries/de/podstawy.yaml`: `lingua: GERMAN`, alfabet 29-literowy, tabela `polskie_znaki` z mapowaniem umlauts (`ä`→`a`, `ö`→`o`, `ü`→`u`, `ß`→`ss`) i wszystkich europejskich diakrytyków.
- `core_poliglota.py` + `core_rezyser.py`: zaktualizowane przez `odswiez_rezysera.py` — docstringi wrapperów `akcent_*` i słownik `_AKCENT_FUNCS` znają teraz DE.
- `buduj_wielojezyczne_ui.py`: `--klucz` przyjmuje listę oddzieloną przecinkami (`kreator_jezyk_bazowy_etykieta_label,kreator_blad_nazwa_jezyka`) — chirurgiczny update wielu kluczy naraz bez re-tłumaczenia całego pliku.
- `build_release.py`: `shutil.which("iscc")` + `zbierz_jezyki_bazowe()` + `INNO_LANG_MAP` → sekcja `[Languages]` generowana automatycznie z `dictionaries/*/podstawy.yaml`; `installer.iss` nie wymaga już ręcznej edycji.
- `dictionaries/de/gui/dokumentacja/`: szablony `dictionaries.yaml` i `manual.yaml` po niemiecku (ręcznie poprawione po nieudanym auto-tłumaczeniu). Wygenerowane: `docs/dictionaries.de.txt`, `docs/manual.de.txt`.

### Breaking changes

Brak.

---

## 13.7 — minor release (motyw przewodni: włoski jako pełnoprawny język bazowy)

*Punkt wyjścia: V13.6 (fed5da6) → commit WIP + commit docs + commit release → V13.7.*

### TL;DR

13.7 zamyka włoski (`it`) jako szósty pełnoprawny język bazowy. Folder `dictionaries/it/` zyskał komplet 6 szyfrów, 4 tryby Reżysera AI i 8 akcentów obcojęzycznych. Język włoski był już wcześniej zarejestrowany w silniku (stub z `podstawy.yaml`, `gui/ui.yaml` i narzędziami czyszczenia), więc ten release domknął wyłącznie brakujące warstwy treści.

### Co nowego dla użytkownika końcowego

- **Tryb Szyfrant** dla włoskiego tekstu: wszystkie 6 algorytmów dostępne. Odwracacz tekstu rozwija 14 włoskich skrótowców z wzorcami `\.?` (kropka opcjonalna — tolerancja na brakującą kropkę):
  `ad es.` → `ad esempio`, `ecc.` → `eccetera`, `dott.` → `dottore`, `prof.` → `professore`, `pagg.` → `pagine`, `pag.` → `pagina`, `sig.ra` → `signora`, `sig.` → `signore`, `art.` → `articolo`, `cap.` → `capitolo`, `n.ro` → `numero`, `n.` → `numero`, `cfr.` → `confronta`, `vol.` → `volume`.

- **Tryb Reżyser** dla włoskiego: pełne 4 reżysery AI po włosku — promty systemowe, suffiksy kontekstowe (riepilogo forzato / ottimizzazione / allarme), słowa-wyzwalacze (`riassumi`, `riassunto`, `sintetizza`, `sommario`). Postprod „Assegna Titoli ai Capitoli" rozpoznaje włoskie nagłówki (`Prologo|Capitolo \d+|Epilogo`).

- **Akcenty fonetyczne** dla włoskiego → 8 obcojęzycznych syntezatorów. Silnik dostał pełny zestaw reguł dla włoskiego tekstu czytanego przez każdy TTS:

  | Akcent | TTS | Kluczowe markery |
  |---|---|---|
  | Polski | Ewa / Adam / Maja | `ch`→`k` (pl-TTS czyta `ch`=/x/), `gh`→`g` |
  | Angielski | David / Zira / Samantha | `ch`→`k` (en-TTS czyta `ch`=/tʃ/), `gh`→`g` |
  | Fiński | Heidi / Onni / Satu | `ch`→`k`, `gh`→`g`; z=/ts/ kompatybilne ✓ |
  | Islandzki | Dóra / Gunnar / Ísrún | `ch`→`k`, `gh`→`g` |
  | Francuski | Thomas / Julie / Marie | `ch`→`k` (fr-TTS czyta `ch`=/ʃ/!), `gh`→`g`; `gn`=/ɲ/ idealne ✓ |
  | Hiszpański | Pablo / María / Carmen | `ch`→`k` (es-TTS czyta `ch`=/tʃ/), `gh`→`g` |
  | Niemecki | Stefan / Petra / Hans | **`v`→`w` (KRYTYCZNE: de-TTS czyta `v`=/f/!)**, `ch`→`k`, `gh`→`g` |
  | Rosyjski | Milena / Irina / Yuri | pełna transliteracja cyrylicka z obsługą digrafów: `gli`→`льи`, `gne/gni/gna/gno/gnu`→`нь+`, `sce/sci`→`ше/ши`, `sche/schi`→`ске/ски`, `ce/ci`→`че/чи`, `ge/gi`→`дже/джи` |

### Pod maską

- `dictionaries/it/szyfry/` — 6 plików: cezar (`min/max: ±20`, alfabet 21-literowy IT), jakanie (samogłoski `aeiou`), odwracanie (14 regexów z notebooka `\.?` — łapie formy z brakującą kropką), samogloskowiec (brak polskich miękczeń — puste listy `zmiekszenia_*`), typoglikemia, waz.
- `dictionaries/it/akcenty/` — 8 nowych plików. Wspólna korekta krytyczna dla 7 akcentów łacińskich: `che`→`ke`, `chi`→`ki`, `ghe`→`ge`, `ghi`→`gi` (włoskie `ch`/`gh` = /k//g/ przed e/i; większość obcych TTS czyta je inaczej). Akcent rosyjski: pełna transliteracja z hierarchicznym procesowaniem digrafów (trigramy → digramy → litery); `usun_polskie_znaki: true` + normaliz. akcentowanych samogłosek it (à/è/é/ì/ò/ù) przed konwersją cyrylicką.
- `dictionaries/it/rezyser/` — 4 pliki: tryb_burza, tryb_skrypt, tryb_audiobook, postprod_tytuly. Wszystkie z `jezyk_odpowiedzi: italiano`. Tag strukturalny `<STRESZCZENIE>` zachowany niezmieniony (silnik go szuka globalnie niezależnie od języka).
- `core_poliglota.py` — docstringi 8 wrapperów `akcent_*` zaktualizowane przez `odswiez_rezysera.py` (dodano `dictionaries/it/akcenty/` jako źródło).

### Breaking changes / migracja

Brak. Włoski to domknięcie istniejącego stuba — żadne istniejące funkcje nie są dotknięte.

---

## 13.6 — minor release (motyw przewodni: islandzki jako pełnoprawny język bazowy)

*Punkt wyjścia: V13.5.1 (26a8169) → commity WIP + commit release → V13.6.*

### TL;DR

13.6 zamyka islandzki (`is`) jako piąty pełnoprawny język bazowy. Folder `dictionaries/is/` zyskał komplet 6 szyfrów, 4 tryby Reżysera AI i 8 akcentów obcojęzycznych.

Islandzki ma kilka cech odróżniających go od pozostałych języków:
- **32-znakowy alfabet** bez C, Q, W, Z, za to z natywnymi Á, É, Í, Ó, Ú, Ý, Þ, Æ, Ö, Ð — Cezar szyfruje wszystkie 32 litery bezpośrednio.
- **14 samogłosek** (a á e é i í o ó u ú y ý æ ö) — Samogłoskowiec jest wyjątkowo dramatyczny.
- **Þ (thorn) i Ð (eth)** — historyczne litery angielskie żyjące tylko w islandzkim; akcent angielski przekształca je do `th` (Þ→Th, Ð→th), co daje fonologicznie doskonałą zgodność `/θ/` i `/ð/` w angielskim TTS.
- **Æ = /ai/** — aksent fiński przekształca je do `ai` (fińskie AI = /ai/ ✓), natomiast w akcencie rosyjskim → `ай`.

### Co nowego dla użytkownika końcowego

- **Tryb Szyfrant** dla islandzkiego tekstu: wszystkie 6 algorytmów dostępne. Odwracacz rozwija 10 islandzkich skrótowców (`t.d.` → `til dæmis`, `þ.e.` → `það er`, `m.a.` → `meðal annars`, `u.þ.b.` → `um það bil`, `o.s.frv.` → `og svo framvegis`, `dr.` → `doktor`, `prof.` → `prófessor`, `bls.` → `blaðsíða`, `skv.` → `samkvæmt`, `fh.` → `fyrir hönd`).
- **Tryb Reżyser** dla islandzkiego: pełne 4 reżysery AI po islandzku — promty systemowe, suffiksy kontekstowe, słowa-wyzwalacze (`samantekt`, `dragðu saman`, `gerðu samantekt`). Postprod rozpoznaje islandzkie nagłówki (Kafli N / Formáli / Eftirorð).
- **Akcenty fonetyczne** dla islandzkiego → 8 obcojęzycznych syntezatorów: islandzki tekst przez angielski/fiński/polski/rosyjski/francuski/hiszpański/włoski/niemiecki TTS z odpowiednim akcentem. Specjalne cechy:
  - Angielski: Þ→th, Ð→th, j→y
  - Fiński: Þ→t, Æ→ai (idealne `ai=/ai/`), Ö bez zmian (fiński TTS czyta go jako `/ø/`)
  - Rosyjski: pełna transliteracja + Æ→ай, Þ→с, Ð→д, Ö→ё
  - Niemiecki: v→w (KRYTYCZNE: de-TTS czyta v jako /f/!), Æ→ei (de-TTS `ei=/ai/`✓), Ö bez zmian
  - Hiszpański: j→y, h→j (po j→y, żeby `/h/` nie zniknął w ciszy), Þ→z (Kastylijski z=/θ/✓)
  - Francuski: Ö→eu (idealne `eu=/ø/`✓), Þ→t, j→y

### Pod maską

- `dictionaries/is/szyfry/` — 6 plików: cezar (`min/max: ±32`), jakanie (samogloski 14 islandzkich), odwracanie (10 regexów z notebooka), samogloskowiec (14 samogłosek), typoglikemia, waz.
- `dictionaries/is/akcenty/` — 8 nowych plików + 3 już-istniejące (oczyszczenie, oczyszczenie_bez_liczb, naprawiacz_tagow).
- `dictionaries/is/rezyser/` — 4 pliki: tryb_burza, tryb_skrypt, tryb_audiobook, postprod_tytuly. Wszystkie z `jezyk_odpowiedzi: á íslensku`.
- `core_poliglota.py` — docstringi 8 wrapperów `akcent_*` zaktualizowane przez `odswiez_rezysera.py` (dodano `dictionaries/is/akcenty/` jako źródło).

### Breaking changes / migracja

Brak. Islandzki to nowy język — żadne istniejące funkcje nie są dotknięte.

---

## 13.5.1 — patch release (motyw przewodni: hiat `и + jotowana` w 3 akcentach)

*Patch: koniec podwojenia [i] w końcówkach `-ие/-ия/-иё/-ию` dla 3 akcentów (polski/francuski/włoski).*

---

## 13.5.1 — patch release (motyw przewodni: hiat `и + jotowana` w 3 akcentach)

*Punkt wyjścia: V13.5 (6527e23) → commit hotfix → V13.5.1.*

### TL;DR

13.5.1 naprawia bug zgłoszony zaraz po wydaniu 13.5: w polskim akcencie końcówka `-ие` (np. `присутствие`) zamieniała się na `prisutstwiie` (podwojone `i`), co polski TTS Ewa wymawiała jako sztucznie przeciągnięte [i:e] zamiast naturalnego [i-je]. Problem dotyczył 3 z 8 akcentów dla rosyjskiego — tych, w których yotowana samogłoska zaczyna się od `i` (а nie `j`/`y`):

* **polski** (`Я→Ia`, `Е→Ie`, `Ё→Io`, `Ю→Iu`) → naprawa: dodaj eksplicytny `j` jako rozdzielnik. `Россия → Rossija` (zamiast `Rossiia`), `присутствие → prisutstwije` (zamiast `prisutstwiie`). Polski Ewa wymawia `j` jako natywne /j/, więc fonetyka jest wierna rosyjskiemu [i-je].
* **francuski** (`Я→Ia`, `Е→Ie`, `Ё→Io`, `Ю→Iou`) → naprawa: skrócenie. `Россия → Rossia`, `присутствие → prisoutstvie`. Francuski `j` to /ʒ/ (jak w „journal"), więc nie nadaje się jako rozdzielnik; skrócenie pozwala francuskiej naturalnej palatalizacji wykonać robotę.
* **włoski** (`Я→Ia`, `Е→Ie`, `Ё→Io`, `Ю→Iu`) → naprawa: skrócenie, jak we francuskim. `Россия → Rossia`, `присутствие → prisutstvie`. Włoski `j` jest niejednoznaczny (Lucia czyta go jako /j/ albo /dʒ/ zależnie od słowa), więc bezpieczniej zostać przy skróceniu.

5 pozostałych akcentów (`angielski`, `niemiecki`, `hiszpanski`, `islandzki`, `finski`) **nie wymagało zmian** — w nich yotowana zaczyna się od `j` (de/is/fi) lub `y` (en/es), więc `ия → ija` / `ия → iya` brzmi naturalnie i jest zgodne ze standardami transliteracji (BGN/PCGN dla angielskiego).

### Pod maską

W każdym z 3 zmienionych plików (`polski.yaml`, `francuski.yaml`, `wloski.yaml`) dodano sekcję 1.5 „Кириллическое и + йотированная гласная" z 12 wpisami (`ИЯ/Ия/ия` × 4 yotowane samogłoski), umieszczoną PRZED sekcją 2 (yotowane jednoznaczne) i sekcją 4 (jednoliterowe). Multi-char zamiana łapie kombinację cyrylica `и + я/е/ё/ю` zanim zwykłe `и → i` i `я → Ia` (etc.) zdążą stworzyć podwojone `i`. Smoke test (`присутствие`, `Россия`, `здание`, `академия`, `стихиё`, `Россию`) zwalidowany dla wszystkich 8 akcentów: 48/48 poprawnych transliteracji, zero podwojeń `ii`.

### Breaking changes / migracja

Brak. Zmiana czysto addytywna — istniejące transliteracje słów BEZ kombinacji `и+jotowana` nie są dotykane.

---

## 13.5 — minor release (motyw przewodni: rosyjski jako pełnoprawny język bazowy)

*Punkt wyjścia: V13.4.3 (58216bd) → commity WIP + commit release → V13.5.*

### TL;DR

13.5 zamyka rosyjski jako pełnoprawny język bazowy (TODO_wielojezycznosc.md §3.1). Folder `dictionaries/ru/` zyskał komplet 6 szyfrów (Cezar, jąkanie, odwracacz, samogłoskowiec, typoglikemia, wąż), 4 tryby Reżysera AI (audiobook, burza, skrypt, postprod tytuły) oraz 8 akcentów obcojęzycznych transliterujących cyrylicę → odpowiednią łacinkę dla docelowego TTS (angielski, polski, niemiecki, francuski, hiszpański, włoski, islandzki, fiński). Każdy akcent ma swoje specyficzne tweaki — np. francuski Х→Kh + У→Ou (bo francuska u = /y/), hiszpański Х→J (hiszpańska j = /x/, idealny match dla rosyjskiego /x/), niemiecki Ш→Sch (niemiecka sch = /ʃ/).

Po drodze domknięto dwa fundamenty silnika, ujawnione przy wdrażaniu rosyjskiego:

1. **Cezar dla dwuskryptowych tekstów (TODO §7.5).** Alfabet Cezara dla `ru` to teraz 59 znaków: 33 cyrylicy + 26 łacinki (wielkie). Dzięki temu nazwy własne (Apple, Müller, iPhone), które nie powinny być transliterowane na cyrylicę, są SZYFROWANE razem z resztą tekstu — Cezar nie pomija ich już bezgłośnie. Round-trip działa: każda litera z obu skryptów wraca do siebie po `+N/-N`.
2. **Universal Unicode-aware regex słowa.** `core_poliglota._REGEX_SLOWA` zmieniony z `\b[a-zA-ZąćęłńóśźżĄĆĘŁŃÓŚŹŻ]+\b` na `[^\W\d_]+` (litery dowolnego skryptu Unicode bez cyfr i `_`). Bez tej łatki `_algo_typoglikemia` i `_algo_jakanie` po prostu nie widziały rosyjskich słów — patrz analogiczna łatka w `core_rezyser.py` z 13.3.

### Co nowego dla użytkownika końcowego

- **Tryb Szyfrant** dla rosyjskiego tekstu: wszystkie 6 algorytmów dostępne. Cezar bezpiecznie szyfruje również wstawki łacińskie (nazwiska, marki) bez utraty znaków. Odwracacz tekstu rozwija typowe rosyjskie skrótowce (`т.е.` → „то есть", `т.д.` → „так далее", `проф.` → „профессор", `ул.` → „улица", `и т.п.` → „и тому подобное" itd. — pełna lista z notebooka autora projektu).
- **Tryb Reżyser** dla rosyjskiego: pełne 4 reżysery AI po rosyjsku — promty systemowe, suffiksy kontekstowe, słowa-wyzwalacze („обобщи", „резюме"). Postprod „Daj Nazwy Rozdziałom" rozpoznaje rosyjskie nagłówki (Глава N / Введение / Эпилог).
- **Akcenty fonetyczne** w rosyjskim → 8 obcojęzycznych syntezatorów: rosyjski tekst odczytywany przez angielskiego/polskiego/niemieckiego/francuskiego/hiszpańskiego/włoskiego/islandzkiego/fińskiego TTS brzmi z naturalnym rosyjskim akcentem (KH dla Х, ZH dla Ж, SHCH dla Щ, itd. dostosowane per docelowy TTS).
- Zamiana w `dictionaries/ru/akcenty/polski.yaml` od autora-noszonego polskiego (студент русской филологии): Щ → Ść, Ч → Ć, plus reguły końcówek bezokolicznika `ть → ć` i zwrotności `сь → ś` — dzięki czemu polski TTS nie bełkocze „wstawat" tylko brzmi po polsku-z-rosyjska.

### Pod maską

- `dictionaries/ru/podstawy.yaml` — rozszerzony alfabet Cezara (59 znaków, dwuskryptowy) + pełna lista normalizacji łacińskich diakrytyków → ASCII (jak `fi/`). Cyrylica natywna nietknięta, więc akcenty obcojęzyczne otrzymują czysty wzór do transliteracji.
- `dictionaries/ru/szyfry/` — 6 plików: cezar (`min/max_przesuniecie: ±59`), jakanie (samogłoski rosyjskie `аеёиоуыэюя`), odwracanie (regexy z notebooka § ABBREV_BY_LANG dla rosyjskiego), samogłoskowiec (wszystkie samogłoski → `о`), typoglikemia (Unicode-aware), waz (szypiące с/з/ш/ж).
- `dictionaries/ru/rezyser/` — 4 pliki: tryb_burza, tryb_skrypt, tryb_audiobook, postprod_tytuly. Wszystkie z `jezyk_odpowiedzi: по-русски`.
- `dictionaries/ru/akcenty/` — 8 nowych plików (angielski, polski, niemiecki, francuski, hiszpanski, wloski, islandzki, finski) + 3 już-istniejące (oczyszczenie, oczyszczenie_bez_liczb, naprawiacz_tagow). Każdy obcojęzyczny akcent ma sortowanie: triglify/digrafy najpierw (Щ → Shch, Sch, Chtch, …), potem yotowane głoski (Ё/Ю/Я/Е), Й, pojedyncze litery, na końcu Ъ/Ь usuwane.
- `core_poliglota._REGEX_SLOWA` → `r"[^\W\d_]+"` (Unicode klasa). Komentarz przy stałej zaktualizowany — lłatka-towarzysz tej z `core_rezyser.py:146` w 13.3.

### Breaking changes / migracja

Brak. Zmiana w pełni addytywna — istniejące języki (pl, en, fi) nadal działają identycznie. Cezar dla `pl/en/fi/it/is` korzysta z dotychczasowych alfabetów; tylko `ru` dostała rozszerzony, dwuskryptowy alfabet.

---

## 13.4.3 — patch release (motyw przewodni: dynamiczna wielojęzyczność wyniku)

*Punkt wyjścia: V13.4.2 (973080b) → commity WIP + commit release → V13.4.3.*

### TL;DR

13.4.3 wymienia bibliotekę detekcji języka z `langdetect` na `lingua-language-detector` i przebudowuje silnik Poligloty, by wykrywał język **per akapit** zamiast raz dla całego tekstu. Każdy fragment (akapit, paragraf HTML, paragraf DOCX) dostaje teraz osobno dobrane reguły fonetyczne / szyfrowe i własny atrybut `lang`. Gdy w tekście pojawi się fragment w języku, dla którego brakuje reguły (np. rosyjski akapit w trybie Szyfrant — `dictionaries/ru/szyfry/` jeszcze nie istnieje), aplikacja zatrzymuje przetwarzanie i pokazuje czytelny komunikat z dokładną ścieżką brakującego pliku — w `wx.Dialog` z polem `TE_READONLY` (A11y: NVDA odczytuje, użytkownik kopiuje Ctrl+C).

Domknięto też lukę architektoniczną: dodanie nowego języka bazowego (TODO planuje niemiecki, hiszpański, francuski) nie wymaga już zmian w kodzie Pythona. Wystarczy nowy folder `dictionaries/<kod>/` z polem `lingua: <NAZWA>` w `podstawy.yaml` — silnik sam zarejestruje język w detektorze. Manager Reguł dostał zaktualizowany szablon i prompt AI, które wprost wymagają tego pola i podają listę poprawnych nazw enum-a `lingua.Language`.

### Co nowego dla użytkownika końcowego

- Mieszany tekst (np. polski wstęp + angielski cytat) jest wreszcie poprawnie obsługiwany: każdy akapit dostaje swój znacznik `lang` w pliku wyjściowym, więc czytniki ekranu i syntezatory TTS (Microsoft, eSpeak, Vocalizer) automatycznie przełączają język wymowy w odpowiednim miejscu.
- W trybie Reżysera akcent islandzki, niemiecki itd. działa poprawnie również na fragmentach niepolskich — silnik dla każdego akapitu sięga po regułę z `dictionaries/<wykryty_język>/akcenty/<akcent>.yaml`, jeśli istnieje.
- W trybie Szyfranta to samo: szyfr Cezara z polskim alfabetem nie szyfruje już rosyjskiej cyrylicy „przez przypadek" — silnik wykrywa, że to inny język i zatrzymuje się z czytelnym komunikatem zamiast produkować śmieci.
- W plikach HTML wynikowych każdy `<p>`, `<h1>`-`<h6>`, `<li>`, `<blockquote>`, `<td>` ma własny atrybut `lang` ustawiony zgodnie z jego treścią (parser `BeautifulSoup` + `lxml`).
- W plikach DOCX każdy paragraf dostaje `<w:lang w:val="...">` zgodny z jego treścią — Word i Adobe Acrobat respektują to przy eksporcie do PDF/audio.
- Wsparcie dla pełnoprawnych dokumentów HTML (`<!DOCTYPE html>...<body>...`): parser `BeautifulSoup` ustawia atrybut `lang` osobno na `<h1>`-`<h6>`, `<p>`, `<li>`, `<blockquote>`, `<td>`, `<th>` i innych elementach blokowych — zachowując całą strukturę DOM.

### Pod maską

- `core_poliglota.py`: `langdetect` → `lingua-language-detector` z lazy singleton-builderem (`_zbuduj_detektor_lingua`). Detektor obsługuje wszystkie 6 języków obecnych w `dictionaries/`.
- Nowy helper `_segmentuj_z_ochrona_tagow(tekst, fallback_jezyk)` dwuwarstwowo dzieli wejście: najpierw po tagach HTML (zachowuje je 1:1), potem po `\n\s*\n` (akapity). Sticky-fallback: krótkie akapity dziedziczą język po sąsiadach.
- Nowy wyjątek `BrakRegulyDlaJezykaError` (atrybuty: `jezyk_kod`, `jezyk_natywna`, `tryb`, `wariant`, `oczekiwany_folder`). `gui_poliglota.py` rozpoznaje go osobno i kieruje do `_wyswietl_blad_ai` (długi multi-line komunikat → `wx.Dialog` z `TextCtrl TE_READONLY`).
- `_przetworz_rezyser` i `_przetworz_szyfrant` przepisane na pętlę per-fragment: dla każdego segmentu pobierają konfigurację wariantu w wykrytym języku i podnoszą wyjątek przy braku reguły. Side-channel `opcje["_segmenty_wynikowe"]` propaguje mapę (iso, fragment, czy_tekst) do `zapisz_wynik`.
- `zapisz_wynik` z nowym keyword-only parametrem `segmenty_wynikowe`. DOCX: tag `w:lang` per paragraf (mapowanie offset→iso, sticky-fallback dla pustych linii). HTML pełnoprawny: BeautifulSoup parsuje DOM, ustawia `lang` na wszystkich elementach blokowych. HTML fragmentaryczny i TXT/MD: nowy helper `_zbuduj_html_z_akapitow` owija akapity w `<p lang="...">`. Naprawiacz tagów: detekcja per paragraf na żywo.
- Klucze i18n `poliglota.brak_reguly_tytul` / `poliglota.brak_reguly_naglowek` dodane we wszystkich 6 plikach `dictionaries/<kod>/gui/ui.yaml` (PL/EN/FI/IS/IT/RU).
- Szablony dokumentacji `dictionaries/<kod>/gui/dokumentacja/dictionaries.yaml` zaktualizowane we wszystkich 6 językach (wzmianka o lingua per akapit zamiast langdetect globalnie).
- `requirements.txt`: usunięto `langdetect`, dodano `lingua-language-detector` i `beautifulsoup4`. Środowisko `runtime/Lib/site-packages` zsynchronizowane z `.venv` (oba bez langdetect, oba z bs4 i lingua).
- **Dynamic lingua mapping (luka architektoniczna domknięta).** `core_poliglota._ISO_TO_LINGUA` zniknął z kodu Pythona. Każdy `dictionaries/<kod>/podstawy.yaml` deklaruje teraz pole `lingua: <NAZWA_ENUMA>` (np. `POLISH`, `ENGLISH`, `GERMAN`). Funkcja `_zbuduj_mapowanie_lingua()` skanuje YAML-e przy pierwszym wywołaniu detektora, mapuje nazwy na `lingua.Language` przez `getattr` (defensywnie pomijając wartości spoza znanego enum-a). Dodanie nowego języka bazowego sprowadza się do utworzenia folderu — bez touchu Pythona. Spójne z istniejącym duchem `odswiez_rezysera.odkryj_obslugiwane_jezyki()` i `dostepne_jezyki_bazowe()`.
- `manager_regul_szablony.szablon_podstawy()` generuje teraz szablon z polem `lingua: <UZUPEŁNIJ_NAZWE_ENUMA_NP_GERMAN>` i komentarzem wyjaśniającym wymóg + URL do listy enum-ów.
- `manager_regul_szablony.prompt_jezyk_bazowy()` (prompt dla AI tworzącego nowy język) ma nową ZASADĘ ŻELAZNĄ #1: pole `lingua` z listą 12 najpopularniejszych poprawnych wartości i instrukcją „jeśli język nie jest na liście lingua, zwróć `# BRAK_W_LINGUA: <kod>` zamiast zgadywać".

---

## 13.4.2 — hotfix (motyw przewodni: i18n nagłówków struktury)

*Punkt wyjścia: V13.4.1 → commit hotfix → V13.4.2.*

### TL;DR

13.4.2 naprawia krytyczny bug internalizacji: panel struktury w Reżyserze AI wstawiał nagłówki rozdziałów, aktów i scen zawsze po polsku, niezależnie od wybranego języka interfejsu. Konwerter DOCX rozpoznawał nagłówki tylko po polsku, przez co angielski „Chapter 1" lub fiński „Näytös 2" nie był promowany na Heading 1. Naprawiono też pogrubianie nagłówków scen dla wszystkich języków.

### Co nowego dla użytkownika końcowego

- Przycisk „Wstaw Rozdział" wstawia teraz „Chapter N" w EN, „Luku N" w FI, „Kafli N" w IS, „Capitolo N" w IT, „Глава N" w RU.
- Analogicznie Akt/Scena/Prolog/Epilog — każdy w natywnym słowie dla wybranego języka.
- Konwerter `.txt → .docx` rozpoznaje nagłówki we wszystkich 6 językach i poprawnie formatuje je jako Heading 1 (rozdziały) lub Bold (sceny).

### Pod maską

- Dodano klucze `rezyser.naglowek_{prolog|epilog|rozdzial|akt|scena}` do wszystkich 6 plików `dictionaries/<kod>/gui/ui.yaml`.
- `core_rezyser.py`: metody `wstaw_*` przyjmują opcjonalne keyword-only parametry `naglowek`/`naglowek_bazowy`/`naglowek_akt`/`naglowek_scena` z polskimi wartościami domyślnymi (backward-compatible).
- `core_rezyser.py`: stałe modułowe `_WZORZEC_{ROZDZIAL|AKT|SCENA|NAGLOWEK_LINIA}` zastąpiły hardkodowane polskie regexy w licznikach (`_odczytaj_liczniki_z_pliku`) i detekcji ostatniej linii (`ostatnia_linia_to_naglowek`).
- `gui_konwerter.py`: regexy detekcji nagłówków/scen rozszerzone o wszystkie 6 języków.
- `gui_rezyser.py`: handlery `_on_wstaw_*` przekazują wartości z `t("rezyser.naglowek_*")` do `core_rezyser`.

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
