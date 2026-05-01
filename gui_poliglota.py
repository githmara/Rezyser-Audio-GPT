"""
gui_poliglota.py – Panel modułu „Poliglota AI" (wxPython, wersja wydawnicza).

Po refaktorze do wersji 13.0 ten plik pełni WYŁĄCZNIE rolę warstwy widoku
(zgodnie z nazwą ``gui_*``). Cała logika przetwarzania tekstu żyje w:

  * ``core_poliglota.py`` – silnik reguł fonetycznych i szyfrów (YAML),
  * ``tlumacz_ai.py``     – tłumacz OpenAI GPT-4o w wątku tła.

GUI:
  1. Wczytuje plik (.txt / .html / .htm / .docx) do pamięci.
  2. Wyświetla listy wariantów (akcenty / szyfry) pobrane z
     ``core_poliglota.lista_wariantow(...)`` – dzięki temu dodanie nowej
     reguły YAML nie wymaga zmian w tym pliku.
  3. Woła ``core_poliglota.przetworz(...)`` lub
     ``tlumacz_ai.tlumacz_dlugi_tekst(...)`` i prezentuje wynik.
  4. Zapisuje wynik przez ``core_poliglota.zapisz_wynik(...)``.

Wzorzec przetwarzania na GUI sprowadza się w praktyce do:

    wynik = core_poliglota.przetworz(tekst, tryb="Szyfrant", jezyk="pl",
                                     wariant="cezar", przesuniecie=7)

Wersja 13.1: cały tekst widoczny dla użytkownika pochodzi z
``dictionaries/pl/gui/ui.yaml`` (sekcja ``poliglota``) przez moduł
:mod:`i18n`.
"""

from __future__ import annotations

import os
import threading

import docx
from dotenv import load_dotenv

import wx

import core_poliglota
import i18n
import tlumacz_ai
from i18n import t


# 13.2+: język bazowy pipeline'u Poligloty żyje na poziomie instancji
# (``self._jezyk_aktywny``). Po wczytaniu pliku panel wywołuje
# ``core_poliglota.wykryj_jezyk_zrodlowy(...)``, który waliduje wynik wobec
# dostępnych folderów w ``dictionaries/`` i przełącza pipeline na wykryty
# kompletny język.
#
# 13.4: dopóki nie ma wczytanego pliku, default bierzemy z języka UI
# (``i18n.aktualny_jezyk()``) — pod warunkiem, że ma komplet reguł
# w ``dictionaries/``. Inaczej spadamy na ``pl`` (rdzeń projektu, zawsze
# kompletny). Bez tego użytkownik EN widział angielski opis sekcji,
# ale po przełączeniu trybu na Reżysera/Szyfranta combobox zalewały
# polskie etykiety akcentów (bug zaobserwowany na 13.3.1).
JEZYK_FALLBACK = "pl"


def _wybierz_domyslny_jezyk_pipeline() -> str:
    """Zwraca kod języka, którym Poliglota zainicjuje pipeline bez projektu.

    Priorytet: aktualny język UI (jeśli ma komplet reguł), fallback na ``pl``.
    """
    ui = i18n.aktualny_jezyk()
    kompletne = core_poliglota.dostepne_jezyki_bazowe()
    if ui in kompletne:
        return ui
    return JEZYK_FALLBACK


