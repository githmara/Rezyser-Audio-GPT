"""
gui_konwerter.py – Panel modułu „Architekt Audiobooków".

Zastępuje pages/3_Konwerter.py (Streamlit).
Dziedziczy po wx.Panel; podpinany do MainFrame z main.py.

Wersja 13.1: cały tekst widoczny dla użytkownika przechodzi przez
:mod:`i18n` (klucze z ``dictionaries/pl/gui/ui.yaml`` – sekcja ``konwerter``).
"""

import os
import re
from functools import lru_cache
from pathlib import Path

import docx
import wx
import yaml

from i18n import t


# v15.1: detekcja znaczników tury wstawianych przez Opowieści
# (dopisz_do_txt(naglowek="\n\n--- Tura N ---\n\n") w core_opowiesci.py).
# Alternatywa pokrywa wszystkie 9 wdrożonych języków zgodnie z kluczem
# `opowiesci.tura_naglowek_format` w dictionaries/<kod>/gui/ui.yaml.
_REGEX_TURA = re.compile(
    r"^---\s*"
    r"(?:Tura|Turn|Runde|Turno|Vuoro|Tour|Umferð|Ход)"
    r"\s+(\d+)\s*---$",
    re.IGNORECASE,
)
# Co ile tur II-osobowych konwerter wstawia nagłówek H1 „Scena N" (cięcie
# rozdziału w ElevenLabs). 5 tur ≈ 5-7,5 tys. znaków, czyli kilka minut audio
# na scenę — zbliżone do naturalnego rozdziału audiobooka. Krótszy próg
# sztucznie tnie narrację; dłuższy traci nawigację dla NVDA.
# v15.4.1: licznik resetuje się po każdym KINOWYM cięciu (`/scena`,
# `/flashback`, auto-cut LLMa) — patrz `_REGEX_PREFIKS_KAMERA` niżej.
TURY_NA_SCENE = 5

# v15.4.1: katalog `dictionaries/` w roocie repo — używany do zebrania
# prefiksów A11y ze wszystkich paczek językowych. Konwerter nie zna języka
# pliku wejściowego, więc detekcja jest unifikowana: rozpoznajemy prefiksy
# z dowolnej paczki (gracz mógł zmienić język aplikacji w trakcie projektu).
_DICTIONARIES_DIR = Path(__file__).resolve().parent / "dictionaries"


@lru_cache(maxsize=1)
def _regex_prefiksow_kamery() -> re.Pattern:
    """Buduje regex prefiksów A11y kinowych narracji ze WSZYSTKICH paczek językowych.

    Tło: ``gui_opowiesci._obsluz_ture`` skleja prefiks A11y (z
    ``opowiesci.prefiks_{flashback,scena,cut}``) z narracją LLM i zapisuje do
    ``skrypty/<nazwa>.txt``. Konwerter widzi tę sklejoną linię na początku
    akapitu tury i traktuje jako sygnał KINOWEGO cięcia: osobny H1, reset
    licznika tur II-osobowych. Bez tego kilkanaście tur kinowych pod rząd
    siedziało pod jednym H1 „Scena N" (ElevenLabs nie tnie rozdziału).

    Dynamiczny pickup z YAML zamiast hardcode'u dlatego, że dodanie kolejnego
    języka w przyszłości (10. paczka) działa zero-touch dla konwertera.

    Zwraca regex case-insensitive matchujący od początku linii; jeśli żadna
    paczka nie ma prefiksów (świeże repo), zwraca regex niezgodny z niczym.
    """
    prefiksy: list[str] = []
    if not _DICTIONARIES_DIR.is_dir():
        return re.compile(r"$^")
    for jezyk_dir in sorted(_DICTIONARIES_DIR.iterdir()):
        ui_path = jezyk_dir / "gui" / "ui.yaml"
        if not ui_path.is_file():
            continue
        try:
            with open(ui_path, "r", encoding="utf-8") as fh:
                dane = yaml.safe_load(fh) or {}
        except (OSError, yaml.YAMLError):
            continue
        opowiesci = dane.get("opowiesci") or {}
        for klucz in ("prefiks_flashback", "prefiks_scena", "prefiks_cut"):
            wartosc = opowiesci.get(klucz)
            if isinstance(wartosc, str) and wartosc.strip():
                prefiksy.append(re.escape(wartosc.strip()))
    if not prefiksy:
        return re.compile(r"$^")
    # Unikalizacja — ten sam prefiks może powtarzać się między paczkami
    # (np. en "Flashback:" i de "Flashback:" — anglicyzm w branży filmowej).
    unikalne = sorted(set(prefiksy), key=len, reverse=True)
    return re.compile(r"^(?:" + "|".join(unikalne) + r")", re.IGNORECASE)


