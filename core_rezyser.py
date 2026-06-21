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
    proj.zapisz_tryb_tworczy("audiobook", zapis_do_pliku=True)  # stabilne id trybu

    # Struktura – mutuje pamięć i plik na dysku
    proj.wstaw_prolog()
    akt, scena1 = proj.wstaw_akt()
    proj.wstaw_rozdzial()

    # Status pamięci modelu (wskaźnik „czy pora na streszczenie")
    status = proj.status_pamieci_modelu()     # StatusPamieciModelu
    print(status.procent, status.poziom, status.tokeny)

    # Mutacje
    proj.twardy_reset()          # wyzeruj wszystko (dysk nietknięty)

    # Snapshot dla wątku tła AI (odcina go od zmian w wątku GUI)
    snap = proj.snapshot()

Silnik fonetyczny udostępniany jest jako wolna funkcja
:func:`zastosuj_akcenty_uniwersalne` – dostęp do niej mają zarówno
``rezyser_ai.py`` (po wygenerowaniu odpowiedzi), jak i ewentualne
testy / narzędzia offline.
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Any, Callable

import core_tokeny as ct
import przepisy_rezysera as pr
import sciezki

# Silnik fonetyczny trybu Reżysera. Od v17.5 akcenty są dyspatchowane
# DYNAMICZNIE: nazwa akcentu z Księgi Świata jest wprost ``id`` wariantu YAML,
# a ``zastosuj_reguly_fonetyczne`` ładuje reguły z
# ``dictionaries/<jezyk>/akcenty/`` w locie — dokładnie jak tryb Poligloty.
# Dzięki temu dorzucenie nowego pliku akcentu OBOK exe działa bez regeneracji
# kodu; zniknął generator ``odswiez_rezysera.py`` i statyczne wrappery
# ``akcent_*`` (martwy whitelist niemożliwy do odświeżenia w paczce frozen).
# Patrz [[reguly_architektury]].
#   ``slowa_akcentu`` – słowa-wyzwalacze parsera akcentów (Księga Świata),
#   ``wariant_po_id`` – sprawdza, czy istnieje YAML akcentu o danej nazwie.
from core_poliglota import (
    TRYB_REZYSER,
    slowa_akcentu,
    wariant_po_id,
    zastosuj_reguly_fonetyczne,
)

# Wzorce nagłówków dla wszystkich 9 obsługiwanych języków aplikacji
# (pl en de es fr it fi is ru). Używane przez parsing liczników, detekcję
# ostatniej linii oraz konwerter. v17.9: domknięty dług 6→9 — do regexów
# dopisane de (Kapitel/Szene), es (Capítulo/Acto/Escena/Prólogo/Epílogo) i fr
# (Chapitre/Acte/Scène/Épilogue), których wcześniej brakowało (źródło prawdy:
# `rezyser.naglowek_*` w `dictionaries/<kod>/gui/ui.yaml`). `(?i)` + Unicode
# obejmują warianty z diakrytykami (ó/é/ä/þ) i cyrylicę; `\s+(\d+)` po członie
# rozróżnia np. „Acto 1" (es) od „Act 1" (en) przez backtracking alternatywy.
_WZORZEC_ROZDZIAL = (
    r"(?i)\b(?:rozdzia[łl]|chapter|chapitre|kapitel|capitolo|capítulo|luku|kafli|глава)\s+(\d+)"
)
_WZORZEC_AKT = (
    r"(?i)\b(?:akt|acte|acto|atto|act|näytös|þáttur|акт)\s+(\d+)"
)
_WZORZEC_SCENA = (
    r"(?i)\b(?:scena|scène|scene|szene|escena|kohtaus|atriði|сцена)\s+(\d+)"
)
_WZORZEC_NAGLOWEK_LINIA = (
    r"(?i)^(?:"
    r"(?:rozdzia[łl]|chapter|chapitre|kapitel|capitolo|capítulo|luku|kafli|глава)\s+\d+"
    r"|(?:akt|acte|acto|atto|act|näytös|þáttur|акт)\s+\d+"
    r"|(?:scena|scène|scene|szene|escena|kohtaus|atriði|сцена)\s+\d+"
    r"|prolog(?:ue|i|o)?|prólogo|formáli|пролог"
    r"|epilog(?:ue|i|o)?|epílogo|épilogue|eftirorð|эпилог"
    r")\s*$"
)


# =============================================================================
# Stałe konfiguracyjne
# =============================================================================

# Foldery projektu (relatywne względem ``app_dir``)
SKRYPTY_DIR = "skrypty"          # pliki .txt / .md / _streszczenie.txt
RUNTIME_DIR = "runtime"          # ukryta metadata – tam leżą .mode


def _dev_log_runtime(sciezka: str) -> None:
    """Loguje zapis do `runtime/` WYŁĄCZNIE na konsolę dewelopera.

    `runtime/` jest folderem systemowym, niewidocznym dla end-usera — w GUI
    komunikaty NIGDY nie mówią o nim wprost (używają nazwy projektu, jak
    Poliglota/Opowieści). Jedyne dozwolone miejsce na wzmiankę o `runtime` to
    konsola dewelopera: w paczce release aplikacja chodzi bez konsoli
    (``sys.stdout`` bywa None/zamknięty), więc print jest strażowany i nigdy
    nie wywróci aplikacji końcowego użytkownika.
    """
    try:
        if sys.stdout is not None:
            print(f"[runtime] zapis: {sciezka}")
    except Exception:  # noqa: BLE001 — log dev nie może nigdy ubić apki
        pass


# =============================================================================
# Globalny cache ISO języka treści (v17.11.1)
# =============================================================================
# Mapowanie prozaicznego `jezyk_odpowiedzi` ("fińsku") → kod ISO ("fi"),
# wyliczonego mikrorequestem LLM (`rezyser_ai.rozwiaz_kod_jezyka`). Cache jest
# GLOBALNY (nie per-projekt): „fińsku → fi" nie zależy od konkretnego projektu,
# więc trzymamy go raz dla całej aplikacji w runtime/ (root, obok metadanych
# projektów), by nie wołać API przy każdym wyborze przepisu. Plik gitignorowany
# (cały runtime/), niewidoczny dla end-usera jak reszta metadanych.
_PLIK_CACHE_ISO = "jezyki_iso.json"


def _sciezka_cache_iso() -> str:
    return os.path.join(sciezki.KATALOG_BAZOWY_STR, RUNTIME_DIR, _PLIK_CACHE_ISO)


def wczytaj_cache_iso() -> dict[str, str]:
    """Czyta cache `jezyk_odpowiedzi → ISO`. Brak pliku / uszkodzony → ``{}``.

    Nigdy nie rzuca — cache to optymalizacja, a nie źródło prawdy (źródłem jest
    mikrorequest LLM). Klucze trzymamy znormalizowane (lower) po stronie zapisu.
    """
    try:
        with open(_sciezka_cache_iso(), encoding="utf-8") as fh:
            dane = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError):
        return {}
    if not isinstance(dane, dict):
        return {}
    return {str(k): str(v) for k, v in dane.items()}


