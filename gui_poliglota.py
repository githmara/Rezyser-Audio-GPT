"""
gui_poliglota.py – Panel modułu „Poliglota AI" (wxPython, wersja wydawnicza).

Po refaktorze do wersji 13.0 ten plik pełni WYŁĄCZNIE rolę warstwy widoku
(zgodnie z nazwą ``gui_*``). Cała logika przetwarzania tekstu żyje w:

  * ``core_poliglota.py`` – silnik reguł fonetycznych i szyfrów (YAML),
  * ``tlumacz_ai.py``     – tłumacz Anthropic Claude w wątku tła.

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
                                     wariant="cezar",
                                     opcje={"przesuniecie": 7})

Wersja 13.1: cały tekst widoczny dla użytkownika pochodzi z
``dictionaries/pl/gui/ui.yaml`` (sekcja ``poliglota``) przez moduł
:mod:`i18n`.
"""

from __future__ import annotations

import os
import threading

from dotenv import load_dotenv

import wx

import bledy_ai
import core_llm as cl
import core_markdown
import core_poliglota
import core_tokeny as ct
import gui_diagnostyka as gd
import i18n
import sciezki
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


class DialogKodyPerAkapit(wx.Dialog):
    """Lista akapitów pliku z edytowalnym kodem języka dla każdego z nich.

    Domyka ostatni punkt architektury Naprawiacza Tagów zaplanowany w 19.1
    („wybór kodu dla pojedynczych akapitów wymaga interfejsu, w którym te
    akapity widzisz" — `manual.yaml` obiecał to użytkownikowi wprost).

    A11y — dlaczego ListBox, a nie tabelka: w całym repozytorium nie ma ani
    jednego ``wx.ListCtrl`` czy ``wx.grid``; GUI stoi na ComboBox / TextCtrl /
    Button / CheckBox / SpinCtrl / Gauge. Tabela z edycją w komórce wymagałaby
    od czytnika ekranu trybu tabelowego i nawigacji po kolumnach, a ``ListBox``
    czyta się jedną strzałką. Dlatego stan jednostki (numer, początek treści
    i NADANY KOD) jest wpisany w etykietę pozycji — użytkownik słyszy go bez
    wchodzenia w którekolwiek pole.

    Opinia detektora jest liczona LENIWIE, dla wybranej pozycji, i pamiętana
    w ``_opinie``: dokument dwutysięczny nie płaci niczego z góry, a pełny
    kanon 75 języków kosztuje ~3 ms na akapit (patrz
    ``core_poliglota._zbuduj_detektor_pelny``). Kody startują wartością z pola
    „Kod ISO", nigdy opinią detektora — do pliku wynikowego nie trafia kod,
    którego użytkownik nie zatwierdził (kanon 19.1: język wyniku to dane).
    """

    MAKS_PODGLAD = 60   # znaków treści w etykiecie pozycji listy

    def __init__(self, parent: wx.Window, jednostki: list[str],
                 kod_domyslny: str) -> None:
        super().__init__(parent, title=t("poliglota.per_akapit_tytul"),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
                         size=(700, 520))
        self._jednostki = jednostki
        self._kod_domyslny = kod_domyslny
        self._kody: list[str] = [kod_domyslny] * len(jednostki)
        self._opinie: dict[int, str | None] = {}

        sizer = wx.BoxSizer(wx.VERTICAL)

        lbl_lista = wx.StaticText(self, label=t("poliglota.per_akapit_lista_lbl",
                                                liczba_akapitow=len(jednostki)))
        self._lista = wx.ListBox(self, choices=self._etykiety(),
                                 style=wx.LB_SINGLE,
                                 name=t("poliglota.per_akapit_lista_name"))

        lbl_tresc = wx.StaticText(self, label=t("poliglota.per_akapit_tresc_lbl"))
        self._txt_tresc = wx.TextCtrl(
            self, style=wx.TE_MULTILINE | wx.TE_READONLY,
            size=(-1, 90), name=t("poliglota.per_akapit_tresc_name"))

        lbl_opinia = wx.StaticText(self, label=t("poliglota.per_akapit_opinia_lbl"))
        self._txt_opinia = wx.TextCtrl(
            self, style=wx.TE_READONLY,
            name=t("poliglota.per_akapit_opinia_name"))

        lbl_kod = wx.StaticText(self, label=t("poliglota.per_akapit_kod_lbl"))
        self._txt_kod = wx.TextCtrl(self, name=t("poliglota.per_akapit_kod_name"))
        self._txt_kod.SetMaxLength(7)

        btn_wszystkie = wx.Button(self, label=t("poliglota.per_akapit_btn_wszystkie"))
        btn_detektor = wx.Button(self, label=t("poliglota.per_akapit_btn_detektor"))
        btn_ok = wx.Button(self, wx.ID_OK, label=t("poliglota.per_akapit_btn_ok"))
        btn_anuluj = wx.Button(self, wx.ID_CANCEL,
                               label=t("poliglota.per_akapit_btn_anuluj"))

        rzad_akcji = wx.BoxSizer(wx.HORIZONTAL)
        rzad_akcji.Add(btn_wszystkie, flag=wx.RIGHT, border=8)
        rzad_akcji.Add(btn_detektor)

        rzad_konca = wx.StdDialogButtonSizer()
        rzad_konca.AddButton(btn_ok)
        rzad_konca.AddButton(btn_anuluj)
        rzad_konca.Realize()

        for kontrolka, proporcja in ((lbl_lista, 0), (self._lista, 1),
                                     (lbl_tresc, 0), (self._txt_tresc, 0),
                                     (lbl_opinia, 0), (self._txt_opinia, 0),
                                     (lbl_kod, 0), (self._txt_kod, 0),
                                     (rzad_akcji, 0)):
            sizer.Add(kontrolka, proportion=proporcja,
                      flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, border=8)
        sizer.Add(rzad_konca, flag=wx.EXPAND | wx.ALL, border=8)
        self.SetSizer(sizer)

        self._lista.Bind(wx.EVT_LISTBOX, self._on_wybor)
        # Kod zapisujemy na UTRACIE FOKUSU pola, nie przy każdym znaku:
        # walidacja po literze odrzucałaby „p" w drodze do „pl", a zapis
        # dopiero na OK gubiłby wpis użytkownika, który przeszedł strzałką do
        # następnego akapitu. Utrata fokusu zachodzi ZAWSZE przed zmianą
        # pozycji na liście, więc ten jeden punkt wystarcza.
        self._txt_kod.Bind(wx.EVT_KILL_FOCUS, self._on_kod_kill_focus)
        btn_wszystkie.Bind(wx.EVT_BUTTON, self._on_wszystkie)
        btn_detektor.Bind(wx.EVT_BUTTON, self._on_detektor)
        btn_ok.Bind(wx.EVT_BUTTON, self._on_ok)

        if self._jednostki:
            self._lista.SetSelection(0)
            self._pokaz_pozycje(0)
        self._lista.SetFocus()

    # ------------------------------------------------------------------
    # Wynik dla wywołującego
    # ------------------------------------------------------------------
    def kody(self) -> list[str]:
        """Kody ISO w kolejności jednostek (długość == długość wejścia)."""
        return list(self._kody)

    # ------------------------------------------------------------------
    # Prezentacja
    # ------------------------------------------------------------------
    def _etykieta(self, i: int) -> str:
        tresc = self._jednostki[i]
        if len(tresc) > self.MAKS_PODGLAD:
            tresc = tresc[:self.MAKS_PODGLAD].rstrip() + "…"
        return t("poliglota.per_akapit_pozycja",
                 numer_akapitu=i + 1, tresc_akapitu=tresc, kod_iso=self._kody[i])

    def _etykiety(self) -> list[str]:
        return [self._etykieta(i) for i in range(len(self._jednostki))]

    def _pokaz_pozycje(self, i: int) -> None:
        self._txt_tresc.SetValue(self._jednostki[i])
        self._txt_kod.SetValue(self._kody[i])
        self._txt_opinia.SetValue(self._opis_opinii(i))

    def _opis_opinii(self, i: int) -> str:
        if i not in self._opinie:
            self._opinie[i] = core_poliglota.opinia_detektora(self._jednostki[i])
        kod = self._opinie[i]
        if not kod:
            return t("poliglota.per_akapit_opinia_brak")
        return t("poliglota.per_akapit_opinia_wynik",
                 nazwa_jezyka=core_poliglota.nazwa_dla_opinii(kod), kod_iso=kod)

    def _odswiez_etykiete(self, i: int) -> None:
        wybrany = self._lista.GetSelection()
        self._lista.SetString(i, self._etykieta(i))
        if wybrany != wx.NOT_FOUND:
            self._lista.SetSelection(wybrany)

    # ------------------------------------------------------------------
    # Zdarzenia
    # ------------------------------------------------------------------
    def _on_wybor(self, _event: wx.Event) -> None:
        i = self._lista.GetSelection()
        if i != wx.NOT_FOUND:
            self._pokaz_pozycje(i)

    def _zapisz_biezacy(self) -> None:
        i = self._lista.GetSelection()
        if i == wx.NOT_FOUND:
            return
        nowy = self._txt_kod.GetValue().strip()
        if nowy == self._kody[i]:
            return
        self._kody[i] = nowy
        self._odswiez_etykiete(i)

    def _on_kod_kill_focus(self, event: wx.Event) -> None:
        # Guard na niszczenie okna: utrata fokusu potrafi przyjść w trakcie
        # `Destroy()`, a wtedy `self._lista` jest już nieużywalne.
        if self.IsBeingDeleted():                           # pragma: no cover
            event.Skip()
            return
        self._zapisz_biezacy()
        event.Skip()        # bez Skip() wx gubi dalszą obsługę fokusu

    def _potwierdz_nadpisanie(self) -> bool:
        """Pyta przed akcją, która nadpisze RĘCZNIE ustawione kody.

        Audyt v19.2: obie akcje masowe („zastosuj do wszystkich", „wypełnij
        wynikiem wykrywania") kasowały całą listę bez pytania i bez cofnięcia,
        a w polskiej paczce miały dodatkowo ten sam akcelerator. Pytamy tylko
        wtedy, gdy jest co stracić — czyli gdy co najmniej jeden kod różni się
        od kodu domyślnego, z którym lista wstała.
        """
        zmienione = sum(1 for kod in self._kody if kod != self._kod_domyslny)
        if not zmienione:
            return True
        odpowiedz = wx.MessageBox(
            t("poliglota.per_akapit_nadpisanie_tresc",
              liczba_zmienionych=zmienione),
            t("poliglota.per_akapit_nadpisanie_tytul"),
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING, self)
        return odpowiedz == wx.YES

    def _on_wszystkie(self, _event: wx.Event) -> None:
        self._zapisz_biezacy()
        i = self._lista.GetSelection()
        if i == wx.NOT_FOUND:
            return
        if not self._potwierdz_nadpisanie():
            return
        self._kody = [self._kody[i]] * len(self._kody)
        self._lista.Set(self._etykiety())
        self._lista.SetSelection(i)
        self._pokaz_pozycje(i)
        self._lista.SetFocus()

    def _on_detektor(self, _event: wx.Event) -> None:
        """Wypełnia kody opinią detektora — jawną decyzją i z BILANSEM na końcu.

        Akapit bez opinii (za krótki, detektor niepewny) ZACHOWUJE dotychczasowy
        kod: „nie wiem" nie może wyczyścić wartości, którą użytkownik wpisał.
        Ale nie może też zniknąć bez słowa — w dokumencie dwutysięcznym nie ma
        jak przesłuchać, których pozycji detektor nie ruszył, więc na końcu
        mówimy wprost, ile wypełniono i ile zostało (audyt v19.2, standard
        „zero ciszy"). To samo dotyczy anulowania: meldujemy, na której
        pozycji przerwano.

        Pasek postępu jest natywnym ``wx.ProgressDialog`` pompującym zdarzenia
        w wątku GUI — świadomie BEZ wątku tła, bo wątek wymagałby własnego
        ``threading.excepthook`` i guardu na zamknięcie dialogu w trakcie
        pracy, a koszt to milisekundy na akapit.
        """
        if not self._jednostki:
            return
        self._zapisz_biezacy()
        if not self._potwierdz_nadpisanie():
            return

        ile = len(self._jednostki)
        postep = wx.ProgressDialog(
            t("poliglota.per_akapit_postep_tytul"),
            t("poliglota.per_akapit_postep_tresc"),
            maximum=ile, parent=self,
            style=wx.PD_APP_MODAL | wx.PD_CAN_ABORT | wx.PD_AUTO_HIDE)
        wypelnione = 0
        przerwane_na: int | None = None
        try:
            for i, tekst in enumerate(self._jednostki):
                # Co dziesiąta pozycja ORAZ ostatnia — inaczej dokument
                # krótszy niż dziesięć akapitów nie dostawał ani jednego
                # odświeżenia poza zerowym.
                if i % 10 == 0 or i == ile - 1:
                    dalej, _ = postep.Update(i + 1)
                    if not dalej:
                        przerwane_na = i + 1
                        break
                if i not in self._opinie:
                    self._opinie[i] = core_poliglota.opinia_detektora(tekst)
                if self._opinie[i]:
                    self._kody[i] = self._opinie[i]
                    wypelnione += 1
        finally:
            postep.Destroy()

        wybrany = max(0, self._lista.GetSelection())
        self._lista.Set(self._etykiety())
        self._lista.SetSelection(wybrany)
        self._pokaz_pozycje(wybrany)
        self._lista.SetFocus()

        if przerwane_na is not None:
            tresc = t("poliglota.per_akapit_detektor_przerwane_tresc",
                      numer_akapitu=przerwane_na,
                      liczba_wypelnionych=wypelnione, liczba_akapitow=ile)
        else:
            tresc = t("poliglota.per_akapit_detektor_bilans_tresc",
                      liczba_wypelnionych=wypelnione, liczba_akapitow=ile,
                      liczba_bez_opinii=ile - wypelnione)
        wx.MessageBox(tresc, t("poliglota.per_akapit_detektor_bilans_tytul"),
                      wx.OK | wx.ICON_INFORMATION, self)

    def _on_ok(self, event: wx.Event) -> None:
        """Waliduje WSZYSTKIE kody przed zamknięciem; pierwszy zły → fokus tam.

        Normalizacja jest ta sama, co dla pola „Kod ISO" i dla Tłumacza AI
        (``tlumacz_ai.normalizuj_kod_jezyka``), więc dialog nie wprowadza
        drugiego rozumienia poprawnego kodu.
        """
        self._zapisz_biezacy()
        for i, kod in enumerate(self._kody):
            znormalizowany = tlumacz_ai.normalizuj_kod_jezyka(kod)
            if not znormalizowany:
                self._lista.SetSelection(i)
                self._pokaz_pozycje(i)
                wx.MessageBox(
                    t("poliglota.per_akapit_zly_kod_tresc",
                      numer_akapitu=i + 1, kod_iso=kod),
                    t("poliglota.per_akapit_zly_kod_tytul"),
                    wx.OK | wx.ICON_WARNING, self)
                self._txt_kod.SetFocus()
                return
            if znormalizowany != kod:
                self._kody[i] = znormalizowany
                self._odswiez_etykiete(i)
        event.Skip()        # domyślna obsługa ID_OK zamyka dialog


