import os
import shutil
import zipfile

root_dir = r'e:\코딩\BossPDF'
dist_dir = os.path.join(root_dir, 'dist')
pkg_name = 'BossPDF_v1.0.0_Setup'
pkg_dir = os.path.join(dist_dir, pkg_name)
zip_path = os.path.join(dist_dir, f'{pkg_name}.zip')

print(f'Creating distribution package: {pkg_dir}')
if os.path.exists(pkg_dir):
    shutil.rmtree(pkg_dir)

os.makedirs(pkg_dir, exist_ok=True)

# 1. Copy BossPDF compiled binaries
src_bosspdf = os.path.join(dist_dir, 'BossPDF')
dst_bosspdf = os.path.join(pkg_dir, 'BossPDF')
shutil.copytree(src_bosspdf, dst_bosspdf)
print('Copied BossPDF binary directory')

# Verify resources in dst_bosspdf
res_dst = os.path.join(dst_bosspdf, 'resources')
os.makedirs(res_dst, exist_ok=True)
for icon in ['app_icon.ico', 'app_icon.png', 'pdf_doc_icon.ico', 'pdf_doc_icon.png']:
    src_icon = os.path.join(root_dir, 'resources', icon)
    if os.path.exists(src_icon):
        shutil.copy2(src_icon, os.path.join(res_dst, icon))
print('Verified resources in BossPDF package')

# 2. Copy scripts
dst_scripts = os.path.join(pkg_dir, 'scripts')
os.makedirs(dst_scripts, exist_ok=True)
for s in ['install.ps1', 'uninstall.ps1']:
    src_s = os.path.join(root_dir, 'scripts', s)
    shutil.copy2(src_s, os.path.join(dst_scripts, s))
print('Copied scripts')

# 3. Copy batch files
for b in ['설치하기(우클릭메뉴등록).bat', '제거하기.bat']:
    src_b = os.path.join(root_dir, b)
    shutil.copy2(src_b, os.path.join(pkg_dir, b))
print('Copied bat files')

# 4. Create README / 사용설명서.txt
readme_text = """==============================================================
                     BossPDF v1.0.0 설치 안내
==============================================================

[프로그램 소개]
BossPDF는 애플 macOS 감성의 깔끔하고 세련된 UI를 갖춘
초고속 PDF 뷰어 및 올인원 편집기입니다.

[주요 기능]
1. 연속 스크롤 뷰어 & 썸네일 탐색
2. 텍스트 직접 수정/편집 (시스템 폰트 지원, 폰트 색상/크기 변경)
3. 주석 및 드로잉 (하이라이트, 밑줄, 취소선, 펜, 직사각형, 텍스트 상자)
4. 페이지 순서 변경 및 회전/삭제 (드래그 앤 드롭 지원)
5. 윈도우 파일 탐색기 연동:
   - 이미지 파일들(JPG, PNG 등) 여러 개 선택 후 마우스 우클릭 -> 'BossPDF로 PDF 병합'
   - PDF 연결 프로그램 설정 시 전용 애플 스타일 PDF 문서 아이콘 자동 적용
6. 고품질 다이렉트 프린트(인쇄) 기능

--------------------------------------------------------------
[설치 방법]
1. 본 압축 파일을 원하는 위치에 압축 해제합니다.
2. '설치하기(우클릭메뉴등록).bat' 파일을 더블 클릭하여 실행합니다.
3. 설치가 완료되면 바탕화면 및 시작 메뉴에 'BossPDF' 바로가기가 생성되고,
   마우스 우클릭 메뉴가 자동으로 등록됩니다.

[삭제 방법]
- '제거하기.bat' 파일을 실행하면 등록된 우클릭 메뉴와 프로그램이
  시스템에서 깔끔하게 제거됩니다.
==============================================================
"""

with open(os.path.join(pkg_dir, '사용설명서.txt'), 'w', encoding='utf-8') as f:
    f.write(readme_text)
print('Created 사용설명서.txt')

# 5. Create ZIP archive
print(f'Compressing into ZIP: {zip_path}')
if os.path.exists(zip_path):
    os.remove(zip_path)

with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
    for root, dirs, files in os.walk(pkg_dir):
        for file in files:
            file_path = os.path.join(root, file)
            arcname = os.path.relpath(file_path, dist_dir)
            zipf.write(file_path, arcname)

print(f'Distribution package ZIP generated successfully! Size: {os.path.getsize(zip_path) / (1024*1024):.2f} MB')
