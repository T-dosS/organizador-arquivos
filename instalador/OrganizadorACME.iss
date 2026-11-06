; Instalador do Organizador de Arquivos ACME (Inno Setup 6).
; Instala por usuário, sem administrador, em %LOCALAPPDATA%\Programs\OrganizadorACME.
; Gerado por gerar_instalador.ps1, que passa /DAppVersion=x.y.z.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6E3B2C1A-4F7D-4B8E-9A21-0D5C7E8F1A30}
AppName=Organizador de Arquivos ACME
AppVersion={#AppVersion}
AppVerName=Organizador de Arquivos ACME {#AppVersion}
AppPublisher=Acme Corp
DefaultDirName={localappdata}\Programs\OrganizadorACME
DefaultGroupName=ACME
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\instalador\saida
OutputBaseFilename=Instalar_OrganizadorACME_{#AppVersion}
SetupIconFile=..\recursos\icone.ico
UninstallDisplayIcon={app}\OrganizadorACME.exe
UninstallDisplayName=Organizador de Arquivos ACME
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes

[Languages]
Name: "ptbr"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na Área de Trabalho"; GroupDescription: "Atalhos:"

[Files]
Source: "..\programa\OrganizadorACME\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\ACME\Organizador de Arquivos ACME"; Filename: "{app}\OrganizadorACME.exe"
Name: "{userdesktop}\Organizador de Arquivos ACME"; Filename: "{app}\OrganizadorACME.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\OrganizadorACME.exe"; Description: "Abrir o Organizador agora"; Flags: nowait postinstall skipifsilent

; O histórico (%LOCALAPPDATA%\organizador_acme) não é apagado na desinstalação: ele registra onde cada arquivo foi parar.
