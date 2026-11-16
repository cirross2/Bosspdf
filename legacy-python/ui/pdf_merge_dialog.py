"""
여러 PDF 파일을 원하는 순서로 하나의 PDF로 합치는 대화상자 (Dialog)
- 탐색기 우클릭 'BossPDF로 PDF 합치기' 및 ☰ 메뉴에서 사용
"""
import os
from typing import Dict, List, Optional
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QListWidget,
    QListWidgetItem, QLabel, QFileDialog, QProgressBar, QMessageBox,
    QAbstractItemView, QFrame, QApplication
)
from PySide6.QtCore import Qt, QTimer

from core import pdf_merge
from core.settings_manager import AppSettings
from ui.theme import AppleTheme


class PdfMergeDialog(QDialog):
    """PDF 파일 목록을 재배열한 뒤 단일 PDF로 합치는 다이얼로그"""

    def __init__(self, parent=None, initial_files: Optional[List[str]] = None,
                 queue_channel: Optional[str] = None):
        super().__init__(parent)
        self.setWindowTitle("BossPDF - PDF 합치기")
        self.resize(640, 520)
        self.setAcceptDrops(True)

        self._theme = AppSettings.get_theme_mode(default=AppleTheme.LIGHT)
        self._passwords: Dict[str, str] = {}
        self._output_pdf_path: Optional[str] = None
        self._init_ui()

        if initial_files:
            self._add_files(sorted(initial_files, key=pdf_merge.natural_sort_key))

        # 탐색기가 파일마다 프로세스를 따로 띄우므로, 늦게 도착한 파일도 계속 받아서 목록에 추가
        self._queue_channel = queue_channel
        if queue_channel:
            self._queue_timer = QTimer(self)
            self._queue_timer.setInterval(300)
            self._queue_timer.timeout.connect(self._poll_queue)
            self._queue_timer.start()

    # ------------------------------------------------------------------ UI
    def _init_ui(self):
        p = AppleTheme.get_palette(self._theme)
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)

        info_label = QLabel(
            "<b>PDF 파일들을 목록 순서대로 하나의 PDF로 합칩니다.</b><br>"
            f"<small style='color: {p['TEXT_SECONDARY']};'>파일을 끌어다 놓거나 [PDF 추가]를 누르세요. "
            "목록을 드래그하거나 버튼으로 순서를 바꿀 수 있습니다.</small>"
        )
        info_label.setTextFormat(Qt.TextFormat.RichText)
        info_label.setWordWrap(True)
        main_layout.addWidget(info_label)

        content_layout = QHBoxLayout()

        self.list_widget = QListWidget()
        self.list_widget.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list_widget.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list_widget.setStyleSheet(f"""
            QListWidget {{
                border: 1px solid {p['BORDER_STANDARD']};
                border-radius: 8px;
                background-color: {p['CARD_BG']};
                color: {p['TEXT_PRIMARY']};
                padding: 4px;
            }}
            QListWidget::item {{
                border-bottom: 1px solid {p['BORDER_SUBTLE']};
                padding: 8px 6px;
                border-radius: 6px;
            }}
            QListWidget::item:selected {{
                background-color: {p['ACCENT_TINT']};
                color: {p['ACCENT_BLUE']};
            }}
        """)
        self.list_widget.model().rowsMoved.connect(lambda *_: self._update_ui_state())
        content_layout.addWidget(self.list_widget, stretch=1)

        btn_col = QVBoxLayout()
        btn_col.setSpacing(8)

        self.btn_add = QPushButton("PDF 추가")
        self.btn_add.clicked.connect(self._on_add_pdfs)
        btn_col.addWidget(self.btn_add)

        self.btn_up = QPushButton("▲ 위로 이동")
        self.btn_up.clicked.connect(lambda: self._move_item(-1))
        btn_col.addWidget(self.btn_up)

        self.btn_down = QPushButton("▼ 아래로 이동")
        self.btn_down.clicked.connect(lambda: self._move_item(1))
        btn_col.addWidget(self.btn_down)

        self.btn_sort = QPushButton("이름순 정렬")
        self.btn_sort.clicked.connect(self._sort_by_name)
        btn_col.addWidget(self.btn_sort)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        btn_col.addWidget(line)

        self.btn_remove = QPushButton("목록에서 빼기")
        self.btn_remove.setStyleSheet(AppleTheme.destructive_button_style(self._theme))
        self.btn_remove.clicked.connect(self._remove_selected)
        btn_col.addWidget(self.btn_remove)

        btn_col.addStretch()

        self.lbl_count = QLabel("")
        self.lbl_count.setStyleSheet(f"font-weight: 600; color: {p['TEXT_SECONDARY']};")
        btn_col.addWidget(self.lbl_count)

        content_layout.addLayout(btn_col)
        main_layout.addLayout(content_layout)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)

        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()

        self.btn_close = QPushButton("닫기")
        self.btn_close.setStyleSheet(AppleTheme.secondary_button_style(self._theme))
        self.btn_close.clicked.connect(self.reject)
        bottom_layout.addWidget(self.btn_close)

        self.btn_merge = QPushButton("하나의 PDF로 합치기")
        self.btn_merge.setStyleSheet(AppleTheme.primary_button_style(self._theme))
        self.btn_merge.setDefault(True)
        self.btn_merge.clicked.connect(self._on_merge)
        bottom_layout.addWidget(self.btn_merge)

        main_layout.addLayout(bottom_layout)
        self._update_ui_state()

    # --------------------------------------------------------------- 목록
    def pdf_paths(self) -> List[str]:
        return [self.list_widget.item(i).data(Qt.ItemDataRole.UserRole)
                for i in range(self.list_widget.count())]

    def get_output_pdf_path(self) -> Optional[str]:
        return self._output_pdf_path

    def _add_files(self, files: List[str]):
        existing = {os.path.normcase(p) for p in self.pdf_paths()}
        for fpath in files:
            norm = os.path.normpath(fpath)
            if not norm.lower().endswith(".pdf") or not os.path.isfile(norm):
                continue
            if os.path.normcase(norm) in existing:
                continue
            existing.add(os.path.normcase(norm))
            self._create_list_item(norm)
        self._update_ui_state()

    def _create_list_item(self, fpath: str):
        try:
            pages = pdf_merge.get_page_count(fpath)
            detail = f"{pages}쪽" if pages is not None else "암호 걸림"
        except Exception:
            detail = "열 수 없음"
        size_kb = os.path.getsize(fpath) / 1024
        size_str = f"{size_kb / 1024:.1f} MB" if size_kb >= 1024 else f"{max(1, round(size_kb))} KB"
        item = QListWidgetItem(f"{os.path.basename(fpath)}\n{detail} · {size_str}")
        item.setData(Qt.ItemDataRole.UserRole, fpath)
        item.setToolTip(fpath)
        self.list_widget.addItem(item)

    def _poll_queue(self):
        from core.ipc_manager import drain_queue
        late = drain_queue(self._queue_channel)
        if late:
            self._add_files(sorted(late, key=pdf_merge.natural_sort_key))
            if self.isMinimized():
                self.showNormal()
            self.raise_()
            self.activateWindow()

    def _move_item(self, delta: int):
        row = self.list_widget.currentRow()
        target = row + delta
        if row < 0 or not (0 <= target < self.list_widget.count()):
            return
        item = self.list_widget.takeItem(row)
        self.list_widget.insertItem(target, item)
        self.list_widget.setCurrentRow(target)

    def _sort_by_name(self):
        paths = sorted(self.pdf_paths(), key=pdf_merge.natural_sort_key)
        self.list_widget.clear()
        for path in paths:
            self._create_list_item(path)
        self._update_ui_state()

    def _remove_selected(self):
        row = self.list_widget.currentRow()
        if row >= 0:
            self.list_widget.takeItem(row)
            self._update_ui_state()

    def _update_ui_state(self):
        cnt = self.list_widget.count()
        self.lbl_count.setText(f"총 {cnt}개 파일")
        self.btn_merge.setEnabled(cnt >= 2)

    # ------------------------------------------------------- 끌어다 놓기
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        files = [u.toLocalFile() for u in event.mimeData().urls()]
        self._add_files(sorted(files, key=pdf_merge.natural_sort_key))

    def _on_add_pdfs(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "합칠 PDF 파일 선택 (여러 개 선택 가능)",
            AppSettings.get_last_open_dir(), "PDF 파일 (*.pdf)"
        )
        if files:
            self._add_files(files)

    # --------------------------------------------------------------- 병합
    def _collect_passwords(self, paths: List[str]) -> bool:
        """암호 걸린 문서의 비밀번호를 받아 둔다. 사용자가 취소하면 False"""
        from ui.password_dialog import PasswordDialog
        for path in paths:
            if path in self._passwords:
                continue
            try:
                locked = pdf_merge.needs_password(path)
            except Exception:
                continue  # 열 수 없는 파일은 병합 단계에서 오류로 안내
            if not locked:
                continue
            pw = PasswordDialog.get_password(
                parent=self, filename=os.path.basename(path),
                verifier=lambda value, p=path: pdf_merge.check_password(p, value)
            )
            if pw is None:
                return False
            self._passwords[path] = pw
        return True

    def _on_merge(self):
        paths = self.pdf_paths()
        if len(paths) < 2:
            QMessageBox.warning(self, "PDF 합치기", "합칠 PDF를 2개 이상 추가해주세요.")
            return
        if not self._collect_passwords(paths):
            return

        save_path, _ = QFileDialog.getSaveFileName(
            self, "합친 PDF 저장", pdf_merge.suggest_output_path(paths), "PDF 파일 (*.pdf)"
        )
        if not save_path:
            return
        if not save_path.lower().endswith(".pdf"):
            save_path += ".pdf"

        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(len(paths))
        self.progress_bar.setValue(0)
        self.btn_merge.setEnabled(False)

        def on_progress(cur, total):
            self.progress_bar.setValue(cur)
            QApplication.processEvents()

        try:
            self._output_pdf_path = pdf_merge.merge_pdfs(
                paths, save_path, passwords=self._passwords, progress_callback=on_progress
            )
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "PDF 합치기", f"PDF를 합치는 중 오류가 발생했습니다:\n{e}")
        finally:
            self.progress_bar.setVisible(False)
            self._update_ui_state()
