"""
gui_poliglota.py – Panel modułu „Poliglota AI".

Zastępuje pages/2_Poliglota.py (Streamlit).
Dziedziczy po wx.Panel; podpinany do MainFrame z main.py.

Funkcjonalność:
    - Wczytywanie pliku .txt / .html / .htm / .docx
    - Tryb Tłumacza AI (OpenAI gpt-4o) – wywołania w wątku tła,
      wyniki przekazywane przez wx.CallAfter (brak GUI freeze)
    - Tryb Reżysera – darmowe fonetyczne skrypty Pythona
    - Zapis do .docx / .html / .txt z tagiem lang=
    - Pasek postępu wx.Gauge + odczytywalne pole wynikowe (TE_READONLY)
"""

from __future__ import annotations

import json
import os
import re
import threading
from typing import Callable

import docx
from docx.oxml.ns import qn
from docx.oxml.shared import OxmlElement
from dotenv import load_dotenv
from langdetect import LangDetectException, detect
from num2words import num2words

import wx


# ---------------------------------------------------------------------------
# Stałe / słowniki
# ---------------------------------------------------------------------------
AKCENT_CHOICES = [
    "Żaden (Czyszczenie BEZ normalizacji liczb)",
    "Żaden (Czyszczenie Z normalizacją liczb)",
    "Islandzki (np. Guðrún / eSpeak)",
    "Angielski (np. Samantha / Mark / Zira / Hazel)",
    "Francuski (np. Thomas / Amelie / Julie)",
    "Niemiecki (np. Stefan / Markus / Katja / Hedda)",
    "Hiszpański (np. Jorge / Monica / Helena)",
    "Włoski (np. Alice / Luca / Elsa)",
    "Fiński (np. Satu / Mikko / Heidi)",
    "🔧 Naprawiacz Tagów (Tylko wstrzyknięcie kodu ISO)",
]

AKCENT_ISO = {
    "Angielski": "en",
    "Francuski": "fr",
    "Niemiecki": "de",
    "Hiszpa": "es",
    "Włoski": "it",
    "Fiński": "fi",
    "Islandzki": "is",
}


# ---------------------------------------------------------------------------
# Czyste funkcje fonetyczne (przeniesione 1:1 z 2_Poliglota.py)
# ---------------------------------------------------------------------------

def normalizuj_liczby(text: str) -> str:
    def zamien(match):
        try:
            return num2words(match.group(), lang="pl")
        except Exception:
            return match.group()
    return re.sub(r"\d+", zamien, text)


def sklej_pojedyncze_litery(text: str) -> str:
    return re.sub(r"(?i)\b([a-z])\s+", r"\1", text)


def usun_polskie_znaki(text: str) -> str:
    text = normalizuj_liczby(text)
    mapping = {
        "ą": "on", "ę": "en", "ł": "l", "ó": "u",
        "ś": "s", "ć": "c", "ń": "n", "ż": "z", "ź": "z",
        "Ą": "On", "Ę": "En", "Ł": "L", "Ó": "U",
        "Ś": "S", "Ć": "C", "Ń": "N", "Ż": "Z", "Ź": "Z",
    }
    for k, v in mapping.items():
        text = text.replace(k, v)
    return text


def akcent_islandzki(text: str) -> str:
    text = usun_polskie_znaki(text)
    text = text.replace("ch", "h").replace("Ch", "H")
    text = text.replace("cz", "ts").replace("Cz", "Ts")
    text = text.replace("sz", "s").replace("Sz", "S")
    text = text.replace("c", "ts").replace("C", "Ts")
    text = text.replace("w", "v").replace("W", "V")
    return sklej_pojedyncze_litery(text)


def akcent_wloski(text: str) -> str:
    text = usun_polskie_znaki(text)
    text = text.replace("y", "i").replace("Y", "I")
    text = text.replace("w", "v").replace("W", "V")
    return sklej_pojedyncze_litery(text)


def akcent_finski(text: str) -> str:
    text = usun_polskie_znaki(text)
    text = text.replace("ch", "h").replace("Ch", "H")
    text = text.replace("cz", "ts").replace("Cz", "Ts")
    text = text.replace("sz", "s").replace("Sz", "S")
    text = text.replace("rz", "r").replace("Rz", "R")
    text = text.replace("c", "ts").replace("C", "Ts")
    text = text.replace("w", "v").replace("W", "V")
    text = text.replace("b", "p").replace("B", "P")
    text = text.replace("d", "t").replace("D", "T")
    text = text.replace("g", "k").replace("G", "K")
    return sklej_pojedyncze_litery(text)


def akcent_angielski(text: str) -> str:
    text = usun_polskie_znaki(text)
    text = text.replace("szcz", "shch").replace("Szcz", "Shch").replace("SZCZ", "SHCH")
    text = text.replace("sz", "sh").replace("Sz", "Sh")
    text = text.replace("cz", "ch").replace("Cz", "Ch")
    text = text.replace("rz", "zh").replace("Rz", "Zh")
    text = text.replace("ch", "h").replace("Ch", "H")
    text = text.replace("w", "v").replace("W", "V")
    return sklej_pojedyncze_litery(text)


def akcent_francuski(text: str) -> str:
    text = usun_polskie_znaki(text)
    text = text.replace("ch", "sh").replace("Ch", "Sh")
    text = text.replace("sz", "sh").replace("Sz", "Sh")
    text = text.replace("cz", "tch").replace("Cz", "Tch")
    text = text.replace("rz", "j").replace("Rz", "J")
    text = text.replace("h", "").replace("H", "")
    text = text.replace("r", "gh").replace("R", "Gh")
    text = text.replace("w", "v").replace("W", "V")
    return sklej_pojedyncze_litery(text)


def akcent_niemiecki(text: str) -> str:
    text = usun_polskie_znaki(text)
    text = text.replace("sz", "sch").replace("Sz", "Sch")
    text = text.replace("cz", "tsch").replace("Cz", "Tsch")
    text = text.replace("rz", "rsch").replace("Rz", "Rsch")
    text = text.replace("w", "v").replace("W", "V")
    text = text.replace("v", "f").replace("V", "F")
    return sklej_pojedyncze_litery(text)


