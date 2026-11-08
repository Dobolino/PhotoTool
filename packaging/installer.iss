#ifndef AppVersion
  #define AppVersion "0.5.0"
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
; Prepared from Microsoft's official endpoint and Authenticode-verified by CI.
; It only downloads/installs the free runtime when no usable runtime is present.
Source: "..\dist\prerequisites\MicrosoftEdgeWebview2Setup.exe"; Flags: dontcopy

[Icons]
Name: "{group}\PhotoTool"; Filename: "{app}\Fotobuch.exe"

[Run]
Filename: "{app}\Fotobuch.exe"; Description: "PhotoTool"; Flags: nowait runasoriginaluser

[CustomMessages]
german.WebViewRuntimeFailed=Microsoft Edge WebView2 konnte nicht eingerichtet werden. Bitte die Internetverbindung prüfen und die Installation erneut starten. PhotoTool benötigt diese kostenlose Microsoft-Laufzeit für die neue Fotoansicht.
english.WebViewRuntimeFailed=Microsoft Edge WebView2 could not be installed. Check the internet connection and run setup again. PhotoTool needs this free Microsoft runtime for the new photo view.

[Code]
const
  WebView2ClientKey = 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';
var
  WebViewBootstrapAttempted: Boolean;

function HasWebView2AtRoot(RootKey: Integer): Boolean;
var
  Version: String;
begin
  Result := RegQueryStringValue(RootKey, WebView2ClientKey, 'pv', Version) and
    (Version <> '') and (Version <> '0.0.0.0');
end;

function HasWebView2Runtime: Boolean;
begin
  Result := HasWebView2AtRoot(HKCU32) or HasWebView2AtRoot(HKCU64) or
    HasWebView2AtRoot(HKLM32) or HasWebView2AtRoot(HKLM64);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ExitCode: Integer;
begin
  Result := '';
  if HasWebView2Runtime then Exit;
  if WebViewBootstrapAttempted then begin
    Result := ExpandConstant('{cm:WebViewRuntimeFailed}');
    Exit;
  end;
  WebViewBootstrapAttempted := True;
  ExtractTemporaryFile('MicrosoftEdgeWebview2Setup.exe');
  if not Exec(ExpandConstant('{tmp}\MicrosoftEdgeWebview2Setup.exe'), '/silent /install',
      '', SW_HIDE, ewWaitUntilTerminated, ExitCode) then begin
    Result := ExpandConstant('{cm:WebViewRuntimeFailed}');
    Exit;
  end;
  if ExitCode = 3010 then NeedsRestart := True;
  if not HasWebView2Runtime then Result := ExpandConstant('{cm:WebViewRuntimeFailed}');
end;
