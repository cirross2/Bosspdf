; BossPDF 설치 스크립트 (Inno Setup 6)
; - 1.x(파이썬 버전)와 같은 AppId·설치 위치를 써서, 설치하면 기존 설치본이 2.x로 바뀐다.
; - 빌드: scripts\build-release.ps1  (버전은 Cargo.toml에서 읽어 /DMyAppVersion으로 넘김)
; - /DTestInstall=1 로 빌드하면 레지스트리·바로가기를 건드리지 않는 시험용 설치 파일이 된다.

#define MyAppName "BossPDF"
#ifndef MyAppVersion
  #define MyAppVersion "2.0.0"
#endif
#define MyAppPublisher "BossPDF Software"
#define MyAppExeName "BossPDF.exe"

[Setup]
#ifdef TestInstall
AppId={{6D0C4E57-2A1B-4F6E-9C55-0B055BDF7E57}
OutputBaseFilename=BossPDF_TestSetup
#else
AppId={{9FA56D23-6B74-4C21-9F1C-9E4B827290D8}
OutputBaseFilename=BossPDF_Setup_v{#MyAppVersion}
#endif
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\dist
SetupIconFile=..\assets\app_icon.ico
Compression=lzma2/ultra
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\{#MyAppExeName}
ChangesAssociations=yes
; 실행 중인 BossPDF가 있으면 닫고 설치한다 (자동 업데이트에서 넘어올 때 필요)
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Tasks]
Name: "desktopicon"; Description: "바탕화면에 바로가기 만들기"; GroupDescription: "추가 아이콘:"; Flags: checkedonce

[InstallDelete]
; 1.x(파이썬 버전)가 남긴 실행 환경 폴더를 지운다. 2.x는 실행 파일 하나만 쓴다.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\target\release\BossPDF.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\assets\pdf_doc_icon.ico"; DestDir: "{app}\resources"; Flags: ignoreversion
Source: "..\assets\app_icon.ico"; DestDir: "{app}\resources"; Flags: ignoreversion
Source: "..\assets\BossPDF_Security_Certificate.cer"; DestDir: "{app}\resources"; Flags: ignoreversion

#ifndef TestInstall
[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{group}\{#MyAppName} 제거"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; 1. 탐색기 우클릭 메뉴 (키 이름은 1.x와 같다. 여러 파일을 골라도 창 하나로 모인다)
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\image\shell\BossPDF.MergeToPdf"; ValueType: string; ValueName: ""; ValueData: "BossPDF로 PDF 병합"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\image\shell\BossPDF.MergeToPdf"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#MyAppExeName}"",0"
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\image\shell\BossPDF.MergeToPdf"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\image\shell\BossPDF.MergeToPdf\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" --merge ""%1"""

Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.png\shell\BossPDF.MergeToPdf"; ValueType: string; ValueName: ""; ValueData: "BossPDF로 PDF 병합"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.png\shell\BossPDF.MergeToPdf"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#MyAppExeName}"",0"
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.png\shell\BossPDF.MergeToPdf"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.png\shell\BossPDF.MergeToPdf\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" --merge ""%1"""

Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.jpg\shell\BossPDF.MergeToPdf"; ValueType: string; ValueName: ""; ValueData: "BossPDF로 PDF 병합"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.jpg\shell\BossPDF.MergeToPdf"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#MyAppExeName}"",0"
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.jpg\shell\BossPDF.MergeToPdf"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.jpg\shell\BossPDF.MergeToPdf\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" --merge ""%1"""

Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.jpeg\shell\BossPDF.MergeToPdf"; ValueType: string; ValueName: ""; ValueData: "BossPDF로 PDF 병합"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.jpeg\shell\BossPDF.MergeToPdf"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#MyAppExeName}"",0"
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.jpeg\shell\BossPDF.MergeToPdf"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.jpeg\shell\BossPDF.MergeToPdf\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" --merge ""%1"""

Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.bmp\shell\BossPDF.MergeToPdf"; ValueType: string; ValueName: ""; ValueData: "BossPDF로 PDF 병합"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.bmp\shell\BossPDF.MergeToPdf"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#MyAppExeName}"",0"
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.bmp\shell\BossPDF.MergeToPdf"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.bmp\shell\BossPDF.MergeToPdf\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" --merge ""%1"""

Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.gif\shell\BossPDF.MergeToPdf"; ValueType: string; ValueName: ""; ValueData: "BossPDF로 PDF 병합"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.gif\shell\BossPDF.MergeToPdf"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#MyAppExeName}"",0"
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.gif\shell\BossPDF.MergeToPdf"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.gif\shell\BossPDF.MergeToPdf\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" --merge ""%1"""

Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.tif\shell\BossPDF.MergeToPdf"; ValueType: string; ValueName: ""; ValueData: "BossPDF로 PDF 병합"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.tif\shell\BossPDF.MergeToPdf"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#MyAppExeName}"",0"
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.tif\shell\BossPDF.MergeToPdf"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.tif\shell\BossPDF.MergeToPdf\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" --merge ""%1"""

Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.tiff\shell\BossPDF.MergeToPdf"; ValueType: string; ValueName: ""; ValueData: "BossPDF로 PDF 병합"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.tiff\shell\BossPDF.MergeToPdf"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#MyAppExeName}"",0"
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.tiff\shell\BossPDF.MergeToPdf"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.tiff\shell\BossPDF.MergeToPdf\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" --merge ""%1"""

Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.webp\shell\BossPDF.MergeToPdf"; ValueType: string; ValueName: ""; ValueData: "BossPDF로 PDF 병합"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.webp\shell\BossPDF.MergeToPdf"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#MyAppExeName}"",0"
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.webp\shell\BossPDF.MergeToPdf"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.webp\shell\BossPDF.MergeToPdf\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" --merge ""%1"""

Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\BossPDF.MergePdfs"; ValueType: string; ValueName: ""; ValueData: "BossPDF로 PDF 합치기"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\BossPDF.MergePdfs"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#MyAppExeName}"",0"
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\BossPDF.MergePdfs"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\BossPDF.MergePdfs\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" --merge ""%1"""

; 2. PDF 문서 아이콘과 연결 프로그램 등록
Root: HKCU; Subkey: "Software\Classes\BossPDF.Document"; ValueType: string; ValueName: ""; ValueData: "BossPDF PDF 문서"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\BossPDF.Document\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: """{app}\resources\pdf_doc_icon.ico"""
Root: HKCU; Subkey: "Software\Classes\BossPDF.Document\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""

Root: HKCU; Subkey: "Software\Classes\Applications\{#MyAppExeName}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\Applications\{#MyAppExeName}\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: """{app}\resources\pdf_doc_icon.ico"""
Root: HKCU; Subkey: "Software\Classes\Applications\{#MyAppExeName}\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""

Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.pdf\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: """{app}\resources\pdf_doc_icon.ico"""; Flags: uninsdeletevalue
#endif

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "BossPDF 지금 실행하기"; Flags: postinstall nowait skipifsilent
