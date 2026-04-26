"""
generuj_dokumentacje.py — Generator dokumentacji użytkownika (i18n).

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
  python generuj_dokumentacje.py --waliduj      # wygeneruj + twardy check
                                                #   (exit 1, jeśli jakikolwiek
                                                #    placeholder NIE został
                                                #    rozwinięty przez ui.yaml)

Historia trybów weryfikacji:
  * Etap 1/5 miał tryb `--sprawdz`, który porównywał wygenerowane pliki
    z historycznymi `instrukcja.txt` i `dictionaries/instrukcja.txt`
    (tolerancja: 1 linia z wersją, whitespace-only). W Etapie 2/5 oba
    referencyjne pliki zostały usunięte z repozytorium — `docs/*.txt`
    stały się jedyną kanoniczną formą. Zastąpiliśmy więc tryb porównawczy
    trybem `--waliduj`, który sprawdza, co realnie chroni spójność:
    czy każdy `{placeholder}` w szablonach ma wartość w `ui.yaml`.

Moduł NIE zależy od wxPython — można go wywołać w headlessowym kontekście
(np. z `buduj_wydanie.py` przed pakowaniem paczki ZIP) bez inicjalizacji GUI.
"""
from __future__ import annotations

import argparse
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

# Single source of truth dla numeru wersji (od 13.4) — plik VERSION w roocie.
# Wczytywane raz przy imporcie, używane do rozwinięcia placeholdera
# `{numer_wersji}` zagnieżdżonego w wartościach `app.wersja` w ui.yaml
# (regex `_rozwin_placeholdery` nie iteruje rekursywnie, więc po pobraniu
# wartości robimy explicit replace w `_zamien`).
_PLIK_WERSJI = ROOT / "VERSION"
try:
    NUMER_WERSJI = _PLIK_WERSJI.read_text(encoding="utf-8").strip()
except OSError:
    NUMER_WERSJI = "?"

# Podfoldery w dictionaries/<kod>/gui/
FOLDER_GUI = "gui"
FOLDER_DOKUMENTACJA = "dokumentacja"
NAZWA_UI = "ui.yaml"

# Regex placeholdera: {klucz} albo {klucz.zagniezdzony.z.kropkami}
# - pierwszy znak: litera lub podkreślenie
# - dalej: litery, cyfry, podkreślenia, kropki (dla ścieżek zagnieżdżonych)
PLACEHOLDER_REGEX = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_.]*)\}")

# Regex akceleratora wxPython: `&` przed dowolną literą Unicode (A-Z, a-z,
# także polskie Ą/ę/Ł itd.). `[^\W\d_]` w trybie domyślnym Pythona działa
# w Unicode, więc łapie akceleratory na przetłumaczonych literach w EN/RU/FI.
# Nie ruszamy `& ` z neutralnych kontekstów typu "Tom & Jerry" — bez litery
# po `&` regex się nie dopasuje.
AKCELERATOR_REGEX = re.compile(r"&([^\W\d_])", flags=re.UNICODE)



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
    """Zwraca posortowaną listę kodów języków, dla których generujemy docs/.

    Od 13.1 stosujemy ten sam filtr kompletności co `dostepne_jezyki_bazowe()`
    w `core_poliglota.py` — generujemy `docs/<id>.<kod>.txt` tylko dla języków
    z PEŁNYM pakietem (`podstawy.yaml` + `gui/ui.yaml` + `akcenty/*.yaml` ≥ 1
    + `szyfry/*.yaml` ≥ 1). Stuby z samym podfolderem `gui/dokumentacja/`
    pomija — w aplikacji i tak są zafiltrowane z menu „Język interfejsu"
    i z listy „obsługiwanych języków", więc dorzucanie użytkownikowi
    instrukcji obsługi w „nieistniejącym" języku byłoby tylko *cosmetic
    confusion*.

    Import `core_poliglota` jest LAZY — generator może być wciąż wywoływany
    standalone (np. z CLI), zanim załadowane są wszystkie moduły aplikacji.
    Gdy import się nie uda (np. minimalny kontekst, brak `docx` lub
    `num2words`), wracamy do zachowania historycznego: wszystkie foldery
    z `gui/dokumentacja/` są generowane (niemaskowanie).
    """
    if not DICT_DIR.is_dir():
        return []

    try:
        from core_poliglota import _jezyk_kompletny
    except ImportError:
        _jezyk_kompletny = None

    wyniki = []
    for wpis in sorted(DICT_DIR.iterdir()):
        if not (wpis.is_dir() and (wpis / FOLDER_GUI / FOLDER_DOKUMENTACJA).is_dir()):
            continue
        if _jezyk_kompletny is not None and not _jezyk_kompletny(wpis.name):
            continue
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


def _normalizuj_etykiete(wartosc: str) -> str:
    """Usuwa z etykiety GUI dekoratory wxPython niepotrzebne w dokumentacji.

    Etykiety w ``ui.yaml`` są zapisane tak, jak wxPython ich oczekuje:
        * ``&Reżyser``         — `&` przed literą robi z niej akcelerator
                                 (Alt+R w GUI). W dokumentacji tekstowej
                                 `&` wygląda jak literówka.
        * ``Strona główna\tCtrl+0`` — znak tabulatora oddziela etykietę
                                       menu od skrótu klawiszowego.
                                       W docs interesuje nas tylko sama
                                       etykieta; skrót („Ctrl+0") cytujemy
                                       osobno w tekście opisowym.

    Ta funkcja jest wywoływana TYLKO tutaj — moduł `i18n.py`, używany przez
    runtime GUI, zachowuje oryginalne stringi z `&`/`\\t` bez zmian,
    bo wxPython ich potrzebuje.
    """
    # 1) Ucinamy skrót klawiszowy. Pierwszy `\t` jest separatorem.
    if "\t" in wartosc:
        wartosc = wartosc.split("\t", 1)[0].rstrip()
    # 2) Usuwamy `&` tylko wtedy, gdy działa jako akcelerator (przed literą).
    wartosc = AKCELERATOR_REGEX.sub(r"\1", wartosc)
    return wartosc


