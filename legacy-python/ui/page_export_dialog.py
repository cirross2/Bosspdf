"""
페이지 선택 추출 및 이미지 변환/이어붙이기 내보내기 대화상자 (Apple macOS 감성 UI)
"""
import os
import subprocess
from typing import Optional, List
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QWidget, QFrame, QRadioButton, QButtonGroup,
    QComboBox, QSpinBox, QFileDialog, QMessageBox
)
from PySide6.QtCore import Qt
from core.pdf_engine import PdfEngine
from core.settings_manager import AppSettings


class PageExportDialog(QDialog):
    """
    선택한 페이지만 분리하여 새 PDF로 저장하거나,
    개별 이미지 또는 하나로 이어 붙인 긴 이미지로 내보내는 대화상자
    """
    def __init__(self, parent: Optional[QWidget] = None, engine: Optional[PdfEngine] = None, current_page: int = 0):
        super().__init__(parent)
        self.engine = engine
        self.current_page = current_page
        self.total_pages = engine.page_count if engine and engine.is_loaded() else 1

        self._init_ui()
        self._update_page_preview()

    def _init_ui(self):
        self.setWindowTitle("페이지 내보내기 & 이미지 저장 - BossPDF")
        self.setFixedSize(560, 600)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(14)

        # 1. 상단 헤더
        header_layout = QHBoxLayout()
        header_layout.setSpacing(16)

        lbl_icon = QLabel("📑")
        lbl_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_icon.setStyleSheet("""
            QLabel {
                font-size: 28px;
                background-color: #F2F2F7;
                border-radius: 24px;
                min-width: 48px;
                max-width: 48px;
                min-height: 48px;
                max-height: 48px;
                border: 1px solid #E5E5EA;
            }
        """)
        header_layout.addWidget(lbl_icon)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(3)

        lbl_title = QLabel("페이지 내보내기 & 이미지 변환")
        lbl_title.setStyleSheet("font-size: 16px; font-weight: 700; color: #1D1D1F;")
        text_layout.addWidget(lbl_title)

        lbl_desc = QLabel("원하는 페이지만 추출하여 새 PDF로 저장하거나 이미지로 변환합니다.")
        lbl_desc.setStyleSheet("font-size: 12px; color: #86868B;")
        text_layout.addWidget(lbl_desc)

        header_layout.addLayout(text_layout)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        # 구분선
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.HLine)
        sep1.setStyleSheet("color: #E5E5EA; background-color: #E5E5EA; max-height: 1px;")
        layout.addWidget(sep1)

        # 2. 페이지 범위 선택 섹션
        lbl_sec1 = QLabel("1. 추출할 페이지 범위 선택")
        lbl_sec1.setStyleSheet("font-size: 13px; font-weight: 700; color: #1D1D1F;")
        layout.addWidget(lbl_sec1)

        self.grp_page_scope = QButtonGroup(self)

        self.rb_all_pages = QRadioButton(f"문서 전체 (1 ~ {self.total_pages}페이지)")
        self.rb_all_pages.setChecked(True)
        self.grp_page_scope.addButton(self.rb_all_pages, 0)
        layout.addWidget(self.rb_all_pages)

        cur_display = self.current_page + 1
        self.rb_cur_page = QRadioButton(f"현재 페이지만 ({cur_display}페이지)")
        self.grp_page_scope.addButton(self.rb_cur_page, 1)
        layout.addWidget(self.rb_cur_page)

        self.rb_custom_range = QRadioButton("페이지 범위 직접 지정:")
        self.grp_page_scope.addButton(self.rb_custom_range, 2)
        layout.addWidget(self.rb_custom_range)

        # 범위 입력창 및 퀵 프리셋 버튼
        range_input_layout = QHBoxLayout()
        range_input_layout.setContentsMargins(20, 0, 0, 0)
        range_input_layout.setSpacing(8)

        self.txt_range = QLineEdit()
        self.txt_range.setPlaceholderText(f"예: 1, 3, 5-{min(8, self.total_pages)}")
        self.txt_range.setText(f"1-{self.total_pages}")
        self.txt_range.setEnabled(False)
        self.txt_range.textChanged.connect(self._update_page_preview)
        range_input_layout.addWidget(self.txt_range, 1)

        self.btn_preset_all = QPushButton("전체")
        self.btn_preset_all.setFixedSize(50, 28)
        self.btn_preset_all.clicked.connect(lambda: self._set_preset_range(f"1-{self.total_pages}"))
        range_input_layout.addWidget(self.btn_preset_all)

        self.btn_preset_odd = QPushButton("홀수")
        self.btn_preset_odd.setFixedSize(50, 28)
        self.btn_preset_odd.clicked.connect(self._preset_odd_pages)
        range_input_layout.addWidget(self.btn_preset_odd)

        self.btn_preset_even = QPushButton("짝수")
        self.btn_preset_even.setFixedSize(50, 28)
        self.btn_preset_even.clicked.connect(self._preset_even_pages)
        range_input_layout.addWidget(self.btn_preset_even)

        layout.addLayout(range_input_layout)

        # 선택된 페이지 실시간 프리뷰 안내
        self.lbl_selected_preview = QLabel("선택된 페이지: 1 ~ {total} (총 {total}페이지)".format(total=self.total_pages))
        self.lbl_selected_preview.setStyleSheet("color: #007AFF; font-size: 11px; font-weight: 600; padding-left: 20px;")
        layout.addWidget(self.lbl_selected_preview)

        self.grp_page_scope.idToggled.connect(self._on_scope_changed)

        # 구분선
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet("color: #E5E5EA; background-color: #E5E5EA; max-height: 1px;")
        layout.addWidget(sep2)

        # 3. 내보내기 형식 섹션
        lbl_sec2 = QLabel("2. 내보내기 형식 선택")
        lbl_sec2.setStyleSheet("font-size: 13px; font-weight: 700; color: #1D1D1F;")
        layout.addWidget(lbl_sec2)

        self.grp_export_type = QButtonGroup(self)

        self.rb_type_pdf = QRadioButton("📑 선택한 페이지만 새 PDF 문서로 저장")
        self.rb_type_pdf.setChecked(True)
        self.grp_export_type.addButton(self.rb_type_pdf, 0)
        layout.addWidget(self.rb_type_pdf)

        self.rb_type_images = QRadioButton("🖼️ 페이지별 개별 이미지 파일로 분할 저장 (PNG/JPG)")
        self.grp_export_type.addButton(self.rb_type_images, 1)
        layout.addWidget(self.rb_type_images)

        self.rb_type_stitched = QRadioButton("📜 하나로 이어 붙인 긴 단일 이미지로 저장 (웹툰/스크롤형)")
        self.grp_export_type.addButton(self.rb_type_stitched, 2)
        layout.addWidget(self.rb_type_stitched)

        self.grp_export_type.idToggled.connect(self._on_export_type_changed)

        # 4. 이미지 세부 옵션 (DPI, 포맷, 간격)
        self.options_frame = QFrame()
        self.options_frame.setStyleSheet("""
            QFrame {
                background-color: #F8F8FA;
                border-radius: 8px;
                padding: 6px;
            }
        """)
        options_layout = QHBoxLayout(self.options_frame)
        options_layout.setContentsMargins(12, 8, 12, 8)
        options_layout.setSpacing(16)

        # 포맷 선택
        lbl_opt_fmt = QLabel("이미지 포맷:")
        lbl_opt_fmt.setStyleSheet("font-size: 12px; font-weight: 600; color: #48484A;")
        options_layout.addWidget(lbl_opt_fmt)

        self.combo_fmt = QComboBox()
        self.combo_fmt.addItems(["PNG (무손실 고화질)", "JPG (고품질 압축)"])
        options_layout.addWidget(self.combo_fmt)

        # 화질/DPI
        lbl_opt_dpi = QLabel("해상도:")
        lbl_opt_dpi.setStyleSheet("font-size: 12px; font-weight: 600; color: #48484A;")
        options_layout.addWidget(lbl_opt_dpi)

        self.combo_dpi = QComboBox()
        self.combo_dpi.addItem("일반 (100 DPI)", 100)
        self.combo_dpi.addItem("고화질 (150 DPI - 추천)", 150)
        self.combo_dpi.addItem("초고화질 (300 DPI - 인쇄용)", 300)
        self.combo_dpi.setCurrentIndex(1)
        options_layout.addWidget(self.combo_dpi)

        # 이어붙이기 여백
        self.lbl_spacing = QLabel("페이지 간격:")
        self.lbl_spacing.setStyleSheet("font-size: 12px; font-weight: 600; color: #48484A;")
        options_layout.addWidget(self.lbl_spacing)

        self.spin_spacing = QSpinBox()
        self.spin_spacing.setRange(0, 100)
        self.spin_spacing.setValue(10)
        self.spin_spacing.setSuffix(" px")
        options_layout.addWidget(self.spin_spacing)

        options_layout.addStretch()
        layout.addWidget(self.options_frame)
        self.options_frame.setEnabled(False)  # 초기 PDF 선택 시 비활성화

        layout.addStretch()

        # 5. 하단 버튼 (취소 / 내보내기 실행)
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        btn_layout.addStretch()

        btn_cancel = QPushButton("취소")
        btn_cancel.setFixedSize(85, 34)
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #E5E5EA;
                color: #1D1D1F;
                border: none;
                border-radius: 8px;
                font-size: 13px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #D1D1D6;
            }
        """)
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        self.btn_export = QPushButton("내보내기 실행...")
        self.btn_export.setFixedSize(140, 34)
        self.btn_export.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_export.setStyleSheet("""
            QPushButton {
                background-color: #007AFF;
                color: #FFFFFF;
                border: none;
                border-radius: 8px;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #0062CC;
            }
            QPushButton:pressed {
                background-color: #004FB3;
            }
        """)
        self.btn_export.clicked.connect(self._execute_export)
        btn_layout.addWidget(self.btn_export)

        layout.addLayout(btn_layout)

    def _on_scope_changed(self, btn_id: int, checked: bool):
        if not checked:
            return
        self.txt_range.setEnabled(btn_id == 2)
        if btn_id == 2:
            self.txt_range.setFocus()
            self.txt_range.selectAll()
        self._update_page_preview()

    def _on_export_type_changed(self, btn_id: int, checked: bool):
        if not checked:
            return
        is_image_mode = (btn_id in [1, 2])
        self.options_frame.setEnabled(is_image_mode)
        is_stitched = (btn_id == 2)
        self.lbl_spacing.setVisible(is_stitched)
        self.spin_spacing.setVisible(is_stitched)

    def _set_preset_range(self, range_text: str):
        self.rb_custom_range.setChecked(True)
        self.txt_range.setEnabled(True)
        self.txt_range.setText(range_text)

    def _preset_odd_pages(self):
        odds = [str(i) for i in range(1, self.total_pages + 1, 2)]
        self._set_preset_range(", ".join(odds))

    def _preset_even_pages(self):
        evens = [str(i) for i in range(2, self.total_pages + 1, 2)]
        self._set_preset_range(", ".join(evens))

    def parse_selected_pages(self) -> List[int]:
        """
        선택된 옵션에 따라 0-indexed 페이지 번호 목록을 파싱하여 반환합니다.
        """
        scope_id = self.grp_page_scope.checkedId()
        if scope_id == 0:
            return list(range(self.total_pages))
        elif scope_id == 1:
            return [self.current_page]

        # 직접 범위 파싱 (예: 1, 3, 5-8)
        text = self.txt_range.text().strip()
        if not text:
            return []

        selected = set()
        parts = text.replace(";", ",").split(",")
        for part in parts:
            part = part.strip()
            if not part:
                continue
            if "-" in part:
                sub = part.split("-")
                if len(sub) == 2:
                    try:
                        start = int(sub[0].strip())
                        end = int(sub[1].strip())
                        for p in range(min(start, end), max(start, end) + 1):
                            if 1 <= p <= self.total_pages:
                                selected.add(p - 1)
                    except ValueError:
                        pass
            else:
                try:
                    p = int(part)
                    if 1 <= p <= self.total_pages:
                        selected.add(p - 1)
                except ValueError:
                    pass

        return sorted(list(selected))

    def _update_page_preview(self):
        pages = self.parse_selected_pages()
        count = len(pages)
        if count == 0:
            self.lbl_selected_preview.setText("⚠️ 유효한 페이지가 선택되지 않았습니다.")
            self.lbl_selected_preview.setStyleSheet("color: #FF3B30; font-size: 11px; font-weight: 600; padding-left: 20px;")
            self.btn_export.setEnabled(False)
        else:
            display_list = [str(p + 1) for p in pages]
            if len(display_list) > 12:
                summary_str = f"{display_list[0]}, {display_list[1]}, ... {display_list[-1]}"
            else:
                summary_str = ", ".join(display_list)
            self.lbl_selected_preview.setText(f"선택된 페이지: {summary_str} (총 {count}페이지 선택됨)")
            self.lbl_selected_preview.setStyleSheet("color: #007AFF; font-size: 11px; font-weight: 600; padding-left: 20px;")
            self.btn_export.setEnabled(True)

    def _execute_export(self):
        pages = self.parse_selected_pages()
        if not pages:
            QMessageBox.warning(self, "안내", "내보낼 페이지를 1개 이상 선택해주세요.")
            return

        export_type = self.grp_export_type.checkedId()
        last_dir = AppSettings.get_last_save_dir() or ""
        doc_name = os.path.splitext(os.path.basename(self.engine.file_path or "문서"))[0]

        try:
            # 1. 새 PDF로 저장
            if export_type == 0:
                default_name = f"{doc_name}_선택페이지({len(pages)}p).pdf"
                default_path = os.path.join(last_dir, default_name) if last_dir else default_name

                save_path, _ = QFileDialog.getSaveFileName(
                    self,
                    "선택한 페이지를 새 PDF로 저장",
                    default_path,
                    "PDF 문서 (*.pdf)"
                )
                if not save_path:
                    return

                AppSettings.set_last_save_dir(os.path.dirname(save_path))
                self.engine.export_pages_to_pdf(pages, save_path)
                self._show_success_and_open_folder(save_path, f"선택한 {len(pages)}페이지가 새 PDF 파일로 성공적으로 저장되었습니다!")

            # 2. 개별 이미지 분할 저장
            elif export_type == 1:
                target_dir = QFileDialog.getExistingDirectory(
                    self,
                    "개별 이미지를 저장할 폴더 선택",
                    last_dir
                )
                if not target_dir:
                    return

                AppSettings.set_last_save_dir(target_dir)
                dpi = self.combo_dpi.currentData()
                fmt = "jpg" if "jpg" in self.combo_fmt.currentText().lower() else "png"

                saved = self.engine.export_pages_as_images(
                    page_indices=pages,
                    output_dir=target_dir,
                    prefix=f"{doc_name}_p",
                    fmt=fmt,
                    dpi=dpi
                )
                self._show_success_and_open_folder(target_dir, f"총 {len(saved)}개의 페이지 이미지가 성공적으로 저장되었습니다!")

            # 3. 하나로 이어 붙인 긴 이미지 저장
            elif export_type == 2:
                fmt_ext = "jpg" if "jpg" in self.combo_fmt.currentText().lower() else "png"
                default_name = f"{doc_name}_이어붙이기({len(pages)}p).{fmt_ext}"
                default_path = os.path.join(last_dir, default_name) if last_dir else default_name

                save_path, _ = QFileDialog.getSaveFileName(
                    self,
                    "하나로 이어 붙인 긴 이미지로 저장",
                    default_path,
                    f"{fmt_ext.upper()} 이미지 (*.{fmt_ext})"
                )
                if not save_path:
                    return

                AppSettings.set_last_save_dir(os.path.dirname(save_path))
                dpi = self.combo_dpi.currentData()
                spacing = self.spin_spacing.value()

                self.engine.export_stitched_image(
                    page_indices=pages,
                    output_path=save_path,
                    dpi=dpi,
                    spacing=spacing
                )
                self._show_success_and_open_folder(save_path, f"선택한 {len(pages)}페이지가 하나의 긴 이미지로 성공적으로 이어 붙여 저장되었습니다!")

            self.accept()

        except Exception as e:
            QMessageBox.critical(self, "내보내기 오류", f"작업 중 오류가 발생했습니다:\n{str(e)}")

    def _show_success_and_open_folder(self, target_path: str, message: str):
        folder = target_path if os.path.isdir(target_path) else os.path.dirname(target_path)
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("내보내기 완료 - BossPDF")
        msg_box.setText(f"✅ {message}\n\n저장 위치: {target_path}")
        msg_box.setIcon(QMessageBox.Icon.Information)
        btn_open = msg_box.addButton("폴더 열기", QMessageBox.ButtonRole.ActionRole)
        msg_box.addButton("확인", QMessageBox.ButtonRole.AcceptRole)
        msg_box.exec()

        if msg_box.clickedButton() == btn_open and os.path.exists(folder):
            if os.path.isfile(target_path):
                subprocess.Popen(f'explorer /select,"{os.path.normpath(target_path)}"')
            else:
                subprocess.Popen(f'explorer "{os.path.normpath(folder)}"')
