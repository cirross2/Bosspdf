"""
윈도우 시스템 폰트 로딩 속도, 폰트 매퍼, PyMuPDF 삽입 및 다이얼로그 연동 테스트
"""
import os
import sys
import time
import pytest
from PySide6.QtWidgets import QApplication

from core.font_manager import FontManager
from core.pdf_engine import PdfEngine
from ui.text_edit_dialog import TextEditDialog


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_system_font_speed_and_count(qapp):
    start_t = time.perf_counter()
    fonts = FontManager.get_all_font_families()
    elapsed = time.perf_counter() - start_t

    print(f"\n[FontManager] 시스템 폰트 {len(fonts)}개 로딩 완료 (소요시간: {elapsed*1000:.2f}ms)")
    assert len(fonts) > 50, f"시스템 폰트가 50개 이상이어야 합니다. (발견: {len(fonts)})"
    assert elapsed < 0.3, f"초기 로딩 시간이 300ms를 초과하지 않아야 합니다. (실제: {elapsed*1000:.2f}ms)"
    assert "맑은 고딕" in fonts or "Malgun Gothic" in fonts


def test_system_font_path_resolution(qapp):
    test_cases = [
        ("맑은 고딕", False, False),
        ("맑은 고딕", True, False),
        ("굴림", False, False),
        ("Calibri", False, False),
        ("Calibri", True, False),
        ("Segoe UI", False, False),
        ("Arial", True, True),
    ]

    for family, bold, italic in test_cases:
        path = FontManager.get_font_file_path(family, is_bold=bold, is_italic=italic)
        assert os.path.exists(path), f"폰트 파일이 존재해야 합니다: {family} -> {path}"
        assert path.lower().endswith((".ttf", ".otf", ".ttc"))


def test_pdf_engine_embed_system_fonts(qapp, tmp_path):
    engine = PdfEngine()
    dummy_pdf = tmp_path / "sysfont_test.pdf"

    import pymupdf as fitz
    doc = fitz.open()
    doc.new_page(width=595, height=842)
    doc.save(str(dummy_pdf))
    doc.close()

    engine.load_document(str(dummy_pdf))

    test_fonts = ["맑은 고딕", "바탕", "Calibri", "Segoe UI", "Arial"]
    y_pos = 50.0
    for f in test_fonts:
        success = engine.add_text(
            page_num=0,
            text=f"안녕하세요 시스템 폰트 테스트: {f}",
            x=50.0,
            y=y_pos,
            font_family=f,
            fontsize=16.0,
            is_bold=False,
            is_italic=False,
            color=(0.1, 0.2, 0.5)
        )
        assert success is True, f"{f} 폰트 삽입에 실패했습니다."
        y_pos += 40.0

    output_pdf = tmp_path / "sysfont_saved.pdf"
    engine.save(str(output_pdf))
    assert os.path.exists(str(output_pdf))
    assert os.path.getsize(str(output_pdf)) > 1000


def test_text_edit_dialog_system_fonts(qapp):
    dlg = TextEditDialog(initial_text="테스트 문구")
    item_count = dlg.combo_font.count()
    print(f"\n[TextEditDialog] 콤보박스 등록된 폰트 수: {item_count}")
    assert item_count > 50, f"콤보박스에 전체 시스템 폰트가 로드되어야 합니다. (개수: {item_count})"
    assert dlg.combo_font.isEditable() is True
    dlg.close()
