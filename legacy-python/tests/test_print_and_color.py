"""
인쇄 렌더링 파이프라인 및 폰트 컬러 변경 기능 단위 테스트
"""
import os
import sys
import tempfile
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtPrintSupport import QPrinter
import pymupdf as fitz

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui.main_window import MainWindow
from ui.text_edit_dialog import TextEditDialog
from core.pdf_engine import PdfEngine


def test_print_and_color():
    app = QApplication.instance() or QApplication(sys.argv)
    temp_dir = tempfile.mkdtemp()
    sample_pdf = os.path.join(temp_dir, "sample_print.pdf")

    print("=== 1. 테스트용 PDF 생성 ===")
    doc = fitz.open()
    p1 = doc.new_page(width=595, height=842)
    p1.insert_text((50, 100), "Print Test Page 1", fontsize=18)
    p2 = doc.new_page(width=595, height=842)
    p2.insert_text((50, 100), "Print Test Page 2", fontsize=18)
    doc.save(sample_pdf)
    doc.close()

    print("\n=== 2. 인쇄 렌더링 파이프라인 검증 ===")
    win = MainWindow()
    win.load_pdf(sample_pdf)

    # 가상 PDF 프린터 설정
    print_output = os.path.join(temp_dir, "printed_output.pdf")
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(print_output)

    # 실제 MainWindow의 인쇄 렌더링 메서드 호출
    win._render_print_pages(printer)

    assert os.path.exists(print_output), "인쇄 결과 파일이 생성되지 않음"
    assert os.path.getsize(print_output) > 0, "인쇄 파일이 비어 있음"

    verify_doc = fitz.open(print_output)
    print(f"인쇄 완료된 페이지 수: {len(verify_doc)} (기대값: 2)")
    assert len(verify_doc) == 2, f"인쇄 페이지 수 불일치: {len(verify_doc)} != 2"
    verify_doc.close()
    print("인쇄 렌더링 파이프라인 정상 작동 확인 완료!")

    print("\n=== 3. 텍스트 수정 및 폰트 컬러 변경 검증 ===")
    # 1) 빨간색 초기값으로 대화상자 생성
    red_color = QColor("#d32f2f")
    dlg = TextEditDialog(
        parent=None,
        initial_text="빨간색 텍스트",
        initial_color=red_color
    )
    data = dlg.get_data()
    print(f"초기 색상 검증: {data['color']}")
    assert abs(data["color"][0] - red_color.redF()) < 0.05, "초기 빨간색 설정 불일치"

    # 2) 파란색으로 색상 변경
    blue_color = QColor("#1976d2")
    dlg._set_color(blue_color)
    data_blue = dlg.get_data()
    print(f"변경된 색상 검증: {data_blue['color']}")
    assert abs(data_blue["color"][2] - blue_color.blueF()) < 0.05, "파란색 변경 실패"

    # 3) PdfEngine에 해당 색상으로 텍스트 추가/수정 반영
    engine = PdfEngine()
    engine.load_document(sample_pdf)
    ok = engine.add_text(
        page_num=0,
        x=50,
        y=200,
        text="파란색 폰트로 수정된 텍스트",
        color=data_blue["color"]
    )
    assert ok, "폰트 컬러 적용 텍스트 추가 실패"
    engine.close()

    print("\n[SUCCESS] 인쇄 기능 및 폰트 컬러 변경 기능 모든 테스트 완벽 통과!")


if __name__ == "__main__":
    test_print_and_color()
