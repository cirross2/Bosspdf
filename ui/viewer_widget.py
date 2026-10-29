"""
고성능 연속 스크롤(Continuous Scroll) 및 대화형 편집 지원 PDF 뷰어
(글꼴/크기/스타일/색상/자동 줄맞춤 지원)
"""
import enum
from typing import Optional, List, Tuple
import pymupdf as fitz
from PySide6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem,
    QGraphicsDropShadowEffect, QMessageBox, QGraphicsRectItem,
    QGraphicsPathItem
)
from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import (
    QPixmap, QColor, QPainter, QWheelEvent, QMouseEvent,
    QCursor, QPen, QBrush, QPainterPath
)

from core.pdf_engine import PdfEngine
from ui.text_edit_dialog import TextEditDialog
from ui.theme import AppleTheme


class EditMode(enum.Enum):
    HAND = "hand"           # 이동 및 연속 스크롤
    ADD_TEXT = "add_text"   # 텍스트 추가
    WHITEOUT = "whiteout"   # 텍스트 삭제/가리기
    EDIT_TEXT = "edit_text" # 텍스트 수정(화이트아웃 후 새 텍스트 입력)
    HIGHLIGHT = "highlight" # 형광펜 하이라이트
    PEN = "pen"             # 자유형 펜 / 서명


