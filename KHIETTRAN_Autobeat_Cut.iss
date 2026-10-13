#define MyAppName "KHIETTRAN Autobeat Cut"
#define MyAppVersion "3.2.0"
#define MyAppPublisher "KHIETTRAN"
#define MyExeName "KHIETTRAN Autobeat Cut.exe"

[Setup]
AppId={{A1B53C82-7C4E-4B21-9E9A-6F3A8D7D3B11}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\KHIETTRAN Autobeat Cut
DefaultGroupName={#MyAppName}
OutputDir=installer_output
OutputBaseFilename=KHIETTRAN_Autobeat_Cut_Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=admin

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "dist\KHIETTRAN Autobeat Cut\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyExeName}"; Description: "Launch {#MyAppName}"; Flags: postinstall nowait skipifsilent
