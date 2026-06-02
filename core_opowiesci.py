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
    * ``skrypty/<nazwa>.md``                       — Księga Świata, idempotentny
                                                     rebuild z ``postacie_aktywne``;
                                                     format ``[Imię: cechy]`` zgodny
                                                     z parserem :func:`core_rezyser`,
                                                     wiersz 199 (regex
                                                     ``r"\\[([^:\\]\\-]+).*?\\]"``).
                                                     Plik jest **mostem** Opowieści →
                                                     Reżyser: gracz może wczytać tę
                                                     samą grę w drugim module i
                                                     dostać natywne akcenty postaci.
    * ``runtime/opowiesci/<nazwa>.game.json``      — pełny stan gry (overwrite per tura)
    * ``runtime/opowiesci/<nazwa>.story.jsonl``    — append-only log surowych tur
                                                     (request payload + response JSON)
    * ``runtime/skrypty/<nazwa>.mode``             — zapisany tryb (3/4/5) — TEN SAM
                                                     folder co Reżyser, bo numeracja
                                                     ``.mode`` jest globalna
                                                     (0=Burza, 1=Reżyser1,
                                                     2=Reżyser2, 3=Swobodny,
                                                     4=Wybory, 5=Mniejsze zło);
                                                     różne nazwy projektu nie
                                                     kolidują, ten sam folder upraszcza
                                                     management metadanych

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
from core_rezyser import RUNTIME_DIR, SKRYPTY_DIR

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
        self.app_dir: str = app_dir or os.path.dirname(os.path.abspath(__file__))
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
        # v15.4: licznik kinowych cięć narracyjnych per etap łuku
        # (`narracja_typ != "druga_osoba"`). Persystowany w `.game.json` żeby
        # przeżyć restart aplikacji — gracz wracający po 3 dniach nie dostaje
        # zresetowanego limitu auto-cut. Etapy zgodne z `meta.etap_luku`
        # z odpowiedzi LLM (ekspozycja → narastanie → kulminacja → rozwiązanie).
        self.cuty_wykorzystane: dict[str, int] = {
            "ekspozycja": 0, "narastanie": 0, "kulminacja": 0, "rozwiazanie": 0,
        }

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
        # Współdzielone z Reżyserem — `core_rezyser._sciezka_mode` używa
        # tej samej ścieżki. Numeracja `.mode` jest globalna (0/1/2/3/4/5),
        # więc jedno repo metadanych eliminuje ryzyko desynchronizacji.
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
        base = app_dir or os.path.dirname(os.path.abspath(__file__))
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

    def rebuild_ksiega_swiata(self) -> str:
        """Idempotentny rebuild `skrypty/<nazwa>.md` z ``postacie_aktywne``.

        Format zgodny z parserem :func:`core_rezyser.zastosuj_akcenty_uniwersalne`
        (wiersz 199, regex ``r"\\[([^:\\]\\-]+).*?\\]"``):

            # Księga Świata — gra <nazwa>
            # Generowana automatycznie po każdej turze Opowieści.
            # Parser Reżysera wymaga formatu [Imię: cechy].

            [Imię1: cechy]
            [Imię2: cechy]

        Po zapisie ten sam plik może zostać wczytany przez panel Reżysera
        (Plik → Wczytaj → wybierz nazwę gry) — Reżyser potraktuje postaci
        jako Księgę Świata i będzie aplikować akcenty + reguły ad-hoc Lore.
        Dlatego ZAWSZE jest rebuild ze stanu bieżącego (overwrite), nigdy
        append — żeby usunięte postacie znikały z pliku.

        Zwraca pełną ścieżkę zapisanego pliku.
        """
        self._wymagaj_nazwy()
        opowiesci = os.path.join(self.app_dir, OPOWIESCI_DIR)
        os.makedirs(opowiesci, exist_ok=True)
        sciezka = self._sciezka_md(self.nazwa_pliku)

        # Komentarze NIE używają nawiasów kwadratowych z dwukropkiem — parser
        # Reżysera (`core_rezyser.py:199`, `re.split(r"\[([^:\]\-]+).*?\]", ...)`)
        # nie odróżnia komentarzy od linii postaci, więc każde `[X:...]` w
        # nagłówku zostałoby potraktowane jak fałszywa postać. Stąd okrągłe
        # nawiasy w prozie metadanych.
        linie: list[str] = [
            f"# Księga Świata — gra {self.nazwa_pliku}",
            "# Generowana automatycznie po każdej turze Opowieści (v15.0).",
            "# Parser Reżysera wymaga formatu (Imię: cechy) — nie zmieniaj ręcznie",
            "# w trakcie aktywnej rozgrywki, bo nadpisze następna tura.",
            "",
        ]
        for postac in self.postacie_aktywne:
            imie = (postac.get("imie") or "").strip()
            cechy = (postac.get("cechy") or "").strip()
            if not imie:
                continue   # bez imienia parser i tak by tej linii nie złapał
            # Sanity: wycinamy `[`/`]`/`:` z imienia, żeby nie rozwalić parsera.
            imie_safe = imie.replace("[", "(").replace("]", ")").replace(":", " ")
            linie.append(f"[{imie_safe}: {cechy}]")

        with open(sciezka, "w", encoding="utf-8") as fh:
            fh.write("\n".join(linie) + "\n")
        return sciezka

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
            "cuty_wykorzystane": self.cuty_wykorzystane,   # v15.4
        }
        with open(sciezka, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
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
        return sciezka

    def zapisz_tryb(self, tryb_int: int) -> None:
        """Zapisuje aktualny tryb do `runtime/skrypty/<nazwa>.mode` (cichy fail).

        Akceptowane wartości: ``3`` (Swobodny), ``4`` (Wybory), ``5``
        (Mniejsze zło). Inne (0=Burza, 1/2=Reżyser) są ignorowane —
        Reżyser ma własny zapis dla swoich trybów.

        Wzorzec dokładnie jak :meth:`core_rezyser.ProjektRezysera.zapisz_tryb_tworczy`:
        metadata trybu to quality-of-life feature, więc cichy fail przy
        problemie z dyskiem (np. read-only USB stick) — gra zostaje grywalna.
        """
        if not self.nazwa_pliku or tryb_int not in (3, 4, 5):
            return
        meta_dir = os.path.join(self.app_dir, RUNTIME_DIR, SKRYPTY_DIR)
        os.makedirs(meta_dir, exist_ok=True)
        sciezka = self._sciezka_mode(self.nazwa_pliku)
        try:
            with open(sciezka, "w", encoding="utf-8") as fh:
                fh.write(str(tryb_int))
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
        # v15.4: gry pre-15.4 nie miały pola — fallback do pełnego słownika
        # zer (gracz dostaje pełen limit auto-cut po update'cie aplikacji).
        # Hardening: brakujące klucze etapów (gdyby zapis był ucięty) też
        # uzupełniamy zerami, żeby `cuty_wykorzystane[etap]` nigdy nie rzucił.
        domyslne_cuty = {"ekspozycja": 0, "narastanie": 0, "kulminacja": 0, "rozwiazanie": 0}
        wczytane_cuty = dict(dane.get("cuty_wykorzystane", {}))
        self.cuty_wykorzystane = {etap: int(wczytane_cuty.get(etap, 0)) for etap in domyslne_cuty}

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

        # Tryb z `.mode` — może być None jeśli plik nie istnieje albo
        # zawiera śmiecia. Jeśli jest sensowny, mamy szansę zsynchronizować
        # GUI bez polegania na `dane["tryb"]` (defensywny double-check).
        try:
            with open(self._sciezka_mode(nazwa), "r", encoding="utf-8") as fh:
                surowy = fh.read().strip()
                if surowy.isdigit():
                    wynik.saved_mode = int(surowy)
        except Exception:
            wynik.saved_mode = None

        return wynik
