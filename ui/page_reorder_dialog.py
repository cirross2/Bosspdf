"""
페이지 순서 변경, 삭제, 회전을 한눈에 관리하는 페이지 정렬 대화상자
"""
from typing import List, Optional
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QListWidget,
    QListWidgetItem, QLabel, QMessageBox, QAbstractItemView, QFrame
)
from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QIcon, QPixmap

from core.pdf_engine import PdfEngine
from ui.theme import AppleTheme


class PageReorderDialog(QDialog):
    """
    모든 페이지의 썸네일을 보며 마우스 드래그 또는 버튼으로
    순서를 직관적으로 바꾸고 회전/삭제할 수 있는 대화상자
    """
    order_changed = Signal(list)  # 새로운 페이지 순서 목록(0-indexed) 전달

    def __init__(self, pdf_engine: PdfEngine, parent=None):
        super().__init__(parent)
        self.setWindowTitle("페이지 순서 변경 및 관리")
        self.resize(780, 620)

        self.pdf_engine = pdf_engine
        # 각 아이템에 원래의 0-based page_index 저장
        self.current_order: List[int] = list(range(pdf_engine.page_count))

        self._init_ui()
        self._load_pages()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)

        # 상단 안내
        info = QLabel(
            "<b>페이지를 원하는 순서대로 드래그 앤 드롭하거나 우측 버튼으로 순서를 변경하세요.</b><br>"
            "<small style='color: #666;'>[적용하기]를 누르면 문서의 페이지 순서가 즉시 재배치됩니다.</small>"
        )
        info.setTextFormat(Qt.TextFormat.RichText)
        main_layout.addWidget(info)

        # 중앙: 리스트 + 우측 제어 버튼
        content_layout = QHBoxLayout()

        self.list_widget = QListWidget()
        self.list_widget.setIconSize(QSize(110, 150))
        self.list_widget.setViewMode(QListWidget.ViewMode.IconMode)
        self.list_widget.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list_widget.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list_widget.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list_widget.setSpacing(12)
        self.list_widget.model().rowsMoved.connect(self._on_rows_moved)
        self.list_widget.itemSelectionChanged.connect(self._update_button_states)

        self.list_widget.setStyleSheet("""
            QListWidget {
                border: 1px solid #D1D1D6;
                border-radius: 8px;
                background-color: #F2F2F7;
                padding: 8px;
            }
            QListWidget::item {
                border: 1px solid #E5E5EA;
                border-radius: 8px;
                background-color: #FFFFFF;
                padding: 6px;
                color: #1D1D1F;
                font-size: 11px;
                font-weight: 500;
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
        content_layout.addWidget(self.list_widget, stretch=1)

        # 우측 순서 변경 버튼 열
        btn_col = QVBoxLayout()
        btn_col.setSpacing(8)

        self.btn_top = QPushButton("⏫ 맨 앞으로")
        self.btn_top.clicked.connect(self._move_to_top)
        btn_col.addWidget(self.btn_top)

        self.btn_up = QPushButton("▲ 앞으로 (위로)")
        self.btn_up.clicked.connect(self._move_up)
        btn_col.addWidget(self.btn_up)

        self.btn_down = QPushButton("▼ 뒤로 (아래로)")
        self.btn_down.clicked.connect(self._move_down)
        btn_col.addWidget(self.btn_down)

        self.btn_bottom = QPushButton("⏬ 맨 뒤로")
        self.btn_bottom.clicked.connect(self._move_to_bottom)
        btn_col.addWidget(self.btn_bottom)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        btn_col.addWidget(line)

        self.lbl_selected_info = QLabel("선택된 페이지 없음")
        self.lbl_selected_info.setStyleSheet("color: #86868B; font-size: 11px;")
        btn_col.addWidget(self.lbl_selected_info)

        btn_col.addStretch()
        content_layout.addLayout(btn_col)

        main_layout.addLayout(content_layout)

        # 하단 확인/취소 버튼
        bottom_layout = QHBoxLayout()
        self.lbl_summary = QLabel(f"총 {self.pdf_engine.page_count}페이지")
        self.lbl_summary.setStyleSheet("font-weight: 600; color: #1D1D1F;")
        bottom_layout.addWidget(self.lbl_summary)

        bottom_layout.addStretch()

        self.btn_cancel = QPushButton("취소")
        self.btn_cancel.setStyleSheet(AppleTheme.secondary_button_style())
        self.btn_cancel.clicked.connect(self.reject)
        bottom_layout.addWidget(self.btn_cancel)

        self.btn_apply = QPushButton("순서 적용하기")
        self.btn_apply.setStyleSheet(AppleTheme.primary_button_style())
        self.btn_apply.clicked.connect(self._on_apply)
        bottom_layout.addWidget(self.btn_apply)

        main_layout.addLayout(bottom_layout)

    def _load_pages(self):
        """문서 페이지 썸네일 로드"""
        self.list_widget.clear()
        for orig_idx in self.current_order:
            pixmap = self.pdf_engine.get_thumbnail(orig_idx, max_size=130)
            item = QListWidgetItem(QIcon(pixmap), f"{orig_idx + 1} p")
            item.setData(Qt.ItemDataRole.UserRole, orig_idx)
            item.setSizeHint(QSize(130, 180))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.list_widget.addItem(item)

        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)
        self._refresh_labels()

    def _refresh_labels(self):
        """현재 배치 순서에 맞게 텍스트 라벨 갱신 (예: '1페이지 (원래 3p)')"""
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            orig_idx = item.data(Qt.ItemDataRole.UserRole)
            if i == orig_idx:
                item.setText(f"{i + 1} p")
            else:
                item.setText(f"{i + 1} p\n(원래 {orig_idx + 1}p)")

    def _on_rows_moved(self, parent, start, end, destination, row):
        self._sync_order_from_list()
        self._refresh_labels()
        self._update_button_states()

    def _sync_order_from_list(self):
        new_order = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            new_order.append(item.data(Qt.ItemDataRole.UserRole))
        self.current_order = new_order

    def _move_up(self):
        row = self.list_widget.currentRow()
        if row > 0:
            item = self.list_widget.takeItem(row)
            self.list_widget.insertItem(row - 1, item)
            self.list_widget.setCurrentRow(row - 1)
            self._sync_order_from_list()
            self._refresh_labels()
            self._update_button_states()

    def _move_down(self):
        row = self.list_widget.currentRow()
        if 0 <= row < self.list_widget.count() - 1:
            item = self.list_widget.takeItem(row)
            self.list_widget.insertItem(row + 1, item)
            self.list_widget.setCurrentRow(row + 1)
            self._sync_order_from_list()
            self._refresh_labels()
            self._update_button_states()

    def _move_to_top(self):
        row = self.list_widget.currentRow()
        if row > 0:
            item = self.list_widget.takeItem(row)
            self.list_widget.insertItem(0, item)
            self.list_widget.setCurrentRow(0)
            self._sync_order_from_list()
            self._refresh_labels()
            self._update_button_states()

    def _move_to_bottom(self):
        row = self.list_widget.currentRow()
        if 0 <= row < self.list_widget.count() - 1:
            item = self.list_widget.takeItem(row)
            self.list_widget.insertItem(self.list_widget.count(), item)
            self.list_widget.setCurrentRow(self.list_widget.count() - 1)
            self._sync_order_from_list()
            self._refresh_labels()
            self._update_button_states()

    def _update_button_states(self):
        row = self.list_widget.currentRow()
        cnt = self.list_widget.count()
        self.btn_top.setEnabled(row > 0)
        self.btn_up.setEnabled(row > 0)
        self.btn_down.setEnabled(0 <= row < cnt - 1)
        self.btn_bottom.setEnabled(0 <= row < cnt - 1)

        if 0 <= row < cnt:
            orig = self.list_widget.item(row).data(Qt.ItemDataRole.UserRole)
            self.lbl_selected_info.setText(f"현재 {row + 1}번째\n(원본 {orig + 1}페이지)")
        else:
            self.lbl_selected_info.setText("선택된 페이지 없음")

    def _on_apply(self):
        self._sync_order_from_list()
        # 원래 순서와 달라졌는지 확인
        original = list(range(self.pdf_engine.page_count))
        if self.current_order == original:
            self.accept()
            return

        success = self.pdf_engine.reorder_pages(self.current_order)
        if success:
            self.order_changed.emit(self.current_order)
            self.accept()
        else:
            QMessageBox.critical(self, "오류", "페이지 순서 재배치에 실패했습니다.")
