"""
i18n.py – Cienka warstwa tłumaczeń UI dla Rezysera Audio GPT.

Wersja 13.1 (pierwszy krok wielojęzyczności). Ten moduł:

  * Ładuje plik ``dictionaries/<kod>/gui/ui.yaml`` do cache w pamięci.
  * Udostępnia funkcję :func:`t(klucz, **kwargs)` która zwraca
    przetłumaczony string, z opcjonalnym ``str.format(**kwargs)``.
  * Obsługuje zagnieżdżone klucze przez kropkę (``"app.title"``).
  * Gdy klucz nie istnieje, zwraca ``[klucz]`` (łatwe do zlokalizowania
    w UI - nic nie pęka, ale wiadomo, co dopisać do YAML-a).
  * Fallback: jeśli zażądany język nie istnieje lub brakuje w nim klucza,
    bierzemy wartość z języka polskiego (język bazowy całego projektu).

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


# ---------------------------------------------------------------------------
# Stałe / ścieżki
# ---------------------------------------------------------------------------
JEZYK_DOMYSLNY = "pl"

_ROOT_DIR = Path(__file__).resolve().parent
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
    :func:`t` zacznie korzystać z fallbacku na polski.
    """
    if jezyk in _CACHE:
        return _CACHE[jezyk]
    dane = _wczytaj_yaml(jezyk)
    _CACHE[jezyk] = dane
    return dane


def ustaw_jezyk(jezyk: str) -> None:
    """Ustawia aktywny język UI i wymusza wczytanie jego pliku YAML.

    Domyślny fallback na polski dzieje się automatycznie w :func:`t` –
    tu tylko zapamiętujemy wybór i preloadujemy cache, żeby pierwsze
    wywołanie ``t()`` nie płaciło narzutu I/O w wątku GUI.
    """
    global _AKTUALNY_JEZYK
    _AKTUALNY_JEZYK = jezyk or JEZYK_DOMYSLNY
    zaladuj(_AKTUALNY_JEZYK)
    # Preloaduj polski jako fallback – gwarantuje to, że nawet brak pliku
    # dla aktywnego języka nie zatrzyma aplikacji.
    if _AKTUALNY_JEZYK != JEZYK_DOMYSLNY:
        zaladuj(JEZYK_DOMYSLNY)


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
def t(klucz: str, **kwargs: Any) -> str:
    """Zwraca przetłumaczony napis dla podanego klucza.

    Kolejność wyszukiwania:
      1. Słownik aktualnego języka (:data:`_AKTUALNY_JEZYK`).
      2. Słownik polski (fallback) – jeśli aktywny ≠ ``pl``.
      3. Literalny placeholder ``[klucz]`` (widać go w GUI, łatwo znaleźć).

    Jeśli podano ``**kwargs``, wartość (string) przechodzi przez
    ``str.format(**kwargs)``. Brakujący placeholder NIE rzuca wyjątku –
    zwracamy surowy tekst, żeby nie wywalić GUI w locie.

    Args:
        klucz:   Klucz typu ``"main.app_title"`` lub ``"rezyser.btn_wstaw_akt"``.
        **kwargs: Parametry dynamiczne do ``str.format``.

    Returns:
        Przetłumaczony tekst (z podstawionymi parametrami) lub
        ``[klucz]``, gdy klucz nie istnieje w żadnym języku.
    """
    # 1. Aktualny język
    dane = _CACHE.get(_AKTUALNY_JEZYK)
    if dane is None:
        dane = zaladuj(_AKTUALNY_JEZYK)
    wartosc = _pobierz(dane, klucz)

    # 2. Fallback na polski
    if wartosc is None and _AKTUALNY_JEZYK != JEZYK_DOMYSLNY:
        dane_pl = _CACHE.get(JEZYK_DOMYSLNY) or zaladuj(JEZYK_DOMYSLNY)
        wartosc = _pobierz(dane_pl, klucz)

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