def zapisz_cache_iso(mapa: dict[str, str]) -> None:
    """Zapis atomowy (tmp + ``os.replace``) cache'u ISO; tworzy runtime/ w razie
    potrzeby. Błąd I/O połykamy — brak zapisu cache'u nie może ubić generacji
    (następnym razem po prostu zapytamy LLM jeszcze raz)."""
    sciezka = _sciezka_cache_iso()
    try:
        os.makedirs(os.path.dirname(sciezka), exist_ok=True)
        tmp = sciezka + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(mapa, fh, ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(tmp, sciezka)
        _dev_log_runtime(sciezka)
    except OSError:  # noqa: BLE001 — cache best-effort
        pass


# Pamięć modelu — od v15.1 wspólne ze ścieżką Opowieści przez `core_tokeny`.
# Liczymy faktyczne tokeny payloadu (tiktoken), nie znaki — gpt-4o ma 128k
# okno, a heurystyka „~4 znaki/token" była gruba (zwłaszcza dla diakrytyków
# słowiańskich i azjatyckich), oraz mierzyła tylko `full_story` z pominięciem
# `summary_text` + `world_lore`, które również lecą w payloadzie do API.
OKNO_KONTEKSTU_MAX = ct.OKNO_KONTEKSTU_MAX
PROG_OSTRZEZENIE   = ct.PROG_OSTRZEZENIE   # 70% — ostrzeżenie + sufiks "alarm"
PROG_ALARM         = ct.PROG_ALARM         # 90% — krytyczne przeładowanie

# Poziomy statusu pamięci modelu – czytelne dla GUI (kolor + ikonka).
POZIOM_CZYSTA      = ct.POZIOM_CZYSTA
POZIOM_OK          = ct.POZIOM_OK
POZIOM_OSTRZEZENIE = ct.POZIOM_OSTRZEZENIE
POZIOM_ALARM       = ct.POZIOM_ALARM

# v15.5 — rekoncyliacja narracji z dysku (po ręcznej edycji `.txt`, np. ucięciu
# złamanego anti-closure). Gdy istnieje streszczenie i CAŁY tekst przekracza
# próg ostrzegawczy, `full_story` odtwarzamy tylko z KOŃCÓWKI `.txt` — od
# ostatniego użytecznego nagłówka struktury — żeby nie zduplikować starej
# części już skompresowanej w `summary_text` (re-inflacja kontekstu).
#   MIN_TRESC_PO_NAGLOWKU — minimalna liczba znaków nie-białych PO nagłówku,
#       by uznać go za „nagłówek z treścią". Guard przed sytuacją: reżyser
#       wstawił sam nagłówek + didaskalia/notkę bez właściwej sceny → cofamy
#       się do poprzedniego nagłówka z istotną treścią.
#   MAX_TAIL_ZN — twardy limit długości przywracanej końcówki (snap do akapitu)
#       gdy brak użytecznego markera lub sekcja od markera jest gigantyczna.
MIN_TRESC_PO_NAGLOWKU = 400
MAX_TAIL_ZN           = 8000

# Polskie znaki → ASCII (do normalizacji nazw akcentów w Księdze Świata).
_PL_TO_ASCII = {
    "ą": "a", "ę": "e", "ł": "l", "ó": "o",
    "ś": "s", "ć": "c", "ń": "n", "ż": "z", "ź": "z",
}

# Audio-tagi ElevenLabs v3 (od v16.1). Słowa w nawiasach kwadratowych, które
# model v3 interpretuje jako dyrektywy aktorskie/dźwiękowe — NIE jako mówcę.
# `zastosuj_akcenty_uniwersalne` pomija je przy detekcji mówcy (inaczej tag
# typu [whispers] zresetowałby atrybucję akcentu). Tagi są ANGIELSKIE i wspólne
# dla wszystkich języków projektu (v3 honoruje je niezależnie od języka mowy).
#
# To NIE jest pełna lista (zestaw v3 jest otwarty i zależny od głosu/kontekstu)
# — to lista DOMYŚLNIE DOZWOLONA, którą prompt trybu Skrypt (E3,
# `dictionaries/<kod>/rezyser/tryb_skrypt.yaml`) narzuca modelowi. Tag spoza
# zbioru nie wywala niczego — most jest na to odporny, a tu degraduje się
# najwyżej akcent jednego fragmentu (nie krytyczne). Porównanie po pierwszym
# tokenie tagu, małymi literami (tak jak parser wyłuskuje mówcę).
AUDIO_TAGS: frozenset[str] = frozenset({
    # — emocje / ton (szeroka paleta; prompt Skryptu zaleca głównie tę grupę) —
    "happy", "joyful", "ecstatic", "cheerful", "playful", "amused",
    "sad", "sorrowful", "melancholic", "heartbroken", "wistful", "bitter",
    "angry", "furious", "indignant", "annoyed", "frustrated", "stern",
    "excited", "enthusiastic", "eager", "hopeful", "proud", "confident",
    "nervous", "anxious", "fearful", "terrified", "panicked", "desperate",
    "sarcastic", "mocking", "contemptuous", "dismissive", "scornful",
    "curious", "surprised", "confused", "suspicious", "thoughtful",
    "disappointed", "resigned", "weary", "tired", "bored",
    "ashamed", "guilty", "jealous", "disgusted",
    "calm", "gentle", "tender", "warmly", "reassuring", "sincere", "solemn",
    "coldly", "hesitant", "shy", "flirtatious", "pleading", "relieved",
    "mischievously", "dramatic", "urgent", "defensive", "awe",
    # — sposób podania —
    "whispers", "whispering", "shouts", "shouting", "yelling", "mutters",
    "murmurs", "stammers", "stuttering", "sings", "singing", "humming",
    "breathless", "trembling", "voice breaking", "through gritted teeth",
    "under breath",
    # — niewerbalne (wokalne) —
    "laughs", "laughing", "giggles", "chuckles", "snickers", "scoffs",
    "sighs", "exhales", "inhales", "gasps", "groans", "grunts", "yawns",
    "sniffs", "sniffles", "clears throat", "coughs", "gulps", "swallows",
    "snorts", "sobs", "crying", "screams", "pauses", "short pause",
    "long pause", "breathes",
    # — efekty dźwiękowe (passthrough; prompt teatru ich NIE zaleca, „zero SFX") —
    "gunshot", "applause", "clapping", "explosion", "footsteps", "thunder",
    "wind", "door slam", "knocking",
})


# =============================================================================
# Rekoncyliacja narracji z dysku (v15.5) — wolne funkcje, czysto-Pythonowe,
# w pełni testowalne bez I/O i bez wxPython.
# =============================================================================

def _znajdz_naglowki(tekst: str) -> list[tuple[int, str]]:
    """Zwraca listę ``(offset_startu_linii, tekst_nagłówka)`` dla linii będących
    czystymi nagłówkami struktury (Rozdział/Akt/Scena/Prolog/Epilog — wszystkie
    obsługiwane języki, regex :data:`_WZORZEC_NAGLOWEK_LINIA`).

    ``offset`` to indeks znakowy początku linii nagłówka w ``tekst`` — pozwala
    pociąć ``tekst[offset:]`` tak, by przywrócona końcówka zaczynała się
    DOKŁADNIE od nagłówka (AI dostaje „Rozdział 7\\n<treść>").
    """
    wynik: list[tuple[int, str]] = []
    offset = 0
    for linia in tekst.splitlines(keepends=True):
        rdzen = linia.strip()
        if rdzen and re.match(_WZORZEC_NAGLOWEK_LINIA, rdzen):
            wynik.append((offset, rdzen))
        offset += len(linia)
    return wynik


def _ma_istotna_tresc(tekst: str, offset_naglowka: int) -> bool:
    """True, gdy PO linii nagłówka (od ``offset_naglowka``) jest co najmniej
    :data:`MIN_TRESC_PO_NAGLOWKU` znaków nie-białych.

    Guard przed snapowaniem do „pustego" nagłówka albo nagłówka, po którym
    reżyser wpisał ręcznie tylko didaskalia/krótką notkę — wtedy snap dałby AI
    nagłówek bez właściwej sceny.
    """
    po = tekst[offset_naglowka:]
    nl = po.find("\n")
    reszta = po[nl + 1:] if nl != -1 else ""
    niebiale = sum(1 for znak in reszta if not znak.isspace())
    return niebiale >= MIN_TRESC_PO_NAGLOWKU


def _ostatni_uzyteczny_naglowek(
    tekst: str, preferowany: str | None = None,
) -> int | None:
    """Zwraca offset początku końcówki do przywrócenia — od ostatniego nagłówka
    z istotną treścią. ``None`` gdy w tekście nie ma żadnego użytecznego nagłówka.

    Kolejność wyboru:
      1. Jeśli ``preferowany`` (z meta-markera streszczenia) występuje w tekście
         i ma istotną treść — używamy jego OSTATNIEGO wystąpienia.
      2. W przeciwnym razie skanujemy nagłówki od końca i bierzemy pierwszy,
         który ma istotną treść (guard cofa nas przed pusty/sam-didaskalia
         nagłówek do poprzedniego pełnego).
    """
    naglowki = _znajdz_naglowki(tekst)
    if not naglowki:
        return None
    if preferowany:
        for offset, txt in reversed(naglowki):
            if txt == preferowany and _ma_istotna_tresc(tekst, offset):
                return offset
    for offset, _txt in reversed(naglowki):
        if _ma_istotna_tresc(tekst, offset):
            return offset
    return None


def _koncowka_po_znakach(tekst: str, max_zn: int = MAX_TAIL_ZN) -> str:
    """Ostatnie ~``max_zn`` znaków ``tekst``, snapnięte do granicy akapitu, by
    przywrócona końcówka nie zaczynała się w środku zdania.

    Zwraca cały ``tekst`` jeśli mieści się pod limitem. Inaczej tnie okno
    końcowe i przeskakuje do pierwszego ``\\n\\n`` w jego wczesnej części;
    brak akapitu → ``lstrip`` okna.
    """
    if len(tekst) <= max_zn:
        return tekst
    okno = tekst[-max_zn:]
    idx = okno.find("\n\n")
    if idx != -1 and idx < max_zn // 2:
        return okno[idx + 2:].lstrip()
    return okno.lstrip()


def _rozbij_naglowek(naglowek: str) -> tuple[str, int | None]:
    """Rozbija tekst nagłówka na ``(typ, numer)``.

    ``typ`` ∈ {rozdzial, akt, scena, prolog, epilog, inny}; ``numer`` to int
    dla rozdziału/aktu/sceny, ``None`` dla prologu/epilogu/innego.
    """
    for typ, wzorzec in (
        ("rozdzial", _WZORZEC_ROZDZIAL),
        ("akt",      _WZORZEC_AKT),
        ("scena",    _WZORZEC_SCENA),
    ):
        m = re.search(wzorzec, naglowek)
        if m:
            return typ, int(m.group(1))
    low = naglowek.lower()
    # v17.9: warianty z diakrytykami (es „prólogo"/„epílogo", fr „épilogue")
    # nie zawieraja czystego „prolog"/„epilog" jako podlancucha — dopisane jawnie.
    if any(s in low for s in ("prolog", "prólogo", "formáli", "пролог")):
        return "prolog", None
    if any(s in low for s in ("epilog", "epílogo", "épilogue", "eftirorð", "эпилог")):
        return "epilog", None
    return "inny", None


def policz_naglowki_per_jezyk(
    content: str, mapa_slow: dict[str, set[str]],
) -> dict[str, int]:
    """Zlicza linie-nagłówki ``content`` per język wg ``mapa_slow``.

    v17.9 (Obszar 3b, ostrzeżenie wczytania): heurystyczna detekcja języka
    istniejącej treści projektu. ``mapa_slow`` = ``{kod_jezyka: {słowa-nagłówki
    małymi literami}}`` budowane przez GUI z ``t("rezyser.naglowek_*",
    jezyk_override=<kod>)`` — pokrywa WSZYSTKIE zainstalowane języki (w
    odróżnieniu od 6-językowego ``_WZORZEC_NAGLOWEK_LINIA``, który nie zna
    np. niemieckiego „Kapitel").

    Liczy tylko linie wyglądające na czysty nagłówek: pojedyncze słowo +
    opcjonalny numer (np. „Akt 1", „Prolog") — nie prozę zaczynającą się od
    słowa-nagłówka. Słowo dzielone między językami (np. „Akt" pl i de) zlicza
    się dla OBU — wołający interpretuje (brak trafień w języku przepisu przy
    trafieniach w innym = sygnał rozjazdu).

    Zwraca ``{kod_jezyka: liczba_trafień}`` dla każdego klucza ``mapa_slow``.
    """
    counts: dict[str, int] = {lang: 0 for lang in mapa_slow}
    for linia in content.splitlines():
        rdzen = linia.strip().lower()
        if not rdzen:
            continue
        m = re.match(r"(\w+)", rdzen, re.UNICODE)
        if not m:
            continue
        first = m.group(1)
        # tylko czysty nagłówek: słowo + opcjonalny numer, nic więcej.
        if not re.fullmatch(rf"{re.escape(first)}(\s+\d+)?", rdzen):
            continue
        for lang, slowa in mapa_slow.items():
            if first in slowa:
                counts[lang] += 1
    return counts


# =============================================================================
# Wybór punktu odniesienia pamięci roboczej (v17.6)
# =============================================================================
# Gdy historia jest za długa, by zmieścić ją w całości, pamięć robocza AI
# musi zacząć się od któregoś nagłówka struktury (wcześniejsze wydarzenia
# reprezentuje Streszczenie Długotrwałe). Do v17.5 ten punkt wybierał silnik
# automatycznie (`_ostatni_uzyteczny_naglowek`). Od v17.6 GUI może go wybrać
# interaktywnie — dla nietechnicznego reżysera — a `wyliczy_markery` dostarcza
# czytelną, zależną od trybu listę dostępnych punktów (rozdziały dla Audiobooka;
# akty z zagnieżdżonymi scenami dla Skryptu).

@dataclass
class MarkerStruktury:
    """Jeden wybieralny punkt odniesienia (nagłówek struktury) + jego pozycja.

    Attributes:
        offset:           indeks znakowy początku linii nagłówka w `.txt`
                          (do pocięcia ``content[offset:]``).
        etykieta:         czytelny tekst nagłówka (np. ``"Rozdział 7"``).
        typ:              ``"rozdzial"`` | ``"akt"`` | ``"scena"`` |
                          ``"prolog"`` | ``"epilog"`` | ``"inny"``.
        numer:            numer struktury (int) lub ``None`` (prolog/epilog/inny).
        ma_istotna_tresc: czy PO nagłówku jest ≥ ``MIN_TRESC_PO_NAGLOWKU`` znaków
                          (guard przed snapem do pustego nagłówka).
        sceny:            podrzędne markery scen — wypełnione TYLKO dla aktów
                          (tryb Skrypt); puste dla płaskiej listy Audiobooka.
    """

    offset: int
    etykieta: str
    typ: str
    numer: int | None
    ma_istotna_tresc: bool
    sceny: list["MarkerStruktury"] = field(default_factory=list)


def wyliczy_markery(content: str, struktura: str) -> list[MarkerStruktury]:
    """Buduje listę wybieralnych punktów odniesienia z treści `.txt`.

    Args:
        content:   pełna treść narracji (`skrypty/<nazwa>.txt`).
        struktura: sposób segmentacji z `PrzepisRezysera.struktura`:
                   ``"akty_sceny"`` = Akty z zagnieżdżonymi Scenami (Skrypt),
                   pozostałe (``"rozdzialy"``/``"brak"``) = płaska lista
                   wszystkich nagłówków (Audiobook i tryby bez struktury).

    Returns:
        Lista top-levelowych :class:`MarkerStruktury`. Dla ``"akty_sceny"`` akty
        niosą swoje sceny w ``sceny``; prolog/epilog oraz sceny przed pierwszym
        aktem trafiają jako top-level (gracz wciąż może od nich wystartować
        pamięć). Płaska lista zawiera wszystkie nagłówki w kolejności.
    """
    surowe = [
        (off, txt, *_rozbij_naglowek(txt))
        for off, txt in _znajdz_naglowki(content)
    ]

    def _mk(off: int, txt: str, typ: str, numer: int | None) -> MarkerStruktury:
        return MarkerStruktury(
            offset=off, etykieta=txt, typ=typ, numer=numer,
            ma_istotna_tresc=_ma_istotna_tresc(content, off),
        )

    # Skrypt (akty_sceny): zagnieżdżamy sceny pod ostatnim napotkanym aktem.
    if struktura == "akty_sceny":
        wynik: list[MarkerStruktury] = []
        biezacy_akt: MarkerStruktury | None = None
        for off, txt, typ, numer in surowe:
            if typ == "akt":
                biezacy_akt = _mk(off, txt, typ, numer)
                wynik.append(biezacy_akt)
            elif typ == "scena" and biezacy_akt is not None:
                biezacy_akt.sceny.append(_mk(off, txt, typ, numer))
            else:
                # Prolog/Epilog/inny LUB scena przed pierwszym aktem → top-level.
                wynik.append(_mk(off, txt, typ, numer))
        return wynik

    # Audiobook (rozdzialy) / tryb bez struktury: płaska lista nagłówków.
    return [_mk(off, txt, typ, numer) for off, txt, typ, numer in surowe]


# =============================================================================
# Silnik fonetyczny (dawna RezyserPanel.zastosuj_akcenty_uniwersalne)
# =============================================================================

def _usun_polskie(nazwa: str) -> str:
    """Normalizuje nazwę akcentu: 'francuski' OK, 'łotewski' → 'lotewski'."""
    for k, v in _PL_TO_ASCII.items():
        nazwa = nazwa.replace(k, v)
    return nazwa.strip()


def zbuduj_mape_akcentow(lore_text: str, jezyk_projektu: str = "pl") -> dict[str, dict]:
    """Parsuje Księgę Świata → ``{nazwa_postaci_lower: {"nazwa", "reguly"}}``.

    ``nazwa`` to rozpoznana nazwa akcentu (np. ``"fiński"``) albo ``None``;
    ``reguly`` to lista par ad-hoc ``[("w","v"), …]`` z zapisów typu
    ``'w' na 'v'``. Postać bez żadnej definicji akcentu nie trafia do mapy.

    Wyłuskane z :func:`zastosuj_akcenty_uniwersalne` w v16.1, bo korzysta z tego
    również generator wersji dla czytników ekranu (``core_screen_reader``) —
    potrzebuje wiedzieć, którzy mówcy mają akcent (i jaki), by owinąć ich kwestie
    w ``<span lang="…">``. Patrz [[reguly_architektury]].
    """
    slowa = slowa_akcentu(jezyk_projektu)
    alt_slow = "|".join(re.escape(s) for s in slowa)
    wzorzec_akcentu = re.compile(
        rf"(?:{alt_slow})\s+(\w+)|(\w+)\s+(?:{alt_slow})",
        re.UNICODE,
    )
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
    return akcenty_map


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
    # ── 1. Mapa postaci → akcent z Księgi Świata ──
    # Wyłuskane do :func:`zbuduj_mape_akcentow` (v16.1), bo z tej samej mapy
    # korzysta generator wersji dla czytników ekranu (core_screen_reader).
    akcenty_map = zbuduj_mape_akcentow(lore_text, jezyk_projektu)

    if not akcenty_map:
        return tekst

    # ── 2. Podział skryptu po tagach i aplikacja akcentów ──
    fragmenty = re.split(r"(\[[^\]]+\])", tekst)
    nowe_fragmenty: list[str] = []
    current_speaker: str | None = None

    for frag in fragmenty:
        if frag.startswith("[") and frag.endswith("]"):
            nowe_fragmenty.append(frag)
            m = re.match(r"^\[([^:\]\-]+)", frag)
            nazwa_w_tagu = m.group(1).strip().lower() if m else None
            # v16.1: audio-tagi ElevenLabs v3 ([whispers], [sighs]…) mają tę samą
            # składnię co tag mówcy, ale są wplecione w treść kwestii. NIE wolno
            # ich brać za nowego mówcę — zresetowałyby atrybucję akcentu (dialog
            # po [whispers] straciłby akcent postaci). Zostają passthrough
            # (dopisane wyżej), a `current_speaker` się nie zmienia. Most
            # (`core_elevenlabs`) jest na to odporny inaczej — parsuje liniowo,
            # więc audio-tag w group(2) nigdy nie jest re-skanowany.
            if nazwa_w_tagu in AUDIO_TAGS:
                continue
            current_speaker = nazwa_w_tagu
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
                        # Dynamiczny dispatch (v17.5): akcent jest „znany", gdy
                        # istnieje jego YAML (kategoria=='akcent') w języku
                        # projektu. Brak pliku → spadamy do reguł ad-hoc niżej,
                        # zamiast — jak dawny statyczny whitelist — oznaczać
                        # fragment jako zmodyfikowany mimo braku reguł fonetycznych.
                        cfg_akc = wariant_po_id(TRYB_REZYSER, jezyk_projektu, znorm)
                        if cfg_akc and cfg_akc.get("kategoria") == "akcent":
                            dialog = zastosuj_reguly_fonetyczne(
                                dialog, znorm, jezyk_projektu
                            )
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
    """Rezultat :meth:`ProjektRezysera.wczytaj` – co i w jakiej ilości trafiło do pamięci.

    Od v17.6 osadza :class:`WynikRekoncyliacji` (``rekoncyliacja``) — wczytanie
    zawsze przepuszcza narrację przez rekoncyliację, a GUI potrzebuje jej trybu
    (calosc/snap/koncowka), użytego nagłówka i flag, by pokazać punkt odniesienia
    pamięci roboczej. Pole jest opcjonalne dla zgodności (None gdy nieustawione).
    """

    nazwa: str
    czy_historia: bool = False
    czy_streszczenie: bool = False
    czy_ksiega_swiata: bool = False
    liczba_znakow: int = 0
    saved_mode: str | None = None   # stabilne `id` trybu z `.mode` (np. "audiobook"); None=brak
    rekoncyliacja: "WynikRekoncyliacji | None" = None


@dataclass
class WynikRekoncyliacji:
    """Rezultat rekoncyliacji narracji z dysku (v15.5; rdzeń
    :meth:`ProjektRezysera._zastosuj_rekoncyliacje`).

    Attributes:
        tryb:                   "calosc"   – cały `.txt` zmieścił się pod progiem,
                                              streszczenie skasowane (D1);
                                "snap"     – długa historia + streszczenie,
                                              przywrócono końcówkę od nagłówka;
                                "koncowka" – brak/anulowano marker LUB wybrana
                                              sekcja za długa → ostatnie
                                              MAX_TAIL_ZN znaków (fallback znakowy).
        skasowano_streszczenie: czy usunięto `_streszczenie.txt` + meta (D1).
        liczba_znakow:          długość przywróconego `full_story`.
        naglowek_uzyty:         tekst nagłówka, od którego snapowano (lub None).
        sekcja_przekroczyla_limit: (v17.6) True gdy WYBRANY marker istniał, ale
                                jego sekcja sama przekroczyła MAX_TAIL_ZN i spadliśmy
                                na fallback znakowy. Sygnał dla GUI, by JEDNORAZOWO
                                ujawnić istnienie fallbacku zamiast kolejnych dialogów.
    """

    tryb: str
    skasowano_streszczenie: bool = False
    liczba_znakow: int = 0
    naglowek_uzyty: str | None = None
    sekcja_przekroczyla_limit: bool = False
    interaktywny: bool = False   # (v17.6) True gdy uruchomiono chooser (anchor był
                                 # nieaktualny) — GUI pokazuje wtedy punkt odniesienia.


@dataclass
class StatusPamieciModelu:
    """Stan wskaźnika pamięci modelu – dane dla GUI (komunikat składa GUI z i18n).

    Attributes:
        procent: 0–100, do ustawienia w ``wx.Gauge``.
        tokeny:  surowa liczba tokenów payloadu (GUI wstawia w lokalizowany
                 komunikat przez ``t("rezyser.pamiec_status_*", tokeny=…)``).
        poziom:  Jeden z ``POZIOM_*`` – GUI dobiera po nim kolor tekstu i klucz
                 treści. v17.9: pole ``komunikat`` USUNIĘTE (było hard-kodowanym
                 polskim wyświetlanym wprost przez `gui_rezyser` — przeciekał do
                 nie-polskiego usera).
    """

    procent: int
    tokeny: int
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


def policz_tokeny_payloadu_snapshot(
    snapshot: SnapshotProjektu,
    model: str = ct.MODEL_DOMYSLNY_REZYSER,
) -> int:
    """Free-function wariant :meth:`ProjektRezysera.policz_tokeny_payloadu`.

    Bierze :class:`SnapshotProjektu` zamiast obiektu projektu — używany
    przez wątek tła (``rezyser_ai.wybierz_sufiks``), który ma dostęp tylko
    do snapshotu.
    """
    tresci = [snapshot.full_story]
    if snapshot.summary_text.strip():
        tresci.append(snapshot.summary_text)
    if snapshot.world_lore.strip():
        tresci.append(snapshot.world_lore)
    return ct.policz_tokeny_chat(tresci, model)


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
        self.app_dir: str = app_dir or sciezki.KATALOG_BAZOWY_STR

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

    def _sciezka_brainstorm(self, nazwa: str) -> str:
        # v15.2: persystencja wyników Burzy (3 opcje + opcjonalne streszczenie).
        # Plik istnieje tylko między wygenerowaniem opcji a wysyłką prompta
        # produkcyjnego (Skrypt/Audiobook), wtedy jest kasowany. Dzięki temu
        # po wczytaniu projektu (np. nazajutrz) gracz wciąż widzi ostatnie
        # opcje wygenerowane przez Burzę — nie musi ich pamiętać.
        # Folder runtime/skrypty/ — ten sam co `.mode`, by jeden katalog
        # trzymał całą metadane projektu (DRY).
        return os.path.join(
            self.app_dir, RUNTIME_DIR, SKRYPTY_DIR, f"{nazwa}.brainstorm.json"
        )

    def _sciezka_streszczenie_meta(self, nazwa: str) -> str:
        # v15.5: metadane streszczenia — ostatni nagłówek struktury wykryty
        # w momencie zapisu streszczenia. Anchor do rekoncyliacji końcówki
        # `.txt` po ręcznej edycji. runtime/skrypty/ (ukryte, gitignored) —
        # ten sam katalog co `.mode` / `.brainstorm.json`.
        return os.path.join(
            self.app_dir, RUNTIME_DIR, SKRYPTY_DIR, f"{nazwa}_streszczenie_meta.json"
        )

    def _sciezka_obsada(self, nazwa: str) -> str:
        # v16.0: szkic obsady głosowej ElevenLabs (mapa postać→voice_id +
        # narrator). Trwały szkic — przeżywa reload i jest bazą dla dispatchera
        # mostu do ElevenLabs Studio. runtime/skrypty/ (ukryte, gitignored,
        # poza paczką release) — ten sam katalog co `.mode` / `.brainstorm.json`.
        return os.path.join(
            self.app_dir, RUNTIME_DIR, SKRYPTY_DIR, f"{nazwa}.obsada.json"
        )

    # ------------------------------------------------------------------
    # Wczytywanie
    # ------------------------------------------------------------------
    def wczytaj(
        self,
        nazwa: str,
        model: str = ct.MODEL_DOMYSLNY_REZYSER,
        wybor_markera: "Callable[[list[MarkerStruktury], str], int | None] | None" = None,
    ) -> WynikWczytania:
        """Wczytuje projekt: historię / streszczenie / Księgę Świata / tryb .mode.

        Od v17.6 jest JEDYNYM wejściem wczytania/przeładowania z dysku — także
        „Przeładuj projekt z dysku" w GUI woła tę metodę (przelicza liczniki,
        podnosi Księgę/tryb/rekoncyliację jednym torem, eliminując desync
        liczników i meta streszczenia po ręcznej edycji `.txt`).

        Ustawia liczniki rozdziałów/aktów/scen na podstawie treści historii.

        v15.5: regułę Nieskończonej Pamięci („streszczenie → full_story=''")
        zastąpiła INTELIGENTNA REKONCYLIACJA (:meth:`_zastosuj_rekoncyliacje`):
          * cały `.txt` mieści się pod progiem ostrzegawczym → wczytujemy CAŁOŚĆ
            bez kompresji (nawet jeśli istnieje streszczenie — wtedy je kasujemy);
          * tekst przekracza próg i jest streszczenie → `full_story` to tylko
            KOŃCÓWKA `.txt` (od wybranego/ostatniego użytecznego nagłówka),
            streszczenie zostaje. To realnie domyka lukę „po wczytaniu z
            _streszczenie.txt AI głupiało bez kontekstu fabuły".

        Args:
            wybor_markera: (v17.6) opcjonalny callback wyboru punktu odniesienia
                pamięci roboczej, wołany TYLKO gdy historia za długa (wariant
                snap). Dostaje ``(markery, struktura)`` z :func:`wyliczy_markery`
                i zwraca wybrany ``offset`` lub ``None`` (anuluj → fallback
                znakowy). Brak callbacku = automatyczny wybór anchora z meta
                (zachowanie sprzed v17.6, używane przez testy/headless).

        Raises:
            FileNotFoundError: gdy nie istnieje plik ``skrypty/<nazwa>.txt``.
        """
        sciezka = self._sciezka_historii(nazwa)
        if not os.path.exists(sciezka):
            raise FileNotFoundError(sciezka)

        with open(sciezka, "r", encoding="utf-8") as fh:
            content = fh.read()

        # --- Liczniki: bierzemy maksimum znalezionych numerów i +1 ---
        chapter_nums = [int(m) for m in re.findall(_WZORZEC_ROZDZIAL, content)]
        akt_nums = [int(m) for m in re.findall(_WZORZEC_AKT, content)]
        # Sceny liczymy tylko wewnątrz OSTATNIEGO aktu – numeracja
        # scen restartuje się z każdym aktem.
        ostatni_split = re.split(_WZORZEC_AKT.replace(r"(\d+)", r"\d+"), content)
        ostatni_frag = ostatni_split[-1] if ostatni_split else content
        scena_nums = [int(m) for m in re.findall(_WZORZEC_SCENA, ostatni_frag)]

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

        # --- Tryb twórczy (.mode) ---
        # Czytany PRZED rekoncyliacją (v17.6): enumeracja markerów punktu
        # odniesienia musi znać strukturę (akty+sceny / rozdziały). Od v18.5
        # `.mode` trzyma stabilne `id` trybu — strukturę rozwiązujemy z przepisu.
        self.nazwa_pliku = nazwa
        wynik.saved_mode = self.wczytaj_tryb_tworczy(nazwa)
        struktura = pr.struktura_dla_id(wynik.saved_mode) if wynik.saved_mode else None

        # --- Inteligentna rekoncyliacja (v15.5) ---
        # nazwa_pliku MUSI być ustawiona przed rekoncyliacją — używa jej przez
        # `_wymagaj_nazwy` i ścieżkowe helpery.
        rek = self._zastosuj_rekoncyliacje(
            content, model, wybor_markera, struktura,
        )
        wynik.rekoncyliacja    = rek
        wynik.czy_historia     = bool(self.full_story.strip())
        wynik.czy_streszczenie = bool(self.summary_text.strip())
        wynik.liczba_znakow    = len(self.full_story)
        return wynik

    # ------------------------------------------------------------------
    # Rekoncyliacja narracji z dysku (v15.5; rdzeń prywatny od v17.6)
    # ------------------------------------------------------------------
    def _zastosuj_rekoncyliacje(
        self,
        content: str,
        model: str = ct.MODEL_DOMYSLNY_REZYSER,
        wybor_markera: "Callable[[list[MarkerStruktury], str], int | None] | None" = None,
        struktura: str | None = None,
    ) -> WynikRekoncyliacji:
        """Czysta logika rekoncyliacji (oddzielona od I/O dla testowalności).

        Ustawia `self.full_story` (+ ewentualnie `self.summary_text`) na
        podstawie ``content`` (treść `.txt`) i obecności streszczenia. Zwraca
        :class:`WynikRekoncyliacji`. Wymaga ustawionej `nazwa_pliku`.
        """
        self._wymagaj_nazwy()
        sciezka_strsz = self._sciezka_streszczenia(self.nazwa_pliku)
        ma_streszczenie = os.path.exists(sciezka_strsz) or bool(self.summary_text.strip())

        # Próg: czy CAŁA narracja (+ Księga Świata) mieści się pod ostrzeżeniem?
        # summary_text="" w teście — sprawdzamy sam tekst narracji.
        test = SnapshotProjektu(
            nazwa=self.nazwa_pliku, full_story=content,
            summary_text="", world_lore=self.world_lore,
        )
        tokeny = policz_tokeny_payloadu_snapshot(test, model)
        miesci_sie = tokeny < int(OKNO_KONTEKSTU_MAX * PROG_OSTRZEZENIE)

        # --- Wariant „całość": krótka historia LUB brak streszczenia ---
        if miesci_sie or not ma_streszczenie:
            self.full_story = content
            skasowano = False
            if not miesci_sie:
                # Brak streszczenia + tekst > próg: wymóg streszczenia w gestii
                # usera (doc). Nie kompresujemy — `.txt` jest źródłem prawdy.
                pass
            if ma_streszczenie and miesci_sie:
                # D1: streszczenie zbędne (całość się mieści) → skasuj plik+meta.
                skasowano = self._skasuj_streszczenie_i_meta()
            else:
                self.summary_text = ""
            return WynikRekoncyliacji(
                tryb="calosc",
                skasowano_streszczenie=skasowano,
                liczba_znakow=len(self.full_story),
            )

        # --- Wariant „snap": długa historia + istnieje streszczenie ---
        # Doładuj streszczenie z dysku jeśli nie ma go jeszcze w RAM.
        if not self.summary_text.strip() and os.path.exists(sciezka_strsz):
            try:
                with open(sciezka_strsz, "r", encoding="utf-8") as fh:
                    self.summary_text = fh.read()
            except OSError:
                pass

        def _od_offsetu(offset: int) -> WynikRekoncyliacji:
            """Ustawia ``full_story`` od ``offset`` (nagłówka). Spada na fallback
            znakowy z flagą ``sekcja_przekroczyla_limit``, gdy sama sekcja od
            markera przekracza :data:`MAX_TAIL_ZN` — sygnał dla GUI, by
            JEDNORAZOWO ujawnić istnienie fallbacku (K3 v17.6)."""
            koncowka = content[offset:]
            naglowek = koncowka.splitlines()[0].strip() if koncowka else None
            if len(koncowka) > MAX_TAIL_ZN:
                self.full_story = _koncowka_po_znakach(content, MAX_TAIL_ZN)
                return WynikRekoncyliacji(
                    tryb="koncowka", liczba_znakow=len(self.full_story),
                    naglowek_uzyty=naglowek, sekcja_przekroczyla_limit=True,
                )
            self.full_story = koncowka
            return WynikRekoncyliacji(
                tryb="snap", liczba_znakow=len(self.full_story),
                naglowek_uzyty=naglowek,
            )

        # Anchor zapisany w meta streszczenia: czy jest WCIĄŻ ważny w bieżącej
        # treści (preferowany nagłówek obecny + ma istotną treść)?
        meta = self._wczytaj_streszczenie_meta()
        preferowany = meta.get("marker_naglowek_tekst") if meta else None
        anchor_offset = None
        if preferowany:
            for off, txt in reversed(_znajdz_naglowki(content)):
                if txt == preferowany and _ma_istotna_tresc(content, off):
                    anchor_offset = off
                    break

        # Tor interaktywny (v17.6) TYLKO gdy anchor nieaktualny (reżyser uciął/
        # przesunął nagłówek po ostatnim streszczeniu) ALBO brak meta — wtedy
        # automat by chybił, więc pytamy gracza, od którego nagłówka startować.
        # Gdy anchor wciąż ważny, używamy go CICHO (zachowanie v15.5), bez dialogu.
        if wybor_markera is not None and anchor_offset is None:
            markery = wyliczy_markery(content, struktura or "rozdzialy")
            offset = wybor_markera(markery, struktura or "rozdzialy") if markery else None
            if offset is None:
                # Anuluj / brak markerów → fallback znakowy (świadoma rezygnacja;
                # BEZ flagi `sekcja_przekroczyla_limit`).
                self.full_story = _koncowka_po_znakach(content, MAX_TAIL_ZN)
                return WynikRekoncyliacji(
                    tryb="koncowka", liczba_znakow=len(self.full_story),
                    interaktywny=True,
                )
            wynik_rek = _od_offsetu(offset)
            wynik_rek.interaktywny = True
            return wynik_rek

        # Anchor ważny (użyj cicho) LUB brak callbacku (testy/headless) → automat.
        offset = (anchor_offset if anchor_offset is not None
                  else _ostatni_uzyteczny_naglowek(content, preferowany or None))
        if offset is not None:
            return _od_offsetu(offset)

        # Brak użytecznego markera (reżyser wymazał nagłówki) → limit znakowy.
        self.full_story = _koncowka_po_znakach(content, MAX_TAIL_ZN)
        return WynikRekoncyliacji(tryb="koncowka", liczba_znakow=len(self.full_story))

    def _skasuj_streszczenie_i_meta(self) -> bool:
        """D1: usuwa `_streszczenie.txt` + `_streszczenie_meta.json` i zeruje
        `summary_text`. Zwraca True jeśli skasowano przynajmniej jeden plik."""
        skasowano = False
        for sciezka in (
            self._sciezka_streszczenia(self.nazwa_pliku),
            self._sciezka_streszczenie_meta(self.nazwa_pliku),
        ):
            if os.path.exists(sciezka):
                try:
                    os.remove(sciezka)
                    skasowano = True
                except OSError:
                    pass
        self.summary_text = ""
        return skasowano

    def _wczytaj_streszczenie_meta(self) -> dict[str, Any] | None:
        """Wczytuje `_streszczenie_meta.json` lub None (brak / błąd parsowania)."""
        sciezka = self._sciezka_streszczenie_meta(self.nazwa_pliku)
        if not os.path.exists(sciezka):
            return None
        try:
            with open(sciezka, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, ValueError):
            return None

    def _zapisz_streszczenie_meta(self) -> None:
        """Wykrywa ostatni nagłówek struktury w `full_story` i zapisuje meta JSON
        (anchor rekoncyliacji). Wołane z :meth:`zapisz_streszczenie`."""
        naglowki = _znajdz_naglowki(self.full_story)
        if naglowki:
            _, tekst_naglowka = naglowki[-1]
            marker_typ, marker_numer = _rozbij_naglowek(tekst_naglowka)
        else:
            marker_typ, marker_numer, tekst_naglowka = "brak", None, ""
        meta = {
            "marker_typ": marker_typ,
            "marker_numer": marker_numer,
            "marker_naglowek_tekst": tekst_naglowka,
            "dlugosc_full_story_przy_streszczeniu": len(self.full_story),
        }
        sciezka = self._sciezka_streszczenie_meta(self.nazwa_pliku)
        os.makedirs(os.path.dirname(sciezka), exist_ok=True)
        with open(sciezka, "w", encoding="utf-8") as fh:
            json.dump(meta, fh, ensure_ascii=False, indent=2)
        _dev_log_runtime(sciezka)

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
        # v15.5: zapisz meta-marker (ostatni nagłówek struktury w full_story
        # w momencie streszczania) — anchor do rekoncyliacji końcówki `.txt`.
        # Niekrytyczne: brak meta → rekoncyliacja użyje fallbacku po znakach.
        try:
            self._zapisz_streszczenie_meta()
        except OSError:
            pass
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

    def zapisz_tryb_tworczy(
        self, id_trybu: str, zapis_do_pliku: bool = True, nazwa: str | None = None,
    ) -> None:
        """Zapisuje stabilne ``id`` trybu twórczego do pliku ``.mode`` (cichy fail).

        Od v18.5 ``.mode`` trzyma ``id`` przepisu (np. ``"audiobook"``), nie
        pozycyjny int — dzięki czemu reorder ``kolejnosc`` w RadioBox nie
        przestawia znaczeń, a stary projekt zawsze wraca do właściwego trybu.

        Args:
            id_trybu:       stabilne ``id`` przepisu (``PrzepisRezysera.id``).
            zapis_do_pliku: ``True`` tylko dla trybów produkcyjnych (zapisujących
                            ``.txt``). Tryby bez zapisu (np. Burza, planowanie)
                            są ulotne — NIE utrwalamy ich w metadanych.
            nazwa:          Opcjonalne nadpisanie nazwy projektu.
        """
        nazwa = nazwa or self.nazwa_pliku
        if not nazwa or not id_trybu or not zapis_do_pliku:
            return
        meta_dir = os.path.join(self.app_dir, RUNTIME_DIR, SKRYPTY_DIR)
        os.makedirs(meta_dir, exist_ok=True)
        sciezka = self._sciezka_mode(nazwa)
        try:
            with open(sciezka, "w", encoding="utf-8") as fh:
                fh.write(str(id_trybu))
            _dev_log_runtime(sciezka)
        except Exception:
            # Metadata trybu to quality-of-life, a nie coś, bez czego
            # aplikacja nie działa – milczymy w razie awarii.
            pass

    def wczytaj_tryb_tworczy(self, nazwa: str | None = None) -> str | None:
        """Odczytuje stabilne ``id`` trybu twórczego z pliku ``.mode``.

        Back-compat: pliki sprzed v18.5 trzymały pozycyjny int — mapujemy
        ``"1"`` → ``"skrypt"``, ``"2"`` → ``"audiobook"`` (stare zapisane
        projekty wracają do właściwego trybu).

        Returns:
            ``id`` trybu (np. ``"audiobook"``) gdy plik istnieje i jest niepusty,
            ``None`` w każdym innym przypadku (brak pliku, błąd odczytu, itd.).
        """
        nazwa = nazwa or self.nazwa_pliku
        if not nazwa:
            return None
        sciezka = self._sciezka_mode(nazwa)
        if not os.path.exists(sciezka):
            return None
        try:
            with open(sciezka, "r", encoding="utf-8") as fh:
                val = fh.read().strip()
        except Exception:
            return None
        if not val:
            return None
        return {"1": "skrypt", "2": "audiobook"}.get(val, val)

    # ------------------------------------------------------------------
    # Persystencja wyników Burzy (v15.2)
    # ------------------------------------------------------------------
    # Cel: po wczytaniu projektu (np. nazajutrz) gracz wciąż widzi ostatnie
    # opcje wygenerowane przez Burzę — nie musi ich pamiętać. Plik
    # `runtime/skrypty/<nazwa>.brainstorm.json` istnieje TYLKO między
    # wygenerowaniem Burzy a wysyłką prompta produkcyjnego (Skrypt/Audiobook)
    # — wtedy GUI woła `usun_brainstorm()` przed wywołaniem produkcyjnego
    # AI, bo opcje z Burzy stały się nieaktualne (gracz „skonsumował" je
    # przy pisaniu sceny).
    #
    # Argumenty są prymitywami (list[dict], str) — żeby uniknąć cyklicznej
    # zależności core_rezyser ↔ rezyser_ai. GUI/silnik konwertują dataclassy
    # OpcjaBurzy z `rezyser_ai` do/z prymitywów przed/po I/O.

    def zapisz_brainstorm(
        self,
        opcje: list[dict[str, str]],
        streszczenie: str = "",
    ) -> str:
        """Zapisuje wynik Burzy do `runtime/skrypty/<nazwa>.brainstorm.json`.

        Args:
            opcje:        Lista dictów ``{"tytul", "opis", "cel_sceny"}``.
                          GUI tworzy je z :class:`rezyser_ai.OpcjaBurzy`
                          przez ``dataclasses.asdict`` lub ręczne mapowanie.
            streszczenie: Opcjonalna treść streszczenia (sufiks alarm/
                          streszczenie). Pusty string gdy bez streszczenia.

        Zwraca ścieżkę zapisanego pliku. Nadpisuje plik (overwrite, jak
        `.mode`) — każda nowa Burza zastępuje poprzednią; do historii
        Burz nie wracamy, bo gracz wybrał JEDNĄ ścieżkę dalej.
        """
        self._wymagaj_nazwy()
        meta_dir = os.path.join(self.app_dir, RUNTIME_DIR, SKRYPTY_DIR)
        os.makedirs(meta_dir, exist_ok=True)
        sciezka = self._sciezka_brainstorm(self.nazwa_pliku)

        # Filtr: tylko dictów ze wszystkimi 3 wymaganymi polami. Halucynacja
        # po stronie wywołującego (np. brak `cel_sceny`) nie powinna zapisać
        # niezdatnego do użytku rekordu na dysk.
        opcje_clean = [
            {"tytul": str(o.get("tytul", "")),
             "opis": str(o.get("opis", "")),
             "cel_sceny": str(o.get("cel_sceny", ""))}
            for o in (opcje or [])
            if o.get("tytul") and o.get("cel_sceny")
        ]
        payload = {
            "wersja": 1,
            "opcje": opcje_clean,
            "streszczenie": streszczenie or "",
        }
        import json  # noqa: PLC0415  (lazy — używane tylko przy I/O brainstorm)
        with open(sciezka, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        _dev_log_runtime(sciezka)
        return sciezka

    def wczytaj_brainstorm(
        self,
        nazwa: str | None = None,
    ) -> dict[str, Any] | None:
        """Wczytuje plik `runtime/skrypty/<nazwa>.brainstorm.json`.

        Returns:
            Dict ``{"opcje": [...], "streszczenie": str}`` gdy plik istnieje
            i parsuje się jako JSON. ``None`` gdy brak pliku, błąd parsowania,
            albo `opcje` puste (uznajemy za niezdatny do GUI).

        GUI wywołuje to po :meth:`wczytaj` żeby odbudować przyciski opcji
        — bez wymagania od gracza ponownej Burzy. Po sukcesie produkcyjnym
        (Skrypt/Audiobook) GUI woła :meth:`usun_brainstorm`.
        """
        nazwa = nazwa or self.nazwa_pliku
        if not nazwa:
            return None
        sciezka = self._sciezka_brainstorm(nazwa)
        if not os.path.exists(sciezka):
            return None
        try:
            import json  # noqa: PLC0415
            with open(sciezka, "r", encoding="utf-8") as fh:
                dane = json.load(fh)
        except Exception:
            return None

        opcje = dane.get("opcje") or []
        if not opcje:
            return None
        return {
            "opcje":        list(opcje),
            "streszczenie": str(dane.get("streszczenie", "")),
        }

    def usun_brainstorm(self, nazwa: str | None = None) -> None:
        """Usuwa plik brainstorm (cichy fail jeśli nie istnieje).

        Wołane przez GUI tuż przed wysłaniem prompta produkcyjnego
        (Skrypt/Audiobook) — opcje z Burzy „zużyły się" przy pisaniu sceny
        i nie powinny być proponowane jako wybór w następnej turze.
        Wołane też przy starcie nowej Burzy (świeży plik nadpisze stary,
        ale jawne `os.remove` przed `os.makedirs` zapobiega race-condition
        gdyby gracz przerwał wysyłkę przed zapisem).
        """
        nazwa = nazwa or self.nazwa_pliku
        if not nazwa:
            return
        sciezka = self._sciezka_brainstorm(nazwa)
        try:
            os.remove(sciezka)
        except FileNotFoundError:
            pass
        except Exception:
            # Jak `.mode` — metadata, cichy fail.
            pass

    # ------------------------------------------------------------------
    # Obsada głosowa ElevenLabs (v16.0) — szkic postać→voice_id + narrator
    # ------------------------------------------------------------------
    def zapisz_obsada(self, glosy: dict[str, str], nazwa: str | None = None) -> str:
        """Zapisuje szkic obsady do `runtime/skrypty/<nazwa>.obsada.json`.

        Args:
            glosy: mapa ``{nazwa_postaci_lower: voice_id, "__narrator__": voice_id}``.
                   Szkic MOŻE być niekompletny (puste/brakujące wpisy) — komplet
                   waliduje dopiero dispatcher przed budową projektu. Puste
                   wartości są odfiltrowywane (zapisujemy tylko realne ID).
            nazwa: opcjonalna nazwa projektu. Postprodukcja bierze nazwę wprost
                   z pola GUI (sztuka z dysku), więc nie wymaga załadowanego
                   projektu. Gdy None — używa ``self.nazwa_pliku``.

        Zwraca ścieżkę zapisanego pliku. Nadpisuje (overwrite, jak brainstorm).
        """
        nazwa = nazwa or self.nazwa_pliku
        if not nazwa:
            raise ValueError("Brak nazwy projektu — nie mogę zapisać obsady.")
        meta_dir = os.path.join(self.app_dir, RUNTIME_DIR, SKRYPTY_DIR)
        os.makedirs(meta_dir, exist_ok=True)
        sciezka = self._sciezka_obsada(nazwa)

        glosy_clean = {
            str(k): str(v).strip()
            for k, v in (glosy or {}).items()
            if k and str(v).strip()
        }
        payload = {"wersja": 1, "glosy": glosy_clean}
        import json  # noqa: PLC0415  (lazy — tylko przy I/O obsady)
        with open(sciezka, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        _dev_log_runtime(sciezka)
        return sciezka

    def wczytaj_obsada(self, nazwa: str | None = None) -> dict[str, str]:
        """Wczytuje szkic obsady. Zwraca mapę ``{nazwa: voice_id}`` (pustą gdy brak).

        Brak pliku / błąd parsowania / zła struktura → pusty dict (feature
        opcjonalny, nigdy nie wywraca panelu). Pre-fill okienka obsady i baza
        dla dispatchera.
        """
        nazwa = nazwa or self.nazwa_pliku
        if not nazwa:
            return {}
        sciezka = self._sciezka_obsada(nazwa)
        if not os.path.exists(sciezka):
            return {}
        try:
            import json  # noqa: PLC0415
            with open(sciezka, "r", encoding="utf-8") as fh:
                dane = json.load(fh)
        except Exception:
            return {}
        glosy = dane.get("glosy") if isinstance(dane, dict) else None
        if not isinstance(glosy, dict):
            return {}
        return {str(k): str(v) for k, v in glosy.items() if k and str(v).strip()}

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

    def wstaw_prolog(self, *, naglowek: str = "Prolog") -> str:
        """Wstawia nagłówek prologu na początek historii (nadpisując plik)."""
        self._wymagaj_nazwy()
        header = f"{naglowek}\n\n"
        self.full_story += header
        # Tryb "w" – Prolog zaczyna historię od zera. Gdyby plik zawierał
        # resztki z poprzedniej sesji (test zmian, zepsuty zapis), byłyby
        # teraz niszczone. Tak samo robił oryginalny kod w gui_rezyser.
        self.dopisz_do_pliku_historii(header, mode="w")
        return naglowek

    def wstaw_epilog(self, *, naglowek: str = "Epilog") -> str:
        """Wstawia nagłówek epilogu na koniec historii. Po nim dalszy zapis jest blokowany."""
        self._wymagaj_nazwy()
        header = f"\n\n{naglowek}\n\n"
        self.full_story += header
        self.dopisz_do_pliku_historii(header)
        return naglowek

    def wstaw_rozdzial(self, *, naglowek_bazowy: str = "Rozdział") -> str:
        """Wstawia nagłówek kolejnego rozdziału (Audiobook) i inkrementuje licznik."""
        self._wymagaj_nazwy()
        naglowek = f"{naglowek_bazowy} {self.chapter_counter}"
        content = f"\n\n{naglowek}\n\n"
        self.full_story += content
        self.chapter_counter += 1
        self.dopisz_do_pliku_historii(content)
        return naglowek

    def wstaw_akt(
        self,
        *,
        naglowek_akt: str = "Akt",
        naglowek_scena: str = "Scena",
    ) -> tuple[str, str]:
        """Wstawia nagłówek aktu + automatycznie sceny 1 (tryb Skrypt).

        Inkrementuje licznik aktów i ustawia licznik scen na 2 (bo Scena 1
        właśnie została wstawiona). Zwraca krotkę ``(akt, scena)``
        – dla GUI do komunikatu zwrotnego.
        """
        self._wymagaj_nazwy()
        akt = f"{naglowek_akt} {self.akt_counter}"
        scena = f"{naglowek_scena} 1"
        content = f"\n\n{akt}\n\n{scena}\n\n"
        self.full_story += content
        self.akt_counter += 1
        self.scena_counter = 2
        self.dopisz_do_pliku_historii(content)
        return akt, scena

    def wstaw_scena(self, *, naglowek_bazowy: str = "Scena") -> str:
        """Wstawia kolejny nagłówek sceny w bieżącym Akcie."""
        self._wymagaj_nazwy()
        scena = f"{naglowek_bazowy} {self.scena_counter}"
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
                return bool(re.match(_WZORZEC_NAGLOWEK_LINIA, linia.strip()))
        return False

    # ------------------------------------------------------------------
    # Status pamięci modelu
    # ------------------------------------------------------------------
    def policz_tokeny_payloadu(
        self,
        model: str = ct.MODEL_DOMYSLNY_REZYSER,
    ) -> int:
        """Liczy tokeny payloadu, jaki poszedłby w kolejnym wywołaniu API.

        Sumuje pola wiadomości chat (``full_story`` + ``summary_text`` +
        ``world_lore``) bez pełnego prompta systemowego — ten różni się
        per tryb (Burza/Skrypt/Audiobook) i nie jest dostępny na poziomie
        ``ProjektRezysera`` (przepisy żyją w `prompty_rezyser`). Wynik
        jest dolnym oszacowaniem: prompt systemowy + user_text dodadzą
        zwykle 2–4k tokenów (mniej niż 3% okna 128k), więc gauge GUI
        zostaje wystarczająco dokładny do auto-alarmu.
        """
        return policz_tokeny_payloadu_snapshot(self.snapshot(), model)

    def status_pamieci_modelu(self) -> StatusPamieciModelu:
        """Zwraca gotowy do wyświetlenia status pamięci modelu.

        GUI używa tego do aktualizacji ``wx.Gauge`` + pola statusu.
        Kolor (zielony/pomarańczowy/czerwony) GUI wybiera na podstawie
        pola ``poziom``.
        """
        # v17.9: tylko dane (procent/tokeny/poziom) — lokalizowany komunikat
        # składa GUI (`gui_rezyser._aktualizuj_pamiec_modelu`) z i18n. Koniec
        # hard-kodowanego polskiego przeciekającego do nie-polskiego usera.
        if not self.full_story and not self.summary_text and not self.world_lore:
            return StatusPamieciModelu(procent=0, tokeny=0, poziom=POZIOM_CZYSTA)

        tokeny  = self.policz_tokeny_payloadu()
        udzial  = tokeny / OKNO_KONTEKSTU_MAX
        procent = min(int(udzial * 100), 100)

        if udzial >= PROG_ALARM:
            return StatusPamieciModelu(procent=procent, tokeny=tokeny, poziom=POZIOM_ALARM)
        if udzial >= PROG_OSTRZEZENIE:
            return StatusPamieciModelu(procent=procent, tokeny=tokeny, poziom=POZIOM_OSTRZEZENIE)
        return StatusPamieciModelu(procent=procent, tokeny=tokeny, poziom=POZIOM_OK)

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
