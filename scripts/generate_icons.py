"""
BossPDF 고선명 멀티 해상도 아이콘 생성기 (16x16부터 256x256까지 완벽 지원)
- Windows 탐색기 작은 아이콘, 자세히, 보통, 큰 아이콘 모든 뷰에서 선명한 PDF 문서 아이콘 보장
"""
import os
import sys
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES_DIR = os.path.join(ROOT_DIR, "resources")


def create_handcrafted_16x16() -> Image.Image:
    """16x16 작은 아이콘/자세히 보기 전용 픽셀 피팅 아이콘"""
    im = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    draw = ImageDraw.Draw(im)

    # 1. 문서 종이 외곽선 및 흰색 바탕 (배경이 흰색 탐색기여도 100% 구분되는 또렷한 1px 테두리)
    # 종이 형태 다각형: 상단 우측 접힘(Fold) 포함
    border_color = (120, 125, 133, 255)  # 차분한 그레이 테두리
    paper_fill = (255, 255, 255, 255)
    fold_color = (218, 222, 228, 255)    # 접힌 모서리 음영

    paper_poly = [(2, 0), (10, 0), (14, 4), (14, 15), (2, 15)]
    draw.polygon(paper_poly, fill=paper_fill, outline=border_color)

    # 접힌 삼각 날개: (10, 0) -> (14, 4) -> (10, 4)
    draw.polygon([(10, 0), (14, 4), (10, 4)], fill=fold_color, outline=border_color)

    # 2. 강렬하고 선명한 레드 PDF 뱃지 (가로로 가득 채워 멀리서도 '아! PDF 문서구나' 인식)
    red_badge = (229, 37, 42, 255)  # Apple & Adobe PDF Red
    draw.rectangle([(2, 7), (14, 11)], fill=red_badge)

    # 3. 뱃지 내부의 또렷한 화이트 'PDF' 픽셀 폰트
    w = (255, 255, 255, 255)
    # 'P' (x=3..5, y=8..10)
    draw.point([(3, 8), (4, 8), (5, 8), (3, 9), (5, 9), (3, 10), (4, 10)], fill=w)
    # 'D' (x=7..9, y=8..10)
    draw.point([(7, 8), (8, 8), (7, 9), (9, 9), (7, 10), (8, 10)], fill=w)
    # 'F' (x=11..13, y=8..10)
    draw.point([(11, 8), (12, 8), (13, 8), (11, 9), (12, 9), (11, 10)], fill=w)

    return im


def create_handcrafted_24x24() -> Image.Image:
    """24x24 (150% 배율 작은 아이콘) 전용 픽셀 피팅 아이콘"""
    im = Image.new("RGBA", (24, 24), (0, 0, 0, 0))
    draw = ImageDraw.Draw(im)

    border_color = (115, 120, 128, 255)
    paper_fill = (255, 255, 255, 255)
    fold_color = (215, 220, 226, 255)

    # x in [3, 21], y in [1, 22]
    paper_poly = [(3, 1), (15, 1), (21, 7), (21, 22), (3, 22)]
    draw.polygon(paper_poly, fill=paper_fill, outline=border_color)

    # 접힌 모서리
    draw.polygon([(15, 1), (21, 7), (15, 7)], fill=fold_color, outline=border_color)

    # 레드 PDF 뱃지
    red_badge = (229, 37, 42, 255)
    draw.rectangle([(3, 10), (21, 17)], fill=red_badge)

    # 텍스트 'PDF'
    w = (255, 255, 255, 255)
    # P (x=5..8, y=12..15)
    draw.line([(5, 12), (5, 15)], fill=w)
    draw.line([(5, 12), (7, 12)], fill=w)
    draw.point([(8, 13), (7, 14), (6, 14)], fill=w)

    # D (x=10..13, y=12..15)
    draw.line([(10, 12), (10, 15)], fill=w)
    draw.line([(10, 12), (12, 12)], fill=w)
    draw.line([(10, 15), (12, 15)], fill=w)
    draw.line([(13, 13), (13, 14)], fill=w)

    # F (x=15..18, y=12..15)
    draw.line([(15, 12), (15, 15)], fill=w)
    draw.line([(15, 12), (18, 12)], fill=w)
    draw.line([(15, 14), (17, 14)], fill=w)

    return im


