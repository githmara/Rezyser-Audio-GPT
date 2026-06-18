"""
Reżyser Audio GPT – główny plik aplikacji (wxPython).
Zastępuje Start.py (Streamlit). Punkt wejścia: python main.py

Wersja 13.1: cały widoczny dla użytkownika tekst pochodzi z
``dictionaries/pl/gui/ui.yaml`` poprzez moduł :mod:`i18n`. Hard-kodowane
stringi zostały zastąpione wywołaniami ``t("klucz", **parametry)``.
"""

import datetime
import os
import platform
import subprocess
import sys
import threading
import traceback
from pathlib import Path

import wx

import sciezki

import core_elevenlabs
import core_poliglota
import core_updater
import i18n
from gui_konwerter import KonwerterPanel
from gui_manager_regul import ManagerRegulPanel
from gui_opowiesci import OpowiesciPanel
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
ID_TOOL_OPOWIESCI  = wx.NewIdRef()   # Interaktywne Opowieści – nowość w 15.0
ID_EXIT            = wx.NewIdRef()
# Menu Pomoc (15.2): 3 podmenu otwierające docs/<rdzen>.<iso>.txt
# w domyślnym handlerze .txt. ISO wybierane wg języka interfejsu (i18n).
ID_HELP_MANUAL       = wx.NewIdRef()
ID_HELP_TALES        = wx.NewIdRef()
ID_HELP_DICTIONARIES = wx.NewIdRef()


# ---------------------------------------------------------------------------
# Konfiguracja użytkownika (wx.Config — cross-platform: rejestr Windows,
# plik INI na Linux, plist na macOS).
# ---------------------------------------------------------------------------
_NAZWA_APP_CONFIG  = "RezyserAudioGPT"
_KLUCZ_CONFIG_JEZYK = "/JezykInterfejsu"


# ---------------------------------------------------------------------------
# Globalny przechwytywacz nieobsłużonych wyjątków (od v17.0)
# ---------------------------------------------------------------------------
# Po migracji na PyInstaller (--windowed) aplikacja chodzi BEZ konsoli, więc
# nieobsłużony traceback leciał dotąd „donikąd" — end-user widział tylko nagłe
# zniknięcie okna, bez żadnej wskazówki co zgłosić. Instalujemy `sys.excepthook`,
# który: (1) dopisuje pełny traceback do `error_log.txt` w katalogu bazowym
# (obok exe), (2) pokazuje zwykłemu userowi czytelny dialog z prośbą o załączenie
# tego pliku do zgłoszenia (Issue) na GitHubie.
#
# Plik nazwy `error_log.txt` zaczyna się od stałego markera CRASH_MARKER — obieg
# „Z Południa na Północ" (`.github/scripts/issue_intake_sami.py`) rozpoznaje po
# nim (oraz po sygnaturze `Traceback (most recent call last)`) zgłoszenie-crash i
# POMIJA detekcję języka Lingua (surowy traceback myli detektor n-gramowy).
CRASH_MARKER = "=== REŻYSER AUDIO GPT — CRASH REPORT ==="
_PLIK_LOGU_BLEDOW = "error_log.txt"


def _zapisz_log_bledu(typ, wartosc, tb) -> str | None:
    """Dopisuje sformatowany traceback do error_log.txt. Zwraca ścieżkę lub None.

    Nigdy nie rzuca — to ostatnia linia obrony; wyjątek przy logowaniu wyjątku
    nie może zamaskować oryginalnego błędu ani wywrócić handlera.
    """
    try:
        sciezka = os.path.join(sciezki.KATALOG_BAZOWY_STR, _PLIK_LOGU_BLEDOW)
        wersja = getattr(i18n, "NUMER_WERSJI", "?")
        stempel = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        slad = "".join(traceback.format_exception(typ, wartosc, tb))
        wpis = (
            f"{CRASH_MARKER}\n"
            f"Wersja / Version: {wersja}\n"
            f"Data / Time: {stempel}\n"
            f"Platforma / Platform: {platform.platform()}\n"
            f"{'-' * 60}\n"
            f"{slad}\n"
            f"{'=' * 60}\n\n"
        )
        # Dopisujemy (a nie nadpisujemy) — kolejne crashe w jednej sesji
        # zostają zachowane; user załącza cały plik.
        with open(sciezka, "a", encoding="utf-8") as fh:
            fh.write(wpis)
        return sciezka
    except Exception:  # noqa: BLE001 — logowanie błędu nie może rzucić
        return None


