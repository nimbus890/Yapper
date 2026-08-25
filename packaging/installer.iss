#define ProjectRoot SourcePath + ".."
#define AppVersion "4.0.0"

[Setup]
AppId={{D58D1264-C7BB-49E0-A9C0-A0789C02E51A}
AppName=yapper_
AppVersion={#AppVersion}
AppPublisher=Nimbus
VersionInfoCompany=Nimbus
VersionInfoDescription=yapper_ Windows installer
VersionInfoVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\Yapper
DefaultGroupName=yapper_
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
OutputDir={#ProjectRoot}\release
OutputBaseFilename=Yapper-{#AppVersion}-Setup
LicenseFile={#ProjectRoot}\LICENSE
InfoBeforeFile={#ProjectRoot}\docs\INSTALLER_TERMS.md
UninstallDisplayIcon={app}\Yapper.exe
SetupIconFile={#ProjectRoot}\assets\app.ico

[Files]
Source: "{#ProjectRoot}\dist\Yapper\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#ProjectRoot}\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#ProjectRoot}\THIRD_PARTY_NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#ProjectRoot}\docs\PRIVACY.md"; DestDir: "{app}\docs"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\yapper_"; Filename: "{app}\Yapper.exe"
Name: "{autodesktop}\yapper_"; Filename: "{app}\Yapper.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Run]
Filename: "{app}\Yapper.exe"; Description: "Launch yapper_"; Flags: nowait postinstall skipifsilent
