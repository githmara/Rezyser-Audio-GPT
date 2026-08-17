#!/usr/bin/env python
"""
buduj_wielojezyczne_poliglota.py — Batchowy autotłumacz REGUŁ POLIGLOTY (i18n).

Piąty brat rodziny `buduj_wielojezyczne_*`: po interfejsie (`_ui.py`),
dokumentacji (`_docs.py`), przepisach Reżysera (`_tryby.py`) i przepisach
Opowieści (`_opowiesci.py`) bierze na siebie `dictionaries/pl/szyfry/*.yaml`
oraz TRZY narzędzia z `dictionaries/pl/akcenty/` (`oczyszczenie`,
`oczyszczenie_bez_liczb`, `naprawiacz_tagow`). Właściwe akcenty fonetyczne
(`akcenty/<jezyk>.yaml`, 99 par) są POZA zakresem — to nie tłumaczenie, a
wyprowadzenie reguły fonetycznej dla pary języków, i ma dostać własne
narzędzie (etap 4 roadmapy).

Materiał jest schematycznie NAJPROSTSZY w rodzinie (zbiór kluczy identyczny
w 9/9 paczkach, brak `prompt_systemowy`, 17–61 linii na plik), ale ma cechę,
której nie miał żaden brat: **plik zawiera DANE JĘZYKA i PRZYKŁADY, których
poprawność rozstrzyga silnik, nie tłumacz.** Stąd trzy własne mechanizmy:

  1. TRZY KLASY, NIE DWIE (:data:`KLASY_SCIEZEK`). Poza „technicznymi"
     (kopia 1:1 z PL) i prozą (tłumaczone) jest klasa **dane języka**:
     `samogloski`, `rozwiniecia`, `wzor_syku`, `min/max_przesuniecie`, `iso`,
     `zmiekszenia_*`. Nie są ani tłumaczeniem, ani kopią — polskie samogłoski
     w paczce fińskiej to bug, a rosyjska `zamiana_samogloski_male` to
     cyrylickie „о", nie łacińskie „o". W ISTNIEJĄCEJ paczce narzędzie ich
     NIE TYKA (bierze wartości z pliku docelowego); dla NOWEJ wyprowadza je
     deterministycznie tam, gdzie się to liczy (zakres Cezara z
     `len(alfabet)`, `iso`), a resztę jednym mini-wywołaniem LLM z twardą
     walidacją wyniku (wzorzec `_wygeneruj_skrotowce_llm` z `_docs.py`).

  2. PRZYKŁADY LICZY SILNIK, NIE MODEL (:func:`przyklady_wyliczone`). Cała
     nawracająca klasa halucynacji Poligloty (alfabet Cezara, „k-k-k-komputer"
     vs „pr-pr-prysznic", niezescramblowana typoglikemia, odwrócone `.nim`)
     bierze się z tego, że model nie widzi `podstawy.yaml` ani `_algo_*`.
     Builder wywołuje FAKTYCZNY algorytm na słowach języka docelowego,
     wstrzykuje wynik do payloadu jako `computed_examples`, a modelowi
     zostawia prozę wokół. Bramka sprawdza, czy ich użył.

  3. WALIDACJA SILNIKIEM JEST TU NAJWAŻNIEJSZĄ BRAMKĄ, nie dodatkiem
     (:func:`waliduj_silnikiem`). To ona znalazła dług zasięgu Cezara
     (pl/fi/is/ru miały `max_przesuniecie == len(alfabet)`, czyli
     przesunięcie ≡ identyczność) i cztery rozjazdy przykładów jąkania
     (de: kapitalizacja reszty słowa ×2 i „Ich" jako „za krótkie"; fr:
     „moi") — wszystkie w plikach, które przez wiele wydań uchodziły za
     poprawne. Tryb `--tylko-walidacja` (zero API) jest jedynym audytem
     porównującym paczki Poligloty MIĘDZY sobą.

Maszyneria (klient, zamrażanie, komentarze YAML, round-trip, chunkowanie,
drafty, orakuły, leaki) mieszka we wspólnym :mod:`tlumacz_rdzen`, bramki
anty-meta-skip w :mod:`tlumacz_bramki`. Doklejka anty-meta-skip wchodzi
w wariancie „mniejszość": tu nie ma promptów systemowych, ale `opis` bywa
pisany w trybie rozkazującym („Uruchamia wyłącznie procedurę…", „Używaj dla
tekstów technicznych"), a to wystarczy, by model rozpoznał się jako adresat.

Znane kosmetyki round-tripu (widoczne w `git diff`, semantycznie bez
znaczenia — sprawdzone testem tożsamościowym na paczce PL):

  * kolumnowe wyrównanie wartości znika (`min_powtorzen: 1` zamiast
    `min_powtorzen:     1`) — to samo zjawisko co w `_tryby.py`/`_opowiesci.py`,
  * flow-mapy list `rozwiniecia`/`zmiekszenia_*` (`- { wzor: …, zamiana: … }`)
    zachowują styl, ale tracą wyrównanie kolumn `zamiana:`.

ZNANE OGRANICZENIA — zmierzone testem bojowym na stubie nowej paczki (`sv`,
2026-08-17; 4 z 5 reguł przeszły). Wszystkie dotyczą WYŁĄCZNIE budowy nowego
języka, nie propagacji zmian PL na osiem istniejących paczek:

  * `samogloskowiec.yaml` dla języka bez polskich zmiękczeń wymaga ADAPTACJI
    REDAKCYJNEJ, nie tłumaczenia: jego `opis` opisuje trzy kroki, z których dwa
    operują na `zmiekszenia_*`, a te są w większości języków pustymi listami.
    Model dostaje o tym jawny fakt (`empty_rule_data`) i regułę „napisz, że krok
    nie ma zastosowania", ale uparcie przepisuje polskie `dzi→dź`; bramka
    odrzuca wtedy plik z konkretnym powodem. Wzorcem do ręcznego przepisania
    jest paczka fińska („vaiheet 1 ja 2 ovat tarkoituksella tyhjiä").
  * `odwracanie.yaml` — przykład odwróconego skrótowca (`m.in.` → `.nim`) NIE
    jest jeszcze liczony silnikiem, więc model zostawia polski. Docelowo należy
    dorzucić do payloadu `abbreviation_facts` policzone z `rozwiniecia` paczki
    docelowej (ten sam wzorzec co `computed_examples`).
  * `waz.yaml` — `opis` cytuje polski dwuznak „sz", którego `wzor_syku` nowego
    języka nie zawiera. Ta klasa jest analogiczna do `empty_rule_data`, ale
    bramki na nią nie ma (ryzyko fałszywych alarmów na jednoliterowych cytatach).

Użycie:
  python buduj_wielojezyczne_poliglota.py --wszystkie --tylko-walidacja   # audyt
  python buduj_wielojezyczne_poliglota.py --jezyki de --dry-run           # zero API
  python buduj_wielojezyczne_poliglota.py --jezyki de,is --reguly waz,typoglikemia
  python buduj_wielojezyczne_poliglota.py --wszystkie --finalizuj         # zero API

Wymaga `ANTHROPIC_API_KEY` w `golden_key.env` (ten sam plik co GUI).
Moduł NIE zależy od wxPython — uruchamialny w CLI bez inicjalizacji GUI.
"""
from __future__ import annotations

import argparse
import io
import os
import random
import re
import sys
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
# Katalog słowników jest ZMIENNY (`--slowniki`): ten sam pipeline obsługuje repo
# (seed) ORAZ zainstalowaną paczkę, w której żyją prywatne reguły usera.
DICT_DIR = ROOT / "dictionaries"

KOD_ZRODLOWY = "pl"

# Trzy narzędzia z `akcenty/` — jedyne pliki tego folderu, które są WSPÓLNE dla
# wszystkich paczek (whitelista z reguły parytetu: `akcenty/` = N-1 akcentów
# obcojęzycznych + te trzy). Akcent `akcenty/<jezyk>.yaml` to inny gatunek pliku
# i inne narzędzie — patrz nagłówek modułu.
NARZEDZIA_AKCENTOW = ("oczyszczenie.yaml", "oczyszczenie_bez_liczb.yaml",
                      "naprawiacz_tagow.yaml")

# Folder → whitelista nazw (None = wszystkie `*.yaml` z folderu paczki PL).
ZAKRES: dict[str, tuple[str, ...] | None] = {
    "szyfry": None,
    "akcenty": NARZEDZIA_AKCENTOW,
}

# Folder → tryb silnika (`core_poliglota._FOLDER_DLA_TRYBU` na odwrót). Trzymamy
# własną mapę, bo narzędzie musi działać także wtedy, gdy silnika nie da się
# zaimportować (kontrybutor bez `python-docx`).
TRYB_DLA_FOLDERU = {"szyfry": "Szyfrant", "akcenty": "Rezyser"}


# ---------------------------------------------------------------------------
# Parametry wywołań LLM
# ---------------------------------------------------------------------------
# Najdłuższy plik zakresu (`samogloskowiec.yaml`, 61 linii) mieści się w jednym
# wywołaniu z ogromnym zapasem; próg zostaje spójny z rodziną, żeby nie mnożyć
# konwencji.
BATCH_MAX_ZNAKOW = 12_000
MAX_TOKENS_OUT = 16_000
MODEL_DOMYSLNY = "claude-sonnet-5"

MAPA_JEZYKOW: dict[str, str] = tlumacz_rdzen.wczytaj_mape_jezykow(
    ROOT, KOD_ZRODLOWY)


def _natywna_nazwa(kod: str) -> str:
    """Natywna nazwa celu (wrapper — `DICT_DIR` bywa przestawiony przez CLI)."""
    return tlumacz_rdzen.natywna_nazwa(DICT_DIR, kod)


# ---------------------------------------------------------------------------
# KLASYFIKACJA PÓL
# ---------------------------------------------------------------------------
KLASA_TECHNICZNA = "techniczne"      # kopia 1:1 z PL (dispatch, progi, flagi)
KLASA_ETYKIETA = "etykieta"          # napis w ComboBox Poligloty
KLASA_OPIS = "opis"                  # proza dydaktyczna (tooltip + docs)
KLASA_DANE = "dane_jezyka"           # NIE tłumaczenie i NIE kopia — patrz nagłówek

KLASY_SCIEZEK: dict[str, str] = {
    # --- Techniczne: identyfikator, dispatch silnika, progi algorytmu, flagi
    "id": KLASA_TECHNICZNA,
    "kategoria": KLASA_TECHNICZNA,
    "kolejnosc": KLASA_TECHNICZNA,
    "algorytm": KLASA_TECHNICZNA,
    "min_dlugosc_slowa": KLASA_TECHNICZNA,
    "min_powtorzen": KLASA_TECHNICZNA,
    "max_powtorzen": KLASA_TECHNICZNA,
    "min_syk": KLASA_TECHNICZNA,
    "max_syk": KLASA_TECHNICZNA,
    "czysc_tekst_tts": KLASA_TECHNICZNA,
    "normalizuj_liczby": KLASA_TECHNICZNA,
    "usun_polskie_znaki": KLASA_TECHNICZNA,
    "skleja_pojedyncze_litery": KLASA_TECHNICZNA,
    # --- Proza
    "etykieta": KLASA_ETYKIETA,
    "opis": KLASA_OPIS,
    # --- Dane języka (całe węzły, także listy — w środek nie schodzimy)
    "iso": KLASA_DANE,
    "alfabet": KLASA_DANE,
    "min_przesuniecie": KLASA_DANE,
    "max_przesuniecie": KLASA_DANE,
    "samogloski": KLASA_DANE,
    "samogloski_male": KLASA_DANE,
    "samogloski_wielkie": KLASA_DANE,
    "zamiana_samogloski_male": KLASA_DANE,
    "zamiana_samogloski_wielkie": KLASA_DANE,
    "wzor_syku": KLASA_DANE,
    "rozwiniecia": KLASA_DANE,
    "zmiekszenia_przed_samogloska": KLASA_DANE,
    "zmiekszenia_przed_spolgloska": KLASA_DANE,
    "zamiany": KLASA_DANE,
}

# `kind` mówi MODELOWI, z czym ma do czynienia; klasa mówi BRAMCE, jak ostro
# walidować.
RODZAJ_PER_KLASA: dict[str, str] = {
    KLASA_ETYKIETA: "label",
    KLASA_OPIS: "description",
}

# Pola techniczne pierwszego poziomu — porównywane 1:1 przy walidacji silnikiem.
POLA_TECHNICZNE = tuple(
    k for k, klasa in KLASY_SCIEZEK.items() if klasa == KLASA_TECHNICZNA)

# Pola danych języka — nigdy nie kopiowane z PL do nowej paczki bez wyprowadzenia.
POLA_DANYCH = tuple(k for k, klasa in KLASY_SCIEZEK.items() if klasa == KLASA_DANE)


def klasa_pola(klucz: str) -> str | None:
    """Klasa pola pierwszego poziomu. ``None`` = pole NIEZNANE (twardy błąd).

    Schemat tego materiału jest płaski (potwierdzone programowo: identyczny
    zbiór kluczy w 9/9 paczkach dla każdego z 9 plików zakresu), więc nie ma tu
    klasyfikacji po ścieżce jak u brata od Opowieści. Listy (`rozwiniecia`,
    `zmiekszenia_*`, `zamiany`) klasyfikujemy CAŁE jako dane języka i nie
    schodzimy w ich wnętrze — `wzor` jest regexem, `zamiana` słowem języka
    docelowego, a jedno i drugie wyprowadza się razem albo wcale.
    """
    return KLASY_SCIEZEK.get(klucz)


# ---------------------------------------------------------------------------
# KOTWICE Z SILNIKA — literały, których Python szuka DOSŁOWNIE
# ---------------------------------------------------------------------------
# Nazwy pól YAML cytowane w `opis` w backtickach. User widzi je w Menedżerze
# Reguł i po nich edytuje regułę, więc lokalizacja („kielikoodi-kenttä") kieruje
# go do pola, którego nie ma — reguła v17.11.1, ta sama klasa co `kod_jezyka`.
_POLA_CYTOWANE_W_OPISIE = tuple(f"`{k}`" for k in sorted(KLASY_SCIEZEK))


def _kotwice_z_silnika() -> tuple[str, ...]:
    """Literały, po których SILNIK rozpoznaje regułę (dispatch + nazwy pól).

    Twarde źródła, nie heurystyka: `core_poliglota._ALGORYTMY_SZYFROW` (klucz
    pola `algorytm`; nieznana nazwa = `ValueError` przy pierwszym uruchomieniu
    reguły) oraz `_FOLDER_DLA_TRYBU`. Wartości `kategoria` zbieramy z paczki PL,
    bo silnik czyta je w `kod_iso` (`naprawiacz`) i w GUI.

    Fail-soft: gdy import silnika padnie, zostaje sama heurystyka kandydatów
    plus orakuł jednomyślności — z komunikatem w logu.
    """
    literaly: list[str] = list(_POLA_CYTOWANE_W_OPISIE)
    try:
        import core_poliglota as cp
    except Exception as exc:  # noqa: BLE001 — dev-tool ma działać też bez silnika
        print(f"⚠️  Nie mogę zaimportować silnika Poligloty ({exc}) — kotwice "
              f"nazw algorytmów opieram tylko na heurystyce + orakule.")
        return tuple(literaly)
    literaly += sorted(cp._ALGORYTMY_SZYFROW)
    return tuple(literaly)


