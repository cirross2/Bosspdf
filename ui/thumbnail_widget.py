"""
좌측 사이드바 썸네일 미리보기 및 페이지 순서 변경 위젯
(SVG 벡터 아이콘, 다크/화이트 모드 지원, 스크롤 연동 지능형 백그라운드 지연 로딩)
"""
from typing import Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QLabel, QPushButton, QMenu, QMessageBox
)
from PySide6.QtCore import Qt, Signal, QSize, QTimer
from PySide6.QtGui import QIcon, QAction, QPixmap, QColor

from core.pdf_engine import PdfEngine
from ui.icons import get_icon
from ui.theme import AppleTheme


class ThumbnailWidget(QWidget):
    """
    페이지별 썸네일 표시 및 페이지 순서 변경/이동/조작 패널
    """
    page_selected = Signal(int)
    page_deleted = Signal(int)
    page_rotated = Signal(int, int)
    page_reorder_requested = Signal()  # 순서 관리 대화상자 호출 시그널
    page_order_changed = Signal()      # 순서 변경 완료 시그널

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pdf_engine: Optional[PdfEngine] = None
        self._load_gen: int = 0
        self._current_theme_mode: str = AppleTheme.LIGHT
        self._is_user_scrolling: bool = False
        self._pending_load_state: Optional[tuple] = None  # (gen_id, start_idx, batch_size)

        self._init_ui()
        self.apply_theme(AppleTheme.LIGHT)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # 상단 헤더 및 빠른 순서 변경 버튼 열
        header_row = QHBoxLayout()
        header_row.setSpacing(4)

        self.lbl_header = QLabel("페이지 썸네일")
        self.lbl_header.setStyleSheet("color: #86868B; font-size: 11px; font-weight: 600; text-transform: uppercase;")
        header_row.addWidget(self.lbl_header)
        header_row.addStretch()

        self.btn_move_up = QPushButton()
        self.btn_move_up.setToolTip("선택한 페이지를 한 칸 위로 이동")
        self.btn_move_up.setFixedSize(26, 24)
        self.btn_move_up.clicked.connect(self._move_current_up)
        header_row.addWidget(self.btn_move_up)

        self.btn_move_down = QPushButton()
        self.btn_move_down.setToolTip("선택한 페이지를 한 칸 아래로 이동")
        self.btn_move_down.setFixedSize(26, 24)
        self.btn_move_down.clicked.connect(self._move_current_down)
        header_row.addWidget(self.btn_move_down)

        self.btn_reorder_all = QPushButton()
        self.btn_reorder_all.setToolTip("전체 페이지 순서 관리 대화상자 열기")
        self.btn_reorder_all.setFixedSize(28, 24)
        self.btn_reorder_all.clicked.connect(self.page_reorder_requested.emit)
        header_row.addWidget(self.btn_reorder_all)

        layout.addLayout(header_row)

        self.list_widget = QListWidget()
        self.list_widget.setIconSize(QSize(120, 160))
        self.list_widget.setViewMode(QListWidget.ViewMode.IconMode)
        self.list_widget.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list_widget.setMovement(QListWidget.Movement.Static)
        self.list_widget.setSpacing(8)
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._show_context_menu)
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        self.list_widget.currentRowChanged.connect(self._on_row_changed)

        layout.addWidget(self.list_widget)
        self._update_btn_states()

    def apply_theme(self, theme_mode: str):
        """다크/화이트 모드에 맞게 UI 스타일 및 SVG 아이콘 동적 갱신"""
        self._current_theme_mode = theme_mode
        is_dark = (theme_mode == AppleTheme.DARK)
        p = AppleTheme.get_palette(theme_mode)

        # SVG 아이콘 갱신
        self.btn_move_up.setIcon(get_icon("chevron_up", is_dark=is_dark, size=14))
        self.btn_move_down.setIcon(get_icon("chevron_down", is_dark=is_dark, size=14))
        self.btn_reorder_all.setIcon(get_icon("reorder", is_dark=is_dark, size=14))

        btn_style = f"""
            QPushButton {{
                background-color: {p["CARD_BG"]};
                border: 1px solid {p["BORDER_STANDARD"]};
                border-radius: 5px;
                padding: 2px;
            }}
            QPushButton:hover {{
                background-color: {p["ITEM_HOVER"]};
                border-color: {p["BORDER_DARK"]};
            }}
            QPushButton:disabled {{
                background-color: transparent;
                border-color: transparent;
            }}
        """
        self.btn_move_up.setStyleSheet(btn_style)
        self.btn_move_down.setStyleSheet(btn_style)
        self.btn_reorder_all.setStyleSheet(btn_style)

        self.lbl_header.setStyleSheet(f"color: {p['TEXT_SECONDARY']}; font-size: 11px; font-weight: 600; text-transform: uppercase;")

        self.list_widget.setStyleSheet(f"""
            QListWidget {{
                border: none;
                background-color: {p["SIDEBAR_BG"]};
            }}
            QListWidget::item {{
                border: 1px solid {p["BORDER_SUBTLE"]};
                border-radius: 8px;
                background-color: {p["CARD_BG"]};
                color: {p["TEXT_PRIMARY"]};
                font-size: 11px;
                font-weight: 500;
                padding: 6px;
                margin: 4px;
            }}
            QListWidget::item:hover {{
                border: 1px solid {p["BORDER_STANDARD"]};
                background-color: {p["ITEM_HOVER"]};
            }}
            QListWidget::item:selected {{
                border: 2px solid {p["ACCENT_BLUE"]};
                background-color: {p["ACCENT_TINT"]};
                color: {p["ACCENT_BLUE"]};
                font-weight: 600;
            }}
        """)

    def on_viewer_scroll_state_changed(self, is_scrolling: bool):
        """뷰어 스크롤 중일 때 백그라운드 썸네일 생성을 일시 정지하여 100% 버터 스크롤 보장"""
        self._is_user_scrolling = is_scrolling
        if not is_scrolling and self._pending_load_state:
            gen_id, start_idx, batch_size = self._pending_load_state
            self._pending_load_state = None
            QTimer.singleShot(60, lambda: self._load_remaining_thumbnails(gen_id, start_idx, batch_size))

    def load_thumbnails(self, engine: PdfEngine):
        """PDF 문서의 각 페이지 썸네일 고속 로드 (초기 4페이지 즉시 로드 후 나머지 백그라운드 지연 처리)"""
        self.pdf_engine = engine
        self._load_gen += 1
        current_gen = self._load_gen
        self._pending_load_state = None
        self.list_widget.clear()

        if not self.pdf_engine or not self.pdf_engine.is_loaded():
            self._update_btn_states()
            return

        total_pages = self.pdf_engine.page_count
        # 빈 플레이스홀더 아이템 목록 우선 생성 (스크롤바 및 위치 즉시 확보)
        placeholder_pixmap = QPixmap(105, 148)
        placeholder_pixmap.fill(QColor("#FFFFFF"))
        placeholder_icon = QIcon(placeholder_pixmap)

        for i in range(total_pages):
            item = QListWidgetItem(placeholder_icon, f"{i + 1} p")
            item.setData(Qt.ItemDataRole.UserRole, i)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item.setSizeHint(QSize(135, 175))
            self.list_widget.addItem(item)

        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)
        self._update_btn_states()

        # 화면에 즉시 보일 첫 배치(최대 4페이지) 즉시 렌더링
        initial_count = min(4, total_pages)
        for i in range(initial_count):
            pixmap = self.pdf_engine.get_thumbnail(i, max_size=140)
            item = self.list_widget.item(i)
            if item:
                item.setIcon(QIcon(pixmap))

        # 나머지 페이지가 있다면 지연 비동기 로드
        if total_pages > initial_count:
            QTimer.singleShot(40, lambda: self._load_remaining_thumbnails(current_gen, initial_count, batch_size=2))

    def _load_remaining_thumbnails(self, gen_id: int, start_idx: int, batch_size: int = 2):
        """나머지 썸네일을 스크롤 방해 없이 온화한 주기로 지연 로드"""
        if gen_id != self._load_gen or not self.pdf_engine or not self.pdf_engine.is_loaded():
            return

        # 사용자가 뷰어를 스크롤 중이거나 사이드바가 숨겨져 있다면 로딩을 대기(Pause)
        if self._is_user_scrolling or self.isHidden():
            self._pending_load_state = (gen_id, start_idx, batch_size)
            return

        total_pages = self.pdf_engine.page_count
        end_idx = min(start_idx + batch_size, total_pages)

        for i in range(start_idx, end_idx):
            if i < self.list_widget.count():
                pixmap = self.pdf_engine.get_thumbnail(i, max_size=140)
                item = self.list_widget.item(i)
                if item:
                    item.setIcon(QIcon(pixmap))

        if end_idx < total_pages:
            # 35ms 간격을 두어 UI 스레드에 넉넉한 렌더링 여유 제공
            QTimer.singleShot(35, lambda: self._load_remaining_thumbnails(gen_id, end_idx, batch_size))

    def select_page(self, page_idx: int):
        """외부에서 페이지 변경 시 썸네일 포커스 동기화 (스크롤 중일 때는 부드럽게 선택만 갱신)"""
        if 0 <= page_idx < self.list_widget.count() and self.list_widget.currentRow() != page_idx:
            self.list_widget.blockSignals(True)
            self.list_widget.setCurrentRow(page_idx)
            # 사용자가 연속 스크롤 중이 아닐 때만 강제 스크롤 위치 이동
            if not self._is_user_scrolling:
                item = self.list_widget.item(page_idx)
                if item:
                    self.list_widget.scrollToItem(item, QListWidget.ScrollHint.EnsureVisible)
            self.list_widget.blockSignals(False)
            self._update_btn_states()

    def _on_item_clicked(self, item: QListWidgetItem):
        page_idx = self.list_widget.row(item)
        self.page_selected.emit(page_idx)

    def _on_row_changed(self, row: int):
        self._update_btn_states()

    def _update_btn_states(self):
        cnt = self.list_widget.count()
        row = self.list_widget.currentRow()
        has_doc = cnt > 1
        self.btn_reorder_all.setEnabled(has_doc)
        self.btn_move_up.setEnabled(has_doc and row > 0)
        self.btn_move_down.setEnabled(has_doc and 0 <= row < cnt - 1)

    def _move_current_up(self):
        row = self.list_widget.currentRow()
        if self.pdf_engine and row > 0:
            if self.pdf_engine.move_page(row, row - 1):
                self.load_thumbnails(self.pdf_engine)
                self.select_page(row - 1)
                self.page_order_changed.emit()

    def _move_current_down(self):
        row = self.list_widget.currentRow()
        if self.pdf_engine and 0 <= row < self.list_widget.count() - 1:
            if self.pdf_engine.move_page(row, row + 1):
                self.load_thumbnails(self.pdf_engine)
                self.select_page(row + 1)
                self.page_order_changed.emit()

    def _move_to_top(self, page_idx: int):
        if self.pdf_engine and page_idx > 0:
            if self.pdf_engine.move_page(page_idx, 0):
                self.load_thumbnails(self.pdf_engine)
                self.select_page(0)
                self.page_order_changed.emit()

    def _move_to_bottom(self, page_idx: int):
        if self.pdf_engine and 0 <= page_idx < self.list_widget.count() - 1:
            last_idx = self.list_widget.count() - 1
            if self.pdf_engine.move_page(page_idx, last_idx):
                self.load_thumbnails(self.pdf_engine)
                self.select_page(last_idx)
                self.page_order_changed.emit()

    def _show_context_menu(self, pos):
        item = self.list_widget.itemAt(pos)
        if not item or not self.pdf_engine:
            return

        page_idx = self.list_widget.row(item)
        menu = QMenu(self)

        act_rotate_cw = QAction("시계 방향 90° 회전", self)
        act_rotate_cw.triggered.connect(lambda: self.page_rotated.emit(page_idx, 90))
        menu.addAction(act_rotate_cw)

        act_rotate_ccw = QAction("반시계 방향 90° 회전", self)
        act_rotate_ccw.triggered.connect(lambda: self.page_rotated.emit(page_idx, 270))
        menu.addAction(act_rotate_ccw)

        menu.addSeparator()

        act_move_up = QAction("위로 이동 (▲)", self)
        act_move_up.setEnabled(page_idx > 0)
        act_move_up.triggered.connect(self._move_current_up)
        menu.addAction(act_move_up)

        act_move_down = QAction("아래로 이동 (▼)", self)
        act_move_down.setEnabled(page_idx < self.list_widget.count() - 1)
        act_move_down.triggered.connect(self._move_current_down)
        menu.addAction(act_move_down)

        act_move_top = QAction("맨 위로 이동", self)
        act_move_top.setEnabled(page_idx > 0)
        act_move_top.triggered.connect(lambda: self._move_to_top(page_idx))
        menu.addAction(act_move_top)

        act_move_bottom = QAction("맨 아래로 이동", self)
        act_move_bottom.setEnabled(page_idx < self.list_widget.count() - 1)
        act_move_bottom.triggered.connect(lambda: self._move_to_bottom(page_idx))
        menu.addAction(act_move_bottom)

        menu.addSeparator()

        act_manage_order = QAction("전체 순서 관리 대화상자...", self)
        act_manage_order.triggered.connect(self.page_reorder_requested.emit)
        menu.addAction(act_manage_order)

        menu.addSeparator()

        act_del = QAction("페이지 삭제", self)
        act_del.setEnabled(self.list_widget.count() > 1)
        act_del.triggered.connect(lambda: self._confirm_delete(page_idx))
        menu.addAction(act_del)

        menu.exec(self.list_widget.mapToGlobal(pos))

    def _confirm_delete(self, page_idx: int):
        reply = QMessageBox.question(
            self,
            "페이지 삭제",
            f"{page_idx + 1} 페이지를 정말로 삭제하시겠습니까?\n이 작업은 취소할 수 있습니다.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.page_deleted.emit(page_idx)
