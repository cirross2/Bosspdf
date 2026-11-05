[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$rootDir = (Resolve-Path "$scriptDir\..").Path
$resDir = Join-Path $rootDir "resources"
$distDir = Join-Path $rootDir "dist"

$versionFile = Join-Path $rootDir "core\version.py"
$appVersion = "1.0.3"
if (Test-Path $versionFile) {
    $verMatch = Select-String -Path $versionFile -Pattern '__version__\s*=\s*"([^"]+)"' | Select-Object -First 1
    if ($verMatch -and $verMatch.Matches.Count -gt 0) {
        $appVersion = $verMatch.Matches[0].Groups[1].Value
    }
}

Write-Host "=== [1/4] BossPDF (v$appVersion) 디지털 서명용 보안 인증서 준비 ===" -ForegroundColor Cyan

$certName = "CN=BossPDF Software"
$existingCert = Get-ChildItem -Path Cert:\CurrentUser\My | Where-Object { $_.Subject -eq $certName } | Select-Object -First 1

if (-not $existingCert) {
    Write-Host "새로운 코드 서명 인증서 생성 중..." -ForegroundColor Yellow
    $cert = New-SelfSignedCertificate `
        -Type CodeSigningCert `
        -Subject $certName `
        -CertStoreLocation "Cert:\CurrentUser\My" `
        -FriendlyName "BossPDF Code Signing Certificate" `
        -NotAfter (Get-Date).AddYears(5)
} else {
    Write-Host "기존 코드 서명 인증서 사용: $($existingCert.Thumbprint)" -ForegroundColor Green
    $cert = $existingCert
}

$cerPath = Join-Path $resDir "BossPDF_Security_Certificate.cer"
Export-Certificate -Cert $cert -FilePath $cerPath -Force | Out-Null
Write-Host "공개 보안 인증서 내보내기 완료: $cerPath" -ForegroundColor Green

$exePath = Join-Path $distDir "BossPDF\BossPDF.exe"
if (Test-Path $exePath) {
    Write-Host "BossPDF.exe 디지털 서명 적용 중..." -ForegroundColor Cyan
    $sig = Set-AuthenticodeSignature -Certificate $cert -FilePath $exePath -HashAlgorithm SHA256
    Write-Host "BossPDF.exe 서명 상태: $($sig.Status)" -ForegroundColor Green
}

$isccCandidates = @(
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe"
)
$isccPath = $null
foreach ($cand in $isccCandidates) {
    if (Test-Path $cand) {
        $isccPath = $cand
        break
    }
}

if ($isccPath) {
    Write-Host "=== [2/4] Inno Setup 기반 설치 파일(BossPDF_Setup_v$appVersion.exe) 컴파일 ===" -ForegroundColor Cyan
    $issFile = Join-Path $scriptDir "BossPDF_Setup.iss"
    if (Test-Path $issFile) {
        & "$isccPath" "/DMyAppVersion=$appVersion" "$issFile"
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Inno Setup 컴파일 성공!" -ForegroundColor Green

            $setupExe = Join-Path $distDir "BossPDF_Setup_v$appVersion.exe"
            if (Test-Path $setupExe) {
                Write-Host "BossPDF_Setup_v$appVersion.exe 디지털 서명 적용 중..." -ForegroundColor Cyan
                $setupSig = Set-AuthenticodeSignature -Certificate $cert -FilePath $setupExe -HashAlgorithm SHA256
                Write-Host "설치 파일 서명 상태: $($setupSig.Status)" -ForegroundColor Green
                Write-Host ""
                Write-Host "==========================================================" -ForegroundColor Yellow
                Write-Host "  BossPDF 단일 설치 파일(Setup.exe) 제작 및 서명 완료!" -ForegroundColor Yellow
                Write-Host "  위치: $setupExe" -ForegroundColor Yellow
                Write-Host "==========================================================" -ForegroundColor Yellow
            }
        } else {
            Write-Host "Inno Setup 컴파일 실패 (ExitCode: $LASTEXITCODE)" -ForegroundColor Red
        }
    }
} else {
    Write-Host "Inno Setup ISCC.exe를 찾을 수 없습니다." -ForegroundColor Yellow
}
