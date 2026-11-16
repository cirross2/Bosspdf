# [프로젝트 보고서] PDF 뷰어 및 편집기 개발 타당성 검토 및 아키텍처 제안서

- **프로젝트명**: PDF Editor & Viewer (가칭: **PDF Studio**)
- **작성일자**: 2026-09-06
- **프로젝트 경로**: `e:\코딩\PdfEditor`

---

## 1. 개요 및 요약 결론 (Executive Summary)

> **핵심 결론**: **100% 개발 가능하며, 매우 높은 완성도와 빠른 성능으로 구현 가능합니다.**

현재 사용자 시스템 환경(Windows 10/11, Python 3.10)에는 이미 GUI 프레임워크인 **PyQt6 / PySide6**, 초고속 PDF 구조 제어기 **pikepdf**, 문서 생성기 **reportlab**, 온디바이스 AI 기반 **RapidOCR**까지 이미 설치되어 있습니다.

여기에 PDF 렌더링 및 주석/편집의 세계 표준급 오픈소스 엔진인 **PyMuPDF (Fitz)** (또는 PySide6 내장 `QtPdf`)를 결합하면, **어도비 아크로뱃(Adobe Acrobat)이나 알PDF 수준의 핵심 기능(고속 뷰어 + 페이지 편집 + 주석/서명/하이라이트 + 텍스트 검색 및 워터마크)**을 갖춘 독립 실행형(.exe) 데스크톱 애플리케이션을 성공적으로 개발할 수 있습니다.

---

## 2. 세부 기능별 구현 가능성 (Feasibility Analysis)

PDF는 본래 "인쇄 규격 고정 포맷"이므로 일반 워드프로세서(Word, 한글)와 문서 구조가 다릅니다. 따라서 기능을 **뷰어**, **페이지 편집**, **주석/마크업**, **내용 편집/보안**의 4가지 핵심 영역으로 분류하여 실현 가능성을 평가하였습니다.

| 분류 | 세부 기능 | 구현 난이도 | 실현 가능성 | 사용 기술 / 핵심 라이브러리 |
| :--- | :--- | :---: | :---: | :--- |
| **뷰어 (Viewer)** | 초고속 PDF 렌더링 (단일/연속 스크롤) | 보통 | **100% 가능** | `PyMuPDF` (pixmap 변환) 또는 `PySide6.QtPdfWidgets` |
| | 확대/축소 (Zoom In/Out), 회전 (90도) | 쉬움 | **100% 가능** | Qt QGraphicsView / Matrix 변환 |
| | 썸네일(미리보기) 사이드바 & 페이지 점프 | 보통 | **100% 가능** | QListWidget + 백그라운드 스레드 썸네일 생성 |
| | 북마크(목차 TOC) 트리 네비게이션 | 보통 | **100% 가능** | `doc.get_toc()` + QTreeWidget |
| | 본문 텍스트 실시간 검색 & 일치 항목 이동 | 보통 | **100% 가능** | `page.search_for(keyword)` |
| **페이지 편집 & 변환** | **다중 이미지 -> 단일 PDF 순서별 즉시 변환/합치기** | 쉬움 | **100% 가능 (초고속)** | `PyMuPDF` / `Pillow` (A4맞춤/원본유지/여백/순서변경) |
| | PDF 합치기 (Merge), 나누기 (Split) | 쉬움 | **100% 가능** | `pikepdf` / `PyMuPDF` |
| | 페이지 순서 드래그 앤 드롭 변경 | 보통 | **100% 가능** | QListWidget Drag & Drop + `doc.move_page()` |
| | 특정 페이지 회전, 삭제, 빈 페이지 삽입 | 쉬움 | **100% 가능** | `doc.delete_page()`, `doc.new_page()` |
| | 특정 페이지만 새 PDF로 추출 (Extract) | 쉬움 | **100% 가능** | `doc.extract_pages()` |
| **주석 및 마크업** | 형광펜(하이라이트), 밑줄, 취소선 | 보통 | **100% 가능** | `page.add_highlight_annot()` (표준 호환) |
| | 텍스트 메모/포스트잇 추가 | 보통 | **100% 가능** | `page.add_text_annot()` |
| | 자유형 펜(손글씨) 드로잉, 형상(사각형/원/화살표) | 보통 | **100% 가능** | `page.add_ink_annot()`, `page.add_rect_annot()` |
| | 도장(Stamp) 및 전자 서명 이미지 삽입 | 보통 | **100% 가능** | `page.insert_image()` |
| **고급 기능** | 텍스트 상자(직접 글자 입력) 추가 | 보통 | **100% 가능** | `page.insert_textbox()` |
| | 워터마크(텍스트/이미지) 일괄 추가 | 쉬움 | **100% 가능** | PyMuPDF 일괄 오버레이 |
| | 비밀번호 설정 및 권한 암호화/해제 | 쉬움 | **100% 가능** | `pikepdf` (기존 PdfUnlocker 경험 적용) |
| | 민감 정보 영구 가리기(블랙마킹/Redaction) | 보통 | **100% 가능** | `page.add_redact_annot()` + `apply_redactions()` |
| | 스캔된 이미지 PDF에서 글자 추출 (OCR) | 보통 | **100% 가능** | 현재 설치된 `rapidocr-onnxruntime` 연동 |

