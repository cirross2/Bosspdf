"""
비밀번호로 보호된 PDF 문서 열기용 암호 입력 대화상자 (macOS 감성 UI)
"""
from typing import Optional, Callable
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QWidget, QFrame
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon, QFont, QAction


class PasswordDialog(QDialog):
    """
    암호화된 PDF 문서를 열기 위한 세련된 Apple 스타일 비밀번호 입력 대화상자
    """
    def __init__(self, parent: Optional[QWidget] = None, filename: str = "", verifier: Optional[Callable[[str], bool]] = None):
        super().__init__(parent)
        self.filename = filename
        self.verifier = verifier
        self.unlocked_password: Optional[str] = None
        self.password_visible = False

        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("비밀번호 입력 - BossPDF")
        self.setFixedSize(440, 290)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(14)

        # 상단 헤더 영역 (아이콘 + 안내)
        header_layout = QHBoxLayout()
        header_layout.setSpacing(16)

        # 자물쇠 아이콘 컨테이너
        lbl_icon = QLabel("🔒")
        lbl_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_icon.setStyleSheet("""
            QLabel {
                font-size: 32px;
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

        # 타이틀 및 설명 텍스트
        text_layout = QVBoxLayout()
        text_layout.setSpacing(4)

        lbl_title = QLabel("암호로 보호된 문서")
        lbl_title.setStyleSheet("font-size: 16px; font-weight: 700; color: #1D1D1F;")
        text_layout.addWidget(lbl_title)

        display_name = self.filename if len(self.filename) <= 30 else (self.filename[:27] + "...")
        lbl_file = QLabel(f"'{display_name}' 문서를 열려면 암호가 필요합니다.")
        lbl_file.setStyleSheet("font-size: 12px; color: #86868B;")
        lbl_file.setWordWrap(True)
        text_layout.addWidget(lbl_file)

        header_layout.addLayout(text_layout)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        # 구분선
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #E5E5EA; background-color: #E5E5EA; max-height: 1px;")
        layout.addWidget(sep)

        # 비밀번호 입력란 컨테이너
        input_container = QVBoxLayout()
        input_container.setSpacing(6)

        lbl_input_hint = QLabel("비밀번호")
        lbl_input_hint.setStyleSheet("font-size: 12px; font-weight: 600; color: #48484A;")
        input_container.addWidget(lbl_input_hint)

        pw_row = QHBoxLayout()
        pw_row.setSpacing(6)

        self.txt_password = QLineEdit()
        self.txt_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_password.setPlaceholderText("문서 비밀번호를 입력하세요")
        self.txt_password.setStyleSheet("""
            QLineEdit {
                border: 1.5px solid #D1D1D6;
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 13px;
                background-color: #FFFFFF;
                color: #1D1D1F;
            }
            QLineEdit:focus {
                border: 1.5px solid #007AFF;
                background-color: #FFFFFF;
            }
        """)
        self.txt_password.returnPressed.connect(self._on_accept)
        pw_row.addWidget(self.txt_password, 1)

        # 비밀번호 보이기/숨기기 토글 버튼
        self.btn_toggle_eye = QPushButton("👁️")
        self.btn_toggle_eye.setToolTip("비밀번호 표시/숨기기")
        self.btn_toggle_eye.setFixedSize(36, 36)
        self.btn_toggle_eye.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_eye.setStyleSheet("""
            QPushButton {
                border: 1px solid #D1D1D6;
                border-radius: 8px;
                background-color: #F2F2F7;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #E5E5EA;
            }
        """)
        self.btn_toggle_eye.clicked.connect(self._toggle_password_visibility)
        pw_row.addWidget(self.btn_toggle_eye)

        input_container.addLayout(pw_row)

        # 에러 메시지 라벨
        self.lbl_error = QLabel("❌ 비밀번호가 일치하지 않습니다. 다시 입력해주세요.")
        self.lbl_error.setStyleSheet("color: #FF3B30; font-size: 11px; font-weight: 500;")
        self.lbl_error.setVisible(False)
        input_container.addWidget(self.lbl_error)

        layout.addLayout(input_container)

        layout.addStretch()

        # 하단 버튼 (취소 / 열기)
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        btn_layout.addStretch()

        self.btn_cancel = QPushButton("취소")
        self.btn_cancel.setFixedSize(85, 34)
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.setStyleSheet("""
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
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_unlock = QPushButton("열기")
        self.btn_unlock.setFixedSize(85, 34)
        self.btn_unlock.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_unlock.setStyleSheet("""
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
        self.btn_unlock.clicked.connect(self._on_accept)
        btn_layout.addWidget(self.btn_unlock)

        layout.addLayout(btn_layout)

        # 초기 포커스 지정
        self.txt_password.setFocus()

    def _toggle_password_visibility(self):
        self.password_visible = not self.password_visible
        if self.password_visible:
            self.txt_password.setEchoMode(QLineEdit.EchoMode.Normal)
            self.btn_toggle_eye.setText("🙈")
        else:
            self.txt_password.setEchoMode(QLineEdit.EchoMode.Password)
            self.btn_toggle_eye.setText("👁️")

    def _on_accept(self):
        pw = self.txt_password.text()
        if not pw:
            self.lbl_error.setText("⚠️ 비밀번호를 입력해주세요.")
            self.lbl_error.setVisible(True)
            self.txt_password.setFocus()
            return

        if self.verifier:
            is_valid = self.verifier(pw)
            if not is_valid:
                self.lbl_error.setText("❌ 비밀번호가 일치하지 않습니다. 다시 입력해주세요.")
                self.lbl_error.setVisible(True)
                self.txt_password.selectAll()
                self.txt_password.setFocus()
                return

        self.unlocked_password = pw
        self.accept()

    @classmethod
    def get_password(
        cls,
        parent: Optional[QWidget] = None,
        filename: str = "",
        verifier: Optional[Callable[[str], bool]] = None
    ) -> Optional[str]:
        dlg = cls(parent=parent, filename=filename, verifier=verifier)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            return dlg.unlocked_password
        return None
