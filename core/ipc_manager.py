"""
탐색기에서 여러 이미지를 선택해 마우스 우클릭 시
동시에 여러 프로세스로 실행되는 인자들을 단일 창으로 안전하게 취합하는
윈도우 네이티브 뮤텍스(Named Mutex) & 큐 매니저
"""
import os
import sys
import time
import tempfile
import ctypes
from typing import List, Tuple, Any

MUTEX_NAME = "BossPDF_ImageMerge_Mutex"
QUEUE_FILE = os.path.join(tempfile.gettempdir(), "bosspdf_merge_queue.txt")
ERROR_ALREADY_EXISTS = 183


def handle_merge_cli(image_files: List[str]) -> Tuple[bool, List[str], Any]:
    """
    --merge-images 호출 시 실행:
    1. 파일 경로를 공유 큐 파일에 추가
    2. 본 프로세스가 Primary(주 실행창)인지 Secondary(보조)인지 확인
    3. Secondary라면 (True, [], None) 반환 (해당 프로세스는 즉시 종료)
    4. Primary라면 (False, 취합된_파일목록, mutex_handle) 반환
    """
    # 1. 큐 파일에 파일 추가 (여러 프로세스가 동시 접근할 수 있으므로 짧은 재시도 처리)
    for _ in range(10):
        try:
            with open(QUEUE_FILE, "a", encoding="utf-8") as f:
                for img in image_files:
                    if os.path.exists(img):
                        f.write(os.path.abspath(img) + "\n")
            break
        except IOError:
            time.sleep(0.02)

    # 2. Windows Named Mutex 생성/획득 시도
    mutex = ctypes.windll.kernel32.CreateMutexW(None, True, MUTEX_NAME)
    err = ctypes.windll.kernel32.GetLastError()
    is_primary = (err != ERROR_ALREADY_EXISTS)

    if not is_primary:
        # 보조 프로세스는 큐에 경로를 등록했으므로 바로 종료
        ctypes.windll.kernel32.CloseHandle(mutex)
        return True, [], None

    # 3. 주(Primary) 프로세스: 다른 보조 프로세스들이 큐에 파일을 모두 쓸 때까지 대기 (디바운스)
    prev_count = -1
    for _ in range(12):
        time.sleep(0.05)
        if os.path.exists(QUEUE_FILE):
            try:
                with open(QUEUE_FILE, "r", encoding="utf-8") as f:
                    curr_count = len([line for line in f if line.strip()])
                if curr_count == prev_count and curr_count > 0:
                    time.sleep(0.08)
                    break
                prev_count = curr_count
            except IOError:
                pass

    # 4. 전체 파일 목록 취합 및 큐 파일 삭제
    all_files: List[str] = []
    if os.path.exists(QUEUE_FILE):
        try:
            with open(QUEUE_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    path = line.strip()
                    if path and os.path.exists(path) and path not in all_files:
                        all_files.append(path)
            os.remove(QUEUE_FILE)
        except Exception:
            pass

    return False, all_files, mutex


def release_merge_mutex(mutex):
    """뮤텍스 해제"""
    if mutex:
        try:
            ctypes.windll.kernel32.ReleaseMutex(mutex)
            ctypes.windll.kernel32.CloseHandle(mutex)
        except Exception:
            pass
