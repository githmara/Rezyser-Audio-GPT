"""
gui_rezyser.py – Panel modułu „Reżyser" (Główna scena twórcza).

Zastępuje pages/1_Rezyseria.py (Streamlit).
Dziedziczy po wx.Panel; podpinany do MainFrame z main.py.

Zaimplementowane funkcje:
    - Stan pamięci w atrybutach instancji (odpowiednik st.session_state)
    - Dwukolumnowy layout: sidebar (Księga Świata + Pamięć) | obszar roboczy
    - Panel Zarządzania Strukturą (dynamicznie ukrywany/pokazywany):
        • Prolog, Epilog – wspólne dla trybów Skrypt i Audiobook
        • Wstaw Akt N + Scena 1 automatycznie (tryb Skrypt)
        • Wstaw Rozdział N (tryb Audiobook)
    - Panel Postprodukcji (tylko tryb Audiobook):
        • Nadaj Tytuły Rozdziałom (AI) – wątek tła + wx.Gauge + CallAfter
    - Pełna integracja OpenAI gpt-4o: _wyslij_worker (threading + wx.CallAfter)
    - Silnik fonetyczny: zastosuj_akcenty_uniwersalne (gui_poliglota)
    - Postprodukcja: _tytuly_worker (gpt-4o-mini, iteracja po rozdziałach)
"""

from __future__ import annotations

import os
import re
import threading

import openai
from dotenv import load_dotenv

import wx
from gui_poliglota import (
    akcent_angielski,
    akcent_finski,
    akcent_francuski,
    akcent_hiszpanski,
    akcent_islandzki,
    akcent_niemiecki,
    akcent_wloski,
)


