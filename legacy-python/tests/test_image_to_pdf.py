"""
이미지 순서별 PDF 변환 및 렌더링 엔진 검증 테스트
"""
import os
import sys
import tempfile
from PIL import Image, ImageDraw

# 경로 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.image_to_pdf import ImageToPdfConverter
from core.pdf_engine import PdfEngine
import pymupdf as fitz
from PySide6.QtGui import QGuiApplication


def test_images_to_pdf():
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    print("=== 1. 테스트 이미지 3장 생성 (빨강, 초록, 파랑) ===")
    temp_dir = tempfile.mkdtemp()
    img_paths = []

    colors = [
        ("red.png", (255, 0, 0), "Page 1 - Red"),
        ("green.jpg", (0, 255, 0), "Page 2 - Green"),
        ("blue.png", (0, 0, 255), "Page 3 - Blue"),
    ]

    for fname, color, label in colors:
        path = os.path.join(temp_dir, fname)
        # 800 x 600 크기 이미지 생성
        img = Image.new("RGB", (800, 600), color=color)
        draw = ImageDraw.Draw(img)
        draw.text((50, 50), label, fill=(255, 255, 255))
        img.save(path)
        img_paths.append(path)
        print(f"생성됨: {path} ({img.size})")

    output_pdf = os.path.join(temp_dir, "merged_result.pdf")

    print("\n=== 2. 이미지들을 순서대로 PDF로 변환 (A4 맞춤 모드) ===")
    out = ImageToPdfConverter.convert_images_to_pdf(
        image_paths=img_paths,
        output_pdf_path=output_pdf,
        fit_a4=True,
        margin=20.0
    )
    assert os.path.exists(out), "PDF 파일이 생성되지 않았습니다."
    print(f"변환 성공: {out} (크기: {os.path.getsize(out)} bytes)")

    print("\n=== 3. 생성된 PDF 무결성 검증 (PyMuPDF) ===")
    doc = fitz.open(out)
    print(f"총 페이지 수: {len(doc)} (기대값: 3)")
    assert len(doc) == 3, f"페이지 수가 일치하지 않습니다: {len(doc)} != 3"

    for i in range(len(doc)):
        page = doc[i]
        print(f"페이지 {i + 1}: 크기 = {page.rect.width} x {page.rect.height}")
    doc.close()

    print("\n=== 4. PdfEngine 렌더링 검증 ===")
    engine = PdfEngine()
    assert engine.load_document(out), "문서 로드 실패"
    assert engine.page_count == 3, "엔진 페이지 수 불일치"

    # 1페이지 렌더링
    qimg = engine.render_page(0, zoom=1.0)
    assert not qimg.isNull(), "QImage 렌더링 실패"
    print(f"렌더링 성공! QImage 크기: {qimg.width()} x {qimg.height()}")

    # 썸네일 검증
    thumb = engine.get_thumbnail(0, max_size=120)
    assert not thumb.isNull(), "썸네일 생성 실패"
    print(f"썸네일 성공! 크기: {thumb.width()} x {thumb.height()}")

    # 회전 검증
    engine.rotate_page(0, 90)
    assert engine.doc[0].rotation == 90, "페이지 회전 실패"
    print("페이지 90도 회전 정상 작동")

    engine.close()
    print("\n[SUCCESS] All tests passed successfully!")


if __name__ == "__main__":
    test_images_to_pdf()
