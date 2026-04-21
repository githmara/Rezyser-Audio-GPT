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
"""

from __future__ import annotations

import os
import threading

import docx
from dotenv import load_dotenv
from langdetect import LangDetectException, detect

import wx

import core_poliglota
import tlumacz_ai


JEZYK_BAZOWY = "pl"   # docelowo konfigurowalne w menu Ustawienia


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

    TOOL_DESCRIPTION = (
        "Moduł Poliglota służy do nakładania twardych akcentów fonetycznych "
        "pod lokalne syntezatory mowy (NVDA/Vocalizer/eSpeak), do zabaw "
        "tekstowych w Trybie Szyfranta oraz do tłumaczenia tekstów za pomocą "
        "AI (OpenAI gpt-4o).\n\n"
        "Obsługuje pliki: .txt, .html, .htm, .docx.\n"
        "Wynik zapisywany jest w tym samym katalogu co plik źródłowy."
    )

    ENV_FILENAME = "golden_key.env"

    # ------------------------------------------------------------------
    # Konstruktor
    # ------------------------------------------------------------------
    def __init__(self, parent: wx.Window) -> None:
        super().__init__(parent, style=wx.TAB_TRAVERSAL)
        self.SetName("Panel Poligloty AI")

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

        # Konfiguracje wariantów (z YAML) – pobierane raz przy starcie panelu
        self._akcenty = core_poliglota.lista_wariantow(
            core_poliglota.TRYB_REZYSER, JEZYK_BAZOWY)
        self._szyfry  = core_poliglota.lista_wariantow(
            core_poliglota.TRYB_SZYFRANT, JEZYK_BAZOWY)

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
        heading = wx.StaticText(self, label="🌍  Poliglota AI – Hybrydowe Studio Tłumaczeń")
        font = heading.GetFont()
        font.SetPointSize(16); font.MakeBold()
        heading.SetFont(font)

        # ── Opis narzędzia (czytany przez NVDA) ──────────────────────────
        self._description = wx.TextCtrl(
            self,
            value=self.TOOL_DESCRIPTION,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.NO_BORDER,
            name="Opis modułu Poliglota",
        )
        self._description.SetBackgroundColour(self.GetBackgroundColour())

        # ── Sekcja 1: Wczytywanie pliku ──────────────────────────────────
        lbl_section1 = self._naglowek("1. Wczytywanie pliku źródłowego")
        lbl_file = wx.StaticText(
            self, label="Nazwa lub pełna ścieżka pliku (.txt, .html, .htm, .docx):")

        self._txt_file = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER,
                                     name="Pole ścieżki pliku źródłowego")
        self._txt_file.SetHint("Wpisz ścieżkę do pliku lub wybierz przyciskiem Przeglądaj…")

        self._btn_browse = wx.Button(self, label="Przeglądaj…")
        self._btn_browse.SetToolTip("Otwiera systemowe okno wyboru pliku")

        file_row = wx.BoxSizer(wx.HORIZONTAL)
        file_row.Add(self._txt_file,   proportion=1,
                     flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=6)
        file_row.Add(self._btn_browse, flag=wx.ALIGN_CENTER_VERTICAL)

        self._btn_load = wx.Button(self, label="Wczytaj plik do pamięci")
        self._btn_load.SetToolTip("Wczytuje zawartość wskazanego pliku do pamięci roboczej")

        self._btn_clear = wx.Button(self, label="Wyczyść pamięć")
        self._btn_clear.SetToolTip("Usuwa wczytaną treść, pozwala wybrać inny plik")
        self._btn_clear.Disable()

        load_row = wx.BoxSizer(wx.HORIZONTAL)
        load_row.Add(self._btn_load,  flag=wx.RIGHT, border=8)
        load_row.Add(self._btn_clear)

        self._lbl_file_status = wx.TextCtrl(
            self, value="Brak wczytanego pliku.",
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.NO_BORDER)
        self._lbl_file_status.SetBackgroundColour(self.GetBackgroundColour())
        self._lbl_file_status.SetName("Status wczytanego pliku")

        # ── Sekcja 2: Konfiguracja trybu pracy ──────────────────────────
        lbl_section2 = self._naglowek("2. Konfiguracja Pracy")

        self._rb_ai = wx.RadioButton(
            self, label="Tłumacz AI (OpenAI gpt-4o – wymaga klucza API, kosztuje kredyty)",
            style=wx.RB_GROUP, name="Tryb Tłumacza AI")
        self._rb_rezyser = wx.RadioButton(
            self, label="Tryb Reżysera (darmowe reguły fonetyczne z YAML)",
            name="Tryb Reżysera darmowy")
        self._rb_szyfrant = wx.RadioButton(
            self, label="Tryb Szyfranta (zabawy tekstem, losowe zacinanie)",
            name="Tryb Szyfranta i zabaw tekstowych")

        if not self._api_dostepne:
            self._rb_ai.Disable()
            self._rb_ai.SetLabel(
                "Tłumacz AI (wyłączony – brak poprawnego pliku golden_key.env)")
            self._rb_rezyser.SetValue(True)
        else:
            self._rb_ai.SetValue(True)

        self._pnl_ai       = self._build_panel_ai()
        self._pnl_rezyser  = self._build_panel_rezyser()
        self._pnl_szyfrant = self._build_panel_szyfrant()
        self._pnl_szyfrant.Hide()

        # ── Sekcja 3: Przetwarzanie ──────────────────────────────────────
        lbl_section3 = self._naglowek("3. Przetwarzanie")

        self._btn_process = wx.Button(self, label="Uruchom Przetwarzanie")
        self._btn_process.SetToolTip(
            "Uruchamia wybrane przetwarzanie i zapisuje wynik obok pliku źródłowego")

        self._gauge = wx.Gauge(self, range=100,
                               style=wx.GA_HORIZONTAL | wx.GA_SMOOTH)
        self._gauge.SetValue(0); self._gauge.Hide()

        self._lbl_progress = wx.TextCtrl(
            self, value="",
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.NO_BORDER)
        self._lbl_progress.SetBackgroundColour(self.GetBackgroundColour())
        self._lbl_progress.SetName("Status postępu przetwarzania")
        self._lbl_progress.Hide()

        # ── Sekcja 4: Wynik ──────────────────────────────────────────────
        lbl_section4 = self._naglowek(
            "4. Wynik (tylko do odczytu – nawiguj strzałkami)")

        self._txt_result = wx.TextCtrl(
            self, value="",
            style=wx.TE_MULTILINE | wx.TE_READONLY,
            name="Pole wynikowe – gotowy tekst")
        self._txt_result.SetMinSize((-1, 200))
        self._txt_result.SetHint("Tutaj pojawi się przetworzona treść…")

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

        lbl = wx.StaticText(
            panel,
            label="Język docelowy tłumaczenia (np. Fiński, Islandzki, Angielski, Arabski):")
        self._txt_lang = wx.TextCtrl(panel, style=wx.TE_PROCESS_ENTER,
                                     name="Pole języka docelowego")
        self._txt_lang.SetHint("Wpisz nazwę języka docelowego…")

        sizer.Add(lbl,           flag=wx.BOTTOM, border=4)
        sizer.Add(self._txt_lang, flag=wx.EXPAND)
        panel.SetSizer(sizer)
        return panel

    # ---------- Panel Reżysera -----------------------------------------
    def _build_panel_rezyser(self) -> wx.Panel:
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        lbl = wx.StaticText(panel, label="Wybierz akcent lub tryb czyszczenia:")
        etykiety = [w["etykieta"] for w in self._akcenty]
        self._combo_akcent = wx.ComboBox(panel, choices=etykiety,
                                         style=wx.CB_READONLY,
                                         name="Lista akcentów i trybów czyszczenia")
        if etykiety:
            self._combo_akcent.SetSelection(0)
        self._combo_akcent.SetToolTip(
            "Wybierz akcent fonetyczny lub tryb czyszczenia tekstu pod czytniki ekranu")

        self._lbl_iso = wx.StaticText(
            panel, label="Kod ISO języka (2 litery, np. en, fr, de):")
        self._txt_iso = wx.TextCtrl(panel, name="Pole kodu ISO języka")
        self._txt_iso.SetMaxLength(2)
        self._txt_iso.SetHint("np. en")
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

        lbl_szyfr = wx.StaticText(panel, label="Wybierz algorytm zniekształcający:")
        etykiety = [w["etykieta"] for w in self._szyfry]
        self._combo_szyfr = wx.ComboBox(panel, choices=etykiety,
                                        style=wx.CB_READONLY,
                                        name="Lista algorytmów szyfrujących")
        if etykiety:
            self._combo_szyfr.SetSelection(0)

        # Zakres SpinCtrl Cezara pochodzi z jego YAML-a (jeśli istnieje)
        cezar_cfg = core_poliglota.wariant_po_id(
            core_poliglota.TRYB_SZYFRANT, JEZYK_BAZOWY, "cezar") or {}
        min_pr = int(cezar_cfg.get("min_przesuniecie", -35))
        max_pr = int(cezar_cfg.get("max_przesuniecie",  35))

        lbl_cezar = wx.StaticText(
            panel,
            label=f"Przesunięcie szyfru Cezara (0 = losowe, zakres {min_pr}…{max_pr}):")
        self._spin_cezara = wx.SpinCtrl(panel, min=min_pr, max=max_pr, initial=0,
                                        name="Przesunięcie szyfru Cezara")

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
            message="Wybierz plik źródłowy",
            wildcard=(
                "Obsługiwane pliki (*.txt;*.html;*.htm;*.docx)"
                "|*.txt;*.html;*.htm;*.docx"
                "|Pliki tekstowe (*.txt)|*.txt"
                "|Pliki HTML (*.html;*.htm)|*.html;*.htm"
                "|Dokumenty Word (*.docx)|*.docx"
                "|Wszystkie pliki (*.*)|*.*"
            ),
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
            wx.MessageBox("Podaj nazwę lub ścieżkę pliku przed wczytaniem.",
                          "Brak pliku", wx.OK | wx.ICON_WARNING, self)
            self._txt_file.SetFocus()
            return

        if not os.path.exists(file_name):
            wx.MessageBox(f"Nie znaleziono pliku:\n{file_name}",
                          "Plik nie istnieje", wx.OK | wx.ICON_ERROR, self)
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
            wx.MessageBox(f"Błąd podczas odczytu pliku:\n{exc}",
                          "Błąd odczytu", wx.OK | wx.ICON_ERROR, self)
            return

        self._oryginalna_nazwa  = os.path.splitext(os.path.basename(file_name))[0]
        self._plik_katalog      = os.path.dirname(os.path.abspath(file_name))
        self._sciezka_oryginalu = os.path.abspath(file_name)

        znaki = len(self._file_content)
        status_msg = (
            f"Plik wczytany: {os.path.basename(file_name)}  ({znaki} znaków).\n"
            "Możesz teraz uruchomić przetwarzanie.")
        self._lbl_file_status.SetValue(status_msg)
        self._lbl_file_status.SetName(status_msg)
        self._lbl_file_status.SetForegroundColour(wx.Colour(0, 128, 0))

        self._txt_file.Disable()
        self._btn_browse.Disable()
        self._btn_load.Disable()
        self._btn_clear.Enable()

        wx.MessageBox(
            f"Wczytano plik: {os.path.basename(file_name)}\n({znaki} znaków).\n\n"
            "Możesz teraz skonfigurować tryb pracy i uruchomić przetwarzanie.",
            "Plik wczytany", wx.OK | wx.ICON_INFORMATION, self)

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

        clear_msg = "Pamięć wyczyszczona. Możesz wczytać nowy plik."
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

    def _aktualny_wariant_akcentu(self) -> dict | None:
        etykieta = self._combo_akcent.GetStringSelection()
        return core_poliglota.wariant_po_etykiecie(
            core_poliglota.TRYB_REZYSER, JEZYK_BAZOWY, etykieta)

    def _aktualny_wariant_szyfru(self) -> dict | None:
        etykieta = self._combo_szyfr.GetStringSelection()
        return core_poliglota.wariant_po_etykiecie(
            core_poliglota.TRYB_SZYFRANT, JEZYK_BAZOWY, etykieta)

    # ==================================================================
    # URUCHOMIENIE PRZETWARZANIA
    # ==================================================================
    def _on_process(self, _event: wx.Event) -> None:
        # --- walidacja ogólna ---
        if not self._file_content:
            wx.MessageBox("Najpierw wczytaj plik źródłowy (sekcja 1).",
                          "Brak pliku w pamięci", wx.OK | wx.ICON_WARNING, self)
            return

        if self._worker_thread and self._worker_thread.is_alive():
            wx.MessageBox("Przetwarzanie jest już w toku. Poczekaj na zakończenie.",
                          "Zajęty", wx.OK | wx.ICON_INFORMATION, self)
            return

        # --- dispatcher trybu ---
        if self._api_dostepne and self._rb_ai.GetValue():
            target_lang = self._txt_lang.GetValue().strip()
            if not target_lang:
                wx.MessageBox("Wpisz język docelowy tłumaczenia przed uruchomieniem.",
                              "Brak języka", wx.OK | wx.ICON_WARNING, self)
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
            wx.MessageBox("Nie wybrano żadnego akcentu.", "Błąd",
                          wx.OK | wx.ICON_ERROR, self)
            return

        opcje: dict = {}
        if cfg.get("kategoria") == "naprawiacz":
            kod_iso = self._txt_iso.GetValue().strip().lower()
            if not kod_iso or len(kod_iso) > 2:
                wx.MessageBox(
                    "Podaj poprawny dwuliterowy kod ISO języka (np. en, fr, de).",
                    "Brak kodu ISO", wx.OK | wx.ICON_WARNING, self)
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
                jezyk=JEZYK_BAZOWY,
                wariant=cfg["id"],
                **opcje,
            )
        except Exception as exc:
            wx.MessageBox(f"Błąd przetwarzania:\n{exc}", "Błąd",
                          wx.OK | wx.ICON_ERROR, self)
            return

        self._zakoncz_zapisem(wynik, cfg, opcje, tryb=core_poliglota.TRYB_REZYSER)

    # ------------------------------------------------------------------
    # TRYB SZYFRANTA
    # ------------------------------------------------------------------
    def _run_szyfrant_mode(self) -> None:
        cfg = self._aktualny_wariant_szyfru()
        if cfg is None:
            wx.MessageBox("Nie wybrano żadnego szyfru.", "Błąd",
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
                jezyk=JEZYK_BAZOWY,
                wariant=cfg["id"],
                **opcje,
            )
        except Exception as exc:
            wx.MessageBox(f"Błąd przetwarzania:\n{exc}", "Błąd",
                          wx.OK | wx.ICON_ERROR, self)
            return

        # Cezar z zerem = wylosowane przesunięcie → poinformuj użytkownika
        if cfg.get("algorytm") == "cezar" and opcje.get("przesuniecie", 0) == 0:
            wylosowane = opcje.get("przesuniecie_faktyczne")
            if wylosowane:
                wx.MessageBox(
                    f"Wartość przesunięcia wynosiła 0 – wylosowano: {wylosowane}.",
                    "Szyfr Cezara – losowe przesunięcie",
                    wx.OK | wx.ICON_INFORMATION, self)

        self._zakoncz_zapisem(wynik, cfg, opcje, tryb=core_poliglota.TRYB_SZYFRANT)

    # ------------------------------------------------------------------
    # Zapis rezultatu (Rezyser / Szyfrant – wspólne)
    # ------------------------------------------------------------------
    def _zakoncz_zapisem(self, wynik: str, cfg: dict,
                         opcje: dict, tryb: str) -> None:
        if not wynik and cfg.get("kategoria") != "naprawiacz":
            wx.MessageBox("Nie udało się wygenerować wynikowego tekstu.",
                          "Błąd", wx.OK | wx.ICON_ERROR, self)
            return

        wariant_id = cfg["id"]
        iso  = core_poliglota.kod_iso(tryb, JEZYK_BAZOWY, wariant_id, opcje)
        base = core_poliglota.sufiks_nazwy_pliku(
            tryb, JEZYK_BAZOWY, wariant_id, self._oryginalna_nazwa, opcje)

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
            )
        except Exception as exc:
            wx.MessageBox(f"Błąd podczas zapisu pliku wynikowego:\n{exc}",
                          "Błąd zapisu", wx.OK | wx.ICON_ERROR, self)
            return

        self._txt_result.SetValue(wynik)
        self._txt_result.SetFocus()
        wx.MessageBox(f"Plik zapisany jako:\n{out_path}", "Sukces",
                      wx.OK | wx.ICON_INFORMATION, self)

    # ------------------------------------------------------------------
    # Miękkie ostrzeżenie o języku źródłowym
    # ------------------------------------------------------------------
    def _maybe_ostrzez_o_jezyku_zrodla(self) -> None:
        try:
            if detect(self._file_content) != JEZYK_BAZOWY:
                ostrzezenie = (
                    "Uwaga: Wykryto język główny inny niż polski. "
                    "Reguły fonetyczne są przystosowane do polszczyzny – "
                    "efekt może być nieprzewidywalny.")
                self._lbl_progress.SetValue(ostrzezenie)
                self._lbl_progress.SetName(ostrzezenie)
                self._lbl_progress.Show()
                self.Layout()
                wx.LogMessage(ostrzezenie)
        except LangDetectException:
            pass

    # ==================================================================
    # TRYB TŁUMACZA AI (w wątku tła)
    # ==================================================================
    def _start_ai_translation(self, target_lang: str) -> None:
        self._btn_process.Disable()
        self._gauge.SetValue(0);   self._gauge.Show()
        self._lbl_progress.Show()
        self._lbl_progress.SetValue("Inicjowanie tłumaczenia…")
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
            self._on_ai_error(f"Błąd zapisu pliku wynikowego:\n{exc}", wynik.tekst)
            return

        self._gauge.SetValue(100)
        self._btn_process.Enable()

        wx.MessageBox(f"Tłumaczenie ukończone!\n\nPlik zapisany jako:\n{out_path}",
                      "Sukces", wx.OK | wx.ICON_INFORMATION, self)

        self._gauge.Hide()
        self._lbl_progress.SetValue(""); self._lbl_progress.Hide()
        self.Layout()

    # ------------------------------------------------------------------
    # Wyświetlanie błędów AI
    # ------------------------------------------------------------------
    def _wyswietl_blad_ai(self, tresc_bledu: str,
                          custom_msg: str | None = None) -> None:
        """Krótki błąd → MessageBox; długi → Dialog z polem do skopiowania."""
        msg_header  = custom_msg or "Wystąpił nieoczekiwany błąd podczas przetwarzania."
        jest_krotki = len(tresc_bledu) <= 200 and "\n" not in tresc_bledu

        if jest_krotki:
            pelna = f"{msg_header}\n\n{tresc_bledu}" if custom_msg else tresc_bledu
            wx.MessageBox(pelna, "Błąd", wx.OK | wx.ICON_ERROR, self)
            return

        dlg = wx.Dialog(self, title="Błąd – Szczegóły techniczne", size=(640, 400))
        sizer = wx.BoxSizer(wx.VERTICAL)
        lbl_head = wx.StaticText(dlg, label=msg_header)
        lbl_copy = wx.StaticText(
            dlg,
            label="Treść błędu (zaznacz Ctrl+A, skopiuj Ctrl+C – do zgłoszenia):")
        txt = wx.TextCtrl(dlg, value=tresc_bledu,
                          style=wx.TE_MULTILINE | wx.TE_READONLY,
                          name="Treść błędu do skopiowania")
        btn_ok = wx.Button(dlg, wx.ID_OK, label="Zamknij")

        sizer.Add(lbl_head, flag=wx.ALL,                                       border=8)
        sizer.Add(lbl_copy, flag=wx.LEFT | wx.RIGHT | wx.BOTTOM,               border=8)
        sizer.Add(txt,      proportion=1, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=8)
        sizer.Add(btn_ok,   flag=wx.ALL | wx.ALIGN_RIGHT,                      border=8)
        dlg.SetSizer(sizer)
        txt.SetFocus()
        dlg.ShowModal()
        dlg.Destroy()
