"""
Reżyser Audio GPT – główny plik aplikacji (wxPython).
Zastępuje Start.py (Streamlit). Punkt wejścia: python main.py

Wersja 13.1: cały widoczny dla użytkownika tekst pochodzi z
``dictionaries/pl/gui/ui.yaml`` poprzez moduł :mod:`i18n`. Hard-kodowane
stringi zostały zastąpione wywołaniami ``t("klucz", **parametry)``.
"""

import os
import platform
import subprocess

import wx

import core_poliglota
import i18n
import odswiez_rezysera
from gui_konwerter import KonwerterPanel
from gui_manager_regul import ManagerRegulPanel
from gui_poliglota import PoliglotaPanel
from gui_rezyser import RezyserPanel
from i18n import t


# ---------------------------------------------------------------------------
# Identyfikatory menu
# ---------------------------------------------------------------------------
ID_HOME            = wx.NewIdRef()
ID_TOOL_REZYSER    = wx.NewIdRef()
ID_TOOL_POLIGLOTA  = wx.NewIdRef()
ID_TOOL_KONWERTER  = wx.NewIdRef()
ID_TOOL_MANAGER    = wx.NewIdRef()   # Manager Reguł – nowość w 13.0
ID_EXIT            = wx.NewIdRef()


# ---------------------------------------------------------------------------
# Konfiguracja użytkownika (wx.Config — cross-platform: rejestr Windows,
# plik INI na Linux, plist na macOS).
# ---------------------------------------------------------------------------
_NAZWA_APP_CONFIG  = "RezyserAudioGPT"
_KLUCZ_CONFIG_JEZYK = "/JezykInterfejsu"


# 13.4: lokalny `_natywna_nazwa` zastąpiony publicznym `core_poliglota.natywna_nazwa`
# (single source of truth — używane też w GUI Poligloty przy dialogu zmiany języka
# pipeline'u). Funkcja modułu Poligloty czyta `<kod>/podstawy.yaml::etykieta`
# i bierze prefiks przed em-dashem.
_natywna_nazwa = core_poliglota.natywna_nazwa


def _wybierz_jezyk_startowy() -> str:
    """Decyduje, który język interfejsu załadować na starcie aplikacji.

    Logika (w kolejności):

      1. Jeśli `wx.Config` ma zapisaną wartość pod kluczem
         `/JezykInterfejsu` i ten kod jest dziś *kompletny*
         (tj. obecny w :func:`core_poliglota.dostepne_jezyki_bazowe`)
         — używamy go.
      2. Jeśli kompletny jest tylko jeden język — milczący zapis
         (silent init), bez pytania użytkownika.
      3. Jeśli kompletnych jest ≥ 2 — pokazujemy first-run dialog
         (hardkodowany po angielsku), zapisujemy wybór do `wx.Config`.
      4. Awaryjny fallback — :data:`i18n.JEZYK_DOMYSLNY` (= ``"pl"``),
         np. gdy `dictionaries/` zniknął lub żaden folder nie przechodzi
         filtra kompletności.

    Wymaga aktywnej instancji `wx.App` (wx.Config zapisuje do rejestru/
    pliku użytkownika, a wx.SingleChoiceDialog korzysta z głównej pętli
    GUI). Wywołuj PRZED utworzeniem :class:`MainFrame`.
    """
    kompletne = core_poliglota.dostepne_jezyki_bazowe()
    if not kompletne:
        return i18n.JEZYK_DOMYSLNY

    cfg = wx.Config(_NAZWA_APP_CONFIG)
    zapisany = cfg.Read(_KLUCZ_CONFIG_JEZYK, "")
    if zapisany and zapisany in kompletne:
        return zapisany

    # Brak ważnego ustawienia — zdecyduj
    if len(kompletne) == 1:
        cfg.Write(_KLUCZ_CONFIG_JEZYK, kompletne[0])
        cfg.Flush()
        return kompletne[0]

    wybor = _first_run_dialog(kompletne)
    cfg.Write(_KLUCZ_CONFIG_JEZYK, wybor)
    cfg.Flush()
    return wybor