def _pokaz_dialog_crash(sciezka_logu: str | None) -> None:
    """Pokazuje zwykłemu userowi dialog o crashu (bilingual PL+EN).

    CELOWO NIE korzysta z i18n/`t()`: handler crashy musi działać nawet gdy to
    właśnie i18n (wczytywanie YAML, format) był przyczyną wyjątku. Stały tekst
    PL+EN to świadomy wyjątek od reguły „etykiety w ui.yaml" — odporność handlera
    ostatniej szansy jest tu ważniejsza niż lokalizacja. URL Issues budujemy z
    `core_updater` (single source of truth dla repo).
    """
    url_issues = (
        f"https://github.com/{core_updater.GITHUB_USER}"
        f"/{core_updater.GITHUB_REPO}/issues/new"
    )
    info_plik = sciezka_logu or _PLIK_LOGU_BLEDOW
    tresc = (
        "Aplikacja napotkała nieoczekiwany błąd i może działać niestabilnie.\n\n"
        f"Szczegóły zapisaliśmy w pliku:\n{info_plik}\n\n"
        "Pomóż go naprawić: utwórz nowe zgłoszenie (Issue) na GitHubie i ZAŁĄCZ "
        "ten plik (albo wklej jego treść):\n"
        f"{url_issues}\n\n"
        "----------------------------------------------------------------\n\n"
        "[EN] The application encountered an unexpected error and may be "
        "unstable.\n\n"
        f"Details were saved to the file:\n{info_plik}\n\n"
        "Please help fix it: open a new GitHub Issue and ATTACH that file "
        "(or paste its contents):\n"
        f"{url_issues}"
    )
    tytul = "Reżyser Audio GPT — błąd / error"

    # Preferujemy wx (spójny wygląd, dostępny dla NVDA), ale gdy crash nastąpił
    # PRZED utworzeniem wx.App, wx.MessageBox by sam rzucił — wtedy natywny
    # MessageBox WinAPI przez ctypes. Zamrożony release jest Windows-only
    # (build_release + installer.iss), więc tam `ctypes.windll` jest zawsze
    # dostępne; przy uruchomieniu ZE ŹRÓDŁA na Linux/macOS (`setup_dev.sh`)
    # `windll` nie istnieje — wtedy pomijamy fallback (log + traceback na stderr
    # z poprzedniego hooka i tak poszły), zamiast polegać na łapaniu wyjątku.
    try:
        if wx.GetApp() is not None:
            wx.MessageBox(tresc, tytul, wx.OK | wx.ICON_ERROR)
            return
    except Exception:  # noqa: BLE001 — spadamy do natywnego fallbacku
        pass
    if sys.platform == "win32":
        try:
            import ctypes  # noqa: PLC0415
            ctypes.windll.user32.MessageBoxW(0, tresc, tytul, 0x10)  # MB_ICONERROR
        except Exception:  # noqa: BLE001 — nie mamy już jak pokazać dialogu
            pass


