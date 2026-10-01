; Inno Setup script for the Doctor Prospector Windows installer.
; Built by desktop\build.ps1, which passes AppVersion and the paths below.

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\DoctorProspector"
#endif
#ifndef OutputDir
  #define OutputDir "..\dist\installer"
#endif

#define AppName "Doctor Prospector"
#define AppExe "DoctorProspector.exe"

[Setup]
; Fixed id so upgrades replace the previous version. Never change it.
AppId={{6B8E2F4A-3D1C-4E7B-9A55-2C9D8E1F0A64}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Wolf (github.com/wolfcatalyst)
AppPublisherURL=https://github.com/wolfcatalyst/doctor-prospector
; Per-user install: no admin prompt. Users may still choose all-users.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#OutputDir}
OutputBaseFilename=DoctorProspector-Setup-{#AppVersion}
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#AppExe}
LicenseFile=..\LICENSE
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
#ifdef SIGN
; build.ps1 -SignCommand passes /Scustom=... ; signs setup + uninstaller
SignTool=custom
SignedUninstaller=yes
#endif

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Refresh Doctor Prospector data"; Filename: "{app}\{#AppExe}"; Parameters: "--refresh"; Comment: "Download the latest public data (takes a while)"
Name: "{group}\Open Doctor Prospector data folder"; Filename: "{app}\{#AppExe}"; Parameters: "--data-folder"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

[Code]
// The app's window uses Microsoft Edge WebView2, built into Windows 11 and
// current Windows 10. Warn (don't block) if it's missing.
function WebView2Installed(): Boolean;
var
  Version: String;
begin
  Result :=
    RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) or
    RegQueryStringValue(HKCU, 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version);
  Result := Result and (Version <> '') and (Version <> '0.0.0.0');
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssPostInstall) and not WebView2Installed() then
    MsgBox('Doctor Prospector needs the Microsoft Edge WebView2 Runtime, which is missing on this PC.' + #13#10 + #13#10 +
           'Download it (free) from: https://developer.microsoft.com/microsoft-edge/webview2/', mbInformation, MB_OK);
end;

// Ask before deleting the user's data (database, settings, exports).
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{localappdata}\DoctorProspector');
    if DirExists(DataDir) then
      if MsgBox('Also delete your Doctor Prospector data (database, settings, exports)?' + #13#10 + #13#10 + DataDir,
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(DataDir, True, True, True);
  end;
end;