def _first_run_dialog(kompletne: list[str]) -> str:
    """First-run language selector — HARDKODOWANY po angielsku.

    Treść NIE używa modułu i18n, bo użytkownik nie wybrał jeszcze języka
    interfejsu — angielski to neutralne i powszechnie zrozumiałe domyślne.
    Lista języków posortowana po kodzie ISO (deterministycznie, bez
    PL-hardcode na pierwszej pozycji), z natywnymi nazwami pobranymi
    z `<kod>/podstawy.yaml::etykieta`.

    Cancel → :data:`i18n.JEZYK_DOMYSLNY` (``"pl"``) jako bezpieczny
    fallback (rdzeń projektu).

    Args:
        kompletne: lista kodów ISO 639-1, każdy spełnia kryterium
                   `core_poliglota._jezyk_kompletny`.

    Returns:
        Wybrany kod ISO (np. ``"fi"``).
    """
    kody_sort = sorted(kompletne)
    nazwy_sort = [_natywna_nazwa(k) for k in kody_sort]

    dlg = wx.SingleChoiceDialog(
        None,
        "Please select the application interface language.",
        "Choose your language",
        nazwy_sort,
    )
    dlg.SetSelection(0)
    try:
        if dlg.ShowModal() == wx.ID_OK:
            wybor = kody_sort[dlg.GetSelection()]
        else:
            wybor = i18n.JEZYK_DOMYSLNY
    finally:
        dlg.Destroy()
    return wybor


