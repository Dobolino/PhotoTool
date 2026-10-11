#ifndef AppVersion
  #define AppVersion "0.2.0"
#endif

[Setup]
AppId={{E8FBC36D-0C09-4B0B-BD60-0916B31EBEA3}
AppName=PhotoTool
AppVersion={#AppVersion}
AppPublisher=Dobolino
AppPublisherURL=https://github.com/Dobolino/PhotoTool
DefaultDirName={localappdata}\Programs\PhotoTool
DefaultGroupName=PhotoTool
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=PhotoTool-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
UninstallDisplayIcon={app}\Fotobuch.exe

[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "..\dist\Fotobuch\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\PhotoTool"; Filename: "{app}\Fotobuch.exe"

[Run]
Filename: "{app}\Fotobuch.exe"; Description: "PhotoTool"; Flags: nowait runasoriginaluser
