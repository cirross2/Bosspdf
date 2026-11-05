"""
PDF 뷰어 및 편집기 메인 윈도우 UI
(연속 스크롤, 실시간 편집 도구, SVG 벡터 아이콘, 다크/화이트 모드, 사이드바 최소화 지원)
"""
import os
from typing import Optional
from PySide6.QtWidgets import (
    QMainWindow, QToolBar, QToolButton, QMenu, QSizePolicy, QFileDialog, QMessageBox,
    QDockWidget, QLineEdit, QLabel, QPushButton, QComboBox, QWidget,
    QHBoxLayout, QVBoxLayout, QFrame, QApplication
)
from PySide6.QtCore import Qt, QSize, QRect, QEvent, QTimer
from PySide6.QtGui import QAction, QKeySequence, QActionGroup, QPainter, QShortcut, QGuiApplication

from core.pdf_engine import PdfEngine, EncryptedPdfError, InvalidPasswordError
from core.settings_manager import AppSettings
from core import window_cascade, single_instance
from core.version import __version__, GITHUB_REPO_URL
from core.updater import CheckUpdateThread, UpdateInfo
from ui.viewer_widget import PdfViewerWidget, EditMode
from ui.thumbnail_widget import ThumbnailWidget
from ui.password_dialog import PasswordDialog
from ui.theme import AppleTheme
from ui.overlays import FloatingBar, ToastLabel
from ui.icons import get_icon


