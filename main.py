"""
Reżyser Audio GPT – główny plik aplikacji (wxPython).
Zastępuje Start.py (Streamlit). Punkt wejścia: python main.py
"""

import os
import platform
import subprocess

import wx

from gui_konwerter import KonwerterPanel
from gui_poliglota import PoliglotaPanel
from gui_rezyser import RezyserPanel


# ---------------------------------------------------------------------------
# Identyfikatory menu
# ---------------------------------------------------------------------------
ID_HOME           = wx.NewIdRef()
ID_TOOL_REZYSER   = wx.NewIdRef()
ID_TOOL_POLIGLOTA = wx.NewIdRef()
ID_TOOL_KONWERTER = wx.NewIdRef()
ID_EXIT           = wx.NewIdRef()


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

    def __init__(self, parent: wx.Window) -> None:
        super().__init__(parent, style=wx.TAB_TRAVERSAL)
        self.SetName("Panel startowy – Strona główna")
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
            value=(
                "To jest Twoje zintegrowane studio nagraniowe.\n"
                "Wybierz narzędzie z paska przycisków lub z menu Narzędzia:\n\n"
                "  \u2022  Reżyser    \u2013  Pisz skrypty i prozę z AI;"
                " dynamicznie zarządzaj Księgą Świata.\n"
                "  \u2022  Poliglota  \u2013  Nakładaj twarde akcenty pod lokalne"
                " syntezatory (NVDA/Vocalizer) i tłumacz teksty.\n"
                "  \u2022  Konwerter  \u2013  Szybko twórz profesjonalne pliki Word"
                " z nagłówkami poziomu 1."
            ),
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
        heading_check = wx.StaticText(self, label="System Check")
        font_h = heading_check.GetFont()
        font_h.SetPointSize(13)
        font_h.MakeBold()
        heading_check.SetFont(font_h)
        main_sizer.Add(heading_check, flag=wx.TOP | wx.LEFT | wx.RIGHT, border=16)

        # --- Etykieta statusu (aktualizowana przez _run_system_check) ---
        self._status_lbl = wx.TextCtrl(
            self,
            value="Sprawdzanie konfiguracji\u2026",
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

        self.SetSizer(main_sizer)

    # ------------------------------------------------------------------
    # Logika walidacji golden_key.env
    # ------------------------------------------------------------------
    def _run_system_check(self) -> None:
        """Waliduje plik golden_key.env i aktualizuje etykietę statusu."""
        env_path = self._env_path

        # Plik nie istnieje – pierwsze uruchomienie
        if not os.path.exists(env_path):
            self._set_status(
                "🚨 Brak pliku konfiguracji środowiskowej!\n\n"
                "Wykryto pierwsze uruchomienie programu. Moduły są zablokowane "
                "ze względów bezpieczeństwa.\n"
                "Aby odblokować wszystkie narzędzia, kliknij przycisk poniżej — "
                "program automatycznie wygeneruje plik golden_key.env "
                "i otworzy go w domyślnym edytorze tekstu.",
                kind="error",
            )
            self._show_action_btn(
                action="generate",
                label="Wygeneruj plik golden_key.env i otwórz edytor tekstu",
            )
            return

        # Odczyt pliku
        try:
            with open(env_path, "r", encoding="utf-8-sig") as fh:
                zawartosc = fh.read().strip()
        except Exception as exc:
            self._set_status(
                f"🚨 Nie udało się odczytać pliku golden_key.env:\n{exc}",
                kind="error",
            )
            return

        # 1. Brak parametru OPENAI_API_KEY=
        if "OPENAI_API_KEY=" not in zawartosc:
            self._set_status(
                "🚨 Błąd struktury pliku!\n"
                "Brakuje wymaganego parametru OPENAI_API_KEY=.\n"
                "Prawdopodobnie skasowałeś znak równości lub nazwę zmiennej.\n"
                "Usuń plik, wygeneruj go ponownie i wklej klucz ostrożniej.",
                kind="error",
            )
            self._show_action_btn("open", "📝 Otwórz plik golden_key.env w edytorze tekstu")
            return

        # 2. Tekst zastępczy nadal w pliku
        if "TUTAJ_WKLEJ_SWOJ_KLUCZ" in zawartosc:
            self._set_status(
                "⚠️ Klucz nie został wprowadzony!\n"
                "W pliku golden_key.env nadal znajduje się tekst zastępczy.\n"
                "Otwórz plik w edytorze tekstu, usuń tekst zastępczy "
                "i wklej swój prawdziwy klucz API.",
                kind="warning",
            )
            self._show_action_btn("open", "📝 Otwórz plik golden_key.env w edytorze tekstu")
            return

        klucz_raw = zawartosc.split("OPENAI_API_KEY=")[-1].split("\n")[0]
        klucz = klucz_raw.strip()

        # 3. Zbędne cudzysłowy
        if (klucz.startswith('"') and klucz.endswith('"')) or \
           (klucz.startswith("'") and klucz.endswith("'")):
            self._set_status(
                "🚨 Zbędne cudzysłowy wokół klucza!\n"
                'Klucz API wklejono w cudzysłowach (np. "sk-\u2026").\n'
                "Otwórz plik w edytorze tekstu i usuń znaki cudzysłowu —\n"
                "klucz musi być wpisany bezpośrednio po znaku '=', "
                "bez żadnych dodatkowych znaków.",
                kind="error",
            )
            self._show_action_btn("open", "📝 Otwórz plik golden_key.env w edytorze tekstu")
            return

        # 4. Spacje lub znaki niedrukowalne przy kluczu
        if klucz_raw != klucz:
            self._set_status(
                "🚨 Niedozwolone znaki wokół klucza!\n"
                "Przed lub za kluczem API wykryto spację bądź inny niewidoczny znak.\n"
                "Otwórz plik w edytorze tekstu i upewnij się, że wartość zaczyna się\n"
                "natychmiast po znaku '=', bez żadnych spacji.",
                kind="error",
            )
            self._show_action_btn("open", "📝 Otwórz plik golden_key.env w edytorze tekstu")
            return

        # 5. Niepoprawny format klucza OpenAI
        if not klucz.startswith("sk-"):
            self._set_status(
                "🚨 Podejrzany format klucza!\n"
                "Poprawny klucz OpenAI zawsze zaczyna się od znaków sk- (np. sk-proj-\u2026).\n"
                "Upewnij się, że skopiowałeś właściwy ciąg znaków "
                "i nie ma przed nim żadnych spacji.",
                kind="error",
            )
            self._show_action_btn("open", "📝 Otwórz plik golden_key.env w edytorze tekstu")
            return

        # 6. Klucz zbyt krótki
        if len(klucz) < 40:
            self._set_status(
                f"⚠️ Klucz wydaje się zbyt krótki "
                f"(wykryto {len(klucz)} znaków, oczekiwano co najmniej 40).\n"
                "Prawdopodobnie skopiowałeś tylko fragment klucza.\n\n"
                "Jeśli zamknąłeś już okienko z kluczem na platform.openai.com,\n"
                "musisz wrócić na konto, użyć opcji 'Revoke secret key' dla tego\n"
                "uciętego klucza i wygenerować nowy. Pamiętaj, by następnym razem\n"
                "skopiować klucz w całości przed kliknięciem 'Done'.",
                kind="warning",
            )
            self._show_action_btn("open", "📝 Otwórz plik golden_key.env w edytorze tekstu")
            return

        # Wszystkie testy przeszły – sukces
        self._set_status(
            "✅ Klucz API (golden_key.env) wykryty i poprawnie sformatowany.\n"
            "Wszystkie moduły są gotowe do pracy.",
            kind="ok",
        )

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
                    f"Nie udało się utworzyć pliku golden_key.env:\n{exc}",
                    "Błąd",
                    wx.OK | wx.ICON_ERROR,
                )
                return
            # Plik wygenerowany – zaktualizuj UI
            self._set_status(
                f"✅ Plik {self.ENV_FILENAME} został wygenerowany!\n"
                "Edytor tekstu otwiera się automatycznie.\n"
                "Wklej swój klucz API, zapisz plik (Ctrl+S) "
                "i uruchom aplikację ponownie.",
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
        except Exception as exc:  # noqa: BLE001
            wx.MessageBox(
                f"Nie udało się automatycznie otworzyć pliku.\n"
                f"Otwórz go ręcznie:\n{env_path}",
                "Informacja",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )


# ---------------------------------------------------------------------------
# Główne okno aplikacji
# ---------------------------------------------------------------------------
class MainFrame(wx.Frame):
    """
    Główne okno aplikacji Reżyser Audio GPT.

    Struktura:
        - pasek menu (wx.MenuBar) z menu „Narzędzia" i „Plik"
        - centralny wx.Panel, w którym podmieniane są panele narzędzi
    """

    TITLE   = "Reżyser Audio GPT"
    VERSION = "12.0 – Wersja Wydawnicza"

    def __init__(self) -> None:
        super().__init__(
            parent=None,
            title=f"{self.TITLE}  |  {self.VERSION}",
            size=(960, 640),
        )

        self._build_menu()
        self._build_ui()
        self._bind_events()

        # Domyślnie ładujemy ekran powitalny (Strona główna)
        self._switch_tool("Dom")

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
            "Strona &główna\tCtrl+0",
            "Wróć do ekranu startowego z opisem narzędzi i System Check",
        )
        menu_tools.AppendSeparator()

        item_rezyser = menu_tools.Append(
            ID_TOOL_REZYSER,
            "&Reżyser\tCtrl+1",
            "Otwiera moduł Reżyserii – pisanie skryptów i prozy z AI",
        )
        item_poliglota = menu_tools.Append(
            ID_TOOL_POLIGLOTA,
            "&Poliglota\tCtrl+2",
            "Otwiera moduł Poligloty – akcenty i tłumaczenie tekstów",
        )
        item_konwerter = menu_tools.Append(
            ID_TOOL_KONWERTER,
            "&Konwerter\tCtrl+3",
            "Otwiera moduł Konwertera – tworzenie plików Word",
        )

        # --- Menu: Plik ------------------------------------------------
        menu_file = wx.Menu()
        menu_file.Append(ID_EXIT, "Za&kończ\tAlt+F4", "Zamknij aplikację")

        menubar.Append(menu_tools, "&Narzędzia")
        menubar.Append(menu_file,  "&Plik")

        self.SetMenuBar(menubar)

        # Dostępnościowa nazwa paska menu (NVDA odczyta ją po Alt)
        menubar.SetName("Pasek menu głównego")

    # ------------------------------------------------------------------
    # Budowanie układu UI (sizer + panel centralny)
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        # Główny kontener – panel z tabulacją
        self._root_panel = wx.Panel(self, style=wx.TAB_TRAVERSAL)
        self._root_panel.SetName("Obszar roboczy")

        self._root_sizer = wx.BoxSizer(wx.VERTICAL)

        # Baner tytułowy (dostępny dla NVDA jako statyczny tekst)
        self._banner = wx.StaticText(
            self._root_panel,
            label=f"🎬  {self.TITLE}",
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
            label="🎬  &Reżyser",
        )
        self._btn_rezyser.SetToolTip(
            "Moduł Reżyserii (Ctrl+1): Pisz skrypty i prozę z pomocą AI"
        )

        self._btn_poliglota = wx.Button(
            self._root_panel,
            id=ID_TOOL_POLIGLOTA,
            label="🌍  &Poliglota",
        )
        self._btn_poliglota.SetToolTip(
            "Moduł Poligloty (Ctrl+2): Akcenty i tłumaczenie tekstów"
        )

        self._btn_konwerter = wx.Button(
            self._root_panel,
            id=ID_TOOL_KONWERTER,
            label="📄  &Konwerter",
        )
        self._btn_konwerter.SetToolTip(
            "Moduł Konwertera (Ctrl+3): Twórz pliki Word z nagłówkami"
        )

        btn_sizer.Add(self._btn_rezyser,   flag=wx.ALL, border=4)
        btn_sizer.Add(self._btn_poliglota, flag=wx.ALL, border=4)
        btn_sizer.Add(self._btn_konwerter, flag=wx.ALL, border=4)

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

    # ------------------------------------------------------------------
    # Podpięcie zdarzeń
    # ------------------------------------------------------------------
    def _bind_events(self) -> None:
        # Menu
        self.Bind(wx.EVT_MENU, self._on_home,       id=ID_HOME)
        self.Bind(wx.EVT_MENU, self._on_rezyser,   id=ID_TOOL_REZYSER)
        self.Bind(wx.EVT_MENU, self._on_poliglota,  id=ID_TOOL_POLIGLOTA)
        self.Bind(wx.EVT_MENU, self._on_konwerter,  id=ID_TOOL_KONWERTER)
        self.Bind(wx.EVT_MENU, self._on_exit,       id=ID_EXIT)

        # Przyciski (te same identyfikatory → te same handlery przez EVT_BUTTON)
        self.Bind(wx.EVT_BUTTON, self._on_rezyser,   id=ID_TOOL_REZYSER)
        self.Bind(wx.EVT_BUTTON, self._on_poliglota,  id=ID_TOOL_POLIGLOTA)
        self.Bind(wx.EVT_BUTTON, self._on_konwerter,  id=ID_TOOL_KONWERTER)

        self.Bind(wx.EVT_CLOSE, self._on_close)

    # ------------------------------------------------------------------
    # Przełączanie narzędzi
    # ------------------------------------------------------------------
    def _switch_tool(self, name: str) -> None:
        """Podmienia panel centralny na panel wskazanego narzędzia."""
        # Usuń poprzedni panel (jeśli istnieje)
        if self._current_panel is not None:
            self._content_area.Detach(self._current_panel)
            self._current_panel.Destroy()

        # Utwórz właściwy panel narzędzia
        if name == "Dom":
            self._current_panel = HomePanel(self._root_panel)
        elif name == "Reżyser":
            self._current_panel = RezyserPanel(self._root_panel)
        elif name == "Poliglota":
            self._current_panel = PoliglotaPanel(self._root_panel)
        else:  # "Konwerter"
            self._current_panel = KonwerterPanel(self._root_panel)
        self._content_area.Add(self._current_panel, proportion=1, flag=wx.EXPAND)

        # Odśwież layout (A11y)
        self._root_panel.Layout()

        # Ustaw fokus na pierwszy sensowny element nowego panelu, żeby NVDA
        # od razu zaczęło czytać nowy widok po zmianie narzędzia.
        # Na ekranie startowym fokus ląduje na tekście powitalnym (welcome),
        # w pozostałych panelach domyślny SetFocus kieruje go na pierwszy TabStop.
        if name == "Dom":
            wx.CallAfter(self._current_panel._welcome.SetFocus)
        else:
            wx.CallAfter(self._current_panel.SetFocus)

        # Zaktualizuj tytuł okna – NVDA go odczyta
        # Dla ekranu startowego pomijamy myślnik (brak aktywnego narzędzia)
        if name == "Dom":
            self.SetTitle(f"{self.TITLE}  |  {self.VERSION}")
        else:
            self.SetTitle(f"{self.TITLE}  –  {name}  |  {self.VERSION}")

        # Zaktualizuj wizualne wyróżnienie aktywnego przycisku
        self._update_button_states(name)

    def _update_button_states(self, active_name: str) -> None:
        """Wizualnie wyróżnia aktywny przycisk narzędzia (bold)."""
        mapping = {
            "Reżyser":   self._btn_rezyser,
            "Poliglota": self._btn_poliglota,
            "Konwerter": self._btn_konwerter,
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
        self._switch_tool("Dom")

    def _on_rezyser(self, _event: wx.Event) -> None:
        self._switch_tool("Reżyser")

    def _on_poliglota(self, _event: wx.Event) -> None:
        self._switch_tool("Poliglota")

    def _on_konwerter(self, _event: wx.Event) -> None:
        self._switch_tool("Konwerter")

    def _on_exit(self, _event: wx.Event) -> None:
        self.Close()

    def _on_close(self, event: wx.CloseEvent) -> None:
        event.Skip()  # Pozwól wxPython zniszczyć okno w standardowy sposób


# ---------------------------------------------------------------------------
# Punkt wejścia
# ---------------------------------------------------------------------------
def main() -> None:
    app = wx.App(False)
    frame = MainFrame()  # noqa: F841  (frame jest trzymany przez wx.App)
    app.MainLoop()


if __name__ == "__main__":
    main()
