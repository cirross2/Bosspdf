"""
윈도우 파일 탐색기 마우스 우클릭 메뉴 등록 스크립트 (HKCU 기반, 관리자 권한 불필요)
- 이미지 파일 우클릭: "BossPDF로 PDF 병합"
- PDF 파일 우클릭: "BossPDF로 열기"
"""
import sys
import os
import winreg

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

IMAGE_EXTENSIONS = [".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tiff", ".tif"]


def register_context_menu(exe_path: str = None):
    """
    지정된 실행 파일 경로(또는 현재 run.py / BossPDF.exe)를 윈도우 우클릭 메뉴에 등록
    """
    if exe_path is None:
        # 빌드된 exe가 있으면 exe 우선, 없으면 python 실행 경로 사용
        current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        dist_exe = os.path.join(current_dir, "dist", "BossPDF", "BossPDF.exe")
        if os.path.exists(dist_exe):
            exe_path = dist_exe
        else:
            python_exe = sys.executable
            run_script = os.path.join(current_dir, "run.py")
            exe_path = f'"{python_exe}" "{run_script}"'

    print(f"[BossPDF] 등록할 실행 명령: {exe_path}")

    # 1. SystemFileAssociations\\image 에 등록 (모든 이미지 공통)
    _set_reg_verb(
        sub_key=r"Software\Classes\SystemFileAssociations\image\shell\BossPDF.MergeToPdf",
        menu_title="BossPDF로 PDF 병합",
        exe_cmd=f'{exe_path} --merge-images "%1"',
        icon_path=exe_path.split('"')[1] if exe_path.startswith('"') else exe_path
    )

    # 2. 각 주요 이미지 확장자별 SystemFileAssociations에 등록 (호환성 극대화)
    for ext in IMAGE_EXTENSIONS:
        _set_reg_verb(
            sub_key=f"Software\\Classes\\SystemFileAssociations\\{ext}\\shell\\BossPDF.MergeToPdf",
            menu_title="BossPDF로 PDF 병합",
            exe_cmd=f'{exe_path} --merge-images "%1"',
            icon_path=exe_path.split('"')[1] if exe_path.startswith('"') else exe_path
        )

    # 3. PDF 파일 'BossPDF로 열기' 메뉴 등록
    _set_reg_verb(
        sub_key=r"Software\Classes\SystemFileAssociations\.pdf\shell\BossPDF.Open",
        menu_title="BossPDF로 열기",
        exe_cmd=f'{exe_path} "%1"',
        icon_path=exe_path.split('"')[1] if exe_path.startswith('"') else exe_path
    )

    print("✅ 윈도우 탐색기 마우스 우클릭 메뉴 등록 완료!")
    return True


def _set_reg_verb(sub_key: str, menu_title: str, exe_cmd: str, icon_path: str):
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, sub_key) as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, menu_title)
            if icon_path and os.path.exists(icon_path):
                winreg.SetValueEx(key, "Icon", 0, winreg.REG_SZ, f'"{icon_path}",0')

        cmd_key_path = f"{sub_key}\\command"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, cmd_key_path) as cmd_key:
            winreg.SetValueEx(cmd_key, "", 0, winreg.REG_SZ, exe_cmd)
    except Exception as e:
        print(f"경고: {sub_key} 등록 중 오류 발생 - {e}")


if __name__ == "__main__":
    target_exe = sys.argv[1] if len(sys.argv) > 1 else None
    register_context_menu(target_exe)
