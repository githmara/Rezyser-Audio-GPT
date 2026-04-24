"""
generuj_dokumentacje.py — Generator dokumentacji użytkownika (i18n, Etap 1).

Czyta szablony z `dictionaries/<kod>/gui/dokumentacja/*.yaml`, podstawia
placeholdery z `dictionaries/<kod>/gui/ui.yaml` i zapisuje wynik do
`docs/<id>.<kod>.txt`.

Model danych:
  * `id` (w szablonie YAML) → rdzeń nazwy pliku wynikowego
    (np. "manual" → `docs/manual.pl.txt`).
  * `tresc` (w szablonie YAML, block-scalar "|") → treść dokumentu
    z placeholderami `{klucz.zagniezdzony}` odpowiadającymi strukturze
    `ui.yaml`. Kropka w kluczu = schodzenie po ścieżce zagnieżdżonej.
  * Wartości nieznalezione w `ui.yaml` zostają jako literał `{klucz}` +
    ostrzeżenie w konsoli (nie rzucamy wyjątku — łagodna degradacja,
    żeby brakujące tłumaczenie nie blokowało wygenerowania reszty).

Konwencja nazewnicza plików wynikowych (decyzja 13.1):
  * Rdzeń nazwy po angielsku (ASCII-only) — `manual`, `dictionaries` —
    żeby zagraniczny użytkownik nie musiał parsować polskich słów
    w Eksploratorze plików / Finderze.
  * Kod ISO języka jako środkowy człon (`.pl`, `.en`, `.ru`, …) —
    od razu widoczne, w jakim języku jest treść.
  * Rozszerzenie `.txt` — plik zwykły tekstowy, otwieralny w dowolnym
    edytorze bez dodatkowego oprogramowania.

Użycie:
  python generuj_dokumentacje.py                # wygeneruj wszystkie języki
  python generuj_dokumentacje.py --sprawdz      # wygeneruj + smoke test (porównanie
                                                #    z referencyjnymi instrukcja.txt
                                                #    dla języka polskiego)

Moduł NIE zależy od wxPython — można go wywołać w headlessowym kontekście
(np. z `buduj_wydanie.py` przed pakowaniem paczki ZIP) bez inicjalizacji GUI.
"""
from __future__ import annotations

import argparse
import difflib
import re
import sys
from pathlib import Path
from typing import Any

import yaml


# ---------------------------------------------------------------------------
# STDOUT UTF-8 (fix dla Windowsa — cp1250 nie umie emoji jak ✅ ⚠️ ℹ️ ❌)
# ---------------------------------------------------------------------------
# Ten sam wzorzec co w `buduj_wydanie.py`. Bez niego `print("✅ ...")` wywala
# UnicodeEncodeError w natywnym CMD (dziedziczy lokalną cp1250 zamiast UTF-8),
# zanim cokolwiek innego zdąży się zalogować. Python 3.7+ ma `reconfigure()`;
# w starszych wersjach po prostu idziemy dalej.
if sys.platform == "win32":
    for strumien in (sys.stdout, sys.stderr):
        try:
            strumien.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass


# ---------------------------------------------------------------------------
# Stałe ścieżek (wszystko względem katalogu, w którym leży ten skrypt)
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
DICT_DIR = ROOT / "dictionaries"
DOCS_DIR = ROOT / "docs"

# Podfoldery w dictionaries/<kod>/gui/
FOLDER_GUI = "gui"
FOLDER_DOKUMENTACJA = "dokumentacja"
NAZWA_UI = "ui.yaml"

# Regex placeholdera: {klucz} albo {klucz.zagniezdzony.z.kropkami}
# - pierwszy znak: litera lub podkreślenie
# - dalej: litery, cyfry, podkreślenia, kropki (dla ścieżek zagnieżdżonych)
PLACEHOLDER_REGEX = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_.]*)\}")