# ---------------------------------------------------------------------------
# PRZYKŁADY DYDAKTYCZNE — liczone SILNIKIEM, nie zgadywane przez model
# ---------------------------------------------------------------------------
# Pary „słowo → wynik" w `opis`. Cudzysłowy są per język (polskie „…", ASCII
# "…", francuskie « … », islandzkie „…"), strzałka bywa unicodowa albo ASCII.
_CUDZYSLOWY = '„”"«»‘’“'
_RE_PARA_PRZYKLADU = re.compile(
    r'[{c}]\s*([^{c}]{{1,40}}?)\s*[{c}]\s*(?:→|->)\s*[{c}]\s*([^{c}]{{1,80}}?)\s*[{c}]'
    .format(c=_CUDZYSLOWY))

# Ziarno losowości przykładów. Algorytmy jąkania, typoglikemii i węża losują
# (liczbę powtórzeń, permutację środka, długość syku), więc „wynik silnika" nie
# jest jedną wartością. Do PODPOWIEDZI dla modelu bierzemy jeden ustalony
# przebieg; bramka porównuje potem NIEZMIENNIKI, nie ten konkretny przebieg.
ZIARNO_PRZYKLADU = 20_260_818


def pary_z_opisu(opis: str) -> list[tuple[str, str]]:
    """Pary „słowo → wynik" wyłuskane z prozy `opis` (bez pustych)."""
    pary: list[tuple[str, str]] = []
    for src, wynik in _RE_PARA_PRZYKLADU.findall(opis or ""):
        src, wynik = src.strip(), wynik.strip()
        if src and wynik:
            pary.append((src, wynik))
    return pary


def _wywolaj_algorytm(nazwa: str, slowo: str, cfg: dict, podstawy: dict,
                      opcje: dict | None = None) -> str | None:
    """Uruchamia `core_poliglota._algo_<nazwa>` na jednym słowie (fail-soft)."""
    try:
        import core_poliglota as cp
    except Exception:  # noqa: BLE001
        return None
    funkcja = cp._ALGORYTMY_SZYFROW.get(nazwa)
    if funkcja is None:
        return None
    random.seed(ZIARNO_PRZYKLADU)
    try:
        return funkcja(slowo, cfg, podstawy, dict(opcje or {}))
    except Exception as exc:  # noqa: BLE001 — zła reguła = błąd walidacji, nie crash
        print(f"⚠️  algorytm {nazwa!r} wywrócił się na {slowo!r}: {exc}")
        return None


def rola_slowa_jakania(slowo: str, cfg: dict) -> str:
    """Rola słowa-przykładu w dydaktyce jąkania (gałąź algorytmu, którą pokazuje).

    Trzy gałęzie `core_poliglota._algo_jakanie`, każda warta osobnego przykładu:

    * ``za_krotkie`` — `len(slowo) < min_dlugosc_slowa`, słowo wraca nietknięte.
      UWAGA na próg: warunek jest OSTRY, więc słowo o długości DOKŁADNIE równej
      progowi JEST jąkane (na tym poległy de „Ich" i fr „moi" — trzy litery przy
      progu 3 wyglądają na „za krótkie", a nie są).
    * ``samogloskowe`` — druga litera jest samogłoską → powtarzana jedna litera.
    * ``spolgloskowe`` — druga litera jest spółgłoską → powtarzane dwie.
    """
    min_len = int(cfg.get("min_dlugosc_slowa", 3))
    samogloski = str(cfg.get("samogloski", ""))
    if len(slowo) < min_len:
        return "za_krotkie"
    if len(slowo) > min_len and slowo[1] not in samogloski:
        return "spolgloskowe"
    return "samogloskowe"


def przyklady_wyliczone(
    algorytm: str, slowa: list[str], cfg: dict, podstawy: dict,
) -> list[dict[str, str]]:
    """Wyjścia FAKTYCZNEGO algorytmu dla podanych słów języka docelowego.

    Zwraca listę ``{"source_word", "engine_output", "role"}`` gotową do wsadzenia
    w payload jako `computed_examples`. Rola jest podpowiedzią redakcyjną: model
    ma wiedzieć, którą gałąź algorytmu ilustruje dany przykład, żeby nie napisał
    prozy sprzecznej z wynikiem.
    """
    wynik: list[dict[str, str]] = []
    for slowo in slowa:
        wyjscie = _wywolaj_algorytm(algorytm, slowo, cfg, podstawy)
        if wyjscie is None:
            continue
        wpis = {"source_word": slowo, "engine_output": wyjscie}
        if algorytm == "jakanie":
            wpis["role"] = rola_slowa_jakania(slowo, cfg)
        wynik.append(wpis)
    return wynik


def fakty_alfabetu(cfg: dict, podstawy: dict) -> dict[str, Any]:
    """Fakty o alfabecie i zasięgu Cezara — jedyne źródło liczb w `opis` szyfru.

    Model nie widzi `podstawy.yaml`, a `opis` Cezara cytuje długość alfabetu
    i zakres przesunięć. Historia klasy: batch 15.2 skopiował polskie „35 znaków"
    do czterech obcych paczek, a wartości pól i tak nie zgadzały się z prozą
    (dług zasięgu naprawiony w v18.18).
    """
    alfabet = str(cfg.get("alfabet") or podstawy.get("alfabet") or "")
    n = len(alfabet)
    return {
        "alphabet": alfabet,
        "alphabet_length": n,
        "spin_range": f"-{n - 1}…{n - 1}" if n else "",
        "random_shift_range": f"1..{n - 1}" if n else "",
    }


