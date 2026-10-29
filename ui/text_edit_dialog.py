"""
텍스트 추가 및 수정을 위한 글꼴/스타일/색상/자동 줄맞춤/수동 조절 대화상자
"""
from typing import Dict, Any, Tuple, Optional, List
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QComboBox,
    QSpinBox, QDoubleSpinBox, QCheckBox, QPushButton, QColorDialog,
    QGroupBox, QRadioButton, QButtonGroup, QFrame
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor
from core.font_manager import FontManager
from ui.theme import AppleTheme


class TextEditDialog(QDialog):
    """
    글꼴, 크기, 스타일(굵게/기울임), 색상 변경, 정렬,
    기존 텍스트와의 자동 줄맞춤(스냅) 및 수동 위치 미세 조절을 제공하는 대화상자
    """
    PRESET_COLORS = [
        ("검정", QColor("#000000")),
        ("진회색", QColor("#424242")),
        ("빨강", QColor("#d32f2f")),
        ("주황", QColor("#f57c00")),
        ("파랑", QColor("#1976d2")),
        ("남색", QColor("#0d47a1")),
        ("초록", QColor("#2e7d32")),
        ("보라", QColor("#7b1fa2"))
    ]

    def __init__(
        self,
        parent=None,
        initial_text: str = "",
        init_x: float = 50.0,
        init_y: float = 50.0,
        init_w: float = 300.0,
        init_h: float = 80.0,
        initial_color: Optional[QColor] = None,
        snap_info: Dict[str, Any] = None,
        title: str = "텍스트 입력 및 서식 설정"
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(560, 620)

        self.init_x = init_x
        self.init_y = init_y
        self.init_w = init_w
        self.init_h = init_h
        self.snap_info = snap_info or {"found": False}

        self.current_color = initial_color or QColor(0, 0, 0)
        self.color_buttons: List[QPushButton] = []

        self._init_ui(initial_text)
        self._apply_snap_if_available()
        self._update_color_buttons_state()
        self._update_preview()

    def _init_ui(self, initial_text: str):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)

        # 1. 텍스트 입력 영역
        lbl_text = QLabel("<b>텍스트 내용:</b>")
        main_layout.addWidget(lbl_text)

        self.edit_text = QTextEdit()
        self.edit_text.setPlaceholderText("삽입하거나 수정할 내용을 입력하세요...")
        self.edit_text.setPlainText(initial_text)
        self.edit_text.setFixedHeight(85)
        self.edit_text.textChanged.connect(self._update_preview)
        main_layout.addWidget(self.edit_text)

        # 2. 폰트 및 서식 그룹
        group_font = QGroupBox("글꼴 및 서식 (Font & Style)")
        font_layout = QVBoxLayout(group_font)

        # 1행: 글꼴 및 크기
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("글꼴:"))
        self.combo_font = QComboBox()
        self.combo_font.setEditable(True)
        self.combo_font.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        if self.combo_font.completer():
            self.combo_font.completer().setFilterMode(Qt.MatchFlag.MatchContains)
        all_fonts = FontManager.get_all_font_families()
        self.combo_font.addItems(all_fonts)
        malgun_idx = self.combo_font.findText("맑은 고딕")
        if malgun_idx >= 0:
            self.combo_font.setCurrentIndex(malgun_idx)
        self.combo_font.currentTextChanged.connect(self._update_preview)
        row1.addWidget(self.combo_font, 2)

        row1.addWidget(QLabel("크기:"))
        self.spin_size = QDoubleSpinBox()
        self.spin_size.setRange(6.0, 72.0)
        self.spin_size.setValue(14.0)
        self.spin_size.setSingleStep(1.0)
        self.spin_size.valueChanged.connect(self._update_preview)
        row1.addWidget(self.spin_size, 1)

        font_layout.addLayout(row1)

        # 2행: 굵게, 기울임, 정렬
        row2 = QHBoxLayout()
        self.chk_bold = QCheckBox("굵게 (Bold)")
        self.chk_bold.toggled.connect(self._update_preview)
        row2.addWidget(self.chk_bold)

        self.chk_italic = QCheckBox("기울임 (Italic)")
        self.chk_italic.toggled.connect(self._update_preview)
        row2.addWidget(self.chk_italic)

        row2.addSpacing(15)
        row2.addWidget(QLabel("정렬:"))
        self.combo_align = QComboBox()
        self.combo_align.addItems(["왼쪽 정렬", "가운데 정렬", "오른쪽 정렬"])
        self.combo_align.currentIndexChanged.connect(self._update_preview)
        row2.addWidget(self.combo_align)

        font_layout.addLayout(row2)

        # 3행: 폰트 컬러 (Font Color) 변경 팔레트
        row3 = QVBoxLayout()
        lbl_color_title = QLabel("<b>글자 색상 (Font Color):</b>")
        row3.addWidget(lbl_color_title)

        color_btn_layout = QHBoxLayout()
        self.color_buttons.clear()

        for name, col in self.PRESET_COLORS:
            btn = QPushButton(name)
            btn.setFixedWidth(52)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {col.name()};
                    color: {"#ffffff" if col.lightness() < 130 else "#000000"};
                    font-weight: bold;
                    border: 2px solid transparent;
                    border-radius: 4px;
                    padding: 4px;
                }}
                QPushButton:hover {{
                    border: 2px solid #ffca28;
                }}
            """)
            btn.clicked.connect(lambda checked, c=col: self._set_color(c))
            color_btn_layout.addWidget(btn)
            self.color_buttons.append(btn)

        self.btn_custom_color = QPushButton("🎨 직접 선택...")
        self.btn_custom_color.clicked.connect(self._choose_custom_color)
        color_btn_layout.addWidget(self.btn_custom_color)

        # 현재 선택된 색상 스와치
        self.lbl_color_preview = QLabel()
        self.lbl_color_preview.setFixedSize(26, 26)
        color_btn_layout.addWidget(self.lbl_color_preview)

        row3.addLayout(color_btn_layout)
        font_layout.addLayout(row3)

        main_layout.addWidget(group_font)

        # 3. 자동 줄맞춤(스냅) 및 수동 위치 조절 그룹
        group_pos = QGroupBox("위치 및 줄맞춤 조절 (Position & Alignment)")
        pos_layout = QVBoxLayout(group_pos)

        # 자동 줄맞춤 체크박스
        self.chk_snap = QCheckBox("기존 텍스트와 자동으로 줄맞춤 (스마트 스냅)")
        self.chk_snap.setChecked(self.snap_info.get("found", False))
        self.chk_snap.toggled.connect(self._on_snap_toggled)
        pos_layout.addWidget(self.chk_snap)

        self.lbl_snap_info = QLabel("")
        self.lbl_snap_info.setStyleSheet("color: #1565c0; font-size: 11px;")
        pos_layout.addWidget(self.lbl_snap_info)

        # 수동 위치 미세 조절 (X, Y, 너비, 높이)
        coord_row = QHBoxLayout()
        coord_row.addWidget(QLabel("X 위치 (pt):"))
        self.spin_x = QDoubleSpinBox()
        self.spin_x.setRange(0.0, 3000.0)
        self.spin_x.setValue(self.init_x)
        self.spin_x.setSingleStep(1.0)
        coord_row.addWidget(self.spin_x)

        coord_row.addWidget(QLabel("Y 위치 (pt):"))
        self.spin_y = QDoubleSpinBox()
        self.spin_y.setRange(0.0, 3000.0)
        self.spin_y.setValue(self.init_y)
        self.spin_y.setSingleStep(1.0)
        coord_row.addWidget(self.spin_y)

        pos_layout.addLayout(coord_row)

        dim_row = QHBoxLayout()
        dim_row.addWidget(QLabel("너비 (W):"))
        self.spin_w = QDoubleSpinBox()
        self.spin_w.setRange(20.0, 2000.0)
        self.spin_w.setValue(self.init_w)
        dim_row.addWidget(self.spin_w)

        dim_row.addWidget(QLabel("높이 (H):"))
        self.spin_h = QDoubleSpinBox()
        self.spin_h.setRange(10.0, 2000.0)
        self.spin_h.setValue(self.init_h)
        dim_row.addWidget(self.spin_h)

        pos_layout.addLayout(dim_row)
        main_layout.addWidget(group_pos)

        # 4. 실시간 미리보기 상자
        lbl_prev = QLabel("<b>실시간 서식 미리보기:</b>")
        main_layout.addWidget(lbl_prev)

        self.preview_box = QLabel("텍스트 미리보기")
        self.preview_box.setFixedHeight(60)
        main_layout.addWidget(self.preview_box)

        # 5. 하단 확인/취소 버튼
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_cancel = QPushButton("취소")
        self.btn_cancel.setStyleSheet(AppleTheme.secondary_button_style())
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_ok = QPushButton("적용하기")
        self.btn_ok.setStyleSheet(AppleTheme.primary_button_style())
        self.btn_ok.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_ok)

        main_layout.addLayout(btn_layout)

    def _apply_snap_if_available(self):
        """인접 텍스트가 있을 경우 자동 스냅 적용"""
        if self.snap_info.get("found", False):
            snap_x = self.snap_info["snap_x"]
            snap_y = self.snap_info["snap_y"]
            sug_size = self.snap_info.get("suggested_size", 14.0)
            sample_txt = self.snap_info.get("nearest_text", "")
            if len(sample_txt) > 20:
                sample_txt = sample_txt[:20] + "..."

            self.spin_x.setValue(snap_x)
            self.spin_y.setValue(snap_y)
            self.spin_size.setValue(sug_size)

            self.lbl_snap_info.setText(
                f"💡 인접 줄('{sample_txt}')에 맞춰 X={snap_x}pt, Y={snap_y}pt, 크기={sug_size}pt 자동 정렬됨"
            )
        else:
            self.lbl_snap_info.setText("주변에 인접한 텍스트가 없어 클릭한 위치로 배치됩니다.")

    def _on_snap_toggled(self, checked: bool):
        if checked:
            self._apply_snap_if_available()
        else:
            self.spin_x.setValue(self.init_x)
            self.spin_y.setValue(self.init_y)
            self.lbl_snap_info.setText("자동 줄맞춤 해제됨 (원래 클릭 위치 적용)")

    def _set_color(self, color: QColor):
        self.current_color = color
        self._update_color_buttons_state()
        self._update_preview()

    def _choose_custom_color(self):
        col = QColorDialog.getColor(self.current_color, self, "글자 색상 선택")
        if col.isValid():
            self._set_color(col)

    def _update_color_buttons_state(self):
        """선택된 색상 버튼에 하이라이트 테두리 적용"""
        self.lbl_color_preview.setStyleSheet(
            f"background-color: {self.current_color.name()}; border: 1.5px solid #D1D1D6; border-radius: 6px;"
        )
        for btn, (name, col) in zip(self.color_buttons, self.PRESET_COLORS):
            is_selected = (col.name().lower() == self.current_color.name().lower())
            border_style = "2px solid #007AFF" if is_selected else "1px solid rgba(0, 0, 0, 0.12)"
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {col.name()};
                    color: {"#ffffff" if col.lightness() < 130 else "#000000"};
                    font-weight: 600;
                    font-size: 11px;
                    border: {border_style};
                    border-radius: 6px;
                    padding: 4px;
                }}
            """)

    def _update_preview(self):
        """실시간 미리보기 갱신"""
        text = self.edit_text.toPlainText() or "텍스트 미리보기"
        self.preview_box.setText(text)

        font_name = self.combo_font.currentText()
        font_size = max(8, int(self.spin_size.value()))
        qfont = QFont(font_name, font_size)
        qfont.setBold(self.chk_bold.isChecked())
        qfont.setItalic(self.chk_italic.isChecked())
        self.preview_box.setFont(qfont)

        # 정렬
        align_idx = self.combo_align.currentIndex()
        if align_idx == 1:
            self.preview_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        elif align_idx == 2:
            self.preview_box.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        else:
            self.preview_box.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        # 색상 실시간 반영 (Apple 깔끔한 카드 스타일)
        self.preview_box.setStyleSheet(f"""
            QLabel {{
                border: 1px solid #D1D1D6;
                border-radius: 8px;
                background-color: #FFFFFF;
                color: {self.current_color.name()};
                padding: 8px;
            }}
        """)

    def get_data(self) -> Dict[str, Any]:
        """설정된 모든 텍스트 및 서식, 좌표 반환"""
        return {
            "text": self.edit_text.toPlainText(),
            "font_family": self.combo_font.currentText(),
            "fontsize": self.spin_size.value(),
            "is_bold": self.chk_bold.isChecked(),
            "is_italic": self.chk_italic.isChecked(),
            "align": self.combo_align.currentIndex(),
            "color": (
                self.current_color.redF(),
                self.current_color.greenF(),
                self.current_color.blueF()
            ),
            "x": self.spin_x.value(),
            "y": self.spin_y.value(),
            "w": self.spin_w.value(),
            "h": self.spin_h.value()
        }
