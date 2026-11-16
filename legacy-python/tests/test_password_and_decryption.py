import os
import pytest
import pymupdf as fitz
from core.pdf_engine import PdfEngine, EncryptedPdfError, InvalidPasswordError


@pytest.fixture
def encrypted_pdf(tmp_path):
    pdf_path = str(tmp_path / "protected.pdf")
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Confidential BossPDF Document")
    doc.save(
        pdf_path,
        encryption=fitz.PDF_ENCRYPT_AES_256,
        user_pw="secret123",
        owner_pw="master123"
    )
    doc.close()
    return pdf_path


def test_load_encrypted_without_password_raises_error(encrypted_pdf):
    engine = PdfEngine()
    with pytest.raises(EncryptedPdfError):
        engine.load_document(encrypted_pdf)
    engine.close()


def test_load_encrypted_with_wrong_password_raises_error(encrypted_pdf):
    engine = PdfEngine()
    with pytest.raises(InvalidPasswordError):
        engine.load_document(encrypted_pdf, password="wrong_pass")
    engine.close()


def test_load_encrypted_with_correct_password(encrypted_pdf):
    engine = PdfEngine()
    success = engine.load_document(encrypted_pdf, password="secret123")
    assert success is True
    assert engine.is_loaded()
    assert engine.page_count == 1
    assert engine.was_encrypted is True
    assert engine.password_unlocked is True

    # Check page rendering
    img = engine.render_page(0, zoom=1.0)
    assert not img.isNull()
    engine.close()


def test_save_with_password_removal(encrypted_pdf, tmp_path):
    engine = PdfEngine()
    engine.load_document(encrypted_pdf, password="secret123")

    # Save to a new decrypted path
    decrypted_path = str(tmp_path / "unprotected.pdf")
    saved_path = engine.save(decrypted_path, remove_password=True)
    assert os.path.exists(saved_path)
    engine.close()

    # Re-open the saved PDF without password
    engine2 = PdfEngine()
    success2 = engine2.load_document(decrypted_path)
    assert success2 is True
    assert engine2.is_loaded()
    assert engine2.page_count == 1
    assert engine2.is_encrypted is False
    assert engine2.was_encrypted is False

    text = engine2.doc[0].get_text().strip()
    assert "Confidential BossPDF Document" in text
    engine2.close()


def test_save_in_place_with_password_removal(encrypted_pdf):
    engine = PdfEngine()
    engine.load_document(encrypted_pdf, password="secret123")
    assert engine.was_encrypted is True

    # Save over the same file with password removal
    engine.save(remove_password=True)
    engine.close()

    # Verify that the original file now opens without requiring password
    engine2 = PdfEngine()
    success = engine2.load_document(encrypted_pdf)
    assert success is True
    assert engine2.is_loaded()
    assert engine2.is_encrypted is False
    assert engine2.was_encrypted is False
    engine2.close()


def test_editing_and_undo_on_unlocked_document(encrypted_pdf):
    engine = PdfEngine()
    engine.load_document(encrypted_pdf, password="secret123")

    # Add text
    added = engine.add_text(page_num=0, x=50, y=150, text="New Unlocked Text", fontsize=14.0)
    assert added is True
    assert engine.can_undo is True

    # Undo
    undo_res = engine.undo()
    assert undo_res is True
    engine.close()