def _zainstaluj_obsluge_bledow() -> None:
    """Instaluje globalny `sys.excepthook` (log do pliku + dialog dla usera).

    wxPython (Phoenix) przepuszcza nieobsłużone wyjątki z handlerów zdarzeń do
    `sys.excepthook`, więc jeden hook pokrywa zarówno crash startowy (przed
    MainLoop), jak i wyjątek w obsłudze zdarzenia. `KeyboardInterrupt` i
    `SystemExit` przepuszczamy do domyślnego zachowania (czyste zamknięcie,
    nie „crash").
    """
    poprzedni_hook = sys.excepthook

    def _hook(typ, wartosc, tb):
        if issubclass(typ, (KeyboardInterrupt, SystemExit)):
            poprzedni_hook(typ, wartosc, tb)
            return
        sciezka_logu = _zapisz_log_bledu(typ, wartosc, tb)
        # Zachowujemy domyślne zachowanie (traceback na stderr) — w trybie dev
        # z konsolą deweloper nadal widzi ślad; w paczce windowed stderr jest
        # None, więc to no-op, a użytkownik dostaje dialog niżej.
        try:
            poprzedni_hook(typ, wartosc, tb)
        except Exception:  # noqa: BLE001
            pass
        _pokaz_dialog_crash(sciezka_logu)

    sys.excepthook = _hook


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
        self._run_elevenlabs_check()

    # ------------------------------------------------------------------
    # Właściwość: bezwzględna ścieżka do golden_key.env
    # ------------------------------------------------------------------
    @property
    def _env_path(self) -> str:
        """Ścieżka do golden_key.env w katalogu bazowym (obok exe / w roocie repo)."""
        return os.path.join(sciezki.KATALOG_BAZOWY_STR, self.ENV_FILENAME)

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

        # --- Sekcja: Postprodukcja audio (ElevenLabs) — opcjonalna (v16.0) ---
        # Klucz ELEVENLABS_API_KEY jest opcjonalny; brak = stan informacyjny,
        # nie błąd. Status liczony niezależnie od głównego System Check (Anthropic).
        main_sizer.Add(
            wx.StaticLine(self), flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=8
        )

        heading_el = wx.StaticText(self, label=t("home.heading_elevenlabs"))
        font_el = heading_el.GetFont()
        font_el.SetPointSize(13)
        font_el.MakeBold()
        heading_el.SetFont(font_el)
        main_sizer.Add(heading_el, flag=wx.TOP | wx.LEFT | wx.RIGHT, border=16)

        self._el_status_lbl = wx.TextCtrl(
            self,
            value=t("home.checking"),
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.NO_BORDER,
        )
        self._el_status_lbl.SetBackgroundColour(self.GetBackgroundColour())
        main_sizer.Add(self._el_status_lbl, flag=wx.ALL | wx.EXPAND, border=16)

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
        tools_btn_sizer.Add(self._btn_open_manager)

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

        # Walidacja klucza Anthropic — JEDYNY wymagany po konsolidacji v18.x
        # (narracja Reżysera, Opowieści, Poliglota, postprodukcja tytułów: wszystko
        # na Claude). Format `sk-ant-`. OpenAI usunięty z całego projektu.
        wynik = self._diagnoza_klucza(
            zawartosc, "ANTHROPIC_API_KEY", "sk-ant-",
            "home.ant_err_struktura", "home.ant_err_format", "home.ant_err_zbyt_krotki",
        )
        if wynik is None:
            self._set_status(t("home.ok_klucz_wykryty"), kind="ok")
            return
        klucz_i18n, kwargs, kind = wynik
        self._set_status(t(klucz_i18n, **kwargs), kind=kind)
        self._show_action_btn("open", t("home.btn_open"))

    def _diagnoza_klucza(
        self,
        zawartosc:    str,
        nazwa_zmiennej: str,
        prefix:        str,
        k_struktura:   str,
        k_format:      str,
        k_zbyt_krotki: str,
    ) -> tuple[str, dict, str] | None:
        """Waliduje pojedynczy WYMAGANY klucz w treści golden_key.env.

        Zwraca ``None`` gdy klucz OK, inaczej krotkę ``(klucz_i18n, kwargs, kind)``
        do wyświetlenia. Funkcja pozostaje sparametryzowana (``nazwa_zmiennej``,
        ``prefix``, ``k_*``), choć po konsolidacji v18.x ma jednego wołającego
        (klucz Anthropic) — komunikaty generyczne (placeholder/cudzysłowy/spacje)
        wstrzykuje sama, specyficzne (struktura/format/zbyt krótki) podaje wołający.
        """
        if f"{nazwa_zmiennej}=" not in zawartosc:
            return (k_struktura, {}, "error")
        klucz_raw = zawartosc.split(f"{nazwa_zmiennej}=")[-1].split("\n")[0]
        klucz = klucz_raw.strip()
        if "TUTAJ_WKLEJ_SWOJ_KLUCZ" in klucz:
            return ("home.err_tekst_zastepczy", {}, "warning")
        if (klucz.startswith('"') and klucz.endswith('"')) or \
           (klucz.startswith("'") and klucz.endswith("'")):
            return ("home.err_cudzyslowy", {}, "error")
        if klucz_raw != klucz:
            return ("home.err_niedozwolone_znaki", {}, "error")
        if not klucz.startswith(prefix):
            return (k_format, {}, "error")
        if len(klucz) < self.MINIMUM_ZNAKOW_KLUCZA:
            return (
                k_zbyt_krotki,
                {"liczba_znakow": len(klucz),
                 "minimum_znakow": self.MINIMUM_ZNAKOW_KLUCZA},
                "warning",
            )
        return None

    # ------------------------------------------------------------------
    # Logika walidacji klucza ElevenLabs (opcjonalny — v16.0)
    # ------------------------------------------------------------------
    def _run_elevenlabs_check(self) -> None:
        """Diagnozuje opcjonalny klucz ElevenLabs i aktualizuje osobny status.

        Niezależny od głównego System Check (Anthropic): brak pliku lub brak zmiennej
        ``ELEVENLABS_API_KEY`` to stan informacyjny (feature wyłączony),
        nie błąd. Mapuje ``core_elevenlabs.STATUS_*`` na komunikat i18n.
        """
        env_path = self._env_path
        try:
            with open(env_path, "r", encoding="utf-8-sig") as fh:
                zawartosc = fh.read()
        except OSError:
            # Brak pliku golden_key.env → feature po prostu nieskonfigurowany.
            zawartosc = ""

        diag = core_elevenlabs.diagnoza_klucza(zawartosc)

        # status → (klucz i18n, rodzaj koloru)
        mapowanie = {
            core_elevenlabs.STATUS_BRAK:        ("home.el_brak",        "info"),
            core_elevenlabs.STATUS_PLACEHOLDER: ("home.el_placeholder", "warning"),
            core_elevenlabs.STATUS_CUDZYSLOWY:  ("home.el_cudzyslowy",  "error"),
            core_elevenlabs.STATUS_SPACJE:      ("home.el_spacje",      "error"),
            core_elevenlabs.STATUS_FORMAT:      ("home.el_format",      "error"),
            core_elevenlabs.STATUS_OK:          ("home.el_ok",          "ok"),
        }

        if diag.status == core_elevenlabs.STATUS_ZBYT_KROTKI:
            message = t(
                "home.el_zbyt_krotki",
                liczba_znakow=diag.liczba_znakow,
                minimum_znakow=core_elevenlabs.MINIMUM_ZNAKOW_KLUCZA,
            )
            kind = "warning"
        else:
            klucz_i18n, kind = mapowanie.get(diag.status, ("home.el_brak", "info"))
            message = t(klucz_i18n)

        self._apply_status(self._el_status_lbl, message, kind)

    # ------------------------------------------------------------------
    # Pomocnicze metody UI
    # ------------------------------------------------------------------
    _COLOUR_MAP = {
        "ok":      wx.Colour(0, 128, 0),    # zielony
        "warning": wx.Colour(180, 100, 0),  # pomarańczowy
        "error":   wx.Colour(180, 0, 0),    # czerwony
        "info":    wx.Colour(0, 90, 160),   # niebieski (stan neutralny/opcjonalny)
    }

    def _apply_status(self, lbl: wx.TextCtrl, message: str, kind: str) -> None:
        """Ustawia tekst i kolor na wskazanej etykiecie statusu (A11y: SetName)."""
        lbl.SetValue(message)
        # Ustawienie nazwy = NVDA odczyta komunikat po sfocusowaniu kontrolki
        lbl.SetName(message)
        lbl.SetForegroundColour(self._COLOUR_MAP.get(kind, self._COLOUR_MAP["ok"]))

    def _set_status(self, message: str, kind: str = "ok") -> None:
        """Ustawia tekst i kolor etykiety System Check (golden_key.env — klucz Anthropic).

        Args:
            message: Treść komunikatu widoczna w interfejsie.
            kind:    ``"ok"`` | ``"warning"`` | ``"error"`` | ``"info"``
        """
        self._apply_status(self._status_lbl, message, kind)

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
                    fh.write(
                        "ANTHROPIC_API_KEY=TUTAJ_WKLEJ_SWOJ_KLUCZ\n"
                        "\n"
                        "# Wymagany klucz Anthropic (sk-ant-…): zasila CAŁY silnik AI —\n"
                        "# narrację Reżysera (audiobook / teatr / burza), Opowieści,\n"
                        "# Poliglotę (tłumacz) i postprodukcję tytułów (konsolidacja v18.x).\n"
                        "\n"
                        "# Opcjonalnie — postprodukcja audio w ElevenLabs Studio (v16.0).\n"
                        "# Odkomentuj poniższą linię i wklej klucz typu sk_ "
                        "(z podkreślnikiem, nie sk-):\n"
                        "# ELEVENLABS_API_KEY=\n"
                    )
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

        # Otwórz plik w domyślnym edytorze tekstu (cross-platform helper)
        try:
            sciezki.otworz_w_systemie(env_path)
        except Exception:  # noqa: BLE001
            wx.MessageBox(
                t("home.blad_otwarcia_pliku_tresc", sciezka_pliku=env_path),
                t("home.blad_otwarcia_pliku_tytul"),
                wx.OK | wx.ICON_INFORMATION,
                self,
            )


