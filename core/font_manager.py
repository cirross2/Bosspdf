"""
윈도우 시스템에 설치된 전체 폰트를 초고속(0.02초)으로 스캔하고
글꼴 이름에 맞는 실제 폰트 파일(.ttf, .otf, .ttc) 경로를 매핑해주는 폰트 매니저
"""
import os
import winreg
from typing import Dict, List, Tuple, Optional
from PySide6.QtGui import QFontDatabase


class FontManager:
    """
    시스템 전체 폰트 검색 및 폰트 파일 경로 매퍼
    """
    _system_font_files: Optional[Dict[str, str]] = None
    _font_families: Optional[List[str]] = None

    # 한국어 대표 폰트와 영문 폰트 매핑 (별칭)
    KOREAN_ALIASES = {
        "맑은 고딕": "malgun gothic",
        "굴림": "gulim",
        "굴림체": "gulimche",
        "돋움": "dotum",
        "돋움체": "dotumche",
        "바탕": "batang",
        "바탕체": "batangche",
        "궁서": "gungsuh",
        "궁서체": "gungsuhche",
        "나눔고딕": "nanumgothic",
        "나눔명조": "nanummyeongjo",
        "나눔스퀘어": "nanumsquare",
        "한컴고딕": "hancom gothic",
        "한컴바탕": "hancom batang",
    }

    # 기본 우선 추천 글꼴 목록
    RECOMMENDED_FONTS = [
        "맑은 고딕", "Malgun Gothic",
        "굴림", "Gulim",
        "바탕", "Batang",
        "돋움", "Dotum",
        "Arial", "Calibri", "Segoe UI",
        "Times New Roman", "Courier New", "Consolas"
    ]

    @classmethod
    def _init_font_map(cls):
        """윈도우 레지스트리를 1회 스캔하여 폰트 이름 -> 파일 경로 매핑 테이블 구성 (약 20ms 소요)"""
        if cls._system_font_files is not None:
            return

        cls._system_font_files = {}

        win_dir = os.environ.get("WINDIR", "C:\\Windows")
        sys_font_dir = os.path.join(win_dir, "Fonts")
        user_font_dir = os.path.expanduser("~\\AppData\\Local\\Microsoft\\Windows\\Fonts")

        keys = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts")
        ]

        for root_key, sub_key in keys:
            try:
                with winreg.OpenKey(root_key, sub_key) as k:
                    num_entries = winreg.QueryInfoKey(k)[1]
                    for i in range(num_entries):
                        val_name, file_name, _ = winreg.EnumValue(k, i)
                        # 'Malgun Gothic (TrueType)' -> 'malgun gothic'
                        base_name = val_name.split(" (")[0].strip().lower()

                        # 파일의 절대 경로 확인
                        if os.path.isabs(file_name):
                            full_path = file_name
                        else:
                            sys_path = os.path.join(sys_font_dir, file_name)
                            user_path = os.path.join(user_font_dir, file_name)
                            if os.path.exists(sys_path):
                                full_path = sys_path
                            elif os.path.exists(user_path):
                                full_path = user_path
                            else:
                                full_path = sys_path

                        if os.path.exists(full_path):
                            # 여러 이름이 합쳐진 경우 처리 (예: 'gulim & gulimche & dotum')
                            for sub in base_name.split(" & "):
                                clean_sub = sub.strip()
                                if clean_sub:
                                    cls._system_font_files[clean_sub] = full_path
            except Exception:
                pass

    @classmethod
    def get_all_font_families(cls) -> List[str]:
        """
        시스템에 설치된 모든 폰트 패밀리 목록 반환
        자주 쓰는 추천 폰트를 상단에 배치하고, 나머지는 알파벳/가나다 순으로 정렬
        """
        if cls._font_families is not None:
            return cls._font_families

        raw_families = QFontDatabase.families()
        seen = set()
        top_list = []
        rest_list = []

        # 1. 추천 폰트 중 실제 설치된 것 우선 배치
        for rec in cls.RECOMMENDED_FONTS:
            for f in raw_families:
                if f.lower() == rec.lower() and f not in seen:
                    seen.add(f)
                    top_list.append(f)

        # 2. 나머지 전체 폰트 추가
        for f in raw_families:
            if f not in seen:
                seen.add(f)
                rest_list.append(f)

        rest_list.sort(key=lambda x: (not any(ord(c) >= 0xAC00 for c in x), x.lower()))
        cls._font_families = top_list + rest_list
        return cls._font_families

    @classmethod
    def get_font_file_path(cls, family: str, is_bold: bool = False, is_italic: bool = False) -> str:
        """
        폰트 패밀리 이름과 스타일(굵게/기울임)을 받아 실제 .ttf/.otf/.ttc 파일 절대 경로 반환
        """
        cls._init_font_map()

        fam_lower = family.strip().lower()
        # 한글 별칭 변환 (예: '맑은 고딕' -> 'malgun gothic')
        fam_en = cls.KOREAN_ALIASES.get(family.strip(), fam_lower)

        # 스타일 접미사 후보군
        style_candidates = []
        if is_bold and is_italic:
            style_candidates.extend([f"{fam_en} bold italic", f"{fam_en} bold", f"{fam_en} italic", fam_en])
        elif is_bold:
            style_candidates.extend([f"{fam_en} bold", f"{fam_en} semibold", f"{fam_en} medium", fam_en])
        elif is_italic:
            style_candidates.extend([f"{fam_en} italic", fam_en])
        else:
            style_candidates.extend([fam_en, f"{fam_en} regular"])

        # 1. 레지스트리 매핑에서 검색
        for cand in style_candidates:
            if cand in cls._system_font_files:
                return cls._system_font_files[cand]

        # 2. 부분 일치 검색
        for cand in style_candidates:
            for reg_name, path in cls._system_font_files.items():
                if cand in reg_name:
                    return path

        # 3. Windows Fonts 디렉토리 직접 파일명 검색
        win_dir = os.environ.get("WINDIR", "C:\\Windows")
        sys_font_dir = os.path.join(win_dir, "Fonts")

        direct_guesses = [
            f"{fam_en}.ttf", f"{fam_en}bd.ttf" if is_bold else "",
            f"{fam_en}.otf", f"{fam_en}.ttc"
        ]
        for g in direct_guesses:
            if g:
                p = os.path.join(sys_font_dir, g)
                if os.path.exists(p):
                    return p

        # 4. 안전한 기본값 (맑은 고딕 또는 Arial)
        fallback_malgun = os.path.join(sys_font_dir, "malgunbd.ttf" if is_bold else "malgun.ttf")
        if os.path.exists(fallback_malgun):
            return fallback_malgun

        return os.path.join(sys_font_dir, "arial.ttf")
