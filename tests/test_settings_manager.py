"""
저장하기 및 불러오기 폴더 위치 분리 기억 단위 테스트
"""
import os
import sys
import tempfile
from PySide6.QtCore import QSettings

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.settings_manager import AppSettings


def test_app_settings():
    print("=== 1. 개별 폴더 4개 임시 생성 ===")
    dir_open = tempfile.mkdtemp(prefix="test_open_")
    dir_save = tempfile.mkdtemp(prefix="test_save_")
    dir_img_open = tempfile.mkdtemp(prefix="test_img_open_")
    dir_img_save = tempfile.mkdtemp(prefix="test_img_save_")

    print(f"불러오기 폴더: {dir_open}")
    print(f"저장하기 폴더: {dir_save}")
    print(f"이미지 불러오기 폴더: {dir_img_open}")
    print(f"이미지 저장하기 폴더: {dir_img_save}")

    print("\n=== 2. 각각 다른 폴더 위치 저장 ===")
    dummy_pdf_open = os.path.join(dir_open, "sample.pdf")
    dummy_pdf_save = os.path.join(dir_save, "saved.pdf")
    dummy_img_open = os.path.join(dir_img_open, "photo.png")
    dummy_img_save = os.path.join(dir_img_save, "merged.pdf")

    AppSettings.set_last_open_dir(dummy_pdf_open)
    AppSettings.set_last_save_dir(dummy_pdf_save)
    AppSettings.set_last_image_open_dir(dummy_img_open)
    AppSettings.set_last_image_save_dir(dummy_img_save)

    print("\n=== 3. 각각 독립적으로 기억되는지 검증 ===")
    got_open = AppSettings.get_last_open_dir()
    got_save = AppSettings.get_last_save_dir()
    got_img_open = AppSettings.get_last_image_open_dir()
    got_img_save = AppSettings.get_last_image_save_dir()

    print(f"불러오기 기억 위치: {got_open}")
    print(f"저장하기 기억 위치: {got_save}")
    print(f"이미지 불러오기 기억 위치: {got_img_open}")
    print(f"이미지 저장하기 기억 위치: {got_img_save}")

    assert os.path.normpath(got_open) == os.path.normpath(dir_open), "불러오기 폴더 불일치"
    assert os.path.normpath(got_save) == os.path.normpath(dir_save), "저장하기 폴더 불일치"
    assert os.path.normpath(got_img_open) == os.path.normpath(dir_img_open), "이미지 불러오기 폴더 불일치"
    assert os.path.normpath(got_img_save) == os.path.normpath(dir_img_save), "이미지 저장하기 폴더 불일치"

    # 둘이 서로 다른지 검증
    assert got_open != got_save, "불러오기와 저장하기 폴더가 분리되지 않음"

    print("\n[SUCCESS] 불러오기/저장하기 위치 독립 기억 기능 정상 작동 검증 완료!")


if __name__ == "__main__":
    test_app_settings()
