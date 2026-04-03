import streamlit as st
import streamlit.components.v1 as components
from openai import OpenAI
import openai 
import os
import re
from dotenv import load_dotenv

# BOMBA ATOMOWA NA INTERFEJS
st.set_page_config(page_title="Reżyser Audio", layout="wide")

st.markdown("""
    <style>
        header {visibility: hidden !important;}
        footer {visibility: hidden !important;}
        #MainMenu {visibility: hidden !important;}
    </style>
""", unsafe_allow_html=True)

components.html("""
    <script>
        window.parent.document.documentElement.lang = 'pl';
    </script>
""", width=0, height=0)

# ==========================================
# INICJALIZACJA KLIENTA OPENAI (z obsługą błędów)
# ==========================================
load_dotenv("golden_key.env")
_api_key = os.getenv("OPENAI_API_KEY")

if not _api_key:
    st.error(
        "🔑 **Brak klucza API!** Nie znaleziono pliku `golden_key.env` lub zmiennej `OPENAI_API_KEY`. "
        "Utwórz plik `golden_key.env` w katalogu głównym aplikacji i wpisz do niego: `OPENAI_API_KEY=sk-...`"
    )
    client = None
else:
    try:
        client = OpenAI(api_key=_api_key)
    except Exception as _e:
        st.error(f"🔑 **Błąd inicjalizacji klienta OpenAI:** {_e}")
        client = None

# ==========================================
# PASEK BOCZNY - TRWAŁA KSIĘGA ŚWIATA
# ==========================================

# Inicjalizacja stanu Księgi Świata przez klucz widgetu.
# Wzorzec "pending": wartość nowego lore odkładamy pod world_lore_pending,
# a tutaj — PRZED renderem widgetu — przenosimy ją do klucza widgetu.
# Streamlit nie pozwala modyfikować klucza widgetu PO jego renderze.
if "world_lore_widget" not in st.session_state:
    st.session_state.world_lore_widget = ""
if "world_lore_pending" in st.session_state:
    st.session_state.world_lore_widget = st.session_state.pop("world_lore_pending")

# Odczytujemy nazwę aktywnego projektu z poprzedniego runu (przed blokiem głównym)
_sidebar_nazwa_pliku = st.session_state.get("zapisana_nazwa_pliku", "")
_zapis_lore_disabled = not _sidebar_nazwa_pliku.strip()

st.sidebar.title("📖 Księga Świata")
if _zapis_lore_disabled:
    st.sidebar.warning("⚠️ Aby korzystać z Księgi, najpierw podaj nazwę pliku projektu w **Kroku 1** na głównym ekranie.")
else:
    st.sidebar.info(f"Edytujesz Księgę projektu: **{_sidebar_nazwa_pliku}**. Kliknij przycisk poniżej, by zapisać zmiany na stałe.")

st.sidebar.text_area("Zasady i Postacie:", key="world_lore_widget", height=450)
world_context = st.session_state.world_lore_widget

if st.sidebar.button(
    "💾 Zapisz Księgę na stałe",
    disabled=_zapis_lore_disabled,
    help="Podaj najpierw nazwę pliku projektu w Kroku 1." if _zapis_lore_disabled else ""
):
    if not os.path.exists("skrypty"):
        os.makedirs("skrypty")
    _lore_path_save = f"skrypty/{_sidebar_nazwa_pliku}.md"
    with open(_lore_path_save, "w", encoding="utf-8") as f:
        f.write(st.session_state.world_lore_widget)
    st.sidebar.success(f"Zapisano! Plik `skrypty/{_sidebar_nazwa_pliku}.md` przetrwa każdy restart skryptu.")

# INICJALIZACJA SESSION STATE
if "full_story" not in st.session_state:
    st.session_state.full_story = ""
if "user_input" not in st.session_state:
    st.session_state.user_input = ""
if "ready_to_send" not in st.session_state:
    st.session_state.ready_to_send = False
if "current_prompt" not in st.session_state:
    st.session_state.current_prompt = ""
if "chapter_counter" not in st.session_state:
    st.session_state.chapter_counter = 1
if "akt_counter" not in st.session_state:
    st.session_state.akt_counter = 1
if "scena_counter" not in st.session_state:
    st.session_state.scena_counter = 1
if "last_response" not in st.session_state:
    st.session_state.last_response = ""
if "summary_text" not in st.session_state:
    st.session_state.summary_text = ""
if "flash_msg" not in st.session_state:
    st.session_state.flash_msg = ""
if "flash_type" not in st.session_state:
    st.session_state.flash_type = ""

def wyswietl_blad_ai(e):
    st.error("🚨 Wystąpił nieoczekiwany błąd podczas przetwarzania. Szczegóły techniczne (do zgłoszenia) znajdziesz poniżej.")
    st.text_area("Treść błędu:", value=str(e), height=150)

import importlib.util

