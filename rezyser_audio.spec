# -*- mode: python ; coding: utf-8 -*-
"""rezyser_audio.spec — konfiguracja PyInstaller dla Reżysera Audio GPT.

Tryb: onedir + windowed (bez konsoli systemowej). Cel migracji (od v17.0):
end-user przestaje widzieć kilkanaście luźnych skryptów ``.py`` z polskimi
nazwami obok aplikacji — wszystko ląduje w jednym, „onieśmielającym" folderze
bundla.

KLUCZOWE DECYZJE:
  * ``contents_directory='runtime'`` (COLLECT) — folder PyInstallera z
    interpreterem i bibliotekami nazywa się ``runtime/`` zamiast domyślnego
    ``_internal/``. Dzięki temu (a) zachowuje „systemową/onieśmielającą" naturę
    dawnego ``runtime/python.exe`` (ciekawski user go nie rusza), (b) metadane
    projektów (``runtime/skrypty/*.mode``, ``.brainstorm.json`` itd.) lądują
    OBOK interpretera, dokładnie jak przed migracją — ``core_rezyser.RUNTIME_DIR``
    łączone z katalogiem exe daje ``<install>/runtime/...``, czyli wnętrze tego
    samego folderu bundla. Wymaga PyInstaller >= 6.0.
  * ``dictionaries/`` i ``docs/`` NIE są pakowane do bundla (brak w ``datas``) —
    to seed-data edytowalna przez Manager Reguł; shipuje je instalator Inno OBOK
    exe (Opcja A), żeby rebuild PyInstallera nie kasował edycji użytkownika i żeby
    kod czytał je z katalogu exe (patrz ``sciezki.KATALOG_BAZOWY``).
  * ``golden_key.env`` to user-data — nie pakujemy go nigdzie (gitignored).

Pakiety z dynamicznymi importami / danymi (Lingua = modele językowe, num2words =
lokale, tiktoken = pluginy ``tiktoken_ext`` + dane BPE, python-docx = szablon
``.docx``) zbieramy jawnie przez helpery hooków — inaczej build by się skompilował,
ale runtime wywaliłby się na ``ModuleNotFoundError`` / braku danych.
"""

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

datas = []
binaries = []
hiddenimports = []

# VERSION — pojedyncze źródło prawdy numeru wersji. To KOD/seed, NIE user-data:
# pakujemy go DO bundla (ląduje w `sys._MEIPASS` = folder `runtime/`), a nie
# luzem obok exe. Runtime czyta go przez `sciezki.KATALOG_ZASOBOW`. Inaczej niż
# `dictionaries/`+`docs/` (edytowalne przez Manager Reguł → shipowane obok exe),
# VERSION nikt nie edytuje, a leżąc luzem bez rozszerzenia kusiłby do otwarcia
# (systemowy file-picker). `(".")` = korzeń bundla.
datas += [("VERSION", ".")]

# collect_all = (datas, binaries, hiddenimports) — komplet dla pakietów, które
# PyInstaller analizuje niepoprawnie z powodu importów dynamicznych / danych.
for _pakiet in ("lingua", "num2words", "tiktoken"):
    _d, _b, _h = collect_all(_pakiet)
    datas += _d
    binaries += _b
    hiddenimports += _h

# python-docx trzyma domyślny szablon .docx jako dane pakietu.
datas += collect_data_files("docx")

# tiktoken ładuje enkodery jako pluginy z namespace tiktoken_ext (entry-points).
hiddenimports += collect_submodules("tiktoken_ext")

# elevenlabs (od v17.1): SDK Fern-generated; namespace'y `studio`/`user` ładujemy
# lazy-importem w core_elevenlabs (`from elevenlabs.client import ElevenLabs`),
# więc dla pewności zbieramy WSZYSTKIE submoduły — inaczej frozen build mógłby
# wywalić się na ModuleNotFoundError przy budowie projektu Studio. SDK to czysty
# kod (httpx+pydantic, brak data-plików), więc collect_submodules wystarcza
# (lżejsze od collect_all). openai analizuje się statycznie i collect nie wymaga.
hiddenimports += collect_submodules("elevenlabs")

block_cipher = None

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # tkinter i narzędzia dev/test nie są potrzebne w paczce end-usera — wycinamy,
    # żeby nie puchł bundle ani nie ciągnąć Tcl/Tk.
    excludes=["tkinter", "pytest", "PyInstaller"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Rezyser Audio GPT",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,             # --windowed: brak konsoli systemowej
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # _internal → runtime. UWAGA: w PyInstaller 6.x `contents_directory` to
    # parametr EXE (bootloader zapisuje go w nagłówku, COLLECT odczytuje z EXE),
    # NIE parametr COLLECT. Interpreter + biblioteki + metadane projektów żyją
    # razem w „onieśmielającym" folderze runtime/ obok exe.
    contents_directory="runtime",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Rezyser Audio GPT",          # folder pod dist/
)
