"""
PDF 페이지 순서 변경 및 관리 기능 단위 테스트
"""
import os
import sys
import tempfile
from PySide6.QtWidgets import QApplication
import pymupdf as fitz

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.pdf_engine import PdfEngine
from ui.page_reorder_dialog import PageReorderDialog


def test_page_reorder():
    app = QApplication.instance() or QApplication(sys.argv)
    temp_dir = tempfile.mkdtemp()
    sample_pdf = os.path.join(temp_dir, "sample_reorder.pdf")

    print("=== 1. 테스트용 4페이지 PDF 생성 ===")
    doc = fitz.open()
    for i in range(1, 5):
        p = doc.new_page(width=400, height=500)
        p.insert_text((50, 50), f"PAGE_{i}_CONTENT", fontsize=20)
    doc.save(sample_pdf)
    doc.close()

    engine = PdfEngine()
    engine.load_document(sample_pdf)
    assert engine.page_count == 4

    def get_order():
        return [engine.doc[i].get_text().strip() for i in range(engine.page_count)]

    print(f"초기 순서: {get_order()}")
    assert get_order() == ["PAGE_1_CONTENT", "PAGE_2_CONTENT", "PAGE_3_CONTENT", "PAGE_4_CONTENT"]

    print("\n=== 2. 특정 페이지 단일 이동 (move_page) 테스트 ===")
    # 0번 페이지(PAGE 1)를 2번 위치로 이동 -> 1, 2, 0, 3 형태
    engine.move_page(0, 2)
    new_order = get_order()
    print(f"0번을 2번으로 이동 후: {new_order}")
    assert new_order == ["PAGE_2_CONTENT", "PAGE_1_CONTENT", "PAGE_3_CONTENT", "PAGE_4_CONTENT"]

    print("\n=== 3. 전체 페이지 임의 순서 재배치 (reorder_pages) 테스트 ===")
    # [3, 2, 1, 0] 역순으로 재배치
    ok = engine.reorder_pages([3, 2, 1, 0])
    assert ok
    reversed_order = get_order()
    print(f"역순 재배치 후: {reversed_order}")
    assert reversed_order == ["PAGE_4_CONTENT", "PAGE_3_CONTENT", "PAGE_1_CONTENT", "PAGE_2_CONTENT"]

    print("\n=== 4. PageReorderDialog 위젯 연동 검증 ===")
    dlg = PageReorderDialog(engine)
    assert dlg.list_widget.count() == 4
    # 다이얼로그 내 아이템 이동 시뮬레이션
    dlg.list_widget.setCurrentRow(0)
    dlg._move_down()
    assert dlg.current_order[1] == 0  # 0번째가 1번째로 이동 확인
    dlg.close()

    print("\n=== 5. 실행 취소 (Undo)로 원래 순서 복원 검증 ===")
    assert engine.can_undo
    engine.undo()  # 역순 취소
    print(f"언두 1단계 후: {get_order()}")
    assert get_order() == ["PAGE_2_CONTENT", "PAGE_1_CONTENT", "PAGE_3_CONTENT", "PAGE_4_CONTENT"]

    engine.undo()  # move_page 취소
    print(f"언두 2단계 후 (원상 복구): {get_order()}")
    assert get_order() == ["PAGE_1_CONTENT", "PAGE_2_CONTENT", "PAGE_3_CONTENT", "PAGE_4_CONTENT"]

    print("\n=== 6. 순서 변경 후 파일 저장 및 재로드 검증 ===")
    engine.reorder_pages([1, 0, 3, 2])
    saved_pdf = os.path.join(temp_dir, "saved_reordered.pdf")
    engine.save(saved_pdf)
    engine.close()

    verify_doc = fitz.open(saved_pdf)
    saved_order = [verify_doc[i].get_text().strip() for i in range(len(verify_doc))]
    print(f"저장된 파일 검증: {saved_order}")
    assert saved_order == ["PAGE_2_CONTENT", "PAGE_1_CONTENT", "PAGE_4_CONTENT", "PAGE_3_CONTENT"]
    verify_doc.close()

    print("\n[SUCCESS] 페이지 순서 변경 및 관리 기능 테스트 완벽 통과!")


if __name__ == "__main__":
    test_page_reorder()