# ---------------------------------------------------------------------------
# DANE JĘZYKA: odczyt z paczki docelowej i wyprowadzenie dla NOWEJ paczki
# ---------------------------------------------------------------------------
def wartosci_danych_z_celu(kod: str, folder: str, nazwa: str) -> dict[str, Any]:
    """Wartości pól klasy :data:`KLASA_DANE` z pliku DOCELOWEGO.

    Pusty słownik, gdy pliku nie ma (nowa paczka) albo się nie parsuje. To jest
    realizacja decyzji „w istniejącej paczce danych języka NIE TYKAMY": wracają
    do wyniku dokładnie takie, jakie były, choćby model dostał je w kontekście.
    """
    plik = DICT_DIR / kod / folder / nazwa
    if not plik.is_file():
        return {}
    try:
        dane = YAML(typ="safe").load(plik.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — zepsuty cel obsłuży walidacja silnikiem
        return {}
    if not isinstance(dane, dict):
        return {}
    return {k: v for k, v in dane.items() if klasa_pola(str(k)) == KLASA_DANE}


def _podstawy_paczki(kod: str) -> dict:
    """`dictionaries/<kod>/podstawy.yaml` jako dict (pusty przy braku/błędzie).

    Czytamy sami, bez silnika: narzędzie musi działać u kontrybutora bez
    `python-docx`, a potrzebny jest z tego pliku wyłącznie `alfabet`.
    """
    plik = DICT_DIR / kod / "podstawy.yaml"
    try:
        dane = YAML(typ="safe").load(plik.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}
    return dane if isinstance(dane, dict) else {}


def _pusta(wartosc: Any) -> bool:
    """Czy wartość PL jest „pusta" (nie ma czego wyprowadzać — kopiujemy 1:1)?"""
    if wartosc is None:
        return True
    if isinstance(wartosc, str):
        return not wartosc.strip()
    if isinstance(wartosc, (list, dict)):
        return len(wartosc) == 0
    return False


# Pola, których dla nowej paczki NIE wyprowadzamy z polskiego wzorca, a zerujemy:
# `zmiekszenia_*` kodują polską logikę zmiękczeń (dzi→dź, ci→ć, ni→ń, si→ś,
# zi→ź). Osiem z dziewięciu paczek trzyma tu puste listy, bo takiej ortografii
# po prostu nie mają — i `_algo_samogloskowiec` obsługuje puste listy bez
# błędu. Zgadywanie fonologii nowego języka przez model byłoby wróżeniem;
# lingwista dopisze reguły, jeśli jego język ich potrzebuje (checklista o tym mówi).
POLA_ZEROWANE_DLA_NOWEJ = ("zmiekszenia_przed_samogloska",
                           "zmiekszenia_przed_spolgloska")


def wyprowadz_dane_jezyka(
    kod: str,
    nazwa: str,
    dane_pl: dict,
    podstawy_cel: dict,
    *,
    dane_llm: dict[str, Any] | None,
) -> tuple[dict[str, Any], list[str]]:
    """Dane języka dla NOWEJ paczki. Zwraca ``(wartości, braki)``.

    Kolejność źródeł jest hierarchią zaufania:

    1. **wartość PL jest pusta** → kopia 1:1 (nie ma czego wyprowadzać; np.
       `zamiany: []` w narzędziach czyszczących),
    2. **da się WYLICZYĆ** → liczymy (`iso` = kod paczki, `min/max_przesuniecie`
       = ±(`len(alfabet)`−1), `alfabet` = alfabet paczki docelowej). Tu model nie
       ma nic do powiedzenia i nie jest pytany,
    3. **polonizm** (`zmiekszenia_*`) → pusta lista, patrz
       :data:`POLA_ZEROWANE_DLA_NOWEJ`,
    4. **reszta** (`samogloski*`, `zamiana_samogloski_*`, `wzor_syku`,
       `rozwiniecia`) → z mini-wywołania LLM, po walidacji.

    Pole, dla którego zabrakło źródła, ląduje w ``braki`` — wołający przerywa
    pracę nad plikiem. Cicha kopia polskiej wartości byłaby najgorszym
    wariantem: paczka wyglądałaby na kompletną, a reguła działałaby na polskich
    samogłoskach.
    """
    alfabet = str(podstawy_cel.get("alfabet") or "")
    wynik: dict[str, Any] = {}
    braki: list[str] = []
    for pole in POLA_DANYCH:
        if pole not in dane_pl:
            continue
        wzorzec = dane_pl[pole]
        if _pusta(wzorzec):
            wynik[pole] = wzorzec
            continue
        if pole == "iso":
            wynik[pole] = kod
            continue
        if pole == "alfabet":
            if not alfabet:
                braki.append(f"`alfabet` — paczka {kod} nie ma go w `podstawy.yaml`")
                continue
            wynik[pole] = alfabet
            continue
        if pole in ("min_przesuniecie", "max_przesuniecie"):
            if not alfabet:
                braki.append(f"`{pole}` — brak alfabetu w {kod}/podstawy.yaml, "
                             f"nie mam z czego policzyć zasięgu")
                continue
            zasieg = len(alfabet) - 1
            wynik[pole] = -zasieg if pole.startswith("min") else zasieg
            continue
        if pole in POLA_ZEROWANE_DLA_NOWEJ:
            wynik[pole] = []
            continue
        wartosc = (dane_llm or {}).get(pole)
        if wartosc is None or _pusta(wartosc):
            braki.append(f"`{pole}` — brak wyprowadzonej wartości dla {kod} "
                         f"(mini-wywołanie danych języka nic nie dało)")
            continue
        wynik[pole] = wartosc
    return wynik, braki


# ---------------------------------------------------------------------------
# MINI-WYWOŁANIE: dane języka dla nowej paczki
# ---------------------------------------------------------------------------
# Świadomie NIE nowy schemat structured-outputs: pytania jadą tym samym
# kontraktem `id → target` co tłumaczenia (`tlumacz_rdzen.wywolaj_llm`), a
# odpowiedzi parsujemy jako linie tekstu — wzorzec `_wygeneruj_skrotowce_llm`
# z doc-autotłumacza, sprawdzony na `es`/`ru`/`zh` w v18.6.
_PYTANIA_DANYCH = (
    ("samogloski",
     "VOWELS FOR THE STUTTER RULE. List every LOWERCASE vowel letter of the "
     "language, immediately followed by the same list in UPPERCASE, as ONE "
     "unbroken string with no separators, no spaces and no commentary. Include "
     "the language's own diacritical vowels. Example shape for English: "
     "aeiouyAEIOUY"),
    ("samogloski_male",
     "VOWELS FOR THE 'EVERYTHING BOOMS ON O' CIPHER, lowercase only: every "
     "lowercase vowel letter EXCEPT the neutral vowel that everything is "
     "replaced WITH (that one must not be on the list — it is the target). One "
     "unbroken string, no separators, no commentary."),
    ("zamiana_samogloski_male",
     "THE NEUTRAL VOWEL, lowercase: the single letter that the cipher replaces "
     "every other vowel with — the language's own letter that sounds like a "
     "long, dull 'o'. Answer with EXACTLY ONE character, in the script of the "
     "target language (Cyrillic 'о' for Russian, not Latin 'o'). Nothing else."),
    ("wzor_syku",
     "HISSING LETTERS for the snake-dialect cipher: the letters (and at most "
     "one digraph) that a hissing snake would stretch out in this language — "
     "the 's'/'z' family and their local equivalents. Answer as a "
     "pipe-separated list, LONGEST FIRST, lowercase, at most four items, no "
     "commentary. Example shape for Polish: sz|s|z"),
    ("rozwiniecia",
     "ABBREVIATIONS for the text-reverser cipher. Give 8 to 15 of the most "
     "common written abbreviations of the language, one per line, in the form "
     "`abbreviation | full expansion`. The abbreviation must be the real "
     "written form INCLUDING its dots (e.g. `e.g.`, `t.d.`, `ул.`), the "
     "expansion must be the spelled-out words a text-to-speech engine should "
     "say instead. No numbering, no bullets, no quotes, no commentary."),
    ("_slowa_przykladowe",
     "EXAMPLE WORDS for the documentation. Give exactly three ordinary words of "
     "the language, one per line, in this order and nothing else:\n"
     "1. a word of at least four letters whose SECOND letter is a VOWEL,\n"
     "2. a word of at least four letters whose SECOND letter is a CONSONANT "
     "(ideally starting with a consonant cluster),\n"
     "3. a very short function word of at most two letters.\n"
     "Plain lowercase words, no numbering, no explanations."),
)


def _linie_odpowiedzi(tekst: str) -> list[str]:
    """Linie odpowiedzi modelu bez numeracji, punktorów i cudzysłowów."""
    czyste: list[str] = []
    for linia in (tekst or "").split("\n"):
        linia = linia.strip().strip("`")
        linia = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", linia)
        linia = linia.strip().strip('"\'' + _CUDZYSLOWY).strip()
        if linia:
            czyste.append(linia)
    return czyste


def _zbuduj_rozwiniecia(linie: list[str]) -> list[dict[str, str]]:
    """Zamienia linie `skrót | rozwinięcie` na wpisy `rozwiniecia` silnika.

    Filtr degeneracji z v18.6 (język bez skrótowców — np. logograficzny —
    zwraca echo „brak takich | brak takich"): odrzucamy pary, w których skrót
    równa się rozwinięciu, oraz duplikaty. Wzorzec budujemy MECHANICZNIE
    (`re.escape` + `\\b` + `\\s`), bo regex jest kontraktem z silnikiem i nie
    ma powodu, żeby pisał go model.
    """
    wpisy: list[dict[str, str]] = []
    widziane: set[str] = set()
    for linia in linie:
        if "|" not in linia:
            continue
        skrot, _, rozwiniecie = linia.partition("|")
        skrot, rozwiniecie = skrot.strip(), rozwiniecie.strip()
        if not skrot or not rozwiniecie:
            continue
        if skrot.lower() == rozwiniecie.lower() or skrot.lower() in widziane:
            continue
        if "." not in skrot:
            continue          # bez kropki to nie skrótowiec, a zwykłe słowo
        widziane.add(skrot.lower())
        wpisy.append({
            "wzor": r"\b" + re.escape(skrot) + r"\s",
            "zamiana": rozwiniecie + " ",
        })
    return wpisy


def _PROMPT_DANE_JEZYKA(nazwa_celu: str, kod: str) -> str:
    """Prompt mini-wywołania danych języka (nowa paczka)."""
    return (
        "# Role\n"
        "You are a linguistic data provider for a desktop accessibility "
        "application. You do NOT translate here: you answer factual questions "
        "about the WRITING SYSTEM of one language, so that a Python engine can "
        "run text transformations on it.\n"
        f"Target language: **{nazwa_celu}** (ISO 639 code: {kod}).\n\n"
        "## Task\n"
        "You receive a JSON object with an `items` field — a list of "
        "`{\"id\": int, \"kind\": str, \"source\": str}` objects, where `source` "
        "is a QUESTION. Answer each one and return JSON of the shape:\n"
        "  `{\"translations\": [{\"id\": int, \"target\": str}, ...]}`\n"
        "Each object MUST carry exactly the same `id` as the question.\n\n"
        "## Rules\n"
        "1. Answer with DATA ONLY — no explanations, no headings, no code "
        "fences, no restating the question.\n"
        "2. Use the language's own script and its own letters. Never substitute "
        "a look-alike from another alphabet.\n"
        "3. Every letter you name must really belong to this language's "
        "alphabet; a parent script checks that.\n"
        "4. If a question genuinely has no answer in this language (for example "
        "it has no dotted abbreviations at all), answer with the single word "
        "`NONE` instead of inventing something.\n"
    )


def wygeneruj_dane_jezyka(
    klient: Any, kod: str, model: str, alfabet: str,
) -> tuple[dict[str, Any], list[str]]:
    """Jedno mini-wywołanie LLM → dane języka dla nowej paczki + słowa przykładowe.

    Zwraca ``(dane, uwagi)``. `dane` zawiera pola klasy :data:`KLASA_DANE`
    (nazwane tak, jak w YAML-u) oraz klucz techniczny `_slowa_przykladowe`.
    Każda wartość jest WALIDOWANA względem alfabetu paczki docelowej — model,
    który poda literę spoza alfabetu, dostaje odrzucone pole (a plik nie
    powstanie), bo taka reguła cicho nic by nie robiła.
    """
    pozycje = [
        (i, "language_data_query", tresc)
        for i, (_, tresc) in enumerate(_PYTANIA_DANYCH)
    ]
    odpowiedzi = tlumacz_rdzen.wywolaj_llm(
        klient,
        model=model,
        system=_PROMPT_DANE_JEZYKA(_natywna_nazwa(kod), kod),
        nazwa_celu=_natywna_nazwa(kod),
        kod=kod,
        pozycje=pozycje,
        max_tokens=2_000,
        wskazowka_limitu="Pytania o dane języka są krótkie — jeśli limit padł, "
                         "sprawdź, czy model nie zaczął komentować.",
    )
    litery_alfabetu = {z.lower() for z in alfabet}
    dane: dict[str, Any] = {}
    uwagi: list[str] = []

    def _obce_litery(tekst: str) -> list[str]:
        return sorted({z for z in tekst.lower()
                       if z.isalpha() and z not in litery_alfabetu})

    for i, (pole, _) in enumerate(_PYTANIA_DANYCH):
        surowa = (odpowiedzi.get(i) or "").strip()
        if not surowa or surowa.upper().startswith("NONE"):
            uwagi.append(f"model nie podał danych dla `{pole}`")
            continue
        linie = _linie_odpowiedzi(surowa)
        if pole == "rozwiniecia":
            wpisy = _zbuduj_rozwiniecia(linie)
            if len(wpisy) < 3:
                uwagi.append(
                    f"`rozwiniecia`: po filtrze degeneracji zostało {len(wpisy)} "
                    f"par (potrzebne ≥3) — język może nie mieć skrótowców "
                    f"z kropką; dopisz je ręcznie")
                continue
            dane[pole] = wpisy
            continue
        wartosc = linie[0] if linie else ""
        if pole == "wzor_syku":
            czlony = [c.strip() for c in wartosc.split("|") if c.strip()][:4]
            obce = _obce_litery("".join(czlony))
            if not czlony or obce:
                uwagi.append(f"`wzor_syku`: człony {czlony} zawierają litery "
                             f"spoza alfabetu {kod}: {obce}")
                continue
            dane[pole] = "(?i)(" + "|".join(czlony) + ")"
            continue
        if pole == "_slowa_przykladowe":
            # Filtr „to naprawdę jest słowo": empiria testu `sv` — model w jednym
            # przebiegu zwrócił tu zlepek samogłosek `aeiuyåäöAEIUYÅÄÖ`, który
            # przeszedł jako „słowo" i posłużył do policzenia bezsensownego
            # przykładu. Wymagamy małych liter, sensownej długości i choćby jednej
            # spółgłoski (inaczej to zbiór znaków, nie wyraz).
            samogloski_jezyka = set(str(dane.get("samogloski_male", "")).lower())
            slowa = [
                s for s in linie
                if s.isalpha() and s.islower() and 2 <= len(s) <= 20
                and (not samogloski_jezyka or set(s) - samogloski_jezyka)
            ][:3]
            if len(slowa) < 3:
                uwagi.append(
                    f"słowa przykładowe: po filtrze zostało {len(slowa)} z 3 "
                    f"(odrzucone: {[l for l in linie if l not in slowa][:4]})")
            if slowa:
                dane[pole] = slowa
            continue
        # Pozostałe pola to zbiory znaków (samogłoski, litera neutralna).
        wartosc = wartosc.replace(" ", "")
        obce = _obce_litery(wartosc)
        if obce:
            uwagi.append(f"`{pole}`: litery spoza alfabetu {kod}: {obce}")
            continue
        if pole == "zamiana_samogloski_male" and len(wartosc) != 1:
            uwagi.append(f"`zamiana_samogloski_male`: oczekuję JEDNEGO znaku, "
                         f"dostałem {wartosc!r}")
            continue
        dane[pole] = wartosc

    # Pola wielkoliterowe wyprowadzamy MECHANICZNIE z małoliterowych — nie ma
    # powodu pytać modelu o coś, co robi `str.upper()`, a rozjazd długości
    # między parą list zepsułby klasę znaków regexu.
    if "samogloski_male" in dane:
        dane["samogloski_wielkie"] = str(dane["samogloski_male"]).upper()
    if "zamiana_samogloski_male" in dane:
        dane["zamiana_samogloski_wielkie"] = str(
            dane["zamiana_samogloski_male"]).upper()
    return dane, uwagi


# ---------------------------------------------------------------------------
# PROMPT SYSTEMOWY TŁUMACZA — ANGIELSKI (jak u wszystkich braci)
# ---------------------------------------------------------------------------
_RODZAJE_OPIS = (
    "- `label` — the rule's name as the user picks it from a dropdown in the "
    "Polyglot tab. Short, native, and it is the CANONICAL name of this cipher or "
    "tool for the whole language pack (the manual and the UI quote it).\n"
    "- `description` — the teaching text shown as help for the rule: what the "
    "transformation does, on what condition, with worked examples. Written for a "
    "curious end user, not for a programmer. Keep its line breaks and its "
    "paragraph structure.\n"
    "- `comment` — YAML developer documentation (a comment block for the person "
    "maintaining this language pack). Translate it as documentation. Lines made "
    "up only of `=`, `-` or `*` are decoration: copy them unchanged, same "
    "length. Keep code identifiers, file names and YAML key names as they are. "
    "WRAP the prose at about 78 characters per line, the way the source block "
    "does — rewrap freely (line count may differ) but keep blank lines and the "
    "leading indentation of continuation lines.\n"
)

_ZASADY_PRZYKLADOW = (
    "- **`computed_examples` IN THE INPUT IS ARITHMETIC, NOT A SUGGESTION.** "
    "Every worked example in the source text (`\"komputer\" → "
    "\"k-k-k-komputer\"`) shows the OUTPUT OF A REAL PYTHON FUNCTION. You cannot "
    "recompute it: you do not see the engine, the alphabet file or the rule "
    "parameters. So when the payload carries `computed_examples`, use those "
    "`source_word` / `engine_output` pairs VERBATIM — same letters, same "
    "hyphens, same capitalization, same number of repetitions — in place of the "
    "Polish pairs, and write the surrounding prose so that it AGREES with them. "
    "A parent script re-runs the engine on your text and drops the file if the "
    "prose and the arithmetic disagree.\n"
    "- The `role` field tells you which branch of the rule an example "
    "illustrates (`samogloskowe` = second letter is a vowel, so ONE letter is "
    "repeated; `spolgloskowe` = second letter is a consonant, so TWO are; "
    "`za_krotkie` = the word is below the length threshold and comes back "
    "unchanged). Keep each example in ITS role — do not swap them, do not drop "
    "one, do not add a fourth.\n"
    "- **`alphabet_facts` are also arithmetic**: the alphabet string, its "
    "LENGTH, the allowed shift range and the random-shift range belong to the "
    "TARGET language pack. Never carry over a number from the Polish text (the "
    "Polish alphabet has 35 letters; almost no other does).\n"
    "- If the payload carries NO computed example for a pair you see in the "
    "source, keep the pair exactly as it is in the source and do not invent a "
    "native replacement — an unverified example is worse than a foreign one.\n"
    "- **`previous_attempt_problems` MEANS YOUR PREVIOUS ANSWER WAS REJECTED.** "
    "When the payload carries it, a parent script already validated an earlier "
    "translation of these very items and refused it for exactly the listed "
    "reasons. Fix those reasons and change nothing else about the task. In "
    "particular, if it says a Polish example word survived, replace it with the "
    "`computed_examples` pair — do not reintroduce the Polish one.\n"
    "- **`empty_rule_data` MEANS THE STEP DOES NOT APPLY HERE.** That field "
    "lists rule fields that are EMPTY for this language (e.g. the Polish "
    "softening tables `dzi→dź`, `ci→ć`, which most languages simply do not "
    "have). Keep the numbered steps and their count 1:1, but for such a step do "
    "NOT translate its Polish worked example: say plainly that the step is "
    "intentionally empty in this language, the way the Finnish pack does "
    "(\"steps 1 and 2 are intentionally empty — this language has no Polish "
    "softening consonants\"). Carrying the Polish example over would document "
    "behaviour the engine does not have here.\n"
)


def _PROMPT_SYSTEMOWY(nazwa_celu: str, kod: str) -> str:
    """Prompt tłumaczenia reguł Poligloty."""
    return (
        "# Role\n"
        "You are a senior localization engineer for a desktop wxPython "
        "application used mostly by BLIND people with screen readers. You "
        "localize RULE FILES of its text-transformation engine (\"Polyglot\"): "
        "YAML files that define ciphers and text-cleanup tools — a dropdown "
        "label, a teaching description and developer comments. The source "
        "strings are in Polish.\n"
        f"Target language: **{nazwa_celu}** (ISO 639 code: {kod}).\n\n"
        + tlumacz_bramki.blok_anty_meta_skip(przewaga_promptow=False) + "\n"
        "## Task\n"
        "You receive a JSON object with an `items` field — a list of "
        "`{\"id\": int, \"kind\": str, \"source\": str}` objects. Translate each "
        "`source` and return JSON of the shape:\n"
        "  `{\"translations\": [{\"id\": int, \"target\": str}, ...]}`\n"
        "Each object MUST carry exactly the same `id` as the input. Skipping ids, "
        "adding new ones or changing their order is not allowed.\n\n"
        "## Item kinds\n"
        + _RODZAJE_OPIS +
        "\n## Technical rules (CRITICAL — a violation blocks the file from being written)\n"
        "1. **Markers ⟦P<n>⟧ and ⟦K<n>⟧** are frozen program fragments: engine "
        "identifiers, algorithm names and YAML field names. Copy every marker "
        "into `target` VERBATIM — same letters, same digits, same brackets — and "
        "exactly as many times as in `source`. Do NOT invent markers, do not "
        "renumber them, do not translate them. The sentence AROUND a marker is "
        "translated normally.\n"
        "2. **YAML FIELD NAMES ARE LITERALS.** `min_dlugosc_slowa`, "
        "`samogloski`, `rozwiniecia`, `min_przesuniecie`, `wzor_syku`, "
        "`zamiany` and the rest keep their Polish spelling in EVERY language: "
        "the user edits those very fields in the in-app Rules Manager, so a "
        "localized name („kielikoodi-kenttä\") points at a field that does not "
        "exist. The same holds for file and folder names (`podstawy.yaml`, "
        "`dictionaries/`, `.docx`, `.html`), the algorithm ids (`cezar`, "
        "`jakanie`, `odwracanie`, `samogloskowiec`, `typoglikemia`, `waz`) and "
        "the category values (`szyfr`, `oczyszczenie`, `naprawiacz`).\n"
        "3. **The values of the rule are NOT in this payload.** You never see "
        "the vowel sets, the abbreviation table, the shift range or the ISO "
        "code, because those are DATA OF THE TARGET LANGUAGE, not translation — "
        "the parent script fills them in. Do not try to state them from memory; "
        "quote only what `computed_examples` / `alphabet_facts` give you.\n"
        "4. **Whitespace is contractual** in the description: preserve line "
        "breaks, blank lines, indentation of the numbered steps and the leading "
        "two spaces of continuation lines.\n"
        "5. **Emoji** — copy 1:1 and keep their position relative to the text.\n"
        "6. **Content is fixed.** Do not add, drop, merge, split or reorder "
        "sentences, steps or examples. No preamble, no commentary, no code "
        "fences.\n\n"
        "## Worked examples and numbers\n"
        + _ZASADY_PRZYKLADOW +
        "\n## Localization quality\n"
        "- **`existing_terminology` IN THE INPUT WINS.** When the payload "
        "carries that field, this language pack ALREADY ships those strings and "
        "its manual, its readme and its UI have quoted them for releases. Reuse "
        "them VERBATIM — above all the rule's `label`, which is the canonical "
        "name of this cipher for the whole pack — instead of coining a "
        "better-sounding synonym. You cannot see the pack's other files; a fresh "
        "coinage would make the dropdown say one thing and the manual another.\n"
        "- Write the way a native technical writer of the target language "
        "writes: idiomatic terminology of screen readers and speech synthesis, "
        "no calques of Polish word order. Convey the FUNCTION of a label, not a "
        "word-for-word gloss.\n"
        "- REDUNDANT GLOSSES: where the Polish text explains a foreign term for "
        "its Polish reader, and that term is NATIVE in the target language, the "
        "gloss becomes a tautology — drop it. Keep it where the term is foreign "
        "to the target reader too.\n"
        "- Grammatical correctness comes first: full diacritics, correct "
        "case/gender/number. For inflected languages (Icelandic, Finnish, "
        "Russian) anchor the declension to forms already present in the batch.\n\n"
        "## Response format\n"
        "Return ONLY valid JSON `{\"translations\": [...]}`."
    )


# ---------------------------------------------------------------------------
# JEDNOSTKI TŁUMACZENIA
# ---------------------------------------------------------------------------
Jednostka = tlumacz_rdzen.Jednostka


def zbierz_jednostki_pol(
    drzewo: Any, sciezka_opisowa: str, *, licznik_od: int = 0,
) -> list[Jednostka]:
    """Wyłuskuje z drzewa jednostki tłumaczenia (bez komentarzy).

    Rzuca ``SystemExit`` na polu, którego nie ma w :data:`KLASY_SCIEZEK` — nowe
    pole w PL musi przejść przez świadomą decyzję: czy to proza, czy dane języka,
    czy dispatch. Cicha kopia byłaby albo polskim leakiem, albo martwą regułą
    w ośmiu paczkach (wzorzec twardego stopu z `_tryby.py`).
    """
    jednostki: list[Jednostka] = []
    licznik = licznik_od
    nieznane: list[str] = []
    for klucz in list(drzewo.keys()):
        klasa = klasa_pola(str(klucz))
        if klasa is None:
            nieznane.append(str(klucz))
            continue
        if klasa not in RODZAJ_PER_KLASA:
            continue                    # techniczne i dane języka — nie tłumaczymy
        wartosc = drzewo[klucz]
        if not isinstance(wartosc, str) or not wartosc.strip():
            continue
        jednostki.append(Jednostka(
            licznik, RODZAJ_PER_KLASA[klasa], klasa,
            ("sciezka", str(klucz)), wartosc))
        licznik += 1
    if nieznane:
        raise SystemExit(
            f"❌ {sciezka_opisowa}: nieznane pola reguły Poligloty: {nieznane}.\n"
            f"   Dopisz każde do KLASY_SCIEZEK w buduj_wielojezyczne_poliglota.py "
            f"(techniczne / etykieta / opis / dane_jezyka) — tłumacz nie zgaduje, "
            f"czy pole się lokalizuje, kopiuje, czy wyprowadza z języka."
        )
    return jednostki


def _wzorce_pustych_krokow(
    cfg_pl: dict, dane_jezyka: dict[str, Any],
) -> tuple[str, ...]:
    """Literały reguł z PL-owych list, które w tym języku są PUSTE.

    Służą bramce „nie opisuj kroku, którego tu nie ma": dla szwedzkiego to
    polskie zmiękczenia (`dzi`→`dź`, `ci`→`ć`), które model chętnie przepisuje
    do opisu, mimo że `zmiekszenia_*` są w tej paczce pustymi listami.
    """
    wzorce: list[str] = []
    for pole in POLA_DANYCH:
        wzorzec_pl = cfg_pl.get(pole)
        if not isinstance(wzorzec_pl, list) or not wzorzec_pl:
            continue
        if not _pusta(dane_jezyka.get(pole, wzorzec_pl)):
            continue
        for para in wzorzec_pl:
            if isinstance(para, dict):
                for klucz in ("wzor", "zamiana"):
                    wartosc = str(para.get(klucz, "")).strip()
                    if len(wartosc) >= 2:
                        wzorce.append(wartosc)
    return tuple(dict.fromkeys(wzorce))


def waliduj_jednostke(
    src_tok: str,
    tgt: str,
    klasa: str,
    *,
    slowa_zakazane: tuple[str, ...] = (),
    wzorce_pustych_krokow: tuple[str, ...] = (),
    cfg_dla_przykladow: dict | None = None,
    podstawy: dict | None = None,
) -> tuple[list[str], list[str]]:
    """Bramka jednej jednostki: tokeny, odcisk, przykłady dydaktyczne.

    Zwraca ``(blokujące, uwagi)``. Miękkie naruszenia odcisku (pogrubienia,
    liczba linii, stosunek długości) są w `opis` UWAGĄ, nie blokadą — ten sam
    precedens co proza manuali w `_docs.py`: nota „ten krok jest w tym języku
    pusty" legalnie zmienia łamanie akapitu, a arytmetykę przykładów pilnują
    bramki twarde niżej.

    Odcisk twardy obowiązuje wszędzie (łapie „model wykonał tekst zamiast go
    przetłumaczyć"), miękki tylko dla `opis` — to proza wielolinijkowa z krokami
    algorytmu, więc utrata linii albo połowa objętości znaczy zgubioną gałąź
    reguły. Etykiety są jednowyrazowe: mierzenie ich objętości byłoby szumem.

    Dla `opis` dochodzą dwie kontrole przykładów, obie z testów bojowych v18.18:

    * **`slowa_zakazane`** — słowa-przykłady z POLSKIEGO źródła. `is/jakanie`
      wróciło z „komputer"/„prysznic" (model zignorował `computed_examples`),
      a walidacja arytmetyczna to PRZEPUŚCIŁA: polskie słowo policzone
      islandzkimi regułami ma przecież poprawny prefiks. Detektor PL-leaków też
      milczał — w tych słowach nie ma ani jednego polskiego diakrytyku. To
      jedyne miejsce, w którym ta klasa wpadki jest widoczna.
    * **przeliczenie KAŻDEJ pary** z tłumaczenia faktycznym algorytmem. Dzięki
      temu model MOŻE dobrać własne, lepsze słowo (szwedzki nie ma polskich
      zmiękczeń, więc jego przykład dla samogłoskowca jest sensowniejszy niż
      przełożone „dzień → dźoń") — pod warunkiem, że arytmetyka się zgadza.
      Wymaganie dosłownie MOICH słów blokowało tu poprawne tłumaczenia.
    """
    problemy = tlumacz_rdzen.parzystosc_tokenow(src_tok, tgt)
    twarde, miekkie = tlumacz_bramki.waliduj_odcisk(src_tok, tgt)
    problemy += twarde
    uwagi: list[str] = []
    if klasa == KLASA_OPIS:
        uwagi += miekkie
        nizsze = tgt.lower()
        for slowo in slowa_zakazane:
            if slowo.lower() in nizsze:
                problemy.append(
                    f"przykład {slowo!r} został ze ŹRÓDŁA POLSKIEGO — model "
                    f"zignorował policzone `computed_examples` i przepisał "
                    f"polskie słowo (leak niewidoczny dla detektora znaków)")
        # Krok algorytmu, którego dane są w tym języku PUSTE, nie może być
        # opisany polskimi przykładami: `sv` dostało „dzi→dź, ci→ć" w opisie,
        # choć jego `zmiekszenia_*` są pustymi listami — dokumentacja obiecywałaby
        # zachowanie, którego silnik tu nie ma. Próg dwóch wystąpień trzyma z
        # daleka fałszywy alarm na pojedynczej literze.
        trafienia = [w for w in wzorce_pustych_krokow if w and w in tgt]
        if len(trafienia) >= 2:
            problemy.append(
                f"opis cytuje reguły kroku, który w tym języku jest PUSTY "
                f"({trafienia[:4]}) — napisz wprost, że ten krok nie ma tu "
                f"zastosowania (tak robi paczka fińska)")
        if cfg_dla_przykladow is not None:
            algorytm = str(cfg_dla_przykladow.get("algorytm", ""))
            for src, oczek in pary_z_opisu(tgt):
                blad = _sprawdz_pare(algorytm, src, oczek, cfg_dla_przykladow,
                                     podstawy or {})
                if blad:
                    problemy.append(f"przykład sprzeczny z silnikiem: {blad}")
    else:
        problemy += miekkie
    return problemy, uwagi


# ---------------------------------------------------------------------------
# NAGŁÓWEK PLIKU WYNIKOWEGO (baner draftu)
# ---------------------------------------------------------------------------
# ŚWIADOMA RÓŻNICA wobec `_ui.py`/`_docs.py`, wspólna z `_tryby.py`/`_opowiesci.py`:
# reguła Poligloty NIE dostaje banera „plik wygenerowany automatycznie, nie edytuj
# ręcznie" — `szyfry/` i `akcenty/` są EDYTOWALNE w Menedżerze Reguł (to dwa
# z pięciu folderów, które Menedżer skanuje). Zakaz edycji byłby kłamstwem wobec
# architektury, więc draft dostaje baner do recenzji, a `--finalizuj` go ZDEJMUJE.
_NOTA_FINALIZACJI = (
    "# (After approval the maintainer runs\n"
    "# `buduj_wielojezyczne_poliglota.py --finalizuj`, which just REMOVES this\n"
    "# banner and keeps everything below — including your manual fixes. This\n"
    "# file stays hand-editable afterwards: cipher rules are meant to be tuned\n"
    "# by the language pack's linguist in the in-app Rules Manager, so it never\n"
    "# gets a \"do not edit\" header. Do NOT re-run the translation: it would\n"
    "# overwrite the file and bring the hallucinations back.)\n"
)


def _baner_draftu(kod: str, folder: str, nazwa: str) -> str:
    return przeglad_tlumaczen.naglowek_roboczy(
        f"dictionaries/{kod}/{folder}/{nazwa}",
        f"dictionaries/{KOD_ZRODLOWY}/{folder}/{nazwa}",
        "buduj_wielojezyczne_poliglota.py",
        nota_finalizacji=_NOTA_FINALIZACJI)


zdejmij_baner_draftu = tlumacz_rdzen.zdejmij_baner_draftu


# ---------------------------------------------------------------------------
# WALIDACJA SILNIKIEM — najostrzejsza bramka (zero API)
# ---------------------------------------------------------------------------
# Znaki WYŁĄCZNIE polskie — świadomie BEZ `ó`, które jest też islandzkie,
# hiszpańskie, francuskie i włoskie (islandzkie `prófessor` w `rozwiniecia`
# dało na tym fałszywy alarm w pierwszym przebiegu audytu). `ñ` (es) nie jest
# tym samym znakiem co `ń`, więc lista niżej nie ma z żadnym z ośmiu języków
# wspólnego repertuaru.
_RE_POLSKIE_ZNAKI = re.compile(r"[ąćęłńśźżĄĆĘŁŃŚŹŻ]")

# Korpus do sprawdzenia, czy `wzor_syku` w ogóle coś łapie. Świadomie bierzemy
# PROZĘ TEGO SAMEGO PLIKU (etykieta + opis w języku docelowym), a nie sztuczne
# zdanie: to jedyny tekst w języku celu, który narzędzie ma pod ręką bez
# zgadywania, a wystarcza — reguła syczenia, która nie trafia w kilkuset znakach
# rodzimej prozy, jest martwa.
def _korpus_paczki(cfg: dict) -> str:
    return f"{cfg.get('etykieta', '')}\n{cfg.get('opis', '')}"


# Krótki korpus smoke-testu reguły. Cyfry, interpunkcja i słowa różnej długości —
# żeby przejść przez normalizację liczb, czyszczenie TTS i wszystkie gałęzie
# algorytmów. Treść jest neutralna językowo (nazwy własne + liczba), bo ten sam
# łańcuch idzie przez dziewięć paczek.
_KORPUS_SMOKE = (
    "Anna i Marek 123. Sesja szyfrant: prysznic, komputer, ulica.\n"
    "Sisu, tietokone, stelpa, ordenador, strada, привет.\n"
)


def _ustaw_silnik() -> Any:
    """Przestawia silnik Poligloty na :data:`DICT_DIR` i czyści jego cache.

    `core_poliglota` liczy ścieżki od własnego `DICTIONARIES_DIR` (repo), a my
    możemy pracować na `--slowniki` wskazującym instalację. Cache wariantów
    i podstaw trzeba czyścić, bo w jednym przebiegu czytamy ten sam plik przed
    i po zapisie.
    """
    import core_poliglota as cp
    cp.DICTIONARIES_DIR = str(DICT_DIR)
    cp._CACHE_WARIANTOW.clear()
    cp._CACHE_PODSTAWY.clear()
    return cp


def _sprawdz_dane_jezyka(
    kod: str, cfg_pl: dict, cfg: dict, podstawy: dict,
) -> list[str]:
    """Dane języka: obecność, zasięg Cezara, kompilowalność regexów, brak kopii z PL."""
    bledy: list[str] = []
    alfabet = str(cfg.get("alfabet") or podstawy.get("alfabet") or "")

    for pole in POLA_DANYCH:
        if pole not in cfg_pl:
            continue
        wzorzec, wartosc = cfg_pl[pole], cfg.get(pole)
        if pole not in cfg:
            bledy.append(f"brak pola `{pole}` (PL je ma) — silnik zejdzie na "
                         f"wbudowany polski default")
            continue
        # Puste `zmiekszenia_*` w obcej paczce to NORMA, nie brak: kodują polską
        # ortografię zmiękczeń (dzi→dź, ci→ć), której osiem języków nie ma —
        # `_algo_samogloskowiec` obsługuje puste listy bez błędu, a fiński plik
        # wprost pisze „tarkoituksella tyhjiä". Pierwszy przebieg audytu wystawił
        # tu 16 fałszywych alarmów; wyjątek jest wąski (dwa nazwane pola).
        if pole in POLA_ZEROWANE_DLA_NOWEJ and _pusta(wartosc):
            continue
        if _pusta(wzorzec) != _pusta(wartosc):
            bledy.append(
                f"`{pole}`: PL {'puste' if _pusta(wzorzec) else 'niepuste'}, "
                f"{kod} {'puste' if _pusta(wartosc) else 'niepuste'} — reguła "
                f"robi w tej paczce co innego niż w polskiej")
            continue
        # Kopia z PL rozpoznana po polskich diakrytykach: samogłoski „ąęó" albo
        # rozwinięcie „między innymi" w paczce fińskiej to nie tłumaczenie, tylko
        # niewyprowadzone dane. Detekcja jest wąska (znak diakrytyczny), więc
        # języki o wspólnym repertuarze liter nie dają fałszywego alarmu.
        if kod != KOD_ZRODLOWY and isinstance(wartosc, str):
            if _RE_POLSKIE_ZNAKI.search(wartosc) and wartosc == wzorzec:
                bledy.append(f"`{pole}` = {wartosc!r} jest kopią wartości PL "
                             f"(polskie znaki diakrytyczne) — dane języka nie "
                             f"zostały wyprowadzone")

    if str(cfg_pl.get("iso", "")).strip():
        if str(cfg.get("iso", "")).strip() != kod:
            bledy.append(f"`iso` = {cfg.get('iso')!r}, oczekuję {kod!r} "
                         f"(z tego pola bierze się tag lang w pliku wynikowym)")
    elif str(cfg.get("iso", "")).strip():
        bledy.append(f"`iso` = {cfg.get('iso')!r}, a PL trzyma tu pustą wartość "
                     f"(kod podaje user w GUI — naprawiacz tagów)")

    if cfg.get("algorytm") == "cezar" and alfabet:
        zasieg = len(alfabet) - 1
        if cfg.get("max_przesuniecie") != zasieg or cfg.get("min_przesuniecie") != -zasieg:
            bledy.append(
                f"zasięg Cezara: `min/max_przesuniecie` = "
                f"{cfg.get('min_przesuniecie')!r}/{cfg.get('max_przesuniecie')!r}, "
                f"a alfabet ma {len(alfabet)} znaków → poprawne jest "
                f"±{zasieg} (przesunięcie równe długości alfabetu to "
                f"identyczność, czyli jawny tekst zamiast szyfru)")
        for liczba in (len(alfabet), zasieg):
            if str(liczba) not in str(cfg.get("opis", "")):
                bledy.append(
                    f"`opis` nie cytuje liczby {liczba} (długość alfabetu / "
                    f"zasięg) — proza rozjechała się z danymi paczki")

    wzor = cfg.get("wzor_syku")
    if isinstance(wzor, str) and wzor.strip():
        try:
            skompilowany = re.compile(wzor)
        except re.error as exc:
            bledy.append(f"`wzor_syku` = {wzor!r} nie kompiluje się: {exc}")
        else:
            if not skompilowany.search(_korpus_paczki(cfg)):
                bledy.append(
                    f"`wzor_syku` = {wzor!r} nie trafia ANI RAZ w rodzimą prozę "
                    f"tego pliku — reguła syczenia jest w tej paczce martwa")

    rozwiniecia = cfg.get("rozwiniecia")
    if isinstance(rozwiniecia, list):
        widziane: set[str] = set()
        for idx, para in enumerate(rozwiniecia):
            if not isinstance(para, dict):
                bledy.append(f"`rozwiniecia[{idx}]` nie jest mapą {{wzor, zamiana}}")
                continue
            wzorzec_re = str(para.get("wzor", ""))
            zamiana = str(para.get("zamiana", ""))
            if not wzorzec_re or not zamiana.strip():
                bledy.append(f"`rozwiniecia[{idx}]`: puste `wzor` albo `zamiana`")
                continue
            try:
                re.compile(wzorzec_re)
            except re.error as exc:
                bledy.append(f"`rozwiniecia[{idx}].wzor` = {wzorzec_re!r} nie "
                             f"kompiluje się: {exc}")
                continue
            if wzorzec_re in widziane:
                bledy.append(f"`rozwiniecia[{idx}].wzor` = {wzorzec_re!r} jest "
                             f"duplikatem — druga reguła nigdy nie zadziała")
            widziane.add(wzorzec_re)
            if kod != KOD_ZRODLOWY and _RE_POLSKIE_ZNAKI.search(zamiana):
                bledy.append(f"`rozwiniecia[{idx}].zamiana` = {zamiana!r} ma "
                             f"polskie znaki diakrytyczne — skrótowce nie zostały "
                             f"wyprowadzone dla {kod}")
    return bledy


def _kolaps_powtorzen(tekst: str) -> str:
    """`ssssshake` → `shake` (do niezmiennika węża)."""
    return re.sub(r"(.)\1+", r"\1", tekst, flags=re.IGNORECASE)


def _sprawdz_pare(
    algorytm: str, src: str, oczek: str, cfg: dict, podstawy: dict,
) -> str | None:
    """Czy para „słowo → wynik" z `opis` zgadza się z FAKTYCZNYM algorytmem?

    Trzy algorytmy są losowe, więc porównujemy NIEZMIENNIKI, nie jeden przebieg:

    * `jakanie` — prefiks (człon przed pierwszym myślnikiem) i ogon (po ostatnim);
      liczba powtórzeń jest losowa z `min_powtorzen..max_powtorzen`,
    * `typoglikemia` — długość, pierwsza i ostatnia litera, wielozbiór liter,
    * `waz` — po zwinięciu powtórzeń wynik równa się źródłu, a najdłuższa seria
      mieści się w `min_syk..max_syk`.

    Pozostałe są deterministyczne (`samogloskowiec`, `odwracanie`) albo
    deterministyczne po ustaleniu przesunięcia (`cezar` — sprawdzamy, czy
    ISTNIEJE przesunięcie z dozwolonego zakresu dające pokazany wynik).
    Zwraca opis błędu albo ``None``.
    """
    if algorytm == "jakanie":
        rola = rola_slowa_jakania(src, cfg)
        if rola == "za_krotkie":
            if oczek != src:
                return (f"{src!r} → {oczek!r}: słowo krótsze niż "
                        f"`min_dlugosc_slowa`={cfg.get('min_dlugosc_slowa')} "
                        f"wraca NIETKNIĘTE")
            return None
        min_len = int(cfg.get("min_dlugosc_slowa", 3))
        samogloski = str(cfg.get("samogloski", ""))
        prefiks = (src[:2] if len(src) > min_len and src[1] not in samogloski
                   else src[0])
        czlony = oczek.split("-")
        if len(czlony) < 2:
            return (f"{src!r} → {oczek!r}: brak zająknięcia, a słowo jest "
                    f"dłuższe niż próg")
        oczek_prefiks, ogon = czlony[0], czlony[-1]
        # Silnik zwraca ogon jako `prefiks.lower() + reszta`, więc pierwsza litera
        # właściwego słowa jest ZAWSZE mała — na tym poległo `de` („St-st-Straße").
        poprawny_ogon = prefiks.lower() + src[len(prefiks):]
        if oczek_prefiks.lower() != prefiks.lower():
            return (f"{src!r} → {oczek!r}: zająknięcie powtarza "
                    f"{oczek_prefiks!r}, a silnik powtórzy {prefiks!r} "
                    f"({rola})")
        if ogon != poprawny_ogon:
            return (f"{src!r} → {oczek!r}: ogon to {ogon!r}, a silnik zapisze "
                    f"{poprawny_ogon!r} (reszta słowa idzie MAŁĄ literą)")
        ile = len(czlony) - 1
        min_pow, max_pow = int(cfg.get("min_powtorzen", 1)), int(cfg.get("max_powtorzen", 3))
        if not min_pow <= ile <= max_pow:
            return (f"{src!r} → {oczek!r}: {ile} powtórzeń poza zakresem "
                    f"{min_pow}..{max_pow}")
        return None

    if algorytm == "typoglikemia":
        min_len = int(cfg.get("min_dlugosc_slowa", 4))
        if len(src) < min_len:
            return None if oczek == src else (
                f"{src!r} → {oczek!r}: słowo krótsze niż "
                f"`min_dlugosc_slowa`={min_len} wraca nietknięte")
        if len(oczek) != len(src) or sorted(oczek) != sorted(src):
            return (f"{src!r} → {oczek!r}: to nie permutacja tego samego słowa "
                    f"(algorytm tylko MIESZA litery)")
        if oczek[0] != src[0] or oczek[-1] != src[-1]:
            return (f"{src!r} → {oczek!r}: pierwsza i ostatnia litera muszą "
                    f"zostać na miejscu")
        if oczek == src and len(src) > 3:
            return (f"{src!r} → {oczek!r}: środek NIE jest wymieszany — "
                    f"przykład nie pokazuje szyfru")
        return None

    if algorytm == "waz":
        min_syk, max_syk = int(cfg.get("min_syk", 4)), int(cfg.get("max_syk", 8))
        if _kolaps_powtorzen(oczek).lower() != _kolaps_powtorzen(src).lower():
            return (f"{src!r} → {oczek!r}: po zwinięciu powtórzeń wynik nie "
                    f"wraca do źródła — algorytm tylko WYDŁUŻA syk")
        najdluzsza = max((len(m.group(0)) for m in re.finditer(r"(.)\1+", oczek)),
                         default=0)
        if not min_syk <= najdluzsza <= max_syk + 1:
            return (f"{src!r} → {oczek!r}: najdłuższa seria to {najdluzsza} "
                    f"znaków, a zakres to {min_syk}..{max_syk}")
        return None

    if algorytm == "cezar":
        alfabet = str(cfg.get("alfabet") or podstawy.get("alfabet") or "")
        if not alfabet or len(src) != len(oczek):
            return None
        for przes in range(1, len(alfabet)):
            wynik = _wywolaj_algorytm("cezar", src, cfg, podstawy,
                                      {"przesuniecie_faktyczne": przes})
            if wynik == oczek:
                return None
        return (f"{src!r} → {oczek!r}: żadne przesunięcie z zakresu "
                f"1..{len(alfabet) - 1} nie daje tego wyniku")

    wynik = _wywolaj_algorytm(algorytm, src, cfg, podstawy)
    if wynik is None or wynik == oczek:
        return None
    return f"{src!r} → {oczek!r}: silnik daje {wynik!r}"


def _sprawdz_przyklady(
    kod: str, cfg_pl: dict, cfg: dict, podstawy: dict,
) -> tuple[list[str], list[str]]:
    """Pary „słowo → wynik" w `opis`. Zwraca ``(błędy, uwagi)``.

    BŁĄD to wyłącznie para SPRZECZNA z faktycznym algorytmem. Rozjazd LICZBY
    przykładów wobec PL jest tylko UWAGĄ, i to świadomie: liczba przykładów
    należy do redakcji paczki, nie do kontraktu. Osiem paczek nie ma
    odpowiednika polskiego „dzień → dźoń" (bo nie ma zmiękczeń), a `en` dorzuciło
    własny przykład węża („shake" → „ssssshake") i oba stany są poprawne —
    twarda równość dała w pierwszym przebiegu audytu 9 fałszywych alarmów.
    Halucynację „model dorzucił przykład" i tak łapie zgodność z silnikiem:
    model nie liczy wyjścia, więc jego wymyślona para prawie zawsze jest błędna.
    """
    algorytm = str(cfg.get("algorytm") or cfg_pl.get("algorytm") or "")
    if not algorytm:
        return [], []
    pary_pl = pary_z_opisu(str(cfg_pl.get("opis", "")))
    pary = pary_z_opisu(str(cfg.get("opis", "")))
    bledy: list[str] = []
    uwagi: list[str] = []
    if len(pary_pl) != len(pary):
        uwagi.append(
            f"`opis`: przykładów „słowo → wynik” jest {len(pary)}, a PL ma "
            f"{len(pary_pl)} — sprawdź, czy to redakcja tej paczki (gałąź "
            f"reguły, której ten język nie ma), a nie zgubiony przykład")
    for src, oczek in pary:
        blad = _sprawdz_pare(algorytm, src, oczek, cfg, podstawy)
        if blad:
            bledy.append(f"`opis` — przykład sprzeczny z silnikiem: {blad}")
    return bledy, uwagi


def waliduj_silnikiem(
    kod: str,
    folder: str,
    nazwa: str,
    cfg_pl: dict,
    kotwice: list[str],
    *,
    etykieta_przed: str | None = None,
) -> tuple[list[str], list[str]]:
    """Ładuje wynikową regułę SILNIKIEM i porównuje z polską.

    Zwraca ``(błędy, uwagi)``: błąd blokuje zapis (rollback), uwaga trafia do
    logu i checklisty recenzenta. Rozdział jest wnioskiem z pierwszego przebiegu
    audytu — patrz :func:`_sprawdz_przyklady`.

    Sprawdza kolejno:
      1. plik istnieje i silnik go widzi pod tym samym `id` co paczka PL
         (brak = `BrakRegulyDlaJezykaError` przy pierwszym akapicie tego języka),
      2. pola techniczne identyczne z PL (dispatch, progi, flagi),
      3. dane języka (:func:`_sprawdz_dane_jezyka`) — w tym zasięg Cezara,
      4. proza: niepusta, zbiór placeholderów i krotności kotwic jak w PL,
      5. przykłady dydaktyczne przeliczone silnikiem (:func:`_sprawdz_przyklady`),
      6. `etykieta` NIE zmieniła się wobec stanu przed przebiegiem, o ile plik
         już istniał — to kanoniczna nazwa szyfru dla całej paczki, cytowana
         w `ui.yaml` i w podręczniku; zmiana wymaga jawnej flagi,
      7. reguła realnie DZIAŁA: `core_poliglota.przetworz` na krótkim korpusie
         nie rzuca wyjątku i zwraca niepusty tekst,
      8. paczka nadal jest KOMPLETNA dla silnika (`_jezyk_kompletny`) plus
         crosscheck baz referencyjnych pl/en.
    """
    bledy: list[str] = []
    uwagi: list[str] = []
    plik = DICT_DIR / kod / folder / nazwa
    if not plik.is_file():
        return ([f"brak pliku {kod}/{folder}/{nazwa} — silnik zgłosiłby "
                 f"BrakRegulyDlaJezykaError przy pierwszym akapicie w tym języku"],
                uwagi)

    cp = _ustaw_silnik()
    tryb = TRYB_DLA_FOLDERU[folder]
    id_reguly = str(cfg_pl.get("id") or nazwa.rsplit(".", 1)[0])
    cfg = cp.wariant_po_id(tryb, kod, id_reguly)
    if cfg is None:
        return ([f"silnik nie widzi reguły o `id` = {id_reguly!r} w "
                 f"{kod}/{folder}/ (plik jest, ale `id` się rozjechało?)"], uwagi)
    podstawy = cp._zaladuj_podstawy(kod)

    for pole in POLA_TECHNICZNE:
        if pole not in cfg_pl:
            continue
        if cfg_pl.get(pole) != cfg.get(pole):
            bledy.append(
                f"pole techniczne `{pole}` rozjechało się: "
                f"PL={cfg_pl.get(pole)!r}, {kod}={cfg.get(pole)!r}")

    bledy += _sprawdz_dane_jezyka(kod, cfg_pl, cfg, podstawy)

    for pole, klasa in ((k, klasa_pola(k)) for k in cfg_pl):
        if klasa not in RODZAJ_PER_KLASA:
            continue
        t_pl = cfg_pl.get(pole)
        t_cel = cfg.get(pole)
        if not isinstance(t_pl, str) or not t_pl.strip():
            continue
        if not isinstance(t_cel, str) or not t_cel.strip():
            bledy.append(f"pole `{pole}` jest puste w {kod}, a niepuste w PL")
            continue
        ph_pl = set(tlumacz_rdzen.PLACEHOLDER_REGEX.findall(t_pl))
        ph_cel = set(tlumacz_rdzen.PLACEHOLDER_REGEX.findall(t_cel))
        if ph_pl != ph_cel:
            bledy.append(
                f"pole `{pole}`: zbiór placeholderów różny — brakuje "
                f"{sorted(ph_pl - ph_cel)}, nadmiar {sorted(ph_cel - ph_pl)}")
        for kotwica in kotwice:
            ile_pl, ile_cel = t_pl.count(kotwica), t_cel.count(kotwica)
            if ile_pl != ile_cel:
                bledy.append(
                    f"pole `{pole}`: kotwica {kotwica!r} — PL {ile_pl}×, "
                    f"{kod} {ile_cel}×")

    bledy_przykladow, uwagi_przykladow = _sprawdz_przyklady(
        kod, cfg_pl, cfg, podstawy)
    bledy += bledy_przykladow
    uwagi += uwagi_przykladow

    if etykieta_przed is not None:
        etykieta_teraz = str(cfg.get("etykieta", "")).strip()
        if etykieta_teraz != etykieta_przed.strip():
            bledy.append(
                f"`etykieta` zmieniła się z {etykieta_przed!r} na "
                f"{etykieta_teraz!r} — to KANONICZNA nazwa tej reguły dla całej "
                f"paczki (cytuje ją `ui.yaml` i podręcznik). Jeśli zmiana jest "
                f"zamierzona, uruchom z --pozwol-zmiane-etykiety i zaktualizuj "
                f"cytaty w docs/ui tego języka")

    try:
        opcje: dict[str, Any] = {"wymus_jezyk": kod}
        if cfg.get("kategoria") == "naprawiacz":
            opcje["iso_reczne"] = kod
        wynik = cp.przetworz(_KORPUS_SMOKE, tryb, kod, id_reguly, opcje)
        if not isinstance(wynik, str) or not wynik.strip():
            bledy.append("`przetworz` zwrócił pusty tekst dla korpusu testowego")
    except Exception as exc:  # noqa: BLE001 — dowolna wpadka reguły = błąd pliku
        bledy.append(f"`przetworz` rzucił {type(exc).__name__}: {exc}")

    try:
        if cp._jezyk_kompletny(kod) is not True:
            # Paczka BEZ `gui/ui.yaml` jest w budowie (pierwsze pliki nowego
            # języka), a nie zepsuta: silnik i tak jej nie pokaże, dopóki nie
            # dostanie interfejsu i po jednym pliku w czterech podfolderach.
            # Bez tego rozróżnienia narzędzie nie potrafiłoby zbudować nowej
            # paczki: pierwszy zapisany plik zawsze wracałby rollbackiem.
            w_budowie = not (DICT_DIR / kod / "gui" / "ui.yaml").is_file()
            komunikat = (
                f"`core_poliglota._jezyk_kompletny({kod!r})` ≠ True — paczka "
                f"niekompletna")
            if w_budowie:
                uwagi.append(komunikat + " (paczka W BUDOWIE: brak `gui/ui.yaml`, "
                             "więc silnik jej nie pokaże — dokończ pozostałe pliki)")
            else:
                bledy.append(komunikat)
        if kod in (KOD_ZRODLOWY, "en"):
            bazowe = cp.dostepne_jezyki_bazowe()
            if not {KOD_ZRODLOWY, "en"} <= set(bazowe):
                bledy.append(
                    f"crosscheck baz referencyjnych zerwany — dostępne bazowe: "
                    f"{bazowe}")
    except ImportError as exc:
        print(f"⚠️  {kod}/{nazwa}: pomijam kontrolę kompletności paczki ({exc}).")

    return bledy, uwagi


# ---------------------------------------------------------------------------
# KONTEKST PACZKI I SŁOWA PRZYKŁADOWE
# ---------------------------------------------------------------------------
def kontekst_paczki(kod: str, folder: str, nazwa: str) -> dict[str, str]:
    """Terminologia, którą paczka docelowa JUŻ ma (pusta, gdy pliku nie ma).

    Dla tego materiału najważniejszym wpisem jest `label`: nazwa szyfru bywa
    cytowana w `ui.yaml` i w podręczniku tej paczki (kanon „nazwy szyfrów zawsze
    z `<kod>/szyfry/<id>.yaml::etykieta`"), więc świeży synonim rozjechałby
    listę wyboru z dokumentacją. Drugim jest sam poprzedni `opis` — model widzi
    z niego, jakiego słowa paczka używa na „szyfr", „akcent" czy „czytnik ekranu".
    """
    plik = DICT_DIR / kod / folder / nazwa
    if not plik.is_file():
        return {}
    try:
        dane = YAML(typ="safe").load(plik.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — wskazówka to wygoda, nie bramka
        return {}
    if not isinstance(dane, dict):
        return {}
    wynik: dict[str, str] = {}
    for pole, nazwa_w_payloadzie in (("etykieta", "label"),
                                     ("opis", "previous_description")):
        wartosc = dane.get(pole)
        if isinstance(wartosc, str) and wartosc.strip():
            wynik[nazwa_w_payloadzie] = wartosc.strip()
    return wynik


def slowa_przykladowe(
    kod: str,
    folder: str,
    nazwa: str,
    cfg_efektywne: dict,
    cfg_pl: dict,
    dane_llm: dict[str, Any] | None,
) -> tuple[list[str], list[str]]:
    """Słowa, na których policzymy przykłady dla języka docelowego.

    Zwraca ``(słowa, uwagi)``. Źródła w kolejności zaufania:

    1. **słowa z ISTNIEJĄCEGO `opis` paczki docelowej** — najlepsze, jakie mamy:
       przeszły recenzję native speakera, a przy okazji przekład nie przestawia
       userowi przykładów, które zna z poprzedniego wydania,
    2. **słowa z mini-wywołania danych języka** (nowa paczka).

    Dla jąkania kolejność słów jest ROLĄ, nie kolejnością: dopasowujemy je do
    gałęzi algorytmu policzonej dla DOCELOWYCH `samogloski`/`min_dlugosc_slowa`.
    Rola bez pokrycia jest raportowana — wtedy model zachowa parę ze źródła PL,
    a walidacja i tak przeliczy ją silnikiem (nie zgadujemy natywnego słowa).
    """
    algorytm = str(cfg_efektywne.get("algorytm") or "")
    pary_pl = pary_z_opisu(str(cfg_pl.get("opis", "")))
    if not pary_pl:
        return [], []

    uwagi: list[str] = []
    plik = DICT_DIR / kod / folder / nazwa
    if plik.is_file():
        try:
            dane = YAML(typ="safe").load(plik.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            dane = None
        if isinstance(dane, dict):
            z_celu = [s for s, _ in pary_z_opisu(str(dane.get("opis", "")))]
            if z_celu:
                # WSZYSTKIE słowa paczki, w jej kolejności i bez dobierania rol:
                # są zrecenzowane, a user zna je z poprzedniego wydania. Gdyby
                # narzędzie dobierało je pod gałęzie polskiego opisu, wyrzuciłoby
                # islandzkie „stelpa" tylko dlatego, że islandzki nie ma słowa
                # z samogłoską na drugiej pozycji — i wróciłby polski „komputer".
                return z_celu, uwagi

    kandydaci = [s for s in (dane_llm or {}).get("_slowa_przykladowe", [])
                 if isinstance(s, str)]
    if not kandydaci:
        return [], [f"{kod}/{nazwa}: nie mam natywnych słów-przykładów — model "
                    f"zobaczy pary polskie i bramka je przeliczy silnikiem"]

    if algorytm != "jakanie":
        # Pozostałe algorytmy mają jedną gałąź na przykład, więc bierzemy słowa
        # pozycyjnie i tyle, ile par ma źródło.
        return kandydaci[:len(pary_pl)], uwagi

    # Nowa paczka: pilnujemy, żeby każda gałąź reguły dostała słowo o WŁAŚCIWEJ
    # klasyfikacji, policzonej dla DOCELOWYCH `samogloski`/`min_dlugosc_slowa` —
    # model podaje kandydatów, arytmetykę robi Python (decyzja P2 z planu etapu).
    role_pl = [rola_slowa_jakania(s, cfg_pl) for s, _ in pary_pl]
    dostepne = {rola_slowa_jakania(s, cfg_efektywne): s for s in kandydaci}
    wybrane: list[str] = []
    for rola in role_pl:
        slowo = dostepne.get(rola)
        if slowo is None:
            uwagi.append(
                f"{kod}/{nazwa}: model nie podał słowa dla gałęzi {rola!r} "
                f"(kandydaci: {kandydaci}) — ta jedna para zostanie ze źródła PL")
            continue
        if slowo not in wybrane:
            wybrane.append(slowo)
    return wybrane, uwagi


# ---------------------------------------------------------------------------
# PIPELINE: jeden plik → jeden język
# ---------------------------------------------------------------------------
_yaml_io = tlumacz_rdzen.yaml_io


def wykryj_kotwice(
    teksty_pl: list[str],
    odniesienia: dict[str, str] | None,
    dodatkowe: tuple[str, ...] = (),
) -> list[str]:
    """Kotwice pliku: heurystyka + orakuł jednomyślności + literały silnika."""
    return tlumacz_rdzen.wykryj_kotwice(
        teksty_pl, odniesienia, dodatkowe, _kotwice_z_silnika())


def wczytaj_orakuly(
    folder: str, pliki: list[str], *, dopusc_drafty: bool = False,
) -> dict[str, dict[str, str]]:
    """Wczytuje pliki paczek odniesienia PRZED zapisem (implementacja w rdzeniu)."""
    return tlumacz_rdzen.wczytaj_orakuly(
        DICT_DIR, folder, pliki,
        kod_zrodlowy=KOD_ZRODLOWY, dopusc_drafty=dopusc_drafty)


def _wywolaj(
    klient: Any, model: str, kod: str,
    pozycje: list[tuple[int, str, str]],
    *,
    kontekst: dict[str, str] | None,
    pola_payloadu: dict[str, Any] | None,
) -> dict[int, str]:
    """Jedno wywołanie LLM z promptem tłumaczenia reguł."""
    nazwa_cel = _natywna_nazwa(kod)
    return tlumacz_rdzen.wywolaj_llm(
        klient,
        model=model,
        system=_PROMPT_SYSTEMOWY(nazwa_cel, kod),
        nazwa_celu=nazwa_cel,
        kod=kod,
        pozycje=pozycje,
        max_tokens=MAX_TOKENS_OUT,
        wskazowka_limitu=(
            f"Zmniejsz BATCH_MAX_ZNAKOW (obecnie {BATCH_MAX_ZNAKOW}) "
            f"i uruchom ponownie."),
        kontekst_paczki=kontekst,
        pola_payloadu=pola_payloadu,
    )


def _bramki_z_powtorka(
    jednostki: list[Jednostka],
    mapa_tgt: dict[int, str],
    kod: str,
    nazwa: str,
    klient: Any,
    model: str,
    *,
    kontekst: dict[str, str] | None,
    pola_payloadu: dict[str, Any] | None,
    slowa_zakazane: tuple[str, ...] = (),
    wzorce_pustych_krokow: tuple[str, ...] = (),
    cfg_dla_przykladow: dict | None = None,
    podstawy: dict | None = None,
) -> bool:
    """Bramki per jednostka + jednorazowa powtórka z czystym kontekstem."""
    porazki: list[tuple[Jednostka, list[str]]] = []
    for j in jednostki:
        j.cel = mapa_tgt[j.id]
        problemy, uwagi = waliduj_jednostke(
            j.zrodlo_tok, j.cel, j.klasa, slowa_zakazane=slowa_zakazane,
            wzorce_pustych_krokow=wzorce_pustych_krokow,
            cfg_dla_przykladow=cfg_dla_przykladow, podstawy=podstawy)
        for uwaga in uwagi:
            print(f"⚠️  {kod}/{nazwa} [{j.id}] {j.opis()}: {uwaga}")
        if problemy:
            porazki.append((j, problemy))
    if not porazki:
        return True

    print(f"⚠️  {kod}/{nazwa}: {len(porazki)} jednostek do powtórki…")
    for j, problemy in porazki[:6]:
        print(f"     [{j.id}] {j.opis()}: {problemy[0]}")
    do_retry = [(j.id, j.rodzaj, j.zrodlo_tok) for j, _ in porazki]
    # SELF-CORRECTION: powtórka dostaje KONKRETNE zarzuty do poprzedniej próby.
    # Bez tego jest ślepym losowaniem — empiria testu `sv`: pierwsza próba miała
    # już poprawny szwedzki przykład, a powtórka wróciła do polskiego „dzień".
    # Wzorzec `--retry` z v17.0, przeniesiony na payload structured-outputs.
    payload_retry = dict(pola_payloadu or {})
    payload_retry["previous_attempt_problems"] = [
        {"id": j.id, "rejected_because": problemy} for j, problemy in porazki]
    try:
        retry = _wywolaj(klient, model, kod, do_retry,
                         kontekst=kontekst, pola_payloadu=payload_retry)
    except RuntimeError as exc:
        print(f"❌ {kod}/{nazwa}: powtórka nieudana — {exc}")
        return False
    zamowione = {j.id for j, _ in porazki}
    porazki_v2: list[tuple[Jednostka, list[str]]] = []
    for j, _ in porazki:
        if j.id in retry:
            j.cel = retry[j.id]
        problemy, _uwagi = waliduj_jednostke(
            j.zrodlo_tok, j.cel, j.klasa, slowa_zakazane=slowa_zakazane,
            wzorce_pustych_krokow=wzorce_pustych_krokow,
            cfg_dla_przykladow=cfg_dla_przykladow, podstawy=podstawy)
        if problemy:
            porazki_v2.append((j, problemy))
    nieproszone = set(retry) - zamowione
    if nieproszone:
        print(f"⚠️  {kod}: powtórka zwróciła {len(nieproszone)} nieproszonych id "
              f"— ignoruję: {sorted(nieproszone)[:10]}")
    if porazki_v2:
        print(f"❌ {kod}/{nazwa}: po powtórce {len(porazki_v2)} jednostek wciąż "
              f"nie przechodzi bramek. NIE zapisuję.")
        for j, problemy in porazki_v2[:10]:
            print(f"     [{j.id}] {j.opis()} ({j.rodzaj})")
            for diag in problemy[:4]:
                print(f"       • {diag}")
        return False
    print(f"✅ {kod}/{nazwa}: powtórka naprawiła wszystkie {len(porazki)} jednostek.")
    return True


def _wstaw_dane_jezyka(drzewo: Any, pole: str, wartosc: Any) -> None:
    """Wstawia wartość klasy :data:`KLASA_DANE`, ratując komentarze ruamel.

    Puenta empiryczna (test tożsamościowy na `samogloskowiec.yaml`): ruamel
    przyczepia blok komentarza otwierający NASTĘPNĄ sekcję do OSTATNIEGO
    ELEMENTU listy, która ją poprzedza. Zwykłe przypisanie
    ``drzewo[pole] = nowa_lista`` niszczy więc cudzy komentarz — plik traci
    „# Krok 2: …”, choć nikt tego nie prosił. `clear()` + `extend()` na tym
    samym obiekcie `CommentedSeq` zachowuje go (sprawdzone: 4 bloki → 4).

    Jedyny przypadek, którego nie da się uratować, to lista OPRÓŻNIANA do zera
    (dla nowej paczki `zmiekszenia_*`): komentarz ginie razem z elementem, do
    którego był przyczepiony. Jest to zgodne z kanonem repo — wszystkie osiem
    obcych paczek nie ma bloku „Krok 2", bo nie mają kroku 2 — a
    :func:`_podmien_komentarze` raportuje wtedy uwagę zamiast wywracać zapis.
    """
    stara = drzewo.get(pole)
    if isinstance(stara, list) and isinstance(wartosc, list):
        stara.clear()
        stara.extend(wartosc)
        return
    drzewo[pole] = wartosc


def _podmien_komentarze(
    dump_cel: str,
    jednostki: list[Jednostka],
    bloki_pl: list[dict],
    koncowe_pl: list[dict],
    kod: str,
    nazwa: str,
) -> str | None:
    """Wstawia przetłumaczone komentarze do dumpu. ``None`` = rozjazd layoutu.

    Bloki dopasowujemy PO TREŚCI, nie po indeksie: dump celu to dump klona PL,
    więc jego komentarze są jeszcze dosłownie polskie i identyczne ze
    źródłowymi — ale ich LICZBA może być mniejsza, gdy wstawienie danych języka
    opróżniło listę, do której ruamel przyczepił blok (patrz
    :func:`_wstaw_dane_jezyka`). Dopasowanie po treści przechodzi przez taki
    ubytek bez fałszywego alarmu, a mimo to nie wstawi tłumaczenia w niewłaściwe
    miejsce: kolejność jest monotoniczna, a treść musi się zgadzać dokładnie.
    """
    bloki_cel = tlumacz_rdzen.bloki_komentarzy(dump_cel, pomin_naglowek=False)
    koncowe_cel = tlumacz_rdzen.komentarze_koncowe(dump_cel)
    if len(koncowe_cel) != len(koncowe_pl):
        print(f"❌ {kod}/{nazwa}: layout komentarzy końcowych rozjechał się "
              f"({len(koncowe_pl)}→{len(koncowe_cel)}). NIE zapisuję.")
        return None
    if len(bloki_cel) > len(bloki_pl):
        print(f"❌ {kod}/{nazwa}: dump celu ma WIĘCEJ bloków komentarzy niż PL "
              f"({len(bloki_pl)}→{len(bloki_cel)}) — czegoś nie rozumiem w tym "
              f"layoucie. NIE zapisuję.")
        return None

    tlum_bloki = {j.adres[1]: j.cel for j in jednostki if j.adres[0] == "komentarz"}
    tlum_koncowe = {
        j.adres[1]: j.cel for j in jednostki if j.adres[0] == "komentarz_koncowy"}

    # Dopasowanie greedy: idziemy oboma listami w przód, blok celu musi być
    # identyczny z blokiem PL o bieżącym indeksie.
    pary: list[tuple[dict, int]] = []
    idx_pl = 0
    for blok_cel in bloki_cel:
        while idx_pl < len(bloki_pl) and bloki_pl[idx_pl]["tresc"] != blok_cel["tresc"]:
            idx_pl += 1
        if idx_pl >= len(bloki_pl):
            print(f"❌ {kod}/{nazwa}: blok komentarza z dumpu celu nie ma "
                  f"odpowiednika w PL — przerywam (ryzyko wstawienia nie tam).")
            return None
        pary.append((blok_cel, idx_pl))
        idx_pl += 1
    zgubione = [i for i in range(len(bloki_pl)) if i not in {j for _, j in pary}]
    if zgubione:
        print(f"⚠️  {kod}/{nazwa}: {len(zgubione)} blok(ów) komentarza zniknęło "
              f"przy wstawianiu danych języka (ruamel trzyma je przy ostatnim "
              f"elemencie opróżnionej listy) — dopisz je ręcznie, jeśli opisują "
              f"coś, co w tej paczce nadal istnieje.")

    linie = dump_cel.split("\n")
    for blok_cel, idx in reversed(pary):        # od końca — numeracja linii
        if idx not in tlum_bloki:
            continue
        linie[blok_cel["start"]:blok_cel["koniec"]] = \
            tlumacz_rdzen.zloz_blok_komentarza(tlum_bloki[idx], blok_cel["wciecie"])
    dump_cel = "\n".join(linie)

    linie = dump_cel.split("\n")
    for idx, wpis in enumerate(tlumacz_rdzen.komentarze_koncowe(dump_cel)):
        if idx not in tlum_koncowe:
            continue
        if wpis["tresc"] != koncowe_pl[idx]["tresc"]:
            print(f"⚠️  {kod}/{nazwa}: komentarz końcowy #{idx} nie zgadza się z PL "
                  f"— zostawiam polski.")
            continue
        linie[wpis["linia"]] = (
            f"{wpis['przed']}{wpis['odstep']}# {tlum_koncowe[idx].strip()}")
    return "\n".join(linie)


def _zapisz_z_walidacja(
    cel: Path, zawartosc: str, kod: str, folder: str, nazwa: str,
    cfg_pl: dict, kotwice: list[str], etykieta_przed: str | None,
) -> bool:
    """Zapisuje plik i uruchamia walidację silnikiem; przy błędach ROLLBACK."""
    kopia = cel.read_text(encoding="utf-8") if cel.is_file() else None
    cel.parent.mkdir(parents=True, exist_ok=True)
    with open(cel, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(zawartosc)

    bledy, uwagi = waliduj_silnikiem(kod, folder, nazwa, cfg_pl, kotwice,
                                     etykieta_przed=etykieta_przed)
    for uwaga in uwagi:
        print(f"⚠️  {kod}/{folder}/{nazwa}: {uwaga}")
    if not bledy:
        return True
    print(f"❌ {kod}/{folder}/{nazwa}: walidacja silnikiem odrzuciła plik "
          f"({len(bledy)} błąd/y):")
    for b in bledy[:12]:
        print(f"     • {b}")
    if kopia is None:
        cel.unlink(missing_ok=True)
        print("     ↩ usunięto świeżo zapisany plik (paczka wraca do stanu przed).")
    else:
        cel.write_text(kopia, encoding="utf-8", newline="\n")
        print(f"     ↩ przywrócono poprzednią treść {cel.name}.")
    return False


def tlumacz_plik(
    kod: str,
    folder: str,
    nazwa: str,
    klient: Any,
    *,
    model: str,
    skip_existing: bool,
    dry_run: bool,
    kotwice_extra: tuple[str, ...],
    orakuly: dict[str, str],
    dane_llm: dict[str, Any] | None,
    pozwol_zmiane_etykiety: bool,
) -> tuple[bool, list[Jednostka]]:
    """Tłumaczy jedną regułę na jeden język. Zwraca (sukces, jednostki).

    Nie zapisuje NICZEGO, dopóki wszystkie bramki nie przejdą; przy porażce
    walidacji silnikiem przywraca poprzednią treść pliku (albo go usuwa, jeśli
    powstał w tym przebiegu). Dane języka wchodzą do wyniku Z PLIKU DOCELOWEGO,
    a dla nowej paczki są wyprowadzane — nigdy nie jadą kopią z PL.
    """
    zrodlo = DICT_DIR / KOD_ZRODLOWY / folder / nazwa
    cel = DICT_DIR / kod / folder / nazwa
    if cel.exists() and skip_existing:
        print(f"⏭️  {kod}/{nazwa}: już istnieje — pomijam (--skip-existing).")
        return True, []

    yaml_io = _yaml_io()
    tekst_zrodla = zrodlo.read_text(encoding="utf-8")
    drzewo_pl = yaml_io.load(tekst_zrodla)
    if not isinstance(drzewo_pl, dict):
        print(f"❌ {zrodlo}: plik nie parsuje się do mapy YAML.")
        return False, []
    cfg_pl = {str(k): drzewo_pl[k] for k in drzewo_pl.keys()}

    # --- Dane języka: z celu (istniejąca paczka) albo wyprowadzone (nowa) ----
    podstawy_cel = _podstawy_paczki(kod)
    dane_jezyka = wartosci_danych_z_celu(kod, folder, nazwa)
    if dane_jezyka:
        print(f"🔒 {kod}/{nazwa}: dane języka biorę z istniejącego pliku "
              f"({', '.join(sorted(dane_jezyka))}) — nie tykam ich.")
    else:
        dane_jezyka, braki = wyprowadz_dane_jezyka(
            kod, nazwa, cfg_pl, podstawy_cel, dane_llm=dane_llm)
        if braki:
            print(f"❌ {kod}/{folder}/{nazwa}: nie mam wyprowadzonych danych "
                  f"języka — NIE zapisuję (cicha kopia polskich wartości dałaby "
                  f"regułę działającą na polskich literach):")
            for brak in braki:
                print(f"     • {brak}")
            return False, []
        if dane_jezyka:
            print(f"🧮 {kod}/{nazwa}: dane języka WYPROWADZONE dla nowej paczki "
                  f"({', '.join(sorted(dane_jezyka))}).")

    # Konfiguracja EFEKTYWNA = szkielet PL + dane języka docelowego. Na niej
    # liczymy przykłady, bo `_algo_*` czyta z niej i progi (PL), i litery (cel).
    cfg_efektywne = {**cfg_pl, **dane_jezyka}

    # Dump PL-a jest ODNIESIENIEM LAYOUTU: komentarze wyciągamy z niego (nie
    # z pliku źródłowego), bo dump celu ma identyczne komentarze w identycznej
    # kolejności — inaczej indeksowanie bloków mogłoby się rozjechać.
    buf = io.StringIO()
    yaml_io.dump(drzewo_pl, buf)
    dump_pl = buf.getvalue()
    bloki_pl = tlumacz_rdzen.bloki_komentarzy(dump_pl, pomin_naglowek=False)
    koncowe_pl = tlumacz_rdzen.komentarze_koncowe(dump_pl)

    jednostki = zbierz_jednostki_pol(drzewo_pl, f"{KOD_ZRODLOWY}/{folder}/{nazwa}")
    licznik = len(jednostki)
    for idx, blok in enumerate(bloki_pl):
        if not blok["tresc"].strip() or tlumacz_rdzen.RE_DEKORACJA.match(blok["tresc"]):
            continue
        jednostki.append(Jednostka(
            licznik, "comment", KLASA_ETYKIETA, ("komentarz", idx), blok["tresc"]))
        licznik += 1
    for idx, wpis in enumerate(koncowe_pl):
        jednostki.append(Jednostka(
            licznik, "comment", KLASA_ETYKIETA,
            ("komentarz_koncowy", idx), wpis["tresc"]))
        licznik += 1

    odniesienia = {k: v for k, v in orakuly.items() if k != kod}
    kotwice = wykryj_kotwice([j.zrodlo for j in jednostki], odniesienia, kotwice_extra)
    if not odniesienia:
        print(f"⚠️  {kod}/{nazwa}: żadna inna paczka nie ma tego pliku — orakuł "
              f"kotwic nieaktywny, zamrażam WSZYSTKICH {len(kotwice)} kandydatów.")
    for j in jednostki:
        j.zrodlo_tok, j.mapa = tlumacz_rdzen.tokenizuj(j.zrodlo, kotwice)

    print(f"ℹ️  {kod}/{folder}/{nazwa}: {len(jednostki)} jednostek "
          f"({sum(1 for j in jednostki if j.rodzaj == 'comment')} komentarzy), "
          f"{len(kotwice)} kotwic, {sum(len(j.mapa) for j in jednostki)} zamrożeń, "
          f"{len(tekst_zrodla):,} znaków źródła.")

    if dry_run:
        print(f"    Kotwice ({len(kotwice)}): "
              + ", ".join(repr(k) for k in kotwice[:10])
              + (" …" if len(kotwice) > 10 else ""))
        for j in jednostki[:3]:
            print(f"      [{j.id}] {j.opis()} ({j.rodzaj}) → {j.zrodlo_tok[:100]!r}")
        print(f"    Chunków do wysłania: "
              f"{len(tlumacz_rdzen.chunkuj(jednostki, BATCH_MAX_ZNAKOW))}")
        podglad, uwagi_dr = slowa_przykladowe(
            kod, folder, nazwa, cfg_efektywne, cfg_pl, dane_llm)
        if podglad:
            print(f"    Przykłady policzone silnikiem: "
                  f"{przyklady_wyliczone(str(cfg_efektywne.get('algorytm', '')), podglad, cfg_efektywne, podstawy_cel)}")
        for uwaga in uwagi_dr:
            print(f"    ⚠️  {uwaga}")
        print(f"    (dry-run) Nie wywołuję API, nie zapisuję {kod}/{nazwa}.")
        return True, []

    # --- Fakty policzone po stronie Pythona ----------------------------------
    slowa, uwagi = slowa_przykladowe(kod, folder, nazwa, cfg_efektywne, cfg_pl,
                                     dane_llm)
    for uwaga in uwagi:
        print(f"⚠️  {uwaga}")
    pola_payloadu: dict[str, Any] = {}
    algorytm = str(cfg_efektywne.get("algorytm", ""))
    if slowa:
        wyliczone = przyklady_wyliczone(algorytm, slowa, cfg_efektywne, podstawy_cel)
        if wyliczone:
            pola_payloadu["computed_examples"] = wyliczone
            print(f"🧮 {kod}/{nazwa}: przykłady policzone silnikiem: "
                  + ", ".join(f"{w['source_word']}→{w['engine_output']}"
                              for w in wyliczone))
    if algorytm == "cezar":
        pola_payloadu["alphabet_facts"] = fakty_alfabetu(cfg_efektywne, podstawy_cel)
    # Pola danych, które w TYM języku są puste, a w PL niepuste: model musi
    # wiedzieć, że opisywany krok algorytmu nie ma tu zastosowania (inaczej
    # przepisuje polski przykład zmiękczeń do paczki, która ich nie zna —
    # empiria testu `sv`, gdzie model dwukrotnie zostawił „dzień → dźoń").
    puste = sorted(
        pole for pole in POLA_DANYCH
        if pole in cfg_pl and not _pusta(cfg_pl[pole])
        and _pusta(dane_jezyka.get(pole, cfg_pl[pole])))
    if puste:
        pola_payloadu["empty_rule_data"] = puste
        print(f"ℹ️  {kod}/{nazwa}: pola danych puste w tym języku: {puste} — "
              f"model dostaje instrukcję, żeby nie tłumaczyć ich przykładów.")

    kontekst = kontekst_paczki(kod, folder, nazwa)
    etykieta_przed = kontekst.get("label") if not pozwol_zmiane_etykiety else None
    if kontekst:
        print(f"🔤 {kod}/{nazwa}: terminologia paczki podana modelowi "
              f"(label={kontekst.get('label')!r}).")

    # --- Wywołania LLM -------------------------------------------------------
    chunki = tlumacz_rdzen.chunkuj(jednostki, BATCH_MAX_ZNAKOW)
    mapa_tgt: dict[int, str] = {}
    print(f"🌍 {kod}/{nazwa}: {model} (cel: {_natywna_nazwa(kod)}), "
          f"{len(chunki)} chunk(ów)…")
    for nr, chunk in enumerate(chunki, start=1):
        pozycje = [(j.id, j.rodzaj, j.zrodlo_tok) for j in chunk]
        try:
            mapa_tgt.update(_wywolaj(klient, model, kod, pozycje,
                                     kontekst=kontekst,
                                     pola_payloadu=pola_payloadu))
        except RuntimeError as exc:
            print(f"❌ {kod}/{nazwa}: błąd LLM w chunku {nr}/{len(chunki)} — {exc}")
            return False, []

    brakujace = {j.id for j in jednostki} - set(mapa_tgt)
    if brakujace:
        print(f"❌ {kod}/{nazwa}: model pominął id {sorted(brakujace)[:20]} "
              f"(razem {len(brakujace)}). NIE zapisuję.")
        return False, []

    if not _bramki_z_powtorka(jednostki, mapa_tgt, kod, nazwa, klient, model,
                              kontekst=kontekst, pola_payloadu=pola_payloadu,
                              slowa_zakazane=tuple(
                                  s for s, _ in pary_z_opisu(
                                      str(cfg_pl.get("opis", "")))),
                              wzorce_pustych_krokow=_wzorce_pustych_krokow(
                                  cfg_pl, dane_jezyka),
                              cfg_dla_przykladow=cfg_efektywne,
                              podstawy=podstawy_cel):
        return False, []

    # --- Detokenizacja + iniekcja do klona drzewa PL ------------------------
    for j in jednostki:
        j.cel = tlumacz_rdzen.detokenizuj(j.cel, j.mapa)

    drzewo_cel = yaml_io.load(dump_pl)
    for j in jednostki:
        if j.adres[0] == "sciezka":
            tlumacz_rdzen.wstaw_po_sciezce(drzewo_cel, j.kroki, j.cel)
    for pole, wartosc in dane_jezyka.items():
        _wstaw_dane_jezyka(drzewo_cel, pole, wartosc)

    buf = io.StringIO()
    yaml_io.dump(drzewo_cel, buf)
    dump_cel = _podmien_komentarze(buf.getvalue(), jednostki, bloki_pl,
                                   koncowe_pl, kod, nazwa)
    if dump_cel is None:
        return False, []

    zawartosc = _baner_draftu(kod, folder, nazwa) + dump_cel
    if not _zapisz_z_walidacja(cel, zawartosc, kod, folder, nazwa, cfg_pl,
                               kotwice, etykieta_przed):
        return False, []
    print(f"✅ {kod}/{folder}/{nazwa}: zapisano DRAFT "
          f"({len(jednostki)} jednostek, {len(zawartosc):,} znaków).")
    return True, jednostki


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _pliki_zrodlowe() -> list[tuple[str, str]]:
    """Pary ``(folder, nazwa)`` w zakresie narzędzia, wg paczki PL."""
    pary: list[tuple[str, str]] = []
    for folder, whitelista in ZAKRES.items():
        katalog = DICT_DIR / KOD_ZRODLOWY / folder
        if not katalog.is_dir():
            raise SystemExit(f"❌ Brak folderu źródłowego: {katalog}")
        for plik in sorted(katalog.glob("*.yaml")):
            if whitelista is not None and plik.name not in whitelista:
                continue
            pary.append((folder, plik.name))
    if not pary:
        raise SystemExit(
            f"❌ dictionaries/{KOD_ZRODLOWY}/ nie zawiera żadnej reguły z zakresu "
            f"(szyfry/*.yaml + {', '.join(NARZEDZIA_AKCENTOW)}).")
    return pary


def _filtruj_pliki(wybor_csv: str) -> list[tuple[str, str]]:
    """Zawęża listę reguł do CSV z `--reguly` (bare-name dozwolony)."""
    wszystkie = _pliki_zrodlowe()
    if not wybor_csv.strip():
        return wszystkie
    wybrane: set[str] = set()
    for pozycja in wybor_csv.split(","):
        nazwa = pozycja.strip()
        if not nazwa:
            continue
        if not nazwa.endswith((".yaml", ".yml")):
            nazwa += ".yaml"
        wybrane.add(nazwa)
    dostepne = {n for _, n in wszystkie}
    nieznane = sorted(wybrane - dostepne)
    if nieznane:
        raise SystemExit(
            f"❌ Nieznane reguły: {nieznane}.\n"
            f"   Dostępne: {', '.join(sorted(dostepne))}")
    return [(f, n) for f, n in wszystkie if n in wybrane]


def _parsuj_argumenty() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Batchowy autotłumacz reguł Poligloty (dictionaries/<kod>/szyfry/*.yaml "
            f"+ {', '.join(NARZEDZIA_AKCENTOW)} z akcenty/) na języki: "
            f"{', '.join(MAPA_JEZYKOW)}. Round-trip ruamel (komentarze i bloki "
            "zachowane), zamrażanie kotwic, bramki anty-meta-skip, przykłady "
            "liczone SILNIKIEM, walidacja silnikiem z rollbackiem."),
    )
    grupa = parser.add_mutually_exclusive_group(required=True)
    grupa.add_argument(
        "-l", "--jezyki", type=str, default="",
        help=f"CSV kodów ISO (np. `de,fi`). Dozwolone: {', '.join(MAPA_JEZYKOW)}.")
    grupa.add_argument(
        "-a", "--wszystkie", action="store_true",
        help=f"Wszystkie języki docelowe ({', '.join(MAPA_JEZYKOW)}).")
    parser.add_argument(
        "-r", "--reguly", type=str, default="",
        help="CSV nazw plików (np. `waz` albo `cezar.yaml`). Puste = wszystkie "
             "reguły z zakresu.")
    parser.add_argument(
        "--slowniki", type=str, default="",
        help="Ścieżka do katalogu `dictionaries` INNEGO niż repo — np. paczki "
             "zainstalowanej aplikacji. Domyślnie katalog repo.")
    parser.add_argument(
        "--skip-existing", action="store_true",
        help="Pomiń pary (język, reguła), dla których plik docelowy już istnieje.")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Podział na jednostki, kotwice, tokeny i PRZYKŁADY policzone "
             "silnikiem. Zero wywołań API.")
    parser.add_argument(
        "--model", default=MODEL_DOMYSLNY,
        help=f"Model Anthropic do tłumaczenia (domyślnie: {MODEL_DOMYSLNY}).")
    parser.add_argument(
        "--kotwica", type=str, default="", metavar="LITERAŁ[,LITERAŁ...]",
        help="Dodatkowe literały wymuszone jako kotwice (zamrażane bez pytania "
             "orakułu). UWAGA: nie wymuszaj terminu, który w JĘZYKU DOCELOWYM "
             "jest wyrazem rodzimym — zamrożony mianownik blokuje odmianę.")
    parser.add_argument(
        "--orakul-drafty", action="store_true",
        help="Dopuść paczki-DRAFTY jako orakuł kotwic (gdy regułę właśnie "
             "rozpropagowano na N języków i dostrajasz paczkę bazową).")
    parser.add_argument(
        "--pozwol-zmiane-etykiety", action="store_true",
        help="Pozwól, by tłumaczenie ZMIENIŁO istniejącą `etykieta`. Domyślnie "
             "jest to błąd: etykieta to kanoniczna nazwa reguły dla całej paczki "
             "(cytują ją `ui.yaml` i podręcznik), więc zmiana wymaga ręcznej "
             "aktualizacji tych cytatów.")
    parser.add_argument(
        "--tylko-walidacja", action="store_true",
        help="Zero API: dla wybranych języków/reguł uruchamia samą WALIDACJĘ "
             "SILNIKIEM istniejących plików (pola techniczne, dane języka, "
             "zasięg Cezara, przykłady przeliczone algorytmem, kotwice, "
             "kompletność paczki). Jedyny audyt porównujący paczki między sobą.")
    parser.add_argument(
        "-f", "--finalizuj", action="store_true",
        help="Zero API: zdejmuje baner DRAFTU z wybranych plików, zostawiając "
             "treść (z ręcznymi poprawkami recenzenta) i przetłumaczony nagłówek "
             "autorski. To właściwy krok po akceptacji przeglądu.")
    args = parser.parse_args()
    tryby_lokalne = sum(bool(x) for x in (args.finalizuj, args.tylko_walidacja))
    if tryby_lokalne and (args.skip_existing or args.dry_run):
        parser.error("--finalizuj / --tylko-walidacja to operacje lokalne (zero API) "
                     "— nie łącz ich z --skip-existing/--dry-run.")
    if tryby_lokalne > 1:
        parser.error("--finalizuj i --tylko-walidacja wykluczają się wzajemnie.")
    return args


def _wybierz_jezyki(args: argparse.Namespace) -> list[str]:
    if args.wszystkie:
        return list(MAPA_JEZYKOW.keys())
    kody = [k.strip() for k in args.jezyki.split(",") if k.strip()]
    nieznane = [k for k in kody if k not in MAPA_JEZYKOW]
    if nieznane:
        raise SystemExit(
            f"❌ Nieznane kody języków: {', '.join(nieznane)}.\n"
            f"   Dozwolone: {', '.join(MAPA_JEZYKOW)}.")
    return kody


def _tryb_finalizuj(kody: list[str], pliki: list[tuple[str, str]]) -> int:
    zmienione = nie_drafty = braki = 0
    for kod in kody:
        for folder, nazwa in pliki:
            cel = DICT_DIR / kod / folder / nazwa
            if not cel.is_file():
                braki += 1
                print(f"⚠️  {kod}/{folder}/{nazwa}: plik nie istnieje — pomijam.")
                continue
            tresc, zdjeto = zdejmij_baner_draftu(cel.read_text(encoding="utf-8"))
            if not zdjeto:
                nie_drafty += 1
                print(f"⏭️  {kod}/{folder}/{nazwa}: brak banera draftu — pomijam.")
                continue
            cel.write_text(tresc, encoding="utf-8", newline="\n")
            zmienione += 1
            print(f"✅ {kod}/{folder}/{nazwa}: baner draftu zdjęty.")
    print("\n========== PODSUMOWANIE (--finalizuj) ==========")
    print(f"✅ sfinalizowane: {zmienione} | ⏭️ już finalne: {nie_drafty} "
          f"| ⚠️ brak pliku: {braki}")
    return 0


def _tryb_walidacji(
    kody: list[str], pliki: list[tuple[str, str]], args: argparse.Namespace,
) -> int:
    yaml_io = _yaml_io()
    extra = tuple(k.strip() for k in args.kotwica.split(",") if k.strip())
    wszystkie_bledy = 0
    wszystkie_uwagi = 0
    orakuly_per_folder: dict[str, dict[str, dict[str, str]]] = {}
    for folder in {f for f, _ in pliki}:
        orakuly_per_folder[folder] = wczytaj_orakuly(
            folder, [n for f, n in pliki if f == folder],
            dopusc_drafty=args.orakul_drafty)
    for folder, nazwa in pliki:
        zrodlo = DICT_DIR / KOD_ZRODLOWY / folder / nazwa
        drzewo_pl = yaml_io.load(zrodlo.read_text(encoding="utf-8"))
        cfg_pl = {str(k): drzewo_pl[k] for k in drzewo_pl.keys()}
        jednostki = zbierz_jednostki_pol(
            drzewo_pl, f"{KOD_ZRODLOWY}/{folder}/{nazwa}")
        odn = orakuly_per_folder[folder].get(nazwa, {})
        for kod in kody:
            # Kotwice liczone per język: walidowana paczka nie jest orakułem dla
            # samej siebie (inaczej każdy jej literał byłby „kotwicą").
            kotwice = wykryj_kotwice(
                [j.zrodlo for j in jednostki],
                {k: v for k, v in odn.items() if k != kod}, extra)
            bledy, uwagi = waliduj_silnikiem(kod, folder, nazwa, cfg_pl, kotwice)
            wszystkie_bledy += len(bledy)
            wszystkie_uwagi += len(uwagi)
            if bledy:
                print(f"❌ {kod}/{folder}/{nazwa}: {len(bledy)} błąd/y")
                for b in bledy[:12]:
                    print(f"     • {b}")
            elif uwagi:
                print(f"⚠️  {kod}/{folder}/{nazwa}: OK, {len(uwagi)} uwaga/i")
            else:
                print(f"✅ {kod}/{folder}/{nazwa}: OK")
            for u in uwagi[:6]:
                print(f"     ~ {u}")
    print("\n========== PODSUMOWANIE (--tylko-walidacja) ==========")
    print(("✅ Bez zastrzeżeń." if not wszystkie_bledy
           else f"❌ Łącznie {wszystkie_bledy} błąd/ów.")
          + (f"  (uwag do przejrzenia: {wszystkie_uwagi})" if wszystkie_uwagi else ""))
    return 1 if wszystkie_bledy else 0


def main() -> int:
    global DICT_DIR
    args = _parsuj_argumenty()

    if args.slowniki:
        DICT_DIR = Path(os.path.expandvars(args.slowniki)).expanduser().resolve()
        if not DICT_DIR.is_dir():
            print(f"❌ --slowniki: {DICT_DIR} nie jest katalogiem.")
            return 2
        print(f"📁 Katalog słowników: {DICT_DIR} (poza repo — tryb user-data).")

    kody = _wybierz_jezyki(args)
    pliki = _filtruj_pliki(args.reguly)
    print(f"ℹ️  Reguły do przetworzenia ({len(pliki)}): "
          + ", ".join(f"{f}/{n}" for f, n in pliki))

    if args.finalizuj:
        return _tryb_finalizuj(kody, pliki)
    if args.tylko_walidacja:
        return _tryb_walidacji(kody, pliki, args)

    klient: Any = (None if args.dry_run
                   else tlumacz_rdzen.zainicjuj_klienta_anthropic(ROOT))
    kotwice_extra = tuple(k.strip() for k in args.kotwica.split(",") if k.strip())
    if kotwice_extra:
        print(f"🔒 Kotwice wymuszone z CLI: {list(kotwice_extra)}")

    orakuly_per_folder: dict[str, dict[str, dict[str, str]]] = {}
    for folder in {f for f, _ in pliki}:
        orakuly_per_folder[folder] = wczytaj_orakuly(
            folder, [n for f, n in pliki if f == folder],
            dopusc_drafty=args.orakul_drafty)

    sukcesy: list[str] = []
    porazki: list[str] = []
    wytworzone: dict[tuple[str, str], list[Jednostka]] = {}
    kotwice_per_plik: dict[tuple[str, str], list[str]] = {}

    for kod in kody:
        print(f"\n========== {kod.upper()} "
              f"({MAPA_JEZYKOW[kod]} / {_natywna_nazwa(kod)}) ==========")
        # Mini-wywołanie danych języka odpalamy LENIWIE: tylko dla paczki, której
        # brakuje choćby jednego pliku z zakresu (czyli realnie dla nowej).
        dane_llm: dict[str, Any] | None = None
        braki_paczki = [n for f, n in pliki if not (DICT_DIR / kod / f / n).is_file()]
        if braki_paczki and not args.dry_run:
            alfabet = str(_podstawy_paczki(kod).get("alfabet") or "")
            if not alfabet:
                print(f"❌ {kod}: brak `alfabet` w podstawy.yaml — nie mam z czego "
                      f"wyprowadzić danych języka dla nowej paczki.")
                porazki.append(kod)
                continue
            print(f"🧪 {kod}: brak {len(braki_paczki)} reguł ({', '.join(braki_paczki)}) "
                  f"— pytam model o dane języka (jedno wywołanie).")
            dane_llm, uwagi = wygeneruj_dane_jezyka(klient, kod, args.model, alfabet)
            for uwaga in uwagi:
                print(f"⚠️  {kod}: {uwaga}")

        wszystko_ok = True
        for folder, nazwa in pliki:
            ok, jednostki = tlumacz_plik(
                kod, folder, nazwa, klient,
                model=args.model,
                skip_existing=args.skip_existing,
                dry_run=args.dry_run,
                kotwice_extra=kotwice_extra,
                orakuly=orakuly_per_folder[folder].get(nazwa, {}),
                dane_llm=dane_llm,
                pozwol_zmiane_etykiety=args.pozwol_zmiane_etykiety,
            )
            if not ok:
                wszystko_ok = False
            elif jednostki:
                wytworzone[(kod, nazwa)] = jednostki
                kotwice_per_plik[(kod, nazwa)] = wykryj_kotwice(
                    [j.zrodlo for j in jednostki], None, kotwice_extra)
        (sukcesy if wszystko_ok else porazki).append(kod)

    if wytworzone:
        print("\n🔎 DRAFT: skan audyt_leakow na wytworzonych draftach…")
        leaki = tlumacz_rdzen.zbierz_leaki(wytworzone, kotwice_per_plik)
        sciezka = przeglad_tlumaczen.zapisz_prompt_przegladu(
            "buduj_wielojezyczne_poliglota.py", sorted(wytworzone.keys()), ROOT,
            leaki_per_plik=leaki,
        )
        if sciezka is not None:
            ile = sum(len(v) for per in leaki.values() for v in per.values())
            print(f"📋 DRAFT: checklista przeglądu → {sciezka.relative_to(ROOT)} "
                  f"({len(wytworzone)} plik(ów) do recenzji, {ile} kandydat(ów) "
                  f"na leak).")

    print("\n========== PODSUMOWANIE ==========")
    print(f"✅ Sukces: {len(sukcesy)}/{len(kody)}  ({', '.join(sukcesy) or '—'})")
    if porazki:
        print(f"❌ Porażki (≥1 reguła nieudana): {', '.join(porazki)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