# ---------------------------------------------------------------------------
# Panel startowy z System Checkiem (odpowiednik Start.py)
# ---------------------------------------------------------------------------
class HomePanel(wx.Panel):
    """
    Ekran powitalny aplikacji.

    Wyświetla krótki opis dostępnych narzędzi oraz przeprowadza
    walidację pliku golden_key.env (System Check).
    Jest to domyślny panel ładowany przy uruchomieniu programu.
    Odpowiada stronie głównej z dawnego Start.py (Streamlit).
    """

    ENV_FILENAME = "golden_key.env"
    MINIMUM_ZNAKOW_KLUCZA = 40

    def __init__(self, parent: wx.Window) -> None:
        super().__init__(parent, style=wx.TAB_TRAVERSAL)
        self.SetName(t("home.panel_name"))
        self._build_ui()
        self._run_system_check()

    # ------------------------------------------------------------------
    # Właściwość: bezwzględna ścieżka do golden_key.env
    # ------------------------------------------------------------------
    @property
    def _env_path(self) -> str:
        """Ścieżka do golden_key.env w tym samym katalogu co main.py."""
        app_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(app_dir, self.ENV_FILENAME)

    # ------------------------------------------------------------------
    # Budowanie UI
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # --- Opis narzędzi ---
        welcome = wx.TextCtrl(
            self,
            value=t("home.welcome_text"),
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.NO_BORDER,
        )
        # Upodabniamy tło pola do tła głównego okna, żeby nie wyglądało jak pole do wpisywania
        welcome.SetBackgroundColour(self.GetBackgroundColour())
        # Przechowujemy referencję – MainFrame użyje jej do ustawienia fokusu startowego
        self._welcome = welcome
        main_sizer.Add(welcome, flag=wx.ALL, border=16)

        # --- Separator ---
        main_sizer.Add(
            wx.StaticLine(self), flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=8
        )

        # --- Nagłówek sekcji System Check ---
        heading_check = wx.StaticText(self, label=t("home.heading_system_check"))
        font_h = heading_check.GetFont()
        font_h.SetPointSize(13)
        font_h.MakeBold()
        heading_check.SetFont(font_h)
        main_sizer.Add(heading_check, flag=wx.TOP | wx.LEFT | wx.RIGHT, border=16)

        # --- Etykieta statusu (aktualizowana przez _run_system_check) ---
        self._status_lbl = wx.TextCtrl(
            self,
            value=t("home.checking"),
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.NO_BORDER,
        )
        # Upodabniamy tło pola do tła głównego okna, żeby nie wyglądało jak pole do wpisywania
        self._status_lbl.SetBackgroundColour(self.GetBackgroundColour())
        main_sizer.Add(self._status_lbl, flag=wx.ALL | wx.EXPAND, border=16)

        # --- Przycisk akcji (domyślnie ukryty) ---
        self._action_btn = wx.Button(self, label="")
        self._action_btn.Hide()
        self.Bind(wx.EVT_BUTTON, self._on_action_btn, self._action_btn)
        main_sizer.Add(self._action_btn, flag=wx.LEFT | wx.BOTTOM, border=16)

        # --- Sekcja: Narzędzia słownikowe (dla lingwistów) ---
        main_sizer.Add(
            wx.StaticLine(self), flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=8
        )

        heading_tools = wx.StaticText(self, label=t("home.heading_narzedzia_slownikowe"))
        font_t = heading_tools.GetFont()
        font_t.SetPointSize(13)
        font_t.MakeBold()
        heading_tools.SetFont(font_t)
        main_sizer.Add(heading_tools, flag=wx.TOP | wx.LEFT | wx.RIGHT, border=16)

        tools_info = wx.TextCtrl(
            self,
            value=t("home.tools_info"),
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.NO_BORDER,
            name=t("home.narzedzia_slownikowe_name"),
        )
        tools_info.SetBackgroundColour(self.GetBackgroundColour())
        main_sizer.Add(tools_info, flag=wx.LEFT | wx.RIGHT | wx.TOP | wx.EXPAND,
                       border=16)

        # --- Pasek z dwoma przyciskami skrótu ---
        tools_btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self._btn_open_manager = wx.Button(
            self, label=t("home.btn_open_manager_label"),
            name=t("home.btn_open_manager_name"),
        )
        self._btn_open_manager.SetToolTip(t("home.btn_open_manager_tooltip"))
        self.Bind(wx.EVT_BUTTON, self._on_open_manager, self._btn_open_manager)
        tools_btn_sizer.Add(self._btn_open_manager, flag=wx.RIGHT, border=8)

        self._btn_odswiez = wx.Button(
            self, label=t("home.btn_odswiez_label"),
            name=t("home.btn_odswiez_name"),
        )
        self._btn_odswiez.SetToolTip(t("home.btn_odswiez_tooltip"))
        self.Bind(wx.EVT_BUTTON, self._on_odswiez_rezysera, self._btn_odswiez)
        tools_btn_sizer.Add(self._btn_odswiez)

        main_sizer.Add(tools_btn_sizer, flag=wx.ALL, border=16)

        self.SetSizer(main_sizer)

    # ------------------------------------------------------------------
    # Handler: przejście do Managera Reguł (przycisk w sekcji
    # „Narzędzia słownikowe" – wykorzystuje MainFrame._on_manager)
    # ------------------------------------------------------------------
    def _on_open_manager(self, _event: wx.Event) -> None:
        """Przełącza aplikację na panel Managera Reguł.

        Zakładamy, że HomePanel jest osadzony w MainFrame – znajdujemy go
        przez GetTopLevelParent i wywołujemy jego publiczny handler.
        """
        top = self.GetTopLevelParent()
        if hasattr(top, "_on_manager"):
            top._on_manager(_event)   # noqa: SLF001 – świadome użycie

    # ------------------------------------------------------------------
    # Logika walidacji golden_key.env
    # ------------------------------------------------------------------
    def _run_system_check(self) -> None:
        """Waliduje plik golden_key.env i aktualizuje etykietę statusu."""
        env_path = self._env_path

        # Plik nie istnieje – pierwsze uruchomienie
        if not os.path.exists(env_path):
            self._set_status(t("home.err_brak_pliku"), kind="error")
            self._show_action_btn(
                action="generate",
                label=t("home.btn_generate"),
            )
            return

        # Odczyt pliku
        try:
            with open(env_path, "r", encoding="utf-8-sig") as fh:
                zawartosc = fh.read().strip()
        except Exception as exc:
            self._set_status(
                t("home.err_odczyt", tresc_bledu=str(exc)),
                kind="error",
            )
            return

        # 1. Brak parametru OPENAI_API_KEY=
        if "OPENAI_API_KEY=" not in zawartosc:
            self._set_status(t("home.err_struktura"), kind="error")
            self._show_action_btn("open", t("home.btn_open"))
            return

        # 2. Tekst zastępczy nadal w pliku
        if "TUTAJ_WKLEJ_SWOJ_KLUCZ" in zawartosc:
            self._set_status(t("home.err_tekst_zastepczy"), kind="warning")
            self._show_action_btn("open", t("home.btn_open"))
            return

        klucz_raw = zawartosc.split("OPENAI_API_KEY=")[-1].split("\n")[0]
        klucz = klucz_raw.strip()

        # 3. Zbędne cudzysłowy
        if (klucz.startswith('"') and klucz.endswith('"')) or \
           (klucz.startswith("'") and klucz.endswith("'")):
            self._set_status(t("home.err_cudzyslowy"), kind="error")
            self._show_action_btn("open", t("home.btn_open"))
            return

        # 4. Spacje lub znaki niedrukowalne przy kluczu
        if klucz_raw != klucz:
            self._set_status(t("home.err_niedozwolone_znaki"), kind="error")
            self._show_action_btn("open", t("home.btn_open"))
            return

        # 5. Niepoprawny format klucza OpenAI
        if not klucz.startswith("sk-"):
            self._set_status(t("home.err_format"), kind="error")
            self._show_action_btn("open", t("home.btn_open"))
            return

        # 6. Klucz zbyt krótki
        if len(klucz) < self.MINIMUM_ZNAKOW_KLUCZA:
            self._set_status(
                t(
                    "home.err_zbyt_krotki",
                    liczba_znakow=len(klucz),
                    minimum_znakow=self.MINIMUM_ZNAKOW_KLUCZA,
                ),
                kind="warning",
            )
            self._show_action_btn("open", t("home.btn_open"))
            return

        # Wszystkie testy przeszły – sukces
        self._set_status(t("home.ok_klucz_wykryty"), kind="ok")

    # ------------------------------------------------------------------
    # Pomocnicze metody UI
    # ------------------------------------------------------------------
    def _set_status(self, message: str, kind: str = "ok") -> None:
        """Ustawia tekst i kolor etykiety statusu.

        Args:
            message: Treść komunikatu widoczna w interfejsie.
            kind:    ``"ok"`` | ``"warning"`` | ``"error"``
        """
        colour_map = {
            "ok":      wx.Colour(0, 128, 0),    # zielony
            "warning": wx.Colour(180, 100, 0),  # pomarańczowy
            "error":   wx.Colour(180, 0, 0),    # czerwony
        }
        self._status_lbl.SetValue(message)
        # Ustawienie nazwy = NVDA odczyta komunikat po sfocusowaniu kontrolki
        self._status_lbl.SetName(message)
        self._status_lbl.SetForegroundColour(colour_map.get(kind, colour_map["ok"]))

    def _show_action_btn(self, action: str, label: str) -> None:
        """Pokazuje przycisk akcji z odpowiednią etykietą."""
        self._action_btn.SetLabel(label)
        self._action_btn.SetName(label)
        self._action_btn._action = action   # noqa: SLF001
        self._action_btn.Show()
        self.Layout()

    # ------------------------------------------------------------------
    # Handler przycisku akcji
    # ------------------------------------------------------------------
    def _on_action_btn(self, _event: wx.Event) -> None:
        """Generuje plik golden_key.env (jeśli brak) lub otwiera go w domyślnym edytorze tekstu."""
        env_path = self._env_path
        action   = getattr(self._action_btn, "_action", "open")

        if action == "generate":
            try:
                with open(env_path, "w", encoding="utf-8") as fh:
                    fh.write("OPENAI_API_KEY=TUTAJ_WKLEJ_SWOJ_KLUCZ")
            except Exception as exc:
                wx.MessageBox(
                    t("home.blad_tworzenia_env_tresc", tresc_bledu=str(exc)),
                    t("home.blad_tworzenia_env_tytul"),
                    wx.OK | wx.ICON_ERROR,
                )
                return
            # Plik wygenerowany – zaktualizuj UI
            self._set_status(
                t("home.ok_plik_wygenerowany", nazwa_pliku=self.ENV_FILENAME),
                kind="ok",
            )
            # Przenieś fokus przed ukryciem przycisku – NVDA nie wpadnie w próżnię (A11y)
            self._status_lbl.SetFocus()
            self._action_btn.Hide()
            self.Layout()

        # Otwórz plik w domyślnym edytorze tekstu (cross-platform)
        try:
            if platform.system() == "Windows":
                os.startfile(env_path)          # otworzy Notatnik lub inny domyślny edytor
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", env_path])
            else:
                subprocess.Popen(["xdg-open", env_path])   # Linux + Orca itp.
        except Exception:  # noqa: BLE001
            wx.MessageBox(
                t("home.blad_otwarcia_pliku_tresc", sciezka_pliku=env_path),
                t("home.blad_otwarcia_pliku_tytul"),
                wx.OK | wx.ICON_INFORMATION,
                self,
            )

    # ------------------------------------------------------------------
    # Handler: Odśwież akcenty Reżysera z YAML
    # ------------------------------------------------------------------
    def _on_odswiez_rezysera(self, _event: wx.Event) -> None:
        """Skanuje dictionaries/ i regeneruje wrappery akcent_* w module Reżysera.

        Zbiera log generatora do listy, a potem pokazuje go w dialogu
        z polem TextCtrl (dostępne dla NVDA – Ctrl+A, Ctrl+C kopiuje całość).
        Przy sukcesie informuje o konieczności ponownego uruchomienia
        aplikacji; przy błędzie wyświetla pełną treść błędu.
        """
        linie: list[str] = []
        try:
            raport = odswiez_rezysera.uruchom(on_log=linie.append)
        except Exception as exc:  # noqa: BLE001
            wx.MessageBox(
                t("home.raport_niespodziewany_tresc", tresc_bledu=str(exc)),
                t("home.raport_niespodziewany_tytul"),
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return

        # Zbuduj nagłówek dialogu w zależności od wyniku
        if raport["errors"]:
            tytul  = t("home.raport_tytul_blad")
            header = t("home.raport_header_blad")
        elif raport["core_changed"] or raport["rezyser_changed"]:
            tytul  = t("home.raport_tytul_sukces")
            n = len(raport["akcenty"])
            header = t("home.raport_header_sukces", liczba_akcentow=n)
        else:
            tytul  = t("home.raport_tytul_bez_zmian")
            n = len(raport["akcenty"])
            header = t("home.raport_header_bez_zmian", liczba_akcentow=n)

        self._pokaz_raport_dialog(tytul, header, "\n".join(linie))

    def _pokaz_raport_dialog(
        self, tytul: str, header: str, tresc_logu: str,
    ) -> None:
        """Wyświetla raport generatora w dialogu z polem do skopiowania.

        Dialog jest w pełni dostępny z klawiatury i NVDA: pole TextCtrl
        (TE_READONLY) odczytuje treść linia po linii strzałkami, Ctrl+A
        + Ctrl+C kopiuje wszystko do schowka.
        """
        dlg = wx.Dialog(self, title=tytul, size=(640, 420))
        sizer = wx.BoxSizer(wx.VERTICAL)

        lbl_head = wx.StaticText(dlg, label=header)
        lbl_copy = wx.StaticText(dlg, label=t("home.raport_lbl_log"))
        txt = wx.TextCtrl(
            dlg, value=tresc_logu,
            style=wx.TE_MULTILINE | wx.TE_READONLY,
            name=t("home.raport_log_name"),
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


# ---------------------------------------------------------------------------
# Główne okno aplikacji
# ---------------------------------------------------------------------------
class MainFrame(wx.Frame):
    """
    Główne okno aplikacji Reżyser Audio GPT.

    Struktura:
        - pasek menu (wx.MenuBar) z menu „Narzędzia" i „Plik"
        - centralny wx.Panel, w którym podmieniane są panele narzędzi

    Wersja 13.1: tytuł, wersja i nazwy narzędzi pobierane z i18n
    (sekcja ``app`` i ``main.nazwy_narzedzi`` w ``ui.yaml``).
    """

    def __init__(self) -> None:
        self._tytul = t("app.nazwa")
        self._wersja = t("app.wersja")
        super().__init__(
            parent=None,
            title=t("app.title_home", nazwa_aplikacji=self._tytul, wersja=self._wersja),
            size=(960, 640),
        )

        self._build_menu()
        self._build_ui()
        self._bind_events()

        # Domyślnie ładujemy ekran powitalny (Strona główna)
        self._switch_tool(t("main.nazwy_narzedzi.dom"))

        self.Centre()
        self.Show()

    # ------------------------------------------------------------------
    # Budowanie paska menu
    # ------------------------------------------------------------------
    def _build_menu(self) -> None:
        menubar = wx.MenuBar()

        # --- Menu: Narzędzia -------------------------------------------
        menu_tools = wx.Menu()

        menu_tools.Append(
            ID_HOME,
            t("main.menu.strona_glowna"),
            t("main.menu_status.strona_glowna"),
        )
        menu_tools.AppendSeparator()

        menu_tools.Append(
            ID_TOOL_REZYSER,
            t("main.menu.rezyser"),
            t("main.menu_status.rezyser"),
        )
        menu_tools.Append(
            ID_TOOL_POLIGLOTA,
            t("main.menu.poliglota"),
            t("main.menu_status.poliglota"),
        )
        menu_tools.Append(
            ID_TOOL_KONWERTER,
            t("main.menu.konwerter"),
            t("main.menu_status.konwerter"),
        )
        menu_tools.Append(
            ID_TOOL_MANAGER,
            t("main.menu.manager"),
            t("main.menu_status.manager"),
        )

        # --- Menu: Plik ------------------------------------------------
        menu_file = wx.Menu()
        menu_file.Append(ID_EXIT, t("main.menu.zakoncz"), t("main.menu_status.zakoncz"))

        menubar.Append(menu_tools, t("main.menu.narzedzia"))
        menubar.Append(menu_file,  t("main.menu.plik"))

        # --- Menu: Język interfejsu (tylko gdy ≥ 2 kompletne języki) --
        # Mapa {wx.WindowIDRef: kod_iso}, wypełniana w pętli i odczytywana
        # przez :meth:`_on_zmien_jezyk`. Pusta gdy menu nie powstaje.
        self._jezyk_menu_ids: dict[int, str] = {}
        kompletne = core_poliglota.dostepne_jezyki_bazowe()
        if len(kompletne) >= 2:
            menu_lang = wx.Menu()
            aktualny = i18n.aktualny_jezyk()
            for kod in kompletne:
                new_id = wx.NewIdRef()
                item = menu_lang.AppendRadioItem(new_id, _natywna_nazwa(kod))
                if kod == aktualny:
                    item.Check(True)
                self._jezyk_menu_ids[int(new_id)] = kod
            menubar.Append(menu_lang, t("main.menu.jezyk_interfejsu"))

        self.SetMenuBar(menubar)

        # Dostępnościowa nazwa paska menu (NVDA odczyta ją po Alt)
        menubar.SetName(t("app.menubar_name"))

    # ------------------------------------------------------------------
    # Budowanie układu UI (sizer + panel centralny)
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        # Główny kontener – panel z tabulacją
        self._root_panel = wx.Panel(self, style=wx.TAB_TRAVERSAL)
        self._root_panel.SetName(t("app.obszar_roboczy_name"))

        self._root_sizer = wx.BoxSizer(wx.VERTICAL)

        # Baner tytułowy (dostępny dla NVDA jako statyczny tekst)
        self._banner = wx.StaticText(
            self._root_panel,
            label=t("app.banner", nazwa_aplikacji=self._tytul),
        )
        banner_font = self._banner.GetFont()
        banner_font.SetPointSize(18)
        banner_font.MakeBold()
        self._banner.SetFont(banner_font)

        # Pasek narzędzi – trzy przyciski (alternatywa dla menu, lepiej A11y)
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self._btn_rezyser = wx.Button(
            self._root_panel,
            id=ID_TOOL_REZYSER,
            label=t("main.btn.rezyser"),
        )
        self._btn_rezyser.SetToolTip(t("main.tooltip.rezyser"))

        self._btn_poliglota = wx.Button(
            self._root_panel,
            id=ID_TOOL_POLIGLOTA,
            label=t("main.btn.poliglota"),
        )
        self._btn_poliglota.SetToolTip(t("main.tooltip.poliglota"))

        self._btn_konwerter = wx.Button(
            self._root_panel,
            id=ID_TOOL_KONWERTER,
            label=t("main.btn.konwerter"),
        )
        self._btn_konwerter.SetToolTip(t("main.tooltip.konwerter"))

        self._btn_manager = wx.Button(
            self._root_panel,
            id=ID_TOOL_MANAGER,
            label=t("main.btn.manager"),
        )
        self._btn_manager.SetToolTip(t("main.tooltip.manager"))

        btn_sizer.Add(self._btn_rezyser,   flag=wx.ALL, border=4)
        btn_sizer.Add(self._btn_poliglota, flag=wx.ALL, border=4)
        btn_sizer.Add(self._btn_konwerter, flag=wx.ALL, border=4)
        btn_sizer.Add(self._btn_manager,   flag=wx.ALL, border=4)

        # Separator poziomy
        separator = wx.StaticLine(self._root_panel)

        # Kontener na aktywny panel narzędzia
        self._content_area = wx.BoxSizer(wx.VERTICAL)
        self._current_panel: wx.Panel | None = None

        # Złożenie layoutu
        self._root_sizer.Add(self._banner,      flag=wx.ALL, border=12)
        self._root_sizer.Add(btn_sizer,         flag=wx.LEFT | wx.RIGHT | wx.BOTTOM, border=8)
        self._root_sizer.Add(separator,         flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=8)
        self._root_sizer.Add(self._content_area, proportion=1, flag=wx.EXPAND | wx.ALL, border=8)

        self._root_panel.SetSizer(self._root_sizer)

        # Kolejność tabulacji: przyciski w logicznej kolejności
        self._btn_rezyser.MoveBeforeInTabOrder(self._btn_poliglota)
        self._btn_poliglota.MoveBeforeInTabOrder(self._btn_konwerter)
        self._btn_konwerter.MoveBeforeInTabOrder(self._btn_manager)

    # ------------------------------------------------------------------
    # Podpięcie zdarzeń
    # ------------------------------------------------------------------
    def _bind_events(self) -> None:
        # Menu
        self.Bind(wx.EVT_MENU, self._on_home,       id=ID_HOME)
        self.Bind(wx.EVT_MENU, self._on_rezyser,    id=ID_TOOL_REZYSER)
        self.Bind(wx.EVT_MENU, self._on_poliglota,  id=ID_TOOL_POLIGLOTA)
        self.Bind(wx.EVT_MENU, self._on_konwerter,  id=ID_TOOL_KONWERTER)
        self.Bind(wx.EVT_MENU, self._on_manager,    id=ID_TOOL_MANAGER)
        self.Bind(wx.EVT_MENU, self._on_exit,       id=ID_EXIT)

        # Menu: Język interfejsu — jeden handler dla wszystkich radio items;
        # rozróżnienie kodu ISO przez `event.GetId()` w `_on_zmien_jezyk`.
        for menu_id in self._jezyk_menu_ids:
            self.Bind(wx.EVT_MENU, self._on_zmien_jezyk, id=menu_id)

        # Przyciski (te same identyfikatory → te same handlery przez EVT_BUTTON)
        self.Bind(wx.EVT_BUTTON, self._on_rezyser,   id=ID_TOOL_REZYSER)
        self.Bind(wx.EVT_BUTTON, self._on_poliglota, id=ID_TOOL_POLIGLOTA)
        self.Bind(wx.EVT_BUTTON, self._on_konwerter, id=ID_TOOL_KONWERTER)
        self.Bind(wx.EVT_BUTTON, self._on_manager,   id=ID_TOOL_MANAGER)

        self.Bind(wx.EVT_CLOSE, self._on_close)

    # ------------------------------------------------------------------
    # Przełączanie narzędzi
    # ------------------------------------------------------------------
    def _switch_tool(self, name: str) -> None:
        """Podmienia panel centralny na panel wskazanego narzędzia.

        Args:
            name: Nazwa narzędzia — wartość zwracana przez
                  ``t("main.nazwy_narzedzi.*")``. Używamy ich zarówno
                  do routingu, jak i do budowy tytułu okna — dzięki temu
                  przy zmianie języka wszystko pozostaje spójne.
        """
        # Pobierz kanoniczne nazwy z i18n (raz, zamiast wielokrotnie wołać t())
        n_dom       = t("main.nazwy_narzedzi.dom")
        n_rezyser   = t("main.nazwy_narzedzi.rezyser")
        n_poliglota = t("main.nazwy_narzedzi.poliglota")
        n_konwerter = t("main.nazwy_narzedzi.konwerter")
        n_manager   = t("main.nazwy_narzedzi.manager")

        # Usuń poprzedni panel (jeśli istnieje)
        if self._current_panel is not None:
            self._content_area.Detach(self._current_panel)
            self._current_panel.Destroy()

        # Utwórz właściwy panel narzędzia
        if name == n_dom:
            self._current_panel = HomePanel(self._root_panel)
        elif name == n_rezyser:
            self._current_panel = RezyserPanel(self._root_panel)
        elif name == n_poliglota:
            self._current_panel = PoliglotaPanel(self._root_panel)
        elif name == n_konwerter:
            self._current_panel = KonwerterPanel(self._root_panel)
        else:  # Manager Reguł
            self._current_panel = ManagerRegulPanel(self._root_panel)
        self._content_area.Add(self._current_panel, proportion=1, flag=wx.EXPAND)

        # Odśwież layout (A11y)
        self._root_panel.Layout()

        # Ustaw fokus na pierwszy sensowny element nowego panelu, żeby NVDA
        # od razu zaczęło czytać nowy widok po zmianie narzędzia.
        # Na ekranie startowym fokus ląduje na tekście powitalnym (welcome),
        # w pozostałych panelach domyślny SetFocus kieruje go na pierwszy TabStop.
        if name == n_dom:
            wx.CallAfter(self._current_panel._welcome.SetFocus)
        else:
            wx.CallAfter(self._current_panel.SetFocus)

        # Zaktualizuj tytuł okna – NVDA go odczyta
        # Dla ekranu startowego pomijamy myślnik (brak aktywnego narzędzia)
        if name == n_dom:
            self.SetTitle(
                t("app.title_home", nazwa_aplikacji=self._tytul, wersja=self._wersja),
            )
        else:
            self.SetTitle(
                t(
                    "app.title_z_narzedziem",
                    nazwa_aplikacji=self._tytul,
                    nazwa_narzedzia=name,
                    wersja=self._wersja,
                ),
            )

        # Zaktualizuj wizualne wyróżnienie aktywnego przycisku
        self._update_button_states(name)

    def _update_button_states(self, active_name: str) -> None:
        """Wizualnie wyróżnia aktywny przycisk narzędzia (bold)."""
        mapping = {
            t("main.nazwy_narzedzi.rezyser"):   self._btn_rezyser,
            t("main.nazwy_narzedzi.poliglota"): self._btn_poliglota,
            t("main.nazwy_narzedzi.konwerter"): self._btn_konwerter,
            t("main.nazwy_narzedzi.manager"):   self._btn_manager,
        }
        for tool_name, btn in mapping.items():
            font = btn.GetFont()
            font.SetWeight(
                wx.FONTWEIGHT_BOLD if tool_name == active_name else wx.FONTWEIGHT_NORMAL
            )
            btn.SetFont(font)

    # ------------------------------------------------------------------
    # Handlery zdarzeń
    # ------------------------------------------------------------------
    def _on_home(self, _event: wx.Event) -> None:
        self._switch_tool(t("main.nazwy_narzedzi.dom"))

    def _on_rezyser(self, _event: wx.Event) -> None:
        self._switch_tool(t("main.nazwy_narzedzi.rezyser"))

    def _on_poliglota(self, _event: wx.Event) -> None:
        self._switch_tool(t("main.nazwy_narzedzi.poliglota"))

    def _on_konwerter(self, _event: wx.Event) -> None:
        self._switch_tool(t("main.nazwy_narzedzi.konwerter"))

    def _on_manager(self, _event: wx.Event) -> None:
        self._switch_tool(t("main.nazwy_narzedzi.manager"))

    def _on_exit(self, _event: wx.Event) -> None:
        self.Close()

    def _on_zmien_jezyk(self, event: wx.Event) -> None:
        """Handler radio-item z menu „Język interfejsu".

        Zapisuje wybór do `wx.Config`, pokazuje komunikat o konieczności
        restartu (w aktywnym = poprzednim języku, bo nowe tłumaczenia
        zaczną obowiązywać dopiero po ponownym uruchomieniu) i zamyka
        aplikację. Brak dynamicznego re-renderu – ryzyko regresji we
        wszystkich oknach byłoby zbyt duże, a użytkownicy NVDA i tak
        odzyskują pełen kontekst po ponownym otwarciu okna.
        """
        kod = self._jezyk_menu_ids.get(event.GetId())
        if not kod or kod == i18n.aktualny_jezyk():
            return  # nic nie zmieniamy

        cfg = wx.Config(_NAZWA_APP_CONFIG)
        cfg.Write(_KLUCZ_CONFIG_JEZYK, kod)
        cfg.Flush()

        wx.MessageBox(
            t("main.dialog.zmiana_jezyka_tresc", nazwa_jezyka=_natywna_nazwa(kod)),
            t("main.dialog.zmiana_jezyka_tytul"),
            wx.OK | wx.ICON_INFORMATION,
            self,
        )
        self.Close()

    def _on_close(self, event: wx.CloseEvent) -> None:
        event.Skip()  # Pozwól wxPython zniszczyć okno w standardowy sposób


# ---------------------------------------------------------------------------
# Punkt wejścia
# ---------------------------------------------------------------------------
def main() -> None:
    # Kolejność jest istotna:
    #   1. wx.App MUSI istnieć przed wx.Config (rejestr/plik użytkownika)
    #      i przed wx.SingleChoiceDialog (first-run dialog korzysta z GUI).
    #   2. _wybierz_jezyk_startowy() ustala kod języka z 4 źródeł
    #      (cfg → silent init → first-run dialog → fallback "pl").
    #   3. i18n.ustaw_jezyk() ładuje `dictionaries/<kod>/gui/ui.yaml` do
    #      cache, dzięki czemu konstruktory paneli mogą wołać `t()` bez
    #      narzutu I/O w wątku GUI.
    #   4. MainFrame() buduje okno na bazie już-aktywnego języka.
    app = wx.App(False)
    kod_jezyka = _wybierz_jezyk_startowy()
    i18n.ustaw_jezyk(kod_jezyka)

    frame = MainFrame()  # noqa: F841  (frame jest trzymany przez wx.App)
    app.MainLoop()


if __name__ == "__main__":
    main()
