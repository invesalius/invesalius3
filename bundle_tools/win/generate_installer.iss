; --------------------------------------------------------------------------
; Software:     InVesalius - Software de Reconstrucao 3D de Imagens Medicas
; Copyright:    (C) 2001  Centro de Pesquisas Renato Archer
; Homepage:     http://www.softwarepublico.gov.br
; Contact:      invesalius@cti.gov.br
; License:      GNU - GPL 2 (LICENSE.txt/LICENCA.txt)
; --------------------------------------------------------------------------
;    Este programa e software livre; voce pode redistribui-lo e/ou
;    modifica-lo sob os termos da Licenca Publica Geral GNU, conforme
;    publicada pela Free Software Foundation; de acordo com a versao 2
;    da Licenca.
;
;    Este programa eh distribuido na expectativa de ser util, mas SEM
;    QUALQUER GARANTIA; sem mesmo a garantia implicita de
;    COMERCIALIZACAO ou de ADEQUACAO A QUALQUER PROPOSITO EM
;    PARTICULAR. Consulte a Licenca Publica Geral GNU para obter mais
;    detalhes.
; --------------------------------------------------------------------------


[Setup]
AppName=InVesalius 3.1
AppVerName=InVesalius 3.1.99998
VersionInfoProductVersion=3.1
VersionInfoVersion=0.0.0.1
AppPublisher=CTI Renato Archer
AppPublisherURL=http://www.cti.gov.br/invesalius
AppSupportURL=http://www.cti.gov.br/invesalius        
AppUpdatesURL=http://www.cti.gov.br/invesalius
AppID={{F768F6BA-F164-4519-BC26-DCCFC2F76833}
AppContact=invesalius@cti.gov.br
AppCopyright=Copyright 2007-2024 - Centro de Tecnologia da Informação Renato Archer
DefaultDirName={pf}\InVesalius 3.1
DefaultGroupName=InVesalius 3.1
OutputDir=..\..\installer\
;OutputBaseFilename=invesalius-3.1.99998-win64
SetupIconFile=..\..\icons\invesalius.ico
Compression=lzma2/ultra64
SolidCompression=true
DisableWelcomePage = No
WizardImageFile=..\..\icons\invesalius_install_wizard.bmp
WizardSmallImageFile=..\..\icons\invesalius_install_wizard_small.bmp

[Languages]
Name: english; MessagesFile: compiler:Default.isl; LicenseFile: "..\\..\LICENSE.txt"
Name: brazilianportuguese; MessagesFile: compiler:Languages\BrazilianPortuguese.isl; LicenseFile: "..\\..\LICENSE.pt.txt"
Name: spanish; MessagesFile: compiler:Languages\Spanish.isl; LicenseFile: "..\\..\LICENSE.txt"

[Tasks]
Name: desktopicon; Description: {cm:CreateDesktopIcon}; GroupDescription: {cm:AdditionalIcons}; Flags: unchecked
;Name: quicklaunchicon; Description: {cm:CreateQuickLaunchIcon}; GroupDescription: {cm:AdditionalIcons}; Flags: unchecked

[Files]
Source: ..\..\dist\app\InVesalius 3.1.exe; DestDir: {app}\dist; Flags: ignoreversion
Source: ..\..\dist\app\*; DestDir: {app}\dist; Flags: ignoreversion recursesubdirs createallsubdirs

;Only the plugin folder should remain in "_internal" after installation.
Source: ..\..\plugins\*; DestDir: {app}\dist\_internal\plugins; Flags: ignoreversion recursesubdirs createallsubdirs

;Source: ..\..\ai\*; DestDir: {app}\dist\ai; Flags: ignoreversion recursesubdirs createallsubdirs
Source: ..\..\locale\*; DestDir: {app}\dist\locale; Flags: ignoreversion recursesubdirs createallsubdirs
Source: ..\..\icons\*; DestDir: {app}\dist\icons; Flags: ignoreversion recursesubdirs createallsubdirs
Source: ..\..\presets\*; DestDir: {app}\dist\presets; Flags: ignoreversion recursesubdirs createallsubdirs
Source: ..\..\docs\user_guide_pt_BR.pdf; DestDir: {app}\dist\docs; Flags: ignoreversion recursesubdirs createallsubdirs
Source: ..\..\docs\user_guide_en.pdf; DestDir: {app}\dist\docs; Flags: ignoreversion recursesubdirs createallsubdirs
Source: ..\..\samples\*; DestDir: {app}\dist\samples; Flags: ignoreversion recursesubdirs createallsubdirs
                                      

;to fix error
;Source: C:\Python37\Lib\site-packages\scipy\extra-dll\*; DestDir: {app}\dist; Flags: ignoreversion recursesubdirs createallsubdirs
;Source: ..\invesalius3\locale\*; DestDir: {app}\dist\locale; Flags: ignoreversion recursesubdirs createallsubdirs
;Source: ..\invesalius3\icons\*; DestDir: {app}\dist\icons; Flags: ignoreversion recursesubdirs createallsubdirs
;Source: ..\invesalius3\presets\*; DestDir: {app}\dist\presets; Flags: ignoreversion recursesubdirs createallsubdirs
;Source: ..\invesalius3\docs\user_guide_pt_BR.pdf; DestDir: {app}\dist\docs; Flags: ignoreversion recursesubdirs createallsubdirs
;Source: ..\invesalius3\docs\user_guide_en.pdf; DestDir: {app}\dist\docs; Flags: ignoreversion recursesubdirs createallsubdirs
;Source: ..\invesalius3\samples\*; DestDir: {app}\dist\samples; Flags: ignoreversion recursesubdirs createallsubdirs

;Source: ..\invesalius3\navigation\mtc_files\CalibrationFiles\*; DestDir: {app}\dist\navigation\mtc_files\CalibrationFiles; Flags: ignoreversion recursesubdirs createallsubdirs
;Source: ..\invesalius3\navigation\mtc_files\Markers\*; DestDir: {app}\dist\navigation\mtc_files\Markers; Flags: ignoreversion recursesubdirs createallsubdirs
;Source: ..\invesalius3\navigation\objects\*; DestDir: {app}\dist\navigation\objects; Flags: ignoreversion recursesubdirs createallsubdirs
;Source: ..\invesalius3\navigation\ndi_files\Markers\*; DestDir: {app}\dist\navigation\ndi_files\Markers; Flags: ignoreversion recursesubdirs createallsubdirs

;Source: .\setup_image\uninstall.ico; DestDir: {app}\dist\icons; Flags: ignoreversion recursesubdirs createallsubdirs


; NOTE: Don't use "Flags: ignoreversion" on any shared system files
Source: install_vc.bat; DestDir: {app}; Flags: deleteafterinstall
Source: vc_redist_2015_2022_x64.exe; DestDir: {app}; Flags: deleteafterinstall
;Source: .\gtk_bundle-2.16-bin\*; DestDir: {sys}; Flags: replacesameversion

[Icons]
Name: {group}\InVesalius 3.1; Filename: {app}\dist\InVesalius 3.1.exe; WorkingDir: {app}\dist; IconFilename: {app}\dist\icons\invesalius.ico
Name: {group}\{cm:ProgramOnTheWeb,InVesalius 3.1}; Filename: http://www.cti.gov.br/invesalius
Name: {group}\{cm:UninstallProgram,InVesalius 3.1}; Filename: {uninstallexe}; IconFilename: {app}\dist\icons\uninstall.ico
Name: {commondesktop}\InVesalius 3.1; Filename: {app}\dist\InVesalius 3.1.exe; WorkingDir: {app}\dist; Tasks: desktopicon; IconFilename: {app}\dist\icons\invesalius.ico
;Name: "{userappdata}\Roaming\Microsoft\Internet Explorer\Quick Launch\InVesalius 3.1"; Filename: "{app}\dist\InVesalius 3.1.exe"; Tasks: quicklaunchicon; WorkingDir: {app}\dist; IconFilename: {app}\dist\InVesalius 3.1.exe; IconIndex: 0
;;;;.; commonstartmenu
[Run]
Filename: {app}\dist\InVesalius 3.1.exe; Description: {cm:LaunchProgram,InVesalius 3.1}; Flags: nowait postinstall skipifsilent

Filename: {app}\install_vc.bat; Flags: runhidden; Tasks: ; Languages: 
[UninstallDelete]
Name: {app}\*; Type: filesandordirs
Name: {app}; Type: dirifempty
[Registry]
Root: HKCR; Subkey: InVesalius 3.1\InstallationDir; ValueType: string; ValueData: {app}
Root: HKCR; Subkey: ".inv3"; ValueType: string; ValueName: ".inv3"; ValueData: "InVesalius 3 Project"; Flags: uninsdeletevalue
Root: HKCR; Subkey: ".inv3\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\dist\icons\inv3_icon.ico,0"
Root: HKCR; Subkey: ".inv3\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\dist\InVesalius 3.1.exe"" ""%1"""

[code]
function GetNumber(var temp: String): Integer;
var
  part: String;
  pos1: Integer;
begin
  if Length(temp) = 0 then
  begin
    Result := -1;
    Exit;
  end;
    pos1 := Pos('.', temp);
    if (pos1 = 0) then
    begin
      Result := StrToInt(temp);
    temp := '';
    end
    else
    begin
    part := Copy(temp, 1, pos1 - 1);
      temp := Copy(temp, pos1 + 1, Length(temp));
      Result := StrToInt(part);
    end;
end;
 
function CompareInner(var temp1, temp2: String): Integer;
var
  num1, num2: Integer;
begin
    num1 := GetNumber(temp1);
  num2 := GetNumber(temp2);
  if (num1 = -1) or (num2 = -1) then
  begin
    Result := 0;
    Exit;
  end;
      if (num1 > num2) then
      begin
        Result := 1;
      end
      else if (num1 < num2) then
      begin
        Result := -1;
      end
      else
      begin
        Result := CompareInner(temp1, temp2);
      end;
end;
 
function CompareVersion(str1, str2: String): Integer;
var
  temp1, temp2: String;
begin
    temp1 := str1;
    temp2 := str2;
    Result := CompareInner(temp1, temp2);
end;

function InitializeSetup(): Boolean;
var
  oldVersion: String;
  uninstaller: String;
  ErrorCode: Integer;
begin
  //InVesalius 3.1
  if RegKeyExists(HKEY_LOCAL_MACHINE,
    'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{F768F6BA-F164-4519-BC26-DCCFC2F76833}_is1') then
      begin
          RegQueryStringValue(HKEY_LOCAL_MACHINE,
            'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{F768F6BA-F164-4519-BC26-DCCFC2F76833}_is1',
            'UninstallString', uninstaller);
          ShellExec('runas', uninstaller, '/SILENT', '', SW_HIDE, ewWaitUntilTerminated, ErrorCode);
          Result := True;
      end;
    
  //InVesalius 3.0 - win64
  if RegKeyExists(HKEY_LOCAL_MACHINE,
    'SOFTWARE\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall\InVesalius 3.0_is1') then
      begin
          RegQueryStringValue(HKEY_LOCAL_MACHINE,
            'SOFTWARE\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall\InVesalius 3.0_is1',
            'UninstallString', uninstaller);
          ShellExec('runas', uninstaller, '/SILENT', '', SW_HIDE, ewWaitUntilTerminated, ErrorCode);
          Result := True;
      end;


  //InVesalius 3.0 Beta 5 - win64
  if RegKeyExists(HKEY_LOCAL_MACHINE,
    'SOFTWARE\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall\InVesalius 3.0 - Beta 5_is1') then
      begin
          RegQueryStringValue(HKEY_LOCAL_MACHINE,
            'SOFTWARE\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall\InVesalius 3.0 - Beta 5_is1',
            'UninstallString', uninstaller);
          ShellExec('runas', uninstaller, '/SILENT', '', SW_HIDE, ewWaitUntilTerminated, ErrorCode);
          Result := True;
      end;

  //InVesalius 3.0 Beta 4 - win64
  if RegKeyExists(HKEY_LOCAL_MACHINE,
    'SOFTWARE\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall\InVesalius 3.0 - Beta 4_is1') then
      begin
          RegQueryStringValue(HKEY_LOCAL_MACHINE,
            'SOFTWARE\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall\InVesalius 3.0 - Beta 4_is1',
            'UninstallString', uninstaller);
          ShellExec('runas', uninstaller, '/SILENT', '', SW_HIDE, ewWaitUntilTerminated, ErrorCode);
          Result := True;
      end;
           
    Result := True;
end;