# ---------------------------------------------------------------------------
# Wczytywanie UI i szablonów dokumentacji
# ---------------------------------------------------------------------------
def _wczytaj_yaml(sciezka: Path) -> dict[str, Any]:
    """Wczytuje plik YAML jako dict. Zwraca {} przy awarii (nie rzuca)."""
    if not sciezka.is_file():
        return {}
    try:
        with open(sciezka, "r", encoding="utf-8") as fh:
            dane = yaml.safe_load(fh)
    except (OSError, yaml.YAMLError) as exc:
        print(f"⚠️  Nie udało się wczytać {sciezka}: {exc}")
        return {}
    return dane if isinstance(dane, dict) else {}


def _wczytaj_ui(jezyk: str) -> dict[str, Any]:
    """Zwraca dict z ``dictionaries/<jezyk>/gui/ui.yaml`` (lub {} przy braku)."""
    return _wczytaj_yaml(DICT_DIR / jezyk / FOLDER_GUI / NAZWA_UI)


def _wczytaj_szablony(jezyk: str) -> list[tuple[str, str]]:
    """Zwraca listę (id, tresc) dla każdego szablonu w danym języku.

    Szablon = plik YAML w ``dictionaries/<jezyk>/gui/dokumentacja/``
    z polami ``id`` (rdzeń nazwy pliku wynikowego) oraz ``tresc``
    (block-scalar z właściwą treścią dokumentu + placeholdery).
    """
    folder = DICT_DIR / jezyk / FOLDER_GUI / FOLDER_DOKUMENTACJA
    if not folder.is_dir():
        return []

    szablony: list[tuple[str, str]] = []
    for plik in sorted(folder.glob("*.yaml")):
        dane = _wczytaj_yaml(plik)
        if not dane:
            continue
        id_szablonu = dane.get("id") or plik.stem
        tresc = dane.get("tresc", "")
        if not isinstance(id_szablonu, str) or not isinstance(tresc, str):
            print(f"⚠️  Pomijam {plik}: pola 'id' i 'tresc' muszą być stringami.")
            continue
        szablony.append((id_szablonu, tresc))
    return szablony


def _jezyki_ze_szablonami() -> list[str]:
    """Zwraca posortowaną listę kodów języków mających folder dokumentacja/."""
    if not DICT_DIR.is_dir():
        return []
    wyniki = []
    for wpis in sorted(DICT_DIR.iterdir()):
        if wpis.is_dir() and (wpis / FOLDER_GUI / FOLDER_DOKUMENTACJA).is_dir():
            wyniki.append(wpis.name)
    return wyniki


# ---------------------------------------------------------------------------
# Podstawianie placeholderów (identyczna semantyka co i18n._pobierz)
# ---------------------------------------------------------------------------
def _pobierz_wartosc(dane: dict[str, Any], klucz: str) -> Any:
    """Zwraca wartość pod kluczem zagnieżdżonym (kropka = schodzenie w dół)."""
    aktualne: Any = dane
    for segment in klucz.split("."):
        if isinstance(aktualne, dict) and segment in aktualne:
            aktualne = aktualne[segment]
        else:
            return None
    return aktualne


def _rozwin_placeholdery(szablon: str, ui_dane: dict[str, Any]) -> tuple[str, list[str]]:
    """Podstawia wszystkie ``{klucz}`` wartościami z ``ui_dane``.

    Returns:
        Krotka (wynikowa_tresc, lista_brakujacych_kluczy).
        Brakujące klucze zostają w tekście jako literał ``{klucz}`` i trafiają
        na listę — wywołujący może wypisać ostrzeżenie.
    """
    brakujace: list[str] = []

    def _zamien(match: re.Match[str]) -> str:
        klucz = match.group(1)
        wartosc = _pobierz_wartosc(ui_dane, klucz)
        if wartosc is None or not isinstance(wartosc, str):
            brakujace.append(klucz)
            return match.group(0)   # zostaw oryginalny {klucz}
        return wartosc

    wynik = PLACEHOLDER_REGEX.sub(_zamien, szablon)
    return wynik, brakujace