class RezyserPanel(wx.Panel):
    """
    Panel modułu „Reżyser Audio GPT".

    Obsługuje trzy tryby pracy z AI (OpenAI gpt-4o):
        - Burza Mózgów  – planowanie fabuły, 3 opcje + prompty (BEZ zapisu)
        - Skrypt        – surowy skrypt dźwiękowy [SFX] + [Postać] (ZAPIS)
        - Audiobook     – tradycyjna proza literacka (ZAPIS)

    Stan sesji przechowywany w atrybutach instancji (odpowiednik
    st.session_state ze Streamlita).

    Wywołania OpenAI API realizowane będą w wątku tła (threading.Thread)
    z wynikami przez wx.CallAfter — implementacja w kolejnym etapie.
    """

    TOOL_DESCRIPTION = (
        "Reżyser Audio GPT to hybrydowe studio twórcze.\n\n"
        "Tryb Burzy Mózgów  – planuj fabułę, generuj 3 opcje (BEZ zapisu do pliku).\n"
        "Tryb Skryptu        – pisz surowy skrypt dźwiękowy z tagami [SFX] i [Postać:"
        " emocja] (ZAPIS DO PLIKU).\n"
        "Tryb Audiobooka     – generuj gęstą, klasyczną prozę literacką (ZAPIS DO PLIKU).\n\n"
        "Projekty zapisywane są w podfolderze 'skrypty/' obok programu.\n"
        "Podaj nazwę projektu BEZ rozszerzenia (np. kroniki_arkonii).\n"
        "Aby zmienić projekt, musisz najpierw wyczyścić pamięć bieżącą."
    )

    ENV_FILENAME = "golden_key.env"
    SKRYPTY_DIR  = "skrypty"

    # Etykiety trybów pracy wyświetlane w RadioBox
    TRYBY_PRACY = [
        "Burza Mózgów (Planowanie, BEZ zapisu do pliku)",
        "Skrypt (Audio-gra, fonetyka, ZAPIS DO PLIKU)",
        "Audiobook (Proza, rozdziały, ZAPIS DO PLIKU)",
    ]

    # ------------------------------------------------------------------
    # Szablony promptów systemowych
    # Użycie: .format(world_context=world_context) przy budowaniu payload
    # ------------------------------------------------------------------
    PROMPT_BURZA_BASE = (
        "# Rola: Kreatywny Architekt Opowieści (Showrunner)\n\n"
        "> **KRYTYCZNY ZAKAZ:** W tym trybie NIE PISZESZ gotowego tekstu skryptu ani "
        "rozdziałów. Generujesz 3 opcje rozwoju fabuły i szkice promptów.\n\n"
        "### \U0001f30d Żelazne Zasady Świata:\n"
        "{world_context}\n\n"
        "### \u2699\ufe0f Algorytm Pracy:\n"
        "1. **LOGIKA I KONSEKWENCJA:** Opcje muszą być spójne z Księgą Świata i opierać się "
        "na akcjach bohaterów. Zakaz tanich cudów i \"deus ex machina\" (chyba że świat na to "
        "wyraźnie pozwala).\n"
        "2. **ESKALACJA LUB KONKLUZJA:** - DOMYŚLNIE: Komplikuj fabułę i zmuszaj bohaterów "
        "do trudnych decyzji.\n"
        "   - WYJĄTEK (WENTYL BEZPIECZEŃSTWA): Jeśli użytkownik wprost prosi o zakończenie, "
        "finał lub epilog, Twoim zadaniem jest wygenerować opcje satysfakcjonującego, "
        "logicznego domknięcia wątków, bez wprowadzania nowych zagrożeń na siłę.\n"
        "3. **TRZY RÓŻNE ŚCIEŻKI:** Generuj 3 różnorodne podejścia do sceny "
        "(np. fizyczne, psychologiczne, kompromisowe).\n\n"
        "Format wyjściowy MUSI wyglądać dokładnie tak.\n"
        "UWAGA: Zmienną do wypełnienia przez Ciebie jest tylko [CEL SCENY]. Linijkę "
        "\"[Reżyserze: ...]\" oraz \"[DYREKTYWA]: ...\" masz przepisać DOSŁOWNIE, "
        "słowo w słowo! Absolutny zakaz wymyślania tam własnych porad!\n\n"
        "**OPCJA 1: [Krótki tytuł]**\n"
        "[Logiczny opis tego, co się wydarzy]\n"
        "```text\n"
        "--- SZKIC PROMPTU (ZMODYFIKUJ PRZED WYSŁANIEM!) ---\n"
        "[CEL SCENY]: [Szczegółowy opis akcji/dialogu, który wymyśliłeś na podstawie Opcji 1]\n\n"
        "[Reżyserze: dopisz tutaj własne pomysły, szczegóły przejścia między scenami lub "
        "specyficzne detale, które chcesz usłyszeć/zobaczyć]\n"
        "[DYREKTYWA]: Wygeneruj DŁUGI tekst, realizując cel. "
        "Trzymaj się żelaznych zasad wybranego trybu!\n"
        "```\n"
        "(Powtórz ten sam, rygorystyczny format dla Opcji 2 i 3).\n"
    )

    PROMPT_SKRYPT = (
        "# Rola: Reżyser Słuchowisk i Inżynier Dźwięku (Audio-Play / Foley Script)\n\n"
        "Piszesz **WYŁĄCZNIE po polsku**. "
        "Twój output to **SUROWY SKRYPT DŹWIĘKOWY** pozbawiony narratora.\n\n"
        "### \U0001f30d Żelazne Zasady Świata i Akcentów:\n"
        "{world_context}\n\n"
        "### \U0001f399\ufe0f Zasady Formatu (MUSISZ ICH PRZESTRZEGAĆ W 100%):\n"
        "1. **TYLKO DWA TAGI (KRYTYCZNE):** Używasz WYŁĄCZNIE tagów:\n"
        "   - `[SFX: <opis>]` dla efektów dźwiękowych tła i akcji.\n"
        "   - `[Imię Postaci: emocja i rodzaj oddechu]` dla dialogów.\n"
        "   **ABSOLUTNY ZAKAZ UŻYWANIA NARRATORA.** Każdy tag musi być w nowej linii.\n"
        "2. **CZYSTA FIZYKA W SFX:** Tagi SFX służą do syntezy w generatorach dźwięku. "
        "Zakaz poezji i metafor. Pisz czysto fizycznie "
        "(np. `[SFX: Głośny brzęk tłuczonego szkła]`).\n"
        "3. **ZWIĘZŁOŚĆ SFX:** Zawartość tagu `[SFX: ...]` może mieć maksymalnie 10 słów.\n"
        "4. **NATURALNOŚĆ FONETYCZNA:** Wplataj naturalne wdechy i westchnienia prosto "
        "w tekst dialogu postaci (`hh...`, `khh...`).\n"
        "5. **DOMYKANIE SCEN:** - DOMYŚLNIE (ANTI-CLOSURE): Urywaj scenę w środku akcji "
        "lub dialogu.\n"
        "   - WYJĄTEK (FINAŁ/EPILOG): Jeśli to koniec historii, wygaś scenę odpowiednio "
        "(np. cichym dźwiękiem tła, ciszą).\n"
    )

    PROMPT_AUDIOBOOK = (
        "# Rola: Pisarz Bestsellerów (Tradycyjna Proza)\n\n"
        "Piszesz **WYŁĄCZNIE po polsku**. "
        "Twój output to **W 100% SUROWY TEKST LITERACKI**.\n\n"
        "> **STYL LITERACKI:** Jesteś w trybie książki. Zero tagów audio `[SFX]`, zero tagów "
        "`[Speaker]`. Dialogi wplataj naturalnie w bogatą narrację z użyciem myślników "
        "(np. *— Nie możesz tego zrobić — powiedziała.*).\n\n"
        "### \U0001f30d Żelazne Zasady Świata:\n"
        "{world_context}\n\n"
        "### \U0001f4d6 Zasady Trybu Audiobooka:\n"
        "1. **GĘSTA, KLASYCZNA PROZA:** Skup się na głębokich opisach, sensoryce "
        "i psychologii postaci. Pisz długie akapity. Pokaż, zamiast tylko opisywać.\n"
        "2. **CZYSTOŚĆ TEKSTU:** Gładki język literacki — bezwzględny zakaz wstawiania "
        "tagów z nawiasami kwadratowymi.\n"
        "3. **ABSOLUTNY ZAKAZ MARKDOWNU:** Żadnych nagłówków (typu \"Rozdział 1\", "
        "\"Scena 2\"), tytułów, ani list punktowanych.\n"
        "4. **DOMYKANIE SCEN:** - DOMYŚLNIE (ANTI-CLOSURE): Urwij tekst bez domykania "
        "sceny, by utrzymać płynność.\n"
        "   - WYJĄTEK (FINAŁ/EPILOG): Jeśli to zakończenie, wygaś narrację "
        "w satysfakcjonujący, literacki sposób.\n"
    )

    def __init__(self, parent: wx.Window) -> None:
        super().__init__(parent, style=wx.TAB_TRAVERSAL)
        self.SetName("Panel Reżysera Audio GPT")

        # ── Stan pamięci (odpowiednik st.session_state z 1_Rezyseria.py) ──
        self.full_story: str = ""            # bieżąca fabuła w pamięci
        self.chapter_counter: int = 1        # licznik rozdziałów (Audiobook)
        self.akt_counter: int = 1            # licznik aktów (Skrypt)
        self.scena_counter: int = 1          # licznik scen (Skrypt)
        self.zapisana_nazwa_pliku: str = ""  # aktywna nazwa projektu (bez .txt)
        self.last_response: str = ""         # ostatnia odpowiedź AI
        self.summary_text: str = ""          # Pamięć Długotrwała (Streszczenie)
        self.world_lore: str = ""            # Księga Świata (zasady i postacie)

        # ── Klient OpenAI ──────────────────────────────────────────────────
        self._client = None
        self._api_dostepne: bool = False
        self._worker_thread: threading.Thread | None = None
        self._init_api()

        self._build_ui()
        self._bind_events()
        self._refresh_ui_state()

        # NVDA odczyta opis narzędzia jako pierwsze po otwarciu panelu
        wx.CallAfter(self._description.SetFocus)

    # ------------------------------------------------------------------
    # Inicjowanie klienta OpenAI
    # ------------------------------------------------------------------
    def _init_api(self) -> None:
        """Ładuje golden_key.env i inicjuje klienta OpenAI (jeśli klucz poprawny)."""
        app_dir = os.path.dirname(os.path.abspath(__file__))
        env_path = os.path.join(app_dir, self.ENV_FILENAME)
        if os.path.exists(env_path):
            load_dotenv(env_path)
            api_key = os.getenv("OPENAI_API_KEY", "")
            if api_key and api_key.startswith("sk-"):
                try:
                    from openai import OpenAI  # noqa: PLC0415
                    self._client = OpenAI(api_key=api_key)
                    self._api_dostepne = True
                except Exception:
                    self._api_dostepne = False

    # ------------------------------------------------------------------
    # Budowanie interfejsu
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        """
        Buduje cały interfejs panelu.

        Kluczowa zasada A11y: wszystkie widżety są bezpośrednimi dziećmi
        RezyserPanel (bez zagnieżdżonych wx.Panel). Dzięki temu kolejność
        tabulatora = kolejność tworzenia widżetów, co pozwala zachować
        logiczny przepływ nawigacji niezależnie od wizualnego rozmieszczenia
        w sizerach.

        Pożądana kolejność Tab:
            opis → nazwa_pliku → wczytaj → wyczyść
            → ksiega_swiata → zapisz_ksiege
            → pamiec_dlugotrwala → zapisz_pamiec
            → radiobox_trybu → pelna_historia → instrukcje → wyslij
        """
        BORDER = 8

        # ══════════════════════════════════════════════════════════════
        # BLOK A – Nagłówek i opis (poza kolejką Tab: StaticText)
        # ══════════════════════════════════════════════════════════════

        heading = wx.StaticText(
            self,
            label="🎬  Reżyser Audio GPT – Hybrydowe Studio Twórcze",
        )
        hf = heading.GetFont()
        hf.SetPointSize(16)
        hf.MakeBold()
        heading.SetFont(hf)

        # ── [TAB 1] Opis narzędzia – Read-Only, NoBorder (NVDA-friendly) ──
        self._description = wx.TextCtrl(
            self,
            value=self.TOOL_DESCRIPTION,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.NO_BORDER,
            name="Opis modułu Reżyser Audio GPT",
        )
        self._description.SetBackgroundColour(self.GetBackgroundColour())
        self._description.SetMinSize((-1, 110))

        # ══════════════════════════════════════════════════════════════
        # BLOK B – Pole nazwy pliku + przyciski wczytaj/wyczyść
        # ══════════════════════════════════════════════════════════════

        lbl_file = wx.StaticText(
            self,
            label="Nazwa pliku projektu (bez rozszerzenia, np. kroniki_arkonii):",
        )

        # ── [TAB 2] Pole nazwy projektu ──────────────────────────────
        self._txt_file_name = wx.TextCtrl(
            self,
            style=wx.TE_PROCESS_ENTER,
            name="Pole nazwy pliku projektu",
        )
        self._txt_file_name.SetHint("np. kroniki_arkonii")
        self._txt_file_name.SetToolTip(
            "Wpisz nazwę projektu BEZ rozszerzenia.\n"
            "Plik historii zapisywany jako: skrypty/<nazwa>.txt\n"
            "Pole zablokowane, gdy pamięć jest zajęta."
        )

        # ── [TAB 3] Wczytaj historię ──────────────────────────────────
        self._btn_load = wx.Button(self, label="Wczytaj historię")
        self._btn_load.SetToolTip(
            "Wczytuje istniejący plik projektu (skrypty/<nazwa>.txt) do pamięci.\n"
            "Aktywny tylko gdy pamięć jest pusta i podano nazwę."
        )

        # ── [TAB 4] Wyczyść bieżącą (zostaw Streszczenie i Księgę) ───
        self._btn_clear_current = wx.Button(
            self, label="Wyczyść bieżącą (zostaw Streszczenie)"
        )
        self._btn_clear_current.SetToolTip(
            "Czyści wyłącznie historię bieżącą z pamięci.\n"
            "Streszczenie (Pamięć Długotrwała) i Księga Świata zostają zachowane.\n"
            "Używaj do kontynuacji długiej książki po wygenerowaniu streszczenia."
        )

        # ── [TAB 5] Zamknij Projekt – Twardy Reset ────────────────────
        self._btn_hard_reset = wx.Button(self, label="Zamknij Projekt (Twardy Reset)")
        self._btn_hard_reset.SetToolTip(
            "CAŁKOWITE wyczyszczenie projektu: historia, streszczenie, Księga Świata.\n"
            "Zeruje wszystkie liczniki i odblokowuje pole nazwy pliku.\n"
            "Używaj przy zmianie projektu lub zupełnie nowej historii."
        )

        # ══════════════════════════════════════════════════════════════
        # BLOK C – Sidebar: Księga Świata + Pamięć Długotrwała
        # (TAB 5–8; wizualnie w lewej kolumnie)
        # ══════════════════════════════════════════════════════════════

        lbl_sb_heading = wx.StaticText(self, label="📖 Pasek Boczny projektu")
        sbf = lbl_sb_heading.GetFont()
        sbf.SetPointSize(11)
        sbf.MakeBold()
        lbl_sb_heading.SetFont(sbf)

        lbl_ksiega = wx.StaticText(
            self,
            label="Księga Świata – Zasady i Postacie:",
        )

        # ── [TAB 5] Ksiega Swiata – duże pole wieloliniowe ────────────
        self._txt_ksiega_swiata = wx.TextCtrl(
            self,
            style=wx.TE_MULTILINE,
            name="Pole Księgi Świata – zasady i postacie",
        )
        self._txt_ksiega_swiata.SetHint(
            "Wpisz zasady świata, opis postaci i ich akcenty fonetyczne…\n"
            "Np. [Geralt: akcent islandzki]\n"
            "Zawartość dołączana jest do każdego zapytania AI."
        )
        self._txt_ksiega_swiata.SetToolTip(
            "Kontekst stale dołączany do AI: zasady świata, postacie, akcenty fonetyczne.\n"
            "Zapis na dysk wymaga podania nazwy pliku projektu."
        )

        # ── [TAB 6] Zapisz Ksiege ─────────────────────────────────────
        self._btn_zapisz_ksiege = wx.Button(self, label="💾 Zapisz Księgę na stałe")
        self._btn_zapisz_ksiege.SetToolTip(
            "Zapisuje Księgę Świata do pliku: skrypty/<nazwa>.md\n"
            "Wymaga podania nazwy pliku projektu."
        )

        lbl_pamiec = wx.StaticText(
            self,
            label="🧠 Pamięć Długotrwała (Streszczenie):",
        )

        # ── [TAB 7] Pamięć Długotrwała ────────────────────────────────
        self._txt_pamiec = wx.TextCtrl(
            self,
            style=wx.TE_MULTILINE,
            name="Pole Pamięci Długotrwałej – streszczenie wydarzeń",
        )
        self._txt_pamiec.SetHint(
            "Tu AI zapisze streszczenie przy przepełnieniu pamięci.\n"
            "Możesz je też edytować ręcznie."
        )
        self._txt_pamiec.SetToolTip(
            "Streszczenie poprzednich wydarzeń dołączane do każdego zapytania AI.\n"
            "Pozwala kontynuować historię bez ograniczeń okna kontekstowego modelu."
        )

        # ── [TAB 8] Zapisz Streszczenie ──────────────────────────────
        self._btn_zapisz_pamiec = wx.Button(self, label="💾 Zapisz Streszczenie")
        self._btn_zapisz_pamiec.SetToolTip(
            "Zapisuje streszczenie do pliku: skrypty/<nazwa>_streszczenie.txt\n"
            "Po zapisie możesz bezpiecznie wyczyścić pamięć bieżącą."
        )

        # ══════════════════════════════════════════════════════════════
        # BLOK D – Główny obszar roboczy
        # (TAB 9–12; wizualnie w prawej kolumnie)
        # ══════════════════════════════════════════════════════════════

        lbl_main_heading = wx.StaticText(self, label="🎬 Obszar Roboczy")
        mf = lbl_main_heading.GetFont()
        mf.SetPointSize(11)
        mf.MakeBold()
        lbl_main_heading.SetFont(mf)

        # ── [TAB 9] RadioBox trybu pracy ─────────────────────────────
        self._rb_mode = wx.RadioBox(
            self,
            label="Tryb pracy:",
            choices=self.TRYBY_PRACY,
            majorDimension=1,
            style=wx.RA_SPECIFY_COLS,
            name="Wybór trybu pracy AI",
        )
        self._rb_mode.SetToolTip(
            "Burza Mózgów – planowanie bez zapisu do pliku.\n"
            "Skrypt        – surowy skrypt dźwiękowy (zapisywany do pliku).\n"
            "Audiobook     – tradycyjna proza literacka (zapisywana do pliku)."
        )

        # ══════════════════════════════════════════════════════════════
        # BLOK E – Panel Zarządzania Strukturą (dynamicznie ukrywany)
        # Tworzony TU (po _rb_mode), by Tab order był poprawny:
        #   RadioBox → [przyciski struktury] → podgląd historii → instrukcje
        # ══════════════════════════════════════════════════════════════
        self._pnl_struktura = wx.Panel(self)

        lbl_struktura = wx.StaticText(
            self._pnl_struktura,
            label="✂️ Zarządzanie Strukturą",
        )
        sf = lbl_struktura.GetFont()
        sf.SetPointSize(10)
        sf.MakeBold()
        lbl_struktura.SetFont(sf)

        self._btn_prolog = wx.Button(
            self._pnl_struktura,
            label="📜 Wstaw Prolog",
            name="Przycisk Wstaw Prolog",
        )
        self._btn_prolog.SetToolTip(
            "Wstawia nagłówek 'Prolog' na samym początku historii.\n"
            "Możliwy tylko gdy historia jest pusta. Wymaga nazwy projektu."
        )

        self._btn_epilog = wx.Button(
            self._pnl_struktura,
            label="🏁 Wstaw Epilog",
            name="Przycisk Wstaw Epilog",
        )
        self._btn_epilog.SetToolTip(
            "Wstawia nagłówek 'Epilog' na końcu historii.\n"
            "Blokuje dalsze dopisywanie treści po Epilogu."
        )

        self._btn_rozdzial = wx.Button(
            self._pnl_struktura,
            label="✂️ Wstaw cięcie (Rozdział 1)",
            name="Przycisk Wstaw Rozdział",
        )
        self._btn_rozdzial.SetToolTip(
            "Wstawia nagłówek kolejnego rozdziału do historii i pliku.\n"
            "Dostępny wyłącznie w trybie Audiobooka."
        )

        self._btn_akt = wx.Button(
            self._pnl_struktura,
            label="🎭 Wstaw Akt 1",
            name="Przycisk Wstaw Akt",
        )
        self._btn_akt.SetToolTip(
            "Wstawia nagłówek 'Akt N' oraz automatycznie 'Scena 1' do historii i pliku.\n"
            "Dostępny wyłącznie w trybie Skryptu."
        )

        self._btn_scena = wx.Button(
            self._pnl_struktura,
            label="🎬 Wstaw Scenę 1",
            name="Przycisk Wstaw Scenę",
        )
        self._btn_scena.SetToolTip(
            "Wstawia nagłówek kolejnej sceny do historii i pliku.\n"
            "Dostępny wyłącznie w trybie Skryptu."
        )

        _prolog_epilog_row = wx.BoxSizer(wx.HORIZONTAL)
        _prolog_epilog_row.Add(self._btn_prolog, flag=wx.RIGHT, border=6)
        _prolog_epilog_row.Add(self._btn_epilog)

        _akt_scena_row = wx.BoxSizer(wx.HORIZONTAL)
        _akt_scena_row.Add(self._btn_akt, flag=wx.RIGHT, border=6)
        _akt_scena_row.Add(self._btn_scena)

        _sizer_struktura = wx.BoxSizer(wx.VERTICAL)
        _sizer_struktura.Add(lbl_struktura,       flag=wx.ALL,                          border=BORDER)
        _sizer_struktura.Add(_prolog_epilog_row,  flag=wx.LEFT | wx.RIGHT | wx.BOTTOM,  border=BORDER)
        _sizer_struktura.Add(self._btn_rozdzial,  flag=wx.LEFT | wx.RIGHT | wx.BOTTOM,  border=BORDER)
        _sizer_struktura.Add(_akt_scena_row,      flag=wx.LEFT | wx.RIGHT | wx.BOTTOM,  border=BORDER)
        self._pnl_struktura.SetSizer(_sizer_struktura)

        # ── Podgląd pełnej historii ───────────────────────────────────
        lbl_full_story = wx.StaticText(
            self,
            label="Bieżąca historia w pamięci (tylko do odczytu – nawiguj strzałkami):",
        )

        # ── [TAB 10] Podgląd full_story – duże pole Read-Only ────────
        self._txt_full_story = wx.TextCtrl(
            self,
            style=wx.TE_MULTILINE | wx.TE_READONLY,
            name="Podgląd pełnej historii w pamięci – tylko do odczytu",
        )
        self._txt_full_story.SetHint("(pamięć jest pusta – wczytaj projekt lub zacznij nowy)")

        # ── Instrukcje ────────────────────────────────────────────────
        lbl_user_input = wx.StaticText(
            self,
            label=(
                "Instrukcje do kolejnego fragmentu "
                "(wpisz 'streszczenie', by wymusić zapis do Pamięci Długotrwałej):"
            ),
        )

        # ── [TAB 11] Pole instrukcji od użytkownika ──────────────────
        self._txt_user_input = wx.TextCtrl(
            self,
            style=wx.TE_MULTILINE,
            name="Pole instrukcji dla AI – dawny user_input",
        )
        self._txt_user_input.SetHint(
            "Podaj instrukcje do kolejnego fragmentu historii…\n"
            "(np. 'Opisz spotkanie Geralta z wiedźmą w lesie. Duże napięcie.')"
        )
        self._txt_user_input.SetMinSize((-1, 100))

        # ── [TAB 12] Wyślij do AI ─────────────────────────────────────
        self._btn_wyslij = wx.Button(self, label="Wyślij do AI")
        self._btn_wyslij.SetToolTip(
            "Wysyła instrukcje do modelu gpt-4o i dopisuje odpowiedź do historii.\n"
            "Wymaga aktywnego klucza API i uzupełnionej Księgi Świata."
        )

        # ══════════════════════════════════════════════════════════════
        # BLOK F – Panel Postprodukcji (dynamicznie ukrywany)
        # Wyświetlany NA SAMYM DOLE obszaru roboczego, pod przyciskiem Wyślij.
        # ══════════════════════════════════════════════════════════════
        self._pnl_postprodukcja = wx.Panel(self)

        lbl_postprod = wx.StaticText(
            self._pnl_postprodukcja,
            label="🎛️ Postprodukcja",
        )
        pf = lbl_postprod.GetFont()
        pf.SetPointSize(10)
        pf.MakeBold()
        lbl_postprod.SetFont(pf)

        lbl_tytuly_info = wx.StaticText(
            self._pnl_postprodukcja,
            label=(
                "Moduł iteruje po rozdziałach z zapisanego pliku "
                "i nadaje im krótki tytuł literacki (analiza AI)."
            ),
        )

        self._btn_tytuly_ai = wx.Button(
            self._pnl_postprodukcja,
            label="📜 Nadaj Tytuły Rozdziałom (AI)",
            name="Przycisk Nadaj Tytuły Rozdziałom AI",
        )
        self._btn_tytuly_ai.SetToolTip(
            "Iteruje po rozdziałach z zapisanego pliku i nadaje im tytuły (gpt-4o-mini).\n"
            "Wymaga zapisanego pliku projektu i aktywnego klucza API."
        )

        self._gauge_postprod = wx.Gauge(self._pnl_postprodukcja, range=100)
        self._gauge_postprod.Hide()

        self._lbl_postprod_status = wx.StaticText(self._pnl_postprodukcja, label="")
        self._lbl_postprod_status.Hide()

        _sizer_postprod = wx.BoxSizer(wx.VERTICAL)
        _sizer_postprod.Add(lbl_postprod,              flag=wx.ALL,                                   border=BORDER)
        _sizer_postprod.Add(lbl_tytuly_info,           flag=wx.LEFT | wx.RIGHT | wx.BOTTOM,           border=BORDER)
        _sizer_postprod.Add(self._btn_tytuly_ai,       flag=wx.LEFT | wx.BOTTOM,                      border=BORDER)
        _sizer_postprod.Add(
            self._gauge_postprod,
            flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP,
            border=BORDER,
        )
        _sizer_postprod.Add(self._lbl_postprod_status, flag=wx.LEFT | wx.BOTTOM,                      border=BORDER)
        self._pnl_postprodukcja.SetSizer(_sizer_postprod)

        # ══════════════════════════════════════════════════════════════
        # BLOK G – Wskaźnik przepełnienia okna kontekstowego AI
        # ══════════════════════════════════════════════════════════════
        lbl_kontekst = wx.StaticText(
            self,
            label="🧠 Pamięć Modelu (Stan Okna Kontekstowego):",
        )
        kf = lbl_kontekst.GetFont()
        kf.SetWeight(wx.FONTWEIGHT_BOLD)
        lbl_kontekst.SetFont(kf)

        self._gauge_kontekst = wx.Gauge(
            self, range=100, style=wx.GA_HORIZONTAL | wx.GA_SMOOTH
        )
        self._gauge_kontekst.SetValue(0)

        self._lbl_kontekst_status = wx.TextCtrl(
            self,
            value="🟢 Pamięć czysta. Maszyna gotowa na nową historię.",
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.NO_BORDER,
            name="Status pamięci modelu AI",
        )
        self._lbl_kontekst_status.SetBackgroundColour(self.GetBackgroundColour())
        self._lbl_kontekst_status.SetMinSize((-1, 60))

        # ══════════════════════════════════════════════════════════════
        # BUDOWANIE SIZERÓW (układ wizualny – niezależny od Tab order)
        # ══════════════════════════════════════════════════════════════

        # ── Górna część: nagłówek + opis + separator ──────────────────
        top_sizer = wx.BoxSizer(wx.VERTICAL)
        top_sizer.Add(heading,            flag=wx.ALL,                    border=BORDER)
        top_sizer.Add(
            self._description,
            flag=wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            border=BORDER,
        )
        top_sizer.Add(
            wx.StaticLine(self),
            flag=wx.EXPAND | wx.LEFT | wx.RIGHT,
            border=BORDER,
        )

        # ── Lewa kolumna – Sidebar ────────────────────────────────────
        sidebar_sizer = wx.BoxSizer(wx.VERTICAL)
        sidebar_sizer.Add(lbl_sb_heading,          flag=wx.ALL,                   border=BORDER)
        sidebar_sizer.Add(lbl_ksiega,              flag=wx.LEFT | wx.RIGHT | wx.TOP, border=BORDER)
        sidebar_sizer.Add(
            self._txt_ksiega_swiata,
            proportion=2,
            flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP,
            border=BORDER,
        )
        sidebar_sizer.Add(self._btn_zapisz_ksiege, flag=wx.ALL,                   border=BORDER)
        sidebar_sizer.Add(
            wx.StaticLine(self),
            flag=wx.EXPAND | wx.LEFT | wx.RIGHT,
            border=BORDER,
        )
        sidebar_sizer.Add(lbl_pamiec,              flag=wx.LEFT | wx.RIGHT | wx.TOP, border=BORDER)
        sidebar_sizer.Add(
            self._txt_pamiec,
            proportion=1,
            flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP,
            border=BORDER,
        )
        sidebar_sizer.Add(self._btn_zapisz_pamiec, flag=wx.ALL,                   border=BORDER)

        # ── Prawa kolumna – Obszar roboczy ────────────────────────────
        main_area_sizer = wx.BoxSizer(wx.VERTICAL)

        # Wiersz: pole nazwy pliku + przyciski
        file_row = wx.BoxSizer(wx.HORIZONTAL)
        file_row.Add(
            self._txt_file_name,
            proportion=1,
            flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT,
            border=6,
        )
        file_row.Add(self._btn_load,          flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=4)
        file_row.Add(self._btn_clear_current, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=4)
        file_row.Add(self._btn_hard_reset,    flag=wx.ALIGN_CENTER_VERTICAL)

        main_area_sizer.Add(lbl_main_heading, flag=wx.ALL,                            border=BORDER)
        main_area_sizer.Add(lbl_file,         flag=wx.LEFT | wx.RIGHT | wx.TOP,        border=BORDER)
        main_area_sizer.Add(file_row,         flag=wx.EXPAND | wx.ALL,                 border=BORDER)
        main_area_sizer.Add(
            wx.StaticLine(self),
            flag=wx.EXPAND | wx.LEFT | wx.RIGHT,
            border=BORDER,
        )
        main_area_sizer.Add(self._rb_mode,        flag=wx.EXPAND | wx.ALL,                 border=BORDER)
        main_area_sizer.Add(self._pnl_struktura,  flag=wx.EXPAND | wx.LEFT | wx.RIGHT,     border=BORDER)
        main_area_sizer.Add(
            wx.StaticLine(self),
            flag=wx.EXPAND | wx.LEFT | wx.RIGHT,
            border=BORDER,
        )
        main_area_sizer.Add(lbl_kontekst,         flag=wx.LEFT | wx.RIGHT | wx.TOP,        border=BORDER)
        main_area_sizer.Add(
            self._gauge_kontekst,
            flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP,
            border=BORDER,
        )
        main_area_sizer.Add(
            self._lbl_kontekst_status,
            flag=wx.EXPAND | wx.LEFT | wx.RIGHT,
            border=BORDER,
        )
        main_area_sizer.Add(
            wx.StaticLine(self),
            flag=wx.EXPAND | wx.LEFT | wx.RIGHT,
            border=BORDER,
        )
        main_area_sizer.Add(lbl_full_story,       flag=wx.LEFT | wx.RIGHT | wx.TOP,        border=BORDER)
        main_area_sizer.Add(
            self._txt_full_story,
            proportion=1,
            flag=wx.EXPAND | wx.ALL,
            border=BORDER,
        )
        main_area_sizer.Add(
            wx.StaticLine(self),
            flag=wx.EXPAND | wx.LEFT | wx.RIGHT,
            border=BORDER,
        )
        main_area_sizer.Add(lbl_user_input,   flag=wx.LEFT | wx.RIGHT | wx.TOP,        border=BORDER)
        main_area_sizer.Add(
            self._txt_user_input,
            flag=wx.EXPAND | wx.ALL,
            border=BORDER,
        )
        main_area_sizer.Add(self._btn_wyslij, flag=wx.LEFT | wx.BOTTOM | wx.TOP,       border=BORDER)
        main_area_sizer.Add(
            wx.StaticLine(self),
            flag=wx.EXPAND | wx.LEFT | wx.RIGHT,
            border=BORDER,
        )
        main_area_sizer.Add(self._pnl_postprodukcja, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=BORDER)

        # ── Pionowy separator między kolumnami ────────────────────────
        v_sep = wx.StaticLine(self, style=wx.LI_VERTICAL)

        # ── Dwukolumnowy sizer (sidebar proportion=1 | main proportion=3) ──
        two_col_sizer = wx.BoxSizer(wx.HORIZONTAL)
        two_col_sizer.Add(sidebar_sizer,   proportion=1, flag=wx.EXPAND | wx.ALL,     border=4)
        two_col_sizer.Add(v_sep,                         flag=wx.EXPAND | wx.TOP | wx.BOTTOM,
                          border=8)
        two_col_sizer.Add(main_area_sizer, proportion=3, flag=wx.EXPAND | wx.ALL,     border=4)

        # ── Złożenie pełnego layoutu ──────────────────────────────────
        root_sizer = wx.BoxSizer(wx.VERTICAL)
        root_sizer.Add(top_sizer,     flag=wx.EXPAND)
        root_sizer.Add(two_col_sizer, proportion=1, flag=wx.EXPAND)

        self.SetSizer(root_sizer)

    # ------------------------------------------------------------------
    # Podpięcie zdarzeń
    # ------------------------------------------------------------------
    def _bind_events(self) -> None:
        self._btn_load.Bind(wx.EVT_BUTTON,          self._on_load)
        self._btn_clear_current.Bind(wx.EVT_BUTTON, self._on_clear_current)
        self._btn_hard_reset.Bind(wx.EVT_BUTTON,    self._on_hard_reset)
        self._btn_zapisz_ksiege.Bind(wx.EVT_BUTTON, self._on_zapisz_ksiege)
        self._btn_zapisz_pamiec.Bind(wx.EVT_BUTTON, self._on_zapisz_pamiec)
        self._btn_wyslij.Bind(wx.EVT_BUTTON,        self._on_wyslij)

        # Zmiany w polu nazwy i polu streszczenia wpływają na stan przycisków
        self._txt_file_name.Bind(wx.EVT_TEXT,         self._on_file_name_change)
        self._txt_file_name.Bind(wx.EVT_TEXT_ENTER,   self._on_load)
        self._txt_pamiec.Bind(wx.EVT_TEXT,             self._on_pamiec_change)
        self._txt_user_input.Bind(wx.EVT_TEXT,         self._on_user_input_change)

        # Zmiana trybu wpływa na wymagania przycisku Wyślij
        self._rb_mode.Bind(wx.EVT_RADIOBOX, self._on_mode_change)

        # ── Przyciski Zarządzania Strukturą ───────────────────────────
        self._btn_prolog.Bind(wx.EVT_BUTTON,   self._on_wstaw_prolog)
        self._btn_epilog.Bind(wx.EVT_BUTTON,   self._on_wstaw_epilog)
        self._btn_rozdzial.Bind(wx.EVT_BUTTON, self._on_wstaw_rozdzial)
        self._btn_akt.Bind(wx.EVT_BUTTON,      self._on_wstaw_akt)
        self._btn_scena.Bind(wx.EVT_BUTTON,    self._on_wstaw_scena)

        # ── Postprodukcja ─────────────────────────────────────────────
        self._btn_tytuly_ai.Bind(wx.EVT_BUTTON, self._on_tytuly_ai)

    # ------------------------------------------------------------------
    # Odświeżanie stanu przycisków (Enable/Disable)
    # ------------------------------------------------------------------
    def _refresh_ui_state(self) -> None:
        """Aktualizuje stan Enabled/Disabled przycisków na podstawie stanu pamięci.

        Na końcu zawsze wywołuje self.Layout(), by okno poprawnie przeliczyło
        rozmiary po ewentualnym ukryciu lub pokazaniu paneli struktury i postprodukcji.
        """
        pamiec_zajeta = bool(self.full_story.strip() or self.summary_text.strip())
        pamiec_pusta  = not pamiec_zajeta
        nazwa_podana  = bool(self._txt_file_name.GetValue().strip())
        streszczenie_wpisane = bool(self._txt_pamiec.GetValue().strip())
        user_text_present    = bool(self._txt_user_input.GetValue().strip())
        tryb_idx    = self._rb_mode.GetSelection()   # 0=BM, 1=Skrypt, 2=Audiobook
        tryb_zapisu = tryb_idx in (1, 2)

        # ── Pole nazwy pliku: zablokowane gdy pamięć zajęta ──────────
        self._txt_file_name.Enable(not pamiec_zajeta)

        # ── Wczytaj: tylko gdy pamięć pusta I nazwa podana ───────────
        self._btn_load.Enable(pamiec_pusta and nazwa_podana)

        # ── Wyczyść bieżącą: tylko gdy pamięć bieżąca zajęta ─────────
        self._btn_clear_current.Enable(pamiec_zajeta)

        # ── Twardy Reset: aktywny gdy cokolwiek w pamięci / polach ───
        cos_do_wyczyszczenia = pamiec_zajeta or bool(
            self._txt_file_name.GetValue().strip()
            or self._txt_ksiega_swiata.GetValue().strip()
            or self._txt_pamiec.GetValue().strip()
        )
        self._btn_hard_reset.Enable(cos_do_wyczyszczenia)

        # ── Zapisz Księgę: wymaga nazwy pliku ────────────────────────
        self._btn_zapisz_ksiege.Enable(nazwa_podana)

        # ── Zapisz Streszczenie: wymaga nazwy i treści ────────────────
        self._btn_zapisz_pamiec.Enable(nazwa_podana and streszczenie_wpisane)

        # ── Wyślij do AI ──────────────────────────────────────────────
        # Sprawdź czy po nagłówku Epilogu jest już treść (zakończona historia)
        _epilog_ref   = re.search(r'(?i)\bepilog\b', self.full_story)
        _epilog_ma_tresc = (
            _epilog_ref is not None
            and len(self.full_story[_epilog_ref.end():].strip()) > 0
        )

        if not self._api_dostepne:
            self._btn_wyslij.Disable()
        elif tryb_zapisu and not nazwa_podana:
            self._btn_wyslij.Disable()
        elif tryb_zapisu and _epilog_ma_tresc:
            self._btn_wyslij.Disable()
        elif not user_text_present:
            self._btn_wyslij.Disable()
        else:
            self._btn_wyslij.Enable()

        # ══════════════════════════════════════════════════════════════
        # DYNAMICZNA WIDOCZNOŚĆ – Panel Zarządzania Strukturą
        # ══════════════════════════════════════════════════════════════

        # Oblicz wspólne warunki dla przycisków struktury
        _prolog_juz_jest  = bool(re.search(r'(?i)\bprolog\b',  self.full_story))
        _epilog_juz_jest  = bool(re.search(r'(?i)\bepilog\b',  self.full_story))
        _historia_niepusta = bool(self.full_story.strip())

        _ostatnia_linia = ""
        for _linia in reversed(self.full_story.splitlines()):
            if _linia.strip():
                _ostatnia_linia = _linia.strip()
                break

        _konczy_sie_naglowkiem = bool(
            re.match(
                r'(?i)^(rozdzia[łl]\s+\d+|akt\s+\d+|scena\s+\d+|prolog|epilog)\s*$',
                _ostatnia_linia,
            )
        ) if _ostatnia_linia else False
        _blokada = _konczy_sie_naglowkiem or _epilog_juz_jest

        if tryb_idx == 0:
            # Tryb Burza Mózgów – ukryj cały panel struktury
            self._pnl_struktura.Hide()
        else:
            # Tryb Skrypt (1) lub Audiobook (2) – pokaż panel
            self._pnl_struktura.Show()

            # Widoczność przycisków wewnątrz panelu (zależna od trybu)
            jest_skrypt   = (tryb_idx == 1)
            jest_audiobok = (tryb_idx == 2)

            self._btn_rozdzial.Show(jest_audiobok)
            self._btn_akt.Show(jest_skrypt)
            self._btn_scena.Show(jest_skrypt)

            # Dynamiczne etykiety z aktualnymi licznikami
            self._btn_rozdzial.SetLabel(
                f"✂️ Wstaw cięcie (Rozdział {self.chapter_counter})"
            )
            self._btn_akt.SetLabel(f"🎭 Wstaw Akt {self.akt_counter}")
            self._btn_scena.SetLabel(f"🎬 Wstaw Scenę {self.scena_counter}")

            # Stany Enable/Disable
            self._btn_prolog.Enable(
                nazwa_podana and not _historia_niepusta and not _prolog_juz_jest
            )
            # Epilog dostępny tylko gdy: jest nazwa, historia NIE jest pusta,
            # i ostatnia linia NIE jest nagłówkiem (jest treść po ostatnim nagłówku).
            self._btn_epilog.Enable(
                nazwa_podana and _historia_niepusta and not _blokada
            )
            self._btn_rozdzial.Enable(nazwa_podana and not _blokada)
            self._btn_akt.Enable(nazwa_podana and not _blokada)
            self._btn_scena.Enable(nazwa_podana and not _blokada)

            # Przelicz sizer wewnątrz panelu po zmianie widoczności przycisków
            self._pnl_struktura.Layout()

        # Ochrona przed przypadkową zmianą trybu twórczego (test12):
        # gdy pamięć jest zajęta (pełna historia LUB streszczenie) w trybie
        # Skrypt (1) lub Audiobook (2), blokuj przełączenie na drugi tryb zapisu.
        # Burza Mózgów (0) zawsze dostępna.
        self._rb_mode.EnableItem(0, True)
        if pamiec_zajeta and tryb_idx == 1:
            self._rb_mode.EnableItem(1, True)
            self._rb_mode.EnableItem(2, False)
        elif pamiec_zajeta and tryb_idx == 2:
            self._rb_mode.EnableItem(1, False)
            self._rb_mode.EnableItem(2, True)
        else:
            self._rb_mode.EnableItem(1, True)
            self._rb_mode.EnableItem(2, True)

        # ══════════════════════════════════════════════════════════════
        # DYNAMICZNA WIDOCZNOŚĆ – Panel Postprodukcji
        # ══════════════════════════════════════════════════════════════
        if tryb_idx == 2:
            # Tryb Audiobook – pokaż panel postprodukcji
            self._pnl_postprodukcja.Show()
            # Przycisk aktywny gdy: API działa + projekt ma nazwę + historia niepusta
            self._btn_tytuly_ai.Enable(
                self._api_dostepne and nazwa_podana and _historia_niepusta
            )
        else:
            self._pnl_postprodukcja.Hide()

        # ── Wskaźnik pamięci modelu AI ────────────────────────────────
        self._aktualizuj_pamiec_modelu()

        # ── Przelicz layout okna po zmianie widoczności paneli ────────
        self.Layout()

    # ------------------------------------------------------------------
    # Handlery zmian w polach tekstowych (odświeżają przyciski)
    # ------------------------------------------------------------------
    def _on_file_name_change(self, _event: wx.Event) -> None:
        self._refresh_ui_state()

    def _on_pamiec_change(self, _event: wx.Event) -> None:
        self._refresh_ui_state()

    def _on_user_input_change(self, _event: wx.Event) -> None:
        self._refresh_ui_state()

    def _on_mode_change(self, _event: wx.Event) -> None:
        self._refresh_ui_state()

    # ------------------------------------------------------------------
    # Wczytywanie historii z pliku
    # ------------------------------------------------------------------
    def _on_load(self, _event: wx.Event) -> None:
        """Wczytuje istniejący plik projektu z folderu skrypty/."""
        nazwa = self._txt_file_name.GetValue().strip()
        if not nazwa:
            wx.MessageBox(
                "Podaj nazwę pliku projektu przed wczytaniem.",
                "Brak nazwy",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            self._txt_file_name.SetFocus()
            return

        app_dir      = os.path.dirname(os.path.abspath(__file__))
        skrypty      = os.path.join(app_dir, self.SKRYPTY_DIR)
        filepath     = os.path.join(skrypty, f"{nazwa}.txt")
        summary_path = os.path.join(skrypty, f"{nazwa}_streszczenie.txt")
        lore_path    = os.path.join(skrypty, f"{nazwa}.md")

        if not os.path.exists(filepath):
            wx.MessageBox(
                f"Nie znaleziono pliku:\n{filepath}\n\n"
                "Jeśli zaczynasz nową historię — po prostu zacznij pisać.\n"
                "Plik zostanie utworzony automatycznie przy pierwszym wysłaniu do AI.",
                "Plik nie istnieje",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            return

        try:
            with open(filepath, "r", encoding="utf-8") as fh:
                content = fh.read()
        except Exception as exc:
            wx.MessageBox(
                f"Błąd odczytu pliku:\n{exc}",
                "Błąd odczytu",
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return

        # Analiza struktury pliku → ustawienie liczników
        chapter_nums  = [int(m) for m in re.findall(r"(?i)\brozdzia[łl]\s+(\d+)", content)]
        akt_nums      = [int(m) for m in re.findall(r"(?i)\bakt\s+(\d+)", content)]
        ostatni_split = re.split(r"(?i)\bakt\s+\d+", content)
        ostatni_frag  = ostatni_split[-1] if ostatni_split else content
        scena_nums    = [int(m) for m in re.findall(r"(?i)\bscena\s+(\d+)", ostatni_frag)]

        self.chapter_counter = (max(chapter_nums) + 1) if chapter_nums else 1
        self.akt_counter     = (max(akt_nums)     + 1) if akt_nums     else 1
        self.scena_counter   = (max(scena_nums)   + 1) if scena_nums   else 1

        # Wczytaj Księgę Świata dla projektu (jeśli istnieje)
        if os.path.exists(lore_path):
            try:
                with open(lore_path, "r", encoding="utf-8") as fh:
                    self.world_lore = fh.read()
                self._txt_ksiega_swiata.SetValue(self.world_lore)
            except Exception:
                pass

        # Logika Nieskończonej Pamięci: streszczenie priorytet > pełna historia
        if os.path.exists(summary_path):
            try:
                with open(summary_path, "r", encoding="utf-8") as fh:
                    self.summary_text = fh.read()
                self._txt_pamiec.SetValue(self.summary_text)
            except Exception:
                pass
            self.full_story = ""
            lore_info = f" Wczytano też Księgę: skrypty/{nazwa}.md." if os.path.exists(lore_path) else ""
            status_msg = (
                f"Wczytano streszczenie projektu '{nazwa}'.{lore_info}\n"
                "Pamięć bieżąca pozostaje pusta (tryb Nieskończonej Pamięci).\n"
                "Możesz kontynuować historię — AI operuje na streszczeniu."
            )
        else:
            self.full_story = content
            self.summary_text = ""
            lore_info = f" Wczytano też Księgę: skrypty/{nazwa}.md." if os.path.exists(lore_path) else ""
            status_msg = (
                f"Wczytano historię '{nazwa}' ({len(content)} znaków).{lore_info}"
            )

        # Wczytaj tryb twórczy z pliku .mode (jeśli istnieje) i ustaw RadioBox
        # Pliki metadanych .mode trzymane w runtime/skrypty/ (ukryte przed end-userami)
        mode_path = os.path.join(app_dir, "runtime", self.SKRYPTY_DIR, f"{nazwa}.mode")
        if os.path.exists(mode_path):
            try:
                with open(mode_path, "r", encoding="utf-8") as fh:
                    saved_mode = int(fh.read().strip())
                if saved_mode in (1, 2):
                    self._rb_mode.SetSelection(saved_mode)
            except Exception:
                pass  # Cichy fail – plik .mode nie jest krytyczny

        self.zapisana_nazwa_pliku = nazwa
        self._txt_full_story.SetValue(self.full_story)
        self._refresh_ui_state()
        wx.MessageBox(status_msg, "Wczytano projekt", wx.OK | wx.ICON_INFORMATION, self)

    # ------------------------------------------------------------------
    # Czyszczenie pamięci bieżącej (streszczenie i Księga zostają)
    # ------------------------------------------------------------------
    def _on_clear_current(self, _event: wx.Event) -> None:
        """Czyści WYŁĄCZNIE bieżącą fabułę (full_story) i ostatnią odpowiedź AI.

        Zachowane: liczniki rozdziałów/aktów/scen, nazwa pliku, Księga Świata,
        Streszczenie (Pamięć Długotrwała), zapamiętany tryb twórczy.
        Dzięki temu użytkownik może kontynuować projekt od razu po wyczyszczeniu.
        """
        self.full_story    = ""
        self.last_response = ""
        # NIE zmieniamy: chapter_counter, akt_counter, scena_counter,
        # zapisana_nazwa_pliku, world_lore, summary_text

        self._txt_full_story.SetValue("")

        self._refresh_ui_state()
        komunikat = "Pamięć bieżąca wyczyszczona."
        if self.summary_text.strip():
            komunikat += "\nStreszczenie w Pamięci Długotrwałej zostało zachowane."
        wx.MessageBox(komunikat, "Pamięć wyczyszczona", wx.OK | wx.ICON_INFORMATION, self)

    # ------------------------------------------------------------------
    # Twardy Reset – całkowite zamknięcie projektu
    # ------------------------------------------------------------------
    def _on_hard_reset(self, _event: wx.Event) -> None:
        """Całkowicie czyści projekt: historia, streszczenie, Księga Świata i liczniki."""
        odp = wx.MessageBox(
            "Czy na pewno chcesz zamknąć projekt?\n\n"
            "Zostanie wyczyszczone:\n"
            "  • historia bieżąca\n"
            "  • streszczenie (Pamięć Długotrwała)\n"
            "  • Księga Świata\n"
            "  • wszystkie liczniki (rozdziały, akty, sceny)\n\n"
            "Pliki na dysku NIE zostaną usunięte.",
            "Zamknij Projekt – Twardy Reset",
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING,
            self,
        )
        if odp != wx.YES:
            return

        # Wyzeruj cały stan pamięci
        self.full_story           = ""
        self.summary_text         = ""
        self.world_lore           = ""
        self.chapter_counter      = 1
        self.akt_counter          = 1
        self.scena_counter        = 1
        self.zapisana_nazwa_pliku = ""
        self.last_response        = ""

        # Wyczyść wszystkie kontrolki UI
        self._txt_file_name.SetValue("")
        self._txt_file_name.Enable()
        self._txt_full_story.SetValue("")
        self._txt_ksiega_swiata.SetValue("")
        self._txt_pamiec.SetValue("")
        self._txt_user_input.SetValue("")

        self._refresh_ui_state()
        wx.MessageBox(
            "Projekt zamknięty. Wszystkie dane w pamięci zostały wyczyszczone.",
            "Projekt zamknięty",
            wx.OK | wx.ICON_INFORMATION,
            self,
        )
        self._txt_file_name.SetFocus()

    # ------------------------------------------------------------------
    # Zapis Księgi Świata
    # ------------------------------------------------------------------
    def _on_zapisz_ksiege(self, _event: wx.Event) -> None:
        """Zapisuje Księgę Świata do pliku skrypty/<nazwa>.md."""
        nazwa = self._txt_file_name.GetValue().strip()
        if not nazwa:
            wx.MessageBox(
                "Podaj najpierw nazwę pliku projektu w polu nazwy.",
                "Brak nazwy pliku",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            self._txt_file_name.SetFocus()
            return

        tresc = self._txt_ksiega_swiata.GetValue().strip()
        if not tresc:
            wx.MessageBox(
                "Księga Świata jest pusta. Nic do zapisania.",
                "Pusta Księga Świata",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            self._txt_ksiega_swiata.SetFocus()
            return

        app_dir   = os.path.dirname(os.path.abspath(__file__))
        skrypty   = os.path.join(app_dir, self.SKRYPTY_DIR)
        os.makedirs(skrypty, exist_ok=True)
        lore_path = os.path.join(skrypty, f"{nazwa}.md")

        try:
            with open(lore_path, "w", encoding="utf-8") as fh:
                fh.write(tresc)
            self.world_lore = tresc
            wx.MessageBox(
                f"Księga Świata zapisana: skrypty/{nazwa}.md",
                "Księga zapisana",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
        except Exception as exc:
            wx.MessageBox(
                f"Błąd zapisu Księgi Świata:\n{exc}",
                "Błąd zapisu",
                wx.OK | wx.ICON_ERROR,
                self,
            )

    # ------------------------------------------------------------------
    # Zapis Streszczenia (Pamięci Długotrwałej)
    # ------------------------------------------------------------------
    def _on_zapisz_pamiec(self, _event: wx.Event) -> None:
        """Zapisuje streszczenie do pliku skrypty/<nazwa>_streszczenie.txt."""
        nazwa = self._txt_file_name.GetValue().strip()
        if not nazwa:
            wx.MessageBox(
                "Podaj najpierw nazwę pliku projektu w polu nazwy.",
                "Brak nazwy pliku",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            self._txt_file_name.SetFocus()
            return

        tresc = self._txt_pamiec.GetValue().strip()
        if not tresc:
            wx.MessageBox(
                "Pamięć Długotrwała jest pusta. Nic do zapisania.",
                "Puste streszczenie",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            self._txt_pamiec.SetFocus()
            return

        app_dir      = os.path.dirname(os.path.abspath(__file__))
        skrypty      = os.path.join(app_dir, self.SKRYPTY_DIR)
        os.makedirs(skrypty, exist_ok=True)
        summary_path = os.path.join(skrypty, f"{nazwa}_streszczenie.txt")

        try:
            with open(summary_path, "w", encoding="utf-8") as fh:
                fh.write(tresc)
            self.summary_text = tresc
            wx.MessageBox(
                f"Streszczenie zapisane: skrypty/{nazwa}_streszczenie.txt\n\n"
                "Możesz teraz bezpiecznie wyczyścić pamięć bieżącą.",
                "Streszczenie zapisane",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
        except Exception as exc:
            wx.MessageBox(
                f"Błąd zapisu streszczenia:\n{exc}",
                "Błąd zapisu",
                wx.OK | wx.ICON_ERROR,
                self,
            )

    # ------------------------------------------------------------------
    # Wysyłanie do AI (stub – logika OpenAI w kolejnym etapie)
    # ------------------------------------------------------------------
    def _on_wyslij(self, _event: wx.Event) -> None:
        """
        Obsługuje przycisk 'Wyślij do AI'.

        Aktualny etap: walidacja danych wejściowych + stub odpowiedzi.
        Pełna implementacja wywołań OpenAI gpt-4o (w wątku tła
        z wx.CallAfter) zostanie dodana w kolejnym etapie pracy.
        """
        if not self._api_dostepne:
            wx.MessageBox(
                "Brak połączenia z OpenAI.\n"
                "Sprawdź plik golden_key.env i uruchom aplikację ponownie.",
                "Brak API",
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return

        user_text = self._txt_user_input.GetValue().strip()
        if not user_text:
            wx.MessageBox(
                "Wpisz instrukcje dla AI przed wysłaniem.",
                "Puste pole",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            self._txt_user_input.SetFocus()
            return

        nazwa      = self._txt_file_name.GetValue().strip()
        tryb_idx   = self._rb_mode.GetSelection()
        tryb_zapisu = tryb_idx in (1, 2)  # Skrypt lub Audiobook

        if tryb_zapisu and not nazwa:
            wx.MessageBox(
                "Podaj nazwę pliku projektu, zanim wygenerujesz tekst do zapisu.\n"
                "(Tryb Skryptu i Audiobooka wymagają nazwy.)",
                "Brak nazwy pliku",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            self._txt_file_name.SetFocus()
            return

        world_context = self._txt_ksiega_swiata.GetValue().strip()
        if not world_context:
            wx.MessageBox(
                "Uzupełnij Księgę Świata przed wysłaniem zapytania do AI.\n"
                "Zasady świata i postacie są wymagane przez model.",
                "Brak Księgi Świata",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            self._txt_ksiega_swiata.SetFocus()
            return

        # Ochrona przed generowaniem streszczenia w trybie zapisu do pliku
        slowa_kluczowe = ["streszcz", "streść", "podsumuj", "podsumowanie"]
        if tryb_zapisu and any(s in user_text.lower() for s in slowa_kluczowe):
            wx.MessageBox(
                "Próbujesz wygenerować streszczenie w trybie zapisu do pliku!\n"
                "To mogłoby uszkodzić Twoją historię.\n\n"
                "Przełącz się na tryb 'Burza Mózgów' i spróbuj ponownie.",
                "Błąd trybu",
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return

        # Zablokuj przycisk, wyczyść pole instrukcji, przekaż snapshot stanu do wątku
        self._btn_wyslij.Disable()
        self._txt_user_input.SetValue("")

        # Snapshot stanu pamięci – bezpieczne przekazanie do wątku tła (GIL-safe)
        full_story_snap = self.full_story
        summary_snap    = self.summary_text

        self._refresh_ui_state()

        t = threading.Thread(
            target=self._wyslij_worker,
            args=(user_text, nazwa, tryb_idx, tryb_zapisu, world_context,
                  full_story_snap, summary_snap),
            daemon=True,
        )
        self._worker_thread = t
        t.start()

    # ------------------------------------------------------------------
    # Pomocnicza metoda zapisu do pliku projektu
    # ------------------------------------------------------------------
    def _dopisz_do_pliku(self, nazwa: str, content: str, mode: str = "a") -> None:
        """Zapisuje tekst do pliku skrypty/<nazwa>.txt.

        Args:
            nazwa:   Nazwa projektu bez rozszerzenia.
            content: Treść do zapisania.
            mode:    Tryb otwarcia pliku: ``"a"`` (dopisz, domyślnie) lub
                     ``"w"`` (nadpisz). Prolog używa ``"w"``, aby mieć pewność,
                     że plik zaczyna się czysto, bez artefaktów z poprzednich sesji.
        """
        app_dir  = os.path.dirname(os.path.abspath(__file__))
        skrypty  = os.path.join(app_dir, self.SKRYPTY_DIR)
        os.makedirs(skrypty, exist_ok=True)
        filepath = os.path.join(skrypty, f"{nazwa}.txt")
        try:
            with open(filepath, mode, encoding="utf-8") as fh:
                fh.write(content)
        except Exception as exc:
            wx.MessageBox(
                f"Błąd zapisu do pliku:\n{exc}",
                "Błąd zapisu",
                wx.OK | wx.ICON_ERROR,
                self,
            )

    # ------------------------------------------------------------------
    # Silnik fonetyczny (integracja z gui_poliglota)
    # ------------------------------------------------------------------
    def zastosuj_akcenty_uniwersalne(self, tekst: str, lore_text: str) -> str:
        """Aplikuje akcenty fonetyczne z Księgi Świata na tekst skryptu.

        Parsuje Księgę Świata w poszukiwaniu bloków [Postać: akcent X],
        a następnie stosuje odpowiednią funkcję z gui_poliglota na każdym
        fragmencie tekstu wypowiadanym przez tę postać (między tagami).
        """
        # 1. Wyciąganie mapowania postaci → akcent z Księgi Świata
        akcenty_map: dict[str, dict] = {}
        postacie_bloki = re.split(r"\[([^:\]\-]+).*?\]", lore_text)

        for i in range(1, len(postacie_bloki), 2):
            imie = postacie_bloki[i].strip().lower()
            opis = postacie_bloki[i + 1].lower() if i + 1 < len(postacie_bloki) else ""

            akcent_match = re.search(
                r"akcent\s+([a-zńśźżćłó]+)|([a-zńśźżćłó]+)\s+akcent", opis
            )
            nazwa_akcentu = (
                (akcent_match.group(1) or akcent_match.group(2))
                if akcent_match
                else None
            )
            reguly_lore = re.findall(
                r"[\"']([a-ząćęłńóśźż])[\"']\s+na\s+[\"']([a-ząćęłńóśźż])[\"']",
                opis,
                re.IGNORECASE,
            )
            if nazwa_akcentu or reguly_lore:
                akcenty_map[imie] = {"nazwa": nazwa_akcentu, "reguly": reguly_lore}

        if not akcenty_map:
            return tekst

        # Pomocnicza: usuwa polskie znaki z nazwy akcentu (na potrzeby klucza mapy)
        def _usun_pl(nazwa: str) -> str:
            for k, v in {
                "ą": "a", "ę": "e", "ł": "l", "ó": "o",
                "ś": "s", "ć": "c", "ń": "n", "ż": "z", "ź": "z",
            }.items():
                nazwa = nazwa.replace(k, v)
            return nazwa.strip()

        # Mapa: znormalizowana nazwa akcentu → funkcja fonetyczna z gui_poliglota
        _AKCENT_FUNCS = {
            "islandzki":  akcent_islandzki,
            "wloski":     akcent_wloski,
            "finski":     akcent_finski,
            "angielski":  akcent_angielski,
            "francuski":  akcent_francuski,
            "niemiecki":  akcent_niemiecki,
            "hiszpanski": akcent_hiszpanski,
        }

        # 2. Podział skryptu po tagach i aplikacja akcentów
        fragmenty = re.split(r"(\[[^\]]+\])", tekst)
        nowe_fragmenty: list[str] = []
        current_speaker: str | None = None

        for frag in fragmenty:
            if frag.startswith("[") and frag.endswith("]"):
                nowe_fragmenty.append(frag)
                m = re.match(r"^\[([^:\]\-]+)", frag)
                current_speaker = m.group(1).strip().lower() if m else None
            else:
                dialog = frag
                if current_speaker and dialog.strip():
                    dopasowane_dane = next(
                        (d for k, d in akcenty_map.items()
                         if k in current_speaker or current_speaker in k),
                        None,
                    )
                    if dopasowane_dane:
                        zmodyfikowano = False
                        if dopasowane_dane["nazwa"]:
                            znorm = _usun_pl(dopasowane_dane["nazwa"])
                            fn = _AKCENT_FUNCS.get(znorm)
                            if fn:
                                dialog = fn(dialog)
                                zmodyfikowano = True
                        if not zmodyfikowano and dopasowane_dane["reguly"]:
                            for z, na in dopasowane_dane["reguly"]:
                                dialog = (
                                    dialog
                                    .replace(z.lower(), na.lower())
                                    .replace(z.upper(), na.upper())
                                )
                nowe_fragmenty.append(dialog)

        return "".join(nowe_fragmenty)

    # ------------------------------------------------------------------
    # Wyświetlanie błędów AI (krótkie → MessageBox; długie → dialog)
    # ------------------------------------------------------------------
    def _wyswietl_blad_ai(self, tresc_bledu: str, custom_msg: str | None = None) -> None:
        """Wyświetla błąd AI – krótki przez MessageBox, długi przez dialog z polem do skopiowania.

        Args:
            tresc_bledu:  Treść błędu (string wyjątku lub długi komunikat).
            custom_msg:   Opcjonalny nagłówek / krótki opis kontekstu błędu.
                          Odpowiednik ``custom_msg`` z wyswietl_blad_ai() w Streamlicie.
        """
        msg_header  = custom_msg or "Wystąpił nieoczekiwany błąd podczas przetwarzania."
        jest_krotki = len(tresc_bledu) <= 200 and "\n" not in tresc_bledu

        if jest_krotki:
            pelna_tresc = f"{msg_header}\n\n{tresc_bledu}" if custom_msg else tresc_bledu
            wx.MessageBox(pelna_tresc, "Błąd AI", wx.OK | wx.ICON_ERROR, self)
        else:
            dlg = wx.Dialog(self, title="Błąd AI – Szczegóły techniczne", size=(640, 400))
            sizer = wx.BoxSizer(wx.VERTICAL)
            lbl_head = wx.StaticText(dlg, label=msg_header)
            lbl_copy = wx.StaticText(
                dlg,
                label="Treść błędu (zaznacz Ctrl+A, skopiuj Ctrl+C – do zgłoszenia):",
            )
            txt = wx.TextCtrl(
                dlg,
                value=tresc_bledu,
                style=wx.TE_MULTILINE | wx.TE_READONLY,
                name="Treść błędu do skopiowania",
            )
            btn_ok = wx.Button(dlg, wx.ID_OK, label="Zamknij")
            sizer.Add(lbl_head, flag=wx.ALL,                                       border=8)
            sizer.Add(lbl_copy, flag=wx.LEFT | wx.RIGHT | wx.BOTTOM,               border=8)
            sizer.Add(txt,      proportion=1, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=8)
            sizer.Add(btn_ok,   flag=wx.ALL | wx.ALIGN_RIGHT,                      border=8)
            dlg.SetSizer(sizer)
            txt.SetFocus()
            dlg.ShowModal()
            dlg.Destroy()

    # ------------------------------------------------------------------
    # Aktualizacja wskaźnika przepełnienia okna kontekstowego AI
    # ------------------------------------------------------------------
    def _aktualizuj_pamiec_modelu(self) -> None:
        """Odświeża wskaźnik pamięci modelu (kontekst okna AI) na podstawie full_story.

        Odpowiednik funkcji aktualizuj_pasek_postepu() z 1_Rezyseria.py (Streamlit).
        Wywoływana automatycznie przez _refresh_ui_state() przy każdej zmianie stanu.
        """
        LIMIT   = 200_000
        ALARM   = 175_000
        OSTRZEZ = 150_000
        total   = len(self.full_story)

        if total == 0:
            pct    = 0
            msg    = "🟢 Pamięć czysta. Maszyna gotowa na nową historię."
            colour = wx.Colour(0, 128, 0)
        elif total >= ALARM:
            pct    = min(int(total / LIMIT * 100), 100)
            msg    = (
                f"🚨 KRYTYCZNE PRZEŁADOWANIE: Zużyto {total} z {LIMIT} znaków.\n"
                "JAK KONTYNUOWAĆ: W Burzy Mózgów wpisz 'streszczenie', kliknij "
                "'Zapisz Streszczenie', potem 'Wyczyść bieżącą (zostaw Streszczenie)'."
            )
            colour = wx.Colour(180, 0, 0)
        elif total >= OSTRZEZ:
            pct    = int(total / LIMIT * 100)
            msg    = (
                f"⚠️ STAN OSTRZEGAWCZY: Zużyto {total} z {LIMIT} znaków. "
                "Pamięć się zapełnia – wkrótce konieczne będzie wygenerowanie streszczenia."
            )
            colour = wx.Colour(180, 100, 0)
        else:
            pct    = int(total / LIMIT * 100)
            msg    = f"🟢 Zużycie pamięci: {total} / {LIMIT} znaków. Bezpieczny bufor."
            colour = wx.Colour(0, 128, 0)

        self._gauge_kontekst.SetValue(pct)
        self._lbl_kontekst_status.SetValue(msg)
        self._lbl_kontekst_status.SetForegroundColour(colour)

    # ------------------------------------------------------------------
    # Wątek tła – główna logika AI  (ŻADNYCH wx.* bezpośrednio!)
    # ------------------------------------------------------------------
    def _wyslij_worker(
        self,
        user_text: str,
        nazwa: str,
        tryb_idx: int,
        tryb_zapisu: bool,
        world_context: str,
        full_story: str,
        summary_text: str,
    ) -> None:
        """Buduje payload, wywołuje OpenAI gpt-4o i przekazuje wyniki przez wx.CallAfter.

        Parametry ``full_story`` i ``summary_text`` to migawki stanu
        przekazane przed uruchomieniem wątku – bezpieczne wobec GIL.
        Wszelka modyfikacja UI odbywa się WYŁĄCZNIE przez wx.CallAfter.
        """
        _total_chars = len(full_story)
        _OSTRZEZENIE = 150_000
        _ALARM       = 175_000
        slowa_kluczowe = ["streszcz", "streść", "podsumuj", "podsumowanie"]

        # ── Budowanie aktywnego system promptu ────────────────────────
        if tryb_idx == 0:  # Burza Mózgów
            active_prompt = self.PROMPT_BURZA_BASE.format(world_context=world_context)
            if any(s in user_text.lower() for s in slowa_kluczowe):
                active_prompt += (
                    "\n\n[TRYB WYMUSZONEGO STRESZCZENIA]: Użytkownik ręcznie zażądał "
                    "zapisania stanu fabuły! Zanim wygenerujesz Opcje, MUSISZ na samej "
                    "górze wygenerować streszczenie zamknięte w tagach "
                    "<STRESZCZENIE> tutaj tekst </STRESZCZENIE>. "
                    "Streszczenie musi zawierać TRZY obowiązkowe elementy:\n"
                    "1. Zwięzłe podsumowanie dotychczasowych wydarzeń.\n"
                    "2. Sekcję [OSTATNIA SCENA]: dokładna kopia (słowo w słowo) ostatnich "
                    "2-3 akapitów przesłanego tekstu.\n"
                    "3. Sekcję [STYL I TON]: jednozdaniowa notatka o klimacie narracji."
                )
            elif _total_chars < _OSTRZEZENIE:
                active_prompt += (
                    "\n\n[TRYB OPTYMALIZACJI]: Pamięć jest pojemna. NIE GENERUJ żadnego "
                    "streszczenia dotychczasowej fabuły. Przejdź od razu do generowania "
                    "3 Opcji i promptów."
                )
            else:
                active_prompt += (
                    "\n\n[TRYB ALARMOWY - ZBLIŻA SIĘ KONIEC PAMIĘCI]: Pamięć jest prawie "
                    "pełna! Zanim wygenerujesz Opcje, MUSISZ na samej górze wygenerować "
                    "streszczenie zamknięte w tagach "
                    "<STRESZCZENIE> tutaj tekst </STRESZCZENIE>. "
                    "Streszczenie musi zawierać TRZY obowiązkowe elementy:\n"
                    "1. Zwięzłe podsumowanie dotychczasowych wydarzeń.\n"
                    "2. Sekcję [OSTATNIA SCENA]: dokładna kopia (słowo w słowo) ostatnich "
                    "2-3 akapitów przesłanego tekstu.\n"
                    "3. Sekcję [STYL I TON]: jednozdaniowa notatka o klimacie narracji."
                )

        elif tryb_idx == 1:  # Skrypt
            active_prompt = self.PROMPT_SKRYPT.format(world_context=world_context)
            if not full_story.strip() or "[" not in full_story:
                active_prompt += (
                    "\n\n[TRYB STARTOWY - PUSTA PAMIĘĆ]: Zaczynasz zupełnie nową historię!\n"
                    "1. AUDIO-EKSPOZYCJA (KRYTYCZNE): Ponieważ brak narratora, MUSISZ "
                    "zbudować kontekst akcją. Scena nie może dziać się w próżni. Rozpocznij "
                    "od wejścia postaci w przestrzeń.\n"
                    "2. EKSPOZYCJA W DIALOGU: Postacie w pierwszych kwestiach muszą w "
                    "naturalny sposób zdradzić, GDZIE są i KIM dla siebie są.\n"
                    "3. ZAKAZ JASNOWIDZENIA: Komentowanie czyjegoś głosu dopiero po jego "
                    "usłyszeniu."
                )
            else:
                active_prompt += (
                    "\n\n[TRYB KONTYNUACJI]: Kontynuujesz trwającą scenę. Utrzymaj naturalną "
                    "płynność akcji i napięcie. Zamiast narratora, regularnie wplataj opisy "
                    "przestrzeni i ruchu postaci za pomocą surowych tagów [SFX: ...] "
                    "pomiędzy dialogami."
                )

        else:  # Audiobook (tryb_idx == 2)
            active_prompt = self.PROMPT_AUDIOBOOK.format(world_context=world_context)

        # ── Budowanie payload_messages ────────────────────────────────
        payload_messages: list[dict] = [
            {"role": "system", "content": active_prompt},
        ]
        if summary_text.strip():
            payload_messages.append({
                "role": "assistant",
                "content": f"[STRESZCZENIE POPRZEDNICH WYDARZEŃ]:\n{summary_text}",
            })
        if full_story.strip():
            payload_messages.append({
                "role": "assistant",
                "content": f"[OBECNA FABUŁA]:\n{full_story}",
            })

        # ── PRZYPOMNIENIE KRYTYCZNE doczepiane do instrukcji użytkownika ─
        user_content = user_text
        if tryb_idx == 1:
            user_content += (
                "\n\n(PRZYPOMNIENIE KRYTYCZNE: Tryb AUDIO-PLAY/FOLEY. Używaj TYLKO tagów "
                "[SFX: ...] oraz [Postać: ...]. ZERO NARRATORA! Tagi SFX: max 10 słów, "
                "czysta akustyka. ZABRONIONE jest rozwiązywanie problemów na końcu tekstu! "
                "Zastosuj BRUTALNY ANTI-CLOSURE: urwij scenę w ułamku sekundy, gdy dzieje "
                "się coś złego. Żadnych szczęśliwych zakończeń ani podsumowań na koniec!)"
            )
        elif tryb_idx == 2:
            user_content += (
                "\n\n(PRZYPOMNIENIE KRYTYCZNE: Tryb KSIĄŻKI. Zero tagów audio/głosowych. "
                "Długa, gęsta proza z dialogami po myślnikach. Zakaz Markdownu i nagłówków. "
                "BRUTALNY ANTI-CLOSURE: urwij tekst w środku napięcia lub w połowie akcji, "
                "chyba że to wyraźny finał historii.)"
            )
        else:  # Burza Mózgów
            user_content += (
                "\n\n(PRZYPOMNIENIE KRYTYCZNE: Generujesz tylko 3 opcje + prompty. Opcje "
                "logiczne i uziemione. Komplikuj fabułę, CHYBA ŻE użytkownik wyraźnie prosi "
                "o Epilog lub zakończenie – wtedy ładnie domknij historię. Opcje NIE MOGĄ "
                "kończyć się pełnym sukcesem bez konsekwencji!)"
            )
        payload_messages.append({"role": "user", "content": user_content})

        # ── Wywołanie OpenAI API ──────────────────────────────────────
        try:
            response = self._client.chat.completions.create(
                model="gpt-4o",
                messages=payload_messages,
                temperature=0.85,
            )
            response_text: str = response.choices[0].message.content
        except openai.RateLimitError:
            wx.CallAfter(
                self._on_wyslij_error,
                "Brak kredytów OpenAI! Doładuj konto i spróbuj ponownie.",
            )
            return
        except Exception as exc:
            wx.CallAfter(self._on_wyslij_error, str(exc))
            return

        # ── Post-processing ───────────────────────────────────────────
        if tryb_idx == 1:  # Skrypt – silnik fonetyczny
            response_text = self.zastosuj_akcenty_uniwersalne(response_text, world_context)

        if tryb_idx == 0:  # Burza Mózgów – wyciągnięcie <STRESZCZENIE>
            _match = re.search(
                r"<STRESZCZENIE>(.*?)</STRESZCZENIE>",
                response_text,
                re.DOTALL | re.IGNORECASE,
            )
            if _match:
                nowe_streszczenie = _match.group(1).strip()
                response_text = re.sub(
                    r"<STRESZCZENIE>.*?</STRESZCZENIE>",
                    "",
                    response_text,
                    flags=re.DOTALL | re.IGNORECASE,
                ).strip()
                wx.CallAfter(self._on_wyslij_zapisz_streszczenie, nowe_streszczenie)

        # ── Zapis do pliku lub wyświetlenie odpowiedzi ────────────────
        if tryb_zapisu:
            refusal_kw = [
                "jako model językowy", "as an ai",
                "nie mogę spełnić tej prośby", "nie mogę wygenerować",
                "narusza zasady", "zasady bezpieczeństwa",
            ]
            if any(kw in response_text.lower() for kw in refusal_kw):
                wx.CallAfter(
                    self._on_wyslij_error,
                    "AI odrzuciło prompt przez filtry bezpieczeństwa!\n"
                    "Tekst NIE ZOSTANIE zapisany.",
                )
                return
            # Blokada zapisu po epilogu
            _ep_idx = full_story.find("Epilog")
            if _ep_idx != -1 and len(full_story[_ep_idx + len("Epilog"):].strip()) > 0:
                wx.CallAfter(
                    self._on_wyslij_error,
                    "Epilog ma już treść – nie można dopisywać kolejnych fragmentów "
                    "po zakończeniu historii.",
                )
                return
            wx.CallAfter(self._on_wyslij_done_zapis, response_text, nazwa)
        else:
            wx.CallAfter(self._on_wyslij_done_burza, response_text)

    # ------------------------------------------------------------------
    # Callbacki _wyslij_worker (wywołania przez wx.CallAfter – wątek GUI)
    # ------------------------------------------------------------------
    def _on_wyslij_error(self, msg: str) -> None:
        """Pokazuje błąd AI i odblokowuje przycisk Wyślij.

        Krótkie komunikaty (np. brak kredytów) → wx.MessageBox.
        Długie / techniczne wyjątki OpenAI → dialog z polem do skopiowania.
        """
        self._btn_wyslij.Enable()
        self._refresh_ui_state()
        self._wyswietl_blad_ai(msg)

    def _on_wyslij_zapisz_streszczenie(self, streszczenie: str) -> None:
        """Zapisuje wykryte streszczenie AI do pamięci i pola UI (Pamięć Długotrwała)."""
        self.summary_text = streszczenie
        self._txt_pamiec.SetValue(streszczenie)

    def _on_wyslij_done_zapis(self, response_text: str, nazwa: str) -> None:
        """Dopisuje odpowiedź AI do full_story i pliku (tryb Skrypt / Audiobook)."""
        if self.full_story:
            self.full_story += "\n\n" + response_text
        else:
            self.full_story = response_text
        self._txt_full_story.SetValue(self.full_story)
        self._dopisz_do_pliku(nazwa, response_text + "\n\n")
        self.last_response = response_text
        self._btn_wyslij.Enable()
        self._refresh_ui_state()
        # A11y: sygnał dźwiękowy + fokus na historii → NVDA od razu czyta nowy fragment
        wx.Bell()
        self._txt_full_story.SetFocus()

    def _on_wyslij_done_burza(self, response_text: str) -> None:
        """Wyświetla odpowiedź AI w oknie dialogowym (tryb Burza Mózgów – BEZ zapisu)."""
        self.last_response = response_text
        self._btn_wyslij.Enable()
        self._refresh_ui_state()
        self._show_response_dialog(response_text)

    def _show_response_dialog(self, tekst: str) -> None:
        """Otwiera modal z odpowiedzią AI (czytelny przez NVDA / klawiatury)."""
        dlg = wx.Dialog(
            self,
            title="Odpowiedź AI – Burza Mózgów",
            size=(720, 520),
        )
        sizer = wx.BoxSizer(wx.VERTICAL)
        lbl = wx.StaticText(
            dlg,
            label="Skopiuj zaznaczony tekst (Ctrl+A, Ctrl+C) lub zamknij:",
        )
        txt = wx.TextCtrl(
            dlg,
            value=tekst,
            style=wx.TE_MULTILINE | wx.TE_READONLY,
            name="Odpowiedź AI – Burza Mózgów",
        )
        btn_ok = wx.Button(dlg, wx.ID_OK, label="Zamknij")
        sizer.Add(lbl,    flag=wx.ALL,                                   border=8)
        sizer.Add(txt,    proportion=1, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=8)
        sizer.Add(btn_ok, flag=wx.ALL | wx.ALIGN_RIGHT,                  border=8)
        dlg.SetSizer(sizer)
        txt.SetFocus()
        dlg.ShowModal()
        dlg.Destroy()

    # ------------------------------------------------------------------
    # Wstawianie Prologu
    # ------------------------------------------------------------------
    def _on_wstaw_prolog(self, _event: wx.Event) -> None:
        """Wstawia nagłówek 'Prolog' do historii i pliku projektu."""
        nazwa = self._txt_file_name.GetValue().strip()
        if not nazwa:
            wx.MessageBox(
                "Podaj nazwę pliku projektu przed wstawianiem struktury.",
                "Brak nazwy",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            self._txt_file_name.SetFocus()
            return

        header_text = "Prolog\n\n"
        self.full_story += header_text
        self._txt_full_story.SetValue(self.full_story)
        # mode="w" – Prolog zaczyna historię od zera; nadpisuje istniejący plik
        # aby uniknąć artefaktów z poprzednich sesji (np. "testProlog").
        self._dopisz_do_pliku(nazwa, header_text, mode="w")
        self._zapisz_tryb_projektu()
        self._refresh_ui_state()
        wx.MessageBox(
            "Wstawiono nagłówek: Prolog.\n\nRozpocznij pisanie treści prologu.",
            "Prolog wstawiony",
            wx.OK | wx.ICON_INFORMATION,
            self,
        )

    # ------------------------------------------------------------------
    # Wstawianie Epilogu
    # ------------------------------------------------------------------
    def _on_wstaw_epilog(self, _event: wx.Event) -> None:
        """Wstawia nagłówek 'Epilog' na końcu historii i pliku projektu."""
        nazwa = self._txt_file_name.GetValue().strip()
        if not nazwa:
            wx.MessageBox(
                "Podaj nazwę pliku projektu przed wstawianiem struktury.",
                "Brak nazwy",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            self._txt_file_name.SetFocus()
            return

        header_text = "\n\nEpilog\n\n"
        self.full_story += header_text
        self._txt_full_story.SetValue(self.full_story)
        self._dopisz_do_pliku(nazwa, header_text)
        self._zapisz_tryb_projektu()
        self._refresh_ui_state()
        wx.MessageBox(
            "Wstawiono nagłówek: Epilog.\n\nDalsze generowanie treści po Epilogu jest zablokowane.",
            "Epilog wstawiony",
            wx.OK | wx.ICON_INFORMATION,
            self,
        )

    # ------------------------------------------------------------------
    # Wstawianie cięcia Rozdziału (Audiobook)
    # ------------------------------------------------------------------
    def _on_wstaw_rozdzial(self, _event: wx.Event) -> None:
        """Wstawia nagłówek 'Rozdział N' do historii i pliku (tryb Audiobook)."""
        nazwa = self._txt_file_name.GetValue().strip()
        if not nazwa:
            wx.MessageBox(
                "Podaj nazwę pliku projektu przed wstawianiem struktury.",
                "Brak nazwy",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            self._txt_file_name.SetFocus()
            return

        naglowek       = f"Rozdział {self.chapter_counter}"
        content_to_add = f"\n\n{naglowek}\n\n"
        self.full_story += content_to_add
        self.chapter_counter += 1
        self._txt_full_story.SetValue(self.full_story)
        self._dopisz_do_pliku(nazwa, content_to_add)
        self._zapisz_tryb_projektu()
        self._refresh_ui_state()
        wx.MessageBox(
            f"Wstawiono nagłówek: {naglowek}.",
            "Cięcie rozdziału wstawione",
            wx.OK | wx.ICON_INFORMATION,
            self,
        )

    # ------------------------------------------------------------------
    # Wstawianie Aktu (Skrypt)
    # ------------------------------------------------------------------
    def _on_wstaw_akt(self, _event: wx.Event) -> None:
        """Wstawia 'Akt N' + automatycznie 'Scena 1' (tryb Skrypt)."""
        nazwa = self._txt_file_name.GetValue().strip()
        if not nazwa:
            wx.MessageBox(
                "Podaj nazwę pliku projektu przed wstawianiem struktury.",
                "Brak nazwy",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            self._txt_file_name.SetFocus()
            return

        akt_naglowek   = f"Akt {self.akt_counter}"
        scena_naglowek = "Scena 1"
        content_to_add = f"\n\n{akt_naglowek}\n\n{scena_naglowek}\n\n"
        self.full_story += content_to_add
        self.akt_counter   += 1
        self.scena_counter  = 2   # Scena 1 już wstawiona – następna to Scena 2
        self._txt_full_story.SetValue(self.full_story)
        self._dopisz_do_pliku(nazwa, content_to_add)
        self._zapisz_tryb_projektu()
        self._refresh_ui_state()
        wx.MessageBox(
            f"Wstawiono: {akt_naglowek} oraz {scena_naglowek}.",
            "Akt wstawiony",
            wx.OK | wx.ICON_INFORMATION,
            self,
        )

    # ------------------------------------------------------------------
    # Wstawianie Sceny (Skrypt)
    # ------------------------------------------------------------------
    def _on_wstaw_scena(self, _event: wx.Event) -> None:
        """Wstawia 'Scena N' do historii i pliku (tryb Skrypt)."""
        nazwa = self._txt_file_name.GetValue().strip()
        if not nazwa:
            wx.MessageBox(
                "Podaj nazwę pliku projektu przed wstawianiem struktury.",
                "Brak nazwy",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            self._txt_file_name.SetFocus()
            return

        scena_naglowek = f"Scena {self.scena_counter}"
        content_to_add = f"\n\n{scena_naglowek}\n\n"
        self.full_story += content_to_add
        self.scena_counter += 1
        self._txt_full_story.SetValue(self.full_story)
        self._dopisz_do_pliku(nazwa, content_to_add)
        self._zapisz_tryb_projektu()
        self._refresh_ui_state()
        wx.MessageBox(
            f"Wstawiono nagłówek: {scena_naglowek}.",
            "Scena wstawiona",
            wx.OK | wx.ICON_INFORMATION,
            self,
        )

    # ------------------------------------------------------------------
    # Postprodukcja – Nadaj Tytuły Rozdziałom (stub)
    # ------------------------------------------------------------------
    def _on_tytuly_ai(self, _event: wx.Event) -> None:
        """Uruchamia wątek generowania tytułów rozdziałów z zapisanego pliku projektu."""
        nazwa = self._txt_file_name.GetValue().strip()
        if not nazwa:
            wx.MessageBox(
                "Podaj nazwę projektu przed nadaniem tytułów.",
                "Brak nazwy projektu",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            return

        if self._worker_thread and self._worker_thread.is_alive():
            wx.MessageBox(
                "Trwa już inne zapytanie do AI. Poczekaj na zakończenie.",
                "Zajęty",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            return

        app_dir  = os.path.dirname(os.path.abspath(__file__))
        filepath = os.path.join(app_dir, self.SKRYPTY_DIR, f"{nazwa}.txt")
        if not os.path.exists(filepath):
            wx.MessageBox(
                f"Nie znaleziono pliku:\n{filepath}\n\n"
                "Wygeneruj i zapisz najpierw treść projektu.",
                "Brak pliku projektu",
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return

        try:
            with open(filepath, "r", encoding="utf-8") as fh:
                pelny_tekst = fh.read()
        except Exception as exc:
            wx.MessageBox(
                f"Błąd odczytu pliku:\n{exc}",
                "Błąd odczytu",
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return

        # Pokaż pasek postępu i zablokuj przycisk
        self._btn_tytuly_ai.Disable()
        self._gauge_postprod.SetValue(0)
        self._gauge_postprod.Show()
        self._lbl_postprod_status.SetLabel("Przygotowywanie…")
        self._lbl_postprod_status.Show()
        self._pnl_postprodukcja.Layout()
        self.Layout()

        t = threading.Thread(
            target=self._tytuly_worker,
            args=(pelny_tekst,),
            daemon=True,
        )
        self._worker_thread = t
        t.start()

    # ------------------------------------------------------------------
    # Wątek tła – generowanie tytułów (ŻADNYCH wx.* bezpośrednio!)
    # ------------------------------------------------------------------
    def _tytuly_worker(self, pelny_tekst: str) -> None:
        """Iteruje po rozdziałach pliku projektu i generuje tytuły via gpt-4o-mini."""
        # Uwaga: ł wpisany dosłownie – w raw-string \u0142 NIE byłby interpretowany
        wzorzec   = r"(?i)\n*(Prolog|Rozdział \d+|Epilog)\n*"
        fragmenty = re.split(wzorzec, pelny_tekst)

        if len(fragmenty) <= 1:
            wx.CallAfter(
                self._on_tytuly_error,
                "Nie znaleziono tagów struktury (Prolog / Rozdział N / Epilog) w pliku.\n"
                "Wstaw cięcia rozdziałów przed nadaniem tytułów.",
            )
            return

        tytuly: list[str] = []
        total   = len(range(1, len(fragmenty), 2))
        current = 0

        for i in range(1, len(fragmenty), 2):
            naglowek = fragmenty[i].strip()
            tresc    = fragmenty[i + 1].strip() if i + 1 < len(fragmenty) else ""
            current += 1
            percent  = int(current / total * 100)

            wx.CallAfter(
                self._update_tytuly_progress,
                f"Tytułowanie: {naglowek} ({current}/{total})…",
                percent,
            )

            if len(tresc) < 50:
                tytuly.append(f"{naglowek}: (Fragment zbyt krótki)")
                continue

            probka = tresc[:6000]
            prompt_tytul = (
                f"Oto treść fragmentu książki ({naglowek}). "
                "Wymyśl JEDEN krótki, chwytliwy i literacki tytuł bez cudzysłowów.\n\n"
                f"TREŚĆ:\n{probka}"
            )

            try:
                resp = self._client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "Jesteś wybitnym redaktorem. "
                                "Odpowiadasz wyłącznie samym tytułem."
                            ),
                        },
                        {"role": "user", "content": prompt_tytul},
                    ],
                    temperature=0.7,
                )
                tytul_out = resp.choices[0].message.content.strip()
                tytuly.append(f"{naglowek}: {tytul_out}")
            except openai.RateLimitError:
                tytuly.append(f"{naglowek}: (Błąd – brak kredytów API)")
                # A11y: częściowe tytuły w czytelnym dialogu zamiast w alercie błędowym
                wx.CallAfter(
                    self._show_titles_dialog,
                    "⚠️ BRAK KREDYTÓW OpenAI! Przerwano po częściowych wynikach:\n\n"
                    + "\n".join(tytuly),
                )
                return
            except Exception as exc:
                tytuly.append(f"{naglowek}: (Błąd – {exc})")
                # Przekaż kopię listy częściowych tytułów – jak w Streamlit (wyswietl_blad_ai + st.markdown)
                wx.CallAfter(self._on_tytuly_error, str(exc), tytuly[:])
                return

        wx.CallAfter(self._show_titles_dialog, "\n".join(tytuly))

    # ------------------------------------------------------------------
    # Callbacki _tytuly_worker (wywołania przez wx.CallAfter – wątek GUI)
    # ------------------------------------------------------------------
    def _update_tytuly_progress(self, msg: str, percent: int) -> None:
        """Aktualizuje pasek i etykietę postępu tytułowania."""
        self._lbl_postprod_status.SetLabel(msg)
        self._gauge_postprod.SetValue(max(0, min(100, percent)))

    def _on_tytuly_error(self, msg: str, partial_tytuly: list | None = None) -> None:
        """Obsługuje błąd tytułowania: ukrywa pasek, pokazuje błąd i ewentualne tytuły częściowe.

        Jeśli do momentu błędu wygenerowano już część tytułów, pokazuje je
        w osobnym oknie dialogowym — tak samo jak w Streamlit (wyswietl_blad_ai + st.markdown).
        """
        self._btn_tytuly_ai.Enable()
        self._gauge_postprod.SetValue(0)
        self._gauge_postprod.Hide()
        self._lbl_postprod_status.Hide()
        self._pnl_postprodukcja.Layout()
        self.Layout()
        self._wyswietl_blad_ai(
            msg,
            "Wystąpił błąd podczas generowania tytułów rozdziałów.",
        )
        if partial_tytuly:
            self._show_titles_dialog(
                "⚠️ Częściowe wyniki (generowanie przerwano błędem):\n\n"
                + "\n".join(partial_tytuly)
            )

    def _show_titles_dialog(self, tytuly_text: str) -> None:
        """Wyświetla wygenerowane tytuły rozdziałów w oknie dialogowym."""
        self._btn_tytuly_ai.Enable()
        self._gauge_postprod.SetValue(100)
        self._lbl_postprod_status.SetLabel("Gotowe! Tytuły wygenerowane.")

        dlg = wx.Dialog(
            self,
            title="Proponowane Tytuły Rozdziałów (AI)",
            size=(620, 420),
        )
        sizer = wx.BoxSizer(wx.VERTICAL)
        lbl = wx.StaticText(
            dlg,
            label="Skopiuj tytuły (Ctrl+A, Ctrl+C) lub zanotuj je w Księdze Świata:",
        )
        txt = wx.TextCtrl(
            dlg,
            value=tytuly_text,
            style=wx.TE_MULTILINE | wx.TE_READONLY,
            name="Lista proponowanych tytułów rozdziałów",
        )
        btn_ok = wx.Button(dlg, wx.ID_OK, label="Zamknij")
        sizer.Add(lbl,    flag=wx.ALL,                                   border=8)
        sizer.Add(txt,    proportion=1, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=8)
        sizer.Add(btn_ok, flag=wx.ALL | wx.ALIGN_RIGHT,                  border=8)
        dlg.SetSizer(sizer)
        txt.SetFocus()
        dlg.ShowModal()
        dlg.Destroy()

    # ------------------------------------------------------------------
    # Zapis trybu twórczego do pliku metadanych projektu
    # ------------------------------------------------------------------
    def _zapisz_tryb_projektu(self) -> None:
        """Zapisuje aktualny tryb twórczy (Skrypt=1 / Audiobook=2) do pliku .mode.

        Plik ``skrypty/<nazwa>.mode`` przywraca właściwy tryb po ponownym
        wczytaniu projektu i zapobiega przypadkowej zmianie trybu na RadioBoxie.
        Cichy fail – metadata nie jest krytyczna dla działania programu.
        """
        nazwa    = self._txt_file_name.GetValue().strip()
        tryb_idx = self._rb_mode.GetSelection()
        if not nazwa or tryb_idx not in (1, 2):
            return
        app_dir     = os.path.dirname(os.path.abspath(__file__))
        runtime_dir = os.path.join(app_dir, "runtime")
        if not os.path.exists(runtime_dir):
            print(f"[INFO] Folder 'runtime/' nie istnieje – zostanie utworzony: {runtime_dir}")
        meta_dir  = os.path.join(runtime_dir, self.SKRYPTY_DIR)
        os.makedirs(meta_dir, exist_ok=True)
        mode_path = os.path.join(meta_dir, f"{nazwa}.mode")
        try:
            with open(mode_path, "w", encoding="utf-8") as fh:
                fh.write(str(tryb_idx))
        except Exception:
            pass