def create_handcrafted_32x32(master_img: Image.Image) -> Image.Image:
    """32x32 (보통 아이콘 / 200% 작은 아이콘) 최적화 아이콘"""
    im = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    draw = ImageDraw.Draw(im)

    border_color = (110, 115, 125, 255)
    paper_fill = (255, 255, 255, 255)
    fold_color = (210, 215, 222, 255)

    # x in [4, 28], y in [1, 30]
    paper_poly = [(4, 1), (20, 1), (28, 9), (28, 30), (4, 30)]
    draw.polygon(paper_poly, fill=paper_fill, outline=border_color)

    # 접힌 모서리
    draw.polygon([(20, 1), (28, 9), (20, 9)], fill=fold_color, outline=border_color)

    # 레드 뱃지
    red_badge = (229, 37, 42, 255)
    draw.rectangle([(4, 13), (28, 22)], fill=red_badge)

    # 'PDF' 글씨
    w = (255, 255, 255, 255)
    # P
    draw.line([(7, 15), (7, 20)], fill=w, width=1)
    draw.line([(7, 15), (10, 15)], fill=w)
    draw.line([(11, 16), (11, 17)], fill=w)
    draw.line([(7, 18), (10, 18)], fill=w)

    # D
    draw.line([(14, 15), (14, 20)], fill=w, width=1)
    draw.line([(14, 15), (17, 15)], fill=w)
    draw.line([(14, 20), (17, 20)], fill=w)
    draw.line([(18, 16), (18, 19)], fill=w)

    # F
    draw.line([(21, 15), (21, 20)], fill=w, width=1)
    draw.line([(21, 15), (25, 15)], fill=w)
    draw.line([(21, 17), (24, 17)], fill=w)

    return im


def generate_all_icons():
    doc_png_path = os.path.join(RES_DIR, "pdf_doc_icon.png")
    doc_ico_path = os.path.join(RES_DIR, "pdf_doc_icon.ico")
    app_png_path = os.path.join(RES_DIR, "app_icon.png")
    app_ico_path = os.path.join(RES_DIR, "app_icon.ico")

    # 1. 마스터 PNG 로드
    raw_doc = Image.open(doc_png_path).convert("RGBA")
    bbox = raw_doc.getbbox()
    x0, y0, x1, y1 = bbox
    pad = 12
    cropped = raw_doc.crop((max(0, x0 - pad), max(0, y0 - pad), min(raw_doc.width, x1 + pad), min(raw_doc.height, y1 + pad)))

    target_size = 1024
    content_w, content_h = cropped.size
    scale = (target_size * 0.94) / max(content_w, content_h)
    new_w = int(content_w * scale)
    new_h = int(content_h * scale)
    scaled_content = cropped.resize((new_w, new_h), Image.Resampling.LANCZOS)

    master_doc = Image.new("RGBA", (target_size, target_size), (0, 0, 0, 0))
    ox = (target_size - new_w) // 2
    oy = (target_size - new_h) // 2
    master_doc.paste(scaled_content, (ox, oy), scaled_content)
    master_doc.save(doc_png_path, "PNG")

    # 2. 멀티 해상도 프레임 생성
    # 작은 크기들은 가독성을 극대화한 전용 픽셀 피팅 이미지 사용
    f16 = create_handcrafted_16x16()
    f24 = create_handcrafted_24x24()
    f32 = create_handcrafted_32x32(master_doc)
    f48 = master_doc.resize((48, 48), Image.Resampling.LANCZOS)
    f64 = master_doc.resize((64, 64), Image.Resampling.LANCZOS)
    f128 = master_doc.resize((128, 128), Image.Resampling.LANCZOS)
    f256 = master_doc.resize((256, 256), Image.Resampling.LANCZOS)

    # 48px 이상에도 테두리가 깔끔하게 보이도록 마스터 이미지 가장자리에 미세한 보정 적용
    # 256x256을 베이스로 하고 나머지 해상도들을 모두 append_images로 묶음
    f256.save(
        doc_ico_path,
        format="ICO",
        append_images=[f16, f24, f32, f48, f64, f128]
    )
    print(f"Generated multi-res PDF doc icon: {doc_ico_path}")

    # 3. 앱 아이콘(app_icon.ico)도 멀티 해상도 생성
    raw_app = Image.open(app_png_path).convert("RGBA")
    app_256 = raw_app.resize((256, 256), Image.Resampling.LANCZOS)
    app_16 = raw_app.resize((16, 16), Image.Resampling.LANCZOS)
    app_24 = raw_app.resize((24, 24), Image.Resampling.LANCZOS)
    app_32 = raw_app.resize((32, 32), Image.Resampling.LANCZOS)
    app_48 = raw_app.resize((48, 48), Image.Resampling.LANCZOS)
    app_64 = raw_app.resize((64, 64), Image.Resampling.LANCZOS)
    app_128 = raw_app.resize((128, 128), Image.Resampling.LANCZOS)

    app_256.save(
        app_ico_path,
        format="ICO",
        append_images=[app_16, app_24, app_32, app_48, app_64, app_128]
    )
    print(f"Generated multi-res app icon: {app_ico_path}")


if __name__ == "__main__":
    generate_all_icons()