class PdfViewerWidget(QGraphicsView):
    """
    모든 페이지가 세로로 자연스럽게 이어지는 연속 스크롤(Continuous Scroll) 뷰어 및
    실시간 PDF 편집(글꼴, 크기, 스타일, 색상, 자동 줄맞춤 스냅 지원) 캔버스
    """
    page_changed = Signal(int, int)       # (current_page, total_pages)
    zoom_changed = Signal(float)          # zoom factor (1.0 = 100%)
    document_modified = Signal()          # 편집 발생 시그널

    PAGE_SPACING = 16.0  # 페이지 간격 (pt)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)

        self.pdf_engine: Optional[PdfEngine] = None
        self.zoom_factor: float = 1.2  # 기본 120%
        self.current_mode: EditMode = EditMode.HAND
        self._current_page: int = 0
        self._rendered_pages: set = set()

        # 페이지별 렌더링 아이템 및 위치 정보 목록
        self.page_items: List[QGraphicsPixmapItem] = []
        self.page_bg_items: List[QGraphicsRectItem] = []
        self.page_rects_in_scene: List[QRectF] = []

        # 검색어 블록 하이라이트 상태
        self.search_results: List[Tuple[int, fitz.Rect]] = []
        self.current_search_index: int = -1
        self.search_highlight_items: List[QGraphicsRectItem] = []

        # 드래그 편집 상태 추적
        self._is_dragging = False
        self._drag_start_scene: Optional[QPointF] = None
        self._drag_start_page: int = -1
        self._drag_rect_item: Optional[QGraphicsRectItem] = None
        self._pen_points: List[Tuple[float, float]] = []
        self._pen_path_item: Optional[QGraphicsPathItem] = None

        # macOS 미리보기 감성의 차분하고 눈이 편안한 캔버스 배경 설정
        self.setBackgroundBrush(QColor(AppleTheme.CANVAS_BG))
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)

        # 스크롤 이벤트 감지하여 현재 페이지 계산
        self.verticalScrollBar().valueChanged.connect(self._on_scroll_changed)
        self.set_mode(EditMode.HAND)

    @property
    def current_page(self) -> int:
        """현재 화면에 표시 중인 활성 페이지 번호 (0-based)"""
        return self._current_page

    def set_engine(self, engine: PdfEngine):
        """PDF 엔진 바인딩 및 모든 페이지 연속 렌더링"""
        self.pdf_engine = engine
        self._current_page = 0
        self.render_all_pages()

    def set_mode(self, mode: EditMode):
        """편집 모드 변경"""
        self.current_mode = mode
        if mode == EditMode.HAND:
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            self.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
        elif mode in (EditMode.ADD_TEXT, EditMode.EDIT_TEXT):
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.viewport().setCursor(Qt.CursorShape.IBeamCursor)
        elif mode in (EditMode.WHITEOUT, EditMode.HIGHLIGHT):
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.viewport().setCursor(Qt.CursorShape.CrossCursor)
        elif mode == EditMode.PEN:
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.viewport().setCursor(Qt.CursorShape.CrossCursor)

    def render_all_pages(self):
        """전체 페이지 위치 및 배경 카드를 즉시 생성하고 가시 영역만 지연 렌더링 (초고속 오픈)"""
        self.search_highlight_items.clear()
        self.scene.clear()
        self.page_items.clear()
        self.page_bg_items.clear()
        self.page_rects_in_scene.clear()
        self._rendered_pages.clear()

        if not self.pdf_engine or not self.pdf_engine.is_loaded():
            return

        current_y = self.PAGE_SPACING
        max_page_width = 0.0

        border_pen = QPen(QColor(0, 0, 0, 50), 1)
        bg_brush = QBrush(QColor("#FFFFFF"))

        for page_idx in range(self.pdf_engine.page_count):
            rect = self.pdf_engine.get_page_rect(page_idx)
            pix_w = rect.width * self.zoom_factor
            pix_h = rect.height * self.zoom_factor
            max_page_width = max(max_page_width, pix_w)

            # 1. 애플 프리뷰 감성의 깔끔한 흰색 용지 배경 및 미세 테두리 (소프트웨어 블러 부하 제거)
            bg_item = self.scene.addRect(0, 0, pix_w, pix_h, border_pen, bg_brush)
            bg_item.setPos(0, current_y)
            self.page_bg_items.append(bg_item)

            # 2. 고화질 렌더링 픽스맵 아이템 (가시 영역 진입 시 렌더링)
            pix_item = QGraphicsPixmapItem()
            pix_item.setPos(0, current_y)
            self.scene.addItem(pix_item)
            self.page_items.append(pix_item)

            # 3. 씬 좌표 내 페이지 영역 저장
            scene_page_rect = QRectF(0, current_y, pix_w, pix_h)
            self.page_rects_in_scene.append(scene_page_rect)

            current_y += pix_h + self.PAGE_SPACING

        # 씬 전체 경계 여백 설정
        self.scene.setSceneRect(-30, 0, max_page_width + 60, current_y + 20)
        self._rebuild_search_highlight_items()
        self._update_visible_pages()
        self._on_scroll_changed()

    # ==================== 문서 내 단어 검색 블록 하이라이트 ====================

    def _rebuild_search_highlight_items(self):
        """현재 검색 결과(self.search_results)를 씬 좌표 기준 블록 사각형으로 강조 표시"""
        for item in self.search_highlight_items:
            try:
                self.scene.removeItem(item)
            except Exception:
                pass
        self.search_highlight_items.clear()

        if not self.search_results or not self.page_rects_in_scene:
            return

        normal_pen = QPen(QColor(230, 162, 0, 210), 1.2)
        normal_brush = QBrush(QColor(255, 214, 10, 115))
        active_pen = QPen(QColor(255, 59, 48, 245), 2.2)
        active_brush = QBrush(QColor(255, 149, 0, 165))

        for idx, (page_idx, fitz_rect) in enumerate(self.search_results):
            if 0 <= page_idx < len(self.page_rects_in_scene):
                page_scene = self.page_rects_in_scene[page_idx]
                pad = 2.0
                rx = page_scene.left() + fitz_rect.x0 * self.zoom_factor - pad
                ry = page_scene.top() + fitz_rect.y0 * self.zoom_factor - pad
                rw = max(6.0, fitz_rect.width * self.zoom_factor + pad * 2)
                rh = max(6.0, fitz_rect.height * self.zoom_factor + pad * 2)

                is_active = (idx == self.current_search_index)
                item = self.scene.addRect(
                    QRectF(rx, ry, rw, rh),
                    active_pen if is_active else normal_pen,
                    active_brush if is_active else normal_brush
                )
                item.setZValue(12.0 if is_active else 10.0)
                self.search_highlight_items.append(item)

    def set_search_results(self, results: List[Tuple[int, fitz.Rect]], active_index: int = -1):
        """검색 결과 목록을 바인딩하고 블록 하이라이트를 갱신한 뒤 활성 위치로 이동"""
        self.search_results = list(results)
        self.current_search_index = active_index if 0 <= active_index < len(self.search_results) else -1
        self._rebuild_search_highlight_items()
        if self.current_search_index >= 0:
            self.scroll_to_search_result(self.current_search_index)

    def set_active_search_index(self, active_index: int):
        """활성 검색 결과 인덱스를 변경하고 해당 블록을 강조 및 화면 중앙으로 스크롤"""
        if not self.search_results:
            self.current_search_index = -1
            return
        self.current_search_index = active_index % len(self.search_results)
        self._rebuild_search_highlight_items()
        self.scroll_to_search_result(self.current_search_index)

    def scroll_to_search_result(self, result_index: int):
        """지정된 검색 결과 블록이 있는 페이지 및 위치로 즉시 스크롤 이동"""
        if not (0 <= result_index < len(self.search_results)):
            return
        page_idx, fitz_rect = self.search_results[result_index]
        if not (0 <= page_idx < len(self.page_rects_in_scene)):
            return
        page_scene = self.page_rects_in_scene[page_idx]
        target_x = page_scene.left() + fitz_rect.irect.x0 * self.zoom_factor + (fitz_rect.width * self.zoom_factor) / 2.0
        target_y = page_scene.top() + fitz_rect.y0 * self.zoom_factor + (fitz_rect.height * self.zoom_factor) / 2.0
        self.centerOn(target_x, target_y)
        self._current_page = page_idx
        if self.pdf_engine:
            self.page_changed.emit(page_idx + 1, self.pdf_engine.page_count)
        self._update_visible_pages()

    def clear_search_highlights(self):
        """모든 검색 블록 하이라이트 제거"""
        self.search_results.clear()
        self.current_search_index = -1
        for item in self.search_highlight_items:
            try:
                self.scene.removeItem(item)
            except Exception:
                pass
        self.search_highlight_items.clear()

    def _update_visible_pages(self):
        """현재 화면에 보이는 페이지 및 인접 버퍼 페이지만 즉시 렌더링"""
        if not self.pdf_engine or not self.pdf_engine.is_loaded() or not self.page_rects_in_scene:
            return

        # 뷰포트 영역 계산 (+상하 1200px 버퍼로 매끄러운 스크롤 보장)
        v_rect = self.mapToScene(self.viewport().rect()).boundingRect()
        vis_top = v_rect.top() - 1200.0
        vis_bottom = v_rect.bottom() + 1200.0

        for idx, rect in enumerate(self.page_rects_in_scene):
            if rect.bottom() >= vis_top and rect.top() <= vis_bottom:
                if idx not in self._rendered_pages:
                    qimg = self.pdf_engine.render_page(idx, zoom=self.zoom_factor)
                    pixmap = QPixmap.fromImage(qimg)
                    self.page_items[idx].setPixmap(pixmap)
                    self._rendered_pages.add(idx)

    def reload_single_page(self, page_idx: int):
        """특정 페이지만 즉시 다시 렌더링 (편집 후 빠른 반영)"""
        if not self.pdf_engine or not self.pdf_engine.is_loaded():
            return
        if 0 <= page_idx < len(self.page_items):
            qimg = self.pdf_engine.render_page(page_idx, zoom=self.zoom_factor)
            pixmap = QPixmap.fromImage(qimg)
            self.page_items[page_idx].setPixmap(pixmap)
            self._rendered_pages.add(page_idx)

    def scroll_to_page(self, page_idx: int):
        """특정 페이지 위치로 부드럽게 스크롤 이동"""
        if 0 <= page_idx < len(self.page_rects_in_scene):
            rect = self.page_rects_in_scene[page_idx]
            self.centerOn(rect.center().x(), rect.top() + 100)
            self._current_page = page_idx
            self.page_changed.emit(page_idx + 1, self.pdf_engine.page_count)
            self._update_visible_pages()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_visible_pages()

    def set_zoom(self, zoom: float):
        """확대/축소 배율 적용 후 재렌더링"""
        new_zoom = max(0.2, min(4.0, zoom))
        if abs(self.zoom_factor - new_zoom) > 0.02:
            self.zoom_factor = new_zoom
            self.render_all_pages()
            self.zoom_changed.emit(self.zoom_factor)

    def zoom_in(self):
        self.set_zoom(self.zoom_factor * 1.2)

    def zoom_out(self):
        self.set_zoom(self.zoom_factor / 1.2)

    def fit_to_width(self):
        """가장 넓은 페이지를 화면 너비에 맞춤"""
        if not self.pdf_engine or not self.pdf_engine.is_loaded():
            return
        max_pt_w = max(self.pdf_engine.get_page_rect(i).width for i in range(self.pdf_engine.page_count))
        view_w = self.viewport().width() - 80
        if max_pt_w > 0 and view_w > 0:
            self.set_zoom(view_w / max_pt_w)

    def fit_to_page(self):
        """한 화면에 1페이지 전체가 들어가도록 배율 조정"""
        if not self.pdf_engine or not self.pdf_engine.is_loaded():
            return
        page_rect = self.pdf_engine.get_page_rect(0)
        view_w = self.viewport().width() - 80
        view_h = self.viewport().height() - 80
        if page_rect.width > 0 and page_rect.height > 0:
            scale = min(view_w / page_rect.width, view_h / page_rect.height)
            self.set_zoom(scale)

    def _get_page_at_scene_pos(self, scene_pos: QPointF) -> Tuple[int, Optional[fitz.Point]]:
        """씬 좌표가 어느 페이지에 해당하는지 및 해당 페이지 내부의 원본 PDF 좌표(pt) 반환"""
        for idx, rect in enumerate(self.page_rects_in_scene):
            if rect.contains(scene_pos):
                rel_x = scene_pos.x() - rect.left()
                rel_y = scene_pos.y() - rect.top()
                pdf_x = rel_x / self.zoom_factor
                pdf_y = rel_y / self.zoom_factor
                return idx, fitz.Point(pdf_x, pdf_y)
        return -1, None

    def _on_scroll_changed(self):
        """스크롤 시 화면 상단/중앙에 가장 많이 보이는 페이지 번호 감지 및 시그널 전송"""
        if not self.pdf_engine or not self.pdf_engine.is_loaded() or not self.page_rects_in_scene:
            return

        self._update_visible_pages()

        viewport_center_y = self.mapToScene(0, self.viewport().height() // 3).y()
        current_idx = 0
        for idx, rect in enumerate(self.page_rects_in_scene):
            if rect.top() <= viewport_center_y <= rect.bottom():
                current_idx = idx
                break
            elif rect.top() > viewport_center_y:
                current_idx = max(0, idx - 1)
                break
            else:
                current_idx = idx

        self._current_page = current_idx
        self.page_changed.emit(current_idx + 1, self.pdf_engine.page_count)

    def wheelEvent(self, event: QWheelEvent):
        # Ctrl + 휠: 줌 인/아웃
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                self.zoom_in()
            else:
                self.zoom_out()
            event.accept()
        else:
            # 기본 세로 연속 스크롤 부드럽게 전달
            super().wheelEvent(event)

    # ==================== 대화형 편집 마우스 이벤트 ====================

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() != Qt.MouseButton.LeftButton or not self.pdf_engine or not self.pdf_engine.is_loaded():
            super().mousePressEvent(event)
            return

        scene_pos = self.mapToScene(event.pos())
        page_idx, pdf_pt = self._get_page_at_scene_pos(scene_pos)

        if self.current_mode == EditMode.HAND:
            super().mousePressEvent(event)
            return

        if page_idx == -1 or not pdf_pt:
            return

        # 1. 텍스트 추가 모드: 클릭 위치 기반 스마트 줄맞춤 분석 후 서식 설정 다이얼로그 호출
        if self.current_mode == EditMode.ADD_TEXT:
            snap_info = self.pdf_engine.find_nearest_text_line(page_idx, pdf_pt.x, pdf_pt.y)
            dlg = TextEditDialog(
                parent=self,
                title="새 텍스트 추가 (서식 및 줄맞춤)",
                init_x=pdf_pt.x,
                init_y=pdf_pt.y,
                init_w=300.0,
                init_h=80.0,
                snap_info=snap_info
            )
            if dlg.exec():
                data = dlg.get_data()
                if data["text"].strip():
                    self.pdf_engine.add_text(
                        page_num=page_idx,
                        x=data["x"],
                        y=data["y"],
                        text=data["text"],
                        font_family=data["font_family"],
                        fontsize=data["fontsize"],
                        is_bold=data["is_bold"],
                        is_italic=data["is_italic"],
                        color=data["color"],
                        align=data["align"],
                        width=data["w"],
                        height=data["h"]
                    )
                    self.reload_single_page(page_idx)
                    self.document_modified.emit()
            return

        # 2. 드래그 시작 (화이트아웃, 텍스트 수정, 형광펜, 펜)
        self._is_dragging = True
        self._drag_start_scene = scene_pos
        self._drag_start_page = page_idx

        if self.current_mode in (EditMode.WHITEOUT, EditMode.EDIT_TEXT, EditMode.HIGHLIGHT):
            color = QColor(255, 255, 0, 100) if self.current_mode == EditMode.HIGHLIGHT else QColor(255, 255, 255, 180)
            border_pen = QPen(Qt.GlobalColor.blue, 1, Qt.PenStyle.DashLine)
            self._drag_rect_item = self.scene.addRect(QRectF(scene_pos, scene_pos), border_pen, QBrush(color))
        elif self.current_mode == EditMode.PEN:
            self._pen_points = [(pdf_pt.x, pdf_pt.y)]
            pen = QPen(QColor(20, 50, 220), 2, Qt.PenStyle.SolidLine)
            path = QPainterPath(scene_pos)
            self._pen_path_item = self.scene.addPath(path, pen)

    def mouseMoveEvent(self, event: QMouseEvent):
        if not self._is_dragging or not self.pdf_engine:
            super().mouseMoveEvent(event)
            return

        scene_pos = self.mapToScene(event.pos())

        if self._drag_rect_item and self._drag_start_scene:
            rect = QRectF(self._drag_start_scene, scene_pos).normalized()
            self._drag_rect_item.setRect(rect)
        elif self._pen_path_item:
            path = self._pen_path_item.path()
            path.lineTo(scene_pos)
            self._pen_path_item.setPath(path)
            _, pdf_pt = self._get_page_at_scene_pos(scene_pos)
            if pdf_pt:
                self._pen_points.append((pdf_pt.x, pdf_pt.y))

    def mouseReleaseEvent(self, event: QMouseEvent):
        if not self._is_dragging or not self.pdf_engine:
            super().mouseReleaseEvent(event)
            return

        self._is_dragging = False
        scene_pos = self.mapToScene(event.pos())
        page_idx = self._drag_start_page

        # 드래그 미리보기 아이템 제거
        if self._drag_rect_item:
            self.scene.removeItem(self._drag_rect_item)
            self._drag_rect_item = None
        if self._pen_path_item:
            self.scene.removeItem(self._pen_path_item)
            self._pen_path_item = None

        if page_idx < 0 or page_idx >= len(self.page_rects_in_scene):
            return

        page_rect_scene = self.page_rects_in_scene[page_idx]

        # 펜 드로잉 완료
        if self.current_mode == EditMode.PEN:
            if len(self._pen_points) >= 2:
                self.pdf_engine.add_ink(page_idx, self._pen_points, color=(0.1, 0.2, 0.8), width=2.0)
                self.reload_single_page(page_idx)
                self.document_modified.emit()
            self._pen_points.clear()
            return

        # 사각형 영역 계산
        if not self._drag_start_scene:
            return

        rect_scene = QRectF(self._drag_start_scene, scene_pos).normalized()
        rel_left = max(0.0, rect_scene.left() - page_rect_scene.left())
        rel_top = max(0.0, rect_scene.top() - page_rect_scene.top())
        rel_right = min(page_rect_scene.width(), rect_scene.right() - page_rect_scene.left())
        rel_bottom = min(page_rect_scene.height(), rect_scene.bottom() - page_rect_scene.top())

        if rel_right - rel_left < 5 or rel_bottom - rel_top < 5:
            return  # 너무 작은 드래그 무시

        fitz_rect = fitz.Rect(
            rel_left / self.zoom_factor,
            rel_top / self.zoom_factor,
            rel_right / self.zoom_factor,
            rel_bottom / self.zoom_factor
        )

        if self.current_mode == EditMode.WHITEOUT:
            # 텍스트 삭제 (화이트아웃만 수행)
            self.pdf_engine.add_whiteout(page_idx, fitz_rect)
            self.reload_single_page(page_idx)
            self.document_modified.emit()

        elif self.current_mode == EditMode.EDIT_TEXT:
            # 텍스트 수정: 기존 내용 추출 -> 서식 대화상자 -> 적용 시에만 화이트아웃 후 새 텍스트 삽입
            existing_text = ""
            existing_color = None
            try:
                page = self.pdf_engine.doc[page_idx]
                existing_text = page.get_text("text", clip=fitz_rect).strip()
                clip_dict = page.get_text("dict", clip=fitz_rect)
                for b in clip_dict.get("blocks", []):
                    for l in b.get("lines", []):
                        for s in l.get("spans", []):
                            c_int = s.get("color")
                            if c_int is not None:
                                r = (c_int >> 16) & 255
                                g = (c_int >> 8) & 255
                                b_val = c_int & 255
                                existing_color = QColor(r, g, b_val)
                                break
                        if existing_color:
                            break
                    if existing_color:
                        break
            except Exception:
                pass

            snap_info = self.pdf_engine.find_nearest_text_line(page_idx, fitz_rect.x0, fitz_rect.y0)
            dlg = TextEditDialog(
                parent=self,
                title="텍스트 수정 (기존 내용 덮어쓰기 & 서식 변경)",
                initial_text=existing_text,
                init_x=fitz_rect.x0,
                init_y=fitz_rect.y0,
                init_w=max(150.0, fitz_rect.width),
                init_h=max(40.0, fitz_rect.height),
                initial_color=existing_color,
                snap_info=snap_info
            )
            if dlg.exec():
                data = dlg.get_data()
                # 기존 영역 화이트아웃 처리
                self.pdf_engine.add_whiteout(page_idx, fitz_rect)
                # 새로운 텍스트 삽입
                if data["text"].strip():
                    self.pdf_engine.add_text(
                        page_num=page_idx,
                        x=data["x"],
                        y=data["y"],
                        text=data["text"],
                        font_family=data["font_family"],
                        fontsize=data["fontsize"],
                        is_bold=data["is_bold"],
                        is_italic=data["is_italic"],
                        color=data["color"],
                        align=data["align"],
                        width=data["w"],
                        height=data["h"]
                    )
                self.reload_single_page(page_idx)
                self.document_modified.emit()

        elif self.current_mode == EditMode.HIGHLIGHT:
            # 형광펜 추가
            self.pdf_engine.add_highlight(page_idx, fitz_rect)
            self.reload_single_page(page_idx)
            self.document_modified.emit()
