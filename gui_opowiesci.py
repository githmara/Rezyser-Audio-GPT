"""
gui_opowiesci.py — Cienka warstwa widoku panelu „Interaktywne Opowieści" (wxPython).

Faza 1 wdrożenia v15.0 — szkielet UI z zaślepionymi callbackami. Kolejne fazy:
    • Faza 2: silnik LLM (``opowiesci_ai.py``), JSON-schema response, daemon thread.
    • Faza 3: engine + lifecycle plików (``core_opowiesci.py``):
              - ``skrypty/[gra].txt`` (narracja bez meta-warningów)
              - ``skrypty/[gra].md``  (księga świata, format ``[Imię: cechy]`` —
                ten sam parser co Reżyser → output Opowieści jest wejściem Reżysera)
              - ``runtime/opowiesci/[gra].game.json`` (pełny stan)
              - ``runtime/opowiesci/[gra].story.jsonl`` (append-only log tur)
              - ``runtime/skrypty/[gra].mode`` (3=Swobodny, 4=Wybory, 5=Mniejsze zło)
    • Faza 4: parser slash-komend (lokalny, bez API), wskaźnik pamięci modelu,
              auto-streszczenie na 70% okna, ``/visualize`` jako tryb 0/Burza
              (bez zapisu do plików).

Wzorzec architektoniczny skopiowany z :class:`gui_rezyser.RezyserPanel`:
    • Klasa dziedzicząca po ``wx.Panel`` z ``style=wx.TAB_TRAVERSAL``.
    • Subpanele budowane przez metody ``_zbuduj_*`` zwracające ``wx.BoxSizer``.
    • Cały tekst widoczny dla użytkownika z ``dictionaries/<jezyk>/gui/ui.yaml``
      sekcja ``opowiesci.*`` przez moduł :mod:`i18n` (``t(...)``).

Logiczna kolejność tabulacji (KRYTYCZNE dla NVDA i innych czytników ekranu):
    1. Pasek pliku gry (nazwa + Nowa/Wczytaj/Zapisz)
    2. RadioBox trybu (Swobodny / Wyborów / Mniejsze zło)
    3. Obszar narracji (TextCtrl readonly multiline) — fokus po każdej turze
    4. Obszar wyborów (dynamiczne przyciski w Fazie 2)
    5. Pole akcji (TextCtrl multiline editable) + przycisk Wyślij

Nawigacja Shift+Tab z pola akcji wraca do wyborów, dalej do narracji — gracz
może w każdej chwili odsłuchać scenę, sprawdzić wybory, wrócić do pisania.
"""

from __future__ import annotations

import os

import wx

from i18n import t


