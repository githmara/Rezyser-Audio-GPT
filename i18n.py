"""
i18n.py – Cienka warstwa tłumaczeń UI dla Rezysera Audio GPT.

Wersja 13.1 (pierwszy krok wielojęzyczności). Ten moduł:

  * Ładuje plik ``dictionaries/<kod>/gui/ui.yaml`` do cache w pamięci.
  * Udostępnia funkcję :func:`t(klucz, **kwargs)` która zwraca
    przetłumaczony string, z opcjonalnym ``str.format(**kwargs)``.
  * Obsługuje zagnieżdżone klucze przez kropkę (``"app.title"``).
  * Gdy klucz nie istnieje, zwraca ``[klucz]`` (łatwe do zlokalizowania
    w UI - nic nie pęka, ale wiadomo, co dopisać do YAML-a).
  * Fallback (zasada międzynarodowości): jeśli zażądany język nie istnieje
    lub brakuje w nim klucza, bierzemy wartość z **angielskiego**
    (:data:`JEZYK_FALLBACK`), a nie polskiego — user niemówiący po polsku
    powinien zobaczyć angielski (lub czytelny ``[klucz]``), nigdy polski
    „przeciek". PL pozostaje jedynie domyślnym AKTYWNYM językiem
    (:data:`JEZYK_DOMYSLNY`) dla startu aplikacji, nie targetem fallbacku.
    EN jest bazą referencyjną 1:1 z PL (crosscheck ``_jezyk_kompletny``),
    więc fallback nigdy nie trafia na stub.

Użycie w kodzie wxPython:

    from i18n import t

    heading = wx.StaticText(self, label=t("konwerter.heading"))
    self._btn_wczytaj.SetToolTip(t("poliglota.btn_load_tooltip"))
    msg = t("main.raport_sukces_akcentow", liczba_akcentow=n)

Plik YAML żyje obok reszty warstwy językowej
(``dictionaries/<kod>/podstawy.yaml``, ``akcenty/``, ``szyfry/``,
``rezyser/``, ``gui/``), dzięki czemu dodanie nowego języka to JEDEN
folder ``dictionaries/<kod>/``.

Wczytanie przy starcie aplikacji:

    import i18n
    i18n.ustaw_jezyk("pl")   # pl jest domyślny; wywołaj jawnie dla bezpieczeństwa
"""
from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

import sciezki
from przepisy_rezysera import opis_bledu_yaml


# ---------------------------------------------------------------------------
# Stałe / ścieżki
# ---------------------------------------------------------------------------
JEZYK_DOMYSLNY = "pl"   # domyślny AKTYWNY język przy starcie (nie target fallbacku)
JEZYK_FALLBACK = "en"   # target fallbacku gdy w aktywnym języku brak klucza
                        # (zasada międzynarodowości — patrz docstring modułu)

_ROOT_DIR = sciezki.KATALOG_BAZOWY
_DICTIONARIES_DIR = _ROOT_DIR / "dictionaries"
_NAZWA_PLIKU_UI = "ui.yaml"
_FOLDER_GUI = "gui"

# Single source of truth dla numeru wersji. Plain text, jeden bump = wszystkie
# języki. Wartość ładowana raz przy imporcie (read_text jest tani), auto-
# wstrzykiwana do każdego format() w `t()` jako kwarg `numer_wersji`.
# VERSION to KOD/seed, nie user-data — siedzi w bundlu (`KATALOG_ZASOBOW` =
# `sys._MEIPASS` gdy frozen), a nie luzem obok exe (`KATALOG_BAZOWY`). Do v18.x
# był kopiowany obok exe i czytany z `KATALOG_BAZOWY` — patrz `sciezki._wyznacz_zasoby`.
_PLIK_WERSJI = sciezki.KATALOG_ZASOBOW / "VERSION"
try:
    NUMER_WERSJI = _PLIK_WERSJI.read_text(encoding="utf-8").strip()
except OSError:
    NUMER_WERSJI = "?"


# ---------------------------------------------------------------------------
# Stan modułu
# ---------------------------------------------------------------------------
# Cache wczytanych słowników: {kod_jezyka: {klucz: wartosc | dict}}.
# Jeden wpis na język, ładowany leniwie przy pierwszym użyciu.
_CACHE: dict[str, dict[str, Any]] = {}

# Aktualnie wybrany język (domyślnie polski – język bazowy projektu).
_AKTUALNY_JEZYK: str = JEZYK_DOMYSLNY


