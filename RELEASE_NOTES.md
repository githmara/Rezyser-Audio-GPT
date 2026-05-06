# Release Notes — Reżyser Audio GPT 13.8 „Wersja Wydawnicza"

*Minor: Deutsch dołącza jako siódmy pełnoprawny język bazowy; refaktor Kreatora nowej reguły w Managerze.*

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
