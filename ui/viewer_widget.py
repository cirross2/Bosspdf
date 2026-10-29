"""
고성능 연속 스크롤(Continuous Scroll) 및 대화형 편집 지원 PDF 뷰어
(글꼴/크기/스타일/색상/자동 줄맞춤 지원, O(log N) 가상화 지연 렌더링, 버터처럼 부드러운 스크롤 최적화)
"""
import enum
import bisect
from typing import Optional, List, Tuple
import pymupdf as fitz
from PySide6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem,
    QGraphicsDropShadowEffect, QMessageBox, QGraphicsRectItem,
    QGraphicsPathItem
)
from PySide6.QtCore import Qt, Signal, QRectF, QPointF, QTimer
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
    scroll_state_changed = Signal(bool)   # True: 스크롤 진행 중, False: 스크롤 유휴(Idle)

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
        self.page_tops: List[float] = []

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

        # 초고속 부드러운 스크롤 제어 타이머
        self._is_scrolling: bool = False
        self._scroll_idle_timer = QTimer(self)
        self._scroll_idle_timer.setSingleShot(True)
        self._scroll_idle_timer.setInterval(220)
        self._scroll_idle_timer.timeout.connect(self._on_scroll_idle)

        self._page_emit_timer = QTimer(self)
        self._page_emit_timer.setSingleShot(True)
        self._page_emit_timer.setInterval(40)
        self._page_emit_timer.timeout.connect(self._emit_page_changed)

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

    def set_theme(self, theme_mode: str):
        """테마(다크/라이트)에 맞게 캔버스 배경색 갱신"""
        self.setBackgroundBrush(QColor(AppleTheme.get_canvas_bg(theme_mode)))

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
        self.page_tops.clear()
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

            # 1. 흰색 용지 배경 및 미세 테두리
            bg_item = self.scene.addRect(0, 0, pix_w, pix_h, border_pen, bg_brush)
            bg_item.setPos(0, current_y)
            self.page_bg_items.append(bg_item)

            # 2. 고화질 렌더링 픽스맵 아이템 (가시 영역 진입 시 지연 렌더링)
            pix_item = QGraphicsPixmapItem()
            pix_item.setPos(0, current_y)
            self.scene.addItem(pix_item)
            self.page_items.append(pix_item)

            # 3. 씬 좌표 내 페이지 영역 저장
            scene_page_rect = QRectF(0, current_y, pix_w, pix_h)
            self.page_rects_in_scene.append(scene_page_rect)
            self.page_tops.append(current_y)

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
        target_x = page_scene.left() + fitz_rect.x0 * self.zoom_factor + (fitz_rect.width * self.zoom_factor) / 2.0
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

    # ==================== O(log N) 가상화 지연 렌더링 및 부드러운 스크롤 ====================

    def _update_visible_pages(self):
        """현재 화면에 보이는 페이지 및 상하 인접 페이지만 O(log N) 탐색으로 즉시 렌더링"""
        if not self.pdf_engine or not self.pdf_engine.is_loaded() or not self.page_rects_in_scene:
            return

        # 뷰포트 영역 계산 (+상하 800px 버퍼로 매끄러운 스크롤 보장)
        v_rect = self.mapToScene(self.viewport().rect()).boundingRect()
        vis_top = v_rect.top() - 800.0
        vis_bottom = v_rect.bottom() + 800.0

        # O(log N) 이진 탐색으로 가시 범위 페이지 인덱스 즉각 산출
        start_idx = max(0, bisect.bisect_right(self.page_tops, vis_top) - 1)
        end_idx = min(len(self.page_rects_in_scene), bisect.bisect_right(self.page_tops, vis_bottom) + 1)

        for idx in range(start_idx, end_idx):
            rect = self.page_rects_in_scene[idx]
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
        if not self.page_rects_in_scene:
            return -1, None
        sy = scene_pos.y()
        # O(log N) 근사 탐색
        idx_guess = max(0, min(len(self.page_tops) - 1, bisect.bisect_right(self.page_tops, sy) - 1))
        candidates = [idx_guess]
        if idx_guess + 1 < len(self.page_rects_in_scene):
            candidates.append(idx_guess + 1)
        for idx in candidates:
            rect = self.page_rects_in_scene[idx]
            if rect.contains(scene_pos):
                rel_x = scene_pos.x() - rect.left()
                rel_y = scene_pos.y() - rect.top()
                pdf_x = rel_x / self.zoom_factor
                pdf_y = rel_y / self.zoom_factor
                return idx, fitz.Point(pdf_x, pdf_y)
        return -1, None

    def _on_scroll_changed(self):
        """스크롤 이벤트 발생 시 고속 O(log N) 페이지 인덱스 계산 및 스크롤 상태 전달"""
        if not self.pdf_engine or not self.pdf_engine.is_loaded() or not self.page_rects_in_scene:
            return

        # 스크롤 진행 중임을 통보 (백그라운드 썸네일 생성을 일시 정지시켜 렉 방지)
        if not self._is_scrolling:
            self._is_scrolling = True
            self.scroll_state_changed.emit(True)
        self._scroll_idle_timer.start()

        self._update_visible_pages()

        # O(log N) 이진 탐색으로 현재 페이지 산출
        viewport_center_y = self.mapToScene(0, self.viewport().height() // 3).y()
        current_idx = max(0, min(len(self.page_tops) - 1, bisect.bisect_right(self.page_tops, viewport_center_y) - 1))

        if current_idx != self._current_page:
            self._current_page = current_idx
            self._page_emit_timer.start()

    def _on_scroll_idle(self):
        """스크롤이 멈췄을 때 호출 (유휴 상태 복귀 및 백그라운드 썸네일 재개 허용)"""
        self._is_scrolling = False
        self.scroll_state_changed.emit(False)
        self._update_visible_pages()
        self._emit_page_changed()

    def _emit_page_changed(self):
        """디바운스된 페이지 변경 시그널 전송 (과도한 썸네일 재선택 부하 방지)"""
        if self.pdf_engine and self.pdf_engine.is_loaded():
            self.page_changed.emit(self._current_page + 1, self.pdf_engine.page_count)

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

    # ==================== 마우스 드래그 편집 상호작용 ====================

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and self.current_mode != EditMode.HAND:
            scene_pos = self.mapToScene(event.pos())
            page_idx, pdf_pt = self._get_page_at_scene_pos(scene_pos)

            if page_idx >= 0 and pdf_pt is not None:
                self._is_dragging = True
                self._drag_start_scene = scene_pos
                self._drag_start_page = page_idx

                if self.current_mode == EditMode.ADD_TEXT:
                    # 클릭 즉시 서식 설정 대화상자 표시
                    self._is_dragging = False
                    self._handle_add_text_dialog(page_idx, pdf_pt)
                    return

                elif self.current_mode in (EditMode.WHITEOUT, EditMode.EDIT_TEXT):
                    # 영역 드래그 사각형 생성
                    self._drag_rect_item = self.scene.addRect(
                        QRectF(scene_pos, scene_pos),
                        QPen(QColor(AppleTheme.ACCENT_BLUE), 1, Qt.PenStyle.DashLine),
                        QBrush(QColor(0, 122, 255, 30))
                    )
                    self._drag_rect_item.setZValue(100)

                elif self.current_mode == EditMode.HIGHLIGHT:
                    self._drag_rect_item = self.scene.addRect(
                        QRectF(scene_pos, scene_pos),
                        QPen(QColor(255, 204, 0), 1),
                        QBrush(QColor(255, 230, 0, 90))
                    )
                    self._drag_rect_item.setZValue(100)

                elif self.current_mode == EditMode.PEN:
                    self._pen_points = [(pdf_pt.x, pdf_pt.y)]
                    path = QPainterPath(scene_pos)
                    self._pen_path_item = self.scene.addPath(
                        path,
                        QPen(QColor(0, 0, 0), 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
                    )
                    self._pen_path_item.setZValue(100)
                return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._is_dragging and self._drag_start_scene is not None:
            cur_scene = self.mapToScene(event.pos())

            if self._drag_rect_item is not None:
                rect = QRectF(self._drag_start_scene, cur_scene).normalized()
                self._drag_rect_item.setRect(rect)

            elif self.current_mode == EditMode.PEN and self._pen_path_item is not None:
                page_idx, pdf_pt = self._get_page_at_scene_pos(cur_scene)
                if page_idx == self._drag_start_page and pdf_pt is not None:
                    self._pen_points.append((pdf_pt.x, pdf_pt.y))
                    path = self._pen_path_item.path()
                    path.lineTo(cur_scene)
                    self._pen_path_item.setPath(path)
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and self._is_dragging:
            self._is_dragging = False
            cur_scene = self.mapToScene(event.pos())
            page_idx = self._drag_start_page

            if self._drag_rect_item is not None:
                self.scene.removeItem(self._drag_rect_item)
                self._drag_rect_item = None

            if self._pen_path_item is not None:
                self.scene.removeItem(self._pen_path_item)
                self._pen_path_item = None

            if page_idx >= 0 and self.pdf_engine and self.pdf_engine.is_loaded():
                page_scene_rect = self.page_rects_in_scene[page_idx]

                if self.current_mode == EditMode.PEN and len(self._pen_points) > 1:
                    self.pdf_engine.add_drawing(page_idx, self._pen_points, stroke_color=(0, 0, 0), width=2.5)
                    self.reload_single_page(page_idx)
                    self.document_modified.emit()
                    self._pen_points = []
                    return

                # 드래그 영역을 PDF 포인트 단위 좌표로 변환
                drag_rect = QRectF(self._drag_start_scene, cur_scene).normalized()
                inter_rect = drag_rect.intersected(page_scene_rect)

                if inter_rect.width() > 5 and inter_rect.height() > 5:
                    rel_x = (inter_rect.left() - page_scene_rect.left()) / self.zoom_factor
                    rel_y = (inter_rect.top() - page_scene_rect.top()) / self.zoom_factor
                    rel_w = inter_rect.width() / self.zoom_factor
                    rel_h = inter_rect.height() / self.zoom_factor
                    fitz_rect = fitz.Rect(rel_x, rel_y, rel_x + rel_w, rel_y + rel_h)

                    self._handle_drag_action(page_idx, fitz_rect)
            return

        super().mouseReleaseEvent(event)

    def _handle_add_text_dialog(self, page_idx: int, pdf_pt: fitz.Point):
        """텍스트 추가 대화상자 표시 및 삽입 처리"""
        snap_info = self.pdf_engine.find_nearest_text_line(page_idx, pdf_pt.x, pdf_pt.y)
        init_font = snap_info["font_family"] if snap_info else "맑은 고딕"
        init_size = snap_info["fontsize"] if snap_info else 12.0
        init_color = snap_info["color"] if snap_info else QColor("#000000")
        init_y = snap_info["snap_y"] if (snap_info and snap_info.get("snap_y") is not None) else pdf_pt.y

        dlg = TextEditDialog(
            parent=self,
            title="새 텍스트 삽입 (글꼴/크기/스타일/색상)",
            initial_text="",
            init_x=pdf_pt.x,
            init_y=init_y,
            init_w=200.0,
            init_h=40.0,
            initial_font=init_font,
            initial_size=init_size,
            initial_color=init_color,
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

    def _handle_drag_action(self, page_idx: int, fitz_rect: fitz.Rect):
        """드래그 완료 후 모드별 동작 수행"""
        if self.current_mode == EditMode.WHITEOUT:
            self.pdf_engine.add_whiteout(page_idx, fitz_rect)
            self.reload_single_page(page_idx)
            self.document_modified.emit()

        elif self.current_mode == EditMode.EDIT_TEXT:
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
                self.pdf_engine.add_whiteout(page_idx, fitz_rect)
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
            self.pdf_engine.add_highlight(page_idx, fitz_rect)
            self.reload_single_page(page_idx)
            self.document_modified.emit()