def zastosuj_akcenty_uniwersalne(tekst, lore_text):
    # 1. Wyciąganie mapowania postaci z Księgi Świata (Odporne na myślniki i dwukropki w Księdze)
    akcenty_map = {}
    postacie_bloki = re.split(r'\[([^:\]\-]+).*?\]', lore_text)

    for i in range(1, len(postacie_bloki), 2):
        imie = postacie_bloki[i].strip().lower()
        opis = postacie_bloki[i+1].lower() if i+1 < len(postacie_bloki) else ""

        # Szukanie nazwy akcentu
        akcent_match = re.search(r'akcent\s+([a-zńśźżćłó]+)|([a-zńśźżćłó]+)\s+akcent', opis)
        nazwa_akcentu = (akcent_match.group(1) or akcent_match.group(2)) if akcent_match else None

        # Szukanie twardych reguł wprost
        reguly_lore = re.findall(r'["\']([a-ząćęłńóśźż])["\']\s+na\s+["\']([a-ząćęłńóśźż])["\']', opis, re.IGNORECASE)

        if nazwa_akcentu or reguly_lore:
            akcenty_map[imie] = {"nazwa": nazwa_akcentu, "reguly": reguly_lore}

    if not akcenty_map:
        return tekst

    # 2. Ładowanie Poligloty w tle (Odporne na ścieżki względne/bezwzględne)
    poliglota = None
    try:
        current_dir = os.path.dirname(__file__)
        sciezka = os.path.join(current_dir, "2_Poliglota.py")
        if not os.path.exists(sciezka):
            sciezka = os.path.join(current_dir, "..", "pages", "2_Poliglota.py")  # Fallback dla root/pages

        if os.path.exists(sciezka):
            spec = importlib.util.spec_from_file_location("Poliglota", sciezka)
            poliglota = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(poliglota)
    except Exception as e:
        st.error(f"Błąd ładowania Poligloty: {e}")

    def usun_pl_znaki_z_nazwy(nazwa):
        mapping = {'ą': 'a', 'ę': 'e', 'ł': 'l', 'ó': 'o', 'ś': 's', 'ć': 'c', 'ń': 'n', 'ż': 'z', 'ź': 'z'}
        for k, v in mapping.items():
            nazwa = nazwa.replace(k, v)
        return nazwa.strip()

    # 3. Dynamiczna modyfikacja Skryptu (Zoptymalizowana: podział po tagach)
    # Rozdziela tekst tak, by tagi [...] i tekst pomiędzy nimi były osobnymi elementami listy
    fragmenty = re.split(r'(\[[^\]]+\])', tekst)
    nowe_fragmenty = []
    zastosowane_info = set()
    current_speaker = None

    for frag in fragmenty:
        if frag.startswith('[') and frag.endswith(']'):
            # To jest tag, zapisujemy go bez zmian i ustalamy aktualnego mówcę
            nowe_fragmenty.append(frag)
            match = re.match(r'^\[([^:\]\-]+)', frag)
            if match:
                current_speaker = match.group(1).strip().lower()
            else:
                current_speaker = None
        else:
            # To jest tekst wypowiadany przez aktualnego mówcę
            dialog = frag
            if current_speaker and dialog.strip():
                # Sprawdzamy, czy mówca ma przypisany akcent
                dopasowane_dane = None
                for klucz, dane in akcenty_map.items():
                    if klucz in current_speaker or current_speaker in klucz:
                        dopasowane_dane = dane
                        break

                if dopasowane_dane:
                    zmodyfikowano = False

                    # Aplikacja przez Poliglotę
                    if poliglota and dopasowane_dane["nazwa"]:
                        znormalizowana = usun_pl_znaki_z_nazwy(dopasowane_dane["nazwa"])
                        nazwa_funkcji = f"akcent_{znormalizowana}"

                        if hasattr(poliglota, nazwa_funkcji):
                            funkcja_akcentu = getattr(poliglota, nazwa_funkcji)
                            dialog = funkcja_akcentu(dialog)
                            zmodyfikowano = True
                            zastosowane_info.add(f"{nazwa_funkcji} dla {current_speaker}")

                    # Fallback ręczny z Księgi
                    if not zmodyfikowano and dopasowane_dane["reguly"]:
                        for z, na in dopasowane_dane["reguly"]:
                            dialog = dialog.replace(z.lower(), na.lower()).replace(z.upper(), na.upper())
                        zastosowane_info.add(f"reguły ręczne dla {current_speaker}")

            nowe_fragmenty.append(dialog)

    if zastosowane_info:
        st.toast(f"🎭 Silnik fonetyczny użył: {', '.join(zastosowane_info)}")

    return "".join(nowe_fragmenty)

st.sidebar.markdown("---")
st.session_state.summary_text = st.sidebar.text_area(
    "🧠 Pamięć Długotrwała (Streszczenie)",
    value=st.session_state.summary_text,
    height=150,
    help="Tutaj AI zapisze streszczenie przy przepełnieniu. Możesz je też edytować ręcznie."
)

# ==========================================
# GŁÓWNY INTERFEJS
# ==========================================
st.title("Reżyser Audio GPT - Hybrydowe Studio")

# System Flash Messages (dla komunikatów po rerun)
if st.session_state.flash_msg:
    if st.session_state.flash_type == "success":
        st.success(st.session_state.flash_msg)
    elif st.session_state.flash_type == "warning":
        st.warning(st.session_state.flash_msg)
    elif st.session_state.flash_type == "error":
        st.error(st.session_state.flash_msg)
    else:
        st.info(st.session_state.flash_msg)
    st.session_state.flash_msg = ""
    st.session_state.flash_type = ""

mode = st.radio(
    "Wybierz tryb pracy:",
    (
        "🧠 Tryb Burzy Mózgów (Planowanie, opcje, BEZ ZAPISU DO PLIKU)",
        "🎬 Tryb Surowego Skryptu (Audio Gry, fonetyka, ZAPIS DO PLIKU)",
        "📖 Tryb Tradycyjnego Audiobooka (Proza, rozdziały, ZAPIS DO PLIKU)"
    )
)

# --- ZBIÓR BAZOWYCH PROMPTÓW ---
PROMPT_BURZA_BASE = f"""# Rola: Kreatywny Architekt Opowieści (Showrunner)

> **KRYTYCZNY ZAKAZ:** W tym trybie NIE PISZESZ gotowego tekstu skryptu ani rozdziałów. Generujesz 3 opcje rozwoju fabuły i szkice promptów.

### 🌍 Żelazne Zasady Świata:
{world_context}

### ⚙️ Algorytm Pracy:
1. **LOGIKA I KONSEKWENCJA:** Opcje muszą być spójne z Księgą Świata i opierać się na akcjach bohaterów. Zakaz tanich cudów i "deus ex machina" (chyba że świat na to wyraźnie pozwala).
2. **ESKALACJA LUB KONKLUZJA:** - DOMYŚLNIE: Komplikuj fabułę i zmuszaj bohaterów do trudnych decyzji.
   - WYJĄTEK (WENTYL BEZPIECZEŃSTWA): Jeśli użytkownik wprost prosi o zakończenie, finał lub epilog, Twoim zadaniem jest wygenerować opcje satysfakcjonującego, logicznego domknięcia wątków, bez wprowadzania nowych zagrożeń na siłę.
3. **TRZY RÓŻNE ŚCIEŻKI:** Generuj 3 różnorodne podejścia do sceny (np. fizyczne, psychologiczne, kompromisowe).

Format wyjściowy MUSI wyglądać dokładnie tak. 
UWAGA: Zmienną do wypełnienia przez Ciebie jest tylko [CEL SCENY]. Linijkę "[Reżyserze: ...]" oraz "[DYREKTYWA]: ..." masz przepisać DOSŁOWNIE, słowo w słowo! Absolutny zakaz wymyślania tam własnych porad!

**OPCJA 1: [Krótki tytuł]**
[Logiczny opis tego, co się wydarzy]
```text
--- SZKIC PROMPTU (ZMODYFIKUJ PRZED WYSŁANIEM!) ---
[CEL SCENY]: [Szczegółowy opis akcji/dialogu, który wymyśliłeś na podstawie Opcji 1]

[Reżyserze: dopisz tutaj własne pomysły, szczegóły przejścia między scenami lub specyficzne detale, które chcesz usłyszeć/zobaczyć!]
[DYREKTYWA]: Wygeneruj DŁUGI tekst, realizując cel. Trzymaj się żelaznych zasad wybranego trybu!
```
(Powtórz ten sam, rygorystyczny format dla Opcji 2 i 3).
"""

