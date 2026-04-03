import streamlit as st
import streamlit.components.v1 as components
import os

st.set_page_config(page_title="Reżyser Audio GPT", page_icon="🎬", layout="wide")

# Ukrywanie UI Streamlita (Deploy, Menu, Stopka, Header)
st.markdown("""
    <style>
    .stAppDeployButton {display:none !important;}
    .stDeployButton {display:none !important;}
    #MainMenu {visibility: hidden !important;}
    header {visibility: hidden !important;}
    footer {visibility: hidden !important;}
    </style>
""", unsafe_allow_html=True)

# Ustawienie głównego języka strony dla NVDA
components.html(
    """
    <script>
        window.parent.document.documentElement.lang = 'pl';
    </script>
    """,
    width=0, height=0)

st.title("🎬 Witaj w Reżyserze Audio GPT (Wersja 10.0 - Publiczna Beta)")
st.markdown("""
To jest Twoje zintegrowane, hybrydowe studio nagraniowe. Zamiast uruchamiać skrypty osobno, **wybierz narzędzie z menu po lewej stronie**:

* **1. Reżyseria** - Pisz skrypty i prozę z AI, dynamicznie zarządzaj Księgą Świata.
* **2. Poliglota** - Nakładaj twarde akcenty pod lokalne syntezatory (NVDA/Vocalizer) i tłumacz teksty.
* **3. Konwerter** - Szybko twórz profesjonalne pliki Word z nagłówkami poziomu 1.
""")

st.markdown("---")
st.subheader("System Check")

env_file = "golden_key.env"

if not os.path.exists(env_file):
    st.warning("⚠️ Nie znaleziono pliku `golden_key.env`. Moduły oparte na AI (Reżyseria, Tłumacz) nie będą działać. Tryby lokalne są aktywne.")
    
    st.info("💡 **Ułatwienie:** Nie musisz tworzyć tego pliku ręcznie. Kliknij przycisk poniżej, a system sam wygeneruje dla Ciebie pusty plik z odpowiednim formatem.")
    
    if st.button("🛠️ Wygeneruj plik golden_key.env"):
        try:
            with open(env_file, "w", encoding="utf-8") as f:
                f.write("OPENAI_API_KEY=TUTAJ_WKLEJ_SWOJ_KLUCZ\n")
            st.success("✅ Plik został pomyślnie utworzony! Przeczytaj instrukcję poniżej, a po wklejeniu klucza odśwież stronę.")
        except Exception as e:
            st.error(f"Nie udało się utworzyć pliku: {e}")
            
    st.markdown("""
    ### 🔑 Co zrobić po wygenerowaniu pliku?
    1. Przejdź do głównego folderu aplikacji (tam, gdzie znajduje się m.in. plik `Start.py`).
    2. Znajdź nowo utworzony plik o nazwie **`golden_key.env`** i naciśnij na nim Enter.
    3. Windows może wyświetlić okno, w którym zaproponuje wyszukanie aplikacji w Microsoft Store. 
    4. **KRYTYCZNE:** Kliknij opcję **"Więcej aplikacji"** (lub "Więcej opcji" w starszych systemach Windows), a dopiero potem znajdź na rozwiniętej liście i wybierz systemowy **Notatnik** (Notepad).
    5. W otwartym Notatniku zobaczysz tekst: `OPENAI_API_KEY=TUTAJ_WKLEJ_SWOJ_KLUCZ`. 
    6. Usuń słowa `TUTAJ_WKLEJ_SWOJ_KLUCZ` i wklej w ich miejsce swój prawdziwy klucz skopiowany ze strony platform.openai.com (klucz zaczyna się od `sk-proj-...`). Znak równości (`=`) musi zostać nienaruszony!
    7. Zapisz plik (skrót Ctrl+S), zamknij Notatnik i **odśwież tę stronę w przeglądarce**.
    """)
