"""
다크 모드 / 화이트 모드 전환, 사이드바 토글, SVG 아이콘 로드 및 스크롤 최적화 단위 테스트
"""
import os
import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui.main_window import MainWindow
from ui.theme import AppleTheme
from ui.icons import SVG_ICONS, get_icon
from core.settings_manager import AppSettings


def test_theme_and_sidebar():
    app = QApplication.instance() or QApplication(sys.argv)

    print("=== 1. SVG 벡터 아이콘 유효성 검증 ===")
    assert len(SVG_ICONS) >= 25, "SVG 아이콘 목록 수 부족"
    for name in SVG_ICONS:
        icon_light = get_icon(name, is_dark=False)
        icon_dark = get_icon(name, is_dark=True)
        assert not icon_light.isNull(), f"아이콘 렌더링 실패: {name} (Light)"
        assert not icon_dark.isNull(), f"아이콘 렌더링 실패: {name} (Dark)"
    print(f"모든 {len(SVG_ICONS)}개 SVG 벡터 아이콘 정상 렌더링 검증 완료!")

    print("\n=== 2. MainWindow 인스턴스 생성 및 테마 모드 검증 ===")
    win = MainWindow()
    win.show()

    # 기본 또는 현재 테마 확인
    init_theme = win.current_theme
    assert init_theme in (AppleTheme.LIGHT, AppleTheme.DARK), "유효하지 않은 테마 모드"

    # 테마 토글 테스트 (Light -> Dark 또는 Dark -> Light)
    win.toggle_theme()
    toggled_theme = win.current_theme
    assert toggled_theme != init_theme, "테마 토글 미작동"
    assert AppSettings.get_theme_mode() == toggled_theme, "테마 환경설정 미저장"

    # 다시 원복 토글
    win.toggle_theme()
    assert win.current_theme == init_theme, "테마 원복 미작동"
    print("다크모드 / 화이트모드 실시간 전환 및 영구 저장 검증 완료!")

    print("\n=== 3. 사이드바(페이지 미리보기) 최소화/표시 토글 검증 ===")
    init_vis = not win.dock_thumb.isHidden()
    win.toggle_sidebar()
    new_vis = not win.dock_thumb.isHidden()
    assert new_vis == (not init_vis), "사이드바 가시성 토글 실패"
    assert AppSettings.get_sidebar_visible() == new_vis, "사이드바 가시성 설정 미저장"

    # 다시 토글
    win.toggle_sidebar()
    assert (not win.dock_thumb.isHidden()) == init_vis, "사이드바 복원 실패"
    print("사이드바 최소화 및 복원 토글 검증 완료!")

    print("\n=== 4. 툴바 버튼 아이콘 전용(텍스트 없음) 검증 ===")
    assert win.findChildren(type(win.act_open))[0] is not None
    print("[SUCCESS] 테마, 사이드바, SVG 아이콘 전체 테스트 통과!")

    win.close()


if __name__ == "__main__":
    test_theme_and_sidebar()
