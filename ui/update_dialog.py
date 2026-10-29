"""
Apple macOS 감성의 자동 업데이트 알림 및 다운로더 대화상자
"""
import os
from typing import Optional
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QTextBrowser, QFrame, QMessageBox, QApplication
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from core.updater import UpdateInfo, DownloadUpdateThread, launch_installer_and_exit
from core.version import __version__
from ui.theme import AppleTheme


class UpdateDialog(QDialog):
    """
    최신 버전 릴리스 알림, 릴리스 노트 확인 및 1클릭 다운로드/설치 대화상자
    """
    def __init__(self, parent=None, update_info: Optional[UpdateInfo] = None):
        super().__init__(parent)
        self.update_info = update_info
        self.download_thread: Optional[DownloadUpdateThread] = None

        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("소프트웨어 업데이트 - BossPDF")
        self.setFixedSize(520, 520)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        # 1. 상단 헤더
        header_layout = QHBoxLayout()
        header_layout.setSpacing(16)

        lbl_icon = QLabel("🚀")
        lbl_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_icon.setStyleSheet("""
            QLabel {
                font-size: 32px;
                background-color: #EBF3FF;
                border-radius: 26px;
                min-width: 52px;
                max-width: 52px;
                min-height: 52px;
                max-height: 52px;
                border: 1px solid #C7DFFF;
            }
        """)
        header_layout.addWidget(lbl_icon)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(4)

        latest_v = self.update_info.latest_version if self.update_info else "최신"
        lbl_title = QLabel(f"새로운 BossPDF v{latest_v} 버전을 사용할 수 있습니다!")
        lbl_title.setStyleSheet("font-size: 15px; font-weight: 700; color: #1D1D1F;")
        text_layout.addWidget(lbl_title)

        cur_v = self.update_info.current_version if self.update_info else __version__
        lbl_sub = QLabel(f"현재 버전: v{cur_v}  ➔  새 버전: v{latest_v}")
        lbl_sub.setStyleSheet("font-size: 12px; color: #86868B;")
        text_layout.addWidget(lbl_sub)

        header_layout.addLayout(text_layout)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        # 구분선
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #E5E5EA; background-color: #E5E5EA; max-height: 1px;")
        layout.addWidget(sep)

        # 2. 릴리스 노트 섹션
        lbl_notes_title = QLabel("업데이트 내용:")
        lbl_notes_title.setStyleSheet("font-size: 12px; font-weight: 600; color: #1D1D1F;")
        layout.addWidget(lbl_notes_title)

        self.txt_notes = QTextBrowser()
        self.txt_notes.setStyleSheet("""
            QTextBrowser {
                background-color: #F5F5F7;
                border: 1px solid #E5E5EA;
                border-radius: 8px;
                padding: 10px;
                color: #1D1D1F;
                font-size: 12px;
                line-height: 1.5;
            }
        """)
        release_text = ""
        if self.update_info and self.update_info.release_notes:
            release_text = self.update_info.release_notes
        else:
            release_text = "• 성능 최적화 및 안정성 개선\n• 버그 수정 및 UI 반응성 향상"
        self.txt_notes.setPlainText(release_text)
        layout.addWidget(self.txt_notes, 1)

        # 3. 다운로드 진행률 바 및 상태 라벨
        self.progress_container = QFrame()
        prog_layout = QVBoxLayout(self.progress_container)
        prog_layout.setContentsMargins(0, 0, 0, 0)
        prog_layout.setSpacing(6)

        self.lbl_progress_status = QLabel("다운로드 대기 중...")
        self.lbl_progress_status.setStyleSheet("font-size: 11px; color: #86868B;")
        prog_layout.addWidget(self.lbl_progress_status)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #E5E5EA;
                border-radius: 6px;
                height: 12px;
                text-align: center;
                font-size: 10px;
                font-weight: 600;
                color: #1D1D1F;
            }
            QProgressBar::chunk {
                background-color: #007AFF;
                border-radius: 6px;
            }
        """)
        prog_layout.addWidget(self.progress_bar)
        self.progress_container.setVisible(False)
        layout.addWidget(self.progress_container)

        # 4. 하단 버튼 열
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.btn_cancel = QPushButton("나중에")
        self.btn_cancel.setFixedSize(90, 32)
        self.btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #E5E5EA;
                color: #1D1D1F;
                border: none;
                border-radius: 16px;
                font-size: 12px;
                font-weight: 500;
            }
            QPushButton:hover { background-color: #D1D1D6; }
        """)
        self.btn_cancel.clicked.connect(self._on_cancel_clicked)
        btn_layout.addWidget(self.btn_cancel)

        btn_layout.addStretch()

        self.btn_update = QPushButton("지금 업데이트")
        self.btn_update.setFixedHeight(32)
        self.btn_update.setStyleSheet("""
            QPushButton {
                background-color: #007AFF;
                color: #FFFFFF;
                border: none;
                border-radius: 16px;
                padding: 0 18px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover { background-color: #0062CC; }
            QPushButton:disabled { background-color: #AEAEB2; }
        """)
        self.btn_update.clicked.connect(self._start_download)
        btn_layout.addWidget(self.btn_update)

        layout.addLayout(btn_layout)

    def _start_download(self):
        if not self.update_info or not self.update_info.download_url:
            QMessageBox.warning(
                self,
                "다운로드 불가",
                "다운로드할 수 있는 설치 파일(Setup.exe)이 아직 등록되지 않았습니다.\nGitHub 릴리스 페이지를 직접 확인해 주세요."
            )
            return

        self.btn_update.setEnabled(False)
        self.btn_cancel.setText("취소")
        self.progress_container.setVisible(True)
        self.lbl_progress_status.setText("업데이트 파일 다운로드 중...")

        self.download_thread = DownloadUpdateThread(
            download_url=self.update_info.download_url,
            file_name=self.update_info.file_name or f"BossPDF_Setup_v{self.update_info.latest_version}.exe",
            parent=self
        )
        self.download_thread.progress.connect(self._on_download_progress)
        self.download_thread.download_finished.connect(self._on_download_finished)
        self.download_thread.download_error.connect(self._on_download_error)
        self.download_thread.start()

    def _on_download_progress(self, downloaded: int, total: int, pct: int):
        self.progress_bar.setValue(pct)
        down_mb = downloaded / (1024 * 1024)
        total_mb = total / (1024 * 1024) if total > 0 else 0
        if total > 0:
            self.lbl_progress_status.setText(f"다운로드 중: {down_mb:.1f} MB / {total_mb:.1f} MB ({pct}%)")
        else:
            self.lbl_progress_status.setText(f"다운로드 중: {down_mb:.1f} MB")

    def _on_download_finished(self, dest_path: str):
        self.lbl_progress_status.setText("다운로드 완료! 설치 프로그램을 실행합니다...")
        self.progress_bar.setValue(100)

        # 사용자에게 설치 여부 확인 후 즉시 업데이트 실행 및 앱 종료
        reply = QMessageBox.question(
            self,
            "업데이트 설치",
            "최신 버전 다운로드가 완료되었습니다.\n지금 설치를 진행하시겠습니까? (BossPDF가 종료됩니다)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            launch_installer_and_exit(dest_path, silent=False)
            QApplication.quit()
        else:
            self.accept()

    def _on_download_error(self, err_msg: str):
        self.progress_container.setVisible(False)
        self.btn_update.setEnabled(True)
        self.btn_cancel.setText("닫기")
        QMessageBox.critical(self, "다운로드 실패", f"업데이트 파일 다운로드에 실패했습니다:\n{err_msg}")

    def _on_cancel_clicked(self):
        if self.download_thread and self.download_thread.isRunning():
            self.download_thread.cancel()
            self.download_thread.wait(1000)
        self.reject()

    def closeEvent(self, event):
        if self.download_thread and self.download_thread.isRunning():
            self.download_thread.cancel()
            self.download_thread.wait(1000)
        super().closeEvent(event)
