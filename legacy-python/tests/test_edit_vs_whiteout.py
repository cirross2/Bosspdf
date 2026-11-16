"""
텍스트 삭제(화이트아웃)와 텍스트 수정(EDIT_TEXT) 기능 분리 및 정상 동작 검증 테스트
"""
import os
import sys
import tempfile
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPointF
import pymupdf as fitz

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.pdf_engine import PdfEngine
from ui.viewer_widget import PdfViewerWidget, EditMode


def test_whiteout_vs_edit_text():
    app = QApplication.instance() or QApplication(sys.argv)
    temp_dir = tempfile.mkdtemp()
    sample_pdf = os.path.join(temp_dir, "sample_mode_test.pdf")

    print("=== 1. 테스트용 PDF 생성 ===")
    doc = fitz.open()
    page = doc.new_page(width=500, height=500)
    page.insert_textbox(fitz.Rect(50, 50, 250, 80), "Original Text To Edit", fontsize=14)
    page.insert_textbox(fitz.Rect(50, 150, 250, 180), "Original Text To Whiteout", fontsize=14)
    doc.save(sample_pdf)
    doc.close()

    engine = PdfEngine()
    engine.load_document(sample_pdf)

    viewer = PdfViewerWidget()
    viewer.set_engine(engine)

    print("\n=== 2. WHITEOUT 모드 검증 (대화상자 없이 즉시 화이트아웃만 수행) ===")
    viewer.set_mode(EditMode.WHITEOUT)
    assert viewer.current_mode == EditMode.WHITEOUT

    # 화이트아웃 영역 적용 (50, 150)~(250, 180)
    whiteout_rect = fitz.Rect(50, 150, 250, 180)
    ok = engine.add_whiteout(0, whiteout_rect)
    assert ok, "화이트아웃 적용 실패"
    print("화이트아웃 적용 성공 (텍스트 삭제/가리기 완료)")

    print("\n=== 3. EDIT_TEXT 모드 검증 (기존 내용 추출 및 교체) ===")
    viewer.set_mode(EditMode.EDIT_TEXT)
    assert viewer.current_mode == EditMode.EDIT_TEXT

    # 1) 기존 텍스트 추출 확인
    edit_rect = fitz.Rect(50, 50, 250, 80)
    extracted = engine.doc[0].get_text("text", clip=edit_rect).strip()
    print(f"드래그 영역에서 추출된 기존 텍스트: '{extracted}'")
    assert "Original Text To Edit" in extracted, "기존 텍스트 추출 실패"

    # 2) 화이트아웃 후 새로운 텍스트로 치환 적용
    engine.add_whiteout(0, edit_rect)
    engine.add_text(
        page_num=0,
        x=50,
        y=50,
        text="New Replaced Text Content",
        fontsize=14,
        color=(0.1, 0.4, 0.9)
    )

    # 확인
    new_extracted = engine.doc[0].get_text("text", clip=edit_rect).strip()
    print(f"수정 후 추출된 텍스트: '{new_extracted}'")
    assert "New Replaced Text Content" in new_extracted, "새 텍스트 치환 실패"

    print("\n=== 4. Undo 실행 시 원래 내용 복원 확인 ===")
    engine.undo()  # 새 텍스트 취소
    engine.undo()  # 화이트아웃 취소
    restored = engine.doc[0].get_text("text", clip=edit_rect).strip()
    print(f"Undo 후 복원된 텍스트: '{restored}'")
    assert "Original Text To Edit" in restored, "원래 텍스트 복원 실패"

    viewer.close()
    engine.close()
    print("\n[SUCCESS] WHITEOUT과 EDIT_TEXT 분기 및 치환 기능 정상 동작 검증 완료!")


if __name__ == "__main__":
    test_whiteout_vs_edit_text()
