#!/usr/bin/env python
"""
buduj_wielojezyczne_akcenty.py — AUDYTOR i GENERATOR par akcentowych Poligloty.

Szósty brat rodziny `buduj_wielojezyczne_*` — i pierwszy, który NIE jest
tłumaczem. Materiał (`dictionaries/<paczka>/akcenty/<akcent>.yaml`, 72 pary =
9 paczek × 8 obcych akcentów) ma cechę rozstrzygającą o architekturze:

    `de/akcenty/finski.yaml` NIE JEST tłumaczeniem `pl/akcenty/finski.yaml`.

Oba pliki opisują ten sam CEL (fiński syntezator mowy), ale INNE ŹRÓDŁO —
pierwszy przerabia tekst niemiecki, drugi polski. Reguły `zamiany` są więc
rozłączne (`sch → s` vs `sz → s`), a proza `opis` opisuje inne zjawiska.
Nie ma tu czego „rozpropagować z polskiego": para akcentowa jest
WYPROWADZENIEM REGUŁY FONETYCZNEJ dla pary (pismo źródła → fonologia celu).

Stąd dwie ścieżki, obie inne niż u pięciu braci:

  1. **AUDYT (domyślny, zero API).** Jedyna kontrola, która porównuje 72 pary
     MIĘDZY sobą i z SILNIKIEM. Bramki niżej powstały przez kalibrację na
     wszystkich parach PRZED napisaniem czegokolwiek (lekcja v18.18: pierwszy
     przebieg bramki daje więcej fałszywych alarmów niż defektów). Dwie
     bramki, które w pierwszej wersji miały 72/72 fałszywych trafień
     („wyjście musi mieścić się w alfabecie celu" — proza paczek cytuje IPA
     i obce przykłady), zostały ZAWĘŻONE, nie utrzymane siłą.

  2. **GENEROWANIE dla NOWEGO języka (`--nowy-jezyk`).** Decyzja maintainera
     z roadmapy: ścieżka generująca NIGDY nie nadpisuje wypełnionej pary —
     na 72 istniejących działa wyłącznie walidacja. Nowy język wymaga par
     w DWÓCH kierunkach (parytet natywności): `<nowy>/akcenty/<obcy>.yaml`
     × 8 oraz `<obcy>/akcenty/<nowy>.yaml` × 9.

Bramki (błąd = blokada zapisu / niezerowy exit; uwaga = triaż recenzenta):

  * **G1 kontrakt pliku** — `id` == nazwa pliku, `iso` == kod języka AKCENTU
    (konsensus 72/72 par), `kategoria: akcent`, cztery flagi pipeline'u,
    niepusta `zamiany`, ZERO nieznanych pól (twardy stop jak w `_tryby.py`).
  * **G2 martwe reguły** — duplikat `wzor`, `wzor == zamiana`, dwuznak PO
    zawierającym go jednoznaku, niekompilowalny regex ORAZ **reguła zjedzona
    przez pre-pass** (patrz niżej — to ta bramka znalazła 43 martwe reguły
    w paczce `de`).
  * **G3 cieniowanie sekwencyjne** — port `core_poliglota._ostrzez_o_lancuchu_zamian`
    do raportu (uwaga: kaskady bywają celowe). Kaskadę ZAMIERZONĄ deklaruje
    się w danych: komentarz z markerem `KASKADA ZAMIERZONA` nad regułą-źródłem
    wycisza to trafienie (v18.21 — inaczej osiem świadomych łańcuchów
    w `de/hiszpanski` i `fr/finski` szumiałoby w audycie na zawsze).
  * **G4 parytet wielkości liter** — reguła małoliterowa bez odpowiednika
    wielkoliterowego. Wyjątek: litery bez odpowiednika (`ß`.upper() == „SS").
  * **G5 pismo wyjścia** — dla akcentu TRANSLITERUJĄCEGO (wyjście w innym
    piśmie niż źródło) resztki liter źródła = dziura w tablicy; dodatkowo
    `skleja_pojedyncze_litery` na wyjściu niełacińskim jest flagą martwą
    (regex silnika ma klasę `[a-z]`).
  * **G6 przykłady w prozie przeliczone SILNIKIEM** — 324 pary „X → Y" w 72
    plikach; bramka rozumie łańcuchy („a" → „b" → „c") i alternatywy
    („au/eau"), a prozę zastrzeżoną („oder", „je nach Kontext") degraduje do
    uwagi. Klasa v17.6.2, ta sama co jąkanie w v18.18.
  * **G7 kolejnosc** — duplikat w obrębie paczki (uwaga, nie błąd: silnik ma
    tie-breaker po etykiecie, więc lista pozostaje deterministyczna).
  * **G8 wariant ALL-CAPS dwuznaku** (v18.21) — reguła o co najmniej dwóch
    literach bez odpowiednika pisanego WERSALIKAMI: `Sz → Sh` nie łapie
    nagłówka „SZKIC", bo `str.replace` jest wrażliwe na wielkość liter. G4
    pilnuje tylko wariantu z wielkiej litery, więc luka przeżyła 72 pary
    (109 brakujących wariantów dosypanych w v18.21). Porównanie idzie po
    wzorcu OBCIĘTYM z białych znaków: wariant wersalikowy reguły, w której
    wielka litera zastępuje granicę słowa (`Sp` → `Шп` w `de/rosyjski`), nosi
    tę granicę jawnie jako spację (` SP`), bo w tekście pisanym wersalikami
    proxy z wielkiej litery nie istnieje.
  * **G9 tablica pre-passu vs. własne akcenty paczki** (v18.22) — wpis
    `podstawy.yaml::polskie_znaki` obowiązuje w każdym akcencie z flagą
    `usun_polskie_znaki: true`, więc jeśli akcenty z flagą `false` czytają ten
    sam znak inaczej, paczka sobie przeczy. Porównanie po PIERWSZEJ literze
    wyniku i tylko w obrębie jednego pisma; jednomyślny rozjazd = błąd. To ta
    bramka nazywa francuską cedyllę: tablica dawała „c" (czyli /k/), a własne
    akcenty — /s/.

**PRE-PASS ZJADA REGUŁY — klasa defektu odkryta tym audytem.** Silnik stosuje
`usun_polskie_znaki` PRZED listą `zamiany` (`core_poliglota` linie 1038-1044),
a pole `polskie_znaki` w `podstawy.yaml` — wbrew historycznej nazwie — spłaszcza
WSZYSTKIE diakrytyki paczki. Reguła, której `wzor` zawiera diakrytyk źródła,
jest więc przy włączonej fladze NIEOSIĄGALNA: paczka `de` obiecuje w prozie
„ä → e" (akcent polski), „ö → eu" (francuski), „ü → y" (fiński/islandzki),
a silnik oddaje gołe a/o/u. Paczki `es` i `fr` znają to rozwiązanie i stawiają
`usun_polskie_znaki: false` w akcentach, które potrzebują własnych diakrytyków.

Zależności: wspólny rdzeń :mod:`tlumacz_rdzen` (klient, round-trip, chunkowanie)
i bramki :mod:`tlumacz_bramki` (anty-meta-skip, odcisk struktury). Moduł jest
DEV-ONLY i nie zależy od wxPython.

Użycie:
  python buduj_wielojezyczne_akcenty.py --audyt                 # 72 pary, zero API
  python buduj_wielojezyczne_akcenty.py --audyt --jezyki de     # jedna paczka
  python buduj_wielojezyczne_akcenty.py --audyt --raport plik.md
  python buduj_wielojezyczne_akcenty.py --nowy-jezyk sv --dry-run
  python buduj_wielojezyczne_akcenty.py --nowy-jezyk sv --kierunek oba

Wymaga `ANTHROPIC_API_KEY` w `golden_key.env` WYŁĄCZNIE dla `--nowy-jezyk`.
"""
from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

import przeglad_tlumaczen
import tlumacz_bramki
import tlumacz_rdzen


tlumacz_rdzen.skonfiguruj_stdout()


# ---------------------------------------------------------------------------
# Ścieżki i zakres
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
DICT_DIR = ROOT / "dictionaries"

KOD_ZRODLOWY = "pl"
FOLDER = "akcenty"

# Trzy narzędzia z `akcenty/` należą do brata od Poligloty (v18.18) — tu ich
# nie tykamy. Zakres tego narzędzia to WYŁĄCZNIE akcenty fonetyczne.
NARZEDZIA_AKCENTOW = ("oczyszczenie.yaml", "oczyszczenie_bez_liczb.yaml",
                      "naprawiacz_tagow.yaml")

TRYB_SILNIKA = "Rezyser"      # `core_poliglota._FOLDER_DLA_TRYBU["Rezyser"] == "akcenty"`

MODEL_DOMYSLNY = "claude-sonnet-5"
MAX_TOKENS_OUT = 16_000


# ---------------------------------------------------------------------------
# KLASYFIKACJA PÓL
# ---------------------------------------------------------------------------
KLASA_KONTRAKT = "kontrakt"       # czyta SILNIK po nazwie/wartości — nie tłumaczymy
KLASA_ETYKIETA = "etykieta"       # napis w ComboBox (lokalizowany, z nazwami głosów)
KLASA_OPIS = "opis"               # proza dydaktyczna (tooltip + docs)
KLASA_PIPELINE = "pipeline"       # flagi kolejności etapów — DANE PARY, nie kopia
KLASA_REGULY = "reguly"           # `zamiany` — wyprowadzenie fonetyczne pary

KLASY_POL: dict[str, str] = {
    "id": KLASA_KONTRAKT,
    "iso": KLASA_KONTRAKT,
    "kategoria": KLASA_KONTRAKT,
    "kolejnosc": KLASA_KONTRAKT,
    "etykieta": KLASA_ETYKIETA,
    "opis": KLASA_OPIS,
    "czysc_tekst_tts": KLASA_PIPELINE,
    "normalizuj_liczby": KLASA_PIPELINE,
    "usun_polskie_znaki": KLASA_PIPELINE,
    "skleja_pojedyncze_litery": KLASA_PIPELINE,
    "zamiany": KLASA_REGULY,
}

FLAGI_PIPELINE = tuple(k for k, v in KLASY_POL.items() if v == KLASA_PIPELINE)

# Flagi, które w 72/72 parach są `true` — wartość `false` jest sygnałem, nie normą.
FLAGI_ZAWSZE_PRAWDA = ("czysc_tekst_tts", "normalizuj_liczby")


# ---------------------------------------------------------------------------
# WYNIK AUDYTU
# ---------------------------------------------------------------------------
class Znalezisko:
    """Jedno trafienie bramki. `blad=True` → blokada; inaczej uwaga do triażu."""

    __slots__ = ("para", "bramka", "opis", "blad")

    def __init__(self, para: str, bramka: str, opis: str, *, blad: bool):
        self.para = para
        self.bramka = bramka
        self.opis = opis
        self.blad = blad

    def __str__(self) -> str:
        return f"[{self.bramka}] {self.para}: {self.opis}"


# ---------------------------------------------------------------------------
# WCZYTYWANIE MATERIAŁU
# ---------------------------------------------------------------------------
def _yaml_safe() -> YAML:
    return YAML(typ="safe")


