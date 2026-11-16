"""
이미지 파일들을 지정된 순서대로 단일 PDF 파일로 변환 및 병합하는 모듈
"""
import os
from typing import List, Optional, Callable
import pymupdf as fitz  # PyMuPDF
from PIL import Image


class ImageToPdfConverter:
    """
    여러 이미지를 선택한 순서대로 단일 PDF로 변환하는 변환기
    """
    # A4 크기 (포인트 단위: 72 dpi 기준 595 x 842 pt)
    A4_WIDTH = 595.0
    A4_HEIGHT = 842.0

    @staticmethod
    def convert_images_to_pdf(
        image_paths: List[str],
        output_pdf_path: str,
        fit_a4: bool = True,
        margin: float = 20.0,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> str:
        """
        지정된 이미지 경로 목록을 순서대로 하나의 PDF 파일로 저장합니다.

        :param image_paths: 변환할 이미지 파일 경로 목록 (순서대로 배치됨)
        :param output_pdf_path: 저장할 PDF 파일 경로
        :param fit_a4: True면 A4 페이지 규격에 맞춰 비율을 유지하며 여백 적용,
                       False면 이미지 본래 해상도/크기 1:1로 페이지 생성
        :param margin: A4 맞춤 시 페이지 테두리 여백 (pt 단위)
        :param progress_callback: 진행률 콜백 (현재 index, 총 개수)
        :return: 저장된 파일 경로
        """
        if not image_paths:
            raise ValueError("변환할 이미지 목록이 비어 있습니다.")

        doc = fitz.open()

        try:
            total = len(image_paths)
            for idx, img_path in enumerate(image_paths):
                if not os.path.exists(img_path):
                    continue

                if progress_callback:
                    progress_callback(idx + 1, total)

                # 이미지 정보 확인
                with Image.open(img_path) as pil_img:
                    orig_w, orig_h = pil_img.size

                if fit_a4:
                    # 가로/세로 비율에 맞춰 A4 방향 결정
                    is_landscape = orig_w > orig_h
                    page_w = ImageToPdfConverter.A4_HEIGHT if is_landscape else ImageToPdfConverter.A4_WIDTH
                    page_h = ImageToPdfConverter.A4_WIDTH if is_landscape else ImageToPdfConverter.A4_HEIGHT

                    # 여백을 제외한 가용 영역
                    avail_w = max(10.0, page_w - (margin * 2))
                    avail_h = max(10.0, page_h - (margin * 2))

                    # 이미지 비율 유지 스케일 계산
                    scale = min(avail_w / orig_w, avail_h / orig_h)
                    dest_w = orig_w * scale
                    dest_h = orig_h * scale

                    # 중앙 정렬
                    offset_x = (page_w - dest_w) / 2.0
                    offset_y = (page_h - dest_h) / 2.0

                    rect = fitz.Rect(offset_x, offset_y, offset_x + dest_w, offset_y + dest_h)
                    page = doc.new_page(width=page_w, height=page_h)
                    page.insert_image(rect, filename=img_path)
                else:
                    # 원본 해상도 1:1 그대로 페이지 생성
                    # 72 DPI 기준 환산 (포인트 = 픽셀 * 72 / 96 대략적 표준)
                    # 직접 픽셀 크기에 맞춰 페이지 생성
                    page = doc.new_page(width=float(orig_w), height=float(orig_h))
                    rect = fitz.Rect(0, 0, float(orig_w), float(orig_h))
                    page.insert_image(rect, filename=img_path)

            doc.save(output_pdf_path)
            return output_pdf_path
        finally:
            doc.close()
