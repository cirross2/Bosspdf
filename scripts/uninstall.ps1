﻿[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$installDir = Join-Path $env:LOCALAPPDATA "Programs\BossPDF"
Write-Host "[BossPDF] 시스템에서 BossPDF 제거 중..." -ForegroundColor Cyan

# 1. 윈도우 우클릭 메뉴 등록 정보 삭제
$extensions = @("image", ".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tiff", ".tif")
foreach ($ext in $extensions) {
    $regPath = "HKCU:\Software\Classes\SystemFileAssociations\$ext\shell\BossPDF.MergeToPdf"
    if (Test-Path $regPath) {
        Remove-Item -Path $regPath -Recurse -Force -ErrorAction SilentlyContinue
    }
}
$pdfReg = "HKCU:\Software\Classes\SystemFileAssociations\.pdf\shell\BossPDF.Open"
if (Test-Path $pdfReg) {
    Remove-Item -Path $pdfReg -Recurse -Force -ErrorAction SilentlyContinue
}

# 2. PDF 문서 아이콘 및 연결 레지스트리 삭제
$progId = "HKCU:\Software\Classes\BossPDF.Document"
if (Test-Path $progId) {
    Remove-Item -Path $progId -Recurse -Force -ErrorAction SilentlyContinue
}
$appReg = "HKCU:\Software\Classes\Applications\BossPDF.exe"
if (Test-Path $appReg) {
    Remove-Item -Path $appReg -Recurse -Force -ErrorAction SilentlyContinue
}
$sysPdfIcon = "HKCU:\Software\Classes\SystemFileAssociations\.pdf\DefaultIcon"
if (Test-Path $sysPdfIcon) {
    Remove-Item -Path $sysPdfIcon -Recurse -Force -ErrorAction SilentlyContinue
}

# 셸 캐시 즉시 갱신
try {
    $code = '[System.Runtime.InteropServices.DllImport("shell32.dll")] public static extern void SHChangeNotify(int eventId, int flags, IntPtr item1, IntPtr item2);'
    Add-Type -MemberDefinition $code -Namespace Win32 -Name Shell -ErrorAction SilentlyContinue | Out-Null
    [Win32.Shell]::SHChangeNotify(0x08000000, 0, [IntPtr]::Zero, [IntPtr]::Zero)
} catch {}

Write-Host "[BossPDF] 탐색기 우클릭 메뉴 및 PDF 문서 아이콘 등록 정보 삭제 완료!" -ForegroundColor Green

# 2. 바로가기 삭제
$desktopShortcut = Join-Path ([Environment]::GetFolderPath('Desktop')) "BossPDF.lnk"
if (Test-Path $desktopShortcut) {
    Remove-Item -Path $desktopShortcut -Force -ErrorAction SilentlyContinue
}

$startShortcut = Join-Path ([Environment]::GetFolderPath('Programs')) "BossPDF.lnk"
if (Test-Path $startShortcut) {
    Remove-Item -Path $startShortcut -Force -ErrorAction SilentlyContinue
}
Write-Host "[BossPDF] 바탕화면 및 시작 메뉴 바로가기 삭제 완료!" -ForegroundColor Green

# 3. 설치 폴더 삭제
if (Test-Path $installDir) {
    Start-Sleep -Seconds 1
    Remove-Item -Path $installDir -Recurse -Force -ErrorAction SilentlyContinue
}
Write-Host "[BossPDF] 프로그램 파일 정리 완료!" -ForegroundColor Green

Write-Host ""
Write-Host "===========================================================" -ForegroundColor Yellow
Write-Host "  BossPDF가 시스템에서 깔끔하게 제거되었습니다." -ForegroundColor Yellow
Write-Host "===========================================================" -ForegroundColor Yellow
