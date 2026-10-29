"""
애플리케이션 환경설정 및 최근 사용 폴더(열기/저장 분리) 관리 모듈
"""
import os
from PySide6.QtCore import QSettings


class AppSettings:
    """
    QSettings를 통해 불러오기/저장하기 폴더 위치를 각각 영구 기억하고 관리하는 클래스
    """
    ORG_NAME = "Antigravity"
    APP_NAME = "PDFStudio"

    KEY_LAST_OPEN_DIR = "paths/last_open_dir"
    KEY_LAST_SAVE_DIR = "paths/last_save_dir"
    KEY_LAST_IMAGE_OPEN_DIR = "paths/last_image_open_dir"
    KEY_LAST_IMAGE_SAVE_DIR = "paths/last_image_save_dir"

    @classmethod
    def _get_settings(cls) -> QSettings:
        return QSettings(cls.ORG_NAME, cls.APP_NAME)

    @staticmethod
    def _extract_dir(file_or_dir_path: str) -> str:
        if not file_or_dir_path:
            return ""
        # 만약 이미 존재하는 폴더 경로인 경우
        if os.path.isdir(file_or_dir_path):
            return os.path.abspath(file_or_dir_path)
        # 파일 경로인 경우(신규 생성 예정이거나 기존 파일), 상위 디렉토리 반환
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
