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

# Refaktor wersji 13.0: logika modelu, przepisy i silnik AI są wydzielone
# z tego pliku. Panel zostaje cienką warstwą widoku wxPython.
import core_rezyser as cr
import przepisy_rezysera as pr
import rezyser_ai as rai

# Reguły fonetyczne są teraz w ``core_rezyser`` (przeniesione z
# ``gui_rezyser`` w ramach Etapu 2). Importy akcentów w blokach
# GENEROWANE_IMPORTY_AKCENTOW_* zostały przeniesione tam i są generowane
# przez ``odswiez_rezysera.py``. Ten plik ich już bezpośrednio nie używa.
# <GENEROWANE_IMPORTY_AKCENTOW_START>
from core_poliglota import (
    akcent_islandzki,
    akcent_angielski,
    akcent_francuski,
    akcent_niemiecki,
    akcent_hiszpanski,
    akcent_wloski,
    akcent_finski,
)
# <GENEROWANE_IMPORTY_AKCENTOW_END>


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

        # ── Model danych: stan projektu, I/O, liczniki, silnik fonetyczny ──
        # Refaktor 13.0: cały stan trzymany w core_rezyser.ProjektRezysera.
        # Atrybuty full_story / summary_text / world_lore / liczniki /
        # zapisana_nazwa_pliku / last_response są @property delegującymi do
        # self._projekt – dzięki temu istniejący kod typu
        # ``self.full_story += tekst`` nadal działa, ale dane są trzymane
        # w jednym miejscu (ProjektRezysera) i dostępne dla wątku tła AI
        # przez ``self._projekt.snapshot()``.
        self._projekt: cr.ProjektRezysera = cr.ProjektRezysera()

        # ── Przepisy twórcze załadowane z YAML-i (dictionaries/pl/rezyser/) ─
        # Kolejność jest zgodna z dawnym TRYBY_PRACY:
        # indeks 0 = Burza, 1 = Skrypt, 2 = Audiobook. Dynamika RadioBox
        # w ``_build_ui`` używa ``p.etykieta`` dla każdego przepisu.
        self._przepisy: list[pr.PrzepisRezysera] = pr.lista_trybow("pl")
        self._przepis_tytuly: pr.PrzepisRezysera | None = pr.zaladuj_przepis(
            "tytuly", kategoria="postprodukcja",
        )

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
    # Helper: wskazuje przepis dla aktualnie zaznaczonego trybu w RadioBox
    # ------------------------------------------------------------------
    def _aktualny_przepis(self) -> pr.PrzepisRezysera | None:
        """Zwraca :class:`PrzepisRezysera` odpowiadający zaznaczonemu trybowi.

        Użyteczne dla wątku tła AI (``_wyslij_worker``) – eliminuje
        konieczność pracy z indeksem trybu (0/1/2) i pozwala korzystać
        z pól YAML-a typu ``zapis_do_pliku``, ``stosuj_akcenty_fonetyczne``.

        Returns:
            Pierwszy przepis odpowiadający ``self._rb_mode.GetSelection()``
            lub ``None``, gdy lista ``self._przepisy`` jest pusta (brak YAML-i).
        """
        if not self._przepisy:
            return None
        idx = self._rb_mode.GetSelection()
        if 0 <= idx < len(self._przepisy):
            return self._przepisy[idx]
        return None

    # ==================================================================
    # SHIMY WŁAŚCIWOŚCI delegujące do self._projekt
    # ------------------------------------------------------------------
    # Po refaktorze 13.0 prawdziwy stan projektu żyje w ``self._projekt``
    # (instancja ``core_rezyser.ProjektRezysera``). Aby nie zmieniać setek
    # miejsc w tym pliku, które czytają/piszą ``self.full_story`` itp.,
    # każdy dawny atrybut jest tu @property z getter'em i setter'em
    # delegującym do ``self._projekt.*``. Operacje typu
    # ``self.full_story += tekst`` działają naturalnie: Python wywołuje
    # getter (by przeczytać bieżącą wartość), konkatenuje i wywołuje setter.
    # ==================================================================

    @property
    def full_story(self) -> str:
        return self._projekt.full_story

    @full_story.setter
    def full_story(self, value: str) -> None:
        self._projekt.full_story = value

    @property
    def summary_text(self) -> str:
        return self._projekt.summary_text

    @summary_text.setter
    def summary_text(self, value: str) -> None:
        self._projekt.summary_text = value

    @property
    def world_lore(self) -> str:
        return self._projekt.world_lore

    @world_lore.setter
    def world_lore(self, value: str) -> None:
        self._projekt.world_lore = value

    @property
    def chapter_counter(self) -> int:
        return self._projekt.chapter_counter

    @chapter_counter.setter
    def chapter_counter(self, value: int) -> None:
        self._projekt.chapter_counter = value

    @property
    def akt_counter(self) -> int:
        return self._projekt.akt_counter

    @akt_counter.setter
    def akt_counter(self, value: int) -> None:
        self._projekt.akt_counter = value

    @property
    def scena_counter(self) -> int:
        return self._projekt.scena_counter

    @scena_counter.setter
    def scena_counter(self, value: int) -> None:
        self._projekt.scena_counter = value

    @property
    def zapisana_nazwa_pliku(self) -> str:
        # Pole w ProjektRezysera nazywa się ``nazwa_pliku`` – shim mapuje
        # starą polską nazwę na nową (krótszą).
        return self._projekt.nazwa_pliku

    @zapisana_nazwa_pliku.setter
    def zapisana_nazwa_pliku(self, value: str) -> None:
        self._projekt.nazwa_pliku = value

    @property
    def last_response(self) -> str:
        return self._projekt.last_response

    @last_response.setter
    def last_response(self, value: str) -> None:
        self._projekt.last_response = value

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
        # Etykiety pobierane dynamicznie z YAML-i w ``dictionaries/pl/rezyser/``.
        # Zbiorczy commit wersji 13.0 zawiera ten folder, więc w środowisku
        # wydawniczym ``self._przepisy`` jest zawsze niepuste.
        self._rb_mode = wx.RadioBox(
            self,
            label="Tryb pracy:",
            choices=[p.etykieta for p in self._przepisy],
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

        Refaktor 13.0: większość obliczeń (``pamiec_zajeta``, ``ma_prolog``,
        ``ma_epilog``, ``ostatnia_linia_to_naglowek``, ``epilog_ma_tresc``)
        została przeniesiona do properties w ``core_rezyser.ProjektRezysera``.
        Dzięki temu ta metoda stała się czytelniejsza: odpowiada wyłącznie
        za mapowanie stanu modelu na ``Enable/Disable/Show/Hide`` widżetów.

        Na końcu zawsze wywołuje self.Layout(), by okno poprawnie przeliczyło
        rozmiary po ewentualnym ukryciu lub pokazaniu paneli struktury i postprodukcji.
        """
        pamiec_zajeta = self._projekt.pamiec_zajeta
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
        # Epilog z treścią = historia zakończona, dalsze dopisywanie zablokowane.
        _epilog_ma_tresc = self._projekt.epilog_ma_tresc

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

        # Wspólne warunki dla przycisków struktury (wszystkie z modelu).
        _prolog_juz_jest   = self._projekt.ma_prolog
        _epilog_juz_jest   = self._projekt.ma_epilog
        _historia_niepusta = bool(self.full_story.strip())
        _blokada = self._projekt.ostatnia_linia_to_naglowek or _epilog_juz_jest


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
        """Wczytuje istniejący plik projektu z folderu skrypty/.

        Deleguje do ``self._projekt.wczytaj()`` – cała logika I/O, analizy
        liczników i reguły Nieskończonej Pamięci (streszczenie priorytet
        nad full_story) żyje w ``core_rezyser.ProjektRezysera``. GUI tylko
        synchronizuje kontrolki UI ze stanem projektu i pokazuje status.
        """
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

        try:
            wynik = self._projekt.wczytaj(nazwa)
        except FileNotFoundError as exc:
            wx.MessageBox(
                f"Nie znaleziono pliku:\n{exc}\n\n"
                "Jeśli zaczynasz nową historię — po prostu zacznij pisać.\n"
                "Plik zostanie utworzony automatycznie przy pierwszym wysłaniu do AI.",
                "Plik nie istnieje",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            return
        except OSError as exc:
            wx.MessageBox(
                f"Błąd odczytu pliku:\n{exc}",
                "Błąd odczytu",
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return

        # Synchronizuj kontrolki UI ze stanem projektu (właściwości @property
        # już przekierowały odczyt do self._projekt.*).
        self._txt_ksiega_swiata.SetValue(self.world_lore)
        self._txt_pamiec.SetValue(self.summary_text)
        self._txt_full_story.SetValue(self.full_story)

        # Jeśli projekt miał zapisany tryb twórczy w pliku .mode – ustaw RadioBox
        if wynik.saved_mode in (1, 2):
            self._rb_mode.SetSelection(wynik.saved_mode)

        # Komunikat statusu: Nieskończona Pamięć vs. zwykłe wczytanie
        lore_info = f" Wczytano też Księgę: skrypty/{nazwa}.md." if wynik.czy_ksiega_swiata else ""
        if wynik.czy_streszczenie:
            status_msg = (
                f"Wczytano streszczenie projektu '{nazwa}'.{lore_info}\n"
                "Pamięć bieżąca pozostaje pusta (tryb Nieskończonej Pamięci).\n"
                "Możesz kontynuować historię — AI operuje na streszczeniu."
            )
        else:
            status_msg = (
                f"Wczytano historię '{nazwa}' ({wynik.liczba_znakow} znaków).{lore_info}"
            )

        self._refresh_ui_state()
        wx.MessageBox(status_msg, "Wczytano projekt", wx.OK | wx.ICON_INFORMATION, self)

    # ------------------------------------------------------------------
    # Czyszczenie pamięci bieżącej (streszczenie i Księga zostają)
    # ------------------------------------------------------------------
    def _on_clear_current(self, _event: wx.Event) -> None:
        """Czyści WYŁĄCZNIE bieżącą fabułę (full_story) i ostatnią odpowiedź AI.

        Deleguje do ``self._projekt.wyczysc_biezaca()`` – zachowane zostają:
        liczniki rozdziałów/aktów/scen, nazwa pliku, Księga Świata,
        Streszczenie (Pamięć Długotrwała), zapamiętany tryb twórczy.
        Dzięki temu użytkownik może kontynuować projekt od razu po wyczyszczeniu.
        """
        self._projekt.wyczysc_biezaca()
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

        # Wyzeruj cały stan pamięci (jedno wywołanie zamiast 8 linii).
        self._projekt.twardy_reset()

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
        """Zapisuje Księgę Świata do pliku skrypty/<nazwa>.md.

        Deleguje do ``self._projekt.zapisz_ksiege_swiata()`` – metoda
        aktualizuje także ``self.world_lore`` przez property-shim.
        """
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

        # Upewnij się, że projekt zna nazwę (walidacja _wymagaj_nazwy w core).
        if self._projekt.nazwa_pliku != nazwa:
            self._projekt.nazwa_pliku = nazwa
        try:
            self._projekt.zapisz_ksiege_swiata(tresc)
            wx.MessageBox(
                f"Księga Świata zapisana: skrypty/{nazwa}.md",
                "Księga zapisana",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
        except Exception as exc:  # noqa: BLE001
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
        """Zapisuje streszczenie do pliku skrypty/<nazwa>_streszczenie.txt.

        Deleguje do ``self._projekt.zapisz_streszczenie()`` – metoda
        aktualizuje także ``self.summary_text`` przez property-shim.
        """
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

        # Upewnij się, że projekt zna nazwę (walidacja _wymagaj_nazwy w core).
        if self._projekt.nazwa_pliku != nazwa:
            self._projekt.nazwa_pliku = nazwa
        try:
            self._projekt.zapisz_streszczenie(tresc)
            wx.MessageBox(
                f"Streszczenie zapisane: skrypty/{nazwa}_streszczenie.txt\n\n"
                "Możesz teraz bezpiecznie wyczyścić pamięć bieżącą.",
                "Streszczenie zapisane",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
        except Exception as exc:  # noqa: BLE001
            wx.MessageBox(
                f"Błąd zapisu streszczenia:\n{exc}",
                "Błąd zapisu",
                wx.OK | wx.ICON_ERROR,
                self,
            )

    # ------------------------------------------------------------------
    # Wysyłanie do AI
    # ------------------------------------------------------------------
    def _on_wyslij(self, _event: wx.Event) -> None:
        """Obsługuje przycisk 'Wyślij do AI'.

        Refaktor 13.0: cała logika budowy promptów, wywołania OpenAI,
        detekcji odrzucenia i ekstrakcji streszczenia żyje teraz w
        :mod:`rezyser_ai` (``generuj_fragment``). Ta metoda tylko
        waliduje dane wejściowe z GUI, ustawia ``self._projekt`` w znany
        stan (``world_lore``, ``nazwa_pliku``) i odpala wątek tła
        z gotowym ``SnapshotProjektu`` + wybranym ``PrzepisRezysera``.
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

        nazwa       = self._txt_file_name.GetValue().strip()
        przepis     = self._aktualny_przepis()
        if przepis is None:
            wx.MessageBox(
                "Nie udało się załadować żadnego trybu pracy z YAML.\n"
                "Uruchom odswiez_rezysera.py lub sprawdź dictionaries/pl/rezyser/.",
                "Brak przepisów",
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return
        tryb_zapisu = przepis.zapis_do_pliku

        if tryb_zapisu and not nazwa:
            wx.MessageBox(
                "Podaj nazwę pliku projektu, zanim wygenerujesz tekst do zapisu.\n"
                f"(Tryb '{przepis.etykieta}' wymaga nazwy pliku.)",
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

        # Ochrona przed generowaniem streszczenia w trybie zapisu do pliku.
        # Słowa kluczowe bierzemy z YAML-a (``slowa_wyzwalajace.streszczenie``)
        # – lingwista może je rozszerzyć o "podsumuj", "streść" itp.
        slowa_streszczenia = przepis.slowa_wyzwalajace.get("streszczenie", [])
        if tryb_zapisu and any(s in user_text.lower() for s in slowa_streszczenia):
            wx.MessageBox(
                "Próbujesz wygenerować streszczenie w trybie zapisu do pliku!\n"
                "To mogłoby uszkodzić Twoją historię.\n\n"
                "Przełącz się na tryb 'Burza Mózgów' i spróbuj ponownie.",
                "Błąd trybu",
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return

        # Synchronizujemy stan modelu z aktualnymi wartościami kontrolek,
        # zanim zrobimy snapshot dla wątku tła:
        #   • Księga Świata mogła zostać zmodyfikowana po ostatnim "Zapisz Księgę";
        #   • nazwa_pliku mogła nie być jeszcze ustawiona w modelu, jeśli user
        #     dopiero wpisał ją do pola (bez "Wczytaj historię").
        self._projekt.world_lore = world_context
        if nazwa and self._projekt.nazwa_pliku != nazwa:
            self._projekt.nazwa_pliku = nazwa

        # Zablokuj przycisk, wyczyść pole instrukcji
        self._btn_wyslij.Disable()
        self._txt_user_input.SetValue("")
        self._refresh_ui_state()

        # Snapshot niezmiennego stanu dla wątku tła (GIL-safe).
        snapshot = self._projekt.snapshot()

        t = threading.Thread(
            target=self._wyslij_worker,
            args=(przepis, snapshot, user_text, nazwa, tryb_zapisu),
            daemon=True,
        )
        self._worker_thread = t
        t.start()


    # ------------------------------------------------------------------
    # Pomocnicza metoda zapisu do pliku projektu (thin wrapper)
    # ------------------------------------------------------------------
    def _dopisz_do_pliku(self, nazwa: str, content: str, mode: str = "a") -> None:
        """Thin wrapper: deleguje do ``self._projekt.dopisz_do_pliku_historii``.

        Zachowany dla kompatybilności z istniejącymi wywołaniami w
        ``_on_wstaw_*`` i ``_on_wyslij_done_zapis``. Błędy I/O zostaną
            obsłużone przez wx.MessageBox, tak jak dotychczas – bo
        ProjektRezysera.dopisz_do_pliku_historii propaguje wyjątki.

        Args:
            nazwa:   Nazwa projektu (tylko dla spójności API – w praktyce
                     ``ProjektRezysera`` używa własnego ``nazwa_pliku``).
            content: Treść do zapisania.
            mode:    ``"a"`` (dopisz) lub ``"w"`` (nadpisz – dla Prologu).
        """
        # Upewnij się, że projekt ma ustawioną nazwę pliku – niezbędne dla
        # walidacji w ProjektRezysera._wymagaj_nazwy().
        if self._projekt.nazwa_pliku != nazwa:
            self._projekt.nazwa_pliku = nazwa
        try:
            self._projekt.dopisz_do_pliku_historii(content, mode=mode)
        except Exception as exc:  # noqa: BLE001
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

        # Mapa: znormalizowana nazwa akcentu → funkcja fonetyczna z core_poliglota.
        # Blok generowany automatycznie przez ``odswiez_rezysera.py`` po każdym
        # dodaniu nowego pliku YAML w dictionaries/<język>/akcenty/.
        # <GENEROWANY_SLOWNIK_AKCENTOW_START>
        _AKCENT_FUNCS = {
            "islandzki": akcent_islandzki,
            "angielski": akcent_angielski,
            "francuski": akcent_francuski,
            "niemiecki": akcent_niemiecki,
            "hiszpanski":akcent_hiszpanski,
            "wloski":    akcent_wloski,
            "finski":    akcent_finski,
        }
# <GENEROWANY_SLOWNIK_AKCENTOW_END>

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
    # Mapa poziom zagrożenia → kolor wskaźnika pamięci modelu.
    # Trzymana poza metodą, by nie tworzyć obiektu wx.Colour przy każdym
    # odświeżeniu UI. Kolory zgodne z dotychczasową wersją (zielony/
    # pomarańczowy/czerwony), tylko teraz mapowane przez poziom z
    # ``core_rezyser.StatusPamieciModelu`` zamiast progiem na sztywno.
    _KOLORY_POZIOMOW = {
        cr.POZIOM_CZYSTA:     (0, 128, 0),
        cr.POZIOM_OK:         (0, 128, 0),
        cr.POZIOM_OSTRZEZENIE:(180, 100, 0),
        cr.POZIOM_ALARM:      (180, 0, 0),
    }

    def _aktualizuj_pamiec_modelu(self) -> None:
        """Odświeża wskaźnik pamięci modelu (kontekst okna AI).

        Refaktor 13.0: obliczenia progów i komunikatów są w
        ``ProjektRezysera.status_pamieci_modelu()``. Ta metoda tylko
        mapuje wynik (procent + komunikat + poziom) na widżety wxPython.
        """
        status = self._projekt.status_pamieci_modelu()
        r, g, b = self._KOLORY_POZIOMOW.get(status.poziom, (0, 0, 0))
        self._gauge_kontekst.SetValue(status.procent)
        self._lbl_kontekst_status.SetValue(status.komunikat)
        self._lbl_kontekst_status.SetForegroundColour(wx.Colour(r, g, b))


    # ------------------------------------------------------------------
    # Wątek tła – główna logika AI (ŻADNYCH wx.* bezpośrednio!)
    # ------------------------------------------------------------------
    def _wyslij_worker(
        self,
        przepis: pr.PrzepisRezysera,
        snapshot: cr.SnapshotProjektu,
        user_text: str,
        nazwa: str,
        tryb_zapisu: bool,
    ) -> None:
        """Wywołuje ``rezyser_ai.generuj_fragment`` i rozsyła wyniki przez wx.CallAfter.

        Refaktor 13.0: cała warstwa budowy payloadu OpenAI, wybierania
        sufiksów kontekstowych, detekcji odrzucenia i ekstrakcji
        ``<STRESZCZENIE>`` została wydzielona do :mod:`rezyser_ai`.
        Tu zostaje tylko „cienki kontroler": przeniesienie wyniku
        z wątku tła z powrotem do GUI (zapis do pliku / okno dialogowe /
        komunikat błędu).

        Args:
            przepis:     Aktualnie wybrany tryb pracy (Burza / Skrypt /
                         Audiobook) załadowany z YAML-a.
            snapshot:    Niezmienny snapshot stanu projektu (``full_story``,
                         ``summary_text``, ``world_lore``, ``nazwa``).
            user_text:   Treść instrukcji użytkownika z pola „Instrukcje".
            nazwa:       Nazwa projektu (do dopisania do pliku po odpowiedzi).
            tryb_zapisu: Odpowiednik ``przepis.zapis_do_pliku`` — powielony
                         jako argument, by nie musieć dodatkowo czytać z
                         ``przepis`` w workerze (drobna optymalizacja).
        """
        try:
            wynik = rai.generuj_fragment(
                klient=self._client,
                przepis=przepis,
                snapshot=snapshot,
                user_text=user_text,
                on_postep=None,  # pasek postępu w _on_wyslij nie jest jeszcze wpięty
            )
        except openai.RateLimitError:
            wx.CallAfter(
                self._on_wyslij_error,
                "Brak kredytów OpenAI! Doładuj konto i spróbuj ponownie.",
            )
            return
        except Exception as exc:  # noqa: BLE001
            wx.CallAfter(self._on_wyslij_error, str(exc))
            return

        # AI odrzuciło prompt – NIE zapisujemy nic do pliku historii.
        if wynik.odrzucone:
            wx.CallAfter(
                self._on_wyslij_error,
                "AI odrzuciło prompt (wykryto tag [ODRZUCENIE_AI]).\n"
                "Tekst NIE zostanie zapisany do pliku historii.\n"
                "Możesz zmodyfikować instrukcję i spróbować ponownie.",
            )
            return

        # Streszczenie wyciągnięte w Burzy Mózgów – aktualizujemy Pamięć Długotrwałą.
        if wynik.nowe_streszczenie:
            wx.CallAfter(
                self._on_wyslij_zapisz_streszczenie, wynik.nowe_streszczenie,
            )

        # Zapis do pliku (Skrypt / Audiobook) lub dialog-only (Burza Mózgów).
        if tryb_zapisu:
            wx.CallAfter(self._on_wyslij_done_zapis, wynik.tekst_odpowiedzi, nazwa)
        else:
            wx.CallAfter(self._on_wyslij_done_burza, wynik.tekst_odpowiedzi)


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
    # Helper: wspólna walidacja nazwy projektu dla operacji strukturalnych
    # ------------------------------------------------------------------
    def _wymagaj_nazwy_lub_alert(self) -> str | None:
        """Zwraca ``nazwa`` z pola lub ``None`` (po pokazaniu alertu i ustawieniu fokusa).

        Refaktor 13.0: wcześniej każda z pięciu metod ``_on_wstaw_*``
        powtarzała identycznych 10 linii walidacji. Teraz jedno wywołanie
        na początku handlera załatwia sprawę. Dodatkowo, po odnalezieniu
        nazwy synchronizujemy ją z ``self._projekt.nazwa_pliku``, by
        ``ProjektRezysera._wymagaj_nazwy()`` mógł przejść bez wyjątku.
        """
        nazwa = self._txt_file_name.GetValue().strip()
        if not nazwa:
            wx.MessageBox(
                "Podaj nazwę pliku projektu przed wstawianiem struktury.",
                "Brak nazwy",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            self._txt_file_name.SetFocus()
            return None
        if self._projekt.nazwa_pliku != nazwa:
            self._projekt.nazwa_pliku = nazwa
        return nazwa

    def _po_wstawieniu_struktury(self, tytul: str, komunikat: str) -> None:
        """Wspólny „post-wstawienie": odśwież UI, zapisz tryb, pokaż MessageBox.

        Używane przez wszystkie pięć handlerów ``_on_wstaw_*``. Nie
        odczytuje już wartości z ``ProjektRezysera`` – te wywołane wcześniej
        przez delegację ``self._projekt.wstaw_*()`` zaktualizowały stan.
        """
        self._txt_full_story.SetValue(self.full_story)
        self._zapisz_tryb_projektu()
        self._refresh_ui_state()
        wx.MessageBox(komunikat, tytul, wx.OK | wx.ICON_INFORMATION, self)

    # ------------------------------------------------------------------
    # Wstawianie Prologu
    # ------------------------------------------------------------------
    def _on_wstaw_prolog(self, _event: wx.Event) -> None:
        """Wstawia nagłówek 'Prolog' do historii i pliku projektu.

        Deleguje do ``self._projekt.wstaw_prolog()`` – cała logika
        (``full_story += header``, mode="w" dla pliku, licznik) żyje
        w ``core_rezyser.ProjektRezysera``.
        """
        if self._wymagaj_nazwy_lub_alert() is None:
            return
        try:
            self._projekt.wstaw_prolog()
        except Exception as exc:  # noqa: BLE001
            wx.MessageBox(
                f"Błąd wstawiania Prologu:\n{exc}",
                "Błąd zapisu",
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return
        self._po_wstawieniu_struktury(
            "Prolog wstawiony",
            "Wstawiono nagłówek: Prolog.\n\nRozpocznij pisanie treści prologu.",
        )

    # ------------------------------------------------------------------
    # Wstawianie Epilogu
    # ------------------------------------------------------------------
    def _on_wstaw_epilog(self, _event: wx.Event) -> None:
        """Wstawia nagłówek 'Epilog' na końcu historii i pliku projektu.

        Deleguje do ``self._projekt.wstaw_epilog()``.
        """
        if self._wymagaj_nazwy_lub_alert() is None:
            return
        try:
            self._projekt.wstaw_epilog()
        except Exception as exc:  # noqa: BLE001
            wx.MessageBox(
                f"Błąd wstawiania Epilogu:\n{exc}",
                "Błąd zapisu",
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return
        self._po_wstawieniu_struktury(
            "Epilog wstawiony",
            "Wstawiono nagłówek: Epilog.\n\n"
            "Dalsze generowanie treści po Epilogu jest zablokowane.",
        )

    # ------------------------------------------------------------------
    # Wstawianie cięcia Rozdziału (Audiobook)
    # ------------------------------------------------------------------
    def _on_wstaw_rozdzial(self, _event: wx.Event) -> None:
        """Wstawia nagłówek 'Rozdział N' do historii i pliku (tryb Audiobook).

        Deleguje do ``self._projekt.wstaw_rozdzial()`` – licznik
        ``chapter_counter`` jest inkrementowany wewnątrz modelu.
        """
        if self._wymagaj_nazwy_lub_alert() is None:
            return
        try:
            naglowek = self._projekt.wstaw_rozdzial()
        except Exception as exc:  # noqa: BLE001
            wx.MessageBox(
                f"Błąd wstawiania rozdziału:\n{exc}",
                "Błąd zapisu",
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return
        self._po_wstawieniu_struktury(
            "Cięcie rozdziału wstawione",
            f"Wstawiono nagłówek: {naglowek}.",
        )

    # ------------------------------------------------------------------
    # Wstawianie Aktu (Skrypt)
    # ------------------------------------------------------------------
    def _on_wstaw_akt(self, _event: wx.Event) -> None:
        """Wstawia 'Akt N' + automatycznie 'Scena 1' (tryb Skrypt).

        Deleguje do ``self._projekt.wstaw_akt()`` – metoda zwraca
        krotkę ``(akt, scena)``, licznik aktów inkrementuje, licznik
        scen ustawia na 2 (bo Scena 1 została właśnie wstawiona).
        """
        if self._wymagaj_nazwy_lub_alert() is None:
            return
        try:
            akt_nag, scena_nag = self._projekt.wstaw_akt()
        except Exception as exc:  # noqa: BLE001
            wx.MessageBox(
                f"Błąd wstawiania aktu:\n{exc}",
                "Błąd zapisu",
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return
        self._po_wstawieniu_struktury(
            "Akt wstawiony",
            f"Wstawiono: {akt_nag} oraz {scena_nag}.",
        )

    # ------------------------------------------------------------------
    # Wstawianie Sceny (Skrypt)
    # ------------------------------------------------------------------
    def _on_wstaw_scena(self, _event: wx.Event) -> None:
        """Wstawia 'Scena N' do historii i pliku (tryb Skrypt).

        Deleguje do ``self._projekt.wstaw_scena()``.
        """
        if self._wymagaj_nazwy_lub_alert() is None:
            return
        try:
            scena_nag = self._projekt.wstaw_scena()
        except Exception as exc:  # noqa: BLE001
            wx.MessageBox(
                f"Błąd wstawiania sceny:\n{exc}",
                "Błąd zapisu",
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return
        self._po_wstawieniu_struktury(
            "Scena wstawiona",
            f"Wstawiono nagłówek: {scena_nag}.",
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
        """Wywołuje ``rezyser_ai.nadaj_tytuly_rozdzialom`` i rozsyła wyniki.

        Refaktor 13.0: cała iteracja po rozdziałach, wywołania OpenAI
        i logika obsługi RateLimitError / innych wyjątków została
        przeniesiona do :func:`rezyser_ai.nadaj_tytuly_rozdzialom`.
        Tutaj zostaje tylko: wybór przepisu z YAML-a, przekazanie
        callbacka postępu przez ``wx.CallAfter`` i finalna prezentacja
        wyników (pełnych lub częściowych przy błędzie).
        """
        if self._przepis_tytuly is None:
            wx.CallAfter(
                self._on_tytuly_error,
                "Nie znaleziono przepisu 'tytuly' w YAML "
                "(dictionaries/pl/rezyser/postprod_tytuly.yaml).\n"
                "Bez niego postprodukcja tytułów rozdziałów jest niedostępna.",
            )
            return

        def _cb(msg: str, percent: int) -> None:
            # Callback tłumaczący progress z rezyser_ai na wx.CallAfter –
            # bezpieczne modyfikowanie GUI z wątku tła.
            wx.CallAfter(self._update_tytuly_progress, msg, percent)

        wynik = rai.nadaj_tytuly_rozdzialom(
            klient=self._client,
            przepis_tytuly=self._przepis_tytuly,
            pelny_tekst=pelny_tekst,
            on_postep=_cb,
        )

        if wynik.przerwano_bledem:
            # Przerwanie błędem – pokazujemy blad + ewentualne
            # częściowe tytuły wygenerowane przed awarią.
            wx.CallAfter(
                self._on_tytuly_error,
                wynik.blad or "Nieznany błąd podczas tytułowania.",
                list(wynik.tytuly),
            )
            return

        wx.CallAfter(self._show_titles_dialog, "\n".join(wynik.tytuly))


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
    # Zapis trybu twórczego do pliku metadanych projektu (thin wrapper)
    # ------------------------------------------------------------------
    def _zapisz_tryb_projektu(self) -> None:
        """Thin wrapper: deleguje do ``self._projekt.zapisz_tryb_tworczy``.

        Plik ``runtime/skrypty/<nazwa>.mode`` przywraca właściwy tryb po
        ponownym wczytaniu projektu. Cichy fail – metadata nie jest
        krytyczna dla działania programu.
        """
        nazwa    = self._txt_file_name.GetValue().strip()
        tryb_idx = self._rb_mode.GetSelection()
        if not nazwa:
            return
        # Upewnij się, że projekt zna nazwę przed zapisem – nawet gdy
        # użytkownik dopiero co wpisał nazwę w pole i nie wczytał jeszcze
        # projektu z dysku.
        if self._projekt.nazwa_pliku != nazwa:
            self._projekt.nazwa_pliku = nazwa
        self._projekt.zapisz_tryb_tworczy(tryb_idx)
