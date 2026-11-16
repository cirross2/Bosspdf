"""
PDF 여러 개 합치기 검증: 병합 로직, 탐색기 다중 프로세스 취합(--merge-pdfs), 대화상자
"""
import os
import sys
import json
import subprocess
import pytest
import pymupdf as fitz
from PySide6.QtWidgets import QApplication, QFileDialog

from core import pdf_merge
from core.ipc_manager import handle_merge_cli, release_merge_mutex, drain_queue, CHANNEL_PDFS


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def make_pdf(path, labels, toc=None, password=None):
    """페이지마다 labels의 글자를 적은 PDF 생성"""
    doc = fitz.open()
    for label in labels:
        page = doc.new_page()
        page.insert_text((72, 72), label)
    if toc:
        doc.set_toc(toc)
    if password:
        doc.save(str(path), encryption=fitz.PDF_ENCRYPT_AES_256, user_pw=password, owner_pw=password)
    else:
        doc.save(str(path))
    doc.close()
    return str(path)


def page_texts(path):
    doc = fitz.open(path)
    try:
        return [page.get_text().strip() for page in doc]
    finally:
        doc.close()


def test_merge_keeps_order_and_pages(tmp_path):
    a = make_pdf(tmp_path / "a.pdf", ["A1", "A2"])
    b = make_pdf(tmp_path / "b.pdf", ["B1"])
    c = make_pdf(tmp_path / "c.pdf", ["C1", "C2", "C3"])
    out = str(tmp_path / "out.pdf")
    progress = []

    pdf_merge.merge_pdfs([c, a, b], out, progress_callback=lambda cur, total: progress.append((cur, total)))

    assert page_texts(out) == ["C1", "C2", "C3", "A1", "A2", "B1"]
    assert progress == [(1, 3), (2, 3), (3, 3)]
    assert not os.path.exists(out + ".bosspdf_tmp")
    assert page_texts(a) == ["A1", "A2"], "원본은 바뀌지 않아야 합니다."


def test_merge_shifts_bookmarks(tmp_path):
    a = make_pdf(tmp_path / "a.pdf", ["A1", "A2"], toc=[[1, "A장", 2]])
    b = make_pdf(tmp_path / "b.pdf", ["B1", "B2"], toc=[[1, "B장", 1]])
    out = str(tmp_path / "out.pdf")
    pdf_merge.merge_pdfs([a, b], out)
    doc = fitz.open(out)
    try:
        assert doc.get_toc(simple=True) == [[1, "A장", 2], [1, "B장", 3]]
    finally:
        doc.close()


def test_merge_encrypted_needs_password(tmp_path):
    a = make_pdf(tmp_path / "a.pdf", ["A1"])
    locked = make_pdf(tmp_path / "locked.pdf", ["L1"], password="secret")
    out = str(tmp_path / "out.pdf")

    assert pdf_merge.needs_password(locked) and not pdf_merge.needs_password(a)
    assert pdf_merge.get_page_count(locked) is None
    assert pdf_merge.check_password(locked, "secret") and not pdf_merge.check_password(locked, "wrong")

    with pytest.raises(pdf_merge.PdfPasswordRequired):
        pdf_merge.merge_pdfs([a, locked], out)
    assert not os.path.exists(out) and not os.path.exists(out + ".bosspdf_tmp")

    pdf_merge.merge_pdfs([a, locked], out, passwords={locked: "secret"})
    assert page_texts(out) == ["A1", "L1"]
    assert not pdf_merge.needs_password(out)


def test_merge_can_overwrite_an_input(tmp_path):
    a = make_pdf(tmp_path / "a.pdf", ["A1"])
    b = make_pdf(tmp_path / "b.pdf", ["B1"])
    pdf_merge.merge_pdfs([a, b], a)
    assert page_texts(a) == ["A1", "B1"]