class KonwerterPanel(wx.Panel):
    """
    Panel narzędzia „Architekt Audiobooków".

    Funkcjonalność:
        - Przyjmuje ścieżkę do pliku .txt lub .docx
        - Przetwarza tekst: czyści HTML/Markdown, wykrywa nagłówki
          (Czołówka, Rozdział, Prolog, Epilog, Akt) i sceny
        - Zapisuje wynik jako architektura_<oryginalna_nazwa>.docx
          w tym samym katalogu co plik źródłowy
        - Sukces / błąd raportuje przez wx.MessageBox (A11y)
    """

    def __init__(self, parent: wx.Window) -> None:
        super().__init__(parent, style=wx.TAB_TRAVERSAL)
        self.SetName(t("konwerter.panel_name"))

        self._build_ui()
        self._bind_events()

    # ------------------------------------------------------------------
    # Budowanie interfejsu
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # --- Nagłówek narzędzia ---
        heading = wx.StaticText(self, label=t("konwerter.heading"))
        heading_font = heading.GetFont()
        heading_font.SetPointSize(16)
        heading_font.MakeBold()
        heading.SetFont(heading_font)

        # --- Opis narzędzia ---
        description = wx.TextCtrl(
            self,
            value=t("konwerter.tool_description"),
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.NO_BORDER,
        )
        # Upodabniamy tło pola do tła głównego okna, żeby nie wyglądało jak pole do wpisywania
        description.SetBackgroundColour(self.GetBackgroundColour())

        # --- Separator ---
        separator = wx.StaticLine(self)

        # --- Etykieta + pole wejściowe na nazwę / ścieżkę pliku ---
        lbl_file = wx.StaticText(self, label=t("konwerter.lbl_plik"))

        self._txt_file = wx.TextCtrl(
            self,
            style=wx.TE_PROCESS_ENTER,
            name=t("konwerter.txt_plik_name"),
        )
        self._txt_file.SetHint(t("konwerter.txt_plik_hint"))

        self._btn_browse = wx.Button(self, label=t("konwerter.btn_przegladaj"))
        self._btn_browse.SetToolTip(t("konwerter.btn_przegladaj_tooltip"))

        # Poziomy sizer: pole tekstowe (rozszerzalne) + przycisk po prawej
        file_row_sizer = wx.BoxSizer(wx.HORIZONTAL)
        file_row_sizer.Add(
            self._txt_file,
            proportion=1,
            flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT,
            border=6,
        )
        file_row_sizer.Add(
            self._btn_browse,
            flag=wx.ALIGN_CENTER_VERTICAL,
        )

        # --- Przycisk akcji ---
        self._btn_build = wx.Button(self, label=t("konwerter.btn_buduj"))
        self._btn_build.SetToolTip(t("konwerter.btn_buduj_tooltip"))

        # --- Złożenie layoutu ---
        main_sizer.Add(heading,       flag=wx.ALL, border=16)
        main_sizer.Add(description,   flag=wx.LEFT | wx.RIGHT | wx.BOTTOM, border=16)
        main_sizer.Add(separator,     flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=16)
        main_sizer.Add(lbl_file,      flag=wx.LEFT | wx.TOP | wx.RIGHT, border=16)
        main_sizer.Add(
            file_row_sizer,
            flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP,
            border=8,
        )
        main_sizer.Add(
            self._btn_build,
            flag=wx.LEFT | wx.TOP | wx.BOTTOM,
            border=16,
        )

        self.SetSizer(main_sizer)

    # ------------------------------------------------------------------
    # Podpięcie zdarzeń
    # ------------------------------------------------------------------
    def _bind_events(self) -> None:
        self._btn_build.Bind(wx.EVT_BUTTON, self._on_build)
        self._btn_browse.Bind(wx.EVT_BUTTON, self._on_browse)
        # Enter w polu tekstowym też uruchamia akcję
        self._txt_file.Bind(wx.EVT_TEXT_ENTER, self._on_build)

    # ------------------------------------------------------------------
    # Otwieranie okna wyboru pliku
    # ------------------------------------------------------------------
    def _on_browse(self, _event: wx.Event) -> None:
        """Otwiera systemowy dialog wyboru pliku i wstawia ścieżkę do pola."""
        with wx.FileDialog(
            self,
            message=t("konwerter.file_dlg_title"),
            wildcard=t("konwerter.file_dlg_wildcard"),
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        ) as dlg:
            if dlg.ShowModal() == wx.ID_OK:
                self._txt_file.SetValue(dlg.GetPath())
                self._txt_file.SetFocus()

    # ------------------------------------------------------------------
    # Logika przetwarzania (przeniesiona z 3_Konwerter.py)
    # ------------------------------------------------------------------
    def _on_build(self, _event: wx.Event) -> None:
        """Obsługuje kliknięcie przycisku „Buduj Architekturę"."""
        file_name = self._txt_file.GetValue().strip()

        # --- Walidacja wejścia ---
        if not file_name:
            wx.MessageBox(
                t("konwerter.brak_pliku_tresc"),
                t("konwerter.brak_pliku_tytul"),
                wx.OK | wx.ICON_WARNING,
                self,
            )
            self._txt_file.SetFocus()
            return

        if not os.path.exists(file_name):
            wx.MessageBox(
                t("konwerter.plik_nie_istnieje_tresc", sciezka_pliku=file_name),
                t("konwerter.plik_nie_istnieje_tytul"),
                wx.OK | wx.ICON_ERROR,
                self,
            )
            self._txt_file.SetFocus()
            return

        # --- Odczyt pliku źródłowego ---
        try:
            if file_name.lower().endswith(".docx"):
                doc_in = docx.Document(file_name)
                tekst = "\n".join(p.text for p in doc_in.paragraphs)
            else:
                with open(file_name, "r", encoding="utf-8") as fh:
                    tekst = fh.read()
        except Exception as exc:
            wx.MessageBox(
                t("konwerter.blad_odczytu_tresc", tresc_bledu=str(exc)),
                t("konwerter.blad_odczytu_tytul"),
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return

        # --- Przetwarzanie treści ---
        # Pole `author` .docx jest widoczne dla NVDA w dymkach podpowiedzi
        # Eksploratora – bierzemy je z i18n, żeby nie pokazywać polskiego
        # „Reżyser" użytkownikom, którzy aplikację mają na innym języku.
        nowy_doc = docx.Document()
        nowy_doc.core_properties.author = t("konwerter.author_metadata")
        nowy_doc.core_properties.comments = ""

        # v15.1: liczniki dla trybu Opowieści — co TURY_NA_SCENE tur II-osobowych
        # wstawiamy H1 „Scena N", pozostałe znaczniki `--- Tura N ---`
        # strippujemy (meta-info „Tura 7" w audiobooku łamie immersję).
        # v15.4.1: licznik tur II-osobowych liczy się OD OSTATNIEGO H1 — każda
        # kinowa narracja (`/scena`, `/flashback`, auto-cut LLMa) wymusza
        # osobne H1 i resetuje licznik. Bez tego kilkanaście kinowych
        # przeskoków pod rząd siedziało pod jednym wspólnym H1 i ElevenLabs
        # nie tnęło rozdziału przy zmianie kamery.
        # Inicjalizacja `tury_od_h1 = TURY_NA_SCENE` żeby pierwsza tura
        # dokumentu wymusiła H1 „Scena 1" (warunek `>=` spełniony od razu).
        tury_od_h1 = TURY_NA_SCENE
        scena_counter = 0
        regex_kamera = _regex_prefiksow_kamery()

        def _wstaw_h1_sceny() -> None:
            nonlocal scena_counter, tury_od_h1
            scena_counter += 1
            tury_od_h1 = 0
            etykieta = t("konwerter.scena_naglowek_format", numer=scena_counter)
            nowy_doc.add_heading(etykieta, level=1)

        for linia in tekst.splitlines():
            linia = linia.strip()
            if not linia:
                continue

            # Usuwanie tagów HTML
            linia = re.sub(r'<[^>]+>', '', linia).strip()
            if not linia:
                continue

            # Usuwanie znaczników nagłówków Markdown (np. ### lub ####)
            linia = re.sub(r'^#+\s*', '', linia)

            # v15.1: Detekcja znaczników tury z Opowieści.
            # Pierwsza tura w dokumencie i każda po TURY_NA_SCENE turach
            # II-osobowych od ostatniego H1 dostają osobną H1 „Scena N".
            # Same znaczniki `--- Tura N ---` są strippowane.
            if _REGEX_TURA.match(linia):
                if tury_od_h1 >= TURY_NA_SCENE:
                    _wstaw_h1_sceny()
                tury_od_h1 += 1
                continue

            # v15.4.1: Detekcja kinowego prefiksu A11y („Retrospekcja:",
            # „Scena zza kadru:", „Tymczasem gdzie indziej:" + odpowiedniki
            # w 8 pozostałych językach). Każdy taki prefiks startuje nową
            # scenę z osobnym H1; treść po prefiksie idzie jako zwykły
            # paragraf pod H1, bez prefiksu meta (w pliku audio mówca
            # nie powinien czytać „Retrospekcja:" jako część fabuły).
            match_kamera = regex_kamera.match(linia)
            if match_kamera:
                _wstaw_h1_sceny()
                ostatek = linia[match_kamera.end():].strip()
                if ostatek:
                    nowy_doc.add_paragraph(ostatek)
                continue

            # Detekcja nagłówków głównych (tnących plik na rozdziały w ElevenLabs)
            # Obsługuje wszystkie 6 języków: pl/en/fi/is/it/ru
            if re.match(
                r"^[=\-\s]*("
                r"Czołówka"
                r"|Rozdzia[łl]|Chapter|Luku|Kafli|Capitolo|Глава"
                r"|Prolog(?:ue|i|o)?|Formáli|Пролог"
                r"|Epilog(?:ue|i|o)?|Eftirorð|Эпилог"
                r"|Akt|Act|Акт|Näytös|Þáttur"
                r")",
                linia,
                re.IGNORECASE,
            ):
                czysty = re.sub(r'^[=\-\s]+|[=\-\s]+$', '', linia)
                nowy_doc.add_heading(czysty, level=1)

            # Detekcja scen (pogrubiony tekst, bez wpisu w spisie treści)
            # Obsługuje wszystkie 6 języków: pl/en/fi/is/it/ru
            elif re.match(
                r"^[=\-\s]*(?:Scena|Scene|Kohtaus|Atriði|Сцена)",
                linia,
                re.IGNORECASE,
            ):
                czysty = re.sub(r'^[=\-\s]+|[=\-\s]+$', '', linia)
                p = nowy_doc.add_paragraph()
                run = p.add_run(czysty)
                run.bold = True

            else:
                nowy_doc.add_paragraph(linia)

        # --- Zapis pliku wynikowego ---
        katalog = os.path.dirname(os.path.abspath(file_name))
        oryginalna_nazwa = os.path.splitext(os.path.basename(file_name))[0]
        out_name = os.path.join(katalog, f"architektura_{oryginalna_nazwa}.docx")

        try:
            nowy_doc.save(out_name)
        except Exception as exc:
            wx.MessageBox(
                t("konwerter.blad_zapisu_tresc", tresc_bledu=str(exc)),
                t("konwerter.blad_zapisu_tytul"),
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return

        wx.MessageBox(
            t("konwerter.sukces_tresc", sciezka_pliku=out_name),
            t("konwerter.sukces_tytul"),
            wx.OK | wx.ICON_INFORMATION,
            self,
        )
