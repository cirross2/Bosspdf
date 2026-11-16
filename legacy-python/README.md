# PDF Studio (PDF 뷰어 및 편집기)

초고속 렌더링, 페이지 조작(병합/분할/회전/순서변경), 주석 및 마크업(형광펜/서명/메모/그리기)을 지원하는 올인원 데스크톱 PDF 뷰어 & 편집 프로그램입니다.

## 📁 디렉토리 구성
- `PDF_Editor_Viewer_Feasibility_Report.md`: 프로젝트 개발 타당성 및 기능별 분석 보고서
- `core/`: PDF 렌더링 및 편집 백엔드 로직
- `ui/`: PyQt/PySide 기반 모던 데스크톱 사용자 인터페이스
- `resources/`: 테마 스타일시트(QSS) 및 아이콘 리소스

## 🛠️ 기술 스택
- **Language**: Python 3.10+
- **GUI Framework**: PySide6 / PyQt6
- **PDF Engine**: PyMuPDF (Fitz), pikepdf
- **Packaging**: PyInstaller (.exe 빌드)
