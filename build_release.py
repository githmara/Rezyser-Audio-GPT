import os
import shutil
import zipfile
import subprocess
import sys
from pathlib import Path

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

# Mapowanie kodów ISO języków na wpisy Inno Setupa (nazwa + plik .isl).
#
# UWAGA: Ta mapa to lustro listy języków OFICJALNIE shippowanych z Inno Setup 6
# (29 paczek w `compiler:Languages\\` + angielski w `compiler:Default.isl`),
# nie listy języków naszego projektu. Pliki .isl należą do instalacji Inno
# Setupa, więc ich nazwy są stałe niezależnie od tego, które języki ma
# `dictionaries/`. Wniosek praktyczny: dodanie nowego języka bazowego do
# `dictionaries/<kod>/` NIE wymaga edycji tej mapy, dopóki ten język ma
# oficjalną paczkę Inno Setupa. Mapa jest pre-populowana, więc fr/es/de/ja/ko/...
# działają out-of-the-box.
#
# Świadomie pomijamy paczki NIEOFICJALNE z https://jrsoftware.org/files/istrans/
# (np. Icelandic, Esperanto, Estonian, SerbianCyrillic, SerbianLatin). Mają różny
# poziom utrzymania (Icelandic ostatni update 2020), więc deweloperzy musieliby
# je doinstalowywać ręcznie — a to przeczy idei "działa po świeżej instalacji
# Inno Setupa". Jeśli kiedyś potrzebny będzie nieoficjalny język, dopisać go tu
# z komentarzem "[unofficial]" i zadbać o instrukcję pobrania w docs.
#
# Fallback "skip with warning" obsługuje dwa scenariusze:
#   1. Język spoza puli Inno Setupa (np. esperanto bez ręcznej paczki) — kod
#      nieobecny w mapie.
#   2. Plik .isl jest w mapie, ale nie istnieje w instalacji u dewelopera
#      (bardzo stara wersja Inno Setupa albo własnoręcznie usunięta paczka).
#      Sprawdzane runtime przez `buduj_wpisy_inno` przed przekazaniem do iscc,
#      żeby nie dostać kryptycznego błędu Windows "nie można odnaleźć
#      określonego pliku" z głębi kompilatora.
INNO_LANG_MAP: dict[str, tuple[str, str]] = {
    "en":    ("english",             "compiler:Default.isl"),
    "ar":    ("arabic",              "compiler:Languages\\Arabic.isl"),
    "bg":    ("bulgarian",           "compiler:Languages\\Bulgarian.isl"),
    "ca":    ("catalan",             "compiler:Languages\\Catalan.isl"),
    "co":    ("corsican",            "compiler:Languages\\Corsican.isl"),
    "cs":    ("czech",               "compiler:Languages\\Czech.isl"),
    "da":    ("danish",              "compiler:Languages\\Danish.isl"),
    "de":    ("german",              "compiler:Languages\\German.isl"),
    "es":    ("spanish",             "compiler:Languages\\Spanish.isl"),
    "fi":    ("finnish",             "compiler:Languages\\Finnish.isl"),
    "fr":    ("french",              "compiler:Languages\\French.isl"),
    "he":    ("hebrew",              "compiler:Languages\\Hebrew.isl"),
    "hu":    ("hungarian",           "compiler:Languages\\Hungarian.isl"),
    "hy":    ("armenian",            "compiler:Languages\\Armenian.isl"),
    "it":    ("italian",             "compiler:Languages\\Italian.isl"),
    "ja":    ("japanese",            "compiler:Languages\\Japanese.isl"),
    "ko":    ("korean",              "compiler:Languages\\Korean.isl"),
    "nb":    ("norwegian",           "compiler:Languages\\Norwegian.isl"),
    "nl":    ("dutch",               "compiler:Languages\\Dutch.isl"),
    "pl":    ("polish",              "compiler:Languages\\Polish.isl"),
    "pt":    ("portuguese",          "compiler:Languages\\Portuguese.isl"),
    "pt-br": ("brazilianportuguese", "compiler:Languages\\BrazilianPortuguese.isl"),
    "ru":    ("russian",             "compiler:Languages\\Russian.isl"),
    "sk":    ("slovak",              "compiler:Languages\\Slovak.isl"),
    "sl":    ("slovenian",           "compiler:Languages\\Slovenian.isl"),
    "sv":    ("swedish",             "compiler:Languages\\Swedish.isl"),
    "ta":    ("tamil",               "compiler:Languages\\Tamil.isl"),
    "th":    ("thai",                "compiler:Languages\\Thai.isl"),
    "tr":    ("turkish",             "compiler:Languages\\Turkish.isl"),
    "uk":    ("ukrainian",           "compiler:Languages\\Ukrainian.isl"),
}


def zbierz_jezyki_bazowe() -> list[str]:
    """Zwraca kody języków bazowych z folderu dictionaries/.

    Kryterium: podfolder dictionaries/<kod>/ zawiera plik podstawy.yaml.
    Wynik posortowany alfabetycznie dla determinizmu outputu.
    """
    katalog = Path(__file__).parent / "dictionaries"
    kody = sorted(
        p.parent.name
        for p in katalog.glob("*/podstawy.yaml")
        if p.parent.is_dir()
    )
    return kody


