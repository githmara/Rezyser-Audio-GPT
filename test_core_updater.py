"""
test_core_updater.py - Testy bez GUI dla modulu core_updater.

Uruchom:  .venv/Scripts/python -m pytest test_core_updater.py -q
Albo jako skrypt (deleguje do pytesta): .venv/Scripts/python test_core_updater.py
Opcjonalnie z tokenem: GITHUB_TOKEN=ghp_... (repo jest publiczne, wiec token
jest tylko podniesieniem limitu 60 zapytan/h).

HISTORIA TEGO PLIKU, bo to lekcja, nie ciekawostka (v19.2.1): do tej wersji
wszystkie cztery funkcje ZWRACALY bool zamiast asertowac — wzorzec z czasow, gdy
plik byl skryptem z wlasnym `__main__`-harnessem sumujacym wyniki. Pod pytestem
wartosc zwracana jest IGNOROWANA, wiec kazdy z tych testow przechodzil ZAWSZE,
takze gdy sprawdzana rzecz byla zepsuta. Pytest 9 zglasza to jako
`PytestReturnNotNoneWarning`. Wniosek do powtarzania: test, ktory nie ma jak
zawiesc, jest gorszy od braku testu — brak testu widac w spisie, a zielony pusty
przebieg uczy, ze obszar jest pokryty.

Testy sieciowe SKIPUJA sie przy braku laczności, zamiast przechodzic na zielono.
Skip jest widoczny w podsumowaniu pytesta, "pass" nie da sie odroznic od realnej
weryfikacji.
"""

import os
import sys
import urllib.error
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import core_updater as cu

# Odczyt tokenu ze srodowiska — None jesli nie ustawiony (repo publiczne)
TOKEN = os.environ.get("GITHUB_TOKEN") or None

# Bledy, ktore znacza "nie ma sieci / API nie odpowiada", a nie "nasz kod jest zly".
BLEDY_SIECI = (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError)


# ---------------------------------------------------------------------------
# 1. Testy jednostkowe _normalizuj_wersje (czysto lokalne, bez sieci)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("wejscie, oczekiwane", [
    ("13.4",     (13, 4, 0)),
    ("v13.4.1",  (13, 4, 1)),
    ("13.5-WIP", (13, 5, 0)),
    ("v2.0",     (2,  0, 0)),
    ("1.2.3",    (1,  2, 3)),
])
def test_normalizuj(wejscie, oczekiwane):
    assert cu._normalizuj_wersje(wejscie) == oczekiwane


# ---------------------------------------------------------------------------
# 2. Odczyt pliku VERSION
# ---------------------------------------------------------------------------

def test_odczyt_version():
    """VERSION musi dac sie odczytac i znormalizowac.

    Dawna wersja lapala `Exception` i zwracala False — czyli brak pliku VERSION
    konczyl sie zielonym testem. Tutaj wyjatek MA wyleciec: to jedyny plik,
    z ktorego bierze sie numer wersji w calym projekcie.
    """
    wersja = cu._odczytaj_wersje_lokalna()
    assert isinstance(wersja, str) and wersja.strip(), f"VERSION puste: {wersja!r}"
    numer = cu._normalizuj_wersje(wersja)
    assert len(numer) == 3 and all(isinstance(c, int) for c in numer), numer
    assert numer != (0, 0, 0), f"VERSION {wersja!r} znormalizowalo sie do zera"


# ---------------------------------------------------------------------------
# 3. Zapytanie do GitHub API (wymaga internetu — przy braku SKIP, nie pass)
# ---------------------------------------------------------------------------

def test_github_api():
    try:
        dane = cu._pobierz_json_api(cu._API_URL, token=TOKEN)
    except BLEDY_SIECI as exc:
        pytest.skip(f"GitHub API nieosiagalne ({type(exc).__name__}: {exc})")

    assert isinstance(dane, dict), type(dane)
    tag = dane.get("tag_name")
    assert tag, f"odpowiedz API bez `tag_name`: {sorted(dane)[:10]}"
    assert cu._normalizuj_wersje(tag) != (0, 0, 0), f"tag nie parsuje sie: {tag!r}"

    # Wydanie MUSI miec instalator i jego sume — updater weryfikuje nia pobranie
    # (od v18.10), a bez sumy weryfikacja SHA256 jest po cichu pomijana.
    nazwy = [a.get("name", "") for a in dane.get("assets", [])]
    assert any(n.endswith(".exe") for n in nazwy), f"brak assetu .exe: {nazwy}"
    assert any(n.endswith(".exe.sha256") for n in nazwy), f"brak sumy .sha256: {nazwy}"


# ---------------------------------------------------------------------------
# 4. Pelny przeplyw: sprawdz_aktualizacje()
# ---------------------------------------------------------------------------

def test_sprawdz_aktualizacje():
    """Kontrakt: albo None (brak nowszego wydania), albo KOMPLETNY UpdateInfo.

    Dawna wersja konczyla sie `return True` w OBU galeziach, wiec nie sprawdzala
    niczego poza tym, ze funkcja nie rzuca. Tu wariant "jest aktualizacja" musi
    dowiezc wszystkie pola, ktorych dialog updatera faktycznie uzywa — pusty
    `url_instalatora` albo zerowy rozmiar to defekt, a nie "brak aktualizacji".
    """
    try:
        wynik = cu.sprawdz_aktualizacje(token=TOKEN)
    except BLEDY_SIECI as exc:
        pytest.skip(f"GitHub API nieosiagalne ({type(exc).__name__}: {exc})")

    if wynik is None:
        # Brak nowszego wydania jest poprawnym wynikiem — ale wtedy lokalna
        # wersja musi byc odczytywalna, inaczej None znaczylo by co innego.
        assert cu._odczytaj_wersje_lokalna().strip()
        return

    assert wynik.tag and wynik.wersja, (wynik.tag, wynik.wersja)
    assert wynik.nazwa_pliku.endswith(".exe"), wynik.nazwa_pliku
    assert wynik.url_instalatora.startswith("https://"), wynik.url_instalatora
    assert wynik.rozmiar_bajtow > 0, wynik.rozmiar_bajtow
    # Nowsza niz lokalna — inaczej `sprawdz_aktualizacje` nie powinno jej zwrocic.
    assert (cu._normalizuj_wersje(wynik.wersja)
            > cu._normalizuj_wersje(cu._odczytaj_wersje_lokalna()))


# ---------------------------------------------------------------------------
# Uruchomienie jako skrypt — deleguje do pytesta.
# ---------------------------------------------------------------------------
# Wlasny harness sumujacy bool-e byl dokladnie tym, co zepsulo te testy pod
# pytestem (dwa sposoby raportowania wyniku, z czego jeden cichy). Jeden
# mechanizm, jedno raportowanie.

if __name__ == "__main__":
    if TOKEN:
        print(f"GITHUB_TOKEN ustawiony (pierwsze 8 znakow: {TOKEN[:8]}...)")
    else:
        print("GITHUB_TOKEN nie ustawiony — zakladam repo publiczne.")
    sys.exit(pytest.main([__file__, "-v"]))
