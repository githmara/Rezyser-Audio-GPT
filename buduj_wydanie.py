import os
import re
import zipfile
import subprocess
import sys


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

# WYKRYWANIE I WALIDACJA WERSJI (wersja 13.0 — koniec z input() i literówkami)
# =============================================================================
# Wersja 12.0 i wcześniejsze prosiły o numer wersji przez input(). To otwierało
# drzwi na czynnik ludzki: literówka w numerze, przypadkowa spacja albo —
# najgorsze — zbudowanie paczki z inną wersją niż ta, którą widzi użytkownik
# w tytule okna aplikacji. W 13.0 wersja jest wyliczana automatycznie z dwóch
# źródeł prawdy i porównywana krzyżowo:
#
#   1) main.py  → klasa MainFrame, atrybut VERSION = "13.0 – ..." (to, co
#      widzi end-user w pasku tytułu okna aplikacji).
#   2) instrukcja.txt → pierwsza linia nagłówka "...(Wersja 13.0 - ...)".
#
# Obie muszą zwrócić IDENTYCZNY numer (np. "13.0"). Jeśli się rozjeżdżają,
# skrypt przerywa działanie ze wskazaniem, który plik wymaga aktualizacji.
# Dodatkowo, jeśli paczka ZIP tej wersji już istnieje na dysku, skrypt też
# przerywa — zmuszając dewelopera do przenumerowania wersji (częstsza
# sytuacja) albo świadomego usunięcia poprzedniego buildu.

SCIEZKA_MAIN_PY      = "main.py"
SCIEZKA_INSTRUKCJA   = "instrukcja.txt"
WZORZEC_VERSION_PY   = re.compile(r'VERSION\s*=\s*"(\d+(?:\.\d+)+)')
WZORZEC_WERSJA_TXT   = re.compile(r'Wersja\s+(\d+(?:\.\d+)+)')


def odczytaj_wersje_z_main_py() -> str:
    """Wyciąga numer wersji z ``MainFrame.VERSION`` w main.py.

    Raises:
        RuntimeError: gdy plik nie istnieje albo wzorzec nie pasuje.

    Returns:
        Sam numer wersji bez sufiksu opisowego, np. ``"13.0"`` z linii
        ``VERSION = "13.0 – Wersja Wydawnicza"``.
    """
    if not os.path.exists(SCIEZKA_MAIN_PY):
        raise RuntimeError(
            f"Nie znaleziono {SCIEZKA_MAIN_PY}. "
            "Uruchom skrypt z katalogu głównego projektu."
        )
    with open(SCIEZKA_MAIN_PY, "r", encoding="utf-8") as fh:
        tresc = fh.read()
    dopasowanie = WZORZEC_VERSION_PY.search(tresc)
    if not dopasowanie:
        raise RuntimeError(
            f"Nie znaleziono linii 'VERSION = \"X.Y ...\"' w {SCIEZKA_MAIN_PY}. "
            "Sprawdź, czy klasa MainFrame nadal ma atrybut VERSION."
        )
    return dopasowanie.group(1)


def odczytaj_wersje_z_instrukcji() -> str:
    """Wyciąga numer wersji z pierwszej linii instrukcja.txt.

    Raises:
        RuntimeError: gdy plik nie istnieje albo wzorzec nie pasuje.

    Returns:
        Sam numer wersji z fragmentu "(Wersja 13.0 - ...)", np. ``"13.0"``.
    """
    if not os.path.exists(SCIEZKA_INSTRUKCJA):
        raise RuntimeError(
            f"Nie znaleziono {SCIEZKA_INSTRUKCJA}. "
            "Uruchom skrypt z katalogu głównego projektu."
        )
    with open(SCIEZKA_INSTRUKCJA, "r", encoding="utf-8") as fh:
        pierwsza_linia = fh.readline()
    dopasowanie = WZORZEC_WERSJA_TXT.search(pierwsza_linia)
    if not dopasowanie:
        raise RuntimeError(
            f"Nie znaleziono fragmentu 'Wersja X.Y' w pierwszej linii "
            f"{SCIEZKA_INSTRUKCJA}.\nObecna pierwsza linia:\n  {pierwsza_linia!r}"
        )
    return dopasowanie.group(1)


def wykryj_i_zweryfikuj_wersje() -> str:
    """Cross-checkuje wersję main.py vs. instrukcja.txt i zwraca numer.

    Oba źródła muszą zwrócić IDENTYCZNY numer. Niezgodność = błąd krytyczny
    ze wskazaniem, który plik zaktualizować. Ta jedna bramka w całości
    eliminuje ryzyko wydania paczki z błędną/niezsynchronizowaną wersją.
    """
    try:
        wersja_py  = odczytaj_wersje_z_main_py()
        wersja_txt = odczytaj_wersje_z_instrukcji()
    except RuntimeError as exc:
        print(f"❌ BŁĄD KRYTYCZNY (odczyt wersji): {exc}")
        sys.exit(1)

    if wersja_py != wersja_txt:
        print("❌ BŁĄD KRYTYCZNY: Niezsynchronizowane numery wersji.")
        print(f"   • {SCIEZKA_MAIN_PY} (MainFrame.VERSION) → {wersja_py!r}")
        print(f"   • {SCIEZKA_INSTRUKCJA} (1. linia)       → {wersja_txt!r}")
        print()
        print("Zaktualizuj OBA pliki przed zbudowaniem wydania.")
        print(
            "Aktualizacja tylko jednego z nich prowadzi do niespójności "
            "(user widzi w tytule okna inną wersję niż czyta w instrukcji)."
        )
        sys.exit(1)

    return wersja_py


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
        print(f"  (a) Przenumeruj wersję w {SCIEZKA_MAIN_PY} i {SCIEZKA_INSTRUKCJA}.")
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
    czesci_sciezki = sciezka.replace('\\', '/').split('/')
    if any(ignorowany in czesci_sciezki for ignorowany in IGNOROWANE_FOLDERY):
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
#   1. Funkcje walidacji wersji (odczytaj_wersje_z_main_py itp.) można
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

    # 3. Automatyczne wykrycie wersji (cross-check main.py ↔ instrukcja.txt)
    print("🔍 Wykrywanie numeru wersji (cross-check main.py ↔ instrukcja.txt)...")
    wersja = wykryj_i_zweryfikuj_wersje()
    print(f"✅ Wersja zweryfikowana w obu źródłach: {wersja}\n")

    nazwa_zip = f"Rezyser_Audio_v{wersja}_Portable.zip"

    # 4. Blokada nadpisywania poprzedniego releasu
    sprawdz_czy_zip_juz_istnieje(nazwa_zip)

    # 5. Ostatnie potwierdzenie dewelopera przed kompresją
    odp = input(f"Zbudować paczkę {nazwa_zip}? (t/n): ").strip().lower()
    if odp != "t":
        print("Anulowano budowanie wydania.")
        sys.exit(0)

    # 6. Budowanie wersji Portable (ZIP)
    print(f"\n[1/2] Pakowanie wersji Portable: {nazwa_zip}...")
    with zipfile.ZipFile(nazwa_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(KATALOG_ZRODLOWY):
            dirs[:] = [d for d in dirs if d not in IGNOROWANE_FOLDERY]
            for file in files:
                if not czy_ignorowac(root, file):
                    pelna_sciezka = os.path.join(root, file)
                    sciezka_w_zip = os.path.relpath(pelna_sciezka, KATALOG_ZRODLOWY)
                    zipf.write(pelna_sciezka, sciezka_w_zip)
    print("✅ Gotowe!")

    # 7. Budowanie wersji Instalacyjnej (EXE)
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


