"""
core_rezyser.py – Model i silnik modułu Reżyser Audio GPT.

Przechowuje cały **stan projektu** (historia, Księga Świata, streszczenie,
liczniki rozdziałów/aktów/scen) wraz z pełnym **I/O dyskowym** oraz
silnikiem fonetycznym (nakładającym akcenty z Księgi Świata na kwestie
dialogowe w trybie Skrypt). Nie zna wxPython ani OpenAI – komunikuje się
z GUI wyłącznie przez klasę :class:`ProjektRezysera` i z wątkiem tła
przez niezmienny :class:`SnapshotProjektu`.

Dlaczego osobny plik (wersja 13.0)?
    * Stan projektu jest używany zarówno przez GUI, jak i przez wątek
      AI – naturalne jest trzymanie go w jednym miejscu, zamiast
      rozsypywania po atrybutach ``wx.Panel``.
    * Testowalność: wszystkie metody są czysto-Pythonowe; testy
      jednostkowe nie muszą mockować ``wx.MessageBox``.
    * Lingwista / programista dostaje jasną mapę tego, co aplikacja
      naprawdę trzyma w pamięci o projekcie.

Publiczne API:

    from core_rezyser import ProjektRezysera

    proj = ProjektRezysera()          # app_dir wywnioskowany z __file__

    # Wczytanie istniejącego projektu (z liczników + Księgi Świata + trybu)
    wynik = proj.wczytaj("kroniki_arkonii")   # WynikWczytania

    # Zapis
    proj.zapisz_ksiege_swiata("[Geralt: akcent islandzki] ...")
    proj.zapisz_streszczenie("W poprzednich odcinkach...")
    proj.dopisz_do_pliku_historii("Tekst sceny.", mode="a")
    proj.zapisz_tryb_tworczy(2)               # 1=Skrypt, 2=Audiobook

    # Struktura – mutuje pamięć i plik na dysku
    proj.wstaw_prolog()
    akt, scena1 = proj.wstaw_akt()
    proj.wstaw_rozdzial()

    # Status pamięci modelu (wskaźnik „czy pora na streszczenie")
    status = proj.status_pamieci_modelu()     # StatusPamieciModelu
    print(status.procent, status.poziom, status.komunikat)

    # Mutacje
    proj.wyczysc_biezaca()       # zostaw Księgę i streszczenie
    proj.twardy_reset()          # wyzeruj wszystko

    # Snapshot dla wątku tła AI (odcina go od zmian w wątku GUI)
    snap = proj.snapshot()

Silnik fonetyczny udostępniany jest jako wolna funkcja
:func:`zastosuj_akcenty_uniwersalne` – dostęp do niej mają zarówno
``rezyser_ai.py`` (po wygenerowaniu odpowiedzi), jak i ewentualne
testy / narzędzia offline.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

# Silnik fonetyczny – punktowy import akcentów z core_poliglota.
# Blok poniżej jest generowany automatycznie przez ``odswiez_rezysera.py``
# na podstawie YAML-i z ``dictionaries/<jezyk>/akcenty/``. NIE edytuj
# ręcznie – uruchom "Odśwież akcenty Reżysera z YAML" w aplikacji.
# <GENEROWANE_IMPORTY_AKCENTOW_START>
from core_poliglota import (
    akcent_islandzki,
    akcent_angielski,
    akcent_rosyjski,
    akcent_francuski,
    akcent_niemiecki,
    akcent_hiszpanski,
    akcent_wloski,
    akcent_finski,
)
# <GENEROWANE_IMPORTY_AKCENTOW_END>

# 13.3: helper do dynamicznego budowania regexa parsera akcentów —
# importowany ręcznie poza blokiem generatora, żeby odświerzacz go nie ruszał.
from core_poliglota import slowa_akcentu


# =============================================================================
# Stałe konfiguracyjne
# =============================================================================

# Foldery projektu (relatywne względem ``app_dir``)
SKRYPTY_DIR = "skrypty"          # pliki .txt / .md / _streszczenie.txt
RUNTIME_DIR = "runtime"          # ukryta metadata – tam leżą .mode

# Limity okna kontekstowego modelu (w znakach full_story).
# LIMIT_PAMIECI to nie twardy limit tokenów OpenAI, tylko bufor bezpieczeństwa
# dla typowej polskiej prozy (~4 znaki na token). Progi wyznaczają, kiedy
# GUI pokazuje ostrzeżenie / wymusza streszczenie.
LIMIT_PAMIECI = 200_000
PROG_ALARM = 175_000
PROG_OSTRZEZENIE = 150_000

# Poziomy statusu pamięci modelu – czytelne dla GUI (kolor + ikonka).
POZIOM_CZYSTA = "czysta"
POZIOM_OK = "ok"
POZIOM_OSTRZEZENIE = "ostrzezenie"
POZIOM_ALARM = "alarm"

# Polskie znaki → ASCII (do normalizacji nazw akcentów w Księdze Świata).
_PL_TO_ASCII = {
    "ą": "a", "ę": "e", "ł": "l", "ó": "o",
    "ś": "s", "ć": "c", "ń": "n", "ż": "z", "ź": "z",
}


# =============================================================================
# Silnik fonetyczny (dawna RezyserPanel.zastosuj_akcenty_uniwersalne)
# =============================================================================

def _usun_polskie(nazwa: str) -> str:
    """Normalizuje nazwę akcentu: 'francuski' OK, 'łotewski' → 'lotewski'."""
    for k, v in _PL_TO_ASCII.items():
        nazwa = nazwa.replace(k, v)
    return nazwa.strip()


def zastosuj_akcenty_uniwersalne(
    tekst: str,
    lore_text: str,
    jezyk_projektu: str = "pl",
) -> str:
    """Aplikuje akcenty fonetyczne z Księgi Świata na tekst skryptu.

    Parsuje Księgę Świata w poszukiwaniu bloków ``[Postać: akcent X]``,
    a następnie stosuje odpowiednią funkcję z ``core_poliglota`` na każdym
    fragmencie tekstu wypowiadanym przez tę postać (między tagami).

    Obsługuje dwa tryby definicji akcentu w Księdze:

        * nazwa akcentu z listy YAML-i ("akcent islandzki"),
        * reguły ad-hoc ("zamień 'w' na 'v'") – stosowane znak po znaku,
          tylko gdy nazwa akcentu nie została rozpoznana.

    Jeśli Księga nie zawiera żadnych definicji akcentów, tekst zwracany
    jest bez zmian.

    Args:
        tekst:           Skrypt audio z tagami ``[Postać: ...]`` i dialogami.
        lore_text:       Treść Księgi Świata (parsowana po blokach postaci).
        jezyk_projektu:  Kod języka, w którym napisany jest tekst skryptu
                         (13.3+). Wybiera ``dictionaries/<jezyk>/akcenty/``
                         przy aplikacji reguł fonetycznych — domyślnie
                         ``"pl"`` (zachowanie sprzed 13.3).
    """
    # ── 1. Wyciąganie mapowania postaci → akcent z Księgi Świata ──
    # 13.3: regex zbudowany dynamicznie z ``slowa_akcentu(jezyk_projektu)``.
    # Słowa-wyzwalacze pochodzą z ``dictionaries/<jezyk>/podstawy.yaml`` (np.
    # PL: ["akcent"], EN: ["accent", "accented"], FI: ["aksentti", "korostus"]).
    # ``\w+`` z flagą ``re.UNICODE`` (domyślną w Py3) łapie diakrytyki
    # skandynawskie/niemieckie/francuskie/cyrylicę — żaden alfabet nie blokuje
    # parsowania tylko dlatego, że nie był na białej liście znaków.
    slowa = slowa_akcentu(jezyk_projektu)
    alt_slow = "|".join(re.escape(s) for s in slowa)
    wzorzec_akcentu = re.compile(
        rf"(?:{alt_slow})\s+(\w+)|(\w+)\s+(?:{alt_slow})",
        re.UNICODE,
    )
    # Reguły ad-hoc Lore: pojedyncze litery zamieniane łącznikiem „na".
    # Same litery na ``\w`` (Unicode) — `na` jako łącznik zostawiamy
    # polski w 13.3, wielojęzyczne łączniki to osobny TODO na 13.x+.
    wzorzec_regul_lore = re.compile(
        r"[\"'](\w)[\"']\s+na\s+[\"'](\w)[\"']",
        re.IGNORECASE | re.UNICODE,
    )

    akcenty_map: dict[str, dict] = {}
    postacie_bloki = re.split(r"\[([^:\]\-]+).*?\]", lore_text)

    for i in range(1, len(postacie_bloki), 2):
        imie = postacie_bloki[i].strip().lower()
        opis = postacie_bloki[i + 1].lower() if i + 1 < len(postacie_bloki) else ""

        akcent_match = wzorzec_akcentu.search(opis)
        nazwa_akcentu = (
            (akcent_match.group(1) or akcent_match.group(2))
            if akcent_match
            else None
        )
        reguly_lore = wzorzec_regul_lore.findall(opis)
        if nazwa_akcentu or reguly_lore:
            akcenty_map[imie] = {"nazwa": nazwa_akcentu, "reguly": reguly_lore}

    if not akcenty_map:
        return tekst

    # Mapa: znormalizowana nazwa akcentu → funkcja fonetyczna z core_poliglota.
    # Blok generowany automatycznie przez ``odswiez_rezysera.py`` po każdym
    # dodaniu nowego pliku YAML w dictionaries/<język>/akcenty/.
    # <GENEROWANY_SLOWNIK_AKCENTOW_START>
    _AKCENT_FUNCS = {
        "islandzki": akcent_islandzki,
        "angielski": akcent_angielski,
        "rosyjski":  akcent_rosyjski,
        "francuski": akcent_francuski,
        "niemiecki": akcent_niemiecki,
        "hiszpanski":akcent_hiszpanski,
        "wloski":    akcent_wloski,
        "finski":    akcent_finski,
    }
# <GENEROWANY_SLOWNIK_AKCENTOW_END>

    # ── 2. Podział skryptu po tagach i aplikacja akcentów ──
    fragmenty = re.split(r"(\[[^\]]+\])", tekst)
    nowe_fragmenty: list[str] = []
    current_speaker: str | None = None

    for frag in fragmenty:
        if frag.startswith("[") and frag.endswith("]"):
            nowe_fragmenty.append(frag)
            m = re.match(r"^\[([^:\]\-]+)", frag)
            current_speaker = m.group(1).strip().lower() if m else None
        else:
            dialog = frag
            if current_speaker and dialog.strip():
                dopasowane_dane = next(
                    (d for k, d in akcenty_map.items()
                     if k in current_speaker or current_speaker in k),
                    None,
                )
                if dopasowane_dane:
                    zmodyfikowano = False
                    if dopasowane_dane["nazwa"]:
                        znorm = _usun_polskie(dopasowane_dane["nazwa"])
                        fn = _AKCENT_FUNCS.get(znorm)
                        if fn:
                            dialog = fn(dialog, jezyk_projektu)
                            zmodyfikowano = True
                    if not zmodyfikowano and dopasowane_dane["reguly"]:
                        for z, na in dopasowane_dane["reguly"]:
                            dialog = (
                                dialog
                                .replace(z.lower(), na.lower())
                                .replace(z.upper(), na.upper())
                            )
            nowe_fragmenty.append(dialog)

    return "".join(nowe_fragmenty)


# =============================================================================
# Wyniki operacji (POCO przekazywane do GUI)
# =============================================================================

@dataclass
class WynikWczytania:
    """Rezultat :meth:`ProjektRezysera.wczytaj` – co i w jakiej ilości trafiło do pamięci."""

    nazwa: str
    czy_historia: bool = False
    czy_streszczenie: bool = False
    czy_ksiega_swiata: bool = False
    liczba_znakow: int = 0
    saved_mode: int | None = None   # 1=Skrypt, 2=Audiobook, None=brak metadanej


@dataclass
class StatusPamieciModelu:
    """Stan wskaźnika pamięci modelu – gotowe dane dla GUI.

    Attributes:
        procent:   0–100, do ustawienia w ``wx.Gauge``.
        komunikat: Pełny tekst (z emoji) – do wyświetlenia w polu statusu.
        poziom:    Jeden z ``POZIOM_*`` – GUI dobiera po nim kolor tekstu.
    """

    procent: int
    komunikat: str
    poziom: str


@dataclass
class SnapshotProjektu:
    """Niezmienny snapshot stanu – przekazywany do wątku tła AI (GIL-safe).

    Wątek nigdy nie dotyka bezpośrednio obiektu :class:`ProjektRezysera`;
    dostaje tylko ten snapshot i callbacki do GUI przez ``wx.CallAfter``.
    Dzięki temu równoczesne mutacje w wątku GUI nie wpływają na payload
    zapytania OpenAI, które jest już w locie.
    """

    nazwa: str
    full_story: str
    summary_text: str
    world_lore: str


# =============================================================================
# Klasa główna: ProjektRezysera
# =============================================================================

class ProjektRezysera:
    """Stan projektu reżyserskiego + I/O dyskowe + zarządzanie strukturą.

    Instancja jest „właścicielem prawdy" o stanie aktualnie otwartego
    projektu. GUI przed każdą operacją I/O synchronizuje swoje kontrolki
    z atrybutami tej klasy (najlepiej przez setter lub bezpośrednie
    przypisanie), a po każdej mutacji z klasą odczytuje stan z powrotem.

    Nie nakłada ograniczeń na współbieżność: wątki w tle powinny
    pracować na :class:`SnapshotProjektu`, nie na żywej instancji.
    """

    def __init__(self, app_dir: str | None = None) -> None:
        # Katalog aplikacji – punkt odniesienia dla folderów skrypty/ i runtime/.
        # Domyślnie wyciąga się z lokalizacji tego modułu, ale dla testów
        # można wskazać dowolny katalog (np. tmp).
        self.app_dir: str = app_dir or os.path.dirname(os.path.abspath(__file__))

        # --- Stan fabuły ---
        self.full_story: str = ""        # bieżąca historia w pamięci
        self.summary_text: str = ""      # Pamięć Długotrwała (streszczenie)
        self.world_lore: str = ""        # Księga Świata – zasady i postacie

        # --- Liczniki struktury ---
        self.chapter_counter: int = 1    # następny numer Rozdziału (Audiobook)
        self.akt_counter: int = 1        # następny numer Aktu (Skrypt)
        self.scena_counter: int = 1      # następny numer Sceny (Skrypt)

        # --- Identyfikacja projektu ---
        self.nazwa_pliku: str = ""       # bez rozszerzenia, np. "kroniki_arkonii"
        self.last_response: str = ""     # ostatnia odpowiedź AI (diagnostyka)

    # ------------------------------------------------------------------
    # Ścieżki pomocnicze
    # ------------------------------------------------------------------
    def _sciezka_historii(self, nazwa: str) -> str:
        return os.path.join(self.app_dir, SKRYPTY_DIR, f"{nazwa}.txt")

    def _sciezka_streszczenia(self, nazwa: str) -> str:
        return os.path.join(self.app_dir, SKRYPTY_DIR, f"{nazwa}_streszczenie.txt")

    def _sciezka_ksiegi(self, nazwa: str) -> str:
        return os.path.join(self.app_dir, SKRYPTY_DIR, f"{nazwa}.md")

    def _sciezka_mode(self, nazwa: str) -> str:
        # Plik .mode trzymany w runtime/skrypty/ – folder „runtime" na Windows
        # jest traktowany jako systemowy, więc niewidoczny dla zwykłych
        # użytkowników końcowych zainstalowanej aplikacji.
        return os.path.join(self.app_dir, RUNTIME_DIR, SKRYPTY_DIR, f"{nazwa}.mode")

    # ------------------------------------------------------------------
    # Wczytywanie
    # ------------------------------------------------------------------
    def wczytaj(self, nazwa: str) -> WynikWczytania:
        """Wczytuje projekt: historię / streszczenie / Księgę Świata / tryb .mode.

        Ustawia liczniki rozdziałów/aktów/scen na podstawie treści historii.
        Implementuje regułę Nieskończonej Pamięci: jeśli istnieje plik
        streszczenia, to wczytujemy streszczenie a ``full_story`` zostaje
        puste (można kontynuować historię operując tylko na streszczeniu).

        Raises:
            FileNotFoundError: gdy nie istnieje plik ``skrypty/<nazwa>.txt``.
        """
        sciezka = self._sciezka_historii(nazwa)
        if not os.path.exists(sciezka):
            raise FileNotFoundError(sciezka)

        with open(sciezka, "r", encoding="utf-8") as fh:
            content = fh.read()

        # --- Liczniki: bierzemy maksimum znalezionych numerów i +1 ---
        chapter_nums = [int(m) for m in re.findall(r"(?i)\brozdzia[łl]\s+(\d+)", content)]
        akt_nums = [int(m) for m in re.findall(r"(?i)\bakt\s+(\d+)", content)]
        # Sceny liczymy tylko wewnątrz OSTATNIEGO aktu – numeracja
        # scen restartuje się z każdym aktem.
        ostatni_split = re.split(r"(?i)\bakt\s+\d+", content)
        ostatni_frag = ostatni_split[-1] if ostatni_split else content
        scena_nums = [int(m) for m in re.findall(r"(?i)\bscena\s+(\d+)", ostatni_frag)]

        self.chapter_counter = (max(chapter_nums) + 1) if chapter_nums else 1
        self.akt_counter = (max(akt_nums) + 1) if akt_nums else 1
        self.scena_counter = (max(scena_nums) + 1) if scena_nums else 1

        wynik = WynikWczytania(nazwa=nazwa)

        # --- Księga Świata (.md) ---
        sciezka_ksiegi = self._sciezka_ksiegi(nazwa)
        if os.path.exists(sciezka_ksiegi):
            try:
                with open(sciezka_ksiegi, "r", encoding="utf-8") as fh:
                    self.world_lore = fh.read()
                wynik.czy_ksiega_swiata = True
            except Exception:
                # Cichy fail – Księga nie jest krytyczna dla wczytania historii.
                pass

        # --- Streszczenie PRIORYTETOWE nad pełną historią ---
        sciezka_strsz = self._sciezka_streszczenia(nazwa)
        if os.path.exists(sciezka_strsz):
            try:
                with open(sciezka_strsz, "r", encoding="utf-8") as fh:
                    self.summary_text = fh.read()
                wynik.czy_streszczenie = True
            except Exception:
                pass
            self.full_story = ""
            wynik.czy_historia = False
            wynik.liczba_znakow = 0
        else:
            self.full_story = content
            self.summary_text = ""
            wynik.czy_historia = True
            wynik.liczba_znakow = len(content)

        # --- Tryb twórczy (.mode) ---
        wynik.saved_mode = self.wczytaj_tryb_tworczy(nazwa)
        self.nazwa_pliku = nazwa
        return wynik

    # ------------------------------------------------------------------
    # Zapis na dysk
    # ------------------------------------------------------------------
    def zapisz_ksiege_swiata(self, tresc: str) -> str:
        """Zapisuje Księgę Świata do pliku ``skrypty/<nazwa>.md``. Zwraca ścieżkę.

        Aktualizuje także ``self.world_lore``, by atrybut pozostawał spójny
        z plikiem na dysku.

        Raises:
            ValueError: gdy nie ustawiono jeszcze ``nazwa_pliku``.
            OSError:    problem z zapisem na dysk.
        """
        self._wymagaj_nazwy()
        skrypty = os.path.join(self.app_dir, SKRYPTY_DIR)
        os.makedirs(skrypty, exist_ok=True)
        sciezka = self._sciezka_ksiegi(self.nazwa_pliku)
        with open(sciezka, "w", encoding="utf-8") as fh:
            fh.write(tresc)
        self.world_lore = tresc
        return sciezka

    def zapisz_streszczenie(self, tresc: str) -> str:
        """Zapisuje Pamięć Długotrwałą do ``skrypty/<nazwa>_streszczenie.txt``."""
        self._wymagaj_nazwy()
        skrypty = os.path.join(self.app_dir, SKRYPTY_DIR)
        os.makedirs(skrypty, exist_ok=True)
        sciezka = self._sciezka_streszczenia(self.nazwa_pliku)
        with open(sciezka, "w", encoding="utf-8") as fh:
            fh.write(tresc)
        self.summary_text = tresc
        return sciezka

    def dopisz_do_pliku_historii(self, content: str, mode: str = "a") -> None:
        """Dopisuje/nadpisuje plik ``skrypty/<nazwa>.txt``.

        Args:
            content: Tekst do zapisania.
            mode:    ``"a"`` (append, domyślnie) lub ``"w"`` (nadpisz).
                     ``"w"`` używane jest przy wstawianiu Prologu – pozwala
                     mieć pewność, że plik zaczyna się czysto, bez artefaktów
                     z poprzednich sesji.

        Nie modyfikuje ``self.full_story`` – to operacja „czystego I/O".
        Do synchronizacji pamięci z dyskiem służy :meth:`dopisz_odpowiedz_ai`.
        """
        self._wymagaj_nazwy()
        skrypty = os.path.join(self.app_dir, SKRYPTY_DIR)
        os.makedirs(skrypty, exist_ok=True)
        sciezka = self._sciezka_historii(self.nazwa_pliku)
        with open(sciezka, mode, encoding="utf-8") as fh:
            fh.write(content)

    def zapisz_tryb_tworczy(self, tryb_idx: int, nazwa: str | None = None) -> None:
        """Zapisuje aktualny tryb twórczy do pliku ``.mode`` (cichy fail).

        Args:
            tryb_idx: 1=Skrypt, 2=Audiobook. Inne wartości (w tym 0=Burza
                      Mózgów) są ignorowane – nie ma sensu zapisywać
                      tymczasowego trybu planowania.
            nazwa:    Opcjonalne nadpisanie nazwy projektu (domyślnie
                      ``self.nazwa_pliku``).
        """
        nazwa = nazwa or self.nazwa_pliku
        if not nazwa or tryb_idx not in (1, 2):
            return
        meta_dir = os.path.join(self.app_dir, RUNTIME_DIR, SKRYPTY_DIR)
        os.makedirs(meta_dir, exist_ok=True)
        sciezka = self._sciezka_mode(nazwa)
        try:
            with open(sciezka, "w", encoding="utf-8") as fh:
                fh.write(str(tryb_idx))
        except Exception:
            # Metadata trybu to quality-of-life, a nie coś, bez czego
            # aplikacja nie działa – milczymy w razie awarii.
            pass

    def wczytaj_tryb_tworczy(self, nazwa: str | None = None) -> int | None:
        """Odczytuje zapisany tryb twórczy z pliku ``.mode``.

        Returns:
            ``1`` lub ``2`` – gdy plik istnieje i zawiera poprawną wartość,
            ``None`` – w każdym innym przypadku (brak pliku, błąd odczytu,
            nie zainstalowana aplikacja w pełnej lokalizacji, itd.).
        """
        nazwa = nazwa or self.nazwa_pliku
        if not nazwa:
            return None
        sciezka = self._sciezka_mode(nazwa)
        if not os.path.exists(sciezka):
            return None
        try:
            with open(sciezka, "r", encoding="utf-8") as fh:
                val = int(fh.read().strip())
            return val if val in (1, 2) else None
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Zarządzanie strukturą (Prolog/Epilog/Rozdział/Akt/Scena)
    # ------------------------------------------------------------------
    # Każda z tych metod wykonuje TRZY operacje atomowo:
    #   1. Dopisuje nagłówek do ``self.full_story``.
    #   2. Dopisuje ten sam nagłówek do pliku na dysku.
    #   3. (poza Prologiem/Epilogiem) Inkrementuje odpowiedni licznik.
    # Zwracają tekst wstawionego nagłówka – GUI używa go do komunikatu
    # „Wstawiono: …".
    # ------------------------------------------------------------------

    def wstaw_prolog(self) -> str:
        """Wstawia ``Prolog`` na początek historii (nadpisując plik)."""
        self._wymagaj_nazwy()
        header = "Prolog\n\n"
        self.full_story += header
        # Tryb "w" – Prolog zaczyna historię od zera. Gdyby plik zawierał
        # resztki z poprzedniej sesji (test zmian, zepsuty zapis), byłyby
        # teraz niszczone. Tak samo robił oryginalny kod w gui_rezyser.
        self.dopisz_do_pliku_historii(header, mode="w")
        return "Prolog"

    def wstaw_epilog(self) -> str:
        """Wstawia ``Epilog`` na koniec historii. Po nim dalszy zapis jest blokowany."""
        self._wymagaj_nazwy()
        header = "\n\nEpilog\n\n"
        self.full_story += header
        self.dopisz_do_pliku_historii(header)
        return "Epilog"

    def wstaw_rozdzial(self) -> str:
        """Wstawia ``Rozdział N`` (Audiobook) i inkrementuje licznik."""
        self._wymagaj_nazwy()
        naglowek = f"Rozdział {self.chapter_counter}"
        content = f"\n\n{naglowek}\n\n"
        self.full_story += content
        self.chapter_counter += 1
        self.dopisz_do_pliku_historii(content)
        return naglowek

    def wstaw_akt(self) -> tuple[str, str]:
        """Wstawia ``Akt N`` + automatycznie ``Scena 1`` (tryb Skrypt).

        Inkrementuje licznik aktów i ustawia licznik scen na 2 (bo Scena 1
        właśnie została wstawiona). Zwraca krotkę ``(akt, scena)``
        – dla GUI do komunikatu zwrotnego.
        """
        self._wymagaj_nazwy()
        akt = f"Akt {self.akt_counter}"
        scena = "Scena 1"
        content = f"\n\n{akt}\n\n{scena}\n\n"
        self.full_story += content
        self.akt_counter += 1
        self.scena_counter = 2
        self.dopisz_do_pliku_historii(content)
        return akt, scena

    def wstaw_scena(self) -> str:
        """Wstawia kolejną ``Scena N`` w bieżącym Akcie."""
        self._wymagaj_nazwy()
        scena = f"Scena {self.scena_counter}"
        content = f"\n\n{scena}\n\n"
        self.full_story += content
        self.scena_counter += 1
        self.dopisz_do_pliku_historii(content)
        return scena

    # ------------------------------------------------------------------
    # Mutacje pamięci (bez bezpośredniego zapisu na dysk)
    # ------------------------------------------------------------------
    def dopisz_odpowiedz_ai(self, tekst: str) -> None:
        """Dopisuje odpowiedź AI do ``full_story`` + pliku. Używane po generacji.

        Składa to, co GUI robiło w dwóch krokach (dopisz do full_story +
        wywołaj self._dopisz_do_pliku). Ustawia także ``last_response``
        dla celów diagnostycznych.
        """
        self._wymagaj_nazwy()
        if self.full_story:
            self.full_story += "\n\n" + tekst
        else:
            self.full_story = tekst
        self.last_response = tekst
        # Oddzielny blok akapitem, jak w oryginale.
        self.dopisz_do_pliku_historii(tekst + "\n\n")

    def wyczysc_biezaca(self) -> None:
        """Czyści tylko ``full_story`` i ``last_response``. Reszta zostaje.

        Scenariusz użycia: projekt-audiobook jest już długi, wygenerowano
        streszczenie, chcemy kontynuować pisanie operując na streszczeniu
        jako kontekście – a pamięć bieżąca ma być czysta, by zmieściła
        się w oknie kontekstowym modelu.
        """
        self.full_story = ""
        self.last_response = ""
        # NIE zmieniamy: chapter_counter, akt_counter, scena_counter,
        # nazwa_pliku, world_lore, summary_text – bo projekt trwa dalej.

    def twardy_reset(self) -> None:
        """Całkowicie zapomina o projekcie. Pliki na dysku zostają nietknięte."""
        self.full_story = ""
        self.summary_text = ""
        self.world_lore = ""
        self.chapter_counter = 1
        self.akt_counter = 1
        self.scena_counter = 1
        self.nazwa_pliku = ""
        self.last_response = ""

    # ------------------------------------------------------------------
    # Właściwości pochodne (używane przez _refresh_ui_state w GUI)
    # ------------------------------------------------------------------

    @property
    def pamiec_zajeta(self) -> bool:
        """True gdy w RAM jest już historia lub streszczenie (blokuje zmianę projektu)."""
        return bool(self.full_story.strip() or self.summary_text.strip())

    @property
    def ma_prolog(self) -> bool:
        """True gdy pamięć zawiera nagłówek Prolog (gdziekolwiek)."""
        return bool(re.search(r"(?i)\bprolog\b", self.full_story))

    @property
    def ma_epilog(self) -> bool:
        """True gdy pamięć zawiera nagłówek Epilog."""
        return bool(re.search(r"(?i)\bepilog\b", self.full_story))

    @property
    def epilog_ma_tresc(self) -> bool:
        """True gdy po Epilogu jest już jakaś treść (historia zamknięta).

        Używane przez GUI do blokady dalszego generowania fragmentów
        po zakończeniu historii.
        """
        m = re.search(r"(?i)\bepilog\b", self.full_story)
        if m is None:
            return False
        return len(self.full_story[m.end():].strip()) > 0

    @property
    def ostatnia_linia_to_naglowek(self) -> bool:
        """True gdy ostatnia niepusta linia jest czystym nagłówkiem (bez treści).

        Blokuje wstawianie kolejnego nagłówka – np. Akt po Akcie bez
        żadnej sceny między nimi, albo Scena po Scena. W GUI steruje
        ``Enable`` przycisków Rozdział / Akt / Scena / Epilog.
        """
        for linia in reversed(self.full_story.splitlines()):
            if linia.strip():
                return bool(re.match(
                    r"(?i)^(rozdzia[łl]\s+\d+|akt\s+\d+|scena\s+\d+|prolog|epilog)\s*$",
                    linia.strip(),
                ))
        return False

    # ------------------------------------------------------------------
    # Status pamięci modelu
    # ------------------------------------------------------------------
    def status_pamieci_modelu(self) -> StatusPamieciModelu:
        """Zwraca gotowy do wyświetlenia status pamięci modelu.

        GUI używa tego do aktualizacji ``wx.Gauge`` + pola statusu.
        Kolor (zielony/pomarańczowy/czerwony) GUI wybiera na podstawie
        pola ``poziom``.
        """
        total = len(self.full_story)

        if total == 0:
            return StatusPamieciModelu(
                procent=0,
                komunikat="🟢 Pamięć czysta. Maszyna gotowa na nową historię.",
                poziom=POZIOM_CZYSTA,
            )

        if total >= PROG_ALARM:
            pct = min(int(total / LIMIT_PAMIECI * 100), 100)
            return StatusPamieciModelu(
                procent=pct,
                komunikat=(
                    f"🚨 KRYTYCZNE PRZEŁADOWANIE: Zużyto {total} z {LIMIT_PAMIECI} znaków.\n"
                    "JAK KONTYNUOWAĆ: W Burzy Mózgów wpisz 'streszczenie', kliknij "
                    "'Zapisz Streszczenie', potem 'Wyczyść bieżącą (zostaw Streszczenie)'."
                ),
                poziom=POZIOM_ALARM,
            )

        if total >= PROG_OSTRZEZENIE:
            return StatusPamieciModelu(
                procent=int(total / LIMIT_PAMIECI * 100),
                komunikat=(
                    f"⚠️ STAN OSTRZEGAWCZY: Zużyto {total} z {LIMIT_PAMIECI} znaków. "
                    "Pamięć się zapełnia – wkrótce konieczne będzie wygenerowanie streszczenia."
                ),
                poziom=POZIOM_OSTRZEZENIE,
            )

        return StatusPamieciModelu(
            procent=int(total / LIMIT_PAMIECI * 100),
            komunikat=f"🟢 Zużycie pamięci: {total} / {LIMIT_PAMIECI} znaków. Bezpieczny bufor.",
            poziom=POZIOM_OK,
        )

    # ------------------------------------------------------------------
    # Snapshot dla wątku tła
    # ------------------------------------------------------------------
    def snapshot(self) -> SnapshotProjektu:
        """Zwraca niezmienny obraz stanu – do przekazania do wątku AI.

        Wątek tła NIE powinien widzieć samej instancji :class:`ProjektRezysera`,
        bo GUI może w międzyczasie ją zmienić (np. użytkownik kliknął
        „Wyczyść bieżącą"). Snapshot jest tanim `dataclass` i zamraża
        stan w momencie wywołania.
        """
        return SnapshotProjektu(
            nazwa=self.nazwa_pliku,
            full_story=self.full_story,
            summary_text=self.summary_text,
            world_lore=self.world_lore,
        )

    # ------------------------------------------------------------------
    # Wewnętrzne: walidacja obecności nazwy projektu
    # ------------------------------------------------------------------
    def _wymagaj_nazwy(self) -> None:
        """Rzuca ``ValueError`` gdy operacja I/O wywołana bez nazwy projektu."""
        if not self.nazwa_pliku:
            raise ValueError(
                "ProjektRezysera: operacja wymaga ustawionej nazwa_pliku "
                "(ustaw self.nazwa_pliku lub najpierw wywołaj wczytaj())."
            )
