; Nazwa wyświetlana (może i powinna zawierać polskie znaki)
#define MyAppName "Reżyser Audio GPT"
; Nazwa pliku wykonywalnego (bezpieczna, bez polskich znaków)
#define MyAppExeName "Uruchom_Rezysera.bat"

[Setup]
AppId={{12345678-ABCD-1234-ABCD-1234567890AB}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
OutputBaseFilename=Rezyser_Audio_v{#MyAppVersion}_Installer
Compression=lzma
SolidCompression=yes
PrivilegesRequired=lowest
OutputDir=.

[Files]
; Excludes: dictionaries\*\gui\dokumentacja\* — surowce developerskie
; dokumentacji end-userowej (szablony YAML z placeholderami {app.wersja}).
; Inno Setup dopasowuje wzorce do ścieżki względnej od Source, wspiera `*`
; jako wildcard (nie `**`). Gwiazdka po `dictionaries\` pokrywa kod języka
; (pl, en, ru, …) — wzorzec działa automatycznie dla przyszłych języków.
; End-user dostaje już wygenerowane pliki z folderu docs\ (docs\manual.pl.txt,
; docs\dictionaries.pl.txt), nie surowy YAML. Analogiczne wykluczenie żyje
; w buduj_wydanie.py::czy_ignorowac() — żeby paczka Portable ZIP i instalator
; EXE były spójne pod względem zawartości.
Source: "*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: ".git\*,.vscode\*,.cline\*,__pycache__\*,skrypty\*,runtime\__pycache__\*,runtime\skrypty\*,venv\*,.venv\*,env\*,*.env,*.pyc,*.md,*.iss,*.sh,*.jsonl,Rezyser_Audio_*.zip,Rezyser_Audio_*.exe,buduj_wydanie.py,requirements.txt,.clinerules,.gitignore,skonfiguruj_dev.bat,uruchom_rezysera_dev.bat,dictionaries\*\gui\dokumentacja\*"

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Utworz skrot na pulpicie"; GroupDescription: "Dodatkowe ikony:"