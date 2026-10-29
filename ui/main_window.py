"""
PDF 뷰어 및 편집기 메인 윈도우 UI (연속 스크롤 및 실시간 편집 도구 지원)
"""
import os
from typing import Optional
from PySide6.QtWidgets import (
    QMainWindow, QToolBar, QStatusBar, QFileDialog, QMessageBox,
    QDockWidget, QLineEdit, QLabel, QPushButton, QComboBox, QWidget,
    QHBoxLayout, QVBoxLayout, QFrame, QButtonGroup
)
from PySide6.QtCore import Qt, QSize, QRectF, QEvent, QTimer
from PySide6.QtGui import QAction, QIcon, QKeySequence, QActionGroup, QPainter, QImage, QShortcut
from PySide6.QtPrintSupport import QPrinter, QPrintDialog, QPrintPreviewDialog
import pymupdf as fitz

from core.pdf_engine import PdfEngine, EncryptedPdfError, InvalidPasswordError
from core.settings_manager import AppSettings
from core.version import __version__, GITHUB_REPO_URL
from core.updater import CheckUpdateThread, UpdateInfo
from ui.viewer_widget import PdfViewerWidget, EditMode
from ui.thumbnail_widget import ThumbnailWidget
from ui.image_merge_dialog import ImageMergeDialog
from ui.page_reorder_dialog import PageReorderDialog
from ui.password_dialog import PasswordDialog
from ui.page_export_dialog import PageExportDialog
from ui.update_dialog import UpdateDialog
from ui.theme import AppleTheme


