import os
import sys
import shutil
import zipfile

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

try:
    from core.version import __version__
except ImportError:
    __version__ = "1.0.1"

dist_dir = os.path.join(root_dir, "dist")
pkg_name = f"BossPDF_배포패키지_v{__version__}"
pkg_dir = os.path.join(dist_dir, pkg_name)
zip_path = os.path.join(dist_dir, f"{pkg_name}.zip")

print(f"Creating release package: {pkg_dir}")
if os.path.exists(pkg_dir):
    shutil.rmtree(pkg_dir)

os.makedirs(pkg_dir, exist_ok=True)

# 1. Copy BossPDF_Setup_v*.exe
setup_exe_name = f"BossPDF_Setup_v{__version__}.exe"
setup_src = os.path.join(dist_dir, setup_exe_name)
if not os.path.exists(setup_src):
    # fallback to latest setup exe in dist
    candidates = [f for f in os.listdir(dist_dir) if f.startswith("BossPDF_Setup_") and f.endswith(".exe")]
    if candidates:
        candidates.sort(key=lambda x: os.path.getmtime(os.path.join(dist_dir, x)), reverse=True)
        setup_exe_name = candidates[0]
        setup_src = os.path.join(dist_dir, setup_exe_name)

if os.path.exists(setup_src):
    shutil.copy2(setup_src, os.path.join(pkg_dir, setup_exe_name))
    print(f"Copied {setup_exe_name}")
else:
    print(f"Warning: Setup executable not found at {setup_src}")

# 2. Copy Certificate
cer_src = os.path.join(root_dir, "resources", "BossPDF_Security_Certificate.cer")
if os.path.exists(cer_src):
    shutil.copy2(cer_src, os.path.join(pkg_dir, "BossPDF_Security_Certificate.cer"))
    print("Copied BossPDF_Security_Certificate.cer")

# 3. Create '보안인증서_등록하기(안전실행).bat'
bat_content = f"""@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ===========================================================
echo       BossPDF 보안 인증서 신뢰 등록 및 SmartScreen 차단 해제
echo ===========================================================
echo.
echo 윈도우 보안 시스템에 BossPDF 공식 인증서를 신뢰할 수 있는 루트로 등록합니다.
echo (이 작업 후 '알 수 없는 게시자' 및 보안 경고가 나타나지 않습니다.)
echo.

if exist "%~dp0BossPDF_Security_Certificate.cer" (
    certutil -addstore -user "Root" "%~dp0BossPDF_Security_Certificate.cer"
)

echo.
echo 인터넷 다운로드 파일에 대한 Windows 잠금(Mark-of-the-Web)을 해제합니다...
powershell -NoProfile -Command "Get-ChildItem -Recurse '%~dp0' | Unblock-File -ErrorAction SilentlyContinue"

echo.
echo ===========================================================
echo   보안 등록 완료! 이제 {setup_exe_name}를 실행하세요.
echo ===========================================================
echo.
pause
"""
with open(os.path.join(pkg_dir, "보안인증서_등록하기(안전실행).bat"), "w", encoding="utf-8-sig") as f:
    f.write(bat_content)
print("Created 보안인증서_등록하기(안전실행).bat")

# 4. Create '설치_및_보안가이드.txt'
guide_content = f"""==============================================================
                 BossPDF v{__version__} 설치 및 보안 가이드
==============================================================

BossPDF는 애플 macOS 감성의 직관적인 고성능 PDF 뷰어 & 올인원 편집기입니다.

[주요 기능]
1. 문서 내 단어 검색 (Ctrl+F): 검색 단어 블록 실시간 강조 및 순환 이동
2. 특정 페이지만 선택하여 새 PDF 또는 고화질 이미지(PNG/JPG)로 내보내기
3. 선택한 여러 페이지 또는 문서 전체를 하나로 이어 붙인 '긴 웹툰형 이미지' 저장 (Ctrl+E)
4. 초고속 가상화 지연 렌더링 (Lazy Viewport Rendering, 100페이지 이상도 즉시 오픈)
5. 암호화 문서 비밀번호 입력 및 비밀번호 영구 해제 저장
6. 텍스트 삽입, 덮어쓰기 수정, 화이트아웃 삭제, 형광펜, 서명 펜
7. 페이지 순서 변경 및 회전/삭제
8. 이미지 파일 우클릭 -> 'BossPDF로 PDF 병합'
9. GitHub 연동 자동 업데이트 (도움말 > 업데이트 확인)

--------------------------------------------------------------
[다른 PC에서 윈도우 보안 경고 없이 설치하는 방법]

인터넷, 웹브라우저, 메신저 등을 통해 파일을 다운로드하면
윈도우가 자동으로 'Mark-of-the-Web (차단 속성)'을 부여하여
'Windows의 PC 보호 (SmartScreen)' 알림창이 뜰 수 있습니다.

이를 방지하는 2가지 방법 중 하나를 선택하세요:

▶ 방법 A (가장 추천 - 1초 원클릭):
  1. 본 압축을 푼 폴더에서 '보안인증서_등록하기(안전실행).bat'을 더블 클릭합니다.
  2. 나타나는 안내창에서 [예]를 누르면 인증서가 등록되고 파일 차단이 해제됩니다.
  3. '{setup_exe_name}'를 더블 클릭하여 설치를 완료합니다.

▶ 방법 B (수동 차단 해제):
  1. '{setup_exe_name}' 파일 우클릭 -> [속성] 클릭
  2. 일반 탭 맨 아래 보안 항목의 [차단 해제(K)] 체크박스에 체크 후 [확인]
  3. 실행 시 'Windows의 PC 보호' 화면이 나타나면 [추가 정보] -> [실행] 클릭!
     (한 번 실행하면 이후에는 경고 없이 즉시 실행됩니다.)
==============================================================
"""
with open(os.path.join(pkg_dir, "설치_및_보안가이드.txt"), "w", encoding="utf-8-sig") as f:
    f.write(guide_content)
print("Created 설치_및_보안가이드.txt")

# 5. Compress into ZIP
print(f"Compressing into {zip_path}...")
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
    for root, dirs, files in os.walk(pkg_dir):
        for file in files:
            fp = os.path.join(root, file)
            arc = os.path.relpath(fp, dist_dir)
            zipf.write(fp, arc)

size_mb = os.path.getsize(zip_path) / (1024 * 1024)
print(f"Release package generated successfully! Size: {size_mb:.2f} MB")
