# BossPDF 배포 빌드: 실행 파일 빌드 → 서명 → 설치 파일 만들기 → 서명
# 사용: .\scripts\build-release.ps1            (dist\BossPDF_Setup_v<버전>.exe)
#       .\scripts\build-release.ps1 -Test      (레지스트리·바로가기를 건드리지 않는 시험용 dist\BossPDF_TestSetup.exe)
param([switch]$Test)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
. .\env.ps1

$version = (Select-String -Path Cargo.toml -Pattern '^version\s*=\s*"([^"]+)"' | Select-Object -First 1).Matches[0].Groups[1].Value
Write-Host "=== BossPDF v$version 빌드 ===" -ForegroundColor Cyan

cargo build --release
if ($LASTEXITCODE -ne 0) { throw 'cargo build 실패' }
$exe = Join-Path $root 'target\release\BossPDF.exe'

# 코드 서명 (1.x와 같은 자체 서명 인증서. 없으면 만든다)
$subject = 'CN=BossPDF Software'
$cert = Get-ChildItem Cert:\CurrentUser\My | Where-Object { $_.Subject -eq $subject } | Select-Object -First 1
if (-not $cert) {
    $cert = New-SelfSignedCertificate -Type CodeSigningCert -Subject $subject -CertStoreLocation 'Cert:\CurrentUser\My' -FriendlyName 'BossPDF Code Signing Certificate' -NotAfter (Get-Date).AddYears(5)
}
Export-Certificate -Cert $cert -FilePath (Join-Path $root 'assets\BossPDF_Security_Certificate.cer') -Force | Out-Null
$sig = Set-AuthenticodeSignature -Certificate $cert -FilePath $exe -HashAlgorithm SHA256
Write-Host "BossPDF.exe 서명: $($sig.Status)"

$iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe', 'C:\Program Files\Inno Setup 6\ISCC.exe') | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw 'Inno Setup(ISCC.exe)을 찾을 수 없습니다.' }
$defines = @("/DMyAppVersion=$version")
if ($Test) { $defines += '/DTestInstall=1' }
& $iscc @defines /Qp (Join-Path $root 'installer\BossPDF_Setup.iss')
if ($LASTEXITCODE -ne 0) { throw 'Inno Setup 컴파일 실패' }

$setup = Join-Path $root ($(if ($Test) { 'dist\BossPDF_TestSetup.exe' } else { "dist\BossPDF_Setup_v$version.exe" }))
$sig = Set-AuthenticodeSignature -Certificate $cert -FilePath $setup -HashAlgorithm SHA256
Write-Host "설치 파일 서명: $($sig.Status)"
Write-Host ("완료: {0} ({1:N1} MB)" -f $setup, ((Get-Item $setup).Length / 1MB)) -ForegroundColor Green
