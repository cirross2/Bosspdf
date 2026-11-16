"""
탐색기에서 여러 파일을 선택해 마우스 우클릭 시
동시에 여러 프로세스로 실행되는 인자들을 단일 창으로 안전하게 취합하는
윈도우 네이티브 뮤텍스(Named Mutex) & 큐 매니저

채널(channel)별로 뮤텍스와 큐 파일을 따로 씁니다.
- "images": 이미지 → PDF 병합 (--merge-images)
- "pdfs":   PDF 여러 개 합치기 (--merge-pdfs)
"""
import os
import time
import tempfile
import ctypes
from typing import List, Tuple, Any

MUTEX_NAME = "BossPDF_ImageMerge_Mutex"
QUEUE_FILE = os.path.join(tempfile.gettempdir(), "bosspdf_merge_queue.txt")
ERROR_ALREADY_EXISTS = 183

CHANNEL_IMAGES = "images"
CHANNEL_PDFS = "pdfs"


def _channel_names(channel: str) -> Tuple[str, str]:
    """(뮤텍스 이름, 큐 파일 경로). 이미지 채널은 이전 버전과 같은 이름을 유지"""
    if channel == CHANNEL_IMAGES:
        return MUTEX_NAME, QUEUE_FILE
    return (
        f"BossPDF_Merge_{channel}_Mutex",
        os.path.join(tempfile.gettempdir(), f"bosspdf_merge_queue_{channel}.txt"),
    )


def drain_queue(channel: str = CHANNEL_IMAGES) -> List[str]:
    """큐 파일에 쌓인 경로를 모두 꺼내고 큐를 비웁니다. (없으면 빈 목록)"""
    _, queue_file = _channel_names(channel)
    if not os.path.exists(queue_file):
        return []
    # 다른 프로세스가 쓰는 도중일 수 있으므로, 이름을 바꿔 가져온 뒤 읽는다
    grabbed = f"{queue_file}.{os.getpid()}.reading"
    for attempt in range(10):
        try:
            os.replace(queue_file, grabbed)
            break
        except FileNotFoundError:
            return []
        except OSError:
            time.sleep(0.02)  # 다른 프로세스가 쓰는 중 → 잠깐 뒤 재시도
    else:
        return []
    files: List[str] = []
    try:
        with open(grabbed, "r", encoding="utf-8") as f:
            for line in f:
                path = line.strip()
                if path and os.path.exists(path) and path not in files:
                    files.append(path)
    except Exception:
        pass
    try:
        os.remove(grabbed)
    except OSError:
        pass
    return files


def handle_merge_cli(files_in: List[str], channel: str = CHANNEL_IMAGES) -> Tuple[bool, List[str], Any]:
    """
    --merge-images / --merge-pdfs 호출 시 실행:
    1. 파일 경로를 공유 큐 파일에 추가
    2. 본 프로세스가 Primary(주 실행창)인지 Secondary(보조)인지 확인
    3. Secondary라면 (True, [], None) 반환 (해당 프로세스는 즉시 종료)
    4. Primary라면 (False, 취합된_파일목록, mutex_handle) 반환
    """
    mutex_name, queue_file = _channel_names(channel)

    # 1. 큐 파일에 파일 추가 (여러 프로세스가 동시 접근할 수 있으므로 짧은 재시도 처리)
    for _ in range(10):
        try:
            with open(queue_file, "a", encoding="utf-8") as f:
                for path in files_in:
                    if os.path.exists(path):
                        f.write(os.path.abspath(path) + "\n")
            break
        except IOError:
            time.sleep(0.02)

    # 2. Windows Named Mutex 생성/획득 시도
    mutex = ctypes.windll.kernel32.CreateMutexW(None, True, mutex_name)
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
        if os.path.exists(queue_file):
            try:
                with open(queue_file, "r", encoding="utf-8") as f:
                    curr_count = len([line for line in f if line.strip()])
                if curr_count == prev_count and curr_count > 0:
                    time.sleep(0.08)
                    break
                prev_count = curr_count
            except IOError:
                pass

    # 4. 전체 파일 목록 취합 및 큐 비우기
    return False, drain_queue(channel), mutex


def release_merge_mutex(mutex):
    """뮤텍스 해제"""
    if mutex:
        try:
            ctypes.windll.kernel32.ReleaseMutex(mutex)
            ctypes.windll.kernel32.CloseHandle(mutex)
        except Exception:
            pass
