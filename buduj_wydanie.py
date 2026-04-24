import os
import re
import zipfile
import subprocess
import sys

import yaml

import generuj_dokumentacje


# =============================================================================
# STDOUT UTF-8 (fix dla Windowsa, gdzie domyślne cp1250 łamie się na emoji 🔍)
# =============================================================================
# Jeśli uruchomisz ten skrypt w CMD albo PowerShellu z polską lokalizacją,
# Python domyślnie używa kodowania cp1250 dla stdout — a to NIE umie znaków
# z płaszczyzny astralnej Unicode (emoji U+1F5xx). print("🔍 ...") wywala
# wtedy UnicodeEncodeError zanim w ogóle zdążymy wypisać cokolwiek innego.
# Wymuszamy UTF-8 przed pierwszym printem. Python 3.7+ ma reconfigure(); w
# starszych wersjach po prostu idziemy dalej.
if sys.platform == "win32":
    for strumien in (sys.stdout, sys.stderr):
        try:
            strumien.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass


# =============================================================================
# WYKRYWANIE WERSJI (wersja 13.1 — single source of truth: ui.yaml)
# =============================================================================
# Historia:
#   * do 12.x: numer wersji podawany ręcznie przez input() — literówki, desynchronizacja.
#   * 13.0:    cross-check main.py::MainFrame.VERSION ↔ pierwsza linia instrukcja.txt
#              — działało, ale wymagało edycji DWÓCH miejsc przy każdym bumpie.
#   * 13.1:    wersja migruje w całości do dictionaries/pl/gui/ui.yaml::app.wersja,
#              czytana przez t("app.wersja") z modułu i18n. Atrybut MainFrame.VERSION
#              i pierwsza linia instrukcja.txt przestały istnieć jako osobne źródła,
#              co sprawiło, że stary cross-check w buduj_wydanie.py zostaje „martwy"
#              (regex nie łapie → exit 1). Od Etapu 2/5 refaktoru dokumentacji build
#              wyciąga numer wersji bezpośrednio z ui.yaml — jedyny plik, który
#              deweloper musi zedytować, żeby wypuścić nowy release.
#
# Wartość `app.wersja` jest stringiem ludzkim, np. „13.1 – Wersja Wydawnicza" —
# regex wyłuskuje z niej sam numer („13.1"). Tolerujemy zarówno ASCII `-`, jak
# i typograficzny em-dash `–` w separatorze, bo oba warianty pojawiły się
# historycznie w plikach tłumaczeń.

SCIEZKA_UI_YAML    = os.path.join("dictionaries", "pl", "gui", "ui.yaml")
KLUCZ_WERSJI       = "app.wersja"
WZORZEC_NUMER_WERSJI = re.compile(r"\d+(?:\.\d+)+")


def odczytaj_wersje_z_ui_yaml() -> str:
    """Wyciąga numer wersji z ``dictionaries/pl/gui/ui.yaml::app.wersja``.

    Raises:
        RuntimeError: gdy plik nie istnieje, nie parsuje się jako YAML,
        nie ma klucza ``app.wersja`` albo wartość nie zawiera numeru
        wersji w formacie ``\\d+(?:\\.\\d+)+``.

    Returns:
        Sam numer wersji bez sufiksu opisowego, np. ``"13.1"`` z wartości
        ``"13.1 – Wersja Wydawnicza"``.
    """
    if not os.path.exists(SCIEZKA_UI_YAML):
        raise RuntimeError(
            f"Nie znaleziono {SCIEZKA_UI_YAML}. "
            "Uruchom skrypt z katalogu głównego projektu."
        )
    try:
        with open(SCIEZKA_UI_YAML, "r", encoding="utf-8") as fh:
            dane = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        raise RuntimeError(
            f"Plik {SCIEZKA_UI_YAML} nie parsuje się jako YAML: {exc}"
        ) from exc

    if not isinstance(dane, dict):
        raise RuntimeError(
            f"Plik {SCIEZKA_UI_YAML} nie zawiera mapy na najwyższym poziomie."
        )

    # Schodzenie po ścieżce zagnieżdżonej (kropka = kolejny poziom) — spójne
    # z semantyką `i18n.t()` i `generuj_dokumentacje._pobierz_wartosc()`.
    wartosc = dane
    for segment in KLUCZ_WERSJI.split("."):
        if not isinstance(wartosc, dict) or segment not in wartosc:
            raise RuntimeError(
                f"Nie znaleziono klucza '{KLUCZ_WERSJI}' w {SCIEZKA_UI_YAML}. "
                "Od wersji 13.1 to jedyne źródło prawdy dla numeru wersji — "
                "sprawdź, czy plik ui.yaml ma sekcję `app:` z polem `wersja:`."
            )
        wartosc = wartosc[segment]

    if not isinstance(wartosc, str):
        raise RuntimeError(
            f"Wartość '{KLUCZ_WERSJI}' w {SCIEZKA_UI_YAML} nie jest stringiem "
            f"(jest: {type(wartosc).__name__})."
        )

    dopasowanie = WZORZEC_NUMER_WERSJI.search(wartosc)
    if not dopasowanie:
        raise RuntimeError(
            f"Wartość '{KLUCZ_WERSJI}' w {SCIEZKA_UI_YAML} nie zawiera numeru "
            f"wersji w formacie X.Y.\n  Obecna wartość: {wartosc!r}"
        )
    return dopasowanie.group(0)


