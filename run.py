"""
BossPDF 애플리케이션 실행 진입점 (Entry Point)
- 일반 실행: 메인 뷰어 윈도우 실행
- 파일 인자: PDF 파일 직접 열람
- --merge-images 인자: 탐색기 우클릭 다중 이미지 선택 시 로컬 IPC 취합 후 단일 병합 창 실행
"""
import sys
import os
from typing import List
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont, QIcon

# 프로젝트 루트 경로를 sys.path에 등록
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from ui.main_window import MainWindow
from ui.image_merge_dialog import ImageMergeDialog
from ui.theme import AppleTheme
from core.settings_manager import AppSettings
from core.ipc_manager import handle_merge_cli, release_merge_mutex


def get_resource_path(relative_path: str) -> str:
    """개발 환경 및 PyInstaller 패키징 환경 모두에서 리소스 경로 반환"""
    if hasattr(sys, "_MEIPASS"):
        meipass_p = os.path.join(sys._MEIPASS, relative_path)
        if os.path.exists(meipass_p):
            return meipass_p
    exe_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
    for candidate in [
        os.path.join(exe_dir, relative_path),
        os.path.join(exe_dir, "_internal", relative_path),
        os.path.join(CURRENT_DIR, relative_path),
    ]:
        if os.path.exists(candidate):
            return candidate
    return os.path.join(CURRENT_DIR, relative_path)


def main():
    args = sys.argv[1:]

    # 1. 탐색기 마우스 우클릭 다중 이미지 병합 요청 처리
    if "--merge-images" in args:
        idx = args.index("--merge-images")
        image_files = [arg for arg in args[idx + 1:] if not arg.startswith("--")]

        # 서브 프로세스는 큐에 파일 등록 후 즉시 종료, 메인 프로세스는 모든 파일 취합
        should_exit, collected_files, mutex = handle_merge_cli(image_files)
        if should_exit:
            sys.exit(0)

        app = QApplication(sys.argv)
        app.setApplicationName("BossPDF")
        app.setOrganizationName("BossPDF")
        theme_mode = AppSettings.get_theme_mode(default=AppleTheme.LIGHT)
        app.setStyleSheet(AppleTheme.get_stylesheet(theme_mode))

        font = QFont("Segoe UI", 10)
        font.setStyleHint(QFont.StyleHint.SansSerif)
        app.setFont(font)
        icon_path = get_resource_path("resources/app_icon.png")
        if os.path.exists(icon_path):
            app.setWindowIcon(QIcon(icon_path))

        dlg = ImageMergeDialog(initial_files=collected_files)
        if os.path.exists(icon_path):
            dlg.setWindowIcon(QIcon(icon_path))
        dlg.exec()
        release_merge_mutex(mutex)
        sys.exit(0)

    # 2. 일반 실행 또는 PDF 파일 직접 열기
    app = QApplication(sys.argv)
    app.setApplicationName("BossPDF")
    app.setOrganizationName("BossPDF")

    # 애플 네이티브 감성 기본 폰트 설정
    font = QFont("Segoe UI", 10)
    font.setStyleHint(QFont.StyleHint.SansSerif)
    app.setFont(font)

    # 저장된 테마(다크/화이트) 전역 적용
    saved_theme = AppSettings.get_theme_mode(default=AppleTheme.LIGHT)
    app.setStyleSheet(AppleTheme.get_stylesheet(saved_theme))

    # 애플리케이션 아이콘 설정
    icon_path = get_resource_path("resources/app_icon.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    window = MainWindow()
    if os.path.exists(icon_path):
        window.setWindowIcon(QIcon(icon_path))

    # 인자로 넘어온 PDF 파일이 있다면 즉시 로드
    pdf_to_open = None
    for arg in args:
        if arg.lower().endswith(".pdf") and os.path.exists(arg):
            pdf_to_open = os.path.abspath(arg)
            break

    window.show()

    if pdf_to_open:
        window.load_pdf(pdf_to_open)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
