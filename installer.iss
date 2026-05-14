; Nazwa wyświetlana (może i powinna zawierać polskie znaki)
#define MyAppName "Reżyser Audio GPT"
; Nazwa pliku wykonywalnego (end-user launcher wygenerowany przez
; build_release.py — leży tylko w paczce ZIP/EXE, nie w repo, bo jest
; dynamicznie tworzony dla każdej wersji; `.gitignore` zawiera wpis `run.bat`).
#define MyAppExeName "run.bat"

; UWAGA: Ten plik NIE jest wywoływany bezpośrednio przez iscc — `build_release.py`
; czyta installer.iss i wstrzykuje 3 sekcje dynamicznie (nazwy sekcji
; w komentarzu zapisuję BEZ nawiasów kwadratowych — split() w
; build_release.py szuka literalnego `[Section]` i fałszywie matchuje
; komentarz przed prawdziwą sekcją):
;   * sekcja Languages       — z `zbierz_jezyki_bazowe()` ∩
;                              `zbierz_jezyki_z_manualem()` ∩ `INNO_LANG_MAP`
;                              (kody z `dictionaries/<kod>/podstawy.yaml`
;                              które mają `docs/manual.<iso>.txt` i oficjalny
;                              `.isl` w pakiecie Inno Setup); aktualnie 8 jzk
;                              (en/pl/de/es/fi/fr/it/ru), is pomijany z warningiem.
;   * sekcja Code            — `function GetManualISO()` z case'ami
;                              `ActiveLanguage() → ISO`, generowanymi
;                              z `buduj_blok_kodu_iso(wpisy)`.
;   * sekcja CustomMessages  — etykiety AdditionalActionsGroup/
;                              OpenManualTaskDesc/OpenManualRunDesc per jzk,
;                              z mapy `INNO_MANUAL_MESSAGES_MAP` w build_release.py.
;
; Wynik leci do tmp `_installer_tmp.iss` i dopiero przekazywany do `iscc`.
; Sekcje poniżej to MINIMALNE PLACEHOLDERY (tylko `english`) — żeby
; `iscc installer.iss` uruchomiony bezpośrednio (sanity check developera)
; nie zawodził z `Unknown language name "german"` itd. Dodanie języka =
; (a) wpis w INNO_LANG_MAP, (b) wpis w INNO_MANUAL_MESSAGES_MAP,
; (c) `dictionaries/<kod>/gui/dokumentacja/manual.yaml`. installer.iss nie
; wymaga zmian.
[Languages]
Name: "english";  MessagesFile: "compiler:Default.isl"

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
Source: "*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: ".git\*,.github\*,.vscode\*,.cline\*,.claude\*,__pycache__\*,skrypty\*,runtime\__pycache__\*,runtime\skrypty\*,runtime\opowiesci\*,venv\*,.venv\*,env\*,notatki_dev\*,*.env,*.pyc,*.md,*.iss,*.sh,*.jsonl,Rezyser_Audio_*.zip,Rezyser_Audio_*.exe,build_release.py,buduj_wielojezyczne_docs.py,buduj_wielojezyczne_ui.py,requirements.txt,.clinerules,.gitignore,setup_dev.bat,run_dev.bat,dictionaries\*\gui\dokumentacja\*"

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
; v15.2: checkbox „Otwórz instrukcję obsługi po instalacji" — domyślnie zaznaczony.
; ISO języka instrukcji wyliczany dynamicznie z ActiveLanguage() przez funkcję
; GetManualISO() w sekcji Code (patrz niżej). Fallback do EN dla języków
; instalatora bez własnego docs/manual.<iso>.txt (np. instalator po angielsku
; → manual.en.txt).
Name: "openmanual"; Description: "{cm:OpenManualTaskDesc}"; GroupDescription: "{cm:AdditionalActionsGroup}"

[Run]
; Otwarcie instrukcji obsługi przez domyślny handler Windows (.txt → Notatnik
; lub VS Code, zależnie od skojarzenia). Flagi:
;   shellexec     — używa ShellExecute, czyli respektuje skojarzenia użytkownika
;   postinstall   — pokazuje na stronie „Finish" jako checkbox (już zaznaczony,
;                   bo task ma domyślnie selected)
;   skipifsilent  — w trybie /SILENT instalator nie próbuje otworzyć manuala
; Plik wskazywany jest przez {code:GetManualISO} — funkcja zwraca kod ISO
; pasujący do języka instalatora. Folder docs\ leży w paczce (NIE jest
; w Excludes w [Files]).
Filename: "{app}\docs\manual.{code:GetManualISO}.txt"; Description: "{cm:OpenManualRunDesc}"; Flags: shellexec postinstall skipifsilent; Tasks: openmanual

; UWAGA: Sekcje Code (GetManualISO) i CustomMessages poniżej są placeholderami
; nadpisywanymi przez `build_release.py` dynamicznie (nazwy sekcji w komentarzu
; BEZ nawiasów kwadratowych — split() szuka literalnie):
;   * sekcja Code body — generowany z `buduj_blok_kodu_iso(wpisy, kody_z_manualem)`,
;     mapuje `ActiveLanguage() → kod_iso` dla każdego jzk z Inno-supported listy,
;     który MA `docs/manual.<iso>.txt`. Reszta → fallback en.
;   * sekcja CustomMessages — generowana z `buduj_blok_custom_messages(wpisy)`,
;     iteruje po `INNO_MANUAL_MESSAGES_MAP` (3 etykiety × N jzk).
;
; Po co stub: (a) `iscc installer.iss` bezpośrednio (poza pipelineem
; build_release.py) musi się skompilować bez błędów składniowych — bo iscc
; parsuje Pascal w sekcji Code i sprawdza CustomMessages cross-reference ze
; sekcją Languages; (b) developer otwierający installer.iss w repo widzi
; minimal-but-valid stan funkcjonalny dla EN (jedynego jzk w placeholder
; Languages obecny u góry).
[Code]
function GetManualISO(Param: String): String;
begin
  Result := 'en';
end;

[CustomMessages]
english.AdditionalActionsGroup=Additional actions:
english.OpenManualTaskDesc=Open the user manual after installation
english.OpenManualRunDesc=Open user manual