def sprawdz_czy_zip_juz_istnieje(nazwa_zip: str) -> None:
    """Przerywa budowanie, jeśli paczka tej wersji już leży na dysku.

    Celowo NIE nadpisujemy automatycznie — dzięki temu najnowszy release
    zostaje na dysku do czasu, gdy deweloper świadomie go usunie lub
    przenumeruje wersję. Chroni przed sytuacją „zbudowałem w złej kolejności
    i nadpisałem wcześniejszy wariant, którego już nigdy nie odtworzę".
    """
    if os.path.exists(nazwa_zip):
        print(f"❌ BŁĄD KRYTYCZNY: Paczka {nazwa_zip} już istnieje w katalogu.")
        print()
        print("Jedno z trojga:")
        print(f"  (a) Przenumeruj wersję w {SCIEZKA_UI_YAML} (klucz {KLUCZ_WERSJI}).")
        print(f"  (b) Przenieś dotychczasowy {nazwa_zip} do innego folderu "
              "(archiwum poprzednich releasów).")
        print(f"  (c) Świadomie usuń {nazwa_zip}, jeśli chcesz go odtworzyć "
              "z aktualnego stanu repo.")
        sys.exit(1)


# =============================================================================
# Reguły wykluczania plików (wspólne dla ZIP-a i filtrów)
# =============================================================================
IGNOROWANE_FOLDERY = {'.git', '.vscode', '.cline', '__pycache__', 'skrypty', 'venv', '.venv', 'env'}
IGNOROWANE_PLIKI = {'.clinerules', 'requirements.txt', '.gitignore', 'buduj_wydanie.py', 'skrypt_instalatora.iss', 'golden_key.env', 'skonfiguruj_dev.bat', 'uruchom_rezysera_dev.bat'}
IGNOROWANE_ROZSZERZENIA = {'.env', '.pyc', '.md', '.sh', '.jsonl'}
KATALOG_ZRODLOWY = "."


def czy_ignorowac(sciezka, nazwa_pliku):
    """Decyduje, czy dany plik ma być pominięty w paczce ZIP."""
    sciezka_ukosniki = sciezka.replace('\\', '/')
    czesci_sciezki = sciezka_ukosniki.split('/')
    if any(ignorowany in czesci_sciezki for ignorowany in IGNOROWANE_FOLDERY):
        return True

    # Szablony YAML dokumentacji end-userowej — `dictionaries/<kod>/gui/dokumentacja/*.yaml`.
    # Te pliki są surowcem developerskim (treść z placeholderami `{app.wersja}`);
    # end-user dostaje przetworzone wersje w `docs/<id>.<kod>.txt`, generowane
    # przez `generuj_dokumentacje.py` przed pakowaniem. Do paczki trafiają
    # tylko docelowe .txt, bez surowych YAML-i — inaczej użytkownik widziałby
    # w aplikacji DWA warianty tego samego dokumentu i nie wiedział, który czytać.
    if '/gui/dokumentacja' in sciezka_ukosniki:
        return True

    if nazwa_pliku in IGNOROWANE_PLIKI:
        return True

    _, ext = os.path.splitext(nazwa_pliku)
    if ext.lower() in IGNOROWANE_ROZSZERZENIA:
        return True

    # --- SMART FILTER: Ochrona runtime/ ---
    # Ignorujemy pliki .exe i .zip TYLKO jeśli leżą bezpośrednio w głównym folderze ('.')
    if sciezka == KATALOG_ZRODLOWY and ext.lower() in {'.exe', '.zip'}:
        return True

    return False


# =============================================================================
# GŁÓWNY FLOW BUDOWANIA WYDANIA (wywoływany tylko przez __main__)
# =============================================================================
# Owinięcie całego flow w funkcję main() + wywołanie pod __main__ daje dwie
# korzyści:
#   1. Funkcje walidacji wersji (odczytaj_wersje_z_ui_yaml itp.) można
#      importować i testować w izolacji, bez wyzwalania guardu runtime/ ani
#      interaktywnego input().
#   2. Skrypt staje się zgodny z normalną konwencją Python (import-safe).


