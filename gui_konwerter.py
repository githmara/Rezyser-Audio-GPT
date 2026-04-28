"""
gui_konwerter.py – Panel modułu „Architekt Audiobooków".

Zastępuje pages/3_Konwerter.py (Streamlit).
Dziedziczy po wx.Panel; podpinany do MainFrame z main.py.

Wersja 13.1: cały tekst widoczny dla użytkownika przechodzi przez
:mod:`i18n` (klucze z ``dictionaries/pl/gui/ui.yaml`` – sekcja ``konwerter``).
"""

import os
import re

import docx
import wx

from i18n import t


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
