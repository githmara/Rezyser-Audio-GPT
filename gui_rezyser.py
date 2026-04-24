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

Wersja 13.1: cały tekst widoczny dla użytkownika pochodzi z
``dictionaries/pl/gui/ui.yaml`` (sekcja ``rezyser``) przez moduł
:mod:`i18n`. W konstruktorze pobieramy też ``TOOL_DESCRIPTION`` i
``PROMPT_ARCHITEKTA`` – są zbyt duże, żeby trzymać je twardo w kodzie
i tak utrudniały tłumaczenie w przyszłości.
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
from i18n import t



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

    ENV_FILENAME = "golden_key.env"
    SKRYPTY_DIR  = "skrypty"


    def __init__(self, parent: wx.Window) -> None:

        super().__init__(parent, style=wx.TAB_TRAVERSAL)
        self.SetName(t("rezyser.panel_name"))

        # --------------------------------------------------------------
        # Wersja 13.1: duże bloki tekstu (opis narzędzia + prompt dla AI)
        # pobrane z YAML-a przez i18n. Przypisujemy je do instancji, a NIE
        # do klasy – bo `t()` działa dopiero po ustawieniu języka w
        # ``i18n.ustaw_jezyk()`` (co robi ``main.py`` w ``main()``).
        # Dzięki temu przy przyszłej zmianie języka w locie wystarczy
        # odbudować panel, a nie podmieniać stałe klasy w runtime.
        # --------------------------------------------------------------
        self._tool_description = t("rezyser.tool_description")
        self._prompt_architekta = t("rezyser.prompt_architekta_content")

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
        """Zwraca :class:`PrzepisRezysera` odpowiadający zaznaczonemu trybowi."""
        if not self._przepisy:
            return None
        idx = self._rb_mode.GetSelection()
        if 0 <= idx < len(self._przepisy):
            return self._przepisy[idx]
        return None

    # ==================================================================
    # SHIMY WŁAŚCIWOŚCI delegujące do self._projekt
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
    def _build_ui(self) -> None:
        """Buduje cały interfejs panelu poprzez wywołanie metod ``_zbuduj_*``."""
        BORDER = 8

        top_sizer         = self._zbuduj_naglowek(BORDER)
        pasek_pliku_sizer = self._zbuduj_pasek_pliku(BORDER)
        sidebar_sizer     = self._zbuduj_sidebar(BORDER)
        main_area_sizer   = self._zbuduj_obszar_roboczy(BORDER, pasek_pliku_sizer)

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
    # BLOK A – Nagłówek panelu
    # ------------------------------------------------------------------
    def _zbuduj_naglowek(self, BORDER: int) -> wx.BoxSizer:
        heading = wx.StaticText(self, label=t("rezyser.heading"))
        hf = heading.GetFont()
        hf.SetPointSize(16)
        hf.MakeBold()
        heading.SetFont(hf)

        self._description = wx.TextCtrl(
            self,
            value=self._tool_description,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.NO_BORDER,
            name=t("rezyser.description_name"),
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
        lbl_file = wx.StaticText(self, label=t("rezyser.lbl_nazwa_pliku"))

        self._txt_file_name = wx.TextCtrl(
            self,
            style=wx.TE_PROCESS_ENTER,
            name=t("rezyser.txt_nazwa_pliku_name"),
        )
        self._txt_file_name.SetHint(t("rezyser.txt_nazwa_pliku_hint"))
        self._txt_file_name.SetToolTip(t("rezyser.txt_nazwa_pliku_tooltip"))

        self._btn_load = wx.Button(self, label=t("rezyser.btn_wczytaj_label"))
        self._btn_load.SetToolTip(t("rezyser.btn_wczytaj_tooltip"))

        self._btn_clear_current = wx.Button(self, label=t("rezyser.btn_wyczysc_biezaca_label"))
        self._btn_clear_current.SetToolTip(t("rezyser.btn_wyczysc_biezaca_tooltip"))

        self._btn_hard_reset = wx.Button(self, label=t("rezyser.btn_hard_reset_label"))
        self._btn_hard_reset.SetToolTip(t("rezyser.btn_hard_reset_tooltip"))

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
    # BLOK C – Sidebar: Księga Świata + Pamięć Długotrwała
    # ------------------------------------------------------------------
    def _zbuduj_sidebar(self, BORDER: int) -> wx.BoxSizer:
        lbl_sb_heading = wx.StaticText(self, label=t("rezyser.sidebar_heading"))
        sbf = lbl_sb_heading.GetFont()
        sbf.SetPointSize(11)
        sbf.MakeBold()
        lbl_sb_heading.SetFont(sbf)

        lbl_ksiega = wx.StaticText(self, label=t("rezyser.lbl_ksiega_swiata"))

        self._txt_ksiega_swiata = wx.TextCtrl(
            self,
            style=wx.TE_MULTILINE,
            name=t("rezyser.txt_ksiega_name"),
        )
        self._txt_ksiega_swiata.SetHint(t("rezyser.txt_ksiega_hint"))
        self._txt_ksiega_swiata.SetToolTip(t("rezyser.txt_ksiega_tooltip"))

        self._btn_zapisz_ksiege = wx.Button(self, label=t("rezyser.btn_zapisz_ksiege_label"))
        self._btn_zapisz_ksiege.SetToolTip(t("rezyser.btn_zapisz_ksiege_tooltip"))

        self._btn_prompt_architekta = wx.Button(
            self,
            label=t("rezyser.btn_prompt_architekta_label"),
            name=t("rezyser.btn_prompt_architekta_name"),
        )
        self._btn_prompt_architekta.SetToolTip(t("rezyser.btn_prompt_architekta_tooltip"))


        lbl_pamiec = wx.StaticText(self, label=t("rezyser.lbl_pamiec_dlugotrwala"))

        self._txt_pamiec = wx.TextCtrl(
            self,
            style=wx.TE_MULTILINE,
            name=t("rezyser.txt_pamiec_name"),
        )
        self._txt_pamiec.SetHint(t("rezyser.txt_pamiec_hint"))
        self._txt_pamiec.SetToolTip(t("rezyser.txt_pamiec_tooltip"))

        self._btn_zapisz_pamiec = wx.Button(self, label=t("rezyser.btn_zapisz_pamiec_label"))
        self._btn_zapisz_pamiec.SetToolTip(t("rezyser.btn_zapisz_pamiec_tooltip"))

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
        lbl_main_heading = wx.StaticText(self, label=t("rezyser.main_heading"))
        mf = lbl_main_heading.GetFont()
        mf.SetPointSize(11)
        mf.MakeBold()
        lbl_main_heading.SetFont(mf)

        radiobox_sizer      = self._zbuduj_radiobox_trybu(BORDER)
        panel_struktury     = self._zbuduj_panel_struktury(BORDER)
        podglad_sizer       = self._zbuduj_podglad_historii(BORDER)
        pole_instrukcji     = self._zbuduj_pole_instrukcji(BORDER)
        panel_postprodukcji = self._zbuduj_panel_postprodukcji(BORDER)
        wskaznik_sizer      = self._zbuduj_wskaznik_pamieci_modelu(BORDER)


        sep = lambda: wx.StaticLine(self)   # noqa: E731

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
        self._rb_mode = wx.RadioBox(
            self,
            label=t("rezyser.rb_tryb_label"),
            choices=[p.etykieta for p in self._przepisy],
            majorDimension=1,
            style=wx.RA_SPECIFY_COLS,
            name=t("rezyser.rb_tryb_name"),
        )
        self._rb_mode.SetToolTip(t("rezyser.rb_tryb_tooltip"))

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self._rb_mode, flag=wx.EXPAND | wx.ALL, border=BORDER)
        return sizer

    # ------------------------------------------------------------------
    # BLOK E – Panel Zarządzania Strukturą (dynamicznie ukrywany)
    # ------------------------------------------------------------------
    def _zbuduj_panel_struktury(self, BORDER: int) -> wx.Panel:
        self._pnl_struktura = wx.Panel(self)

        lbl_struktura = wx.StaticText(self._pnl_struktura, label=t("rezyser.struktura_heading"))
        sf = lbl_struktura.GetFont()
        sf.SetPointSize(10)
        sf.MakeBold()
        lbl_struktura.SetFont(sf)

        self._btn_prolog = wx.Button(
            self._pnl_struktura,
            label=t("rezyser.btn_prolog_label"),
            name=t("rezyser.btn_prolog_name"),
        )
        self._btn_prolog.SetToolTip(t("rezyser.btn_prolog_tooltip"))

        self._btn_epilog = wx.Button(
            self._pnl_struktura,
            label=t("rezyser.btn_epilog_label"),
            name=t("rezyser.btn_epilog_name"),
        )
        self._btn_epilog.SetToolTip(t("rezyser.btn_epilog_tooltip"))

        self._btn_rozdzial = wx.Button(
            self._pnl_struktura,
            label=t("rezyser.btn_rozdzial_label", numer_rozdzialu=1),
            name=t("rezyser.btn_rozdzial_name"),
        )
        self._btn_rozdzial.SetToolTip(t("rezyser.btn_rozdzial_tooltip"))

        self._btn_akt = wx.Button(
            self._pnl_struktura,
            label=t("rezyser.btn_akt_label", numer_aktu=1),
            name=t("rezyser.btn_akt_name"),
        )
        self._btn_akt.SetToolTip(t("rezyser.btn_akt_tooltip"))

        self._btn_scena = wx.Button(
            self._pnl_struktura,
            label=t("rezyser.btn_scena_label", numer_sceny=1),
            name=t("rezyser.btn_scena_name"),
        )
        self._btn_scena.SetToolTip(t("rezyser.btn_scena_tooltip"))

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
    # BLOK E.1 – Podgląd pełnej historii
    # ------------------------------------------------------------------
    def _zbuduj_podglad_historii(self, BORDER: int) -> wx.BoxSizer:
        lbl_full_story = wx.StaticText(self, label=t("rezyser.lbl_podglad_historii"))

        self._txt_full_story = wx.TextCtrl(
            self,
            style=wx.TE_MULTILINE | wx.TE_READONLY,
            name=t("rezyser.txt_podglad_name"),
        )
        self._txt_full_story.SetHint(t("rezyser.txt_podglad_hint"))

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
        lbl_user_input = wx.StaticText(self, label=t("rezyser.lbl_instrukcje"))

        self._txt_user_input = wx.TextCtrl(
            self,
            style=wx.TE_MULTILINE,
            name=t("rezyser.txt_instrukcje_name"),
        )
        self._txt_user_input.SetHint(t("rezyser.txt_instrukcje_hint"))
        self._txt_user_input.SetMinSize((-1, 100))

        self._btn_wyslij = wx.Button(self, label=t("rezyser.btn_wyslij_label"))
        self._btn_wyslij.SetToolTip(t("rezyser.btn_wyslij_tooltip"))

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(lbl_user_input,       flag=wx.LEFT | wx.RIGHT | wx.TOP, border=BORDER)
        sizer.Add(self._txt_user_input, flag=wx.EXPAND | wx.ALL,          border=BORDER)
        sizer.Add(self._btn_wyslij,     flag=wx.LEFT | wx.BOTTOM | wx.TOP, border=BORDER)
        return sizer

    # ------------------------------------------------------------------
    # BLOK F – Panel Postprodukcji
    # ------------------------------------------------------------------
    def _zbuduj_panel_postprodukcji(self, BORDER: int) -> wx.Panel:
        self._pnl_postprodukcja = wx.Panel(self)

        lbl_postprod = wx.StaticText(self._pnl_postprodukcja, label=t("rezyser.postprod_heading"))
        pf = lbl_postprod.GetFont()
        pf.SetPointSize(10)
        pf.MakeBold()
        lbl_postprod.SetFont(pf)

        lbl_tytuly_info = wx.StaticText(
            self._pnl_postprodukcja,
            label=t("rezyser.postprod_info"),
        )

        self._btn_tytuly_ai = wx.Button(
            self._pnl_postprodukcja,
            label=t("rezyser.btn_tytuly_ai_label"),
            name=t("rezyser.btn_tytuly_ai_name"),
        )
        self._btn_tytuly_ai.SetToolTip(t("rezyser.btn_tytuly_ai_tooltip"))

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
    # BLOK G – Wskaźnik okna kontekstowego AI
    # ------------------------------------------------------------------
    def _zbuduj_wskaznik_pamieci_modelu(self, BORDER: int) -> wx.BoxSizer:
        lbl_kontekst = wx.StaticText(self, label=t("rezyser.lbl_pamiec_modelu"))
        kf = lbl_kontekst.GetFont()
        kf.SetWeight(wx.FONTWEIGHT_BOLD)
        lbl_kontekst.SetFont(kf)

        self._gauge_kontekst = wx.Gauge(
            self, range=100, style=wx.GA_HORIZONTAL | wx.GA_SMOOTH
        )
        self._gauge_kontekst.SetValue(0)

        self._lbl_kontekst_status = wx.TextCtrl(
            self,
            value=t("rezyser.lbl_pamiec_modelu_start"),
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.NO_BORDER,
            name=t("rezyser.pamiec_modelu_status_name"),
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

        self._txt_file_name.Bind(wx.EVT_TEXT,         self._on_file_name_change)
        self._txt_file_name.Bind(wx.EVT_TEXT_ENTER,   self._on_load)
        self._txt_pamiec.Bind(wx.EVT_TEXT,             self._on_pamiec_change)
        self._txt_user_input.Bind(wx.EVT_TEXT,         self._on_user_input_change)

        self._rb_mode.Bind(wx.EVT_RADIOBOX, self._on_mode_change)

        self._btn_prolog.Bind(wx.EVT_BUTTON,   self._on_wstaw_prolog)
        self._btn_epilog.Bind(wx.EVT_BUTTON,   self._on_wstaw_epilog)
        self._btn_rozdzial.Bind(wx.EVT_BUTTON, self._on_wstaw_rozdzial)
        self._btn_akt.Bind(wx.EVT_BUTTON,      self._on_wstaw_akt)
        self._btn_scena.Bind(wx.EVT_BUTTON,    self._on_wstaw_scena)

        self._btn_tytuly_ai.Bind(wx.EVT_BUTTON, self._on_tytuly_ai)

    # ------------------------------------------------------------------
    # Odświeżanie stanu przycisków (Enable/Disable)
    # ------------------------------------------------------------------
    def _refresh_ui_state(self) -> None:
        """Aktualizuje stan Enabled/Disabled przycisków na podstawie stanu pamięci."""
        pamiec_zajeta = self._projekt.pamiec_zajeta
        pamiec_pusta  = not pamiec_zajeta
        nazwa_podana  = bool(self._txt_file_name.GetValue().strip())
        streszczenie_wpisane = bool(self._txt_pamiec.GetValue().strip())
        user_text_present    = bool(self._txt_user_input.GetValue().strip())
        tryb_idx    = self._rb_mode.GetSelection()
        tryb_zapisu = tryb_idx in (1, 2)

        self._txt_file_name.Enable(not pamiec_zajeta)
        self._btn_load.Enable(pamiec_pusta and nazwa_podana)
        self._btn_clear_current.Enable(pamiec_zajeta)

        cos_do_wyczyszczenia = pamiec_zajeta or bool(
            self._txt_file_name.GetValue().strip()
            or self._txt_ksiega_swiata.GetValue().strip()
            or self._txt_pamiec.GetValue().strip()
        )
        self._btn_hard_reset.Enable(cos_do_wyczyszczenia)

        self._btn_zapisz_ksiege.Enable(nazwa_podana)
        self._btn_zapisz_pamiec.Enable(nazwa_podana and streszczenie_wpisane)

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

        _prolog_juz_jest   = self._projekt.ma_prolog
        _epilog_juz_jest   = self._projekt.ma_epilog
        _historia_niepusta = bool(self.full_story.strip())
        _blokada = self._projekt.ostatnia_linia_to_naglowek or _epilog_juz_jest


        if tryb_idx == 0:
            self._pnl_struktura.Hide()
        else:
            self._pnl_struktura.Show()

            jest_skrypt   = (tryb_idx == 1)
            jest_audiobok = (tryb_idx == 2)

            self._btn_rozdzial.Show(jest_audiobok)
            self._btn_akt.Show(jest_skrypt)
            self._btn_scena.Show(jest_skrypt)

            # Dynamiczne etykiety z aktualnymi licznikami (z i18n)
            self._btn_rozdzial.SetLabel(
                t("rezyser.btn_rozdzial_label", numer_rozdzialu=self.chapter_counter),
            )
            self._btn_akt.SetLabel(
                t("rezyser.btn_akt_label", numer_aktu=self.akt_counter),
            )
            self._btn_scena.SetLabel(
                t("rezyser.btn_scena_label", numer_sceny=self.scena_counter),
            )

            self._btn_prolog.Enable(
                nazwa_podana and not _historia_niepusta and not _prolog_juz_jest
            )
            self._btn_epilog.Enable(
                nazwa_podana and _historia_niepusta and not _blokada
            )
            self._btn_rozdzial.Enable(nazwa_podana and not _blokada)
            self._btn_akt.Enable(nazwa_podana and not _blokada)
            self._btn_scena.Enable(nazwa_podana and not _blokada)

            self._pnl_struktura.Layout()

        # Ochrona przed przypadkową zmianą trybu twórczego.
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

        if tryb_idx == 2:
            self._pnl_postprodukcja.Show()
            self._btn_tytuly_ai.Enable(
                self._api_dostepne and nazwa_podana and _historia_niepusta
            )
        else:
            self._pnl_postprodukcja.Hide()

        self._aktualizuj_pamiec_modelu()

        self.Layout()

    # ------------------------------------------------------------------
    # Handlery zmian w polach tekstowych
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
        nazwa = self._txt_file_name.GetValue().strip()
        if not nazwa:
            wx.MessageBox(
                t("rezyser.brak_nazwy_tresc"),
                t("rezyser.brak_nazwy_tytul"),
                wx.OK | wx.ICON_WARNING,
                self,
            )
            self._txt_file_name.SetFocus()
            return

        try:
            wynik = self._projekt.wczytaj(nazwa)
        except FileNotFoundError as exc:
            wx.MessageBox(
                t("rezyser.plik_nie_istnieje_tresc", tresc_bledu=str(exc)),
                t("rezyser.plik_nie_istnieje_tytul"),
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            return
        except OSError as exc:
            wx.MessageBox(
                t("rezyser.blad_odczytu_tresc", tresc_bledu=str(exc)),
                t("common.blad_odczytu_tytul"),
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return

        self._txt_ksiega_swiata.SetValue(self.world_lore)
        self._txt_pamiec.SetValue(self.summary_text)
        self._txt_full_story.SetValue(self.full_story)

        if wynik.saved_mode in (1, 2):
            self._rb_mode.SetSelection(wynik.saved_mode)

        lore_info = (
            t("rezyser.status_wczytano_ksiega", nazwa_projektu=nazwa)
            if wynik.czy_ksiega_swiata else ""
        )
        if wynik.czy_streszczenie:
            status_msg = t(
                "rezyser.status_wczytano_streszczenie",
                nazwa_projektu=nazwa,
                lore_info=lore_info,
            )
        else:
            status_msg = t(
                "rezyser.status_wczytano_historia",
                nazwa_projektu=nazwa,
                liczba_znakow=wynik.liczba_znakow,
                lore_info=lore_info,
            )

        self._refresh_ui_state()
        wx.MessageBox(status_msg, t("rezyser.status_wczytano_tytul"),
                      wx.OK | wx.ICON_INFORMATION, self)

    # ------------------------------------------------------------------
    # Czyszczenie pamięci bieżącej
    # ------------------------------------------------------------------
    def _on_clear_current(self, _event: wx.Event) -> None:
        self._projekt.wyczysc_biezaca()
        self._txt_full_story.SetValue("")

        self._refresh_ui_state()
        komunikat = t("rezyser.pamiec_wyczyszczona_tresc")
        if self.summary_text.strip():
            komunikat += t("rezyser.pamiec_wyczyszczona_streszczenie_zostaje")
        wx.MessageBox(
            komunikat, t("rezyser.pamiec_wyczyszczona_tytul"),
            wx.OK | wx.ICON_INFORMATION, self,
        )

    # ------------------------------------------------------------------
    # Twardy Reset
    # ------------------------------------------------------------------
    def _on_hard_reset(self, _event: wx.Event) -> None:
        odp = wx.MessageBox(
            t("rezyser.hard_reset_pytanie"),
            t("rezyser.hard_reset_pytanie_tytul"),
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING,
            self,
        )
        if odp != wx.YES:
            return

        self._projekt.twardy_reset()

        self._txt_file_name.SetValue("")
        self._txt_file_name.Enable()
        self._txt_full_story.SetValue("")
        self._txt_ksiega_swiata.SetValue("")
        self._txt_pamiec.SetValue("")
        self._txt_user_input.SetValue("")

        self._refresh_ui_state()
        wx.MessageBox(
            t("rezyser.hard_reset_ok_tresc"),
            t("rezyser.hard_reset_ok_tytul"),
            wx.OK | wx.ICON_INFORMATION,
            self,
        )
        self._txt_file_name.SetFocus()

    # ------------------------------------------------------------------
    # Zapis Księgi Świata
    # ------------------------------------------------------------------
    def _on_zapisz_ksiege(self, _event: wx.Event) -> None:
        nazwa = self._txt_file_name.GetValue().strip()
        if not nazwa:
            wx.MessageBox(
                t("rezyser.brak_nazwy_ksiega_tresc"),
                t("rezyser.brak_nazwy_ksiega_tytul"),
                wx.OK | wx.ICON_WARNING,
                self,
            )
            self._txt_file_name.SetFocus()
            return

        tresc = self._txt_ksiega_swiata.GetValue().strip()
        if not tresc:
            wx.MessageBox(
                t("rezyser.ksiega_pusta_tresc"),
                t("rezyser.ksiega_pusta_tytul"),
                wx.OK | wx.ICON_WARNING,
                self,
            )
            self._txt_ksiega_swiata.SetFocus()
            return

        if self._projekt.nazwa_pliku != nazwa:
            self._projekt.nazwa_pliku = nazwa
        try:
            self._projekt.zapisz_ksiege_swiata(tresc)
            wx.MessageBox(
                t("rezyser.ksiega_zapisana_tresc", nazwa_projektu=nazwa),
                t("rezyser.ksiega_zapisana_tytul"),
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
        except Exception as exc:  # noqa: BLE001
            wx.MessageBox(
                t("rezyser.blad_zapisu_ksiegi", tresc_bledu=str(exc)),
                t("common.blad_zapisu_tytul"),
                wx.OK | wx.ICON_ERROR,
                self,
            )

    # ------------------------------------------------------------------
    # Prompt Architekta – dialog z gotowym promptem do skopiowania
    # ------------------------------------------------------------------
    def _on_prompt_architekta(self, _event: wx.Event) -> None:
        dlg = wx.Dialog(
            self,
            title=t("rezyser.prompt_arch_dlg_tytul"),
            size=(720, 560),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        sizer = wx.BoxSizer(wx.VERTICAL)

        lbl_head = wx.TextCtrl(
            dlg,
            value=t("rezyser.prompt_arch_instrukcja"),
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.NO_BORDER,
            name=t("rezyser.prompt_arch_instrukcja_name"),
        )
        lbl_head.SetBackgroundColour(dlg.GetBackgroundColour())
        lbl_head.SetMinSize((-1, 110))
        sizer.Add(lbl_head, flag=wx.ALL | wx.EXPAND, border=12)

        lbl_prompt = wx.StaticText(dlg, label=t("rezyser.prompt_arch_lbl"))
        f = lbl_prompt.GetFont()
        f.MakeBold()
        lbl_prompt.SetFont(f)
        sizer.Add(lbl_prompt, flag=wx.LEFT | wx.RIGHT, border=12)

        txt_prompt = wx.TextCtrl(
            dlg,
            value=self._prompt_architekta,
            style=wx.TE_MULTILINE | wx.TE_READONLY,
            name=t("rezyser.prompt_arch_tresc_name"),
        )
        sizer.Add(
            txt_prompt, proportion=1,
            flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, border=12,
        )

        btn_row = wx.BoxSizer(wx.HORIZONTAL)

        btn_kopiuj = wx.Button(
            dlg, label=t("rezyser.prompt_arch_btn_kopiuj"),
            name=t("rezyser.prompt_arch_btn_kopiuj_name"),
        )

        def _kopiuj(_e: wx.Event) -> None:
            dane = wx.TextDataObject(self._prompt_architekta)
            if wx.TheClipboard.Open():
                try:
                    wx.TheClipboard.SetData(dane)
                    wx.TheClipboard.Flush()
                    wx.MessageBox(
                        t("rezyser.prompt_arch_skopiowano_tresc"),
                        t("rezyser.prompt_arch_skopiowano_tytul"),
                        wx.OK | wx.ICON_INFORMATION,
                        dlg,
                    )
                finally:
                    wx.TheClipboard.Close()
            else:
                wx.MessageBox(
                    t("rezyser.prompt_arch_schowek_nieudany"),
                    t("common.komunikat_schowek_nieudany_tytul"),
                    wx.OK | wx.ICON_WARNING,
                    dlg,
                )

        dlg.Bind(wx.EVT_BUTTON, _kopiuj, btn_kopiuj)
        btn_row.Add(btn_kopiuj, flag=wx.RIGHT, border=8)

        btn_close = wx.Button(dlg, wx.ID_CLOSE, label=t("common.btn_zamknij"))
        dlg.Bind(wx.EVT_BUTTON, lambda _e: dlg.EndModal(wx.ID_CLOSE), btn_close)
        dlg.SetEscapeId(wx.ID_CLOSE)
        btn_row.Add(btn_close)

        sizer.Add(btn_row, flag=wx.ALL | wx.ALIGN_RIGHT, border=12)

        dlg.SetSizer(sizer)
        txt_prompt.SetFocus()
        dlg.ShowModal()
        dlg.Destroy()

    # ------------------------------------------------------------------
    # Zapis Streszczenia
    # ------------------------------------------------------------------
    def _on_zapisz_pamiec(self, _event: wx.Event) -> None:
        nazwa = self._txt_file_name.GetValue().strip()
        if not nazwa:
            wx.MessageBox(
                t("rezyser.brak_nazwy_ksiega_tresc"),
                t("rezyser.brak_nazwy_ksiega_tytul"),
                wx.OK | wx.ICON_WARNING,
                self,
            )
            self._txt_file_name.SetFocus()
            return

        tresc = self._txt_pamiec.GetValue().strip()
        if not tresc:
            wx.MessageBox(
                t("rezyser.pamiec_pusta_tresc"),
                t("rezyser.pamiec_pusta_tytul"),
                wx.OK | wx.ICON_WARNING,
                self,
            )
            self._txt_pamiec.SetFocus()
            return

        if self._projekt.nazwa_pliku != nazwa:
            self._projekt.nazwa_pliku = nazwa
        try:
            self._projekt.zapisz_streszczenie(tresc)
            wx.MessageBox(
                t("rezyser.streszczenie_zapisane_tresc", nazwa_projektu=nazwa),
                t("rezyser.streszczenie_zapisane_tytul"),
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
        except Exception as exc:  # noqa: BLE001
            wx.MessageBox(
                t("rezyser.blad_zapisu_streszczenia", tresc_bledu=str(exc)),
                t("common.blad_zapisu_tytul"),
                wx.OK | wx.ICON_ERROR,
                self,
            )

    # ------------------------------------------------------------------
    # Wysyłanie do AI
    # ------------------------------------------------------------------
    def _on_wyslij(self, _event: wx.Event) -> None:
        if not self._api_dostepne:
            wx.MessageBox(
                t("rezyser.brak_api_tresc"),
                t("rezyser.brak_api_tytul"),
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return

        user_text = self._txt_user_input.GetValue().strip()
        if not user_text:
            wx.MessageBox(
                t("rezyser.puste_pole_tresc"),
                t("rezyser.puste_pole_tytul"),
                wx.OK | wx.ICON_WARNING,
                self,
            )
            self._txt_user_input.SetFocus()
            return

        nazwa       = self._txt_file_name.GetValue().strip()
        przepis     = self._aktualny_przepis()
        if przepis is None:
            wx.MessageBox(
                t("rezyser.brak_przepisow_tresc"),
                t("rezyser.brak_przepisow_tytul"),
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return
        tryb_zapisu = przepis.zapis_do_pliku

        if tryb_zapisu and not nazwa:
            wx.MessageBox(
                t("rezyser.brak_nazwy_wyslanie_tresc", tytul_trybu=przepis.etykieta),
                t("rezyser.brak_nazwy_ksiega_tytul"),
                wx.OK | wx.ICON_WARNING,
                self,
            )
            self._txt_file_name.SetFocus()
            return

        world_context = self._txt_ksiega_swiata.GetValue().strip()
        if not world_context:
            wx.MessageBox(
                t("rezyser.brak_ksiegi_tresc"),
                t("rezyser.brak_ksiegi_tytul"),
                wx.OK | wx.ICON_WARNING,
                self,
            )
            self._txt_ksiega_swiata.SetFocus()
            return

        slowa_streszczenia = przepis.slowa_wyzwalajace.get("streszczenie", [])
        if tryb_zapisu and any(s in user_text.lower() for s in slowa_streszczenia):
            wx.MessageBox(
                t("rezyser.blad_trybu_tresc"),
                t("rezyser.blad_trybu_tytul"),
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return

        self._projekt.world_lore = world_context
        if nazwa and self._projekt.nazwa_pliku != nazwa:
            self._projekt.nazwa_pliku = nazwa

        self._btn_wyslij.Disable()
        self._txt_user_input.SetValue("")
        self._refresh_ui_state()

        snapshot = self._projekt.snapshot()

        t_thread = threading.Thread(
            target=self._wyslij_worker,
            args=(przepis, snapshot, user_text, nazwa, tryb_zapisu),
            daemon=True,
        )
        self._worker_thread = t_thread
        t_thread.start()


    # ------------------------------------------------------------------
    # Pomocnicza metoda zapisu do pliku projektu
    # ------------------------------------------------------------------
    def _dopisz_do_pliku(self, nazwa: str, content: str, mode: str = "a") -> None:
        if self._projekt.nazwa_pliku != nazwa:
            self._projekt.nazwa_pliku = nazwa
        try:
            self._projekt.dopisz_do_pliku_historii(content, mode=mode)
        except Exception as exc:  # noqa: BLE001
            wx.MessageBox(
                t("rezyser.blad_zapisu_do_pliku", tresc_bledu=str(exc)),
                t("common.blad_zapisu_tytul"),
                wx.OK | wx.ICON_ERROR,
                self,
            )

    # ------------------------------------------------------------------
    # Wyświetlanie błędów AI
    # ------------------------------------------------------------------
    def _wyswietl_blad_ai(self, tresc_bledu: str, custom_msg: str | None = None) -> None:
        """Krótki błąd → MessageBox; długi → dialog z polem do skopiowania."""
        msg_header  = custom_msg or t("rezyser.blad_ai_naglowek")
        jest_krotki = len(tresc_bledu) <= 200 and "\n" not in tresc_bledu

        if jest_krotki:
            pelna_tresc = f"{msg_header}\n\n{tresc_bledu}" if custom_msg else tresc_bledu
            wx.MessageBox(pelna_tresc, t("rezyser.blad_ai_tytul"),
                          wx.OK | wx.ICON_ERROR, self)
        else:
            dlg = wx.Dialog(self, title=t("rezyser.blad_ai_szczegoly_tytul"), size=(640, 400))
            sizer = wx.BoxSizer(wx.VERTICAL)
            lbl_head = wx.StaticText(dlg, label=msg_header)
            lbl_copy = wx.StaticText(dlg, label=t("rezyser.blad_ai_lbl_tresc"))
            txt = wx.TextCtrl(
                dlg,
                value=tresc_bledu,
                style=wx.TE_MULTILINE | wx.TE_READONLY,
                name=t("rezyser.blad_ai_tresc_name"),
            )
            btn_ok = wx.Button(dlg, wx.ID_OK, label=t("common.btn_zamknij"))
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
    _KOLORY_POZIOMOW = {
        cr.POZIOM_CZYSTA:     (0, 128, 0),
        cr.POZIOM_OK:         (0, 128, 0),
        cr.POZIOM_OSTRZEZENIE:(180, 100, 0),
        cr.POZIOM_ALARM:      (180, 0, 0),
    }

    def _aktualizuj_pamiec_modelu(self) -> None:
        status = self._projekt.status_pamieci_modelu()
        r, g, b = self._KOLORY_POZIOMOW.get(status.poziom, (0, 0, 0))
        self._gauge_kontekst.SetValue(status.procent)
        self._lbl_kontekst_status.SetValue(status.komunikat)
        self._lbl_kontekst_status.SetForegroundColour(wx.Colour(r, g, b))


    # ------------------------------------------------------------------
    # Wątek tła – główna logika AI
    # ------------------------------------------------------------------
    def _wyslij_worker(
        self,
        przepis: pr.PrzepisRezysera,
        snapshot: cr.SnapshotProjektu,
        user_text: str,
        nazwa: str,
        tryb_zapisu: bool,
    ) -> None:
        try:
            wynik = rai.generuj_fragment(
                klient=self._client,
                przepis=przepis,
                snapshot=snapshot,
                user_text=user_text,
                on_postep=None,
            )
        except openai.RateLimitError:
            wx.CallAfter(
                self._on_wyslij_error,
                t("rezyser.err_rate_limit"),
            )
            return
        except Exception as exc:  # noqa: BLE001
            wx.CallAfter(self._on_wyslij_error, str(exc))
            return

        if wynik.odrzucone:
            wx.CallAfter(
                self._on_wyslij_error,
                t("rezyser.err_odrzucenie"),
            )
            return

        if wynik.nowe_streszczenie:
            wx.CallAfter(
                self._on_wyslij_zapisz_streszczenie, wynik.nowe_streszczenie,
            )

        if tryb_zapisu:
            wx.CallAfter(self._on_wyslij_done_zapis, wynik.tekst_odpowiedzi, nazwa)
        else:
            wx.CallAfter(self._on_wyslij_done_burza, wynik.tekst_odpowiedzi)


    # ------------------------------------------------------------------
    # Callbacki _wyslij_worker
    # ------------------------------------------------------------------
    def _on_wyslij_error(self, msg: str) -> None:
        self._btn_wyslij.Enable()
        self._refresh_ui_state()
        self._wyswietl_blad_ai(msg)

    def _on_wyslij_zapisz_streszczenie(self, streszczenie: str) -> None:
        self.summary_text = streszczenie
        self._txt_pamiec.SetValue(streszczenie)

    def _on_wyslij_done_zapis(self, response_text: str, nazwa: str) -> None:
        if self.full_story:
            self.full_story += "\n\n" + response_text
        else:
            self.full_story = response_text
        self._txt_full_story.SetValue(self.full_story)
        self._dopisz_do_pliku(nazwa, response_text + "\n\n")
        self.last_response = response_text
        self._btn_wyslij.Enable()
        self._refresh_ui_state()
        wx.Bell()
        self._txt_full_story.SetFocus()

    def _on_wyslij_done_burza(self, response_text: str) -> None:
        self.last_response = response_text
        self._btn_wyslij.Enable()
        self._refresh_ui_state()
        self._show_response_dialog(response_text)

    def _show_response_dialog(self, tekst: str) -> None:
        dlg = wx.Dialog(
            self,
            title=t("rezyser.burza_dlg_tytul"),
            size=(720, 520),
        )
        sizer = wx.BoxSizer(wx.VERTICAL)
        lbl = wx.StaticText(dlg, label=t("rezyser.burza_dlg_lbl"))
        txt = wx.TextCtrl(
            dlg,
            value=tekst,
            style=wx.TE_MULTILINE | wx.TE_READONLY,
            name=t("rezyser.burza_dlg_name"),
        )
        btn_ok = wx.Button(dlg, wx.ID_OK, label=t("common.btn_zamknij"))
        sizer.Add(lbl,    flag=wx.ALL,                                   border=8)
        sizer.Add(txt,    proportion=1, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=8)
        sizer.Add(btn_ok, flag=wx.ALL | wx.ALIGN_RIGHT,                  border=8)
        dlg.SetSizer(sizer)
        txt.SetFocus()
        dlg.ShowModal()
        dlg.Destroy()

    # ------------------------------------------------------------------
    # Helper: wspólna walidacja nazwy projektu
    # ------------------------------------------------------------------
    def _wymagaj_nazwy_lub_alert(self) -> str | None:
        nazwa = self._txt_file_name.GetValue().strip()
        if not nazwa:
            wx.MessageBox(
                t("rezyser.struktura_brak_nazwy_tresc"),
                t("rezyser.struktura_brak_nazwy_tytul"),
                wx.OK | wx.ICON_WARNING,
                self,
            )
            self._txt_file_name.SetFocus()
            return None
        if self._projekt.nazwa_pliku != nazwa:
            self._projekt.nazwa_pliku = nazwa
        return nazwa

    def _po_wstawieniu_struktury(self, tytul: str, komunikat: str) -> None:
        self._txt_full_story.SetValue(self.full_story)
        self._zapisz_tryb_projektu()
        self._refresh_ui_state()
        wx.MessageBox(komunikat, tytul, wx.OK | wx.ICON_INFORMATION, self)

    # ------------------------------------------------------------------
    # Wstawianie Prologu
    # ------------------------------------------------------------------
    def _on_wstaw_prolog(self, _event: wx.Event) -> None:
        if self._wymagaj_nazwy_lub_alert() is None:
            return
        try:
            self._projekt.wstaw_prolog()
        except Exception as exc:  # noqa: BLE001
            wx.MessageBox(
                t("rezyser.blad_wstawiania_prolog", tresc_bledu=str(exc)),
                t("common.blad_zapisu_tytul"),
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return
        self._po_wstawieniu_struktury(
            t("rezyser.prolog_tytul"),
            t("rezyser.prolog_tresc"),
        )

    # ------------------------------------------------------------------
    # Wstawianie Epilogu
    # ------------------------------------------------------------------
    def _on_wstaw_epilog(self, _event: wx.Event) -> None:
        if self._wymagaj_nazwy_lub_alert() is None:
            return
        try:
            self._projekt.wstaw_epilog()
        except Exception as exc:  # noqa: BLE001
            wx.MessageBox(
                t("rezyser.blad_wstawiania_epilog", tresc_bledu=str(exc)),
                t("common.blad_zapisu_tytul"),
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return
        self._po_wstawieniu_struktury(
            t("rezyser.epilog_tytul"),
            t("rezyser.epilog_tresc"),
        )

    # ------------------------------------------------------------------
    # Wstawianie cięcia Rozdziału (Audiobook)
    # ------------------------------------------------------------------
    def _on_wstaw_rozdzial(self, _event: wx.Event) -> None:
        if self._wymagaj_nazwy_lub_alert() is None:
            return
        try:
            naglowek = self._projekt.wstaw_rozdzial()
        except Exception as exc:  # noqa: BLE001
            wx.MessageBox(
                t("rezyser.blad_wstawiania_rozdzialu", tresc_bledu=str(exc)),
                t("common.blad_zapisu_tytul"),
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return
        self._po_wstawieniu_struktury(
            t("rezyser.rozdzial_tytul"),
            t("rezyser.rozdzial_tresc", naglowek=naglowek),
        )

    # ------------------------------------------------------------------
    # Wstawianie Aktu (Skrypt)
    # ------------------------------------------------------------------
    def _on_wstaw_akt(self, _event: wx.Event) -> None:
        if self._wymagaj_nazwy_lub_alert() is None:
            return
        try:
            akt_nag, scena_nag = self._projekt.wstaw_akt()
        except Exception as exc:  # noqa: BLE001
            wx.MessageBox(
                t("rezyser.blad_wstawiania_aktu", tresc_bledu=str(exc)),
                t("common.blad_zapisu_tytul"),
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return
        self._po_wstawieniu_struktury(
            t("rezyser.akt_tytul"),
            t("rezyser.akt_tresc", akt_naglowek=akt_nag, scena_naglowek=scena_nag),
        )

    # ------------------------------------------------------------------
    # Wstawianie Sceny (Skrypt)
    # ------------------------------------------------------------------
    def _on_wstaw_scena(self, _event: wx.Event) -> None:
        if self._wymagaj_nazwy_lub_alert() is None:
            return
        try:
            scena_nag = self._projekt.wstaw_scena()
        except Exception as exc:  # noqa: BLE001
            wx.MessageBox(
                t("rezyser.blad_wstawiania_sceny", tresc_bledu=str(exc)),
                t("common.blad_zapisu_tytul"),
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return
        self._po_wstawieniu_struktury(
            t("rezyser.scena_tytul"),
            t("rezyser.scena_tresc", naglowek=scena_nag),
        )


    # ------------------------------------------------------------------
    # Postprodukcja – Nadaj Tytuły Rozdziałom
    # ------------------------------------------------------------------
    def _on_tytuly_ai(self, _event: wx.Event) -> None:
        nazwa = self._txt_file_name.GetValue().strip()
        if not nazwa:
            wx.MessageBox(
                t("rezyser.tytuly_brak_nazwy_tresc"),
                t("rezyser.tytuly_brak_nazwy_tytul"),
                wx.OK | wx.ICON_WARNING,
                self,
            )
            return

        if self._worker_thread and self._worker_thread.is_alive():
            wx.MessageBox(
                t("rezyser.tytuly_zajety_tresc"),
                t("rezyser.tytuly_zajety_tytul"),
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            return

        app_dir  = os.path.dirname(os.path.abspath(__file__))
        filepath = os.path.join(app_dir, self.SKRYPTY_DIR, f"{nazwa}.txt")
        if not os.path.exists(filepath):
            wx.MessageBox(
                t("rezyser.tytuly_brak_pliku_tresc", sciezka_pliku=filepath),
                t("rezyser.tytuly_brak_pliku_tytul"),
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return

        try:
            with open(filepath, "r", encoding="utf-8") as fh:
                pelny_tekst = fh.read()
        except Exception as exc:
            wx.MessageBox(
                t("rezyser.blad_odczytu_tresc", tresc_bledu=str(exc)),
                t("common.blad_odczytu_tytul"),
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return

        self._btn_tytuly_ai.Disable()
        self._gauge_postprod.SetValue(0)
        self._gauge_postprod.Show()
        self._lbl_postprod_status.SetLabel(t("rezyser.tytuly_prep"))
        self._lbl_postprod_status.Show()
        self._pnl_postprodukcja.Layout()
        self.Layout()

        t_thread = threading.Thread(
            target=self._tytuly_worker,
            args=(pelny_tekst,),
            daemon=True,
        )
        self._worker_thread = t_thread
        t_thread.start()

    # ------------------------------------------------------------------
    # Wątek tła – generowanie tytułów
    # ------------------------------------------------------------------
    def _tytuly_worker(self, pelny_tekst: str) -> None:
        if self._przepis_tytuly is None:
            wx.CallAfter(
                self._on_tytuly_error,
                t("rezyser.tytuly_brak_przepisu_tresc"),
            )
            return

        def _cb(msg: str, percent: int) -> None:
            wx.CallAfter(self._update_tytuly_progress, msg, percent)

        wynik = rai.nadaj_tytuly_rozdzialom(
            klient=self._client,
            przepis_tytuly=self._przepis_tytuly,
            pelny_tekst=pelny_tekst,
            on_postep=_cb,
        )

        if wynik.przerwano_bledem:
            wx.CallAfter(
                self._on_tytuly_error,
                wynik.blad or t("rezyser.tytuly_blad_nieznany"),
                list(wynik.tytuly),
            )
            return

        wx.CallAfter(self._show_titles_dialog, "\n".join(wynik.tytuly))


    # ------------------------------------------------------------------
    # Callbacki _tytuly_worker
    # ------------------------------------------------------------------
    def _update_tytuly_progress(self, msg: str, percent: int) -> None:
        self._lbl_postprod_status.SetLabel(msg)
        self._gauge_postprod.SetValue(max(0, min(100, percent)))

    def _on_tytuly_error(self, msg: str, partial_tytuly: list | None = None) -> None:
        self._btn_tytuly_ai.Enable()
        self._gauge_postprod.SetValue(0)
        self._gauge_postprod.Hide()
        self._lbl_postprod_status.Hide()
        self._pnl_postprodukcja.Layout()
        self.Layout()
        self._wyswietl_blad_ai(
            msg,
            t("rezyser.tytuly_blad_naglowek"),
        )
        if partial_tytuly:
            self._show_titles_dialog(
                t(
                    "rezyser.tytuly_czesciowe_naglowek",
                    wyniki="\n".join(partial_tytuly),
                )
            )

    def _show_titles_dialog(self, tytuly_text: str) -> None:
        self._btn_tytuly_ai.Enable()
        self._gauge_postprod.SetValue(100)
        self._lbl_postprod_status.SetLabel(t("rezyser.tytuly_gotowe"))

        dlg = wx.Dialog(
            self,
            title=t("rezyser.tytuly_dlg_tytul"),
            size=(620, 420),
        )
        sizer = wx.BoxSizer(wx.VERTICAL)
        lbl = wx.StaticText(dlg, label=t("rezyser.tytuly_dlg_lbl"))
        txt = wx.TextCtrl(
            dlg,
            value=tytuly_text,
            style=wx.TE_MULTILINE | wx.TE_READONLY,
            name=t("rezyser.tytuly_dlg_name"),
        )
        btn_ok = wx.Button(dlg, wx.ID_OK, label=t("common.btn_zamknij"))
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
        nazwa    = self._txt_file_name.GetValue().strip()
        tryb_idx = self._rb_mode.GetSelection()
        if not nazwa:
            return
        if self._projekt.nazwa_pliku != nazwa:
            self._projekt.nazwa_pliku = nazwa
        self._projekt.zapisz_tryb_tworczy(tryb_idx)
