"""
좌측 사이드바 썸네일 미리보기 및 페이지 순서 변경 위젯
"""
from typing import Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QLabel, QPushButton, QMenu, QMessageBox
)
from PySide6.QtCore import Qt, Signal, QSize, QTimer
from PySide6.QtGui import QIcon, QAction, QPixmap, QColor

from core.pdf_engine import PdfEngine


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
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # 상단 헤더 및 빠른 순서 변경 버튼 열
        header_row = QHBoxLayout()
        header = QLabel("페이지 썸네일")
        header.setStyleSheet("color: #86868B; font-size: 11px; font-weight: 600; text-transform: uppercase;")
        header_row.addWidget(header)
        header_row.addStretch()

        self.btn_move_up = QPushButton("▲")
        self.btn_move_up.setToolTip("선택한 페이지를 한 칸 위로 이동")
        self.btn_move_up.setFixedSize(26, 24)
        self.btn_move_up.setStyleSheet("""
            QPushButton {
                background-color: #FFFFFF;
                border: 1px solid #D1D1D6;
                border-radius: 6px;
                font-size: 10px;
                color: #1D1D1F;
            }
            QPushButton:hover { background-color: #F5F5F7; border-color: #AEAEB2; }
            QPushButton:disabled { background-color: transparent; border-color: transparent; color: #AEAEB2; }
        """)
        self.btn_move_up.clicked.connect(self._move_current_up)
        header_row.addWidget(self.btn_move_up)

        self.btn_move_down = QPushButton("▼")
        self.btn_move_down.setToolTip("선택한 페이지를 한 칸 아래로 이동")
        self.btn_move_down.setFixedSize(26, 24)
        self.btn_move_down.setStyleSheet("""
            QPushButton {
                background-color: #FFFFFF;
                border: 1px solid #D1D1D6;
                border-radius: 6px;
                font-size: 10px;
                color: #1D1D1F;
            }
            QPushButton:hover { background-color: #F5F5F7; border-color: #AEAEB2; }
            QPushButton:disabled { background-color: transparent; border-color: transparent; color: #AEAEB2; }
        """)
        self.btn_move_down.clicked.connect(self._move_current_down)
        header_row.addWidget(self.btn_move_down)

        self.btn_reorder_all = QPushButton("순서 관리")
        self.btn_reorder_all.setToolTip("전체 페이지 순서 변경 대화상자 열기")
        self.btn_reorder_all.setFixedHeight(24)
        self.btn_reorder_all.setStyleSheet("""
            QPushButton {
                background-color: #FFFFFF;
                border: 1px solid #D1D1D6;
                border-radius: 6px;
                font-size: 11px;
                font-weight: 500;
                padding: 0 8px;
                color: #1D1D1F;
            }
            QPushButton:hover { background-color: #F5F5F7; border-color: #AEAEB2; }
        """)
        self.btn_reorder_all.clicked.connect(self.page_reorder_requested.emit)
        header_row.addWidget(self.btn_reorder_all)

        layout.addLayout(header_row)

        self.list_widget = QListWidget()
        self.list_widget.setIconSize(QSize(120, 160))
        self.list_widget.setViewMode(QListWidget.ViewMode.IconMode)
        self.list_widget.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list_widget.setMovement(QListWidget.Movement.Static)
        self.list_widget.setSpacing(10)
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._show_context_menu)
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        self.list_widget.currentRowChanged.connect(self._on_row_changed)

        self.list_widget.setStyleSheet("""
            QListWidget {
                border: none;
                background-color: #F2F2F7;
            }
            QListWidget::item {
                border: 1px solid #E5E5EA;
                border-radius: 8px;
                background-color: #FFFFFF;
                color: #1D1D1F;
                font-size: 11px;
                font-weight: 500;
                padding: 6px;
                margin: 4px;
            }
            QListWidget::item:hover {
                border: 1px solid #C7C7CC;
                background-color: #FAFAFC;
            }
            QListWidget::item:selected {
                border: 2px solid #007AFF;
                background-color: #EBF3FF;
                color: #007AFF;
                font-weight: 600;
            }
        """)

        layout.addWidget(self.list_widget)
        self._update_btn_states()

    def load_thumbnails(self, engine: PdfEngine):
        """PDF 문서의 각 페이지 썸네일 고속 로드 (초기 4페이지 즉시 로드 후 나머지 백그라운드 지연 처리)"""
        self.pdf_engine = engine
        self._load_gen += 1
        current_gen = self._load_gen
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
            item.setSizeHint(QSize(140, 180))
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

        # 나머지 페이지가 있다면 UI 블로킹 없이 분할 비동기 로드
        if total_pages > initial_count:
            QTimer.singleShot(10, lambda: self._load_remaining_thumbnails(current_gen, initial_count))

    def _load_remaining_thumbnails(self, gen_id: int, start_idx: int, batch_size: int = 4):
        """나머지 썸네일을 배치 단위로 비동기 로드하여 GUI 반응성 100% 유지"""
        if gen_id != self._load_gen or not self.pdf_engine or not self.pdf_engine.is_loaded():
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
            QTimer.singleShot(5, lambda: self._load_remaining_thumbnails(gen_id, end_idx, batch_size))

    def select_page(self, page_idx: int):
        """외부에서 페이지 변경 시 썸네일 포커스 동기화"""
        if 0 <= page_idx < self.list_widget.count():
            self.list_widget.blockSignals(True)
            self.list_widget.setCurrentRow(page_idx)
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
        cnt = self.pdf_engine.page_count
        if self.pdf_engine and 0 <= page_idx < cnt - 1:
            if self.pdf_engine.move_page(page_idx, cnt - 1):
                self.load_thumbnails(self.pdf_engine)
                self.select_page(cnt - 1)
                self.page_order_changed.emit()

    def _show_context_menu(self, pos):
        item = self.list_widget.itemAt(pos)
        if not item or not self.pdf_engine:
            return

        page_idx = self.list_widget.row(item)
        cnt = self.list_widget.count()
        menu = QMenu(self)

        # 1. 순서 이동 액션
        act_up = QAction("▲ 한 페이지 앞으로 (위로)", self)
        act_up.setEnabled(page_idx > 0)
        act_up.triggered.connect(self._move_current_up)
        menu.addAction(act_up)

        act_down = QAction("▼ 한 페이지 뒤로 (아래로)", self)
        act_down.setEnabled(page_idx < cnt - 1)
        act_down.triggered.connect(self._move_current_down)
        menu.addAction(act_down)

        act_top = QAction("⏫ 맨 앞으로 이동", self)
        act_top.setEnabled(page_idx > 0)
        act_top.triggered.connect(lambda: self._move_to_top(page_idx))
        menu.addAction(act_top)

        act_bottom = QAction("⏬ 맨 뒤로 이동", self)
        act_bottom.setEnabled(page_idx < cnt - 1)
        act_bottom.triggered.connect(lambda: self._move_to_bottom(page_idx))
        menu.addAction(act_bottom)

        menu.addSeparator()

        act_reorder_dlg = QAction("📑 페이지 순서 전체 관리...", self)
        act_reorder_dlg.triggered.connect(self.page_reorder_requested.emit)
        menu.addAction(act_reorder_dlg)

        menu.addSeparator()

        # 2. 회전 및 삭제
        act_rot_cw = QAction("시계 방향으로 90° 회전", self)
        act_rot_cw.triggered.connect(lambda: self.page_rotated.emit(page_idx, 90))
        menu.addAction(act_rot_cw)

        act_rot_ccw = QAction("반시계 방향으로 90° 회전", self)
        act_rot_ccw.triggered.connect(lambda: self.page_rotated.emit(page_idx, 270))
        menu.addAction(act_rot_ccw)

        menu.addSeparator()

        act_del = QAction("이 페이지 삭제", self)
        act_del.triggered.connect(lambda: self._confirm_delete(page_idx))
        menu.addAction(act_del)

        menu.exec(self.list_widget.mapToGlobal(pos))

    def _confirm_delete(self, page_idx: int):
        if self.list_widget.count() <= 1:
            QMessageBox.warning(self, "경고", "최소 1페이지 이상 존재해야 하므로 삭제할 수 없습니다.")
            return

        reply = QMessageBox.question(
            self,
            "페이지 삭제 확인",
            f"{page_idx + 1}페이지를 삭제하시겠습니까?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.page_deleted.emit(page_idx)
