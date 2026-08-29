"""
gui_rezyser.py – Cienka warstwa widoku panelu „Reżyser" (wxPython).

Po refaktorze 13.0 plik zawiera WYŁĄCZNIE:
    • Definicje widgetów wxPython (budowane przez metody ``_zbuduj_*``).
    • Handlery zdarzeń GUI (``_on_*``).
    • Worker-threads przekazujące pracę do :mod:`rezyser_ai`
      (``_wyslij_worker``, ``_tytuly_worker``).
    • Property-shimy (``full_story``, ``summary_text``, …) delegujące do
      ``self._projekt``.

Logika biznesowa (stan projektu, przepisy, wywołania Anthropic) żyje w:
    • :mod:`core_rezyser`     – ``ProjektRezysera`` + silnik fonetyczny.
    • :mod:`przepisy_rezysera` – loader YAML-i z ``dictionaries/pl/rezyser/``.
    • :mod:`rezyser_ai`       – ``generuj_fragment``, ``nadaj_tytuly_rozdzialom``.

Panel dziedziczy po :class:`wx.Panel`; podpinany do ``MainFrame`` z ``main.py``.

Główne sekcje UI (zobacz metody ``_zbuduj_*``):
    • BLOK A – nagłówek + opis narzędzia.
    • BLOK B – pole nazwy pliku + przyciski wczytaj/reset/otwórz/przeładuj.
    • BLOK C – sidebar: Księga Świata + Pamięć Długotrwała (lewa kolumna).
    • BLOK D – obszar roboczy (prawa kolumna, kompozycja pod-bloków).
    • BLOK E – panel struktury (Prolog/Epilog/Akt/Scena/Rozdział).
    • BLOK F – panel postprodukcji (od v18.12 dynamiczny: przycisk per
      narzędzie z YAML `kategoria: postprodukcja`, filtr `dla_trybow`).
    • BLOK G – wskaźnik okna kontekstowego AI (Gauge + status).

Wersja 13.1: cały tekst widoczny dla użytkownika pochodzi z
``dictionaries/pl/gui/ui.yaml`` (sekcja ``rezyser``) przez moduł
:mod:`i18n`. W konstruktorze pobieramy też ``TOOL_DESCRIPTION`` i
``PROMPT_ARCHITEKTA`` – są zbyt duże, żeby trzymać je twardo w kodzie
i tak utrudniały tłumaczenie w przyszłości.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass

from dotenv import load_dotenv

import wx

# Refaktor wersji 13.0: logika modelu, przepisy i silnik AI są wydzielone
# z tego pliku. Panel zostaje cienką warstwą widoku wxPython.
import core_elevenlabs as ce
import core_llm as cl
import core_rezyser as cr
import core_tokeny as ct
import core_screen_reader as csr
import przepisy_rezysera as pr
import sciezki
import rezyser_ai as rai
import bledy_ai
from bledy_ai import BladGeneracjiAI
from i18n import aktualny_jezyk, dostepne_jezyki_ui, t


@dataclass
class ZadaniePostprodukcji:
    """Komplet danych jednego uruchomienia postprodukcji (v18.13).

    Do v18.12 workery dostawały luźne argumenty pozycyjne; po dołożeniu zakresu
    ``rekoncyliacja`` i roli ``pamiec_dlugotrwala`` potrzebnych jest sześć wartości,
    a dwie z nich to bliźniacze stringi (``tresc_modelu`` vs ``pelny_tekst``) —
    czyli dokładnie ten rodzaj sygnatury, w którym zamiana argumentów miejscami
    kompiluje się i cicho psuje wynik. Snapshot zamraża je w jednym obiekcie
    przekazywanym do wątku tła (wzorzec ``SnapshotProjektu``).

    Attributes:
        przepis:      Przepis postprodukcji (YAML).
        nazwa:        Nazwa projektu z pola GUI (może NIE być projektem otwartym).
        tresc_modelu: To, co realnie leci do modelu — cały plik (``calosc``) albo
                      złożone wejście rekoncyliacji (streszczenie + fabuła
                      od anchora).
        pelny_tekst:  Pełna treść ``skrypty/<nazwa>.txt``. Potrzebna osobno, bo
                      anchor meta Pamięci Długotrwałej liczymy z CAŁEGO pliku,
                      nie z przyciętego wejścia.
        ksiega:       Treść Księgi Świata (``None`` gdy brak / nieczytelna).
        sciezka_wyj:  Plik wyniku lub ``None`` (wynik tylko w dialogu).
        auto:         True = uruchomienie automatyczne (próg pamięci), bez pytań
                      i bez dialogu wyniku — patrz ``_spawn_auto_pamiec``.
    """

    przepis: pr.PrzepisRezysera
    nazwa: str
    tresc_modelu: str
    pelny_tekst: str
    ksiega: str | None = None
    sciezka_wyj: str | None = None
    auto: bool = False


class RezyserPanel(wx.Panel):
    """Panel modułu „Reżyser Audio GPT" — cienka warstwa widoku wxPython.

    Trzy tryby pracy (AI Anthropic Claude Sonnet 4.6) wczytywane są dynamicznie z YAML-i
    (``dictionaries/pl/rezyser/``) przez :mod:`przepisy_rezysera`:

        * Burza Mózgów – planowanie fabuły, 3 opcje + prompty (BEZ zapisu).
        * Skrypt       – surowy skrypt dźwiękowy [SFX] + [Postać] (ZAPIS).
        * Audiobook    – tradycyjna proza literacka (ZAPIS).

    Dodanie nowego trybu = nowy plik YAML + restart aplikacji. Kod
    Pythona nie wymaga zmian.

    Stan projektu (historia, streszczenie, Księga Świata, liczniki) żyje
    w ``self._projekt`` (:class:`core_rezyser.ProjektRezysera`); atrybuty
    typu ``self.full_story`` są property-shimami delegującymi do modelu.

    Wywołania Anthropic realizowane są w wątkach tła (``threading.Thread``)
    z wynikami przekazywanymi do GUI przez ``wx.CallAfter``.
    """

    ENV_FILENAME = "golden_key.env"
    SKRYPTY_DIR  = "skrypty"


    def __init__(self, parent: wx.Window) -> None:

        super().__init__(parent, style=wx.TAB_TRAVERSAL)
        self.SetName(t("rezyser.panel_name"))

        # --------------------------------------------------------------
        # Wersja 13.1: duże bloki tekstu (opis narzędzia + prompt dla AI)
        # pobrane z YAML-a przez i18n. Przypisujemy je do instancji, a NIE
        # do klasy – bo `t()` działa dopiero po ustawieniu języka w
        # ``i18n.ustaw_jezyk()`` (co robi ``main.py`` w ``main()``).
        # Dzięki temu przy przyszłej zmianie języka w locie wystarczy
        # odbudować panel, a nie podmieniać stałe klasy w runtime.
        # --------------------------------------------------------------
        self._tool_description = t("rezyser.tool_description")
        self._prompt_architekta = t("rezyser.prompt_architekta_content")

        # ── Model danych: stan projektu, I/O, liczniki, silnik fonetyczny ──
        # Refaktor 13.0: cały stan trzymany w core_rezyser.ProjektRezysera.
        # Atrybuty full_story / summary_text / world_lore / liczniki /
        # zapisana_nazwa_pliku / last_response są @property delegującymi do
        # self._projekt – dzięki temu istniejący kod typu
        # ``self.full_story += tekst`` nadal działa, ale dane są trzymane
        # w jednym miejscu (ProjektRezysera) i dostępne dla wątku tła AI
        # przez ``self._projekt.snapshot()``.
        self._projekt: cr.ProjektRezysera = cr.ProjektRezysera()

        # Mirror pliku `.mode` w RAM. Trzyma trwałą decyzję trybu zapisu
        # projektu jako stabilne `id` przepisu (np. "audiobook") niezależnie od
        # bieżącego stanu `_rb_mode`, który gracz może swobodnie przełączać na
        # Burzę — Burza pełni rolę awaryjną (streszczenie przy przepełnieniu
        # okna kontekstowego, opcje fabularne) i musi pozostać dostępna na
        # każdym etapie. Materializuje się przy wczytaniu projektu z `.mode`,
        # pierwszym wstawieniu struktury i pierwszej udanej wysyłce
        # produkcyjnej. Reset tylko przez twardy reset projektu.
        self._zapisany_tryb: str | None = None

        # D2 (od 18.3): „czysty" snapshot pól Księga Świata / Pamięć z chwili
        # ostatniego wczytania albo zapisu. Detektor niezapisanych zmian w
        # `_on_przeladuj_z_dysku` porównuje z nim aktualną treść — bez tego
        # ostrzeżenie wyskakiwało zawsze, gdy pola były NIEPUSTE (nawet bez
        # żadnej edycji), co irytowało przy zwykłym przeładowaniu projektu.
        self._ksiega_swiata_zapisana: str = ""
        self._pamiec_zapisana: str = ""

        # ── Przepisy twórcze załadowane z YAML-i (dictionaries/<jezyk>/rezyser/) ─
        # 13.2: ładujemy tryby w języku UI z miękkim fallbackiem do EN. Twardego
        # polskiego fallbacku NIE robimy — etykiety i prompty mają być spójne
        # z językiem użytkownika, a angielski jest neutralny dla wszystkich.
        # Kolejność RadioBoxa wynika z pola ``kolejnosc`` w YAML-ach
        # (Burza=10, Skrypt=20, Audiobook=30).
        jezyk_ui = aktualny_jezyk()
        przepisy = pr.lista_trybow(jezyk_ui)
        if not przepisy and jezyk_ui != "en":
            przepisy = pr.lista_trybow("en")
        self._przepisy: list[pr.PrzepisRezysera] = przepisy

        # Postprodukcje (v18.12, generalizacja): pełna lista z paczki języka
        # UI z tym samym miękkim fallbackiem do EN co tryby (do v18.11 GUI
        # ładowało na sztywno pojedynczy przepis `tytuly`). Które narzędzia
        # są widoczne dla bieżącego trybu, decyduje `_refresh_ui_state`
        # filtrem `pr.filtruj_postprodukcje` (pole `dla_trybow` z YAML).
        postprodukcje = pr.lista_postprodukcji(jezyk_ui)
        if not postprodukcje and jezyk_ui != "en":
            postprodukcje = pr.lista_postprodukcji("en")
        self._postprodukcje: list[pr.PrzepisRezysera] = postprodukcje

        # v18.13: nazwa pliku Pamięci Długotrwałej pochodzi z przepisu o roli
        # `pamiec_dlugotrwala`. Model MUSI liczyć tę samą ścieżkę co panel,
        # więc bierzemy sufiks z DOKŁADNIE tej listy, którą GUI wyświetla
        # (a nie z paczki `pl`, na której `ProjektRezysera` opiera default).
        # v18.14: sufiksy są lokalizowane, więc podajemy całą listę KANDYDATÓW,
        # a docelowo (po zbudowaniu RadioBoxa) bierzemy ją z paczki JĘZYKA
        # PROJEKTU — patrz `_odswiez_kandydatow_pamieci`. Tu jeszcze nie ma
        # `_rb_mode`, więc startujemy od paczki interfejsu.
        self._projekt.ustaw_kandydatow_pamieci(
            pr.sufiksy_pamieci_dlugotrwalej(self._postprodukcje))

        # Skrajny przypadek: ani język UI, ani EN nie ma trybów — komunikat A11y.
        if not self._przepisy:
            wx.CallAfter(
                wx.MessageBox,
                t("rezyser.brak_trybow_dla_jezyka", jezyk=jezyk_ui),
                t("rezyser.brak_trybow_tytul"),
                wx.OK | wx.ICON_WARNING,
                self,
            )

        # ── Klient LLM (single-provider, Anthropic Claude od v18.2.1) ──────
        # Claude Sonnet 4.6 obsługuje WSZYSTKO: tryby narracyjne (audiobook /
        # skrypt / burza), postprodukcję tytułów ORAZ mikro-call kodu języka.
        # (Do v18.2.1 GUI trzymało jeszcze martwego klienta OpenAI mimo migracji
        # `rezyser_ai` na Messages API — co łamało obietnicę single-key.)
        self._klient_llm = None   # Anthropic
        self._api_dostepne: bool = False
        self._worker_thread: threading.Thread | None = None
        # v18.13: czy auto-zapis Pamięci Długotrwałej (próg ALARM) już zadziałał
        # dla BIEŻĄCEGO stanu projektu. Streszczenie nie zmniejsza `full_story`
        # w pamięci roboczej — realnie skraca kontekst dopiero rekoncyliacja przy
        # wczytaniu/przeładowaniu projektu. Bez tej flagi automat odpalałby się
        # (i płacił) po KAŻDEJ kolejnej turze powyżej progu. Reset: wczytanie /
        # przeładowanie projektu i twardy reset.
        self._auto_pamiec_wykonane: bool = False
        # v17.9 (Obszar 3b): id przepisów, dla których trwa wnioskowanie
        # `kod_jezyka` w tle — guard przed równoległymi mikrorequestami LLM.
        self._kod_jezyka_w_toku: set[str] = set()
        # v17.11.1: id przepisów już rozwiązanych w TEJ sesji (sukces LUB pokazany
        # dialog edukacyjny) — żeby nie ponawiać resolvera ani nie powtarzać
        # ostrzeżenia/dialogu przy każdym ponownym wyborze tego samego przepisu.
        self._kod_jezyka_rozwiazany: set[str] = set()
        self._init_api()

        # ── Most ElevenLabs (opcjonalny, v16.0) ────────────────────────────
        self._el_klucz: str | None = None
        self._el_dostepne: bool = False
        self._init_elevenlabs()

        self._build_ui()
        self._bind_events()
        self._refresh_ui_state()

        # NVDA odczyta opis narzędzia jako pierwsze po otwarciu panelu
        wx.CallAfter(self._description.SetFocus)

    # ------------------------------------------------------------------
    # Helper: wskazuje przepis dla aktualnie zaznaczonego trybu w RadioBox
    # ------------------------------------------------------------------
    def _aktualny_przepis(self) -> pr.PrzepisRezysera | None:
        """Zwraca :class:`PrzepisRezysera` odpowiadający zaznaczonemu trybowi."""
        if not self._przepisy:
            return None
        idx = self._rb_mode.GetSelection()
        if 0 <= idx < len(self._przepisy):
            return self._przepisy[idx]
        return None

    def _przepis_burzy(self) -> pr.PrzepisRezysera | None:
        """Zwraca przepis Burzy (``id == "burza"``) NIEZALEŻNIE od RadioBoxa.

        Doklejka ``[Reżyserze: ...]`` / ``[DYREKTYWA]: ...`` mieszka WYŁĄCZNIE
        w przepisie Burzy (``tryb_burza.yaml::doklejka_celu_sceny``) — tryby
        produkcyjne (Skrypt/Audiobook) mają to pole puste. Opcje Burzy są
        zawsze owocem Burzy, więc doklejkę bierzemy z jej przepisu, nie z
        aktualnie zaznaczonego trybu. Inaczej po wczytaniu projektu z
        ``saved_mode`` 1/2 (RadioBox przeskakuje na tryb produkcyjny, patrz
        :meth:`_on_load`) ``_aktualny_przepis()`` zwracałby tryb bez
        doklejki i przyciski opcji wstawiałyby sam ``[CEL SCENY]`` — bug
        „znikających tagów [Reżyserze]/[DYREKTYWA] po wczytaniu projektu".
        """
        for przepis in self._przepisy:
            if przepis.id == "burza":
                return przepis
        return None

    # ------------------------------------------------------------------
    # Język TREŚCI przepisu (v17.9, Obszar 3a/3b) — nagłówki + akcenty
    # ------------------------------------------------------------------
    def _kod_jezyka_aktywny(self) -> str:
        """Kod ISO języka TREŚCI aktywnego przepisu — do nagłówków struktury
        (`t(jezyk_override=...)`) oraz wersji dla czytników ekranu.

        Fallback na język GUI (`aktualny_jezyk()`) gdy przepis nie ma jeszcze
        `kod_jezyka` (np. przepis bez struktury, albo lingwista nie wypełnił a
        wnioskowanie w tle jeszcze nie wróciło). Paczki shippowane mają pole
        wypełnione, więc fallback to ścieżka brzegowa.
        """
        przepis = self._aktualny_przepis()
        return (przepis.kod_jezyka if przepis else "") or aktualny_jezyk()

    def _odswiez_kandydatow_pamieci(self) -> None:
        """Przelicza kandydatów na plik Pamięci Długotrwałej (v18.14).

        Sufiks pliku pamięci jest od v18.14 LOKALIZOWANY, a jego źródłem jest
        paczka JĘZYKA PROJEKTU (`kod_jezyka` aktywnego przepisu — ta sama
        wartość, którą dostaje most do ElevenLabs), NIE język interfejsu.
        Powód: plik należy do treści projektu, więc przełączenie menu na inny
        język nie może przemianowywać pamięci cudzej historii, a projekt pisany
        po fińsku ma mieć fińską nazwę pliku także u reżysera z polskim UI.

        Gdy paczka języka treści nie ma narzędzia z rolą pamięci (paczka
        niekompletna, user skasował YAML) — spadamy na listę, którą panel
        realnie wyświetla (język UI z miękkim fallbackiem EN), żeby sufiks
        pochodził DOKŁADNIE z przepisu, który wygeneruje treść.
        """
        kod = self._kod_jezyka_aktywny()
        lista = pr.lista_postprodukcji(kod) if kod else []
        if not pr.przepisy_pamieci_dlugotrwalej(lista):
            lista = self._postprodukcje
        self._projekt.ustaw_kandydatow_pamieci(
            pr.sufiksy_pamieci_dlugotrwalej(lista))

    def _zapewnij_kod_jezyka_w_tle(self) -> None:
        """1b: dla aktywnego przepisu ZAPISU (Skrypt/Audiobook) ustala `kod_jezyka`
        z `jezyk_odpowiedzi` w wątku tła (cache → LLM → fallback) i wpisuje wynik
        na obiekt przepisu. Wołane gdy przepis staje się aktywny (zmiana trybu,
        wczytanie projektu), żeby do kliknięcia nagłówka kod był gotowy bez
        blokowania GUI (A11y).

        v17.11.1 (D1 Wariant A): NIE ufamy już wpisanemu `kod_jezyka` na ślepo —
        resolver liczy kod z `jezyk_odpowiedzi` ZAWSZE (przez cache, więc bez
        spamu API). Wpisany kod jest tylko fallbackiem offline; pewny rozjazd
        (wpisane „pl" przy `jezyk_odpowiedzi: fińsku`) → jawne ostrzeżenie.

        No-op gdy: brak API (zostaje wpisany kod jako fallback), przepis nie jest
        trybem zapisu, wnioskowanie już trwa, albo przepis rozwiązano w tej sesji.
        """
        przepis = self._aktualny_przepis()
        if przepis is None or not przepis.zapis_do_pliku:
            return
        if not self._api_dostepne or self._klient_llm is None:
            return  # offline: wpisany `kod_jezyka` zostaje fallbackiem
        if przepis.id in self._kod_jezyka_w_toku:
            return
        if przepis.id in self._kod_jezyka_rozwiazany:
            return
        self._kod_jezyka_w_toku.add(przepis.id)
        klient    = self._klient_llm
        jezyk_odp = przepis.jezyk_odpowiedzi
        kod_yaml  = przepis.kod_jezyka
        dozwolone = set(dostepne_jezyki_ui())

        def _worker() -> None:
            wynik = rai.rozwiaz_kod_jezyka(klient, jezyk_odp, kod_yaml, dozwolone)
            wx.CallAfter(self._kod_jezyka_done, przepis, wynik)

        threading.Thread(target=_worker, daemon=True).start()

    def _kod_jezyka_done(
        self, przepis: pr.PrzepisRezysera, wynik: "rai.RozwiazanieKodu",
    ) -> None:
        """Callback resolvera `kod_jezyka` (wątek GUI). Sukces → wpis na przepis;
        rozjazd z wpisanym kodem → jawne ostrzeżenie; brak rozwiązania → dłuższy
        dialog edukacyjny z promptem dla chatbota (D1)."""
        self._kod_jezyka_w_toku.discard(przepis.id)
        self._kod_jezyka_rozwiazany.add(przepis.id)
        if wynik.kod:
            przepis.kod_jezyka = wynik.kod
            # v18.14: nazwa pliku Pamięci Długotrwałej podąża za językiem TREŚCI,
            # nie interfejsu — świeżo rozstrzygnięty kod może wskazywać inną
            # paczkę, więc przeliczamy kandydatów (plik już rozstrzygniętego
            # projektu zostaje nietknięty — patrz `ustaw_kandydatow_pamieci`).
            self._odswiez_kandydatow_pamieci()
            if wynik.rozjazd_z_yaml:
                # D1: kod wyliczony z `jezyk_odpowiedzi` WYGRYWA z wpisanym;
                # uciszamy reżysera, który sądził, że sam `jezyk_odpowiedzi`
                # wystarcza, i tłumaczymy, że to wyliczony kod steruje strukturą.
                wx.MessageBox(
                    t("rezyser.kod_jezyka_rozjazd_tresc",
                      jezyk_odpowiedzi=przepis.jezyk_odpowiedzi,
                      kod_wpisany=wynik.yaml_kod,
                      kod_wykryty=wynik.kod),
                    t("rezyser.kod_jezyka_rozjazd_tytul"),
                    wx.OK | wx.ICON_WARNING,
                    self,
                )
            return
        self._pokaz_dialog_iso_edu(przepis.jezyk_odpowiedzi)

    def _pokaz_dialog_iso_edu(self, jezyk_odpowiedzi: str) -> None:
        """Dłuższy, dostępny dialog (readonly `TextCtrl` + „Zamknij") gdy kodu
        ISO NIE udało się ustalić (brak API / halucynacja / brak fallbacku).

        Tłumaczy nieświadomemu reżyserowi, że sam `jezyk_odpowiedzi` nie
        wystarcza, i wkleja gotowy prompt do zwykłego chatbota, którym sam
        ustali właściwy kod ISO 639-1. Treść z `ui.yaml` (język UI). Wzorzec
        zgodny z CLAUDE.md: długie treści techniczne → `wx.Dialog`+`TE_READONLY`.
        """
        tresc = (
            t("rezyser.kod_jezyka_edu_tresc", jezyk_odpowiedzi=jezyk_odpowiedzi)
            + "\n\n"
            + t("rezyser.kod_jezyka_edu_prompt", jezyk_odpowiedzi=jezyk_odpowiedzi)
        )
        dlg = wx.Dialog(
            self, title=t("rezyser.kod_jezyka_edu_tytul"), size=(640, 440),
        )
        sizer = wx.BoxSizer(wx.VERTICAL)
        lbl = wx.StaticText(dlg, label=t("rezyser.kod_jezyka_edu_naglowek"))
        txt = wx.TextCtrl(
            dlg, value=tresc,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_BESTWRAP,
            name=t("rezyser.kod_jezyka_edu_name"),
        )
        btn = wx.Button(dlg, wx.ID_OK, label=t("common.btn_zamknij"))
        sizer.Add(lbl, flag=wx.ALL, border=8)
        sizer.Add(txt, proportion=1, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=8)
        sizer.Add(btn, flag=wx.ALL | wx.ALIGN_RIGHT, border=8)
        dlg.SetSizer(sizer)
        txt.SetFocus()
        dlg.ShowModal()
        dlg.Destroy()

    def _mapa_slow_naglowkow(self) -> dict[str, set[str]]:
        """Mapa ``kod_jezyka → {słowa-nagłówki małymi literami}`` dla
        zainstalowanych języków — paliwo dla
        :func:`core_rezyser.policz_naglowki_per_jezyk`. Słowa bierzemy z
        ``t("rezyser.naglowek_*", jezyk_override=<kod>)`` (pierwszy token)."""
        klucze = (
            "naglowek_prolog", "naglowek_epilog", "naglowek_rozdzial",
            "naglowek_akt", "naglowek_scena",
        )
        mapa: dict[str, set[str]] = {}
        for lang in dostepne_jezyki_ui():
            slowa: set[str] = set()
            for k in klucze:
                w = t(f"rezyser.{k}", jezyk_override=lang).strip().lower()
                if w:
                    slowa.add(w.split()[0])
            mapa[lang] = slowa
        return mapa

    def _moze_ostrzec_o_jezyku_naglowkow(self, content: str) -> None:
        """3a: po wczytaniu — INFORMACYJNE ostrzeżenie, gdy nagłówki istniejącej
        treści NIE są w języku aktywnego przepisu, a wyglądają na inny. Wczytanie
        i tak kontynuuje (reżyser może świadomie migrować język projektu).

        Reguła niskiego false-positive: ostrzegamy TYLKO gdy język przepisu ma
        ZERO trafień w nagłówkach, a inny język ma ≥1 (słowa wspólne, np. „Akt"
        pl/de, liczą się dla obu, więc spójna treść nie wywoła alarmu)."""
        if not content or not content.strip():
            return
        kod = self._kod_jezyka_aktywny()
        counts = cr.policz_naglowki_per_jezyk(content, self._mapa_slow_naglowkow())
        if counts.get(kod, 0) > 0:
            return
        inne = sorted(
            ((l, c) for l, c in counts.items() if c > 0 and l != kod),
            key=lambda x: -x[1],
        )
        if not inne:
            return
        wx.MessageBox(
            t("rezyser.jezyk_naglowkow_ostrzezenie_tresc",
              wykryty=inne[0][0], kod=kod),
            t("rezyser.jezyk_naglowkow_ostrzezenie_tytul"),
            wx.OK | wx.ICON_WARNING,
            self,
        )

    # ==================================================================
    # SHIMY WŁAŚCIWOŚCI delegujące do self._projekt
    # ==================================================================

    @property
    def full_story(self) -> str:
        return self._projekt.full_story

    @full_story.setter
    def full_story(self, value: str) -> None:
        self._projekt.full_story = value

    @property
    def summary_text(self) -> str:
        return self._projekt.summary_text

    @summary_text.setter
    def summary_text(self, value: str) -> None:
        self._projekt.summary_text = value

    @property
    def world_lore(self) -> str:
        return self._projekt.world_lore

    @world_lore.setter
    def world_lore(self, value: str) -> None:
        self._projekt.world_lore = value

    @property
    def chapter_counter(self) -> int:
        return self._projekt.chapter_counter

    @chapter_counter.setter
    def chapter_counter(self, value: int) -> None:
        self._projekt.chapter_counter = value

    @property
    def akt_counter(self) -> int:
        return self._projekt.akt_counter

    @akt_counter.setter
    def akt_counter(self, value: int) -> None:
        self._projekt.akt_counter = value

    @property
    def scena_counter(self) -> int:
        return self._projekt.scena_counter

    @scena_counter.setter
    def scena_counter(self, value: int) -> None:
        self._projekt.scena_counter = value

    @property
    def zapisana_nazwa_pliku(self) -> str:
        return self._projekt.nazwa_pliku

    @zapisana_nazwa_pliku.setter
    def zapisana_nazwa_pliku(self, value: str) -> None:
        self._projekt.nazwa_pliku = value

    @property
    def last_response(self) -> str:
        return self._projekt.last_response

    @last_response.setter
    def last_response(self, value: str) -> None:
        self._projekt.last_response = value

    # ------------------------------------------------------------------
    # Inicjowanie klienta Anthropic
    # ------------------------------------------------------------------
    def _init_api(self) -> None:
        """Ładuje golden_key.env i inicjuje klienta LLM przez `core_llm`.

        Od v18.4 provider-agnostic: domyślnie Anthropic Claude (`ANTHROPIC_API_KEY`,
        `sk-ant-`), a gdy `LLM_PROVIDER=openai_compat` — dowolny endpoint zgodny z
        OpenAI (`LLM_BASE_URL` + `OPENAI_API_KEY` + `LLM_MODEL`). WSZYSTKIE wywołania
        Reżysera (tryby narracyjne + postprodukcje + mikro-call kodu języka)
        idą przez `_klient_llm`. `_api_dostepne` = klient zbudowany (konfiguracja
        kompletna). Claude pozostaje rekomendowanym filarem jakości.
        """
        app_dir = sciezki.KATALOG_BAZOWY_STR
        env_path = os.path.join(app_dir, self.ENV_FILENAME)
        if not os.path.exists(env_path):
            return
        load_dotenv(env_path)

        self._klient_llm = cl.zbuduj_klienta(cl.wczytaj_konfiguracje())
        self._api_dostepne = self._klient_llm is not None

    def _init_elevenlabs(self) -> None:
        """Wczytuje opcjonalny klucz ElevenLabs z golden_key.env (v16.0).

        Brak/zły klucz → ``_el_dostepne = False`` i UI mostu pozostaje ukryte;
        reszta panelu działa bez zmian. Walidacja w ``core_elevenlabs``
        (prefix ``sk_``, długość) — single source of truth z System Check.
        """
        app_dir = sciezki.KATALOG_BAZOWY_STR
        env_path = os.path.join(app_dir, self.ENV_FILENAME)
        self._el_klucz = ce.wczytaj_klucz(env_path)
        self._el_dostepne = self._el_klucz is not None

    # ------------------------------------------------------------------
    # Budowanie interfejsu (kompozer)
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        """Buduje cały interfejs panelu poprzez wywołanie metod ``_zbuduj_*``."""
        BORDER = 8

        top_sizer         = self._zbuduj_naglowek(BORDER)
        pasek_pliku_sizer = self._zbuduj_pasek_pliku(BORDER)
        sidebar_sizer     = self._zbuduj_sidebar(BORDER)
        main_area_sizer   = self._zbuduj_obszar_roboczy(BORDER, pasek_pliku_sizer)

        v_sep = wx.StaticLine(self, style=wx.LI_VERTICAL)

        two_col_sizer = wx.BoxSizer(wx.HORIZONTAL)
        two_col_sizer.Add(sidebar_sizer,   proportion=1, flag=wx.EXPAND | wx.ALL, border=4)
        two_col_sizer.Add(v_sep,                         flag=wx.EXPAND | wx.TOP | wx.BOTTOM,
                          border=8)
        two_col_sizer.Add(main_area_sizer, proportion=3, flag=wx.EXPAND | wx.ALL, border=4)

        root_sizer = wx.BoxSizer(wx.VERTICAL)
        root_sizer.Add(top_sizer,     flag=wx.EXPAND)
        root_sizer.Add(two_col_sizer, proportion=1, flag=wx.EXPAND)

        self.SetSizer(root_sizer)

    # ------------------------------------------------------------------
    # BLOK A – Nagłówek panelu
    # ------------------------------------------------------------------
    def _zbuduj_naglowek(self, BORDER: int) -> wx.BoxSizer:
        heading = wx.StaticText(self, label=t("rezyser.heading"))
        hf = heading.GetFont()
        hf.SetPointSize(16)
        hf.MakeBold()
        heading.SetFont(hf)

        self._description = wx.TextCtrl(
            self,
            value=self._tool_description,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.NO_BORDER,
            name=t("rezyser.description_name"),
        )
        self._description.SetBackgroundColour(self.GetBackgroundColour())
        self._description.SetMinSize((-1, 110))

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(heading, flag=wx.ALL, border=BORDER)
        sizer.Add(
            self._description,
            flag=wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            border=BORDER,
        )
        sizer.Add(
            wx.StaticLine(self),
            flag=wx.EXPAND | wx.LEFT | wx.RIGHT,
            border=BORDER,
        )
        return sizer

    # ------------------------------------------------------------------
    # BLOK B – Pole nazwy pliku + przyciski wczytaj / reset / otwórz / przeładuj
    # ------------------------------------------------------------------
    def _zbuduj_pasek_pliku(self, BORDER: int) -> wx.BoxSizer:
        lbl_file = wx.StaticText(self, label=t("rezyser.lbl_nazwa_pliku"))

        self._txt_file_name = wx.TextCtrl(
            self,
            style=wx.TE_PROCESS_ENTER,
            name=t("rezyser.txt_nazwa_pliku_name"),
        )
        self._txt_file_name.SetHint(t("rezyser.txt_nazwa_pliku_hint"))
        self._txt_file_name.SetToolTip(t("rezyser.txt_nazwa_pliku_tooltip"))

        self._btn_load = wx.Button(self, label=t("rezyser.btn_wczytaj_label"))
        self._btn_load.SetToolTip(t("rezyser.btn_wczytaj_tooltip"))

        self._btn_hard_reset = wx.Button(self, label=t("rezyser.btn_hard_reset_label"))
        self._btn_hard_reset.SetToolTip(t("rezyser.btn_hard_reset_tooltip"))

        # v15.2.3: awaryjna edycja pliku narracji w systemowym edytorze tekstu.
        # Łata lukę architektoniczną w pamięci streszczenia: po wczytaniu
        # projektu z istniejącym .summary.txt skrypt ZEROWAŁ full_story
        # (priorytet streszczenia nad pełną historią), więc gracz, który
        # wpisał krótką notatkę i zamknął apkę, po reload miał Księgę
        # Świata + jednozdaniowe streszczenie i AI „głupiało" bez kontekstu
        # ostatnich scen. Przycisk pozwala otworzyć plik .txt w Notatniku
        # (jak `golden_key.env` w main.py / yamle w manager_regul) — gracz
        # widzi pełną narrację, może z niej skopiować fragmenty do pamięci
        # albo dopisać/edytować scenę ręcznie przed kolejną wysyłką do AI.
        self._btn_otworz_narracje = wx.Button(self, label=t("rezyser.btn_otworz_narracje_label"))
        self._btn_otworz_narracje.SetToolTip(t("rezyser.btn_otworz_narracje_tooltip"))

        # v15.5/v17.6: pełne PRZEŁADOWANIE projektu z dysku po ręcznej edycji
        # `.txt` (np. ucięciu złamanego anti-closure, dopisaniu/usunięciu
        # rozdziału). Domyka cykl „Otwórz narrację → edytuj w edytorze →
        # Przeładuj z dysku". Od v17.6 to faktyczny reload przez
        # `core_rezyser.ProjektRezysera.wczytaj` — przelicza liczniki struktury,
        # podnosi Księgę/tryb/Burzę i rekoncyliuje pamięć roboczą jednym torem
        # (koniec desyncu liczników i meta streszczenia z czasów częściowego
        # `rekoncyliuj_z_dysku`).
        self._btn_przeladuj = wx.Button(self, label=t("rezyser.btn_przeladuj_label"))
        self._btn_przeladuj.SetToolTip(t("rezyser.btn_przeladuj_tooltip"))

        file_row = wx.BoxSizer(wx.HORIZONTAL)
        file_row.Add(self._txt_file_name,      proportion=1, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=6)
        file_row.Add(self._btn_load,           flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=4)
        file_row.Add(self._btn_hard_reset,     flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=4)
        file_row.Add(self._btn_otworz_narracje, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=4)
        file_row.Add(self._btn_przeladuj,      flag=wx.ALIGN_CENTER_VERTICAL)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(lbl_file, flag=wx.LEFT | wx.RIGHT | wx.TOP, border=BORDER)
        sizer.Add(file_row, flag=wx.EXPAND | wx.ALL,          border=BORDER)
        return sizer

    # ------------------------------------------------------------------
    # BLOK C – Sidebar: Księga Świata + Pamięć Długotrwała
    # ------------------------------------------------------------------
    def _zbuduj_sidebar(self, BORDER: int) -> wx.BoxSizer:
        lbl_sb_heading = wx.StaticText(self, label=t("rezyser.sidebar_heading"))
        sbf = lbl_sb_heading.GetFont()
        sbf.SetPointSize(11)
        sbf.MakeBold()
        lbl_sb_heading.SetFont(sbf)

        lbl_ksiega = wx.StaticText(self, label=t("rezyser.lbl_ksiega_swiata"))

        self._txt_ksiega_swiata = wx.TextCtrl(
            self,
            style=wx.TE_MULTILINE,
            name=t("rezyser.txt_ksiega_name"),
        )
        self._txt_ksiega_swiata.SetHint(t("rezyser.txt_ksiega_hint"))
        self._txt_ksiega_swiata.SetToolTip(t("rezyser.txt_ksiega_tooltip"))

        self._btn_zapisz_ksiege = wx.Button(self, label=t("rezyser.btn_zapisz_ksiege_label"))
        self._btn_zapisz_ksiege.SetToolTip(t("rezyser.btn_zapisz_ksiege_tooltip"))

        self._btn_prompt_architekta = wx.Button(
            self,
            label=t("rezyser.btn_prompt_architekta_label"),
            name=t("rezyser.btn_prompt_architekta_name"),
        )
        self._btn_prompt_architekta.SetToolTip(t("rezyser.btn_prompt_architekta_tooltip"))


        lbl_pamiec = wx.StaticText(self, label=t("rezyser.lbl_pamiec_dlugotrwala"))

        self._txt_pamiec = wx.TextCtrl(
            self,
            style=wx.TE_MULTILINE,
            name=t("rezyser.txt_pamiec_name"),
        )
        self._txt_pamiec.SetHint(t("rezyser.txt_pamiec_hint"))
        self._txt_pamiec.SetToolTip(t("rezyser.txt_pamiec_tooltip"))

        self._btn_zapisz_pamiec = wx.Button(self, label=t("rezyser.btn_zapisz_pamiec_label"))
        self._btn_zapisz_pamiec.SetToolTip(t("rezyser.btn_zapisz_pamiec_tooltip"))

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(lbl_sb_heading, flag=wx.ALL, border=BORDER)
        sizer.Add(lbl_ksiega,     flag=wx.LEFT | wx.RIGHT | wx.TOP, border=BORDER)
        sizer.Add(
            self._txt_ksiega_swiata,
            proportion=2,
            flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP,
            border=BORDER,
        )
        sizer.Add(self._btn_zapisz_ksiege, flag=wx.ALL, border=BORDER)
        sizer.Add(
            self._btn_prompt_architekta,
            flag=wx.LEFT | wx.RIGHT | wx.BOTTOM,
            border=BORDER,
        )
        sizer.Add(
            wx.StaticLine(self),
            flag=wx.EXPAND | wx.LEFT | wx.RIGHT,
            border=BORDER,
        )
        sizer.Add(lbl_pamiec, flag=wx.LEFT | wx.RIGHT | wx.TOP, border=BORDER)

        sizer.Add(
            self._txt_pamiec,
            proportion=1,
            flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP,
            border=BORDER,
        )
        sizer.Add(self._btn_zapisz_pamiec, flag=wx.ALL, border=BORDER)
        return sizer

    # ------------------------------------------------------------------
    # BLOK D – Obszar roboczy (prawa kolumna, kompozycja)
    # ------------------------------------------------------------------
    def _zbuduj_obszar_roboczy(
        self,
        BORDER: int,
        pasek_pliku_sizer: wx.BoxSizer,
    ) -> wx.BoxSizer:
        lbl_main_heading = wx.StaticText(self, label=t("rezyser.main_heading"))
        mf = lbl_main_heading.GetFont()
        mf.SetPointSize(11)
        mf.MakeBold()
        lbl_main_heading.SetFont(mf)

        radiobox_sizer      = self._zbuduj_radiobox_trybu(BORDER)
        panel_struktury     = self._zbuduj_panel_struktury(BORDER)
        podglad_sizer       = self._zbuduj_podglad_historii(BORDER)
        panel_opcji_burzy   = self._zbuduj_panel_opcji_burzy(BORDER)
        pole_instrukcji     = self._zbuduj_pole_instrukcji(BORDER)
        panel_postprodukcji = self._zbuduj_panel_postprodukcji(BORDER)
        panel_elevenlabs    = self._zbuduj_panel_elevenlabs(BORDER)
        panel_screen_reader = self._zbuduj_panel_screen_reader(BORDER)
        wskaznik_sizer      = self._zbuduj_wskaznik_pamieci_modelu(BORDER)


        sep = lambda: wx.StaticLine(self)   # noqa: E731

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(lbl_main_heading, flag=wx.ALL, border=BORDER)
        sizer.Add(pasek_pliku_sizer, flag=wx.EXPAND)
        sizer.Add(sep(), flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=BORDER)
        sizer.Add(radiobox_sizer, flag=wx.EXPAND)
        sizer.Add(panel_struktury, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=BORDER)
        sizer.Add(sep(), flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=BORDER)
        sizer.Add(wskaznik_sizer, flag=wx.EXPAND)
        sizer.Add(sep(), flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=BORDER)
        sizer.Add(podglad_sizer, proportion=1, flag=wx.EXPAND)
        sizer.Add(sep(), flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=BORDER)
        # v15.2: panel opcji Burzy między podglądem historii a polem instrukcji.
        # Domyślnie ukryty; pokazuje się po sukcesie Burzy lub przy wczytaniu
        # projektu z istniejącym `.brainstorm.json`. Tab-order naturalny —
        # gracz po przeczytaniu opcji może wybrać przyciskiem (lub Enter +
        # focus przesuwa się dalej do pola Instrukcji).
        sizer.Add(panel_opcji_burzy, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=BORDER)
        sizer.Add(pole_instrukcji, flag=wx.EXPAND)
        sizer.Add(sep(), flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=BORDER)
        sizer.Add(panel_postprodukcji, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=BORDER)
        # Most ElevenLabs (v16.0) — należy do trybu Skrypt (teatr czytany),
        # nie do postprodukcji Audiobooka. Widoczność w `_refresh_ui_state`.
        sizer.Add(panel_elevenlabs, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=BORDER)
        # Wersja dla czytników ekranu (v16.1) — też tryb Skrypt, ale NIEZALEŻNIE
        # od klucza ElevenLabs (akcent przez ortografię + lang, nie przez API).
        sizer.Add(panel_screen_reader, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=BORDER)
        return sizer

    # ------------------------------------------------------------------
    # BLOK D.1 – RadioBox wyboru trybu pracy
    # ------------------------------------------------------------------
    def _zbuduj_radiobox_trybu(self, BORDER: int) -> wx.BoxSizer:
        # wx.RadioBox z choices=[] rzuca wxAssertionError. Skrajny przypadek
        # braku trybów (sprawdzony w __init__ + komunikat A11y) zabezpieczamy
        # placeholderem, żeby panel zbudował się normalnie.
        choices = [p.etykieta for p in self._przepisy] or [
            t("rezyser.placeholder_brak_trybow")
        ]
        self._rb_mode = wx.RadioBox(
            self,
            label=t("rezyser.rb_tryb_label"),
            choices=choices,
            majorDimension=1,
            style=wx.RA_SPECIFY_COLS,
            name=t("rezyser.rb_tryb_name"),
        )
        self._rb_mode.SetToolTip(t("rezyser.rb_tryb_tooltip"))

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self._rb_mode, flag=wx.EXPAND | wx.ALL, border=BORDER)
        return sizer

    # ------------------------------------------------------------------
    # BLOK E – Panel Zarządzania Strukturą (dynamicznie ukrywany)
    # ------------------------------------------------------------------
    def _zbuduj_panel_struktury(self, BORDER: int) -> wx.Panel:
        self._pnl_struktura = wx.Panel(self)

        lbl_struktura = wx.StaticText(self._pnl_struktura, label=t("rezyser.struktura_heading"))
        sf = lbl_struktura.GetFont()
        sf.SetPointSize(10)
        sf.MakeBold()
        lbl_struktura.SetFont(sf)

        self._btn_prolog = wx.Button(
            self._pnl_struktura,
            label=t("rezyser.btn_prolog_label"),
            name=t("rezyser.btn_prolog_name"),
        )
        self._btn_prolog.SetToolTip(t("rezyser.btn_prolog_tooltip"))

        self._btn_epilog = wx.Button(
            self._pnl_struktura,
            label=t("rezyser.btn_epilog_label"),
            name=t("rezyser.btn_epilog_name"),
        )
        self._btn_epilog.SetToolTip(t("rezyser.btn_epilog_tooltip"))

        self._btn_rozdzial = wx.Button(
            self._pnl_struktura,
            label=t("rezyser.btn_rozdzial_label", numer_rozdzialu=1),
            name=t("rezyser.btn_rozdzial_name"),
        )
        self._btn_rozdzial.SetToolTip(t("rezyser.btn_rozdzial_tooltip"))

        self._btn_akt = wx.Button(
            self._pnl_struktura,
            label=t("rezyser.btn_akt_label", numer_aktu=1),
            name=t("rezyser.btn_akt_name"),
        )
        self._btn_akt.SetToolTip(t("rezyser.btn_akt_tooltip"))

        self._btn_scena = wx.Button(
            self._pnl_struktura,
            label=t("rezyser.btn_scena_label", numer_sceny=1),
            name=t("rezyser.btn_scena_name"),
        )
        self._btn_scena.SetToolTip(t("rezyser.btn_scena_tooltip"))

        prolog_epilog_row = wx.BoxSizer(wx.HORIZONTAL)
        prolog_epilog_row.Add(self._btn_prolog, flag=wx.RIGHT, border=6)
        prolog_epilog_row.Add(self._btn_epilog)

        akt_scena_row = wx.BoxSizer(wx.HORIZONTAL)
        akt_scena_row.Add(self._btn_akt, flag=wx.RIGHT, border=6)
        akt_scena_row.Add(self._btn_scena)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(lbl_struktura,      flag=wx.ALL,                         border=BORDER)
        sizer.Add(prolog_epilog_row,  flag=wx.LEFT | wx.RIGHT | wx.BOTTOM, border=BORDER)
        sizer.Add(self._btn_rozdzial, flag=wx.LEFT | wx.RIGHT | wx.BOTTOM, border=BORDER)
        sizer.Add(akt_scena_row,      flag=wx.LEFT | wx.RIGHT | wx.BOTTOM, border=BORDER)
        self._pnl_struktura.SetSizer(sizer)
        return self._pnl_struktura

    # ------------------------------------------------------------------
    # BLOK E.1 – Podgląd pełnej historii
    # ------------------------------------------------------------------
    def _zbuduj_podglad_historii(self, BORDER: int) -> wx.BoxSizer:
        lbl_full_story = wx.StaticText(self, label=t("rezyser.lbl_podglad_historii"))

        self._txt_full_story = wx.TextCtrl(
            self,
            style=wx.TE_MULTILINE | wx.TE_READONLY,
            name=t("rezyser.txt_podglad_name"),
        )
        self._txt_full_story.SetHint(t("rezyser.txt_podglad_hint"))

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(lbl_full_story, flag=wx.LEFT | wx.RIGHT | wx.TOP, border=BORDER)
        sizer.Add(
            self._txt_full_story,
            proportion=1,
            flag=wx.EXPAND | wx.ALL,
            border=BORDER,
        )
        return sizer

    # ------------------------------------------------------------------
    # BLOK E.1b – Panel opcji Burzy Mózgów (v15.2)
    # ------------------------------------------------------------------
    # Dynamicznie pokazywany po sukcesie Burzy. Zawiera 3 przyciski
    # (po jednym per opcja z JSON-a LLM) + opcjonalny label streszczenia.
    # Klik przycisku wpisuje pełen szkic prompta (cel_sceny od LLM +
    # doklejka_celu_sceny z yaml) do pola Instrukcji — gracz dopisuje
    # własne uwagi reżyserskie i wysyła w trybie Skrypt/Audiobook.
    # Po wysyłce produkcyjnej `proj.usun_brainstorm` + ukrycie panelu.
    # Po wczytaniu projektu: jeśli `.brainstorm.json` istnieje, panel
    # jest rebuildowany (gracz wciąż widzi ostatnie opcje sprzed paukacji).

    def _zbuduj_panel_opcji_burzy(self, BORDER: int) -> wx.Panel:
        self._pnl_opcji_burzy = wx.Panel(self, name=t("rezyser.pnl_opcji_burzy_name"))

        # Label nagłówek panelu
        self._lbl_opcji_burzy = wx.StaticText(
            self._pnl_opcji_burzy,
            label=t("rezyser.lbl_opcji_burzy"),
        )
        f = self._lbl_opcji_burzy.GetFont()
        f.MakeBold()
        self._lbl_opcji_burzy.SetFont(f)

        # Label streszczenia (widoczny tylko gdy LLM wygenerował streszczenie).
        # Multilinia + read-only — gracz może skopiować treść do Pamięci
        # Długotrwałej, ale nie edytuje.
        self._txt_opcji_burzy_streszczenie = wx.TextCtrl(
            self._pnl_opcji_burzy,
            style=wx.TE_MULTILINE | wx.TE_READONLY,
            name=t("rezyser.txt_streszczenie_burzy_name"),
        )
        self._txt_opcji_burzy_streszczenie.SetMinSize((-1, 80))
        self._txt_opcji_burzy_streszczenie.Hide()

        # Kontener przycisków — populowany dynamicznie przez `_przeladuj_opcje_burzy`.
        self._sizer_przyciskow_burzy = wx.BoxSizer(wx.VERTICAL)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self._lbl_opcji_burzy,                flag=wx.ALL, border=BORDER)
        sizer.Add(self._txt_opcji_burzy_streszczenie,   flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, border=BORDER)
        sizer.Add(self._sizer_przyciskow_burzy,         flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, border=BORDER)
        self._pnl_opcji_burzy.SetSizer(sizer)

        # Panel jest ukryty domyślnie — pokazuje się dopiero po sukcesie Burzy.
        self._pnl_opcji_burzy.Hide()
        return self._pnl_opcji_burzy

    def _przeladuj_opcje_burzy(
        self,
        opcje:        list[dict[str, str]],
        streszczenie: str,
    ) -> None:
        """Rebuilduje przyciski w panelu opcji Burzy z list[dict].

        Wzorzec analogiczny do :meth:`gui_opowiesci.OpowiesciPanel._przeladuj_wybory`:
        1. Wyczyść sizer (delete_windows=True) — usuwa stare wx.Button.
        2. Dodaj nowy przycisk per opcja z bind-em na :meth:`_on_kliknieto_opcje_burzy`
           (closure z `cel_sceny` przez default arg lambdy — chroni przed
           late-binding gotcha).
        3. `Layout()` panelu i okna nadrzędnego (sizery zewnętrzne też
           muszą się przeliczyć po zmianie zawartości).
        4. Pokaż / ukryj label streszczenia w zależności od ``streszczenie``.
        5. Pokaż cały panel (`_pnl_opcji_burzy`) — był ukryty.
        """
        self._sizer_przyciskow_burzy.Clear(delete_windows=True)

        # Streszczenie — pokazujemy tylko gdy LLM celowo je wygenerował
        # (sufiks alarm/streszczenie był aktywny). Pusty string → ukrywamy.
        if streszczenie:
            self._txt_opcji_burzy_streszczenie.SetValue(streszczenie)
            self._txt_opcji_burzy_streszczenie.Show()
        else:
            self._txt_opcji_burzy_streszczenie.Hide()

        # Doklejkę pobieramy z przepisu BURZY, nie z aktualnie zaznaczonego
        # trybu w RadioBox-ie — opcje Burzy są zawsze owocem Burzy, a doklejka
        # `[Reżyserze]/[DYREKTYWA]` żyje wyłącznie w `tryb_burza.yaml`. Dzięki
        # temu działa też ścieżka wczytania projektu z `saved_mode` 1/2, gdzie
        # RadioBox przeskakuje na tryb produkcyjny (Skrypt/Audiobook) PRZED tym
        # przeładowaniem. Patrz :meth:`_przepis_burzy`. Cache yaml —
        # `rezyser_ai.doklejka_celu_sceny` czyta atrybut PrzepisRezysera, tani.
        przepis_burzy = self._przepis_burzy()
        doklejka = rai.doklejka_celu_sceny(przepis_burzy) if przepis_burzy else ""

        for i, opcja in enumerate(opcje, start=1):
            tytul = (opcja.get("tytul") or "").strip()
            opis = (opcja.get("opis") or "").strip()
            cel_sceny = (opcja.get("cel_sceny") or "").strip()
            if not tytul or not cel_sceny:
                continue   # halucynacja — zignoruj

            etykieta = t("rezyser.btn_opcja_burzy_format", numer=i, tytul=tytul)
            btn = wx.Button(self._pnl_opcji_burzy, label=etykieta)
            btn.SetToolTip(opis or tytul)
            # Closure z `cel_sceny` ORAZ `doklejka` jako default args —
            # każdy przycisk dostaje SWÓJ tekst, nie ostatniego z pętli.
            btn.Bind(
                wx.EVT_BUTTON,
                lambda evt, c=cel_sceny, d=doklejka:
                    self._on_kliknieto_opcje_burzy(evt, c, d),
            )
            self._sizer_przyciskow_burzy.Add(btn, flag=wx.EXPAND | wx.BOTTOM, border=4)

        self._pnl_opcji_burzy.Layout()
        self._pnl_opcji_burzy.Show()
        self.Layout()

    def _ukryj_panel_opcji_burzy(self) -> None:
        """Ukrywa panel opcji Burzy i czyści przyciski (po wysyłce produkcyjnej)."""
        self._sizer_przyciskow_burzy.Clear(delete_windows=True)
        self._txt_opcji_burzy_streszczenie.SetValue("")
        self._txt_opcji_burzy_streszczenie.Hide()
        self._pnl_opcji_burzy.Hide()
        self.Layout()

    def _on_kliknieto_opcje_burzy(
        self,
        _event:    wx.Event,
        cel_sceny: str,
        doklejka:  str,
    ) -> None:
        """Klik na przycisku opcji Burzy — wpisuje pełen szkic do Instrukcji.

        Format wpisanego tekstu:

            [CEL SCENY]: <cel_sceny z JSON-a LLM>

            <doklejka_celu_sceny z yaml — [Reżyserze: ...] + [DYREKTYWA]: ...>

        Doklejka jest deterministyczna (Python czyta z yaml), `cel_sceny`
        twórczo wymyślony przez LLM. Gracz może edytować całość przed
        wysyłką — typowo dopisuje swoje uwagi reżyserskie do linii
        `[Reżyserze: ...]`. NIE wysyłamy automatycznie.

        A11y: focus na pole instrukcji, kursor na końcu — NVDA odczyta
        wstawiony tekst, gracz dopisuje dalej.
        """
        sklejka = f"[CEL SCENY]: {cel_sceny}\n\n{doklejka}".rstrip() + "\n"
        self._txt_user_input.SetValue(sklejka)
        self._txt_user_input.SetInsertionPointEnd()
        self._txt_user_input.SetFocus()

    # ------------------------------------------------------------------
    # BLOK E.2 – Pole instrukcji dla AI + przycisk Wyślij
    # ------------------------------------------------------------------
    def _zbuduj_pole_instrukcji(self, BORDER: int) -> wx.BoxSizer:
        lbl_user_input = wx.StaticText(self, label=t("rezyser.lbl_instrukcje"))

        self._txt_user_input = wx.TextCtrl(
            self,
            style=wx.TE_MULTILINE,
            name=t("rezyser.txt_instrukcje_name"),
        )
        self._txt_user_input.SetHint(t("rezyser.txt_instrukcje_hint"))
        self._txt_user_input.SetMinSize((-1, 100))

        self._btn_wyslij = wx.Button(self, label=t("rezyser.btn_wyslij_label"))
        self._btn_wyslij.SetToolTip(t("rezyser.btn_wyslij_tooltip"))

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(lbl_user_input,       flag=wx.LEFT | wx.RIGHT | wx.TOP, border=BORDER)
        sizer.Add(self._txt_user_input, flag=wx.EXPAND | wx.ALL,          border=BORDER)
        sizer.Add(self._btn_wyslij,     flag=wx.LEFT | wx.BOTTOM | wx.TOP, border=BORDER)
        return sizer

    # ------------------------------------------------------------------
    # BLOK F – Panel Postprodukcji
    # ------------------------------------------------------------------
    def _zbuduj_panel_postprodukcji(self, BORDER: int) -> wx.Panel:
        """BLOK F (od v18.12 dynamiczny): przycisk per narzędzie postprodukcyjne.

        Przyciski powstają dla WSZYSTKICH postprodukcji paczki — etykieta
        wprost z YAML (jest już zlokalizowana per język paczki, jak etykiety
        trybów w RadioBoxie). Które przyciski są widoczne dla bieżącego trybu,
        decyduje `_refresh_ui_state` filtrem `dla_trybow`. Gauge i etykieta
        statusu są WSPÓLNE dla wszystkich narzędzi — naraz działa najwyżej
        jeden worker (guard `is_alive` na wejściu handlera).
        """
        self._pnl_postprodukcja = wx.Panel(self)

        lbl_postprod = wx.StaticText(self._pnl_postprodukcja, label=t("rezyser.postprod_heading"))
        pf = lbl_postprod.GetFont()
        pf.SetPointSize(10)
        pf.MakeBold()
        lbl_postprod.SetFont(pf)

        lbl_postprod_info = wx.StaticText(
            self._pnl_postprodukcja,
            label=t("rezyser.postprod_info"),
        )

        self._btn_postprod: dict[str, wx.Button] = {}
        for przepis_pp in self._postprodukcje:
            # `name=` (accessible name NVDA) + wspólny tooltip z wymaganiami —
            # audyt 18.12, NISKA-1: stary przycisk tytułów je miał, dynamiczne
            # nie mogą być gorsze.
            btn = wx.Button(
                self._pnl_postprodukcja,
                label=przepis_pp.etykieta,
                name=przepis_pp.etykieta,
            )
            btn.SetToolTip(t("rezyser.postprod_info"))
            self._btn_postprod[przepis_pp.id] = btn

        self._gauge_postprod = wx.Gauge(self._pnl_postprodukcja, range=100)
        self._gauge_postprod.Hide()

        self._lbl_postprod_status = wx.StaticText(self._pnl_postprodukcja, label="")
        self._lbl_postprod_status.Hide()

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(lbl_postprod,              flag=wx.ALL,                              border=BORDER)
        sizer.Add(lbl_postprod_info,         flag=wx.LEFT | wx.RIGHT | wx.BOTTOM,      border=BORDER)
        for btn in self._btn_postprod.values():
            sizer.Add(btn,                   flag=wx.LEFT | wx.BOTTOM,                 border=BORDER)
        sizer.Add(
            self._gauge_postprod,
            flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP,
            border=BORDER,
        )
        sizer.Add(self._lbl_postprod_status, flag=wx.LEFT | wx.BOTTOM,                 border=BORDER)
        self._pnl_postprodukcja.SetSizer(sizer)
        return self._pnl_postprodukcja

    def _zbuduj_panel_elevenlabs(self, BORDER: int) -> wx.Panel:
        """Panel mostu ElevenLabs Studio — należy do trybu SKRYPT (teatr czytany).

        Świadomie NIE w panelu postprodukcji Audiobooka: most buduje wielogłosowy
        projekt z teatru czytanego (tryb Skrypt), a nie z prozy audiobooka. Dodatkowo
        ochrona trybu (`_zapisany_tryb`) zablokowałaby dotarcie do Audiobooka dla
        projektu zapisanego jako Skrypt. Widoczność: tryb Skrypt + ważny klucz EL
        (`_el_dostepne`) — patrz ``_refresh_ui_state``. Przycisk budowy: Etap 5.
        """
        self._pnl_el = wx.Panel(self)

        lbl_el = wx.StaticText(self._pnl_el, label=t("rezyser.el_heading"))
        ef = lbl_el.GetFont()
        ef.SetPointSize(10)
        ef.MakeBold()
        lbl_el.SetFont(ef)

        lbl_el_info = wx.StaticText(self._pnl_el, label=t("rezyser.el_info"))

        self._btn_el_obsada = wx.Button(
            self._pnl_el,
            label=t("rezyser.el_btn_obsada_label"),
            name=t("rezyser.el_btn_obsada_name"),
        )
        self._btn_el_obsada.SetToolTip(t("rezyser.el_btn_obsada_tooltip"))
        self._btn_el_obsada.Bind(wx.EVT_BUTTON, self._on_el_obsada)

        self._btn_el_build = wx.Button(
            self._pnl_el,
            label=t("rezyser.el_btn_build_label"),
            name=t("rezyser.el_btn_build_name"),
        )
        self._btn_el_build.SetToolTip(t("rezyser.el_btn_build_tooltip"))
        self._btn_el_build.Bind(wx.EVT_BUTTON, self._on_el_build)

        # Status budowy (A11y: SetName czytane przez NVDA). Domyślnie ukryty.
        self._lbl_el_status = wx.StaticText(self._pnl_el, label="")
        self._lbl_el_status.Hide()

        btn_row = wx.BoxSizer(wx.HORIZONTAL)
        btn_row.Add(self._btn_el_obsada, flag=wx.RIGHT, border=BORDER)
        btn_row.Add(self._btn_el_build)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(lbl_el,             flag=wx.ALL,                         border=BORDER)
        sizer.Add(lbl_el_info,        flag=wx.LEFT | wx.RIGHT | wx.BOTTOM, border=BORDER)
        sizer.Add(btn_row,            flag=wx.LEFT | wx.BOTTOM,            border=BORDER)
        sizer.Add(self._lbl_el_status, flag=wx.LEFT | wx.RIGHT | wx.BOTTOM, border=BORDER)
        self._pnl_el.SetSizer(sizer)
        return self._pnl_el

    # ------------------------------------------------------------------
    # BLOK F2 – Wersja dla czytników ekranu (v16.1) — tryb SKRYPT
    # ------------------------------------------------------------------
    def _zbuduj_panel_screen_reader(self, BORDER: int) -> wx.Panel:
        """Panel generatora HTML dla czytników ekranu — tryb SKRYPT.

        Niezależny od mostu ElevenLabs: akcent realizowany przez psucie
        ortografii + ``<span lang>``, nie przez API. Widoczny zawsze w trybie
        Skrypt (bez wymogu klucza EL) — patrz ``_refresh_ui_state``. Generacja
        jest synchroniczna (czysty tekst, bez sieci), więc bez wątku tła.
        """
        self._pnl_sr = wx.Panel(self)

        lbl_sr = wx.StaticText(self._pnl_sr, label=t("rezyser.sr_heading"))
        sf = lbl_sr.GetFont()
        sf.SetPointSize(10)
        sf.MakeBold()
        lbl_sr.SetFont(sf)

        lbl_sr_info = wx.StaticText(self._pnl_sr, label=t("rezyser.sr_info"))

        self._btn_sr = wx.Button(
            self._pnl_sr,
            label=t("rezyser.btn_sr_label"),
            name=t("rezyser.btn_sr_name"),
        )
        self._btn_sr.SetToolTip(t("rezyser.btn_sr_tooltip"))

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(lbl_sr,      flag=wx.ALL,                         border=BORDER)
        sizer.Add(lbl_sr_info, flag=wx.LEFT | wx.RIGHT | wx.BOTTOM, border=BORDER)
        sizer.Add(self._btn_sr, flag=wx.LEFT | wx.BOTTOM,           border=BORDER)
        self._pnl_sr.SetSizer(sizer)
        return self._pnl_sr

    # ------------------------------------------------------------------
    # BLOK G – Wskaźnik okna kontekstowego AI
    # ------------------------------------------------------------------
    def _zbuduj_wskaznik_pamieci_modelu(self, BORDER: int) -> wx.BoxSizer:
        lbl_kontekst = wx.StaticText(self, label=t("rezyser.lbl_pamiec_modelu"))
        kf = lbl_kontekst.GetFont()
        kf.SetWeight(wx.FONTWEIGHT_BOLD)
        lbl_kontekst.SetFont(kf)

        self._gauge_kontekst = wx.Gauge(
            self, range=100, style=wx.GA_HORIZONTAL | wx.GA_SMOOTH
        )
        self._gauge_kontekst.SetValue(0)

        self._lbl_kontekst_status = wx.TextCtrl(
            self,
            value=t("rezyser.lbl_pamiec_modelu_start"),
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.NO_BORDER,
            name=t("rezyser.pamiec_modelu_status_name"),
        )
        self._lbl_kontekst_status.SetBackgroundColour(self.GetBackgroundColour())
        self._lbl_kontekst_status.SetMinSize((-1, 60))

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(lbl_kontekst, flag=wx.LEFT | wx.RIGHT | wx.TOP, border=BORDER)
        sizer.Add(
            self._gauge_kontekst,
            flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP,
            border=BORDER,
        )
        sizer.Add(
            self._lbl_kontekst_status,
            flag=wx.EXPAND | wx.LEFT | wx.RIGHT,
            border=BORDER,
        )
        return sizer


    # ------------------------------------------------------------------
    # Podpięcie zdarzeń
    # ------------------------------------------------------------------
    def _bind_events(self) -> None:
        self._btn_load.Bind(wx.EVT_BUTTON,          self._on_load)
        self._btn_hard_reset.Bind(wx.EVT_BUTTON,    self._on_hard_reset)
        self._btn_otworz_narracje.Bind(wx.EVT_BUTTON, self._on_otworz_narracje)
        self._btn_przeladuj.Bind(wx.EVT_BUTTON,     self._on_przeladuj_z_dysku)
        self._btn_zapisz_ksiege.Bind(wx.EVT_BUTTON, self._on_zapisz_ksiege)
        self._btn_prompt_architekta.Bind(wx.EVT_BUTTON, self._on_prompt_architekta)
        self._btn_zapisz_pamiec.Bind(wx.EVT_BUTTON, self._on_zapisz_pamiec)
        self._btn_wyslij.Bind(wx.EVT_BUTTON,        self._on_wyslij)

        self._txt_file_name.Bind(wx.EVT_TEXT,         self._on_file_name_change)
        self._txt_file_name.Bind(wx.EVT_TEXT_ENTER,   self._on_load)
        self._txt_pamiec.Bind(wx.EVT_TEXT,             self._on_pamiec_change)
        self._txt_user_input.Bind(wx.EVT_TEXT,         self._on_user_input_change)

        self._rb_mode.Bind(wx.EVT_RADIOBOX, self._on_mode_change)

        self._btn_prolog.Bind(wx.EVT_BUTTON,   self._on_wstaw_prolog)
        self._btn_epilog.Bind(wx.EVT_BUTTON,   self._on_wstaw_epilog)
        self._btn_rozdzial.Bind(wx.EVT_BUTTON, self._on_wstaw_rozdzial)
        self._btn_akt.Bind(wx.EVT_BUTTON,      self._on_wstaw_akt)
        self._btn_scena.Bind(wx.EVT_BUTTON,    self._on_wstaw_scena)

        # Postprodukcje (v18.12): jeden handler, id narzędzia domknięte
        # w lambdzie (domyślny argument — klasyczny idiom przeciw późnemu
        # wiązaniu zmiennej pętli).
        for pp_id, btn in self._btn_postprod.items():
            btn.Bind(wx.EVT_BUTTON,
                     lambda _evt, i=pp_id: self._on_postprodukcja(i))
        self._btn_sr.Bind(wx.EVT_BUTTON, self._on_sr_generate)

    # ------------------------------------------------------------------
    # Odświeżanie stanu przycisków (Enable/Disable)
    # ------------------------------------------------------------------
    def _refresh_ui_state(self) -> None:
        """Aktualizuje stan Enabled/Disabled przycisków na podstawie stanu pamięci."""
        pamiec_zajeta = self._projekt.pamiec_zajeta
        pamiec_pusta  = not pamiec_zajeta
        nazwa_podana  = bool(self._txt_file_name.GetValue().strip())
        streszczenie_wpisane = bool(self._txt_pamiec.GetValue().strip())
        user_text_present    = bool(self._txt_user_input.GetValue().strip())
        przepis     = self._aktualny_przepis()
        tryb_zapisu = bool(przepis and przepis.zapis_do_pliku)
        struktura   = przepis.struktura if przepis else "brak"

        self._txt_file_name.Enable(not pamiec_zajeta)
        # v15.2.3: przycisk Wczytaj jest aktywny też przy pustym polu nazwy —
        # otwiera wtedy dialog wyboru projektu (A11y, gracz nie musi
        # pamiętać/przepisywać nazwy). Pole wypełnione = ścieżka eksperta
        # (bezpośrednia próba wczytania tej konkretnej nazwy).
        self._btn_load.Enable(pamiec_pusta)
        # Otwórz plik narracji — wymaga wpisanej nazwy. Istnienie pliku na
        # dysku sprawdzamy dopiero w handlerze (cheaper UX: gracz może
        # kliknąć i dostaje info „brak narracji" zamiast trzymać disabled).
        self._btn_otworz_narracje.Enable(nazwa_podana)
        # v15.5/v17.6: Przeładuj z dysku — wymaga nazwy i braku trwającej
        # generacji AI (pełny reload mutuje liczniki/full_story/summary_text;
        # nie kolidujemy z workerem).
        worker_w_toku = bool(self._worker_thread and self._worker_thread.is_alive())
        self._btn_przeladuj.Enable(nazwa_podana and not worker_w_toku)

        cos_do_wyczyszczenia = pamiec_zajeta or bool(
            self._txt_file_name.GetValue().strip()
            or self._txt_ksiega_swiata.GetValue().strip()
            or self._txt_pamiec.GetValue().strip()
        )
        self._btn_hard_reset.Enable(cos_do_wyczyszczenia)

        self._btn_zapisz_ksiege.Enable(nazwa_podana)
        self._btn_zapisz_pamiec.Enable(nazwa_podana and streszczenie_wpisane)

        _epilog_ma_tresc = self._projekt.epilog_ma_tresc

        if not self._api_dostepne:
            self._btn_wyslij.Disable()
        elif tryb_zapisu and not nazwa_podana:
            self._btn_wyslij.Disable()
        elif tryb_zapisu and _epilog_ma_tresc:
            self._btn_wyslij.Disable()
        elif not user_text_present:
            self._btn_wyslij.Disable()
        elif worker_w_toku:
            # v18.9: bez tego warunku wpisanie czegokolwiek w pole promptu
            # PODCZAS generacji (EVT_TEXT → ta metoda) odblokowywało Wyślij —
            # drugi klik startował równoległy worker na przestarzałym snapshocie
            # i oba dopisywały do `skrypty/<nazwa>.txt` (przeplatana narracja).
            self._btn_wyslij.Disable()
        else:
            self._btn_wyslij.Enable()

        _prolog_juz_jest   = self._projekt.ma_prolog
        _epilog_juz_jest   = self._projekt.ma_epilog
        _historia_niepusta = bool(self.full_story.strip())
        _blokada = self._projekt.ostatnia_linia_to_naglowek or _epilog_juz_jest


        # Panel struktury widoczny tylko gdy bieżący tryb to tryb zapisu z
        # niepustą `struktura` ORAZ zgadza się z utrwaloną decyzją projektu
        # (`_zapisany_tryb`, stabilne `id`). Świeży projekt (`_zapisany_tryb
        # is None`) ma wolny wybór — pierwsza wstawiona struktura lub udana
        # wysyłka produkcyjna materializuje decyzję. Po materializacji
        # przełączenie `_rb_mode` na Burzę chowa panel (Burza ma struktura:brak),
        # a powrót do drugiego trybu zapisu jest zablokowany przez EnableItem
        # niżej — więc gracz nigdy nie zobaczy „Akt 1" w projekcie Audiobook.
        tryb_zapisu_aktywny = (
            tryb_zapisu
            and struktura != "brak"
            and (self._zapisany_tryb is None
                 or (przepis is not None and self._zapisany_tryb == przepis.id))
        )

        if not tryb_zapisu_aktywny:
            self._pnl_struktura.Hide()
        else:
            jest_skrypt   = (struktura == "akty_sceny")
            jest_audiobok = (struktura == "rozdzialy")

            self._btn_rozdzial.Show(jest_audiobok)
            self._btn_akt.Show(jest_skrypt)
            self._btn_scena.Show(jest_skrypt)

            # Dynamiczne etykiety z aktualnymi licznikami (z i18n)
            self._btn_rozdzial.SetLabel(
                t("rezyser.btn_rozdzial_label", numer_rozdzialu=self.chapter_counter),
            )
            self._btn_akt.SetLabel(
                t("rezyser.btn_akt_label", numer_aktu=self.akt_counter),
            )
            self._btn_scena.SetLabel(
                t("rezyser.btn_scena_label", numer_sceny=self.scena_counter),
            )

            prolog_on   = nazwa_podana and not _historia_niepusta and not _prolog_juz_jest
            epilog_on   = nazwa_podana and _historia_niepusta and not _blokada
            rozdzial_on = nazwa_podana and not _blokada
            akt_on      = nazwa_podana and not _blokada
            scena_on    = nazwa_podana and not _blokada

            self._btn_prolog.Enable(prolog_on)
            self._btn_epilog.Enable(epilog_on)
            self._btn_rozdzial.Enable(rozdzial_on)
            self._btn_akt.Enable(akt_on)
            self._btn_scena.Enable(scena_on)

            # P2 (v17.4): panel struktury chowamy całkowicie, gdy żaden
            # WIDOCZNY w danym trybie przycisk nie jest aktywny. Bez tego —
            # gdy ostatnia linia historii to nagłówek (akt/scena/rozdział) lub
            # jest epilog (`_blokada`) — wszystkie przyciski lądowały disabled,
            # a wciąż pokazany, martwy panel łapał fokus NVDA przy tabulacji
            # („panel" bez żadnej akcji). To ten sam wzorzec, którym Opowieści
            # od początku chowają pusty panel wyborów (`_aktywuj_obszar_wyborow`).
            # Prolog/Epilog są zawsze widoczne; Rozdział tylko w Audiobooku,
            # Akt/Scena tylko w Skrypcie — liczymy więc per tryb.
            strukturalne_aktywne = prolog_on or epilog_on or (
                rozdzial_on if jest_audiobok else (akt_on or scena_on)
            )
            if strukturalne_aktywne:
                self._pnl_struktura.Show()
                self._pnl_struktura.Layout()
            else:
                self._pnl_struktura.Hide()

        # Ochrona przed przypadkową zmianą trybu twórczego (po stabilnym `id`,
        # nie po pozycji w RadioBox). Tryby BEZ zapisu (np. Burza) ZAWSZE
        # aktywne — to mechanizmy awaryjne/planowania, nie tryby zapisu sensu
        # stricto. Tryby zapisu zamrażamy na utrwalonej decyzji `_zapisany_tryb`
        # — gdy projekt zmaterializował jeden tryb produkcyjny, pozostałe tryby
        # zapisu są zablokowane (gracz nie zmiesza Skryptu z Audiobookiem).
        for i, p in enumerate(self._przepisy):
            if self._zapisany_tryb and p.zapis_do_pliku:
                self._rb_mode.EnableItem(i, p.id == self._zapisany_tryb)
            else:
                self._rb_mode.EnableItem(i, True)

        # Postprodukcje (v18.12): panel widoczny, gdy bieżący tryb ma
        # JAKIEKOLWIEK narzędzia (filtr `dla_trybow` z YAML — do v18.11 panel
        # był bramkowany na sztywno `id == "audiobook"`); przycisk per
        # narzędzie. `worker_zajety` w Enable to tylko pierwsza linia obrony —
        # właściwy guard jest na WEJŚCIU handlera (lekcja v18.9), bo każdy
        # refresh (np. wpisywanie nazwy) przelicza Enable od zera.
        postprod_dostepne = pr.filtruj_postprodukcje(self._postprodukcje, przepis)
        if postprod_dostepne:
            dostepne_id = {p.id for p in postprod_dostepne}
            worker_zajety = bool(
                self._worker_thread and self._worker_thread.is_alive()
            )
            postprod_on = (
                self._api_dostepne and nazwa_podana
                and _historia_niepusta and not worker_zajety
            )
            for pp_id, btn in self._btn_postprod.items():
                btn.Show(pp_id in dostepne_id)
                btn.Enable(postprod_on)
            # v18.19: ten sam wzorzec, co panel struktury (P2, v17.4) — panel
            # z samymi nieaktywnymi przyciskami wciąż łapał fokus NVDA jako
            # „panel" bez żadnej akcji. Do v18.11 stan „widoczny i cały
            # disabled" był rzadki (bramka `id == "audiobook"`), po
            # generalizacji postprodukcji (v18.12) stał się ZWYKŁY: każdy
            # świeży projekt bez nazwy albo bez narracji ma wszystkie
            # narzędzia nieaktywne.
            # WYJĄTEK: postęp w toku. Gauge i status mieszkają w tym panelu,
            # a `_start_postprodukcje` robi refresh JUŻ po starcie workera
            # (`worker_zajety` = True, wszystkie przyciski disabled) —
            # bez tego warunku pasek postępu i komunikat „pamięć w tle"
            # zniknęłyby dokładnie wtedy, kiedy są potrzebne (A11y).
            postep_w_toku = (
                self._gauge_postprod.IsShown()
                or self._lbl_postprod_status.IsShown()
            )
            if postprod_on or postep_w_toku:
                self._pnl_postprodukcja.Show()
                self._pnl_postprodukcja.Layout()
            else:
                self._pnl_postprodukcja.Hide()
        else:
            self._pnl_postprodukcja.Hide()

        # Most ElevenLabs (v16.0) — bespoke funkcja trybu SKRYPT (teatr czytany),
        # nie Audiobooka. Cały panel tylko gdy klucz EL ważny; obsadę można
        # edytować, gdy podano nazwę projektu (źródło skryptu z dysku).
        if przepis is not None and przepis.id == "skrypt" and self._el_dostepne:
            self._btn_el_obsada.Enable(nazwa_podana)
            self._btn_el_build.Enable(nazwa_podana)
            # v18.19: ten sam wzorzec P2 co panel struktury i postprodukcji —
            # bez nazwy projektu oba przyciski są disabled, a panel łapał
            # fokus NVDA jako martwy „panel". Status budowy mieszka w tym
            # panelu, więc trzyma go widocznym niezależnie od przycisków.
            if nazwa_podana or self._lbl_el_status.IsShown():
                self._pnl_el.Show()
            else:
                self._pnl_el.Hide()
        else:
            self._pnl_el.Hide()

        # Wersja dla czytników ekranu (v16.1) — bespoke funkcja trybu Skrypt,
        # NIEZALEŻNIE od klucza EL (akcent przez ortografię + lang, nie przez API).
        if przepis is not None and przepis.id == "skrypt":
            self._btn_sr.Enable(nazwa_podana)
            # v18.19: wzorzec P2 — jedyny przycisk panelu jest bezużyteczny
            # bez nazwy projektu (generator czyta skrypt z dysku), więc panel
            # bez nazwy jest martwy. Brak wyjątku „postęp w toku": generacja
            # HTML jest synchroniczna, panel nie ma własnego paska.
            self._pnl_sr.Show(nazwa_podana)
        else:
            self._pnl_sr.Hide()

        self._aktualizuj_pamiec_modelu()

        self.Layout()

    # ------------------------------------------------------------------
    # Handlery zmian w polach tekstowych
    # ------------------------------------------------------------------
    def _on_file_name_change(self, _event: wx.Event) -> None:
        self._refresh_ui_state()

    def _on_pamiec_change(self, _event: wx.Event) -> None:
        self._refresh_ui_state()

    def _on_user_input_change(self, _event: wx.Event) -> None:
        self._refresh_ui_state()

    def _on_mode_change(self, _event: wx.Event) -> None:
        self._refresh_ui_state()
        # 1b: przepis stał się aktywny — zapewnij `kod_jezyka` (w tle, jeśli pusty).
        self._zapewnij_kod_jezyka_w_tle()

    # ------------------------------------------------------------------
    # Helper: zbiera dostępne projekty do wczytania (A11y dialog wyboru)
    # ------------------------------------------------------------------
    def _zbierz_dostepne_projekty(self) -> list[str]:
        """Skanuje folder `skrypty/` i zwraca posortowaną listę nazw projektów.

        Kryterium: plik `.txt` w `skrypty/`, którego nazwa NIE kończy się
        sufiksem pliku wyniku którejkolwiek postprodukcji (np. `_audyt` — audyt
        18.12, ŚREDNIA-2: raport narzędzia to derived-data, nie samodzielny
        projekt). Od v18.13 obejmuje to również streszczenia: Pamięć Długotrwała
        jest postprodukcją, więc jej sufiks przychodzi z YAML-a zamiast
        z hard-kodu.

        v18.14 (KRYTYCZNE): filtrujemy po unii sufiksów ze WSZYSTKICH paczek
        (`pr.sufiksy_wynikow_wszystkich_paczek`), a nie po liście z paczki języka
        UI. Sufiksy są od tego wydania lokalizowane, więc plik pamięci wytworzony
        przy niemieckim interfejsie (`_zusammenfassung`) trafiłby u polskiego
        usera na listę PROJEKTÓW — a po wczytaniu silnik dopisywałby tury do
        streszczenia. Unia zawiera też oba sufiksy fallbackowe (`_overview`,
        historyczny `_streszczenie`), więc pliki sprzed v18.13 i pliki
        z nieobecnych paczek są rozpoznawane bez żadnego YAML-a.

        Pliki `.md` (Księga Świata) traktujemy jako opcjonalne — gracze, którzy
        nigdy nie zapisali księgi, też mają prawo zobaczyć swoje projekty na
        liście wyboru.

        Zwraca pustą listę gdy folder `skrypty/` nie istnieje lub jest
        pusty po filtracji — wywołujący `_on_load` decyduje wtedy o
        odpowiednim komunikacie dla gracza.
        """
        app_dir = sciezki.KATALOG_BAZOWY_STR
        skrypty_dir = os.path.join(app_dir, cr.SKRYPTY_DIR)
        if not os.path.isdir(skrypty_dir):
            return []
        sufiksy_wynikow = tuple({
            *(p.sufiks_pliku_wyniku for p in self._postprodukcje
              if p.sufiks_pliku_wyniku),
            *pr.sufiksy_wynikow_wszystkich_paczek(),
        })
        projekty: list[str] = []
        for nazwa_pliku in os.listdir(skrypty_dir):
            if not nazwa_pliku.endswith(".txt"):
                continue
            rdzen = nazwa_pliku[:-len(".txt")]
            if rdzen.endswith(sufiksy_wynikow):
                continue
            projekty.append(rdzen)
        return sorted(projekty)

    # ------------------------------------------------------------------
    # Wczytywanie historii z pliku
    # ------------------------------------------------------------------
    def _on_load(self, _event: wx.Event) -> None:
        # Dwie ścieżki UX:
        # • pole nazwy puste → otwieramy dialog wyboru projektu (A11y —
        #   niewidomy gracz nie musi pamiętać i przepisywać nazwy pliku);
        # • pole nazwy wypełnione → próba bezpośredniego wczytania (ścieżka
        #   eksperta — Enter w polu nazwy lub klik po wpisaniu z pamięci).
        nazwa = self._txt_file_name.GetValue().strip()
        if not nazwa:
            projekty = self._zbierz_dostepne_projekty()
            if not projekty:
                wx.MessageBox(
                    t("rezyser.brak_projektow_tresc"),
                    t("rezyser.brak_projektow_tytul"),
                    wx.OK | wx.ICON_INFORMATION,
                    self,
                )
                self._txt_file_name.SetFocus()
                return
            with wx.SingleChoiceDialog(
                self,
                t("rezyser.dlg_wybierz_projekt_lbl"),
                t("rezyser.dlg_wybierz_projekt_tytul"),
                projekty,
            ) as dlg:
                # Lokalizacja etykiety „Cancel" — wbudowane dialogi wxPython
                # używają lokalizacji systemowej Windows, więc na PL-systemie
                # przycisk zostałby angielski. SetLabel po znalezieniu po ID
                # załatwia sprawę bez podmiany wxLocale (która zaburzyłaby
                # inne wbudowane dialogi, np. FileDialog → tłumaczone „Open").
                btn_cancel = dlg.FindWindowById(wx.ID_CANCEL)
                if btn_cancel is not None:
                    btn_cancel.SetLabel(t("common.btn_anuluj"))
                if dlg.ShowModal() != wx.ID_OK:
                    return
                nazwa = dlg.GetStringSelection()
            self._txt_file_name.SetValue(nazwa)

        # v18.14: sufiksy pamięci z paczki języka TREŚCI — przed wczytaniem,
        # bo rozstrzygnięcie pliku pamięci dzieje się wewnątrz `wczytaj`.
        self._odswiez_kandydatow_pamieci()
        try:
            wynik = self._projekt.wczytaj(
                nazwa,
                wybor_markera=self._dialog_wyboru_markera,
                wybor_pamieci=self._dialog_wyboru_pamieci,
            )
        except FileNotFoundError as exc:
            wx.MessageBox(
                t("rezyser.plik_nie_istnieje_tresc", tresc_bledu=str(exc)),
                t("rezyser.plik_nie_istnieje_tytul"),
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            return
        # `ValueError` obejmuje `UnicodeDecodeError` (v18.9): plik narracji
        # zapisany w Notatniku jako ANSI/cp1250 zamiast UTF-8 wywalał wczytanie
        # crash-dialogiem zamiast czytelnego komunikatu. Bliźniaczy
        # `_on_przeladuj_z_dysku` łapał ten przypadek od początku — wyrównujemy.
        except (OSError, ValueError) as exc:
            wx.MessageBox(
                t("rezyser.blad_odczytu_tresc", tresc_bledu=str(exc)),
                t("common.blad_odczytu_tytul"),
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return

        self._zasiej_gui_po_wczytaniu(wynik, nazwa)

        lore_info = (
            t("rezyser.status_wczytano_ksiega", nazwa_projektu=nazwa)
            if wynik.czy_ksiega_swiata else ""
        )
        if wynik.czy_streszczenie:
            status_msg = t(
                "rezyser.status_wczytano_streszczenie",
                nazwa_projektu=nazwa,
                lore_info=lore_info,
            )
        else:
            status_msg = t(
                "rezyser.status_wczytano_historia",
                nazwa_projektu=nazwa,
                liczba_znakow=wynik.liczba_znakow,
                lore_info=lore_info,
            )

        wx.MessageBox(status_msg, t("rezyser.status_wczytano_tytul"),
                      wx.OK | wx.ICON_INFORMATION, self)
        self._moze_ostrzec_o_odrzuconej_pamieci(wynik)
        # Punkt odniesienia pokazujemy przy WCZYTANIU tylko gdy faktycznie trzeba
        # było pytać o marker (anchor nieaktualny) lub zadziałał fallback sekcji
        # za długiej — przy normalnym wczytaniu (anchor z meta ważny) box byłby
        # zbędny obok statusu. Reload ma własną, bezwarunkową konfirmację.
        rek = wynik.rekoncyliacja
        if rek is not None and (rek.interaktywny or rek.sekcja_przekroczyla_limit):
            self._pokaz_punkt_odniesienia(rek)

    def _moze_ostrzec_o_odrzuconej_pamieci(self, wynik: "cr.WynikWczytania") -> None:
        """v18.14: nota, gdy reżyser anulował wybór spośród kilku plików pamięci.

        Bez niej puste pole „Pamięć Długotrwała" po wczytaniu wyglądałoby jak
        utrata danych — a pliki leżą na dysku nietknięte i wystarczy wczytać
        projekt ponownie, żeby dostać pytanie jeszcze raz. Wspólne dla „Wczytaj"
        i „Przeładuj projekt z dysku" (oba tory wołają `wczytaj`).
        """
        if not wynik.pamiec_odrzucona:
            return
        wx.MessageBox(
            t("rezyser.pamiec_wybor_anulowano_tresc"),
            t("rezyser.pamiec_wybor_anulowano_tytul"),
            wx.OK | wx.ICON_INFORMATION, self,
        )

    # ------------------------------------------------------------------
    # Wspólne sianie GUI po wczytaniu/przeładowaniu projektu (v17.6)
    # ------------------------------------------------------------------
    def _zasiej_gui_po_wczytaniu(
        self, wynik: "cr.WynikWczytania", nazwa: str,
    ) -> None:
        """Synchronizuje WSZYSTKIE widgety ze świeżo wczytanym stanem projektu.

        Wspólne dla „Wczytaj" i „Przeładuj projekt z dysku" — jeden tor, by
        oba zachowywały się identycznie (Księga, Pamięć, narracja, tryb, Burza).
        """
        self._txt_ksiega_swiata.SetValue(self.world_lore)
        self._txt_pamiec.SetValue(self.summary_text)
        self._txt_full_story.SetValue(self.full_story)
        self._txt_full_story.SetInsertionPointEnd()

        # D2: świeżo wczytany stan = „czysty" punkt odniesienia detektora zmian.
        self._ksiega_swiata_zapisana = self._txt_ksiega_swiata.GetValue()
        self._pamiec_zapisana = self._txt_pamiec.GetValue()
        # v18.13: wczytanie przepuściło narrację przez rekoncyliację, więc pamięć
        # robocza jest już przycięta — automat Pamięci Długotrwałej dostaje nową
        # szansę zadziałania, jeśli mimo to znów dobijemy do progu alarmowego.
        self._auto_pamiec_wykonane = False

        # `.mode` trzyma stabilne `id` trybu (od v18.5) — mapujemy na pozycję
        # w RadioBox po `id`, nie po wartości int (reorder `kolejnosc` bezpieczny).
        idx = None
        if wynik.saved_mode:
            idx = next(
                (i for i, p in enumerate(self._przepisy) if p.id == wynik.saved_mode),
                None,
            )
        if idx is not None:
            self._rb_mode.SetSelection(idx)
            self._zapisany_tryb = wynik.saved_mode
        else:
            # Stary projekt bez `.mode`, projekt tylko w Burzy, lub tryb usunięty
            # z paczki. Decyzja trybu zostanie utrwalona przy pierwszej strukturze
            # albo pierwszej udanej wysyłce produkcyjnej.
            self._zapisany_tryb = None

        # 1b: po wczytaniu przepis trybu zapisu jest aktywny — zapewnij `kod_jezyka`
        # (w tle), żeby nagłówki struktury trafiły w język treści, nie GUI.
        self._zapewnij_kod_jezyka_w_tle()
        # 3a: ostrzeż, jeśli nagłówki wczytanej treści rozjeżdżają się z językiem
        # przepisu (np. reżyser zmienił kod_jezyka po zapisaniu projektu).
        self._moze_ostrzec_o_jezyku_naglowkow(self.full_story)

        # v15.2: rebuild panelu opcji Burzy z `.brainstorm.json` jeśli istnieje.
        # Po wczytaniu projektu gracz wciąż widzi 3 opcje wygenerowane przy
        # poprzedniej sesji — nie musi pamiętać co planował, nie musi
        # ponownie odpalać Burzy. Plik istnieje tylko między Burzą a wysyłką
        # produkcyjną; jeśli go nie ma, panel pozostaje ukryty.
        try:
            brainstorm = self._projekt.wczytaj_brainstorm(nazwa)
        except Exception:
            brainstorm = None
        if brainstorm is not None:
            self._przeladuj_opcje_burzy(
                brainstorm["opcje"],
                brainstorm.get("streszczenie", ""),
            )
        else:
            # Bezpieczeństwo: gdyby panel był pokazany ze starszych
            # operacji (np. cykl Burza → wczytaj inny projekt bez brainstorm),
            # chowamy go żeby nie wprowadzać w błąd.
            self._ukryj_panel_opcji_burzy()

        self._refresh_ui_state()

    # ------------------------------------------------------------------
    # Wybór punktu odniesienia pamięci roboczej (v17.6) — callback dla core
    # ------------------------------------------------------------------
    def _lokalizuj_anuluj(self, dlg: wx.Dialog) -> None:
        """Tłumaczy systemowy przycisk „Cancel" wbudowanego dialogu na język UI.

        Wbudowane dialogi wxPython biorą etykietę z lokalizacji systemowej
        Windows — na PL-systemie zostałaby angielska. SetLabel po ID załatwia
        sprawę bez podmiany wxLocale (która zaburzyłaby inne dialogi systemowe).
        """
        btn_cancel = dlg.FindWindowById(wx.ID_CANCEL)
        if btn_cancel is not None:
            btn_cancel.SetLabel(t("common.btn_anuluj"))

    def _dialog_wyboru_pamieci(
        self, kandydaci: "list[tuple[str, str]]",
    ) -> int | None:
        """Callback `core_rezyser.wczytaj` — który plik jest Pamięcią Długotrwałą.

        Wołany TYLKO gdy projekt ma na dysku kilka plików pamięci (sufiksy są
        lokalizowane, a paczka może mieć dwa narzędzia pamięci — „pod siebie"
        i „pod AI"). Nie zgadujemy za reżysera: zła pamięć w kontekście to
        zafałszowana fabuła w kolejnych rozdziałach.

        Etykiety: nazwa pliku + data modyfikacji i rozmiar w znakach — po tym
        realnie da się poznać, który zapis jest świeższy (czytnik ekranu odczyta
        całą linię). Data w formacie ISO, bez lokalizacji: neutralna dla
        wszystkich 9 paczek i jednoznaczna dla NVDA.

        Anuluj → ``None`` = sesja bez pamięci; pliki zostają na dysku, a silnik
        traktuje projekt jak „bez pamięci" (przy długiej narracji pyta jeszcze
        o punkt odniesienia pamięci roboczej).
        """
        etykiety: list[str] = []
        for _suf, sciezka in kandydaci:
            nazwa_pliku = os.path.basename(sciezka)
            try:
                st = os.stat(sciezka)
                data = time.strftime("%Y-%m-%d %H:%M", time.localtime(st.st_mtime))
                etykiety.append(t("rezyser.pamiec_wybor_pozycja",
                                  plik=nazwa_pliku, data=data, bajty=st.st_size))
            except OSError:
                etykiety.append(nazwa_pliku)

        with wx.SingleChoiceDialog(
            self,
            t("rezyser.pamiec_wybor_lbl"),
            t("rezyser.pamiec_wybor_tytul"),
            etykiety,
        ) as dlg:
            self._lokalizuj_anuluj(dlg)
            dlg.SetSelection(0)
            if dlg.ShowModal() != wx.ID_OK:
                return None
            return dlg.GetSelection()

    def _dialog_wyboru_markera(
        self, markery: "list[cr.MarkerStruktury]", struktura: str,
    ) -> int | None:
        """Callback przekazywany do `core_rezyser.wczytaj` — pozwala graczowi
        wskazać punkt odniesienia pamięci roboczej, gdy historia jest za długa.

        ``struktura == "akty_sceny"`` (Skrypt) → dwustopniowo: Akty, potem Sceny
        wybranego aktu (z opcją „cały Akt"). Pozostałe (``"rozdzialy"``/``"brak"``)
        → płaska lista nagłówków. Anuluj na dowolnym etapie → ``None`` (silnik
        użyje fallbacku znakowego).
        """
        if struktura == "akty_sceny" and any(m.typ == "akt" for m in markery):
            return self._wybierz_marker_skrypt(markery)
        return self._wybierz_marker_plaski(markery)

    def _wybierz_marker_plaski(
        self, markery: "list[cr.MarkerStruktury]",
    ) -> int | None:
        """Płaski wybór (Audiobook): jedna lista nagłówków. Domyślnie zaznaczony
        ostatni (najbliższy końca — najczęstszy wybór)."""
        etykiety = [m.etykieta for m in markery]
        with wx.SingleChoiceDialog(
            self,
            t("rezyser.marker_dlg_plaski_lbl"),
            t("rezyser.marker_dlg_tytul"),
            etykiety,
        ) as dlg:
            self._lokalizuj_anuluj(dlg)
            dlg.SetSelection(len(etykiety) - 1)
            if dlg.ShowModal() != wx.ID_OK:
                return None
            return markery[dlg.GetSelection()].offset

    def _wybierz_marker_skrypt(
        self, markery: "list[cr.MarkerStruktury]",
    ) -> int | None:
        """Dwustopniowy wybór (Skrypt): Akt → Scena. Wybór samego Aktu (pozycja
        „cały Akt") startuje pamięć od nagłówka aktu; prolog/epilog/akt bez scen
        startują od własnego nagłówka."""
        etykiety = [m.etykieta for m in markery]
        with wx.SingleChoiceDialog(
            self,
            t("rezyser.marker_dlg_akt_lbl"),
            t("rezyser.marker_dlg_tytul"),
            etykiety,
        ) as dlg:
            self._lokalizuj_anuluj(dlg)
            dlg.SetSelection(len(etykiety) - 1)
            if dlg.ShowModal() != wx.ID_OK:
                return None
            wybrany = markery[dlg.GetSelection()]

        if not wybrany.sceny:
            # Prolog/Epilog/akt bez scen → bierzemy jego własny nagłówek.
            return wybrany.offset

        opcje = [t("rezyser.marker_dlg_caly_akt")] + [s.etykieta for s in wybrany.sceny]
        with wx.SingleChoiceDialog(
            self,
            t("rezyser.marker_dlg_scena_lbl"),
            t("rezyser.marker_dlg_tytul"),
            opcje,
        ) as dlg2:
            self._lokalizuj_anuluj(dlg2)
            dlg2.SetSelection(len(opcje) - 1)
            if dlg2.ShowModal() != wx.ID_OK:
                return None
            idx = dlg2.GetSelection()
        if idx == 0:
            return wybrany.offset            # „cały Akt" — od nagłówka aktu
        return wybrany.sceny[idx - 1].offset

    def _pokaz_punkt_odniesienia(
        self, rek: "cr.WynikRekoncyliacji | None",
    ) -> None:
        """Po wczytaniu/przeładowaniu jawnie informuje, od którego nagłówka
        startuje pamięć robocza AI (snap) lub że zadziałał fallback znakowy.
        Dla wariantu 'calosc' (cała historia w pamięci) — nic nie pokazuje."""
        if rek is None or rek.tryb == "calosc":
            return
        if rek.tryb == "snap":
            tresc = t(
                "rezyser.punkt_odniesienia_snap_tresc",
                naglowek=rek.naglowek_uzyty or "",
                liczba_znakow=rek.liczba_znakow,
            )
        elif rek.sekcja_przekroczyla_limit:
            # K3: wybrany akt/rozdział sam za długi — JEDEN szczery komunikat
            # ujawniający fallback zamiast bombardowania kolejnymi dialogami.
            tresc = t(
                "rezyser.punkt_odniesienia_za_dluga_tresc",
                naglowek=rek.naglowek_uzyty or "",
                liczba_znakow=rek.liczba_znakow,
            )
        else:
            tresc = t(
                "rezyser.punkt_odniesienia_fallback_tresc",
                liczba_znakow=rek.liczba_znakow,
            )
        wx.MessageBox(
            tresc, t("rezyser.punkt_odniesienia_tytul"),
            wx.OK | wx.ICON_INFORMATION, self,
        )

    # ------------------------------------------------------------------
    # Twardy Reset
    # ------------------------------------------------------------------
    def _on_hard_reset(self, _event: wx.Event) -> None:
        odp = wx.MessageBox(
            t("rezyser.hard_reset_pytanie"),
            t("rezyser.hard_reset_pytanie_tytul"),
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING,
            self,
        )
        if odp != wx.YES:
            return

        self._projekt.twardy_reset()
        self._auto_pamiec_wykonane = False
        # Mirror `.mode` zwalniamy — nowy projekt zaczyna z pustą decyzją
        # trybu, wszystkie 3 pozycje RadioBoxa znów wolne do wyboru.
        # (Twardy Reset zapomina o projekcie; „Przeładuj z dysku" przeciwnie —
        # synchronizuje pamięć z plikiem, zachowując tożsamość projektu.)
        self._zapisany_tryb = None

        self._txt_file_name.SetValue("")
        self._txt_file_name.Enable()
        self._txt_full_story.SetValue("")
        self._txt_ksiega_swiata.SetValue("")
        self._txt_pamiec.SetValue("")
        self._txt_user_input.SetValue("")

        self._refresh_ui_state()
        wx.MessageBox(
            t("rezyser.hard_reset_ok_tresc"),
            t("rezyser.hard_reset_ok_tytul"),
            wx.OK | wx.ICON_INFORMATION,
            self,
        )
        self._txt_file_name.SetFocus()

    # ------------------------------------------------------------------
    # Zapis Księgi Świata
    # ------------------------------------------------------------------
    def _on_zapisz_ksiege(self, _event: wx.Event) -> None:
        nazwa = self._txt_file_name.GetValue().strip()
        if not nazwa:
            wx.MessageBox(
                t("rezyser.brak_nazwy_ksiega_tresc"),
                t("rezyser.brak_nazwy_ksiega_tytul"),
                wx.OK | wx.ICON_WARNING,
                self,
            )
            self._txt_file_name.SetFocus()
            return

        tresc = self._txt_ksiega_swiata.GetValue().strip()
        if not tresc:
            wx.MessageBox(
                t("rezyser.ksiega_pusta_tresc"),
                t("rezyser.ksiega_pusta_tytul"),
                wx.OK | wx.ICON_WARNING,
                self,
            )
            self._txt_ksiega_swiata.SetFocus()
            return

        if self._projekt.nazwa_pliku != nazwa:
            self._projekt.nazwa_pliku = nazwa
        try:
            self._projekt.zapisz_ksiege_swiata(tresc)
            # D2: zapis = nowy „czysty" punkt odniesienia detektora zmian.
            self._ksiega_swiata_zapisana = self._txt_ksiega_swiata.GetValue()
            wx.MessageBox(
                t("rezyser.ksiega_zapisana_tresc", nazwa_projektu=nazwa),
                t("rezyser.ksiega_zapisana_tytul"),
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
        except Exception as exc:  # noqa: BLE001
            wx.MessageBox(
                t("rezyser.blad_zapisu_ksiegi", tresc_bledu=str(exc)),
                t("common.blad_zapisu_tytul"),
                wx.OK | wx.ICON_ERROR,
                self,
            )

    # ------------------------------------------------------------------
    # Prompt Architekta – dialog z gotowym promptem do skopiowania
    # ------------------------------------------------------------------
    def _on_prompt_architekta(self, _event: wx.Event) -> None:
        dlg = wx.Dialog(
            self,
            title=t("rezyser.prompt_arch_dlg_tytul"),
            size=(720, 560),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        sizer = wx.BoxSizer(wx.VERTICAL)

        lbl_head = wx.TextCtrl(
            dlg,
            value=t("rezyser.prompt_arch_instrukcja"),
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.NO_BORDER,
            name=t("rezyser.prompt_arch_instrukcja_name"),
        )
        lbl_head.SetBackgroundColour(dlg.GetBackgroundColour())
        lbl_head.SetMinSize((-1, 110))
        sizer.Add(lbl_head, flag=wx.ALL | wx.EXPAND, border=12)

        lbl_prompt = wx.StaticText(dlg, label=t("rezyser.prompt_arch_lbl"))
        f = lbl_prompt.GetFont()
        f.MakeBold()
        lbl_prompt.SetFont(f)
        sizer.Add(lbl_prompt, flag=wx.LEFT | wx.RIGHT, border=12)

        txt_prompt = wx.TextCtrl(
            dlg,
            value=self._prompt_architekta,
            style=wx.TE_MULTILINE | wx.TE_READONLY,
            name=t("rezyser.prompt_arch_tresc_name"),
        )
        sizer.Add(
            txt_prompt, proportion=1,
            flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, border=12,
        )

        btn_row = wx.BoxSizer(wx.HORIZONTAL)

        btn_kopiuj = wx.Button(
            dlg, label=t("rezyser.prompt_arch_btn_kopiuj"),
            name=t("rezyser.prompt_arch_btn_kopiuj_name"),
        )

        def _kopiuj(_e: wx.Event) -> None:
            dane = wx.TextDataObject(self._prompt_architekta)
            if wx.TheClipboard.Open():
                try:
                    wx.TheClipboard.SetData(dane)
                    wx.TheClipboard.Flush()
                    wx.MessageBox(
                        t("rezyser.prompt_arch_skopiowano_tresc"),
                        t("rezyser.prompt_arch_skopiowano_tytul"),
                        wx.OK | wx.ICON_INFORMATION,
                        dlg,
                    )
                finally:
                    wx.TheClipboard.Close()
            else:
                wx.MessageBox(
                    t("rezyser.prompt_arch_schowek_nieudany"),
                    t("common.komunikat_schowek_nieudany_tytul"),
                    wx.OK | wx.ICON_WARNING,
                    dlg,
                )

        dlg.Bind(wx.EVT_BUTTON, _kopiuj, btn_kopiuj)
        btn_row.Add(btn_kopiuj, flag=wx.RIGHT, border=8)

        btn_close = wx.Button(dlg, wx.ID_CLOSE, label=t("common.btn_zamknij"))
        dlg.Bind(wx.EVT_BUTTON, lambda _e: dlg.EndModal(wx.ID_CLOSE), btn_close)
        dlg.SetEscapeId(wx.ID_CLOSE)
        btn_row.Add(btn_close)

        sizer.Add(btn_row, flag=wx.ALL | wx.ALIGN_RIGHT, border=12)

        dlg.SetSizer(sizer)
        txt_prompt.SetFocus()
        dlg.ShowModal()
        dlg.Destroy()

    # ------------------------------------------------------------------
    # Zapis Streszczenia
    # ------------------------------------------------------------------
    def _on_zapisz_pamiec(self, _event: wx.Event) -> None:
        nazwa = self._txt_file_name.GetValue().strip()
        if not nazwa:
            wx.MessageBox(
                t("rezyser.brak_nazwy_ksiega_tresc"),
                t("rezyser.brak_nazwy_ksiega_tytul"),
                wx.OK | wx.ICON_WARNING,
                self,
            )
            self._txt_file_name.SetFocus()
            return

        tresc = self._txt_pamiec.GetValue().strip()
        if not tresc:
            wx.MessageBox(
                t("rezyser.pamiec_pusta_tresc"),
                t("rezyser.pamiec_pusta_tytul"),
                wx.OK | wx.ICON_WARNING,
                self,
            )
            self._txt_pamiec.SetFocus()
            return

        # v18.14: sufiksy pamięci pochodzą z paczki języka TREŚCI.
        self._odswiez_kandydatow_pamieci()
        # Projekt jeszcze nie wczytany do panelu (reżyser wpisał samą nazwę) →
        # sufiks rozstrzygamy po dysku DLA TEJ nazwy, ZANIM przypiszemy
        # `nazwa_pliku`. Inaczej `zapisz_streszczenie` uznałby projekt za otwarty
        # i użył sufiksu rozstrzygniętego dla poprzedniej historii.
        sufiks_celu: str | None = None
        if self._projekt.nazwa_pliku != nazwa:
            sufiks_celu = self._projekt.rozstrzygnij_sufiks_pamieci(nazwa)
            self._projekt.nazwa_pliku = nazwa
        try:
            sciezka = self._projekt.zapisz_streszczenie(tresc, sufiks=sufiks_celu)
            # D2: zapis = nowy „czysty" punkt odniesienia detektora zmian.
            self._pamiec_zapisana = self._txt_pamiec.GetValue()
            wx.MessageBox(
                # v18.14: nazwa pliku z DYSKU, nie z szablonu — sufiks jest
                # lokalizowany i mógł zostać rozstrzygnięty na inny kandydat.
                t("rezyser.streszczenie_zapisane_tresc",
                  plik=os.path.basename(sciezka)),
                t("rezyser.streszczenie_zapisane_tytul"),
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
        except Exception as exc:  # noqa: BLE001
            wx.MessageBox(
                t("rezyser.blad_zapisu_streszczenia", tresc_bledu=str(exc)),
                t("common.blad_zapisu_tytul"),
                wx.OK | wx.ICON_ERROR,
                self,
            )

    # ------------------------------------------------------------------
    # Wysyłanie do AI
    # ------------------------------------------------------------------
    def _on_wyslij(self, _event: wx.Event) -> None:
        # Guard „druga wysyłka w trakcie pierwszej" (v18.9). Stan przycisku to
        # za mało: klawiatura/NVDA potrafią dostarczyć zdarzenie zanim
        # `_refresh_ui_state` przeliczy Enable, a każdy równoległy worker
        # dopisywałby do tego samego pliku narracji. Cicho ignorujemy —
        # generacja już trwa, pasek postępu jest widoczny.
        if self._worker_thread and self._worker_thread.is_alive():
            return

        if not self._api_dostepne:
            wx.MessageBox(
                t("rezyser.brak_api_tresc"),
                t("rezyser.brak_api_tytul"),
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return

        user_text = self._txt_user_input.GetValue().strip()
        if not user_text:
            wx.MessageBox(
                t("rezyser.puste_pole_tresc"),
                t("rezyser.puste_pole_tytul"),
                wx.OK | wx.ICON_WARNING,
                self,
            )
            self._txt_user_input.SetFocus()
            return

        nazwa       = self._txt_file_name.GetValue().strip()
        przepis     = self._aktualny_przepis()
        if przepis is None:
            wx.MessageBox(
                t("rezyser.brak_przepisow_tresc"),
                t("rezyser.brak_przepisow_tytul"),
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return
        # Shortcut Burzy: tag produkcyjny w Instrukcji przy zaznaczonej Burzy
        # = gracz kliknął opcję Burzy (lub wkleił szkic) i zapomniał przełączyć
        # RadioBox na tryb zapisu. Zamiast odpalać Burzę na jej własnym owocu,
        # przeskakujemy na utrwalony tryb projektu. Wyzwalaczem jest wyłącznie
        # ``[CEL SCENY]`` — literał hardkodowany w :meth:`_on_kliknieto_opcje_burzy`,
        # niezależny od języka UI ([DYREKTYWA] z doklejki jest lokalizowana,
        # więc nie nadaje się na sygnaturę).
        if przepis.id == "burza" and "[cel sceny]" in user_text.lower():
            idx_zapisany = next(
                (i for i, p in enumerate(self._przepisy)
                 if p.id == self._zapisany_tryb),
                None,
            ) if self._zapisany_tryb else None
            if idx_zapisany is not None:
                self._rb_mode.SetSelection(idx_zapisany)
                self._refresh_ui_state()
                przepis = self._aktualny_przepis()
                if przepis is None:
                    wx.MessageBox(
                        t("rezyser.brak_przepisow_tresc"),
                        t("rezyser.brak_przepisow_tytul"),
                        wx.OK | wx.ICON_ERROR,
                        self,
                    )
                    return
            else:
                # Projekt nie ma jeszcze utrwalonej decyzji trybu twórczego —
                # wybór należy do gracza. Instrukcji NIE czyścimy (czyszczenie
                # następuje dopiero przy faktycznej wysyłce), więc szkic
                # przeżywa komunikat i czeka na ponowne Wyślij.
                wx.MessageBox(
                    t("rezyser.burza_shortcut_brak_trybu_tresc"),
                    t("rezyser.burza_shortcut_brak_trybu_tytul"),
                    wx.OK | wx.ICON_WARNING,
                    self,
                )
                self._rb_mode.SetFocus()
                return

        tryb_zapisu = przepis.zapis_do_pliku

        if tryb_zapisu and not nazwa:
            wx.MessageBox(
                t("rezyser.brak_nazwy_wyslanie_tresc", tytul_trybu=przepis.etykieta),
                t("rezyser.brak_nazwy_ksiega_tytul"),
                wx.OK | wx.ICON_WARNING,
                self,
            )
            self._txt_file_name.SetFocus()
            return

        world_context = self._txt_ksiega_swiata.GetValue().strip()
        if not world_context:
            wx.MessageBox(
                t("rezyser.brak_ksiegi_tresc"),
                t("rezyser.brak_ksiegi_tytul"),
                wx.OK | wx.ICON_WARNING,
                self,
            )
            self._txt_ksiega_swiata.SetFocus()
            return

        slowa_streszczenia = przepis.slowa_wyzwalajace.get("streszczenie", [])
        if tryb_zapisu and any(s in user_text.lower() for s in slowa_streszczenia):
            wx.MessageBox(
                t("rezyser.blad_trybu_tresc"),
                t("rezyser.blad_trybu_tytul"),
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return

        self._projekt.world_lore = world_context
        if nazwa and self._projekt.nazwa_pliku != nazwa:
            self._projekt.nazwa_pliku = nazwa

        # v15.2: wysyłka w trybie produkcyjnym „zużywa" opcje z poprzedniej
        # Burzy — gracz zdecydował co pisać i zawartość Burzy stała się
        # nieaktualna. Kasujemy brainstorm + ukrywamy panel jeszcze przed
        # wątkiem tła, żeby ekran natychmiast pokazał świeży stan.
        if tryb_zapisu:
            self._projekt.usun_brainstorm()
            self._ukryj_panel_opcji_burzy()

        self._btn_wyslij.Disable()
        self._txt_user_input.SetValue("")
        self._refresh_ui_state()

        snapshot = self._projekt.snapshot()

        t_thread = threading.Thread(
            target=self._wyslij_worker,
            args=(przepis, snapshot, user_text, nazwa, tryb_zapisu),
            daemon=True,
        )
        self._worker_thread = t_thread
        t_thread.start()


    # ------------------------------------------------------------------
    # Pomocnicza metoda zapisu do pliku projektu
    # ------------------------------------------------------------------
    def _dopisz_do_pliku(self, nazwa: str, content: str, mode: str = "a") -> None:
        if self._projekt.nazwa_pliku != nazwa:
            self._projekt.nazwa_pliku = nazwa
        try:
            self._projekt.dopisz_do_pliku_historii(content, mode=mode)
        except Exception as exc:  # noqa: BLE001
            wx.MessageBox(
                t("rezyser.blad_zapisu_do_pliku", tresc_bledu=str(exc)),
                t("common.blad_zapisu_tytul"),
                wx.OK | wx.ICON_ERROR,
                self,
            )

    # ------------------------------------------------------------------
    # Wyświetlanie błędów AI
    # ------------------------------------------------------------------
    def _komunikat_bledu_ai(self, exc: Exception) -> str:
        """Mapuje wyjątek workera na treść dla użytkownika.

        Typowane błędy generacji AI (struktura/długość) niosą `klucz_i18n` —
        zwracamy komunikat lokalizowany w namespace `rezyser`, żeby user nigdy
        nie zobaczył surowej, angielskiej treści technicznej. Ta treść NIE
        ginie — `zapisz_diagnostyke` dopisuje ją do error_log.txt PRZED
        zwróceniem komunikatu, żeby dało się zdiagnozować powtarzające się
        halucynacje struktury. Reszta wyjątków → `str(exc)`.
        """
        if isinstance(exc, BladGeneracjiAI):
            bledy_ai.zapisz_diagnostyke(exc, "rezyser")
            return t(f"rezyser.{exc.klucz_i18n}")
        if isinstance(exc, cl.BladTimeoutLLM):
            return t("rezyser.err_timeout")
        # v18.13: przepełnione okno kontekstowe modelu — komunikat mówi, CO
        # zrobić (streszczenie / mniejszy zakres / model z większym oknem),
        # zamiast pokazywać surową angielską treść z SDK.
        if isinstance(exc, cl.BladKontekstuLLM):
            return t("rezyser.err_kontekst")
        return str(exc)

    def _wyswietl_blad_ai(self, tresc_bledu: str, custom_msg: str | None = None) -> None:
        """Krótki błąd → MessageBox; długi → dialog z polem do skopiowania."""
        msg_header  = custom_msg or t("rezyser.blad_ai_naglowek")
        jest_krotki = len(tresc_bledu) <= 200 and "\n" not in tresc_bledu

        if jest_krotki:
            pelna_tresc = f"{msg_header}\n\n{tresc_bledu}" if custom_msg else tresc_bledu
            wx.MessageBox(pelna_tresc, t("rezyser.blad_ai_tytul"),
                          wx.OK | wx.ICON_ERROR, self)
        else:
            dlg = wx.Dialog(self, title=t("rezyser.blad_ai_szczegoly_tytul"), size=(640, 400))
            sizer = wx.BoxSizer(wx.VERTICAL)
            lbl_head = wx.StaticText(dlg, label=msg_header)
            lbl_copy = wx.StaticText(dlg, label=t("rezyser.blad_ai_lbl_tresc"))
            txt = wx.TextCtrl(
                dlg,
                value=tresc_bledu,
                style=wx.TE_MULTILINE | wx.TE_READONLY,
                name=t("rezyser.blad_ai_tresc_name"),
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

    # ------------------------------------------------------------------
    # Aktualizacja wskaźnika przepełnienia okna kontekstowego AI
    # ------------------------------------------------------------------
    _KOLORY_POZIOMOW = {
        cr.POZIOM_CZYSTA:     (0, 128, 0),
        cr.POZIOM_OK:         (0, 128, 0),
        cr.POZIOM_OSTRZEZENIE:(180, 100, 0),
        cr.POZIOM_ALARM:      (180, 0, 0),
    }

    def _aktualizuj_pamiec_modelu(self) -> None:
        status = self._projekt.status_pamieci_modelu()
        r, g, b = self._KOLORY_POZIOMOW.get(status.poziom, (0, 0, 0))
        self._gauge_kontekst.SetValue(status.procent)
        # v18.10: brak tabel BPE (offline + pusty cache) → pomiar zdegradowany
        # do heurystyki znakowej w core_tokeny; user musi wiedzieć, że wartości
        # są przybliżone i że przyczyną jest brak Internetu.
        if not ct.tokenizer_dostepny():
            self._lbl_kontekst_status.SetValue(
                t("rezyser.pamiec_status_offline",
                  tokeny=status.tokeny, maks=cr.OKNO_KONTEKSTU_MAX)
            )
            self._lbl_kontekst_status.SetForegroundColour(wx.Colour(180, 100, 0))
            return
        # v17.9: komunikat składamy z i18n po `poziom` (silnik zwraca już tylko
        # dane) — koniec hard-kodowanego polskiego przeciekającego do GUI.
        klucz = {
            cr.POZIOM_CZYSTA:      "rezyser.pamiec_status_czysta",
            cr.POZIOM_OK:          "rezyser.pamiec_status_ok",
            cr.POZIOM_OSTRZEZENIE: "rezyser.pamiec_status_ostrzezenie",
            cr.POZIOM_ALARM:       "rezyser.pamiec_status_alarm",
        }.get(status.poziom, "rezyser.pamiec_status_ok")
        self._lbl_kontekst_status.SetValue(
            t(klucz, tokeny=status.tokeny, maks=cr.OKNO_KONTEKSTU_MAX)
        )
        self._lbl_kontekst_status.SetForegroundColour(wx.Colour(r, g, b))


    # ------------------------------------------------------------------
    # Wątek tła – główna logika AI
    # ------------------------------------------------------------------
    @staticmethod
    def _wyglada_na_surowy_json(tekst: str) -> bool:
        """``True``, gdy odpowiedź tekstowa wygląda na nierozparsowany obiekt JSON.

        Bezpiecznik dispatchu `format_wyjscia`: tryb produkcyjny z
        `format_wyjscia: tekst`, którego prompt każe modelowi zwracać JSON
        (typowo: ktoś zduplikował Skrypt i tylko zmienił `id`), zwróciłby
        `{"tury": [...]}` na ścieżce tekstowej — a ta dopisałaby surowy JSON
        wprost do pliku projektu `.txt`. Wykrywamy KOMPLETNY obiekt JSON
        (proza praktycznie nigdy nie parsuje się jako dict) i blokujemy zapis.
        """
        fragment = (tekst or "").strip()
        if not fragment.startswith("{"):
            return False
        try:
            return isinstance(json.loads(fragment), dict)
        except (ValueError, TypeError):
            return False

    def _wyslij_worker(
        self,
        przepis: pr.PrzepisRezysera,
        snapshot: cr.SnapshotProjektu,
        user_text: str,
        nazwa: str,
        tryb_zapisu: bool,
    ) -> None:
        # Dispatch na podstawie `przepis.format_wyjscia` (zastąpił dawne
        # `if przepis.id == "burza"/"skrypt"` — patrz przepisy_rezysera.py).
        # Dzięki temu nowy tryb JSON powstaje przez samą duplikację YAML
        # (pole jedzie razem z plikiem), bez dopisywania warunku w kodzie.
        # Burza idzie ścieżką JSON-mode (`generuj_burze` → :class:`WynikBurzy`),
        # Skrypt ścieżką JSON-mode (`generuj_skrypt` → WynikSkryptu), reszta
        # zostaje na ścieżce tekstowej (`generuj_fragment` → WynikGeneracji).
        if przepis.format_wyjscia == "burza_json":
            try:
                wynik_b = rai.generuj_burze(
                    klient=self._klient_llm,
                    przepis=przepis,
                    snapshot=snapshot,
                    user_text=user_text,
                )
            except cl.BladLimituLLM:
                wx.CallAfter(self._on_wyslij_error, t("rezyser.err_rate_limit"))
                return
            except cl.BladTimeoutLLM:
                wx.CallAfter(self._on_wyslij_error, t("rezyser.err_timeout"))
                return
            except Exception as exc:  # noqa: BLE001
                wx.CallAfter(self._on_wyslij_error, self._komunikat_bledu_ai(exc))
                return

            if wynik_b.odrzucone:
                wx.CallAfter(self._on_wyslij_error, t("rezyser.err_odrzucenie"))
                return

            if wynik_b.streszczenie:
                wx.CallAfter(
                    self._on_wyslij_zapisz_streszczenie, wynik_b.streszczenie,
                )

            wx.CallAfter(self._on_wyslij_done_burza_json, wynik_b)
            return

        # v16.1: Skrypt idzie ścieżką JSON-mode (`generuj_skrypt` → WynikSkryptu):
        # LLM zwraca {"tury":[{mowca,tekst}]}, Python renderuje do [Mówca] treść
        # (+ akcenty) i dopisuje do pliku jak każdy tryb zapisu. Audiobook /
        # postprodukcja zostają na starej ścieżce tekstowej (`generuj_fragment`).
        if przepis.format_wyjscia == "skrypt_json":
            try:
                wynik_s = rai.generuj_skrypt(
                    klient=self._klient_llm,
                    przepis=przepis,
                    snapshot=snapshot,
                    user_text=user_text,
                )
            except cl.BladLimituLLM:
                wx.CallAfter(self._on_wyslij_error, t("rezyser.err_rate_limit"))
                return
            except cl.BladTimeoutLLM:
                wx.CallAfter(self._on_wyslij_error, t("rezyser.err_timeout"))
                return
            except Exception as exc:  # noqa: BLE001
                wx.CallAfter(self._on_wyslij_error, self._komunikat_bledu_ai(exc))
                return

            if wynik_s.odrzucone:
                wx.CallAfter(self._on_wyslij_error, t("rezyser.err_odrzucenie"))
                return

            wx.CallAfter(self._on_wyslij_done_zapis, wynik_s.tekst_odpowiedzi, nazwa)
            return

        # --- Tryby produkcyjne (Audiobook / postprodukcja) ---
        try:
            wynik = rai.generuj_fragment(
                klient=self._klient_llm,
                przepis=przepis,
                snapshot=snapshot,
                user_text=user_text,
            )
        except cl.BladLimituLLM:
            wx.CallAfter(
                self._on_wyslij_error,
                t("rezyser.err_rate_limit"),
            )
            return
        except cl.BladTimeoutLLM:
            wx.CallAfter(
                self._on_wyslij_error,
                t("rezyser.err_timeout"),
            )
            return
        except Exception as exc:  # noqa: BLE001
            wx.CallAfter(self._on_wyslij_error, self._komunikat_bledu_ai(exc))
            return

        if wynik.odrzucone:
            wx.CallAfter(
                self._on_wyslij_error,
                t("rezyser.err_odrzucenie"),
            )
            return

        if wynik.nowe_streszczenie:
            wx.CallAfter(
                self._on_wyslij_zapisz_streszczenie, wynik.nowe_streszczenie,
            )

        if tryb_zapisu:
            # Bezpiecznik: tryb tekstowy (`format_wyjscia: tekst`), którego prompt
            # został tak zaprojektowany (np. przez duplikację Skryptu), że model
            # zwrócił surowy JSON, NIE może po cichu dopisać tego JSON-a do pliku
            # — most ElevenLabs/NVDA dostałby śmieci zamiast prozy. Lepiej jawnie
            # ostrzec, że tryb wymaga skonfigurowania `format_wyjscia` (+ kodu).
            if self._wyglada_na_surowy_json(wynik.tekst_odpowiedzi):
                wx.CallAfter(self._on_wyslij_error, t("rezyser.err_surowy_json"))
                return
            wx.CallAfter(
                self._on_wyslij_done_zapis,
                wynik.tekst_odpowiedzi, nazwa, wynik.ostrzezenie,
            )
        else:
            wx.CallAfter(self._on_wyslij_done_burza, wynik.tekst_odpowiedzi)


    # ------------------------------------------------------------------
    # Callbacki _wyslij_worker
    # ------------------------------------------------------------------
    def _on_wyslij_error(self, msg: str) -> None:
        self._zwolnij_workera()
        self._btn_wyslij.Enable()
        self._refresh_ui_state()
        self._wyswietl_blad_ai(msg)

    def _zwolnij_workera(self) -> None:
        """Zwalnia referencję wątku tła — wołane na WEJŚCIU callbacku końcowego.

        v18.13: callbacki generacji (w odróżnieniu od postprodukcyjnych) tego nie
        robiły, więc przez chwilę po zakończeniu pracy `self._worker_thread` wciąż
        wskazywał dogasający wątek. Guardy `is_alive()` widziały wtedy „zajęte":
        `Enable` kontrolek zależał od wyścigu, a auto-zapis Pamięci Długotrwałej
        (`_spawn_auto_pamiec`, wołany właśnie z takiego callbacku) bywał CICHO
        pomijany — niedeterministycznie, bo `wx.CallAfter` tylko kolejkuje
        wywołanie i wątek zwykle, ale nie zawsze, zdąży się zakończyć wcześniej.
        """
        self._worker_thread = None

    def _on_wyslij_zapisz_streszczenie(self, streszczenie: str) -> None:
        self.summary_text = streszczenie
        self._txt_pamiec.SetValue(streszczenie)

    def _on_wyslij_done_zapis(
        self, response_text: str, nazwa: str, ostrzezenie: str = "",
    ) -> None:
        self._zwolnij_workera()
        if self.full_story:
            self.full_story += "\n\n" + response_text
        else:
            self.full_story = response_text
        self._txt_full_story.SetValue(self.full_story)
        self._dopisz_do_pliku(nazwa, response_text + "\n\n")
        self.last_response = response_text
        # Pierwsza udana wysyłka produkcyjna utrwala tryb zapisu. Dotychczas
        # `.mode` powstawał tylko przez kliknięcie Akt/Scena/Rozdział, więc
        # gracze wysyłający tekst bez wstawiania struktury (typowe dla
        # wersji finalnych pod ElevenLabs) nie mieli żadnej blokady przed
        # przypadkowym przeskokiem między Skryptem a Audiobookiem.
        self._zapisz_tryb_projektu()
        self._btn_wyslij.Enable()
        self._refresh_ui_state()
        wx.Bell()
        self._txt_full_story.SetFocus()
        # Miękkie ostrzeżenie (sprawa #1): odpowiedź urwała się na limicie
        # długości i nie dała się domknąć mikro-callem. Fragment JEST już
        # zapisany — informujemy tylko, by reżyser sprawdził końcówkę.
        if ostrzezenie:
            wx.MessageBox(
                ostrzezenie,
                t("rezyser.ostrzezenie_urwane_tytul"),
                wx.OK | wx.ICON_WARNING,
            )
        # v18.13: pamięć modelu na poziomie ALARM → sam zapisz Pamięć Długotrwałą
        # (cichy no-op, gdy warunki niespełnione — patrz `_spawn_auto_pamiec`).
        self._spawn_auto_pamiec()

    def _on_wyslij_done_burza(self, response_text: str) -> None:
        # v15.2: ścieżka legacy — fallback dla hipotetycznych przepisów
        # spoza id="burza" z `zapis_do_pliku=false`. Burza w v15.2+ idzie
        # przez :meth:`_on_wyslij_done_burza_json`. Zachowane na wypadek
        # gdyby lingwista dodał własny przepis planowy bez JSON-schemy.
        self._zwolnij_workera()
        self.last_response = response_text
        self._btn_wyslij.Enable()
        self._refresh_ui_state()
        self._show_response_dialog(response_text)

    def _on_wyslij_done_burza_json(self, wynik: rai.WynikBurzy) -> None:
        """v15.2: callback po sukcesie Burzy w trybie JSON.

        Buduje przyciski opcji w panelu, persystuje wynik do
        `runtime/skrypty/<nazwa>.brainstorm.json` żeby przeżył reload.
        """
        self._zwolnij_workera()
        # Dataclass → list[dict] dla persystencji + przekazania do GUI.
        # `dataclasses.asdict` nie jest tutaj idealne (nie wszystkie pola
        # opcji mają iść do persystencji), więc ręczne mapowanie 3 pól.
        opcje_dict = [
            {"tytul": o.tytul, "opis": o.opis, "cel_sceny": o.cel_sceny}
            for o in wynik.opcje
        ]

        # v18.23: opcja z samymi białymi znakami PRZECHODZI walidację schematu
        # (`minLength: 1` liczy znaki przed `strip()`), a `_przeladuj_opcje_burzy`
        # pomija ją jako halucynację. Gdy takie są WSZYSTKIE, panel zostawał
        # pusty, `wx.Bell()` sygnalizował sukces i NVDA nie miał czego przeczytać
        # — reżyser nie wiedział, czy coś się stało. Traktujemy to jak błąd
        # struktury (klucz istnieje w 9 paczkach) i nie budujemy panelu.
        if not any(
            (o["tytul"] or "").strip() and (o["cel_sceny"] or "").strip()
            for o in opcje_dict
        ):
            self._wyswietl_blad_ai(t("rezyser.err_struktura"))
            self._btn_wyslij.Enable()
            self._refresh_ui_state()
            return

        # Persystencja — tylko gdy mamy nazwę projektu. Burza bez nazwy
        # (gracz nie wpisał) nie jest blokowana, po prostu nie zapisujemy.
        if self._projekt.nazwa_pliku:
            try:
                self._projekt.zapisz_brainstorm(opcje_dict, wynik.streszczenie)
            except OSError as exc:
                # Niekrytyczne — opcje są w GUI, brak pliku oznacza tylko
                # że nie przeżyją reload. Logujemy w last_response żeby
                # nie zatracić wyniku przy debug.
                self._wyswietl_blad_ai(
                    t("rezyser.blad_zapisu_do_pliku", tresc_bledu=str(exc)),
                )

        # Logujemy surowy JSON w last_response — pomocne w debug.
        self.last_response = wynik.surowy_json

        # Rebuild przycisków — pokazuje panel, ukryty od inicjalizacji.
        self._przeladuj_opcje_burzy(opcje_dict, wynik.streszczenie)

        self._btn_wyslij.Enable()
        self._refresh_ui_state()
        wx.Bell()  # A11y: NVDA „ping" sygnał gotowości
        # Focus na pierwszy przycisk opcji, jeśli istnieje — NVDA przeczyta
        # tytuł najsilniejszej propozycji jako pierwszą reakcję na sukces.
        if self._pnl_opcji_burzy.GetChildren():
            for child in self._pnl_opcji_burzy.GetChildren():
                if isinstance(child, wx.Button):
                    child.SetFocus()
                    break

    def _show_response_dialog(self, tekst: str) -> None:
        dlg = wx.Dialog(
            self,
            title=t("rezyser.burza_dlg_tytul"),
            size=(720, 520),
        )
        sizer = wx.BoxSizer(wx.VERTICAL)
        lbl = wx.StaticText(dlg, label=t("rezyser.burza_dlg_lbl"))
        txt = wx.TextCtrl(
            dlg,
            value=tekst,
            style=wx.TE_MULTILINE | wx.TE_READONLY,
            name=t("rezyser.burza_dlg_name"),
        )
        btn_ok = wx.Button(dlg, wx.ID_OK, label=t("common.btn_zamknij"))
        sizer.Add(lbl,    flag=wx.ALL,                                   border=8)
        sizer.Add(txt,    proportion=1, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=8)
        sizer.Add(btn_ok, flag=wx.ALL | wx.ALIGN_RIGHT,                  border=8)
        dlg.SetSizer(sizer)
        txt.SetFocus()
        dlg.ShowModal()
        dlg.Destroy()

    # ------------------------------------------------------------------
    # Helper: wspólna walidacja nazwy projektu
    # ------------------------------------------------------------------
    def _wymagaj_nazwy_lub_alert(self) -> str | None:
        nazwa = self._txt_file_name.GetValue().strip()
        if not nazwa:
            wx.MessageBox(
                t("rezyser.struktura_brak_nazwy_tresc"),
                t("rezyser.struktura_brak_nazwy_tytul"),
                wx.OK | wx.ICON_WARNING,
                self,
            )
            self._txt_file_name.SetFocus()
            return None
        if self._projekt.nazwa_pliku != nazwa:
            self._projekt.nazwa_pliku = nazwa
        return nazwa

    def _po_wstawieniu_struktury(self, tytul: str, komunikat: str) -> None:
        self._txt_full_story.SetValue(self.full_story)
        self._zapisz_tryb_projektu()
        self._refresh_ui_state()
        wx.MessageBox(komunikat, tytul, wx.OK | wx.ICON_INFORMATION, self)

    # ------------------------------------------------------------------
    # Wstawianie Prologu
    # ------------------------------------------------------------------
    def _on_wstaw_prolog(self, _event: wx.Event) -> None:
        if self._wymagaj_nazwy_lub_alert() is None:
            return
        kod = self._kod_jezyka_aktywny()
        try:
            self._projekt.wstaw_prolog(
                naglowek=t("rezyser.naglowek_prolog", jezyk_override=kod))
        except Exception as exc:  # noqa: BLE001
            wx.MessageBox(
                t("rezyser.blad_wstawiania_prolog", tresc_bledu=str(exc)),
                t("common.blad_zapisu_tytul"),
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return
        self._po_wstawieniu_struktury(
            t("rezyser.prolog_tytul"),
            t("rezyser.prolog_tresc"),
        )

    # ------------------------------------------------------------------
    # Wstawianie Epilogu
    # ------------------------------------------------------------------
    def _on_wstaw_epilog(self, _event: wx.Event) -> None:
        if self._wymagaj_nazwy_lub_alert() is None:
            return
        kod = self._kod_jezyka_aktywny()
        try:
            self._projekt.wstaw_epilog(
                naglowek=t("rezyser.naglowek_epilog", jezyk_override=kod))
        except Exception as exc:  # noqa: BLE001
            wx.MessageBox(
                t("rezyser.blad_wstawiania_epilog", tresc_bledu=str(exc)),
                t("common.blad_zapisu_tytul"),
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return
        self._po_wstawieniu_struktury(
            t("rezyser.epilog_tytul"),
            t("rezyser.epilog_tresc"),
        )

    # ------------------------------------------------------------------
    # Wstawianie cięcia Rozdziału (Audiobook)
    # ------------------------------------------------------------------
    def _on_wstaw_rozdzial(self, _event: wx.Event) -> None:
        if self._wymagaj_nazwy_lub_alert() is None:
            return
        kod = self._kod_jezyka_aktywny()
        try:
            naglowek = self._projekt.wstaw_rozdzial(
                naglowek_bazowy=t("rezyser.naglowek_rozdzial", jezyk_override=kod),
            )
        except Exception as exc:  # noqa: BLE001
            wx.MessageBox(
                t("rezyser.blad_wstawiania_rozdzialu", tresc_bledu=str(exc)),
                t("common.blad_zapisu_tytul"),
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return
        self._po_wstawieniu_struktury(
            t("rezyser.rozdzial_tytul"),
            t("rezyser.rozdzial_tresc", naglowek=naglowek),
        )

    # ------------------------------------------------------------------
    # Wstawianie Aktu (Skrypt)
    # ------------------------------------------------------------------
    def _on_wstaw_akt(self, _event: wx.Event) -> None:
        if self._wymagaj_nazwy_lub_alert() is None:
            return
        kod = self._kod_jezyka_aktywny()
        try:
            akt_nag, scena_nag = self._projekt.wstaw_akt(
                naglowek_akt=t("rezyser.naglowek_akt", jezyk_override=kod),
                naglowek_scena=t("rezyser.naglowek_scena", jezyk_override=kod),
            )
        except Exception as exc:  # noqa: BLE001
            wx.MessageBox(
                t("rezyser.blad_wstawiania_aktu", tresc_bledu=str(exc)),
                t("common.blad_zapisu_tytul"),
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return
        self._po_wstawieniu_struktury(
            t("rezyser.akt_tytul"),
            t("rezyser.akt_tresc", akt_naglowek=akt_nag, scena_naglowek=scena_nag),
        )

    # ------------------------------------------------------------------
    # Wstawianie Sceny (Skrypt)
    # ------------------------------------------------------------------
    def _on_wstaw_scena(self, _event: wx.Event) -> None:
        if self._wymagaj_nazwy_lub_alert() is None:
            return
        kod = self._kod_jezyka_aktywny()
        try:
            scena_nag = self._projekt.wstaw_scena(
                naglowek_bazowy=t("rezyser.naglowek_scena", jezyk_override=kod),
            )
        except Exception as exc:  # noqa: BLE001
            wx.MessageBox(
                t("rezyser.blad_wstawiania_sceny", tresc_bledu=str(exc)),
                t("common.blad_zapisu_tytul"),
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return
        self._po_wstawieniu_struktury(
            t("rezyser.scena_tytul"),
            t("rezyser.scena_tresc", naglowek=scena_nag),
        )


    # ------------------------------------------------------------------
    # Postprodukcja – Nadaj Tytuły Rozdziałom
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # Most ElevenLabs (v16.0): obsada głosowa
    # ------------------------------------------------------------------
    def _on_el_obsada(self, _event: wx.Event) -> None:
        """Otwiera okienko obsady głosowej ElevenLabs i zapisuje szkic.

        Źródło postaci = plik ``skrypty/<nazwa>.txt`` z dysku (postprodukcja
        zakończonej sztuki, nie bieżąca pamięć). Narrator zawsze obecny
        (głos domyślny — tytuły rozdziałów + narracja). Pre-fill z istniejącego
        szkicu; zapis → ``runtime/skrypty/<nazwa>.obsada.json`` (może być
        niekompletny — komplet waliduje dopiero dispatcher).
        """
        nazwa = self._txt_file_name.GetValue().strip()
        if not nazwa:
            wx.MessageBox(
                t("rezyser.el_brak_nazwy_tresc"),
                t("rezyser.el_brak_nazwy_tytul"),
                wx.OK | wx.ICON_WARNING, self,
            )
            return

        app_dir = sciezki.KATALOG_BAZOWY_STR
        filepath = os.path.join(app_dir, self.SKRYPTY_DIR, f"{nazwa}.txt")
        if not os.path.exists(filepath):
            wx.MessageBox(
                t("rezyser.plik_narracji_brak_tresc", nazwa_projektu=nazwa),
                t("rezyser.plik_narracji_brak_tytul"),
                wx.OK | wx.ICON_ERROR, self,
            )
            return
        try:
            with open(filepath, "r", encoding="utf-8") as fh:
                tekst = fh.read()
        except Exception as exc:
            wx.MessageBox(
                t("rezyser.blad_odczytu_tresc", tresc_bledu=str(exc)),
                t("common.blad_odczytu_tytul"),
                wx.OK | wx.ICON_ERROR, self,
            )
            return

        postacie, czy_narrator = ce.wykryj_postacie(tekst)
        if not postacie and not czy_narrator:
            wx.MessageBox(
                t("rezyser.el_brak_postaci_tresc"),
                t("rezyser.el_brak_postaci_tytul"),
                wx.OK | wx.ICON_WARNING, self,
            )
            return

        prefill = self._projekt.wczytaj_obsada(nazwa)
        dlg = DialogObsady(self, postacie, prefill)
        try:
            if dlg.ShowModal() == wx.ID_OK:
                try:
                    # zapisz_obsada loguje ścieżkę runtime na konsolę dewelopera;
                    # userowi pokazujemy tylko czystą nazwę projektu (runtime ukryty).
                    self._projekt.zapisz_obsada(dlg.glosy, nazwa=nazwa)
                except Exception as exc:
                    wx.MessageBox(
                        str(exc),
                        t("rezyser.el_obsada_blad_tytul"),
                        wx.OK | wx.ICON_ERROR, self,
                    )
                    return
                wx.MessageBox(
                    t("rezyser.el_obsada_zapisana_tresc", nazwa=nazwa),
                    t("rezyser.el_obsada_zapisana_tytul"),
                    wx.OK | wx.ICON_INFORMATION, self,
                )
        finally:
            dlg.Destroy()

    # ------------------------------------------------------------------
    # Most ElevenLabs (v16.0): dispatcher — budowa projektu Studio
    # ------------------------------------------------------------------
    def _on_el_build(self, _event: wx.Event) -> None:
        """Buduje wielogłosowy projekt ElevenLabs Studio z gotowego skryptu.

        Walidacja: ≥1 rozdział (Prolog/Akt/…) + komplet obsady (narrator i każda
        postać z kwestiami mają voice_id w szkicu z dysku). Budowa projektu idzie
        w wątku tła (``create_project``, 0 kredytów — render robi user w webie).
        """
        nazwa = self._txt_file_name.GetValue().strip()
        if not nazwa:
            wx.MessageBox(
                t("rezyser.el_brak_nazwy_tresc"),
                t("rezyser.el_brak_nazwy_tytul"),
                wx.OK | wx.ICON_WARNING, self,
            )
            return

        if self._worker_thread and self._worker_thread.is_alive():
            wx.MessageBox(
                t("rezyser.tytuly_zajety_tresc"),
                t("rezyser.tytuly_zajety_tytul"),
                wx.OK | wx.ICON_INFORMATION, self,
            )
            return

        app_dir = sciezki.KATALOG_BAZOWY_STR
        filepath = os.path.join(app_dir, self.SKRYPTY_DIR, f"{nazwa}.txt")
        if not os.path.exists(filepath):
            wx.MessageBox(
                t("rezyser.plik_narracji_brak_tresc", nazwa_projektu=nazwa),
                t("rezyser.plik_narracji_brak_tytul"),
                wx.OK | wx.ICON_ERROR, self,
            )
            return
        try:
            with open(filepath, "r", encoding="utf-8") as fh:
                tekst = fh.read()
        except Exception as exc:
            wx.MessageBox(
                t("rezyser.blad_odczytu_tresc", tresc_bledu=str(exc)),
                t("common.blad_odczytu_tytul"),
                wx.OK | wx.ICON_ERROR, self,
            )
            return

        # Walidacja struktury: ≥1 rozdział („dramatów modernistycznych" bez
        # żadnego Prologu/Aktu/Rozdziału nie przyjmujemy — Studio potrzebuje chapterów).
        if ce.liczba_rozdzialow(tekst) < 1:
            wx.MessageBox(
                t("rezyser.el_brak_rozdzialu_tresc"),
                t("rezyser.el_brak_rozdzialu_tytul"),
                wx.OK | wx.ICON_WARNING, self,
            )
            return

        # Walidacja kompletności obsady (szkic z dysku).
        postacie, _czy_narrator = ce.wykryj_postacie(tekst)
        obsada = self._projekt.wczytaj_obsada(nazwa)
        if not obsada:
            wx.MessageBox(
                t("rezyser.el_obsada_brak_tresc"),
                t("rezyser.el_obsada_brak_tytul"),
                wx.OK | wx.ICON_WARNING, self,
            )
            return

        wymagane = [ce.NARRATOR_KEY] + [p.lower().strip() for p in postacie]
        brakujace = [k for k in wymagane if not obsada.get(k)]
        if brakujace:
            czytelne = []
            for k in brakujace:
                if k == ce.NARRATOR_KEY:
                    czytelne.append(t("rezyser.dlg_obsada_narrator_label").rstrip(": "))
                else:
                    czytelne.append(
                        next((p for p in postacie if p.lower().strip() == k), k)
                    )
            wx.MessageBox(
                t("rezyser.el_obsada_niekompletna_tresc", brakujace=", ".join(czytelne)),
                t("rezyser.el_obsada_niekompletna_tytul"),
                wx.OK | wx.ICON_WARNING, self,
            )
            return

        # Strażnik formatu mostu (v17.2 — rozszerzenie Zasady Montażysty): linie
        # bez znacznika mówcy i niebędące nagłówkiem są w buduj_chapters po cichu
        # pomijane, więc projekt Studio może rozjechać się z plikiem. Ostrzegamy
        # i oddajemy decyzję reżyserowi (Reżyser rządzi — twarde limity tylko
        # przeciw samowoli modelu, nie reżysera).
        sieroty = ce.wykryj_sieroty(tekst)
        if sieroty and not self._potwierdz_sieroty(sieroty):
            return

        # Komplet — buduj w wątku tła.
        self._btn_el_build.Disable()
        self._btn_el_obsada.Disable()
        self._lbl_el_status.SetLabel(t("rezyser.el_build_status"))
        self._lbl_el_status.SetName(t("rezyser.el_build_status"))
        self._lbl_el_status.Show()
        self._pnl_el.Layout()
        self.Layout()

        # Język projektu (kod ISO treści, NIE język UI) — rozwiązujemy na wątku
        # głównym i przekazujemy do workera (czystość wątkowa: nie czytamy stanu
        # przepisu z tła). Reżyser z polskim UI tworzący np. fiński audiobook musi
        # dostać `fi`, nie `pl` — patrz `_kod_jezyka_aktywny` (przepis.kod_jezyka).
        kod_jezyka = self._kod_jezyka_aktywny()

        th = threading.Thread(
            target=self._el_build_worker,
            args=(nazwa, tekst, obsada, kod_jezyka),
            daemon=True,
        )
        self._worker_thread = th
        th.start()

    def _el_build_worker(
        self, nazwa: str, tekst: str, obsada: dict, kod_jezyka: str,
    ) -> None:
        """Wątek tła: buduje from_content_json i tworzy projekt Studio."""
        try:
            chapters = ce.buduj_chapters(tekst, obsada)
            # v16.1: język projektu = kod ISO 639-1 TREŚCI dla Studio. Naprawia
            # nagłówki (v3 bez języka bywa na nich niespójny). Od v18.4: kod treści
            # przepisu (`_kod_jezyka_aktywny`), NIE język UI — projekt może być w
            # innym języku niż interfejs (polski UI + fiński audiobook).
            project_id = ce.create_project(
                self._el_klucz, nazwa, obsada[ce.NARRATOR_KEY], chapters,
                language=kod_jezyka,
            )
        except ce.BrakUprawnien as exc:
            wx.CallAfter(self._on_el_build_error, "uprawnienia", str(exc))
            return
        except ce.BladElevenLabs as exc:
            wx.CallAfter(self._on_el_build_error, "ogolny", str(exc))
            return
        except Exception as exc:  # noqa: BLE001 — sieć/parsowanie; pokaż userowi
            wx.CallAfter(self._on_el_build_error, "ogolny", str(exc))
            return
        wx.CallAfter(self._on_el_build_done, project_id, nazwa)

    def _on_sr_generate(self, _event: wx.Event) -> None:
        """Generuje ``skrypty/<nazwa>_screen_reader.html`` z bieżącego skryptu.

        Tryb Skrypt, niezależny od ElevenLabs. Akcenty z Księgi Świata przez
        psucie ortografii + ``<span lang>``; audio-tagi v3 usuwane. Czysty tekst
        → generacja synchroniczna (bez wątku tła).
        """
        nazwa = self._txt_file_name.GetValue().strip()
        if not nazwa:
            wx.MessageBox(
                t("rezyser.el_brak_nazwy_tresc"), t("rezyser.el_brak_nazwy_tytul"),
                wx.OK | wx.ICON_WARNING, self,
            )
            return

        app_dir = sciezki.KATALOG_BAZOWY_STR
        sciezka_txt = os.path.join(app_dir, self.SKRYPTY_DIR, f"{nazwa}.txt")
        if not os.path.exists(sciezka_txt):
            wx.MessageBox(
                t("rezyser.plik_narracji_brak_tresc", nazwa_projektu=nazwa),
                t("rezyser.plik_narracji_brak_tytul"), wx.OK | wx.ICON_ERROR, self,
            )
            return
        try:
            with open(sciezka_txt, "r", encoding="utf-8") as fh:
                tekst = fh.read()
        except Exception as exc:  # noqa: BLE001
            wx.MessageBox(
                t("rezyser.blad_odczytu_tresc", tresc_bledu=str(exc)),
                t("common.blad_odczytu_tytul"), wx.OK | wx.ICON_ERROR, self,
            )
            return

        # Księga Świata (.md) — opcjonalna; bez niej HTML powstaje bez akcentów.
        lore = ""
        sciezka_md = os.path.join(app_dir, self.SKRYPTY_DIR, f"{nazwa}.md")
        if os.path.exists(sciezka_md):
            try:
                with open(sciezka_md, "r", encoding="utf-8") as fh:
                    lore = fh.read()
            except Exception:  # noqa: BLE001 — Księga opcjonalna, błąd nie blokuje
                lore = ""

        try:
            # v17.9 (Obszar 3a): wersja dla czytników w JĘZYKU TREŚCI przepisu
            # (akcenty + atrybut lang HTML), nie w języku GUI.
            html = csr.generuj_html(
                tekst, lore, jezyk_projektu=self._kod_jezyka_aktywny(), tytul=nazwa,
            )
            sciezka_out = os.path.join(
                app_dir, self.SKRYPTY_DIR, f"{nazwa}_screen_reader.html"
            )
            with open(sciezka_out, "w", encoding="utf-8") as fh:
                fh.write(html)
        except Exception as exc:  # noqa: BLE001
            wx.MessageBox(
                t("rezyser.sr_blad_tresc", tresc_bledu=str(exc)),
                t("rezyser.sr_blad_tytul"), wx.OK | wx.ICON_ERROR, self,
            )
            return

        wx.MessageBox(
            t("rezyser.sr_sukces_tresc", nazwa_pliku=nazwa),
            t("rezyser.sr_sukces_tytul"), wx.OK | wx.ICON_INFORMATION, self,
        )

    def _reset_el_busy(self) -> None:
        self._btn_el_build.Enable()
        self._btn_el_obsada.Enable()
        self._lbl_el_status.Hide()
        self._pnl_el.Layout()
        self.Layout()

    def _on_el_build_error(self, rodzaj: str, msg: str) -> None:
        self._reset_el_busy()
        if rodzaj == "uprawnienia":
            tresc = t("rezyser.el_build_blad_uprawnienia_tresc")
        else:
            tresc = t("rezyser.el_build_blad_tresc", tresc_bledu=msg)
        wx.MessageBox(tresc, t("rezyser.el_build_blad_tytul"), wx.OK | wx.ICON_ERROR, self)

    def _on_el_build_done(self, project_id: str, nazwa: str) -> None:
        self._reset_el_busy()
        self._show_el_report(project_id, nazwa)

    def _show_el_report(self, project_id: str, nazwa: str) -> None:
        """Raport read-only: ID projektu + link do Studio + instrukcja renderu."""
        tresc = t("rezyser.el_raport_tresc", nazwa=nazwa, project_id=project_id)
        dlg = wx.Dialog(
            self,
            title=t("rezyser.el_raport_tytul"),
            size=(620, 460),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        txt = wx.TextCtrl(
            dlg, value=tresc,
            style=wx.TE_MULTILINE | wx.TE_READONLY,
            name=t("rezyser.el_raport_tytul"),
        )
        btn_studio = wx.Button(dlg, label=t("rezyser.el_btn_otworz_studio"))
        btn_close = wx.Button(dlg, wx.ID_OK, label=t("rezyser.el_raport_btn_zamknij"))
        btn_close.SetDefault()

        def _otworz_studio(_e: wx.Event) -> None:
            import webbrowser  # noqa: PLC0415
            webbrowser.open(ce.STUDIO_URL)

        btn_studio.Bind(wx.EVT_BUTTON, _otworz_studio)

        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(btn_studio, flag=wx.RIGHT, border=8)
        row.AddStretchSpacer()
        row.Add(btn_close)

        s = wx.BoxSizer(wx.VERTICAL)
        s.Add(txt, proportion=1, flag=wx.EXPAND | wx.ALL, border=10)
        s.Add(row, flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, border=10)
        dlg.SetSizer(s)
        wx.CallAfter(txt.SetFocus)
        try:
            dlg.ShowModal()
        finally:
            dlg.Destroy()

    #: Ile linii-sierot wypisać w dialogu, zanim dołożymy notkę „… i N więcej"
    #: (NVDA nie powinno czytać tysięcy linii, gdy reżyser wczytał całą prozę).
    MAX_SIEROTY_POKAZ = 50

    def _potwierdz_sieroty(self, sieroty: list) -> bool:
        """Ostrzega o liniach-sierotach mostu i pyta, czy budować mimo to.

        ``sieroty`` to lista ``(numer_linii, tekst)`` z ``ce.wykryj_sieroty``.
        Dialog wyboru (read-only lista + „Buduj mimo to" / „Anuluj i popraw"):
        zwraca True, gdy reżyser świadomie akceptuje pominięcie tych linii.
        Domyślny przycisk to bezpieczne „Anuluj" — Enter nie buduje przez pomyłkę.
        """
        pokazane = sieroty[: self.MAX_SIEROTY_POKAZ]
        linie = [
            t("rezyser.el_sieroty_pozycja", nr=nr, tekst=tekst)
            for nr, tekst in pokazane
        ]
        if len(sieroty) > len(pokazane):
            linie.append(
                t("rezyser.el_sieroty_wiecej", liczba=len(sieroty) - len(pokazane))
            )
        tresc = (
            t("rezyser.el_sieroty_naglowek", liczba=len(sieroty))
            + "\n\n" + "\n".join(linie)
            + "\n\n" + t("rezyser.el_sieroty_stopka")
        )

        dlg = wx.Dialog(
            self,
            title=t("rezyser.el_sieroty_tytul"),
            size=(640, 480),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        txt = wx.TextCtrl(
            dlg, value=tresc,
            style=wx.TE_MULTILINE | wx.TE_READONLY,
            name=t("rezyser.el_sieroty_tytul"),
        )
        btn_buduj = wx.Button(
            dlg, wx.ID_OK, label=t("rezyser.el_sieroty_btn_buduj")
        )
        btn_anuluj = wx.Button(
            dlg, wx.ID_CANCEL, label=t("rezyser.el_sieroty_btn_anuluj")
        )
        btn_anuluj.SetDefault()  # bezpieczny domyślny — Enter anuluje, nie buduje

        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(btn_buduj, flag=wx.RIGHT, border=8)
        row.AddStretchSpacer()
        row.Add(btn_anuluj)

        s = wx.BoxSizer(wx.VERTICAL)
        s.Add(txt, proportion=1, flag=wx.EXPAND | wx.ALL, border=10)
        s.Add(row, flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, border=10)
        dlg.SetSizer(s)
        wx.CallAfter(txt.SetFocus)
        try:
            return dlg.ShowModal() == wx.ID_OK
        finally:
            dlg.Destroy()

    def _on_postprodukcja(self, id_postprod: str) -> None:
        """Wspólny handler przycisków postprodukcji (v18.12, dispatch po `zakres`).

        Wszystkie kosztowne pytania (brak nazwy/pliku, zgoda na nadpisanie
        pliku wyniku) zadawane są PRZED startem workera — user nie płaci za
        call, którego wynik miałby odrzucić przy zapisie.
        """
        przepis_pp = next(
            (p for p in self._postprodukcje if p.id == id_postprod), None,
        )
        if przepis_pp is None:
            return

        nazwa = self._txt_file_name.GetValue().strip()
        if not nazwa:
            wx.MessageBox(
                t("rezyser.tytuly_brak_nazwy_tresc"),
                t("rezyser.tytuly_brak_nazwy_tytul"),
                wx.OK | wx.ICON_WARNING,
                self,
            )
            return

        if self._worker_thread and self._worker_thread.is_alive():
            wx.MessageBox(
                t("rezyser.tytuly_zajety_tresc"),
                t("rezyser.tytuly_zajety_tytul"),
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            return

        app_dir  = sciezki.KATALOG_BAZOWY_STR
        filepath = os.path.join(app_dir, self.SKRYPTY_DIR, f"{nazwa}.txt")
        if not os.path.exists(filepath):
            wx.MessageBox(
                t("rezyser.tytuly_brak_pliku_tresc", sciezka_pliku=filepath),
                t("rezyser.tytuly_brak_pliku_tytul"),
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return

        try:
            with open(filepath, "r", encoding="utf-8") as fh:
                pelny_tekst = fh.read()
        except Exception as exc:
            wx.MessageBox(
                t("rezyser.blad_odczytu_tresc", tresc_bledu=str(exc)),
                t("common.blad_odczytu_tytul"),
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return

        # Plik wyniku (`sufiks_pliku_wyniku` z YAML): zgoda na nadpisanie
        # PRZED wywołaniem API.
        sciezka_wyj = self._sciezka_wyniku_postprod(przepis_pp, nazwa)
        if sciezka_wyj and os.path.exists(sciezka_wyj):
            odp = wx.MessageBox(
                t("rezyser.postprod_nadpisac_tresc",
                  plik=os.path.basename(sciezka_wyj)),
                t("rezyser.postprod_nadpisac_tytul"),
                wx.YES_NO | wx.ICON_QUESTION,
                self,
            )
            if odp != wx.YES:
                return

        zadanie = self._zbuduj_zadanie_postprod(przepis_pp, nazwa, pelny_tekst)

        # Pre-check okna kontekstowego (v18.13): narzędzia operujące na całym
        # projekcie potrafią przerosnąć okno modelu. Liczymy tokeny lokalnie —
        # tym samym pomiarem, co wskaźnik pamięci — i pytamy PRZED opłaceniem
        # calla. To ostrzeżenie, nie blokada: filar jakości (Claude) ma okno
        # znacznie większe niż nasz licznik, więc twarde „nie" byłoby fałszywe.
        # Decyzję zostawiamy reżyserowi, bo tylko on wie, jakim modelem jedzie.
        if not self._potwierdz_rozmiar_kontekstu(zadanie):
            return

        self._start_postprodukcje(zadanie)

    # ------------------------------------------------------------------
    # Przygotowanie zadania postprodukcji (wspólne dla ręcznego i auto)
    # ------------------------------------------------------------------
    def _sciezka_wyniku_postprod(
        self, przepis_pp: pr.PrzepisRezysera, nazwa: str,
    ) -> str | None:
        """Ścieżka pliku wyniku wg ``sufiks_pliku_wyniku`` (``None`` = brak pliku)."""
        if not przepis_pp.sufiks_pliku_wyniku:
            return None
        return os.path.join(
            sciezki.KATALOG_BAZOWY_STR, self.SKRYPTY_DIR,
            f"{nazwa}{przepis_pp.sufiks_pliku_wyniku}.txt",
        )

    def _zbuduj_zadanie_postprod(
        self,
        przepis_pp: pr.PrzepisRezysera,
        nazwa: str,
        pelny_tekst: str,
        auto: bool = False,
    ) -> ZadaniePostprodukcji:
        """Składa :class:`ZadaniePostprodukcji` — w tym wejście dla `rekoncyliacja`."""
        app_dir = sciezki.KATALOG_BAZOWY_STR

        # Księga Świata (`skrypty/<nazwa>.md`) — opcjonalny kontekst dla zakresów
        # całościowych; jej brak/nieczytelność nie blokuje narzędzia (silnik
        # dokleja blok tylko gdy przepis ma `prompt_ksiegi_szablon`).
        ksiega: str | None = None
        if przepis_pp.zakres != pr.ZAKRES_PER_ROZDZIAL:
            sciezka_md = os.path.join(app_dir, self.SKRYPTY_DIR, f"{nazwa}.md")
            if os.path.exists(sciezka_md):
                try:
                    with open(sciezka_md, "r", encoding="utf-8") as fh:
                        ksiega = fh.read()
                except Exception:
                    ksiega = None

        # `rekoncyliacja` (v18.13): zamiast całego pliku wysyłamy dotychczasową
        # Pamięć Długotrwałą + narrację od jej anchora. Kolejne streszczenie jest
        # dzięki temu przyrostowe, a payload nie rośnie liniowo z projektem.
        if przepis_pp.zakres == pr.ZAKRES_REKONCYLIACJA:
            # v18.14: dla projektu OTWARTEGO w panelu scalamy dokładnie ten plik
            # pamięci, który rozstrzygnęło wczytanie (być może ręcznym wyborem
            # reżysera spośród kilku). Dla projektu wskazanego samą nazwą sufiks
            # rozstrzyga się po dysku — dla NIEJ, nie dla stanu panelu.
            self._odswiez_kandydatow_pamieci()
            sufiks_zrodla = (
                self._projekt.sufiks_streszczenia
                if nazwa == self._projekt.nazwa_pliku else None
            )
            stare, fragment, _naglowek = self._projekt.wejscie_pamieci_dlugotrwalej(
                pelny_tekst, nazwa, sufiks_zrodla,
            )
            tresc_modelu = rai.zloz_wejscie_rekoncyliacji(przepis_pp, stare, fragment)
        else:
            tresc_modelu = pelny_tekst

        return ZadaniePostprodukcji(
            przepis=przepis_pp,
            nazwa=nazwa,
            tresc_modelu=tresc_modelu,
            pelny_tekst=pelny_tekst,
            ksiega=ksiega,
            sciezka_wyj=self._sciezka_wyniku_postprod(przepis_pp, nazwa),
            auto=auto,
        )

    def _potwierdz_rozmiar_kontekstu(self, zadanie: ZadaniePostprodukcji) -> bool:
        """Ostrzega, gdy payload przekracza okno licznika (128k). ``False`` = anuluj.

        Pomijane dla ``per_rozdzial`` (tam do modelu idą krótkie próbki rozdziałów)
        oraz dla uruchomień automatycznych (bez GUI-owego pytania — automat i tak
        nie ma komu zadać pytania, a rekoncyliacja z definicji tnie kontekst).
        """
        if zadanie.auto or zadanie.przepis.zakres == pr.ZAKRES_PER_ROZDZIAL:
            return True
        tokeny = ct.policz_tokeny_chat(
            [zadanie.tresc_modelu, zadanie.ksiega or "",
             zadanie.przepis.prompt_systemowy],
            ct.MODEL_DOMYSLNY_REZYSER,
        )
        if tokeny <= ct.OKNO_KONTEKSTU_MAX:
            return True
        odp = wx.MessageBox(
            t("rezyser.postprod_kontekst_tresc",
              tokeny=tokeny, limit=ct.OKNO_KONTEKSTU_MAX),
            t("rezyser.postprod_kontekst_tytul"),
            wx.YES_NO | wx.ICON_WARNING,
            self,
        )
        return odp == wx.YES

    def _start_postprodukcje(self, zadanie: ZadaniePostprodukcji) -> None:
        """Blokuje panel, pokazuje postęp i startuje wątek właściwy dla zakresu."""
        for btn in self._btn_postprod.values():
            btn.Disable()
        self._gauge_postprod.SetValue(0)
        self._gauge_postprod.Show()
        self._lbl_postprod_status.SetLabel(t("rezyser.tytuly_prep"))
        self._lbl_postprod_status.Show()
        self._pnl_postprodukcja.Layout()
        self.Layout()

        target = (
            self._tytuly_worker
            if zadanie.przepis.zakres == pr.ZAKRES_PER_ROZDZIAL
            else self._postprod_calosc_worker
        )
        t_thread = threading.Thread(target=target, args=(zadanie,), daemon=True)
        self._worker_thread = t_thread
        t_thread.start()
        # Refresh PO starcie workera (audyt 18.12, NISKA-3): przelicza Enable
        # kontrolek zależnych od `worker_w_toku` (np. „Przeładuj z dysku"),
        # które inaczej zostałyby aktywne do najbliższego przypadkowego
        # refreshu. Nadpisuje też ręczny Disable przycisków postprodukcji
        # spójnym warunkiem (`worker_zajety` jest już True).
        self._refresh_ui_state()

    # ------------------------------------------------------------------
    # Wątek tła – postprodukcja per rozdział (np. tytuły)
    # ------------------------------------------------------------------
    def _tytuly_worker(self, zadanie: ZadaniePostprodukcji) -> None:
        przepis_pp = zadanie.przepis

        def _cb(msg: str, percent: int) -> None:
            wx.CallAfter(self._update_postprod_progress, msg, percent)

        # Siatka bezpieczeństwa wątku (v18.9): `nadaj_tytuly_rozdzialom` zwraca
        # błędy przez `wynik.przerwano_bledem`, ale potrafi RZUCIĆ zanim tam
        # dojdzie — np. `re.split` na `regex_podzial_rozdzialow` z YAML-a
        # (edytowalnego w Managerze Reguł): zepsuty wzorzec = `re.error`.
        # Bez tego wątek ginął cicho, a przyciski postprodukcji zostawały
        # wyłączone do restartu aplikacji.
        try:
            wynik = rai.nadaj_tytuly_rozdzialom(
                klient=self._klient_llm,
                przepis_tytuly=przepis_pp,
                pelny_tekst=zadanie.tresc_modelu,
                on_postep=_cb,
            )
        except Exception as exc:  # noqa: BLE001 — wątek nie może umrzeć po cichu
            bledy_ai.zapisz_diagnostyke(exc, "rezyser._tytuly_worker")
            # v18.10 (audyt): przez centralny maper — timeout i typowane błędy
            # generacji dostają komunikat i18n zamiast surowego str(exc).
            wx.CallAfter(self._on_postprod_error, self._komunikat_bledu_ai(exc))
            return

        if wynik.przerwano_bledem:
            wx.CallAfter(
                self._on_postprod_error,
                wynik.blad or t("rezyser.tytuly_blad_nieznany"),
                list(wynik.tytuly),
                przepis_pp,
            )
            return

        tekst = "\n".join(wynik.tytuly)
        self._domknij_postprodukcje(zadanie, tekst, "")

    # ------------------------------------------------------------------
    # Wątek tła – postprodukcja całościowa (v18.12, `zakres: calosc`)
    # ------------------------------------------------------------------
    def _postprod_calosc_worker(self, zadanie: ZadaniePostprodukcji) -> None:
        przepis_pp = zadanie.przepis

        def _cb(msg: str, percent: int) -> None:
            wx.CallAfter(self._update_postprod_progress, msg, percent)

        # Siatka bezpieczeństwa wątku (v18.9): silnik zwraca rate-limit/timeout
        # typowanym wynikiem, ale pozostałe wyjątki SDK celowo PROPAGUJE —
        # bez try wątek ginąłby cicho w paczce --windowed.
        try:
            wynik = rai.wykonaj_postprodukcje_calosc(
                klient=self._klient_llm,
                przepis=przepis_pp,
                pelny_tekst=zadanie.tresc_modelu,
                ksiega=zadanie.ksiega,
                on_postep=_cb,
            )
        except Exception as exc:  # noqa: BLE001 — wątek nie może umrzeć po cichu
            bledy_ai.zapisz_diagnostyke(exc, "rezyser._postprod_calosc_worker")
            wx.CallAfter(self._on_postprod_error, self._komunikat_bledu_ai(exc))
            return

        if wynik.przerwano_bledem:
            wx.CallAfter(
                self._on_postprod_error,
                wynik.blad or t("rezyser.tytuly_blad_nieznany"),
            )
            return

        if wynik.odrzucone:
            wx.CallAfter(self._on_postprod_error, t("rezyser.err_odrzucenie"))
            return

        self._domknij_postprodukcje(zadanie, wynik.tekst, wynik.ostrzezenie)

    # ------------------------------------------------------------------
    # Domknięcie postprodukcji (wątek tła → GUI)
    # ------------------------------------------------------------------
    def _domknij_postprodukcje(
        self, zadanie: ZadaniePostprodukcji, tekst: str, ostrzezenie: str,
    ) -> None:
        """Zapisuje wynik i oddaje sterowanie GUI. Wołane Z WĄTKU TŁA.

        Trzy ścieżki:
          * **rola ``pamiec_dlugotrwala``** (v18.13) — wynik JEST Pamięcią
            Długotrwałą projektu, więc zapis idzie przez
            ``ProjektRezysera.zapisz_streszczenie`` (plik + meta-anchor + stan
            w RAM). Robi to wątek GUI, bo operacja mutuje model i pola panelu —
            wątek tła nie ma prawa ich dotykać.
          * **zwykły plik wyniku** — zapis tutaj (I/O poza wątkiem GUI); porażka
            zapisu NIE gubi opłaconego wyniku, tylko pokazuje go w dialogu
            (audyt 18.12, ŚREDNIA-1).
          * **bez pliku** — sam dialog wyniku.
        """
        # Ostatnia instrukcja workera biegnie POZA jego try/except, więc dostaje
        # własną siatkę (lekcja v18.9): wyjątek tutaj ubiłby wątek po cichu,
        # zostawiając panel postprodukcji zablokowany aż do restartu aplikacji.
        try:
            if zadanie.przepis.rola == pr.ROLA_PAMIEC_DLUGOTRWALA:
                wx.CallAfter(self._on_postprod_pamiec, zadanie, tekst, ostrzezenie)
                return
            if zadanie.sciezka_wyj and not self._zapisz_wynik_postprod(
                    zadanie.sciezka_wyj, tekst):
                wx.CallAfter(self._show_postprod_dialog, zadanie.przepis, tekst, None)
                return
            wx.CallAfter(
                self._on_postprod_sukces,
                zadanie.przepis, tekst, zadanie.sciezka_wyj, ostrzezenie,
            )
        except Exception as exc:  # noqa: BLE001 — wątek nie może umrzeć po cichu
            bledy_ai.zapisz_diagnostyke(exc, "rezyser._domknij_postprodukcje")
            wx.CallAfter(self._on_postprod_error, self._komunikat_bledu_ai(exc))

    def _zapisz_wynik_postprod(self, sciezka: str, tekst: str) -> bool:
        """Zapis pliku wyniku (wątek tła). Błąd → callback błędu + ``False``.

        Wynik modelu jest już opłacony, więc porażka zapisu NIE może zginąć
        po cichu — user dostaje pełny komunikat i może ponowić narzędzie.
        """
        try:
            with open(sciezka, "w", encoding="utf-8") as fh:
                fh.write(tekst + "\n")
            return True
        except Exception as exc:  # noqa: BLE001 — dysk/uprawnienia to realne wejście
            bledy_ai.zapisz_diagnostyke(exc, "rezyser._zapisz_wynik_postprod")
            wx.CallAfter(
                self._on_postprod_error,
                t("rezyser.blad_zapisu_do_pliku", tresc_bledu=str(exc)),
            )
            return False

    # ------------------------------------------------------------------
    # Callbacki workerów postprodukcji
    # ------------------------------------------------------------------
    def _update_postprod_progress(self, msg: str, percent: int) -> None:
        self._lbl_postprod_status.SetLabel(msg)
        self._gauge_postprod.SetValue(max(0, min(100, percent)))

    def _on_postprod_error(
        self,
        msg: str,
        partial_wyniki: list | None = None,
        przepis_pp: pr.PrzepisRezysera | None = None,
    ) -> None:
        # Worker skończył (callback to jego ostatnia instrukcja) — zwalniamy
        # referencję PRZED refreshem, żeby Enable nie zależał od wyścigu
        # z dogasającym wątkiem.
        self._worker_thread = None
        self._gauge_postprod.SetValue(0)
        self._gauge_postprod.Hide()
        self._lbl_postprod_status.Hide()
        # Pełny refresh zamiast bezwarunkowego Enable() (audyt 18.12,
        # NISKA-2): stan przycisków wraca do prawdy (nazwa/historia/API),
        # a refresh robi też Layout panelu i całości.
        self._refresh_ui_state()
        self._wyswietl_blad_ai(
            msg,
            t("rezyser.tytuly_blad_naglowek"),
        )
        if partial_wyniki:
            self._show_postprod_dialog(
                przepis_pp,
                t(
                    "rezyser.tytuly_czesciowe_naglowek",
                    wyniki="\n".join(partial_wyniki),
                ),
                sciezka_wyj=None,
            )

    def _on_postprod_sukces(
        self,
        przepis_pp: pr.PrzepisRezysera,
        tekst: str,
        sciezka_wyj: str | None,
        ostrzezenie: str = "",
    ) -> None:
        # Jak w `_on_postprod_error`: zwolnij referencję workera i przelicz
        # stan przycisków pełnym refreshem (audyt 18.12, NISKA-2).
        self._worker_thread = None
        self._gauge_postprod.SetValue(100)
        self._lbl_postprod_status.SetLabel(t("rezyser.postprod_postep_gotowe"))
        self._refresh_ui_state()

        # Ostrzeżenie o ucięciu PRZED dialogiem wyniku — user wie, czego
        # szukać na końcówce (konwencja miękka jak w `generuj_fragment`).
        if ostrzezenie:
            wx.MessageBox(
                ostrzezenie,
                t("rezyser.postprod_ostrzezenie_tytul"),
                wx.OK | wx.ICON_WARNING,
                self,
            )
        self._show_postprod_dialog(przepis_pp, tekst, sciezka_wyj)

    def _on_postprod_pamiec(
        self,
        zadanie: ZadaniePostprodukcji,
        tekst: str,
        ostrzezenie: str = "",
    ) -> None:
        """Zapis wyniku o roli ``pamiec_dlugotrwala`` (v18.13). Wątek GUI.

        Idzie przez ``zapisz_streszczenie``, a nie przez zwykły zapis pliku, bo
        Pamięć Długotrwała to TRÓJKA: plik ``<nazwa><sufiks>.txt``, meta-anchor
        rekoncyliacji i stan w RAM. Zapisanie samego pliku zostawiłoby anchor
        wskazujący poprzednie streszczenie — kolejna rekoncyliacja wciągnęłaby
        ponownie materiał już skompresowany.
        """
        self._worker_thread = None
        self._gauge_postprod.SetValue(100)
        self._lbl_postprod_status.SetLabel(t("rezyser.postprod_postep_gotowe"))

        try:
            # v18.14: nazwą pliku rządzi sufiks PRZEPISU, który user kliknął —
            # paczka może mieć kilka narzędzi pamięci (osobna „pod siebie",
            # osobna „pod AI"), a każde ma prawo pisać do swojego pliku.
            sciezka = self._projekt.zapisz_streszczenie(
                tekst, nazwa=zadanie.nazwa, content=zadanie.pelny_tekst,
                sufiks=zadanie.przepis.sufiks_pliku_wyniku,
            )
        except (OSError, ValueError) as exc:
            bledy_ai.zapisz_diagnostyke(exc, "rezyser._on_postprod_pamiec")
            # Opłacony wynik nie ginie z porażką zapisu (wzorzec ŚREDNIA-1
            # z audytu 18.12) — pokazujemy go do ręcznego skopiowania.
            self._on_postprod_error(
                t("rezyser.blad_zapisu_streszczenia", tresc_bledu=str(exc)))
            self._show_postprod_dialog(zadanie.przepis, tekst, None)
            return

        # Panel synchronizujemy TYLKO gdy streszczenie dotyczy otwartego projektu
        # (postprodukcja może działać na projekcie wskazanym samą nazwą).
        if zadanie.nazwa == self._projekt.nazwa_pliku:
            self._txt_pamiec.SetValue(tekst)
            # D2: świeży zapis = nowy „czysty" punkt odniesienia detektora zmian.
            self._pamiec_zapisana = tekst
        self._refresh_ui_state()

        if ostrzezenie:
            wx.MessageBox(
                ostrzezenie,
                t("rezyser.postprod_ostrzezenie_tytul"),
                wx.OK | wx.ICON_WARNING,
                self,
            )

        if zadanie.auto:
            # Automat (próg alarmowy pamięci): bez dialogu z treścią — reżyser
            # nie prosił o ten wynik, więc nie zabieramy mu fokusu na długi
            # tekst. Sam komunikat, żeby wiedział, co aplikacja zrobiła.
            wx.MessageBox(
                t("rezyser.pamiec_auto_zapisana_tresc",
                  nazwa_projektu=zadanie.nazwa,
                  plik=os.path.basename(sciezka)),
                t("rezyser.pamiec_auto_zapisana_tytul"),
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            return
        self._show_postprod_dialog(zadanie.przepis, tekst, sciezka)

    # ------------------------------------------------------------------
    # Auto-streszczenie po przekroczeniu progu alarmowego (v18.13)
    # ------------------------------------------------------------------
    def _spawn_auto_pamiec(self) -> None:
        """Po udanej turze: przy poziomie ALARM sam zapisuje Pamięć Długotrwałą.

        Parytet z Opowieściami, gdzie auto-streszczenie działa od Fazy 4 — z tą
        różnicą, że tam progiem jest 70%, a tu 90%. Powód: w Reżyserze etykieta
        ostrzeżenia (70%) już dziś zapowiada, że streszczenie „niedługo będzie
        konieczne", więc automat przy 90% domyka obietnicę UI zamiast ją
        wyprzedzać, a pojedynczy call Reżysera jest droższy niż tura Opowieści.

        Cichy no-op, gdy: brak przepisu z rolą ``pamiec_dlugotrwala`` (user
        skasował YAML), brak API, trwa inny worker albo projekt nie ma jeszcze
        pliku na dysku. Auto-mechanizm nie ma prawa niczym rzucić ani niczego
        blokować — reżyser zawsze może kliknąć narzędzie ręcznie.
        """
        if self._projekt.status_pamieci_modelu().poziom != cr.POZIOM_ALARM:
            return
        if not self._api_dostepne or self._klient_llm is None:
            return
        if self._worker_thread and self._worker_thread.is_alive():
            return
        if self._auto_pamiec_wykonane:
            return
        przepis_pp = pr.przepis_pamieci_dlugotrwalej(self._postprodukcje)
        if przepis_pp is None:
            return

        nazwa = self._projekt.nazwa_pliku or self._txt_file_name.GetValue().strip()
        if not nazwa:
            return
        filepath = os.path.join(
            sciezki.KATALOG_BAZOWY_STR, self.SKRYPTY_DIR, f"{nazwa}.txt")
        try:
            with open(filepath, "r", encoding="utf-8") as fh:
                pelny_tekst = fh.read()
        except (OSError, ValueError):
            return

        zadanie = self._zbuduj_zadanie_postprod(
            przepis_pp, nazwa, pelny_tekst, auto=True)
        # Flagę stawiamy przy STARCIE, nie po sukcesie: nieudany call też nie
        # powinien ponawiać się automatycznie przy każdej następnej turze.
        self._auto_pamiec_wykonane = True
        self._start_postprodukcje(zadanie)
        # Komunikat PO starcie (A11y): reżyser słyszy, dlaczego panel się
        # zablokował, zanim zacznie szukać przyczyny.
        self._lbl_postprod_status.SetLabel(t("rezyser.pamiec_auto_start"))

    def _show_postprod_dialog(
        self,
        przepis_pp: pr.PrzepisRezysera | None,
        tekst: str,
        sciezka_wyj: str | None,
    ) -> None:
        """Dialog wyniku postprodukcji (TE_READONLY — długa treść, A11y).

        Tytuł okna = etykieta narzędzia z YAML (już zlokalizowana). Gdy wynik
        poszedł też do pliku, etykieta nad polem podaje jego nazwę.
        """
        tytul_dlg = przepis_pp.etykieta if przepis_pp else t("rezyser.postprod_heading")
        lbl_tekst = (
            t("rezyser.postprod_dlg_zapisano", plik=os.path.basename(sciezka_wyj))
            if sciezka_wyj else t("rezyser.postprod_dlg_lbl")
        )
        dlg = wx.Dialog(
            self,
            title=tytul_dlg,
            size=(620, 420),
        )
        sizer = wx.BoxSizer(wx.VERTICAL)
        lbl = wx.StaticText(dlg, label=lbl_tekst)
        txt = wx.TextCtrl(
            dlg,
            value=tekst,
            style=wx.TE_MULTILINE | wx.TE_READONLY,
            name=t("rezyser.postprod_dlg_name"),
        )
        btn_ok = wx.Button(dlg, wx.ID_OK, label=t("common.btn_zamknij"))
        sizer.Add(lbl,    flag=wx.ALL,                                   border=8)
        sizer.Add(txt,    proportion=1, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=8)
        sizer.Add(btn_ok, flag=wx.ALL | wx.ALIGN_RIGHT,                  border=8)
        dlg.SetSizer(sizer)
        txt.SetFocus()
        dlg.ShowModal()
        dlg.Destroy()

    # ------------------------------------------------------------------
    # Zapis trybu twórczego do pliku metadanych projektu
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # v15.2.3 — awaryjne otwarcie pliku narracji w edytorze tekstu
    # ------------------------------------------------------------------
    def _otworz_w_edytorze(self, sciezka: str) -> None:
        """Otwiera plik w domyślnym edytorze tekstu systemu.

        Deleguje do wspólnego :func:`sciezki.otworz_w_systemie` (cross-platform).
        Przy błędzie pokazujemy MessageBox ze ścieżką, żeby gracz mógł otworzyć
        plik manualnie z Eksploratora.
        """
        try:
            sciezki.otworz_w_systemie(sciezka)
        except Exception as exc:                                    # noqa: BLE001
            wx.MessageBox(
                t(
                    "rezyser.blad_otwarcia_tresc",
                    sciezka_pliku=sciezka,
                    tresc_bledu=str(exc),
                ),
                t("rezyser.blad_otwarcia_tytul"),
                wx.OK | wx.ICON_ERROR,
                self,
            )

    def _on_otworz_narracje(self, _event: wx.Event) -> None:
        """Otwiera `skrypty/<nazwa>.txt` w systemowym edytorze.

        Łata lukę pamięci streszczenia (patrz komentarz przy `_btn_otworz_narracje`
        w `_zbuduj_pasek_pliku`) — gracz po reload-zie projektu ze streszczeniem
        widzi tylko Księgę Świata + jednozdaniową notatkę w pamięci długotrwałej,
        a pełna narracja siedzi nadal na dysku. Przycisk otwiera plik w
        Notatniku/VS Code — gracz może skopiować ostatnie sceny do pola
        Pamięci albo dopisać własne domknięcie przed kolejną wysyłką do AI.
        """
        nazwa = self._txt_file_name.GetValue().strip()
        if not nazwa:
            wx.MessageBox(
                t("rezyser.brak_nazwy_tresc"),
                t("rezyser.brak_nazwy_tytul"),
                wx.OK | wx.ICON_WARNING,
                self,
            )
            self._txt_file_name.SetFocus()
            return
        sciezka = os.path.join(
            self._projekt.app_dir, cr.SKRYPTY_DIR, f"{nazwa}.txt"
        )
        if not os.path.exists(sciezka):
            wx.MessageBox(
                t("rezyser.plik_narracji_brak_tresc", nazwa_projektu=nazwa),
                t("rezyser.plik_narracji_brak_tytul"),
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            return
        self._otworz_w_edytorze(sciezka)

    # ------------------------------------------------------------------
    # v15.5/v17.6 — PEŁNE przeładowanie projektu z dysku (po ręcznej edycji .txt)
    # ------------------------------------------------------------------
    def _on_przeladuj_z_dysku(self, _event: wx.Event) -> None:
        """Przeładowuje CAŁY projekt z dysku przez wspólny tor `wczytaj`.

        Domyka cykl „Otwórz narrację → edytuj ręcznie → Przeładuj z dysku".
        Od v17.6 to faktyczny reload: przelicza liczniki struktury, podnosi
        Księgę Świata / tryb / Burzę i rekoncyliuje pamięć roboczą jednym torem
        (koniec desyncu liczników i meta streszczenia po ręcznej edycji `.txt`).
        Gdy historia za długa — pyta gracza o punkt odniesienia pamięci roboczej
        (`_dialog_wyboru_markera`). Ostrzega przed nadpisaniem niezapisanych
        edycji w polach Księga/Pamięć (D2).
        """
        # Guard `is_alive` NA WEJŚCIU (audyt 18.12, NISKA-3; checklist v18.9):
        # pełny reload mutuje full_story/liczniki/streszczenie — warunek Enable
        # (`worker_w_toku`) to za mało, bo refresh może nie nadążyć za startem
        # workera, a handler musi bronić się sam.
        if self._worker_thread and self._worker_thread.is_alive():
            wx.MessageBox(
                t("rezyser.tytuly_zajety_tresc"),
                t("rezyser.tytuly_zajety_tytul"),
                wx.OK | wx.ICON_INFORMATION, self,
            )
            return
        nazwa = self._txt_file_name.GetValue().strip()
        if not nazwa:
            wx.MessageBox(
                t("rezyser.brak_nazwy_tresc"),
                t("rezyser.brak_nazwy_tytul"),
                wx.OK | wx.ICON_WARNING, self,
            )
            self._txt_file_name.SetFocus()
            return
        sciezka = self._projekt._sciezka_historii(nazwa)
        if not os.path.exists(sciezka):
            wx.MessageBox(
                t("rezyser.plik_narracji_brak_tresc", nazwa_projektu=nazwa),
                t("rezyser.plik_narracji_brak_tytul"),
                wx.OK | wx.ICON_INFORMATION, self,
            )
            return

        # D2: pełny reload nadpisze pola wersją z dysku — ostrzeż TYLKO gdy w
        # polach Księga/Pamięć są NIEZAPISANE zmiany (treść różni się od „czystego"
        # snapshotu z ostatniego wczytania/zapisu). Do 18.3 warunek sprawdzał samo
        # „pole niepuste", więc ostrzeżenie wyskakiwało nawet bez żadnej edycji.
        if (self._txt_ksiega_swiata.GetValue() != self._ksiega_swiata_zapisana
                or self._txt_pamiec.GetValue() != self._pamiec_zapisana):
            odp = wx.MessageBox(
                t("rezyser.przeladuj_ostrzezenie_tresc"),
                t("rezyser.przeladuj_ostrzezenie_tytul"),
                wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING, self,
            )
            if odp != wx.YES:
                return

        self._odswiez_kandydatow_pamieci()
        try:
            wynik = self._projekt.wczytaj(
                nazwa,
                wybor_markera=self._dialog_wyboru_markera,
                wybor_pamieci=self._dialog_wyboru_pamieci,
            )
        except (FileNotFoundError, OSError, ValueError) as exc:
            self._wyswietl_blad_ai(
                t("rezyser.blad_odczytu_tresc", tresc_bledu=str(exc)),
            )
            return

        self._zasiej_gui_po_wczytaniu(wynik, nazwa)
        self._moze_ostrzec_o_odrzuconej_pamieci(wynik)

        rek = wynik.rekoncyliacja
        if rek is not None and rek.tryb == "calosc":
            if rek.skasowano_streszczenie:
                tresc = t("rezyser.przeladuj_calosc_skasowano_tresc",
                          liczba_znakow=rek.liczba_znakow)
            else:
                tresc = t("rezyser.przeladuj_calosc_tresc",
                          liczba_znakow=rek.liczba_znakow)
            wx.MessageBox(
                tresc, t("rezyser.przeladuj_tytul"),
                wx.OK | wx.ICON_INFORMATION, self,
            )
        else:
            # snap / fallback — pokaż punkt odniesienia pamięci roboczej.
            self._pokaz_punkt_odniesienia(rek)
        self._txt_full_story.SetFocus()

    def _zapisz_tryb_projektu(self) -> None:
        nazwa   = self._txt_file_name.GetValue().strip()
        przepis = self._aktualny_przepis()
        if not nazwa or przepis is None:
            return
        if self._projekt.nazwa_pliku != nazwa:
            self._projekt.nazwa_pliku = nazwa
        # `.mode` trzyma stabilne `id`; utrwalamy TYLKO tryby zapisu (Burza i
        # inne tryby bez `zapis_do_pliku` są ulotne — silnik je pomija).
        self._projekt.zapisz_tryb_tworczy(przepis.id, przepis.zapis_do_pliku)
        # Synchronizacja mirror'a w RAM — tylko gdy to tryb zapisu.
        if przepis.zapis_do_pliku:
            self._zapisany_tryb = przepis.id


class DialogObsady(wx.Dialog):
    """Okno obsady głosowej ElevenLabs — przypisanie voice_id do mówców (v16.0).

    Wzorzec A11y jak :class:`gui_opowiesci.DialogEdycjaStanuGry`: wx.Dialog,
    pola z czytelnymi etykietami (``SetName`` dla NVDA), ``wx.CallAfter`` fokus.
    NARRATOR jest zawsze pierwszym wierszem (głos domyślny — tytuły rozdziałów
    i narracja). Pozostałe wiersze to postacie Z KWESTIAMI (z ``wykryj_postacie``).

    To okno ZAPISUJE SZKIC — pola mogą zostać puste/niekompletne (reżyser może
    wrócić później). Komplet obsady waliduje dopiero dispatcher przed budową
    projektu. Po ``ShowModal() == wx.ID_OK`` atrybut :attr:`glosy` zawiera mapę
    ``{klucz: voice_id}`` (klucz postaci = nazwa małymi literami; narrator =
    ``core_elevenlabs.NARRATOR_KEY``).
    """

    def __init__(self, parent: wx.Window, postacie: list[str], prefill: dict[str, str]) -> None:
        super().__init__(
            parent,
            title=t("rezyser.dlg_obsada_tytul"),
            size=(640, 500),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )

        # Atrybut publiczny — wywołujący czyta po ID_OK.
        self.glosy: dict[str, str] = {}

        # Lista (klucz, kontrolka) w kolejności wyświetlania (narrator pierwszy).
        self._wiersze: list[tuple[str, wx.TextCtrl]] = []

        instrukcja = wx.StaticText(self, label=t("rezyser.dlg_obsada_instrukcja"))
        instrukcja.Wrap(600)

        # Siatka: etykieta | pole na voice_id.
        grid = wx.FlexGridSizer(cols=2, vgap=8, hgap=10)
        grid.AddGrowableCol(1, 1)

        def _dodaj_wiersz(klucz: str, etykieta: str) -> None:
            lbl = wx.StaticText(self, label=etykieta)
            txt = wx.TextCtrl(self, value=prefill.get(klucz, ""), name=etykieta)
            txt.SetHint(t("rezyser.dlg_obsada_hint"))
            grid.Add(lbl, flag=wx.ALIGN_CENTER_VERTICAL)
            grid.Add(txt, flag=wx.EXPAND)
            self._wiersze.append((klucz, txt))

        # Narrator zawsze pierwszy.
        _dodaj_wiersz(ce.NARRATOR_KEY, t("rezyser.dlg_obsada_narrator_label"))
        # Postacie z kwestiami — klucz = nazwa małymi literami (spójnie z parserem).
        for nazwa in postacie:
            _dodaj_wiersz(
                nazwa.lower().strip(),
                t("rezyser.dlg_obsada_postac_label", nazwa=nazwa),
            )

        btn_ok = wx.Button(self, wx.ID_OK, label=t("rezyser.dlg_obsada_btn_zapisz"))
        btn_anuluj = wx.Button(self, wx.ID_CANCEL, label=t("rezyser.dlg_obsada_btn_anuluj"))
        btn_ok.SetDefault()
        btn_ok.Bind(wx.EVT_BUTTON, self._on_zapisz)

        row_btn = wx.BoxSizer(wx.HORIZONTAL)
        row_btn.AddStretchSpacer()
        row_btn.Add(btn_anuluj, flag=wx.RIGHT, border=8)
        row_btn.Add(btn_ok)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(instrukcja, flag=wx.ALL, border=10)
        sizer.Add(grid, proportion=1, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=10)
        sizer.Add(row_btn, flag=wx.EXPAND | wx.ALL, border=10)
        self.SetSizer(sizer)

        if self._wiersze:
            wx.CallAfter(self._wiersze[0][1].SetFocus)

    def _on_zapisz(self, _event: wx.Event) -> None:
        """Zbiera wpisane voice_id do :attr:`glosy` i zamyka modal.

        Szkic — żadnego twardego wymogu kompletności. Puste pola trafiają do
        mapy jako pusty string; ``ProjektRezysera.zapisz_obsada`` je odfiltruje.
        """
        self.glosy = {
            klucz: txt.GetValue().strip()
            for klucz, txt in self._wiersze
        }
        self.EndModal(wx.ID_OK)