# ---------------------------------------------------------------------------
# Rejestr awarii pliku tłumaczeń (v18.25)
# ---------------------------------------------------------------------------
# `dictionaries/<kod>/gui/ui.yaml` jest EDYTOWALNY przez użytkownika (Manager
# Reguł otwiera go w systemowym edytorze), więc jego błąd składni to normalna,
# spodziewana awaria — a do v18.24.2 była CAŁKOWICIE cicha: `_wczytaj_yaml`
# zwracał `{}`, `t()` spadał na angielski, a przy zepsutym `en` cały interfejs
# degradował do gołych `[sekcja.klucz]`. Bez ANI JEDNEJ informacji, dlaczego.
#
# Ten rejestr jest ODDZIELNY od `przepisy_rezysera._POMINIETE` (reguły silnika,
# raportowane zdaniami z kluczy `diag.*`) i to nie duplikacja: powód pominięcia
# REGUŁY można opowiedzieć przez `i18n`, a awarię samego `i18n` — nie. Zdania
# o niej są twardym tekstem PL+EN w `gui_diagnostyka`, wzorem
# `main._pokaz_dialog_crash`. Format opisu błędu składni bierzemy z
# `przepisy_rezysera.opis_bledu_yaml`, żeby „4:1: found unexpected end of
# stream" wyglądało identycznie w obu kanałach (import jednokierunkowy — tamten
# moduł pozostaje i18n-free i wx-free).
POWOD_PARSE  = "parse"    # błąd składni YAML (najczęstsza pomyłka w edytorze)
POWOD_PUSTY  = "pusty"    # plik jest, ale nie zawiera mapy klucz → wartość
POWOD_ODCZYT = "odczyt"   # OSError: brak uprawnień, plik zajęty, zły dysk


@dataclass(frozen=True)
class AwariaUI:
    """Jedna paczka językowa, której pliku tłumaczeń nie da się użyć.

    Args:
        jezyk:    Kod ISO paczki (``"pl"``) — po nim widać, czy chodzi o język
                  interfejsu, czy o angielski fallback.
        sciezka:  Pełna ścieżka pliku — użytkownik ma go otworzyć i poprawić.
        powod:    Kod ``POWOD_*``.
        szczegol: Dane techniczne bez słów (pozycja błędu, komunikat parsera).
                  Celowo NIE tłumaczone — to cytat z biblioteki.
    """

    jezyk: str
    sciezka: str
    powod: str
    szczegol: str = ""


# Lock, bo `t()` wołają też wątki tła (worker Reżysera/Opowieści komponuje
# komunikaty), a `zaladuj` może wtedy wypełniać rejestr równolegle z GUI.
_AWARIE: dict[str, AwariaUI] = {}
_LOCK_AWARII = threading.Lock()


def _zglos_awarie(jezyk: str, sciezka: Path, powod: str, szczegol: str) -> None:
    """Zapisuje awarię pliku tłumaczeń (jedna, najświeższa, na język)."""
    with _LOCK_AWARII:
        _AWARIE[jezyk] = AwariaUI(
            jezyk=jezyk, sciezka=str(sciezka), powod=powod, szczegol=szczegol,
        )


def _odwolaj_awarie(jezyk: str) -> None:
    """Zapomina awarię tej paczki — plik wczytał się poprawnie (user poprawił)."""
    with _LOCK_AWARII:
        _AWARIE.pop(jezyk, None)


def awarie_ui() -> tuple[AwariaUI, ...]:
    """Zwraca zebrane awarie plików tłumaczeń (pusta krotka = czysto).

    Rejestr wypełnia się LENIWIE, przy wczytywaniu paczek: po
    :func:`ustaw_jezyk` zawiera więc dokładnie to, co aplikacja próbowała
    wczytać na starcie (język interfejsu + angielski fallback).
    """
    with _LOCK_AWARII:
        return tuple(_AWARIE[kod] for kod in sorted(_AWARIE))


def sprawdz_pliki_ui(
    jezyki: tuple[str, ...] | list[str] | None = None,
) -> tuple[AwariaUI, ...]:
    """Czyta wskazane pliki tłumaczeń z dysku od nowa i zwraca wszystkie awarie.

    Świadomie NIE dotyka ``_CACHE``: gdyby kontrola podmieniała wczytane
    tłumaczenia, zepsucie pliku degradowałoby DZIAŁAJĄCE okno w locie (etykiety
    już zbudowanych paneli zostają, ale każdy kolejny ``t()`` spadałby na
    angielski). Naprawa pliku tłumaczeń wymaga restartu aplikacji i komunikat
    tak właśnie mówi — a ta funkcja tylko STAWIA diagnozę.

    Args:
        jezyki: Kody do sprawdzenia; ``None`` = aktywny język + angielski
                fallback, czyli dokładnie te paczki, z których aplikacja bierze
                napisy.

    Returns:
        Snapshot rejestru po kontroli (obejmuje też awarie zebrane wcześniej,
        np. przy ``jezyk_override`` na paczkę innego języka).
    """
    if jezyki is None:
        jezyki = [_AKTUALNY_JEZYK]
        if _AKTUALNY_JEZYK != JEZYK_FALLBACK:
            jezyki.append(JEZYK_FALLBACK)
    for kod in jezyki:
        _wczytaj_yaml(kod)
    return awarie_ui()