PROMPT_SKRYPT = f"""# Rola: Reżyser Słuchowisk i Inżynier Dźwięku (Audio-Play / Foley Script)

Piszesz **WYŁĄCZNIE po polsku**. Twój output to **SUROWY SKRYPT DŹWIĘKOWY** pozbawiony narratora. 

### 🌍 Żelazne Zasady Świata i Akcentów:
{world_context}

### 🎙️ Zasady Formatu (MUSISZ ICH PRZESTRZEGAĆ W 100%):
1. **TYLKO DWA TAGI (KRYTYCZNE):** Używasz WYŁĄCZNIE tagów: 
   - `[SFX: <opis>]` dla efektów dźwiękowych tła i akcji.
   - `[Imię Postaci: emocja i rodzaj oddechu]` dla dialogów.
   **ABSOLUTNY ZAKAZ UŻYWANIA NARRATORA.** Każdy tag musi być w nowej linii.
2. **CZYSTA FIZYKA W SFX:** Tagi SFX służą do syntezy w generatorach dźwięku. Zakaz poezji i metafor. Pisz czysto fizycznie (np. `[SFX: Głośny brzęk tłuczonego szkła]`).
3. **ZWIĘZŁOŚĆ SFX:** Zawartość tagu `[SFX: ...]` może mieć maksymalnie 10 słów.
4. **NATURALNOŚĆ FONETYCZNA:** Wplataj naturalne wdechy i westchnienia prosto w tekst dialogu postaci (`hh...`, `khh...`).
5. **DOMYKANIE SCEN:** - DOMYŚLNIE (ANTI-CLOSURE): Urywaj scenę w środku akcji lub dialogu.
   - WYJĄTEK (FINAŁ/EPILOG): Jeśli to koniec historii, wygaś scenę odpowiednio (np. cichym dźwiękiem tła, ciszą).
"""

PROMPT_AUDIOBOOK = f"""# Rola: Pisarz Bestsellerów (Tradycyjna Proza)

Piszesz **WYŁĄCZNIE po polsku**. Twój output to **W 100% SUROWY TEKST LITERACKI**.

> **STYL LITERACKI:** Jesteś w trybie książki. Zero tagów audio `[SFX]`, zero tagów `[Speaker]`. Dialogi wplataj naturalnie w bogatą narrację z użyciem myślników (np. *— Nie możesz tego zrobić — powiedziała.*).

### 🌍 Żelazne Zasady Świata:
{world_context}

### 📖 Zasady Trybu Audiobooka:
1. **GĘSTA, KLASYCZNA PROZA:** Skup się na głębokich opisach, sensoryce i psychologii postaci. Pisz długie akapity. Pokaż, zamiast tylko opisywać.
2. **CZYSTOŚĆ TEKSTU:** Gładki język literacki — bezwzględny zakaz wstawiania tagów z nawiasami kwadratowymi.
3. **ABSOLUTNY ZAKAZ MARKDOWNU:** Żadnych nagłówków (typu "Rozdział 1", "Scena 2"), tytułów, ani list punktowanych.
4. **DOMYKANIE SCEN:** - DOMYŚLNIE (ANTI-CLOSURE): Urwij tekst bez domykania sceny, by utrzymać płynność.
   - WYJĄTEK (FINAŁ/EPILOG): Jeśli to zakończenie, wygaś narrację w satysfakcjonujący, literacki sposób.
"""

# ==========================================

def submit_text():
    if st.session_state.user_input.strip() != "":
        st.session_state.current_prompt = st.session_state.user_input
        st.session_state.ready_to_send = True
        st.session_state.user_input = ""

# ==========================================
# WSKAŹNIK PRZECIĄŻENIA AI (DYNAMICZNY)
# ==========================================
progress_placeholder = st.empty()

def aktualizuj_pasek_postepu():
    total_chars = len(st.session_state.full_story)
    LIMIT_ZNAKOW = 200000
    OSTRZEZENIE = 150000
    ALARM = 175000

    with progress_placeholder.container():
        st.write("### 🧠 Pamięć Modelu (Stan Okna Kontekstowego)")
        if total_chars > 0:
            zapelnienie = min(total_chars / LIMIT_ZNAKOW, 1.0)
            st.progress(zapelnienie)
            if total_chars >= ALARM:
                st.error(f"🚨 KRYTYCZNE PRZEŁADOWANIE: Zużyto {total_chars} z {LIMIT_ZNAKOW} znaków! \n\n**JAK KONTYNUOWAĆ W NIESKOŃCZONOŚĆ:** \n1. Użyj 'Burzy Mózgów' i wpisz polecenie zawierające słowo **streszczenie** lub **podsumowanie**. \n2. Kliknij 'Zapisz Streszczenie (na stałe)'. \n3. Kliknij 'Wyczyść pamięć'. \nKolejne wygenerowane fragmenty będą dopisywane do pliku bez przeciążania maszyny!")
            elif total_chars >= OSTRZEZENIE:
                st.warning(f"⚠️ STAN OSTRZEGAWCZY: Zużyto {total_chars} z {LIMIT_ZNAKOW} znaków. Pamięć się zapełnia. Wkrótce konieczne będzie wygenerowanie i zapisanie streszczenia.")
            else:
                st.info(f"🟢 Zużycie pamięci: {total_chars} / {LIMIT_ZNAKOW} znaków. Masz bezpieczny bufor. Jeśli chcesz, zawsze możesz poprosić w Burzy Mózgów o aktualizację <STRESZCZENIE>.")
        else:
            st.info("🟢 Pamięć jest czysta. Maszyna gotowa na nową historię.")

