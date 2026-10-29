"""
다중 이미지를 선택한 순서대로 PDF로 일괄 합치는 대화상자 (Dialog)
"""
import os
from typing import List, Optional
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QListWidget,
    QListWidgetItem, QLabel, QFileDialog, QRadioButton, QButtonGroup,
    QComboBox, QProgressBar, QMessageBox, QAbstractItemView, QWidget,
    QFrame
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QIcon, QPixmap, QImageReader

from core.image_to_pdf import ImageToPdfConverter
from core.settings_manager import AppSettings
from ui.theme import AppleTheme


class ImageMergeDialog(QDialog):
    """
    이미지 파일들을 선택하고, 원하는 순서로 재배열한 후
    단일 PDF 파일로 즉시 합치는 다이얼로그
    """
    pdf_created = Signal(str)  # 생성된 PDF 파일 경로 전달 시그널

    def __init__(self, parent=None, initial_files: Optional[List[str]] = None):
        super().__init__(parent)
        self.setWindowTitle("BossPDF - 이미지들을 PDF로 합치기")
        self.resize(720, 600)
        self.setAcceptDrops(True)

        self.image_paths: List[str] = []
        self._init_ui()

        if initial_files:
            valid_exts = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tiff", ".tif"}
            filtered = [
                f for f in initial_files
                if os.path.exists(f) and os.path.splitext(f)[1].lower() in valid_exts
            ]
            if filtered:
                self._add_files(filtered)

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)

        # 상단 안내 문구
        info_label = QLabel(
            "<b>이미지 파일들을 선택한 순서대로 단일 PDF 문서로 합칩니다.</b><br>"
            "<small style='color: #666;'>파일을 목록으로 직접 드래그 앤 드롭하거나 [이미지 추가] 버튼을 누르세요. "
            "목록에서 마우스 드래그 또는 버튼으로 최종 순서를 변경할 수 있습니다.</small>"
        )
        info_label.setTextFormat(Qt.TextFormat.RichText)
        main_layout.addWidget(info_label)

        # 중앙 목록 및 순서 조정 버튼
        content_layout = QHBoxLayout()

        # 이미지 리스트 위젯
        self.list_widget = QListWidget()
        self.list_widget.setIconSize(QSize(64, 64))
        self.list_widget.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list_widget.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list_widget.setStyleSheet("""
            QListWidget {
                border: 1px solid #D1D1D6;
                border-radius: 8px;
                background-color: #FFFFFF;
                padding: 4px;
            }
            QListWidget::item {
                border-bottom: 1px solid #E5E5EA;
                padding: 6px;
                border-radius: 6px;
            }
            QListWidget::item:hover {
                background-color: #F8F8FA;
            }
            QListWidget::item:selected {
                background-color: #EBF3FF;
                color: #007AFF;
                font-weight: 500;
            }
        """)
        content_layout.addWidget(self.list_widget, stretch=1)

        # 순서 제어 및 관리 버튼 열
        btn_col = QVBoxLayout()
        btn_col.setSpacing(8)

        self.btn_add = QPushButton("➕ 이미지 추가")
        self.btn_add.clicked.connect(self._on_add_images)
        btn_col.addWidget(self.btn_add)

        self.btn_up = QPushButton("▲ 위로 이동")
        self.btn_up.clicked.connect(self._move_item_up)
        btn_col.addWidget(self.btn_up)

        self.btn_down = QPushButton("▼ 아래로 이동")
        self.btn_down.clicked.connect(self._move_item_down)
        btn_col.addWidget(self.btn_down)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        btn_col.addWidget(line)

        self.btn_remove = QPushButton("선택 삭제")
        self.btn_remove.setStyleSheet(AppleTheme.destructive_button_style())
        self.btn_remove.clicked.connect(self._remove_selected)
        btn_col.addWidget(self.btn_remove)

        self.btn_clear = QPushButton("전체 비우기")
        self.btn_clear.clicked.connect(self._clear_all)
        btn_col.addWidget(self.btn_clear)

        btn_col.addStretch()

        self.lbl_count = QLabel("총 0장 선택됨")
        self.lbl_count.setStyleSheet("font-weight: bold; color: #444;")
        btn_col.addWidget(self.lbl_count)

        content_layout.addLayout(btn_col)
        main_layout.addLayout(content_layout)

        # 변환 옵션 패널
        opt_box = QFrame()
        opt_box.setStyleSheet("background-color: #f4f6f8; border-radius: 6px; padding: 6px;")
        opt_layout = QVBoxLayout(opt_box)
        opt_layout.setSpacing(6)

        lbl_opt = QLabel("<b>변환 옵션</b>")
        lbl_opt.setTextFormat(Qt.TextFormat.RichText)
        opt_layout.addWidget(lbl_opt)

        opt_row = QHBoxLayout()
        self.rb_fit_a4 = QRadioButton("A4 용지 맞춤 (가로/세로 자동 최적화 & 비율 유지)")
        self.rb_fit_a4.setChecked(True)
        self.rb_orig = QRadioButton("이미지 본래 크기(원본 해상도) 유지")
        self.btn_group = QButtonGroup(self)
        self.btn_group.addButton(self.rb_fit_a4)
        self.btn_group.addButton(self.rb_orig)

        opt_row.addWidget(self.rb_fit_a4)
        opt_row.addWidget(self.rb_orig)
        opt_row.addStretch()

        # 여백 선택
        opt_row.addWidget(QLabel("여백:"))
        self.combo_margin = QComboBox()
        self.combo_margin.addItems(["여백 없음 (0 pt)", "좁게 (10 pt)", "기본 (20 pt)", "넓게 (36 pt)"])
        self.combo_margin.setCurrentIndex(2)  # 기본
        opt_row.addWidget(self.combo_margin)

        opt_layout.addLayout(opt_row)
        main_layout.addWidget(opt_box)

        # 진행 상태 바
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        main_layout.addWidget(self.progress_bar)

        # 하단 버튼
        bottom_layout = QHBoxLayout()
        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet("color: #2e7d32; font-weight: bold;")
        bottom_layout.addWidget(self.lbl_status)
        bottom_layout.addStretch()

        self.btn_close = QPushButton("닫기")
        self.btn_close.setStyleSheet(AppleTheme.secondary_button_style())
        self.btn_close.clicked.connect(self.reject)
        bottom_layout.addWidget(self.btn_close)

        self.btn_convert = QPushButton("PDF로 즉시 합치기")
        self.btn_convert.setStyleSheet(AppleTheme.primary_button_style())
        self.btn_convert.clicked.connect(self._on_convert)
        bottom_layout.addWidget(self.btn_convert)

        main_layout.addLayout(bottom_layout)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        valid_exts = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tiff", ".gif"}
        files = []
        for url in urls:
            path = url.toLocalFile()
            ext = os.path.splitext(path)[1].lower()
            if ext in valid_exts and os.path.exists(path):
                files.append(path)
        if files:
            self._add_files(files)

    def _on_add_images(self):
        init_dir = AppSettings.get_last_image_open_dir()
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "합칠 이미지 파일들을 선택하세요 (다중 선택 가능)",
            init_dir,
            "이미지 파일 (*.png *.jpg *.jpeg *.bmp *.webp *.tiff *.tif);;모든 파일 (*.*)"
        )
        if files:
            AppSettings.set_last_image_open_dir(files[0])
            self._add_files(files)

    def _add_files(self, files: List[str]):
        for fpath in files:
            norm_path = os.path.normpath(fpath)
            if norm_path not in self.image_paths:
                self.image_paths.append(norm_path)
                self._create_list_item(norm_path)
        self._update_ui_state()

    def _create_list_item(self, fpath: str):
        filename = os.path.basename(fpath)
        # 이미지 크기 및 썸네일 로드
        pixmap = QPixmap(fpath)
        if not pixmap.isNull():
            orig_size_str = f"{pixmap.width()} x {pixmap.height()}"
            icon_pixmap = pixmap.scaled(
                64, 64,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            icon = QIcon(icon_pixmap)
        else:
            orig_size_str = "알 수 없음"
            icon = QIcon()

        size_kb = os.path.getsize(fpath) / 1024.0
        text = f"{filename}\n({orig_size_str}, {size_kb:.1f} KB)"

        item = QListWidgetItem(icon, text)
        item.setData(Qt.ItemDataRole.UserRole, fpath)
        item.setToolTip(fpath)
        self.list_widget.addItem(item)

    def _move_item_up(self):
        curr_row = self.list_widget.currentRow()
        if curr_row > 0:
            item = self.list_widget.takeItem(curr_row)
            self.list_widget.insertItem(curr_row - 1, item)
            self.list_widget.setCurrentRow(curr_row - 1)
            self._sync_paths_from_list()

    def _move_item_down(self):
        curr_row = self.list_widget.currentRow()
        if curr_row >= 0 and curr_row < self.list_widget.count() - 1:
            item = self.list_widget.takeItem(curr_row)
            self.list_widget.insertItem(curr_row + 1, item)
            self.list_widget.setCurrentRow(curr_row + 1)
            self._sync_paths_from_list()

    def _remove_selected(self):
        curr_row = self.list_widget.currentRow()
        if curr_row >= 0:
            self.list_widget.takeItem(curr_row)
            self._sync_paths_from_list()
            self._update_ui_state()

    def _clear_all(self):
        self.list_widget.clear()
        self.image_paths.clear()
        self._update_ui_state()

    def _sync_paths_from_list(self):
        new_paths = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            new_paths.append(item.data(Qt.ItemDataRole.UserRole))
        self.image_paths = new_paths

    def _update_ui_state(self):
        cnt = self.list_widget.count()
        self.lbl_count.setText(f"총 {cnt}장 선택됨")
        self.btn_convert.setEnabled(cnt > 0)

    def _on_convert(self):
        self._sync_paths_from_list()
        if not self.image_paths:
            QMessageBox.warning(self, "경고", "합칠 이미지를 먼저 추가해주세요.")
            return

        # 저장할 PDF 경로 선택 (마지막 저장 폴더 기억)
        last_save_dir = AppSettings.get_last_image_save_dir()
        if last_save_dir:
            default_save = os.path.join(last_save_dir, "합쳐진_이미지_문서.pdf")
        else:
            first_dir = os.path.dirname(self.image_paths[0]) if self.image_paths else AppSettings.get_last_save_dir()
            default_save = os.path.join(first_dir or "", "합쳐진_이미지_문서.pdf")

        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "합쳐진 PDF 파일 저장",
            default_save,
            "PDF 파일 (*.pdf)"
        )
        if not save_path:
            return

        AppSettings.set_last_image_save_dir(save_path)

        # 여백 환산
        margin_idx = self.combo_margin.currentIndex()
        margins = [0.0, 10.0, 20.0, 36.0]
        margin = margins[margin_idx]
        fit_a4 = self.rb_fit_a4.isChecked()

        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(len(self.image_paths))
        self.progress_bar.setValue(0)
        self.btn_convert.setEnabled(False)

        def on_progress(cur, total):
            self.progress_bar.setValue(cur)
            self.lbl_status.setText(f"변환 중: {cur} / {total} 장 완료...")

        try:
            out_file = ImageToPdfConverter.convert_images_to_pdf(
                image_paths=self.image_paths,
                output_pdf_path=save_path,
                fit_a4=fit_a4,
                margin=margin,
                progress_callback=on_progress
            )
            self.lbl_status.setText("✅ 변환 완료!")
            QMessageBox.information(
                self,
                "성공",
                f"총 {len(self.image_paths)}장의 이미지가 순서대로 성공적으로 병합되었습니다!\n\n저장 경로: {out_file}"
            )
            self.pdf_created.emit(out_file)
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "오류 발생", f"PDF 생성 중 오류가 발생했습니다:\n{str(e)}")
            self.lbl_status.setText("❌ 오류 발생")
        finally:
            self.progress_bar.setVisible(False)
            self.btn_convert.setEnabled(True)