# ---------------------------------------------------------------------------
# Ładowanie plików YAML
# ---------------------------------------------------------------------------
def _sciezka_ui(jezyk: str) -> Path:
    """Zwraca bezwzględną ścieżkę do ``dictionaries/<jezyk>/gui/ui.yaml``."""
    return _DICTIONARIES_DIR / jezyk / _FOLDER_GUI / _NAZWA_PLIKU_UI


def _wczytaj_yaml(jezyk: str) -> dict[str, Any]:
    """Wczytuje surowy plik YAML. Nie rzuca wyjątków – zwraca ``{}`` przy awarii.

    v18.25: awaria pliku, który ISTNIEJE, ale nie daje się użyć, ląduje
    w rejestrze :data:`_AWARIE` (patrz sekcja wyżej). BRAKU pliku celowo nie
    zgłaszamy: dla nieobsługiwanego kodu języka (``jezyk_override`` z przepisu,
    stub w ``dictionaries/``) to normalny stan, a brak pliku aktywnej paczki
    odfiltrowuje już ``core_poliglota._jezyk_kompletny`` przed wyborem języka.
    """
    sciezka = _sciezka_ui(jezyk)
    if not sciezka.is_file():
        return {}
    try:
        with open(sciezka, "r", encoding="utf-8") as fh:
            dane = yaml.safe_load(fh)
    except OSError as exc:
        _zglos_awarie(jezyk, sciezka, POWOD_ODCZYT, str(exc))
        return {}
    except yaml.YAMLError as exc:
        _zglos_awarie(jezyk, sciezka, POWOD_PARSE, opis_bledu_yaml(exc))
        return {}
    if not isinstance(dane, dict) or not dane:
        _zglos_awarie(jezyk, sciezka, POWOD_PUSTY, type(dane).__name__)
        return {}
    _odwolaj_awarie(jezyk)
    return dane


def zaladuj(jezyk: str) -> dict[str, Any]:
    """Ładuje ``dictionaries/<jezyk>/gui/ui.yaml`` (z cache) i zwraca słownik.

    Jeśli plik nie istnieje lub jest pusty, zwraca ``{}`` – wtedy
    :func:`t` zacznie korzystać z fallbacku na angielski (:data:`JEZYK_FALLBACK`),
    a powód (gdy plik jest, lecz jest zepsuty) czeka w :func:`awarie_ui`.
    """
    if jezyk in _CACHE:
        return _CACHE[jezyk]
    dane = _wczytaj_yaml(jezyk)
    _CACHE[jezyk] = dane
    return dane


def ustaw_jezyk(jezyk: str) -> None:
    """Ustawia aktywny język UI i wymusza wczytanie jego pliku YAML.

    Fallback na angielski (:data:`JEZYK_FALLBACK`) dzieje się automatycznie
    w :func:`t` – tu tylko zapamiętujemy wybór i preloadujemy cache, żeby
    pierwsze wywołanie ``t()`` nie płaciło narzutu I/O w wątku GUI.
    """
    global _AKTUALNY_JEZYK
    _AKTUALNY_JEZYK = jezyk or JEZYK_DOMYSLNY
    zaladuj(_AKTUALNY_JEZYK)
    # Preloaduj angielski jako fallback – gwarantuje to, że nawet brak pliku
    # (lub klucza) dla aktywnego języka nie zatrzyma aplikacji i nie przecieknie
    # polskim tekstem do nie-polskiego usera.
    if _AKTUALNY_JEZYK != JEZYK_FALLBACK:
        zaladuj(JEZYK_FALLBACK)


def aktualny_jezyk() -> str:
    """Zwraca kod aktualnie wybranego języka UI."""
    return _AKTUALNY_JEZYK


# ---------------------------------------------------------------------------
# Pobieranie wartości z zagnieżdżonego słownika
# ---------------------------------------------------------------------------
def _pobierz(dane: dict[str, Any], klucz: str) -> Any:
    """Zwraca wartość pod kluczem (obsługuje kropki jako ścieżkę).

    Zwraca ``None``, gdy gdziekolwiek po drodze ścieżka się urwie –
    dzięki temu :func:`t` wie, że trzeba spróbować fallbacku.
    """
    aktualne: Any = dane
    for segment in klucz.split("."):
        if isinstance(aktualne, dict) and segment in aktualne:
            aktualne = aktualne[segment]
        else:
            return None
    return aktualne