def akcent_hiszpanski(text: str) -> str:
    text = usun_polskie_znaki(text)
    text = text.replace("sz", "s").replace("Sz", "S")
    text = text.replace("cz", "ch").replace("Cz", "Ch")
    text = text.replace("rz", "r").replace("Rz", "R")
    text = text.replace("w", "b").replace("W", "B")
    text = text.replace("v", "b").replace("V", "B")
    return sklej_pojedyncze_litery(text)


def procesuj_z_ochrona_tagow(text: str, funkcja_akcentu: Callable[[str], str]) -> str:
    """Stosuje funkcję fonetyczną tylko do tekstu, pomijając tagi HTML."""
    parts = re.split(r"(<[^>]+>)", text)
    for i in range(0, len(parts), 2):
        parts[i] = funkcja_akcentu(parts[i])
    return "".join(parts)


def oczysc_tekst_tts(tekst: str, z_normalizacja: bool = True) -> str:
    if z_normalizacja:
        tekst = normalizuj_liczby(tekst)
    tekst = re.sub(r"[\*=]+", "", tekst)
    tekst = re.sub(r"^#+\s*", "", tekst, flags=re.MULTILINE)
    tekst = re.sub(r"\([^)]*\)", "", tekst)
    tekst = re.sub(r"\b(khh|hh|pff|ahh|ehh)\b[\.\s]*", "... ", tekst, flags=re.IGNORECASE)
    tekst = re.sub(r"(?i)[,\s]*z\s*wplecionymi\s*wdechami", "", tekst)
    tekst = re.sub(r"(?i)[,\s]*z\s*wdech(em|ami)", "", tekst)
    tekst = re.sub(r"^\s*,\s*", "", tekst, flags=re.MULTILINE)
    tekst = re.sub(r"([!\?\.])\s*,\s*", r"\1 ", tekst)
    tekst = re.sub(r",\s*\.\.\.", "...", tekst)
    tekst = re.sub(r"(?:\.\s*){4,}", "... ", tekst)
    tekst = re.sub(r"([!\?\.])\s*\.\.\.\s*", r"\1 ", tekst)
    tekst = re.sub(r"^\s*\.\.\.\s*", "", tekst, flags=re.MULTILINE)
    tekst = re.sub(r"\.\.\.([^\s\.])", r"... \1", tekst)
    tekst = re.sub(r" {2,}", " ", tekst)
    return tekst.strip()


# ---------------------------------------------------------------------------
# Klasa panelu głównego
# ---------------------------------------------------------------------------

