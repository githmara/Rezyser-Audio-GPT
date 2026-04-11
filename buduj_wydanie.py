import os
import zipfile
import subprocess
import sys

# --- STRAŻNIK (GUARD CLAUSE) ---
if not os.path.exists("runtime") or not os.path.exists(os.path.join("runtime", "python.exe")):
    print("❌ BŁĄD KRYTYCZNY: Nie znaleziono folderu 'runtime/' z lokalnym środowiskiem Pythona!")
    print("Repozytorium Git nie zawiera bibliotek uruchomieniowych.")
    print("Zanim zbudujesz wydanie, musisz umieścić przenośnego Pythona w folderze 'runtime'.")
    sys.exit(1)

# 1. Pobieranie danych wejściowych
wersja = input("Podaj numer wersji do zbudowania (np. 10.1): ").strip()
nazwa_zip = f"Rezyser_Audio_v{wersja}_Portable.zip"
KATALOG_ZRODLOWY = "."

# 2. Definiowanie wykluczeń
IGNOROWANE_FOLDERY = {'.git', '.vscode', '.cline', '__pycache__', 'skrypty', 'venv', '.venv', 'env'}
IGNOROWANE_PLIKI = {'.clinerules', 'requirements.txt', '.gitignore', 'buduj_wydanie.py', 'skrypt_instalatora.iss', 'golden_key.env', 'skonfiguruj_dev.bat', 'uruchom_rezysera_dev.bat'}
IGNOROWANE_ROZSZERZENIA = {'.env', '.pyc', '.md', '.sh', '.jsonl'}

def czy_ignorowac(sciezka, nazwa_pliku):
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

# 3. Budowanie wersji Portable (ZIP)
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

# 4. Budowanie wersji Instalacyjnej (EXE)
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