# Wywołanie funkcji przy pierwszym ładowaniu strony
aktualizuj_pasek_postepu()

# ==========================================
# 1. ZARZĄDZANIE HISTORIĄ
# ==========================================
st.write("### 1. Zarządzanie historią")

# Blokada zmiany pliku w trakcie pracy
czy_pamiec_zajeta = bool(st.session_state.full_story.strip() or st.session_state.summary_text.strip())
czy_pamiec_pusta = not czy_pamiec_zajeta

# --- TWARDE ZARZĄDZANIE NAZWĄ PLIKU ---
if "zapisana_nazwa_pliku" not in st.session_state:
    st.session_state.zapisana_nazwa_pliku = ""

file_name_input = st.text_input(
    "Nazwa pliku projektu (np. znieczulica, kroniki_arkonii, audiobook_wampiry):",
    value=st.session_state.zapisana_nazwa_pliku,
    key="file_name_widget",
    disabled=czy_pamiec_zajeta,
    help="Aby zmienić plik, musisz najpierw wyczyścić pamięć." if czy_pamiec_zajeta else ""
)

# Jeśli pamięć jest pusta (pole aktywne), aktualizujemy nazwę. Jeśli zajęta (pole wyłączone), trzymamy się zapisanej.
if not czy_pamiec_zajeta:
    st.session_state.zapisana_nazwa_pliku = file_name_input
    file_name = file_name_input
else:
    file_name = st.session_state.zapisana_nazwa_pliku

# --- BLOKADA: Wymóg podania nazwy pliku ---
brak_nazwy_pliku = not file_name.strip()

col_load, col_clear, col_sum = st.columns(3)

_load_btn = col_load.button(
    "Wczytaj plik do pamięci",
    disabled=czy_pamiec_zajeta or brak_nazwy_pliku,
    help="Podaj nazwę pliku, aby wczytać." if brak_nazwy_pliku else ("Aby wczytać nowy plik, musisz najpierw wyczyścić pamięć." if czy_pamiec_zajeta else "")
)

if _load_btn:
    if not file_name.strip():
        st.error("⚠️ Podaj nazwę pliku przed wczytaniem!")
    else:
        filepath = f"skrypty/{file_name}.txt"
        summary_path = f"skrypty/{file_name}_streszczenie.txt"

        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            # --- Analiza struktury wczytanego pliku ---
            _has_prolog  = bool(re.search(r'(?i)\bprolog\b', content))
            _has_epilog  = bool(re.search(r'(?i)\bepilog\b', content))
            _chapter_nums = [int(m) for m in re.findall(r'(?i)\brozdzia[łl]\s+(\d+)', content)]
            _max_chapter  = max(_chapter_nums) if _chapter_nums else 0

            # --- Nowe liczniki dla Aktów i Scen ---
            _akt_nums = [int(m) for m in re.findall(r'(?i)\bakt\s+(\d+)', content)]
            _max_akt = max(_akt_nums) if _akt_nums else 0
            # Szukamy najwyższego numeru sceny, ale tylko w obrębie ostatniego Aktu
            ostatni_akt_split = re.split(r'(?i)\bakt\s+\d+', content)
            ostatni_fragment = ostatni_akt_split[-1] if ostatni_akt_split else content
            _scena_nums = [int(m) for m in re.findall(r'(?i)\bscena\s+(\d+)', ostatni_fragment)]
            _max_scena = max(_scena_nums) if _scena_nums else 0
            st.session_state.akt_counter = _max_akt + 1
            st.session_state.scena_counter = _max_scena + 1
            _epilog_match = re.search(r'(?i)\bepilog\b', content)
            _epilog_has_content = (
                _epilog_match is not None and
                len(content[_epilog_match.end():].strip()) > 0
            )

            if _has_epilog:
                st.session_state.chapter_counter = _max_chapter + 1
            elif _has_prolog and _max_chapter == 0:
                st.session_state.chapter_counter = 1
            else:
                st.session_state.chapter_counter = _max_chapter + 1

            # --- WCZYTAJ KSIĘGĘ ŚWIATA DLA TEGO PROJEKTU ---
            # Używamy klucza pending — faktyczne przypisanie do world_lore_widget
            # nastąpi na początku NASTĘPNEGO runu, zanim widget zostanie wyrenderowany.
            _lore_path_load = f"skrypty/{file_name}.md"
            if os.path.exists(_lore_path_load):
                with open(_lore_path_load, "r", encoding="utf-8") as f:
                    st.session_state.world_lore_pending = f.read()
            else:
                st.session_state.world_lore_pending = ""

            # --- LOGIKA NIESKOŃCZONEJ PAMIĘCI ---
            if os.path.exists(summary_path):
                with open(summary_path, "r", encoding="utf-8") as f:
                    st.session_state.summary_text = f.read()
                st.session_state.full_story = "" # Celowe czyszczenie pod nieskończoną kontynuację
                _lore_info = f" Wczytano też Księgę Świata z pliku `{file_name}.md`." if os.path.exists(_lore_path_load) else ""
                st.session_state.flash_msg = f"✅ Znaleziono zapisane streszczenie! Wczytano je do Pamięci Długotrwałej. Pamięć Bieżąca pozostaje pusta, by oszczędzać tokeny. Skrypt jest gotowy do nieskończonej kontynuacji pliku **{file_name}.txt**!{_lore_info}"
                st.session_state.flash_type = "success"
                st.rerun()
            else:
                st.session_state.full_story = content
                st.session_state.summary_text = ""
                _lore_info = f" Wczytano też Księgę Świata z pliku `{file_name}.md`." if os.path.exists(_lore_path_load) else ""
                st.session_state.flash_msg = f"✅ Wczytano całą historię z pliku **{file_name}.txt**!{_lore_info}"
                st.session_state.flash_type = "success"
                st.rerun()
        else:
            st.error(f"Nie znaleziono pliku: {filepath}")

