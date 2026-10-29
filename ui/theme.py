"""
Apple macOS 네이티브 스타일(Human Interface Guidelines 감성) 디자인 시스템 및 QSS 테마 모듈
라이트 모드(White)와 다크 모드(Dark) 완벽 지원
"""
from typing import Dict, Any


class AppleTheme:
    DARK = "dark"
    LIGHT = "light"

    # Fonts
    FONT_FAMILY = '-apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", "Apple SD Gothic Neo", "Malgun Gothic", sans-serif'

    # Color Palettes
    PALETTES: Dict[str, Dict[str, str]] = {
        LIGHT: {
            "WINDOW_BG": "#F5F5F7",
            "SIDEBAR_BG": "#F2F2F7",
            "CARD_BG": "#FFFFFF",
            "CANVAS_BG": "#383B40",          # macOS 미리보기 감성의 차분한 그레이 캔버스
            "POPUP_BG": "#FFFFFF",
            "INPUT_BG": "#FFFFFF",
            "TOOLBAR_BG": "#F5F5F7",
            "SEARCH_BG": "#FFFFFF",

            "TEXT_PRIMARY": "#1D1D1F",
            "TEXT_SECONDARY": "#86868B",
            "TEXT_TERTIARY": "#AEAEB2",

            "ACCENT_BLUE": "#007AFF",        # Apple System Blue
            "ACCENT_BLUE_HOVER": "#0062CC",
            "ACCENT_BLUE_PRESSED": "#0051A8",
            "ACCENT_TINT": "#EBF3FF",

            "BORDER_SUBTLE": "#E5E5EA",
            "BORDER_STANDARD": "#D1D1D6",
            "BORDER_DARK": "#AEAEB2",

            "DANGER_RED": "#FF3B30",
            "SUCCESS_GREEN": "#34C759",
            "WARNING_ORANGE": "#FF9500",

            "SCROLLBAR_HANDLE": "rgba(0, 0, 0, 0.2)",
            "SCROLLBAR_HOVER": "rgba(0, 0, 0, 0.35)",
            "ITEM_HOVER": "rgba(0, 0, 0, 0.04)",
            "ITEM_PRESSED": "rgba(0, 0, 0, 0.08)",
        },
        DARK: {
            "WINDOW_BG": "#1C1C1E",
            "SIDEBAR_BG": "#161618",
            "CARD_BG": "#2C2C2E",
            "CANVAS_BG": "#121214",          # 다크모드 전용 딥 블랙 캔버스
            "POPUP_BG": "#252528",
            "INPUT_BG": "#2C2C2E",
            "TOOLBAR_BG": "#1C1C1E",
            "SEARCH_BG": "#242426",

            "TEXT_PRIMARY": "#FFFFFF",
            "TEXT_SECONDARY": "#8E8E93",
            "TEXT_TERTIARY": "#636366",

            "ACCENT_BLUE": "#2997FF",        # Apple Dark System Blue
            "ACCENT_BLUE_HOVER": "#0077ED",
            "ACCENT_BLUE_PRESSED": "#005FB8",
            "ACCENT_TINT": "rgba(41, 151, 255, 0.22)",

            "BORDER_SUBTLE": "#2C2C2E",
            "BORDER_STANDARD": "#3A3A3C",
            "BORDER_DARK": "#48484A",

            "DANGER_RED": "#FF453A",
            "SUCCESS_GREEN": "#32D74B",
            "WARNING_ORANGE": "#FF9F0A",

            "SCROLLBAR_HANDLE": "rgba(255, 255, 255, 0.22)",
            "SCROLLBAR_HOVER": "rgba(255, 255, 255, 0.38)",
            "ITEM_HOVER": "rgba(255, 255, 255, 0.06)",
            "ITEM_PRESSED": "rgba(255, 255, 255, 0.12)",
        }
    }

    # Backward compatibility defaults (Light)
    WINDOW_BG = PALETTES[LIGHT]["WINDOW_BG"]
    SIDEBAR_BG = PALETTES[LIGHT]["SIDEBAR_BG"]
    CARD_BG = PALETTES[LIGHT]["CARD_BG"]
    CANVAS_BG = PALETTES[LIGHT]["CANVAS_BG"]
    TEXT_PRIMARY = PALETTES[LIGHT]["TEXT_PRIMARY"]
    TEXT_SECONDARY = PALETTES[LIGHT]["TEXT_SECONDARY"]
    TEXT_TERTIARY = PALETTES[LIGHT]["TEXT_TERTIARY"]
    ACCENT_BLUE = PALETTES[LIGHT]["ACCENT_BLUE"]
    ACCENT_BLUE_HOVER = PALETTES[LIGHT]["ACCENT_BLUE_HOVER"]
    ACCENT_BLUE_PRESSED = PALETTES[LIGHT]["ACCENT_BLUE_PRESSED"]
    ACCENT_TINT = PALETTES[LIGHT]["ACCENT_TINT"]
    BORDER_SUBTLE = PALETTES[LIGHT]["BORDER_SUBTLE"]
    BORDER_STANDARD = PALETTES[LIGHT]["BORDER_STANDARD"]
    BORDER_DARK = PALETTES[LIGHT]["BORDER_DARK"]
    DANGER_RED = PALETTES[LIGHT]["DANGER_RED"]
    SUCCESS_GREEN = PALETTES[LIGHT]["SUCCESS_GREEN"]
    WARNING_ORANGE = PALETTES[LIGHT]["WARNING_ORANGE"]

    @classmethod
    def get_palette(cls, theme_mode: str = LIGHT) -> Dict[str, str]:
        mode = theme_mode.lower() if theme_mode and theme_mode.lower() in cls.PALETTES else cls.LIGHT
        return cls.PALETTES[mode]

    @classmethod
    def get_canvas_bg(cls, theme_mode: str = LIGHT) -> str:
        return cls.get_palette(theme_mode)["CANVAS_BG"]

    @classmethod
    def get_window_bg(cls, theme_mode: str = LIGHT) -> str:
        return cls.get_palette(theme_mode)["WINDOW_BG"]

    @classmethod
    def get_sidebar_bg(cls, theme_mode: str = LIGHT) -> str:
        return cls.get_palette(theme_mode)["SIDEBAR_BG"]

    @classmethod
    def get_stylesheet(cls, theme_mode: str = LIGHT) -> str:
        """애플 네이티브 앱 감성의 통합 QSS 스타일시트 반환 (다크/라이트 지원)"""
        p = cls.get_palette(theme_mode)
        is_dark = (theme_mode == cls.DARK)

        return f"""
        /* 전역 기본 설정 */
        QWidget {{
            font-family: {cls.FONT_FAMILY};
            font-size: 13px;
            color: {p["TEXT_PRIMARY"]};
            background-color: transparent;
        }}

        QMainWindow, QDialog {{
            background-color: {p["WINDOW_BG"]};
            color: {p["TEXT_PRIMARY"]};
        }}

        /* 윈도우 메뉴바 */
        QMenuBar {{
            background-color: {p["WINDOW_BG"]};
            border-bottom: 1px solid {p["BORDER_SUBTLE"]};
            padding: 2px 6px;
            font-size: 13px;
            color: {p["TEXT_PRIMARY"]};
        }}
        QMenuBar::item {{
            background: transparent;
            padding: 4px 8px;
            border-radius: 4px;
            color: {p["TEXT_PRIMARY"]};
        }}
        QMenuBar::item:selected {{
            background-color: {p["ITEM_HOVER"]};
        }}
        QMenuBar::item:pressed {{
            background-color: {p["ITEM_PRESSED"]};
        }}

        /* 컨텍스트 및 드롭다운 메뉴 */
        QMenu {{
            background-color: {p["POPUP_BG"]};
            border: 1px solid {p["BORDER_STANDARD"]};
            border-radius: 8px;
            padding: 4px;
            color: {p["TEXT_PRIMARY"]};
        }}
        QMenu::item {{
            padding: 6px 20px 6px 12px;
            border-radius: 4px;
            color: {p["TEXT_PRIMARY"]};
        }}
        QMenu::item:selected {{
            background-color: {p["ACCENT_BLUE"]};
            color: #FFFFFF;
        }}
        QMenu::separator {{
            height: 1px;
            background: {p["BORDER_SUBTLE"]};
            margin: 4px 6px;
        }}

        /* macOS 스타일 툴바 */
        QToolBar {{
            background-color: {p["TOOLBAR_BG"]};
            border-bottom: 1px solid {p["BORDER_SUBTLE"]};
            padding: 4px 8px;
            spacing: 3px;
        }}
        QToolBar::separator {{
            width: 1px;
            background-color: {p["BORDER_STANDARD"]};
            margin: 4px 6px;
        }}

        /* 알약/아이콘 형태의 툴버튼 (Pill Buttons) */
        QToolButton {{
            background-color: transparent;
            border: 1px solid transparent;
            border-radius: 6px;
            padding: 4px 6px;
            font-size: 12px;
            color: {p["TEXT_PRIMARY"]};
        }}
        QToolButton:hover {{
            background-color: {p["ITEM_HOVER"]};
            border-color: {p["BORDER_SUBTLE"]};
        }}
        QToolButton:pressed {{
            background-color: {p["ITEM_PRESSED"]};
        }}
        QToolButton:checked {{
            background-color: {p["ACCENT_TINT"]};
            border: 1px solid {p["ACCENT_BLUE"]};
            color: {p["ACCENT_BLUE"]};
        }}
        QToolButton:disabled {{
            color: {p["TEXT_TERTIARY"]};
        }}

        /* 텍스트 입력창 (QLineEdit, QTextEdit) */
        QLineEdit, QTextEdit, QPlainTextEdit {{
            background-color: {p["INPUT_BG"]};
            border: 1px solid {p["BORDER_STANDARD"]};
            border-radius: 6px;
            padding: 5px 8px;
            color: {p["TEXT_PRIMARY"]};
            selection-background-color: {p["ACCENT_BLUE"]};
            selection-color: #FFFFFF;
        }}
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
            border: 1.5px solid {p["ACCENT_BLUE"]};
        }}

        /* 콤보박스 및 스핀박스 */
        QComboBox, QSpinBox, QDoubleSpinBox {{
            background-color: {p["INPUT_BG"]};
            border: 1px solid {p["BORDER_STANDARD"]};
            border-radius: 6px;
            padding: 4px 8px;
            min-height: 22px;
            color: {p["TEXT_PRIMARY"]};
        }}
        QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover {{
            border-color: {p["BORDER_DARK"]};
        }}
        QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
            border: 1.5px solid {p["ACCENT_BLUE"]};
        }}
        QComboBox::drop-down {{
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 20px;
            border-left: none;
        }}
        QComboBox QAbstractItemView {{
            background-color: {p["POPUP_BG"]};
            border: 1px solid {p["BORDER_STANDARD"]};
            border-radius: 6px;
            padding: 4px;
            color: {p["TEXT_PRIMARY"]};
            selection-background-color: {p["ACCENT_BLUE"]};
            selection-color: #FFFFFF;
        }}

        /* 기본 버튼 (QPushButton) */
        QPushButton {{
            background-color: {p["CARD_BG"]};
            border: 1px solid {p["BORDER_STANDARD"]};
            border-radius: 6px;
            padding: 6px 14px;
            font-size: 13px;
            color: {p["TEXT_PRIMARY"]};
        }}
        QPushButton:hover {{
            background-color: {p["ITEM_HOVER"]};
            border-color: {p["BORDER_DARK"]};
        }}
        QPushButton:pressed {{
            background-color: {p["ITEM_PRESSED"]};
        }}
        QPushButton:disabled {{
            background-color: {p["WINDOW_BG"]};
            border-color: {p["BORDER_SUBTLE"]};
            color: {p["TEXT_TERTIARY"]};
        }}

        /* 그룹 상자 (QGroupBox) */
        QGroupBox {{
            background-color: {p["CARD_BG"]};
            border: 1px solid {p["BORDER_SUBTLE"]};
            border-radius: 8px;
            margin-top: 18px;
            padding: 12px;
            font-weight: bold;
            color: {p["TEXT_PRIMARY"]};
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 12px;
            top: 2px;
            padding: 0 4px;
            background-color: transparent;
            color: {p["TEXT_SECONDARY"]};
            font-size: 12px;
        }}

        /* 체크박스 및 라디오 버튼 */
        QCheckBox, QRadioButton {{
            spacing: 6px;
            color: {p["TEXT_PRIMARY"]};
        }}
        QCheckBox::indicator, QRadioButton::indicator {{
            width: 16px;
            height: 16px;
            border-radius: 4px;
            border: 1px solid {p["BORDER_STANDARD"]};
            background-color: {p["INPUT_BG"]};
        }}
        QRadioButton::indicator {{
            border-radius: 8px;
        }}
        QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
            background-color: {p["ACCENT_BLUE"]};
            border-color: {p["ACCENT_BLUE"]};
        }}

        /* 도크 위젯 (사이드바) */
        QDockWidget {{
            background-color: {p["SIDEBAR_BG"]};
            border-right: 1px solid {p["BORDER_SUBTLE"]};
            color: {p["TEXT_PRIMARY"]};
        }}
        QDockWidget::title {{
            background-color: {p["SIDEBAR_BG"]};
            padding: 8px 10px;
            font-weight: 600;
            font-size: 12px;
            color: {p["TEXT_SECONDARY"]};
            border-bottom: 1px solid {p["BORDER_SUBTLE"]};
        }}

        /* 리스트 위젯 (QListWidget) */
        QListWidget {{
            background-color: transparent;
            border: none;
            padding: 4px;
            color: {p["TEXT_PRIMARY"]};
        }}
        QListWidget::item {{
            background-color: {p["CARD_BG"]};
            border: 1px solid {p["BORDER_SUBTLE"]};
            border-radius: 8px;
            padding: 4px;
            margin: 4px;
            color: {p["TEXT_PRIMARY"]};
        }}
        QListWidget::item:hover {{
            background-color: {p["ITEM_HOVER"]};
            border-color: {p["BORDER_STANDARD"]};
        }}
        QListWidget::item:selected {{
            background-color: {p["ACCENT_TINT"]};
            border: 2px solid {p["ACCENT_BLUE"]};
            color: {p["ACCENT_BLUE"]};
        }}

        /* 상태 표시줄 */
        QStatusBar {{
            background-color: {p["WINDOW_BG"]};
            border-top: 1px solid {p["BORDER_SUBTLE"]};
            color: {p["TEXT_SECONDARY"]};
            font-size: 12px;
            padding: 3px 8px;
        }}
        QStatusBar QLabel {{
            color: {p["TEXT_SECONDARY"]};
        }}

        /* 스크롤바 (macOS의 미니멀 라운드 스크롤바) */
        QScrollBar:vertical {{
            border: none;
            background: transparent;
            width: 9px;
            margin: 0;
        }}
        QScrollBar::handle:vertical {{
            background: {p["SCROLLBAR_HANDLE"]};
            min-height: 24px;
            border-radius: 4px;
            margin: 2px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {p["SCROLLBAR_HOVER"]};
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
            background: {p["SCROLLBAR_HANDLE"]};
            min-width: 24px;
            border-radius: 4px;
            margin: 2px;
        }}
        QScrollBar::handle:horizontal:hover {{
            background: {p["SCROLLBAR_HOVER"]};
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
            border: 1px solid {p["BORDER_SUBTLE"]};
            border-radius: 5px;
            text-align: center;
            background-color: {p["BORDER_SUBTLE"]};
            height: 10px;
            font-size: 10px;
            color: {p["TEXT_PRIMARY"]};
        }}
        QProgressBar::chunk {{
            background-color: {p["ACCENT_BLUE"]};
            border-radius: 5px;
        }}
        """

    @classmethod
    def primary_button_style(cls, theme_mode: str = LIGHT) -> str:
        """애플 스타일 강조(Primary Blue) 액션 버튼 스타일"""
        p = cls.get_palette(theme_mode)
        return f"""
            QPushButton {{
                background-color: {p["ACCENT_BLUE"]};
                color: #FFFFFF;
                font-weight: 600;
                font-size: 13px;
                border: 1px solid {p["ACCENT_BLUE"]};
                border-radius: 6px;
                padding: 6px 18px;
            }}
            QPushButton:hover {{
                background-color: {p["ACCENT_BLUE_HOVER"]};
                border-color: {p["ACCENT_BLUE_HOVER"]};
            }}
            QPushButton:pressed {{
                background-color: {p["ACCENT_BLUE_PRESSED"]};
                border-color: {p["ACCENT_BLUE_PRESSED"]};
            }}
            QPushButton:disabled {{
                background-color: {p["BORDER_STANDARD"]};
                border-color: {p["BORDER_STANDARD"]};
                color: {p["TEXT_TERTIARY"]};
            }}
        """

    @classmethod
    def secondary_button_style(cls, theme_mode: str = LIGHT) -> str:
        """애플 스타일 일반/취소(Secondary) 버튼 스타일"""
        p = cls.get_palette(theme_mode)
        return f"""
            QPushButton {{
                background-color: {p["CARD_BG"]};
                color: {p["TEXT_PRIMARY"]};
                font-weight: 500;
                font-size: 13px;
                border: 1px solid {p["BORDER_STANDARD"]};
                border-radius: 6px;
                padding: 6px 16px;
            }}
            QPushButton:hover {{
                background-color: {p["ITEM_HOVER"]};
                border-color: {p["BORDER_DARK"]};
            }}
            QPushButton:pressed {{
                background-color: {p["ITEM_PRESSED"]};
            }}
        """

    @classmethod
    def destructive_button_style(cls, theme_mode: str = LIGHT) -> str:
        """애플 스타일 삭제/경고(Destructive Red) 버튼 스타일"""
        p = cls.get_palette(theme_mode)
        is_dark = (theme_mode == cls.DARK)
        bg = "#3A1A1A" if is_dark else "#FFF2F2"
        border = "#5A2222" if is_dark else "#FFD6D6"
        return f"""
            QPushButton {{
                background-color: {bg};
                color: {p["DANGER_RED"]};
                font-weight: 600;
                font-size: 13px;
                border: 1px solid {border};
                border-radius: 6px;
                padding: 6px 14px;
            }}
            QPushButton:hover {{
                background-color: {p["DANGER_RED"]};
                color: #FFFFFF;
                border-color: {p["DANGER_RED"]};
            }}
            QPushButton:pressed {{
                background-color: #B3261E;
                border-color: #B3261E;
            }}
        """
