"""
gui_rezyser.py – Cienka warstwa widoku panelu „Reżyser" (wxPython).

Po refaktorze 13.0 plik zawiera WYŁĄCZNIE:
    • Definicje widgetów wxPython (budowane przez metody ``_zbuduj_*``).
    • Handlery zdarzeń GUI (``_on_*``).
    • Worker-threads przekazujące pracę do :mod:`rezyser_ai`
      (``_wyslij_worker``, ``_tytuly_worker``).
    • Property-shimy (``full_story``, ``summary_text``, …) delegujące do
      ``self._projekt``.

Logika biznesowa (stan projektu, przepisy, wywołania OpenAI) żyje w:
    • :mod:`core_rezyser`     – ``ProjektRezysera`` + silnik fonetyczny.
    • :mod:`przepisy_rezysera` – loader YAML-i z ``dictionaries/pl/rezyser/``.
    • :mod:`rezyser_ai`       – ``generuj_fragment``, ``nadaj_tytuly_rozdzialom``.

Panel dziedziczy po :class:`wx.Panel`; podpinany do ``MainFrame`` z ``main.py``.

Główne sekcje UI (zobacz metody ``_zbuduj_*``):
    • BLOK A – nagłówek + opis narzędzia.
    • BLOK B – pole nazwy pliku + przyciski wczytaj/wyczyść/reset.
    • BLOK C – sidebar: Księga Świata + Pamięć Długotrwała (lewa kolumna).
    • BLOK D – obszar roboczy (prawa kolumna, kompozycja pod-bloków).
    • BLOK E – panel struktury (Prolog/Epilog/Akt/Scena/Rozdział).
    • BLOK F – panel postprodukcji (tytułowanie rozdziałów AI).
    • BLOK G – wskaźnik okna kontekstowego AI (Gauge + status).
"""

from __future__ import annotations

import os
import threading

import openai
from dotenv import load_dotenv

import wx

# Refaktor wersji 13.0: logika modelu, przepisy i silnik AI są wydzielone
# z tego pliku. Panel zostaje cienką warstwą widoku wxPython.
import core_rezyser as cr
import przepisy_rezysera as pr
import rezyser_ai as rai