# ---------------------------------------------------------------------------
# Główne API: t(klucz, **kwargs)
# ---------------------------------------------------------------------------
def t(klucz: str, *, jezyk_override: str | None = None, **kwargs: Any) -> str:
    """Zwraca przetłumaczony napis dla podanego klucza.

    Kolejność wyszukiwania (zasada międzynarodowości):
      1. Słownik języka bazowego: ``jezyk_override`` jeśli podany, inaczej
         aktualny (:data:`_AKTUALNY_JEZYK`).
      2. Słownik **angielski** (:data:`JEZYK_FALLBACK`) – jeśli baza ≠ ``en``.
         (Świadomie NIE polski — nie-polski user nie powinien zobaczyć
         polskiego przecieku; patrz docstring modułu.)
      3. Literalny placeholder ``[klucz]`` (widać go w GUI, łatwo znaleźć).

    Jeśli podano ``**kwargs``, wartość (string) przechodzi przez
    ``str.format(**kwargs)``. Brakujący placeholder NIE rzuca wyjątku –
    zwracamy surowy tekst, żeby nie wywalić GUI w locie.

    Args:
        klucz:          Klucz typu ``"main.app_title"`` lub ``"rezyser.btn_wstaw_akt"``.
        jezyk_override: Opcjonalny kod języka wymuszający tłumaczenie w nim
                        zamiast w aktywnym (np. nagłówki struktury Reżysera
                        w języku treści przepisu, nie GUI). Keyword-only,
                        żeby nie kolidować z format-kwargiem ``jezyk``
                        (``t("...", jezyk=...)`` używany w GUI).
        **kwargs:       Parametry dynamiczne do ``str.format``.

    Returns:
        Przetłumaczony tekst (z podstawionymi parametrami) lub
        ``[klucz]``, gdy klucz nie istnieje ani w bazie, ani w EN.
    """
    # 1. Język bazowy (override albo aktywny)
    jezyk_bazowy = jezyk_override or _AKTUALNY_JEZYK
    dane = _CACHE.get(jezyk_bazowy)
    if dane is None:
        dane = zaladuj(jezyk_bazowy)
    wartosc = _pobierz(dane, klucz)

    # 2. Fallback na angielski (NIE polski — międzynarodowość)
    if wartosc is None and jezyk_bazowy != JEZYK_FALLBACK:
        dane_fb = _CACHE.get(JEZYK_FALLBACK) or zaladuj(JEZYK_FALLBACK)
        wartosc = _pobierz(dane_fb, klucz)

    # 3. Brak klucza – zwróć placeholder widoczny w GUI
    if wartosc is None:
        return f"[{klucz}]"

    # Listy i dicty oddajemy jak są (przydatne np. dla tooltipów
    # wieloliniowych, gdybyśmy trzymali listy linii).
    if not isinstance(wartosc, str):
        return wartosc

    # Auto-wstrzyknięcie numer_wersji: każda wartość w ui.yaml może użyć
    # placeholdera {numer_wersji} bez konieczności wywoływania t() z kwargiem.
    # Wartość przekazana jawnie (np. w testach) ma pierwszeństwo.
    kwargs.setdefault("numer_wersji", NUMER_WERSJI)
    try:
        return wartosc.format(**kwargs)
    except (KeyError, IndexError, ValueError):
        return wartosc


# ---------------------------------------------------------------------------
# Debug / testy – pomocnicze
# ---------------------------------------------------------------------------
def dostepne_jezyki_ui() -> list[str]:
    """Zwraca posortowaną listę kodów z ``dictionaries/<kod>/gui/ui.yaml`` na dysku."""
    if not _DICTIONARIES_DIR.is_dir():
        return []
    wyniki = []
    for wpis in sorted(os.listdir(_DICTIONARIES_DIR)):
        sciezka = _sciezka_ui(wpis)
        if sciezka.is_file():
            wyniki.append(wpis)
    return wyniki


def wyczysc_cache() -> None:
    """Czyści cache i rejestr awarii – przy przeładowaniu tłumaczeń i w testach.

    Rejestr idzie razem z cache, bo oba opisują ten sam stan („co wiemy
    o plikach na dysku"): po wyczyszczeniu kolejny ``t()`` czyta plik od nowa,
    więc stara awaria byłaby nieaktualną diagnozą.
    """
    _CACHE.clear()
    with _LOCK_AWARII:
        _AWARIE.clear()