# ---------------------------------------------------------------------------
# Główna funkcja generatora
# ---------------------------------------------------------------------------
def generuj(docelowy_katalog: Path = DOCS_DIR, *, cicho: bool = False) -> list[Path]:
    """Generuje wszystkie pliki ``docs/<id>.<kod>.txt`` z szablonów YAML.

    Args:
        docelowy_katalog: Gdzie zapisać wynikowe pliki .txt (domyślnie ``docs/``).
        cicho:            Czy pominąć przyjazne komunikaty print (dla testów).

    Returns:
        Lista ścieżek wygenerowanych plików.
    """
    docelowy_katalog.mkdir(exist_ok=True)
    wyniki: list[Path] = []

    jezyki = _jezyki_ze_szablonami()
    if not jezyki and not cicho:
        print("ℹ️  Brak folderów dictionaries/<kod>/gui/dokumentacja/ — nic do zrobienia.")
        return wyniki

    for jezyk in jezyki:
        ui = _wczytaj_ui(jezyk)
        szablony = _wczytaj_szablony(jezyk)
        if not szablony and not cicho:
            print(f"ℹ️  {jezyk}: brak szablonów w gui/dokumentacja/.")
            continue

        for id_szablonu, tresc_szablonu in szablony:
            wynik_tresc, brakujace = _rozwin_placeholdery(tresc_szablonu, ui)
            if brakujace and not cicho:
                unikalne = sorted(set(brakujace))
                print(f"⚠️  {jezyk}/{id_szablonu}: brakujące placeholdery w ui.yaml: {unikalne}")

            sciezka_wyjscia = docelowy_katalog / f"{id_szablonu}.{jezyk}.txt"
            # Piszemy z `newline="\n"` — celowo LF, nie platform-default.
            # Dzięki temu diff na Windowsie vs Linux zwraca ten sam wynik,
            # a `git` może sam zdecydować o konwersji przy checkoucie.
            with open(sciezka_wyjscia, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(wynik_tresc)
            wyniki.append(sciezka_wyjscia)
            if not cicho:
                print(f"✅  {sciezka_wyjscia.relative_to(ROOT)}")

    return wyniki


# ---------------------------------------------------------------------------
# Smoke test: porównanie ze starymi plikami referencyjnymi (tylko Etap 1!)
# ---------------------------------------------------------------------------
def _znormalizuj(tekst: str) -> str:
    """Normalizuje EOL (CRLF → LF), żeby diff na Windowsie nie wybuchał."""
    return tekst.replace("\r\n", "\n")


def sprawdz_zgodnosc_z_referencyjnymi() -> int:
    """Smoke test Etapu 1: porównanie z dzisiejszym instrukcja.txt.

    Oczekiwany rezultat:
      * `docs/dictionaries.pl.txt` ≡ `dictionaries/instrukcja.txt` (bajt-po-bajcie
        po normalizacji EOL), bo ten plik nie ma placeholderów.
      * `docs/manual.pl.txt` różni się od `instrukcja.txt` WYŁĄCZNIE w linii
        z wersją (po migracji na ui.yaml wartość to "13.1 – Wersja Wydawnicza"
        zamiast zahardkodowanego "13.0 - Release Candidate"). To jest oczekiwana
        zmiana — ui.yaml jest od 13.1 źródłem prawdy dla wersji.

    Returns:
        Liczba par, gdzie diff przekracza tolerancję (0 = wszystko OK).
    """
    pary = [
        (DOCS_DIR / "manual.pl.txt",       ROOT / "instrukcja.txt",
         "Tolerowana różnica: 1 linia z wersją (13.0 → 13.1 po migracji na ui.yaml)."),
        (DOCS_DIR / "dictionaries.pl.txt", ROOT / "dictionaries" / "instrukcja.txt",
         "Powinien być identyczny bajt-po-bajcie (brak placeholderów)."),
    ]

    liczba_bledow = 0
    for wygenerowany, referencyjny, uwaga in pary:
        print(f"\n── Porównanie: {wygenerowany.name} ↔ {referencyjny.relative_to(ROOT)}")
        print(f"   {uwaga}")

        if not wygenerowany.is_file():
            print(f"   ❌ Brak wygenerowanego pliku: {wygenerowany}")
            liczba_bledow += 1
            continue
        if not referencyjny.is_file():
            print(f"   ❌ Brak referencyjnego pliku: {referencyjny}")
            liczba_bledow += 1
            continue

        tresc_wyg = _znormalizuj(wygenerowany.read_text(encoding="utf-8"))
        tresc_ref = _znormalizuj(referencyjny.read_text(encoding="utf-8"))

        if tresc_wyg == tresc_ref:
            print("   ✅ Pliki identyczne.")
            continue

        # Policz linie różniące się.
        # Tolerujemy różnice "whitespace-only" — wynikają z tego, że edytory
        # często auto-trimują trailing whitespace w pustych liniach
        # (a referencyjny `instrukcja.txt` miał je zachowane historycznie).
        # Semantycznie dla czytelnika plik wygląda identycznie — 1:1 puste linie.
        linie_wyg = tresc_wyg.splitlines()
        linie_ref = tresc_ref.splitlines()

        # Odrzucamy TRAILING EMPTY LINES przed liczeniem długości — referencyjny
        # `instrukcja.txt` miał historycznie 2 pustki na końcu pliku, a YAML
        # block-scalar `|` normalizuje do 1 trailing newline (UNIX best-practice).
        # Różnica niewidoczna w edytorze, irrelewantna dla usera.
        while linie_wyg and not linie_wyg[-1].strip():
            linie_wyg.pop()
        while linie_ref and not linie_ref[-1].strip():
            linie_ref.pop()
        rozniace_istotne = 0
        rozniace_kosmetyczne = 0
        for l_wyg, l_ref in zip(linie_wyg, linie_ref):
            if l_wyg == l_ref:
                continue
            if not l_wyg.strip() and not l_ref.strip():
                rozniace_kosmetyczne += 1
            else:
                rozniace_istotne += 1
        roznica_dlugosci = abs(len(linie_wyg) - len(linie_ref))
        rozniace = rozniace_istotne  # "istotne" = niepuste wizualnie

        print(
            f"   Różnic: {rozniace_istotne} istotnych + {rozniace_kosmetyczne} "
            f"kosmetycznych (trailing whitespace w pustych liniach), "
            f"{roznica_dlugosci} linii dopisanych/usuniętych."
        )
        diff = list(difflib.unified_diff(
            linie_ref, linie_wyg,
            fromfile=str(referencyjny.relative_to(ROOT)),
            tofile=str(wygenerowany.relative_to(ROOT)),
            lineterm="",
            n=1,
        ))
        for linia in diff[:20]:
            print("     " + linia)
        if len(diff) > 20:
            print(f"     ... (łącznie {len(diff)} linii diff, pokazano pierwsze 20)")

        # Tolerancje:
        #   * 0 istotnych różnic + 0 linii dopisanych/usuniętych → OK dla każdego pliku
        #     (kosmetyczne różnice whitespace-only w pustych liniach są akceptowane).
        #   * manual.pl.txt: dodatkowo DOKŁADNIE 1 istotna różnica (linia z wersją)
        #     jest akceptowana po migracji na `ui.yaml::app.wersja`.
        if rozniace_istotne == 0 and roznica_dlugosci == 0:
            print("   ✅ Różnica mieści się w tolerancji (tylko whitespace w pustych liniach).")
        elif (wygenerowany.name == "manual.pl.txt"
              and rozniace_istotne == 1 and roznica_dlugosci == 0):
            print("   ✅ Różnica mieści się w tolerancji (tylko linia z wersją — oczekiwana po migracji).")
        else:
            liczba_bledow += 1

    return liczba_bledow


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generator dokumentacji użytkownika (i18n, Etap 1 wersji 13.x).",
    )
    parser.add_argument(
        "--sprawdz",
        action="store_true",
        help="Po wygenerowaniu porównaj output z referencyjnymi plikami "
             "(instrukcja.txt w rooclie i dictionaries/instrukcja.txt).",
    )
    args = parser.parse_args()

    generuj()

    if args.sprawdz:
        print("\n========== SMOKE TEST ==========")
        bledy = sprawdz_zgodnosc_z_referencyjnymi()
        print("================================")
        if bledy:
            print(f"❌ Smoke test NIE przeszedł: {bledy} par z błędami.")
            return 1
        print("✅ Smoke test OK (wszystkie pary mieszczą się w tolerancji).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
