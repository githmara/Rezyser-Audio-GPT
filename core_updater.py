"""
core_updater.py – Logika sprawdzania i pobierania aktualizacji z GitHub Releases.

Publiczne API (używane przez wątek tła w main.py):

    from core_updater import sprawdz_aktualizacje, pobierz_instalator, UpdateInfo

    info = sprawdz_aktualizacje()          # None → brak aktualizacji / błąd sieci
    if info:
        print(info.tag, info.url_instalatora, info.rozmiar_bajtow)
        sciezka = pobierz_instalator(info, callback=lambda p, t: ...)

Moduł jest w pełni niezależny od wxPython — testuj go bez GUI.
"""

from __future__ import annotations

import os
import re
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional
from urllib.error import URLError, HTTPError

import sciezki


# ---------------------------------------------------------------------------
# Konfiguracja
# ---------------------------------------------------------------------------

GITHUB_USER = "githmara"
GITHUB_REPO = "Rezyser-Audio-GPT"

_API_URL = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/releases/latest"
# VERSION liczony przez `sciezki.KATALOG_ZASOBOW`, TAK SAMO jak `i18n._PLIK_WERSJI`.
# Historia: do v17.11 było tu `Path(__file__).with_name("VERSION")` — w paczce
# PyInstaller `__file__` wskazuje WEWNĄTRZ bundla, więc plik nie był znajdowany →
# `_odczytaj_wersje_lokalna` rzucał FileNotFoundError → `sprawdz_aktualizacje`
# zwracał None → DIALOG AKTUALIZACJI NIGDY SIĘ NIE POKAZYWAŁ w żadnym frozen
# buildzie (cichy regres od migracji na PyInstaller, v17.0). Quick-fix v17.11
# przepiął odczyt na `KATALOG_BAZOWY` (obok exe) + kopiowanie pliku w buildzie.
# Od v18.x VERSION (kod/seed, nie user-data) jest pakowany do bundla przez `datas`
# i czytany z `KATALOG_ZASOBOW` (= `sys._MEIPASS` gdy frozen) — patrz
# `sciezki._wyznacz_zasoby`; build już nie kopiuje go luzem obok exe.
_SCIEZKA_VERSION = sciezki.KATALOG_ZASOBOW / "VERSION"

# Wzorzec nazwy pliku instalatora w assets (GitHub Release)
_WZORZEC_INSTALATORA = re.compile(r"rezyser_audio.*installer.*\.exe", re.IGNORECASE)

# Timeout HTTP (sekundy) — nie blokuj UI dłużej niż konieczne
_TIMEOUT = 10


# ---------------------------------------------------------------------------
# Typy danych
# ---------------------------------------------------------------------------

@dataclass
class UpdateInfo:
    """Informacje o dostępnej aktualizacji."""
    tag: str                 # np. "v13.4.1"
    wersja: str              # np. "13.4.1" (bez "v")
    url_instalatora: str     # bezpośredni link do .exe
    nazwa_pliku: str         # np. "rezyser_audio_13.4.1_Installer.exe"
    rozmiar_bajtow: int      # 0 jeśli GitHub nie podał Content-Length
    url_release: str = ""    # (v17.6) strona Release na GitHubie (html_url) —
                             # „Szczegóły online" w DialogAktualizacji. Treść po PL.
    url_zrodla: str = ""     # (v17.11) `zipball_url` — kod źródłowy (ZIP) tej
                             # wersji. Cel przycisku „Pobierz" w trybie NIE-frozen
                             # (dev / non-Windows): brak instalatora .exe, więc
                             # oferujemy źródło bez dodatkowej instalacji.
    changelog: str = ""      # (v17.11) treść Release (`body` z API) = sekcja
                             # `RELEASE_NOTES ## <wersja>` NOWEJ wersji. Realny
                             # changelog do świadomej decyzji o aktualizacji —
                             # zapisywany do `docs/changelog.md` i otwierany z
                             # dialogu. Do v17.11 dialog pokazywał baked-in opis
                             # wersji JUŻ zainstalowanej (bug: nagłówek nowej,
                             # treść starej). EN-lead + PL (format RELEASE_NOTES).


# ---------------------------------------------------------------------------
# Pomocnicze funkcje wewnętrzne
# ---------------------------------------------------------------------------

def _odczytaj_wersje_lokalna() -> str:
    """Czyta bieżącą wersję aplikacji z pliku VERSION."""
    if not _SCIEZKA_VERSION.exists():
        raise FileNotFoundError(
            f"Nie znaleziono pliku VERSION w {_SCIEZKA_VERSION}. "
            "Sprawdź, czy plik istnieje w katalogu głównym projektu."
        )
    wartosc = _SCIEZKA_VERSION.read_text(encoding="utf-8").strip()
    if not wartosc:
        raise ValueError("Plik VERSION jest pusty.")
    return wartosc