class PoliglotaPanel(wx.Panel):
    """Panel modułu „Poliglota AI" – cienka warstwa prezentacji.

    Obsługuje trzy tryby pracy, ale sam nie zawiera logiki przetwarzania:
        - Tłumacz AI (Anthropic Claude) – woła ``tlumacz_ai.tlumacz_dlugi_tekst``.
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
        # v19.1: wejście dla trybów BEZ API (Reżyser/Szyfrant). Dla `.md` to
        # wyrenderowany HTML, dla pozostałych rozszerzeń — to samo, co
        # `_file_content`. Tłumacz AI dostaje treść SUROWĄ: jego prompt wprost
        # obiecuje zachowanie tagów Markdowna, a render nadmuchałby płatny
        # payload (`## X` → `<h2>X</h2>`) bez żadnego zysku.
        self._tresc_pipeline: str = ""
        self._ext_pipeline: str = ""
        self._oryginalna_nazwa: str = "nieznany"
        self._plik_katalog: str = "."
        self._sciezka_oryginalu: str | None = None

        # Klient Anthropic (None → brak klucza, AI wyłączone)
        self._client = None
        self._api_dostepne: bool = False
        self._init_api()

        # Wątek tła tłumacza AI (referencja, by nie uruchamiać drugiego)
        self._worker_thread: threading.Thread | None = None

        # Aktywny język pipeline'u (akcenty/szyfry/cezar). Bez wczytanego
        # pliku domyślnie idzie z języka UI (gdy ma komplet reguł), żeby
        # użytkownik EN nie zobaczył polskich etykiet akcentów w combo.
        # 18.11: sterowany przez combo „Język przetwarzania" — pozycja
        # „Wykryj automatycznie" podmienia go po wczytaniu pliku wynikiem
        # ``wykryj_jezyk_zrodlowy()``, wybór ręczny jest wiążący (detekcja
        # przy wczytywaniu pomijana).
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

        # v18.24.2: akcent albo szyfr zepsuty w edytorze tekstu znikał z list
        # powyżej bez słowa wyjaśnienia (loader zwracał pusty słownik, a jego
        # `print` w buildzie `--windowed` nie ma gdzie trafić).
        gd.pokaz_raport_raz(self)

    # ------------------------------------------------------------------
    # Inicjowanie klienta Anthropic (Claude) — konsolidacja v18.x, Opcja A
    # ------------------------------------------------------------------
    def _init_api(self) -> None:
        app_dir = sciezki.KATALOG_BAZOWY_STR
        env_path = os.path.join(app_dir, self.ENV_FILENAME)
        if os.path.exists(env_path):
            load_dotenv(env_path)
            # v18.4 provider-agnostic (przez core_llm): domyślnie Anthropic Claude,
            # a przy LLM_PROVIDER=openai_compat dowolny endpoint zgodny z OpenAI.
            self._client = cl.zbuduj_klienta(cl.wczytaj_konfiguracje())
            self._api_dostepne = self._client is not None

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

        # 18.11: jawny wybór języka pipeline'u (reguły akcentów/szyfrów).
        # Pozycja 0 = „Wykryj automatycznie" (dotychczasowe zachowanie),
        # pozycje 1+ = kompletne języki bazowe pod nazwami natywnymi.
        lbl_jezyk_pipeline = wx.StaticText(
            self, label=t("poliglota.lbl_jezyk_pipeline"))
        self._jezyki_pipeline = core_poliglota.dostepne_jezyki_bazowe()
        wybory_jezyka = [t("poliglota.jezyk_auto")] + [
            core_poliglota.natywna_nazwa(kod) for kod in self._jezyki_pipeline]
        self._combo_jezyk = wx.ComboBox(
            self, choices=wybory_jezyka, style=wx.CB_READONLY,
            name=t("poliglota.combo_jezyk_name"))
        self._combo_jezyk.SetSelection(0)
        self._combo_jezyk.SetToolTip(t("poliglota.combo_jezyk_tooltip"))

        self._chk_wymus = wx.CheckBox(
            self, label=t("poliglota.chk_wymus"),
            name=t("poliglota.chk_wymus_name"))
        self._chk_wymus.SetToolTip(t("poliglota.chk_wymus_tooltip"))

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
        # Widoczność spina Cezara zależna od startowego wyboru szyfru
        # (pierwszy na liście nie musi być Cezarem).
        self._on_szyfr_change()

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
        main_sizer.Add(lbl_jezyk_pipeline,   flag=wx.LEFT | wx.RIGHT, border=BORDER)
        main_sizer.Add(self._combo_jezyk,    flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, border=8)
        main_sizer.Add(self._chk_wymus,      flag=wx.LEFT | wx.TOP | wx.RIGHT | wx.BOTTOM, border=BORDER)
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

        # 18.11: tryb quality (extended thinking). Checkbox widoczny zawsze —
        # etykieta mówi wprost, że na endpointach OpenAI-compatible nie ma
        # efektu (core_llm cicho ignoruje parametr, wzorzec segmenty/wymusz_json).
        self._chk_quality = wx.CheckBox(
            panel, label=t("poliglota.chk_quality"),
            name=t("poliglota.chk_quality_name"))
        self._chk_quality.SetToolTip(t("poliglota.chk_quality_tooltip"))

        sizer.Add(lbl,           flag=wx.BOTTOM, border=4)
        sizer.Add(self._txt_lang, flag=wx.EXPAND | wx.BOTTOM, border=8)
        sizer.Add(self._chk_quality)
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
        # BCP-47: najdłuższy akceptowany kod to język+pismo, np. "zh-Hans"
        # (7 znaków). Do v17.2 limit 2 blokował kody regionalne (issue #16).
        self._txt_iso.SetMaxLength(7)
        self._txt_iso.SetHint(t("poliglota.txt_iso_hint"))
        self._lbl_iso.Hide(); self._txt_iso.Hide()

        # v19.2: przelacznik trybu „kody per akapit". Odznaczony = bieg
        # sprzed 19.2 (jeden kod na caly plik, zero dodatkowych okien).
        # Zaznaczony = „Przetworz" otwiera dialog z lista akapitow. Stanu
        # NIE trzymamy miedzy biegami: lista jednostek powstaje dopiero
        # w momencie przetwarzania, wiec nie ma czego uniewazniac po
        # wczytaniu innego pliku (klasa bledu z checklisty audytu).
        self._chk_per_akapit = wx.CheckBox(
            panel, label=t("poliglota.chk_per_akapit"),
            name=t("poliglota.chk_per_akapit_name"))
        self._chk_per_akapit.SetToolTip(t("poliglota.chk_per_akapit_tooltip"))
        self._chk_per_akapit.Hide()

        sizer.Add(lbl,                     flag=wx.BOTTOM, border=4)
        sizer.Add(self._combo_akcent,      flag=wx.EXPAND | wx.BOTTOM, border=8)
        sizer.Add(self._lbl_iso,           flag=wx.BOTTOM, border=4)
        sizer.Add(self._txt_iso,           flag=wx.EXPAND)
        sizer.Add(self._chk_per_akapit,    flag=wx.TOP, border=8)
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

        self._lbl_cezar = wx.StaticText(
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
        sizer.Add(self._lbl_cezar,    flag=wx.BOTTOM, border=4)
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
        self._combo_szyfr.Bind(wx.EVT_COMBOBOX, self._on_szyfr_change)
        self._combo_jezyk.Bind(wx.EVT_COMBOBOX, self._on_jezyk_pipeline_change)

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

        # 19.1: guard rozszerzeń. Wildcard „Wszystkie pliki (*.*)" wpuszczał
        # dotąd cokolwiek, a silnik mielił to w ciszy — `.srt` czy `.py`
        # wychodziły jako HTML z surową składnią w treści. Nie odrzucamy:
        # przemielenie dowolnego tekstu jest legalnym użyciem, tylko nie może
        # być niejawne (zasada „zero ciszy"). Binaria odpadają osobno, na
        # `UnicodeDecodeError` z bloku niżej.
        _, ext = os.path.splitext(file_name)
        ext = ext.lower()
        if ext not in core_poliglota.EXT_OBSLUGIWANE:
            odpowiedz = wx.MessageBox(
                t("poliglota.ext_nieobslugiwane_tresc",
                  rozszerzenie=ext or t("poliglota.ext_brak"),
                  lista_rozszerzen=", ".join(core_poliglota.EXT_OBSLUGIWANE)),
                t("poliglota.ext_nieobslugiwane_tytul"),
                wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING, self)
            if odpowiedz != wx.YES:
                self._txt_file.SetFocus()
                return

        try:
            self._file_ext = ext
            if self._file_ext == ".docx":
                # v19.2: przez `core_poliglota.tekst_docx`, bo `doc.paragraphs`
                # pomija akapity z komórek tabel — podgląd i licznik znaków
                # gubiły całą treść tabel (zmierzone: 2 akapity z 8 na
                # dokumencie z jedną tabelą). Ten sam iterator, którym
                # stempluje `zapisz_wynik`.
                self._file_content = core_poliglota.tekst_docx(file_name)
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
        # 18.11: detekcja działa TYLKO przy combo w pozycji „Wykryj
        # automatycznie" — wybór ręczny jest wiążący. Dawny dialog YES/NO
        # (13.4) zredukowany do powiadomienia INFO: jawny wybór języka ma
        # teraz własne combo, więc pytanie dublowałoby kontrolkę, a dialog
        # INFO nadal jest jawnym sygnałem A11y, że etykiety akcentów/szyfrów
        # właśnie się zmieniły.
        if self._combo_jezyk.GetSelection() <= 0:
            wykryty = core_poliglota.wykryj_jezyk_zrodlowy(
                self._file_content,
                fallback=self._jezyk_aktywny,
            )
            if wykryty != self._jezyk_aktywny:
                self._jezyk_aktywny = wykryty
                self._odswiez_warianty()
                wx.MessageBox(
                    t(
                        "poliglota.wykryto_jezyk_tresc",
                        jezyk_wykryty=core_poliglota.natywna_nazwa(wykryty),
                    ),
                    t("poliglota.wykryto_jezyk_tytul"),
                    wx.OK | wx.ICON_INFORMATION, self,
                )

        # v19.1: Markdown dostaje render do HTML, ale dopiero na wejściu do
        # pipeline'u bez API (patrz `_tresc_pipeline`).
        self._przygotuj_tresc_pipeline(os.path.basename(file_name))

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

    def _przygotuj_tresc_pipeline(self, nazwa_pliku: str) -> None:
        """Ustala treść i rozszerzenie dla trybów BEZ API (Reżyser/Szyfrant).

        Dla `.md` renderuje Markdown → pełny HTML (`core_markdown`), bo inaczej
        surowa składnia jedzie do wyniku jako treść: zmierzone na 4 kB
        dokumentu — 18 linii z `---`, `- ` i `> `, które syntezator czyta na
        głos, plus zero nagłówków w wynikowym HTML-u (czytnik traci nawigację
        1–6/H). Reszta rozszerzeń przechodzi 1:1.

        Render jest GŁOŚNY w obie strony: sukces potwierdzamy dialogiem INFO
        (zmienia się format wyniku, więc użytkownik ma o tym wiedzieć), a brak
        biblioteki `markdown` — komunikatem błędu z degradacją do treści
        surowej, nigdy ciszą.
        """
        self._tresc_pipeline = self._file_content
        self._ext_pipeline = self._file_ext
        if self._file_ext != ".md":
            return
        try:
            self._tresc_pipeline = core_markdown.renderuj(
                self._file_content, self._jezyk_aktywny)
        except Exception as exc:
            wx.MessageBox(
                t("poliglota.md_render_blad_tresc", tresc_bledu=str(exc)),
                t("poliglota.md_render_blad_tytul"),
                wx.OK | wx.ICON_ERROR, self)
            return
        self._ext_pipeline = ".html"
        wx.MessageBox(
            t("poliglota.md_render_tresc", nazwa_pliku=nazwa_pliku),
            t("poliglota.md_render_tytul"),
            wx.OK | wx.ICON_INFORMATION, self)

    def _on_clear(self, _event: wx.Event) -> None:
        # 18.11 (audyt): guard is_alive — „Wyczyść" w trakcie tłumaczenia AI
        # zerował _plik_katalog/_oryginalna_nazwa/_file_content, a callbacki
        # końca wątku czytają je z instancji → ukończone (opłacone)
        # tłumaczenie lądowało w bieżącym katalogu roboczym z pustym
        # oryginałem; po wyczyszczeniu dało się też wczytać INNY plik
        # w trakcie pracy wątku.
        if self._worker_thread and self._worker_thread.is_alive():
            wx.MessageBox(t("poliglota.zajety_tresc"),
                          t("poliglota.zajety_tytul"),
                          wx.OK | wx.ICON_INFORMATION, self)
            return

        self._file_content      = ""
        self._file_ext          = ""
        self._tresc_pipeline    = ""
        self._ext_pipeline      = ""
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

        # 18.11: w trybie auto po wyczyszczeniu wróć do języka domyślnego
        # (UI), żeby język poprzedniego dokumentu nie „przyklejał się"
        # do panelu. Wybór ręczny zostaje nietknięty.
        if self._combo_jezyk.GetSelection() <= 0:
            domyslny = _wybierz_domyslny_jezyk_pipeline()
            if domyslny != self._jezyk_aktywny:
                self._jezyk_aktywny = domyslny
                self._odswiez_warianty()

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
        self._odswiez_dostepnosc_wymuszania()
        self.Layout()

    def _wymus_jezyk_do_opcji(self, opcje: dict) -> bool:
        """Wpisuje `wymus_jezyk` do opcji silnika; ``False`` = przerwij bieg.

        v19.1: wymuszenie ma znaczyc „ZERO detekcji", a przy combo na „Wykryj
        automatycznie" wymuszany jezyk sam pochodzi z detekcji przy wczytaniu.
        Dla dokumentu juz zaszyfrowanego (kanoniczny przypadek uzycia: nalozyc
        kolejna warstwe na szyfrogram) detektor zwraca przypadkowa paczke, wiec
        wymuszenie cicho nalozyloby ZLY alfabet. Zamiast zgadywac — mowimy to
        wprost i zatrzymujemy sie.
        """
        if not self._chk_wymus.GetValue():
            return True
        if self._combo_jezyk.GetSelection() <= 0:
            wx.MessageBox(t("poliglota.wymus_bez_jezyka_tresc"),
                          t("poliglota.wymus_bez_jezyka_tytul"),
                          wx.OK | wx.ICON_WARNING, self)
            self._combo_jezyk.SetFocus()
            return False
        opcje["wymus_jezyk"] = self._jezyk_aktywny
        return True

    def _odswiez_dostepnosc_wymuszania(self) -> None:
        """Wyszarza checkbox wymuszania języka tam, gdzie nie ma on efektu.

        18.11 (audyt): wymuszanie działa wyłącznie na ścieżkach z segmentacją
        (oczyszczenie/akcent/szyfry). Tłumacz AI go nie czyta, a Naprawiacz
        Tagów wraca przed segmentacją i stempluje cały dokument kodem z pola
        „Kod ISO" (v19.1 — bez detekcji per akapit). Aktywny checkbox bez
        efektu = etykieta kłamie — wyszarzamy zamiast udawać.
        """
        cfg = self._aktualny_wariant_akcentu()
        naprawiacz = bool(cfg and cfg.get("kategoria") == "naprawiacz")
        rez_mode = self._rb_rezyser.GetValue()
        szyf_mode = self._rb_szyfrant.GetValue()
        dziala = szyf_mode or (rez_mode and not naprawiacz)
        self._chk_wymus.Enable(dziala)

    def _on_akcent_change(self, _event: wx.Event | None = None) -> None:
        """Pokaż pole „Kod ISO" i przełącznik kodów per akapit — tylko dla
        wariantu Naprawiacz Tagów (A11y: NVDA nie ma ogłaszać kontrolek,
        które dla akcentu fonetycznego nic nie robią)."""
        cfg = self._aktualny_wariant_akcentu()
        pokaz_iso = bool(cfg and cfg.get("kategoria") == "naprawiacz")
        self._lbl_iso.Show(pokaz_iso)
        self._txt_iso.Show(pokaz_iso)
        self._chk_per_akapit.Show(pokaz_iso)
        self._odswiez_dostepnosc_wymuszania()
        self._pnl_rezyser.Layout()
        self.Layout()

    def _on_szyfr_change(self, _event: wx.Event | None = None) -> None:
        """Pokaż spin przesunięcia tylko dla szyfru Cezara (A11y: NVDA nie
        powinna ogłaszać pola, które dla innych szyfrów nic nie robi)."""
        cfg = self._aktualny_wariant_szyfru()
        pokaz_cezar = bool(cfg and cfg.get("algorytm") == "cezar")
        self._lbl_cezar.Show(pokaz_cezar)
        self._spin_cezara.Show(pokaz_cezar)
        self._pnl_szyfrant.Layout()
        self.Layout()

    def _odswiez_zakres_cezara(self) -> None:
        """Dopasuj zakres i etykietę spinu Cezara do języka pipeline'u.

        Zakres pochodzi z ``szyfry/cezar.yaml`` języka aktywnego i różni się
        per język, bo alfabety mają różną długość (it ±20 … ru ±59). Do
        v18.10 zakres był ustawiany tylko raz, w konstruktorze — po zmianie
        języka pipeline'u spinner blokował część legalnych przesunięć
        (it→ru) albo etykieta kłamała o zakresie (ru→it).
        """
        cezar_cfg = core_poliglota.wariant_po_id(
            core_poliglota.TRYB_SZYFRANT, self._jezyk_aktywny, "cezar") or {}
        min_pr = int(cezar_cfg.get("min_przesuniecie", -35))
        max_pr = int(cezar_cfg.get("max_przesuniecie",  35))
        self._spin_cezara.SetRange(min_pr, max_pr)
        # Jawny clamp — nie polegamy na platformowym zachowaniu SetRange
        # wobec wartości spoza nowego zakresu.
        self._spin_cezara.SetValue(
            max(min_pr, min(max_pr, self._spin_cezara.GetValue())))
        self._lbl_cezar.SetLabel(t(
            "poliglota.lbl_cezar",
            min_przesuniecie=min_pr,
            max_przesuniecie=max_pr,
        ))

    def _on_jezyk_pipeline_change(self, _event: wx.Event | None = None) -> None:
        """Reakcja na combo „Język przetwarzania" (18.11).

        Pozycja 0 („Wykryj automatycznie") przywraca dotychczasowe
        zachowanie: język z wczytanego pliku (jeśli jest), inaczej domyślny
        z języka UI. Pozycje 1+ ustawiają język na sztywno.
        """
        idx = self._combo_jezyk.GetSelection()
        if idx <= 0:
            if self._file_content:
                nowy = core_poliglota.wykryj_jezyk_zrodlowy(
                    self._file_content,
                    fallback=_wybierz_domyslny_jezyk_pipeline(),
                )
            else:
                nowy = _wybierz_domyslny_jezyk_pipeline()
        else:
            nowy = self._jezyki_pipeline[idx - 1]
        if nowy != self._jezyk_aktywny:
            self._jezyk_aktywny = nowy
            self._odswiez_warianty()

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

        # Zakres spinu Cezara zależy od alfabetu języka — odśwież przed
        # aktualizacją widoczności pól.
        self._odswiez_zakres_cezara()

        # Reset selekcji na indeks 0 unieważnia widoczność pól zależnych od
        # wariantu (ISO naprawiacza, spin Cezara) — odśwież je jawnie.
        self._on_akcent_change()
        self._on_szyfr_change()

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
            # Wspólny walidator BCP-47 z Tłumaczem AI: akceptuje "en", ale
            # też odmiany regionalne/pisma ("pt-BR", "zh-Hans") i normalizuje
            # wielkość liter ("pt-br" → "pt-BR").
            kod_iso = tlumacz_ai.normalizuj_kod_jezyka(self._txt_iso.GetValue())
            if not kod_iso:
                wx.MessageBox(t("poliglota.brak_iso_tresc"),
                              t("poliglota.brak_iso_tytul"),
                              wx.OK | wx.ICON_WARNING, self)
                self._txt_iso.SetFocus()
                return
            opcje["iso_reczne"] = kod_iso

        # 18.11: checkbox „wymuś język" pomija detekcję lingua per akapit —
        # cały dokument przechodzi przez reguły języka pipeline'u.
        # 19.1: wymaga jawnego wyboru języka (patrz `_wymus_jezyk_do_opcji`).
        if not self._wymus_jezyk_do_opcji(opcje):
            return

        # Ostrzeżenie o języku źródłowym (tylko dla akcentów; przy jawnym
        # wymuszeniu rozjazd detekcji z wyborem usera jest zamierzony —
        # ostrzeżenie byłoby szumem).
        if cfg.get("kategoria") == "akcent" and not self._chk_wymus.GetValue():
            self._maybe_ostrzez_o_jezyku_zrodla()

        # >>>> GŁÓWNE WYWOŁANIE SILNIKA <<<<
        try:
            wynik = core_poliglota.przetworz(
                self._tresc_pipeline,
                tryb=core_poliglota.TRYB_REZYSER,
                jezyk=self._jezyk_aktywny,
                wariant=cfg["id"],
                opcje=opcje,   # przez referencję — silnik dopisze kanał zwrotny
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

        # v19.2 (audyt): dialog kodów per akapit stoi NA KOŃCU, za całą
        # walidacją i za silnikiem. Otwarty wcześniej kazałby użytkownikowi
        # wypełnić kody, żeby po OK dostać komunikat o zupełnie innym polu
        # (np. o wymuszaniu języka) — i stracić całą tę pracę.
        kody_jednostek: list[str] | None = None
        if cfg.get("kategoria") == "naprawiacz":
            if not self._ostrzez_o_braku_tagu():
                return
            kody_jednostek = self._zbierz_kody_per_akapit(opcje["iso_reczne"])
            if kody_jednostek is False:
                return

        self._zakoncz_zapisem(wynik, cfg, opcje, tryb=core_poliglota.TRYB_REZYSER,
                              kody_jednostek=kody_jednostek)

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

        # 18.11: wymuszenie języka = jeden zestaw reguł (i jeden alfabet
        # Cezara) na cały dokument — warunek odwracalności szyfrowania
        # wielowarstwowego przy tekstach mieszanych językowo.
        # 19.1: wymaga jawnego wyboru języka (patrz `_wymus_jezyk_do_opcji`).
        if not self._wymus_jezyk_do_opcji(opcje):
            return

        # >>>> GŁÓWNE WYWOŁANIE SILNIKA <<<<
        try:
            wynik = core_poliglota.przetworz(
                self._tresc_pipeline,
                tryb=core_poliglota.TRYB_SZYFRANT,
                jezyk=self._jezyk_aktywny,
                wariant=cfg["id"],
                opcje=opcje,   # przez referencję — silnik dopisze kanał zwrotny
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
    # Naprawiacz Tagów – ostrzeżenie i kody per akapit
    # ------------------------------------------------------------------
    def _ostrzez_o_braku_tagu(self) -> bool:
        """Uprzedza, że dla tego rozszerzenia Naprawiacz NIE wstrzyknie tagu.

        v19.2, standard „zero ciszy". Guard rozszerzeń z 19.1 pyta przy
        WCZYTANIU, czy przemleć plik spoza listy — i to zostaje. Ale dla
        Naprawiacza konsekwencja jest mocniejsza niż dla akcentu: ścieżka
        „zapis surowy" nie stempluje ani jednej jednostki, więc operacja jest
        kompletnym no-opem, a aplikacja meldowała „sukces" i podawała ścieżkę
        pliku, który jest kopią 1:1 bez tagu językowego. Pytamy więc wprost.

        Returns:
            ``True`` gdy wolno kontynuować (rozszerzenie obsługiwane albo
            użytkownik potwierdził), ``False`` gdy bieg ma się zatrzymać.
        """
        if self._ext_pipeline in core_poliglota.EXT_OBSLUGIWANE:
            return True
        odpowiedz = wx.MessageBox(
            t("poliglota.naprawiacz_bez_tagu_tresc",
              rozszerzenie=self._ext_pipeline or t("poliglota.ext_brak"),
              lista_rozszerzen=", ".join(core_poliglota.EXT_OBSLUGIWANE)),
            t("poliglota.naprawiacz_bez_tagu_tytul"),
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING, self)
        return odpowiedz == wx.YES

    def _zbierz_kody_per_akapit(self, kod_domyslny: str):
        """Zwraca listę kodów z dialogu, ``None`` (tryb wyłączony) lub ``False``.

        ``False`` znaczy „użytkownik przerwał" i wywołujący ma zakończyć bieg
        bez zapisu — rozróżnienie jest istotne, bo ``None`` to legalny stan
        (jeden kod na cały plik), a pusta lista też (plik bez jednostek).
        """
        if not self._chk_per_akapit.GetValue():
            return None

        try:
            jednostki = core_poliglota.jednostki_jezykowe(
                self._tresc_pipeline, self._ext_pipeline, self._sciezka_oryginalu)
        except Exception as exc:
            wx.MessageBox(
                t("poliglota.blad_przetwarzania", tresc_bledu=str(exc)),
                t("poliglota.blad_wyniku_tytul"),
                wx.OK | wx.ICON_ERROR, self)
            return False

        if not jednostki:
            # Plik bez ani jednej jednostki (zapis surowy albo pusta treść) —
            # dialog byłby pustą listą, więc mówimy to wprost i wracamy do
            # trybu jednego kodu, zamiast pokazywać okno bez zawartości.
            wx.MessageBox(t("poliglota.per_akapit_brak_jednostek_tresc"),
                          t("poliglota.per_akapit_brak_jednostek_tytul"),
                          wx.OK | wx.ICON_INFORMATION, self)
            return None

        dlg = DialogKodyPerAkapit(self, jednostki, kod_domyslny)
        try:
            if dlg.ShowModal() != wx.ID_OK:
                return False
            return dlg.kody()
        finally:
            dlg.Destroy()

    # ------------------------------------------------------------------
    # Zapis rezultatu (Rezyser / Szyfrant – wspólne)
    # ------------------------------------------------------------------
    def _zakoncz_zapisem(self, wynik: str, cfg: dict,
                         opcje: dict, tryb: str,
                         kody_jednostek: list[str] | None = None) -> None:
        if not wynik and cfg.get("kategoria") != "naprawiacz":
            wx.MessageBox(t("poliglota.blad_wyniku_tresc"),
                          t("poliglota.blad_wyniku_tytul"),
                          wx.OK | wx.ICON_ERROR, self)
            return

        wariant_id = cfg["id"]
        # v19.2: nazwa pliku ma odbić RZECZYWISTY zbiór kodów, nie tylko ten
        # z pola „Kod ISO" (patrz `sufiks_nazwy_pliku`).
        if kody_jednostek:
            opcje["kody_jednostek"] = kody_jednostek
        iso  = core_poliglota.kod_iso(tryb, self._jezyk_aktywny, wariant_id, opcje)
        # 18.8: człony nazwy pliku w języku UI (klucze filename_* z ui.yaml) —
        # sanityzacja + fallback na polskie defaulty w bezpieczny_czlon_nazwy.
        slowa_nazw = {
            "naprawiony":  t("poliglota.filename_naprawiony"),
            "oczyszczony": t("poliglota.filename_oczyszczony"),
            "akcent":      t("poliglota.filename_akcent"),
            "szyfr":       t("poliglota.filename_szyfr"),
        }
        base = core_poliglota.sufiks_nazwy_pliku(
            tryb, self._jezyk_aktywny, wariant_id, self._oryginalna_nazwa, opcje,
            slowa=slowa_nazw)

        # 13.5: side-channel z core_poliglota._przetworz_* — mapa
        # (iso, fragment, czy_tekst) per akapit. Pozwala zapisz_wynik
        # wstrzyknąć tag lang per paragraf bez ponownej detekcji.
        segmenty_wynikowe = opcje.get("_segmenty_wynikowe")

        try:
            out_path = core_poliglota.zapisz_wynik(
                tresc_wynikowa=wynik,
                katalog_wyjscia=self._plik_katalog,
                base_name=base,
                ext=self._ext_pipeline,
                iso_code=iso,
                tryb=tryb,
                wariant_cfg=cfg,
                oryginalny_content=self._tresc_pipeline,
                sciezka_oryginalu=self._sciezka_oryginalu,
                segmenty_wynikowe=segmenty_wynikowe,
                kody_jednostek=kody_jednostek,
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

        app_dir = sciezki.KATALOG_BAZOWY_STR
        runtime_dir = os.path.join(app_dir, "runtime")

        self._worker_thread = threading.Thread(
            target=self._ai_worker,
            # Stan checkboxa quality czytany TU (wątek GUI), nie w workerze.
            args=(self._file_content, self._file_ext, target_lang, runtime_dir,
                  self._chk_quality.GetValue()),
            daemon=True,
        )
        self._worker_thread.start()

    def _ai_worker(self, content: str, ext: str,
                   target_lang: str, runtime_dir: str,
                   tryb_quality: bool) -> None:
        """Wątek tła – żaden bezpośredni wx.* (tylko przez wx.CallAfter!)."""

        def _cb_postep(info: tlumacz_ai.InfoPostepu) -> None:
            # InfoPostepu → natywny pasek z `poliglota.<klucz>` (mostek i18n,
            # jak przy błędach); `kwargs` podstawia {numer}/{ile}/{znaki}.
            wx.CallAfter(self._update_progress_label,
                         t(f"poliglota.{info.klucz_i18n}", **info.kwargs), info.procent)

        def _cb_blad_kryt(info: tlumacz_ai.InfoBleduTlumaczenia, partial: str) -> None:
            # Typowany błąd → natywny komunikat z `poliglota.<klucz>`; pusty klucz
            # = błąd nieoczekiwany → techniczny `detal` (EN) pod domyślnym nagłówkiem,
            # w polu do skopiowania (zgłoszenie issue).
            if info.klucz_i18n:
                wx.CallAfter(self._on_ai_error,
                             t(f"poliglota.{info.klucz_i18n}", **info.kwargs), partial)
            else:
                wx.CallAfter(self._on_ai_error, info.detal, partial,
                             t("poliglota.blad_ai_naglowek"))

        def _cb_blad_miekki(info: tlumacz_ai.InfoBleduTlumaczenia) -> None:
            naglowek = t(f"poliglota.{info.klucz_tytul}") if info.klucz_tytul else None
            wx.CallAfter(self._wyswietl_blad_ai,
                         t(f"poliglota.{info.klucz_i18n}", **info.kwargs), naglowek)

        # Siatka bezpieczeństwa wątku (v18.9): `tlumacz_dlugi_tekst` mapuje na
        # callbacki tylko błędy Z PĘTLI per blok. Wyjątek RZUCONY WCZEŚNIEJ
        # (np. `os.makedirs` na runtime_dir, inicjalizacja tiktoken, zapis
        # metryki cache) leciał dotąd do `threading.excepthook`, czyli w paczce
        # windowed donikąd — `_btn_process` zostawał wyłączony do restartu.
        try:
            wynik = tlumacz_ai.tlumacz_dlugi_tekst(
                tresc=content,
                jezyk_docelowy=target_lang,
                klient=self._client,
                runtime_dir=runtime_dir,
                oryginalna_nazwa=self._oryginalna_nazwa,
                on_postep=_cb_postep,
                on_blad_krytyczny=_cb_blad_kryt,
                on_blad_miekki=_cb_blad_miekki,
                slowo_tlumaczenie=core_poliglota.bezpieczny_czlon_nazwy(
                    t("poliglota.filename_tlumaczenie"), "tlumaczenie"),
                tryb_quality=tryb_quality,
            )
        except ct.BladTokenizeraOffline as exc:
            # v18.10: brak tabel BPE (chunking tiktoken) = brak Internetu —
            # natywny komunikat zamiast surowego tracebacku EN.
            bledy_ai.zapisz_diagnostyke(exc, "poliglota._ai_worker")
            wx.CallAfter(self._on_ai_error,
                         t("poliglota.err_tokenizer_offline"), "")
            return
        except Exception as exc:  # noqa: BLE001 — wątek nie może umrzeć po cichu
            bledy_ai.zapisz_diagnostyke(exc, "poliglota._ai_worker")
            wx.CallAfter(self._on_ai_error, str(exc), "",
                         t("poliglota.blad_ai_naglowek"))
            return

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

    def _on_ai_error(self, msg: str, partial_text: str = "",
                     naglowek: str | None = None) -> None:
        self._btn_process.Enable()
        self._gauge.Hide();        self._lbl_progress.Hide()
        self.Layout()

        if partial_text:
            self._txt_result.SetValue(partial_text)
            self._txt_result.SetFocus()

        self._wyswietl_blad_ai(msg, naglowek)

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
