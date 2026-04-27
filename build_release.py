import os
import zipfile
import subprocess
import sys

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
# WYKRYWANIE WERSJI (od 13.4 — single source of truth: plik VERSION w roocie)
# =============================================================================
# Historia:
#   * do 12.x: numer wersji podawany ręcznie przez input() — literówki, desynchronizacja.
#   * 13.0:    cross-check main.py::MainFrame.VERSION ↔ pierwsza linia instrukcja.txt
#              — działało, ale wymagało edycji DWÓCH miejsc przy każdym bumpie.
#   * 13.1:    wersja migruje w całości do dictionaries/pl/gui/ui.yaml::app.wersja,
#              czytana przez t("app.wersja"). Bumpa robisz w jednym pliku — ALE
#              po dodaniu kolejnych języków (en/fi/is/it/ru w 13.3) pojawiła się
#              regresja: app.wersja jest powielony w każdej paczce, co przy
#              bumpie skaluje się liniowo z liczbą języków (fi/is/it/ru tkwiło
#              przez dwa wydania na "13.1" — nikt nie pamiętał).
#   * 13.4:    numer wersji wyjeżdża do plain-text pliku VERSION w roocie.
#              W ui.yaml::app.wersja zostaje tylko placeholder typu
#              "{numer_wersji} – Wersja Wydawnicza". i18n.py auto-wstrzykuje
#              numer_wersji do każdego format() w t(), więc main.py i szablony
#              docs/manual.*.txt nadal działają bez zmian. Bumpa robisz wyłącznie
#              w pliku VERSION — niezależnie od liczby paczek językowych.

SCIEZKA_VERSION = os.path.join(os.path.dirname(__file__), "VERSION")


def odczytaj_wersje() -> str:
    """Wczytuje numer wersji z pliku ``VERSION`` w roocie projektu.

    Raises:
        RuntimeError: gdy plik nie istnieje albo jest pusty/białoznakowy.

    Returns:
        Numer wersji bez końcowego whitespace'a, np. ``"13.4-WIP"`` lub ``"13.4"``.
    """
    if not os.path.exists(SCIEZKA_VERSION):
        raise RuntimeError(
            f"Nie znaleziono pliku VERSION w {SCIEZKA_VERSION}. "
            "Od 13.4 to jedyne źródło prawdy dla numeru wersji — "
            "sprawdź, czy plik istnieje w roocie projektu."
        )
    try:
        with open(SCIEZKA_VERSION, "r", encoding="utf-8") as fh:
            wartosc = fh.read().strip()
    except OSError as exc:
        raise RuntimeError(f"Nie udało się odczytać {SCIEZKA_VERSION}: {exc}") from exc

    if not wartosc:
        raise RuntimeError(
            f"Plik {SCIEZKA_VERSION} jest pusty. Wpisz numer wersji "
            "(np. 13.4 albo 13.4-WIP)."
        )
    return wartosc


def sprawdz_czy_zip_juz_istnieje(nazwa_zip: str) -> None:
    """Przerywa budowanie, jeśli paczka tej wersji już leży na dysku.

    Celowo NIE nadpisujemy automatycznie — dzięki temu najnowszy release
    zostaje na dysku do czasu, gdy deweloper świadomie go usunie lub
    przenumeruje wersję. Chroni przed sytuacją „zbudowałem w złej kolejności
    i nadpisałem wcześniejszy wariant, którego już nigdy nie odtworzę".

    Komunikaty po angielsku — od 13.1 cała infrastruktura buildowa mówi do
    dewelopera po angielsku, żeby ewentualni zagraniczni kontrybutorzy mieli
    zerowy próg wejścia. Polski interfejs aplikacji dla end-userów
    (dictionaries/pl/gui/ui.yaml) zostaje bez zmian.
    """
    if os.path.exists(nazwa_zip):
        print(f"❌ FATAL: Release package {nazwa_zip} already exists in this directory.")
        print()
        print("Pick one of three:")
        print(f"  (a) Bump the version in {SCIEZKA_VERSION}.")
        print(f"  (b) Move the existing {nazwa_zip} somewhere else "
              "(archive of previous releases).")
        print(f"  (c) Delete {nazwa_zip} on purpose if you want to rebuild it "
              "from the current state of the repo.")
        sys.exit(1)