class MainWindow(QMainWindow):
    """
    연속 스크롤 뷰어 및 텍스트/마크업 편집 메인 윈도우
    """
    _windows: list = []
    _update_check_scheduled = False
    _bg_update_thread = None
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BossPDF - 고성능 PDF 뷰어 & 편집기")
        self.resize(1280, 850)
        self._restore_window_geometry()

        # 이동/크기 변경 후 잠시 뒤 창 위치를 저장 (강제 종료·자동 업데이트 대비)
        self._geometry_save_timer = QTimer(self)
        self._geometry_save_timer.setSingleShot(True)
        self._geometry_save_timer.setInterval(500)
        self._geometry_save_timer.timeout.connect(self._save_window_geometry)

        self.current_theme = AppSettings.get_theme_mode(default=AppleTheme.LIGHT)
        self.pdf_engine = PdfEngine()

        self._init_ui()
        self._create_menus_and_toolbars()
        self._update_title()
        self.apply_theme(self.current_theme)

        # 앱(프로세스)마다 한 번만, 시작 2.5초 후 백그라운드에서 최신 업데이트 확인
        if not MainWindow._update_check_scheduled:
            MainWindow._update_check_scheduled = True
            QTimer.singleShot(2500, self._check_updates_background)

    # ---------- 한 프로세스 안의 여러 문서 창 관리 ----------
    @classmethod
    def open_window(cls, pdf_path: Optional[str] = None) -> "MainWindow":
        """새 문서 창을 열고 (같은 파일이 이미 열려 있으면 그 창을 앞으로) 반환"""
        if pdf_path:
            target = os.path.normcase(os.path.abspath(pdf_path))
            for w in list(cls._windows):
                fp = w.pdf_engine.file_path if w.pdf_engine and w.pdf_engine.is_loaded() else None
                if fp and os.path.normcase(os.path.abspath(fp)) == target:
                    w.bring_to_front()
                    return w
        win = cls()
        win.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        cls._windows.append(win)
        win.show()
        win.bring_to_front()
        if pdf_path:
            QTimer.singleShot(0, lambda: win.load_pdf(pdf_path))
        return win

    def bring_to_front(self):
        if self.isMinimized():
            self.showNormal()
        self.raise_()
        self.activateWindow()

    @classmethod
    def handle_external_request(cls, paths):
        """다른 BossPDF 실행에서 전달받은 열기 요청 처리 (single_instance)"""
        pdfs = [p for p in paths if p.lower().endswith(".pdf") and os.path.exists(p)]
        if not pdfs:
            cls.open_window(None)
        for p in pdfs:
            cls.open_window(p)

    def nativeEvent(self, event_type, message):
        handled = single_instance.handle_native_message(event_type, message, MainWindow.handle_external_request)
        if handled:
            return True, 1
        return super().nativeEvent(event_type, message)

    # ---------- 창 위치·크기 기억 + 계단식 배치 ----------
    def _restore_window_geometry(self):
        # 사용자가 직접 옮기거나 크기를 바꾼 경우에만 저장 (계단식으로 비켜 선 위치는 저장하지 않음)
        self._geometry_tracking = False
        self._geometry_changed_by_user = False

        geometry = AppSettings.get_window_geometry()
        if geometry is not None:
            try:
                self.restoreGeometry(geometry)
            except Exception:
                pass
        self._cascade_if_overlapping()

    def _cascade_if_overlapping(self):
        """다른 BossPDF 창이 같은 자리에 떠 있으면 오른쪽 아래로 살짝 비켜서 열기"""
        if self.isMaximized() or self.isFullScreen():
            return
        occupied = window_cascade.other_window_positions()
        if not occupied:
            return
        geo = self.geometry()
        bounds = None
        screen = QGuiApplication.screenAt(geo.center()) or QGuiApplication.primaryScreen()
        if screen is not None:
            avail = screen.availableGeometry()
            bounds = (avail.left(), avail.top(), avail.right(), avail.bottom(), geo.width(), geo.height())
        nx, ny = window_cascade.find_free_position(geo.x(), geo.y(), occupied, bounds)
        if (nx, ny) != (geo.x(), geo.y()):
            self.setGeometry(QRect(nx, ny, geo.width(), geo.height()))

    def _publish_window_position(self):
        geo = self.geometry()
        window_cascade.publish_position(int(self.winId()), geo.x(), geo.y())

    def _start_geometry_tracking(self):
        self._geometry_tracking = True

    def _save_window_geometry(self):
        if self.isVisible() and not self.isMinimized() and self._geometry_changed_by_user:
            AppSettings.set_window_geometry(self.saveGeometry())

    def _on_geometry_changed(self):
        if not getattr(self, "_geometry_tracking", False) or not self.isVisible():
            return
        self._publish_window_position()
        self._geometry_changed_by_user = True
        self._geometry_save_timer.start()

    def showEvent(self, event):
        super().showEvent(event)
        self._publish_window_position()
        # 첫 표시 직후 발생하는 시스템 이동/크기 이벤트는 사용자 조작으로 보지 않음
        QTimer.singleShot(300, self._start_geometry_tracking)

    def moveEvent(self, event):
        super().moveEvent(event)
        self._on_geometry_changed()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._on_geometry_changed()

    def closeEvent(self, event):
        self._save_window_geometry()
        window_cascade.unpublish(int(self.winId()))
        if self in MainWindow._windows:
            MainWindow._windows.remove(self)
        super().closeEvent(event)

    def _init_ui(self):
        # 중앙 컨테이너 (상단 Ctrl+F 검색바 + 연속 스크롤 뷰어)
        central_container = QWidget(self)
        central_layout = QVBoxLayout(central_container)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)

        # Apple 스타일 상단 단어 검색 바 (Ctrl+F)
        self.search_bar = QFrame(self)
        self.search_bar.setObjectName("searchBarFrame")
        search_layout = QHBoxLayout(self.search_bar)
        search_layout.setContentsMargins(10, 5, 10, 5)
        search_layout.setSpacing(8)

        self.lbl_search_title = QLabel("단어 검색:")
        search_layout.addWidget(self.lbl_search_title)

        self.txt_search = QLineEdit(self.search_bar)
        self.txt_search.setPlaceholderText("검색할 단어를 입력하세요 (Enter: 다음, Shift+Enter: 이전, Esc: 닫기)")
        self.txt_search.setMinimumWidth(260)
        self.txt_search.setMaximumWidth(400)
        self.txt_search.setClearButtonEnabled(True)
        self.txt_search.installEventFilter(self)
        self.txt_search.textChanged.connect(self._on_search_text_changed)
        search_layout.addWidget(self.txt_search)

        self.lbl_search_status = QLabel("0 / 0건")
        self.lbl_search_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_search_status.setMinimumWidth(145)
        search_layout.addWidget(self.lbl_search_status)

        self.btn_search_prev = QPushButton()
        self.btn_search_prev.setToolTip("이전 검색 결과로 이동 (Shift+Enter / Shift+F3)")
        self.btn_search_prev.setFixedSize(28, 28)
        self.btn_search_prev.setEnabled(False)
        self.btn_search_prev.clicked.connect(self.find_prev_result)
        search_layout.addWidget(self.btn_search_prev)

        self.btn_search_next = QPushButton()
        self.btn_search_next.setToolTip("다음 검색 결과로 이동 (Enter / F3)")
        self.btn_search_next.setFixedSize(28, 28)
        self.btn_search_next.setEnabled(False)
        self.btn_search_next.clicked.connect(self.find_next_result)
        search_layout.addWidget(self.btn_search_next)

        search_layout.addStretch(1)

        self.btn_search_close = QPushButton()
        self.btn_search_close.setToolTip("검색창 닫기 및 강조 표시 해제 (Esc)")
        self.btn_search_close.setFixedSize(28, 28)
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
        # 패널 안에 같은 제목이 있으므로 도크 제목줄은 숨겨 세로 공간 확보 (닫기는 레일 버튼/Ctrl+B)
        self.dock_thumb.setTitleBarWidget(QWidget(self.dock_thumb))
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.dock_thumb)

        # 스크롤 최적화: 뷰어 스크롤 중 썸네일 생성 일시 정지 연동
        self.viewer.scroll_state_changed.connect(self.thumbnail_widget.on_viewer_scroll_state_changed)

        # 사이드바 가시성 복원 및 변경 감지
        initial_sidebar_vis = AppSettings.get_sidebar_visible(default=True)
        self.dock_thumb.setVisible(initial_sidebar_vis)
        self.dock_thumb.visibilityChanged.connect(self._on_dock_visibility_changed)

        # 상태 표시줄은 쓰지 않음: 알림은 문서 위 토스트(self.status_bar)로 표시 (_create_menus_and_toolbars)

    def _create_menus_and_toolbars(self):
        # ---------- 액션 정의 (단축키는 창에 직접 등록해 메뉴바 없이도 동작) ----------
        def make_action(text, slot=None, shortcut=None, tip=None, checkable=False):
            act = QAction(text, self)
            if shortcut is not None:
                act.setShortcut(QKeySequence(shortcut) if isinstance(shortcut, str) else shortcut)
            if tip:
                act.setToolTip(tip)
                act.setStatusTip(tip)
            act.setCheckable(checkable)
            if slot is not None:
                act.triggered.connect(slot)
            self.addAction(act)
            return act

        self.act_sidebar = make_action("페이지 썸네일 보기/가리기", self.toggle_sidebar, "Ctrl+B",
                                       "페이지 썸네일 보기/가리기 (Ctrl+B)", checkable=True)
        self.act_sidebar.setChecked(self.dock_thumb.isVisible())

        self.act_open = make_action("열기...", self.open_file_dialog, QKeySequence.StandardKey.Open, "파일 열기 (Ctrl+O)")
        self.act_save = make_action("저장", self.save_file, QKeySequence.StandardKey.Save, "저장 (Ctrl+S)")
        self.act_save_as = make_action("다른 이름으로 저장...", self.save_as_file, QKeySequence.StandardKey.SaveAs)
        self.act_remove_password = make_action("비밀번호 해제 후 저장", self.on_remove_password_and_save,
                                               tip="문서의 비밀번호를 완전히 해제하여 저장")
        self.act_remove_password.setEnabled(False)
        self.act_remove_password.setVisible(False)
        self.act_export_pages = make_action("페이지 내보내기...", self.open_export_dialog, "Ctrl+E",
                                            "특정 페이지를 새 PDF나 이미지로 내보내기 (Ctrl+E)")
        self.act_print = make_action("인쇄...", self.print_document, QKeySequence.StandardKey.Print, "인쇄 (Ctrl+P)")
        self.act_print_preview = make_action("인쇄 미리보기...", self.print_preview)
        self.act_img_merge = make_action("이미지를 PDF로 합치기...", self.open_image_merge_dialog,
                                         tip="여러 이미지를 순서대로 하나의 PDF로 합치기")
        self.act_reorder = make_action("페이지 순서 관리...", self.open_page_reorder_dialog,
                                       tip="전체 페이지 순서 변경 및 관리")
        self.act_find = make_action("단어 검색", self.open_search_bar, QKeySequence.StandardKey.Find, "단어 검색 (Ctrl+F)")
        self.act_theme = make_action("테마 전환", self.toggle_theme, "Ctrl+T")
        self.act_fullscreen = make_action("집중 모드 (전체 화면)", self.toggle_focus_mode, "F11",
                                          "도구를 모두 숨기고 문서만 보기 (F11, 나가기: Esc)", checkable=True)
        self.act_exit = make_action("종료", self.close, QKeySequence.StandardKey.Quit)

        self.act_zoom_out = make_action("축소", self.viewer.zoom_out, QKeySequence.StandardKey.ZoomOut, "축소 (Ctrl+-)")
        self.act_zoom_in = make_action("확대", self.viewer.zoom_in, QKeySequence.StandardKey.ZoomIn, "확대 (Ctrl++)")
        self.act_fit_width = make_action("너비 맞춤", self.viewer.fit_to_width, tip="너비 맞춤")
        self.act_fit_page = make_action("전체 맞춤", self.viewer.fit_to_page, tip="한 페이지 전체 맞춤")

        self.shortcut_find_next = QShortcut(QKeySequence("F3"), self)
        self.shortcut_find_next.activated.connect(self.find_next_result)
        self.shortcut_find_prev = QShortcut(QKeySequence("Shift+F3"), self)
        self.shortcut_find_prev.activated.connect(self.find_prev_result)
        self.shortcut_exit_focus = QShortcut(QKeySequence("Esc"), self)
        self.shortcut_exit_focus.setContext(Qt.ShortcutContext.WindowShortcut)
        self.shortcut_exit_focus.activated.connect(self._exit_focus_mode)
        self.shortcut_exit_focus.setEnabled(False)

        # 편집 모드 (서로 배타적)
        mode_group = QActionGroup(self)
        mode_group.setExclusive(True)

        def make_mode(text, mode, tip):
            act = make_action(text, lambda: self._set_edit_mode(mode, text), tip=tip, checkable=True)
            mode_group.addAction(act)
            return act

        self.act_mode_hand = make_mode("이동/스크롤", EditMode.HAND, "이동/스크롤 도구")
        self.act_mode_hand.setChecked(True)
        self.act_mode_text = make_mode("텍스트 추가", EditMode.ADD_TEXT, "텍스트 추가 (클릭한 위치)")
        self.act_mode_whiteout = make_mode("텍스트 삭제/가리기", EditMode.WHITEOUT, "텍스트 삭제/가리기 (드래그)")
        self.act_mode_edit_text = make_mode("텍스트 수정", EditMode.EDIT_TEXT, "텍스트 수정 (드래그)")
        self.act_mode_highlight = make_mode("형광펜", EditMode.HIGHLIGHT, "형광펜 (드래그)")
        self.act_mode_pen = make_mode("손글씨/서명", EditMode.PEN, "손글씨/서명 (마우스로 그리기)")

        self.act_undo = make_action("실행 취소", self._on_undo, QKeySequence.StandardKey.Undo, "실행 취소 (Ctrl+Z)")
        self.act_undo.setEnabled(False)

        act_check_update = QAction("업데이트 확인...", self)
        act_check_update.triggered.connect(self.check_for_updates_interactive)
        act_github = QAction("GitHub 저장소 방문...", self)
        act_github.triggered.connect(self.open_github_repo)
        act_about = QAction("BossPDF 정보...", self)
        act_about.triggered.connect(self.show_about_dialog)

        # ---------- ☰ 메뉴 (기존 메뉴바 대체) ----------
        self.main_menu = QMenu(self)
        for act in (self.act_open, self.act_save, self.act_save_as, self.act_remove_password):
            self.main_menu.addAction(act)
        self.main_menu.addSeparator()
        for act in (self.act_export_pages, self.act_print, self.act_print_preview):
            self.main_menu.addAction(act)
        self.main_menu.addSeparator()
        self.main_menu.addAction(self.act_reorder)
        self.main_menu.addAction(self.act_img_merge)
        self.main_menu.addSeparator()
        menu_view = self.main_menu.addMenu("보기")
        for act in (self.act_sidebar, self.act_fullscreen, self.act_theme):
            menu_view.addAction(act)
        menu_view.addSeparator()
        for act in (self.act_zoom_in, self.act_zoom_out, self.act_fit_width, self.act_fit_page):
            menu_view.addAction(act)
        menu_help = self.main_menu.addMenu("도움말")
        for act in (act_check_update, act_github, act_about):
            menu_help.addAction(act)
        self.main_menu.addSeparator()
        self.main_menu.addAction(self.act_exit)

        # ---------- 왼쪽 세로 레일 ----------
        self.rail = QToolBar("도구", self)
        self.rail.setObjectName("sideRail")
        self.rail.setOrientation(Qt.Orientation.Vertical)
        self.rail.setIconSize(QSize(20, 20))
        self.rail.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.rail.setMovable(False)
        self.rail.setFloatable(False)
        self.rail.toggleViewAction().setVisible(False)
        self.addToolBar(Qt.ToolBarArea.LeftToolBarArea, self.rail)

        self.btn_main_menu = QToolButton(self.rail)
        self.btn_main_menu.setObjectName("railMenuButton")
        self.btn_main_menu.setToolTip("메뉴")
        self.btn_main_menu.setMenu(self.main_menu)
        self.btn_main_menu.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.btn_main_menu.setIconSize(QSize(20, 20))
        self.rail.addWidget(self.btn_main_menu)
        self.rail.addAction(self.act_sidebar)
        self.rail.addSeparator()
        self.rail.addAction(self.act_open)
        self.rail.addAction(self.act_save)
        self.rail.addSeparator()
        for act in (self.act_mode_hand, self.act_mode_text, self.act_mode_whiteout,
                    self.act_mode_edit_text, self.act_mode_highlight, self.act_mode_pen):
            self.rail.addAction(act)
        self.rail.addSeparator()
        self.rail.addAction(self.act_undo)
        self.rail.addAction(self.act_find)
        rail_spacer = QWidget(self.rail)
        rail_spacer.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.rail.addWidget(rail_spacer)
        self.rail.addAction(self.act_theme)

        # ---------- 문서 위 플로팅 바 (페이지 이동·줌) ----------
        self.floating_bar = FloatingBar(self.viewer)

        def bar_button(action):
            btn = QToolButton(self.floating_bar)
            btn.setDefaultAction(action)
            btn.setIconSize(QSize(18, 18))
            btn.setAutoRaise(True)
            return btn

        self.btn_prev_page = QPushButton(self.floating_bar)
        self.btn_prev_page.setToolTip("이전 페이지")
        self.btn_prev_page.setFixedSize(26, 24)
        self.btn_prev_page.clicked.connect(self._on_prev_page)
        self.txt_page = QLineEdit("1", self.floating_bar)
        self.txt_page.setFixedWidth(40)
        self.txt_page.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.txt_page.returnPressed.connect(self._on_jump_page)
        self.lbl_total_page = QLabel("/ 0", self.floating_bar)
        self.lbl_total_page.setStyleSheet("color: #86868B; font-weight: 500; padding: 0 4px;")
        self.btn_next_page = QPushButton(self.floating_bar)
        self.btn_next_page.setToolTip("다음 페이지")
        self.btn_next_page.setFixedSize(26, 24)
        self.btn_next_page.clicked.connect(self._on_next_page)

        self.combo_zoom = QComboBox(self.floating_bar)
        self.combo_zoom.addItems(["50%", "75%", "100%", "120%", "150%", "200%"])
        self.combo_zoom.setCurrentText("120%")
        self.combo_zoom.setFixedWidth(78)
        self.combo_zoom.currentTextChanged.connect(self._on_combo_zoom_changed)

        for w in (self.btn_prev_page, self.txt_page, self.lbl_total_page, self.btn_next_page):
            self.floating_bar.add_widget(w)
        self.floating_bar.add_separator()
        self.floating_bar.add_widget(bar_button(self.act_zoom_out))
        self.floating_bar.add_widget(self.combo_zoom)
        self.floating_bar.add_widget(bar_button(self.act_zoom_in))
        self.floating_bar.add_widget(bar_button(self.act_fit_width))
        self.floating_bar.add_widget(bar_button(self.act_fit_page))
        self.floating_bar.add_separator()
        self.floating_bar.add_widget(bar_button(self.act_fullscreen))

        # 상태 표시줄 대신 문서 위 알림
        self.status_bar = ToastLabel(self.viewer)
        self.viewer.installEventFilter(self)
        QTimer.singleShot(0, self._reposition_overlays)

    def _reposition_overlays(self):
        if hasattr(self, "floating_bar"):
            self.floating_bar.reposition()
            self.status_bar.reposition()

    # ==================== 집중 모드 (F11) ====================

    def toggle_focus_mode(self):
        entering = not getattr(self, "_focus_mode", False)
        self._focus_mode = entering
        self.act_fullscreen.setChecked(entering)
        self.shortcut_exit_focus.setEnabled(entering)
        if entering:
            self._focus_restore = {
                "maximized": self.isMaximized(),
                "sidebar": self.dock_thumb.isVisible(),
            }
            self.rail.setVisible(False)
            self.dock_thumb.blockSignals(True)
            self.dock_thumb.setVisible(False)
            self.dock_thumb.blockSignals(False)
            self.showFullScreen()
            self.status_bar.showMessage("집중 모드입니다. Esc나 F11을 누르면 돌아갑니다.", 2500)
        else:
            state = getattr(self, "_focus_restore", {"maximized": False, "sidebar": True})
            if state["maximized"]:
                self.showMaximized()
            else:
                self.showNormal()
            self.rail.setVisible(True)
            self.dock_thumb.blockSignals(True)
            self.dock_thumb.setVisible(state["sidebar"])
            self.dock_thumb.blockSignals(False)
            self.act_sidebar.setChecked(state["sidebar"])
        QTimer.singleShot(0, self._reposition_overlays)

    def _exit_focus_mode(self):
        if getattr(self, "_focus_mode", False):
            self.toggle_focus_mode()

    # ==================== 사이드바 및 테마 제어 ====================

    def toggle_sidebar(self):
        """사이드바(페이지 썸네일 패널) 최소화/복원 토글"""
        is_vis = not self.dock_thumb.isVisible()
        self.dock_thumb.setVisible(is_vis)
        self.act_sidebar.setChecked(is_vis)
        AppSettings.set_sidebar_visible(is_vis)

    def _on_dock_visibility_changed(self, visible: bool):
        if hasattr(self, "act_sidebar"):
            self.act_sidebar.setChecked(visible)
        AppSettings.set_sidebar_visible(visible)

    def toggle_theme(self):
        """다크 모드 <-> 라이트 모드 상호 전환"""
        new_theme = AppleTheme.DARK if self.current_theme == AppleTheme.LIGHT else AppleTheme.LIGHT
        self.apply_theme(new_theme)
        # 같은 프로세스의 다른 문서 창도 함께 전환
        for w in MainWindow._windows:
            if w is not self:
                w.apply_theme(new_theme)

    def apply_theme(self, theme_mode: str):
        """전체 애플리케이션에 다크/라이트 테마 및 SVG 아이콘 팔레트 일괄 적용"""
        self.current_theme = theme_mode
        is_dark = (theme_mode == AppleTheme.DARK)
        p = AppleTheme.get_palette(theme_mode)

        # 1. 앱 전역 QSS 스타일시트 적용
        app = QApplication.instance()
        if app:
            app.setStyleSheet(AppleTheme.get_stylesheet(theme_mode))

        # 2. 뷰어 및 썸네일 위젯 테마 동기화
        self.viewer.set_theme(theme_mode)
        self.thumbnail_widget.apply_theme(theme_mode)

        # 3. 모든 액션 및 버튼의 SVG 아이콘 리렌더링
        self._update_all_icons()

        # 4. 상단 검색바 프레임 및 상태 레이블 스타일 갱신
        self.search_bar.setStyleSheet(f"""
            QFrame#searchBarFrame {{
                background-color: {p["SEARCH_BG"]};
                border-bottom: 1px solid {p["BORDER_STANDARD"]};
                padding: 4px 12px;
            }}
        """)
        self.lbl_search_title.setStyleSheet(f"font-weight: 600; color: {p['TEXT_PRIMARY']}; font-size: 13px;")

        # 검색 바 버튼 스타일
        btn_search_style = f"""
            QPushButton {{
                background-color: transparent;
                border: 1px solid transparent;
                border-radius: 5px;
                padding: 2px;
            }}
            QPushButton:hover {{
                background-color: {p["ITEM_HOVER"]};
                border-color: {p["BORDER_SUBTLE"]};
            }}
            QPushButton:disabled {{
                background-color: transparent;
                border-color: transparent;
            }}
        """
        self.btn_search_prev.setStyleSheet(btn_search_style)
        self.btn_search_next.setStyleSheet(btn_search_style)
        self.btn_search_close.setStyleSheet(btn_search_style)

        # 페이지 이동 버튼 스타일
        btn_page_style = f"""
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
        """
        self.btn_prev_page.setStyleSheet(btn_page_style)
        self.btn_next_page.setStyleSheet(btn_page_style)

        # 테마 토글 버튼 툴팁 및 상태 안내 갱신
        if is_dark:
            self.act_theme.setToolTip("라이트 모드로 전환 (Ctrl+T)")
            self.act_theme.setStatusTip("화면을 라이트 모드로 전환합니다 (Ctrl+T)")
        else:
            self.act_theme.setToolTip("다크 모드로 전환 (Ctrl+T)")
            self.act_theme.setStatusTip("화면을 다크 모드로 전환합니다 (Ctrl+T)")

        # 5. 사용자 환경설정 영구 저장
        AppSettings.set_theme_mode(theme_mode)

    def _update_all_icons(self):
        """현재 테마(다크/라이트)에 맞는 고해상도 벡터 SVG 아이콘 일괄 로드"""
        is_dark = (self.current_theme == AppleTheme.DARK)

        # 메인 툴바
        self.btn_main_menu.setIcon(get_icon("menu", is_dark=is_dark))
        self.act_sidebar.setIcon(get_icon("sidebar", is_dark=is_dark))
        self.act_fullscreen.setIcon(get_icon("fullscreen", is_dark=is_dark, size=18))
        self.act_open.setIcon(get_icon("open", is_dark=is_dark))
        self.act_save.setIcon(get_icon("save", is_dark=is_dark))
        self.act_remove_password.setIcon(get_icon("unlock", is_dark=is_dark))
        self.act_export_pages.setIcon(get_icon("export", is_dark=is_dark))
        self.act_print.setIcon(get_icon("print", is_dark=is_dark))
        self.btn_prev_page.setIcon(get_icon("chevron_left", is_dark=is_dark, size=15))
        self.btn_next_page.setIcon(get_icon("chevron_right", is_dark=is_dark, size=15))
        self.act_zoom_out.setIcon(get_icon("zoom_out", is_dark=is_dark))
        self.act_zoom_in.setIcon(get_icon("zoom_in", is_dark=is_dark))
        self.act_fit_width.setIcon(get_icon("fit_width", is_dark=is_dark))
        self.act_fit_page.setIcon(get_icon("fit_page", is_dark=is_dark))
        self.act_img_merge.setIcon(get_icon("images", is_dark=is_dark))
        self.act_reorder.setIcon(get_icon("reorder", is_dark=is_dark))
        self.act_find.setIcon(get_icon("search", is_dark=is_dark))

        # 테마 아이콘: 라이트 모드일 땐 달(Moon), 다크 모드일 땐 해(Sun)
        theme_icon_name = "sun" if is_dark else "moon"
        self.act_theme.setIcon(get_icon(theme_icon_name, is_dark=is_dark))

        # 편집 툴바
        self.act_mode_hand.setIcon(get_icon("hand", is_dark=is_dark))
        self.act_mode_text.setIcon(get_icon("text", is_dark=is_dark))
        self.act_mode_whiteout.setIcon(get_icon("whiteout", is_dark=is_dark))
        self.act_mode_edit_text.setIcon(get_icon("edit_text", is_dark=is_dark))
        self.act_mode_highlight.setIcon(get_icon("highlight", is_dark=is_dark))
        self.act_mode_pen.setIcon(get_icon("pen", is_dark=is_dark))
        self.act_undo.setIcon(get_icon("undo", is_dark=is_dark))

        # 검색 바 컨트롤
        self.btn_search_prev.setIcon(get_icon("chevron_up", is_dark=is_dark, size=14))
        self.btn_search_next.setIcon(get_icon("chevron_down", is_dark=is_dark, size=14))
        self.btn_search_close.setIcon(get_icon("close", is_dark=is_dark, size=14))

    # ==================== 문서 제어 및 편집 ====================

    def _set_edit_mode(self, mode: EditMode, mode_name: str):
        self.viewer.set_mode(mode)

    def _on_undo(self):
        if self.pdf_engine.undo():
            self.viewer.render_all_pages()
            self.thumbnail_widget.load_thumbnails(self.pdf_engine)
            self.act_undo.setEnabled(self.pdf_engine.can_undo)
            self.status_bar.showMessage("실행 취소되었습니다.", 3000)

    def _on_document_modified(self):
        self.thumbnail_widget.load_thumbnails(self.pdf_engine)
        self.act_undo.setEnabled(self.pdf_engine.can_undo)
        self.status_bar.showMessage("문서가 편집되었습니다. [Ctrl+S]로 저장할 수 있습니다.", 4000)

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
                    return

            self.viewer.set_engine(self.pdf_engine)
            self.thumbnail_widget.load_thumbnails(self.pdf_engine)
            self._update_title()
            self._update_security_status()
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

            if self.pdf_engine.was_encrypted:
                self.status_bar.showMessage("암호가 인증되어 문서가 열렸습니다. ☰ 메뉴의 [비밀번호 해제 후 저장]으로 암호를 영구 제거할 수 있습니다.", 6000)
        except Exception as e:
            QMessageBox.critical(self, "열기 오류", f"PDF 파일을 여는 중 오류가 발생했습니다:\n{str(e)}")

    def _update_security_status(self):
        """현재 문서의 암호화 상태를 확인하고 UI 요소를 갱신"""
        if self.pdf_engine.is_loaded() and self.pdf_engine.was_encrypted:
            self.act_remove_password.setEnabled(True)
            self.act_remove_password.setVisible(True)
        else:
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
                self.status_bar.showMessage("비밀번호가 완전히 해제되어 저장되었습니다.", 5000)
                QMessageBox.information(
                    self,
                    "비밀번호 해제 완료",
                    "현재 파일의 비밀번호가 완전히 해제되었습니다!\n이제 비밀번호 입력 없이 바로 열 수 있습니다."
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
                self.status_bar.showMessage("비밀번호가 해제된 상태로 문서가 저장되었습니다.", 4000)
            else:
                self.status_bar.showMessage("문서가 성공적으로 저장되었습니다.", 4000)
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
                    "새로 저장할 파일에서 비밀번호를 완전히 해제(제거)하시겠습니까?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Yes
                )
                if reply == QMessageBox.StandardButton.Cancel:
                    return
                remove_password = (reply == QMessageBox.StandardButton.Yes)
            else:
                remove_password = False

        init_dir = AppSettings.get_last_save_dir()
        cur_file = self.pdf_engine.file_path or "untitled.pdf"
        default_name = os.path.join(init_dir, f"수정본_{os.path.basename(cur_file)}")

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "다른 이름으로 저장",
            default_name,
            "PDF 문서 (*.pdf)"
        )
        if file_path:
            try:
                self.pdf_engine.save_as(file_path, remove_password=remove_password)
                AppSettings.set_last_save_dir(file_path)
                self._update_title()
                self._update_security_status()
                if remove_password:
                    self.status_bar.showMessage(f"비밀번호가 해제되어 저장되었습니다: {os.path.basename(file_path)}", 4000)
                else:
                    self.status_bar.showMessage(f"다른 이름으로 저장되었습니다: {os.path.basename(file_path)}", 4000)
                self.act_undo.setEnabled(self.pdf_engine.can_undo)
            except Exception as e:
                QMessageBox.critical(self, "저장 오류", f"다른 이름으로 저장 실패:\n{str(e)}")

    def open_export_dialog(self):
        """특정 페이지 추출 및 개별/이어붙인 이미지 내보내기 대화상자 실행"""
        if not self.pdf_engine.is_loaded():
            QMessageBox.information(self, "안내", "먼저 PDF 문서를 열어주세요.")
            return

        from ui.page_export_dialog import PageExportDialog  # 쓸 때만 로드 (시작 속도)
        dlg = PageExportDialog(self.pdf_engine, parent=self)
        dlg.exec()

    def print_document(self):
        if not self.pdf_engine.is_loaded():
            return
        from PySide6.QtPrintSupport import QPrinter, QPrintDialog  # 인쇄할 때만 로드
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dlg = QPrintDialog(printer, self)
        if dlg.exec() == QPrintDialog.DialogCode.Accepted:
            self._do_print(printer)

    def print_preview(self):
        if not self.pdf_engine.is_loaded():
            return
        from PySide6.QtPrintSupport import QPrinter, QPrintPreviewDialog
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        preview = QPrintPreviewDialog(printer, self)
        preview.paintRequested.connect(self._do_print)
        preview.exec()

    def _render_print_pages(self, printer):
        painter = QPainter(printer)
        for i in range(self.pdf_engine.page_count):
            if i > 0:
                printer.newPage()
            qimg = self.pdf_engine.render_page(i, zoom=2.0)
            target_rect = printer.pageLayout().paintRectPixels(printer.resolution())
            painter.drawImage(target_rect, qimg)
        painter.end()

    def _do_print(self, printer):
        self._render_print_pages(printer)

    def open_image_merge_dialog(self):
        from ui.image_merge_dialog import ImageMergeDialog
        dlg = ImageMergeDialog(parent=self)
        if dlg.exec():
            merged_pdf_path = dlg.get_output_pdf_path()
            if merged_pdf_path and os.path.exists(merged_pdf_path):
                self.load_pdf(merged_pdf_path)

    def open_page_reorder_dialog(self):
        if not self.pdf_engine.is_loaded():
            return
        from ui.page_reorder_dialog import PageReorderDialog
        dlg = PageReorderDialog(self.pdf_engine, parent=self)
        if dlg.exec():
            self.viewer.render_all_pages()
            self.thumbnail_widget.load_thumbnails(self.pdf_engine)
            self._update_title()
            self.lbl_total_page.setText(f"/ {self.pdf_engine.page_count}  ")
            self.status_bar.showMessage("페이지 순서가 업데이트되었습니다.", 4000)

    def _on_page_order_changed(self):
        self.viewer.render_all_pages()
        self._update_title()

    def _on_thumbnail_page_selected(self, page_idx: int):
        self.viewer.scroll_to_page(page_idx)

    def _on_thumbnail_rotate(self, page_idx: int, angle: int):
        if self.pdf_engine.rotate_page(page_idx, angle):
            self.viewer.render_all_pages()
            self.thumbnail_widget.load_thumbnails(self.pdf_engine)

    def _on_thumbnail_delete(self, page_idx: int):
        if self.pdf_engine.delete_page(page_idx):
            self.viewer.render_all_pages()
            self.thumbnail_widget.load_thumbnails(self.pdf_engine)
            self.lbl_total_page.setText(f"/ {self.pdf_engine.page_count}  ")

    def _on_prev_page(self):
        cur = self.viewer.current_page
        if cur > 0:
            self.viewer.scroll_to_page(cur - 1)

    def _on_next_page(self):
        cur = self.viewer.current_page
        if self.pdf_engine and cur < self.pdf_engine.page_count - 1:
            self.viewer.scroll_to_page(cur + 1)

    def _on_jump_page(self):
        try:
            target = int(self.txt_page.text().strip()) - 1
            if self.pdf_engine and 0 <= target < self.pdf_engine.page_count:
                self.viewer.scroll_to_page(target)
            else:
                self.txt_page.setText(str(self.viewer.current_page + 1))
        except ValueError:
            self.txt_page.setText(str(self.viewer.current_page + 1))

    def _on_page_changed(self, current: int, total: int):
        self.txt_page.blockSignals(True)
        self.txt_page.setText(str(current))
        self.txt_page.blockSignals(False)
        self.lbl_total_page.setText(f"/ {total}  ")
        self.thumbnail_widget.select_page(current - 1)

    def _on_zoom_changed(self, zoom: float):
        pct = int(zoom * 100)
        self.combo_zoom.blockSignals(True)
        self.combo_zoom.setCurrentText(f"{pct}%")
        self.combo_zoom.blockSignals(False)

    def _on_combo_zoom_changed(self, text: str):
        try:
            val = float(text.replace("%", "").strip()) / 100.0
            self.viewer.set_zoom(val)
        except ValueError:
            pass

    def _update_title(self):
        title = "BossPDF - 고성능 PDF 뷰어 & 편집기"
        if self.pdf_engine and self.pdf_engine.is_loaded():
            fn = os.path.basename(self.pdf_engine.file_path or "새 문서")
            sec_tag = " [암호 보호]" if self.pdf_engine.was_encrypted else ""
            title = f"{fn}{sec_tag} - BossPDF"
        self.setWindowTitle(title)

    # ==================== 문서 내 단어 검색 (Ctrl+F) ====================

    def open_search_bar(self):
        """검색 바를 표시하고 텍스트 입력 포커스"""
        self.search_bar.setVisible(True)
        self.txt_search.setFocus()
        self.txt_search.selectAll()
        if self.txt_search.text().strip():
            self._perform_search(self.txt_search.text(), reset_index=False)

    def close_search_bar(self):
        """검색 바를 숨기고 하이라이트 해제"""
        self.search_bar.setVisible(False)
        self.viewer.clear_search_highlights()
        self._update_search_status_ui(0, 0, False)

    def eventFilter(self, obj, event):
        """검색창 키 처리 + 뷰어 크기 변경 시 플로팅 바/알림 위치 갱신"""
        if obj is getattr(self, "viewer", None) and event.type() == QEvent.Type.Resize:
            QTimer.singleShot(0, self._reposition_overlays)
        if obj == self.txt_search and event.type() == QEvent.Type.KeyPress:
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
        p = AppleTheme.get_palette(self.current_theme)

        if not has_query:
            self.lbl_search_status.setText("0 / 0건")
            self.lbl_search_status.setStyleSheet(
                f"background-color: {p['SIDEBAR_BG']}; color: {p['TEXT_SECONDARY']}; font-weight: 600; padding: 4px 12px; border-radius: 6px; font-size: 12.5px;"
            )
        elif has_matches:
            self.lbl_search_status.setText(f"{current_one_based} / {total}건 ({current_one_based}번째 결과)")
            self.lbl_search_status.setStyleSheet(
                f"background-color: {p['ACCENT_TINT']}; color: {p['ACCENT_BLUE']}; font-weight: 700; padding: 4px 12px; border-radius: 6px; font-size: 12.5px;"
            )
        else:
            self.lbl_search_status.setText("0 / 0건 (검색 결과 없음)")
            is_dark = (self.current_theme == AppleTheme.DARK)
            err_bg = "#3A1A1A" if is_dark else "#FFF2F2"
            self.lbl_search_status.setStyleSheet(
                f"background-color: {err_bg}; color: {p['DANGER_RED']}; font-weight: 700; padding: 4px 12px; border-radius: 6px; font-size: 12.5px;"
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
        # 창이 먼저 닫혀도 스레드가 함께 파괴되지 않도록 부모 없이 클래스에 보관
        thread = CheckUpdateThread(current_version=__version__)
        thread.check_finished.connect(MainWindow._on_bg_update_checked)
        MainWindow._bg_update_thread = thread
        thread.start()

    @classmethod
    def _on_bg_update_checked(cls, info: UpdateInfo):
        if not (info and info.has_update):
            return
        live = [w for w in cls._windows if w.isVisible()]
        if not live:
            return
        owner = next((w for w in live if w.isActiveWindow()), live[-1])
        owner.status_bar.showMessage(f"새 버전 v{info.latest_version}이 나왔습니다.", 5000)
        from ui.update_dialog import UpdateDialog
        UpdateDialog(owner, update_info=info).exec()

    def check_for_updates_interactive(self):
        """도움말 메뉴에서 수동으로 업데이트 확인 클릭 시 실행"""
        self.status_bar.showMessage("GitHub에서 최신 버전을 확인하는 중...", 3000)
        self._manual_update_thread = CheckUpdateThread(current_version=__version__, parent=self)
        self._manual_update_thread.check_finished.connect(self._on_manual_update_checked)
        self._manual_update_thread.start()

    def _on_manual_update_checked(self, info: UpdateInfo):
        if info and info.has_update:
            from ui.update_dialog import UpdateDialog
            dlg = UpdateDialog(self, update_info=info)
            dlg.exec()
        elif info and info.error_message:
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("업데이트 확인 - BossPDF")
            msg_box.setIcon(QMessageBox.Icon.Information)
            msg_box.setText(f"<b>현재 최신 버전(v{__version__})을 사용 중입니다.</b>")
            msg_box.setInformativeText(
                f"• GitHub 저장소: {GITHUB_REPO_URL}\n" +
                f"• 상태 안내: {info.error_message}\n\n" +
                "※ GitHub Releases에 신규 버전(Setup.exe)이 등록되면 앱 시작 시 자동 감지 및 원클릭 업데이트가 지원됩니다."
            )
            msg_box.addButton("확인", QMessageBox.ButtonRole.AcceptRole)
            btn_repo = msg_box.addButton("GitHub 저장소 방문", QMessageBox.ButtonRole.ActionRole)
            msg_box.exec()
            if msg_box.clickedButton() == btn_repo:
                self.open_github_repo()
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
            "페이지 순서 재배치, 특정 페이지/이어붙이기 이미지 내보내기, 비밀번호 해제, 다크/화이트 모드, 사이드바 최소화, 자동 업데이트</p>"
        )
