; Atyrau Armwrestling — установщик
; Запуск: "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" setup.iss
; (или просто build_installer.bat). Компилируется из build/,
; поэтому все пути ниже относительны к build/.

#define MyAppName "Atyrau Armwrestling"
#define MyAppVersion "1.6.0"
#define MyAppPublisher "Atyrau Armsport"
#define MyAppExeName "AtyrauArmwrestling.exe"

[Setup]
AppId={{F0A3712E-8F7F-4B3C-9C6A-5E2B4D1A8C90}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\Atyrau Armwrestling
DefaultGroupName=Atyrau Armwrestling
; Установка WITHOUT прав администратора: ставится в %LOCALAPPDATA%\Programs
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=.
OutputBaseFilename=AtyrauArmwrestlingSetup
SetupIconFile=AtyrauArmwrestling.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Ярлыки
DisableProgramGroupPage=yes
ArchitecturesInstallIn64BitMode=x64compatible

; Данные приложения лежат в %APPDATA%\AtyrauArmwrestling (см. paths.py),
; поэтому инсталлятор НЕ должен ничего писать в AppData и ничего удалять
; там при деинсталляции.
[Files]
Source: "..\desktop-app\dist\AtyrauArmwrestling.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Дополнительно:"; Flags: unchecked

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Запустить {#MyAppName}"; Flags: nowait postinstall skipifsilent

; Ярлыки удаляются автоматически деинсталлятором. Файл Excel-onefile
; удаляется целиком. Пользовательские данные в AppData сохраняются.
[UninstallDelete]
Type: files; Name: "{app}\{#MyAppExeName}"