class PoliglotaPanel(wx.Panel):
    """
    Panel modułu „Poliglota AI".

    Obsługuje dwa tryby pracy:
        - Tryb Tłumacza AI (wymaga golden_key.env z OPENAI_API_KEY)
        - Tryb Reżysera  (darmowe, lokalne reguły fonetyczne)

    Wywołania API OpenAI realizowane są w wątku tła (threading.Thread),
    a wyniki przekazywane do wątku GUI wyłącznie przez wx.CallAfter,
    co wyklucza tzw. GUI freeze.
    """

    TOOL_DESCRIPTION = (
        "Moduł Poliglota służy do nakładania twardych akcentów fonetycznych "
        "pod lokalne syntezatory mowy (NVDA/Vocalizer/eSpeak) oraz do "
        "tłumaczenia tekstów za pomocą AI (OpenAI gpt-4o).\n\n"
        "Obsługuje pliki: .txt, .html, .htm, .docx.\n"
        "Wynik zapisywany jest w tym samym katalogu co plik źródłowy."
    )

    ENV_FILENAME = "golden_key.env"

    def __init__(self, parent: wx.Window) -> None:
        super().__init__(parent, style=wx.TAB_TRAVERSAL)
        self.SetName("Panel Poligloty AI")

        # Stan wewnętrzny (odpowiednik st.session_state)
        self._file_content: str = ""
        self._file_ext: str = ""
        self._oryginalna_nazwa: str = "nieznany"
        self._plik_katalog: str = "."

        # Klient OpenAI (None jeśli brak golden_key.env)
        self._client = None
        self._api_dostepne: bool = False
        self._init_api()

        # Wątek tła (referencja, by nie uruchamiać drugiego)
        self._worker_thread: threading.Thread | None = None

        self._build_ui()
        self._bind_events()
        self._refresh_mode_ui()

        # Po ustabilizowaniu layoutu ustaw fokus na polu opisu modułu —
        # spójnie z pozostałymi panelami; NVDA odczyta opis narzędzia.
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

    # ------------------------------------------------------------------
    # Budowanie interfejsu
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # ── Nagłówek ────────────────────────────────────────────────────
        heading = wx.StaticText(self, label="🌍  Poliglota AI – Hybrydowe Studio Tłumaczeń")
        heading_font = heading.GetFont()
        heading_font.SetPointSize(16)
        heading_font.MakeBold()
        heading.SetFont(heading_font)

        # ── Opis narzędzia ───────────────────────────────────────────────
        self._description = wx.TextCtrl(
            self,
            value=self.TOOL_DESCRIPTION,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.NO_BORDER,
            name="Opis modułu Poliglota",
        )
        self._description.SetBackgroundColour(self.GetBackgroundColour())
        description = self._description   # alias dla Add() poniżej

        # ── Separator ────────────────────────────────────────────────────
        sep1 = wx.StaticLine(self)

        # ── Sekcja 1: Wczytywanie pliku ──────────────────────────────────
        lbl_section1 = wx.StaticText(self, label="1. Wczytywanie pliku źródłowego")
        font_s = lbl_section1.GetFont()
        font_s.SetPointSize(12)
        font_s.MakeBold()
        lbl_section1.SetFont(font_s)

        lbl_file = wx.StaticText(
            self,
            label="Nazwa lub pełna ścieżka pliku (.txt, .html, .htm, .docx):",
        )

        self._txt_file = wx.TextCtrl(
            self,
            style=wx.TE_PROCESS_ENTER,
            name="Pole ścieżki pliku źródłowego",
        )
        self._txt_file.SetHint("Wpisz ścieżkę do pliku lub wybierz przyciskiem Przeglądaj…")

        self._btn_browse = wx.Button(self, label="Przeglądaj…")
        self._btn_browse.SetToolTip("Otwiera systemowe okno wyboru pliku")

        file_row = wx.BoxSizer(wx.HORIZONTAL)
        file_row.Add(self._txt_file, proportion=1, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=6)
        file_row.Add(self._btn_browse, flag=wx.ALIGN_CENTER_VERTICAL)

        self._btn_load = wx.Button(self, label="Wczytaj plik do pamięci")
        self._btn_load.SetToolTip("Wczytuje zawartość wskazanego pliku do pamięci roboczej")

        self._btn_clear = wx.Button(self, label="Wyczyść pamięć")
        self._btn_clear.SetToolTip("Usuwa wczytaną treść, pozwala wybrać inny plik")
        self._btn_clear.Disable()

        load_row = wx.BoxSizer(wx.HORIZONTAL)
        load_row.Add(self._btn_load,  flag=wx.RIGHT, border=8)
        load_row.Add(self._btn_clear, flag=wx.RIGHT, border=0)

        # Status wczytanego pliku
        self._lbl_file_status = wx.TextCtrl(
            self,
            value="Brak wczytanego pliku.",
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.NO_BORDER,
        )
        self._lbl_file_status.SetBackgroundColour(self.GetBackgroundColour())
        self._lbl_file_status.SetName("Status wczytanego pliku")

        # ── Separator ────────────────────────────────────────────────────
        sep2 = wx.StaticLine(self)

        # ── Sekcja 2: Konfiguracja trybu pracy ──────────────────────────
        lbl_section2 = wx.StaticText(self, label="2. Konfiguracja Pracy")
        font_s2 = lbl_section2.GetFont()
        font_s2.SetPointSize(12)
        font_s2.MakeBold()
        lbl_section2.SetFont(font_s2)

        # Radio: tryb pracy
        self._rb_ai = wx.RadioButton(
            self,
            label="Tłumacz AI (OpenAI gpt-4o – wymaga klucza API, kosztuje kredyty)",
            style=wx.RB_GROUP,
            name="Tryb Tłumacza AI",
        )
        self._rb_rezyser = wx.RadioButton(
            self,
            label="Tryb Reżysera (darmowe skrypty fonetyczne Pythona)",
            name="Tryb Reżysera darmowy",
        )

        if not self._api_dostepne:
            self._rb_ai.Disable()
            self._rb_ai.SetLabel(
                "Tłumacz AI (wyłączony – brak poprawnego pliku golden_key.env)"
            )
            self._rb_rezyser.SetValue(True)
        else:
            self._rb_ai.SetValue(True)

        # ── Panel trybu AI: pole języka docelowego ───────────────────────
        self._pnl_ai = wx.Panel(self)
        pnl_ai_sizer = wx.BoxSizer(wx.VERTICAL)

        lbl_lang = wx.StaticText(
            self._pnl_ai,
            label="Język docelowy tłumaczenia (np. Fiński, Islandzki, Angielski, Arabski):",
        )
        self._txt_lang = wx.TextCtrl(
            self._pnl_ai,
            style=wx.TE_PROCESS_ENTER,
            name="Pole języka docelowego",
        )
        self._txt_lang.SetHint("Wpisz nazwę języka docelowego…")

        pnl_ai_sizer.Add(lbl_lang,         flag=wx.BOTTOM, border=4)
        pnl_ai_sizer.Add(self._txt_lang,   flag=wx.EXPAND)
        self._pnl_ai.SetSizer(pnl_ai_sizer)

        # ── Panel trybu Reżysera: ComboBox akcentów ──────────────────────
        self._pnl_rezyser = wx.Panel(self)
        pnl_rez_sizer = wx.BoxSizer(wx.VERTICAL)

        lbl_akcent = wx.StaticText(
            self._pnl_rezyser,
            label="Wybierz akcent lub tryb czyszczenia:",
        )
        self._combo_akcent = wx.ComboBox(
            self._pnl_rezyser,
            choices=AKCENT_CHOICES,
            style=wx.CB_READONLY,
            name="Lista akcentów i trybów czyszczenia",
        )
        self._combo_akcent.SetSelection(0)
        self._combo_akcent.SetToolTip(
            "Wybierz akcent fonetyczny lub tryb czyszczenia tekstu pod czytniki ekranu"
        )

        # Pole kodu ISO (widoczne tylko dla „Naprawiacz Tagów")
        self._lbl_iso = wx.StaticText(
            self._pnl_rezyser,
            label="Kod ISO języka (2 litery, np. en, fr, de):",
        )
        self._txt_iso = wx.TextCtrl(
            self._pnl_rezyser,
            name="Pole kodu ISO języka",
        )
        self._txt_iso.SetMaxLength(2)
        self._txt_iso.SetHint("np. en")
        self._lbl_iso.Hide()
        self._txt_iso.Hide()

        pnl_rez_sizer.Add(lbl_akcent,       flag=wx.BOTTOM, border=4)
        pnl_rez_sizer.Add(self._combo_akcent, flag=wx.EXPAND | wx.BOTTOM, border=8)
        pnl_rez_sizer.Add(self._lbl_iso,    flag=wx.BOTTOM, border=4)
        pnl_rez_sizer.Add(self._txt_iso,    flag=wx.EXPAND)
        self._pnl_rezyser.SetSizer(pnl_rez_sizer)

        # ── Separator ────────────────────────────────────────────────────
        sep3 = wx.StaticLine(self)

        # ── Sekcja 3: Przetwarzanie ──────────────────────────────────────
        lbl_section3 = wx.StaticText(self, label="3. Przetwarzanie")
        font_s3 = lbl_section3.GetFont()
        font_s3.SetPointSize(12)
        font_s3.MakeBold()
        lbl_section3.SetFont(font_s3)

        self._btn_process = wx.Button(self, label="Uruchom Przetwarzanie")
        self._btn_process.SetToolTip(
            "Uruchamia wybrane przetwarzanie i zapisuje wynik obok pliku źródłowego"
        )

        # Pasek postępu (widoczny tylko podczas pracy AI)
        self._gauge = wx.Gauge(self, range=100, style=wx.GA_HORIZONTAL | wx.GA_SMOOTH)
        self._gauge.SetValue(0)
        self._gauge.Hide()

        # Etykieta postępu (czytana przez NVDA)
        self._lbl_progress = wx.TextCtrl(
            self,
            value="",
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.NO_BORDER,
        )
        self._lbl_progress.SetBackgroundColour(self.GetBackgroundColour())
        self._lbl_progress.SetName("Status postępu przetwarzania")
        self._lbl_progress.Hide()

        # ── Separator ────────────────────────────────────────────────────
        sep4 = wx.StaticLine(self)

        # ── Sekcja 4: Wynik ──────────────────────────────────────────────
        lbl_section4 = wx.StaticText(self, label="4. Wynik (tylko do odczytu – nawiguj strzałkami)")
        font_s4 = lbl_section4.GetFont()
        font_s4.SetPointSize(12)
        font_s4.MakeBold()
        lbl_section4.SetFont(font_s4)

        self._txt_result = wx.TextCtrl(
            self,
            value="",
            style=wx.TE_MULTILINE | wx.TE_READONLY,
            name="Pole wynikowe – gotowy tekst",
        )
        self._txt_result.SetMinSize((-1, 200))
        self._txt_result.SetHint("Tutaj pojawi się przetworzona treść…")

        # ── Złożenie layoutu ─────────────────────────────────────────────
        BORDER = 12
        main_sizer.Add(heading,             flag=wx.ALL, border=BORDER)
        main_sizer.Add(description,         flag=wx.LEFT | wx.RIGHT | wx.BOTTOM, border=BORDER)
        main_sizer.Add(sep1,                flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=BORDER)
        main_sizer.Add(lbl_section1,        flag=wx.LEFT | wx.TOP | wx.RIGHT, border=BORDER)
        main_sizer.Add(lbl_file,            flag=wx.LEFT | wx.TOP | wx.RIGHT, border=BORDER)
        main_sizer.Add(file_row,            flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, border=8)
        main_sizer.Add(load_row,            flag=wx.LEFT | wx.TOP, border=BORDER)
        main_sizer.Add(self._lbl_file_status, flag=wx.EXPAND | wx.ALL, border=BORDER)
        main_sizer.Add(sep2,                flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=BORDER)
        main_sizer.Add(lbl_section2,        flag=wx.LEFT | wx.TOP | wx.RIGHT, border=BORDER)
        main_sizer.Add(self._rb_ai,         flag=wx.LEFT | wx.TOP, border=BORDER)
        main_sizer.Add(self._rb_rezyser,    flag=wx.LEFT | wx.TOP, border=BORDER)
        main_sizer.Add(self._pnl_ai,        flag=wx.EXPAND | wx.ALL, border=BORDER)
        main_sizer.Add(self._pnl_rezyser,   flag=wx.EXPAND | wx.ALL, border=BORDER)
        main_sizer.Add(sep3,                flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=BORDER)
        main_sizer.Add(lbl_section3,        flag=wx.LEFT | wx.TOP | wx.RIGHT, border=BORDER)
        main_sizer.Add(self._btn_process,   flag=wx.LEFT | wx.TOP | wx.BOTTOM, border=BORDER)
        main_sizer.Add(self._gauge,         flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=BORDER)
        main_sizer.Add(self._lbl_progress,  flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=BORDER)
        main_sizer.Add(sep4,                flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=BORDER)
        main_sizer.Add(lbl_section4,        flag=wx.LEFT | wx.TOP | wx.RIGHT, border=BORDER)
        main_sizer.Add(self._txt_result,    proportion=1, flag=wx.EXPAND | wx.ALL, border=BORDER)

        self.SetSizer(main_sizer)

    # ------------------------------------------------------------------
    # Podpięcie zdarzeń
    # ------------------------------------------------------------------
    def _bind_events(self) -> None:
        self._btn_browse.Bind(wx.EVT_BUTTON, self._on_browse)
        self._btn_load.Bind(wx.EVT_BUTTON, self._on_load)
        self._btn_clear.Bind(wx.EVT_BUTTON, self._on_clear)
        self._btn_process.Bind(wx.EVT_BUTTON, self._on_process)
        self._txt_file.Bind(wx.EVT_TEXT_ENTER, self._on_load)
        self._txt_lang.Bind(wx.EVT_TEXT_ENTER, self._on_process)
        self._rb_ai.Bind(wx.EVT_RADIOBUTTON, self._on_mode_change)
        self._rb_rezyser.Bind(wx.EVT_RADIOBUTTON, self._on_mode_change)
        self._combo_akcent.Bind(wx.EVT_COMBOBOX, self._on_akcent_change)

    # ------------------------------------------------------------------
    # Przeglądarka plików
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # Wczytywanie pliku
    # ------------------------------------------------------------------
    def _on_load(self, _event: wx.Event) -> None:
        if self._file_content:
            return  # plik już wczytany – ignoruj

        file_name = self._txt_file.GetValue().strip()
        if not file_name:
            wx.MessageBox(
                "Podaj nazwę lub ścieżkę pliku przed wczytaniem.",
                "Brak pliku",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            self._txt_file.SetFocus()
            return

        if not os.path.exists(file_name):
            wx.MessageBox(
                f"Nie znaleziono pliku:\n{file_name}",
                "Plik nie istnieje",
                wx.OK | wx.ICON_ERROR,
                self,
            )
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
                f"Błąd podczas odczytu pliku:\n{exc}",
                "Błąd odczytu",
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return

        self._oryginalna_nazwa = os.path.splitext(os.path.basename(file_name))[0]
        self._plik_katalog = os.path.dirname(os.path.abspath(file_name))

        znaki = len(self._file_content)
        status_msg = (
            f"Plik wczytany: {os.path.basename(file_name)}  ({znaki} znaków).\n"
            "Możesz teraz uruchomić przetwarzanie."
        )
        self._lbl_file_status.SetValue(status_msg)
        self._lbl_file_status.SetName(status_msg)
        self._lbl_file_status.SetForegroundColour(wx.Colour(0, 128, 0))

        # Zablokuj pole i przycisk wczytywania, odblokuj „wyczyść"
        self._txt_file.Disable()
        self._btn_browse.Disable()
        self._btn_load.Disable()
        self._btn_clear.Enable()
        # Powiadomienie dostępnościowe – NVDA odczyta dialog automatycznie
        wx.MessageBox(
            f"Wczytano plik: {os.path.basename(file_name)}\n({znaki} znaków).\n\n"
            "Możesz teraz skonfigurować tryb pracy i uruchomić przetwarzanie.",
            "Plik wczytany",
            wx.OK | wx.ICON_INFORMATION,
            self,
        )

    # ------------------------------------------------------------------
    # Czyszczenie pamięci
    # ------------------------------------------------------------------
    def _on_clear(self, _event: wx.Event) -> None:
        self._file_content = ""
        self._file_ext = ""
        self._oryginalna_nazwa = "nieznany"
        self._plik_katalog = "."

        self._txt_file.Enable()
        self._txt_file.SetValue("")
        self._btn_browse.Enable()
        self._btn_load.Enable()
        self._btn_clear.Disable()

        clear_msg = "Pamięć wyczyszczona. Możesz wczytać nowy plik."
        self._lbl_file_status.SetValue(clear_msg)
        self._lbl_file_status.SetName(clear_msg)
        self._lbl_file_status.SetForegroundColour(self.GetForegroundColour())

        self._txt_result.SetValue("")
        self._gauge.SetValue(0)
        self._gauge.Hide()
        self._lbl_progress.SetValue("")
        self._lbl_progress.Hide()
        self.Layout()

    # ------------------------------------------------------------------
    # Zmiana trybu pracy
    # ------------------------------------------------------------------
    def _on_mode_change(self, _event: wx.Event) -> None:
        self._refresh_mode_ui()

    def _refresh_mode_ui(self) -> None:
        ai_mode = self._api_dostepne and self._rb_ai.GetValue()
        self._pnl_ai.Show(ai_mode)
        self._pnl_rezyser.Show(not ai_mode)
        self.Layout()

    # ------------------------------------------------------------------
    # Zmiana akcentu – pokazuje/ukrywa pole ISO
    # ------------------------------------------------------------------
    def _on_akcent_change(self, _event: wx.Event) -> None:
        sel = self._combo_akcent.GetStringSelection()
        is_napr = "Naprawiacz" in sel
        self._lbl_iso.Show(is_napr)
        self._txt_iso.Show(is_napr)
        self._pnl_rezyser.Layout()
        self.Layout()

    # ------------------------------------------------------------------
    # Uruchomienie przetwarzania
    # ------------------------------------------------------------------
    def _on_process(self, _event: wx.Event) -> None:
        # Walidacja: plik wczytany?
        if not self._file_content:
            wx.MessageBox(
                "Najpierw wczytaj plik źródłowy (sekcja 1).",
                "Brak pliku w pamięci",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            return

        # Walidacja: wątek już działa?
        if self._worker_thread and self._worker_thread.is_alive():
            wx.MessageBox(
                "Przetwarzanie jest już w toku. Poczekaj na zakończenie.",
                "Zajęty",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            return

        ai_mode = self._api_dostepne and self._rb_ai.GetValue()

        if ai_mode:
            target_lang = self._txt_lang.GetValue().strip()
            if not target_lang:
                wx.MessageBox(
                    "Wpisz język docelowy tłumaczenia przed uruchomieniem.",
                    "Brak języka",
                    wx.OK | wx.ICON_WARNING,
                    self,
                )
                self._txt_lang.SetFocus()
                return
            self._start_ai_translation(target_lang)
        else:
            selected = self._combo_akcent.GetStringSelection()
            if "Naprawiacz" in selected:
                kod_iso = self._txt_iso.GetValue().strip().lower()
                if not kod_iso or len(kod_iso) > 2:
                    wx.MessageBox(
                        "Podaj poprawny dwuliterowy kod ISO języka (np. en, fr, de).",
                        "Brak kodu ISO",
                        wx.OK | wx.ICON_WARNING,
                        self,
                    )
                    self._txt_iso.SetFocus()
                    return
                self._run_rezyser_mode(selected, kod_iso)
            else:
                self._run_rezyser_mode(selected, "")

    # ------------------------------------------------------------------
    # TRYB REŻYSERA (synchroniczny – szybki, bez wątku)
    # ------------------------------------------------------------------
    def _run_rezyser_mode(self, selected: str, reczny_iso: str) -> None:
        content = self._file_content
        ext = self._file_ext
        iso_code = "pl"
        result_text = ""

        bezpieczny = usun_polskie_znaki(selected.split()[0])
        safe_lang = re.sub(r"[^a-zA-Z0-9]", "", bezpieczny)

        # Ustal nazwy pliku wynikowego
        if "Naprawiacz" in selected:
            base_name = f"naprawiony_{self._oryginalna_nazwa}_{reczny_iso}"
            result_text = content
            iso_code = reczny_iso if reczny_iso else "pl"
        elif "Żaden" in selected or safe_lang.lower() == "aden":
            base_name = f"oczyszczony_{self._oryginalna_nazwa}"
            iso_code = "pl"
        else:
            base_name = f"{self._oryginalna_nazwa}_akcent_{safe_lang.lower()}"
            for klucz, kod in AKCENT_ISO.items():
                if klucz in selected:
                    iso_code = kod
                    break

        # Ostrzeżenie o języku źródłowym (tylko gdy nie naprawiacz)
        if "Naprawiacz" not in selected:
            try:
                if detect(content) != "pl":
                    ostrzezenie = (
                        "Uwaga: Wykryto język główny inny niż polski. "
                        "Reguły fonetyczne są przystosowane do polszczyzny – "
                        "efekt może być nieprzewidywalny."
                    )
                    self._lbl_progress.SetValue(ostrzezenie)
                    self._lbl_progress.SetName(ostrzezenie)
                    self._lbl_progress.Show()
                    self.Layout()
                    wx.LogMessage(ostrzezenie)
            except LangDetectException:
                pass

            # Zastosowanie funkcji fonetycznej
            if "Islandzki" in selected:
                result_text = procesuj_z_ochrona_tagow(oczysc_tekst_tts(content, True), akcent_islandzki)
            elif "Włoski" in selected:
                result_text = procesuj_z_ochrona_tagow(oczysc_tekst_tts(content, True), akcent_wloski)
            elif "Fiński" in selected:
                result_text = procesuj_z_ochrona_tagow(oczysc_tekst_tts(content, True), akcent_finski)
            elif "Angielski" in selected:
                result_text = procesuj_z_ochrona_tagow(oczysc_tekst_tts(content, True), akcent_angielski)
            elif "Francuski" in selected:
                result_text = procesuj_z_ochrona_tagow(oczysc_tekst_tts(content, True), akcent_francuski)
            elif "Niemiecki" in selected:
                result_text = procesuj_z_ochrona_tagow(oczysc_tekst_tts(content, True), akcent_niemiecki)
            elif "Hiszpa" in selected:
                result_text = procesuj_z_ochrona_tagow(oczysc_tekst_tts(content, True), akcent_hiszpanski)
            elif "Żaden" in selected:
                result_text = oczysc_tekst_tts(content, z_normalizacja=("BEZ" not in selected))

        if not result_text:
            wx.MessageBox("Nie udało się wygenerować wynikowego tekstu.", "Błąd", wx.OK | wx.ICON_ERROR, self)
            return

        out_path = self._zapisz_wynik(result_text, base_name, ext, iso_code, selected, content)
        if out_path:
            self._txt_result.SetValue(result_text)
            self._txt_result.SetFocus()
            wx.MessageBox(
                f"Plik zapisany jako:\n{out_path}",
                "Sukces",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )

    # ------------------------------------------------------------------
    # TRYB AI – start wątku tła
    # ------------------------------------------------------------------
    def _start_ai_translation(self, target_lang: str) -> None:
        self._btn_process.Disable()
        self._gauge.SetValue(0)
        self._gauge.Show()
        self._lbl_progress.Show()
        self._lbl_progress.SetValue("Inicjowanie tłumaczenia…")
        self._txt_result.SetValue("")
        self.Layout()

        content = self._file_content
        ext = self._file_ext

        self._worker_thread = threading.Thread(
            target=self._ai_worker,
            args=(content, ext, target_lang),
            daemon=True,
        )
        self._worker_thread.start()

    # ------------------------------------------------------------------
    # TRYB AI – wątek tła (ŻADNEGO wx.* bezpośrednio tu!)
    # ------------------------------------------------------------------
    def _ai_worker(self, content: str, ext: str, target_lang: str) -> None:
        """Wykonuje tłumaczenie AI w wątku tła.

        Wszelka komunikacja z GUI odbywa się wyłącznie przez wx.CallAfter.
        """
        import openai  # noqa: PLC0415

        bezpieczny = usun_polskie_znaki(target_lang.split()[0])
        safe_lang = re.sub(r"[^a-zA-Z0-9]", "", bezpieczny)
        base_name = f"{self._oryginalna_nazwa}_tlumaczenie_{safe_lang.lower()}"

        # Plik tymczasowy trafia do runtime/ — ukryty przed end-userem jak .mode
        app_dir = os.path.dirname(os.path.abspath(__file__))
        runtime_dir = os.path.join(app_dir, "runtime")
        if not os.path.exists(runtime_dir):
            print(f"[DEV] Folder runtime/ nie istnieje — tworzę: {runtime_dir}")
            os.makedirs(runtime_dir, exist_ok=True)
        temp_filename = os.path.join(runtime_dir, f"temp_{base_name}.jsonl")

        sys_prompt = (
            f"# Rola\n"
            f"Jesteś ekspertem w dziedzinie tłumaczeń literackich i technicznych.\n\n"
            f"## Zadanie\n"
            f"Przetłumacz **cały** dostarczony tekst na język: **{target_lang}**.\n\n"
            f"## Zasady jakości (obowiązkowe)\n"
            f"- Tłumaczenie musi być dokładne, naturalne i zachowywać styl oryginału.\n"
            f"- Zachowaj strukturę akapitów i podział na linie.\n"
            f"- Imiona własne i terminy tłumacz zgodnie z konwencją języka docelowego.\n"
            f"- Idiomy i metafory oddaj ich sensem, nie dosłownie.\n\n"
            f"## Zasady techniczne (krytyczne)\n"
            f"- BEZWZGLĘDNIE zachowaj wszystkie znaczniki HTML i Markdown.\n"
            f"- Jeśli tekst zawiera HTML, tłumacz WYŁĄCZNIE tekst widoczny.\n"
            f"- Nie dodawaj komentarzy ani wstępów od siebie.\n\n"
            f"## Format odpowiedzi\n"
            f"Zwróć WYŁĄCZNIE przetłumaczony tekst."
        )

        # Podział na bloki (max ~10 000 znaków)
        akapity = content.split("\n")
        bloki: list[str] = []
        obecny_blok = ""
        for akapit in akapity:
            if len(obecny_blok) + len(akapit) < 10_000:
                obecny_blok += akapit + "\n"
            else:
                if obecny_blok.strip():
                    bloki.append(obecny_blok.strip())
                obecny_blok = akapit + "\n"
        if obecny_blok.strip():
            bloki.append(obecny_blok.strip())

        if len(bloki) > 1 and len(bloki[-1]) < 4_000:
            if len(bloki[-2]) + len(bloki[-1]) < 16_000:
                bloki[-2] += "\n\n" + bloki[-1]
                bloki.pop()

        # Odczyt pliku tymczasowego (wznawianie po przerwaniu)
        wczytane_bloki: dict[int, str] = {}
        if os.path.exists(temp_filename):
            wx.CallAfter(
                self._update_progress_label,
                "Wykryto plik zapisu – odtwarzanie opłaconego postępu…",
                0,
            )
            try:
                with open(temp_filename, "r", encoding="utf-8") as fh:
                    for line in fh:
                        if line.strip():
                            data = json.loads(line)
                            wczytane_bloki[data["id"]] = data["text"]
            except Exception as exc:
                wx.CallAfter(self._on_ai_error, f"Błąd odczytu pliku tymczasowego:\n{exc}")
                return

        n = len(bloki)
        przetlumaczono_wszystko = True

        for i, blok in enumerate(bloki):
            if i in wczytane_bloki:
                wx.CallAfter(
                    self._update_progress_label,
                    f"Blok {i + 1}/{n} odzyskany z pliku zapisu.",
                    int((i + 1) / n * 100),
                )
                continue

            wx.CallAfter(
                self._update_progress_label,
                f"Tłumaczenie bloku {i + 1} z {n}… ({len(blok)} znaków)",
                int(i / n * 100),
            )

            messages_payload = [{"role": "system", "content": sys_prompt}]

            if i > 0 and (i - 1) in wczytane_bloki:
                messages_payload.append({
                    "role": "assistant",
                    "content": wczytane_bloki[i - 1],
                })
                user_content = (
                    "[KRYTYCZNE: Kontynuuj tłumaczenie poniższego tekstu. "
                    "Zachowaj absolutną spójność terminologii, tonu i stylu "
                    "z Twoją poprzednią odpowiedzią.]\n\n" + blok
                )
            else:
                user_content = blok

            messages_payload.append({"role": "user", "content": user_content})

            try:
                response = self._client.chat.completions.create(
                    model="gpt-4o",
                    messages=messages_payload,
                    temperature=0.3,
                )
                fragment = response.choices[0].message.content.strip()
                wczytane_bloki[i] = fragment

                with open(temp_filename, "a", encoding="utf-8") as fh:
                    fh.write(
                        json.dumps({"id": i, "text": fragment}, ensure_ascii=False) + "\n"
                    )

            except openai.RateLimitError:
                wx.CallAfter(
                    self._on_ai_error,
                    f"BRAK ŚRODKÓW LUB LIMIT API! Przerwano na bloku {i + 1}.\n\n"
                    "Postęp został automatycznie zabezpieczony.\n"
                    "Zasil konto API i wczytaj oryginał ponownie, "
                    "by kontynuować od tego miejsca.",
                    partial_text="\n\n".join(
                        wczytane_bloki[k] for k in sorted(wczytane_bloki)
                    ),
                )
                return
            except Exception as exc:
                wx.CallAfter(self._on_ai_error, str(exc))
                return

        # ── Pobranie kodu ISO języka docelowego ─────────────────────────
        wx.CallAfter(
            self._update_progress_label,
            "Generowanie tagu językowego dla czytników ekranu…",
            95,
        )
        iso_code = "pl"
        iso_raw_response: str = ""
        try:
            iso_prompt = (
                f"Podaj WYŁĄCZNIE dwuliterowy kod języka ISO 639-1 "
                f"dla języka: {target_lang}. "
                f"Odpowiedź musi zawierać tylko dwuliterowy kod, np.: fi, it, en."
            )
            iso_resp = self._client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": iso_prompt}],
                temperature=0.0,
            )
            iso_raw_response = iso_resp.choices[0].message.content.strip()
            raw = iso_raw_response.lower()
            iso_code = re.sub(r"[^a-z]", "", raw)
            if not iso_code or len(iso_code) > 3:
                blad_info = (
                    f"Nie udało się automatycznie pobrać kodu ISO z API. "
                    f"Użyto domyślnego tagu 'pl'. W razie problemów z czytnikiem ekranu, "
                    f"użyj 'Naprawiacza Tagów' w Trybie Reżysera.\n\n"
                    f"Odpowiedź modelu: {iso_raw_response}"
                )
                wx.CallAfter(
                    self._wyswietl_blad_ai,
                    blad_info,
                    "Ostrzeżenie tagu językowego",
                )
                iso_code = "pl"
        except Exception as iso_exc:
            blad_info = (
                f"Nie udało się automatycznie pobrać kodu ISO z API. "
                f"Użyto domyślnego tagu 'pl'. W razie problemów z czytnikiem ekranu, "
                f"użyj 'Naprawiacza Tagów' w Trybie Reżysera.\n\n"
                f"Szczegóły błędu: {iso_exc}"
                + (f"\n\nOdpowiedź modelu: {iso_raw_response}" if iso_raw_response else "")
            )
            wx.CallAfter(
                self._wyswietl_blad_ai,
                blad_info,
                "Ostrzeżenie tagu językowego",
            )
            iso_code = "pl"

        # ── Usunięcie pliku tymczasowego ────────────────────────────────
        if os.path.exists(temp_filename):
            try:
                os.remove(temp_filename)
            except Exception:
                pass

        result_text = "\n\n".join(wczytane_bloki[k] for k in sorted(wczytane_bloki)).strip()

        wx.CallAfter(self._update_progress_label, "Zapis pliku wynikowego…", 99)

        # Zapis i informacja – muszą być w wątku GUI
        wx.CallAfter(
            self._on_ai_done,
            result_text,
            base_name,
            ext,
            iso_code,
            target_lang,
        )

    # ------------------------------------------------------------------
    # Wyświetlanie błędów (krótkie → MessageBox; długie → dialog z polem)
    # ------------------------------------------------------------------
    def _wyswietl_blad_ai(self, tresc_bledu: str, custom_msg: str | None = None) -> None:
        """Wyświetla błąd – krótki przez MessageBox, długi przez dialog z polem do skopiowania.

        Args:
            tresc_bledu:  Treść błędu (string wyjątku lub długi komunikat).
            custom_msg:   Opcjonalny nagłówek / krótki opis kontekstu błędu.
                          Odpowiednik ``custom_msg`` z wyswietl_blad_ai() w Streamlicie.
        """
        msg_header  = custom_msg or "Wystąpił nieoczekiwany błąd podczas przetwarzania."
        jest_krotki = len(tresc_bledu) <= 200 and "\n" not in tresc_bledu

        if jest_krotki:
            pelna_tresc = f"{msg_header}\n\n{tresc_bledu}" if custom_msg else tresc_bledu
            wx.MessageBox(pelna_tresc, "Błąd", wx.OK | wx.ICON_ERROR, self)
        else:
            dlg = wx.Dialog(self, title="Błąd – Szczegóły techniczne", size=(640, 400))
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
    # Callbacki wywoływane z wx.CallAfter (zawsze w wątku GUI)
    # ------------------------------------------------------------------
    def _update_progress_label(self, msg: str, percent: int) -> None:
        self._lbl_progress.SetValue(msg)
        self._lbl_progress.SetName(msg)
        self._gauge.SetValue(max(0, min(100, percent)))

    def _on_ai_error(self, msg: str, partial_text: str = "") -> None:
        self._btn_process.Enable()
        self._gauge.Hide()
        self._lbl_progress.Hide()
        self.Layout()

        if partial_text:
            self._txt_result.SetValue(partial_text)
            self._txt_result.SetFocus()

        self._wyswietl_blad_ai(msg)

    def _on_ai_done(
        self,
        result_text: str,
        base_name: str,
        ext: str,
        iso_code: str,
        target_lang: str,
    ) -> None:
        self._txt_result.SetValue(result_text)
        self._txt_result.SetFocus()

        out_path = self._zapisz_wynik(
            result_text, base_name, ext, iso_code, target_lang, self._file_content
        )

        self._gauge.SetValue(100)
        self._btn_process.Enable()

        if out_path:
            wx.MessageBox(
                f"Tłumaczenie ukończone!\n\nPlik zapisany jako:\n{out_path}",
                "Sukces",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
        self._gauge.Hide()
        self._lbl_progress.SetValue("")
        self._lbl_progress.Hide()
        self.Layout()

    # ------------------------------------------------------------------
    # Zapis pliku wynikowego (wspólny dla obu trybów)
    # ------------------------------------------------------------------
    def _zapisz_wynik(
        self,
        result_text: str,
        base_name: str,
        ext: str,
        iso_code: str,
        mode_or_lang: str,
        oryginalny_content: str,
    ) -> str | None:
        """Zapisuje wynik do pliku. Zwraca ścieżkę do pliku lub None przy błędzie."""
        katalog = self._plik_katalog

        try:
            if ext == ".docx":
                out_path = os.path.join(katalog, f"{base_name}.docx")
                if "Naprawiacz" in mode_or_lang:
                    # Tryb naprawiania tagów – modyfikujemy istniejący .docx
                    orig_file = os.path.join(katalog, f"{self._oryginalna_nazwa}{ext}")
                    if os.path.exists(orig_file):
                        doc = docx.Document(orig_file)
                    else:
                        doc = docx.Document()
                        for linia in oryginalny_content.split("\n"):
                            doc.add_paragraph(linia)
                    for p in doc.paragraphs:
                        for run in p.runs:
                            rPr = run._r.get_or_add_rPr()
                            lang_el = rPr.find(qn("w:lang"))
                            if lang_el is None:
                                lang_el = OxmlElement("w:lang")
                                rPr.append(lang_el)
                            lang_el.set(qn("w:val"), iso_code)
                    doc.save(out_path)
                elif "Tryb Reżysera" in mode_or_lang or any(
                    a in mode_or_lang for a in ["Islandzki", "Angielski", "Francuski",
                                                 "Niemiecki", "Hiszpa", "Włoski", "Fiński", "Żaden"]
                ):
                    # Prosty zapis płaskiego tekstu do nowego .docx
                    nowy_doc = docx.Document()
                    for linia in result_text.split("\n"):
                        p = nowy_doc.add_paragraph(linia)
                        for run in p.runs:
                            rPr = run._r.get_or_add_rPr()
                            lang_el = rPr.find(qn("w:lang"))
                            if lang_el is None:
                                lang_el = OxmlElement("w:lang")
                                rPr.append(lang_el)
                            lang_el.set(qn("w:val"), iso_code)
                    nowy_doc.save(out_path)
                else:
                    # Tryb AI – nowy dokument z tagiem lang
                    nowy_doc = docx.Document()
                    for linia in result_text.split("\n"):
                        p = nowy_doc.add_paragraph(linia)
                        for run in p.runs:
                            rPr = run._r.get_or_add_rPr()
                            lang_el = rPr.find(qn("w:lang"))
                            if lang_el is None:
                                lang_el = OxmlElement("w:lang")
                                rPr.append(lang_el)
                            lang_el.set(qn("w:val"), iso_code)
                    nowy_doc.save(out_path)

            elif ext in (".html", ".htm"):
                out_path = os.path.join(katalog, f"{base_name}{ext}")
                txt = result_text
                if "lang=" in txt.lower():
                    txt = re.sub(
                        r'(<html[^>]*?)lang=["\'][^"\']+["\']',
                        fr'\1lang="{iso_code}"',
                        txt,
                        flags=re.IGNORECASE,
                    )
                elif "<html" in txt.lower():
                    txt = re.sub(
                        r"(<html[^>]*)>",
                        fr'\1 lang="{iso_code}">',
                        txt,
                        flags=re.IGNORECASE,
                    )
                with open(out_path, "w", encoding="utf-8") as fh:
                    fh.write(txt)

            elif ext in (".txt", ".md"):
                # Konwertujemy na HTML z tagiem lang (jak oryginał Streamlit)
                out_path = os.path.join(katalog, f"{base_name}.html")
                linie = result_text.split("\n")
                tytul = linie[0].strip() if linie and linie[0].strip() else "Dokument"
                html_body = result_text.replace("\n", "<br>\n")
                html_content = (
                    f'<!DOCTYPE html>\n<html lang="{iso_code}">\n'
                    f"<head>\n<meta charset=\"utf-8\">\n<title>{tytul}</title>\n</head>\n"
                    f"<body>\n{html_body}\n</body>\n</html>"
                )
                with open(out_path, "w", encoding="utf-8") as fh:
                    fh.write(html_content)

            else:
                out_path = os.path.join(katalog, f"{base_name}{ext if ext else '.txt'}")
                with open(out_path, "w", encoding="utf-8") as fh:
                    fh.write(result_text)

        except Exception as exc:
            wx.MessageBox(
                f"Błąd podczas zapisu pliku wynikowego:\n{exc}",
                "Błąd zapisu",
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return None

        return out_path
