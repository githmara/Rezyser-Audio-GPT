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
from pathlib import Path
from typing import Any

import yaml

import sciezki


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

# Single source of truth dla numeru wersji. Plain text w roocie, jeden bump
# = wszystkie języki. Wartość ładowana raz przy imporcie (read_text jest tani),
# auto-wstrzykiwana do każdego format() w `t()` jako kwarg `numer_wersji`.
_PLIK_WERSJI = _ROOT_DIR / "VERSION"
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
# Ładowanie plików YAML
# ---------------------------------------------------------------------------
def _sciezka_ui(jezyk: str) -> Path:
    """Zwraca bezwzględną ścieżkę do ``dictionaries/<jezyk>/gui/ui.yaml``."""
    return _DICTIONARIES_DIR / jezyk / _FOLDER_GUI / _NAZWA_PLIKU_UI


def _wczytaj_yaml(jezyk: str) -> dict[str, Any]:
    """Wczytuje surowy plik YAML. Nie rzuca wyjątków – zwraca ``{}`` przy awarii."""
    sciezka = _sciezka_ui(jezyk)
    if not sciezka.is_file():
        return {}
    try:
        with open(sciezka, "r", encoding="utf-8") as fh:
            dane = yaml.safe_load(fh)
    except (OSError, yaml.YAMLError):
        return {}
    return dane if isinstance(dane, dict) else {}


def zaladuj(jezyk: str) -> dict[str, Any]:
    """Ładuje ``dictionaries/<jezyk>/gui/ui.yaml`` (z cache) i zwraca słownik.

    Jeśli plik nie istnieje lub jest pusty, zwraca ``{}`` – wtedy
    :func:`t` zacznie korzystać z fallbacku na angielski (:data:`JEZYK_FALLBACK`).
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
    """Czyści cache – przydatne w testach i przy przeładowaniu tłumaczeń."""
    _CACHE.clear()
