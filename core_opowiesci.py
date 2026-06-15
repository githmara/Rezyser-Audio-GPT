"""
core_opowiesci.py — Stan + I/O dyskowe modułu „Interaktywne Opowieści" (v15.0 Faza 3).

Klasa :class:`ProjektOpowiesci` jest analogiem :class:`core_rezyser.ProjektRezysera` —
„właścicielem prawdy" o stanie aktualnie otwartej gry. GUI (``OpowiesciPanel``)
synchronizuje swoje kontrolki z atrybutami tej klasy przed I/O i odczytuje
stan z powrotem po każdej mutacji.

Ścieżki plików (5 ścieżek per gra ``<nazwa>``):
    * ``skrypty/<nazwa>.txt``                      — narracja, append-only,
                                                     BEZ meta-warningów (Cinematic
                                                     Warning z Fazy 4 jest cięty
                                                     przez :meth:`czysc_meta_warningi`)
    * ``opowiesci/<nazwa>.md``                     — (DEPRECATED, v17.4 / P6A)
                                                     dawna Księga Świata Opowieści.
                                                     Rebuild usunięty: miał być
                                                     mostem do Reżysera, którego
                                                     nigdy nie zbudowano, więc plik
                                                     był martwym kosztem. Nowe gry
                                                     go nie tworzą; ``wczytaj`` wciąż
                                                     migruje legacy `.md` z `skrypty/`
                                                     (de-clutter dialogu Reżysera).
    * ``runtime/opowiesci/<nazwa>.game.json``      — pełny stan gry (overwrite per tura)
    * ``runtime/opowiesci/<nazwa>.story.jsonl``    — append-only log surowych tur
                                                     (request payload + response JSON)
    * ``runtime/opowiesci/<nazwa>.mode``           — zapisany tryb (3/4/5).
                                                     v17.4: WŁASNY folder Opowieści
                                                     (koniec współdzielenia z
                                                     Reżyserem, który trzyma swój
                                                     ``.mode`` 1/2 w
                                                     ``runtime/skrypty/``). Dawniej
                                                     wspólny plik powodował, że przy
                                                     zbieżnej nazwie projektu zapis
                                                     jednego modułu cicho nadpisywał
                                                     tryb drugiego; ``wczytaj`` migruje
                                                     stare pliki 3/4/5 do nowej
                                                     lokalizacji

Faza 3 NIE robi auto-streszczenia ani wskaźnika pamięci modelu — to Faza 4.
``wczytaj()`` toleruje uszkodzone pliki (cichy fail per element nieobowiązkowy),
żeby pojedynczy krytyczny zapis nie zablokował dostępu do reszty gry.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any

# Stałe folderów dzielimy z Reżyserem — `core_rezyser.SKRYPTY_DIR`/`RUNTIME_DIR`.
# DRY: jeden punkt prawdy, jakby kiedyś zmieniła się nazwa folderu, oba moduły
# dostaną zmianę.
import sciezki
from core_rezyser import RUNTIME_DIR, SKRYPTY_DIR, _dev_log_runtime

# Podfolder runtime/ specyficzny dla Opowieści — `runtime/opowiesci/<nazwa>.{game.json,story.jsonl}`.
OPOWIESCI_DIR = "opowiesci"

# Regex Cinematic Meta Warning. Faza 4 wprowadzi mechanikę „LLM emituje
# ostrzeżenie dramatyczne między ⚠️🚨⚠️ markerami po 150 turach". Tutaj
# już mamy filter, żeby Faza 3 (która zapisuje narrację) była przygotowana
# i nie trzeba było wracać do `core_opowiesci.py` w Fazie 4.
# `re.DOTALL` (`s` flag) — `.` matchuje też newline, ostrzeżenie może
# być wielolinijkowe.
_REGEX_META_WARNING = re.compile(
    r"⚠️🚨⚠️.*?⚠️🚨⚠️",
    re.DOTALL,
)


# =============================================================================
# Wynik wczytania (POCO przekazywane do GUI)
# =============================================================================

@dataclass
class WynikWczytaniaOpowiesci:
    """Rezultat :meth:`ProjektOpowiesci.wczytaj` — co i w jakiej ilości trafiło do pamięci."""
    nazwa: str
    czy_game_json:           bool = False
    czy_narracja:            bool = False
    czy_story_jsonl:         bool = False
    saved_mode:              int | None = None
    numer_tury:              int = 0
    liczba_znakow_narracji:  int = 0


# =============================================================================
# Klasa główna: ProjektOpowiesci
# =============================================================================

class ProjektOpowiesci:
    """Stan gry interaktywnej + I/O dyskowe.

    Atrybuty:
        app_dir            : katalog roota repo / instalacji (default = lokalizacja modułu)
        nazwa_pliku        : nazwa gry bez rozszerzenia (np. „kroniki_arkonii")
        full_story         : pełna narracja w pamięci (cache do `.txt` na dysku)
        postacie_aktywne   : lista ``{"imie", "cechy"}`` z ostatniej tury LLM
        stan               : ``{"lokacja", "ekwipunek_zmiany", "watki_otwarte"}``
                             z ostatniej tury LLM
        tryb               : 3=Swobodny, 4=Wybory, 5=Mniejsze zło
        jezyk_projektu     : kod języka narracji ("pl"/"en"/...)
        seed_swiata        : opcjonalny opis świata gracza (od /nowa); ""
                             jeśli świat ma być wylosowany przez LLM
        numer_tury         : licznik; 0 przed pierwszą turą, inkrementowany
                             przed wysyłką w ``OpowiesciPanel._on_wyslij``
        ostatnie_tury      : skondensowana historia (FIFO, ostatnie 6 par
                             akcja+narracja_skrót); Faza 4 doda streszczenie
        zasady_swiata      : opcjonalny tekst z regułami świata zdefiniowanymi
                             przez gracza (fonetyka tożsamości, koncepcje
                             mechaniczne, ograniczenia kulturowe). Pusty
                             string = stary tryb, kompatybilność wsteczna.
                             Wstrzykiwany do prompt-systemowy przez
                             :func:`opowiesci_ai._zbuduj_prompt_systemowy`
                             jeśli niepusty. v15.1+.
        ostatnie_wybory    : lista wyborów wygenerowanych przez LLM w ostatniej
                             turze (struktury ``{"id","tekst"}``). Persystowane
                             w `.game.json` od v15.1, by po wczytaniu gry
                             w trybie Wyborów/Mniejszego Zła odtworzyć
                             przyciski — gracz nie musi pisać free-textu
                             po reloadzie. Puste w trybie Swobodnym (3).
    """

    def __init__(self, app_dir: str | None = None) -> None:
        self.app_dir: str = app_dir or sciezki.KATALOG_BAZOWY_STR
        self.nazwa_pliku: str = ""
        self.full_story: str = ""
        self.postacie_aktywne: list[dict[str, str]] = []
        self.stan: dict[str, Any] = {}
        self.tryb: int = 3
        self.jezyk_projektu: str = "pl"
        self.seed_swiata: str = ""
        self.numer_tury: int = 0
        self.ostatnie_tury: list[dict[str, str]] = []
        self.zasady_swiata: str = ""
        self.ostatnie_wybory: list[dict[str, str]] = []

    # ------------------------------------------------------------------
    # Walidacja stanu
    # ------------------------------------------------------------------
    def _wymagaj_nazwy(self) -> None:
        if not self.nazwa_pliku:
            raise ValueError(
                "ProjektOpowiesci nie ma ustawionej nazwy gry — przed I/O "
                "wywołaj `_on_nowa_gra` lub `wczytaj(nazwa)`."
            )

    # ------------------------------------------------------------------
    # Ścieżki pomocnicze
    # ------------------------------------------------------------------
    def _sciezka_txt(self, nazwa: str) -> str:
        # v15.2.3: user-facing pliki Opowieści (.txt + .md) wydzielone do
        # własnego folderu `opowiesci/` — wcześniej leżały w `skrypty/`
        # razem z projektami Reżysera, co powodowało kolizje w dialogu
        # wyboru projektu Reżysera (saved_mode 3/4/5 nie pasowało do
        # zakresu 1/2 Reżysera, fallback otwierał wszystkie tryby).
        return os.path.join(self.app_dir, OPOWIESCI_DIR, f"{nazwa}.txt")

    def _sciezka_md(self, nazwa: str) -> str:
        return os.path.join(self.app_dir, OPOWIESCI_DIR, f"{nazwa}.md")

    def _sciezka_txt_legacy(self, nazwa: str) -> str:
        """v15.2.3: ścieżka starych plików Opowieści w `skrypty/` (pre-migracja).

        Używana wyłącznie w `wczytaj()` do detekcji pre-15.2.3 gier i
        automatycznego przeniesienia ich do nowego folderu `opowiesci/`.
        """
        return os.path.join(self.app_dir, SKRYPTY_DIR, f"{nazwa}.txt")

    def _sciezka_md_legacy(self, nazwa: str) -> str:
        """v15.2.3: legacy Księga Świata w `skrypty/` — patrz `_sciezka_txt_legacy`."""
        return os.path.join(self.app_dir, SKRYPTY_DIR, f"{nazwa}.md")

    def _sciezka_game_json(self, nazwa: str) -> str:
        return os.path.join(self.app_dir, RUNTIME_DIR, OPOWIESCI_DIR, f"{nazwa}.game.json")

    def _sciezka_story_jsonl(self, nazwa: str) -> str:
        return os.path.join(self.app_dir, RUNTIME_DIR, OPOWIESCI_DIR, f"{nazwa}.story.jsonl")

    def _sciezka_mode(self, nazwa: str) -> str:
        # v17.4: WŁASNY folder `runtime/opowiesci/` — koniec współdzielenia
        # `.mode` z Reżyserem. Dawniej oba moduły pisały do
        # `runtime/skrypty/<nazwa>.mode`, mimo rozłącznych zakresów wartości
        # (Reżyser 1/2, Opowieści 3/4/5). Przy tej samej nazwie projektu w obu
        # narzędziach zapis jednego CICHO NADPISYWAŁ tryb drugiego — ochrona
        # trybu padała otwarta („furtki dowolnych wyborów"). To dokładnie ta
        # sama klasa kolizji, którą v15.2.3 naprawiła dla `.txt`/`.md`,
        # przeoczając `.mode`. Teraz `.mode` Opowieści leży obok pozostałych
        # ich plików stanu (`.game.json`/`.story.jsonl`); migracja starych
        # plików z wartością 3/4/5 → `wczytaj` (z gwardią zakresu, żeby NIE
        # ukraść Reżyserowi jego pliku 1/2).
        return os.path.join(self.app_dir, RUNTIME_DIR, OPOWIESCI_DIR, f"{nazwa}.mode")

    def _sciezka_mode_legacy(self, nazwa: str) -> str:
        """Pre-v17.4 ścieżka `.mode` współdzielona z Reżyserem (`runtime/skrypty/`).

        Używana wyłącznie w `wczytaj()` do jednorazowej migracji starych
        plików trybu Opowieści (wartość 3/4/5) do nowego folderu.
        """
        return os.path.join(self.app_dir, RUNTIME_DIR, SKRYPTY_DIR, f"{nazwa}.mode")

    # ------------------------------------------------------------------
    # Statyczne helpery
    # ------------------------------------------------------------------
    @staticmethod
    def istnieje(nazwa: str, app_dir: str | None = None) -> bool:
        """Czy gra o danej nazwie ma już artefakty na dysku?

        Sprawdza obecność `.game.json` (źródło prawdy o grze). `.txt`
        może istnieć z Reżysera (kolizja nazw) — to NIE oznacza, że gra
        Opowieści istnieje. Stąd ten helper bazuje wyłącznie na `.game.json`.
        """
        base = app_dir or sciezki.KATALOG_BAZOWY_STR
        return os.path.exists(
            os.path.join(base, RUNTIME_DIR, OPOWIESCI_DIR, f"{nazwa}.game.json")
        )

    @staticmethod
    def czysc_meta_warningi(tekst: str) -> str:
        """Wycina Cinematic Meta Warningi z narracji przed appendem do `.txt`.

        Faza 4 wprowadzi LLM-generowane ostrzeżenia dramatyczne (pojawią się
        po ~150 turach). Trafiają one do `.story.jsonl` jako log surowy,
        ale NIE do `.txt` przeznaczonego do TTS — gracz nie chce słyszeć
        meta-komentarza o własnej historii w trakcie odsłuchu.

        Faza 3 implementuje filter już teraz, mimo że ostrzeżeń jeszcze
        nie ma — łatwiej dodać kontrakt zanim pierwszy tekst trafi na
        dysk niż refaktorować plik narracji potem.
        """
        return _REGEX_META_WARNING.sub("", tekst)

    # ------------------------------------------------------------------
    # Operacje zapisu
    # ------------------------------------------------------------------
    def dopisz_do_txt(self, narracja: str, naglowek: str = "") -> str:
        """Append narracji do `skrypty/<nazwa>.txt` (po przefiltrowaniu meta).

        Args:
            narracja: tekst narracji LLM (już bez wyborów, bez JSON-a).
            naglowek: opcjonalny prefix (np. ``"\\n\\n--- Tura 5 ---\\n\\n"``)
                      dodawany PRZED narracją — pomaga TTS odróżnić tury,
                      a NVDA dostaje czytelny separator.

        Zwraca pełną ścieżkę zapisanego pliku.
        """
        self._wymagaj_nazwy()
        opowiesci = os.path.join(self.app_dir, OPOWIESCI_DIR)
        os.makedirs(opowiesci, exist_ok=True)
        sciezka = self._sciezka_txt(self.nazwa_pliku)

        czyste = self.czysc_meta_warningi(narracja)
        with open(sciezka, "a", encoding="utf-8") as fh:
            fh.write(naglowek + czyste)

        # Cache w pamięci synchronizujemy ręcznie, żeby GUI mogło pokazać
        # narrację bez ponownego czytania z dysku.
        self.full_story = (self.full_story or "") + naglowek + czyste
        return sciezka

    def przeladuj_narracje_z_dysku(self) -> str:
        """v15.5: ponownie wczytuje `opowiesci/<nazwa>.txt` do ``full_story``.

        Czyste I/O — synchronizuje cache narracji w RAM z ręcznymi zmianami
        na dysku (np. ucięciem złamanego kinowego cięcia). NIE dotyka
        ``ostatnie_tury`` (kontekst LLM) — rekoncyliację tej struktury robi
        GUI, bo wymaga decyzji o streszczeniu. Zwraca nową treść.

        Raises:
            ValueError:        gdy projekt nie ma ustawionej nazwy.
            FileNotFoundError: gdy nie istnieje `opowiesci/<nazwa>.txt`.
        """
        self._wymagaj_nazwy()
        sciezka = self._sciezka_txt(self.nazwa_pliku)
        if not os.path.exists(sciezka):
            raise FileNotFoundError(sciezka)
        with open(sciezka, "r", encoding="utf-8") as fh:
            self.full_story = fh.read()
        return self.full_story

    # v17.4 (P6A): `rebuild_ksiega_swiata` USUNIĘTE. Generowało po każdej
    # turze `<nazwa>.md` w formacie `[Imię: cechy]` „zgodnym z parserem
    # Reżysera" jako rzekomy MOST Opowieści → Reżyser. Mostu jednak nigdy
    # nie zbudowano (brak jakiejkolwiek ścieżki UI wczytania opowieści do
    # Reżysera), a parser Reżysera czyta z tego formatu wyłącznie akcenty —
    # więc plik był martwym kosztem I/O na każdej turze. Stara migracja `.md`
    # w `wczytaj()` zostaje (odsuwa legacy księgę z `skrypty/`, by nie
    # kolidowała z Księgą Świata Reżysera); nowe pliki `.md` nie powstają.

    def zapisz_game_json(self) -> str:
        """Overwrite pełnego stanu gry do `runtime/opowiesci/<nazwa>.game.json`.

        Plik jest źródłem prawdy do reload-a gry — zawiera wszystko, co
        :meth:`wczytaj` potrzebuje, żeby przywrócić sesję do tego samego
        miejsca po zamknięciu aplikacji. Schema:

            {
              "nazwa_gry":        str,
              "tryb":             int,
              "jezyk_projektu":   str,
              "seed_swiata":      str,
              "numer_tury":       int,
              "postacie_aktywne": list[{"imie","cechy"}],
              "stan":             dict,
              "ostatnie_tury":    list[{"akcja_gracza","narracja_skrot"}],
              "zasady_swiata":    str,
              "ostatnie_wybory":  list[{"id","tekst"}]    # v15.1+
            }

        (Pole ``cuty_wykorzystane`` istniało w schemacie v15.4–v17.2; usunięte
        w v17.3 razem z funkcją „druga kamera". Stare zapisy z tym polem
        wczytują się czysto — ``wczytaj`` po prostu je ignoruje.)

        Pole ``full_story`` celowo NIE jest tu zapisane — narracja żyje
        w `.txt` (jeden plik, jedna prawda; uniknięcie podwójnej synchronizacji).
        """
        self._wymagaj_nazwy()
        runtime_op = os.path.join(self.app_dir, RUNTIME_DIR, OPOWIESCI_DIR)
        os.makedirs(runtime_op, exist_ok=True)
        sciezka = self._sciezka_game_json(self.nazwa_pliku)

        payload = {
            "nazwa_gry":         self.nazwa_pliku,
            "tryb":              self.tryb,
            "jezyk_projektu":    self.jezyk_projektu,
            "seed_swiata":       self.seed_swiata,
            "numer_tury":        self.numer_tury,
            "postacie_aktywne":  self.postacie_aktywne,
            "stan":              self.stan,
            "ostatnie_tury":     self.ostatnie_tury,
            "zasady_swiata":     self.zasady_swiata,
            "ostatnie_wybory":   self.ostatnie_wybory,
        }
        with open(sciezka, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        _dev_log_runtime(sciezka)
        return sciezka

    def dopisz_story_jsonl(self, payload: dict[str, Any]) -> str:
        """Append-only log jednej tury do `runtime/opowiesci/<nazwa>.story.jsonl`.

        Format JSONL: jedna linia = jeden JSON object, zakończona ``\\n``.
        Pojedyncza linia powinna być samodzielnym JSON-em — nie blokujemy
        na zewnętrznej tablicy, bo wtedy nie da się streamować ani
        bezpiecznie tolerować ucięcia w połowie pliku (ostatnia uszkodzona
        linia parsuje się po prostu jako błąd, a poprzednie wciąż są
        czytelne).

        Args:
            payload: dowolny dict (zalecane:
                     ``{"tura", "akcja_gracza", "request_messages",
                       "response_json"}``); decyzja co zapisać należy do
                     wywołującego.
        """
        self._wymagaj_nazwy()
        runtime_op = os.path.join(self.app_dir, RUNTIME_DIR, OPOWIESCI_DIR)
        os.makedirs(runtime_op, exist_ok=True)
        sciezka = self._sciezka_story_jsonl(self.nazwa_pliku)

        with open(sciezka, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
        _dev_log_runtime(sciezka)
        return sciezka

    def ostatnia_tura_surowa(self, nazwa: str) -> str | None:
        """Zwraca `response_json` z OSTATNIEJ niepustej linii `.story.jsonl`.

        v17.9 (Obszar 2): ożywia dotąd write-only log. Po wczytaniu gry z dysku
        GUI używa tego do wskrzeszenia `SnapshotOpowiesci.ostatni_surowy_json` —
        surowy JSON ostatniej tury trafia do kolejnej tury jako wiadomość
        `role=assistant` (ciągłość + wzorzec struktury). W trakcie gry źródłem
        jest świeży `WynikTury.surowy_json`; ten odczyt potrzebny TYLKO po
        reloadzie (gdy pamięć RAM nie zna jeszcze ostatniej tury).

        Tolerancyjne — brak pliku / uszkodzona ostatnia linia / brak klucza →
        ``None`` (degradacja: kolejna tura po prostu nie dostanie assistant-turna,
        co jest bezpieczne, tylko mniej kontekstu ciągłości).
        """
        sciezka = self._sciezka_story_jsonl(nazwa)
        if not os.path.exists(sciezka):
            return None
        ostatnia: str | None = None
        try:
            with open(sciezka, "r", encoding="utf-8") as fh:
                for linia in fh:
                    if linia.strip():
                        ostatnia = linia
        except OSError:
            return None
        if not ostatnia:
            return None
        try:
            wpis = json.loads(ostatnia)
        except ValueError:
            return None
        rj = wpis.get("response_json") if isinstance(wpis, dict) else None
        return rj if isinstance(rj, str) and rj.strip() else None

    def zapisz_tryb(self, tryb_int: int) -> None:
        """Zapisuje aktualny tryb do `runtime/opowiesci/<nazwa>.mode` (cichy fail).

        Akceptowane wartości: ``3`` (Swobodny), ``4`` (Wybory), ``5``
        (Mniejsze zło). Inne (0=Burza, 1/2=Reżyser) są ignorowane —
        Reżyser ma własny zapis dla swoich trybów.

        v17.4: własny folder `runtime/opowiesci/` (koniec współdzielenia
        z Reżyserem — patrz :meth:`_sciezka_mode`). Wzorzec dokładnie jak
        :meth:`core_rezyser.ProjektRezysera.zapisz_tryb_tworczy`: metadata
        trybu to quality-of-life feature, więc cichy fail przy problemie
        z dyskiem (np. read-only USB stick) — gra zostaje grywalna.
        """
        if not self.nazwa_pliku or tryb_int not in (3, 4, 5):
            return
        meta_dir = os.path.join(self.app_dir, RUNTIME_DIR, OPOWIESCI_DIR)
        os.makedirs(meta_dir, exist_ok=True)
        sciezka = self._sciezka_mode(self.nazwa_pliku)
        try:
            with open(sciezka, "w", encoding="utf-8") as fh:
                fh.write(str(tryb_int))
            _dev_log_runtime(sciezka)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Wczytywanie
    # ------------------------------------------------------------------
    def wczytaj(self, nazwa: str) -> WynikWczytaniaOpowiesci:
        """Wczytuje grę: stan z `.game.json` + narrację z `.txt` + tryb z `.mode`.

        Tolerancyjne — uszkodzone pliki nieobowiązkowe (np. ucięty
        ``.story.jsonl``) NIE blokują startu gry. Tylko brak `.game.json`
        rzuca ``FileNotFoundError`` — bez tego pliku nie wiadomo co to za gra.

        Po sukcesie ustawia ``self.nazwa_pliku``; gracz może od razu robić
        kolejną turę.
        """
        sciezka_json = self._sciezka_game_json(nazwa)
        if not os.path.exists(sciezka_json):
            raise FileNotFoundError(sciezka_json)

        # v15.2.3: auto-migracja pre-patch gier — pliki .txt / .md Opowieści
        # przed tą wersją leżały w `skrypty/` razem z projektami Reżysera, co
        # zlewało domeny i powodowało, że Reżyserowy dialog wyboru projektu
        # pokazywał też gry Opowieści. Tu jednorazowo przenosimy je do
        # nowego folderu `opowiesci/`. Warunek bezpieczeństwa: ruch tylko gdy
        # nowy plik jeszcze nie istnieje I stary plik istnieje I gra ma
        # `.game.json` (potwierdzenie, że to faktycznie Opowieści, nie
        # projekt Reżysera o przypadkowo zbieżnej nazwie).
        for sciezka_nowa_fn, sciezka_legacy_fn in (
            (self._sciezka_txt, self._sciezka_txt_legacy),
            (self._sciezka_md,  self._sciezka_md_legacy),
        ):
            sciezka_nowa = sciezka_nowa_fn(nazwa)
            sciezka_legacy = sciezka_legacy_fn(nazwa)
            if os.path.exists(sciezka_nowa):
                continue
            if not os.path.exists(sciezka_legacy):
                continue
            try:
                os.makedirs(os.path.dirname(sciezka_nowa), exist_ok=True)
                os.rename(sciezka_legacy, sciezka_nowa)
            except OSError:
                # Cichy fail — gracz może mieć read-only USB stick albo
                # plik zablokowany przez Notatnik. Nie blokujemy load-a;
                # w najgorszym razie txt zostanie w starym folderze i
                # gracz zobaczy go w obu dialogach do następnej próby.
                pass

        with open(sciezka_json, "r", encoding="utf-8") as fh:
            dane = json.load(fh)

        # Hardenowane mapowanie z fallbackami — pole, którego brakuje w
        # zapisanym pliku (bo np. powstał w starszej wersji formatu),
        # dostaje sensowny default. To zapobiega crashowi po update'cie
        # aplikacji, który dodaje nowe pole do schemy game.json.
        self.nazwa_pliku       = nazwa
        self.tryb              = int(dane.get("tryb", 3))
        self.jezyk_projektu    = str(dane.get("jezyk_projektu", "pl"))
        self.seed_swiata       = str(dane.get("seed_swiata", ""))
        self.numer_tury        = int(dane.get("numer_tury", 0))
        self.postacie_aktywne  = list(dane.get("postacie_aktywne", []))
        self.stan              = dict(dane.get("stan", {}))
        self.ostatnie_tury     = list(dane.get("ostatnie_tury", []))
        self.zasady_swiata     = str(dane.get("zasady_swiata", ""))
        self.ostatnie_wybory   = list(dane.get("ostatnie_wybory", []))
        # v17.3: pole `cuty_wykorzystane` (v15.4 „druga kamera") usunięte —
        # stare zapisy mogą je jeszcze zawierać, po prostu je ignorujemy.

        wynik = WynikWczytaniaOpowiesci(
            nazwa=nazwa,
            czy_game_json=True,
            numer_tury=self.numer_tury,
        )

        # Narracja `.txt` — opcjonalna, ale 99% przypadków istnieje.
        sciezka_txt = self._sciezka_txt(nazwa)
        if os.path.exists(sciezka_txt):
            try:
                with open(sciezka_txt, "r", encoding="utf-8") as fh:
                    self.full_story = fh.read()
                wynik.czy_narracja           = True
                wynik.liczba_znakow_narracji = len(self.full_story)
            except Exception:
                self.full_story = ""

        # `.story.jsonl` — log, sam fakt jego istnienia raportujemy GUI,
        # ale nie wczytujemy go do pamięci (to byłby niepotrzebny memory bloat;
        # stan z `.game.json` w zupełności wystarczy do kontynuacji).
        wynik.czy_story_jsonl = os.path.exists(self._sciezka_story_jsonl(nazwa))

        # Tryb z `.mode` (v17.4: własny folder `runtime/opowiesci/`).
        # Jednorazowa migracja starych plików ze współdzielonego
        # `runtime/skrypty/<nazwa>.mode` — TYLKO gdy stara wartość należy do
        # zakresu Opowieści (3/4/5). Plik 1/2 zostaje nietknięty: należy do
        # Reżysera o przypadkowo zbieżnej nazwie, a jego kradzież odtworzyłaby
        # dawną kolizję w drugą stronę.
        sciezka_mode = self._sciezka_mode(nazwa)
        if not os.path.exists(sciezka_mode):
            sciezka_mode_legacy = self._sciezka_mode_legacy(nazwa)
            if os.path.exists(sciezka_mode_legacy):
                try:
                    with open(sciezka_mode_legacy, "r", encoding="utf-8") as fh:
                        surowy_legacy = fh.read().strip()
                    if surowy_legacy.isdigit() and int(surowy_legacy) in (3, 4, 5):
                        os.makedirs(os.path.dirname(sciezka_mode), exist_ok=True)
                        os.rename(sciezka_mode_legacy, sciezka_mode)
                except OSError:
                    # Cichy fail (read-only nośnik / plik zablokowany) — tryb
                    # wczyta się przez fallback `dane["tryb"]` z game.json.
                    pass

        # Odczyt z WALIDACJĄ ZAKRESU — akceptujemy tylko 3/4/5. Wartość spoza
        # zakresu (np. resztka po starej kolizji z Reżyserem) traktujemy jak
        # brak, by GUI spadło na `dane["tryb"]` zamiast otwierać złe furtki.
        try:
            with open(sciezka_mode, "r", encoding="utf-8") as fh:
                surowy = fh.read().strip()
            if surowy.isdigit() and int(surowy) in (3, 4, 5):
                wynik.saved_mode = int(surowy)
        except Exception:
            wynik.saved_mode = None

        return wynik