def odczytaj_wersje() -> str:
    """Wczytuje numer wersji z pliku ``VERSION`` w roocie projektu.

    Raises:
        RuntimeError: gdy plik nie istnieje albo jest pusty/białoznakowy.

    Returns:
        Numer wersji bez końcowego whitespace'a, np. ``"13.4-WIP"`` lub ``"13.4"``.
    """
    if not os.path.exists(SCIEZKA_VERSION):
        raise RuntimeError(
            f"VERSION file not found at {SCIEZKA_VERSION}. "
            "Since 13.4 it's the single source of truth for the version number — "
            "make sure the file exists in the repo root."
        )
    try:
        with open(SCIEZKA_VERSION, "r", encoding="utf-8") as fh:
            wartosc = fh.read().strip()
    except OSError as exc:
        raise RuntimeError(f"Failed to read {SCIEZKA_VERSION}: {exc}") from exc

    if not wartosc:
        raise RuntimeError(
            f"{SCIEZKA_VERSION} is empty. Write the version number into it "
            "(e.g. 13.4 or 13.4-WIP)."
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


def buduj_wpisy_inno(kody: list[str], katalog_inno: Path) -> list[tuple[str, str]]:
    """Mapuje kody języków bazowych na wpisy bloku ``[Languages]`` Inno Setupa.

    Pomija języki nieobecne w INNO_LANG_MAP (Inno Setup nie ma oficjalnej
    paczki — np. islandzki, esperanto, estoński; mapa świadomie ich nie
    zawiera, patrz komentarz przy INNO_LANG_MAP) oraz te, których plik ``.isl``
    nie istnieje w lokalnej instalacji (bardzo stara wersja Inno Setupa albo
    własnoręcznie usunięta paczka). Sprawdzanie runtime, żeby zamiast
    kryptycznego błędu Windows o nieznalezionym pliku dostać czytelny
    ``⚠ Skipping language``. Angielski leci pierwszy, żeby Inno Setup wybrał
    go jako fallback default.
    """
    wpisy: list[tuple[str, str]] = []
    kolejnosc = (["en"] if "en" in kody else []) + [k for k in kody if k != "en"]
    for kod in kolejnosc:
        if kod not in INNO_LANG_MAP:
            print(f"   ⚠ Skipping language '{kod}': not supported by Inno Setup.")
            continue
        nazwa, plik = INNO_LANG_MAP[kod]
        relatywna = plik.removeprefix("compiler:").replace("\\", "/")
        if not (katalog_inno / relatywna).exists():
            nazwa_pliku = relatywna.rsplit("/", 1)[-1]
            print(f"   ⚠ Skipping language '{kod}': '{nazwa_pliku}' missing in "
                  f"Inno Setup install ({katalog_inno}).")
            print("     → Update Inno Setup or grab the .isl from "
                  "https://jrsoftware.org/files/istrans/")
            continue
        wpisy.append((nazwa, plik))
    return wpisy



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
    iscc_exe = shutil.which("iscc")
    if iscc_exe is None:
        print("❌ FATAL: 'iscc' not found in PATH.")
        print("Install Inno Setup (https://jrsoftware.org/isinfo.php) and make sure")
        print("its folder (e.g. C:\\Program Files (x86)\\Inno Setup 6) is in your PATH.")
        sys.exit(1)

    # Collect base language codes and map them to Inno Setup .isl entries.
    # `katalog_inno` derives from iscc_exe (it sits in the Inno Setup install
    # root) — we use it to verify each .isl file is actually present before
    # handing the path to the compiler.
    katalog_inno = Path(iscc_exe).parent
    kody = zbierz_jezyki_bazowe()
    wpisy = buduj_wpisy_inno(kody, katalog_inno)

    # Build the [Languages] block.
    blok_languages = "\n".join(
        f'Name: "{nazwa}";  MessagesFile: "{plik}"'
        for nazwa, plik in wpisy
    )

    # Read installer.iss and replace the [Languages] section dynamically.
    sciezka_iss = Path(__file__).parent / "installer.iss"
    sciezka_tmp = Path(__file__).parent / "_installer_tmp.iss"
    iss_tresc = sciezka_iss.read_text(encoding="utf-8")
    # Split around [Languages] … [Setup] to replace only that section.
    przed, reszta = iss_tresc.split("[Languages]", 1)
    _, po_setup = reszta.split("[Setup]", 1)
    nowy_iss = f"{przed}[Languages]\n{blok_languages}\n\n[Setup]{po_setup}"

    print("\n[2/2] Creating the installer...")
    tmp_created = False
    try:
        sciezka_tmp.write_text(nowy_iss, encoding="utf-8")
        tmp_created = True
        subprocess.run(
            [iscc_exe, "/Q", str(sciezka_tmp), f"/DMyAppVersion={wersja}"],
            check=True,
        )
        print(f"✅ Installer created: Rezyser_Audio_v{wersja}_Installer.exe")
    except subprocess.CalledProcessError:
        print("❌ Compilation error. Inno Setup returned a non-zero exit code.")
    finally:
        if tmp_created and sciezka_tmp.exists():
            sciezka_tmp.unlink()



if __name__ == "__main__":
    main()