class MainWindow(QMainWindow):
    """
    연속 스크롤 뷰어 및 텍스트/마크업 편집 메인 윈도우
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BossPDF - 고성능 PDF 뷰어 & 편집기")
        self.resize(1280, 850)

        self.pdf_engine = PdfEngine()

        self._init_ui()
        self._create_menus_and_toolbars()
        self._update_title()

        # 앱 시작 2.5초 후 백그라운드에서 조용히 최신 업데이트 확인
        QTimer.singleShot(2500, self._check_updates_background)

    def _init_ui(self):
        # 중앙 컨테이너 (상단 Ctrl+F 검색바 + 연속 스크롤 뷰어)
        central_container = QWidget(self)
        central_layout = QVBoxLayout(central_container)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)

        # Apple 스타일 상단 단어 검색 바 (Ctrl+F)
        self.search_bar = QFrame(self)
        self.search_bar.setObjectName("searchBarFrame")
        self.search_bar.setStyleSheet(
            """
            QFrame#searchBarFrame {
                background-color: #FFFFFF;
                border-bottom: 1px solid #D1D1D6;
                padding: 4px 12px;
            }
            """
        )
        search_layout = QHBoxLayout(self.search_bar)
        search_layout.setContentsMargins(8, 5, 8, 5)
        search_layout.setSpacing(8)

        lbl_find_icon = QLabel("🔍 단어 검색:")
        lbl_find_icon.setStyleSheet("font-weight: 600; color: #1D1D1F; font-size: 13px;")
        search_layout.addWidget(lbl_find_icon)

        self.txt_search = QLineEdit(self.search_bar)
        self.txt_search.setPlaceholderText("검색할 단어를 입력하세요 (Enter: 다음 결과, Shift+Enter: 이전 결과, Esc: 닫기)")
        self.txt_search.setMinimumWidth(260)
        self.txt_search.setMaximumWidth(400)
        self.txt_search.setClearButtonEnabled(True)
        self.txt_search.installEventFilter(self)
        self.txt_search.textChanged.connect(self._on_search_text_changed)
        search_layout.addWidget(self.txt_search)

        self.lbl_search_status = QLabel("0 / 0건")
        self.lbl_search_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_search_status.setMinimumWidth(145)
        self.lbl_search_status.setStyleSheet(
            "background-color: #F2F2F7; color: #86868B; font-weight: 600; padding: 4px 12px; border-radius: 6px; font-size: 12.5px;"
        )
        search_layout.addWidget(self.lbl_search_status)

        self.btn_search_prev = QPushButton("▲ 이전")
        self.btn_search_prev.setToolTip("이전 검색 결과로 이동 (Shift+Enter)")
        self.btn_search_prev.setFixedHeight(28)
        self.btn_search_prev.setEnabled(False)
        self.btn_search_prev.clicked.connect(self.find_prev_result)
        search_layout.addWidget(self.btn_search_prev)

        self.btn_search_next = QPushButton("▼ 다음")
        self.btn_search_next.setToolTip("다음 검색 결과로 이동 (Enter / F3)")
        self.btn_search_next.setFixedHeight(28)
        self.btn_search_next.setEnabled(False)
        self.btn_search_next.clicked.connect(self.find_next_result)
        search_layout.addWidget(self.btn_search_next)

        search_layout.addStretch(1)

        self.btn_search_close = QPushButton("✕ 닫기")
        self.btn_search_close.setToolTip("검색창 닫기 및 강조 표시 해제 (Esc)")
        self.btn_search_close.setFixedHeight(28)
        self.btn_search_close.clicked.connect(self.close_search_bar)
        search_layout.addWidget(self.btn_search_close)

        self.search_bar.setVisible(False)
        central_layout.addWidget(self.search_bar)

        # 중앙 연속 스크롤 뷰어
        self.viewer = PdfViewerWidget(self)
        self.viewer.set_engine(self.pdf_engine)
        self.viewer.page_changed.connect(self._on_page_changed)
        self.viewer.zoom_changed.connect(self._on_zoom_changed)
        self.viewer.document_modified.connect(self._on_document_modified)
        central_layout.addWidget(self.viewer, 1)

        self.setCentralWidget(central_container)
        self._last_search_query: str = ""
        self._search_debounce_timer = QTimer(self)
        self._search_debounce_timer.setSingleShot(True)
        self._search_debounce_timer.setInterval(120)
        self._search_debounce_timer.timeout.connect(self._on_debounced_search)

        # 좌측 썸네일 도크 위젯
        self.dock_thumb = QDockWidget("페이지 썸네일", self)
        self.dock_thumb.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable |
            QDockWidget.DockWidgetFeature.DockWidgetClosable
        )
        self.thumbnail_widget = ThumbnailWidget(self)
        self.thumbnail_widget.page_selected.connect(self._on_thumbnail_page_selected)
        self.thumbnail_widget.page_rotated.connect(self._on_thumbnail_rotate)
        self.thumbnail_widget.page_deleted.connect(self._on_thumbnail_delete)
        self.thumbnail_widget.page_reorder_requested.connect(self.open_page_reorder_dialog)
        self.thumbnail_widget.page_order_changed.connect(self._on_page_order_changed)
        self.dock_thumb.setWidget(self.thumbnail_widget)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.dock_thumb)

        # 상태 표시줄
        self.status_bar = QStatusBar(self)
        self.setStatusBar(self.status_bar)

        self.lbl_status_file = QLabel("열린 파일 없음")
        self.lbl_status_file.setStyleSheet("color: #86868B; font-weight: 500;")

        self.lbl_status_mode = QLabel("모드: 이동/스크롤")
        self.lbl_status_mode.setStyleSheet(
            "background-color: #EBF3FF; color: #007AFF; font-weight: 600; padding: 2px 10px; border-radius: 8px;"
        )

        self.lbl_status_zoom = QLabel("120%")
        self.lbl_status_zoom.setStyleSheet(
            "background-color: #E5E5EA; color: #1D1D1F; font-weight: 500; padding: 2px 10px; border-radius: 8px;"
        )

        self.lbl_status_security = QLabel("🔒 암호 보호됨")
        self.lbl_status_security.setStyleSheet(
            "background-color: #FFF3CD; color: #856404; font-weight: 600; padding: 2px 10px; border-radius: 8px;"
        )
        self.lbl_status_security.setVisible(False)

        self.status_bar.addWidget(self.lbl_status_file, 1)
        self.status_bar.addPermanentWidget(self.lbl_status_security)
        self.status_bar.addPermanentWidget(self.lbl_status_mode)
        self.status_bar.addPermanentWidget(self.lbl_status_zoom)

    def _create_menus_and_toolbars(self):
        # 1. 파일 및 탐색 툴바
        toolbar_main = QToolBar("파일 및 탐색 도구", self)
        toolbar_main.setIconSize(QSize(18, 18))
        toolbar_main.setMovable(False)
        self.addToolBar(toolbar_main)

        # 파일 액션
        act_open = QAction("📂 열기", self)
        act_open.setShortcut(QKeySequence.StandardKey.Open)
        act_open.triggered.connect(self.open_file_dialog)
        toolbar_main.addAction(act_open)

        self.act_save = QAction("💾 저장", self)
        self.act_save.setShortcut(QKeySequence.StandardKey.Save)
        self.act_save.triggered.connect(self.save_file)
        toolbar_main.addAction(self.act_save)

        self.act_remove_password = QAction("🔓 비밀번호 해제 후 저장", self)
        self.act_remove_password.setStatusTip("문서의 비밀번호를 완전히 해제하여 저장 (이후 비밀번호 없이 열람 가능)")
        self.act_remove_password.triggered.connect(self.on_remove_password_and_save)
        self.act_remove_password.setEnabled(False)
        self.act_remove_password.setVisible(False)
        toolbar_main.addAction(self.act_remove_password)

        self.act_export_pages = QAction("📤 내보내기...", self)
        self.act_export_pages.setShortcut(QKeySequence("Ctrl+E"))
        self.act_export_pages.setStatusTip("특정 페이지만 새 PDF로 추출하거나 개별/이어붙인 이미지로 저장 (Ctrl+E)")
        self.act_export_pages.triggered.connect(self.open_export_dialog)
        toolbar_main.addAction(self.act_export_pages)

        self.act_print = QAction("🖨️ 인쇄...", self)
        self.act_print.setShortcut(QKeySequence.StandardKey.Print)
        self.act_print.setStatusTip("문서 인쇄 (Ctrl+P)")
        self.act_print.triggered.connect(self.print_document)
        toolbar_main.addAction(self.act_print)

        toolbar_main.addSeparator()

        # 페이지 이동 컨트롤 (◀ 1 / 0 ▶)
        self.btn_prev_page = QPushButton("◀")
        self.btn_prev_page.setToolTip("이전 페이지")
        self.btn_prev_page.setFixedSize(26, 24)
        self.btn_prev_page.clicked.connect(self._on_prev_page)
        toolbar_main.addWidget(self.btn_prev_page)

        self.txt_page = QLineEdit("1")
        self.txt_page.setFixedWidth(36)
        self.txt_page.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.txt_page.returnPressed.connect(self._on_jump_page)
        toolbar_main.addWidget(self.txt_page)

        self.lbl_total_page = QLabel("/ 0")
        self.lbl_total_page.setStyleSheet("color: #86868B; font-weight: 500; padding: 0 4px;")
        toolbar_main.addWidget(self.lbl_total_page)

        self.btn_next_page = QPushButton("▶")
        self.btn_next_page.setToolTip("다음 페이지")
        self.btn_next_page.setFixedSize(26, 24)
        self.btn_next_page.clicked.connect(self._on_next_page)
        toolbar_main.addWidget(self.btn_next_page)

        toolbar_main.addSeparator()

        # 줌 컨트롤
        act_zoom_out = QAction("🔍-", self)
        act_zoom_out.setShortcut(QKeySequence.StandardKey.ZoomOut)
        act_zoom_out.triggered.connect(self.viewer.zoom_out)
        toolbar_main.addAction(act_zoom_out)

        self.combo_zoom = QComboBox()
        self.combo_zoom.addItems(["50%", "75%", "100%", "120%", "150%", "200%"])
        self.combo_zoom.setCurrentText("120%")
        self.combo_zoom.setFixedWidth(78)
        self.combo_zoom.currentTextChanged.connect(self._on_combo_zoom_changed)
        toolbar_main.addWidget(self.combo_zoom)

        act_zoom_in = QAction("🔍+", self)
        act_zoom_in.setShortcut(QKeySequence.StandardKey.ZoomIn)
        act_zoom_in.triggered.connect(self.viewer.zoom_in)
        toolbar_main.addAction(act_zoom_in)

        act_fit_width = QAction("↔ 너비 맞춤", self)
        act_fit_width.triggered.connect(self.viewer.fit_to_width)
        toolbar_main.addAction(act_fit_width)

        act_fit_page = QAction("↕ 전체 맞춤", self)
        act_fit_page.triggered.connect(self.viewer.fit_to_page)
        toolbar_main.addAction(act_fit_page)

        toolbar_main.addSeparator()

        # 이미지들을 PDF로 합치기
        act_img_merge = QAction("🖼️ 이미지 병합", self)
        act_img_merge.setStatusTip("선택한 여러 이미지를 순서대로 단일 PDF로 즉시 병합")
        act_img_merge.triggered.connect(self.open_image_merge_dialog)
        toolbar_main.addAction(act_img_merge)

        # 페이지 순서 변경 및 관리
        self.act_reorder = QAction("📑 순서 관리", self)
        self.act_reorder.setStatusTip("전체 페이지 순서 변경 및 관리 대화상자 열기")
        self.act_reorder.triggered.connect(self.open_page_reorder_dialog)
        toolbar_main.addAction(self.act_reorder)

        toolbar_main.addSeparator()

        # 문서 내 단어 검색 (Ctrl+F)
        self.act_find = QAction("🔍 검색 (Ctrl+F)", self)
        self.act_find.setShortcut(QKeySequence.StandardKey.Find)
        self.act_find.setStatusTip("문서 내 단어 검색 및 위치 이동 (Ctrl+F)")
        self.act_find.triggered.connect(self.open_search_bar)
        toolbar_main.addAction(self.act_find)

        self.shortcut_find_next = QShortcut(QKeySequence("F3"), self)
        self.shortcut_find_next.activated.connect(self.find_next_result)
        self.shortcut_find_prev = QShortcut(QKeySequence("Shift+F3"), self)
        self.shortcut_find_prev.activated.connect(self.find_prev_result)

        # 2. 실시간 PDF 편집 툴바 (2번째 줄)
        self.addToolBarBreak()
        toolbar_edit = QToolBar("PDF 편집 도구", self)
        toolbar_edit.setIconSize(QSize(20, 20))
        toolbar_edit.setMovable(False)
        self.addToolBar(toolbar_edit)

        # 편집 모드 액션 그룹 (단일 선택)
        mode_group = QActionGroup(self)
        mode_group.setExclusive(True)

        self.act_mode_hand = QAction("🖐️ 이동/스크롤", self)
        self.act_mode_hand.setCheckable(True)
        self.act_mode_hand.setChecked(True)
        self.act_mode_hand.setStatusTip("기본 연속 스크롤 및 마우스 드래그 이동")
        self.act_mode_hand.triggered.connect(lambda: self._set_edit_mode(EditMode.HAND, "이동/스크롤"))
        mode_group.addAction(self.act_mode_hand)
        toolbar_edit.addAction(self.act_mode_hand)

        toolbar_edit.addSeparator()

        self.act_mode_text = QAction("🔤 텍스트 추가", self)
        self.act_mode_text.setCheckable(True)
        self.act_mode_text.setStatusTip("클릭한 위치에 텍스트 상자 삽입")
        self.act_mode_text.triggered.connect(lambda: self._set_edit_mode(EditMode.ADD_TEXT, "텍스트 추가 (클릭)"))
        mode_group.addAction(self.act_mode_text)
        toolbar_edit.addAction(self.act_mode_text)

        self.act_mode_whiteout = QAction("⬜ 텍스트 삭제/가리기", self)
        self.act_mode_whiteout.setCheckable(True)
        self.act_mode_whiteout.setStatusTip("지우고 싶은 영역을 마우스로 드래그하여 흰색으로 완전히 삭제/가리기")
        self.act_mode_whiteout.triggered.connect(lambda: self._set_edit_mode(EditMode.WHITEOUT, "텍스트 삭제/가리기 (드래그)"))
        mode_group.addAction(self.act_mode_whiteout)
        toolbar_edit.addAction(self.act_mode_whiteout)

        self.act_mode_edit_text = QAction("✏️ 텍스트 수정", self)
        self.act_mode_edit_text.setCheckable(True)
        self.act_mode_edit_text.setStatusTip("기존 텍스트 영역을 드래그하여 새 내용으로 치환/수정")
        self.act_mode_edit_text.triggered.connect(lambda: self._set_edit_mode(EditMode.EDIT_TEXT, "텍스트 수정 (드래그)"))
        mode_group.addAction(self.act_mode_edit_text)
        toolbar_edit.addAction(self.act_mode_edit_text)

        toolbar_edit.addSeparator()

        self.act_mode_highlight = QAction("🖍️ 형광펜", self)
        self.act_mode_highlight.setCheckable(True)
        self.act_mode_highlight.setStatusTip("마우스로 드래그한 영역에 반투명 형광펜 칠하기")
        self.act_mode_highlight.triggered.connect(lambda: self._set_edit_mode(EditMode.HIGHLIGHT, "형광펜 (드래그)"))
        mode_group.addAction(self.act_mode_highlight)
        toolbar_edit.addAction(self.act_mode_highlight)

        self.act_mode_pen = QAction("🖋️ 손글씨/서명", self)
        self.act_mode_pen.setCheckable(True)
        self.act_mode_pen.setStatusTip("마우스로 자유형 서명 또는 메모 그리기")
        self.act_mode_pen.triggered.connect(lambda: self._set_edit_mode(EditMode.PEN, "손글씨/서명 (마우스 드로잉)"))
        mode_group.addAction(self.act_mode_pen)
        toolbar_edit.addAction(self.act_mode_pen)

        toolbar_edit.addSeparator()

        # 실행 취소 (Undo)
        self.act_undo = QAction("↩️ 실행 취소", self)
        self.act_undo.setShortcut(QKeySequence.StandardKey.Undo)
        self.act_undo.setEnabled(False)
        self.act_undo.setStatusTip("마지막 편집 취소 (Ctrl+Z)")
        self.act_undo.triggered.connect(self._on_undo)
        toolbar_edit.addAction(self.act_undo)

        # 메뉴바 구성
        menubar = self.menuBar()

        # [파일] 메뉴
        menu_file = menubar.addMenu("파일(&F)")
        menu_file.addAction(act_open)
        menu_file.addAction(self.act_save)

        act_save_as = QAction("다른 이름으로 저장...", self)
        act_save_as.setShortcut(QKeySequence.StandardKey.SaveAs)
        act_save_as.triggered.connect(self.save_as_file)
        menu_file.addAction(act_save_as)
        menu_file.addAction(self.act_remove_password)
        menu_file.addAction(self.act_export_pages)

        menu_file.addSeparator()
        menu_file.addAction(self.act_print)

        act_print_prev = QAction("🔍 인쇄 미리보기...", self)
        act_print_prev.setStatusTip("인쇄 미리보기 창 열기")
        act_print_prev.triggered.connect(self.print_preview)
        menu_file.addAction(act_print_prev)

        menu_file.addSeparator()
        menu_file.addAction(act_img_merge)
        menu_file.addSeparator()

        act_exit = QAction("종료(&X)", self)
        act_exit.setShortcut(QKeySequence.StandardKey.Quit)
        act_exit.triggered.connect(self.close)
        menu_file.addAction(act_exit)

        # [편집] 메뉴
        menu_edit = menubar.addMenu("편집(&E)")
        menu_edit.addAction(self.act_undo)
        menu_edit.addAction(self.act_find)
        menu_edit.addSeparator()
        menu_edit.addAction(self.act_mode_hand)
        menu_edit.addAction(self.act_mode_text)
        menu_edit.addAction(self.act_mode_whiteout)
        menu_edit.addAction(self.act_mode_edit_text)
        menu_edit.addAction(self.act_mode_highlight)
        menu_edit.addAction(self.act_mode_pen)
        menu_edit.addSeparator()
        menu_edit.addAction(self.act_reorder)

        # [페이지] 메뉴
        menu_page = menubar.addMenu("페이지(&P)")
        menu_page.addAction(self.act_reorder)
        menu_page.addAction(self.act_export_pages)

        # [보기] 메뉴
        menu_view = menubar.addMenu("보기(&V)")
        menu_view.addAction(act_zoom_in)
        menu_view.addAction(act_zoom_out)
        menu_view.addAction(act_fit_width)
        menu_view.addAction(act_fit_page)
        menu_view.addSeparator()
        menu_view.addAction(self.dock_thumb.toggleViewAction())

        # [도움말] 메뉴 (자동 업데이트 & 정보)
        menu_help = menubar.addMenu("도움말(&H)")

        act_check_update = QAction("🚀 업데이트 확인...", self)
        act_check_update.setStatusTip("최신 버전 출시 여부 확인 및 자동 업데이트")
        act_check_update.triggered.connect(self.check_for_updates_interactive)
        menu_help.addAction(act_check_update)

        menu_help.addSeparator()

        act_github = QAction("🌐 GitHub 저장소 방문...", self)
        act_github.setStatusTip(f"GitHub 프로젝트 페이지 열기 ({GITHUB_REPO_URL})")
        act_github.triggered.connect(self.open_github_repo)
        menu_help.addAction(act_github)

        menu_help.addSeparator()

        act_about = QAction("ℹ️ BossPDF 정보...", self)
        act_about.setStatusTip("BossPDF 버전 및 소프트웨어 정보")
        act_about.triggered.connect(self.show_about_dialog)
        menu_help.addAction(act_about)

    def _set_edit_mode(self, mode: EditMode, mode_name: str):
        self.viewer.set_mode(mode)
        self.lbl_status_mode.setText(f"모드: {mode_name}")

    def _on_undo(self):
        if self.pdf_engine.undo():
            self.viewer.render_all_pages()
            self.thumbnail_widget.load_thumbnails(self.pdf_engine)
            self.act_undo.setEnabled(self.pdf_engine.can_undo)
            self.status_bar.showMessage("실행 취소되었습니다.", 3000)

    def _on_document_modified(self):
        self.thumbnail_widget.load_thumbnails(self.pdf_engine)
        self.act_undo.setEnabled(self.pdf_engine.can_undo)
        self.status_bar.showMessage("✏️ 문서가 편집되었습니다. [Ctrl+S]로 저장할 수 있습니다.", 4000)

    def open_file_dialog(self):
        init_dir = AppSettings.get_last_open_dir()
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "PDF 파일 열기",
            init_dir,
            "PDF 문서 (*.pdf);;모든 파일 (*.*)"
        )
        if file_path:
            AppSettings.set_last_open_dir(file_path)
            self.load_pdf(file_path)

    def load_pdf(self, file_path: str):
        try:
            try:
                self.pdf_engine.load_document(file_path)
            except EncryptedPdfError:
                # 암호화된 PDF -> 비밀번호 입력 다이얼로그 표시
                def verifier(pw: str) -> bool:
                    try:
                        return self.pdf_engine.load_document(file_path, password=pw)
                    except InvalidPasswordError:
                        return False
                    except Exception:
                        return False

                pw = PasswordDialog.get_password(
                    self,
                    filename=os.path.basename(file_path),
                    verifier=verifier
                )
                if not pw:
                    # 사용자가 취소함
                    return

            self.viewer.set_engine(self.pdf_engine)
            self.thumbnail_widget.load_thumbnails(self.pdf_engine)
            self._update_title()
            self._update_security_status()
            self.lbl_status_file.setText(f"문서: {os.path.basename(file_path)} ({self.pdf_engine.page_count} 페이지)")
            self.lbl_total_page.setText(f"/ {self.pdf_engine.page_count}  ")
            self.txt_page.setText("1")
            self.act_undo.setEnabled(False)
            self.act_mode_hand.setChecked(True)
            self._set_edit_mode(EditMode.HAND, "이동/스크롤")
            if self.search_bar.isVisible() and self.txt_search.text().strip():
                self._perform_search(self.txt_search.text(), reset_index=True)
            else:
                self.viewer.clear_search_highlights()
                self._update_search_status_ui(0, 0, False)
                QTimer.singleShot(80, self._warmup_ocr_step)
            if self.pdf_engine.was_encrypted:
                self.status_bar.showMessage("🔓 암호가 인증되어 문서가 열렸습니다. [비밀번호 해제 후 저장]을 통해 암호를 영구 제거할 수 있습니다.", 6000)
        except Exception as e:
            QMessageBox.critical(self, "열기 오류", f"PDF 파일을 여는 중 오류가 발생했습니다:\n{str(e)}")

    def _update_security_status(self):
        """현재 문서의 암호화 상태를 확인하고 UI 요소를 갱신"""
        if self.pdf_engine.is_loaded() and self.pdf_engine.was_encrypted:
            self.lbl_status_security.setText("🔒 암호 보호됨 (해제 가능)")
            self.lbl_status_security.setVisible(True)
            self.act_remove_password.setEnabled(True)
            self.act_remove_password.setVisible(True)
        else:
            self.lbl_status_security.setVisible(False)
            self.act_remove_password.setEnabled(False)
            self.act_remove_password.setVisible(False)

    def on_remove_password_and_save(self):
        """비밀번호를 완전히 해제(제거)하여 저장"""
        if not self.pdf_engine.is_loaded():
            return

        reply = QMessageBox.question(
            self,
            "비밀번호 해제 후 저장",
            "현재 열려 있는 문서의 비밀번호를 완전히 해제하여 저장하시겠습니까?\n\n"
            "• [예]: 현재 원본 파일에 덮어써서 비밀번호를 즉시 해제합니다.\n"
            "• [아니오]: 비밀번호가 해제된 '새 파일'로 다른 이름으로 저장합니다.\n"
            "• [취소]: 작업을 취소합니다.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Yes
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                self.pdf_engine.save(remove_password=True)
                self._update_security_status()
                self._update_title()
                self.status_bar.showMessage("✅ 비밀번호가 완전히 해제되어 저장되었습니다.", 5000)
                QMessageBox.information(
                    self,
                    "비밀번호 해제 완료",
                    "✅ 현재 파일의 비밀번호가 완전히 해제되었습니다!\n이제 비밀번호 입력 없이 바로 열 수 있습니다."
                )
            except Exception as e:
                QMessageBox.critical(self, "저장 오류", f"비밀번호 해제 저장 중 오류가 발생했습니다:\n{str(e)}")
        elif reply == QMessageBox.StandardButton.No:
            self.save_as_file(remove_password=True)

    def save_file(self):
        if not self.pdf_engine.is_loaded():
            return

        remove_pw = True
        if self.pdf_engine.was_encrypted:
            reply = QMessageBox.question(
                self,
                "비밀번호 해제 저장",
                "이 문서는 원래 비밀번호로 보호되어 있었습니다.\n\n"
                "비밀번호를 완전히 해제(제거)하여 저장하시겠습니까?\n"
                "(해제 시 이후 열람할 때 비밀번호를 묻지 않습니다.)",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Yes
            )
            if reply == QMessageBox.StandardButton.Cancel:
                return
            remove_pw = (reply == QMessageBox.StandardButton.Yes)

        try:
            self.pdf_engine.save(remove_password=remove_pw)
            self._update_security_status()
            if self.pdf_engine.file_path:
                AppSettings.set_last_save_dir(self.pdf_engine.file_path)
            if remove_pw:
                self.status_bar.showMessage("✅ 비밀번호가 해제된 상태로 문서가 저장되었습니다.", 4000)
            else:
                self.status_bar.showMessage("✅ 문서가 성공적으로 저장되었습니다.", 4000)
            self.act_undo.setEnabled(self.pdf_engine.can_undo)
        except Exception as e:
            QMessageBox.critical(self, "저장 오류", f"문서 저장 실패:\n{str(e)}")

    def save_as_file(self, remove_password: Optional[bool] = None):
        if not self.pdf_engine.is_loaded():
            return

        if remove_password is None:
            if self.pdf_engine.was_encrypted:
                reply = QMessageBox.question(
                    self,
                    "비밀번호 해제 여부 확인",
                    "이 문서는 원래 비밀번호로 보호되어 있었습니다.\n\n"
                    "새 파일에 비밀번호를 해제(제거)하여 저장하시겠습니까?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Yes
                )
                if reply == QMessageBox.StandardButton.Cancel:
                    return
                remove_password = (reply == QMessageBox.StandardButton.Yes)
            else:
                remove_password = False

        last_save_dir = AppSettings.get_last_save_dir()
        cur_name = os.path.basename(self.pdf_engine.file_path or "문서.pdf")
        if last_save_dir:
            default_save_path = os.path.join(last_save_dir, cur_name)
        else:
            default_save_path = self.pdf_engine.file_path or "문서.pdf"

        dialog_title = "비밀번호 해제 후 다른 이름으로 저장" if remove_password else "다른 이름으로 저장"
        path, _ = QFileDialog.getSaveFileName(
            self,
            dialog_title,
            default_save_path,
            "PDF 문서 (*.pdf)"
        )
        if path:
            AppSettings.set_last_save_dir(path)
            try:
                self.pdf_engine.save(path, remove_password=remove_password)
                self._update_title()
                self._update_security_status()
                msg = f"✅ 비밀번호가 해제된 새 파일로 저장 완료: {path}" if remove_password else f"✅ 새 파일로 저장 완료: {path}"
                self.status_bar.showMessage(msg, 4000)
            except Exception as e:
                QMessageBox.critical(self, "저장 오류", f"저장 실패:\n{str(e)}")

    def open_export_dialog(self):
        """특정 페이지 추출 및 이미지 내보내기 대화상자 실행"""
        if not self.pdf_engine.is_loaded():
            QMessageBox.warning(self, "안내", "먼저 PDF 문서를 열어주세요.")
            return

        try:
            cur_page = getattr(self.viewer, 'current_page', 0)
            dlg = PageExportDialog(self, engine=self.pdf_engine, current_page=cur_page)
            dlg.exec()
        except Exception as e:
            QMessageBox.critical(self, "내보내기 오류", f"내보내기 창을 여는 중 오류가 발생했습니다:\n{str(e)}")

    def print_document(self):
        """PDF 문서 인쇄 대화상자 실행"""
        if not self.pdf_engine.is_loaded():
            QMessageBox.warning(self, "안내", "먼저 인쇄할 PDF 문서를 열어주세요.")
            return

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dlg = QPrintDialog(printer, self)
        dlg.setWindowTitle("PDF 문서 인쇄")
        dlg.setMinMax(1, self.pdf_engine.page_count)

        if dlg.exec() == QPrintDialog.DialogCode.Accepted:
            try:
                self._render_print_pages(printer)
                self.status_bar.showMessage("🖨️ 인쇄 작업이 전송되었습니다.", 4000)
            except Exception as e:
                QMessageBox.critical(self, "인쇄 오류", f"인쇄 처리 중 오류가 발생했습니다:\n{str(e)}")

    def print_preview(self):
        """인쇄 미리보기 창 실행"""
        if not self.pdf_engine.is_loaded():
            QMessageBox.warning(self, "안내", "먼저 인쇄할 PDF 문서를 열어주세요.")
            return

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        preview = QPrintPreviewDialog(printer, self)
        preview.setWindowTitle("BossPDF - 인쇄 미리보기")
        preview.resize(1000, 800)
        preview.paintRequested.connect(self._render_print_pages)
        preview.exec()

    def _render_print_pages(self, printer: QPrinter):
        """프린터 디바이스로 고화질(300 DPI) 페이지 렌더링 및 출력"""
        if not self.pdf_engine or not self.pdf_engine.is_loaded():
            return

        painter = QPainter(printer)

        print_range = printer.printRange()
        if print_range == QPrinter.PrintRange.PageRange:
            from_page = max(0, printer.fromPage() - 1)
            to_page = min(self.pdf_engine.page_count - 1, printer.toPage() - 1)
        elif print_range == QPrinter.PrintRange.CurrentPage:
            from_page = to_page = max(0, min(self.viewer.current_page, self.pdf_engine.page_count - 1))
        else:
            from_page = 0
            to_page = self.pdf_engine.page_count - 1

        target_pages = list(range(from_page, to_page + 1))

        for idx, page_idx in enumerate(target_pages):
            if idx > 0:
                printer.newPage()

            page = self.pdf_engine.doc[page_idx]

            # 300 DPI 고해상도 렌더링
            zoom = 300.0 / 72.0
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)

            qimg = QImage(
                pix.samples,
                pix.width,
                pix.height,
                pix.stride,
                QImage.Format.Format_RGB888
            )

            printer_rect = printer.pageRect(QPrinter.Unit.DevicePixel)
            scale = min(
                printer_rect.width() / qimg.width(),
                printer_rect.height() / qimg.height()
            )
            dest_w = qimg.width() * scale
            dest_h = qimg.height() * scale
            dest_x = printer_rect.left() + (printer_rect.width() - dest_w) / 2.0
            dest_y = printer_rect.top() + (printer_rect.height() - dest_h) / 2.0

            painter.drawImage(
                QRectF(dest_x, dest_y, dest_w, dest_h),
                qimg,
                QRectF(0, 0, qimg.width(), qimg.height())
            )

        painter.end()

    def open_image_merge_dialog(self):
        dlg = ImageMergeDialog(self)
        dlg.pdf_created.connect(self._on_image_pdf_created)
        dlg.exec()

    def _on_image_pdf_created(self, created_pdf_path: str):
        if os.path.exists(created_pdf_path):
            self.load_pdf(created_pdf_path)
            self.status_bar.showMessage(f"🖼️ 병합된 이미지 PDF 열림: {created_pdf_path}", 5000)

    def _on_page_changed(self, current: int, total: int):
        self.txt_page.blockSignals(True)
        self.txt_page.setText(str(current))
        self.txt_page.blockSignals(False)
        self.lbl_total_page.setText(f"/ {total}  ")
        self.thumbnail_widget.select_page(current - 1)

    def _on_zoom_changed(self, zoom: float):
        pct = int(zoom * 100)
        self.lbl_status_zoom.setText(f"{pct}%")
        self.combo_zoom.blockSignals(True)
        self.combo_zoom.setCurrentText(f"{pct}%")
        self.combo_zoom.blockSignals(False)

    def _on_combo_zoom_changed(self, text: str):
        try:
            val = float(text.replace("%", "").strip()) / 100.0
            self.viewer.set_zoom(val)
        except ValueError:
            pass

    def _on_jump_page(self):
        try:
            p = int(self.txt_page.text().strip()) - 1
            self.viewer.scroll_to_page(p)
        except ValueError:
            pass

    def _on_prev_page(self):
        try:
            cur = int(self.txt_page.text().strip())
            if cur > 1:
                self.viewer.scroll_to_page(cur - 2)
        except ValueError:
            pass

    def _on_next_page(self):
        try:
            cur = int(self.txt_page.text().strip())
            if cur < self.pdf_engine.page_count:
                self.viewer.scroll_to_page(cur)
        except ValueError:
            pass

    def _on_thumbnail_page_selected(self, page_idx: int):
        self.viewer.scroll_to_page(page_idx)

    def _on_thumbnail_rotate(self, page_idx: int, angle: int):
        self.pdf_engine.rotate_page(page_idx, angle)
        self.viewer.reload_single_page(page_idx)
        self.thumbnail_widget.load_thumbnails(self.pdf_engine)
        self.act_undo.setEnabled(self.pdf_engine.can_undo)

    def _on_thumbnail_delete(self, page_idx: int):
        try:
            self.pdf_engine.delete_page(page_idx)
            self.viewer.render_all_pages()
            self.thumbnail_widget.load_thumbnails(self.pdf_engine)
            self.lbl_total_page.setText(f"/ {self.pdf_engine.page_count}  ")
            self.act_undo.setEnabled(self.pdf_engine.can_undo)
            self.status_bar.showMessage("페이지가 삭제되었습니다.", 3000)
        except Exception as e:
            QMessageBox.warning(self, "삭제 실패", str(e))

    def open_page_reorder_dialog(self):
        """전체 페이지 순서 변경 및 관리 대화상자 실행"""
        if not self.pdf_engine.is_loaded():
            QMessageBox.warning(self, "안내", "먼저 PDF 문서를 열어주세요.")
            return
        if self.pdf_engine.page_count <= 1:
            QMessageBox.information(self, "안내", "문서가 1페이지뿐이어서 순서를 변경할 수 없습니다.")
            return

        dlg = PageReorderDialog(self.pdf_engine, self)
        dlg.order_changed.connect(self._on_page_order_changed)
        dlg.exec()

    def _on_page_order_changed(self):
        """페이지 순서가 변경되었을 때 화면 및 썸네일 새로고침"""
        self.viewer.render_all_pages()
        self.thumbnail_widget.load_thumbnails(self.pdf_engine)
        self.act_undo.setEnabled(self.pdf_engine.can_undo)
        self.status_bar.showMessage("📑 페이지 순서가 성공적으로 변경되었습니다.", 4000)

    def _update_title(self):
        if self.pdf_engine.is_loaded():
            fname = os.path.basename(self.pdf_engine.file_path)
            self.setWindowTitle(f"BossPDF v{__version__} - {fname}")
        else:
            self.setWindowTitle(f"BossPDF v{__version__} - 고성능 PDF 뷰어 & 올인원 편집기")

    # ==================== 문서 내 단어 검색 (Ctrl+F) ====================

    def open_search_bar(self):
        """Ctrl+F 검색바 표시 및 입력창 포커스"""
        self.search_bar.setVisible(True)
        self.txt_search.setFocus()
        self.txt_search.selectAll()
        query = self.txt_search.text().strip()
        if query:
            self._perform_search(query, reset_index=False)

    def close_search_bar(self):
        """검색바 숨김 및 캔버스 검색 강조 블록 제거"""
        self.search_bar.setVisible(False)
        self.viewer.clear_search_highlights()
        self._last_search_query = ""
        self.viewer.setFocus()

    def eventFilter(self, obj, event):
        """검색 입력창에서 Enter / Shift+Enter / Esc 키 동작 처리"""
        if obj is self.txt_search and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            mods = event.modifiers()
            if key == Qt.Key.Key_Escape:
                self.close_search_bar()
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if mods & Qt.KeyboardModifier.ShiftModifier:
                    self.find_prev_result()
                else:
                    self.find_next_result()
                return True
        return super().eventFilter(obj, event)

    def _warmup_ocr_step(self):
        """유휴 시간에 이미지 기반 PDF 페이지를 1페이지씩 백그라운드 OCR 캐싱"""
        if not self.pdf_engine.is_loaded():
            return
        has_more = self.pdf_engine.warmup_next_ocr_page()
        if has_more:
            QTimer.singleShot(50, self._warmup_ocr_step)

    def _on_search_text_changed(self, text: str):
        if not (text or "").strip():
            self._search_debounce_timer.stop()
            self._perform_search("", reset_index=True)
            return
        self._search_debounce_timer.start()

    def _on_debounced_search(self):
        self._perform_search(self.txt_search.text(), reset_index=True)

    def _perform_search(self, raw_text: str, reset_index: bool = True):
        query = (raw_text or "").strip()
        self._last_search_query = query

        if not query or not self.pdf_engine.is_loaded():
            self.viewer.clear_search_highlights()
            self._update_search_status_ui(0, 0, False)
            return

        results = self.pdf_engine.search_text(query)
        total = len(results)
        if total == 0:
            self.viewer.clear_search_highlights()
            self._update_search_status_ui(0, 0, True)
            return

        if reset_index or self.viewer.current_search_index < 0 or self.viewer.current_search_index >= total:
            active_idx = 0
        else:
            active_idx = self.viewer.current_search_index

        self.viewer.set_search_results(results, active_index=active_idx)
        self._update_search_status_ui(active_idx + 1, total, True)

    def _update_search_status_ui(self, current_one_based: int, total: int, has_query: bool):
        has_matches = total > 0 and current_one_based > 0
        self.btn_search_prev.setEnabled(total > 0)
        self.btn_search_next.setEnabled(total > 0)

        if not has_query:
            self.lbl_search_status.setText("0 / 0건")
            self.lbl_search_status.setStyleSheet(
                "background-color: #F2F2F7; color: #86868B; font-weight: 600; padding: 4px 12px; border-radius: 6px; font-size: 12.5px;"
            )
        elif has_matches:
            self.lbl_search_status.setText(f"{current_one_based} / {total}건 ({current_one_based}번째 결과)")
            self.lbl_search_status.setStyleSheet(
                "background-color: #EBF3FF; color: #007AFF; font-weight: 700; padding: 4px 12px; border-radius: 6px; font-size: 12.5px;"
            )
        else:
            self.lbl_search_status.setText("0 / 0건 (검색 결과 없음)")
            self.lbl_search_status.setStyleSheet(
                "background-color: #FFF2F2; color: #FF3B30; font-weight: 700; padding: 4px 12px; border-radius: 6px; font-size: 12.5px;"
            )

    def find_next_result(self):
        """다음 검색 결과로 이동 (순환)"""
        if not self.search_bar.isVisible():
            self.open_search_bar()
            return
        query = self.txt_search.text().strip()
        if not query:
            return
        if query != self._last_search_query or not self.viewer.search_results:
            self._perform_search(query, reset_index=True)
            return
        total = len(self.viewer.search_results)
        if total == 0:
            return
        next_idx = (self.viewer.current_search_index + 1) % total
        self.viewer.set_active_search_index(next_idx)
        self._update_search_status_ui(next_idx + 1, total, True)

    def find_prev_result(self):
        """이전 검색 결과로 이동 (순환)"""
        if not self.search_bar.isVisible():
            self.open_search_bar()
            return
        query = self.txt_search.text().strip()
        if not query:
            return
        if query != self._last_search_query or not self.viewer.search_results:
            self._perform_search(query, reset_index=True)
            return
        total = len(self.viewer.search_results)
        if total == 0:
            return
        prev_idx = (self.viewer.current_search_index - 1) % total
        self.viewer.set_active_search_index(prev_idx)
        self._update_search_status_ui(prev_idx + 1, total, True)

    # ==================== 자동 업데이트 및 정보 (GitHub Releases) ====================

    def _check_updates_background(self):
        """앱 시작 후 백그라운드에서 최신 버전 출시 여부 비동기 확인"""
        self._bg_update_thread = CheckUpdateThread(current_version=__version__, parent=self)
        self._bg_update_thread.check_finished.connect(self._on_bg_update_checked)
        self._bg_update_thread.start()

    def _on_bg_update_checked(self, info: UpdateInfo):
        if info and info.has_update:
            self.status_bar.showMessage(
                f"🚀 새로운 BossPDF v{info.latest_version} 버전이 출시되었습니다! [도움말 > 업데이트 확인]", 12000
            )

    def check_for_updates_interactive(self):
        """도움말 메뉴에서 수동으로 업데이트 확인 클릭 시 실행"""
        self.status_bar.showMessage("GitHub에서 최신 버전을 확인하는 중...", 3000)
        self._manual_update_thread = CheckUpdateThread(current_version=__version__, parent=self)
        self._manual_update_thread.check_finished.connect(self._on_manual_update_checked)
        self._manual_update_thread.start()

    def _on_manual_update_checked(self, info: UpdateInfo):
        if info.has_update:
            dlg = UpdateDialog(self, update_info=info)
            dlg.exec()
        elif info.error_message:
            QMessageBox.information(
                self,
                "업데이트 확인",
                f"현재 최신 버전(v{__version__})을 사용 중이거나 아직 신규 릴리스가 등록되지 않았습니다.\n\n상세: {info.error_message}"
            )
        else:
            QMessageBox.information(
                self,
                "최신 버전",
                f"현재 최신 버전(v{__version__})을 사용 중입니다!\n새로운 업데이트가 없습니다."
            )

    def open_github_repo(self):
        import webbrowser
        webbrowser.open(GITHUB_REPO_URL)

    def show_about_dialog(self):
        QMessageBox.about(
            self,
            "BossPDF 정보",
            f"<h3>BossPDF v{__version__}</h3>"
            "<p>애플 macOS 감성의 초고속 PDF 뷰어 & 올인원 편집기</p>"
            "<p>• 개발: Boss Software (백도윤 보스 전담)<br>"
            f"• 저장소: <a href='{GITHUB_REPO_URL}'>{GITHUB_REPO_URL}</a></p>"
            "<p><b>주요 기능</b>: 연속 스크롤, 텍스트 삽입/수정/삭제, 형광펜/서명, "
            "페이지 순서 재배치, 특정 페이지/이어붙이기 이미지 내보내기, 비밀번호 해제, 자동 업데이트</p>"
        )