# =============================================================================
# Reguły wykluczania plików (wspólne dla ZIP-a i filtrów)
# =============================================================================
IGNOROWANE_FOLDERY = {'.git', '.vscode', '.cline', '.claude', '__pycache__', 'skrypty', 'venv', '.venv', 'env'}
# Skrypty infrastruktury developerskiej (nigdy nie trafiają do paczki dla
# end-usera). Nazwy zangielszczone w 13.1 — patrz changelog manual.yaml:
#   skonfiguruj_dev.bat  → setup_dev.bat
#   skonfiguruj_dev.sh   → setup_dev.sh   (filtrowane przez `.sh` w IGNOROWANE_ROZSZERZENIA)
#   uruchom_rezysera_dev.bat → run_dev.bat
#   uruchom_rezysera.sh  → run.sh         (filtrowane przez `.sh` w IGNOROWANE_ROZSZERZENIA)
#   buduj_wydanie.py     → build_release.py
#   skrypt_instalatora.iss → installer.iss
IGNOROWANE_PLIKI = {'.clinerules', 'requirements.txt', '.gitignore', 'build_release.py', 'installer.iss', 'golden_key.env', 'setup_dev.bat', 'run_dev.bat', 'buduj_wielojezyczne_docs.py', 'buduj_wielojezyczne_ui.py'}
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
#   1. Funkcje walidacji wersji (odczytaj_wersje itp.) można
#      importować i testować w izolacji, bez wyzwalania guardu runtime/ ani
#      interaktywnego input().
#   2. Skrypt staje się zgodny z normalną konwencją Python (import-safe).


def main() -> None:
    # --- GUARD CLAUSE (runtime/ folder check) ---
    sciezka_python = os.path.join("runtime", "python.exe")

    # 1. Check if the portable Python file exists at all.
    if not os.path.exists("runtime") or not os.path.exists(sciezka_python):
        print("❌ FATAL: 'runtime/' folder with the portable Python environment not found!")
        print("The Git repo does not ship runtime libraries.")
        print("Drop a portable Python into the 'runtime/' folder before building a release.")
        sys.exit(1)

    # 2. Validate that it behaves like a real Python interpreter.
    print("🔍 Verifying the runtime Python environment...")
    try:
        wynik = subprocess.run(
            [sciezka_python, "-c", "print('OK')"],
            capture_output=True,
            text=True,
            timeout=3,  # guard against a hang
        )

        if "OK" not in wynik.stdout:
            print("❌ FATAL: 'runtime/python.exe' exists but does not behave like Python!")
            print("Make sure you put a proper Portable Python build there, not an installer or some other program.")
            sys.exit(1)

    except subprocess.TimeoutExpired:
        print("❌ FATAL: 'runtime/python.exe' stopped responding (timeout). It is probably not Python.")
        sys.exit(1)
    except Exception as e:
        print(f"❌ FATAL: Cannot launch 'runtime/python.exe'. Details: {e}")
        sys.exit(1)

    print("✅ Portable Python environment verified.\n")

    # 3. Read the release version (single source of truth: VERSION in repo root).
    print(f"🔍 Detecting release version ({SCIEZKA_VERSION})...")
    try:
        wersja = odczytaj_wersje()
    except RuntimeError as exc:
        print(f"❌ FATAL (version read): {exc}")
        sys.exit(1)
    print(f"✅ Version loaded: {wersja}\n")

    nazwa_zip = f"Rezyser_Audio_v{wersja}_Portable.zip"

    # 4. Refuse to overwrite a previous release package.
    sprawdz_czy_zip_juz_istnieje(nazwa_zip)

    # 5. Last-chance developer confirmation before we actually compress.
    odp = input(f"Build package {nazwa_zip}? (y/n): ").strip().lower()
    if odp not in ("y", "t"):   # `t` kept as alias — historical tak/nie habit
        print("Build aborted.")
        sys.exit(0)

    # 6. Regenerate end-user documentation (docs/<id>.<kod>.txt).
    # We call the generator in-process (same Python process, no subprocess) —
    # the module has its own UTF-8 fix and does not need a fresh session.
    # This guarantees the ZIP package ships fresh docs/ even when the developer
    # forgot to run the generator manually after editing a template.
    print("🔍 Regenerating documentation (YAML templates → docs/*.txt)...")
    generuj_dokumentacje.generuj()
    print("✅ Documentation regenerated.\n")

    # 7. Build the Portable ZIP package.
    print(f"[1/2] Packing the Portable ZIP: {nazwa_zip}...")
    with zipfile.ZipFile(nazwa_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(KATALOG_ZRODLOWY):
            dirs[:] = [d for d in dirs if d not in IGNOROWANE_FOLDERY]
            for file in files:
                if not czy_ignorowac(root, file):
                    pelna_sciezka = os.path.join(root, file)
                    sciezka_w_zip = os.path.relpath(pelna_sciezka, KATALOG_ZRODLOWY)
                    zipf.write(pelna_sciezka, sciezka_w_zip)
    print("✅ Done!")

    # 8. Build the Installer EXE (always — required for GitHub Releases auto-update).
    print("\n[2/2] Launching the Inno Setup compiler (iscc)...")
    komenda = f'iscc /Q installer.iss /DMyAppVersion="{wersja}"'

    try:
        subprocess.run(komenda, shell=True, check=True)
        print(f"✅ Success! Installer created: Rezyser_Audio_v{wersja}_Installer.exe")
    except subprocess.CalledProcessError:
        print("❌ Compilation error. Make sure Inno Setup is installed and 'iscc' is in your system PATH.")



if __name__ == "__main__":
    main()
