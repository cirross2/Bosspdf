import os
import pytest
import pymupdf as fitz
from PIL import Image
from core.pdf_engine import PdfEngine
from ui.page_export_dialog import PageExportDialog
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def sample_pdf(tmp_path):
    pdf_path = str(tmp_path / "sample_5pages.pdf")
    doc = fitz.open()
    for i in range(5):
        page = doc.new_page(width=400, height=500)
        page.insert_text((50, 50), f"Content of Page {i + 1}")
    doc.save(pdf_path)
    doc.close()
    return pdf_path


def test_export_pages_to_pdf(sample_pdf, tmp_path):
    engine = PdfEngine()
    engine.load_document(sample_pdf)
    assert engine.page_count == 5

    out_pdf = str(tmp_path / "exported_pages_1_3_5.pdf")
    res = engine.export_pages_to_pdf([0, 2, 4], out_pdf)
    assert os.path.exists(res)

    verify_doc = fitz.open(res)
    assert len(verify_doc) == 3
    assert "Page 1" in verify_doc[0].get_text()
    assert "Page 3" in verify_doc[1].get_text()
    assert "Page 5" in verify_doc[2].get_text()
    verify_doc.close()
    engine.close()


def test_export_pages_as_images(sample_pdf, tmp_path):
    engine = PdfEngine()
    engine.load_document(sample_pdf)

    out_dir = str(tmp_path / "images")
    files = engine.export_pages_as_images([1, 3], out_dir, prefix="test_page", fmt="png", dpi=100)
    assert len(files) == 2
    for f in files:
        assert os.path.exists(f)
        with Image.open(f) as im:
            assert im.format == "PNG"
            assert im.width > 0 and im.height > 0
    engine.close()


def test_export_stitched_image(sample_pdf, tmp_path):
    engine = PdfEngine()
    engine.load_document(sample_pdf)

    out_stitched = str(tmp_path / "stitched_long.png")
    res = engine.export_stitched_image([0, 1, 2], out_stitched, dpi=100, spacing=15)
    assert os.path.exists(res)

    with Image.open(res) as im:
        assert im.format == "PNG"
        # Total height should be roughly 3 * page_height + 2 * spacing
        assert im.height > 1000
        assert im.width > 0
    engine.close()


def test_parse_selected_pages_custom_ranges(sample_pdf, qapp):
    engine = PdfEngine()
    engine.load_document(sample_pdf)

    dlg = PageExportDialog(engine=engine, current_page=1)
    dlg.rb_custom_range.setChecked(True)

    # 1. Standard range
    dlg.txt_range.setText("1, 3, 5")
    assert dlg.parse_selected_pages() == [0, 2, 4]

    # 2. Hyphen range
    dlg.txt_range.setText("2-4")
    assert dlg.parse_selected_pages() == [1, 2, 3]

    # 3. Mixed range with spaces and out of bound
    dlg.txt_range.setText("1, 3-4, 99")
    assert dlg.parse_selected_pages() == [0, 2, 3]

    # 4. All pages
    dlg.rb_all_pages.setChecked(True)
    assert dlg.parse_selected_pages() == [0, 1, 2, 3, 4]

    # 5. Current page
    dlg.rb_cur_page.setChecked(True)
    assert dlg.parse_selected_pages() == [1]

    dlg.close()
    engine.close()


def test_viewer_current_page_and_dialog_integration(sample_pdf, qapp):
    from ui.viewer_widget import PdfViewerWidget
    engine = PdfEngine()
    engine.load_document(sample_pdf)
    viewer = PdfViewerWidget()
    viewer.set_engine(engine)

    assert hasattr(viewer, "current_page")
    assert viewer.current_page == 0

    # Dialog initialized with viewer.current_page
    dlg = PageExportDialog(engine=engine, current_page=viewer.current_page)
    assert dlg.current_page == 0
    assert dlg.rb_cur_page.text() == "현재 페이지만 (1페이지)"
    dlg.close()
    engine.close()