def wczytaj_pare(paczka: str, akcent: str) -> dict:
    """Surowy dict jednej pary akcentowej (pusty, gdy pliku nie ma / zły YAML)."""
    plik = DICT_DIR / paczka / FOLDER / f"{akcent}.yaml"
    try:
        dane = _yaml_safe().load(plik.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — zepsuty plik zgłosi G1
        return {}
    return dane if isinstance(dane, dict) else {}


def pary_akcentowe() -> dict[tuple[str, str], dict]:
    """Wszystkie pary `(paczka, akcent) → cfg`, bez trzech narzędzi."""
    wynik: dict[tuple[str, str], dict] = {}
    for katalog in sorted(p for p in DICT_DIR.iterdir() if p.is_dir()):
        folder = katalog / FOLDER
        if not folder.is_dir():
            continue
        for plik in sorted(folder.glob("*.yaml")):
            if plik.name in NARZEDZIA_AKCENTOW:
                continue
            wynik[(katalog.name, plik.stem)] = wczytaj_pare(katalog.name, plik.stem)
    return wynik


def podstawy_paczki(kod: str) -> dict:
    """`dictionaries/<kod>/podstawy.yaml` (pusty przy braku/błędzie)."""
    try:
        dane = _yaml_safe().load(
            (DICT_DIR / kod / "podstawy.yaml").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}
    return dane if isinstance(dane, dict) else {}


def konsensus_iso(pary: dict[tuple[str, str], dict]) -> dict[str, str]:
    """Nazwa akcentu → kod ISO, ustalona JEDNOMYŚLNOŚCIĄ paczek.

    Wzorzec orakułu z v18.15 przeniesiony na dane: `iso` nie jest tłumaczeniem
    ani wyborem redakcyjnym, a kodem języka DOCELOWEGO — więc paczki muszą się
    tu zgadzać. Pomiar wejściowy: 72/72 par zgodnych, więc konsensus to
    kontrakt, a nie heurystyka. Zwracamy wartość WIĘKSZOŚCIOWĄ, żeby jeden
    zepsuty plik nie przesunął oczekiwania dla pozostałych ośmiu.
    """
    per_akcent: dict[str, Counter] = defaultdict(Counter)
    for (_, akcent), cfg in pary.items():
        kod = str(cfg.get("iso", "")).strip()
        if kod:
            per_akcent[akcent][kod] += 1
    return {akc: licznik.most_common(1)[0][0] for akc, licznik in per_akcent.items()}


# ---------------------------------------------------------------------------
# SILNIK
# ---------------------------------------------------------------------------
def ustaw_silnik() -> Any:
    """Przestawia `core_poliglota` na :data:`DICT_DIR` i czyści jego cache."""
    import core_poliglota as cp
    cp.DICTIONARIES_DIR = str(DICT_DIR)
    cp._CACHE_WARIANTOW.clear()
    cp._CACHE_PODSTAWY.clear()
    return cp


def zastosuj(cp: Any, tekst: str, paczka: str, akcent: str) -> str | None:
    """`zastosuj_reguly_fonetyczne` z przechwyceniem wpadki reguły."""
    try:
        return cp.zastosuj_reguly_fonetyczne(tekst, akcent, paczka)
    except Exception as exc:  # noqa: BLE001 — zła reguła = znalezisko, nie crash
        print(f"⚠️  {paczka}/{akcent}: the engine raised {type(exc).__name__}: {exc}")
        return None


def korpus_paczki(paczka: str, *, tylko_pismo_zrodla: bool = False) -> str:
    """Rodzima proza paczki: `podstawy.yaml::opis` + etykiety/opisy jej akcentów.

    To jedyny tekst w języku paczki, który narzędzie ma pod ręką bez zgadywania.
    `tylko_pismo_zrodla=True` odsiewa znaki spoza alfabetu paczki — bez tego
    bramka pisma wyjścia miała 72/72 fałszywych trafień: opisy cytują symbole
    IPA (`ʃ`, `θ`, `ɪ`) i obce przykłady, których żadna reguła nie tyka.
    """
    czesci = [str(podstawy_paczki(paczka).get("opis", ""))]
    folder = DICT_DIR / paczka / FOLDER
    if folder.is_dir():
        for plik in sorted(folder.glob("*.yaml")):
            cfg = wczytaj_pare(paczka, plik.stem)
            czesci.append(str(cfg.get("etykieta", "")))
            czesci.append(str(cfg.get("opis", "")))
    tekst = "\n".join(czesci)
    if not tylko_pismo_zrodla:
        return tekst
    alfabet = str(podstawy_paczki(paczka).get("alfabet", ""))
    dozwolone = set(alfabet.lower()) | set(alfabet.upper())
    return "".join(z for z in tekst if not z.isalpha() or z in dozwolone)


def _czy_lacinskie(tekst: str) -> float:
    """Udział liter łacińskich wśród liter tekstu (0.0 gdy brak liter)."""
    litery = [z for z in tekst if z.isalpha()]
    if not litery:
        return 0.0
    lac = sum(1 for z in litery if "LATIN" in unicodedata.name(z, ""))
    return lac / len(litery)


# ---------------------------------------------------------------------------
# PRZYKŁADY W PROZIE — wyłuskanie z obsługą łańcuchów i alternatyw
# ---------------------------------------------------------------------------
_CUDZYSLOWY = '„”"«»‘’“'
# Ogniwo łańcucha: „x" → (strzałka unicodowa albo ASCII)
_RE_OGNIWO = re.compile(
    r'[{c}]\s*([^{c}\n]{{1,40}}?)\s*[{c}]\s*(?:→|->)\s*'.format(c=_CUDZYSLOWY))
_RE_CUDZYSLOW = re.compile(
    r'[{c}]\s*([^{c}\n]{{1,80}}?)\s*[{c}]'.format(c=_CUDZYSLOWY))

# Kształt fragmentu ortograficznego albo słowa: litery (dowolnego pisma) plus
# apostrof, kropka i łącznik W ŚRODKU. Odsiewa szum, który wpada w cytaty przy
# guillemetach (klasa cudzysłowów nie rozróżnia « od », więc regex potrafi
# złapać tekst MIĘDZY dwoma cytatami: „ + e/i es = /k/, italiano ").
_RE_KSZTALT_FRAGMENTU = re.compile(
    r"^[^\W\d_]+(?:[.'’\-][^\W\d_]+)*\.?$", re.UNICODE)

# Ten sam filtr dla materiału DOKUMENTACJI (`dopusc_frazy=True` — konsument:
# bramka D2 w `buduj_wielojezyczne_docs.py`). Podręczniki cytują CAŁE FRAZY
# („Dzień dobry" → „Dźoń dobro", „Schöne Grüße" → „Schono Großo"), których
# filtr fragmentu odsiewał — a to właśnie w nich siedział akapit o Samogłoskowcu
# kłamiący w ośmiu językach (v18.19). Dopuszczamy spacje, przecinki i dwukropki
# W ŚRODKU, ale nadal wymagamy litery i zakazujemy znaków, po których poznaje się
# ścieżkę menu albo kod (`/`, `\`, `{`, `` ` ``, `=`, `→` w środku cytatu).
_RE_KSZTALT_FRAZY = re.compile(
    r"^[^\W\d_][^/\\{}`=<>|→\n]*$", re.UNICODE)

# Gloss WYMOWY, nie podmiana: „zana"-ääninen / „zaga"-hljóð / „vater"-Laut.
# Proza mówi wtedy, jak CEL to CZYTA (natywnie), a nie co robi tabela — więc
# nie ma czego porównywać z silnikiem.
_RE_SUFIKS_GLOSSU = re.compile(r"^-[^\W\d_]{2,}")

# Proza zastrzeżona: obietnica warunkowa, której silnik nie umie oddać (nie ma
# reguł kontekstowych). Rozjazd degradujemy wtedy do uwagi — empiria
# `de/finski`: „„v" → „f" oder „v" je nach Kontext".
_ZASTRZEZENIA = (
    " oder ", " albo ", " lub ", " ou bien ", " eða ", " tai ",
    "je nach", "depending", "zależnie", "kontekst", "context", "kontext",
    "riippuen", "según el", "selon le", "a seconda", "в зависимости",
)

# Kontekst HISTORYCZNY/NEGATYWNY: para cytowana jako przykład tego, co robiła
# reguła USUNIĘTA albo błędna. Kalibracja na paczce `de`: `de/francuski` opisuje
# wprost, że dawne `ch→k` psuło świeżo wprowadzone `ch` („Schön" → „Kon"), więc
# ta para jest w prozie ANTY-przykładem — bramka bez tej listy oskarżałaby
# dokumentację o defekt, który sama opisuje jako naprawiony.
_KONTEKST_HISTORYCZNY = (
    # historia reguły
    "früher", "frühere", "ehemal", "alte regel", "zerstör", "dawn", "stara reg",
    "poprzedni", "wcześniej", "kiedyś", "formerly", "previously", "used to",
    "old rule", "no longer", "nicht mehr", "nie ma już", "aiemmin", "áður",
    # jawne „to byłoby błędem" — anty-przykład
    "erróne", "sería", "byłoby", "wäre", "would be", "incorrect", "błędn",
    "psuł", "psuło", "väärin", "villa",
    # kaskada opisana świadomie
    "kaskad", "cascade", "cascada",
    # „tak WŁAŚNIE nie robimy" — para jako karykatura odrzuconego wariantu
    "caricatur", "karykatur", "karikat", "broader", "grates",
)
# Okno kontekstu dla wykrywania zastrzeżeń i historii: szersze niż sam cytat,
# bo wyjaśnienie stoi w tym samym punkcie listy, ale o zdanie dalej.
_OKNO_KONTEKSTU = 160


def lancuchy_z_opisu(
    opis: str, *, dopusc_frazy: bool = False,
) -> list[tuple[str, str, str]]:
    """Pary „źródło → oczekiwane" z prozy, jako `(src, oczekiwane, kontekst)`.

    `dopusc_frazy=True` przełącza filtr kształtu na :data:`_RE_KSZTALT_FRAZY`
    (materiał podręczników — patrz komentarz przy tej stałej). Domyślnie
    obowiązuje węższy filtr fragmentu ortograficznego, skalibrowany na 72
    parach akcentowych.

    Dwie własności materiału, których naiwny regex nie widzi (obie zmierzone
    na 72 plikach — bez nich bramka produkuje ~10 fałszywych alarmów):

    * **łańcuch** — `„shiny" → „sziny" → „szyny"` opisuje DWA kroki tej samej
      reguły; silnik odda ostatni element, nie środkowy,
    * **alternatywa** — `„au/eau" → „о"` to dwa źródła o jednym wyniku.

    `kontekst` to ~80 znaków prozy wokół trafienia — po nim bramka poznaje
    zastrzeżenie („je nach Kontext") i degraduje rozjazd do uwagi.
    """
    wynik: list[tuple[str, str, str]] = []
    ksztalt = _RE_KSZTALT_FRAZY if dopusc_frazy else _RE_KSZTALT_FRAGMENTU
    tekst = opis or ""
    pozycja = 0
    while True:
        m = _RE_OGNIWO.search(tekst, pozycja)
        if m is None:
            break
        ogniwa = [m.group(1).strip()]
        koniec = m.end()
        # Kolejne ogniwa łańcucha: każde kolejne „x" → …
        while True:
            m_next = _RE_OGNIWO.match(tekst, koniec)
            if m_next is None:
                break
            ogniwa.append(m_next.group(1).strip())
            koniec = m_next.end()
        m_last = _RE_CUDZYSLOW.match(tekst, koniec)
        if m_last is None:
            pozycja = m.end()
            continue
        ogniwa.append(m_last.group(1).strip())
        koniec = m_last.end()
        pozycja = koniec

        src, oczekiwane = ogniwa[0], ogniwa[-1]
        if not src or not oczekiwane:
            continue
        # Gloss wymowy („zana"-ääninen) — proza opisuje BRZMIENIE celu, nie
        # podmianę, więc silnik nie ma tu nic do powiedzenia.
        if _RE_SUFIKS_GLOSSU.match(tekst[koniec:koniec + 20]):
            continue
        kontekst = tekst[max(0, m.start() - _OKNO_KONTEKSTU):
                         min(len(tekst), koniec + _OKNO_KONTEKSTU)]
        # Alternatywy: „au/eau" → „о" (jeden wynik) albo równoliczne „a/b" → „x/y".
        czlony_src = [c.strip() for c in src.split("/") if c.strip()]
        czlony_cel = [c.strip() for c in oczekiwane.strip().split("/") if c.strip()]
        if len(czlony_src) > 1 and len(czlony_cel) == len(czlony_src):
            kandydaci = list(zip(czlony_src, czlony_cel))
        elif len(czlony_src) > 1 and len(czlony_cel) == 1:
            kandydaci = [(s, czlony_cel[0]) for s in czlony_src]
        else:
            kandydaci = [(src, oczekiwane)]
        for s, c in kandydaci:
            # Oba końce muszą mieć KSZTAŁT fragmentu ortograficznego (albo
            # frazy, gdy `dopusc_frazy`). Bez tego filtru guillemety wpuszczały
            # do bramki tekst spomiędzy cytatów i produkowały „rozjazdy"
            # na frazach, nie na przykładach.
            if ksztalt.match(s) and ksztalt.match(c):
                wynik.append((s, c, kontekst))
    return wynik


def zastrzezone(kontekst: str) -> bool:
    """Czy rozjazd tej pary ma być UWAGĄ, a nie błędem?

    Dwa powody: proza obwarowuje obietnicę warunkiem, którego silnik nie ma
    („je nach Kontext"), albo cytuje parę jako ANTY-przykład — to, co robiła
    reguła usunięta lub błędna. W obu przypadkach dokumentacja jest uczciwa,
    a bramka bez tego rozróżnienia oskarżałaby ją o własną szczerość.
    """
    nizsze = kontekst.lower()
    return (any(z in nizsze for z in _ZASTRZEZENIA)
            or any(z in nizsze for z in _KONTEKST_HISTORYCZNY))


# ---------------------------------------------------------------------------
# BRAMKI
# ---------------------------------------------------------------------------
def bramka_kontrakt(
    paczka: str, akcent: str, cfg: dict, oczekiwane_iso: str,
) -> list[Znalezisko]:
    """G1: pola, po których SILNIK rozpoznaje i dispatchuje regułę."""
    nazwa = f"{paczka}/{akcent}"
    zn: list[Znalezisko] = []

    def blad(opis: str) -> None:
        zn.append(Znalezisko(nazwa, "G1", opis, blad=True))

    def uwaga(opis: str) -> None:
        zn.append(Znalezisko(nazwa, "G1", opis, blad=False))

    if not cfg:
        blad("plik nie parsuje się do mapy YAML albo jest pusty")
        return zn

    nieznane = sorted(set(map(str, cfg)) - set(KLASY_POL))
    if nieznane:
        blad(f"nieznane pola {nieznane} — dopisz każde do KLASY_POL "
             f"(kontrakt / etykieta / opis / pipeline / reguly); narzędzie nie "
             f"zgaduje, czy pole się lokalizuje, kopiuje, czy wyprowadza")

    if str(cfg.get("id", "")) != akcent:
        blad(f"`id` = {cfg.get('id')!r}, a plik nazywa się {akcent}.yaml — "
             f"Reżyser szuka akcentu po `id` z Księgi Świata")
    if str(cfg.get("kategoria", "")) != "akcent":
        blad(f"`kategoria` = {cfg.get('kategoria')!r}, oczekuję 'akcent'")

    iso = str(cfg.get("iso", "")).strip()
    if iso != oczekiwane_iso:
        blad(f"`iso` = {iso!r}, a pozostałe paczki zgodnie mówią "
             f"{oczekiwane_iso!r} (z tego pola bierze się tag lang wyniku)")
    if iso == paczka:
        blad(f"`iso` == kod paczki ({paczka}) — akcent własnego języka nie ma sensu")
    if iso and not (DICT_DIR / iso).is_dir():
        uwaga(f"`iso` = {iso!r}, ale paczki `dictionaries/{iso}/` nie ma — "
              f"syntezator celu nie jest wspieranym językiem bazowym")

    if not isinstance(cfg.get("kolejnosc"), int):
        blad(f"`kolejnosc` = {cfg.get('kolejnosc')!r} nie jest liczbą całkowitą")

    for pole in FLAGI_PIPELINE:
        if pole not in cfg:
            blad(f"brak flagi pipeline'u `{pole}` — silnik zejdzie na default")
        elif not isinstance(cfg[pole], bool):
            blad(f"`{pole}` = {cfg[pole]!r} nie jest wartością logiczną")
    for pole in FLAGI_ZAWSZE_PRAWDA:
        if cfg.get(pole) is False:
            uwaga(f"`{pole}: false` — w 72/72 parach jest tu `true`; jeśli to "
                  f"świadome, dopisz uzasadnienie w komentarzu pliku")

    for pole in ("etykieta", "opis"):
        if not str(cfg.get(pole, "")).strip():
            blad(f"pole `{pole}` jest puste — user zobaczy w liście goły `id`")

    zamiany = cfg.get("zamiany")
    if not isinstance(zamiany, list) or not zamiany:
        blad("`zamiany` jest puste — akcent bez reguł fonetycznych nic nie robi "
             "(narzędzia czyszczące mają własne pliki i inne narzędzie)")
    return zn


def bramka_martwe_reguly(
    paczka: str, akcent: str, cfg: dict, cp: Any,
) -> list[Znalezisko]:
    """G2: reguły, które nie mają szans zadziałać.

    Cztery klasy, wszystkie deterministyczne:

    1. duplikat `wzor` — druga reguła nigdy nie zobaczy swojego wzorca,
    2. `wzor == zamiana` — reguła no-op,
    3. dwuznak PO zawierającym go jednoznaku (`sz` po `s`),
    4. **zjedzenie przez pre-pass** — patrz nagłówek modułu. Rozdzielamy
       stratę REALNĄ (`zamiana` różna od spłaszczonego wzorca — reguła coś
       obiecywała) od nieszkodliwego duplikatu (`ü → u`, gdy pre-pass i tak
       daje `u`).
    """
    nazwa = f"{paczka}/{akcent}"
    zn: list[Znalezisko] = []
    zamiany = cfg.get("zamiany")
    if not isinstance(zamiany, list):
        return zn

    proste = [p for p in zamiany if isinstance(p, dict) and not p.get("regex")]
    widziane: set[str] = set()
    for idx, para in enumerate(zamiany):
        if not isinstance(para, dict):
            zn.append(Znalezisko(nazwa, "G2",
                                 f"`zamiany[{idx}]` nie jest mapą {{wzor, zamiana}}",
                                 blad=True))
            continue
        wzor = str(para.get("wzor", ""))
        zamiana = str(para.get("zamiana", ""))
        if not wzor:
            zn.append(Znalezisko(nazwa, "G2", f"`zamiany[{idx}]` ma pusty `wzor`",
                                 blad=True))
            continue
        if para.get("regex"):
            try:
                re.compile(wzor)
            except re.error as exc:
                zn.append(Znalezisko(nazwa, "G2",
                                     f"`zamiany[{idx}].wzor` = {wzor!r} nie "
                                     f"kompiluje się jako regex: {exc}", blad=True))
            continue
        if wzor in widziane:
            zn.append(Znalezisko(nazwa, "G2",
                                 f"`zamiany[{idx}].wzor` = {wzor!r} to duplikat — "
                                 f"druga reguła nigdy nie zadziała", blad=True))
        widziane.add(wzor)
        if wzor == zamiana:
            zn.append(Znalezisko(nazwa, "G2",
                                 f"`zamiany[{idx}]`: {wzor!r} → {zamiana!r} to "
                                 f"reguła no-op", blad=True))
        if len(wzor) > 1 and para in proste:
            poprzednie = proste[:proste.index(para)]
            # Wzorzec bywa PRODUKOWANY przez wcześniejszą regułę — wtedy nie ma
            # znaczenia, że któraś rozbija go w tekście WEJŚCIOWYM, bo reguła
            # pracuje na wyniku (wzorzec-warta: `de/hiszpanski` prowadzi „tsch"
            # przez „jj", żeby „ch" → „j" nie zjadło świeżego /tʃ/). Bez tego
            # rozróżnienia bramka ubijała jedyny mechanizm, jakim sekwencyjne
            # `str.replace` umie obsłużyć trzy nachodzące na siebie dźwięki.
            odtwarzany = any(wzor in str(wcz.get("zamiana", "")) for wcz in poprzednie)
            for wcz in ([] if odtwarzany else poprzednie):
                krotszy = str(wcz.get("wzor", ""))
                if krotszy and len(krotszy) < len(wzor) and krotszy in wzor:
                    zn.append(Znalezisko(
                        nazwa, "G2",
                        f"{wzor!r} stoi PO regule {krotszy!r}, która go rozbija "
                        f"— dłuższy wzorzec nie ma szans (dwuznaki PRZED "
                        f"jednoznakami)", blad=True))
                    break

    # Klasa 4: pre-pass diakrytyków.
    if cfg.get("usun_polskie_znaki"):
        podstawy = cp._zaladuj_podstawy(paczka)
        for idx, para in enumerate(zamiany):
            if not isinstance(para, dict) or para.get("regex"):
                continue
            wzor = str(para.get("wzor", ""))
            if not wzor:
                continue
            po_prepass = cp._usun_polskie_znaki(wzor, podstawy)
            if po_prepass == wzor:
                continue
            zamiana = str(para.get("zamiana", ""))
            realna_strata = po_prepass != zamiana
            zn.append(Znalezisko(
                nazwa, "G2",
                f"`zamiany[{idx}]`: {wzor!r} → {zamiana!r} jest NIEOSIĄGALNA — "
                f"`usun_polskie_znaki: true` spłaszcza wzorzec do {po_prepass!r} "
                f"PRZED listą `zamiany`"
                + ("; reguła obiecywała inny wynik, więc to realna strata "
                   "(napraw flagą `usun_polskie_znaki: false` jak paczki es/fr "
                   "albo usuń regułę i prozę o niej)"
                   if realna_strata else
                   "; pre-pass daje ten sam wynik, więc to nieszkodliwy duplikat"),
                blad=realna_strata))
    return zn


MARKER_KASKADY = "KASKADA ZAMIERZONA"


def kaskady_zamierzone(paczka: str, akcent: str) -> set[str]:
    """Wzorce reguł, nad którymi stoi komentarz z :data:`MARKER_KASKADY`.

    Świadomy łańcuch zamian jest własnością DANYCH, nie pamięci recenzenta:
    `de/hiszpanski` prowadzi „tsch" przez wartę „jj", żeby reguła „ch" → „j"
    nie zjadła świeżego /tʃ/, a `fr/finski` naprawia „uu" → „yy" powstałe
    z „ou" → „uu". Bez tej deklaracji G3 raportowałaby oba łańcuchy w każdym
    przebiegu, a stała uwaga w audycie przestaje być sygnałem.

    Marker obowiązuje od swojego bloku komentarza do NASTĘPNEGO bloku (tak
    działają nagłówki sekcji w tych plikach), więc nagłówek grupy oznacza całą
    grupę, a komentarz nad jedną regułą — tylko ją i jej warianty wielkości
    liter stojące niżej.
    """
    plik = DICT_DIR / paczka / FOLDER / f"{akcent}.yaml"
    try:
        linie = plik.read_text(encoding="utf-8").split("\n")
    except OSError:
        return set()
    oznaczone: set[str] = set()
    blok = poprzednia_komentarz = False
    for linia in linie:
        naga = linia.strip()
        if naga.startswith("#"):
            if not poprzednia_komentarz:
                blok = False
            blok = blok or MARKER_KASKADY in naga
            poprzednia_komentarz = True
            continue
        poprzednia_komentarz = False
        trafienie = re.search(r"""wzor:\s*(["'])(.*?)\1""", linia)
        if trafienie and blok:
            oznaczone.add(trafienie.group(2))
    return oznaczone


def bramka_cieniowanie(paczka: str, akcent: str, cfg: dict) -> list[Znalezisko]:
    """G3: reguła wprowadza znak, który łapie późniejsza reguła (uwaga)."""
    nazwa = f"{paczka}/{akcent}"
    zamiany = cfg.get("zamiany")
    if not isinstance(zamiany, list):
        return []
    pary = [(str(p.get("wzor", "")), str(p.get("zamiana", "")), bool(p.get("regex")))
            for p in zamiany if isinstance(p, dict)]
    zamierzone = kaskady_zamierzone(paczka, akcent)
    zn: list[Znalezisko] = []
    for i, (wzor_i, zam_i, regex_i) in enumerate(pary):
        if not zam_i or regex_i or wzor_i in zamierzone:
            continue
        for j in range(i + 1, len(pary)):
            wzor_j, _, regex_j = pary[j]
            if not wzor_j or regex_j:
                continue
            if wzor_j in zam_i:
                zn.append(Znalezisko(
                    nazwa, "G3",
                    f"#{i + 1} ({wzor_i!r}→{zam_i!r}) wprowadza wzorzec reguły "
                    f"#{j + 1} ({wzor_j!r}) — jeśli kaskada nie jest zamierzona, "
                    f"zamień TARGET pierwszy, SOURCE potem", blad=False))
                break
    return zn


def bramka_parytet_liter(paczka: str, akcent: str, cfg: dict) -> list[Znalezisko]:
    """G4: reguła małoliterowa bez wariantu wielkoliterowego (uwaga)."""
    nazwa = f"{paczka}/{akcent}"
    zamiany = cfg.get("zamiany")
    if not isinstance(zamiany, list):
        return []
    wzory = {str(p.get("wzor", "")) for p in zamiany
             if isinstance(p, dict) and not p.get("regex")}
    braki: list[str] = []
    for wzor in sorted(wzory):
        if not wzor or not wzor[:1].islower():
            continue
        # `ß`.upper() == "SS" — litera bez odpowiednika wielkiego, legalny wyjątek.
        if len(wzor.upper()) != len(wzor):
            continue
        if wzor.capitalize() not in wzory and wzor.upper() not in wzory:
            braki.append(wzor)
    if braki:
        return [Znalezisko(
            nazwa, "G4",
            f"reguły bez wariantu wielkoliterowego: {braki[:8]} — słowo na "
            f"początku zdania nie dostanie akcentu", blad=False)]
    return []


def bramka_wersaliki(paczka: str, akcent: str, cfg: dict) -> list[Znalezisko]:
    """G8: reguła o ≥2 literach bez wariantu pisanego WERSALIKAMI (uwaga).

    `str.replace` jest wrażliwe na wielkość liter, więc `Sz → Sh` nie tyka
    nagłówka „SZKIC PROMPTU" ani wykrzyknienia pisanego wersalikami. G4 pilnuje
    wariantu z WIELKIEJ litery (początek zdania), ta bramka — wariantu ALL-CAPS.
    Jednoliterowe reguły są poza zakresem: dla nich wariant wielkoliterowy
    z G4 JEST wariantem wersalikowym.

    Wzorce porównujemy OBCIĘTE z białych znaków, bo w jednej parze wielka
    litera zastępuje granicę słowa (`Sp` → `Шп`, „sp" na początku wyrazu),
    a jej odpowiednik wersalikowy musi tę granicę nosić jawnie (` SP`) —
    w tekście pisanym wersalikami proxy z wielkiej litery nie istnieje.
    """
    nazwa = f"{paczka}/{akcent}"
    zamiany = cfg.get("zamiany")
    if not isinstance(zamiany, list):
        return []
    wzory = [str(p.get("wzor", "")) for p in zamiany
             if isinstance(p, dict) and not p.get("regex")]
    wersaliki = {w.strip().upper() for w in wzory
                 if w.strip() and w.strip() == w.strip().upper()
                 and w.strip() != w.strip().lower()}
    braki: list[str] = []
    for wzor in sorted(set(wzory)):
        rdzen = wzor.strip()
        if len([z for z in rdzen if z.isalpha()]) < 2:
            continue
        gorny = rdzen.upper()
        # „ß".upper() == „SS" — zmiana długości znaczy, że to inny wzorzec.
        if gorny == rdzen or len(gorny) != len(rdzen) or gorny in wersaliki:
            continue
        braki.append(wzor)
    if braki:
        return [Znalezisko(
            nazwa, "G8",
            f"reguły wielozankowe bez wariantu ALL-CAPS: {braki[:8]} — tekst "
            f"pisany wersalikami przejdzie obok nich bez akcentu", blad=False)]
    return []


def bramka_pismo_wyjscia(
    paczka: str, akcent: str, cfg: dict, cp: Any,
) -> list[Znalezisko]:
    """G5: akcent transliterujący musi wyczerpywać pismo źródła.

    Bramka działa TYLKO dla par, w których pismo wyjścia jest inne niż pismo
    źródła (dziś: akcenty na cyrylicę). Dla par łacińsko-łacińskich kryterium
    „wynik mieści się w alfabecie celu" jest FAŁSZYWE i dawało 72/72 alarmów:
    włoski alfabet nie ma `k`/`x`/`y`, a włoski syntezator te litery czyta bez
    problemu — celem akcentu jest wymowa, nie ortografia celu.
    """
    nazwa = f"{paczka}/{akcent}"
    zn: list[Znalezisko] = []
    korpus = korpus_paczki(paczka, tylko_pismo_zrodla=True)
    wynik = zastosuj(cp, korpus, paczka, akcent)
    if wynik is None:
        return [Znalezisko(nazwa, "G5", "silnik nie przetworzył korpusu paczki",
                           blad=True)]

    lac_wejscie = _czy_lacinskie(korpus)
    lac_wyjscie = _czy_lacinskie(wynik)
    zmiana_pisma = abs(lac_wejscie - lac_wyjscie) > 0.5
    if not zmiana_pisma:
        return zn

    # KALIBRACJA: flaga jest martwa, gdy WYJŚCIE jest niełacińskie — nie gdy
    # zmienia się pismo. `sklej_pojedyncze_litery` pracuje na wyniku, więc dla
    # akcentów paczki `ru` (cyrylica → łacinka) działa normalnie; pierwsza
    # wersja bramki oskarżała je niesłusznie (8 fałszywych alarmów na 11).
    if cfg.get("skleja_pojedyncze_litery") and lac_wyjscie < 0.5:
        zn.append(Znalezisko(
            nazwa, "G5",
            "`skleja_pojedyncze_litery: true` przy NIEŁACIŃSKIM wyjściu to "
            "flaga MARTWA (regex silnika ma klasę [a-z]); kanon paczek "
            "en/fi/is/it/pl stawia tu `false`", blad=False))

    # Resztki pisma źródła = dziura w tablicy transliteracji.
    resztki = Counter(
        z for z in wynik
        if z.isalpha() and ("LATIN" in unicodedata.name(z, "")) == (lac_wejscie > 0.5)
    )
    if resztki:
        podglad = ", ".join(f"{z!r}×{n}" for z, n in resztki.most_common(6))
        zn.append(Znalezisko(
            nazwa, "G5",
            f"po transliteracji zostały litery pisma ŹRÓDŁA ({podglad}) — "
            f"tablica `zamiany` nie pokrywa całego alfabetu", blad=True))
    return zn


def bramka_przyklady(
    paczka: str, akcent: str, cfg: dict, cp: Any,
) -> list[Znalezisko]:
    """G6: każdą parę „X → Y" z `opis` przelicz FAKTYCZNYM silnikiem."""
    nazwa = f"{paczka}/{akcent}"
    zn: list[Znalezisko] = []
    for src, oczekiwane, kontekst in lancuchy_z_opisu(str(cfg.get("opis", ""))):
        wynik = zastosuj(cp, src, paczka, akcent)
        if wynik is None or wynik == oczekiwane:
            continue
        # Czy w wyniku uczestniczyła reguła POZYCYJNA (`regex: true`)? Jeśli
        # tak, atomowy odczyt bramki bywa mylący: `з\b → с` (rosyjskie
        # ubezdźwięcznienie w wygłosie) zamienia izolowane „th" na „с", choć
        # w prawdziwym słowie („the" → „зэ") proza ma rację. Bramka NIE udaje
        # wtedy, że wie — mówi wprost, że nie rozstrzyga. Uczciwsze niż
        # milczenie (przeoczony defekt) i niż oskarżenie (fałszywy alarm).
        pozycyjna = regex_uczestniczyl(cfg, src)
        miekkie = pozycyjna or zastrzezone(kontekst)
        powod = ""
        if pozycyjna:
            powod = (" — w wyniku uczestniczy reguła pozycyjna `regex: true`, "
                     "więc bramka NIE ROZSTRZYGA: sprawdź ten przykład ręcznie "
                     "na całym słowie")
        elif miekkie:
            powod = (" (proza zastrzeżona warunkiem albo cytuje anty-przykład "
                     "— uwaga)")
        zn.append(Znalezisko(
            nazwa, "G6",
            f"przykład {src!r} → obiecuje {oczekiwane!r}, a silnik daje "
            f"{wynik!r}{powod}",
            blad=not miekkie))
    return zn


def regex_uczestniczyl(cfg: dict, src: str) -> bool:
    """Czy przy przetwarzaniu `src` zmieniła tekst któraś reguła `regex: true`?

    Powtarzamy pętlę silnika (sekwencyjnie, w kolejności listy) i patrzymy nie
    na to, czy regex PASUJE do wejścia, a czy realnie zadziałał — bo wzorzec
    pozycyjny bywa dopasowany dopiero do WYNIKU wcześniejszych reguł
    (`з\\b` po `th → з`), a wtedy właśnie atomowy test bramki jest zwodniczy.
    """
    tekst = src
    for para in cfg.get("zamiany") or []:
        if not isinstance(para, dict):
            continue
        wzor, zamiana = str(para.get("wzor", "")), str(para.get("zamiana", ""))
        if not wzor:
            continue
        if para.get("regex"):
            try:
                nowy = re.sub(wzor, zamiana, tekst)
            except re.error:
                continue
            if nowy != tekst:
                return True
            tekst = nowy
        else:
            tekst = tekst.replace(wzor, zamiana)
    return False


def bramka_kolejnosc(pary: dict[tuple[str, str], dict]) -> list[Znalezisko]:
    """G7: duplikat `kolejnosc` w obrębie paczki (uwaga).

    Silnik sortuje `(kolejnosc, etykieta)`, więc remis NIE psuje
    determinizmu listy — tylko wstawia alfabet w miejsce zamierzonej pozycji.
    Liczymy razem z trzema narzędziami, bo lądują w tej samej liście GUI.
    """
    zn: list[Znalezisko] = []
    for paczka in sorted({p for p, _ in pary}):
        folder = DICT_DIR / paczka / FOLDER
        wartosci: list[tuple[Any, str]] = []
        for plik in sorted(folder.glob("*.yaml")):
            cfg = wczytaj_pare(paczka, plik.stem)
            wartosci.append((cfg.get("kolejnosc"), plik.stem))
        liczby = [k for k, _ in wartosci]
        for wartosc in sorted({k for k in liczby if liczby.count(k) > 1},
                              key=lambda x: (x is None, x)):
            kolizja = [n for k, n in wartosci if k == wartosc]
            zn.append(Znalezisko(
                f"{paczka}/*", "G7",
                f"`kolejnosc: {wartosc}` powtarza się w {kolizja} — pozycję "
                f"w liście rozstrzyga wtedy alfabet etykiet, nie zamysł autora",
                blad=False))
    return zn


def _pierwsza_litera(tekst: str) -> str:
    """Pierwsza litera napisu (małą literą) albo pusty napis."""
    return next((z.lower() for z in tekst if z.isalpha()), "")


def _pismo(znak: str) -> str:
    """Nazwa pisma znaku (`LATIN`, `CYRILLIC`, …) — do odsiania cudzych alfabetów."""
    return unicodedata.name(znak, " ").split()[0] if znak else ""


def bramka_tablica_prepassu(pary: dict[tuple[str, str], dict]) -> list[Znalezisko]:
    """G9: tablica pre-passu paczki wbrew opinii jej WŁASNYCH akcentów (18.22).

    `podstawy.yaml::polskie_znaki` spłaszcza diakrytyki PRZED regułami akcentu,
    więc jej wpis obowiązuje w każdym akcencie z `usun_polskie_znaki: true` —
    a akcenty z flagą `false` mają o tym samym znaku opinię WŁASNĄ, wyrażoną
    regułą. Rozjazd między jednym a drugim to defekt: paczka `fr` spłaszczała
    „ç" do „c", choć jej własne akcenty (`niemiecki`, `polski`) czytają cedyllę
    jako /s/ — i sześć par z pre-passem czytało „français" przez /k/, bo regułę
    przejmowało „c" (dług C roadmapy, spłacony w 18.22).

    Kryterium jest OBLICZALNE, nie ocenne — porównujemy PIERWSZĄ literę wyniku
    (niemieckie „ss" i polskie „s" zapisują ten sam dźwięk, więc zgadzają się),
    a opinie w innym piśmie odsiewamy (`pl/rosyjski` mapuje „ł" na „л" — to
    nie spór o dźwięk, to inny alfabet). Jednomyślny rozjazd = BŁĄD (tablica
    jest po prostu zła); podzielone opinie = uwaga (bywają zapisem celu).
    """
    zn: list[Znalezisko] = []
    for paczka in sorted({p for p, _ in pary}):
        tabela = {str(r.get("wzor", "")): str(r.get("zamiana", ""))
                  for r in podstawy_paczki(paczka).get("polskie_znaki", [])
                  if isinstance(r, dict)}
        z_prepassem = sorted(a for (p, a), cfg in pary.items()
                             if p == paczka and cfg.get("usun_polskie_znaki"))
        if not tabela or not z_prepassem:
            continue  # tablica nie działa w żadnym akcencie — nie ma o co pytać
        opinie: dict[str, dict[str, str]] = defaultdict(dict)
        for (p, akcent), cfg in pary.items():
            if p != paczka or cfg.get("usun_polskie_znaki"):
                continue
            for regula in cfg.get("zamiany") or []:
                if regula.get("regex"):
                    continue
                wzor = str(regula.get("wzor", ""))
                if wzor in tabela:
                    opinie[wzor][akcent] = str(regula.get("zamiana", ""))
        for znak, per_akcent in sorted(opinie.items()):
            z_tabeli = _pierwsza_litera(tabela[znak])
            wazne = {a: z for a, z in per_akcent.items()
                     if _pismo(_pierwsza_litera(z)) == _pismo(z_tabeli)}
            sporne = {a: z for a, z in wazne.items()
                      if _pierwsza_litera(z) != z_tabeli}
            if not sporne:
                continue
            jednomyslnie = len(sporne) == len(wazne)
            glosy = ", ".join(f"{a} → {z!r}" for a, z in sorted(sporne.items()))
            zn.append(Znalezisko(
                f"{paczka}/podstawy", "G9",
                f"pre-pass spłaszcza {znak!r} do {tabela[znak]!r}, a własne akcenty "
                f"paczki czytają ten znak inaczej ({glosy})"
                + (f" — zgodnie, więc tablica obowiązująca w {len(z_prepassem)} "
                   f"akcentach z pre-passem jest błędna" if jednomyslnie else
                   " — opinie podzielone, sprawdź czy to zapis celu"),
                blad=jednomyslnie))
    return zn


# ---------------------------------------------------------------------------
# AUDYT — przebieg
# ---------------------------------------------------------------------------
def audytuj(
    kody_paczek: list[str] | None = None,
    akcenty: list[str] | None = None,
) -> tuple[list[Znalezisko], int]:
    """Uruchamia wszystkie bramki. Zwraca `(znaleziska, liczba_par)`."""
    pary = pary_akcentowe()
    if not pary:
        raise SystemExit(f"❌ No accent pairs in {DICT_DIR}")
    iso_konsensus = konsensus_iso(pary)
    cp = ustaw_silnik()

    wybrane = {
        (pkg, akc): cfg for (pkg, akc), cfg in pary.items()
        if (not kody_paczek or pkg in kody_paczek)
        and (not akcenty or akc in akcenty)
    }
    znaleziska: list[Znalezisko] = []
    for (pkg, akc), cfg in sorted(wybrane.items()):
        oczekiwane = iso_konsensus.get(akc, "")
        znaleziska += bramka_kontrakt(pkg, akc, cfg, oczekiwane)
        if not cfg:
            continue
        znaleziska += bramka_martwe_reguly(pkg, akc, cfg, cp)
        znaleziska += bramka_cieniowanie(pkg, akc, cfg)
        znaleziska += bramka_parytet_liter(pkg, akc, cfg)
        znaleziska += bramka_wersaliki(pkg, akc, cfg)
        znaleziska += bramka_pismo_wyjscia(pkg, akc, cfg, cp)
        znaleziska += bramka_przyklady(pkg, akc, cfg, cp)
    if not kody_paczek and not akcenty:
        znaleziska += bramka_kolejnosc(pary)
        znaleziska += bramka_tablica_prepassu(pary)
    return znaleziska, len(wybrane)


def grupuj(znaleziska: list[Znalezisko]) -> dict[str, list[Znalezisko]]:
    per_bramka: dict[str, list[Znalezisko]] = defaultdict(list)
    for z in znaleziska:
        per_bramka[z.bramka].append(z)
    return per_bramka


def raport_markdown(znaleziska: list[Znalezisko], ile_par: int) -> str:
    """Raport audytu do pliku (długa treść nie idzie do terminala)."""
    bledy = [z for z in znaleziska if z.blad]
    uwagi = [z for z in znaleziska if not z.blad]
    linie = [
        "# Audyt par akcentowych Poligloty",
        "",
        f"Par w zakresie: **{ile_par}**. Błędów: **{len(bledy)}**, "
        f"uwag: **{len(uwagi)}**.",
        "",
        "Bramki: G1 kontrakt pliku · G2 martwe reguły · G3 cieniowanie "
        "sekwencyjne · G4 parytet wielkości liter · G5 pismo wyjścia · "
        "G6 przykłady przeliczone silnikiem · G7 kolejność w liście · "
        "G8 wariant ALL-CAPS dwuznaku · G9 tablica pre-passu vs. własne akcenty.",
        "",
    ]
    for tytul, zbior in (("Błędy (blokują)", bledy), ("Uwagi (triaż)", uwagi)):
        linie += [f"## {tytul}", ""]
        if not zbior:
            linie += ["Brak.", ""]
            continue
        for bramka, lista in sorted(grupuj(zbior).items()):
            linie += [f"### {bramka} ({len(lista)})", ""]
            for z in lista:
                linie.append(f"- `{z.para}` — {z.opis}")
            linie.append("")
    return "\n".join(linie)


def wypisz_podsumowanie(znaleziska: list[Znalezisko], ile_par: int) -> None:
    bledy = [z for z in znaleziska if z.blad]
    uwagi = [z for z in znaleziska if not z.blad]
    print(f"\n========== ACCENT AUDIT ({ile_par} pairs) ==========")
    for bramka, lista in sorted(grupuj(znaleziska).items()):
        ile_b = sum(1 for z in lista if z.blad)
        print(f"  {bramka}: {len(lista)} hit(s) ({ile_b} error(s))")
    print(f"{'✅ No findings.' if not bledy else f'❌ Errors: {len(bledy)}'}"
          f"  (notes: {len(uwagi)})")


# ---------------------------------------------------------------------------
# ŚCIEŻKA GENERUJĄCA — NOWY JĘZYK (dwa kierunki)
# ---------------------------------------------------------------------------
def nazwa_pliku_akcentu(nazwa_polska: str) -> str:
    """`fiński` → `finski`, `włoski` → `wloski` (nazwa pliku = identyfikator).

    Nazwy plików akcentów są polskimi przymiotnikami BEZ diakrytyków —
    zweryfikowane na 72 parach (`finski`, `wloski`, `hiszpanski`). Fold robimy
    przez NFKD plus ręczne `ł`, którego dekompozycja nie rozbija.
    """
    bez_l = nazwa_polska.replace("ł", "l").replace("Ł", "L")
    rozlozone = unicodedata.normalize("NFKD", bez_l)
    return "".join(z for z in rozlozone if not unicodedata.combining(z)).lower()


def _mapa_akcentow(pary: dict[tuple[str, str], dict]) -> dict[str, str]:
    """Kod ISO → nazwa pliku akcentu (z istniejących par)."""
    return {kod: akc for akc, kod in konsensus_iso(pary).items()}


def glosy_konsensusu(pary: dict[tuple[str, str], dict], akcent: str) -> list[str]:
    """Nazwy głosów TTS wymieniane w etykietach tego akcentu w innych paczkach.

    Głosy są REALNYMI nazwami z NVDA/Vocalizera/OneCore, więc dla nowej paczki
    bierzemy je z paczek istniejących zamiast pytać model (halucynacja nazwy
    głosu jest niesprawdzalna dla recenzenta, który tego syntezatora nie ma).
    Zbiory różnią się redakcyjnie per paczka (`Satu/Mikko` vs `Onni/Heidi`) —
    dlatego bierzemy najczęstsze, nie sumę.
    """
    licznik: Counter = Counter()
    for (_, akc), cfg in pary.items():
        if akc != akcent:
            continue
        etykieta = str(cfg.get("etykieta", ""))
        wnetrze = re.search(r"\(([^)]*)\)", etykieta)
        if not wnetrze:
            continue
        for czlon in re.split(r"[/,]", wnetrze.group(1)):
            czlon = re.sub(r"^\s*(?:np\.|z\.\s?B\.|e\.g\.|esim\.|t\.d\.|např\.)\s*",
                           "", czlon.strip())
            czlon = czlon.strip(" .")
            if czlon and czlon[:1].isupper() and " " not in czlon:
                licznik[czlon] += 1
    return [glos for glos, _ in licznik.most_common(3)]


def tabele_precedensowe(
    pary: dict[tuple[str, str], dict], akcent: str, pomijana: str, *, ile: int = 3,
) -> list[dict[str, Any]]:
    """Tabele innych paczek dla TEGO SAMEGO celu — jako precedens fonologiczny.

    Empiria z testu bojowego (replay `pl/finski`, dwa przebiegi): model
    wyprowadzał tabelę spójną i obronną, ale DWA RAZY zgubił ubezdźwięcznienie
    `b/d/g → p/t/k`, czyli najsilniejszy marker fińskości — bo litery b, d, g
    SĄ w fińskim alfabecie, więc nic nie wyglądało na brakujące. Dokręcanie
    prompta („przejdź osie fonologiczne") nie pomogło.

    Dźwignia jest w DANYCH, nie w promptcie: osiem istniejących tabel na ten
    sam cel koduje to, co należy do SYNTEZATORA, a nie do źródła. Jeśli każda
    z nich ubezdźwięcznia zwarte, to jest własność celu — i model dostaje ją
    jako fakt, nie jako swoją pamięć fonologiczną. Ten sam wzorzec, którym
    `existing_terminology` naprawiło rozjazd terminologii w v18.17.
    """
    wynik: list[dict[str, Any]] = []
    for (pkg, akc), cfg in sorted(pary.items()):
        if akc != akcent or pkg == pomijana:
            continue
        reguly = [f"{p.get('wzor')}>{p.get('zamiana')}"
                  for p in cfg.get("zamiany") or [] if isinstance(p, dict)]
        if not reguly:
            continue
        wynik.append({
            "source_language": pkg,
            "rules": " ".join(reguly),
            "removes_source_diacritics_first": bool(cfg.get("usun_polskie_znaki")),
        })
        if len(wynik) >= ile:
            break
    return wynik


def _pytania_pary(
    kod_zrodla: str, kod_celu: str, nazwa_zrodla: str, nazwa_celu: str,
) -> list[tuple[int, str, str]]:
    """Trzy pozycje payloadu: reguły, etykieta, opis.

    Świadomie ten sam kontrakt `id → target` co u pięciu braci (rdzeń rodziny),
    z odpowiedzią parsowaną liniowo — wzorzec `_wygeneruj_skrotowce_llm`
    z doc-autotłumacza. Nowy schemat structured-outputs byłby tu szóstą
    konwencją bez zysku.
    """
    return [
        (0, "phonetic_rules",
         f"PHONETIC SUBSTITUTION TABLE for reading {nazwa_zrodla} "
         f"({kod_zrodla}) text with a {nazwa_celu} ({kod_celu}) "
         f"text-to-speech voice. One rule per line, in the form\n"
         f"    pattern | replacement\n"
         f"applied SEQUENTIALLY by `str.replace` — so ORDER MATTERS and every "
         f"rule sees the output of the previous one. Rules:\n"
         f"1. Put MULTI-CHARACTER patterns BEFORE any single character they "
         f"contain (a rule for `sch` must precede the rule for `s`).\n"
         f"2. Give a separate line for the capitalized form of every rule "
         f"whose pattern starts with a letter.\n"
         f"3. Never introduce a character that a LATER rule consumes, unless "
         f"the cascade is what you want.\n"
         f"4. Patterns are literal text, not regex.\n"
         f"5. 12-40 rules. No commentary, no numbering, no code fences."),
        (1, "label",
         f"DROPDOWN LABEL for this accent, written in {nazwa_zrodla} — the "
         f"language of the pack's user interface. Follow the shape used by the "
         f"pack: the {nazwa_celu} language name in {nazwa_zrodla}, then the "
         f"example voice names in parentheses. Answer with the label only."),
        (2, "description",
         f"TEACHING DESCRIPTION shown as help for this accent, in "
         f"{nazwa_zrodla}. Two short paragraphs: what the accent does to "
         f"{nazwa_zrodla} text and why a {nazwa_celu} voice needs it, then a "
         f"list of the MOST IMPORTANT substitutions. Every worked example you "
         f"write will be RE-RUN through the engine and the file is rejected if "
         f"the engine disagrees, so quote only pairs that follow from the rules "
         f"you gave above. No commentary outside the description."),
    ]


def _PROMPT_GENERATORA(
    kod_zrodla: str, kod_celu: str, nazwa_zrodla: str, nazwa_celu: str,
) -> str:
    """Prompt systemowy ścieżki generującej (po angielsku, jak u braci)."""
    return (
        "# Role\n"
        "You are a phonetician building data files for a desktop accessibility "
        "application used mostly by BLIND people with screen readers. The app "
        "can read a text in one language using a speech synthesizer of ANOTHER "
        "language, and to make that sound like a native speaker of the second "
        "language reading the first, it deliberately MIS-SPELLS the text so the "
        "foreign synthesizer's own reading rules produce the intended sounds.\n"
        f"Source language of the text: **{nazwa_zrodla}** ({kod_zrodla}).\n"
        f"Language of the synthesizer: **{nazwa_celu}** ({kod_celu}).\n\n"
        + tlumacz_bramki.blok_anty_meta_skip(przewaga_promptow=False) + "\n"
        "## What you are producing\n"
        "You are NOT translating. You are DERIVING a phonetic rule for one "
        "ordered pair of writing systems. The same target language paired with "
        "a different source language gets a completely different table.\n\n"
        "## Task\n"
        "You receive a JSON object with an `items` field — a list of "
        "`{\"id\": int, \"kind\": str, \"source\": str}` objects, where `source` "
        "is an INSTRUCTION describing what to produce. Return JSON of the "
        "shape:\n"
        "  `{\"translations\": [{\"id\": int, \"target\": str}, ...]}`\n"
        "Each object MUST carry exactly the same `id` as its instruction.\n\n"
        "## Hard rules (a violation blocks the file from being written)\n"
        "1. **The engine applies the table with sequential `str.replace`.** No "
        "regex, no lookaround, no context conditions — a rule that needs "
        "\"only at the start of a word\" cannot be expressed and must not be "
        "promised in the description.\n"
        "2. **`source_diacritics_removed_first`, when present in the payload, "
        "lists characters that a PRE-PASS strips BEFORE your table runs.** A "
        "rule whose pattern contains one of them is unreachable — either do not "
        "write it, or write it and say so in `notes`, and the parent script will "
        "switch the pre-pass off for this pair.\n"
        "3. **`target_alphabet` is the inventory the synthesizer reads "
        "natively.** Prefer replacements built from it. Letters outside it are "
        "allowed only when the target voice reads them correctly anyway.\n"
        "4. Keep the source language's own letters where the target voice "
        "happens to read them correctly — every rule must earn its place.\n"
        "5. `existing_terminology`, when present, is how this pack already "
        "names things. Reuse its wording for the label.\n"
        "6. **Every rule of two letters or more needs THREE case variants: "
        "lowercase, Capitalised and ALL-CAPS** (`sz`, `Sz`, `SZ`). "
        "`str.replace` is case-sensitive, so a table with only the first two "
        "leaves headings and shouting written in capitals unaccented — that gap "
        "existed in 25 of the 72 hand-written pairs until v18.21. Two "
        "exceptions: a single-letter rule needs only the two obvious variants, "
        "and a rule that uses the capital letter AS A PROXY for the start of a "
        "word cannot have a plain ALL-CAPS twin (the proxy does not exist in "
        "text written in capitals) — spell the boundary out as a leading space "
        "instead, as `de/akcenty/rosyjski.yaml` does for ` SP`.\n"
        "7. **Never write a rule to fix the CASE OF A RESULT.** Since 18.22 the "
        "engine lifts a replacement to capitals whenever the match sits inside an "
        "all-caps word, so a single-letter rule with a multi-letter replacement "
        "(`Ж` → `Zh`) already yields `ZHDAT` for `ЖДАТЬ`. A positional rule for "
        "that is dead weight.\n\n"
        "## `previous_attempt_problems` MEANS YOUR PREVIOUS ANSWER WAS REJECTED\n"
        "When the payload carries that field (the diagnostics are in Polish, the "
        "language of the parent script), a gate already re-ran the ENGINE on your "
        "previous table and refused it for exactly those reasons. Fix them and "
        "change nothing else. The most common one: a worked example in the "
        "description that does not survive your OWN table — remember that every "
        "rule applies to every occurrence, including the first letter of the "
        "example word.\n\n"
        "## `precedent_tables_for_same_target` — the strongest signal you get\n"
        "When the payload carries that field, those are REAL, hand-written and "
        "reviewed tables that adapt OTHER source languages for THIS SAME "
        "synthesizer. Do not copy them — their source language is different, so "
        "most of their patterns do not occur in your source. Read them for one "
        "thing: **a phonological class that EVERY one of them handles is a "
        "property of the TARGET voice, and your table must handle it too, in "
        "your source's own spelling.** If all of them turn voiced plosives into "
        "voiceless ones, the target has no voiced plosives — that is a fact "
        "about the synthesizer, not a coincidence of those languages.\n\n"
        "## Axes you must walk before writing the table\n"
        "Go through every axis below and decide explicitly whether it applies. "
        "This list exists because a table can look plausible and still miss the "
        "single most audible feature of the accent — a derivation that skipped "
        "the voicing axis for a Finnish voice produced text that no listener "
        "would call Finnish, even though every rule in it was defensible.\n"
        "1. **Voicing contrasts the target lacks.** If the target has no voiced "
        "plosives or fricatives, map the source's voiced letters onto the "
        "voiceless ones — this is usually the strongest single marker of the "
        "accent, and it is easy to overlook because the letters themselves "
        "exist in the target alphabet.\n"
        "2. **Sibilants and affricates.** Which of the source's hushing / "
        "hissing / affricate spellings has no counterpart, and what is the "
        "nearest sound the target voice can actually produce?\n"
        "3. **Digraphs.** Source digraphs that the target reads letter by "
        "letter (or vice versa) have to be rewritten, longest first.\n"
        "4. **Vowel inventory.** Vowels absent from the target, and vowels the "
        "target spells the same but reads differently.\n"
        "5. **Letters read with a different value.** A letter present in both "
        "alphabets but pronounced differently (Polish `w` = /v/, English `w` = "
        "/w/) needs a rule even though nothing looks missing.\n"
        "6. **Clusters and phonotactics.** Onsets or codas the target avoids, "
        "and what its speakers do to them.\n"
        "Leave an axis alone when it genuinely does not apply — a rule that "
        "changes nothing audible is worse than no rule.\n\n"
        "## Response format\n"
        "Return ONLY valid JSON `{\"translations\": [...]}`."
    )


def _parsuj_reguly(surowa: str) -> tuple[list[dict[str, str]], list[str]]:
    """Linie `wzorzec | zamiana` → lista wpisów `zamiany`. Zwraca (wpisy, uwagi).

    Filtr degeneracji wzorowany na `_zbuduj_rozwiniecia` z Poligloty: odrzucamy
    reguły no-op i duplikaty NA WEJŚCIU, żeby bramka G2 nie musiała ich potem
    zgłaszać jako defektu danych.
    """
    wpisy: list[dict[str, str]] = []
    uwagi: list[str] = []
    widziane: set[str] = set()
    for linia in (surowa or "").split("\n"):
        linia = linia.strip().strip("`")
        linia = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", linia)
        if "|" not in linia:
            continue
        wzor, _, zamiana = linia.partition("|")
        wzor, zamiana = wzor.strip().strip('"\''), zamiana.strip().strip('"\'')
        if not wzor:
            continue
        if wzor == zamiana:
            uwagi.append(f"pominięto regułę no-op {wzor!r}")
            continue
        if wzor in widziane:
            uwagi.append(f"pominięto duplikat wzorca {wzor!r}")
            continue
        widziane.add(wzor)
        wpisy.append({"wzor": wzor, "zamiana": zamiana})
    # Dwuznaki PRZED jednoznakami — kolejność jest kontraktem silnika, więc
    # porządkujemy ją MECHANICZNIE zamiast wierzyć modelowi na słowo.
    wpisy.sort(key=lambda w: -len(w["wzor"]))
    return wpisy, uwagi


def _flaga_prepass(wpisy: list[dict[str, str]], podstawy_zrodla: dict, cp: Any) -> bool:
    """Czy `usun_polskie_znaki` może zostać włączone dla tej pary?

    Wyprowadzenie z DANYCH, nie z gustu: jeśli którakolwiek reguła opiera się
    na diakrytyku, który pre-pass spłaszcza, flaga MUSI być wyłączona — inaczej
    reguła jest martwa. Dokładnie ten błąd żył w siedmiu parach paczki `de`
    (43 martwe reguły) i w pięciu parach paczki `fr`.
    """
    for wpis in wpisy:
        wzor = wpis["wzor"]
        if cp._usun_polskie_znaki(wzor, podstawy_zrodla) != wzor:
            return False
    return True


def _naglowek_pary(paczka: str, akcent: str) -> str:
    return przeglad_tlumaczen.naglowek_roboczy(
        f"dictionaries/{paczka}/{FOLDER}/{akcent}.yaml",
        "(brak źródła — para akcentowa jest WYPROWADZANA, nie tłumaczona)",
        "buduj_wielojezyczne_akcenty.py",
        nota_finalizacji=_NOTA_FINALIZACJI)


_NOTA_FINALIZACJI = (
    "# (After review the maintainer runs\n"
    "# `buduj_wielojezyczne_akcenty.py --finalizuj`, which only REMOVES this\n"
    "# banner and keeps your edits. Accent files stay hand-editable: the rule\n"
    "# table is meant to be tuned by the language pack's linguist in the\n"
    "# in-app Rules Manager. Listen to the result with the target synthesizer\n"
    "# before approving — a table can pass every gate and still sound wrong.)\n"
)


def _zbuduj_plik(
    paczka: str, akcent: str, iso_celu: str, kolejnosc: int,
    etykieta: str, opis: str, wpisy: list[dict[str, str]], prepass: bool,
) -> str:
    """Składa treść pliku pary akcentowej (płaski YAML, bez round-tripu).

    Round-trip ruamel byłby tu nieużyteczny: nie mamy pliku źródłowego do
    zachowania (para jest wyprowadzana, nie tłumaczona), a układ jest płaski
    i w pełni znany.
    """
    # Etykieta w scalarze POJEDYNCZO cytowanym z podwojonym apostrofem: nazwy
    # głosów i skróty („np.", „z. B.") ciągną za sobą kropki i cudzysłowy, a
    # ASCII-owy `"` w scalarze double-quoted wywraca parsowanie CAŁEGO pliku
    # (mina udokumentowana w [[reguly_architektury]]).
    linie = [
        _naglowek_pary(paczka, akcent).rstrip("\n"),
        f"id: {akcent}",
        "etykieta: '" + etykieta.replace("'", "''") + "'",
        "opis: |",
    ]
    for wiersz in opis.rstrip().split("\n"):
        linie.append(f"  {wiersz}".rstrip())
    linie += [
        f"iso: {iso_celu}",
        "kategoria: akcent",
        f"kolejnosc: {kolejnosc}",
        "",
        "czysc_tekst_tts: true",
        "normalizuj_liczby: true",
        f"usun_polskie_znaki: {'true' if prepass else 'false'}",
        "skleja_pojedyncze_litery: true",
        "",
        "# Kolejność JEST kontraktem: silnik stosuje reguły sekwencyjnie przez",
        "# `str.replace`, więc wzorce dłuższe stoją przed krótszymi, które w nich",
        "# siedzą. Zmiana kolejności zmienia wynik.",
        "zamiany:",
    ]
    for wpis in wpisy:
        linie.append(f'  - {{ wzor: "{wpis["wzor"]}", zamiana: "{wpis["zamiana"]}" }}')
    return "\n".join(linie) + "\n"


def _wolna_kolejnosc(paczka: str) -> int:
    """Pierwsza wolna wartość `kolejnosc` w paczce (co 5, od 30)."""
    zajete = set()
    folder = DICT_DIR / paczka / FOLDER
    if folder.is_dir():
        for plik in folder.glob("*.yaml"):
            wartosc = wczytaj_pare(paczka, plik.stem).get("kolejnosc")
            if isinstance(wartosc, int):
                zajete.add(wartosc)
    kandydat = 30
    while kandydat in zajete:
        kandydat += 5
    return kandydat


def _zapisz_z_walidacja(paczka: str, akcent: str, tresc: str) -> list[Znalezisko]:
    """Zapisuje parę i uruchamia na niej bramki; przy błędach ROLLBACK."""
    cel = DICT_DIR / paczka / FOLDER / f"{akcent}.yaml"
    kopia = cel.read_text(encoding="utf-8") if cel.is_file() else None
    cel.parent.mkdir(parents=True, exist_ok=True)
    cel.write_text(tresc, encoding="utf-8", newline="\n")

    znaleziska, _ = audytuj([paczka], [akcent])
    bledy = [z for z in znaleziska if z.blad]
    if not bledy:
        return znaleziska
    if kopia is None:
        cel.unlink(missing_ok=True)
    else:
        cel.write_text(kopia, encoding="utf-8", newline="\n")
    return znaleziska


def generuj_pare(
    klient: Any, paczka: str, akcent: str, iso_celu: str, *,
    model: str, dry_run: bool, pary: dict[tuple[str, str], dict], cp: Any,
) -> bool:
    """Wyprowadza JEDNĄ parę akcentową. Zwraca sukces."""
    cel = DICT_DIR / paczka / FOLDER / f"{akcent}.yaml"
    if cel.exists():
        print(f"⏭️  {paczka}/{akcent}: para już istnieje — nie tykam "
              f"(ścieżka generująca nigdy nie nadpisuje wypełnionej pary).")
        return True

    podstawy_zrodla = podstawy_paczki(paczka)
    podstawy_celu = podstawy_paczki(iso_celu)
    nazwa_zrodla = tlumacz_rdzen.natywna_nazwa(DICT_DIR, paczka)
    nazwa_celu = tlumacz_rdzen.natywna_nazwa(DICT_DIR, iso_celu)
    if not podstawy_zrodla.get("alfabet") or not podstawy_celu.get("alfabet"):
        print(f"❌ {paczka}/{akcent}: no `alfabet` in the "
              f"{'source' if not podstawy_zrodla.get('alfabet') else 'target'} basics — "
              f"nothing to derive the rule from.")
        return False

    zjadane = sorted({
        str(p.get("wzor")) for p in podstawy_zrodla.get("polskie_znaki", [])
        if len(str(p.get("wzor", ""))) == 1
        and str(p.get("wzor")) in str(podstawy_zrodla.get("alfabet", "")).lower()
    })
    glosy = glosy_konsensusu(pary, akcent)
    pola: dict[str, Any] = {
        "source_alphabet": str(podstawy_zrodla.get("alfabet", "")),
        "target_alphabet": str(podstawy_celu.get("alfabet", "")),
        "source_diacritics_removed_first": zjadane,
        "native_prose_sample": korpus_paczki(paczka)[:1200],
    }
    if glosy:
        pola["known_target_voices"] = glosy
    precedensy = tabele_precedensowe(pary, akcent, paczka)
    if precedensy:
        pola["precedent_tables_for_same_target"] = precedensy
    kontekst = {}
    inna_para = next(((p, a) for (p, a) in pary if p == paczka), None)
    if inna_para:
        cfg_wzor = pary[inna_para]
        kontekst = {"label": str(cfg_wzor.get("etykieta", "")),
                    "description_style": str(cfg_wzor.get("opis", ""))[:600]}

    print(f"🧭 {paczka}/{akcent}: wyprowadzam regułę {nazwa_zrodla} → "
          f"{nazwa_celu} (głosy: {glosy or 'brak konsensusu'}; "
          f"pre-pass zjada {len(zjadane)} znaków)")
    if dry_run:
        print(f"    (dry-run) payload: {sorted(pola)} + "
              f"{'kontekst paczki' if kontekst else 'brak kontekstu'}; "
              f"nie wywołuję API.")
        return True

    pozycje = _pytania_pary(paczka, iso_celu, nazwa_zrodla, nazwa_celu)
    system = _PROMPT_GENERATORA(paczka, iso_celu, nazwa_zrodla, nazwa_celu)

    # JEDNA powtórka z KONKRETNYMI zarzutami (lekcja v18.18: ślepa powtórka
    # bywa gorsza od pierwszej próby). Empiria replaya `pl/finski`: tabela była
    # już poprawna, a bramka odrzuciła plik za jeden przykład w prozie, w którym
    # model zapomniał zastosować własną regułę do pierwszej litery słowa —
    # dokładnie ta klasa wpadki, którą powtórka z zarzutem naprawia.
    zarzuty: list[str] = []
    for proba in (1, 2):
        pola_proby = dict(pola)
        if zarzuty:
            pola_proby["previous_attempt_problems"] = zarzuty
            print(f"🔁 {paczka}/{akcent}: powtórka z {len(zarzuty)} zarzutami…")
        try:
            odpowiedzi = tlumacz_rdzen.wywolaj_llm(
                klient, model=model, system=system,
                nazwa_celu=nazwa_celu, kod=iso_celu, pozycje=pozycje,
                max_tokens=MAX_TOKENS_OUT,
                wskazowka_limitu="Tabela reguł jest krótka — jeśli limit padł, "
                                 "model prawdopodobnie zaczął komentować.",
                kontekst_paczki=kontekst or None, pola_payloadu=pola_proby,
                myslenie=True)
        except RuntimeError as exc:
            print(f"❌ {paczka}/{akcent}: LLM error — {exc}")
            return False

        wpisy, uwagi = _parsuj_reguly(odpowiedzi.get(0, ""))
        for uwaga in uwagi:
            print(f"⚠️  {paczka}/{akcent}: {uwaga}")
        etykieta = (odpowiedzi.get(1, "") or "").strip().strip('"')
        opis = (odpowiedzi.get(2, "") or "").strip()
        if len(wpisy) < 6 or not etykieta or not opis:
            zarzuty = [f"the rule table had {len(wpisy)} usable rules (need at "
                       f"least 6), or the label/description came back empty"]
            continue

        prepass = _flaga_prepass(wpisy, podstawy_zrodla, cp)
        if not prepass:
            print(f"🔎 {paczka}/{akcent}: reguły opierają się na diakrytykach "
                  f"źródła → `usun_polskie_znaki: false` (inaczej byłyby martwe).")
        tresc = _zbuduj_plik(paczka, akcent, iso_celu, _wolna_kolejnosc(paczka),
                             etykieta, opis, wpisy, prepass)
        znaleziska = _zapisz_z_walidacja(paczka, akcent, tresc)
        bledy = [z for z in znaleziska if z.blad]
        for z in znaleziska:
            print(("     ❌ " if z.blad else "     ⚠️  ") + str(z))
        if not bledy:
            print(f"✅ {paczka}/{akcent}: zapisano DRAFT ({len(wpisy)} reguł"
                  + (", po powtórce" if proba == 2 else "") + ").")
            return True
        zarzuty = [z.opis for z in bledy]
        if proba == 2:
            print(f"❌ {paczka}/{akcent}: after the retry {len(bledy)} errors "
                  f"remain — file rolled back.")
            return False
    return False


def generuj_nowy_jezyk(args: argparse.Namespace) -> int:
    """Tworzy brakujące pary akcentowe dla nowego języka (dwa kierunki)."""
    kod = args.nowy_jezyk.strip()
    pary = pary_akcentowe()
    cp = ustaw_silnik()
    mapa = _mapa_akcentow(pary)          # ISO → nazwa pliku akcentu
    if not podstawy_paczki(kod).get("alfabet"):
        print(f"❌ {kod}: `dictionaries/{kod}/podstawy.yaml` does not exist or has "
              f"no `alfabet`. Create the pack first (podstawy + etykieta), then "
              f"derive the accents.")
        return 2

    mapa_jezykow = tlumacz_rdzen.wczytaj_mape_jezykow(ROOT, KOD_ZRODLOWY)
    nazwa_polska = mapa_jezykow.get(kod, "")
    plik_nowego = nazwa_pliku_akcentu(nazwa_polska) if nazwa_polska else ""

    zadania: list[tuple[str, str, str]] = []       # (paczka, akcent, iso_celu)
    if args.kierunek in ("oba", "z-nowego"):
        for iso_celu, nazwa_akcentu in sorted(mapa.items()):
            if iso_celu != kod:
                zadania.append((kod, nazwa_akcentu, iso_celu))
    if args.kierunek in ("oba", "do-nowego"):
        if not plik_nowego:
            print(f"⚠️  {kod}: no entry in `jezyki_docelowe.yaml`, so the Polish "
                  f"name of this language is unknown — skipping the `do-nowego` "
                  f"direction. Run `refresh_languages.py` and try again.")
        else:
            for paczka in sorted({p for p, _ in pary} | {kod}):
                if paczka != kod:
                    zadania.append((paczka, plik_nowego, kod))

    braki = [(p, a, i) for p, a, i in zadania
             if not (DICT_DIR / p / FOLDER / f"{a}.yaml").exists()]
    print(f"ℹ️  Par do wyprowadzenia: {len(braki)} z {len(zadania)} w zakresie "
          f"(kierunek: {args.kierunek}).")
    if not braki:
        print("✅ Wszystkie pary tego języka już istnieją — nic do zrobienia.")
        return 0

    klient = (None if args.dry_run
              else tlumacz_rdzen.zainicjuj_klienta_anthropic(ROOT))
    wytworzone: list[tuple[str, str]] = []
    porazki: list[str] = []
    for paczka, akcent, iso_celu in braki:
        ok = generuj_pare(klient, paczka, akcent, iso_celu, model=args.model,
                          dry_run=args.dry_run, pary=pary, cp=cp)
        if ok:
            wytworzone.append((paczka, akcent))
        else:
            porazki.append(f"{paczka}/{akcent}")

    if wytworzone and not args.dry_run:
        sciezka = przeglad_tlumaczen.zapisz_prompt_przegladu(
            "buduj_wielojezyczne_akcenty.py", sorted(wytworzone), ROOT)
        if sciezka is not None:
            print(f"📋 Checklista przeglądu → {sciezka.relative_to(ROOT)}")
    print("\n========== SUMMARY (--nowy-jezyk) ==========")
    print(f"✅ Derived: {len(wytworzone)} | ❌ Failed: {len(porazki)}")
    if porazki:
        print("   " + ", ".join(porazki))
        return 1
    return 0


def replay_pary(args: argparse.Namespace) -> int:
    """Test bojowy: wyprowadź ISTNIEJĄCĄ parę od nowa i porównaj ze wzorcem.

    Ścieżka generująca nie ma prawa nadpisać wypełnionej pary, a jednocześnie
    jedyny uczciwy test jej jakości to materiał, dla którego istnieje ręcznie
    napisany złoty standard (decyzja maintainera 2026-08-18: „regenerujemy
    ręcznie napisane reguły pl/fi i restore"). Rozwiązanie: podmieniamy plik na
    czas przebiegu (bramki muszą widzieć go na dysku, bo pracują SILNIKIEM),
    porównujemy wynik ze wzorcem, a potem BEZWARUNKOWO przywracamy wzorzec.
    Wyprowadzony draft zostaje w `skrypty/` do recenzji — nigdy w `dictionaries/`.
    """
    if "/" not in args.replay:
        print("❌ --replay expects the format PACK/ACCENT (e.g. `pl/finski`).")
        return 2
    paczka, akcent = args.replay.split("/", 1)
    cel = DICT_DIR / paczka / FOLDER / f"{akcent}.yaml"
    if not cel.is_file():
        print(f"❌ {args.replay}: no such pair (replay works on an EXISTING "
              f"reference pair).")
        return 2

    wzorzec_tekst = cel.read_text(encoding="utf-8")
    wzorzec = wczytaj_pare(paczka, akcent)
    iso_celu = str(wzorzec.get("iso", ""))
    pary = pary_akcentowe()
    cp = ustaw_silnik()
    probka = str(podstawy_paczki(paczka).get("opis", ""))[:400] or "Test 42."
    przed = zastosuj(cp, probka, paczka, akcent)

    klient = (None if args.dry_run
              else tlumacz_rdzen.zainicjuj_klienta_anthropic(ROOT))
    cel.unlink()
    try:
        pary_bez = {k: v for k, v in pary.items() if k != (paczka, akcent)}
        ok = generuj_pare(klient, paczka, akcent, iso_celu, model=args.model,
                          dry_run=args.dry_run, pary=pary_bez, cp=cp)
        nowy_tekst = cel.read_text(encoding="utf-8") if cel.is_file() else ""
        nowy = wczytaj_pare(paczka, akcent) if cel.is_file() else {}
        po = zastosuj(ustaw_silnik(), probka, paczka, akcent) if nowy else None
    finally:
        cel.write_text(wzorzec_tekst, encoding="utf-8", newline="\n")
        ustaw_silnik()
        print(f"↩ przywrócono wzorzec {paczka}/{akcent}.yaml")

    if not ok or not nowy:
        print("❌ replay: the derivation did not pass the gates — nothing to compare.")
        return 1

    sciezka_draftu = ROOT / "skrypty" / f"replay_{paczka}_{akcent}.yaml"
    sciezka_draftu.parent.mkdir(parents=True, exist_ok=True)
    sciezka_draftu.write_text(nowy_tekst, encoding="utf-8", newline="\n")

    reguly_wzorca = [(str(p.get("wzor")), str(p.get("zamiana")))
                     for p in wzorzec.get("zamiany") or []]
    reguly_nowe = [(str(p.get("wzor")), str(p.get("zamiana")))
                   for p in nowy.get("zamiany") or []]
    wspolne = set(reguly_wzorca) & set(reguly_nowe)
    print(f"\n========== REPLAY {paczka}/{akcent} ==========")
    print(f"rules: reference {len(reguly_wzorca)}, derived {len(reguly_nowe)}, "
          f"shared {len(wspolne)}")
    tylko_wzorzec = sorted(set(reguly_wzorca) - set(reguly_nowe))
    tylko_nowe = sorted(set(reguly_nowe) - set(reguly_wzorca))
    if tylko_wzorzec:
        print(f"reference only ({len(tylko_wzorzec)}): {tylko_wzorzec[:12]}")
    if tylko_nowe:
        print(f"derived only ({len(tylko_nowe)}): {tylko_nowe[:12]}")
    for pole in FLAGI_PIPELINE:
        if wzorzec.get(pole) != nowy.get(pole):
            print(f"flag `{pole}`: reference {wzorzec.get(pole)!r} vs "
                  f"derived {nowy.get(pole)!r}")
    print(f"\nreference output: {(przed or '')[:160]!r}")
    print(f"derived output  : {(po or '')[:160]!r}")
    print(f"identical: {przed == po}")
    print(f"📄 draft do recenzji → {sciezka_draftu.relative_to(ROOT)}")
    return 0


def finalizuj(kody: list[str]) -> int:
    """Zdejmuje baner draftu z par akcentowych wskazanych paczek (zero API)."""
    zmienione = pominiete = 0
    for (paczka, akcent) in sorted(pary_akcentowe()):
        if kody and paczka not in kody:
            continue
        cel = DICT_DIR / paczka / FOLDER / f"{akcent}.yaml"
        tresc, zdjeto = tlumacz_rdzen.zdejmij_baner_draftu(
            cel.read_text(encoding="utf-8"))
        if not zdjeto:
            pominiete += 1
            continue
        cel.write_text(tresc, encoding="utf-8", newline="\n")
        zmienione += 1
        print(f"✅ {paczka}/{akcent}: baner draftu zdjęty.")
    print(f"\n✅ sfinalizowane: {zmienione} | ⏭️ już finalne: {pominiete}")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _parsuj_argumenty() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Auditor and generator for the Polyglot accent pairs "
            "(dictionaries/<pack>/akcenty/<accent>.yaml). AUDIT by default: "
            "no API, seven gates, and the only check that compares all 72 pairs "
            "against each other and against the engine."),
    )
    parser.add_argument(
        "--audyt", action="store_true",
        help="Audit the existing pairs (no API). This is the default mode.")
    parser.add_argument(
        "-l", "--jezyki", type=str, default="",
        help="CSV of PACK codes to audit (e.g. `de,fr`). Empty = all of them.")
    parser.add_argument(
        "-a", "--akcenty", type=str, default="",
        help="CSV of accent names (e.g. `finski,rosyjski`). Empty = all of them.")
    parser.add_argument(
        "--slowniki", type=str, default="",
        help="Path to a `dictionaries` directory OTHER than the repo one (an installation).")
    parser.add_argument(
        "--raport", type=str, default="",
        help="Write the full markdown report to a file (the terminal gets the "
             "summary).")
    parser.add_argument(
        "--nowy-jezyk", type=str, default="", metavar="CODE",
        help="Generate the accent pairs a NEW language is missing. Never "
             "overwrites a pair that already exists.")
    parser.add_argument(
        "--kierunek", choices=("oba", "z-nowego", "do-nowego"), default="oba",
        help="Which pairs to generate: `z-nowego` = <new>/akcenty/<foreign>.yaml, "
             "`do-nowego` = <foreign>/akcenty/<new>.yaml, `oba` (default).")
    parser.add_argument(
        "--model", default=MODEL_DOMYSLNY,
        help=f"Anthropic model for the generating path (default: {MODEL_DOMYSLNY}).")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Generating path without API: show what would be sent to the model, "
             "and with what payload.")
    parser.add_argument(
        "--replay", type=str, default="", metavar="PACK/ACCENT",
        help="Live test of the generating path on an EXISTING pair: derives it "
             "from scratch, compares it with the reference and RESTORES the "
             "reference. The draft stays in `skrypty/` (never in `dictionaries/`).")
    parser.add_argument(
        "-f", "--finalizuj", action="store_true",
        help="No API: strips the DRAFT banner from accent pairs (after the review), "
             "keeping the content with its manual fixes. Narrow it with `--jezyki`.")
    return parser.parse_args()


