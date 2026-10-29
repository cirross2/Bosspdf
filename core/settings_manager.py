"""
애플리케이션 환경설정 및 최근 사용 폴더(열기/저장 분리), 테마, UI 상태 관리 모듈
"""
import os
from PySide6.QtCore import QSettings


class AppSettings:
    """
    QSettings를 통해 불러오기/저장하기 폴더 위치, 다크/화이트 테마, 사이드바 상태 등을 영구 기억하고 관리하는 클래스
    """
    ORG_NAME = "Antigravity"
    APP_NAME = "PDFStudio"

    KEY_LAST_OPEN_DIR = "paths/last_open_dir"
    KEY_LAST_SAVE_DIR = "paths/last_save_dir"
    KEY_LAST_IMAGE_OPEN_DIR = "paths/last_image_open_dir"
    KEY_LAST_IMAGE_SAVE_DIR = "paths/last_image_save_dir"
    KEY_THEME_MODE = "appearance/theme_mode"
    KEY_SIDEBAR_VISIBLE = "appearance/sidebar_visible"

    @classmethod
    def _get_settings(cls) -> QSettings:
        return QSettings(cls.ORG_NAME, cls.APP_NAME)

    @staticmethod
    def _extract_dir(file_or_dir_path: str) -> str:
        if not file_or_dir_path:
            return ""
        if os.path.isdir(file_or_dir_path):
            return os.path.abspath(file_or_dir_path)
        parent = os.path.dirname(os.path.abspath(file_or_dir_path))
        if os.path.isdir(parent):
            return parent
        return ""

    # 1. PDF 불러오기(열기) 폴더
    @classmethod
    def get_last_open_dir(cls) -> str:
        val = cls._get_settings().value(cls.KEY_LAST_OPEN_DIR, "")
        if val and os.path.isdir(str(val)):
            return str(val)
        return ""

    @classmethod
    def set_last_open_dir(cls, file_or_dir_path: str):
        d = cls._extract_dir(file_or_dir_path)
        if d:
            cls._get_settings().setValue(cls.KEY_LAST_OPEN_DIR, d)

    # 2. PDF 저장하기 폴더
    @classmethod
    def get_last_save_dir(cls) -> str:
        val = cls._get_settings().value(cls.KEY_LAST_SAVE_DIR, "")
        if val and os.path.isdir(str(val)):
            return str(val)
        return ""

    @classmethod
    def set_last_save_dir(cls, file_or_dir_path: str):
        d = cls._extract_dir(file_or_dir_path)
        if d:
            cls._get_settings().setValue(cls.KEY_LAST_SAVE_DIR, d)

    # 3. 이미지 선택(불러오기) 폴더
    @classmethod
    def get_last_image_open_dir(cls) -> str:
        val = cls._get_settings().value(cls.KEY_LAST_IMAGE_OPEN_DIR, "")
        if val and os.path.isdir(str(val)):
            return str(val)
        return ""

    @classmethod
    def set_last_image_open_dir(cls, file_or_dir_path: str):
        d = cls._extract_dir(file_or_dir_path)
        if d:
            cls._get_settings().setValue(cls.KEY_LAST_IMAGE_OPEN_DIR, d)

    # 4. 이미지 합친 PDF 저장하기 폴더
    @classmethod
    def get_last_image_save_dir(cls) -> str:
        val = cls._get_settings().value(cls.KEY_LAST_IMAGE_SAVE_DIR, "")
        if val and os.path.isdir(str(val)):
            return str(val)
        return ""

    @classmethod
    def set_last_image_save_dir(cls, file_or_dir_path: str):
        d = cls._extract_dir(file_or_dir_path)
        if d:
            cls._get_settings().setValue(cls.KEY_LAST_IMAGE_SAVE_DIR, d)

    # 5. 다크 모드 / 화이트 모드 ("dark" / "light")
    @classmethod
    def get_theme_mode(cls, default: str = "light") -> str:
        val = cls._get_settings().value(cls.KEY_THEME_MODE, default)
        return str(val).lower() if str(val).lower() in ("dark", "light") else default

    @classmethod
    def set_theme_mode(cls, mode: str):
        mode = mode.lower() if mode.lower() in ("dark", "light") else "light"
        cls._get_settings().setValue(cls.KEY_THEME_MODE, mode)

    # 6. 사이드바(페이지 미리보기) 가시성 (True: 표시, False: 최소화/숨김)
    @classmethod
    def get_sidebar_visible(cls, default: bool = True) -> bool:
        val = cls._get_settings().value(cls.KEY_SIDEBAR_VISIBLE, default)
        if isinstance(val, bool):
            return val
        if isinstance(val, str):
            return val.lower() not in ("false", "0", "no")
        return bool(val)

    @classmethod
    def set_sidebar_visible(cls, visible: bool):
        cls._get_settings().setValue(cls.KEY_SIDEBAR_VISIBLE, bool(visible))