def main() -> None:
    # --- STRAŻNIK (GUARD CLAUSE) ---
    sciezka_python = os.path.join("runtime", "python.exe")

    # 1. Sprawdzenie, czy plik w ogóle istnieje
    if not os.path.exists("runtime") or not os.path.exists(sciezka_python):
        print("❌ BŁĄD KRYTYCZNY: Nie znaleziono folderu 'runtime/' z lokalnym środowiskiem Pythona!")
        print("Repozytorium Git nie zawiera bibliotek uruchomieniowych.")
        print("Zanim zbudujesz wydanie, musisz umieścić przenośnego Pythona w folderze 'runtime'.")
        sys.exit(1)

    # 2. Walidacja, czy to faktycznie działający interpreter Pythona
    print("🔍 Sprawdzanie środowiska uruchomieniowego...")
    try:
        # Próbujemy wywołać prostą komendę, która zwróci tekst "OK"
        wynik = subprocess.run(
            [sciezka_python, "-c", "print('OK')"],
            capture_output=True,
            text=True,
            timeout=3  # Zabezpieczenie przed zawieszeniem
        )

        if "OK" not in wynik.stdout:
            print("❌ BŁĄD KRYTYCZNY: Plik 'runtime/python.exe' istnieje, ale nie zachowuje się jak Python!")
            print("Upewnij się, że umieszczono prawidłową wersję Portable, a nie instalator lub inny program.")
            sys.exit(1)

    except subprocess.TimeoutExpired:
        print("❌ BŁĄD KRYTYCZNY: Plik 'runtime/python.exe' przestał odpowiadać (Timeout). To prawdopodobnie nie jest Python.")
        sys.exit(1)
    except Exception as e:
        print(f"❌ BŁĄD KRYTYCZNY: Nie można uruchomić 'runtime/python.exe'. Szczegóły błędu: {e}")
        sys.exit(1)

    print("✅ Środowisko Pythona zweryfikowane pomyślnie.\n")

    # 3. Automatyczne wykrycie wersji (single source of truth: ui.yaml)
    print(f"🔍 Wykrywanie numeru wersji ({SCIEZKA_UI_YAML} → {KLUCZ_WERSJI})...")
    try:
        wersja = odczytaj_wersje_z_ui_yaml()
    except RuntimeError as exc:
        print(f"❌ BŁĄD KRYTYCZNY (odczyt wersji): {exc}")
        sys.exit(1)
    print(f"✅ Wersja wczytana: {wersja}\n")

    nazwa_zip = f"Rezyser_Audio_v{wersja}_Portable.zip"

    # 4. Blokada nadpisywania poprzedniego releasu
    sprawdz_czy_zip_juz_istnieje(nazwa_zip)

    # 5. Ostatnie potwierdzenie dewelopera przed kompresją
    odp = input(f"Zbudować paczkę {nazwa_zip}? (t/n): ").strip().lower()
    if odp != "t":
        print("Anulowano budowanie wydania.")
        sys.exit(0)

    # 6. Regeneracja dokumentacji end-userowej (docs/<id>.<kod>.txt)
    # Wywołujemy generator in-proc (ten sam proces Pythona, bez subprocess),
    # bo moduł ma własny UTF-8 fix i nie potrzebuje osobnej sesji. Dzięki
    # temu masz gwarancję, że paczka ZIP zawiera świeże docs/ nawet jeśli
    # deweloper zapomniał ręcznie uruchomić generator po edycji szablonu.
    print("🔍 Regeneracja dokumentacji (szablony YAML → docs/*.txt)...")
    generuj_dokumentacje.generuj()
    print("✅ Dokumentacja zregenerowana.\n")

    # 7. Budowanie wersji Portable (ZIP)
    print(f"[1/2] Pakowanie wersji Portable: {nazwa_zip}...")
    with zipfile.ZipFile(nazwa_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(KATALOG_ZRODLOWY):
            dirs[:] = [d for d in dirs if d not in IGNOROWANE_FOLDERY]
            for file in files:
                if not czy_ignorowac(root, file):
                    pelna_sciezka = os.path.join(root, file)
                    sciezka_w_zip = os.path.relpath(pelna_sciezka, KATALOG_ZRODLOWY)
                    zipf.write(pelna_sciezka, sciezka_w_zip)
    print("✅ Gotowe!")

    # 8. Budowanie wersji Instalacyjnej (EXE)
    chce_instalator = input("\nCzy chcesz wygenerowac rowniez instalator .exe? (t/n): ").strip().lower()

    if chce_instalator == 't':
        print("\n[2/2] Uruchamiam kompilator Inno Setup (iscc)...")
        komenda = f'iscc /Q skrypt_instalatora.iss /DMyAppVersion="{wersja}"'

        try:
            subprocess.run(komenda, shell=True, check=True)
            print(f"✅ Sukces! Utworzono instalator Rezyser_Audio_v{wersja}_Installer.exe")
        except subprocess.CalledProcessError:
            print("❌ Błąd kompilacji. Upewnij się, że Inno Setup jest zainstalowany, a 'iscc' dodano do systemowej zmiennej PATH.")
    else:
        print("\nPominięto budowanie instalatora.")


if __name__ == "__main__":
    main()