if col_sum.button("💾 Zapisz Streszczenie (na stałe)", disabled=brak_nazwy_pliku, help="Podaj nazwę pliku, aby zapisać streszczenie." if brak_nazwy_pliku else ""):
    if not file_name.strip():
        st.error("⚠️ Podaj nazwę pliku w polu 'Nazwa pliku', aby zapisać streszczenie (np. znieczulica)!")
    elif not st.session_state.summary_text.strip():
        st.error("⚠️ Pamięć Długotrwała (Streszczenie) jest pusta! Wygeneruj je w Trybie Burzy Mózgów i skopiuj lub poczekaj na auto-zapis AI.")
    else:
        if not os.path.exists("skrypty"):
            os.makedirs("skrypty")
        summary_path = f"skrypty/{file_name}_streszczenie.txt"
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write(st.session_state.summary_text)
        st.success(f"✅ Zapisano pigułkę wiedzy do pliku: **{file_name}_streszczenie.txt**! Możesz teraz bezpiecznie wyczyścić pamięć.")

if col_clear.button(
    "Wyczyść pamięć",
    disabled=czy_pamiec_pusta,
    help="Pamięć jest już pusta." if czy_pamiec_pusta else ""
):
    st.session_state.full_story = ""
    st.session_state.current_prompt = ""
    st.session_state.ready_to_send = False
    st.session_state.chapter_counter = 1
    st.session_state.akt_counter = 1
    st.session_state.scena_counter = 1
    # Resetujemy projekt — użytkownik musi wpisać nową nazwę, by zacząć kolejną sesję.
    # Używamy pending, bo widget world_lore_widget został już wyrenderowany w tym runie.
    st.session_state.zapisana_nazwa_pliku = ""
    st.session_state.world_lore_pending = ""
    st.info("Pamięć bieżąca wyczyszczona. Streszczenie w Pamięci Długotrwałej zostało zachowane.")
    st.rerun()

# ==========================================
# PANEL CIĘĆ I STRUKTURY
# ==========================================
if "Burzy" not in mode:
    st.write("### ✂️ Zarządzanie Strukturą")
    _ostatnia_niepusta_linia = ""
    for _linia in reversed(st.session_state.full_story.splitlines()):
        if _linia.strip():
            _ostatnia_niepusta_linia = _linia.strip()
            break
    _epilog_w_tekscie = bool(re.search(r'(?i)\bepilog\b', st.session_state.full_story))

    _konczy_sie_naglowkiem = bool(re.match(r'(?i)^(rozdzia[łl]\s+\d+|akt\s+\d+|scena\s+\d+|prolog)\s*$', _ostatnia_niepusta_linia)) or _epilog_w_tekscie

    # --- TRYB AUDIOBOOKA (Rozdziały) ---
    if "Audiobooka" in mode:
        st.info("ℹ️ **Tryb Audiobooka:** LLM generuje limitowane partie tekstu. Kiedy uznasz, że rozdział jest gotowy, wstaw cięcie poniżej.")

        if st.session_state.chapter_counter > 0:
            automatyczny_naglowek = f"Rozdział {st.session_state.chapter_counter}"

            if st.button(
                f"✂️ Wstaw cięcie ({automatyczny_naglowek})",
                disabled=_konczy_sie_naglowkiem or brak_nazwy_pliku,
                help="Podaj nazwę pliku, aby zarządzać cięciami." if brak_nazwy_pliku else ("Nagłówek już istnieje na końcu historii." if _konczy_sie_naglowkiem else "Nie można dodawać po epilogu." if _epilog_w_tekscie else "")
            ):
                content_to_add = f"\n\n{automatyczny_naglowek}\n\n"
                if not os.path.exists("skrypty"):
                    os.makedirs("skrypty")
                with open(f"skrypty/{file_name}.txt", "a", encoding="utf-8") as f:
                    f.write(content_to_add)

                st.session_state.full_story += content_to_add
                st.session_state.chapter_counter += 1

                st.session_state.flash_msg = f"✅ Wstawiono nagłówek: **{automatyczny_naglowek}**."
                st.session_state.flash_type = "success"
                st.rerun()

    # --- TRYB SKRYPTU (Akty i Sceny) ---
    elif "Skryptu" in mode:
        st.info("🎬 **Tryb Skryptu:** Dziel swoją sztukę na Akty i Sceny. Architekt Audiobooków automatycznie zamieni Akty na główne punkty nawigacyjne (Heading 1) dla ElevenLabs.")

        col_akt, col_scena = st.columns(2)

        if col_akt.button(
            f"🎭 Wstaw Akt {st.session_state.akt_counter}",
            disabled=_konczy_sie_naglowkiem or brak_nazwy_pliku,
            help="Podaj nazwę pliku." if brak_nazwy_pliku else ("Nagłówek już istnieje na końcu." if _konczy_sie_naglowkiem else "Blokada po epilogu." if _epilog_w_tekscie else "")
        ):
            akt_naglowek = f"Akt {st.session_state.akt_counter}"
            scena_naglowek = "Scena 1"
            content_to_add = f"\n\n{akt_naglowek}\n\n{scena_naglowek}\n\n"

            if not os.path.exists("skrypty"):
                os.makedirs("skrypty")
            with open(f"skrypty/{file_name}.txt", "a", encoding="utf-8") as f:
                f.write(content_to_add)

            st.session_state.full_story += content_to_add
            st.session_state.akt_counter += 1
            st.session_state.scena_counter = 2  # Od razu ustawiamy na 2, bo Scena 1 została właśnie wstawiona

            st.session_state.flash_msg = f"✅ Wstawiono: **{akt_naglowek}** oraz **{scena_naglowek}**."
            st.session_state.flash_type = "success"
            st.rerun()

        if col_scena.button(
            f"🎬 Wstaw Scenę {st.session_state.scena_counter}",
            disabled=_konczy_sie_naglowkiem or brak_nazwy_pliku,
            help="Podaj nazwę pliku." if brak_nazwy_pliku else ("Nagłówek już istnieje na końcu." if _konczy_sie_naglowkiem else "Blokada po epilogu." if _epilog_w_tekscie else "")
        ):
            scena_naglowek = f"Scena {st.session_state.scena_counter}"
            content_to_add = f"\n\n{scena_naglowek}\n\n"
            if not os.path.exists("skrypty"):
                os.makedirs("skrypty")
            with open(f"skrypty/{file_name}.txt", "a", encoding="utf-8") as f:
                f.write(content_to_add)

            st.session_state.full_story += content_to_add
            st.session_state.scena_counter += 1

            st.session_state.flash_msg = f"✅ Wstawiono: **{scena_naglowek}**."
            st.session_state.flash_type = "success"
            st.rerun()

    # --- PROLOG I EPILOG (Wspólne dla obu trybów) ---
    col_prolog, col_epilog = st.columns(2)
    _prolog_juz_jest = "Prolog" in st.session_state.full_story
    _historia_niepusta = bool(st.session_state.full_story.strip())
    _epilog_juz_jest = "Epilog" in st.session_state.full_story
    _prolog_disabled = _historia_niepusta or _prolog_juz_jest
    _prolog_help = "Prolog już istnieje." if _prolog_juz_jest else ("Fabuła nie jest pusta." if _historia_niepusta else "")

    if col_prolog.button("📜 Wstaw Prolog", disabled=_prolog_disabled or brak_nazwy_pliku, help="Podaj nazwę pliku." if brak_nazwy_pliku else _prolog_help):
        if not file_name.strip():
            st.error("⚠️ Podaj nazwę pliku!")
        else:
            header_text = "Prolog\n\n"
            st.session_state.full_story = header_text
            if not os.path.exists("skrypty"):
                os.makedirs("skrypty")
            with open(f"skrypty/{file_name}.txt", "a", encoding="utf-8") as f:
                f.write(header_text)
            st.session_state.flash_msg = "✅ Wstawiono **Prolog**."
            st.session_state.flash_type = "success"
            st.rerun()

    if col_epilog.button("🏁 Wstaw Epilog", disabled=_epilog_juz_jest or brak_nazwy_pliku, help="Podaj nazwę pliku." if brak_nazwy_pliku else ("Epilog już istnieje." if _epilog_juz_jest else "")):
        if not file_name.strip():
            st.error("⚠️ Podaj nazwę pliku!")
        else:
            header_text = "\n\nEpilog\n\n"
            st.session_state.full_story += header_text
            if not os.path.exists("skrypty"):
                os.makedirs("skrypty")
            with open(f"skrypty/{file_name}.txt", "a", encoding="utf-8") as f:
                f.write(header_text)
            st.session_state.flash_msg = "✅ Wstawiono **Epilog**."
            st.session_state.flash_type = "success"
            st.rerun()