def _normalizuj_wersje(tekst: str) -> tuple[int, ...]:
    """Konwertuje string wersji na krotkę intów do porównywania.

    Przykłady:
        "13.4"     → (13, 4, 0)
        "v13.4.1"  → (13, 4, 1)
        "13.5-WIP" → (13, 5, 0)  — sufiks -WIP jest ignorowany
    """
    bez_v = tekst.lstrip("v")
    # Odetnij sufiks tekstowy (np. "-WIP", "-beta")
    bez_sufiks = re.split(r"[^0-9.]", bez_v)[0]
    czesci = bez_sufiks.split(".")
    try:
        krotka = tuple(int(c) for c in czesci if c)
    except ValueError:
        raise ValueError(f"Nieprawidłowy format wersji: {tekst!r}")
    # Uzupełnij do co najmniej 3 elementów zerami
    return krotka + (0,) * max(0, 3 - len(krotka))


def _pobierz_json_api(url: str, token: Optional[str] = None) -> dict:
    """Wykonuje GET na podany URL i zwraca JSON jako dict.

    Args:
        token: Opcjonalny GitHub Personal Access Token (Bearer).
               Potrzebny tylko dla prywatnych repozytoriów.
    """
    import json

    naglowki = {
        "Accept": "application/vnd.github+json",
        "User-Agent": f"RezyserAudio/{_odczytaj_wersje_lokalna()} (+github.com/{GITHUB_USER}/{GITHUB_REPO})",
    }
    if token:
        naglowki["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, headers=naglowki)
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _znajdz_asset_instalatora(assets: list[dict]) -> Optional[dict]:
    """Zwraca pierwszy asset pasujący do wzorca instalatora .exe."""
    for asset in assets:
        if _WZORZEC_INSTALATORA.search(asset.get("name", "")):
            return asset
    return None


def _oczysc_changelog(body: str) -> str:
    """Przycina treść Release do czystego changelogu (bez końcowego `---`).

    `body` Release pochodzi z sekcji `RELEASE_NOTES.md`; draft-workflow do v17.11
    dołączał końcowy separator `---` (należy MIĘDZY sekcje). Tniemy go również tu,
    defensywnie, by już OPUBLIKOWANE Release (z dawnym `---`) też wyświetlały się
    czysto w `docs/changelog.md`. Strip dotyczy wyłącznie KOŃCA tekstu.
    """
    return re.sub(r"\n+-{3,}[ \t]*$", "", (body or "").strip()).strip()


# ---------------------------------------------------------------------------
# Publiczne API
# ---------------------------------------------------------------------------

def sprawdz_aktualizacje(token: Optional[str] = None) -> Optional[UpdateInfo]:
    """Odpytuje GitHub API i sprawdza czy dostępna jest nowsza wersja.

    Args:
        token: Opcjonalny GitHub PAT — wymagany tylko dla prywatnych repozytoriów.

    Returns:
        UpdateInfo jeśli nowa wersja dostępna, None w przeciwnym razie
        (aktualna wersja, brak assetów instalatora, błąd sieci).

    Raises:
        Nic — wszystkie wyjątki są łapane i zwracane jako None,
        żeby wątek tła nie wysypał aplikacji.
    """
    try:
        wersja_lokalna = _odczytaj_wersje_lokalna()
        dane = _pobierz_json_api(_API_URL, token=token)

        tag = dane.get("tag_name", "")
        if not tag:
            return None

        wersja_zdalna = tag.lstrip("v")

        if _normalizuj_wersje(wersja_zdalna) <= _normalizuj_wersje(wersja_lokalna):
            return None

        asset = _znajdz_asset_instalatora(dane.get("assets", []))
        if asset is None:
            return None

        return UpdateInfo(
            tag=tag,
            wersja=wersja_zdalna,
            url_instalatora=asset["browser_download_url"],
            nazwa_pliku=asset["name"],
            rozmiar_bajtow=asset.get("size", 0),
            url_release=dane.get("html_url", ""),
            url_zrodla=dane.get("zipball_url", ""),
            changelog=_oczysc_changelog(dane.get("body", "")),
        )

    except (HTTPError, URLError, OSError, KeyError, ValueError):
        return None


def pobierz_instalator(
    info: UpdateInfo,
    callback: Optional[Callable[[int, int], None]] = None,
) -> Path:
    """Pobiera instalator do folderu tymczasowego.

    Args:
        info:     Dane aktualizacji zwrócone przez sprawdz_aktualizacje().
        callback: Wywoływany co każdy pobrany chunk z argumentami
                  (pobrane_bajty, total_bajty). Użyj wx.CallAfter w GUI.

    Returns:
        Ścieżka do pobranego pliku .exe w %TEMP%.

    Raises:
        OSError / HTTPError: przy błędzie pobierania.
    """
    sciezka_docelowa = Path(tempfile.gettempdir()) / info.nazwa_pliku

    req = urllib.request.Request(
        info.url_instalatora,
        headers={"User-Agent": f"RezyserAudio/{_odczytaj_wersje_lokalna()}"},
    )

    with urllib.request.urlopen(req, timeout=60) as resp, \
            open(sciezka_docelowa, "wb") as fh:

        total = int(resp.headers.get("Content-Length") or info.rozmiar_bajtow or 0)
        pobrane = 0
        rozmiar_chunka = 65536  # 64 KB

        while True:
            chunk = resp.read(rozmiar_chunka)
            if not chunk:
                break
            fh.write(chunk)
            pobrane += len(chunk)
            if callback:
                callback(pobrane, total)

    return sciezka_docelowa
