"""
PDF 문서 로드, 렌더링, 페이지 조작 및 텍스트/마크업 편집 엔진
(글꼴, 크기, 스타일, 자동 줄맞춤 스냅 지원)
"""
import os
import math
import asyncio
import unicodedata
from typing import Optional, List, Tuple, Dict, Any
import pymupdf as fitz  # PyMuPDF
from PySide6.QtGui import QImage, QPixmap
from PIL import Image
from core.font_manager import FontManager


class EncryptedPdfError(Exception):
    """비밀번호가 필요한 암호화 PDF 문서 예외"""
    pass


class InvalidPasswordError(Exception):
    """입력된 비밀번호가 올바르지 않은 경우의 예외"""
    pass


class PdfEngine:
    """
    PyMuPDF 기반 PDF 로드, 페이지 렌더링 및 편집 제어 클래스
    """
    # 윈도우 시스템 폰트 매핑 테이블
    FONT_REGISTRY = {
        "맑은 고딕": {
            "regular": "C:/Windows/Fonts/malgun.ttf",
            "bold": "C:/Windows/Fonts/malgunbd.ttf"
        },
        "굴림": {
            "regular": "C:/Windows/Fonts/gulim.ttc",
            "bold": "C:/Windows/Fonts/gulim.ttc"
        },
        "바탕": {
            "regular": "C:/Windows/Fonts/batang.ttc",
            "bold": "C:/Windows/Fonts/batang.ttc"
        },
        "돋움": {
            "regular": "C:/Windows/Fonts/gulim.ttc",
            "bold": "C:/Windows/Fonts/gulim.ttc"
        },
        "Arial": {
            "regular": "C:/Windows/Fonts/arial.ttf",
            "bold": "C:/Windows/Fonts/arialbd.ttf"
        },
        "Times New Roman": {
            "regular": "C:/Windows/Fonts/times.ttf",
            "bold": "C:/Windows/Fonts/timesbd.ttf"
        },
        "Courier New": {
            "regular": "C:/Windows/Fonts/cour.ttf",
            "bold": "C:/Windows/Fonts/courbd.ttf"
        }
    }

    def __init__(self):
        self.doc: Optional[fitz.Document] = None
        self.file_path: Optional[str] = None
        self.undo_stack: List[bytes] = []  # 실행 취소용 PDF 바이트 스냅샷
        self.is_encrypted: bool = False
        self.was_encrypted: bool = False
        self.password_unlocked: bool = False
        # 페이지별 이미지 OCR 결과 캐시: page_idx -> List[Dict{"text": str, "bbox": fitz.Rect, "chars": List[Tuple[str, fitz.Rect]]}]
        self._ocr_cache: Dict[int, List[Dict[str, Any]]] = {}

    def _push_undo_state(self):
        """현재 상태를 언두 스택에 저장 (최대 10단계)"""
        if self.is_loaded():
            snapshot = self.doc.tobytes(garbage=0, deflate=False)
            self.undo_stack.append(snapshot)
            if len(self.undo_stack) > 10:
                self.undo_stack.pop(0)
            self._ocr_cache.clear()

    def undo(self) -> bool:
        """이전 편집 상태로 되돌리기"""
        if not self.undo_stack:
            return False
        prev_bytes = self.undo_stack.pop()
        if self.doc:
            self.doc.close()
        self.doc = fitz.open("pdf", prev_bytes)
        self._ocr_cache.clear()
        return True

    @property
    def can_undo(self) -> bool:
        return len(self.undo_stack) > 0

    def load_document(self, file_path: str, password: Optional[str] = None) -> bool:
        """PDF 파일을 열고 초기화합니다. 암호화 문서인 경우 비밀번호 인증을 수행합니다."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"파일을 찾을 수 없습니다: {file_path}")

        if self.doc:
            self.doc.close()

        self.file_path = file_path
        self.doc = fitz.open(file_path)
        self.is_encrypted = bool(self.doc.is_encrypted)
        self.was_encrypted = bool(self.doc.is_encrypted)
        self.password_unlocked = False

        if self.doc.is_encrypted and self.doc.needs_pass:
            if password is None:
                raise EncryptedPdfError("문서가 비밀번호로 암호화되어 있습니다.")
            auth_res = self.doc.authenticate(password)
            if auth_res <= 0:
                raise InvalidPasswordError("비밀번호가 일치하지 않습니다.")
            self.password_unlocked = True

        self.undo_stack.clear()
        self._ocr_cache.clear()
        return True

    def authenticate_doc(self, password: str) -> bool:
        """현재 열린 문서에 비밀번호 인증 수행"""
        if not self.is_loaded():
            return False
        res = self.doc.authenticate(password)
        if res > 0:
            self.password_unlocked = True
            return True
        return False

    def remove_password(self) -> None:
        """비밀번호 해제 플래그 설정 (이후 저장 시 암호 없이 저장)"""
        self.was_encrypted = False

    def is_loaded(self) -> bool:
        return self.doc is not None and not self.doc.is_closed

    @property
    def page_count(self) -> int:
        return len(self.doc) if self.is_loaded() else 0

    def get_page_rect(self, page_num: int) -> fitz.Rect:
        """페이지의 원본 크기 반환"""
        if not self.is_loaded() or page_num < 0 or page_num >= self.page_count:
            return fitz.Rect(0, 0, 595, 842)
        return self.doc[page_num].rect

    def render_page(self, page_num: int, zoom: float = 1.0, rotation: int = 0) -> QImage:
        """지정된 페이지를 QImage로 고화질 렌더링"""
        if not self.is_loaded():
            raise RuntimeError("열린 PDF 문서가 없습니다.")

        if page_num < 0 or page_num >= self.page_count:
            raise IndexError("페이지 범위를 벗어났습니다.")

        page = self.doc[page_num]
        mat = fitz.Matrix(zoom, zoom).prerotate(rotation)
        pix = page.get_pixmap(matrix=mat, alpha=False)

        img = QImage(
            pix.samples,
            pix.width,
            pix.height,
            pix.stride,
            QImage.Format.Format_RGB888
        )
        return img.copy()

    def get_thumbnail(self, page_num: int, max_size: int = 160) -> QPixmap:
        """사이드바 썸네일용 작은 이미지 생성"""
        if not self.is_loaded() or page_num < 0 or page_num >= self.page_count:
            return QPixmap()

        page = self.doc[page_num]
        rect = page.rect
        scale = max_size / max(rect.width, rect.height)
        mat = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=mat, alpha=False)

        qimg = QImage(
            pix.samples,
            pix.width,
            pix.height,
            pix.stride,
            QImage.Format.Format_RGB888
        )
        return QPixmap.fromImage(qimg)

    # ==================== 스마트 줄맞춤 분석 (Smart Text Alignment) ====================

    def find_nearest_text_line(
        self,
        page_num: int,
        target_x: float,
        target_y: float,
        max_distance: float = 120.0
    ) -> Dict[str, Any]:
        """
        클릭/지정한 좌표 주변에서 가장 인접한 기존 텍스트 줄을 감지하여
        스마트 줄맞춤(X좌표 마진 스냅, Y좌표 줄바꿈 스냅, 폰트 크기 감지) 데이터를 반환합니다.
        """
        result = {
            "found": False,
            "snap_x": target_x,
            "snap_y": target_y,
            "suggested_size": 12.0,
            "suggested_font": "맑은 고딕",
            "nearest_text": "",
            "distance": 9999.0
        }

        if not self.is_loaded() or page_num < 0 or page_num >= self.page_count:
            return result

        page = self.doc[page_num]
        text_dict = page.get_text("dict")

        min_dist = float("inf")
        best_span = None
        best_bbox = None

        for b in text_dict.get("blocks", []):
            if "lines" not in b:
                continue
            for line in b["lines"]:
                line_bbox = line["bbox"]  # (x0, y0, x1, y1)
                # 라인 중심까지 거리 계산
                mid_x = (line_bbox[0] + line_bbox[2]) / 2.0
                mid_y = (line_bbox[1] + line_bbox[3]) / 2.0
                dist = math.hypot(target_x - line_bbox[0], target_y - mid_y)

                if dist < min_dist and dist <= max_distance:
                    min_dist = dist
                    best_bbox = line_bbox
                    if line.get("spans"):
                        best_span = line["spans"][0]

        if not best_bbox and self._needs_ocr_for_page(page_num):
            ocr_lines = self._ensure_page_ocr(page_num)
            for oline in ocr_lines:
                lb = oline["bbox"]
                mid_y = (lb.y0 + lb.y1) / 2.0
                dist = math.hypot(target_x - lb.x0, target_y - mid_y)
                if dist < min_dist and dist <= max_distance:
                    min_dist = dist
                    best_bbox = (lb.x0, lb.y0, lb.x1, lb.y1)
                    best_span = {
                        "size": round(max(8.0, min(48.0, (lb.y1 - lb.y0) * 0.85)), 1),
                        "font": "맑은 고딕",
                        "text": oline["text"]
                    }

        if best_bbox and best_span:
            x0, y0, x1, y1 = best_bbox
            line_height = max(10.0, y1 - y0)

            # X좌표 스냅: 기존 줄의 왼쪽 시작점에 수평 정렬
            snapped_x = round(x0, 1)

            # Y좌표 스냅:
            # 클릭 위치가 해당 줄의 내부/인접이면 해당 줄에 맞추고, 아래쪽이면 줄간격 맞춰 다음 줄로 배치
            if target_y < y0:
                snapped_y = round(y0 - line_height * 1.2, 1)  # 윗줄
            elif target_y <= y1 + (line_height * 0.5):
                snapped_y = round(y0, 1)  # 같은 줄
            else:
                snapped_y = round(y1 + (line_height * 0.25), 1)  # 아랫줄 줄맞춤

            # 폰트 크기 감지
            detected_size = round(best_span.get("size", 12.0), 1)
            detected_font = best_span.get("font", "맑은 고딕")

            result.update({
                "found": True,
                "snap_x": snapped_x,
                "snap_y": snapped_y,
                "suggested_size": detected_size if 6.0 <= detected_size <= 72.0 else 12.0,
                "suggested_font": "맑은 고딕",
                "nearest_text": best_span.get("text", "").strip(),
                "distance": min_dist
            })

        return result

    # ==================== 고급 편집 기능 (Editing Features) ====================

    def _resolve_font_file(self, family: str, is_bold: bool = False, is_italic: bool = False) -> Tuple[str, str]:
        """FontManager를 통해 윈도우 전체 시스템 폰트의 실제 ttf/otf/ttc 파일 경로 및 별칭 반환"""
        path = FontManager.get_font_file_path(family, is_bold=is_bold, is_italic=is_italic)
        clean_fam = "".join(c for c in family if c.isalnum() or c == "_")
        if not clean_fam:
            clean_fam = "sysfont"
        alias = f"f_{clean_fam}_{'b' if is_bold else 'r'}{'i' if is_italic else ''}"
        return path, alias

    def add_text(
        self,
        page_num: int,
        x: float,
        y: float,
        text: str,
        font_family: str = "맑은 고딕",
        fontsize: float = 14.0,
        is_bold: bool = False,
        is_italic: bool = False,
        color: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        align: int = 0,  # 0: Left, 1: Center, 2: Right
        width: float = 300.0,
        height: float = 80.0
    ) -> bool:
        """
        시스템 글꼴, 크기, 스타일(Bold/Italic), 색상, 정렬을 반영하여 텍스트 상자 추가
        """
        if not self.is_loaded() or page_num < 0 or page_num >= self.page_count or not text:
            return False

        self._push_undo_state()
        page = self.doc[page_num]

        font_path, font_alias = self._resolve_font_file(font_family, is_bold=is_bold, is_italic=is_italic)

        if os.path.exists(font_path):
            try:
                page.insert_font(fontname=font_alias, fontfile=font_path)
            except Exception:
                font_alias = "helv"
        else:
            font_alias = "helv"

        # 정렬 변환
        fitz_align = fitz.TEXT_ALIGN_LEFT
        if align == 1:
            fitz_align = fitz.TEXT_ALIGN_CENTER
        elif align == 2:
            fitz_align = fitz.TEXT_ALIGN_RIGHT

        rect = fitz.Rect(x, y, x + width, y + height)
        page.insert_textbox(
            rect,
            text,
            fontsize=fontsize,
            fontname=font_alias,
            color=color,
            align=fitz_align
        )
        return True

    def add_whiteout(self, page_num: int, rect: fitz.Rect) -> bool:
        """특정 사각형 영역을 흰색으로 완전히 덮어 텍스트나 그림 삭제/가리기"""
        if not self.is_loaded() or page_num < 0 or page_num >= self.page_count:
            return False

        self._push_undo_state()
        page = self.doc[page_num]
        page.draw_rect(rect, color=(1.0, 1.0, 1.0), fill=(1.0, 1.0, 1.0), overlay=True)
        return True

    def add_highlight(
        self,
        page_num: int,
        rect: fitz.Rect,
        color: Tuple[float, float, float] = (1.0, 0.9, 0.2)
    ) -> bool:
        """특정 사각형 영역에 반투명 형광펜(하이라이트) 칠하기"""
        if not self.is_loaded() or page_num < 0 or page_num >= self.page_count:
            return False

        self._push_undo_state()
        page = self.doc[page_num]
        page.draw_rect(rect, color=None, fill=color, fill_opacity=0.4, overlay=True)
        return True

    def add_ink(
        self,
        page_num: int,
        points: List[Tuple[float, float]],
        color: Tuple[float, float, float] = (0.1, 0.3, 0.9),
        width: float = 2.0
    ) -> bool:
        """자유형 손글씨 / 서명 그리기"""
        if not self.is_loaded() or page_num < 0 or page_num >= self.page_count or len(points) < 2:
            return False

        self._push_undo_state()
        page = self.doc[page_num]
        fitz_points = [fitz.Point(pt[0], pt[1]) for pt in points]
        page.draw_polyline(fitz_points, color=color, width=width, overlay=True)
        return True

    # ==================== 페이지 구조 조작 ====================

    def rotate_page(self, page_num: int, angle: int = 90) -> None:
        """특정 페이지 90도 회전"""
        if not self.is_loaded():
            return
        self._push_undo_state()
        page = self.doc[page_num]
        page.set_rotation((page.rotation + angle) % 360)

    def delete_page(self, page_num: int) -> None:
        """특정 페이지 삭제"""
        if not self.is_loaded() or self.page_count <= 1:
            raise ValueError("최소 1페이지 이상 남아있어야 삭제할 수 있습니다.")
        self._push_undo_state()
        self.doc.delete_page(page_num)

    def move_page(self, from_idx: int, to_idx: int) -> bool:
        """특정 페이지를 다른 위치로 이동"""
        if not self.is_loaded() or from_idx == to_idx:
            return False
        if not (0 <= from_idx < self.page_count and 0 <= to_idx < self.page_count):
            return False
        self._push_undo_state()
        self.doc.move_page(from_idx, to_idx)
        return True

    def reorder_pages(self, new_order: List[int]) -> bool:
        """
        지정된 인덱스 목록(0-indexed)에 따라 전체 페이지 순서를 재배치합니다.
        예: [2, 0, 1] -> 3페이지가 1페이지로, 1페이지가 2페이지로 이동
        """
        if not self.is_loaded() or len(new_order) != self.page_count:
            return False
        self._push_undo_state()
        self.doc.select(new_order)
        return True

    def save(self, output_path: Optional[str] = None, remove_password: bool = True) -> str:
        """문서 저장 (remove_password=True일 경우 비밀번호 암호화를 해제하여 저장)"""
        if not self.is_loaded():
            raise RuntimeError("저장할 문서가 없습니다.")

        target = output_path or self.file_path
        if target == self.file_path:
            tmp_path = target + ".tmp"
            if remove_password:
                self.doc.save(tmp_path, encryption=fitz.PDF_ENCRYPT_NONE, garbage=3, deflate=True)
            else:
                self.doc.save(tmp_path, garbage=3, deflate=True)
            self.doc.close()
            if os.path.exists(target):
                os.remove(target)
            os.rename(tmp_path, target)
            self.doc = fitz.open(target)
            if remove_password:
                self.was_encrypted = False
                self.is_encrypted = False
                self.password_unlocked = False
        else:
            if remove_password:
                self.doc.save(target, encryption=fitz.PDF_ENCRYPT_NONE, garbage=3, deflate=True)
                self.was_encrypted = False
                self.is_encrypted = False
                self.password_unlocked = False
            else:
                self.doc.save(target, garbage=3, deflate=True)
            self.file_path = target
        return target

    def close(self):
        """문서 닫기"""
        if self.doc:
            self.doc.close()
            self.doc = None
            self.file_path = None
        self.is_encrypted = False
        self.was_encrypted = False
        self.password_unlocked = False
        self.undo_stack.clear()
        self._ocr_cache.clear()

    # ==================== 페이지 추출 및 내보내기 / 이미지 변환 ====================

    def export_pages_to_pdf(self, page_indices: List[int], output_path: str) -> str:
        """
        선택된 페이지 목록(0-indexed)만 추출하여 새로운 독립 PDF 파일로 저장합니다.
        """
        if not self.is_loaded():
            raise RuntimeError("열린 PDF 문서가 없습니다.")
        if not page_indices:
            raise ValueError("내보낼 페이지가 선택되지 않았습니다.")

        valid_indices = [idx for idx in page_indices if 0 <= idx < self.page_count]
        if not valid_indices:
            raise ValueError("유효한 페이지 번호가 없습니다.")

        new_doc = fitz.open()
        for idx in valid_indices:
            new_doc.insert_pdf(self.doc, from_page=idx, to_page=idx)

        new_doc.save(output_path, garbage=3, deflate=True)
        new_doc.close()
        return output_path

    def export_pages_as_images(
        self,
        page_indices: List[int],
        output_dir: str,
        prefix: str = "page",
        fmt: str = "png",
        dpi: int = 150
    ) -> List[str]:
        """
        선택된 페이지들을 개별 이미지 파일로 렌더링하여 지정된 폴더에 저장합니다.
        반환값: 생성된 이미지 파일 경로 목록
        """
        if not self.is_loaded():
            raise RuntimeError("열린 PDF 문서가 없습니다.")
        if not page_indices:
            raise ValueError("내보낼 페이지가 선택되지 않았습니다.")

        valid_indices = [idx for idx in page_indices if 0 <= idx < self.page_count]
        if not valid_indices:
            raise ValueError("유효한 페이지 번호가 없습니다.")

        os.makedirs(output_dir, exist_ok=True)
        saved_files = []
        fmt_clean = fmt.lower().strip().replace(".", "")

        for idx in valid_indices:
            page = self.doc[idx]
            pix = page.get_pixmap(dpi=dpi)
            filename = f"{prefix}_{idx + 1}.{fmt_clean}"
            filepath = os.path.join(output_dir, filename)

            if fmt_clean in ["jpg", "jpeg"]:
                im = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                im.save(filepath, "JPEG", quality=95)
            else:
                pix.save(filepath)

            saved_files.append(filepath)

        return saved_files

    def export_stitched_image(
        self,
        page_indices: List[int],
        output_path: str,
        dpi: int = 150,
        spacing: int = 10,
        bg_color: Tuple[int, int, int] = (255, 255, 255),
        direction: str = "vertical"
    ) -> str:
        """
        선택된 여러 페이지를 고화질로 렌더링한 후, 하나의 긴 이미지(웹툰/스크롤형)로 이어 붙여 저장합니다.
        """
        if not self.is_loaded():
            raise RuntimeError("열린 PDF 문서가 없습니다.")
        if not page_indices:
            raise ValueError("이어 붙일 페이지가 선택되지 않았습니다.")

        valid_indices = [idx for idx in page_indices if 0 <= idx < self.page_count]
        if not valid_indices:
            raise ValueError("유효한 페이지 번호가 없습니다.")

        images = []
        for idx in valid_indices:
            page = self.doc[idx]
            pix = page.get_pixmap(dpi=dpi)
            im = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            images.append(im)

        if not images:
            raise ValueError("렌더링된 이미지가 없습니다.")

        if direction == "vertical":
            total_w = max(im.width for im in images)
            total_h = sum(im.height for im in images) + spacing * (len(images) - 1)
            canvas = Image.new("RGB", (total_w, total_h), bg_color)

            current_y = 0
            for im in images:
                offset_x = (total_w - im.width) // 2
                canvas.paste(im, (offset_x, current_y))
                current_y += im.height + spacing
        else:
            total_w = sum(im.width for im in images) + spacing * (len(images) - 1)
            total_h = max(im.height for im in images)
            canvas = Image.new("RGB", (total_w, total_h), bg_color)

            current_x = 0
            for im in images:
                offset_y = (total_h - im.height) // 2
                canvas.paste(im, (current_x, offset_y))
                current_x += im.width + spacing

        ext = os.path.splitext(output_path)[1].lower()
        if ext in [".jpg", ".jpeg"]:
            canvas.save(output_path, "JPEG", quality=95)
        else:
            canvas.save(output_path, "PNG")

        return output_path

    # ==================== 문서 내 단어 검색 (텍스트 PDF + 스캔/이미지 PDF OCR 통합) ====================

    _CHO_GROUPS = [
        {"ㄱ", "ㅋ", "ㄲ"},
        {"ㄴ", "ㄷ", "ㅌ", "ㄸ"},
        {"ㅂ", "ㅍ", "ㅃ"},
        {"ㅅ", "ㅆ"},
        {"ㅈ", "ㅊ", "ㅉ"},
        {"ㅇ", "ㅎ"},
    ]
    _JUNG_GROUPS = [
        {"ㅏ", "ㅑ"},
        {"ㅓ", "ㅕ"},
        {"ㅗ", "ㅛ", "ㅜ", "ㅠ", "ㅡ", "ㅚ"},
        {"ㅐ", "ㅒ", "ㅔ", "ㅖ"},
    ]

    @staticmethod
    def _decompose_hangul(ch: str) -> Optional[Tuple[str, str, str]]:
        code = ord(ch) - 0xAC00
        if 0 <= code <= 11171:
            cho = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"[code // 588]
            jung = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"[(code % 588) // 28]
            jong = " ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"[code % 28]
            return (cho, jung, jong)
        return None

    @staticmethod
    def _same_jamo_group(a: str, b: str, groups: List[set]) -> bool:
        if a == b:
            return True
        return any(a in g and b in g for g in groups)

    @classmethod
    def _ocr_char_match(cls, c1: str, c2: str) -> bool:
        if c1 == c2:
            return True
        d1 = cls._decompose_hangul(c1)
        d2 = cls._decompose_hangul(c2)
        if not d1 or not d2:
            return False
        if d1[2] != d2[2]:
            return False
        if d1[0] == d2[0] and cls._same_jamo_group(d1[1], d2[1], cls._JUNG_GROUPS):
            return True
        if d1[1] == d2[1] and cls._same_jamo_group(d1[0], d2[0], cls._CHO_GROUPS):
            return True
        return False

    @classmethod
    def _match_query_in_chars(cls, chars_str: str, q: str) -> List[Tuple[int, int]]:
        n, m = len(chars_str), len(q)
        if m == 0 or m > n:
            return []
        matches: List[Tuple[int, int]] = []
        i = 0
        while i <= n - m:
            if m == 1:
                if chars_str[i] == q[0]:
                    matches.append((i, i + 1))
                    i += 1
                    continue
            else:
                ok = True
                exact_cnt = 0
                for k in range(m):
                    if chars_str[i + k] == q[k]:
                        exact_cnt += 1
                    elif not cls._ocr_char_match(chars_str[i + k], q[k]):
                        ok = False
                        break
                if ok and exact_cnt >= max(1, m - 1):
                    matches.append((i, i + m))
                    i += m
                    continue
            i += 1
        return matches

    def _needs_ocr_for_page(self, page_idx: int) -> bool:
        if not self.is_loaded() or page_idx < 0 or page_idx >= self.page_count:
            return False
        page = self.doc[page_idx]
        if len(page.get_images()) > 0:
            return True
        txt = page.get_text("text").strip()
        return len(txt) < 30

    def _ensure_page_ocr(self, page_idx: int) -> List[Dict[str, Any]]:
        if page_idx in self._ocr_cache:
            return self._ocr_cache[page_idx]

        if not self._needs_ocr_for_page(page_idx):
            self._ocr_cache[page_idx] = []
            return []

        page = self.doc[page_idx]
        ocr_dpi = 180
        scale = 72.0 / float(ocr_dpi)
        parsed_lines: List[Dict[str, Any]] = []

        try:
            from winrt.windows.media.ocr import OcrEngine
            from winrt.windows.globalization import Language
            from winrt.windows.storage.streams import DataWriter
            from winrt.windows.graphics.imaging import SoftwareBitmap, BitmapPixelFormat

            pix = page.get_pixmap(dpi=ocr_dpi, alpha=True)
            engine = None
            for lang_tag in ("ko", "ko-KR", "en"):
                try:
                    lang_obj = Language(lang_tag)
                    if OcrEngine.is_language_supported(lang_obj):
                        engine = OcrEngine.try_create_from_language(lang_obj)
                        if engine is not None:
                            break
                except Exception:
                    continue
            if engine is None:
                engine = OcrEngine.try_create_from_user_profile_languages()

            if engine is not None:
                async def _run_winrt_ocr():
                    writer = DataWriter()
                    writer.write_bytes(pix.samples)
                    sb = SoftwareBitmap.create_copy_from_buffer(
                        writer.detach_buffer(),
                        BitmapPixelFormat.RGBA8,
                        pix.width,
                        pix.height
                    )
                    return await engine.recognize_async(sb)

                try:
                    loop = asyncio.new_event_loop()
                    try:
                        res = loop.run_until_complete(_run_winrt_ocr())
                    finally:
                        loop.close()
                except Exception:
                    res = None

                if res is not None:
                    for line in res.lines:
                        line_chars: List[Tuple[str, fitz.Rect]] = []
                        line_rect: Optional[fitz.Rect] = None
                        for w in line.words:
                            wt = unicodedata.normalize("NFC", w.text or "").strip()
                            if not wt:
                                continue
                            br = w.bounding_rect
                            x0 = br.x * scale
                            y0 = br.y * scale
                            w_pt = max(2.0, br.width * scale)
                            h_pt = max(2.0, br.height * scale)
                            w_rect = fitz.Rect(x0, y0, x0 + w_pt, y0 + h_pt)
                            line_rect = w_rect if line_rect is None else (line_rect | w_rect)
                            w_len = len(wt)
                            for idx_ch, ch in enumerate(wt):
                                if ch.isspace():
                                    continue
                                cx0 = x0 + w_pt * (idx_ch / w_len)
                                cx1 = x0 + w_pt * ((idx_ch + 1) / w_len)
                                char_rect = fitz.Rect(cx0, y0, cx1, y0 + h_pt)
                                line_chars.append((ch.lower(), char_rect))
                        if line_chars and line_rect is not None:
                            parsed_lines.append({
                                "text": unicodedata.normalize("NFC", line.text or "").strip(),
                                "bbox": line_rect,
                                "chars": line_chars,
                                "compact_str": "".join(c[0] for c in line_chars)
                            })
        except Exception:
            pass

        self._ocr_cache[page_idx] = parsed_lines
        return parsed_lines

    def warmup_next_ocr_page(self) -> bool:
        """
        백그라운드 유휴 타이머에서 호출하여 이미지 페이지를 1페이지씩 사전 OCR 캐싱합니다.
        더 캐싱할 페이지가 남아 있으면 True, 모두 완료되었으면 False 반환.
        """
        if not self.is_loaded():
            return False
        for page_idx in range(self.page_count):
            if page_idx not in self._ocr_cache:
                self._ensure_page_ocr(page_idx)
                return page_idx + 1 < self.page_count
        return False

    @staticmethod
    def _rects_overlap(r1: fitz.Rect, r2: fitz.Rect) -> bool:
        inter = fitz.Rect(r1) & fitz.Rect(r2)
        if inter.is_empty or inter.width <= 0 or inter.height <= 0:
            return False
        inter_area = inter.width * inter.height
        min_area = max(1.0, min(r1.width * r1.height, r2.width * r2.height))
        return (inter_area / min_area) >= 0.35

    def search_text(self, query: str) -> List[Tuple[int, fitz.Rect]]:
        """
        전체 페이지에서 검색어(query)를 찾아 (page_idx, fitz.Rect) 목록을 반환합니다.
        일반 텍스트 레이어 검색과 스캔/이미지 PDF용 Windows OCR 검색을 모두 지원합니다.
        """
        if not self.is_loaded() or not query or not query.strip():
            return []

        q_raw = query.strip()
        q_nfc = unicodedata.normalize("NFC", q_raw)
        q_nfd = unicodedata.normalize("NFD", q_raw)
        q_compact = "".join(q_nfc.lower().split())

        results: List[Tuple[int, fitz.Rect]] = []
        for page_idx in range(self.page_count):
            page = self.doc[page_idx]
            page_rects: List[fitz.Rect] = []

            # 1) PDF 내장 텍스트 레이어 검색 (NFC & NFD 모두 대응)
            for candidate_q in ([q_nfc, q_nfd] if q_nfc != q_nfd else [q_nfc]):
                for r in page.search_for(candidate_q):
                    if not any(self._rects_overlap(r, existing) for existing in page_rects):
                        page_rects.append(r)

            # 2) 이미지/스캔 기반 페이지인 경우 OCR 캐시 검색 병합
            if q_compact and self._needs_ocr_for_page(page_idx):
                ocr_lines = self._ensure_page_ocr(page_idx)
                for oline in ocr_lines:
                    chars = oline["chars"]
                    compact_str = oline["compact_str"]
                    spans = self._match_query_in_chars(compact_str, q_compact)
                    for start_i, end_i in spans:
                        match_rect = fitz.Rect(chars[start_i][1])
                        for k in range(start_i + 1, end_i):
                            match_rect |= chars[k][1]
                        if not any(self._rects_overlap(match_rect, existing) for existing in page_rects):
                            page_rects.append(match_rect)

            for r in page_rects:
                results.append((page_idx, r))
        return results