else:
    # --- ZAAWANSOWANY SYSTEM CHECK (WALIDACJA SKŁADNI) ---
    try:
        with open(env_file, "r", encoding="utf-8-sig") as f:
            zawartosc = f.read().strip()

        # 1. Sprawdzanie, czy użytkownik nie skasował parametru lub znaku równości
        if "OPENAI_API_KEY=" not in zawartosc:
            st.error("🚨 **Błąd struktury pliku!** Brakuje wymaganego parametru `OPENAI_API_KEY=`. Prawdopodobnie skasowałeś znak równości lub nazwę zmiennej. Usuń plik, wygeneruj go ponownie i wklej klucz ostrożniej.")

        # 2. Sprawdzanie, czy użytkownik w ogóle wkleił swój klucz
        elif "TUTAJ_WKLEJ_SWOJ_KLUCZ" in zawartosc:
            st.warning("⚠️ **Klucz nie został wprowadzony!** W pliku `golden_key.env` nadal znajduje się tekst zastępczy. Otwórz plik w Notatniku, usuń tekst zastępczy i wklej swój prawdziwy klucz API.")

        else:
            # Wyodrębnij wartość klucza (część po "OPENAI_API_KEY=")
            klucz_raw = zawartosc.split("OPENAI_API_KEY=")[-1].split("\n")[0]
            klucz = klucz_raw.strip()

            # 3. Sprawdzanie cudzysłowów wokół klucza
            if (klucz.startswith('"') and klucz.endswith('"')) or \
               (klucz.startswith("'") and klucz.endswith("'")):
                st.error("🚨 **Zbędne cudzysłowy wokół klucza!** Klucz API wklejono w cudzysłowach (np. `\"sk-...\"`). Otwórz plik w Notatniku i usuń znaki cudzysłowu — klucz musi być wpisany bezpośrednio po znaku równości, bez żadnych dodatkowych znaków.")

            # 4. Sprawdzanie spacji lub znaków niedrukowalnych na początku wartości
            elif klucz_raw != klucz:
                st.error("🚨 **Niedozwolone znaki wokół klucza!** Przed lub za kluczem API wykryto spację bądź inny niewidoczny znak. Otwórz plik w Notatniku i upewnij się, że wartość zaczyna się natychmiast po znaku `=`, bez żadnych spacji.")

            # 5. Sprawdzanie, czy wklejony klucz w ogóle przypomina format OpenAI
            elif not klucz.startswith("sk-"):
                st.error("🚨 **Podejrzany format klucza!** Poprawny klucz OpenAI zawsze zaczyna się od znaków `sk-` (np. `sk-proj-...`). Upewnij się, że skopiowałeś właściwy ciąg znaków i nie ma przed nim spacji.")

            # 6. Sprawdzanie minimalnej długości klucza (z lekcją dla użytkownika)
            elif len(klucz) < 40:
                st.warning(f"⚠️ **Klucz wydaje się zbyt krótki** (wykryto {len(klucz)} znaków, oczekiwano co najmniej 40). Prawdopodobnie skopiowałeś tylko fragment. Jeśli zamknąłeś już okienko z kluczem na stronie platform.openai.com, zapamiętaj tę surową lekcję: system wyświetla klucz w całości tylko raz! Musisz teraz wrócić na swoje konto, użyć opcji 'Revoke secret key' dla tego uciętego klucza i wygenerować nowy. Na Twojej liście pozostanie ślad po starym, martwym kluczu — zignoruj go, nie robi on żadnej szkody, ale niech przypomina Ci, by następnym razem przed kliknięciem 'Done' skopiować całość od deski do deski.")

            # Jeśli wszystkie testy przeszły pomyślnie
            else:
                st.success("✅ Klucz API (golden_key.env) wykryty i poprawnie sformatowany. Wszystkie moduły są gotowe do pracy.")

    except Exception as e:
        st.error(f"🚨 **Nie udało się odczytać pliku golden_key.env:** {e}")