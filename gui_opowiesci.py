"""
gui_opowiesci.py — Cienka warstwa widoku panelu „Interaktywne Opowieści" (wxPython).

Faza 1 wdrożenia v15.0 — szkielet UI z zaślepionymi callbackami. Kolejne fazy:
    • Faza 2: silnik LLM (``opowiesci_ai.py``), JSON-schema response, daemon thread.
    • Faza 3: engine + lifecycle plików (``core_opowiesci.py``):
              - ``opowiesci/[gra].txt`` (narracja bez meta-warningów)
              - ``runtime/opowiesci/[gra].game.json`` (pełny stan)
              - ``runtime/opowiesci/[gra].story.jsonl`` (append-only log tur)
              - ``runtime/opowiesci/[gra].mode`` (3=Swobodny, 4=Wybory, 5=Mniejsze zło;
                v17.4: własny folder, koniec współdzielenia z Reżyserem)
              (księga świata ``.md`` usunięta w v17.4 / P6A — była martwym mostem)
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

import json
import os
import threading
from typing import Any

import wx

import core_llm as cl
import opowiesci_ai as oai
import sciezki
import bledy_ai
from bledy_ai import BladGeneracjiAI
from core_opowiesci import ProjektOpowiesci
from i18n import aktualny_jezyk, t


# v15.1: skrót `narracja_skrot` (FIFO `ostatnie_tury` + pole „Ostatnia tura"
# po wczytaniu gry) tnie na granicy zdania, nie po sztywnym `[:N]`. Powód:
# stare `[:400]` ucinało w środku słowa/dialogu — nieprofesjonalny wygląd
# w widgecie po reloadzie. Limit znaków podniesiony do 1200, ale szukamy
# ostatniego `.!?` w drugiej połowie okna; fallback z elipsą tylko gdy
# w okrojonym fragmencie nie ma żadnego sensownego końca zdania.
_SKROT_MAX_ZN = 1200
_SKROT_MIN_PROG = 0.60   # nie cofaj się wcześniej niż 60% max_znakow


# v15.6: opt-in techniczna edycja stanu gry (`.game.json`) dla świadomych
# userów. Domyka dziurę, którą v15.5.1 tylko zamaskowała (ukryty „Odśwież
# z dysku" w Opowieściach — rekoncyliacja narracji NIE re-derywowała stanu
# strukturalnego, cichy dryf). Re-derywacja przez LLM odrzucona (koszt API,
# którego zwykły user nie oczekuje); zamiast tego dajemy bezpośrednią,
# walidowaną edycję surowego JSON-a.
#
# FLAGA ZASZYTA W KODZIE (NIE env-var, NIE user-facing): przycisk „Edytuj
# stan gry…" jest widoczny TYLKO gdy ta stała = True. Domyślnie False —
# zwykły end-user nigdy go nie zobaczy, bo ręczna edycja JSON to ryzyko
# uszkodzenia zapisu, na które świadomie wystawia się tylko techniczny user
# (modyfikuje stałą w źródle przed buildem własnej paczki).
EDYCJA_STANU_GRY_WIDOCZNA = False


def _skroc_na_granicy_zdania(tekst: str, max_znakow: int = _SKROT_MAX_ZN) -> str:
    """Skraca `tekst` do ~`max_znakow` znaków, tnąc na granicy zdania.

    Zwraca `tekst` w całości jeśli mieści się pod limit. W przeciwnym razie
    szuka ostatniego `.!?` w obrębie [`_SKROT_MIN_PROG` × max, max], po którym
    występuje whitespace, koniec stringa albo zamykający cudzysłów. Brak
    sensownej granicy → twardy cut z dopisanym `…` (sygnał dla NVDA i wzroku
    że to skrót).
    """
    if len(tekst) <= max_znakow:
        return tekst.rstrip()
    okrojony = tekst[:max_znakow]
    min_prog = int(max_znakow * _SKROT_MIN_PROG)
    najlepszy = -1
    for znak in (".", "!", "?"):
        idx = okrojony.rfind(znak)
        if idx < min_prog or idx <= najlepszy:
            continue
        kontynuacja = tekst[idx + 1 : idx + 2]
        if kontynuacja == "" or kontynuacja.isspace() or kontynuacja in ('"', "'", "”", "»", "’"):
            najlepszy = idx
    if najlepszy != -1:
        return tekst[: najlepszy + 1].rstrip()
    return okrojony.rstrip() + "…"


# v15.5: lustro `_skroc_na_granicy_zdania`, ale trzyma KONIEC tekstu — używane
# przy odświeżeniu narracji z dysku do wyciągnięcia świeżej końcówki dla
# `ostatnie_tury` (kontekst LLM). Limit spójny ze `_SKROT_MAX_ZN` (~1200) +
# zapas, bo to pojedynczy wpis kontekstu.
_FRAGMENT_MAX_ZN = 1500


def _ostatni_fragment(tekst: str, max_znakow: int = _FRAGMENT_MAX_ZN) -> str:
    """Zwraca KOŃCÓWKĘ `tekst` (~`max_znakow`), snapniętą do początku zdania.

    Cały `tekst` jeśli mieści się pod limitem. Inaczej bierze ostatnie
    `max_znakow` znaków i obcina wiodące zdanie urwane w połowie: szuka
    najwcześniejszej granicy `.!?` lub nowej linii w pierwszej połowie okna
    i zaczyna tuż za nią; brak granicy → samo okno (lstrip).
    """
    if len(tekst) <= max_znakow:
        return tekst.strip()
    okno = tekst[-max_znakow:]
    prog = max_znakow // 2
    najwczesniejszy = -1
    for znak in (".", "!", "?", "\n"):
        idx = okno.find(znak)
        if 0 <= idx <= prog and (najwczesniejszy == -1 or idx < najwczesniejszy):
            najwczesniejszy = idx
    if najwczesniejszy != -1:
        return okno[najwczesniejszy + 1:].strip()
    return okno.strip()


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

    # Slash-komendy (Faza 4). Klucze to zarówno warianty PL jak i EN-fallback —
    # gracz angielski w polskim UI nadal może pisać `/save`, `/quit` itd.
    # EN-fallback ZAWSZE aktywny, niezależnie od `i18n.AKTUALNY_JEZYK`.
    # Wartości to nazwy metod-handlerów na panelu (string, nie callable —
    # late-binding pozwala dispatcherowi reagować na metody dodane po init).
    _DISPATCH_KOMEND = {
        "/zapisz":     "_komenda_zapisz",
        "/save":       "_komenda_zapisz",
        "/wczytaj":    "_komenda_wczytaj",
        "/load":       "_komenda_wczytaj",
        "/wizualizuj": "_komenda_visualize",
        "/visualize":  "_komenda_visualize",
        "/koniec":     "_komenda_koniec",
        "/quit":       "_komenda_koniec",
        # v15.4: szybka pomoc — pokazuje listę dostępnych komend bez
        # konieczności wywoływania błędnej komendy. NVDA-friendly: dialog
        # MessageBox z TextCtrl readonly.
        "/pomoc":      "_komenda_pomoc",
        "/help":       "_komenda_pomoc",
        # v15.5: odświeżenie narracji z dysku po ręcznej edycji `.txt`.
        "/odswiez":    "_komenda_odswiez",
        "/refresh":    "_komenda_odswiez",
    }

    # Mapowanie kolorów dla wskaźnika pamięci modelu (analog `gui_rezyser._KOLORY_POZIOMOW`).
    _KOLORY_POZIOMOW = {
        oai.POZIOM_CZYSTA:      (0,   128, 0),
        oai.POZIOM_OK:          (0,   128, 0),
        oai.POZIOM_OSTRZEZENIE: (180, 100, 0),
        oai.POZIOM_ALARM:       (180, 0,   0),
    }

    def __init__(self, parent: wx.Window) -> None:
        super().__init__(parent, style=wx.TAB_TRAVERSAL)
        self.SetName(t("opowiesci.panel_name"))

        # Wzorzec z RezyserPanel: duży tekst opisu modułu z YAML, nie z kodu.
        # Pobieramy raz w konstruktorze — t() działa dopiero po
        # ``i18n.ustaw_jezyk()`` w main.main().
        self._tool_description = t("opowiesci.tool_description")

        # ---- Faza 2: stan silnika LLM (klient + niezmienny snapshot) -----
        # ``_snapshot`` żyje w pamięci panelu i jest zsynchronizowany z
        # ``_projekt`` (perzystencja na dysk). Liczniki tury startują od 0;
        # pierwsza akcja gracza inkrementuje do 1 przed wysyłką.
        self._client: Any = None
        self._api_dostepne: bool = False
        self._snapshot: oai.SnapshotOpowiesci = oai.SnapshotOpowiesci(
            nazwa_gry="", numer_tury=0,
        )
        self._worker_thread: threading.Thread | None = None

        # ---- Faza 3: perzystencja stanu (5 ścieżek na dysk) --------------
        # ``_projekt`` jest ``None`` dopóki gracz nie założy gry przyciskiem
        # „Nowa gra" albo nie wczyta starej. Bez tego ``_btn_wyslij`` /
        # ``_btn_zapisz`` są disabled — chronimy przed I/O bez nazwy.
        self._projekt: ProjektOpowiesci | None = None

        # Mirror pliku `.mode` w RAM. Trzyma utrwaloną decyzję trybu gry
        # (3=Swobodny, 4=Wyborów, 5=Mniejsze zło). Materializowany przy
        # założeniu nowej gry, wczytaniu istniejącej i ręcznym zapisie;
        # rozsynchronizowuje EnableItem RadioBoxa od bieżącego
        # `_rb_tryb.GetSelection()`, dzięki czemu zmiana trybu w trakcie
        # gry wymaga świadomej akcji przez dialog „Edytuj tryb gry"
        # (furtka na sytuacje awaryjne — np. AI nie chce zakończyć fabuły).
        self._zapisany_tryb: int | None = None

        # ---- Faza 4: slash-komendy + tiktoken + auto-streszczenie ---------
        # v15.1: brak globalnego pola `_aktualny_model` — model dobierany
        # automatycznie z trybu przez :meth:`_model_dla_trybu`. Powód:
        # gpt-4o-mini regularnie łamał zasady świata w trybach Wyborów /
        # Mniejszego zła (np. proponował opcje neutralne mimo wymogu
        # „wszystkie wybory niekorzystne"), więc tryb decyduje twardo.
        # Race-condition guard: streszczenie i cinematic warning to wywołania
        # LLM w wątku tła. Bez locka gracz mógłby spawnować drugie wywołanie
        # zanim pierwsze wróci, mutując ``_snapshot.ostatnie_tury`` w trakcie
        # czytania go przez wątek streszczeniowy.
        self._meta_w_toku: bool = False
        # Cinematic Warning pokazujemy DOKŁADNIE RAZ na grę (po 150. turze).
        # Persystowany w `_projekt.stan["cinematic_pokazany"]` — Faza 3
        # zapisuje cały dict `stan` do `.game.json`, więc rebuild po
        # wczytaniu odzyska informację.
        #
        # v15.2: flaga „w tej turze gracz wybrał Odkorkuj fiolkę". Ustawiana
        # w :meth:`_on_wybor_btn` gdy `id_wyboru == "0"`, zerowana w
        # :meth:`_obsluz_ture` po pomyślnej wymianie z LLM. Pomiędzy klikiem
        # a wysyłką gracz może edytować tekst akcji — flaga pamięta intencję
        # niezależnie od finalnej treści `_txt_akcja` (np. „Odkorkuję fiolkę
        # z drżącą ręką" wciąż liczy się jako użycie fiolki). Kliknięcie
        # innego wyboru po fiolce kasuje flagę (gracz zmienił zdanie).
        self._fiolka_klikneto_w_tej_turze: bool = False
        self._build_ui()
        self._bind_events()
        self._init_api()
        self._aktualizuj_uistate()

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

        sizer_naglowek       = self._zbuduj_naglowek(BORDER)
        sizer_pasek_pliku    = self._zbuduj_pasek_pliku(BORDER)
        sizer_tryb           = self._zbuduj_radiobox_trybu(BORDER)
        sizer_pamiec         = self._zbuduj_wskaznik_pamieci(BORDER)
        sizer_ostatnia_tura  = self._zbuduj_obszar_ostatnia_tura(BORDER)
        sizer_narracja       = self._zbuduj_obszar_narracji(BORDER)
        sizer_wybory         = self._zbuduj_obszar_wyborow(BORDER)
        sizer_akcja          = self._zbuduj_pole_akcji(BORDER)

        sep = lambda: wx.StaticLine(self)  # noqa: E731

        # Kolejność tabulacji (A11y krytyczna): pasek pliku → tryb → pamięć →
        # ostatnia tura (NVDA czyta świeżą scenę najpierw) → pełna narracja
        # (gracz może nawigować w głąb historii, ale to NIE pierwszy stop) →
        # wybory → pole akcji.
        root = wx.BoxSizer(wx.VERTICAL)
        root.Add(sizer_naglowek,                       flag=wx.EXPAND)
        root.Add(sizer_pasek_pliku,                    flag=wx.EXPAND)
        root.Add(sep(),                                flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=BORDER)
        root.Add(sizer_tryb,                           flag=wx.EXPAND)
        root.Add(sep(),                                flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=BORDER)
        root.Add(sizer_pamiec,                         flag=wx.EXPAND)
        root.Add(sep(),                                flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=BORDER)
        root.Add(sizer_ostatnia_tura,                  flag=wx.EXPAND)
        root.Add(sep(),                                flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=BORDER)
        root.Add(sizer_narracja,        proportion=3,  flag=wx.EXPAND)
        root.Add(sep(),                                flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=BORDER)
        root.Add(sizer_wybory,                         flag=wx.EXPAND)
        root.Add(sep(),                                flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=BORDER)
        root.Add(sizer_akcja,                          flag=wx.EXPAND)

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

        # 18.3: świadoma akcja zamknięcia gry — zastępuje kruchy guard
        # `_on_nazwa_gry_change`, który reagował na każdą zmianę pola nazwy
        # (ryzyko rozjazdu UI ze stanem przy edycji w trakcie wysyłki tury).
        # Filozofia hard-resetu Reżysera. Przycisk jest zawsze widoczny;
        # `_aktualizuj_uistate` aktywuje go (Enable) tylko gdy gra trwa, a pole
        # nazwy + Nowa gra + Wczytaj wyłącza. Enable/Disable zamiast Show/Hide —
        # nowsze NVDA pomija wyłączone kontrolki przy tabowaniu (spójnie z
        # Reżyserem, bez skakania layoutu).
        self._btn_zamknij_gre = wx.Button(self, label=t("opowiesci.btn_zamknij_gre_label"))
        self._btn_zamknij_gre.SetToolTip(t("opowiesci.btn_zamknij_gre_tooltip"))

        self._btn_zapisz = wx.Button(self, label=t("opowiesci.btn_zapisz_label"))
        self._btn_zapisz.SetToolTip(t("opowiesci.btn_zapisz_tooltip"))

        # v15.2.3: awaryjna edycja `opowiesci/<gra>.txt` w systemowym edytorze.
        # Konsystencja z Reżyserem (gui_rezyser._btn_otworz_narracje). W
        # Opowieściach dodajemy explicit ostrzeżenie o ryzyku rozjazdu z
        # `.game.json` (stan postaci, lokacji, ekwipunku) — `.txt` jest tylko
        # narracją dla TTS, a stan gry żyje w `.game.json`. Edycja `.txt`
        # nie aktualizuje stanu, więc kolejna tura LLM dostanie sytuację
        # świata sprzed edycji + nową narrację w polu — może powstać dryf.
        self._btn_otworz_narracje = wx.Button(self, label=t("opowiesci.btn_otworz_narracje_label"))
        self._btn_otworz_narracje.SetToolTip(t("opowiesci.btn_otworz_narracje_tooltip"))

        # v15.5: odświeżenie pamięci wewnętrznej po ręcznej edycji `.txt`
        # (np. ucięciu złamanego kinowego cięcia). Domyka cykl „Otwórz narrację
        # → edytuj → Odśwież z dysku" bez twardego resetu i wczytania gry.
        # P4 (v17.4): OPT-IN pod tą samą flagą `EDYCJA_STANU_GRY_WIDOCZNA` co
        # „Edytuj stan gry…". Rekoncyliacja wsiąka edytowaną narrację do
        # `ostatnie_tury`/`.game.json`, ale NIE re-derywuje `stan`,
        # `postacie_aktywne` ani liczników — powstaje cichy dryf między narracją
        # a stanem strukturalnym. v15.5.1 chowała przycisk bezwarunkowo; teraz,
        # gdy istnieje już ścieżka ręcznego domknięcia dryfu („Edytuj stan gry"),
        # odsłaniamy oba razem dla świadomego, technicznego usera (który modyfikuje
        # stałą w źródle przed buildem własnej paczki). Bez flagi przycisk
        # pozostaje ukryty, a handler `_on_odswiez_z_dysku` nie jest martwy.
        self._btn_odswiez_z_dysku = wx.Button(self, label=t("opowiesci.btn_odswiez_z_dysku_label"))
        self._btn_odswiez_z_dysku.SetToolTip(t("opowiesci.btn_odswiez_z_dysku_tooltip"))
        if not EDYCJA_STANU_GRY_WIDOCZNA:
            self._btn_odswiez_z_dysku.Hide()

        # v15.6: opt-in techniczna edycja `.game.json` (stała `EDYCJA_STANU_GRY_WIDOCZNA`).
        # Przycisk istnieje zawsze (spójny kod budowy paska), ale bez flagi jest
        # bezwarunkowo ukryty — `_aktualizuj_uistate` steruje jego Enable tylko gdy
        # flaga włączona. To NOWY przycisk, świadomie odrębny od „Odśwież z dysku":
        # semantyka inna (bezpośrednia edycja surowego stanu strukturalnego, nie
        # rekoncyliacja narracji), a handler-hook starego przycisku zostawiamy
        # nietknięty.
        self._btn_edytuj_stan = wx.Button(self, label=t("opowiesci.btn_edytuj_stan_label"))
        self._btn_edytuj_stan.SetToolTip(t("opowiesci.btn_edytuj_stan_tooltip"))
        if not EDYCJA_STANU_GRY_WIDOCZNA:
            self._btn_edytuj_stan.Hide()

        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(self._txt_nazwa_gry, proportion=1,
                flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=6)
        row.Add(self._btn_nowa_gra,
                flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=4)
        row.Add(self._btn_wczytaj,
                flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=4)
        row.Add(self._btn_zamknij_gre,
                flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=4)
        row.Add(self._btn_zapisz,
                flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=4)
        row.Add(self._btn_otworz_narracje,
                flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=4)
        row.Add(self._btn_odswiez_z_dysku,
                flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=4)
        row.Add(self._btn_edytuj_stan,
                flag=wx.ALIGN_CENTER_VERTICAL)

        # Faza 5: Quick Start preset picker — drugi wiersz w pasku.
        # Loading z YAML zamiast hardkodowanej listy: lingwista dorabiając
        # nowy zaczatek nie musi dotykać Pythona, tylko `zaczatki.yaml`.
        # ``_klucze_zaczatkow`` przechowuje kolejność (Choice używa indeksów).
        # v15.1: zaczątki ładowane z UI lang (fallback do PL przez `_zaladuj_przepis`).
        zaczatki_dict = oai._zaladuj_przepis(aktualny_jezyk(), "zaczatki").get("zaczatki", {})
        # Kolejność z YAML zachowana (Python 3.7+ dict insertion-order).
        self._klucze_zaczatkow: list[str] = list(zaczatki_dict.keys())
        # Pierwsza pozycja to „własna gra" (brak presetu, tryb z RadioBox-a).
        opcje_choice = [t("opowiesci.quick_start_wlasna")] + [
            zaczatki_dict[k]["etykieta"] for k in self._klucze_zaczatkow
        ]

        # P5 (v17.4): referencja na labelu zachowana (`_lbl_quick_start`) —
        # `_aktualizuj_uistate` chowa Quick Start (label + Choice) w trakcie
        # aktywnej gry. Presety mają sens tylko przy zakładaniu nowej gry;
        # w trakcie rozgrywki gracz nic z nimi nie zrobi, a NVDA i tak czytał
        # je przy tabulacji = szum.
        self._lbl_quick_start = wx.StaticText(self, label=t("opowiesci.lbl_quick_start"))
        self._choice_zaczatek = wx.Choice(
            self, choices=opcje_choice,
            name=t("opowiesci.choice_quick_start_name"),
        )
        self._choice_zaczatek.SetSelection(0)
        self._choice_zaczatek.SetToolTip(t("opowiesci.choice_quick_start_tooltip"))

        row_qs = wx.BoxSizer(wx.HORIZONTAL)
        row_qs.Add(self._lbl_quick_start, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=6)
        row_qs.Add(self._choice_zaczatek, proportion=1,
                   flag=wx.ALIGN_CENTER_VERTICAL)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(lbl_nazwa, flag=wx.LEFT | wx.RIGHT | wx.TOP,                 border=BORDER)
        sizer.Add(row,       flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM,  border=BORDER)
        sizer.Add(row_qs,    flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM,  border=BORDER)
        return sizer

    # ------------------------------------------------------------------
    # BLOK C — RadioBox wyboru trybu gry + przycisk Zasady świata (v15.1)
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

        # v15.1: przycisk otwierający dedykowane okno edycji zasad świata.
        # CELOWO nie wstawiamy inline TextCtrl w głównym panelu — wieloliniowe
        # pole byłoby Tab-pułapką dla NVDA przy każdej turze gry. Dialog
        # otwiera się tylko na żądanie, edycja zasad jest aktem okazjonalnym.
        self._btn_zasady_swiata = wx.Button(
            self, label=t("opowiesci.btn_zasady_swiata_label"),
        )
        self._btn_zasady_swiata.SetToolTip(t("opowiesci.btn_zasady_swiata_tooltip"))

        # Furtka awaryjna: przycisk odblokowujący zmianę trybu gry w trakcie
        # zabawy. Domyślnie ukryty — `_aktualizuj_uistate` pokazuje go gdy
        # projekt jest aktywny ORAZ `_zapisany_tryb` został utrwalony.
        # Powód istnienia furtki: AI sporadycznie odmawia zakończenia historii
        # w trybach z wyborami i gracz może chcieć przeskoczyć na Swobodny,
        # gdzie sam pisze finałową scenę. Dialog wymaga jawnej akceptacji
        # ostrzeżenia, żeby uniknąć przypadkowych zmian.
        self._btn_edytuj_tryb = wx.Button(
            self, label=t("opowiesci.btn_edytuj_tryb_label"),
        )
        self._btn_edytuj_tryb.SetToolTip(t("opowiesci.btn_edytuj_tryb_tooltip"))
        self._btn_edytuj_tryb.Hide()

        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(self._rb_tryb, proportion=1, flag=wx.EXPAND | wx.RIGHT, border=BORDER)
        row.Add(self._btn_zasady_swiata, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=BORDER)
        row.Add(self._btn_edytuj_tryb, flag=wx.ALIGN_CENTER_VERTICAL)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(row, flag=wx.EXPAND | wx.ALL, border=BORDER)
        return sizer

    # ------------------------------------------------------------------
    # BLOK D — Wskaźnik pamięci modelu (placeholder; pełna logika w Fazie 4)
    # ------------------------------------------------------------------
    def _zbuduj_wskaznik_pamieci(self, BORDER: int) -> wx.BoxSizer:
        lbl = wx.StaticText(self, label=t("opowiesci.pamiec_lbl"))

        self._gauge_pamiec = wx.Gauge(self, range=100, name=t("opowiesci.pamiec_gauge_name"))
        self._gauge_pamiec.SetValue(0)

        # P3 (v17.4): status pamięci to readonly `wx.TextCtrl`, nie `StaticText`
        # — parytet z Reżyserem (`_zbuduj_wskaznik_pamieci_modelu`) i zgodnie
        # z regułą A11y z CLAUDE.md (komunikaty techniczne → nawigowalne,
        # kopiowalne pole readonly, nie „aktualizuj label + ustaw fokus").
        # NO_BORDER + tło panelu maskują, że to pole edycji; treść ustawiamy
        # przez SetValue (NIE SetLabel) + SetForegroundColour dla poziomu.
        self._lbl_pamiec_status = wx.TextCtrl(
            self,
            value=t("opowiesci.pamiec_status_init"),
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.NO_BORDER,
            name=t("opowiesci.pamiec_status_name"),
        )
        self._lbl_pamiec_status.SetBackgroundColour(self.GetBackgroundColour())
        self._lbl_pamiec_status.SetMinSize((-1, 48))

        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(lbl,                flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=8)
        row.Add(self._gauge_pamiec, proportion=1,
                flag=wx.ALIGN_CENTER_VERTICAL)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(row, flag=wx.EXPAND | wx.ALL, border=BORDER)
        sizer.Add(
            self._lbl_pamiec_status,
            flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM,
            border=BORDER,
        )
        return sizer

    # ------------------------------------------------------------------
    # BLOK E1 — Obszar „Ostatnia tura" (skrót dla NVDA — czyta tylko świeżo
    # wygenerowany fragment, bez nawigowania przez setki linii historii)
    # ------------------------------------------------------------------
    def _zbuduj_obszar_ostatnia_tura(self, BORDER: int) -> wx.BoxSizer:
        lbl = wx.StaticText(self, label=t("opowiesci.lbl_ostatnia_tura"))
        lf = lbl.GetFont()
        lf.SetPointSize(11)
        lf.MakeBold()
        lbl.SetFont(lf)

        self._txt_ostatnia_tura = wx.TextCtrl(
            self,
            value=t("opowiesci.txt_ostatnia_tura_init"),
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_BESTWRAP,
            name=t("opowiesci.txt_ostatnia_tura_name"),
        )
        self._txt_ostatnia_tura.SetToolTip(t("opowiesci.txt_ostatnia_tura_tooltip"))
        # Mniejsza wysokość niż pełna narracja — to skrót, nie czytadło.
        self._txt_ostatnia_tura.SetMinSize((-1, 140))

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(lbl,                    flag=wx.LEFT | wx.RIGHT | wx.TOP,         border=BORDER)
        sizer.Add(self._txt_ostatnia_tura,
                  flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM,                  border=BORDER)
        return sizer

    # ------------------------------------------------------------------
    # BLOK E2 — Obszar pełnej narracji (TextCtrl readonly multiline) — KLUCZOWY A11y
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
        # Faza 3 dorobiła realny lifecycle plików — wszystkie callbacki
        # są podłączone do prawdziwych handlerów.
        self._btn_nowa_gra.Bind(wx.EVT_BUTTON, self._on_nowa_gra)
        self._btn_wczytaj.Bind(wx.EVT_BUTTON, self._on_wczytaj)
        self._btn_zapisz.Bind(wx.EVT_BUTTON, self._on_zapisz)
        # 18.3: zamknięcie aktywnej gry → powrót do stanu zakładania nowej.
        self._btn_zamknij_gre.Bind(wx.EVT_BUTTON, self._on_zamknij_gre)
        self._btn_otworz_narracje.Bind(wx.EVT_BUTTON, self._on_otworz_narracje)
        self._btn_odswiez_z_dysku.Bind(wx.EVT_BUTTON, self._on_odswiez_z_dysku)
        # v15.6: opt-in techniczna edycja `.game.json` (bind aktywny zawsze;
        # widoczność/Enable steruje `EDYCJA_STANU_GRY_WIDOCZNA` + `_aktualizuj_uistate`).
        self._btn_edytuj_stan.Bind(wx.EVT_BUTTON, self._on_edytuj_stan)
        self._btn_wyslij.Bind(wx.EVT_BUTTON, self._on_wyslij)
        # v15.1: edycja zasad świata przez dedykowany dialog.
        self._btn_zasady_swiata.Bind(wx.EVT_BUTTON, self._on_zasady_swiata)
        # Furtka awaryjna: ręczna zmiana trybu w trakcie aktywnej gry.
        self._btn_edytuj_tryb.Bind(wx.EVT_BUTTON, self._on_edytuj_tryb)
        # 18.3: ścieżka ekspercka (parytet z gui_rezyser._on_load) — Enter w polu
        # nazwy wczytuje grę o tej nazwie wprost, bez dialogu wyboru. Dawny guard
        # `_on_nazwa_gry_change` (reagujący na każdą zmianę pola) usunięty: w
        # trakcie gry pasek jest zwinięty do „Zamknij grę", więc pole nie jest
        # edytowalne podczas tury — znika ryzyko rozjazdu UI ze stanem.
        self._txt_nazwa_gry.Bind(wx.EVT_TEXT_ENTER, self._on_wczytaj)
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
        """Inicjuje klienta Anthropic (Claude) z ``golden_key.env``.

        v18.x (konsolidacja): cały moduł Opowieści woła Claude, więc
        :func:`opowiesci_ai.inicjalizuj_klienta` zwraca klienta Anthropic
        (``ANTHROPIC_API_KEY``/``sk-ant-``). Błąd ładowania nigdy nie blokuje
        otwarcia panelu — brak klucza → ``_api_dostepne`` zostaje ``False``,
        a :meth:`_on_wyslij` pokaże MessageBox z `opowiesci.brak_api_tresc`.
        Detekcja w silniku (testy izolowane korzystają z tej samej funkcji).
        """
        app_dir = sciezki.KATALOG_BAZOWY_STR
        klient = oai.inicjalizuj_klienta(app_dir)
        if klient is not None:
            self._client = klient
            self._api_dostepne = True

    def _aktualny_tryb_int(self) -> int:
        """Zwraca numer trybu (3/4/5) ze stanu RadioBox-a (indeks 0/1/2)."""
        return self._MAPA_TRYB_RB_NA_INT[self._rb_tryb.GetSelection()]

    @staticmethod
    def _model_dla_trybu(tryb: int) -> str:
        """Zwraca model LLM tury — jeden Claude dla WSZYSTKICH trybów.

        v18.x (konsolidacja na Anthropic, Opcja A): koniec model-per-tryb.
        GPT-4o-mini regularnie łamał zasady świata w trybach z wyborami (4/5)
        — proponował opcje neutralne mimo „wszystkie wybory niekorzystne".
        Analogicznie do migracji narracji Reżysera (v18.0) całość przechodzi
        na jeden, mocniejszy model (`claude-sonnet-5`), który ten problem
        usuwa. Argument ``tryb`` zachowany dla zgodności sygnatury wywołań.
        """
        _ = tryb  # zachowany dla zgodności sygnatury (jeden model dla wszystkich)
        return oai.MODEL_NARRACJA

    # ------------------------------------------------------------------
    # _on_wyslij: walidacja → spawn daemon thread → _wyslij_worker
    # ------------------------------------------------------------------
    def _on_wyslij(self, _event: wx.Event) -> None:
        """Handler przycisku „Wyślij" — bramka między GUI a wątkiem tła."""
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

        # Faza 4: slash-komendy są przechwytywane PRZED walidacją API/projektu.
        # `/koniec` działa nawet bez aktywnej gry; `/zapisz`, `/wizualizuj`
        # mają własne walidacje wewnątrz handlerów.
        if user_text.startswith("/"):
            self._txt_akcja.SetValue("")
            self._obsluz_komende(user_text)
            return

        if not self._api_dostepne:
            wx.MessageBox(
                t("opowiesci.brak_api_tresc"),
                t("opowiesci.brak_api_tytul"),
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return

        # Faza 3: bez aktywnej gry nie ma I/O. Walidacja nazwy przeszła
        # do `_on_nowa_gra` — tutaj sprawdzamy tylko czy projekt istnieje.
        if self._projekt is None:
            wx.MessageBox(
                t("opowiesci.brak_gry_tresc"),
                t("opowiesci.brak_gry_tytul"),
                wx.OK | wx.ICON_WARNING,
                self,
            )
            self._txt_nazwa_gry.SetFocus()
            return

        # Faza 4: alarm pamięci modelu — blokuj wysyłkę dopóki gracz nie
        # zwolni bufora (zakończy grę / wczyta nową). Auto-streszczenie
        # próbuje to robić same po `_obsluz_ture`, ale w razie awarii
        # streszczenia (rate limit, timeout) bufor zostaje pełny.
        status_pamieci = oai.oblicz_status_pamieci(
            self._snapshot, self._aktualny_tryb_int(), oai.MODEL_DOMYSLNY,
        )
        if status_pamieci.poziom == oai.POZIOM_ALARM:
            wx.MessageBox(
                t("opowiesci.alarm_blokada_tresc", procent=status_pamieci.procent),
                t("opowiesci.alarm_blokada_tytul"),
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return

        nazwa = self._projekt.nazwa_pliku
        tryb  = self._aktualny_tryb_int()

        # Aktualizujemy snapshot przed wysyłką: nazwa + nowy numer tury.
        # Snapshot jest niezmienny po stronie wątku tła, ale tutaj jeszcze
        # możemy mutować referencję panelu (GIL: pojedyncze przypisanie
        # atrybutu jest atomowe w CPythonie).
        # v15.1: zasady świata pobierane z `_projekt` (źródło prawdy po
        # edycji dialogiem), nie z `_snapshot` — gdyby user edytował zasady
        # w trakcie streszczenia, snapshot byłby stary.
        self._snapshot = oai.SnapshotOpowiesci(
            nazwa_gry=nazwa,
            numer_tury=self._snapshot.numer_tury + 1,
            ostatnie_tury=self._snapshot.ostatnie_tury,
            postacie_aktywne=self._snapshot.postacie_aktywne,
            stan_poprzedni=self._snapshot.stan_poprzedni,
            seed_swiata=self._snapshot.seed_swiata,
            jezyk_projektu=self._snapshot.jezyk_projektu,
            zasady_swiata=self._projekt.zasady_swiata,
            # carry-forward: surowy JSON ostatniej tury dożywa do tej wysyłki
            # (generuj_ture wstrzyknie go jako role=assistant).
            ostatni_surowy_json=self._snapshot.ostatni_surowy_json,
        )

        # v15.2: mechanika fiolki — wyliczana TYLKO w trybie Mniejsze zło.
        # `fiolka_aktywacja` — czy LLM ma wprowadzić fiolkę w tej turze
        # (próg z yaml osiągnięty, fiolka jeszcze nie obecna ani niezniszczona).
        # `fiolka_seed` — losowany Pythonem skutek odkorkowania (jeśli
        # gracz kliknął wybór 0). LLM dostaje gotowy seed; nie wymyśla
        # skutku samodzielnie. Oba bloki defaultem None/False — w trybach
        # 3/4 lecą jako no-op do generuj_ture.
        fiolka_aktywacja = False
        fiolka_seed: dict[str, str] | None = None
        if tryb == oai.TRYB_MNIEJSZE_ZLO:
            prog = oai.prog_aktywacji_fiolki(self._snapshot.jezyk_projektu or "pl")
            fiolka_aktywacja = oai.czy_fiolka_powinna_sie_pojawic(self._snapshot, prog)
            if self._fiolka_klikneto_w_tej_turze:
                # Bezpiecznik: gracz mógł kliknąć „Odkorkuj fiolkę" w turze
                # gdy fiolka NIE jest jeszcze obecna (race — przycisk powinien
                # być widoczny tylko gdy obecna, ale jeśli zniszczona w
                # poprzedniej turze a LLM nie usunął wyboru 0 z `wybory[]`,
                # mogłaby się prześlizgnąć). Losujemy seed tylko gdy obecna.
                fiolka_stan = (self._snapshot.stan_poprzedni or {}).get("fiolka") or {}
                if fiolka_stan.get("obecna") and not fiolka_stan.get("zniszczona"):
                    fiolka_seed = oai.wylosuj_seed_fiolki(
                        self._snapshot.jezyk_projektu or "pl"
                    )

        # Lock UI: zapobiega podwójnej wysyłce, dezorientacji NVDA.
        self._btn_wyslij.Disable()
        self._txt_akcja.SetValue("")
        self._lbl_pamiec_status.SetValue(t("opowiesci.status_wysylanie"))

        # Daemon thread — proces nie czeka na nas przy zamknięciu aplikacji.
        snapshot_kopia = self._snapshot
        self._worker_thread = threading.Thread(
            target=self._wyslij_worker,
            args=(snapshot_kopia, user_text, tryb, fiolka_aktywacja, fiolka_seed),
            daemon=True,
        )
        self._worker_thread.start()

    # ------------------------------------------------------------------
    # _wyslij_worker: w wątku tła; do GUI tylko przez wx.CallAfter
    # ------------------------------------------------------------------
    def _wyslij_worker(
        self,
        snapshot:         oai.SnapshotOpowiesci,
        user_input:       str,
        tryb:             int,
        fiolka_aktywacja: bool = False,
        fiolka_seed:      dict[str, str] | None = None,
    ) -> None:
        """Worker w tle — wątek nigdy nie dotyka widgetów wxPython bezpośrednio.

        Wszelka komunikacja z GUI idzie przez ``wx.CallAfter`` — gwarantuje
        wykonanie w wątku głównym (event loop wxPython jest single-threaded).
        Wzorzec z :meth:`gui_rezyser.RezyserPanel._wyslij_worker`.

        v15.2: parametry ``fiolka_aktywacja`` / ``fiolka_seed`` propagowane
        do :func:`opowiesci_ai.generuj_ture`. Domyślnie False/None — w trybach
        Swobodny/Wyborów no-op.
        """
        try:
            wynik = oai.generuj_ture(
                klient=self._client,
                snapshot=snapshot,
                user_input=user_input,
                tryb=tryb,
                model=self._model_dla_trybu(tryb),
                fiolka_aktywacja=fiolka_aktywacja,
                fiolka_seed=fiolka_seed,
            )
        except Exception as exc:  # noqa: BLE001
            # Łapiemy wszystko (RateLimitError, APITimeoutError, RuntimeError
            # po wyczerpaniu retry, JSONDecode, etc.) — kategoryzacja per typ
            # leży w :meth:`_obsluz_blad` żeby trzymać worker krótki.
            wx.CallAfter(self._obsluz_blad, exc)
            return

        # v17.11.1: LLM odmówił obsłużenia akcji gracza (free-text mógł być nie
        # na temat / niemożliwy do poprowadzenia). Odrzucenie idzie OSOBNĄ
        # ścieżką — NIE jest błędem (nie `_obsluz_blad`) ani sukcesem
        # (nie `_obsluz_ture`): tura „się nie wydarzyła".
        if wynik.odrzucone:
            wx.CallAfter(self._obsluz_odrzucenie, user_input)
            return

        wx.CallAfter(self._obsluz_ture, wynik, user_input, tryb)

    # ------------------------------------------------------------------
    # _obsluz_odrzucenie: callback w wątku UI — odmowa LLM (v17.11.1)
    # ------------------------------------------------------------------
    def _obsluz_odrzucenie(self, user_input: str) -> None:
        """Akcja gracza odrzucona przez LLM — tura nie liczy się i nic nie zapisuje.

        D5 (decyzja projektowa): odrzucona tura „się nie wydarzyła" — cofamy
        inkrementację `numer_tury` z `_on_wyslij` (linia ~825), żeby licznik
        tur i próg Cinematic Warning nie rosły od nieudanych prób. NIE dotykamy
        `.game.json` / `.story.jsonl` (synchronizacja dysku jest tylko w
        `_obsluz_ture`, którego tu świadomie nie wołamy). Przywracamy tekst do
        pola akcji, żeby gracz mógł go poprawić zamiast pisać od zera.
        """
        # Cofnięcie numeru tury (snapshot jest niezmienny — odtwarzamy z -1).
        self._snapshot = oai.SnapshotOpowiesci(
            nazwa_gry=self._snapshot.nazwa_gry,
            numer_tury=max(0, self._snapshot.numer_tury - 1),
            ostatnie_tury=self._snapshot.ostatnie_tury,
            postacie_aktywne=self._snapshot.postacie_aktywne,
            stan_poprzedni=self._snapshot.stan_poprzedni,
            seed_swiata=self._snapshot.seed_swiata,
            jezyk_projektu=self._snapshot.jezyk_projektu,
            zasady_swiata=self._snapshot.zasady_swiata,
            ostatni_surowy_json=self._snapshot.ostatni_surowy_json,
        )

        self._lbl_pamiec_status.SetValue(t("opowiesci.status_gotowe"))
        self._btn_wyslij.Enable()
        self._txt_akcja.SetValue(user_input)   # gracz poprawia, nie pisze od zera
        wx.MessageBox(
            t("opowiesci.odrzucenie_tresc"),
            t("opowiesci.odrzucenie_tytul"),
            wx.OK | wx.ICON_INFORMATION,
            self,
        )
        self._txt_akcja.SetFocus()

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

        # 1b. Pole „Ostatnia tura" — zastępujemy całość świeżym fragmentem.
        # NVDA usłyszy go natychmiast po focusie (wx.CallAfter w pkt 5 niżej),
        # bez konieczności nawigowania przez setki linii pełnej narracji.
        self._txt_ostatnia_tura.SetValue(naglowek.lstrip() + wynik.narracja)
        self._txt_ostatnia_tura.SetInsertionPoint(0)

        # 2. Aktualizacja snapshotu: nowe `ostatnie_tury` + postacie + stan.
        # Trzymamy ostatnie 6 par (akcja, narracja_skrót) — Faza 4 dorobi
        # streszczenie po 70% kontekstu; tu prosty FIFO.
        nowe_ostatnie = list(self._snapshot.ostatnie_tury)
        nowe_ostatnie.append({
            "akcja_gracza":  user_input,
            # v15.1: smart-trim na granicy zdania (`.!?`), limit ~1200 zn;
            # stary `[:400]` ucinał w środku słowa i wyglądał nieprofesjonalnie
            # w polu „Ostatnia tura" po wczytaniu gry.
            "narracja_skrot": _skroc_na_granicy_zdania(wynik.narracja),
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
            zasady_swiata=self._snapshot.zasady_swiata,
            # v17.9: surowy JSON WŁAŚNIE ukończonej tury — wejdzie jako
            # role=assistant do następnej tury (ciągłość + wzorzec struktury).
            ostatni_surowy_json=wynik.surowy_json,
        )

        # 3. Faza 3: synchronizacja stanu z dyskiem — 4 pliki per tura.
        # Kolejność jest istotna: NAJPIERW append do `.txt` (najszybciej
        # widoczny dla TTS jeśli ktoś otworzy plik bezpośrednio), POTEM
        # rebuild księgi świata, na końcu game.json + story.jsonl. Błąd
        # I/O w którymkolwiek kroku idzie w `_zglos_blad_zapisu` —
        # narracja jest już w UI, więc gracz nie traci tury.
        if self._projekt is not None:
            self._zsynchronizuj_projekt_z_wynikiem(
                wynik, user_input, tryb, naglowek,
            )

        # 4. Wybory: w trybie Swobodnym (3) zawsze ukryte, w 4/5 widoczne
        # tylko gdy LLM zwrócił niepustą tablicę (halucynacja → ukrywamy).
        self._przeladuj_wybory(wynik.wybory, tryb)

        # 4b. v15.2: reset flagi fiolki — kolejna tura zaczyna od czystego
        # stanu intencji. Gracz w nowej turze albo wybierze fiolkę znowu
        # (flag wraca przez _on_wybor_btn), albo coś innego.
        self._fiolka_klikneto_w_tej_turze = False

        # 5. Status + odblokowanie + dźwięk + fokus.
        self._btn_wyslij.Enable()
        wx.Bell()  # A11y: NVDA usłyszy „pinga" — sygnał gotowości
        # P1-min (v17.4): fokus na „Ostatnia tura", NIE na pełną narrację.
        # Pełna narracja (`_txt_narracja`) po AppendText + SetFocus stawia
        # kursor na początku — NVDA odczytałby historię od pierwszej linii
        # zamiast świeżej sceny. Pole „Ostatnia tura" trzyma wyłącznie skrót
        # właśnie wygenerowanej tury (SetInsertionPoint(0) w pkt 1b), więc to
        # ono jest właściwym celem fokusu po wysyłce.
        self._txt_ostatnia_tura.SetFocus()  # NVDA przeczyta świeżą turę od początku

        # 6. Faza 4: aktualizacja wskaźnika pamięci modelu (po update snapshotu).
        self._aktualizuj_pamiec_modelu()

        # 7. Cinematic Meta Warning po 150 turze (raz per gra). Persistujemy
        # flagę w `_projekt.stan["cinematic_pokazany"]` — Faza 3 zapisuje
        # cały stan do `.game.json`, więc po wczytaniu nie pokażemy ponownie.
        if (
            self._snapshot.numer_tury >= oai.TURY_DO_CINEMATIC
            and self._projekt is not None
            and not self._projekt.stan.get("cinematic_pokazany")
            and not self._meta_w_toku
        ):
            self._spawn_cinematic_warning()
            return   # cinematic warning blokuje resztę post-turn flow

        # 8. Auto-streszczenie po przekroczeniu progu pamięci (70%).
        # Robimy je AFTER Cinematic, żeby nie ucinać kontekstu który
        # cinematic zna jako tło (3 ostatnie tury).
        status_pamieci = oai.oblicz_status_pamieci(
            self._snapshot, tryb, oai.MODEL_DOMYSLNY,
        )
        if status_pamieci.poziom == oai.POZIOM_OSTRZEZENIE and not self._meta_w_toku:
            self._spawn_streszczenie()

    def _zsynchronizuj_projekt_z_wynikiem(
        self,
        wynik:              oai.WynikTury,
        user_input:         str,
        tryb:               int,
        naglowek:           str,
    ) -> None:
        """Wpisuje wynik tury w stan projektu i serializuje 4 pliki na dysk.

        Ten helper jest celowo wydzielony z :meth:`_obsluz_ture` — UI części
        nie da się testować bez wxPython, ale tę synchronizację tak.
        """
        assert self._projekt is not None, "wywoływane tylko gdy _projekt nie None"

        self._projekt.numer_tury       = self._snapshot.numer_tury
        self._projekt.tryb             = tryb
        self._projekt.postacie_aktywne = wynik.postacie_aktywne
        self._projekt.stan             = wynik.stan
        self._projekt.ostatnie_tury    = list(self._snapshot.ostatnie_tury)
        # v15.1: persistujemy wybory ostatniej tury, żeby po reloadzie gracz
        # w trybie 4/5 zobaczył te same przyciski (bez tego musiałby pisać
        # free-text dopóki nie zrobi pierwszej własnej akcji).
        self._projekt.ostatnie_wybory  = list(wynik.wybory)

        try:
            self._projekt.dopisz_do_txt(wynik.narracja, naglowek=naglowek)
            self._projekt.zapisz_game_json()
            self._projekt.dopisz_story_jsonl({
                "tura":          self._snapshot.numer_tury,
                "akcja_gracza":  user_input,
                "tryb":          tryb,
                "response_json": wynik.surowy_json,
            })
        except OSError as exc:
            self._wyswietl_blad_ai(t(
                "opowiesci.blad_zapisu_tresc",
                tresc_bledu=str(exc),
            ))

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
                # Closure z `tekst` ORAZ `id` — id potrzebne do rozpoznania
                # wyboru fiolki (`id="0"` w trybie 5, v15.2). Default args
                # w lambdzie chronią przed late-binding gotcha (każdy
                # przycisk dostaje SWOJE wartości, nie ostatnich z pętli).
                btn.Bind(
                    wx.EVT_BUTTON,
                    lambda evt, t_wyb=wybor["tekst"], id_wyb=wybor["id"]:
                        self._on_wybor_btn(evt, t_wyb, id_wyb),
                )
                self._sizer_wyborow.Add(btn, flag=wx.EXPAND | wx.ALL, border=4)

        self._panel_wyborow.Layout()
        self.Layout()
        self._aktywuj_obszar_wyborow(pokazac)

    def _on_wybor_btn(
        self,
        _event:       wx.Event,
        tekst_wyboru: str,
        id_wyboru:    str = "",
    ) -> None:
        """Klik na przycisku wyboru — natychmiast wysyła ten wybór jako turę.

        v18.x (przywrócona auto-wysyłka): klik = commit. To domyka separację
        ról aplikacji — w Reżyserze REŻYSERUJESZ (Burza Mózgów produkuje
        opcje-drafty do dalszej obróbki), a w Opowieściach GRASZ: wybór to
        ruch w grze, więc idzie do silnika od razu, bez kroku pośredniego.
        Spójne z głównym manualem (zalecany workflow) i z migracją na Anthropic
        — Claude rygorystycznie trzyma zasady świata, więc ręczna korekta
        fonetyki wyboru przed wysyłką nie jest już regułą, lecz wyjątkiem.

        Furtka edycji: gracz, który chce przeredagować ruch (np. zasady świata
        narzucają twardą fonetykę imienia, którą odmiana gramatyczna w tekście
        wyboru by zmiękczyła), NIE klika przycisku — wpisuje własną akcję
        wolnym tekstem w polu akcji i wysyła ją „Wyślij"/Enter. Free-text był i
        pozostaje zawsze dostępny; to on jest teraz ścieżką ręcznej korekty.
        (Dawne v15.1: klik tylko wpisywał tekst do pola i czekał na ręczną
        wysyłkę — zniesione, bo zacierało różnicę między rolą gracza a reżysera.)

        v15.2: parametr ``id_wyboru`` — gdy ``"0"`` (mechanika fiolki w
        trybie Mniejsze zło), ustawiamy ``_fiolka_klikneto_w_tej_turze=True``.
        Inny ID (A-E) zeruje flagę — gracz zmienił zdanie, fiolka nie idzie.
        Flagę ustawiamy PRZED wysyłką, bo `_on_wyslij` czyta ją przy budowie
        seeda fiolki w tej turze.

        Guard zajętości: auto-wysyłka odpala TYLKO gdy „Wyślij" jest aktywny.
        Gdy trwa tura albo auto-streszczenie w tle, przycisk jest wyłączony —
        a klik wyboru wywołuje `_on_wyslij` wprost, więc bez tego guardu
        obszedłby blokadę i odpalił drugiego workera (podwójna wysyłka, race
        na snapshot). W stanie zajętości zachowujemy więc dawne zachowanie:
        wpisujemy wybór do pola i dajemy fokus, a gracz wyśle go ręcznie, gdy
        panel się odblokuje (nic nie ginie).
        """
        self._fiolka_klikneto_w_tej_turze = (id_wyboru == "0")
        self._txt_akcja.SetValue(tekst_wyboru)
        if self._btn_wyslij.IsEnabled():
            self._on_wyslij(_event)
        else:
            self._txt_akcja.SetInsertionPointEnd()
            self._txt_akcja.SetFocus()

    # ------------------------------------------------------------------
    # _obsluz_blad: callback w wątku UI po wyjątku w workerze
    # ------------------------------------------------------------------
    def _obsluz_blad(self, exc: Exception) -> None:
        """Mapuje wyjątek na komunikat lokalizowany i pokazuje dialog."""
        # Błędy LLM są provider-agnostyczne (`core_llm`): limit→BladLimituLLM,
        # timeout→BladTimeoutLLM (działa tak samo dla Anthropic i OpenAI-compat).
        # Typowane błędy generacji AI (struktura/długość) niosą `klucz_i18n` —
        # mapujemy TYP na komunikat lokalizowany w namespace `opowiesci`, żeby
        # użytkownik nigdy nie zobaczył surowej, angielskiej treści technicznej.
        # `zapisz_diagnostyke` dopisuje tę treść do error_log.txt PRZED
        # zbudowaniem komunikatu — inaczej ginie bezpowrotnie (bug 2026-07-01).
        if isinstance(exc, BladGeneracjiAI):
            bledy_ai.zapisz_diagnostyke(exc, "opowiesci")
            msg = t(f"opowiesci.{exc.klucz_i18n}")
        elif isinstance(exc, cl.BladLimituLLM):
            msg = t("opowiesci.err_rate_limit")
        elif isinstance(exc, cl.BladTimeoutLLM):
            msg = t("opowiesci.err_timeout")
        else:
            msg = str(exc)

        self._lbl_pamiec_status.SetValue(t("opowiesci.status_blad"))
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

    # ==================================================================
    # FAZA 3 — Lifecycle plików (Nowa gra / Wczytaj / Zapisz)
    # ==================================================================
    def _aktualizuj_uistate(self) -> None:
        """Włącza/wyłącza przyciski zależnie od istnienia ``_projekt``.

        - Bez projektu: nie ma sensu pokazywać „Wyślij" ani „Zapisz" —
          gracz musi najpierw założyć grę albo wczytać starą. RadioBox
          ma wszystkie 3 pozycje aktywne (wolny wybór trybu nowej gry),
          przycisk furtki ukryty (nie ma czego edytować).
        - Z projektem: oba aktywne, RadioBox zsynchronizowany. Po utrwaleniu
          trybu (`_zapisany_tryb in (3,4,5)`) dwie pozostałe pozycje
          RadioBoxa są disabled, a furtka „Edytuj tryb gry…" widoczna —
          jedyna ścieżka do zmiany trybu w trakcie gry biegnie przez
          świadome potwierdzenie ostrzeżenia w dialogu.

        Wzorzec :meth:`gui_rezyser.RezyserPanel._refresh_ui_state`.
        """
        ma_projekt = self._projekt is not None
        self._btn_wyslij.Enable(ma_projekt)
        self._btn_zapisz.Enable(ma_projekt)
        # Otwórz plik narracji wymaga aktywnej gry (plik powstaje po
        # pierwszej turze — w nowo założonej, bez tury, sam handler
        # pokaże info zamiast otwarcia pustej ścieżki).
        self._btn_otworz_narracje.Enable(ma_projekt)
        # P4 + v15.6: „Odśwież z dysku" oraz „Edytuj stan gry…" są opt-in dla
        # technicznych userów — oba pod tą samą flagą `EDYCJA_STANU_GRY_WIDOCZNA`.
        # Rekoncyliacja narracji NIE re-derywuje stanu strukturalnego (cichy
        # dryf, patrz komentarz przy tworzeniu „Odśwież z dysku"), ale techniczny
        # user domyka dryf ręcznie przez „Edytuj stan gry" — dlatego wiążemy je
        # razem zamiast trzymać martwy, niewywoływalny handler. Enable tylko gdy
        # flaga włączona ORAZ jest aktywny projekt (bez gry nie ma `.game.json`
        # ani `.txt` do edycji/rekoncyliacji). Bez flagi oba pozostają ukryte
        # z konstruktora, więc Enable jest no-op.
        if EDYCJA_STANU_GRY_WIDOCZNA:
            self._btn_edytuj_stan.Enable(ma_projekt)
            self._btn_odswiez_z_dysku.Enable(ma_projekt)

        utrwalony = self._zapisany_tryb in self._MAPA_TRYB_RB_NA_INT
        if utrwalony:
            idx_utrwalony = self._MAPA_TRYB_RB_NA_INT.index(self._zapisany_tryb)
            for idx in range(self._rb_tryb.GetCount()):
                self._rb_tryb.EnableItem(idx, idx == idx_utrwalony)
        else:
            for idx in range(self._rb_tryb.GetCount()):
                self._rb_tryb.EnableItem(idx, True)

        # Furtka pojawia się tylko gdy faktycznie blokujemy zmianę trybu.
        # Przed startem gry (brak `_zapisany_tryb`) i po `/koniec` (reset
        # projektu) gracz ma swobodny wybór z poziomu RadioBoxa — dialog
        # byłby tu redundantny.
        self._btn_edytuj_tryb.Show(ma_projekt and utrwalony)

        # P5 (v17.4): Quick Start (label + Choice presetów) chowamy w trakcie
        # aktywnej gry — presety dotyczą wyłącznie zakładania nowej gry.
        self._lbl_quick_start.Show(not ma_projekt)
        self._choice_zaczatek.Show(not ma_projekt)

        # 18.3: pasek zakładania gry (nazwa + Nowa gra + Wczytaj) jest aktywny
        # tylko w stanie SETUP; w trakcie gry wyłączamy go i aktywujemy „Zamknij
        # grę". Enable/Disable zamiast Show/Hide — nowsze NVDA pomija wyłączone
        # kontrolki przy tabowaniu (niewidomy gracz ich nie napotka), a layout
        # nie skacze. Spójne z Reżyserem (`_txt_file_name.Enable(...)`,
        # `_btn_load.Enable(...)`). Quick Start (label + Choice) ZOSTAJE na
        # Show/Hide wyżej — to elementy bez sensu w trakcie rozgrywki.
        self._txt_nazwa_gry.Enable(not ma_projekt)
        self._btn_nowa_gra.Enable(not ma_projekt)
        self._btn_wczytaj.Enable(not ma_projekt)
        self._btn_zamknij_gre.Enable(ma_projekt)
        self.Layout()

    def _ustaw_rb_z_trybu(self, tryb_int: int) -> None:
        """RadioBox-owi ustawia indeks (0/1/2) na podstawie trybu (3/4/5)."""
        if tryb_int in self._MAPA_TRYB_RB_NA_INT:
            self._rb_tryb.SetSelection(self._MAPA_TRYB_RB_NA_INT.index(tryb_int))

    # ------------------------------------------------------------------
    # _on_nowa_gra: zakłada projekt + pliki (.game.json/.mode; .txt po 1. turze)
    # ------------------------------------------------------------------
    def _on_nowa_gra(self, _event: wx.Event) -> None:
        """Tworzy nową grę pod podaną nazwą.

        Walidacje:
        1. Niepusta nazwa.
        2. Jeśli `<nazwa>.game.json` już istnieje — confirmation dialog
           (gracz może chcieć kontynuować poprzednią; ostrzegamy że
           „Nowa gra" nadpisze stan zerowymi wartościami).
        """
        nazwa = self._txt_nazwa_gry.GetValue().strip()
        if not nazwa:
            wx.MessageBox(
                t("opowiesci.puste_nazwa_tresc"),
                t("opowiesci.puste_nazwa_tytul"),
                wx.OK | wx.ICON_WARNING,
                self,
            )
            self._txt_nazwa_gry.SetFocus()
            return

        app_dir = sciezki.KATALOG_BAZOWY_STR
        if ProjektOpowiesci.istnieje(nazwa, app_dir):
            potwierdzenie = wx.MessageBox(
                t("opowiesci.gra_istnieje_tresc", nazwa=nazwa),
                t("opowiesci.gra_istnieje_tytul"),
                wx.YES_NO | wx.ICON_WARNING | wx.NO_DEFAULT,
                self,
            )
            if potwierdzenie != wx.YES:
                return

        # Faza 5: Quick Start — jeśli wybrany preset, wstrzykuje seed_swiata
        # do projektu i nadpisuje wybrany tryb (tryb_domyslny presetu ma
        # priorytet nad RadioBox-em — preset zna swój gatunek lepiej niż
        # gracz, który mógł zostawić RadioBox na domyślnym).
        seed_swiata = ""
        idx_zaczatek = self._choice_zaczatek.GetSelection()
        if idx_zaczatek > 0:
            klucz = self._klucze_zaczatkow[idx_zaczatek - 1]
            preset = oai._zaladuj_przepis(aktualny_jezyk(), "zaczatki")["zaczatki"][klucz]
            seed_swiata = preset.get("seed_swiata", "").strip()
            tryb_preset = int(preset.get("tryb_domyslny", self._aktualny_tryb_int()))
            self._ustaw_rb_z_trybu(tryb_preset)

        tryb = self._aktualny_tryb_int()
        projekt = ProjektOpowiesci(app_dir)
        projekt.nazwa_pliku    = nazwa
        projekt.tryb           = tryb
        projekt.jezyk_projektu = aktualny_jezyk()   # v15.1: sync z UI lang
        projekt.seed_swiata    = seed_swiata

        try:
            projekt.zapisz_tryb(tryb)
            self._zapisany_tryb = tryb           # utrwalenie decyzji w RAM
            projekt.zapisz_game_json()           # initial state na dysku
            # v17.4 (P6A): brak rebuildu księgi świata — patrz core_opowiesci.
            # `.txt` nie tworzymy w „Nowa gra" — pierwsza tura LLM go założy
            # (`dopisz_do_txt` ma `mode="a"` z domyślnym tworzeniem pliku).
        except OSError as exc:
            self._wyswietl_blad_ai(t(
                "opowiesci.blad_zapisu_tresc",
                tresc_bledu=str(exc),
            ))
            return

        # Reset stanu pamięci: nowa gra → pusty snapshot (z seed_swiata jeśli był).
        # v15.1: świeży projekt nie ma zasad świata (`projekt.zasady_swiata = ""`),
        # więc snapshot startuje też z pustym polem (default w dataclass).
        self._projekt = projekt
        self._snapshot = oai.SnapshotOpowiesci(
            nazwa_gry=nazwa, numer_tury=0,
            seed_swiata=seed_swiata, jezyk_projektu=aktualny_jezyk(),
            zasady_swiata=projekt.zasady_swiata,
        )
        self._txt_narracja.SetValue(t("opowiesci.nowa_gra_zaczatek", nazwa=nazwa))
        self._txt_ostatnia_tura.SetValue(t("opowiesci.txt_ostatnia_tura_init"))
        self._aktywuj_obszar_wyborow(False)   # czysta gra → brak wyborów
        self._aktualizuj_uistate()

        wx.MessageBox(
            t("opowiesci.gra_nowa_tresc", nazwa=nazwa),
            t("opowiesci.gra_nowa_tytul"),
            wx.OK | wx.ICON_INFORMATION,
            self,
        )
        self._txt_akcja.SetFocus()

    # ------------------------------------------------------------------
    # Helper: zbiera dostępne gry do wczytania (A11y dialog wyboru)
    # ------------------------------------------------------------------
    def _zbierz_dostepne_gry(self) -> list[str]:
        """Skanuje folder `runtime/opowiesci/` i zwraca nazwy gier.

        Kryterium: plik `.game.json` (twarde źródło prawdy stanu gry —
        bez niego `ProjektOpowiesci.wczytaj` rzuci FileNotFoundError).
        Plik narracji `.txt` traktujemy jako opcjonalny, bo świeżo
        założone gry (przed pierwszą turą) jeszcze go nie mają.

        Zwraca pustą listę gdy folder nie istnieje lub jest pusty —
        wywołujący `_on_wczytaj` decyduje wtedy o komunikacie informacyjnym.
        """
        app_dir = sciezki.KATALOG_BAZOWY_STR
        runtime_op = os.path.join(app_dir, "runtime", "opowiesci")
        if not os.path.isdir(runtime_op):
            return []
        gry: list[str] = []
        sufiks = ".game.json"
        for nazwa_pliku in os.listdir(runtime_op):
            if not nazwa_pliku.endswith(sufiks):
                continue
            gry.append(nazwa_pliku[:-len(sufiks)])
        return sorted(gry)

    # ------------------------------------------------------------------
    # _on_wczytaj: SingleChoiceDialog → ProjektOpowiesci.wczytaj() → sync UI
    # ------------------------------------------------------------------
    def _on_wczytaj(self, _event: wx.Event) -> None:
        """Wczytuje grę. Dwie ścieżki UX (parytet z gui_rezyser._on_load):

        • pole nazwy PUSTE → dialog z listą gier (A11y — niewidomy gracz nie
          musi pamiętać i przepisywać nazwy pliku);
        • pole nazwy WYPEŁNIONE → bezpośrednie wczytanie tej nazwy (ścieżka
          eksperta — Enter w polu nazwy lub klik po wpisaniu z pamięci).

        v15.2.3: dialog to wx.SingleChoiceDialog (nie systemowy file picker) —
        NVDA czyta listę choice items naturalnie. Konsystentne z Reżyserem.
        """
        nazwa = self._txt_nazwa_gry.GetValue().strip()
        if nazwa:
            self._wczytaj_gre_po_nazwie(nazwa)   # ścieżka eksperta
            return

        gry = self._zbierz_dostepne_gry()
        if not gry:
            wx.MessageBox(
                t("opowiesci.brak_gier_tresc"),
                t("opowiesci.brak_gier_tytul"),
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            self._txt_nazwa_gry.SetFocus()
            return

        with wx.SingleChoiceDialog(
            self,
            t("opowiesci.dlg_wybierz_gre_lbl"),
            t("opowiesci.dlg_wybierz_gre_tytul"),
            gry,
        ) as dlg:
            # Lokalizacja etykiety „Cancel" — analogicznie jak w
            # gui_rezyser._on_load. wx.SingleChoiceDialog nie ma metody
            # SetCancelLabel, więc szukamy buttona po wx.ID_CANCEL i podmieniamy
            # label ręcznie. Bez tego polski user widzi „Cancel" na PL-systemie.
            btn_cancel = dlg.FindWindowById(wx.ID_CANCEL)
            if btn_cancel is not None:
                btn_cancel.SetLabel(t("common.btn_anuluj"))
            if dlg.ShowModal() != wx.ID_OK:
                return
            nazwa = dlg.GetStringSelection()

        self._wczytaj_gre_po_nazwie(nazwa)

    def _wczytaj_gre_po_nazwie(self, nazwa: str) -> None:
        """Wczytuje grę o podanej nazwie i wstawia ją do UI.

        Wspólny tor dla ścieżki eksperckiej (pole nazwy) i dialogu wyboru.
        Nieistniejąca/uszkodzona gra → `blad_wczytania_tresc` (np. literówka
        w nazwie wpisanej ręcznie).
        """
        app_dir = sciezki.KATALOG_BAZOWY_STR
        projekt = ProjektOpowiesci(app_dir)
        try:
            wynik = projekt.wczytaj(nazwa)
        except (FileNotFoundError, OSError, ValueError) as exc:
            self._wyswietl_blad_ai(t(
                "opowiesci.blad_wczytania_tresc",
                nazwa=nazwa,
                tresc_bledu=str(exc),
            ))
            return

        self._zaladuj_projekt_do_ui(projekt, wynik, nazwa)

        wx.MessageBox(
            t(
                "opowiesci.gra_wczytana_tresc",
                nazwa=nazwa,
                numer_tury=projekt.numer_tury,
            ),
            t("opowiesci.gra_wczytana_tytul"),
            wx.OK | wx.ICON_INFORMATION,
            self,
        )
        self._txt_akcja.SetFocus()

    def _zaladuj_projekt_do_ui(
        self,
        projekt: ProjektOpowiesci,
        wynik: Any,
        nazwa: str,
    ) -> None:
        """Synchronizuje cały widok z właśnie wczytanym projektem.

        Wspólny rdzeń wczytania gry — używany zarówno przez „Wczytaj"
        (:meth:`_on_wczytaj`), jak i przez opt-in techniczną edycję
        `.game.json` (:meth:`_on_edytuj_stan`), która po zapisie surowego
        JSON-a przeładowuje projekt z dysku i musi odświeżyć ten sam zestaw
        widgetów. Ustawia `_zapisany_tryb`, snapshot, nazwę, RadioBox trybu,
        narrację, „Ostatnią turę", przyciski wyborów oraz stan UI. NIE
        pokazuje komunikatu sukcesu — to robi wywołujący (różne treści
        per kontekst).
        """
        # Synchronizacja `_zapisany_tryb` z dysku — `.mode` ma priorytet
        # nad polem `tryb` w `.game.json` (analogicznie do `_ustaw_rb_z_trybu`
        # niżej). Brak `.mode` (stara gra) → fallback na `projekt.tryb`.
        tryb_utrwalony = wynik.saved_mode if wynik.saved_mode is not None else projekt.tryb
        if tryb_utrwalony in self._MAPA_TRYB_RB_NA_INT:
            self._zapisany_tryb = tryb_utrwalony
        else:
            self._zapisany_tryb = None

        # Sync UI ze stanem wczytanego projektu.
        # v15.1: zasady świata też wczytywane z `.game.json` (z fallbackiem
        # do "" dla starych zapisów bez tego pola).
        self._projekt = projekt
        self._snapshot = oai.SnapshotOpowiesci(
            nazwa_gry=projekt.nazwa_pliku,
            numer_tury=projekt.numer_tury,
            ostatnie_tury=list(projekt.ostatnie_tury),
            postacie_aktywne=list(projekt.postacie_aktywne),
            stan_poprzedni=dict(projekt.stan),
            seed_swiata=projekt.seed_swiata,
            jezyk_projektu=projekt.jezyk_projektu,
            zasady_swiata=projekt.zasady_swiata,
            # v17.9: po reloadzie wskrzeszamy surowy JSON ostatniej tury z
            # `.story.jsonl` (RAM go nie zna) — następna tura dostanie go jako
            # role=assistant. Brak/uszkodzony log → "" (bezpieczna degradacja).
            ostatni_surowy_json=projekt.ostatnia_tura_surowa(projekt.nazwa_pliku) or "",
        )

        self._txt_nazwa_gry.SetValue(projekt.nazwa_pliku)
        # Tryb: priorytet ma `.mode` (saved_mode); jeśli brak — z game.json.
        tryb_z_dysku = wynik.saved_mode if wynik.saved_mode is not None else projekt.tryb
        self._ustaw_rb_z_trybu(tryb_z_dysku)
        # Narracja: pełny tekst z `.txt` (lub fallback komunikat).
        if wynik.czy_narracja:
            self._txt_narracja.SetValue(projekt.full_story)
            self._txt_narracja.SetInsertionPointEnd()
        else:
            self._txt_narracja.SetValue(t("opowiesci.brak_narracji_info", nazwa=nazwa))

        # Pole „Ostatnia tura": pokażmy skrót ostatniej zapisanej tury, jeśli
        # istnieje w `ostatnie_tury` (snapshot wczytany z .game.json). Skrót
        # od v15.1 jest cięty na granicy zdania (`_skroc_na_granicy_zdania`,
        # ~1200 zn), więc nie urywa w środku słowa.
        if projekt.ostatnie_tury:
            ostatnia = projekt.ostatnie_tury[-1]
            self._txt_ostatnia_tura.SetValue(
                t("opowiesci.txt_ostatnia_tura_skrot_naglowek")
                + (ostatnia.get("narracja_skrot") or "")
            )
        else:
            self._txt_ostatnia_tura.SetValue(t("opowiesci.txt_ostatnia_tura_init"))

        # v15.1: wybory ostatniej tury są persystowane w `.game.json`, więc
        # po wczytaniu w trybie 4/5 przywracamy przyciski (gracz nie musi
        # pisać free-textu po reloadzie). `_przeladuj_wybory` sam ukryje
        # obszar dla trybu Swobodnego (3) i dla pustej listy.
        self._przeladuj_wybory(list(projekt.ostatnie_wybory), tryb_z_dysku)
        self._aktualizuj_uistate()
        self._lbl_pamiec_status.SetValue(t("opowiesci.status_gotowe"))

    # ------------------------------------------------------------------
    # _on_zapisz: ręczny dump game.json (autozapis działa po każdej turze)
    # ------------------------------------------------------------------
    def _on_zapisz(self, _event: wx.Event) -> None:
        """Wymusza dump `.game.json` na dysk.

        W normalnej rozgrywce każda tura sama zapisuje stan w
        :meth:`_zsynchronizuj_projekt_z_wynikiem` — ten przycisk jest
        zachowany dla parytetu z Reżyserem (gracz wie że ma kontrolę)
        i jako bezpieczna opcja przed zamknięciem aplikacji.
        """
        if self._projekt is None:
            wx.MessageBox(
                t("opowiesci.brak_gry_tresc"),
                t("opowiesci.brak_gry_tytul"),
                wx.OK | wx.ICON_WARNING,
                self,
            )
            return

        try:
            self._projekt.zapisz_game_json()
            tryb_aktualny = self._aktualny_tryb_int()
            self._projekt.zapisz_tryb(tryb_aktualny)
            self._zapisany_tryb = tryb_aktualny   # pokrywa też stare gry bez `.mode`
        except OSError as exc:
            self._wyswietl_blad_ai(t(
                "opowiesci.blad_zapisu_tresc",
                tresc_bledu=str(exc),
            ))
            return

        wx.MessageBox(
            t("opowiesci.gra_zapisana_tresc", nazwa=self._projekt.nazwa_pliku),
            t("opowiesci.gra_zapisana_tytul"),
            wx.OK | wx.ICON_INFORMATION,
            self,
        )

    # ------------------------------------------------------------------
    # v15.2.3 — awaryjne otwarcie pliku narracji w edytorze tekstu
    # ------------------------------------------------------------------
    def _on_otworz_narracje(self, _event: wx.Event) -> None:
        """Otwiera `opowiesci/<gra>.txt` w systemowym edytorze z ostrzeżeniem.

        Konsystencja z Reżyserem (gui_rezyser._on_otworz_narracje), ale z
        dodatkowym confirmation dialog — w Opowieściach .txt jest tylko
        narracją dla TTS, a źródłem prawdy stanu gry (postacie, lokacja,
        ekwipunek, wątki) jest `.game.json`. Edycja .txt nie aktualizuje
        stanu, więc kolejna tura LLM dostanie świat sprzed edycji + nową
        narrację — może powstać dryf semantyczny.

        Typowy use-case zgodny z designem: dopisanie ręcznej finałowej sceny
        gdy AI w trybie Wyborów/Mniejszego zła nie chce zakończyć historii
        (alternatywa dla furtki „Edytuj tryb gry…" → Swobodny).
        """
        if self._projekt is None:
            wx.MessageBox(
                t("opowiesci.brak_gry_tresc"),
                t("opowiesci.brak_gry_tytul"),
                wx.OK | wx.ICON_WARNING, self,
            )
            return
        nazwa = self._projekt.nazwa_pliku
        sciezka = self._projekt._sciezka_txt(nazwa)
        if not os.path.exists(sciezka):
            wx.MessageBox(
                t("opowiesci.plik_narracji_brak_tresc", nazwa=nazwa),
                t("opowiesci.plik_narracji_brak_tytul"),
                wx.OK | wx.ICON_INFORMATION, self,
            )
            return
        # Ostrzeżenie z YES_NO — Anuluj jako NO_DEFAULT (bezpieczna akcja).
        odp = wx.MessageBox(
            t("opowiesci.otworz_narracje_ostrzezenie_tresc"),
            t("opowiesci.otworz_narracje_ostrzezenie_tytul"),
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING, self,
        )
        if odp != wx.YES:
            return
        try:
            sciezki.otworz_w_systemie(sciezka)
        except Exception as exc:                                    # noqa: BLE001
            wx.MessageBox(
                t(
                    "opowiesci.blad_otwarcia_tresc",
                    sciezka_pliku=sciezka,
                    tresc_bledu=str(exc),
                ),
                t("opowiesci.blad_otwarcia_tytul"),
                wx.OK | wx.ICON_ERROR, self,
            )

    # ------------------------------------------------------------------
    # v15.5 — odświeżenie pamięci wewnętrznej z dysku (po ręcznej edycji .txt)
    # ------------------------------------------------------------------
    def _on_odswiez_z_dysku(self, _event: wx.Event) -> None:
        """Wczytuje ponownie `opowiesci/<gra>.txt` i uzgadnia kontekst LLM.

        Domyka cykl „Otwórz narrację → edytuj ręcznie → Odśwież z dysku" bez
        twardego resetu i ponownego wczytywania gry. Rekoncyliacja
        `ostatnie_tury`:
          * krótka historia (brak streszczenia) → nadpisujemy `narracja_skrot`
            ostatniego wpisu świeżą końcówką z dysku;
          * istnieje streszczenie (sentinel `AKCJA_STRESZCZENIE` na idx 0)
            zwinięte do 1 wpisu → DOPISUJEMY świeży wpis-końcówkę, streszczenie
            (stara wiedza) zostaje nietknięte;
          * streszczenie + późniejsze tury → nadpisujemy ostatnią turę.
        NIE rusza `stan` (lokacja, ekwipunek, wątki) ani `postacie_aktywne`
        w `.game.json` — to ostrzegamy w komunikacie (możliwy dryf).
        """
        if self._projekt is None:
            wx.MessageBox(
                t("opowiesci.brak_gry_tresc"),
                t("opowiesci.brak_gry_tytul"),
                wx.OK | wx.ICON_WARNING, self,
            )
            return
        worker_w_toku = bool(self._worker_thread and self._worker_thread.is_alive())
        if worker_w_toku or self._meta_w_toku:
            wx.MessageBox(
                t("opowiesci.odswiez_zajete_tresc"),
                t("opowiesci.odswiez_zajete_tytul"),
                wx.OK | wx.ICON_INFORMATION, self,
            )
            return
        try:
            full = self._projekt.przeladuj_narracje_z_dysku()
        except (FileNotFoundError, OSError, ValueError):
            wx.MessageBox(
                t("opowiesci.plik_narracji_brak_tresc", nazwa=self._projekt.nazwa_pliku),
                t("opowiesci.plik_narracji_brak_tytul"),
                wx.OK | wx.ICON_INFORMATION, self,
            )
            return

        # Narracja w widgecie.
        self._txt_narracja.SetValue(full)
        self._txt_narracja.SetInsertionPointEnd()

        # Rekoncyliacja kontekstu LLM (ostatnie_tury).
        tail = _ostatni_fragment(full)
        ot = list(self._snapshot.ostatnie_tury)
        ma_streszczenie = bool(ot) and ot[0].get("akcja_gracza") == oai.AKCJA_STRESZCZENIE
        if not ot:
            ot = [{"akcja_gracza": oai.AKCJA_SYNC, "narracja_skrot": tail}]
        elif ma_streszczenie and len(ot) == 1:
            ot.append({"akcja_gracza": oai.AKCJA_SYNC, "narracja_skrot": tail})
        else:
            ot[-1] = {
                "akcja_gracza":  ot[-1].get("akcja_gracza", oai.AKCJA_SYNC),
                "narracja_skrot": tail,
            }

        self._snapshot = oai.SnapshotOpowiesci(
            nazwa_gry=self._snapshot.nazwa_gry,
            numer_tury=self._snapshot.numer_tury,
            ostatnie_tury=ot,
            postacie_aktywne=list(self._snapshot.postacie_aktywne),
            stan_poprzedni=dict(self._snapshot.stan_poprzedni),
            seed_swiata=self._snapshot.seed_swiata,
            jezyk_projektu=self._snapshot.jezyk_projektu,
            zasady_swiata=self._snapshot.zasady_swiata,
            ostatni_surowy_json=self._snapshot.ostatni_surowy_json,  # carry-forward
        )

        # Pole „Ostatnia tura" — świeża końcówka (NVDA usłyszy po fokusie).
        self._txt_ostatnia_tura.SetValue(
            t("opowiesci.txt_ostatnia_tura_skrot_naglowek") + tail
        )
        self._txt_ostatnia_tura.SetInsertionPoint(0)

        # Persystencja kontekstu do `.game.json` (inaczej restart cofa efekt).
        self._projekt.ostatnie_tury = list(ot)
        try:
            self._projekt.zapisz_game_json()
        except OSError:
            pass
        self._aktualizuj_pamiec_modelu()

        tresc = (
            t("opowiesci.odswiez_streszczenie_tresc")
            if ma_streszczenie else
            t("opowiesci.odswiez_calosc_tresc")
        )
        wx.MessageBox(
            tresc,
            t("opowiesci.odswiez_z_dysku_tytul"),
            wx.OK | wx.ICON_INFORMATION, self,
        )
        self._txt_narracja.SetFocus()

    # ==================================================================
    # v15.6 — opt-in techniczna edycja stanu gry (`.game.json`)
    # ==================================================================
    def _on_edytuj_stan(self, _event: wx.Event) -> None:
        """Otwiera dialog bezpośredniej edycji surowego `.game.json`.

        Opt-in dla technicznego usera (stała `EDYCJA_STANU_GRY_WIDOCZNA`).
        Domyka dziurę po v15.5.1: „Odśwież z dysku" rekoncyliowało narrację,
        ale NIE re-derywowało stanu strukturalnego (postacie, lokacja,
        ekwipunek, wątki, liczniki). Tu user edytuje ten stan wprost.

        Flow:
          1. Dump bieżącego stanu z RAM na dysk (`zapisz_game_json`) — gwarantuje
             że edytowany tekst odzwierciedla żywą sesję, nie stary plik.
          2. Wczytanie surowego JSON-a do dialogu.
          3. Po OK (dialog waliduje, że tekst to parsowalny obiekt JSON) —
             zapis na dysk i PRZEŁADOWANIE projektu z dysku przez `wczytaj`,
             żeby RAM/snapshot/UI zgadzały się z nowym plikiem.

        Walidacja JSON jest KRYTYCZNA: uszkodzony `.game.json` wywaliłby
        kolejne `wczytaj`. Dialog nie pozwala zatwierdzić nieparsowalnej treści.
        """
        if self._projekt is None:
            wx.MessageBox(
                t("opowiesci.brak_gry_tresc"),
                t("opowiesci.brak_gry_tytul"),
                wx.OK | wx.ICON_WARNING, self,
            )
            return

        # Edycja w trakcie generowania tury/streszczenia = race: worker po
        # zakończeniu nadpisze `.game.json` własnym stanem, gubiąc edycję
        # (albo my nadpiszemy jego). Blokujemy — reuse komunikatu „w toku".
        worker_w_toku = bool(self._worker_thread and self._worker_thread.is_alive())
        if worker_w_toku or self._meta_w_toku:
            wx.MessageBox(
                t("opowiesci.odswiez_zajete_tresc"),
                t("opowiesci.odswiez_zajete_tytul"),
                wx.OK | wx.ICON_INFORMATION, self,
            )
            return

        sciezka = self._projekt._sciezka_game_json(self._projekt.nazwa_pliku)
        try:
            self._projekt.zapisz_game_json()   # snapshot RAM → dysk (i gwarancja istnienia pliku)
            with open(sciezka, "r", encoding="utf-8") as fh:
                surowy = fh.read()
        except OSError as exc:
            self._wyswietl_blad_ai(t(
                "opowiesci.blad_zapisu_tresc",
                tresc_bledu=str(exc),
            ))
            return

        dlg = DialogEdycjaStanuGry(self, initial_text=surowy)
        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()
            return
        nowy = dlg.tekst   # zwalidowany w dialogu: parsowalny obiekt JSON
        dlg.Destroy()

        try:
            with open(sciezka, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(nowy)
        except OSError as exc:
            self._wyswietl_blad_ai(t(
                "opowiesci.blad_zapisu_tresc",
                tresc_bledu=str(exc),
            ))
            return

        # Przeładowanie z dysku — RAM, snapshot i cały widok zgrane z nowym
        # plikiem (ten sam rdzeń co „Wczytaj").
        nazwa = self._projekt.nazwa_pliku
        app_dir = sciezki.KATALOG_BAZOWY_STR
        projekt = ProjektOpowiesci(app_dir)
        try:
            wynik = projekt.wczytaj(nazwa)
        except (FileNotFoundError, OSError, ValueError) as exc:
            self._wyswietl_blad_ai(t(
                "opowiesci.blad_wczytania_tresc",
                nazwa=nazwa,
                tresc_bledu=str(exc),
            ))
            return

        self._zaladuj_projekt_do_ui(projekt, wynik, nazwa)
        wx.MessageBox(
            t("opowiesci.edytuj_stan_zapisano_tresc", nazwa=nazwa),
            t("opowiesci.edytuj_stan_zapisano_tytul"),
            wx.OK | wx.ICON_INFORMATION, self,
        )
        self._txt_akcja.SetFocus()

    # ==================================================================
    # v15.1 — Zasady świata (dedykowany dialog, NIE inline TextCtrl)
    # ==================================================================
    def _on_zasady_swiata(self, _event: wx.Event) -> None:
        """Otwiera dialog edycji zasad świata gry.

        Zasady są opcjonalnym tekstem z regułami świata (fonetyka tożsamości,
        koncepcje kulturowe, ograniczenia mechaniczne), które silnik narracyjny
        respektuje przez całą grę. Wstrzykiwane do prompt-systemowy w
        :func:`opowiesci_ai._zbuduj_prompt_systemowy`.

        Wymóg: aktywna gra (`_projekt is not None`). Bez gry nie ma gdzie
        zapisać zasad (są w `.game.json` per nazwa gry).
        """
        if self._projekt is None:
            wx.MessageBox(
                t("opowiesci.zasady_bez_gry_tresc"),
                t("opowiesci.zasady_bez_gry_tytul"),
                wx.OK | wx.ICON_WARNING,
                self,
            )
            self._txt_nazwa_gry.SetFocus()
            return

        dlg = DialogZasadySwiata(self, initial_text=self._projekt.zasady_swiata)
        if dlg.ShowModal() == wx.ID_OK:
            nowe_zasady = dlg.tekst
            self._projekt.zasady_swiata = nowe_zasady
            # Propagacja do snapshotu — następna tura użyje już nowych zasad.
            self._snapshot = oai.SnapshotOpowiesci(
                nazwa_gry=self._snapshot.nazwa_gry,
                numer_tury=self._snapshot.numer_tury,
                ostatnie_tury=list(self._snapshot.ostatnie_tury),
                postacie_aktywne=list(self._snapshot.postacie_aktywne),
                stan_poprzedni=dict(self._snapshot.stan_poprzedni),
                seed_swiata=self._snapshot.seed_swiata,
                jezyk_projektu=self._snapshot.jezyk_projektu,
                zasady_swiata=nowe_zasady,
                ostatni_surowy_json=self._snapshot.ostatni_surowy_json,  # carry-forward
            )
            try:
                self._projekt.zapisz_game_json()
            except OSError as exc:
                self._wyswietl_blad_ai(t(
                    "opowiesci.blad_zapisu_tresc",
                    tresc_bledu=str(exc),
                ))
                dlg.Destroy()
                return
            wx.MessageBox(
                t("opowiesci.status_zasady_zapisane"),
                t("opowiesci.dlg_zasady_swiata_tytul"),
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
        dlg.Destroy()

    # ------------------------------------------------------------------
    # Furtka awaryjna: ręczna zmiana trybu w trakcie aktywnej gry
    # ------------------------------------------------------------------
    def _on_edytuj_tryb(self, _event: wx.Event) -> None:
        """Pokazuje dialog z 3 trybami i ostrzeżeniem o ryzyku zmiany w locie.

        Typowy use-case: gracz w trybie Wyborów / Mniejszego zła chce ręcznie
        wymusić zakończenie historii, ale AI uparcie generuje kolejne dylematy.
        Przeskok na Swobodny daje graczowi pełną kontrolę nad finałem.

        Po OK aktualizujemy `_zapisany_tryb`, `.mode` na dysku i RadioBox.
        Dialog wymaga jawnego potwierdzenia, żeby zmiana nie przeszła
        przypadkowo (np. przy bezmyślnym klikaniu w interfejs).
        """
        if self._projekt is None or self._zapisany_tryb not in self._MAPA_TRYB_RB_NA_INT:
            # Furtka nie powinna być widoczna w tym stanie (sprawdza
            # `_aktualizuj_uistate`), ale strzeżemy się na wypadek
            # nieprzewidzianego wywołania (np. skrót klawiszowy).
            return

        idx_obecny = self._MAPA_TRYB_RB_NA_INT.index(self._zapisany_tryb)
        choices = [
            t("opowiesci.tryb_swobodny"),
            t("opowiesci.tryb_wyborow"),
            t("opowiesci.tryb_mniejsze_zlo"),
        ]

        dlg = wx.Dialog(
            self,
            title=t("opowiesci.dlg_edytuj_tryb_tytul"),
            size=(560, 360),
        )
        ostrzezenie = wx.TextCtrl(
            dlg,
            value=t("opowiesci.dlg_edytuj_tryb_ostrzezenie"),
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.NO_BORDER,
            name=t("opowiesci.dlg_edytuj_tryb_ostrzezenie_name"),
        )
        ostrzezenie.SetBackgroundColour(dlg.GetBackgroundColour())
        ostrzezenie.SetMinSize((-1, 140))

        lbl = wx.StaticText(dlg, label=t("opowiesci.dlg_edytuj_tryb_lbl"))
        rb = wx.RadioBox(
            dlg,
            label=t("opowiesci.rb_tryb_label"),
            choices=choices,
            majorDimension=1,
            style=wx.RA_SPECIFY_COLS,
            name=t("opowiesci.dlg_edytuj_tryb_name"),
        )
        rb.SetSelection(idx_obecny)

        btn_ok = wx.Button(dlg, wx.ID_OK, label=t("opowiesci.dlg_edytuj_tryb_btn_ok"))
        btn_anuluj = wx.Button(dlg, wx.ID_CANCEL, label=t("opowiesci.dlg_edytuj_tryb_btn_anuluj"))
        btn_anuluj.SetDefault()   # Anuluj jest bezpieczną akcją domyślną

        btn_row = wx.BoxSizer(wx.HORIZONTAL)
        btn_row.AddStretchSpacer()
        btn_row.Add(btn_anuluj, flag=wx.RIGHT, border=8)
        btn_row.Add(btn_ok)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(ostrzezenie, proportion=1, flag=wx.EXPAND | wx.ALL, border=8)
        sizer.Add(lbl,    flag=wx.LEFT | wx.RIGHT | wx.TOP, border=8)
        sizer.Add(rb,     flag=wx.EXPAND | wx.ALL, border=8)
        sizer.Add(btn_row, flag=wx.EXPAND | wx.ALL, border=8)
        dlg.SetSizer(sizer)

        # NVDA czyta najpierw ostrzeżenie (ważne dla świadomej decyzji).
        ostrzezenie.SetFocus()

        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()
            return

        nowy_tryb = self._MAPA_TRYB_RB_NA_INT[rb.GetSelection()]
        dlg.Destroy()

        if nowy_tryb == self._zapisany_tryb:
            return   # gracz potwierdził ten sam tryb — brak operacji

        try:
            self._projekt.zapisz_tryb(nowy_tryb)
        except OSError as exc:
            self._wyswietl_blad_ai(t(
                "opowiesci.blad_zapisu_tresc",
                tresc_bledu=str(exc),
            ))
            return

        self._zapisany_tryb = nowy_tryb
        self._projekt.tryb = nowy_tryb
        self._ustaw_rb_z_trybu(nowy_tryb)
        self._aktualizuj_uistate()

        wx.MessageBox(
            t("opowiesci.status_tryb_zmieniony", tryb_nazwa=choices[rb.GetSelection()].replace("&", "")),
            t("opowiesci.dlg_edytuj_tryb_tytul"),
            wx.OK | wx.ICON_INFORMATION,
            self,
        )

    def _on_zamknij_gre(self, _event: wx.Event) -> None:
        """Zamyka aktywną grę i wraca do stanu zakładania nowej (setup).

        Zastępuje dawny guard na polu nazwy (18.3). Gra jest zapisywana na
        dysku po KAŻDEJ turze (`.game.json`), więc zamknięcie jest
        NIEDESTRUKCYJNE — można ją wczytać ponownie przyciskiem „Wczytaj".
        Mimo to prosimy o potwierdzenie (A11y: świadoma zmiana kontekstu),
        spójnie z filozofią hard-resetu Reżysera. Po potwierdzeniu czyścimy
        projekt, mirror trybu (`_zapisany_tryb`) i snapshot, a
        `_aktualizuj_uistate` rozwija pasek zakładania gry z powrotem
        (odblokowując wybór trybu i Quick Start).
        """
        if self._projekt is None:
            return
        odp = wx.MessageBox(
            t("opowiesci.zamknij_gre_pytanie"),
            t("opowiesci.zamknij_gre_pytanie_tytul"),
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING,
            self,
        )
        if odp != wx.YES:
            return

        self._projekt = None
        self._zapisany_tryb = None
        self._snapshot = oai.SnapshotOpowiesci(nazwa_gry="", numer_tury=0)
        self._txt_nazwa_gry.SetValue("")
        self._txt_narracja.SetValue("")
        self._txt_ostatnia_tura.SetValue(t("opowiesci.txt_ostatnia_tura_init"))
        self._txt_akcja.SetValue("")
        self._choice_zaczatek.SetSelection(0)
        self._aktywuj_obszar_wyborow(False)
        self._aktualizuj_uistate()
        self._txt_nazwa_gry.SetFocus()

    # ==================================================================
    # FAZA 4 — Slash-komendy (parser lokalny, bez API)
    # ==================================================================
    def _lista_komend_widoczna(self) -> str:
        """Lista komend do dialogu pomocy / komunikatu „nieznana komenda".

        Komenda `/odswiez` (`/refresh`) jest opt-in pod flagą
        `EDYCJA_STANU_GRY_WIDOCZNA` (tak jak przyciski „Odśwież z dysku" /
        „Edytuj stan gry"), bo rekoncyliacja narracji z dysku NIE re-derywuje
        stanu strukturalnego — grozi cichym dryfem semantycznym. Gdy flaga jest
        wyłączona:
          • we frozen exe wiersz `/odswiez` znika całkowicie (end-user nigdy go
            nie zobaczy — komenda zachowuje się jak nieznana);
          • ze źródła (dev) wiersz znika z bazowej listy, ale doklejamy dopisek
            mówiący, którą flagę włączyć, by ją odblokować.
        Token `/refresh` nie jest tłumaczony, więc filtr wiersza działa
        identycznie we wszystkich językach (zero zależności od listy w ui.yaml).
        """
        lista = t("opowiesci.komendy_dostepne_lista")
        if EDYCJA_STANU_GRY_WIDOCZNA:
            return lista
        widoczne = [w for w in lista.splitlines() if "/refresh" not in w]
        baza = "\n".join(widoczne)
        if not sciezki.JEST_FROZEN:
            baza = baza + "\n" + t("opowiesci.komenda_odswiez_zablokowana_hint")
        return baza

    def _obsluz_komende(self, user_text: str) -> None:
        """Dispatcher slash-komend. Wzorzec PL+EN fallback.

        Tokenizacja: pierwsze słowo to nazwa komendy, reszta jest argumentem
        (np. ``/wizualizuj jak wygląda strażnik" → komenda='/wizualizuj',
        arg='jak wygląda strażnik'). Komendy nieznane → MessageBox z listą.
        """
        # Pierwsze słowo (do whitespace) — komenda; reszta — argument.
        czesci = user_text.split(None, 1)
        komenda = czesci[0].lower()
        arg = czesci[1] if len(czesci) > 1 else ""

        nazwa_handlera = self._DISPATCH_KOMEND.get(komenda)
        # 18.3: bramka dryfu — `/odswiez`|`/refresh` działa tylko gdy włączona
        # flaga EDYCJA_STANU_GRY_WIDOCZNA (jak przyciski technicznej edycji
        # stanu). Bez flagi: we frozen exe traktujemy jak nieznaną komendę
        # (niewidoczna dla end-usera), ze źródła pokazujemy, jak ją odblokować.
        if nazwa_handlera == "_komenda_odswiez" and not EDYCJA_STANU_GRY_WIDOCZNA:
            if sciezki.JEST_FROZEN:
                nazwa_handlera = None
            else:
                wx.MessageBox(
                    t("opowiesci.komenda_odswiez_zablokowana_tresc", komenda=komenda),
                    t("opowiesci.komenda_odswiez_zablokowana_tytul"),
                    wx.OK | wx.ICON_INFORMATION,
                    self,
                )
                return

        if nazwa_handlera is None:
            wx.MessageBox(
                t(
                    "opowiesci.komenda_nieznana_tresc",
                    komenda=komenda,
                    lista=self._lista_komend_widoczna(),
                ),
                t("opowiesci.komenda_nieznana_tytul"),
                wx.OK | wx.ICON_WARNING,
                self,
            )
            return

        # Late-binding: handler może być dodany przez subclass lub mockiem
        # w teście — `getattr` pozwala na to, statyczna referencja by nie.
        handler = getattr(self, nazwa_handlera)
        handler(arg)

    def _komenda_zapisz(self, _arg: str) -> None:
        """`/zapisz` / `/save` — proxy do :meth:`_on_zapisz`."""
        self._on_zapisz(None)

    def _komenda_wczytaj(self, _arg: str) -> None:
        """`/wczytaj` / `/load` — proxy do :meth:`_on_wczytaj`."""
        self._on_wczytaj(None)

    def _komenda_odswiez(self, _arg: str) -> None:
        """`/odswiez` / `/refresh` — proxy do :meth:`_on_odswiez_z_dysku`.

        Opt-in pod `EDYCJA_STANU_GRY_WIDOCZNA` (główna bramka w
        :meth:`_obsluz_komende`); ten warunek to druga linia obrony na wypadek
        wywołania handlera z innego miejsca.
        """
        if not EDYCJA_STANU_GRY_WIDOCZNA:
            return
        self._on_odswiez_z_dysku(None)

    def _komenda_koniec(self, _arg: str) -> None:
        """`/koniec` / `/quit` — zamyka aplikację."""
        wx.GetTopLevelParent(self).Close()

    def _komenda_pomoc(self, _arg: str) -> None:
        """`/pomoc` / `/help` — pokazuje listę dostępnych slash-komend (v15.4).

        Wzorzec ten sam co przy nieznanej komendzie, tylko proaktywnie.
        Dialog readonly z `wx.TextCtrl` (NVDA-friendly) zamiast MessageBoxa,
        bo lista jest wielolinijkowa.
        """
        dlg = wx.Dialog(self, title=t("opowiesci.dlg_pomoc_tytul"), size=(640, 420))
        sizer = wx.BoxSizer(wx.VERTICAL)
        lbl = wx.StaticText(dlg, label=t("opowiesci.dlg_pomoc_lbl"))
        txt = wx.TextCtrl(
            dlg, value=self._lista_komend_widoczna(),
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_BESTWRAP,
            name=t("opowiesci.dlg_pomoc_name"),
        )
        btn_ok = wx.Button(dlg, wx.ID_OK, label=t("common.btn_zamknij"))
        sizer.Add(lbl,    flag=wx.ALL,                                       border=8)
        sizer.Add(txt,    proportion=1, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=8)
        sizer.Add(btn_ok, flag=wx.ALL | wx.ALIGN_RIGHT,                      border=8)
        dlg.SetSizer(sizer)
        txt.SetFocus()   # NVDA odczyta listę
        dlg.ShowModal()
        dlg.Destroy()

    def _komenda_visualize(self, arg: str) -> None:
        """`/wizualizuj <opis>` / `/visualize` — multisensoryczny opis sceny."""
        if not self._api_dostepne:
            wx.MessageBox(
                t("opowiesci.brak_api_tresc"),
                t("opowiesci.brak_api_tytul"),
                wx.OK | wx.ICON_ERROR, self,
            )
            return
        if self._projekt is None:
            wx.MessageBox(
                t("opowiesci.brak_gry_tresc"),
                t("opowiesci.brak_gry_tytul"),
                wx.OK | wx.ICON_WARNING, self,
            )
            return
        arg = arg.strip()
        if not arg:
            wx.MessageBox(
                t("opowiesci.dlg_visualize_pusta_akcja_tresc"),
                t("opowiesci.dlg_visualize_pusta_akcja_tytul"),
                wx.OK | wx.ICON_WARNING, self,
            )
            return

        self._lbl_pamiec_status.SetValue(t("opowiesci.status_wizualizowanie"))
        snapshot_kopia = self._snapshot
        threading.Thread(
            target=self._visualize_worker,
            args=(snapshot_kopia, arg),
            daemon=True,
        ).start()

    def _visualize_worker(self, snapshot: oai.SnapshotOpowiesci, arg: str) -> None:
        """Worker `/visualize` — bez blokady `_btn_wyslij` (side-quest, gracz może
        kontynuować rozgrywkę równolegle do generacji opisu)."""
        try:
            tekst = oai.wygeneruj_wizualizacje(
                klient=self._client,
                snapshot=snapshot,
                user_input=arg,
                model=oai.MODEL_NARRACJA,
            )
        except Exception as exc:  # noqa: BLE001
            wx.CallAfter(self._obsluz_blad, exc)
            return
        # v17.11.1: LLM mógł odmówić również wizualizacji (free-text argument
        # `/visualize` bywa nie na temat). Pokazujemy przyjazny komunikat
        # zamiast renderować surowy `[ODRZUCENIE_AI]` w dialogu.
        if oai.wykryto_odrzucenie(tekst):
            wx.CallAfter(self._obsluz_odrzucenie_visualize)
            return
        wx.CallAfter(self._pokaz_visualize_dialog, tekst)

    def _obsluz_odrzucenie_visualize(self) -> None:
        """`/visualize` odrzucony przez LLM — wizualizacja to side-quest bez
        zapisu i bez licznika tur, więc żaden stan się nie zmienia; pokazujemy
        tylko ten sam przyjazny komunikat odmowy co dla zwykłej tury."""
        self._lbl_pamiec_status.SetValue(t("opowiesci.status_gotowe"))
        wx.MessageBox(
            t("opowiesci.odrzucenie_tresc"),
            t("opowiesci.odrzucenie_tytul"),
            wx.OK | wx.ICON_INFORMATION,
            self,
        )

    def _pokaz_visualize_dialog(self, tekst: str) -> None:
        """Dialog z multisensorycznym opisem — readonly, NVDA-friendly, nie zapisuje plików."""
        self._lbl_pamiec_status.SetValue(t("opowiesci.status_gotowe"))

        dlg = wx.Dialog(self, title=t("opowiesci.dlg_visualize_tytul"), size=(720, 520))
        sizer = wx.BoxSizer(wx.VERTICAL)
        lbl = wx.StaticText(dlg, label=t("opowiesci.dlg_visualize_lbl"))
        txt = wx.TextCtrl(
            dlg, value=tekst,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_BESTWRAP,
            name=t("opowiesci.dlg_visualize_name"),
        )
        btn_ok = wx.Button(dlg, wx.ID_OK, label=t("common.btn_zamknij"))
        sizer.Add(lbl,    flag=wx.ALL,                                       border=8)
        sizer.Add(txt,    proportion=1, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=8)
        sizer.Add(btn_ok, flag=wx.ALL | wx.ALIGN_RIGHT,                      border=8)
        dlg.SetSizer(sizer)
        txt.SetFocus()  # NVDA odczyta opis sceny
        dlg.ShowModal()
        dlg.Destroy()

    # ==================================================================
    # FAZA 4 — Wskaźnik pamięci modelu (tiktoken)
    # ==================================================================
    def _aktualizuj_pamiec_modelu(self) -> None:
        """Odświeża `wx.Gauge` + label statusu na podstawie tokenów payloadu.

        Wywoływane po każdej turze (w `_obsluz_ture`) i po auto-streszczeniu
        (w `_streszczenie_done`). Operacja jest tania (~kilka ms na 6 tur),
        ale rzucanie tego po każdym keystroke byłoby przesadą.
        """
        if self._projekt is None:
            self._gauge_pamiec.SetValue(0)
            self._lbl_pamiec_status.SetValue(t("opowiesci.pamiec_status_init"))
            return

        status = oai.oblicz_status_pamieci(
            self._snapshot, self._aktualny_tryb_int(), oai.MODEL_DOMYSLNY,
        )
        self._gauge_pamiec.SetValue(status.procent)
        etap_klucz = {
            oai.POZIOM_CZYSTA:      "opowiesci.pamiec_etap_czysta",
            oai.POZIOM_OK:          "opowiesci.pamiec_etap_ok",
            oai.POZIOM_OSTRZEZENIE: "opowiesci.pamiec_etap_ostrzezenie",
            oai.POZIOM_ALARM:       "opowiesci.pamiec_etap_alarm",
        }[status.poziom]
        self._lbl_pamiec_status.SetValue(t(
            "opowiesci.pamiec_status_format",
            procent=status.procent,
            tokeny=status.tokeny,
            etap=t(etap_klucz),
        ))
        r, g, b = self._KOLORY_POZIOMOW.get(status.poziom, (0, 0, 0))
        self._lbl_pamiec_status.SetForegroundColour(wx.Colour(r, g, b))

    # ==================================================================
    # FAZA 4 — Auto-streszczenie po przekroczeniu PROG_OSTRZEZENIE
    # ==================================================================
    def _spawn_streszczenie(self) -> None:
        """Spawn wątku tła z LLM-streszczeniem `ostatnie_tury`."""
        self._meta_w_toku = True
        self._btn_wyslij.Disable()  # blokada: race condition na ostatnie_tury
        self._lbl_pamiec_status.SetValue(t("opowiesci.status_streszczanie"))

        snapshot_kopia = self._snapshot
        liczba_tur = len(snapshot_kopia.ostatnie_tury)
        threading.Thread(
            target=self._streszczenie_worker,
            args=(snapshot_kopia, liczba_tur),
            daemon=True,
        ).start()

    def _streszczenie_worker(self, snapshot: oai.SnapshotOpowiesci, liczba_tur: int) -> None:
        """LLM streszcza ostatnie tury — blokujący wątek tła."""
        try:
            streszczenie = oai.streszczaj_kontekst(
                klient=self._client, snapshot=snapshot, model=oai.MODEL_NARRACJA,
            )
        except Exception as exc:  # noqa: BLE001
            wx.CallAfter(self._streszczenie_blad, exc)
            return
        wx.CallAfter(self._streszczenie_done, streszczenie, liczba_tur)

    def _streszczenie_done(self, streszczenie: str, liczba_tur: int) -> None:
        """Po sukcesie streszczenia: zwiń `ostatnie_tury` do jednego elementu."""
        # Zwijamy pełną historię w jeden wpis-streszczenie. LLM w kolejnej
        # turze dostanie 1 element zamiast 6, ale ten 1 zawiera cały
        # backstory — kontekst zachowany, bufor zwolniony.
        self._snapshot = oai.SnapshotOpowiesci(
            nazwa_gry=self._snapshot.nazwa_gry,
            numer_tury=self._snapshot.numer_tury,
            ostatnie_tury=[{
                "akcja_gracza":   oai.AKCJA_STRESZCZENIE,
                "narracja_skrot": streszczenie,
            }],
            postacie_aktywne=self._snapshot.postacie_aktywne,
            stan_poprzedni=self._snapshot.stan_poprzedni,
            seed_swiata=self._snapshot.seed_swiata,
            jezyk_projektu=self._snapshot.jezyk_projektu,
            zasady_swiata=self._snapshot.zasady_swiata,
            # carry-forward: po streszczeniu ostatnia REALNA tura wciąż jest
            # najlepszym wzorcem ciągłości — zostaje jako role=assistant.
            ostatni_surowy_json=self._snapshot.ostatni_surowy_json,
        )
        if self._projekt is not None:
            self._projekt.ostatnie_tury = list(self._snapshot.ostatnie_tury)
            try:
                self._projekt.zapisz_game_json()
            except OSError:
                pass   # zapis fail nie powinien blokować gry

        self._meta_w_toku = False
        self._btn_wyslij.Enable()
        self._aktualizuj_pamiec_modelu()
        wx.MessageBox(
            t("opowiesci.streszczenie_skonczone_tresc", liczba_tur=liczba_tur),
            t("opowiesci.streszczenie_skonczone_tytul"),
            wx.OK | wx.ICON_INFORMATION, self,
        )

    def _streszczenie_blad(self, exc: Exception) -> None:
        """Streszczenie nie powiodło się — gra może iść dalej, ale alarm zostanie."""
        self._meta_w_toku = False
        self._btn_wyslij.Enable()
        self._aktualizuj_pamiec_modelu()
        self._wyswietl_blad_ai(str(exc))

    # ==================================================================
    # FAZA 4 — Cinematic Meta Warning po 150 turze
    # ==================================================================
    def _spawn_cinematic_warning(self) -> None:
        """Spawn wątku tła z LLM-generowaniem przerywnika dramatycznego."""
        self._meta_w_toku = True
        self._btn_wyslij.Disable()

        snapshot_kopia = self._snapshot
        threading.Thread(
            target=self._cinematic_worker,
            args=(snapshot_kopia,),
            daemon=True,
        ).start()

    def _cinematic_worker(self, snapshot: oai.SnapshotOpowiesci) -> None:
        try:
            tekst = oai.generuj_cinematic_warning(
                klient=self._client, snapshot=snapshot, model=oai.MODEL_NARRACJA,
            )
        except Exception as exc:  # noqa: BLE001
            wx.CallAfter(self._cinematic_blad, exc)
            return
        wx.CallAfter(self._cinematic_done, tekst)

    def _cinematic_done(self, tekst: str) -> None:
        """Pokaż dialog + zaloguj do .story.jsonl + flag w stanie projektu.

        NIE appendujemy do `.txt` — `core_opowiesci.czysc_meta_warningi`
        wyciąłby tekst między ⚠️🚨⚠️ markerami i tak. Filtr Faza 3 dba o to,
        że audiobook nie zawiera meta-komentarza o własnej narracji.
        """
        if self._projekt is not None:
            try:
                self._projekt.dopisz_story_jsonl({
                    "tura":                self._snapshot.numer_tury,
                    "typ":                 "cinematic_meta_warning",
                    "tresc":               tekst,
                })
                self._projekt.stan = dict(self._projekt.stan)
                self._projekt.stan["cinematic_pokazany"] = True
                self._projekt.zapisz_game_json()
            except OSError:
                pass

        # Zsynchronizuj snapshot z nowym stanem (cinematic_pokazany=True),
        # żeby kolejne tury nie spawnowały warningu ponownie.
        if self._projekt is not None:
            self._snapshot = oai.SnapshotOpowiesci(
                nazwa_gry=self._snapshot.nazwa_gry,
                numer_tury=self._snapshot.numer_tury,
                ostatnie_tury=self._snapshot.ostatnie_tury,
                postacie_aktywne=self._snapshot.postacie_aktywne,
                stan_poprzedni=dict(self._projekt.stan),
                seed_swiata=self._snapshot.seed_swiata,
                jezyk_projektu=self._snapshot.jezyk_projektu,
                zasady_swiata=self._snapshot.zasady_swiata,
                ostatni_surowy_json=self._snapshot.ostatni_surowy_json,  # carry-forward
            )

        self._meta_w_toku = False
        self._btn_wyslij.Enable()
        self._aktualizuj_pamiec_modelu()

        # Dialog z treścią Cinematic Warning. wx.Bell() w tle — A11y „ping".
        wx.Bell()
        dlg = wx.Dialog(self, title=t("opowiesci.cinematic_warning_dlg_tytul"), size=(720, 520))
        sizer = wx.BoxSizer(wx.VERTICAL)
        lbl = wx.StaticText(dlg, label=t("opowiesci.cinematic_warning_dlg_lbl"))
        txt = wx.TextCtrl(
            dlg, value=tekst,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_BESTWRAP,
            name=t("opowiesci.cinematic_warning_dlg_name"),
        )
        btn_ok = wx.Button(dlg, wx.ID_OK, label=t("common.btn_zamknij"))
        sizer.Add(lbl,    flag=wx.ALL,                                       border=8)
        sizer.Add(txt,    proportion=1, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=8)
        sizer.Add(btn_ok, flag=wx.ALL | wx.ALIGN_RIGHT,                      border=8)
        dlg.SetSizer(sizer)
        txt.SetFocus()
        dlg.ShowModal()
        dlg.Destroy()

    def _cinematic_blad(self, exc: Exception) -> None:
        """Cinematic Warning fail — niegroźne, oznacz pokazany żeby nie powtarzać."""
        self._meta_w_toku = False
        self._btn_wyslij.Enable()
        if self._projekt is not None:
            # Mark as shown żeby w przypadku transient API błędu (rate limit)
            # nie spawnować ponownie przy każdej turze ≥ 150.
            self._projekt.stan["cinematic_pokazany"] = True
            try:
                self._projekt.zapisz_game_json()
            except OSError:
                pass
        # Nie pokazujemy błędu — to was side-quest, gracz nie czekał na to
        # akcjonalnie. Cichy fail.


# =====================================================================
# v15.1 — Dialog edycji „Zasady świata"
# =====================================================================

class DialogZasadySwiata(wx.Dialog):
    """Dedykowane okno edycji opcjonalnego tekstu z regułami świata gry.

    A11y rationale: zasady świata to akt okazjonalny (gracz dopisuje regułę
    raz na kilkanaście-kilkadziesiąt tur), więc wieloliniowy ``TextCtrl`` NIE
    siedzi w głównym panelu jako kolejny stop tabulacji. Otwiera się tylko
    na żądanie przyciskiem „Edytuj zasady świata…" obok bloku trybu.

    Po sukcesie (Zapisz) atrybut :attr:`tekst` zawiera nową treść zasad
    (string, może być pusty — pusty = brak dodatkowych reguł). Wywołujący
    sam decyduje co z tym zrobić (typowo: zapis do `.game.json` przez
    :meth:`core_opowiesci.ProjektOpowiesci.zapisz_game_json`).
    """

    def __init__(self, parent: wx.Window, initial_text: str = "") -> None:
        super().__init__(
            parent,
            title=t("opowiesci.dlg_zasady_swiata_tytul"),
            size=(640, 460),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )

        # Atrybut publiczny — wywołujący czyta go po `ShowModal() == wx.ID_OK`.
        self.tekst: str = initial_text

        lbl = wx.StaticText(self, label=t("opowiesci.dlg_zasady_swiata_lbl"))
        # Wraps na długości okna — A11y: NVDA przeczyta etykietę przed
        # wejściem w TextCtrl.
        lbl.Wrap(600)

        self._txt = wx.TextCtrl(
            self,
            value=initial_text,
            style=wx.TE_MULTILINE | wx.TE_BESTWRAP,
            name=t("opowiesci.dlg_zasady_swiata_name"),
        )
        # Hint pokazuje 3 przykłady (fonetyka, mechanika, antagonista). Renderuje
        # się TYLKO gdy pole jest puste — gdy gracz coś już wpisał, hint znika.
        self._txt.SetHint(t("opowiesci.dlg_zasady_swiata_hint"))
        self._txt.SetMinSize((-1, 280))

        btn_ok = wx.Button(self, wx.ID_OK,     label=t("opowiesci.dlg_zasady_swiata_btn_ok"))
        btn_anuluj = wx.Button(self, wx.ID_CANCEL, label=t("opowiesci.dlg_zasady_swiata_btn_anuluj"))
        btn_ok.SetDefault()

        # OK musi zsynchronizować `self.tekst` z aktualną wartością TextCtrl
        # PRZED zamknięciem dialogu — domyślny handler ID_OK zamknie modal
        # natychmiast i wywołujący nie zobaczy zmian.
        btn_ok.Bind(wx.EVT_BUTTON, self._on_zapisz)

        row_btn = wx.BoxSizer(wx.HORIZONTAL)
        row_btn.AddStretchSpacer()
        row_btn.Add(btn_anuluj, flag=wx.RIGHT, border=8)
        row_btn.Add(btn_ok)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(lbl,       flag=wx.ALL,                                       border=10)
        sizer.Add(self._txt, proportion=1, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=10)
        sizer.Add(row_btn,   flag=wx.EXPAND | wx.ALL,                           border=10)
        self.SetSizer(sizer)

        # Fokus na pole tekstowe — gracz od razu może pisać.
        wx.CallAfter(self._txt.SetFocus)

    def _on_zapisz(self, _event: wx.Event) -> None:
        """Zapisz zawartość pola do `self.tekst` i zamknij dialog z ID_OK."""
        self.tekst = self._txt.GetValue()
        self.EndModal(wx.ID_OK)


class DialogEdycjaStanuGry(wx.Dialog):
    """Okno bezpośredniej edycji surowego stanu gry (`.game.json`) — v15.6.

    Opt-in dla technicznego usera (przycisk widoczny tylko gdy
    ``gui_opowiesci.EDYCJA_STANU_GRY_WIDOCZNA``). Pokazuje sformatowany JSON
    w wieloliniowym, monospaced ``TextCtrl``. Przycisk „Zapisz" NIE zamyka
    dialogu, dopóki treść nie sparsuje się jako obiekt JSON (``dict``) —
    uszkodzony `.game.json` wywaliłby kolejne wczytanie gry, więc walidacja
    jest twardym warunkiem zatwierdzenia.

    Po sukcesie (Zapisz) atrybut :attr:`tekst` zawiera zwalidowany surowy
    JSON (string). Wywołujący zapisuje go na dysk i przeładowuje projekt
    (:meth:`OpowiesciPanel._on_edytuj_stan`).
    """

    def __init__(self, parent: wx.Window, initial_text: str = "") -> None:
        super().__init__(
            parent,
            title=t("opowiesci.dlg_edytuj_stan_tytul"),
            size=(680, 560),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )

        # Atrybut publiczny — wywołujący czyta go po `ShowModal() == wx.ID_OK`.
        self.tekst: str = initial_text

        lbl = wx.StaticText(self, label=t("opowiesci.dlg_edytuj_stan_lbl"))
        lbl.Wrap(640)

        self._txt = wx.TextCtrl(
            self,
            value=initial_text,
            style=wx.TE_MULTILINE | wx.TE_DONTWRAP,
            name=t("opowiesci.dlg_edytuj_stan_name"),
        )
        # Monospace — JSON czyta się znacznie lepiej wzrokowo z wcięciami
        # w stałej szerokości znaku; NVDA czyta tak samo, więc bez kosztu A11y.
        self._txt.SetFont(
            wx.Font(wx.FontInfo(10).Family(wx.FONTFAMILY_TELETYPE))
        )
        self._txt.SetMinSize((-1, 380))

        btn_ok = wx.Button(self, wx.ID_OK, label=t("opowiesci.dlg_edytuj_stan_btn_ok"))
        btn_anuluj = wx.Button(self, wx.ID_CANCEL, label=t("opowiesci.dlg_edytuj_stan_btn_anuluj"))
        btn_ok.SetDefault()
        btn_ok.Bind(wx.EVT_BUTTON, self._on_zapisz)

        row_btn = wx.BoxSizer(wx.HORIZONTAL)
        row_btn.AddStretchSpacer()
        row_btn.Add(btn_anuluj, flag=wx.RIGHT, border=8)
        row_btn.Add(btn_ok)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(lbl,       flag=wx.ALL,                                       border=10)
        sizer.Add(self._txt, proportion=1, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=10)
        sizer.Add(row_btn,   flag=wx.EXPAND | wx.ALL,                           border=10)
        self.SetSizer(sizer)

        wx.CallAfter(self._txt.SetFocus)

    def _on_zapisz(self, _event: wx.Event) -> None:
        """Waliduje JSON i — jeśli OK — zapisuje do `self.tekst`, zamyka modal.

        Dwa warunki: (1) treść parsuje się jako JSON; (2) korzeń to obiekt
        (``dict``) — `.game.json` to mapa pól, a `core_opowiesci.wczytaj`
        woła ``dane.get(...)``, więc lista/skalar na topie wywaliłaby reload.
        Niespełnienie → komunikat błędu i dialog ZOSTAJE otwarty (user poprawia).
        """
        surowy = self._txt.GetValue()
        try:
            dane = json.loads(surowy)
        except json.JSONDecodeError as exc:
            wx.MessageBox(
                t("opowiesci.edytuj_stan_blad_json_tresc", tresc_bledu=str(exc)),
                t("opowiesci.edytuj_stan_blad_json_tytul"),
                wx.OK | wx.ICON_ERROR, self,
            )
            return
        if not isinstance(dane, dict):
            wx.MessageBox(
                t("opowiesci.edytuj_stan_blad_typ_tresc"),
                t("opowiesci.edytuj_stan_blad_json_tytul"),
                wx.OK | wx.ICON_ERROR, self,
            )
            return
        self.tekst = surowy
        self.EndModal(wx.ID_OK)