# ==========================================
# 2. STUDIO NAGRANIOWE
# ==========================================
st.write("### 2. Studio Nagraniowe")

with st.expander("Pokaż aktualną fabułę w pamięci"):
    if st.session_state.full_story:
        st.text_area("Podgląd", value=st.session_state.full_story, height=400, disabled=True, label_visibility="hidden")
    else:
        st.info("(Pamięć jest pusta)")

st.text_area("Podaj instrukcje do kolejnego fragmentu (Wpisz słowo 'streszczenie' lub 'podsumowanie', aby wymusić zapis pamięci):", key="user_input")
st.button("Wyślij do AI", on_click=submit_text)

if st.session_state.ready_to_send:
    # --- BLOKADA: brak Księgi Świata ---
    if not world_context.strip():
        st.error("🚫 **Brak Księgi Świata!** Uzupełnij zasady świata w panelu bocznym przed wysłaniem zapytania do AI.")
        st.session_state.ready_to_send = False
    # --- BLOKADA: brak klienta OpenAI ---
    elif client is None:
        st.error("🔑 **Brak połączenia z OpenAI.** Sprawdź plik `golden_key.env` i uruchom aplikację ponownie.")
        st.session_state.ready_to_send = False
    elif "Burzy" not in mode and brak_nazwy_pliku:
        st.error("🚨 **BŁĄD NAZWY PLIKU:** Zanim wygenerujesz tekst do zapisu (Tryb Skryptu lub Audiobooka), musisz podać nazwę pliku docelowego na samej górze strony!")
        st.session_state.ready_to_send = False
    else:
        user_text = st.session_state.current_prompt
        slowa_kluczowe = ["streszcz", "streść", "podsumuj", "podsumowanie"]

        # --- BLOKADA: Ochrona przed zniszczeniem pliku głównym ---
        if "Burzy" not in mode and any(slowo in user_text.lower() for slowo in slowa_kluczowe):
            st.error("🚨 **BŁĄD ZAPISU:** Próbujesz wygenerować streszczenie, będąc w trybie zapisu do pliku (Skrypt/Audiobook)! To zniszczyłoby Twoją książkę. Przełącz się na '🧠 Tryb Burzy Mózgów' na samej górze interfejsu i spróbuj ponownie.")
            st.session_state.ready_to_send = False
        else:
            with st.spinner("AI przetwarza..."):
                # --- DYNAMICZNY SYSTEM PROMPT ---
                _total_chars_now = len(st.session_state.full_story)
                _OSTRZEZENIE = 150000
                if "Burzy" in mode:
                    active_system_prompt = PROMPT_BURZA_BASE
                    # Sprawdzamy, czy użytkownik ręcznie poprosił o streszczenie używając różnych synonimów
                    slowa_kluczowe = ["streszcz", "streść", "podsumuj", "podsumowanie"]
                    if any(slowo in user_text.lower() for slowo in slowa_kluczowe):
                        active_system_prompt += "\n\n[TRYB WYMUSZONEGO STRESZCZENIA]: Użytkownik ręcznie zażądał zapisania stanu fabuły! Zanim wygenerujesz Opcje, MUSISZ na samej górze wygenerować streszczenie zamknięte w tagach <STRESZCZENIE> tutaj tekst </STRESZCZENIE>. Streszczenie musi zawierać TRZY obowiązkowe elementy:\n1. Zwięzłe podsumowanie dotychczasowych wydarzeń.\n2. Sekcję [OSTATNIA SCENA]: dokładna kopia (słowo w słowo) ostatnich 2-3 akapitów przesłanego tekstu — posłuży jako punkt zahaczenia dla kolejnych generacji.\n3. Sekcję [STYL I TON]: jednozdaniowa notatka o aktualnym klimacie i tempie narracji (np. 'Akcja jest napięta, język surowy i brutalny')."
                    elif _total_chars_now < _OSTRZEZENIE:
                        active_system_prompt += "\n\n[TRYB OPTYMALIZACJI]: Pamięć jest pojemna. NIE GENERUJ żadnego streszczenia dotychczasowej fabuły. Przejdź od razu do generowania 3 Opcji i promptów."
                    else:
                        active_system_prompt += "\n\n[TRYB ALARMOWY - ZBLIŻA SIĘ KONIEC PAMIĘCI]: Pamięć jest prawie pełna! Zanim wygenerujesz Opcje, MUSISZ na samej górze wygenerować streszczenie zamknięte w tagach <STRESZCZENIE> tutaj tekst </STRESZCZENIE>. Streszczenie musi zawierać TRZY obowiązkowe elementy:\n1. Zwięzłe podsumowanie dotychczasowych wydarzeń.\n2. Sekcję [OSTATNIA SCENA]: dokładna kopia (słowo w słowo) ostatnich 2-3 akapitów przesłanego tekstu — posłuży jako punkt zahaczenia dla kolejnych generacji.\n3. Sekcję [STYL I TON]: jednozdaniowa notatka o aktualnym klimacie i tempie narracji (np. 'Akcja jest napięta, język surowy i brutalny')."
                elif "Skryptu" in mode:
                    active_system_prompt = PROMPT_SKRYPT
                    # DYNAMICZNA KONTROLA LOGIKI I CHRONOLOGII
                    if not st.session_state.full_story.strip() or "[" not in st.session_state.full_story:
                        active_system_prompt += "\n\n[TRYB STARTOWY - PUSTA PAMIĘĆ]: Zaczynasz zupełnie nową historię! \n1. AUDIO-EKSPOZYCJA (KRYTYCZNE): Ponieważ brak narratora, MUSISZ zbudować kontekst akcją. Scena nie może dziać się w próżni. Rozpocznij od wejścia postaci w przestrzeń (np. podjeżdżające auto, otwieranie ciężkich drzwi, zjazd windą, kroki z zewnątrz). \n2. EKSPOZYCJA W DIALOGU: Postacie w pierwszych kwestiach muszą w naturalny sposób (lub np. przez odprawę radiową) zdradzić, GDZIE są i KIM dla siebie są. \n3. ZAKAZ JASNOWIDZENIA: Komentowanie czyjegoś głosu dopiero po jego usłyszeniu."
                    else:
                        active_system_prompt += "\n\n[TRYB KONTYNUACJI]: Kontynuujesz trwającą scenę. Utrzymaj naturalną płynność akcji i napięcie. Zamiast narratora, regularnie wplataj opisy przestrzeni i ruchu postaci za pomocą surowych tagów [SFX: ...] pomiędzy dialogami."
                else:
                    active_system_prompt = PROMPT_AUDIOBOOK

                # Profesjonalne budowanie kontekstu API
                payload_messages = [
                    {"role": "system", "content": active_system_prompt}
                ]

                # 1. Pamięć Długotrwała
                if st.session_state.summary_text.strip():
                    payload_messages.append({"role": "assistant", "content": f"[STRESZCZENIE POPRZEDNICH WYDARZEŃ]:\n{st.session_state.summary_text}"})

                # 2. Pamięć Krótkotrwała (Bieżąca fabuła)
                if st.session_state.full_story.strip():
                    payload_messages.append({"role": "assistant", "content": f"[OBECNA FABUŁA]:\n{st.session_state.full_story}"})

                # Instrukcja od użytkownika jako niezależny krok
                payload_messages.append({"role": "user", "content": user_text})

                if "Skryptu" in mode:
                    payload_messages[-1]["content"] += "\n\n(PRZYPOMNIENIE KRYTYCZNE: Tryb AUDIO-PLAY/FOLEY. Używaj TYLKO tagów [SFX: ...] oraz [Postać: ...]. ZERO NARRATORA! Tagi SFX: max 10 słów, czysta akustyka. ZABRONIONE jest rozwiązywanie problemów na końcu tekstu! Zastosuj BRUTALNY ANTI-CLOSURE: urwij scenę w ułamku sekundy, gdy dzieje się coś złego (np. rozlega się nagły alarm, zamek iskrzy, postać urywa zdanie w połowie). Żadnych szczęśliwych zakończeń, podsumowań i dziękowania sobie na koniec!)"
                elif "Audiobooka" in mode:
                    payload_messages[-1]["content"] += "\n\n(PRZYPOMNIENIE KRYTYCZNE: Tryb KSIĄŻKI. Zero tagów audio/głosowych. Długa, gęsta proza z dialogami po myślnikach. Zakaz Markdownu i nagłówków. BRUTALNY ANTI-CLOSURE: urwij tekst w środku napięcia lub w połowie akcji, chyba że to wyraźny finał historii.)"
                elif "Burzy" in mode:
                    payload_messages[-1]["content"] += "\n\n(PRZYPOMNIENIE KRYTYCZNE: Generujesz tylko 3 opcje + prompty. Opcje logiczne i uziemione. Komplikuj fabułę, CHYBA ŻE użytkownik wyraźnie prosi o Epilog lub zakończenie - wtedy ładnie domknij historię. Opcje NIE MOGĄ kończyć się pełnym sukcesem bez konsekwencji!)"

                try:
                    response = client.chat.completions.create(
                        model="gpt-4o",
                        messages=payload_messages,
                        temperature=0.85
                    )
                    response_text = response.choices[0].message.content

                    # --- Aplikacja twardych filtrów fonetycznych w Pythonie ---
                    if "Skryptu" in mode:
                        response_text = zastosuj_akcenty_uniwersalne(response_text, world_context)

                    # --- WYCIĄGANIE STRESZCZENIA (tylko Burza Mózgów w trybie alarmowym) ---
                    if "Burzy" in mode:
                        _match = re.search(r'<STRESZCZENIE>(.*?)</STRESZCZENIE>', response_text, re.DOTALL | re.IGNORECASE)
                        if _match:
                            st.session_state.summary_text = _match.group(1).strip()
                            st.success("✅ Wykryto i zapisano nowe streszczenie do Pamięci Długotrwałej!")
                            response_text = re.sub(r'<STRESZCZENIE>.*?</STRESZCZENIE>', '', response_text, flags=re.DOTALL | re.IGNORECASE).strip()

                    # Zapisz odpowiedź do last_response
                    st.session_state.last_response = response_text

                    if "ZAPIS DO PLIKU" in mode:
                        refusal_keywords = [
                            "jako model językowy", "as an ai", "nie mogę spełnić tej prośby",
                            "nie mogę wygenerować", "narusza zasady", "zasady bezpieczeństwa"
                        ]
                        # Blokada zapisu po epilogu: tylko gdy po nagłówku "Epilog" jest już treść
                        _epilog_idx = st.session_state.full_story.find("Epilog")
                        _epilog_has_content = (
                            _epilog_idx != -1 and
                            len(st.session_state.full_story[_epilog_idx + len("Epilog"):].strip()) > 0
                        )
                        if not file_name.strip():
                            st.error("⚠️ Podaj nazwę pliku w sekcji 'Zarządzanie historią', aby zapisać odpowiedź AI do pliku!")
                        elif "Audiobooka" in mode and _epilog_has_content:
                            st.error("🚫 Epilog ma już treść — nie można dopisywać kolejnych fragmentów po zakończeniu historii. Wyczyść pamięć, by zacząć nową.")
                        elif any(keyword in response_text.lower() for keyword in refusal_keywords):
                            st.error("🚨 AI odrzuciło prompt przez filtry bezpieczeństwa! Tekst NIE ZOSTANIE zapisany.")
                        else:
                            if st.session_state.full_story:
                                st.session_state.full_story += "\n\n" + response_text
                            else:
                                st.session_state.full_story = response_text

                            if not os.path.exists("skrypty"):
                                os.makedirs("skrypty")
                            target_file = f"skrypty/{file_name}.txt"
                            with open(target_file, "a", encoding="utf-8") as f:
                                f.write(response_text + "\n\n")
                            st.session_state.flash_msg = f"✅ Dopisano do pliku: {target_file}"
                            st.session_state.flash_type = "success"
                            # USUNIĘTO st.rerun()

                    elif "Burzy" in mode:
                        st.session_state.flash_msg = "Odpowiedź wygenerowana. Fabuła w pamięci pozostaje niezmieniona."
                        st.session_state.flash_type = "info"
                        # USUNIĘTO st.rerun()

                except openai.RateLimitError:
                    st.error("🚨 Brak kredytów OpenAI!")
                except Exception as e:
                    wyswietl_blad_ai(e)

        st.session_state.ready_to_send = False

        # Bezpieczny rerun dopiero po wyjściu ze spinnera i zgaszeniu flagi
        if st.session_state.flash_msg:
            st.rerun()

