"""
글꼴, 스타일, 색상, 정렬 및 스마트 줄맞춤 기능 단위 테스트
"""
import os
import sys
import tempfile
import pymupdf as fitz
from PySide6.QtGui import QGuiApplication

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.pdf_engine import PdfEngine
from ui.text_edit_dialog import TextEditDialog


def test_font_and_snap():
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    temp_dir = tempfile.mkdtemp()
    test_pdf = os.path.join(temp_dir, "test_font_snap.pdf")

    print("=== 1. 기준 텍스트가 있는 샘플 PDF 생성 ===")
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    # 기준 텍스트 줄 배치: X=50, Y=100
    page.insert_textbox(
        fitz.Rect(50, 100, 350, 130),
        "기준 텍스트 1행 (Left Margin 50pt, FontSize 14pt)",
        fontsize=14.0
    )
    # 기준 텍스트 줄 배치: X=50, Y=140
    page.insert_textbox(
        fitz.Rect(50, 140, 350, 170),
        "기준 텍스트 2행 (Left Margin 50pt, FontSize 14pt)",
        fontsize=14.0
    )
    doc.save(test_pdf)
    doc.close()

    print("=== 2. 스마트 줄맞춤(스냅) 분석 테스트 ===")
    engine = PdfEngine()
    engine.load_document(test_pdf)

    # 사용자가 (58, 178) 근처를 클릭했다고 가정
    snap = engine.find_nearest_text_line(page_num=0, target_x=58.0, target_y=178.0)
    print(f"스냅 결과: found={snap['found']}, snap_x={snap['snap_x']}, snap_y={snap['snap_y']}, font_size={snap['suggested_size']}")
    assert snap["found"] is True, "인접 줄 감지 실패"
    assert abs(snap["snap_x"] - 50.0) < 5.0, f"X좌표 마진 스냅 실패: {snap['snap_x']}"
    assert snap["suggested_size"] == 14.0, f"폰트 크기 감지 실패: {snap['suggested_size']}"

    print("=== 3. 다양한 글꼴 및 스타일 삽입 테스트 ===")
    # 1) 맑은 고딕 Bold 테스트
    ok = engine.add_text(
        page_num=0,
        x=snap["snap_x"],
        y=snap["snap_y"],
        text="맑은 고딕 굵게 테스트 (자동 정렬)",
        font_family="맑은 고딕",
        fontsize=14.0,
        is_bold=True,
        color=(0.8, 0.1, 0.1),  # 빨강
        align=0
    )
    assert ok, "맑은 고딕 Bold 삽입 실패"

    # 2) 바탕체 + 가운데 정렬 테스트
    ok2 = engine.add_text(
        page_num=0,
        x=50.0,
        y=220.0,
        text="바탕체 가운데 정렬 테스트",
        font_family="바탕",
        fontsize=16.0,
        is_bold=False,
        color=(0.1, 0.3, 0.8),  # 파랑
        align=1  # Center
    )
    assert ok2, "바탕체 삽입 실패"

    # 3) Arial 테스트
    ok3 = engine.add_text(
        page_num=0,
        x=50.0,
        y=260.0,
        text="English Arial Bold Text Alignment",
        font_family="Arial",
        fontsize=12.0,
        is_bold=True,
        color=(0.1, 0.6, 0.2),  # 초록
        align=0
    )
    assert ok3, "Arial 삽입 실패"

    print("=== 4. 렌더링 및 저장 무결성 검증 ===")
    qimg = engine.render_page(0, zoom=1.0)
    assert not qimg.isNull(), "렌더링 실패"
    print(f"렌더링 성공! QImage 크기: {qimg.width()} x {qimg.height()}")

    save_path = os.path.join(temp_dir, "final_verified.pdf")
    engine.save(save_path)
    engine.close()

    verify_doc = fitz.open(save_path)
    assert len(verify_doc) == 1
    verify_doc.close()

    print("\n[SUCCESS] 글꼴, 스타일, 색상 및 스마트 줄맞춤 테스트 완벽 통과!")


if __name__ == "__main__":
    test_font_and_snap()
