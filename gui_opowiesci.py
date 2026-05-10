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
import threading
from typing import Any

import wx

import opowiesci_ai as oai
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

    # Mapowanie indeksu RadioBox-a (0/1/2) na numer trybu w `.mode` (3/4/5).
    # Kontynuuje numerację Reżysera (0=Burza, 1=Reżyser1, 2=Reżyser2).
    _MAPA_TRYB_RB_NA_INT = (oai.TRYB_SWOBODNY, oai.TRYB_WYBOROW, oai.TRYB_MNIEJSZE_ZLO)

    def __init__(self, parent: wx.Window) -> None:
        super().__init__(parent, style=wx.TAB_TRAVERSAL)
        self.SetName(t("opowiesci.panel_name"))

        # Wzorzec z RezyserPanel: duży tekst opisu modułu z YAML, nie z kodu.
        # Pobieramy raz w konstruktorze — t() działa dopiero po
        # ``i18n.ustaw_jezyk()`` w main.main().
        self._tool_description = t("opowiesci.tool_description")

        # ---- Faza 2: stan silnika LLM (klient + niezmienny snapshot) -----
        # ``_snapshot`` żyje w pamięci panelu — Faza 3 zsynchronizuje go z
        # plikami `.game.json`. Liczniki tury startują od 0; pierwsza akcja
        # gracza inkrementuje do 1 przed wysyłką.
        self._client: Any = None
        self._api_dostepne: bool = False
        self._snapshot: oai.SnapshotOpowiesci = oai.SnapshotOpowiesci(
            nazwa_gry="", numer_tury=0,
        )
        self._worker_thread: threading.Thread | None = None

        self._build_ui()
        self._bind_events()
        self._init_api()

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
        # Faza 3 podmieni `_btn_nowa_gra`/`_btn_wczytaj`/`_btn_zapisz` na realny
        # lifecycle plików; w Fazie 2 nadal idą w stub.
        self._btn_nowa_gra.Bind(wx.EVT_BUTTON, self._on_placeholder)
        self._btn_wczytaj.Bind(wx.EVT_BUTTON, self._on_placeholder)
        self._btn_zapisz.Bind(wx.EVT_BUTTON, self._on_placeholder)
        # Faza 2: `_btn_wyslij` ma realnego workera silnika narracyjnego.
        self._btn_wyslij.Bind(wx.EVT_BUTTON, self._on_wyslij)
        # `_rb_tryb` bez callbacku — wybór trybu odczytujemy w `_on_wyslij`.

    def _on_placeholder(self, _event: wx.Event) -> None:
        """Stub Fazy 1 — informuje że funkcja zostanie podłączona później."""
        wx.MessageBox(
            t("opowiesci.placeholder_msg_tresc"),
            t("opowiesci.placeholder_msg_tytul"),
            wx.OK | wx.ICON_INFORMATION,
            self,
        )

    # ==================================================================
    # FAZA 2 — Silnik LLM
    # ==================================================================
    def _init_api(self) -> None:
        """Inicjuje klienta OpenAI z ``golden_key.env``.

        Wzorzec :meth:`gui_rezyser.RezyserPanel._init_api` — błąd ładowania
        nigdy nie blokuje otwarcia panelu. Brak klucza → ``_api_dostepne``
        zostaje ``False``, a :meth:`_on_wyslij` pokaże MessageBox z
        `opowiesci.brak_api_tresc`. Sama detekcja przeniesiona do
        :func:`opowiesci_ai.inicjalizuj_klienta` — moduł silnika i tak
        potrzebuje tej funkcji do testów izolowanych.
        """
        app_dir = os.path.dirname(os.path.abspath(__file__))
        klient = oai.inicjalizuj_klienta(app_dir)
        if klient is not None:
            self._client = klient
            self._api_dostepne = True

    def _aktualny_tryb_int(self) -> int:
        """Zwraca numer trybu (3/4/5) ze stanu RadioBox-a (indeks 0/1/2)."""
        return self._MAPA_TRYB_RB_NA_INT[self._rb_tryb.GetSelection()]

    # ------------------------------------------------------------------
    # _on_wyslij: walidacja → spawn daemon thread → _wyslij_worker
    # ------------------------------------------------------------------
    def _on_wyslij(self, _event: wx.Event) -> None:
        """Handler przycisku „Wyślij" — bramka między GUI a wątkiem tła."""
        if not self._api_dostepne:
            wx.MessageBox(
                t("opowiesci.brak_api_tresc"),
                t("opowiesci.brak_api_tytul"),
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return

        user_text = self._txt_akcja.GetValue().strip()
        if not user_text:
            wx.MessageBox(
                t("opowiesci.puste_pole_tresc"),
                t("opowiesci.puste_pole_tytul"),
                wx.OK | wx.ICON_WARNING,
                self,
            )
            self._txt_akcja.SetFocus()
            return

        nazwa = self._txt_nazwa_gry.GetValue().strip()
        if not nazwa:
            # Faza 2 wymaga nazwy do logu i kontekstu, nawet jeśli plików
            # jeszcze nie zapisujemy (lifecycle dochodzi w Fazie 3).
            wx.MessageBox(
                t("opowiesci.puste_nazwa_tresc"),
                t("opowiesci.puste_nazwa_tytul"),
                wx.OK | wx.ICON_WARNING,
                self,
            )
            self._txt_nazwa_gry.SetFocus()
            return

        tryb = self._aktualny_tryb_int()

        # Aktualizujemy snapshot przed wysyłką: nazwa + nowy numer tury.
        # Snapshot jest niezmienny po stronie wątku tła, ale tutaj jeszcze
        # możemy mutować referencję panelu (GIL: pojedyncze przypisanie
        # atrybutu jest atomowe w CPythonie).
        self._snapshot = oai.SnapshotOpowiesci(
            nazwa_gry=nazwa,
            numer_tury=self._snapshot.numer_tury + 1,
            ostatnie_tury=self._snapshot.ostatnie_tury,
            postacie_aktywne=self._snapshot.postacie_aktywne,
            stan_poprzedni=self._snapshot.stan_poprzedni,
            seed_swiata=self._snapshot.seed_swiata,
            jezyk_projektu=self._snapshot.jezyk_projektu,
        )

        # Lock UI: zapobiega podwójnej wysyłce, dezorientacji NVDA.
        self._btn_wyslij.Disable()
        self._txt_akcja.SetValue("")
        self._lbl_pamiec_status.SetLabel(t("opowiesci.status_wysylanie"))

        # Daemon thread — proces nie czeka na nas przy zamknięciu aplikacji.
        snapshot_kopia = self._snapshot
        self._worker_thread = threading.Thread(
            target=self._wyslij_worker,
            args=(snapshot_kopia, user_text, tryb),
            daemon=True,
        )
        self._worker_thread.start()

    # ------------------------------------------------------------------
    # _wyslij_worker: w wątku tła; do GUI tylko przez wx.CallAfter
    # ------------------------------------------------------------------
    def _wyslij_worker(
        self,
        snapshot:   oai.SnapshotOpowiesci,
        user_input: str,
        tryb:       int,
    ) -> None:
        """Worker w tle — wątek nigdy nie dotyka widgetów wxPython bezpośrednio.

        Wszelka komunikacja z GUI idzie przez ``wx.CallAfter`` — gwarantuje
        wykonanie w wątku głównym (event loop wxPython jest single-threaded).
        Wzorzec z :meth:`gui_rezyser.RezyserPanel._wyslij_worker`.
        """
        try:
            wynik = oai.generuj_ture(
                klient=self._client,
                snapshot=snapshot,
                user_input=user_input,
                tryb=tryb,
            )
        except Exception as exc:  # noqa: BLE001
            # Łapiemy wszystko (RateLimitError, APITimeoutError, RuntimeError
            # po wyczerpaniu retry, JSONDecode, etc.) — kategoryzacja per typ
            # leży w :meth:`_obsluz_blad` żeby trzymać worker krótki.
            wx.CallAfter(self._obsluz_blad, exc)
            return

        wx.CallAfter(self._obsluz_ture, wynik, user_input, tryb)

    # ------------------------------------------------------------------
    # _obsluz_ture: callback w wątku UI — append narracji + wybory
    # ------------------------------------------------------------------
    def _obsluz_ture(
        self,
        wynik:      oai.WynikTury,
        user_input: str,
        tryb:       int,
    ) -> None:
        """Aktualizacja UI po sukcesie tury — wszystko w wątku głównym."""
        # 1. Append narracji do TextCtrl. AppendText jest tańszy niż SetValue
        # (nie kasuje historii) i zachowuje pozycję kursora bliską końca.
        naglowek = t(
            "opowiesci.tura_naglowek_format",
            numer=self._snapshot.numer_tury,
        )
        self._txt_narracja.AppendText(naglowek + wynik.narracja)
        self._txt_narracja.SetInsertionPointEnd()

        # 2. Aktualizacja snapshotu: nowe `ostatnie_tury` + postacie + stan.
        # Trzymamy ostatnie 6 par (akcja, narracja_skrót) — Faza 4 dorobi
        # streszczenie po 70% kontekstu; tu prosty FIFO.
        nowe_ostatnie = list(self._snapshot.ostatnie_tury)
        nowe_ostatnie.append({
            "akcja_gracza":  user_input,
            "narracja_skrot": wynik.narracja[:400],  # skracamy do oszczędności kontekstu
        })
        nowe_ostatnie = nowe_ostatnie[-6:]

        self._snapshot = oai.SnapshotOpowiesci(
            nazwa_gry=self._snapshot.nazwa_gry,
            numer_tury=self._snapshot.numer_tury,
            ostatnie_tury=nowe_ostatnie,
            postacie_aktywne=wynik.postacie_aktywne,
            stan_poprzedni=wynik.stan,
            seed_swiata=self._snapshot.seed_swiata,
            jezyk_projektu=self._snapshot.jezyk_projektu,
        )

        # 3. Wybory: w trybie Swobodnym (3) zawsze ukryte, w 4/5 widoczne
        # tylko gdy LLM zwrócił niepustą tablicę (halucynacja → ukrywamy).
        self._przeladuj_wybory(wynik.wybory, tryb)

        # 4. Status + odblokowanie + dźwięk + fokus.
        self._lbl_pamiec_status.SetLabel(t("opowiesci.status_gotowe"))
        self._btn_wyslij.Enable()
        wx.Bell()  # A11y: NVDA usłyszy „pinga" — sygnał gotowości
        self._txt_narracja.SetFocus()  # NVDA przeczyta nową narrację

    def _przeladuj_wybory(self, wybory: list[dict[str, str]], tryb: int) -> None:
        """Rebuilduje obszar wyborów: kasuje stare przyciski, dodaje nowe.

        KOLEJNOŚĆ KRYTYCZNA (znaleziono w analizie codebase):
        1. ``_sizer_wyborow.Clear(delete_windows=True)`` — usuwa stare widgety
        2. dodanie nowych ``wx.Button`` z bind-em na ``_on_wybor_btn``
        3. ``_panel_wyborow.Layout()`` ORAZ ``self.Layout()`` — sizery
           zewnętrzne też muszą się przeliczyć po zmianie zawartości
        4. ``_aktywuj_obszar_wyborow(visible)`` — POTEM, bo Show/Hide z
           pustym sizerem nie ustabilizowałby layoutu
        """
        self._sizer_wyborow.Clear(delete_windows=True)
        # Referencja do placeholdera została zniszczona razem z panelem — usuwamy.
        self._lbl_placeholder_wyborow = None

        pokazac = (
            tryb in (oai.TRYB_WYBOROW, oai.TRYB_MNIEJSZE_ZLO)
            and len(wybory) > 0
        )

        if pokazac:
            for wybor in wybory:
                etykieta = f"{wybor['id']}.  {wybor['tekst']}"
                btn = wx.Button(self._panel_wyborow, label=etykieta)
                btn.SetToolTip(t(
                    "opowiesci.btn_wybor_tooltip_format",
                    tekst=wybor["tekst"],
                ))
                # Closure z `tekst` — robimy lambda z default arg żeby
                # uniknąć late-binding gotcha (każdy przycisk dostaje
                # SWÓJ tekst, nie ostatniego z pętli).
                btn.Bind(
                    wx.EVT_BUTTON,
                    lambda evt, t_wyb=wybor["tekst"]: self._on_wybor_btn(evt, t_wyb),
                )
                self._sizer_wyborow.Add(btn, flag=wx.EXPAND | wx.ALL, border=4)

        self._panel_wyborow.Layout()
        self.Layout()
        self._aktywuj_obszar_wyborow(pokazac)

    def _on_wybor_btn(self, _event: wx.Event, tekst_wyboru: str) -> None:
        """Klik na przycisku wyboru — wpisuje tekst do pola akcji + auto-wysyła."""
        self._txt_akcja.SetValue(tekst_wyboru)
        # Symulujemy klik na „Wyślij" — przechodzi przez tę samą walidację.
        # Bezpośrednie wywołanie `_on_wyslij(None)` zamiast EVT, bo to nie
        # jest zdarzenie z magistrali wxPython, tylko nasza synteza.
        self._on_wyslij(_event)

    # ------------------------------------------------------------------
    # _obsluz_blad: callback w wątku UI po wyjątku w workerze
    # ------------------------------------------------------------------
    def _obsluz_blad(self, exc: Exception) -> None:
        """Mapuje wyjątek na komunikat lokalizowany i pokazuje dialog."""
        # Lazy import — `openai` może nie być dostępne (brak klucza, brak
        # paczki w środowisku testowym), a wtedy `import openai` na górze
        # pliku rzuciłby ImportError i zablokowałby otwarcie panelu.
        try:
            import openai  # noqa: PLC0415
            if isinstance(exc, openai.RateLimitError):
                msg = t("opowiesci.err_rate_limit")
            elif isinstance(exc, openai.APITimeoutError):
                msg = t("opowiesci.err_timeout")
            else:
                msg = str(exc)
        except ImportError:
            msg = str(exc)

        # Heurystyka: nasz custom RuntimeError o niewłaściwej strukturze
        # ma w treści „niewłaściwą strukturę JSON" — podmieniamy na klucz
        # lokalizowany żeby user nie widział angielskiej technicznej treści.
        if "niewłaściwą strukturę JSON" in msg:
            msg = t("opowiesci.err_struktura")

        self._lbl_pamiec_status.SetLabel(t("opowiesci.status_blad"))
        self._btn_wyslij.Enable()
        self._wyswietl_blad_ai(msg)

    # ------------------------------------------------------------------
    # _wyswietl_blad_ai: krótki błąd → MessageBox; długi → dialog z TextCtrl
    # ------------------------------------------------------------------
    def _wyswietl_blad_ai(self, tresc_bledu: str) -> None:
        """Wzorzec z :meth:`gui_rezyser.RezyserPanel._wyswietl_blad_ai`.

        Krótki błąd (≤200 znaków bez newline) idzie w MessageBox — szybkie
        powiadomienie. Długi (np. dump traceback) idzie w dialog z
        ``wx.TextCtrl(TE_READONLY)``, który NVDA potrafi przeczytać i
        który użytkownik może kopiować (Ctrl+C).
        """
        jest_krotki = len(tresc_bledu) <= 200 and "\n" not in tresc_bledu
        if jest_krotki:
            wx.MessageBox(
                tresc_bledu,
                t("opowiesci.blad_ai_tytul"),
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return

        dlg = wx.Dialog(
            self,
            title=t("opowiesci.blad_ai_szczegoly_tytul"),
            size=(640, 400),
        )
        sizer = wx.BoxSizer(wx.VERTICAL)
        lbl_head = wx.StaticText(dlg, label=t("opowiesci.blad_ai_naglowek"))
        lbl_copy = wx.StaticText(dlg, label=t("opowiesci.blad_ai_lbl_tresc"))
        txt = wx.TextCtrl(
            dlg,
            value=tresc_bledu,
            style=wx.TE_MULTILINE | wx.TE_READONLY,
            name=t("opowiesci.blad_ai_tresc_name"),
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
