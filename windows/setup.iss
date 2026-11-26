[Setup]
AppId={{EE956D7B-A46C-4A4F-9C17-2204078F1E26}
AppName=Hub
AppPublisher=devrin
AppPublisherURL=https://github.com/200ProNt/hub
AppVersion={#HubVersion}
VersionInfoVersion={#HubVersion}
VersionInfoTextVersion={#HubVersion}
VersionInfoProductTextVersion={#HubVersion}
DefaultDirName={localappdata}\Hub\App
DisableProgramGroupPage=yes
AllowNoIcons=yes
PrivilegesRequired=lowest
MinVersion=10.0.22000
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#HubIconName}
SetupIconFile={#HubIcon}
OutputBaseFilename=Hub-Setup-Windows-x64
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
RestartApplications=no

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"
Name: "migrate"; Description: "Перенести данные из браузерной версии Hub"; Flags: unchecked; Check: CanMigrate

[Files]
Source: "{#HubExe}"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#HubIcon}"; DestDir: "{app}"; DestName: "{#HubIconName}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\Hub"; Filename: "{app}\Hub.exe"; WorkingDir: "{app}"; IconFilename: "{app}\{#HubIconName}"
Name: "{autodesktop}\Hub"; Filename: "{app}\Hub.exe"; WorkingDir: "{app}"; IconFilename: "{app}\{#HubIconName}"; Tasks: desktopicon

[Run]
Filename: "{app}\Hub.exe"; WorkingDir: "{app}"; Description: "Запустить Hub"; Flags: nowait postinstall skipifsilent; Check: CanLaunch

[Code]
const
  SHCNE_UPDATEITEM = $00002000;
  SHCNF_PATHW = $0005;

var
  MigrationPage: TInputDirWizardPage;
  MigrationFailed: Boolean;

procedure SHChangeNotify(EventId, Flags: Integer; Item: string; OtherItem: Integer);
  external 'SHChangeNotify@shell32.dll stdcall';

procedure RefreshDesktopIcon;
var
  LinkPath: String;
  Shell, Shortcut: Variant;
begin
  LinkPath := ExpandConstant('{autodesktop}\Hub.lnk');
  if not FileExists(LinkPath) then
    Exit;
  if not WizardIsTaskSelected('desktopicon') then begin
    try
      Shell := CreateOleObject('WScript.Shell');
      Shortcut := Shell.CreateShortcut(LinkPath);
      if CompareText(Shortcut.TargetPath, ExpandConstant('{app}\Hub.exe')) <> 0 then
        Exit;
      Shortcut.IconLocation := ExpandConstant('{app}\{#HubIconName},0');
      Shortcut.Save;
    except
      Log('Could not refresh Hub desktop shortcut: ' + GetExceptionMessage);
      Exit;
    end;
  end;
  SHChangeNotify(SHCNE_UPDATEITEM, SHCNF_PATHW, LinkPath, 0);
end;

function CanMigrate: Boolean;
begin
  Result := not DirExists(ExpandConstant('{localappdata}\Hub\data'));
end;

function CanLaunch: Boolean;
begin
  Result := not MigrationFailed;
end;

procedure InitializeWizard;
begin
  MigrationPage := CreateInputDirPage(wpSelectTasks, 'Перенос данных',
    'Выбери папку прежнего Hub',
    'Сначала закрой старый Hub через трей или окно консоли. Выбери папку, в которой находятся server.py и data.',
    False, '');
  MigrationPage.Add('Папка старого Hub');
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := (PageID = MigrationPage.ID) and not WizardIsTaskSelected('migrate');
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Source: String;
begin
  Result := True;
  if CurPageID = MigrationPage.ID then begin
    Source := AddBackslash(MigrationPage.Values[0]);
    Result := FileExists(Source + 'server.py') and DirExists(Source + 'data');
    if not Result then
      MsgBox('В этой папке должны быть server.py и data.', mbError, MB_OK);
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ExitCode: Integer;
begin
  if CurStep <> ssPostInstall then
    Exit;
  SHChangeNotify(SHCNE_UPDATEITEM, SHCNF_PATHW, ExpandConstant('{app}\Hub.exe'), 0);
  SHChangeNotify(SHCNE_UPDATEITEM, SHCNF_PATHW, ExpandConstant('{autoprograms}\Hub.lnk'), 0);
  RefreshDesktopIcon;
  if WizardIsTaskSelected('migrate') then begin
    MigrationFailed := not Exec(ExpandConstant('{app}\Hub.exe'),
      '--migrate-only --migrate ' + AddQuotes(RemoveBackslashUnlessRoot(MigrationPage.Values[0])),
      '', SW_HIDE, ewWaitUntilTerminated, ExitCode) or (ExitCode <> 0);
    if MigrationFailed then
      MsgBox('Данные не перенесены. Проверь выбранную папку и повтори установку до первого запуска Hub.', mbError, MB_OK);
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Stored: String;
  RunKey: String;
begin
  RunKey := 'Software\Microsoft\Windows\CurrentVersion\Run';
  if (CurUninstallStep = usUninstall) and RegQueryStringValue(HKCU, RunKey, 'Hub', Stored) then
    if CompareText(Stored, AddQuotes(ExpandConstant('{app}\Hub.exe')) + ' --background') = 0 then
      RegDeleteValue(HKCU, RunKey, 'Hub');
end;
