"""
PDF 연속 스크롤 레이아웃 및 텍스트 편집/삭제/하이라이트/서명/언두 검증 테스트
"""
import os
import sys
import tempfile
import pymupdf as fitz
from PySide6.QtGui import QGuiApplication

# 경로 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.pdf_engine import PdfEngine


def test_editing_features():
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    temp_dir = tempfile.mkdtemp()
    test_pdf_path = os.path.join(temp_dir, "sample_edit_test.pdf")

    print("=== 1. 테스트용 3페이지 PDF 생성 ===")
    doc = fitz.open()
    for i in range(3):
        page = doc.new_page(width=595, height=842)
        page.draw_rect(fitz.Rect(50, 50, 545, 792), color=(0.8, 0.8, 0.8), width=1)
        # 기본 텍스트 삽입
        page.insert_textbox(fitz.Rect(60, 60, 400, 100), f"Sample Page {i + 1} Original Content")
    doc.save(test_pdf_path)
    doc.close()
    print(f"생성 완료: {test_pdf_path}")

    print("\n=== 2. PdfEngine 로드 및 편집 테스트 ===")
    engine = PdfEngine()
    engine.load_document(test_pdf_path)
    assert engine.page_count == 3, "페이지 수 불일치"

    # 1) 텍스트 추가 테스트 (한글)
    print("-> 텍스트 추가 테스트 (한글 지원)")
    success = engine.add_text(
        page_num=0,
        x=60,
        y=150,
        text="안녕하세요! 새로 추가된 한글 텍스트입니다.",
        fontsize=14.0
    )
    assert success, "텍스트 추가 실패"
    assert engine.can_undo, "언두 스택이 활성화되지 않음"

    # 2) 텍스트 삭제/가리기 (화이트아웃) 테스트
    print("-> 화이트아웃 (텍스트 삭제/가리기) 테스트")
    erase_rect = fitz.Rect(60, 60, 300, 100)
    success = engine.add_whiteout(page_num=0, rect=erase_rect)
    assert success, "화이트아웃 실패"

    # 3) 형광펜 하이라이트 테스트
    print("-> 형광펜 하이라이트 테스트")
    hl_rect = fitz.Rect(60, 200, 250, 230)
    success = engine.add_highlight(page_num=0, rect=hl_rect)
    assert success, "형광펜 추가 실패"

    # 4) 손글씨/서명 그리기 테스트
    print("-> 손글씨/서명 그리기 테스트")
    ink_points = [(100, 300), (120, 320), (150, 290), (180, 340)]
    success = engine.add_ink(page_num=0, points=ink_points)
    assert success, "서명 그리기 실패"

    # 5) 렌더링 정상 검증
    print("-> 편집 후 QImage 렌더링 검증")
    qimg = engine.render_page(0, zoom=1.0)
    assert not qimg.isNull(), "편집 후 렌더링 실패"
    print(f"렌더링 성공 (크기: {qimg.width()} x {qimg.height()})")

    # 6) 실행 취소 (Undo) 테스트
    print("-> 실행 취소 (Undo) 테스트")
    assert engine.can_undo
    engine.undo()  # 서명 취소
    engine.undo()  # 형광펜 취소
    print("실행 취소 2단계 정상 완료")

    # 7) 문서 저장 및 재로드 검증
    print("-> 수정된 문서 저장 및 검증")
    saved_path = os.path.join(temp_dir, "saved_edited.pdf")
    engine.save(saved_path)
    engine.close()

    # 다시 열어서 무결성 확인
    verify_doc = fitz.open(saved_path)
    assert len(verify_doc) == 3, "저장 후 페이지 수 불일치"
    verify_doc.close()
    print("저장된 PDF 파일 무결성 확인 완료")

    print("\n[SUCCESS] 모든 PDF 편집 및 렌더링 검증 완료!")


if __name__ == "__main__":
    test_editing_features()