class RezyserPanel(wx.Panel):
    """Panel modułu „Reżyser Audio GPT" — cienka warstwa widoku wxPython.

    Trzy tryby pracy (AI OpenAI gpt-4o) wczytywane są dynamicznie z YAML-i
    (``dictionaries/pl/rezyser/``) przez :mod:`przepisy_rezysera`:

        * Burza Mózgów – planowanie fabuły, 3 opcje + prompty (BEZ zapisu).
        * Skrypt       – surowy skrypt dźwiękowy [SFX] + [Postać] (ZAPIS).
        * Audiobook    – tradycyjna proza literacka (ZAPIS).

    Dodanie nowego trybu = nowy plik YAML + restart aplikacji. Kod
    Pythona nie wymaga zmian.

    Stan projektu (historia, streszczenie, Księga Świata, liczniki) żyje
    w ``self._projekt`` (:class:`core_rezyser.ProjektRezysera`); atrybuty
    typu ``self.full_story`` są property-shimami delegującymi do modelu.

    Wywołania OpenAI realizowane są w wątkach tła (``threading.Thread``)
    z wynikami przekazywanymi do GUI przez ``wx.CallAfter``.
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

    # --------------------------------------------------------------
    # PROMPT ARCHITEKTA – gotowy tekst do wklejenia w zewnętrznego chatbota.
    # Wersja 13.0: przeniesiony z instrukcja.txt bezpośrednio do GUI, by
    # użytkownik (zwłaszcza korzystający z NVDA) nie musiał go wyszukiwać
    # w pliku tekstowym. Dialog wywołany przez przycisk „📖 Prompt
    # Architekta dla AI…” pokazuje ten tekst w polu READONLY gotowym do
    # skopiowania (Ctrl+A → Ctrl+C lub przycisk „Skopiuj do schowka").
    #
    # Jeśli kiedykolwiek zmienisz tę treść — zaktualizuj też sekcję
    # „KROK 7" w ``instrukcja.txt`` (jedno zdanie wprowadzające),
    # żeby dokumentacja dla end-userów nie odbiegała od stanu GUI.
    # --------------------------------------------------------------
    PROMPT_ARCHITEKTA = (
        "Jesteś wybitnym architektem światów (Worldbuilder) i konsultantem "
        "literackim. Mam luźny pomysł na fabułę: [TUTAJ WPISZ SWÓJ POMYSŁ]. "
        "Twoim zadaniem jest rozbudowanie tego do profesjonalnej "
        "„Księgi Świata”.\n"
        "Dostosuj ton i zasady do mojego pomysłu. Unikaj tanich, "
        "baśniowych skrótów i klisz AI.\n\n"
        "ZASADY FORMATOWANIA (KRYTYCZNE):\n"
        "Musisz zwrócić odpowiedź w dwóch oddzielnych częściach:\n\n"
        "CZĘŚĆ 1: KSIĘGA ŚWIATA\n"
        "Tę część musisz bezwzględnie zamknąć w JEDNYM bloku kodu Markdown "
        "(użyj znaczników ```markdown na początku i ``` na końcu). "
        "Wewnątrz bloku kodu zastosuj te reguły:\n"
        "1. Rozpocznij od emotki otwartej książki i roboczego tytułu, "
        "np. 📖 Księga Świata: [Tytuł].\n"
        "2. Używaj pojedynczego hashtagu (#) dla głównych sekcji "
        "(np. # Zasady Świata, # Postacie).\n"
        "3. Używaj podwójnego hashtagu (##) dla podsekcji.\n"
        "4. Używaj myślników (-) do tworzenia czytelnych list.\n"
        "5. Używaj podwójnych gwiazdek (**tekst**), by pogrubić absolutne, "
        "nienaruszalne zasady (np. **Bohater NIGDY nie kłamie**).\n"
        "6. Opisz psychologię postaci, ich największe wady i motywacje. "
        "W przypadku postaci obcojęzycznych, dodaj informację o akcencie "
        "bezpośrednio przy tagu, np. `[Speaker 1: Imię] - sepleni i ma "
        "akcent francuski`. **Wskazówka techniczna:** Użycie słowa "
        "kluczowego `akcent` jest bezwzględnie wymagane, ponieważ to na "
        "jego podstawie zewnętrzny skrypt aplikacji automatycznie wykrywa "
        "i nakłada poprawne reguły fonetyczne na dialogi danej postaci.\n\n"
        "CZĘŚĆ 2: REKOMENDACJA TRYBU\n"
        "Tę część umieść POZA blokiem kodu, jako zwykły tekst pod spodem. "
        "Doradź mi, który z trybów mojej aplikacji będzie najlepszy do "
        "realizacji tego pomysłu: 🎬 Tryb Surowego Skryptu (słuchowiska, "
        "SFX, fonetyka), czy 📖 Tryb Tradycyjnego Audiobooka (klasyczna "
        "proza literacka)."
    )

    ENV_FILENAME = "golden_key.env"
    SKRYPTY_DIR  = "skrypty"


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
    # Budowanie interfejsu (kompozer)
    # ------------------------------------------------------------------
    # Refaktor 13.0/4F: dawniej monolityczny ``_build_ui`` został podzielony
    # na prywatne metody ``_zbuduj_*``, jedna na każdy logiczny blok.
    # Każda taka metoda:
    #   1. Tworzy swoje widżety jako bezpośrednie dzieci ``self`` lub
    #      dedykowanego sub-panelu (``self._pnl_struktura`` /
    #      ``self._pnl_postprodukcja``).
    #   2. Zwraca gotowy ``wx.BoxSizer`` z logicznym rozmieszczeniem.
    # Dzięki temu:
    #   * Każdy blok UI można przeczytać osobno (~30-50 linii).
    #   * Łatwiej eksperymentować z układem w konkretnej sekcji bez
    #     ryzyka, że zepsuje się reszta.
    #   * Tab order zachowany, bo kolejność WYWOŁAŃ metod pozostaje
    #     identyczna z oryginałem (widżety są tworzone w tej samej
    #     kolejności co przed refaktorem).
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Buduje cały interfejs panelu poprzez wywołanie metod ``_zbuduj_*``.

        A11y: wszystkie widżety są bezpośrednimi dziećmi RezyserPanel
        (poza dwoma sub-panelami struktury i postprodukcji). Kolejność
        tabulatora = kolejność tworzenia widżetów w poszczególnych
        ``_zbuduj_*``.

        Pożądana kolejność Tab:
            opis → nazwa_pliku → wczytaj → wyczyść → hard_reset
            → ksiega_swiata → zapisz_ksiege
            → pamiec_dlugotrwala → zapisz_pamiec
            → radiobox_trybu → [przyciski struktury]
            → podgląd_historii → instrukcje → wyslij
            → [przycisk postprodukcji] → wskaźnik_pamięci_modelu
        """
        BORDER = 8

        # Kolejność wywołań ≡ kolejność tworzenia widżetów ≡ tab order.
        # UWAGA: pasek pliku (BLOK B) MUSI być utworzony PRZED sidebarem (BLOK C),
        # bo w kolejności tabulatora: nazwa_pliku → wczytaj → wyczyść → hard_reset
        # → ksiega_swiata → zapisz_ksiege → pamiec → zapisz_pamiec. Sidebar
        # wizualnie jest w LEWEJ kolumnie, ale jego widgety tworzone są
        # dopiero w trzeciej kolejności.
        top_sizer         = self._zbuduj_naglowek(BORDER)
        pasek_pliku_sizer = self._zbuduj_pasek_pliku(BORDER)
        sidebar_sizer     = self._zbuduj_sidebar(BORDER)
        main_area_sizer   = self._zbuduj_obszar_roboczy(BORDER, pasek_pliku_sizer)

        # Pionowy separator między lewą a prawą kolumną.
        v_sep = wx.StaticLine(self, style=wx.LI_VERTICAL)


        two_col_sizer = wx.BoxSizer(wx.HORIZONTAL)
        two_col_sizer.Add(sidebar_sizer,   proportion=1, flag=wx.EXPAND | wx.ALL, border=4)
        two_col_sizer.Add(v_sep,                         flag=wx.EXPAND | wx.TOP | wx.BOTTOM,
                          border=8)
        two_col_sizer.Add(main_area_sizer, proportion=3, flag=wx.EXPAND | wx.ALL, border=4)

        root_sizer = wx.BoxSizer(wx.VERTICAL)
        root_sizer.Add(top_sizer,     flag=wx.EXPAND)
        root_sizer.Add(two_col_sizer, proportion=1, flag=wx.EXPAND)

        self.SetSizer(root_sizer)

    # ------------------------------------------------------------------
    # BLOK A – Nagłówek panelu (tytuł + opis narzędzia + separator)
    # ------------------------------------------------------------------
    def _zbuduj_naglowek(self, BORDER: int) -> wx.BoxSizer:
        """Buduje nagłówek Reżysera (tytuł + opis narzędzia + separator)."""
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

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(heading, flag=wx.ALL, border=BORDER)
        sizer.Add(
            self._description,
            flag=wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            border=BORDER,
        )
        sizer.Add(
            wx.StaticLine(self),
            flag=wx.EXPAND | wx.LEFT | wx.RIGHT,
            border=BORDER,
        )
        return sizer

    # ------------------------------------------------------------------
    # BLOK B – Pole nazwy pliku + przyciski wczytaj / wyczyść / reset
    # ------------------------------------------------------------------
    def _zbuduj_pasek_pliku(self, BORDER: int) -> wx.BoxSizer:
        """Buduje pasek: etykieta + pole nazwy pliku + 3 przyciski (wiersz)."""
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

        file_row = wx.BoxSizer(wx.HORIZONTAL)
        file_row.Add(self._txt_file_name,     proportion=1, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=6)
        file_row.Add(self._btn_load,          flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=4)
        file_row.Add(self._btn_clear_current, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=4)
        file_row.Add(self._btn_hard_reset,    flag=wx.ALIGN_CENTER_VERTICAL)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(lbl_file, flag=wx.LEFT | wx.RIGHT | wx.TOP, border=BORDER)
        sizer.Add(file_row, flag=wx.EXPAND | wx.ALL,          border=BORDER)
        return sizer

    # ------------------------------------------------------------------
    # BLOK C – Sidebar: Księga Świata + Pamięć Długotrwała (lewa kolumna)
    # ------------------------------------------------------------------
    def _zbuduj_sidebar(self, BORDER: int) -> wx.BoxSizer:
        """Buduje sidebar (lewą kolumnę): Księga Świata + Pamięć Długotrwała.

        Uwaga: sidebar jest tworzony JAKO TRZECI (po nagłówku i pasku pliku),
        by zachować tab order: nazwa_pliku → wczytaj → ... → ksiega_swiata.
        Wizualnie pojawia się jednak w lewej kolumnie two_col_sizer.
        """
        lbl_sb_heading = wx.StaticText(self, label="📖 Pasek Boczny projektu")
        sbf = lbl_sb_heading.GetFont()
        sbf.SetPointSize(11)
        sbf.MakeBold()
        lbl_sb_heading.SetFont(sbf)

        lbl_ksiega = wx.StaticText(self, label="Księga Świata – Zasady i Postacie:")

        # ── [TAB 6] Księga Świata – duże pole wieloliniowe ────────────
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

        # ── [TAB 7] Zapisz Księgę ─────────────────────────────────────
        self._btn_zapisz_ksiege = wx.Button(self, label="💾 Zapisz Księgę na stałe")
        self._btn_zapisz_ksiege.SetToolTip(
            "Zapisuje Księgę Świata do pliku: skrypty/<nazwa>.md\n"
            "Wymaga podania nazwy pliku projektu."
        )

        # ── [TAB 7a] Prompt Architekta (skopiuj do zewnętrznego AI) ───
        # Refaktor 13.0: prompt architekta przeniesiony z instrukcja.txt
        # wprost do GUI jako przycisk + dialog z polem do skopiowania.
        # Wzorzec A11y identyczny jak dla ``WynikKreatoraDialog`` w
        # Managerze Reguł – pełny tekst w wx.TextCtrl (TE_READONLY),
        # przycisk "Skopiuj do schowka", NVDA od razu czyta zawartość.
        self._btn_prompt_architekta = wx.Button(
            self,
            label="📖 Prompt Architekta dla AI…",
            name="Przycisk Pokaż Prompt Architekta dla zewnętrznego chatbota",
        )
        self._btn_prompt_architekta.SetToolTip(
            "Otwiera okno z gotowym promptem dla zewnętrznego chatbota "
            "(ChatGPT, Claude).\n"
            "Wklej swój pomysł fabularny, a AI wygeneruje profesjonalną "
            "Księgę Świata sformatowaną w Markdown – do wklejenia do pola "
            "„Księga Świata” powyżej."
        )


        lbl_pamiec = wx.StaticText(self, label="🧠 Pamięć Długotrwała (Streszczenie):")

        # ── [TAB 8] Pamięć Długotrwała ────────────────────────────────
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

        # ── [TAB 9] Zapisz Streszczenie ──────────────────────────────
        self._btn_zapisz_pamiec = wx.Button(self, label="💾 Zapisz Streszczenie")
        self._btn_zapisz_pamiec.SetToolTip(
            "Zapisuje streszczenie do pliku: skrypty/<nazwa>_streszczenie.txt\n"
            "Po zapisie możesz bezpiecznie wyczyścić pamięć bieżącą."
        )

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(lbl_sb_heading, flag=wx.ALL, border=BORDER)
        sizer.Add(lbl_ksiega,     flag=wx.LEFT | wx.RIGHT | wx.TOP, border=BORDER)
        sizer.Add(
            self._txt_ksiega_swiata,
            proportion=2,
            flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP,
            border=BORDER,
        )
        sizer.Add(self._btn_zapisz_ksiege, flag=wx.ALL, border=BORDER)
        sizer.Add(
            self._btn_prompt_architekta,
            flag=wx.LEFT | wx.RIGHT | wx.BOTTOM,
            border=BORDER,
        )
        sizer.Add(
            wx.StaticLine(self),
            flag=wx.EXPAND | wx.LEFT | wx.RIGHT,
            border=BORDER,
        )
        sizer.Add(lbl_pamiec, flag=wx.LEFT | wx.RIGHT | wx.TOP, border=BORDER)

        sizer.Add(
            self._txt_pamiec,
            proportion=1,
            flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP,
            border=BORDER,
        )
        sizer.Add(self._btn_zapisz_pamiec, flag=wx.ALL, border=BORDER)
        return sizer

    # ------------------------------------------------------------------
    # BLOK D – Obszar roboczy (prawa kolumna, kompozycja)
    # ------------------------------------------------------------------
    def _zbuduj_obszar_roboczy(
        self,
        BORDER: int,
        pasek_pliku_sizer: wx.BoxSizer,
    ) -> wx.BoxSizer:
        """Buduje prawą kolumnę: pasek pliku + tryb + struktura + wskaźnik pamięci
        + podgląd historii + instrukcje + postprodukcja.

        Args:
            BORDER:             Wspólna wartość marginesu w pikselach.
            pasek_pliku_sizer:  Gotowy sizer paska pliku, zbudowany wcześniej
                                przez ``_zbuduj_pasek_pliku`` — sidebar musi
                                być utworzony MIĘDZY paskiem pliku a resztą
                                obszaru roboczego, więc pasek_pliku przychodzi
                                z zewnątrz.

        A11y: kolejność tworzenia widżetów wewnątrz tej metody to
        RadioBox → panel struktury → podgląd historii → instrukcje →
        panel postprodukcji → wskaźnik pamięci. To wyznacza tab order
        DALSZEJ części obszaru roboczego (po pasku pliku i sidebarze).
        """
        lbl_main_heading = wx.StaticText(self, label="🎬 Obszar Roboczy")
        mf = lbl_main_heading.GetFont()
        mf.SetPointSize(11)
        mf.MakeBold()
        lbl_main_heading.SetFont(mf)

        # Kolejność wywołań = kolejność tworzenia widżetów = tab order.
        # Pasek pliku jest już gotowy (przekazany z ``_build_ui``), tworzymy tu:
        # tryb → struktura → podgląd → instrukcje → postprodukcja → wskaźnik.
        radiobox_sizer      = self._zbuduj_radiobox_trybu(BORDER)
        panel_struktury     = self._zbuduj_panel_struktury(BORDER)
        podglad_sizer       = self._zbuduj_podglad_historii(BORDER)
        pole_instrukcji     = self._zbuduj_pole_instrukcji(BORDER)
        panel_postprodukcji = self._zbuduj_panel_postprodukcji(BORDER)
        wskaznik_sizer      = self._zbuduj_wskaznik_pamieci_modelu(BORDER)


        sep = lambda: wx.StaticLine(self)   # noqa: E731 - krótka fabryka separatorów

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(lbl_main_heading, flag=wx.ALL, border=BORDER)
        sizer.Add(pasek_pliku_sizer, flag=wx.EXPAND)
        sizer.Add(sep(), flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=BORDER)
        sizer.Add(radiobox_sizer, flag=wx.EXPAND)
        sizer.Add(panel_struktury, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=BORDER)
        sizer.Add(sep(), flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=BORDER)
        sizer.Add(wskaznik_sizer, flag=wx.EXPAND)
        sizer.Add(sep(), flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=BORDER)
        sizer.Add(podglad_sizer, proportion=1, flag=wx.EXPAND)
        sizer.Add(sep(), flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=BORDER)
        sizer.Add(pole_instrukcji, flag=wx.EXPAND)
        sizer.Add(sep(), flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=BORDER)
        sizer.Add(panel_postprodukcji, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=BORDER)
        return sizer

    # ------------------------------------------------------------------
    # BLOK D.1 – RadioBox wyboru trybu pracy
    # ------------------------------------------------------------------
    def _zbuduj_radiobox_trybu(self, BORDER: int) -> wx.BoxSizer:
        """Buduje RadioBox z trybami pracy załadowanymi z YAML-i."""
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

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self._rb_mode, flag=wx.EXPAND | wx.ALL, border=BORDER)
        return sizer

    # ------------------------------------------------------------------
    # BLOK E – Panel Zarządzania Strukturą (dynamicznie ukrywany)
    # ------------------------------------------------------------------
    def _zbuduj_panel_struktury(self, BORDER: int) -> wx.Panel:
        """Buduje ``self._pnl_struktura`` z przyciskami Prolog/Epilog/Rozdział/Akt/Scena."""
        self._pnl_struktura = wx.Panel(self)

        lbl_struktura = wx.StaticText(self._pnl_struktura, label="✂️ Zarządzanie Strukturą")
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

        prolog_epilog_row = wx.BoxSizer(wx.HORIZONTAL)
        prolog_epilog_row.Add(self._btn_prolog, flag=wx.RIGHT, border=6)
        prolog_epilog_row.Add(self._btn_epilog)

        akt_scena_row = wx.BoxSizer(wx.HORIZONTAL)
        akt_scena_row.Add(self._btn_akt, flag=wx.RIGHT, border=6)
        akt_scena_row.Add(self._btn_scena)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(lbl_struktura,      flag=wx.ALL,                         border=BORDER)
        sizer.Add(prolog_epilog_row,  flag=wx.LEFT | wx.RIGHT | wx.BOTTOM, border=BORDER)
        sizer.Add(self._btn_rozdzial, flag=wx.LEFT | wx.RIGHT | wx.BOTTOM, border=BORDER)
        sizer.Add(akt_scena_row,      flag=wx.LEFT | wx.RIGHT | wx.BOTTOM, border=BORDER)
        self._pnl_struktura.SetSizer(sizer)
        return self._pnl_struktura

    # ------------------------------------------------------------------
    # BLOK E.1 – Podgląd pełnej historii (TextCtrl read-only)
    # ------------------------------------------------------------------
    def _zbuduj_podglad_historii(self, BORDER: int) -> wx.BoxSizer:
        """Buduje podgląd ``full_story`` (TextCtrl read-only) + etykietę."""
        lbl_full_story = wx.StaticText(
            self,
            label="Bieżąca historia w pamięci (tylko do odczytu – nawiguj strzałkami):",
        )

        # ── [TAB] Podgląd full_story ──────────────────────────────────
        self._txt_full_story = wx.TextCtrl(
            self,
            style=wx.TE_MULTILINE | wx.TE_READONLY,
            name="Podgląd pełnej historii w pamięci – tylko do odczytu",
        )
        self._txt_full_story.SetHint("(pamięć jest pusta – wczytaj projekt lub zacznij nowy)")

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(lbl_full_story, flag=wx.LEFT | wx.RIGHT | wx.TOP, border=BORDER)
        sizer.Add(
            self._txt_full_story,
            proportion=1,
            flag=wx.EXPAND | wx.ALL,
            border=BORDER,
        )
        return sizer

    # ------------------------------------------------------------------
    # BLOK E.2 – Pole instrukcji dla AI + przycisk Wyślij
    # ------------------------------------------------------------------
    def _zbuduj_pole_instrukcji(self, BORDER: int) -> wx.BoxSizer:
        """Buduje etykietę + pole instrukcji dla AI + przycisk 'Wyślij'."""
        lbl_user_input = wx.StaticText(
            self,
            label=(
                "Instrukcje do kolejnego fragmentu "
                "(wpisz 'streszczenie', by wymusić zapis do Pamięci Długotrwałej):"
            ),
        )

        # ── [TAB] Pole instrukcji ─────────────────────────────────────
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

        # ── [TAB] Wyślij do AI ────────────────────────────────────────
        self._btn_wyslij = wx.Button(self, label="Wyślij do AI")
        self._btn_wyslij.SetToolTip(
            "Wysyła instrukcje do modelu gpt-4o i dopisuje odpowiedź do historii.\n"
            "Wymaga aktywnego klucza API i uzupełnionej Księgi Świata."
        )

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(lbl_user_input,       flag=wx.LEFT | wx.RIGHT | wx.TOP, border=BORDER)
        sizer.Add(self._txt_user_input, flag=wx.EXPAND | wx.ALL,          border=BORDER)
        sizer.Add(self._btn_wyslij,     flag=wx.LEFT | wx.BOTTOM | wx.TOP, border=BORDER)
        return sizer

    # ------------------------------------------------------------------
    # BLOK F – Panel Postprodukcji (dynamicznie ukrywany)
    # ------------------------------------------------------------------
    def _zbuduj_panel_postprodukcji(self, BORDER: int) -> wx.Panel:
        """Buduje ``self._pnl_postprodukcja`` (tytułowanie rozdziałów AI)."""
        self._pnl_postprodukcja = wx.Panel(self)

        lbl_postprod = wx.StaticText(self._pnl_postprodukcja, label="🎛️ Postprodukcja")
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

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(lbl_postprod,              flag=wx.ALL,                              border=BORDER)
        sizer.Add(lbl_tytuly_info,           flag=wx.LEFT | wx.RIGHT | wx.BOTTOM,      border=BORDER)
        sizer.Add(self._btn_tytuly_ai,       flag=wx.LEFT | wx.BOTTOM,                 border=BORDER)
        sizer.Add(
            self._gauge_postprod,
            flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP,
            border=BORDER,
        )
        sizer.Add(self._lbl_postprod_status, flag=wx.LEFT | wx.BOTTOM,                 border=BORDER)
        self._pnl_postprodukcja.SetSizer(sizer)
        return self._pnl_postprodukcja

    # ------------------------------------------------------------------
    # BLOK G – Wskaźnik okna kontekstowego AI (Gauge + status)
    # ------------------------------------------------------------------
    def _zbuduj_wskaznik_pamieci_modelu(self, BORDER: int) -> wx.BoxSizer:
        """Buduje wskaźnik pamięci modelu (nagłówek + Gauge + status read-only)."""
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

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(lbl_kontekst, flag=wx.LEFT | wx.RIGHT | wx.TOP, border=BORDER)
        sizer.Add(
            self._gauge_kontekst,
            flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP,
            border=BORDER,
        )
        sizer.Add(
            self._lbl_kontekst_status,
            flag=wx.EXPAND | wx.LEFT | wx.RIGHT,
            border=BORDER,
        )
        return sizer


    # ------------------------------------------------------------------
    # Podpięcie zdarzeń
    # ------------------------------------------------------------------
    def _bind_events(self) -> None:
        self._btn_load.Bind(wx.EVT_BUTTON,          self._on_load)
        self._btn_clear_current.Bind(wx.EVT_BUTTON, self._on_clear_current)
        self._btn_hard_reset.Bind(wx.EVT_BUTTON,    self._on_hard_reset)
        self._btn_zapisz_ksiege.Bind(wx.EVT_BUTTON, self._on_zapisz_ksiege)
        self._btn_prompt_architekta.Bind(wx.EVT_BUTTON, self._on_prompt_architekta)
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
    # Prompt Architekta – dialog z gotowym promptem do skopiowania
    # ------------------------------------------------------------------
    def _on_prompt_architekta(self, _event: wx.Event) -> None:
        """Otwiera okno dialogowe z treścią ``PROMPT_ARCHITEKTA`` (A11y-friendly).

        Wzorzec dialogu identyczny z :class:`gui_manager_regul.WynikKreatoraDialog`
        – TextCtrl READONLY + przycisk "Skopiuj do schowka" + opis działania.
        Dzięki temu użytkownik (zwłaszcza z NVDA) może wybrać tekst strzałkami,
        skopiować Ctrl+A/Ctrl+C lub przyciskiem — bez wracania do instrukcji.
        """
        dlg = wx.Dialog(
            self,
            title="Prompt Architekta – wklej do zewnętrznego chatbota",
            size=(720, 560),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Nagłówek: krótkie wyjaśnienie po co i jak.
        lbl_head = wx.TextCtrl(
            dlg,
            value=(
                "Ten gotowy prompt wklej do zewnętrznego chatbota "
                "(np. darmowego ChatGPT albo Claude) i zastąp tekst "
                "„[TUTAJ WPISZ SWÓJ POMYSŁ]” własnym zalążkiem fabuły.\n\n"
                "AI zwróci ci gotową Księgę Świata w bloku kodu Markdown — "
                "skopiuj jej zawartość (bez otaczających znaczników ```) "
                "i wklej do pola „Księga Świata” powyżej, a następnie "
                "kliknij „Zapisz Księgę na stałe”."
            ),
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.NO_BORDER,
            name="Instrukcja korzystania z Promptu Architekta",
        )
        lbl_head.SetBackgroundColour(dlg.GetBackgroundColour())
        lbl_head.SetMinSize((-1, 110))
        sizer.Add(lbl_head, flag=wx.ALL | wx.EXPAND, border=12)

        # Główne pole – Prompt Architekta (READONLY, rozciąga się na całe okno).
        lbl_prompt = wx.StaticText(dlg, label="Prompt do skopiowania (Ctrl+A, Ctrl+C):")
        f = lbl_prompt.GetFont()
        f.MakeBold()
        lbl_prompt.SetFont(f)
        sizer.Add(lbl_prompt, flag=wx.LEFT | wx.RIGHT, border=12)

        txt_prompt = wx.TextCtrl(
            dlg,
            value=self.PROMPT_ARCHITEKTA,
            style=wx.TE_MULTILINE | wx.TE_READONLY,
            name="Pełna treść Promptu Architekta",
        )
        sizer.Add(
            txt_prompt, proportion=1,
            flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, border=12,
        )

        # Rząd przycisków: „Skopiuj do schowka” + „Zamknij” (IDENTYCZNIE
        # jak w WynikKreatoraDialog w Managerze Reguł).
        btn_row = wx.BoxSizer(wx.HORIZONTAL)

        btn_kopiuj = wx.Button(
            dlg, label="📋  Skopiuj prompt do schowka",
            name="Przycisk Skopiuj Prompt Architekta do schowka",
        )

        def _kopiuj(_e: wx.Event) -> None:
            dane = wx.TextDataObject(self.PROMPT_ARCHITEKTA)
            if wx.TheClipboard.Open():
                try:
                    wx.TheClipboard.SetData(dane)
                    wx.TheClipboard.Flush()
                    wx.MessageBox(
                        "Prompt Architekta został skopiowany do schowka.\n"
                        "Wklej go (Ctrl+V) do ChatGPT lub Claude i zastąp "
                        "[TUTAJ WPISZ SWÓJ POMYSŁ] własnym pomysłem fabularnym.",
                        "Skopiowano",
                        wx.OK | wx.ICON_INFORMATION,
                        dlg,
                    )
                finally:
                    wx.TheClipboard.Close()
            else:
                wx.MessageBox(
                    "Nie udało się otworzyć schowka systemowego.\n"
                    "Skopiuj prompt ręcznie: kliknij w pole powyżej, "
                    "zaznacz wszystko (Ctrl+A) i skopiuj (Ctrl+C).",
                    "Schowek niedostępny",
                    wx.OK | wx.ICON_WARNING,
                    dlg,
                )

        dlg.Bind(wx.EVT_BUTTON, _kopiuj, btn_kopiuj)
        btn_row.Add(btn_kopiuj, flag=wx.RIGHT, border=8)

        btn_close = wx.Button(dlg, wx.ID_CLOSE, label="Zamknij")
        dlg.Bind(wx.EVT_BUTTON, lambda _e: dlg.EndModal(wx.ID_CLOSE), btn_close)
        dlg.SetEscapeId(wx.ID_CLOSE)
        btn_row.Add(btn_close)

        sizer.Add(btn_row, flag=wx.ALL | wx.ALIGN_RIGHT, border=12)

        dlg.SetSizer(sizer)
        # Fokus startowy: główne pole z promptem (NVDA od razu zacznie
        # czytać treść zamiast ogłaszać tytuł przycisku).
        txt_prompt.SetFocus()
        dlg.ShowModal()
        dlg.Destroy()

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