class PoliglotaPanel(wx.Panel):
    """Panel modułu „Poliglota AI" – cienka warstwa prezentacji.

    Obsługuje trzy tryby pracy, ale sam nie zawiera logiki przetwarzania:
        - Tłumacz AI (OpenAI gpt-4o) – woła ``tlumacz_ai.tlumacz_dlugi_tekst``.
        - Tryb Reżysera (YAML: dictionaries/pl/akcenty/*) – woła
          ``core_poliglota.przetworz(tryb="Rezyser", ...)``.
        - Tryb Szyfranta (YAML: dictionaries/pl/szyfry/*) – woła
          ``core_poliglota.przetworz(tryb="Szyfrant", ...)``.

    Wywołania sieciowe (AI) idą przez ``threading.Thread`` + ``wx.CallAfter``.
    Wywołania lokalne (Reżyser/Szyfrant) są szybkie i uruchamiane synchronicznie
    w wątku GUI.
    """

    ENV_FILENAME = "golden_key.env"

    # ------------------------------------------------------------------
    # Konstruktor
    # ------------------------------------------------------------------
    def __init__(self, parent: wx.Window) -> None:
        super().__init__(parent, style=wx.TAB_TRAVERSAL)
        self.SetName(t("poliglota.panel_name"))

        # Stan wewnętrzny (odpowiednik st.session_state)
        self._file_content: str = ""
        self._file_ext: str = ""
        self._oryginalna_nazwa: str = "nieznany"
        self._plik_katalog: str = "."
        self._sciezka_oryginalu: str | None = None

        # Klient OpenAI (None → brak klucza, AI wyłączone)
        self._client = None
        self._api_dostepne: bool = False
        self._init_api()

        # Wątek tła tłumacza AI (referencja, by nie uruchamiać drugiego)
        self._worker_thread: threading.Thread | None = None

        # Aktywny język pipeline'u (akcenty/szyfry/cezar). Bez wczytanego
        # pliku domyślnie idzie z języka UI (gdy ma komplet reguł), żeby
        # użytkownik EN nie zobaczył polskich etykiet akcentów w combo.
        # Po wczytaniu pliku podmieniany przez ``_odswiez_warianty()``
        # na wynik ``wykryj_jezyk_zrodlowy()``.
        self._jezyk_aktywny: str = _wybierz_domyslny_jezyk_pipeline()

        # Konfiguracje wariantów (z YAML) – pobierane raz przy starcie panelu,
        # ponownie przy zmianie ``self._jezyk_aktywny``.
        self._akcenty = core_poliglota.lista_wariantow(
            core_poliglota.TRYB_REZYSER, self._jezyk_aktywny)
        self._szyfry  = core_poliglota.lista_wariantow(
            core_poliglota.TRYB_SZYFRANT, self._jezyk_aktywny)

        self._build_ui()
        self._bind_events()
        self._refresh_mode_ui()

        wx.CallAfter(self._description.SetFocus)

    # ------------------------------------------------------------------
    # Inicjowanie klienta OpenAI
    # ------------------------------------------------------------------
    def _init_api(self) -> None:
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

    # ==================================================================
    # BUDOWANIE INTERFEJSU
    # ==================================================================
    def _build_ui(self) -> None:
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        BORDER = 12

        # ── Nagłówek ────────────────────────────────────────────────────
        heading = wx.StaticText(self, label=t("poliglota.heading"))
        font = heading.GetFont()
        font.SetPointSize(16); font.MakeBold()
        heading.SetFont(font)

        # ── Opis narzędzia (czytany przez NVDA) ──────────────────────────
        self._description = wx.TextCtrl(
            self,
            value=t("poliglota.tool_description"),
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.NO_BORDER,
            name=t("poliglota.description_name"),
        )
        self._description.SetBackgroundColour(self.GetBackgroundColour())

        # ── Sekcja 1: Wczytywanie pliku ──────────────────────────────────
        lbl_section1 = self._naglowek(t("poliglota.section1_heading"))
        lbl_file = wx.StaticText(self, label=t("poliglota.lbl_plik"))

        self._txt_file = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER,
                                     name=t("poliglota.txt_plik_name"))
        self._txt_file.SetHint(t("poliglota.txt_plik_hint"))

        self._btn_browse = wx.Button(self, label=t("poliglota.btn_przegladaj"))
        self._btn_browse.SetToolTip(t("poliglota.btn_przegladaj_tooltip"))

        file_row = wx.BoxSizer(wx.HORIZONTAL)
        file_row.Add(self._txt_file,   proportion=1,
                     flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=6)
        file_row.Add(self._btn_browse, flag=wx.ALIGN_CENTER_VERTICAL)

        self._btn_load = wx.Button(self, label=t("poliglota.btn_wczytaj"))
        self._btn_load.SetToolTip(t("poliglota.btn_wczytaj_tooltip"))

        self._btn_clear = wx.Button(self, label=t("poliglota.btn_wyczysc"))
        self._btn_clear.SetToolTip(t("poliglota.btn_wyczysc_tooltip"))
        self._btn_clear.Disable()

        load_row = wx.BoxSizer(wx.HORIZONTAL)
        load_row.Add(self._btn_load,  flag=wx.RIGHT, border=8)
        load_row.Add(self._btn_clear)

        self._lbl_file_status = wx.TextCtrl(
            self, value=t("poliglota.plik_status_brak"),
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.NO_BORDER)
        self._lbl_file_status.SetBackgroundColour(self.GetBackgroundColour())
        self._lbl_file_status.SetName(t("poliglota.lbl_plik_status_name"))

        # ── Sekcja 2: Konfiguracja trybu pracy ──────────────────────────
        lbl_section2 = self._naglowek(t("poliglota.section2_heading"))

        self._rb_ai = wx.RadioButton(
            self, label=t("poliglota.rb_ai"),
            style=wx.RB_GROUP, name=t("poliglota.rb_ai_name"))
        self._rb_rezyser = wx.RadioButton(
            self, label=t("poliglota.rb_rezyser"),
            name=t("poliglota.rb_rezyser_name"))
        self._rb_szyfrant = wx.RadioButton(
            self, label=t("poliglota.rb_szyfrant"),
            name=t("poliglota.rb_szyfrant_name"))

        if not self._api_dostepne:
            self._rb_ai.Disable()
            self._rb_ai.SetLabel(t("poliglota.rb_ai_disabled"))
            self._rb_rezyser.SetValue(True)
        else:
            self._rb_ai.SetValue(True)

        self._pnl_ai       = self._build_panel_ai()
        self._pnl_rezyser  = self._build_panel_rezyser()
        self._pnl_szyfrant = self._build_panel_szyfrant()
        self._pnl_szyfrant.Hide()

        # ── Sekcja 3: Przetwarzanie ──────────────────────────────────────
        lbl_section3 = self._naglowek(t("poliglota.section3_heading"))

        self._btn_process = wx.Button(self, label=t("poliglota.btn_process"))
        self._btn_process.SetToolTip(t("poliglota.btn_process_tooltip"))

        self._gauge = wx.Gauge(self, range=100,
                               style=wx.GA_HORIZONTAL | wx.GA_SMOOTH)
        self._gauge.SetValue(0); self._gauge.Hide()

        self._lbl_progress = wx.TextCtrl(
            self, value="",
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.NO_BORDER)
        self._lbl_progress.SetBackgroundColour(self.GetBackgroundColour())
        self._lbl_progress.SetName(t("poliglota.lbl_progress_name"))
        self._lbl_progress.Hide()

        # ── Sekcja 4: Wynik ──────────────────────────────────────────────
        lbl_section4 = self._naglowek(t("poliglota.section4_heading"))

        self._txt_result = wx.TextCtrl(
            self, value="",
            style=wx.TE_MULTILINE | wx.TE_READONLY,
            name=t("poliglota.txt_wynik_name"))
        self._txt_result.SetMinSize((-1, 200))
        self._txt_result.SetHint(t("poliglota.txt_wynik_hint"))

        # ── Złożenie layoutu ─────────────────────────────────────────────
        main_sizer.Add(heading,              flag=wx.ALL, border=BORDER)
        main_sizer.Add(self._description,    flag=wx.LEFT | wx.RIGHT | wx.BOTTOM, border=BORDER)
        main_sizer.Add(wx.StaticLine(self),  flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=BORDER)

        main_sizer.Add(lbl_section1,         flag=wx.LEFT | wx.TOP | wx.RIGHT, border=BORDER)
        main_sizer.Add(lbl_file,             flag=wx.LEFT | wx.TOP | wx.RIGHT, border=BORDER)
        main_sizer.Add(file_row,             flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, border=8)
        main_sizer.Add(load_row,             flag=wx.LEFT | wx.TOP, border=BORDER)
        main_sizer.Add(self._lbl_file_status, flag=wx.EXPAND | wx.ALL, border=BORDER)
        main_sizer.Add(wx.StaticLine(self),  flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=BORDER)

        main_sizer.Add(lbl_section2,         flag=wx.LEFT | wx.TOP | wx.RIGHT, border=BORDER)
        main_sizer.Add(self._rb_ai,          flag=wx.LEFT | wx.TOP, border=BORDER)
        main_sizer.Add(self._rb_rezyser,     flag=wx.LEFT | wx.TOP, border=BORDER)
        main_sizer.Add(self._rb_szyfrant,    flag=wx.LEFT | wx.TOP, border=BORDER)
        main_sizer.Add(self._pnl_ai,         flag=wx.EXPAND | wx.ALL, border=BORDER)
        main_sizer.Add(self._pnl_rezyser,    flag=wx.EXPAND | wx.ALL, border=BORDER)
        main_sizer.Add(self._pnl_szyfrant,   flag=wx.EXPAND | wx.ALL, border=BORDER)
        main_sizer.Add(wx.StaticLine(self),  flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=BORDER)

        main_sizer.Add(lbl_section3,         flag=wx.LEFT | wx.TOP | wx.RIGHT, border=BORDER)
        main_sizer.Add(self._btn_process,    flag=wx.LEFT | wx.TOP | wx.BOTTOM, border=BORDER)
        main_sizer.Add(self._gauge,          flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=BORDER)
        main_sizer.Add(self._lbl_progress,   flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=BORDER)
        main_sizer.Add(wx.StaticLine(self),  flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=BORDER)

        main_sizer.Add(lbl_section4,         flag=wx.LEFT | wx.TOP | wx.RIGHT, border=BORDER)
        main_sizer.Add(self._txt_result,     proportion=1,
                       flag=wx.EXPAND | wx.ALL, border=BORDER)

        self.SetSizer(main_sizer)

    def _naglowek(self, tekst: str) -> wx.StaticText:
        lbl = wx.StaticText(self, label=tekst)
        font = lbl.GetFont()
        font.SetPointSize(12); font.MakeBold()
        lbl.SetFont(font)
        return lbl

    # ---------- Panel AI -----------------------------------------------
    def _build_panel_ai(self) -> wx.Panel:
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        lbl = wx.StaticText(panel, label=t("poliglota.lbl_jezyk_docelowy"))
        self._txt_lang = wx.TextCtrl(panel, style=wx.TE_PROCESS_ENTER,
                                     name=t("poliglota.txt_jezyk_name"))
        self._txt_lang.SetHint(t("poliglota.txt_jezyk_hint"))

        sizer.Add(lbl,           flag=wx.BOTTOM, border=4)
        sizer.Add(self._txt_lang, flag=wx.EXPAND)
        panel.SetSizer(sizer)
        return panel

    # ---------- Panel Reżysera -----------------------------------------
    def _build_panel_rezyser(self) -> wx.Panel:
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        lbl = wx.StaticText(panel, label=t("poliglota.lbl_akcent"))
        etykiety = [w["etykieta"] for w in self._akcenty]
        self._combo_akcent = wx.ComboBox(panel, choices=etykiety,
                                         style=wx.CB_READONLY,
                                         name=t("poliglota.combo_akcent_name"))
        if etykiety:
            self._combo_akcent.SetSelection(0)
        self._combo_akcent.SetToolTip(t("poliglota.combo_akcent_tooltip"))

        self._lbl_iso = wx.StaticText(panel, label=t("poliglota.lbl_iso"))
        self._txt_iso = wx.TextCtrl(panel, name=t("poliglota.txt_iso_name"))
        self._txt_iso.SetMaxLength(2)
        self._txt_iso.SetHint(t("poliglota.txt_iso_hint"))
        self._lbl_iso.Hide(); self._txt_iso.Hide()

        sizer.Add(lbl,                flag=wx.BOTTOM, border=4)
        sizer.Add(self._combo_akcent, flag=wx.EXPAND | wx.BOTTOM, border=8)
        sizer.Add(self._lbl_iso,      flag=wx.BOTTOM, border=4)
        sizer.Add(self._txt_iso,      flag=wx.EXPAND)
        panel.SetSizer(sizer)
        return panel

    # ---------- Panel Szyfranta ----------------------------------------
    def _build_panel_szyfrant(self) -> wx.Panel:
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        lbl_szyfr = wx.StaticText(panel, label=t("poliglota.lbl_szyfr"))
        etykiety = [w["etykieta"] for w in self._szyfry]
        self._combo_szyfr = wx.ComboBox(panel, choices=etykiety,
                                        style=wx.CB_READONLY,
                                        name=t("poliglota.combo_szyfr_name"))
        if etykiety:
            self._combo_szyfr.SetSelection(0)

        # Zakres SpinCtrl Cezara pochodzi z jego YAML-a (jeśli istnieje)
        cezar_cfg = core_poliglota.wariant_po_id(
            core_poliglota.TRYB_SZYFRANT, self._jezyk_aktywny, "cezar") or {}
        min_pr = int(cezar_cfg.get("min_przesuniecie", -35))
        max_pr = int(cezar_cfg.get("max_przesuniecie",  35))

        lbl_cezar = wx.StaticText(
            panel,
            label=t(
                "poliglota.lbl_cezar",
                min_przesuniecie=min_pr,
                max_przesuniecie=max_pr,
            ),
        )
        self._spin_cezara = wx.SpinCtrl(panel, min=min_pr, max=max_pr, initial=0,
                                        name=t("poliglota.spin_cezar_name"))

        sizer.Add(lbl_szyfr,          flag=wx.BOTTOM, border=4)
        sizer.Add(self._combo_szyfr,  flag=wx.EXPAND | wx.BOTTOM, border=8)
        sizer.Add(lbl_cezar,          flag=wx.BOTTOM, border=4)
        sizer.Add(self._spin_cezara,  flag=wx.EXPAND)
        panel.SetSizer(sizer)
        return panel

    # ==================================================================
    # PODPIĘCIE ZDARZEŃ
    # ==================================================================
    def _bind_events(self) -> None:
        self._btn_browse.Bind(wx.EVT_BUTTON, self._on_browse)
        self._btn_load.Bind(wx.EVT_BUTTON, self._on_load)
        self._btn_clear.Bind(wx.EVT_BUTTON, self._on_clear)
        self._btn_process.Bind(wx.EVT_BUTTON, self._on_process)
        self._txt_file.Bind(wx.EVT_TEXT_ENTER, self._on_load)
        self._txt_lang.Bind(wx.EVT_TEXT_ENTER, self._on_process)
        self._rb_ai.Bind(wx.EVT_RADIOBUTTON, self._on_mode_change)
        self._rb_rezyser.Bind(wx.EVT_RADIOBUTTON, self._on_mode_change)
        self._rb_szyfrant.Bind(wx.EVT_RADIOBUTTON, self._on_mode_change)
        self._combo_akcent.Bind(wx.EVT_COMBOBOX, self._on_akcent_change)

    # ==================================================================
    # OBSŁUGA PLIKU ŹRÓDŁOWEGO
    # ==================================================================
    def _on_browse(self, _event: wx.Event) -> None:
        with wx.FileDialog(
            self,
            message=t("poliglota.file_dlg_title"),
            wildcard=t("poliglota.file_dlg_wildcard"),
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        ) as dlg:
            if dlg.ShowModal() == wx.ID_OK:
                self._txt_file.SetValue(dlg.GetPath())
                self._txt_file.SetFocus()

    def _on_load(self, _event: wx.Event) -> None:
        if self._file_content:
            return

        file_name = self._txt_file.GetValue().strip()
        if not file_name:
            wx.MessageBox(t("poliglota.brak_pliku_tresc"),
                          t("common.brak_pliku_tytul"),
                          wx.OK | wx.ICON_WARNING, self)
            self._txt_file.SetFocus()
            return

        if not os.path.exists(file_name):
            wx.MessageBox(
                t("poliglota.plik_nie_istnieje_tresc", sciezka_pliku=file_name),
                t("common.plik_nie_istnieje_tytul"),
                wx.OK | wx.ICON_ERROR, self)
            self._txt_file.SetFocus()
            return

        try:
            _, ext = os.path.splitext(file_name)
            self._file_ext = ext.lower()
            if self._file_ext == ".docx":
                doc = docx.Document(file_name)
                self._file_content = "\n".join(p.text for p in doc.paragraphs)
            else:
                with open(file_name, "r", encoding="utf-8") as fh:
                    self._file_content = fh.read()
        except Exception as exc:
            wx.MessageBox(
                t("poliglota.blad_odczytu_tresc", tresc_bledu=str(exc)),
                t("common.blad_odczytu_tytul"),
                wx.OK | wx.ICON_ERROR, self)
            return

        self._oryginalna_nazwa  = os.path.splitext(os.path.basename(file_name))[0]
        self._plik_katalog      = os.path.dirname(os.path.abspath(file_name))
        self._sciezka_oryginalu = os.path.abspath(file_name)

        # 13.2: po wczytaniu pliku wykrywamy język treści (tylko jeśli ma
        # kompletny folder w ``dictionaries/``). Domyślny ``self._jezyk_aktywny``
        # jest zachowywany jako fallback.
        # 13.4 (A11Y): poprzednio przełączenie odbywało się cicho, przez co
        # NVDA nie zgłaszało zmiany etykiet w combo akcentów/szyfrów. Teraz
        # przed przełączeniem prosimy o jawną zgodę użytkownika — dialog
        # YES_NO jest sam w sobie powiadomieniem (czytnik ekranu odczyta
        # tytuł i treść, więc użytkownik wie, że etykiety zaraz się zmienią).
        # Cancel = zostaje aktywny język UI; ``_maybe_ostrzez_o_jezyku_zrodla``
        # i tak rzuci miękkie ostrzeżenie przy uruchomieniu trybu Reżysera.
        wykryty = core_poliglota.wykryj_jezyk_zrodlowy(
            self._file_content,
            fallback=self._jezyk_aktywny,
        )
        if wykryty != self._jezyk_aktywny:
            odp = wx.MessageBox(
                t(
                    "poliglota.zmiana_jezyka_pipeline_tresc",
                    jezyk_aktywny=core_poliglota.natywna_nazwa(self._jezyk_aktywny),
                    jezyk_wykryty=core_poliglota.natywna_nazwa(wykryty),
                ),
                t("poliglota.zmiana_jezyka_pipeline_tytul"),
                wx.YES_NO | wx.ICON_QUESTION, self,
            )
            if odp == wx.YES:
                self._jezyk_aktywny = wykryty
                self._odswiez_warianty()

        znaki = len(self._file_content)
        status_msg = t(
            "poliglota.plik_status_wczytany",
            nazwa_pliku=os.path.basename(file_name),
            liczba_znakow=znaki,
        )
        self._lbl_file_status.SetValue(status_msg)
        self._lbl_file_status.SetName(status_msg)
        self._lbl_file_status.SetForegroundColour(wx.Colour(0, 128, 0))

        self._txt_file.Disable()
        self._btn_browse.Disable()
        self._btn_load.Disable()
        self._btn_clear.Enable()

        wx.MessageBox(
            t(
                "poliglota.plik_wczytany_tresc",
                nazwa_pliku=os.path.basename(file_name),
                liczba_znakow=znaki,
            ),
            t("poliglota.plik_wczytany_tytul"),
            wx.OK | wx.ICON_INFORMATION, self)

    def _on_clear(self, _event: wx.Event) -> None:
        self._file_content      = ""
        self._file_ext          = ""
        self._oryginalna_nazwa  = "nieznany"
        self._plik_katalog      = "."
        self._sciezka_oryginalu = None

        self._txt_file.Enable();  self._txt_file.SetValue("")
        self._btn_browse.Enable()
        self._btn_load.Enable()
        self._btn_clear.Disable()

        clear_msg = t("poliglota.plik_status_wyczyszczono")
        self._lbl_file_status.SetValue(clear_msg)
        self._lbl_file_status.SetName(clear_msg)
        self._lbl_file_status.SetForegroundColour(self.GetForegroundColour())

        self._txt_result.SetValue("")
        self._gauge.SetValue(0);        self._gauge.Hide()
        self._lbl_progress.SetValue(""); self._lbl_progress.Hide()
        self.Layout()

    # ==================================================================
    # ZMIANA TRYBU PRACY
    # ==================================================================
    def _on_mode_change(self, _event: wx.Event) -> None:
        self._refresh_mode_ui()

    def _refresh_mode_ui(self) -> None:
        ai_mode   = self._api_dostepne and self._rb_ai.GetValue()
        rez_mode  = self._rb_rezyser.GetValue()
        szyf_mode = self._rb_szyfrant.GetValue()
        self._pnl_ai.Show(ai_mode)
        self._pnl_rezyser.Show(rez_mode)
        self._pnl_szyfrant.Show(szyf_mode)
        self.Layout()

    def _on_akcent_change(self, _event: wx.Event) -> None:
        """Pokaż pole „Kod ISO" tylko dla wariantu Naprawiacz Tagów."""
        cfg = self._aktualny_wariant_akcentu()
        pokaz_iso = bool(cfg and cfg.get("kategoria") == "naprawiacz")
        self._lbl_iso.Show(pokaz_iso)
        self._txt_iso.Show(pokaz_iso)
        self._pnl_rezyser.Layout()
        self.Layout()

    # ------------------------------------------------------------------
    # 13.2: przeładowanie list wariantów po zmianie języka aktywnego
    # ------------------------------------------------------------------
    def _odswiez_warianty(self) -> None:
        """Wczytuje akcenty/szyfry dla ``self._jezyk_aktywny`` i odświeża GUI.

        Twardy filtr: nie ma fallbacku do innego języka — gdy folder reguł
        nie istnieje, ComboBox jest pusty i wyłączony, a tooltip informuje
        użytkownika, że dla danego języka nie ma jeszcze reguł.
        """
        self._akcenty = core_poliglota.lista_wariantow(
            core_poliglota.TRYB_REZYSER, self._jezyk_aktywny)
        self._szyfry = core_poliglota.lista_wariantow(
            core_poliglota.TRYB_SZYFRANT, self._jezyk_aktywny)

        # ── Akcenty ─────────────────────────────────────────────────────
        etykiety_akcentow = [w["etykieta"] for w in self._akcenty]
        self._combo_akcent.Set(etykiety_akcentow)
        if etykiety_akcentow:
            self._combo_akcent.SetSelection(0)
            self._combo_akcent.Enable()
            self._combo_akcent.SetToolTip(t("poliglota.combo_akcent_tooltip"))
        else:
            self._combo_akcent.Disable()
            self._combo_akcent.SetToolTip(
                t("poliglota.brak_akcentow_dla_jezyka", jezyk=self._jezyk_aktywny)
            )

        # ── Szyfry ──────────────────────────────────────────────────────
        etykiety_szyfrow = [w["etykieta"] for w in self._szyfry]
        self._combo_szyfr.Set(etykiety_szyfrow)
        if etykiety_szyfrow:
            self._combo_szyfr.SetSelection(0)
            self._combo_szyfr.Enable()
        else:
            self._combo_szyfr.Disable()
            self._combo_szyfr.SetToolTip(
                t("poliglota.brak_szyfrow_dla_jezyka", jezyk=self._jezyk_aktywny)
            )

    def _aktualny_wariant_akcentu(self) -> dict | None:
        etykieta = self._combo_akcent.GetStringSelection()
        return core_poliglota.wariant_po_etykiecie(
            core_poliglota.TRYB_REZYSER, self._jezyk_aktywny, etykieta)

    def _aktualny_wariant_szyfru(self) -> dict | None:
        etykieta = self._combo_szyfr.GetStringSelection()
        return core_poliglota.wariant_po_etykiecie(
            core_poliglota.TRYB_SZYFRANT, self._jezyk_aktywny, etykieta)

    # ==================================================================
    # URUCHOMIENIE PRZETWARZANIA
    # ==================================================================
    def _on_process(self, _event: wx.Event) -> None:
        # --- walidacja ogólna ---
        if not self._file_content:
            wx.MessageBox(t("poliglota.brak_pliku_pamieci_tresc"),
                          t("poliglota.brak_pliku_pamieci_tytul"),
                          wx.OK | wx.ICON_WARNING, self)
            return

        if self._worker_thread and self._worker_thread.is_alive():
            wx.MessageBox(t("poliglota.zajety_tresc"),
                          t("poliglota.zajety_tytul"),
                          wx.OK | wx.ICON_INFORMATION, self)
            return

        # --- dispatcher trybu ---
        if self._api_dostepne and self._rb_ai.GetValue():
            target_lang = self._txt_lang.GetValue().strip()
            if not target_lang:
                wx.MessageBox(t("poliglota.brak_jezyka_tresc"),
                              t("poliglota.brak_jezyka_tytul"),
                              wx.OK | wx.ICON_WARNING, self)
                self._txt_lang.SetFocus()
                return
            self._start_ai_translation(target_lang)
            return

        if self._rb_rezyser.GetValue():
            self._run_rezyser_mode()
            return

        if self._rb_szyfrant.GetValue():
            self._run_szyfrant_mode()
            return

    # ------------------------------------------------------------------
    # TRYB REŻYSERA
    # ------------------------------------------------------------------
    def _run_rezyser_mode(self) -> None:
        cfg = self._aktualny_wariant_akcentu()
        if cfg is None:
            wx.MessageBox(t("poliglota.nie_wybrano_akcentu"),
                          t("poliglota.blad_wyniku_tytul"),
                          wx.OK | wx.ICON_ERROR, self)
            return

        opcje: dict = {}
        if cfg.get("kategoria") == "naprawiacz":
            kod_iso = self._txt_iso.GetValue().strip().lower()
            if not kod_iso or len(kod_iso) > 2:
                wx.MessageBox(t("poliglota.brak_iso_tresc"),
                              t("poliglota.brak_iso_tytul"),
                              wx.OK | wx.ICON_WARNING, self)
                self._txt_iso.SetFocus()
                return
            opcje["iso_reczne"] = kod_iso

        # Ostrzeżenie o języku źródłowym (tylko dla akcentów)
        if cfg.get("kategoria") == "akcent":
            self._maybe_ostrzez_o_jezyku_zrodla()

        # >>>> GŁÓWNE WYWOŁANIE SILNIKA <<<<
        try:
            wynik = core_poliglota.przetworz(
                self._file_content,
                tryb=core_poliglota.TRYB_REZYSER,
                jezyk=self._jezyk_aktywny,
                wariant=cfg["id"],
                **opcje,
            )
        except core_poliglota.BrakRegulyDlaJezykaError as exc:
            # 13.5: długi techniczny komunikat → wx.Dialog z TextCtrl TE_READONLY
            # (zgodnie z konwencją A11y: NVDA ma spokojnie odczytać i pozwolić
            # użytkownikowi skopiować ścieżkę brakującej reguły).
            self._wyswietl_blad_ai(
                str(exc),
                custom_msg=t("poliglota.brak_reguly_naglowek"),
            )
            return
        except Exception as exc:
            wx.MessageBox(
                t("poliglota.blad_przetwarzania", tresc_bledu=str(exc)),
                t("poliglota.blad_wyniku_tytul"),
                wx.OK | wx.ICON_ERROR, self)
            return

        self._zakoncz_zapisem(wynik, cfg, opcje, tryb=core_poliglota.TRYB_REZYSER)

    # ------------------------------------------------------------------
    # TRYB SZYFRANTA
    # ------------------------------------------------------------------
    def _run_szyfrant_mode(self) -> None:
        cfg = self._aktualny_wariant_szyfru()
        if cfg is None:
            wx.MessageBox(t("poliglota.nie_wybrano_szyfru"),
                          t("poliglota.blad_wyniku_tytul"),
                          wx.OK | wx.ICON_ERROR, self)
            return

        opcje: dict = {}
        if cfg.get("algorytm") == "cezar":
            opcje["przesuniecie"] = int(self._spin_cezara.GetValue())

        # >>>> GŁÓWNE WYWOŁANIE SILNIKA <<<<
        try:
            wynik = core_poliglota.przetworz(
                self._file_content,
                tryb=core_poliglota.TRYB_SZYFRANT,
                jezyk=self._jezyk_aktywny,
                wariant=cfg["id"],
                **opcje,
            )
        except core_poliglota.BrakRegulyDlaJezykaError as exc:
            self._wyswietl_blad_ai(
                str(exc),
                custom_msg=t("poliglota.brak_reguly_naglowek"),
            )
            return
        except Exception as exc:
            wx.MessageBox(
                t("poliglota.blad_przetwarzania", tresc_bledu=str(exc)),
                t("poliglota.blad_wyniku_tytul"),
                wx.OK | wx.ICON_ERROR, self)
            return

        # Cezar z zerem = wylosowane przesunięcie → poinformuj użytkownika
        if cfg.get("algorytm") == "cezar" and opcje.get("przesuniecie", 0) == 0:
            wylosowane = opcje.get("przesuniecie_faktyczne")
            if wylosowane:
                wx.MessageBox(
                    t(
                        "poliglota.cezar_losowe_tresc",
                        wylosowane_przesuniecie=wylosowane,
                    ),
                    t("poliglota.cezar_losowe_tytul"),
                    wx.OK | wx.ICON_INFORMATION, self)

        self._zakoncz_zapisem(wynik, cfg, opcje, tryb=core_poliglota.TRYB_SZYFRANT)

    # ------------------------------------------------------------------
    # Zapis rezultatu (Rezyser / Szyfrant – wspólne)
    # ------------------------------------------------------------------
    def _zakoncz_zapisem(self, wynik: str, cfg: dict,
                         opcje: dict, tryb: str) -> None:
        if not wynik and cfg.get("kategoria") != "naprawiacz":
            wx.MessageBox(t("poliglota.blad_wyniku_tresc"),
                          t("poliglota.blad_wyniku_tytul"),
                          wx.OK | wx.ICON_ERROR, self)
            return

        wariant_id = cfg["id"]
        iso  = core_poliglota.kod_iso(tryb, self._jezyk_aktywny, wariant_id, opcje)
        base = core_poliglota.sufiks_nazwy_pliku(
            tryb, self._jezyk_aktywny, wariant_id, self._oryginalna_nazwa, opcje)

        # 13.5: side-channel z core_poliglota._przetworz_* — mapa
        # (iso, fragment, czy_tekst) per akapit. Pozwala zapisz_wynik
        # wstrzyknąć tag lang per paragraf bez ponownej detekcji.
        segmenty_wynikowe = opcje.get("_segmenty_wynikowe")

        try:
            out_path = core_poliglota.zapisz_wynik(
                tresc_wynikowa=wynik,
                katalog_wyjscia=self._plik_katalog,
                base_name=base,
                ext=self._file_ext,
                iso_code=iso,
                tryb=tryb,
                wariant_cfg=cfg,
                oryginalny_content=self._file_content,
                sciezka_oryginalu=self._sciezka_oryginalu,
                segmenty_wynikowe=segmenty_wynikowe,
            )
        except Exception as exc:
            wx.MessageBox(
                t("poliglota.blad_zapisu_wyjscia", tresc_bledu=str(exc)),
                t("common.blad_zapisu_tytul"),
                wx.OK | wx.ICON_ERROR, self)
            return

        self._txt_result.SetValue(wynik)
        self._txt_result.SetFocus()
        wx.MessageBox(
            t("poliglota.sukces_zapis", sciezka_pliku=out_path),
            t("common.sukces_tytul"),
            wx.OK | wx.ICON_INFORMATION, self)

    # ------------------------------------------------------------------
    # Miękkie ostrzeżenie o języku źródłowym
    # ------------------------------------------------------------------
    def _maybe_ostrzez_o_jezyku_zrodla(self) -> None:
        # 13.2: detekcja przez core_poliglota.wykryj_jezyk_zrodlowy(), które
        # waliduje wynik wobec folderów w ``dictionaries/`` i zwraca tylko
        # kompletne języki bazowe. Porównujemy z aktywnym językiem pipeline'u
        # (przełączanym w _odswiez_warianty po wczytaniu pliku) — ostrzeżenie
        # jest miękkie i pojawia się tylko, gdy detekcja widzi inny kompletny
        # język niż aktualnie wybrany w GUI.
        wykryty = core_poliglota.wykryj_jezyk_zrodlowy(
            self._file_content,
            fallback=self._jezyk_aktywny,
        )
        if wykryty != self._jezyk_aktywny:
            ostrzezenie = t(
                "poliglota.ostrzezenie_jezyk",
                wspierane_jezyki=core_poliglota.lista_wspieranych_jezykow_natywnie(
                    jezyk_pierwszy=i18n.aktualny_jezyk(),
                ),
            )
            self._lbl_progress.SetValue(ostrzezenie)
            self._lbl_progress.SetName(ostrzezenie)
            self._lbl_progress.Show()
            self.Layout()
            wx.LogMessage(ostrzezenie)

    # ==================================================================
    # TRYB TŁUMACZA AI (w wątku tła)
    # ==================================================================
    def _start_ai_translation(self, target_lang: str) -> None:
        self._btn_process.Disable()
        self._gauge.SetValue(0);   self._gauge.Show()
        self._lbl_progress.Show()
        self._lbl_progress.SetValue(t("poliglota.ai_init"))
        self._txt_result.SetValue("")
        self.Layout()

        app_dir = os.path.dirname(os.path.abspath(__file__))
        runtime_dir = os.path.join(app_dir, "runtime")

        self._worker_thread = threading.Thread(
            target=self._ai_worker,
            args=(self._file_content, self._file_ext, target_lang, runtime_dir),
            daemon=True,
        )
        self._worker_thread.start()

    def _ai_worker(self, content: str, ext: str,
                   target_lang: str, runtime_dir: str) -> None:
        """Wątek tła – żaden bezpośredni wx.* (tylko przez wx.CallAfter!)."""

        def _cb_postep(msg: str, pct: int) -> None:
            wx.CallAfter(self._update_progress_label, msg, pct)

        def _cb_blad_kryt(msg: str, partial: str) -> None:
            wx.CallAfter(self._on_ai_error, msg, partial)

        def _cb_blad_miekki(msg: str, tytul: str) -> None:
            wx.CallAfter(self._wyswietl_blad_ai, msg, tytul)

        wynik = tlumacz_ai.tlumacz_dlugi_tekst(
            tresc=content,
            jezyk_docelowy=target_lang,
            klient=self._client,
            runtime_dir=runtime_dir,
            oryginalna_nazwa=self._oryginalna_nazwa,
            on_postep=_cb_postep,
            on_blad_krytyczny=_cb_blad_kryt,
            on_blad_miekki=_cb_blad_miekki,
        )

        if wynik is None:
            return   # _cb_blad_kryt już zajął się GUI
        wx.CallAfter(self._on_ai_done, wynik, ext)

    # ------------------------------------------------------------------
    # Callbacki wątku AI (wołane w wątku GUI przez wx.CallAfter)
    # ------------------------------------------------------------------
    def _update_progress_label(self, msg: str, percent: int) -> None:
        self._lbl_progress.SetValue(msg)
        self._lbl_progress.SetName(msg)
        self._gauge.SetValue(max(0, min(100, percent)))

    def _on_ai_error(self, msg: str, partial_text: str = "") -> None:
        self._btn_process.Enable()
        self._gauge.Hide();        self._lbl_progress.Hide()
        self.Layout()

        if partial_text:
            self._txt_result.SetValue(partial_text)
            self._txt_result.SetFocus()

        self._wyswietl_blad_ai(msg)

    def _on_ai_done(self, wynik: tlumacz_ai.WynikTlumaczenia, ext: str) -> None:
        self._txt_result.SetValue(wynik.tekst)
        self._txt_result.SetFocus()

        # Tłumacz AI nie używa core_poliglota.wariant_cfg – to tryb specjalny.
        # Przekazujemy wariant_cfg=None (→ nie jest naprawiaczem, więc
        # zapisz_wynik potraktuje wynik jak nowy dokument z tagiem lang).
        try:
            out_path = core_poliglota.zapisz_wynik(
                tresc_wynikowa=wynik.tekst,
                katalog_wyjscia=self._plik_katalog,
                base_name=wynik.base_name,
                ext=ext,
                iso_code=wynik.iso,
                tryb="Tlumacz",
                wariant_cfg=None,
                oryginalny_content=self._file_content,
                sciezka_oryginalu=self._sciezka_oryginalu,
            )
        except Exception as exc:
            self._on_ai_error(
                t("poliglota.ai_blad_zapisu", tresc_bledu=str(exc)),
                wynik.tekst,
            )
            return

        self._gauge.SetValue(100)
        self._btn_process.Enable()

        wx.MessageBox(
            t("poliglota.ai_zakonczone_tresc", sciezka_pliku=out_path),
            t("poliglota.ai_zakonczone_tytul"),
            wx.OK | wx.ICON_INFORMATION, self)

        self._gauge.Hide()
        self._lbl_progress.SetValue(""); self._lbl_progress.Hide()
        self.Layout()

    # ------------------------------------------------------------------
    # Wyświetlanie błędów AI
    # ------------------------------------------------------------------
    def _wyswietl_blad_ai(self, tresc_bledu: str,
                          custom_msg: str | None = None) -> None:
        """Krótki błąd → MessageBox; długi → Dialog z polem do skopiowania."""
        msg_header  = custom_msg or t("poliglota.blad_ai_naglowek")
        jest_krotki = len(tresc_bledu) <= 200 and "\n" not in tresc_bledu

        if jest_krotki:
            pelna = f"{msg_header}\n\n{tresc_bledu}" if custom_msg else tresc_bledu
            wx.MessageBox(pelna, t("poliglota.blad_ai_tytul"),
                          wx.OK | wx.ICON_ERROR, self)
            return

        dlg = wx.Dialog(self, title=t("poliglota.blad_ai_szczegoly_tytul"), size=(640, 400))
        sizer = wx.BoxSizer(wx.VERTICAL)
        lbl_head = wx.StaticText(dlg, label=msg_header)
        lbl_copy = wx.StaticText(dlg, label=t("poliglota.blad_ai_lbl_tresc"))
        txt = wx.TextCtrl(dlg, value=tresc_bledu,
                          style=wx.TE_MULTILINE | wx.TE_READONLY,
                          name=t("poliglota.blad_ai_tresc_name"))
        btn_ok = wx.Button(dlg, wx.ID_OK, label=t("common.btn_zamknij"))

        sizer.Add(lbl_head, flag=wx.ALL,                                       border=8)
        sizer.Add(lbl_copy, flag=wx.LEFT | wx.RIGHT | wx.BOTTOM,               border=8)
        sizer.Add(txt,      proportion=1, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=8)
        sizer.Add(btn_ok,   flag=wx.ALL | wx.ALIGN_RIGHT,                      border=8)
        dlg.SetSizer(sizer)
        txt.SetFocus()
        dlg.ShowModal()
        dlg.Destroy()
