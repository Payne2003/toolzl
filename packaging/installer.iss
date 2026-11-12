; Inno Setup — tạo bộ cài ZaloMarketing-Setup-<version>.exe
; Build: iscc /DAppVersion=1.0.0 packaging\installer.iss   (sau khi chạy PyInstaller)

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{8F1C2B5E-6A7D-4E3B-9C21-5D0B7A1E4F33}
AppName=Zalo Marketing - Group Posting
AppVersion={#AppVersion}
AppPublisher=Zalo Marketing
DefaultDirName={autopf}\ZaloMarketing
DefaultGroupName=Zalo Marketing
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist
OutputBaseFilename=ZaloMarketing-Setup-{#AppVersion}
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\ZaloMarketing.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\ZaloMarketing\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Zalo Marketing"; Filename: "{app}\ZaloMarketing.exe"
Name: "{autodesktop}\Zalo Marketing"; Filename: "{app}\ZaloMarketing.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\ZaloMarketing.exe"; Description: "{cm:LaunchProgram,Zalo Marketing}"; Flags: nowait postinstall skipifsilent