# ---------------------------------------------------------------------------
# Dialog auto-aktualizacji (od v15.2.8 — ostrzeżenie o dictionaries/)
# ---------------------------------------------------------------------------
class DialogAktualizacji(wx.Dialog):
    """Dialog proponujący aktualizację z ostrzeżeniem o nadpisaniu dictionaries/.

    Wprowadzony w v15.2.8 po bug-issue #13 (utrata 6-miesięcznych modyfikacji
    w dictionaries/it/akcenty/*.yaml po update'cie do v15.2.5). Stary wx.MessageBox
    YES_NO nie ostrzegał inline — manual v15.2.5+ ostrzega, ale user czytał stary
    v15.2.4 manual w momencie decyzji o update. Krytyczne info o utracie danych
    MUSI być w samym dialogu, nie tylko w manualu.

    Przyciski (A11y kolejność lewy→prawy + akceleratory z kluczy ui.yaml):
      - Pobierz (default, ID_YES + jawny EndModal) — Enter/klik zamyka z ID_YES
      - Pokaż changelog / Otwórz folder dictionaries / Szczegóły online —
        akcje poboczne, NIE zamykają dialogu
      - Anuluj (ID_CANCEL) — wxDialog auto-domyka + mapuje na Escape (A11y)
    """

    def __init__(self, parent, info_aktualizacji):
        super().__init__(
            parent,
            title=t("updater.nowa_wersja_tytul"),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )

        self._dictionaries_path = os.path.join(
            sciezki.KATALOG_BAZOWY_STR,
            "dictionaries",
        )

        tresc_pelna = t(
            "updater.nowa_wersja_tresc",
            nowa_wersja=info_aktualizacji.wersja,
            aktualna_wersja=i18n.NUMER_WERSJI,
        )

        # v17.6: strona Release (html_url) do przycisku „Szczegóły online".
        self._url_release = getattr(info_aktualizacji, "url_release", "") or ""

        sizer = wx.BoxSizer(wx.VERTICAL)

        tresc_ctrl = wx.StaticText(self, label=tresc_pelna)
        tresc_ctrl.Wrap(560)
        sizer.Add(tresc_ctrl, proportion=1, flag=wx.ALL | wx.EXPAND, border=12)

        # v17.11: realny changelog NOWEJ wersji (`body` Release z API). Do v17.11
        # dialog pokazywał baked-in `co_nowego_tresc` opisujący wersję JUŻ
        # zainstalowaną (nagłówek nowej, treść starej — krytyczny bug). Teraz
        # surowy changelog zapisujemy do `docs/changelog.md` i otwieramy z
        # przycisku domyślnym edytorem (cross-platform). Body jest EN+PL — nota
        # podpowiada nie-PL/EN userowi, by przetłumaczył plik w module Poliglota
        # (Tłumacz AI) lub dowolnym tłumaczu/chatbocie. Świadoma decyzja o update.
        self._changelog = (getattr(info_aktualizacji, "changelog", "") or "").strip()
        self._nowa_wersja = info_aktualizacji.wersja
        if self._changelog:
            changelog_uwaga = wx.StaticText(self, label=t("updater.changelog_uwaga"))
            changelog_uwaga.Wrap(560)
            sizer.Add(changelog_uwaga, flag=wx.LEFT | wx.RIGHT | wx.TOP, border=12)

        if self._url_release:
            uwaga_ctrl = wx.StaticText(self, label=t("updater.co_nowego_online_pl"))
            uwaga_ctrl.Wrap(560)
            sizer.Add(uwaga_ctrl, flag=wx.LEFT | wx.RIGHT | wx.BOTTOM, border=12)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        # Etykieta zależna od trybu: frozen → instalator .exe; źródło (dev /
        # non-Windows) → kod źródłowy ZIP (bez dodatkowej instalacji). Sam dialog
        # jest identyczny niezależnie od sposobu uruchomienia (decyzja v17.11) —
        # różni się TYLKO cel pobierania (obsłużony w `_start_pobieranie`).
        label_pobierz = (
            t("updater.btn_pobierz") if getattr(sys, "frozen", False)
            else t("updater.btn_pobierz_zrodlo")
        )
        self._btn_pobierz = wx.Button(self, wx.ID_YES, label_pobierz)
        self._btn_pobierz.SetDefault()
        # JAWNY EndModal — wxDialog auto-domyka tylko ID_OK/ID_CANCEL; dla ID_YES
        # poleganie na auto-handlingu jest zawodne (klik myszką potrafił nie
        # zamknąć dialogu). Bind gwarantuje zamknięcie z ID_YES niezależnie od tego.
        self._btn_pobierz.Bind(wx.EVT_BUTTON, lambda _e: self.EndModal(wx.ID_YES))

        self._btn_otworz = wx.Button(
            self, wx.ID_ANY, t("updater.btn_otworz_dictionaries")
        )
        self._btn_otworz.Bind(wx.EVT_BUTTON, self._on_otworz_folder)

        # ID_CANCEL (NIE ID_NO): wxDialog domyka go automatycznie i mapuje na
        # Escape (A11y). Do v17.11 był ID_NO — wxDialog NIE auto-domyka ID_NO,
        # więc „Anuluj" nie robił nic (zamykało tylko Alt+F4). Reszta dialogów
        # aplikacji od dawna używa ID_CANCEL — to był jedyny odstający dialog.
        self._btn_anuluj = wx.Button(self, wx.ID_CANCEL, t("updater.btn_anuluj"))

        btn_sizer.Add(self._btn_pobierz, flag=wx.ALL, border=6)
        # „Pokaż changelog" — zapis docs/changelog.md + otwarcie (tylko gdy mamy body).
        if self._changelog:
            self._btn_changelog = wx.Button(
                self, wx.ID_ANY,
                t("updater.btn_changelog", nowa_wersja=info_aktualizacji.wersja),
            )
            self._btn_changelog.Bind(wx.EVT_BUTTON, self._on_pokaz_changelog)
            btn_sizer.Add(self._btn_changelog, flag=wx.ALL, border=6)
        btn_sizer.Add(self._btn_otworz, flag=wx.ALL, border=6)
        # „Szczegóły online" tylko gdy znamy URL strony Release.
        if self._url_release:
            self._btn_szczegoly = wx.Button(
                self, wx.ID_ANY, t("updater.btn_szczegoly_online")
            )
            self._btn_szczegoly.Bind(wx.EVT_BUTTON, self._on_szczegoly_online)
            btn_sizer.Add(self._btn_szczegoly, flag=wx.ALL, border=6)
        btn_sizer.Add(self._btn_anuluj, flag=wx.ALL, border=6)

        sizer.Add(btn_sizer, flag=wx.ALIGN_CENTER | wx.ALL, border=6)

        self.SetSizerAndFit(sizer)
        self.SetMinSize((600, -1))
        self._btn_pobierz.SetFocus()

    def _on_pokaz_changelog(self, _event):
        """Zapisuje surowy changelog NOWEJ wersji do docs/changelog.md i otwiera go.

        Plik `.md` (rozszerzenie celowo — czytelne, edytor je otworzy) user może
        wczytać do modułu Poliglota (Tłumacz AI) albo dowolnego tłumacza/chatbota,
        jeśli nie zna PL/EN. Dialog pozostaje otwarty; po side-effekcie otwarcia
        przywracamy fokus na „Pobierz" (ten sam wzorzec co `_on_otworz_folder`)."""
        plik = sciezki.KATALOG_BAZOWY / "docs" / "changelog.md"
        try:
            plik.parent.mkdir(parents=True, exist_ok=True)
            naglowek = t("updater.changelog_naglowek", nowa_wersja=self._nowa_wersja)
            plik.write_text(naglowek + "\n\n" + self._changelog + "\n",
                            encoding="utf-8")
            sciezki.otworz_w_systemie(plik)
        except Exception as exc:  # noqa: BLE001
            wx.MessageBox(
                t("updater.changelog_blad", sciezka=str(plik), tresc_bledu=str(exc)),
                t("updater.blad_pobierania_tytul"),
                wx.OK | wx.ICON_ERROR,
                self,
            )
        wx.CallAfter(self._btn_pobierz.SetFocus)

    def _on_otworz_folder(self, _event):
        """Cross-platform open dictionaries/ folder; dialog pozostaje otwarty.

        Od v15.2.9 (re: #14): po side-effect operacji otwarcia Eksploratora /
        Findera / xdg-open, fokus systemowy przechodzi na nowe top-level okno
        zewnętrznej aplikacji. Gdy user zamyka tę aplikację (Alt+F4),
        Windows/macOS/Linux zwraca fokus do naszego procesu, ale wxPython nie
        gwarantuje że przekaże fokus konkretnemu widget'owi dialogu — może
        wylądować w nikt'sland (NVDA milczy, user nie wie gdzie jest). Fix:
        wx.CallAfter wstawia ponowne SetFocus na default button (Pobierz) DO
        KOLEJKI EVENT LOOP, więc wykonuje się PO bieżącym handlerze i po
        ewentualnym domknięciu side-effect przez OS. Wzorzec znany w
        NVDA-wxPython community jako „fokus-anker-muster nach side-effect".
        """
        try:
            sciezki.otworz_w_systemie(self._dictionaries_path)
        except Exception as exc:  # noqa: BLE001
            wx.MessageBox(
                t("updater.blad_otworz_folder",
                  sciezka=self._dictionaries_path,
                  tresc_bledu=str(exc)),
                t("updater.blad_pobierania_tytul"),
                wx.OK | wx.ICON_ERROR,
                self,
            )
        # Restoration fokusu działa OBU ścieżkach (sukces + błąd MessageBox),
        # bo MessageBox też jest side-effect dialogiem — po jego zamknięciu
        # fokus default-na-dialog wraca, ale nasz dialog może go nie odzyskać
        # spod parent frame'a. wx.CallAfter() umieszcza SetFocus po wszystkich
        # bieżących events w kolejce — bezpieczna kolejność.
        wx.CallAfter(self._btn_pobierz.SetFocus)

    def _on_szczegoly_online(self, _event):
        """Otwiera stronę Release na GitHubie w domyślnej przeglądarce; dialog
        pozostaje otwarty (jak „Otwórz folder dictionaries"). Treść strony jest
        po polsku — uprzedza o tym `co_nowego_online_pl` w samym dialogu."""
        if self._url_release:
            wx.LaunchDefaultBrowser(self._url_release)
        wx.CallAfter(self._btn_pobierz.SetFocus)


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
        self._start_update_check()

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
        menu_tools.Append(
            ID_TOOL_OPOWIESCI,
            t("main.menu.opowiesci"),
            t("main.menu_status.opowiesci"),
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

        # --- Menu: Pomoc (15.2) — otwiera docs/<rdzen>.<iso>.txt --------
        # ISO wybierany z i18n.aktualny_jezyk(), rdzeń (manual/tales/
        # dictionaries) określa _on_pomoc_* handler. Pliki otwierane przez
        # `os.startfile` (Windows shell association — Notatnik / VS Code
        # / co użytkownik ma skojarzone z .txt).
        menu_help = wx.Menu()
        menu_help.Append(
            ID_HELP_MANUAL,
            t("main.menu.pomoc_manual"),
            t("main.menu_status.pomoc_manual"),
        )
        menu_help.Append(
            ID_HELP_TALES,
            t("main.menu.pomoc_tales"),
            t("main.menu_status.pomoc_tales"),
        )
        menu_help.Append(
            ID_HELP_DICTIONARIES,
            t("main.menu.pomoc_dictionaries"),
            t("main.menu_status.pomoc_dictionaries"),
        )
        menubar.Append(menu_help, t("main.menu.pomoc"))

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

        self._btn_opowiesci = wx.Button(
            self._root_panel,
            id=ID_TOOL_OPOWIESCI,
            label=t("main.btn.opowiesci"),
        )
        self._btn_opowiesci.SetToolTip(t("main.tooltip.opowiesci"))

        btn_sizer.Add(self._btn_rezyser,   flag=wx.ALL, border=4)
        btn_sizer.Add(self._btn_poliglota, flag=wx.ALL, border=4)
        btn_sizer.Add(self._btn_konwerter, flag=wx.ALL, border=4)
        btn_sizer.Add(self._btn_manager,   flag=wx.ALL, border=4)
        btn_sizer.Add(self._btn_opowiesci, flag=wx.ALL, border=4)

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
        self._btn_manager.MoveBeforeInTabOrder(self._btn_opowiesci)

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
        self.Bind(wx.EVT_MENU, self._on_opowiesci,  id=ID_TOOL_OPOWIESCI)
        self.Bind(wx.EVT_MENU, self._on_exit,       id=ID_EXIT)

        # Menu: Pomoc — każde podmenu wywołuje `_otworz_dokument` z innym
        # rdzeniem nazwy pliku w docs/. ISO ustalane wewnątrz funkcji.
        self.Bind(wx.EVT_MENU, lambda evt: self._otworz_dokument("manual"),
                  id=ID_HELP_MANUAL)
        self.Bind(wx.EVT_MENU, lambda evt: self._otworz_dokument("tales"),
                  id=ID_HELP_TALES)
        self.Bind(wx.EVT_MENU, lambda evt: self._otworz_dokument("dictionaries"),
                  id=ID_HELP_DICTIONARIES)

        # Menu: Język interfejsu — jeden handler dla wszystkich radio items;
        # rozróżnienie kodu ISO przez `event.GetId()` w `_on_zmien_jezyk`.
        for menu_id in self._jezyk_menu_ids:
            self.Bind(wx.EVT_MENU, self._on_zmien_jezyk, id=menu_id)

        # Przyciski (te same identyfikatory → te same handlery przez EVT_BUTTON)
        self.Bind(wx.EVT_BUTTON, self._on_rezyser,   id=ID_TOOL_REZYSER)
        self.Bind(wx.EVT_BUTTON, self._on_poliglota, id=ID_TOOL_POLIGLOTA)
        self.Bind(wx.EVT_BUTTON, self._on_konwerter, id=ID_TOOL_KONWERTER)
        self.Bind(wx.EVT_BUTTON, self._on_manager,   id=ID_TOOL_MANAGER)
        self.Bind(wx.EVT_BUTTON, self._on_opowiesci, id=ID_TOOL_OPOWIESCI)

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
        n_opowiesci = t("main.nazwy_narzedzi.opowiesci")

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
        elif name == n_opowiesci:
            self._current_panel = OpowiesciPanel(self._root_panel)
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
            t("main.nazwy_narzedzi.opowiesci"): self._btn_opowiesci,
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

    def _on_opowiesci(self, _event: wx.Event) -> None:
        self._switch_tool(t("main.nazwy_narzedzi.opowiesci"))

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

    # ------------------------------------------------------------------
    # Menu Pomoc: otwieranie dokumentacji w domyślnym handlerze .txt
    # ------------------------------------------------------------------
    def _otworz_dokument(self, rdzen: str) -> None:
        """Otwiera plik `docs/<rdzen>.<iso>.txt` przez Windows shell association.

        Args:
            rdzen: ``"manual"`` | ``"tales"`` | ``"dictionaries"`` —
                rdzeń nazwy pliku w ``docs/`` (po refaktorze 15.2 user-facing
                pliki mają konwencję anglojęzyczną).

        ISO języka brany z ``i18n.aktualny_jezyk()`` — czyli plik otworzy
        się w tym języku, w którym aktualnie używasz GUI. Jeśli plik nie
        istnieje (uszkodzona paczka / brak docs/ w trybie deweloperskim
        przed odpaleniem `generuj_dokumentacje.py`), wyświetla MessageBox
        z lokalizowanym komunikatem.
        """
        iso = i18n.aktualny_jezyk()
        sciezka = sciezki.KATALOG_BAZOWY / "docs" / f"{rdzen}.{iso}.txt"
        if not sciezka.is_file():
            wx.MessageBox(
                t("main.pomoc.brak_pliku", sciezka=str(sciezka)),
                t("main.pomoc.blad_tytul"),
                wx.OK | wx.ICON_WARNING,
                self,
            )
            return
        # Otwórz docs/<rdzen>.<iso>.txt domyślną aplikacją (cross-platform helper).
        # Wcześniej był tu goły `os.startfile` z komentarzem „Windows-only" —
        # niespójne ze źródłem chodzącym też na Linux/macOS (`setup_dev.sh`).
        try:
            sciezki.otworz_w_systemie(sciezka)
        except Exception:  # noqa: BLE001
            wx.MessageBox(
                t("main.pomoc.brak_pliku", sciezka=str(sciezka)),
                t("main.pomoc.blad_tytul"),
                wx.OK | wx.ICON_WARNING,
                self,
            )

    # ------------------------------------------------------------------
    # Auto-aktualizacja
    # ------------------------------------------------------------------

    def _start_update_check(self) -> None:
        """Odpytuje GitHub API w wątku tła — nie blokuje MainLoop."""
        threading.Thread(target=self._w_watku_sprawdz, daemon=True).start()

    def _w_watku_sprawdz(self) -> None:
        """Wątek tła: jeśli jest nowsza wersja, zgłasza to do głównego wątku."""
        info = core_updater.sprawdz_aktualizacje()
        if info:
            wx.CallAfter(self._on_aktualizacja_dostepna, info)

    def _on_aktualizacja_dostepna(self, info: core_updater.UpdateInfo) -> None:
        """Główny wątek: rozgałęzia na dwa tryby w zależności od środowiska.

        Aplikacja zamrożona PyInstallerem (``sys.frozen``) → paczka Inno Setup →
        oferuj pobranie .exe. Uruchomienie ze źródła (dev) → informuj o ręcznej
        aktualizacji (sklonuj repo lub pobierz archiwum „Source code" z Releases).

        Od v17.0: detekcja oparta o ``sys.frozen`` zamiast obecności
        ``runtime/python.exe``. Przed migracją na PyInstaller paczka wożona była
        z przenośnym ``runtime/python.exe``, którego obecność rozróżniała paczkę
        od dev-a. Po migracji interpreter jest wbudowany w bundla, a folder
        ``runtime/`` przechowuje już tylko metadane projektów — więc jego
        obecność nie świadczy o tym, czy chodzimy z paczki. Jedynym wiarygodnym
        sygnałem „to skompilowana paczka" jest ``sys.frozen``.
        """
        # Ten sam dialog niezależnie od sposobu uruchomienia (v17.11) — wygląd nie
        # zależy już od frozen/źródło. Rozgałęzienie celu pobierania jest dopiero
        # w `_start_pobieranie` (instalator .exe vs kod źródłowy ZIP).
        dlg = DialogAktualizacji(self, info)
        odpowiedz = dlg.ShowModal()
        dlg.Destroy()
        if odpowiedz == wx.ID_YES:
            self._start_pobieranie(info)

    def _start_pobieranie(self, info: core_updater.UpdateInfo) -> None:
        """Główny wątek: rozgałęzia pobieranie wg trybu uruchomienia.

        frozen (paczka PyInstaller) → pobranie instalatora .exe z paskiem postępu
        i automatyczne uruchomienie. Źródło (dev / non-Windows) → otwarcie w
        przeglądarce linku do kodu źródłowego (ZIP) danej wersji — bez instalatora
        i bez dodatkowej instalacji (user rozpakowuje nad swoim klonem)."""
        if not getattr(sys, "frozen", False):
            url = info.url_zrodla or info.url_release
            if url:
                wx.LaunchDefaultBrowser(url)
            return
        self._progress_dlg = wx.ProgressDialog(
            t("updater.pobieranie_tytul", nowa_wersja=info.wersja),
            t("updater.pobieranie_tresc", nazwa_pliku=info.nazwa_pliku),
            maximum=100,
            parent=self,
            style=wx.PD_APP_MODAL | wx.PD_ELAPSED_TIME | wx.PD_REMAINING_TIME,
        )
        threading.Thread(
            target=self._w_watku_pobierz, args=(info,), daemon=True,
        ).start()

    def _w_watku_pobierz(self, info: core_updater.UpdateInfo) -> None:
        """Wątek tła: pobiera instalator; odświeża dialog przez CallAfter."""
        try:
            sciezka = core_updater.pobierz_instalator(
                info,
                callback=lambda pobrane, total: wx.CallAfter(
                    self._on_postep_pobierania, pobrane, total
                ),
            )
            wx.CallAfter(self._on_pobieranie_zakonczone, sciezka)
        except Exception as exc:  # noqa: BLE001
            wx.CallAfter(self._on_pobieranie_blad, exc)

    def _on_postep_pobierania(self, pobrane: int, total: int) -> None:
        """Główny wątek: odświeża pasek postępu (A11y: NVDA czyta % automatycznie)."""
        if not getattr(self, "_progress_dlg", None):
            return
        if total > 0:
            # max=99 — nie wyzwala auto-hide przed naszym jawnym Destroy()
            self._progress_dlg.Update(min(int(pobrane * 100 / total), 99))
        else:
            self._progress_dlg.Pulse()

    def _on_pobieranie_zakonczone(self, sciezka) -> None:
        """Główny wątek: zamknij dialog, uruchom instalator, wyjdź z aplikacji."""
        if getattr(self, "_progress_dlg", None):
            self._progress_dlg.Destroy()
            self._progress_dlg = None

        wx.MessageBox(
            t("updater.instalacja_tresc"),
            t("updater.instalacja_tytul"),
            wx.OK | wx.ICON_INFORMATION,
            self,
        )
        try:
            subprocess.Popen([str(sciezka)])
        except Exception as exc:  # noqa: BLE001
            wx.MessageBox(
                t(
                    "updater.blad_uruchomienia_tresc",
                    sciezka_pliku=str(sciezka),
                    tresc_bledu=str(exc),
                ),
                t("updater.blad_uruchomienia_tytul"),
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return
        wx.GetApp().ExitMainLoop()

    def _on_pobieranie_blad(self, exc: Exception) -> None:
        """Główny wątek: zamknij dialog i pokaż komunikat błędu."""
        if getattr(self, "_progress_dlg", None):
            self._progress_dlg.Destroy()
            self._progress_dlg = None
        wx.MessageBox(
            t("updater.blad_pobierania_tresc", tresc_bledu=str(exc)),
            t("updater.blad_pobierania_tytul"),
            wx.OK | wx.ICON_ERROR,
            self,
        )


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
    # Handler crashy instalujemy NAJPIERW — łapie też wyjątki z kroków 1-4
    # (np. uszkodzona paczka dictionaries przy starcie), zanim w ogóle powstanie
    # okno. Dla crashy przed `wx.App` dialog leci natywnym MessageBoxem WinAPI.
    _zainstaluj_obsluge_bledow()

    app = wx.App(False)
    kod_jezyka = _wybierz_jezyk_startowy()
    i18n.ustaw_jezyk(kod_jezyka)

    frame = MainFrame()  # noqa: F841  (frame jest trzymany przez wx.App)
    app.MainLoop()


if __name__ == "__main__":
    main()