def test_natural_sort_and_suggested_name(tmp_path):
    names = ["10.pdf", "2.pdf", "1.pdf"]
    paths = [make_pdf(tmp_path / n, ["x"]) for n in names]
    ordered = sorted(paths, key=pdf_merge.natural_sort_key)
    assert [os.path.basename(p) for p in ordered] == ["1.pdf", "2.pdf", "10.pdf"]

    first = pdf_merge.suggest_output_path(ordered)
    assert os.path.basename(first) == "1_합본.pdf"
    open(first, "wb").close()
    assert os.path.basename(pdf_merge.suggest_output_path(ordered)) == "1_합본(2).pdf"


def test_merge_pdfs_cli_multi_process(tmp_path):
    """탐색기처럼 파일마다 프로세스가 따로 떠도 한 곳으로 모이는지 검증"""
    drain_queue(CHANNEL_PDFS)
    pdfs = [make_pdf(tmp_path / f"doc{i}.pdf", [f"D{i}"]) for i in range(6)]
    runner = tmp_path / "runner.py"
    runner.write_text(
        "import sys, json, time\n"
        "from core.ipc_manager import handle_merge_cli, release_merge_mutex, CHANNEL_PDFS\n"
        "should_exit, files, mutex = handle_merge_cli(sys.argv[1:], channel=CHANNEL_PDFS)\n"
        "if should_exit:\n"
        "    sys.exit(0)\n"
        "print('COLLECTED:' + json.dumps(files))\n"
        "release_merge_mutex(mutex)\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = os.getcwd()
    procs = [
        subprocess.Popen([sys.executable, str(runner), p], env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        for p in pdfs
    ]
    outputs = [proc.communicate(timeout=30)[0] for proc in procs]
    collected = [json.loads(o.split("COLLECTED:", 1)[1]) for o in outputs if "COLLECTED:" in o]
    leftovers = drain_queue(CHANNEL_PDFS)  # 늦게 도착한 파일은 대화상자가 큐에서 이어 받는다

    assert len(collected) >= 1
    got = {os.path.normcase(p) for group in collected for p in group} | {os.path.normcase(p) for p in leftovers}
    assert got == {os.path.normcase(p) for p in pdfs}


def test_dialog_sorts_receives_late_files_and_merges(qapp, tmp_path, monkeypatch):
    from ui.pdf_merge_dialog import PdfMergeDialog
    drain_queue(CHANNEL_PDFS)
    p10 = make_pdf(tmp_path / "10.pdf", ["ten"])
    p2 = make_pdf(tmp_path / "2.pdf", ["two"])
    p1 = make_pdf(tmp_path / "1.pdf", ["one"])
    (tmp_path / "note.txt").write_text("x")

    dlg = PdfMergeDialog(initial_files=[p10, str(tmp_path / "note.txt"), p2], queue_channel=CHANNEL_PDFS)
    assert [os.path.basename(p) for p in dlg.pdf_paths()] == ["2.pdf", "10.pdf"]
    assert dlg.btn_merge.isEnabled()

    # 대화상자가 뜬 뒤 늦게 도착한 프로세스: 보조로 판정되어 큐에만 남기고 끝난다
    should_exit, files, mutex = handle_merge_cli([p10], channel=CHANNEL_PDFS)  # 뮤텍스를 쥔 주 프로세스 역할
    drain_queue(CHANNEL_PDFS)
    try:
        late = subprocess.run(
            [sys.executable, "-c",
             "import sys; from core.ipc_manager import handle_merge_cli, CHANNEL_PDFS; "
             "print(handle_merge_cli(sys.argv[1:], channel=CHANNEL_PDFS)[0])", p1],
            env={**os.environ, "PYTHONPATH": os.getcwd()}, capture_output=True, text=True, timeout=30,
        )
        assert late.stdout.strip() == "True"
        dlg._poll_queue()
    finally:
        release_merge_mutex(mutex)
    assert [os.path.basename(p) for p in dlg.pdf_paths()] == ["2.pdf", "10.pdf", "1.pdf"]

    dlg._sort_by_name()
    assert [os.path.basename(p) for p in dlg.pdf_paths()] == ["1.pdf", "2.pdf", "10.pdf"]

    out = str(tmp_path / "merged.pdf")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (out, ""))
    dlg._on_merge()
    assert dlg.get_output_pdf_path() == out
    assert page_texts(out) == ["one", "two", "ten"]
    dlg._queue_timer.stop()
