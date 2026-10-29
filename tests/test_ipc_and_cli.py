"""
탐색기 다중 이미지 경로 취합 및 ImageMergeDialog 사전 로드 검증
"""
import os
import sys
import subprocess
import pytest
from PySide6.QtWidgets import QApplication

from core.ipc_manager import handle_merge_cli, release_merge_mutex
from ui.image_merge_dialog import ImageMergeDialog


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_handle_merge_cli_single(tmp_path):
    """단일 실행 시 Primary 프로세스로 전체 파일 목록 반환 검증"""
    img1 = tmp_path / "img1.png"
    img2 = tmp_path / "img2.jpg"
    img1.write_bytes(b"PNG")
    img2.write_bytes(b"JPG")

    should_exit, files, mutex = handle_merge_cli([str(img1), str(img2)])
    try:
        assert should_exit is False, "Primary 프로세스는 종료되지 않아야 합니다."
        assert len(files) == 2
        assert str(img1) in files
        assert str(img2) in files
    finally:
        release_merge_mutex(mutex)


def test_handle_merge_cli_multi_process(tmp_path):
    """실제 여러 프로세스가 동시 실행되었을 때 Primary로 모두 취합되는지 검증"""
    img1 = tmp_path / "sub1.png"
    img2 = tmp_path / "sub2.jpg"
    img3 = tmp_path / "sub3.webp"
    for f in [img1, img2, img3]:
        f.write_bytes(b"DATA")

    runner_script = tmp_path / "runner.py"
    runner_script.write_text(
        "import sys, json\n"
        "from core.ipc_manager import handle_merge_cli, release_merge_mutex\n"
        "should_exit, files, mutex = handle_merge_cli(sys.argv[1:])\n"
        "if should_exit:\n"
        "    sys.exit(0)\n"
        "print('COLLECTED:' + json.dumps(files))\n"
        "release_merge_mutex(mutex)\n",
        encoding="utf-8"
    )

    env = os.environ.copy()
    env["PYTHONPATH"] = os.getcwd()

    p_main = subprocess.Popen([sys.executable, str(runner_script), str(img1)], stdout=subprocess.PIPE, text=True, env=env)
    p_sub1 = subprocess.Popen([sys.executable, str(runner_script), str(img2)], env=env)
    p_sub2 = subprocess.Popen([sys.executable, str(runner_script), str(img3)], env=env)

    out, _ = p_main.communicate()
    p_sub1.wait()
    p_sub2.wait()

    import json
    collected = []
    for line in out.splitlines():
        if line.startswith("COLLECTED:"):
            collected = json.loads(line.replace("COLLECTED:", ""))

    print(f"\n[Multi-proc Test] 취합된 파일 목록: {collected}")
    assert len(collected) == 3, f"3개 프로세스의 파일이 모두 취합되어야 합니다. (실제: {len(collected)})"
    assert str(img1) in collected
    assert str(img2) in collected
    assert str(img3) in collected


def test_image_merge_dialog_initial_files(qapp, tmp_path):
    """ImageMergeDialog에 initial_files 전달 시 다이얼로그 목록에 자동 추가되는지 검증"""
    img_a = tmp_path / "photo_a.png"
    img_b = tmp_path / "photo_b.jpg"
    img_a.write_bytes(b"PNG")
    img_b.write_bytes(b"JPG")

    dlg = ImageMergeDialog(initial_files=[str(img_a), str(img_b)])
    assert dlg.list_widget.count() == 2, f"리스트에 2개 아이템이 있어야 합니다. (실제: {dlg.list_widget.count()})"
    assert len(dlg.image_paths) == 2
    assert dlg.windowTitle() == "BossPDF - 이미지들을 PDF로 합치기"
    dlg.close()
