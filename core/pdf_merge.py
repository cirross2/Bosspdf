"""
여러 PDF 파일을 지정된 순서대로 하나의 PDF로 합치는 모듈
"""
import os
import re
from typing import Callable, Dict, List, Optional
import pymupdf as fitz  # PyMuPDF


class PdfPasswordRequired(Exception):
    """비밀번호가 없거나 틀려서 열 수 없는 PDF"""

    def __init__(self, path: str):
        super().__init__(f"비밀번호가 필요한 문서입니다: {os.path.basename(path)}")
        self.path = path


def natural_sort_key(path: str):
    """파일명 기준 자연 정렬 키 (2.pdf가 10.pdf보다 앞에 오도록)"""
    name = os.path.basename(path).lower()
    return [int(tok) if tok.isdigit() else tok for tok in re.split(r"(\d+)", name)]


def needs_password(path: str) -> bool:
    doc = fitz.open(path)
    try:
        return bool(doc.needs_pass)
    finally:
        doc.close()


def check_password(path: str, password: str) -> bool:
    doc = fitz.open(path)
    try:
        return (not doc.needs_pass) or bool(doc.authenticate(password))
    finally:
        doc.close()


def get_page_count(path: str, password: Optional[str] = None) -> Optional[int]:
    """페이지 수 반환. 암호 때문에 알 수 없으면 None"""
    doc = fitz.open(path)
    try:
        if doc.needs_pass and not (password and doc.authenticate(password)):
            return None
        return doc.page_count
    finally:
        doc.close()


def suggest_output_path(pdf_paths: List[str]) -> str:
    """첫 번째 파일 옆에 겹치지 않는 '<이름>_합본.pdf' 경로 제안"""
    first = pdf_paths[0]
    folder = os.path.dirname(os.path.abspath(first))
    stem = os.path.splitext(os.path.basename(first))[0]
    candidate = os.path.join(folder, f"{stem}_합본.pdf")
    n = 2
    while os.path.exists(candidate):
        candidate = os.path.join(folder, f"{stem}_합본({n}).pdf")
        n += 1
    return candidate


def merge_pdfs(
    pdf_paths: List[str],
    output_pdf_path: str,
    passwords: Optional[Dict[str, str]] = None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> str:
    """
    pdf_paths 순서대로 모든 페이지를 이어 붙여 output_pdf_path에 저장합니다.
    - 각 문서의 책갈피(목차)는 페이지 번호를 밀어서 그대로 유지합니다.
    - 결과는 임시 파일에 먼저 쓴 뒤 교체하므로, 실패해도 기존 파일은 손상되지 않습니다.
    """
    if not pdf_paths:
        raise ValueError("합칠 PDF 목록이 비어 있습니다.")
    passwords = passwords or {}

    out = fitz.open()
    merged_toc = []
    tmp_path = output_pdf_path + ".bosspdf_tmp"
    try:
        total = len(pdf_paths)
        for idx, path in enumerate(pdf_paths):
            src = fitz.open(path)
            try:
                if src.needs_pass:
                    pw = passwords.get(path)
                    if not pw or not src.authenticate(pw):
                        raise PdfPasswordRequired(path)
                offset = out.page_count
                out.insert_pdf(src)
                try:
                    for level, title, page in src.get_toc(simple=True):
                        merged_toc.append([level, title, page + offset if page > 0 else page])
                except Exception:
                    pass
            finally:
                src.close()
            if progress_callback:
                progress_callback(idx + 1, total)

        if merged_toc:
            try:
                out.set_toc(merged_toc)
            except Exception:
                pass  # 목차 구조가 깨진 문서가 섞여 있어도 병합 자체는 계속

        out.save(tmp_path, garbage=3, deflate=True)
    except Exception:
        out.close()
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        raise
    out.close()
    os.replace(tmp_path, output_pdf_path)
    return output_pdf_path
