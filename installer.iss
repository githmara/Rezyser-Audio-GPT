; Nazwa wyświetlana (może i powinna zawierać polskie znaki)
#define MyAppName "Reżyser Audio GPT"
; Nazwa pliku wykonywalnego (end-user launcher wygenerowany przez
; build_release.py — leży tylko w paczce ZIP/EXE, nie w repo, bo jest
; dynamicznie tworzony dla każdej wersji; `.gitignore` zawiera wpis `run.bat`).
#define MyAppExeName "run.bat"

[Languages]
Name: "english";  MessagesFile: "compiler:Default.isl"
Name: "polish";   MessagesFile: "compiler:Languages\Polish.isl"
Name: "italian";  MessagesFile: "compiler:Languages\Italian.isl"
Name: "russian";  MessagesFile: "compiler:Languages\Russian.isl"
Name: "finnish";  MessagesFile: "compiler:Languages\Finnish.isl"
Name: "icelandic"; MessagesFile: "compiler:Languages\Icelandic.isl"

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
; w build_release.py::czy_ignorowac() — żeby paczka Portable ZIP i instalator
; EXE były spójne pod względem zawartości.
;
; Skrypty deweloperskie (setup_dev.bat/sh, run_dev.bat) są wyłączane z paczki
; dla end-userów — w paczce leży tylko `run.bat` (launcher wskazujący na
; `runtime\python.exe`). Nazwy zostały zangielszczone w wersji 13.1, stare
; polskie nazwy (`skonfiguruj_dev.bat`, `uruchom_rezysera_dev.bat`,
; `skonfiguruj_dev.sh`, `uruchom_rezysera.sh`) przestały istnieć w repo.
Source: "*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: ".git\*,.vscode\*,.cline\*,.claude\*,__pycache__\*,skrypty\*,runtime\__pycache__\*,runtime\skrypty\*,venv\*,.venv\*,env\*,*.env,*.pyc,*.md,*.iss,*.sh,*.jsonl,Rezyser_Audio_*.zip,Rezyser_Audio_*.exe,build_release.py,buduj_wielojezyczne_docs.py,buduj_wielojezyczne_ui.py,requirements.txt,.clinerules,.gitignore,setup_dev.bat,run_dev.bat,dictionaries\*\gui\dokumentacja\*"

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