---

## 3. 추천 아키텍처 및 기술 스택

- **GUI Framework**: **PySide6** 또는 **PyQt6** (모던 윈도우 UI, Fluent 다크/라이트 테마)
- **PDF Core Engine**: **PyMuPDF (`pymupdf`)** + **pikepdf**
  - PyMuPDF: C/C++ 기반 세계 최고속 MuPDF 렌더러 + 주석/서명/수정 표준 지원
  - pikepdf: 무손실 초고속 문서 구조 병합, 메타데이터 처리, 암호화 처리
- **배포 방식**: **PyInstaller**를 통한 단일 `.exe` 패키징 (파이썬 미설치 PC에서도 즉시 실행)

---

## 4. 추천 디렉토리 구조

```
e:\코딩\PdfEditor\
├── run.py                 # 프로그램 실행 진입점
├── requirements.txt       # 의존성 패키지 목록
├── README.md              # 프로젝트 안내서
├── PDF_Editor_Viewer_Feasibility_Report.md  # 타당성 보고서 (본 문서)
├── core\                  # 백엔드 엔진
│   ├── pdf_engine.py      # PyMuPDF/pikepdf 기반 문서 로드, 렌더링, 저장
│   ├── page_manager.py    # 회전, 삭제, 분할, 병합, 재정렬
│   └── annot_manager.py   # 주석, 하이라이트, 그리기, 텍스트 상자
├── ui\                    # 화면 UI 모듈
│   ├── main_window.py     # 메인 윈도우 (메뉴, 툴바, 독패널)
│   ├── viewer_widget.py   # 부드러운 스크롤/줌/뷰 캔버스
│   ├── thumbnail_view.py  # 드래그 앤 드롭 가능한 썸네일 패널
│   ├── search_bar.py      # 실시간 단어 검색 위젯
│   └── dialogs\           # 병합/분할/암호설정 대화상자
└── resources\             # 아이콘 및 스타일시트(QSS)
```

---

## 5. 단계별 개발 로드맵 (Roadmap)

1. **Phase 1: 고속 뷰어 및 네비게이션 (기본 완성)**
   - 메인 화면 구성 (메뉴바, 툴바, 상태바, 다크/라이트 테마)
   - PDF 고화질 고속 렌더링 및 줌/팬/연속 스크롤
   - 좌측 썸네일 미리보기 바 & 북마크 목차 트리
   - 단축키 및 페이지 이동 컨트롤

2. **Phase 2: 페이지 편집 도구**
   - 페이지 회전(시계/반시계 90도) 및 삭제
   - 썸네일 드래그 앤 드롭으로 페이지 순서 바꾸기
   - PDF 병합(Merge) 및 분할(Split), 페이지 추출

3. **Phase 3: 주석, 서명 및 마크업 편집기**
   - 본문 텍스트 선택 후 형광펜(하이라이트), 밑줄
   - 자유형 펜(손글씨/서명) 드로잉
   - 텍스트 상자 삽입 및 서명 이미지(도장) 추가
   - 표준 PDF 규격으로 완벽 저장

4. **Phase 4: 부가기능 및 .exe 빌드**
   - 텍스트 실시간 검색(Ctrl+F)
   - 워터마크 추가, 비밀번호 보호
   - PyInstaller 단일 실행파일(.exe) 생성
