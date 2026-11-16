"""
BossPDF PDF 문서 아이콘 등록 및 Windows Explorer 셸 아이콘 캐시 즉시 갱신 스크립트
"""
import sys
import os
import shutil
import winreg
import ctypes

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass


def register_pdf_doc_icon(exe_path: str = None, icon_path: str = None):
    current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    local_app_dir = os.path.expandvars(r"%LOCALAPPDATA%\Programs\BossPDF")
    local_res_dir = os.path.join(local_app_dir, "resources")

    # 대상 resources 디렉터리 보장 및 최신 아이콘 복사
    os.makedirs(local_res_dir, exist_ok=True)
    src_doc_ico = os.path.join(current_dir, "resources", "pdf_doc_icon.ico")
    src_app_ico = os.path.join(current_dir, "resources", "app_icon.ico")
    dst_doc_ico = os.path.join(local_res_dir, "pdf_doc_icon.ico")
    dst_app_ico = os.path.join(local_res_dir, "app_icon.ico")

    if os.path.exists(src_doc_ico):
        shutil.copy2(src_doc_ico, dst_doc_ico)
    if os.path.exists(src_app_ico):
        shutil.copy2(src_app_ico, dst_app_ico)

    if exe_path is None:
        installed_exe = os.path.join(local_app_dir, "BossPDF.exe")
        dist_exe = os.path.join(current_dir, "dist", "BossPDF", "BossPDF.exe")
        if os.path.exists(installed_exe):
            exe_path = installed_exe
        elif os.path.exists(dist_exe):
            exe_path = dist_exe
        else:
            exe_path = f'"{sys.executable}" "{os.path.join(current_dir, "run.py")}"'

    if icon_path is None:
        if os.path.exists(dst_doc_ico):
            icon_path = dst_doc_ico
        elif os.path.exists(src_doc_ico):
            icon_path = src_doc_ico
        else:
            icon_path = src_app_ico

    print(f"[BossPDF] 등록할 PDF 문서 아이콘: {icon_path}")
    print(f"[BossPDF] 등록할 실행 파일 경로: {exe_path}")

    # 1. ProgID 'BossPDF.Document' 등록 (ICO 파일 단독 지정 시 ,0 생략)
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\BossPDF.Document") as k:
        winreg.SetValueEx(k, "", 0, winreg.REG_SZ, "BossPDF PDF 문서")

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\BossPDF.Document\DefaultIcon") as k:
        winreg.SetValueEx(k, "", 0, winreg.REG_SZ, f'"{icon_path}"')

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\BossPDF.Document\shell\open\command") as k:
        winreg.SetValueEx(k, "", 0, winreg.REG_SZ, f'"{exe_path}" "%1"')

    # 2. SystemFileAssociations\.pdf 에 DefaultIcon 등록
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\SystemFileAssociations\.pdf\DefaultIcon") as k:
        winreg.SetValueEx(k, "", 0, winreg.REG_SZ, f'"{icon_path}"')

    # 3. Applications\BossPDF.exe 등록
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\Applications\BossPDF.exe\DefaultIcon") as k:
        winreg.SetValueEx(k, "", 0, winreg.REG_SZ, f'"{icon_path}"')

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\Applications\BossPDF.exe\shell\open\command") as k:
        winreg.SetValueEx(k, "", 0, winreg.REG_SZ, f'"{exe_path}" "%1"')

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\Applications\BossPDF.exe\SupportedTypes") as k:
        winreg.SetValueEx(k, ".pdf", 0, winreg.REG_SZ, "")

    # 4. .pdf 확장자 연결 (OpenWithProgids)
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\.pdf") as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, "BossPDF.Document")
            winreg.SetValueEx(k, "Content Type", 0, winreg.REG_SZ, "application/pdf")
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\.pdf\OpenWithProgids") as k:
            winreg.SetValueEx(k, "BossPDF.Document", 0, winreg.REG_NONE, b"")
    except Exception as e:
        print(f"참고: .pdf 연결 등록 - {e}")

    # 5. Windows Shell 아이콘 캐시 즉시 갱신 (SHCNE_ASSOCCHANGED)
    SHCNE_ASSOCCHANGED = 0x08000000
    SHCNF_IDLIST = 0x0000
    try:
        ctypes.windll.shell32.SHChangeNotify(SHCNE_ASSOCCHANGED, SHCNF_IDLIST, None, None)
        print("[BossPDF] 윈도우 탐색기 셸 아이콘 캐시 새로고침 완료!")
    except Exception as e:
        print(f"SHChangeNotify 경고: {e}")

    print("[BossPDF] PDF 문서 아이콘 등록 성공!")
    return True


if __name__ == "__main__":
    target_exe = sys.argv[1] if len(sys.argv) > 1 else None
    target_icon = sys.argv[2] if len(sys.argv) > 2 else None
    register_pdf_doc_icon(target_exe, target_icon)