def main() -> int:
    global DICT_DIR
    args = _parsuj_argumenty()

    if args.slowniki:
        DICT_DIR = Path(args.slowniki).expanduser().resolve()
        if not DICT_DIR.is_dir():
            print(f"❌ --slowniki: {DICT_DIR} is not a directory.")
            return 2
        print(f"📁 Katalog słowników: {DICT_DIR} (poza repo — tryb user-data).")

    if args.nowy_jezyk:
        return generuj_nowy_jezyk(args)
    if args.replay:
        return replay_pary(args)

    kody = [k.strip() for k in args.jezyki.split(",") if k.strip()]
    if args.finalizuj:
        return finalizuj(kody)
    akcenty = [a.strip() for a in args.akcenty.split(",") if a.strip()]
    znaleziska, ile_par = audytuj(kody or None, akcenty or None)

    if args.raport:
        sciezka = Path(args.raport)
        sciezka.parent.mkdir(parents=True, exist_ok=True)
        sciezka.write_text(raport_markdown(znaleziska, ile_par),
                           encoding="utf-8", newline="\n")
        print(f"📋 Raport audytu → {sciezka}")
    else:
        for z in znaleziska:
            print(("❌ " if z.blad else "⚠️  ") + str(z))
    wypisz_podsumowanie(znaleziska, ile_par)
    return 1 if any(z.blad for z in znaleziska) else 0


if __name__ == "__main__":
    sys.exit(main())
