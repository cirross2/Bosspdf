@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ===========================================================
echo       BossPDF 배포용 인스톨러 패키지 생성 (Inno Setup & ZIP)
echo ===========================================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\create_certificate_and_sign.ps1"
python "%~dp0scripts\create_release_package.py"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] 배포 패키지 생성 중 오류가 발생했습니다.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo ===========================================================
echo   배포 패키지 생성이 완료되었습니다!
echo   1) 단일 설치 파일: dist\BossPDF_Setup_v1.0.0.exe (70 MB)
echo   2) 배포용 압축팩: dist\BossPDF_배포패키지_v1.0.0.zip (70 MB)
echo ===========================================================
echo.
pause
