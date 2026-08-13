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

import hashlib
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
    url_sha256: str = ""     # (v18.10) link do assetu `<instalator>.sha256`
                             # (drugi asset Release, generowany przez
                             # build_release). Pusty dla starych wydań —
                             # weryfikacja SHA256 jest wtedy pomijana.


class BladWeryfikacjiPobrania(RuntimeError):
    """Pobrany instalator nie przeszedł weryfikacji integralności.

    Rzucany przez :func:`pobierz_instalator` gdy rozmiar pliku nie zgadza się
    z rozmiarem assetu z API GitHuba ALBO SHA256 nie zgadza się z sumą z assetu
    `.sha256`. Plik tymczasowy jest wtedy usuwany — GUI mapuje wyjątek na
    komunikat i18n (`updater.blad_weryfikacji_tresc`), nigdy nie uruchamiamy
    instalatora, którego integralności nie potwierdziliśmy.
    """


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


def _znajdz_asset_sha256(assets: list[dict], nazwa_instalatora: str) -> Optional[dict]:
    """Zwraca asset `.sha256` sparowany z instalatorem (None = brak; v18.10).

    Preferowana konwencja: `<nazwa instalatora>.sha256` (tak generuje
    build_release). Fallback: jedyny asset `*.sha256` w Release — na wypadek
    ręcznej zmiany nazwy przy uploadzie.
    """
    oczekiwana = f"{nazwa_instalatora}.sha256".lower()
    kandydaci = sorted(
        (a for a in assets if a.get("name", "").lower().endswith(".sha256")),
        key=lambda a: a.get("name", ""),
    )
    for asset in kandydaci:
        if asset.get("name", "").lower() == oczekiwana:
            return asset
    # Audyt v18.10: przy 2+ niedokładnych kandydatach NIE pomijamy cicho
    # weryfikacji (fail-open) — bierzemy deterministycznie pierwszego;
    # zły plik i tak wywali mismatch SHA256 (fail-closed przez porównanie).
    return kandydaci[0] if kandydaci else None


_REGEX_HEX_SHA256 = re.compile(r"\b[0-9a-fA-F]{64}\b")


def _pobierz_oczekiwany_sha256(url: str) -> str:
    """Pobiera asset `.sha256` i wyciąga 64-znakowy hash (format sha256sum).

    Raises:
        BladWeryfikacjiPobrania: asset istnieje, ale nie dało się go pobrać
            lub sparsować — celowo FAIL-CLOSED (skoro wydawca zadeklarował
            sumę, brak możliwości jej sprawdzenia = nie uruchamiamy exe).
    """
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": f"RezyserAudio/{_odczytaj_wersje_lokalna()}"},
        )
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            tresc = resp.read(4096).decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001 — mapujemy na typowany wyjątek
        raise BladWeryfikacjiPobrania(
            f"failed to download the checksum asset: {exc}") from exc
    dopasowanie = _REGEX_HEX_SHA256.search(tresc)
    if not dopasowanie:
        raise BladWeryfikacjiPobrania(
            "checksum asset does not contain a valid SHA256 hash")
    return dopasowanie.group(0).lower()


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

        asset_sha = _znajdz_asset_sha256(dane.get("assets", []), asset["name"])

        return UpdateInfo(
            tag=tag,
            wersja=wersja_zdalna,
            url_instalatora=asset["browser_download_url"],
            nazwa_pliku=asset["name"],
            rozmiar_bajtow=asset.get("size", 0),
            url_release=dane.get("html_url", ""),
            url_zrodla=dane.get("zipball_url", ""),
            changelog=_oczysc_changelog(dane.get("body", "")),
            url_sha256=(asset_sha or {}).get("browser_download_url", ""),
        )

    # Świadomie szeroki łapacz — docstring obiecuje „nigdy nie rzuca", a wąska
    # krotka tej obietnicy nie dotrzymywała: `http.client.HTTPException`
    # (BadStatusLine / IncompleteRead przy zerwanym połączeniu) NIE dziedziczy
    # po OSError, więc leciała z wątku tła. Sprawdzenie aktualizacji jest
    # całkowicie opcjonalne — każdy jego błąd ma być cichym „brak aktualizacji",
    # nigdy dialogiem crashu przy starcie aplikacji.
    except Exception:  # noqa: BLE001 — patrz komentarz wyżej (kontrakt: zawsze None)
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
        BladWeryfikacjiPobrania: (v18.10) rozmiar pliku ≠ rozmiar assetu z API
            ALBO SHA256 ≠ suma z assetu `.sha256`. Plik tymczasowy usuwany.
            Weryfikacja SHA256 pomijana, gdy Release nie ma assetu `.sha256`
            (stare wydania); weryfikacja rozmiaru pomijana przy `size == 0`.
    """
    sciezka_docelowa = Path(tempfile.gettempdir()) / info.nazwa_pliku

    req = urllib.request.Request(
        info.url_instalatora,
        headers={"User-Agent": f"RezyserAudio/{_odczytaj_wersje_lokalna()}"},
    )

    skrot = hashlib.sha256()
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
            skrot.update(chunk)
            pobrane += len(chunk)
            if callback:
                callback(pobrane, total)

    # --- Weryfikacja integralności (v18.10) ---
    try:
        if info.rozmiar_bajtow and pobrane != info.rozmiar_bajtow:
            raise BladWeryfikacjiPobrania(
                f"size mismatch: downloaded {pobrane} B, "
                f"release asset declares {info.rozmiar_bajtow} B")
        if info.url_sha256:
            oczekiwany = _pobierz_oczekiwany_sha256(info.url_sha256)
            if skrot.hexdigest().lower() != oczekiwany:
                raise BladWeryfikacjiPobrania(
                    f"SHA256 mismatch: got {skrot.hexdigest()}, "
                    f"expected {oczekiwany}")
    except BladWeryfikacjiPobrania:
        # Nie zostawiamy w %TEMP% pliku, którego integralności nie
        # potwierdziliśmy — mógłby zostać uruchomiony ręcznie.
        try:
            sciezka_docelowa.unlink()
        except OSError:
            pass
        raise

    return sciezka_docelowa
