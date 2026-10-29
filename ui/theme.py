"""
Apple macOS 네이티브 스타일(Human Interface Guidelines 감성) 디자인 시스템 및 QSS 테마 모듈
"""

class AppleTheme:
    # Colors
    WINDOW_BG = "#F5F5F7"
    SIDEBAR_BG = "#F2F2F7"
    CARD_BG = "#FFFFFF"
    CANVAS_BG = "#383B40"          # macOS 미리보기(Preview) 뷰어 배경

    TEXT_PRIMARY = "#1D1D1F"
    TEXT_SECONDARY = "#86868B"
    TEXT_TERTIARY = "#AEAEB2"

    ACCENT_BLUE = "#007AFF"        # Apple System Blue
    ACCENT_BLUE_HOVER = "#0062CC"
    ACCENT_BLUE_PRESSED = "#0051A8"
    ACCENT_TINT = "#EBF3FF"

    BORDER_SUBTLE = "#E5E5EA"
    BORDER_STANDARD = "#D1D1D6"
    BORDER_DARK = "#AEAEB2"

    DANGER_RED = "#FF3B30"
    SUCCESS_GREEN = "#34C759"
    WARNING_ORANGE = "#FF9500"

    # Fonts
    FONT_FAMILY = '-apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", "Apple SD Gothic Neo", "Malgun Gothic", sans-serif'

    @classmethod
    def get_stylesheet(cls) -> str:
        """애플 네이티브 앱 감성의 통합 QSS 스타일시트 반환"""
        return f"""
        /* 전역 기본 설정 */
        QWidget {{
            font-family: {cls.FONT_FAMILY};
            font-size: 13px;
            color: {cls.TEXT_PRIMARY};
            background-color: transparent;
        }}

        QMainWindow, QDialog {{
            background-color: {cls.WINDOW_BG};
        }}

        /* 윈도우 메뉴바 */
        QMenuBar {{
            background-color: {cls.WINDOW_BG};
            border-bottom: 1px solid {cls.BORDER_SUBTLE};
            padding: 2px 6px;
            font-size: 13px;
        }}
        QMenuBar::item {{
            background: transparent;
            padding: 4px 8px;
            border-radius: 4px;
        }}
        QMenuBar::item:selected {{
            background-color: rgba(0, 0, 0, 0.06);
        }}
        QMenuBar::item:pressed {{
            background-color: rgba(0, 0, 0, 0.1);
        }}

        /* 컨텍스트 및 드롭다운 메뉴 */
        QMenu {{
            background-color: #FFFFFF;
            border: 1px solid {cls.BORDER_STANDARD};
            border-radius: 8px;
            padding: 4px;
        }}
        QMenu::item {{
            padding: 6px 20px 6px 12px;
            border-radius: 4px;
        }}
        QMenu::item:selected {{
            background-color: {cls.ACCENT_BLUE};
            color: #FFFFFF;
        }}
        QMenu::separator {{
            height: 1px;
            background: {cls.BORDER_SUBTLE};
            margin: 4px 6px;
        }}

        /* macOS 스타일 툴바 (단일 통합 & 정돈된 형태) */
        QToolBar {{
            background-color: {cls.WINDOW_BG};
            border-bottom: 1px solid {cls.BORDER_SUBTLE};
            padding: 4px 8px;
            spacing: 4px;
        }}
        QToolBar::separator {{
            width: 1px;
            background-color: {cls.BORDER_STANDARD};
            margin: 4px 6px;
        }}

        /* 알약 형태의 툴버튼 (Pill Buttons & Segmented Control) */
        QToolButton {{
            background-color: transparent;
            border: 1px solid transparent;
            border-radius: 6px;
            padding: 4px 9px;
            font-size: 12px;
            color: {cls.TEXT_PRIMARY};
        }}
        QToolButton:hover {{
            background-color: rgba(0, 0, 0, 0.05);
        }}
        QToolButton:pressed {{
            background-color: rgba(0, 0, 0, 0.1);
        }}
        QToolButton:checked {{
            background-color: {cls.ACCENT_BLUE};
            color: #FFFFFF;
            font-weight: bold;
        }}
        QToolButton:disabled {{
            color: {cls.TEXT_TERTIARY};
        }}

        /* 텍스트 입력창 (QLineEdit, QTextEdit) */
        QLineEdit, QTextEdit, QPlainTextEdit {{
            background-color: #FFFFFF;
            border: 1px solid {cls.BORDER_STANDARD};
            border-radius: 6px;
            padding: 5px 8px;
            color: {cls.TEXT_PRIMARY};
            selection-background-color: {cls.ACCENT_BLUE};
            selection-color: #FFFFFF;
        }}
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
            border: 1.5px solid {cls.ACCENT_BLUE};
            background-color: #FFFFFF;
        }}

        /* 콤보박스 및 스핀박스 */
        QComboBox, QSpinBox, QDoubleSpinBox {{
            background-color: #FFFFFF;
            border: 1px solid {cls.BORDER_STANDARD};
            border-radius: 6px;
            padding: 4px 8px;
            min-height: 22px;
        }}
        QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover {{
            border-color: {cls.BORDER_DARK};
        }}
        QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
            border: 1.5px solid {cls.ACCENT_BLUE};
        }}
        QComboBox::drop-down {{
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 20px;
            border-left: none;
        }}
        QComboBox QAbstractItemView {{
            background-color: #FFFFFF;
            border: 1px solid {cls.BORDER_STANDARD};
            border-radius: 6px;
            padding: 4px;
            selection-background-color: {cls.ACCENT_BLUE};
            selection-color: #FFFFFF;
        }}

        /* 버튼 (QPushButton) */
        QPushButton {{
            background-color: #FFFFFF;
            border: 1px solid {cls.BORDER_STANDARD};
            border-radius: 6px;
            padding: 6px 14px;
            font-size: 13px;
            color: {cls.TEXT_PRIMARY};
        }}
        QPushButton:hover {{
            background-color: #F8F8F9;
            border-color: {cls.BORDER_DARK};
        }}
        QPushButton:pressed {{
            background-color: #ECECEE;
        }}
        QPushButton:disabled {{
            background-color: #F5F5F7;
            border-color: {cls.BORDER_SUBTLE};
            color: {cls.TEXT_TERTIARY};
        }}

        /* 그룹 상자 (QGroupBox) */
        QGroupBox {{
            background-color: #FFFFFF;
            border: 1px solid {cls.BORDER_SUBTLE};
            border-radius: 8px;
            margin-top: 18px;
            padding: 12px;
            font-weight: bold;
            color: {cls.TEXT_PRIMARY};
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 12px;
            top: 2px;
            padding: 0 4px;
            background-color: transparent;
            color: {cls.TEXT_SECONDARY};
            font-size: 12px;
        }}

        /* 체크박스 및 라디오 버튼 */
        QCheckBox, QRadioButton {{
            spacing: 6px;
            color: {cls.TEXT_PRIMARY};
        }}
        QCheckBox::indicator, QRadioButton::indicator {{
            width: 16px;
            height: 16px;
            border-radius: 4px;
            border: 1px solid {cls.BORDER_STANDARD};
            background-color: #FFFFFF;
        }}
        QRadioButton::indicator {{
            border-radius: 8px;
        }}
        QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
            background-color: {cls.ACCENT_BLUE};
            border-color: {cls.ACCENT_BLUE};
        }}

        /* 도크 위젯 (사이드바) */
        QDockWidget {{
            background-color: {cls.SIDEBAR_BG};
            border-right: 1px solid {cls.BORDER_SUBTLE};
        }}
        QDockWidget::title {{
            background-color: {cls.SIDEBAR_BG};
            padding: 8px 10px;
            font-weight: 600;
            font-size: 12px;
            color: {cls.TEXT_SECONDARY};
            border-bottom: 1px solid {cls.BORDER_SUBTLE};
        }}

        /* 리스트 위젯 (QListWidget) */
        QListWidget {{
            background-color: transparent;
            border: none;
            padding: 4px;
        }}
        QListWidget::item {{
            background-color: #FFFFFF;
            border: 1px solid {cls.BORDER_SUBTLE};
            border-radius: 8px;
            padding: 4px;
            margin: 4px;
        }}
        QListWidget::item:hover {{
            background-color: #FAFAFA;
            border-color: {cls.BORDER_STANDARD};
        }}
        QListWidget::item:selected {{
            background-color: {cls.ACCENT_TINT};
            border: 2px solid {cls.ACCENT_BLUE};
            color: {cls.ACCENT_BLUE};
        }}

        /* 상태 표시줄 */
        QStatusBar {{
            background-color: {cls.WINDOW_BG};
            border-top: 1px solid {cls.BORDER_SUBTLE};
            color: {cls.TEXT_SECONDARY};
            font-size: 12px;
            padding: 3px 8px;
        }}
        QStatusBar QLabel {{
            color: {cls.TEXT_SECONDARY};
        }}

        /* 스크롤바 (macOS의 미니멀 라운드 스크롤바) */
        QScrollBar:vertical {{
            border: none;
            background: transparent;
            width: 9px;
            margin: 0;
        }}
        QScrollBar::handle:vertical {{
            background: rgba(0, 0, 0, 0.2);
            min-height: 24px;
            border-radius: 4px;
            margin: 2px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: rgba(0, 0, 0, 0.35);
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
            background: none;
        }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
            background: none;
        }}

        QScrollBar:horizontal {{
            border: none;
            background: transparent;
            height: 9px;
            margin: 0;
        }}
        QScrollBar::handle:horizontal {{
            background: rgba(0, 0, 0, 0.2);
            min-width: 24px;
            border-radius: 4px;
            margin: 2px;
        }}
        QScrollBar::handle:horizontal:hover {{
            background: rgba(0, 0, 0, 0.35);
        }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            width: 0px;
            background: none;
        }}
        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
            background: none;
        }}

        /* 탭 및 프로그레스바 */
        QProgressBar {{
            border: 1px solid {cls.BORDER_SUBTLE};
            border-radius: 5px;
            text-align: center;
            background-color: #E5E5EA;
            height: 10px;
            font-size: 10px;
        }}
        QProgressBar::chunk {{
            background-color: {cls.ACCENT_BLUE};
            border-radius: 5px;
        }}
        """

    @classmethod
    def primary_button_style(cls) -> str:
        """애플 스타일 강조(Primary Blue) 액션 버튼 스타일"""
        return f"""
            QPushButton {{
                background-color: {cls.ACCENT_BLUE};
                color: #FFFFFF;
                font-weight: 600;
                font-size: 13px;
                border: 1px solid {cls.ACCENT_BLUE};
                border-radius: 6px;
                padding: 6px 18px;
            }}
            QPushButton:hover {{
                background-color: {cls.ACCENT_BLUE_HOVER};
                border-color: {cls.ACCENT_BLUE_HOVER};
            }}
            QPushButton:pressed {{
                background-color: {cls.ACCENT_BLUE_PRESSED};
                border-color: {cls.ACCENT_BLUE_PRESSED};
            }}
            QPushButton:disabled {{
                background-color: #D1D1D6;
                border-color: #D1D1D6;
                color: #FFFFFF;
            }}
        """

    @classmethod
    def secondary_button_style(cls) -> str:
        """애플 스타일 일반/취소(Secondary) 버튼 스타일"""
        return f"""
            QPushButton {{
                background-color: #FFFFFF;
                color: {cls.TEXT_PRIMARY};
                font-weight: 500;
                font-size: 13px;
                border: 1px solid {cls.BORDER_STANDARD};
                border-radius: 6px;
                padding: 6px 16px;
            }}
            QPushButton:hover {{
                background-color: #F8F8F9;
                border-color: {cls.BORDER_DARK};
            }}
            QPushButton:pressed {{
                background-color: #ECECEE;
            }}
        """

    @classmethod
    def destructive_button_style(cls) -> str:
        """애플 스타일 삭제/경고(Destructive Red) 버튼 스타일"""
        return f"""
            QPushButton {{
                background-color: #FFF2F2;
                color: {cls.DANGER_RED};
                font-weight: 600;
                font-size: 13px;
                border: 1px solid #FFD6D6;
                border-radius: 6px;
                padding: 6px 14px;
            }}
            QPushButton:hover {{
                background-color: {cls.DANGER_RED};
                color: #FFFFFF;
                border-color: {cls.DANGER_RED};
            }}
            QPushButton:pressed {{
                background-color: #D32F2F;
                border-color: #D32F2F;
            }}
        """
