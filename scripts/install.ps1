[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition

# 배포 환경 또는 개발 환경에서 BossPDF 바이너리 폴더 자동 탐색
$candidates = @(
    (Join-Path $scriptDir "..\dist\BossPDF"),
    (Join-Path $scriptDir "..\BossPDF"),
    (Join-Path $scriptDir ".."),
    $scriptDir
)
$distDir = $null
foreach ($c in $candidates) {
    if (Test-Path (Join-Path $c "BossPDF.exe")) {
        $distDir = (Resolve-Path $c).Path
        break
    }
}
if (-not $distDir) {
    Write-Host "[ERROR] BossPDF.exe 실행 파일을 찾을 수 없습니다." -ForegroundColor Red
    exit 1
}

$installDir = Join-Path $env:LOCALAPPDATA "Programs\BossPDF"
Write-Host "[BossPDF] 설치 대상 폴더: $installDir" -ForegroundColor Cyan

if (-not (Test-Path $installDir)) {
    New-Item -ItemType Directory -Path $installDir -Force | Out-Null
}

# 프로그램 바이너리 복사
Copy-Item -Path (Join-Path $distDir "*") -Destination $installDir -Recurse -Force
Write-Host "[BossPDF] 프로그램 파일 복사 완료!" -ForegroundColor Green

$exePath = Join-Path $installDir "BossPDF.exe"

# 1. 윈도우 파일 탐색기 마우스 우클릭 메뉴 등록 (HKCU)
$extensions = @("image", ".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tiff", ".tif")
foreach ($ext in $extensions) {
    $regPath = "HKCU:\Software\Classes\SystemFileAssociations\$ext\shell\BossPDF.MergeToPdf"
    New-Item -Path $regPath -Force | Out-Null
    Set-ItemProperty -Path $regPath -Name '(default)' -Value "BossPDF로 PDF 병합"
    Set-ItemProperty -Path $regPath -Name 'Icon' -Value "`"$exePath`",0"
    $cmdPath = Join-Path $regPath "command"
    New-Item -Path $cmdPath -Force | Out-Null
    Set-ItemProperty -Path $cmdPath -Name '(default)' -Value "`"$exePath`" --merge-images `"%1`""
}

# PDF 문서 전용 아이콘 등록 (ProgID 및 Applications)
$docIconPath = Join-Path $installDir "resources\pdf_doc_icon.ico"
if (-not (Test-Path $docIconPath)) {
    $docIconPath = Join-Path $installDir "resources\app_icon.ico"
}

# 1) BossPDF.Document ProgID
$progId = "HKCU:\Software\Classes\BossPDF.Document"
New-Item -Path $progId -Force | Out-Null
Set-ItemProperty -Path $progId -Name '(default)' -Value "BossPDF PDF 문서"

$progIcon = Join-Path $progId "DefaultIcon"
New-Item -Path $progIcon -Force | Out-Null
Set-ItemProperty -Path $progIcon -Name '(default)' -Value "`"$docIconPath`",0"

$progCmd = Join-Path $progId "shell\open\command"
New-Item -Path $progCmd -Force | Out-Null
Set-ItemProperty -Path $progCmd -Name '(default)' -Value "`"$exePath`" `"%1`""

# 2) SystemFileAssociations\.pdf\DefaultIcon
$sysPdfIcon = "HKCU:\Software\Classes\SystemFileAssociations\.pdf\DefaultIcon"
New-Item -Path $sysPdfIcon -Force | Out-Null
Set-ItemProperty -Path $sysPdfIcon -Name '(default)' -Value "`"$docIconPath`",0"

# 3) Applications\BossPDF.exe\DefaultIcon
$appIconKey = "HKCU:\Software\Classes\Applications\BossPDF.exe\DefaultIcon"
New-Item -Path $appIconKey -Force | Out-Null
Set-ItemProperty -Path $appIconKey -Name '(default)' -Value "`"$docIconPath`",0"

# 4) 셸 캐시 즉시 갱신
try {
    $code = '[System.Runtime.InteropServices.DllImport("shell32.dll")] public static extern void SHChangeNotify(int eventId, int flags, IntPtr item1, IntPtr item2);'
    Add-Type -MemberDefinition $code -Namespace Win32 -Name Shell -ErrorAction SilentlyContinue | Out-Null
    [Win32.Shell]::SHChangeNotify(0x08000000, 0, [IntPtr]::Zero, [IntPtr]::Zero)
} catch {}

Write-Host "[BossPDF] 탐색기 마우스 우클릭 메뉴 및 PDF 문서 아이콘 등록 완료!" -ForegroundColor Green

# 2. 바탕화면 및 시작 프로그램 바로가기 생성
$wsh = New-Object -ComObject WScript.Shell

$desktopPath = [Environment]::GetFolderPath('Desktop')
$shortcut = $wsh.CreateShortcut((Join-Path $desktopPath "BossPDF.lnk"))
$shortcut.TargetPath = $exePath
$shortcut.WorkingDirectory = $installDir
$shortcut.IconLocation = "$exePath,0"
$shortcut.Description = 'BossPDF - 고성능 PDF 뷰어 및 편집기'
$shortcut.Save()

$startMenuPath = [Environment]::GetFolderPath('Programs')
$startShortcut = $wsh.CreateShortcut((Join-Path $startMenuPath "BossPDF.lnk"))
$startShortcut.TargetPath = $exePath
$startShortcut.WorkingDirectory = $installDir
$startShortcut.IconLocation = "$exePath,0"
$startShortcut.Description = 'BossPDF - 고성능 PDF 뷰어 및 편집기'
$startShortcut.Save()

# 제거 스크립트 복사
$uninstallBatSrc = Join-Path $scriptDir "..\제거하기.bat"
if (Test-Path $uninstallBatSrc) {
    Copy-Item -Path $uninstallBatSrc -Destination (Join-Path $installDir "제거하기.bat") -Force
}
$uninstallPs1Src = Join-Path $scriptDir "uninstall.ps1"
if (Test-Path $uninstallPs1Src) {
    Copy-Item -Path $uninstallPs1Src -Destination (Join-Path $installDir "uninstall.ps1") -Force
}

Write-Host "[BossPDF] 바탕화면 및 시작 메뉴 바로가기 생성 완료!" -ForegroundColor Green
Write-Host ""
Write-Host "===========================================================" -ForegroundColor Yellow
Write-Host "  BossPDF 설치 및 탐색기 우클릭 메뉴 등록이 완료되었습니다!" -ForegroundColor Yellow
Write-Host "===========================================================" -ForegroundColor Yellow
