"""
test_core_updater.py - Testy bez GUI dla modulu core_updater.

Uruchom:  .venv/Scripts/python test_core_updater.py
Opcjonalnie z tokenem: GITHUB_TOKEN=ghp_... .venv/Scripts/python test_core_updater.py
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import core_updater as cu

# Odczyt tokenu ze srodowiska — None jesli nie ustawiony (repo publiczne)
TOKEN = os.environ.get("GITHUB_TOKEN") or None


# ---------------------------------------------------------------------------
# 1. Testy jednostkowe _normalizuj_wersje (czysto lokalne, bez sieci)
# ---------------------------------------------------------------------------

def test_normalizuj():
    przypadki = [
        ("13.4",      (13, 4, 0)),
        ("v13.4.1",   (13, 4, 1)),
        ("13.5-WIP",  (13, 5, 0)),
        ("v2.0",      (2,  0, 0)),
        ("1.2.3",     (1,  2, 3)),
    ]
    ok = True
    for wejscie, oczekiwane in przypadki:
        wynik = cu._normalizuj_wersje(wejscie)
        status = "OK" if wynik == oczekiwane else "FAIL"
        if status == "FAIL":
            ok = False
        print(f"  [{status}] _normalizuj_wersje({wejscie!r}) = {wynik}  (oczekiwano {oczekiwane})")
    return ok


# ---------------------------------------------------------------------------
# 2. Odczyt pliku VERSION
# ---------------------------------------------------------------------------

def test_odczyt_version():
    try:
        wersja = cu._odczytaj_wersje_lokalna()
        print(f"  [OK] VERSION = {wersja!r}")
        return True
    except Exception as exc:
        print(f"  [FAIL] {exc}")
        return False


# ---------------------------------------------------------------------------
# 3. Zapytanie do GitHub API (wymaga internetu)
# ---------------------------------------------------------------------------

def test_github_api():
    token_info = "z tokenem" if TOKEN else "bez tokenu (repo publiczne)"
    print(f"  Odpytujem: {cu._API_URL}  [{token_info}]")
    try:
        dane = cu._pobierz_json_api(cu._API_URL, token=TOKEN)
        tag = dane.get("tag_name", "(brak)")
        assets = dane.get("assets", [])
        print(f"  [OK] Najnowszy release: {tag}  |  assets: {len(assets)}")
        for a in assets:
            print(f"       - {a['name']}  ({a.get('size', 0):,} B)")
        return True
    except Exception as exc:
        print(f"  [FAIL] {type(exc).__name__}: {exc}")
        return False


# ---------------------------------------------------------------------------
# 4. Pelny przeplyw: sprawdz_aktualizacje()
# ---------------------------------------------------------------------------

def test_sprawdz_aktualizacje():
    wynik = cu.sprawdz_aktualizacje(token=TOKEN)
    if wynik is None:
        wersja_lokalna = cu._odczytaj_wersje_lokalna()
        print(f"  [OK] Brak aktualizacji (lokalna: {wersja_lokalna})"
              " -- albo brak nowszego releasu, albo brak assetow instalatora.")
    else:
        print(f"  [OK] Dostepna aktualizacja!")
        print(f"       Tag:      {wynik.tag}")
        print(f"       Wersja:   {wynik.wersja}")
        print(f"       Plik:     {wynik.nazwa_pliku}")
        print(f"       Rozmiar:  {wynik.rozmiar_bajtow:,} B")
        print(f"       URL:      {wynik.url_instalatora}")
    return True


# ---------------------------------------------------------------------------
# Uruchomienie
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if TOKEN:
        print(f"GITHUB_TOKEN ustawiony (pierwsze 8 znakow: {TOKEN[:8]}...)")
    else:
        print("GITHUB_TOKEN nie ustawiony — zakladam repo publiczne.")

    wyniki = []

    print("\n=== 1. Normalizacja wersji ===")
    wyniki.append(test_normalizuj())

    print("\n=== 2. Odczyt pliku VERSION ===")
    wyniki.append(test_odczyt_version())

    print("\n=== 3. GitHub API ===")
    wyniki.append(test_github_api())

    print("\n=== 4. sprawdz_aktualizacje() ===")
    wyniki.append(test_sprawdz_aktualizacje())

    print()
    if all(wyniki):
        print("Wszystkie testy zaliczone.")
        sys.exit(0)
    else:
        print("Niektore testy nie przeszly -- sprawdz logi powyzej.")
        sys.exit(1)