if st.session_state.last_response:
    st.write("### Ostatnia Odpowiedź AI:")
    st.text_area("Zaznacz i skopiuj poniższy tekst:", value=st.session_state.last_response, height=350)

# ==========================================
# 3. POSTPRODUKCJA
# ==========================================
if "Audiobooka" in mode:
    st.write("### 3. 🎛️ Postprodukcja")
    _pamiec_pusta = not st.session_state.full_story.strip()
    _brak_klienta = client is None

    st.write("#### 📜 Nadaj Tytuły Rozdziałom (AI)")
    st.info("Moduł iteruje po rozdziałach z zapisanego pliku i nadaje im krótki tytuł (analizując tylko początki).")
    if st.button("Nadaj Tytuły Rozdziałom (AI)", disabled=_pamiec_pusta or _brak_klienta):
        filepath = f"skrypty/{file_name}.txt" if 'file_name' in locals() else "skrypty/skrypt_audio.txt"
        if not os.path.exists(filepath):
            st.error("⚠️ Brak zapisanego pliku! Wczytaj lub wygeneruj najpierw fabułę, by móc nadać tytuły.")
        else:
            with open(filepath, "r", encoding="utf-8") as f:
                pelny_tekst = f.read()
            with st.spinner("AI wymyśla tytuły... To może potrwać."):
                tytuly = []
                try:
                    wzorzec = r'(?i)\n*(Prolog|Rozdział \d+|Epilog)\n*'
                    fragmenty = re.split(wzorzec, pelny_tekst)
                    if len(fragmenty) <= 1:
                        st.warning("Nie znaleziono tagów rozdziałów w pliku.")
                    else:
                        progress_bar = st.progress(0)
                        total_chapters = len(range(1, len(fragmenty), 2))
                        current = 0
                        for i in range(1, len(fragmenty), 2):
                            naglowek = fragmenty[i].strip()
                            tresc = fragmenty[i+1].strip()
                            current += 1
                            if len(tresc) < 50:
                                tytuly.append(f"**{naglowek}**: (Fragment zbyt krótki)")
                                progress_bar.progress(current / total_chapters)
                                continue
                            st.write(f"⏳ Tytułowanie: {naglowek}...")
                            probka = tresc[:6000]
                            prompt_tytul = f"Oto treść fragmentu książki ({naglowek}). Wymyśl JEDEN krótki, chwytliwy i literacki tytuł bez cudzysłowów.\n\nTREŚĆ:\n{probka}"
                            response = client.chat.completions.create(
                                model="gpt-4o-mini",
                                messages=[
                                    {"role": "system", "content": "Jesteś wybitnym redaktorem. Odpowiadasz wyłącznie samym tytułem."},
                                    {"role": "user", "content": prompt_tytul}
                                ],
                                temperature=0.7
                            )
                            tytul_out = response.choices[0].message.content.strip()
                            tytuly.append(f"**{naglowek}**: {tytul_out}")
                            progress_bar.progress(current / total_chapters)
                        st.success("✅ Generowanie tytułów zakończone!")
                        st.markdown("### 📜 Proponowane Tytuły:")
                        for t in tytuly:
                            st.markdown(t)
                except openai.RateLimitError:
                    st.error("🚨 BRAK KREDYTÓW! Przerwano operację.")
                    if tytuly:
                        st.markdown("### 📜 Proponowane Tytuły (Częściowe):")
                        for t in tytuly:
                            st.markdown(t)
                except Exception as e:
                    wyswietl_blad_ai(e)
                    if tytuly:
                        st.markdown("### 📜 Proponowane Tytuły (Częściowe):")
                        for t in tytuly:
                            st.markdown(t)