def _rozwin_placeholdery(szablon: str, ui_dane: dict[str, Any]) -> tuple[str, list[str]]:
    """Podstawia wszystkie ``{klucz}`` wartościami z ``ui_dane``.

    Wartości przechodzą przez `_normalizuj_etykiete` — wstawiamy do
    dokumentacji „suchą" wersję etykiety bez `&` akceleratora i bez
    końcówki `\\tCtrl+…`, żeby tekst .txt czytało się naturalnie nawet
    dla przycisków/menu, które w GUI mają te dekoratory.

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
        # Drugi krok: rozwiń zagnieżdżony placeholder {numer_wersji}, jeśli
        # występuje w wartości (np. `app.wersja: "{numer_wersji} – Sufiks"`
        # w ui.yaml — od 13.4 numer wersji żyje w pliku VERSION).
        if "{numer_wersji}" in wartosc:
            wartosc = wartosc.replace("{numer_wersji}", NUMER_WERSJI)
        return _normalizuj_etykiete(wartosc)

    wynik = PLACEHOLDER_REGEX.sub(_zamien, szablon)
    return wynik, brakujace



# ---------------------------------------------------------------------------
# Główna funkcja generatora
# ---------------------------------------------------------------------------
def generuj(
    docelowy_katalog: Path = DOCS_DIR,
    *,
    cicho: bool = False,
    zbieraj_brakujace: dict[str, list[str]] | None = None,
) -> list[Path]:
    """Generuje wszystkie pliki ``docs/<id>.<kod>.txt`` z szablonów YAML.

    Args:
        docelowy_katalog:   Gdzie zapisać wynikowe pliki .txt (domyślnie ``docs/``).
        cicho:              Czy pominąć przyjazne komunikaty print (dla testów).
        zbieraj_brakujace:  Jeśli podasz pusty dict, funkcja wypełni go
                            mapowaniem ``"<jezyk>/<id_szablonu>"`` →
                            posortowana lista unikalnych brakujących placeholderów.
                            Używane przez tryb ``--waliduj`` do zwrócenia
                            twardego exit code po zakończeniu generacji.

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
            if zbieraj_brakujace is not None and brakujace:
                zbieraj_brakujace[f"{jezyk}/{id_szablonu}"] = sorted(set(brakujace))

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
# Walidacja: czy wszystkie placeholdery rozwinięte przez ui.yaml?
# ---------------------------------------------------------------------------
def waliduj() -> int:
    """Twardy check spójności szablonów z ``ui.yaml``.

    Generuje pliki tak samo jak ``generuj()``, a następnie sprawdza,
    czy w którymkolwiek szablonie pozostał niesparowany placeholder
    ``{klucz.zagniezdzony}``, dla którego nie znaleziono wartości
    w ``dictionaries/<jezyk>/gui/ui.yaml``.

    To jest jedyny mechaniczny kontrakt między szablonami dokumentacji
    a warstwą i18n. Nie dba o stylistykę ani zawartość merytoryczną
    (tłumaczenia robi człowiek albo LLM), dba tylko o to, żeby żadna
    nazwa klucza nie zostawała w wynikowym .txt jako surowy `{coś}`.

    Returns:
        0 — wszystkie placeholdery rozwinięte, paczka gotowa do buildu.
        1 — znaleziono brakujące placeholdery; exit code dla CI / buduj_wydanie.
    """
    brakujace_wedlug_pliku: dict[str, list[str]] = {}
    generuj(zbieraj_brakujace=brakujace_wedlug_pliku)

    print("\n========== WALIDACJA PLACEHOLDERÓW ==========")
    if not brakujace_wedlug_pliku:
        print("✅ Wszystkie {placeholdery} w szablonach mają wartości w ui.yaml.")
        print("=============================================")
        return 0

    print(f"❌ Znaleziono brakujące placeholdery w {len(brakujace_wedlug_pliku)} "
          f"szablonie/ach:")
    for nazwa, brakujace in sorted(brakujace_wedlug_pliku.items()):
        print(f"  • {nazwa}")
        for klucz in brakujace:
            print(f"      - {{{klucz}}}")
    print("=============================================")
    print(
        "Napraw: dodaj brakujące klucze do ui.yaml danego języka ALBO usuń "
        "nieużywane placeholdery z szablonu. Surowe `{coś}` w docs/*.txt "
        "wygląda jak błąd, więc build nie przejdzie."
    )
    return 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generator dokumentacji użytkownika (i18n).",
    )
    parser.add_argument(
        "--waliduj",
        action="store_true",
        help="Po wygenerowaniu sprawdź, czy wszystkie {placeholdery} zostały "
             "rozwinięte przez ui.yaml. Exit 1, gdy cokolwiek zostało jako "
             "surowe `{klucz}` w wynikowym docs/*.txt.",
    )
    args = parser.parse_args()

    if args.waliduj:
        return waliduj()

    generuj()
    return 0


if __name__ == "__main__":
    sys.exit(main())