class OpowiesciPanel(wx.Panel):
    """Panel modułu „Interaktywne Opowieści" — szkielet Fazy 1 v15.0.

    Tryby gry (kontynuacja numeracji ``.mode`` po Reżyserze: 0=Burza pominięta,
    1=Reżyser tryb 1, 2=Reżyser tryb 2):

        * Tryb 3 — Swobodny: gracz może spróbować dowolnej akcji free-textem.
        * Tryb 4 — Wyborów: 3-5 numerowanych opcji per tura, free-text mapuje
                   na najbliższy wybór albo prosi o numer.
        * Tryb 5 — Mniejsze zło: jak Wybory, ale wszystkie opcje niekorzystne;
                   mechanika Fiolki/Vial odłożona do v15.1.

    W Fazie 1 wszystkie callbacki idą do :meth:`_on_placeholder` — komunikat
    informacyjny, że funkcja zostanie podłączona w kolejnej fazie.
    """

    # --------------------------------------------------------------
    # Stałe ścieżek (używane od Fazy 3 — engine + lifecycle plików)
    # --------------------------------------------------------------
    SKRYPTY_DIR    = "skrypty"
    OPOWIESCI_DIR  = os.path.join("runtime", "opowiesci")
    MODE_DIR       = os.path.join("runtime", "skrypty")  # ten sam folder co Reżyser

    def __init__(self, parent: wx.Window) -> None:
        super().__init__(parent, style=wx.TAB_TRAVERSAL)
        self.SetName(t("opowiesci.panel_name"))

        # Wzorzec z RezyserPanel: duży tekst opisu modułu z YAML, nie z kodu.
        # Pobieramy raz w konstruktorze — t() działa dopiero po
        # ``i18n.ustaw_jezyk()`` w main.main().
        self._tool_description = t("opowiesci.tool_description")

        self._build_ui()
        self._bind_events()

        # Faza 1: obszar wyborów zawsze schowany — silnika narracyjnego
        # nie ma jeszcze, więc placeholder nie ma kontekstu i pusty panel
        # tabowalny dezorientowałby NVDA. Faza 2 wywoła ten helper z
        # ``True`` w trybach Wyborów (4) / Mniejsze zło (5) tylko po
        # pomyślnej walidacji JSON-schema z niepustym ``wybory[]``.
        # W trybie Swobodnym (3) panel pozostaje permanentnie schowany.
        self._aktywuj_obszar_wyborow(False)

        # NVDA odczyta opis modułu jako pierwsze po wejściu na panel
        wx.CallAfter(self._description.SetFocus)

    # ==================================================================
    # KOMPOZER UI
    # ==================================================================
    def _build_ui(self) -> None:
        """Składa szkielet panelu z subpaneli ``_zbuduj_*``."""
        BORDER = 8

        sizer_naglowek    = self._zbuduj_naglowek(BORDER)
        sizer_pasek_pliku = self._zbuduj_pasek_pliku(BORDER)
        sizer_tryb        = self._zbuduj_radiobox_trybu(BORDER)
        sizer_pamiec      = self._zbuduj_wskaznik_pamieci(BORDER)
        sizer_narracja    = self._zbuduj_obszar_narracji(BORDER)
        sizer_wybory      = self._zbuduj_obszar_wyborow(BORDER)
        sizer_akcja       = self._zbuduj_pole_akcji(BORDER)

        sep = lambda: wx.StaticLine(self)  # noqa: E731

        root = wx.BoxSizer(wx.VERTICAL)
        root.Add(sizer_naglowek,                 flag=wx.EXPAND)
        root.Add(sizer_pasek_pliku,              flag=wx.EXPAND)
        root.Add(sep(),                          flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=BORDER)
        root.Add(sizer_tryb,                     flag=wx.EXPAND)
        root.Add(sep(),                          flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=BORDER)
        root.Add(sizer_pamiec,                   flag=wx.EXPAND)
        root.Add(sep(),                          flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=BORDER)
        root.Add(sizer_narracja, proportion=3,   flag=wx.EXPAND)
        root.Add(sep(),                          flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=BORDER)
        root.Add(sizer_wybory,                   flag=wx.EXPAND)
        root.Add(sep(),                          flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=BORDER)
        root.Add(sizer_akcja,                    flag=wx.EXPAND)

        self.SetSizer(root)

    # ------------------------------------------------------------------
    # BLOK A — Nagłówek modułu
    # ------------------------------------------------------------------
    def _zbuduj_naglowek(self, BORDER: int) -> wx.BoxSizer:
        heading = wx.StaticText(self, label=t("opowiesci.heading"))
        hf = heading.GetFont()
        hf.SetPointSize(16)
        hf.MakeBold()
        heading.SetFont(hf)

        self._description = wx.TextCtrl(
            self,
            value=self._tool_description,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.NO_BORDER,
            name=t("opowiesci.description_name"),
        )
        self._description.SetBackgroundColour(self.GetBackgroundColour())
        self._description.SetMinSize((-1, 90))

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(heading, flag=wx.ALL, border=BORDER)
        sizer.Add(
            self._description,
            flag=wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            border=BORDER,
        )
        return sizer

    # ------------------------------------------------------------------
    # BLOK B — Pasek pliku gry: nazwa + Nowa gra / Wczytaj / Zapisz
    # ------------------------------------------------------------------
    def _zbuduj_pasek_pliku(self, BORDER: int) -> wx.BoxSizer:
        lbl_nazwa = wx.StaticText(self, label=t("opowiesci.lbl_nazwa_gry"))

        self._txt_nazwa_gry = wx.TextCtrl(
            self,
            style=wx.TE_PROCESS_ENTER,
            name=t("opowiesci.txt_nazwa_gry_name"),
        )
        self._txt_nazwa_gry.SetHint(t("opowiesci.txt_nazwa_gry_hint"))
        self._txt_nazwa_gry.SetToolTip(t("opowiesci.txt_nazwa_gry_tooltip"))

        self._btn_nowa_gra = wx.Button(self, label=t("opowiesci.btn_nowa_gra_label"))
        self._btn_nowa_gra.SetToolTip(t("opowiesci.btn_nowa_gra_tooltip"))

        self._btn_wczytaj = wx.Button(self, label=t("opowiesci.btn_wczytaj_label"))
        self._btn_wczytaj.SetToolTip(t("opowiesci.btn_wczytaj_tooltip"))

        self._btn_zapisz = wx.Button(self, label=t("opowiesci.btn_zapisz_label"))
        self._btn_zapisz.SetToolTip(t("opowiesci.btn_zapisz_tooltip"))

        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(self._txt_nazwa_gry, proportion=1,
                flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=6)
        row.Add(self._btn_nowa_gra,
                flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=4)
        row.Add(self._btn_wczytaj,
                flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=4)
        row.Add(self._btn_zapisz,
                flag=wx.ALIGN_CENTER_VERTICAL)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(lbl_nazwa, flag=wx.LEFT | wx.RIGHT | wx.TOP, border=BORDER)
        sizer.Add(row,       flag=wx.EXPAND | wx.ALL,          border=BORDER)
        return sizer

    # ------------------------------------------------------------------
    # BLOK C — RadioBox wyboru trybu gry (Swobodny / Wyborów / Mniejsze zło)
    # ------------------------------------------------------------------
    def _zbuduj_radiobox_trybu(self, BORDER: int) -> wx.BoxSizer:
        choices = [
            t("opowiesci.tryb_swobodny"),
            t("opowiesci.tryb_wyborow"),
            t("opowiesci.tryb_mniejsze_zlo"),
        ]
        self._rb_tryb = wx.RadioBox(
            self,
            label=t("opowiesci.rb_tryb_label"),
            choices=choices,
            majorDimension=1,
            style=wx.RA_SPECIFY_COLS,
            name=t("opowiesci.rb_tryb_name"),
        )
        self._rb_tryb.SetToolTip(t("opowiesci.rb_tryb_tooltip"))

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self._rb_tryb, flag=wx.EXPAND | wx.ALL, border=BORDER)
        return sizer

    # ------------------------------------------------------------------
    # BLOK D — Wskaźnik pamięci modelu (placeholder; pełna logika w Fazie 4)
    # ------------------------------------------------------------------
    def _zbuduj_wskaznik_pamieci(self, BORDER: int) -> wx.BoxSizer:
        lbl = wx.StaticText(self, label=t("opowiesci.pamiec_lbl"))

        self._gauge_pamiec = wx.Gauge(self, range=100, name=t("opowiesci.pamiec_gauge_name"))
        self._gauge_pamiec.SetValue(0)

        self._lbl_pamiec_status = wx.StaticText(
            self, label=t("opowiesci.pamiec_status_init"),
            name=t("opowiesci.pamiec_status_name"),
        )

        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(lbl,                     flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=8)
        row.Add(self._gauge_pamiec,      proportion=1,
                flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=8)
        row.Add(self._lbl_pamiec_status, flag=wx.ALIGN_CENTER_VERTICAL)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(row, flag=wx.EXPAND | wx.ALL, border=BORDER)
        return sizer

    # ------------------------------------------------------------------
    # BLOK E — Obszar narracji (TextCtrl readonly multiline) — KLUCZOWY A11y
    # ------------------------------------------------------------------
    def _zbuduj_obszar_narracji(self, BORDER: int) -> wx.BoxSizer:
        lbl = wx.StaticText(self, label=t("opowiesci.lbl_narracja"))
        lf = lbl.GetFont()
        lf.SetPointSize(11)
        lf.MakeBold()
        lbl.SetFont(lf)

        self._txt_narracja = wx.TextCtrl(
            self,
            value=t("opowiesci.txt_narracja_init"),
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_BESTWRAP,
            name=t("opowiesci.txt_narracja_name"),
        )
        self._txt_narracja.SetToolTip(t("opowiesci.txt_narracja_tooltip"))
        self._txt_narracja.SetMinSize((-1, 200))

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(lbl,
                 flag=wx.LEFT | wx.RIGHT | wx.TOP, border=BORDER)
        sizer.Add(self._txt_narracja, proportion=1,
                 flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, border=BORDER)
        return sizer

    # ------------------------------------------------------------------
    # BLOK F — Obszar wyborów (placeholder w Fazie 1; dynamic w Fazie 2)
    # ------------------------------------------------------------------
    def _zbuduj_obszar_wyborow(self, BORDER: int) -> wx.BoxSizer:
        lbl = wx.StaticText(self, label=t("opowiesci.lbl_wybory"))
        lf = lbl.GetFont()
        lf.SetPointSize(11)
        lf.MakeBold()
        lbl.SetFont(lf)
        # Referencja zatrzymana — hide/show steruje :meth:`_aktywuj_obszar_wyborow`.
        self._lbl_wybory = lbl

        # Faza 1: kontener pusty z placeholderem-tekstem. Faza 2 będzie
        # czyścić sizer i dodawać wx.Button-y dynamicznie z odpowiedzi LLM
        # (pole `wybory[]` JSON-schema).
        self._panel_wyborow = wx.Panel(self, name=t("opowiesci.panel_wyborow_name"))
        sizer_wyborow = wx.BoxSizer(wx.VERTICAL)
        self._panel_wyborow.SetSizer(sizer_wyborow)
        self._sizer_wyborow = sizer_wyborow  # zachowujemy referencję dla Fazy 2

        placeholder = wx.StaticText(
            self._panel_wyborow,
            label=t("opowiesci.panel_wyborow_placeholder"),
        )
        placeholder.Disable()  # wizualnie wyszarzony — sygnał A11y „nieaktywny"
        sizer_wyborow.Add(placeholder, flag=wx.ALL, border=4)
        self._lbl_placeholder_wyborow = placeholder

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(lbl,
                 flag=wx.LEFT | wx.RIGHT | wx.TOP, border=BORDER)
        sizer.Add(self._panel_wyborow,
                 flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, border=BORDER)
        return sizer

    # ------------------------------------------------------------------
    # BLOK G — Pole akcji (free-text + slash) + przycisk Wyślij
    # ------------------------------------------------------------------
    def _zbuduj_pole_akcji(self, BORDER: int) -> wx.BoxSizer:
        lbl = wx.StaticText(self, label=t("opowiesci.lbl_akcja"))

        self._txt_akcja = wx.TextCtrl(
            self,
            style=wx.TE_MULTILINE,
            name=t("opowiesci.txt_akcja_name"),
        )
        self._txt_akcja.SetHint(t("opowiesci.txt_akcja_hint"))
        self._txt_akcja.SetToolTip(t("opowiesci.txt_akcja_tooltip"))
        self._txt_akcja.SetMinSize((-1, 60))

        self._btn_wyslij = wx.Button(self, label=t("opowiesci.btn_wyslij_label"))
        self._btn_wyslij.SetToolTip(t("opowiesci.btn_wyslij_tooltip"))

        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(self._txt_akcja, proportion=1,
                flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=6)
        row.Add(self._btn_wyslij,
                flag=wx.ALIGN_CENTER_VERTICAL)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(lbl, flag=wx.LEFT | wx.RIGHT | wx.TOP, border=BORDER)
        sizer.Add(row, flag=wx.EXPAND | wx.ALL,          border=BORDER)
        return sizer

    # ==================================================================
    # WIDOCZNOŚĆ DYNAMICZNA — kontrola pokazywania sekcji w runtime
    # ==================================================================
    def _aktywuj_obszar_wyborow(self, visible: bool) -> None:
        """Pokazuje albo ukrywa cały obszar wyborów (label + panel przycisków).

        Krytyczne dla A11y: ukryty widget jest pomijany przez nawigację Tab
        i czytniki ekranu (NVDA nie wciągnie go do listy elementów), więc
        gracz nie wpada przez Tab do pustego placeholdera. ``Disable()``
        nie wystarczy — to tylko sygnał wizualny, fokus nadal tam wchodzi.

        Strategia w kolejnych fazach:
            * Faza 1 — zawsze ``False`` (silnika narracyjnego brak).
            * Faza 2 — w trybie Swobodnym (3) ZAWSZE ``False`` (gracz
              steruje free-textem). W trybach Wyborów (4) i Mniejsze
              zło (5) ``True`` po pomyślnej walidacji JSON-schema z
              niepustą tablicą ``wybory[]``; halucynacja modelu (puste
              ``wybory[]``) → ``False``.
        """
        self._lbl_wybory.Show(visible)
        self._panel_wyborow.Show(visible)
        self.Layout()

    # ==================================================================
    # ZDARZENIA — wszystkie ślepe w Fazie 1; Faza 2/3/4 podłączą logikę
    # ==================================================================
    def _bind_events(self) -> None:
        self._btn_nowa_gra.Bind(wx.EVT_BUTTON, self._on_placeholder)
        self._btn_wczytaj.Bind(wx.EVT_BUTTON, self._on_placeholder)
        self._btn_zapisz.Bind(wx.EVT_BUTTON, self._on_placeholder)
        self._btn_wyslij.Bind(wx.EVT_BUTTON, self._on_placeholder)
        # `_rb_tryb` nie ma callbacku w Fazie 1 — wybór trybu zostanie odczytany
        # dopiero przy uruchomieniu gry (Faza 3).

    def _on_placeholder(self, _event: wx.Event) -> None:
        """Stub Fazy 1 — informuje że funkcja zostanie podłączona później."""
        wx.MessageBox(
            t("opowiesci.placeholder_msg_tresc"),
            t("opowiesci.placeholder_msg_tytul"),
            wx.OK | wx.ICON_INFORMATION,
            self,
        )
