; Inno Setup Script for BossPDF
; High-performance PDF Viewer & Editor

#define MyAppName "BossPDF"
#define MyAppVersion "1.0.1"
#define MyAppPublisher "BossPDF Software"
#define MyAppExeName "BossPDF.exe"

[Setup]
AppId={{9FA56D23-6B74-4C21-9F1C-9E4B827290D8}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=BossPDF_Setup_v1.0.1
SetupIconFile=..\resources\app_icon.ico
Compression=lzma2/ultra
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\{#MyAppExeName}
ChangesAssociations=yes

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Tasks]
Name: "desktopicon"; Description: "바탕화면에 바로가기 만들기"; GroupDescription: "추가 아이콘:"; Flags: checkedonce

[Files]
Source: "..\dist\BossPDF\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\resources\BossPDF_Security_Certificate.cer"; DestDir: "{app}\resources"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{group}\{#MyAppName} 제거"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; 1. 파일 탐색기 우클릭 이미지 병합 메뉴 등록
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\image\shell\BossPDF.MergeToPdf"; ValueType: string; ValueName: ""; ValueData: "BossPDF로 PDF 병합"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\image\shell\BossPDF.MergeToPdf"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#MyAppExeName}"",0"
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\image\shell\BossPDF.MergeToPdf\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" --merge-images ""%1"""

Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.png\shell\BossPDF.MergeToPdf"; ValueType: string; ValueName: ""; ValueData: "BossPDF로 PDF 병합"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.png\shell\BossPDF.MergeToPdf"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#MyAppExeName}"",0"
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.png\shell\BossPDF.MergeToPdf\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" --merge-images ""%1"""

Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.jpg\shell\BossPDF.MergeToPdf"; ValueType: string; ValueName: ""; ValueData: "BossPDF로 PDF 병합"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.jpg\shell\BossPDF.MergeToPdf"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#MyAppExeName}"",0"
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.jpg\shell\BossPDF.MergeToPdf\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" --merge-images ""%1"""

Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.jpeg\shell\BossPDF.MergeToPdf"; ValueType: string; ValueName: ""; ValueData: "BossPDF로 PDF 병합"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.jpeg\shell\BossPDF.MergeToPdf"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#MyAppExeName}"",0"
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.jpeg\shell\BossPDF.MergeToPdf\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" --merge-images ""%1"""

Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.webp\shell\BossPDF.MergeToPdf"; ValueType: string; ValueName: ""; ValueData: "BossPDF로 PDF 병합"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.webp\shell\BossPDF.MergeToPdf"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#MyAppExeName}"",0"
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.webp\shell\BossPDF.MergeToPdf\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" --merge-images ""%1"""

; 2. PDF 전용 문서 아이콘 및 연결 등록
Root: HKCU; Subkey: "Software\Classes\BossPDF.Document"; ValueType: string; ValueName: ""; ValueData: "BossPDF PDF 문서"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\BossPDF.Document\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: """{app}\resources\pdf_doc_icon.ico"",0"
Root: HKCU; Subkey: "Software\Classes\BossPDF.Document\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""

Root: HKCU; Subkey: "Software\Classes\Applications\{#MyAppExeName}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\Applications\{#MyAppExeName}\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: """{app}\resources\pdf_doc_icon.ico"",0"
Root: HKCU; Subkey: "Software\Classes\Applications\{#MyAppExeName}\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""

Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.pdf\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: """{app}\resources\pdf_doc_icon.ico"",0"; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "BossPDF 지금 실행하기"; Flags: postinstall nowait skipifsilent

