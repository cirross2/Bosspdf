"""
GitHub Releases 기반 BossPDF 자동 업데이트 모듈
"""
import os
import sys
import re
import tempfile
import urllib.request
import urllib.error
import json
import subprocess
from dataclasses import dataclass
from typing import Optional, Tuple
from PySide6.QtCore import QThread, Signal

from core.version import __version__, GITHUB_OWNER, GITHUB_REPO


@dataclass
class UpdateInfo:
    has_update: bool
    current_version: str
    latest_version: str
    release_title: str = ""
    release_notes: str = ""
    download_url: str = ""
    file_name: str = ""
    file_size: int = 0
    published_at: str = ""
    error_message: Optional[str] = None


def parse_version(ver_str: str) -> Tuple[int, ...]:
    """버전 문자열에서 숫자 튜플을 추출 (예: 'v1.0.1' -> (1, 0, 1))"""
    cleaned = re.sub(r"^[vV]", "", ver_str.strip())
    nums = []
    for part in cleaned.split("."):
        try:
            nums.append(int(part))
        except ValueError:
            # 1.0.0-rc1 등의 경우 숫자만 추출
            digits = re.findall(r"\d+", part)
            if digits:
                nums.append(int(digits[0]))
            else:
                nums.append(0)
    return tuple(nums) if nums else (0, 0, 0)


def is_newer_version(latest: str, current: str) -> bool:
    """latest가 current보다 높은 버전인지 비교"""
    return parse_version(latest) > parse_version(current)


def check_github_update(
    current_version: str = __version__,
    owner: str = GITHUB_OWNER,
    repo: str = GITHUB_REPO,
    timeout: int = 6
) -> UpdateInfo:
    """GitHub API를 통해 최신 릴리스 정보 확인"""
    api_url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
    req = urllib.request.Request(
        api_url,
        headers={
            "User-Agent": f"BossPDF-App/{current_version}",
            "Accept": "application/vnd.github.v3+json"
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.status != 200:
                return UpdateInfo(
                    has_update=False,
                    current_version=current_version,
                    latest_version=current_version,
                    error_message=f"GitHub 서버 응답 오류 ({response.status})"
                )
            data = json.loads(response.read().decode("utf-8"))

        tag_name = data.get("tag_name", "").strip()
        latest_ver = re.sub(r"^[vV]", "", tag_name)
        has_update = is_newer_version(latest_ver, current_version)

        # 첨부된 자산(Assets) 중 Setup.exe 검색
        download_url = ""
        file_name = ""
        file_size = 0

        for asset in data.get("assets", []):
            name = asset.get("name", "")
            if name.lower().endswith(".exe") and ("setup" in name.lower() or "bosspdf" in name.lower()):
                download_url = asset.get("browser_download_url", "")
                file_name = name
                file_size = asset.get("size", 0)
                break

        # setup exe가 없으면 첫 번째 exe 또는 zip 탐색
        if not download_url:
            for asset in data.get("assets", []):
                name = asset.get("name", "")
                if name.lower().endswith(".exe") or name.lower().endswith(".zip"):
                    download_url = asset.get("browser_download_url", "")
                    file_name = name
                    file_size = asset.get("size", 0)
                    break

        return UpdateInfo(
            has_update=has_update,
            current_version=current_version,
            latest_version=latest_ver,
            release_title=data.get("name", tag_name),
            release_notes=data.get("body", ""),
            download_url=download_url,
            file_name=file_name,
            file_size=file_size,
            published_at=data.get("published_at", "")[:10]
        )

    except urllib.error.HTTPError as e:
        if e.code == 404:
            return UpdateInfo(
                has_update=False,
                current_version=current_version,
                latest_version=current_version,
                error_message="GitHub 저장소에 발행된 Release(릴리스)가 없거나 저장소가 비공개(Private) 상태입니다."
            )
        return UpdateInfo(
            has_update=False,
            current_version=current_version,
            latest_version=current_version,
            error_message=f"HTTP 요청 실패: {e.code}"
        )
    except Exception as e:
        return UpdateInfo(
            has_update=False,
            current_version=current_version,
            latest_version=current_version,
            error_message=str(e)
        )


class CheckUpdateThread(QThread):
    """비동기 업데이트 확인 스레드"""
    check_finished = Signal(object)  # UpdateInfo

    def __init__(self, current_version: str = __version__, parent=None):
        super().__init__(parent)
        self.current_version = current_version

    def run(self):
        info = check_github_update(self.current_version)
        self.check_finished.emit(info)


class DownloadUpdateThread(QThread):
    """설치 파일 다운로드 스레드"""
    progress = Signal(int, int, int)  # (downloaded_bytes, total_bytes, percent)
    download_finished = Signal(str)    # destination_path
    download_error = Signal(str)       # error_message

    def __init__(self, download_url: str, file_name: str, parent=None):
        super().__init__(parent)
        self.download_url = download_url
        self.file_name = file_name
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        if not self.download_url:
            self.download_error.emit("다운로드 URL이 지정되지 않았습니다.")
            return

        try:
            temp_dir = tempfile.gettempdir()
            dest_path = os.path.join(temp_dir, self.file_name or "BossPDF_Setup_Latest.exe")

            req = urllib.request.Request(
                self.download_url,
                headers={"User-Agent": f"BossPDF-App/{__version__}"}
            )

            with urllib.request.urlopen(req, timeout=30) as resp:
                total_size = int(resp.headers.get("content-length", 0))
                downloaded = 0
                chunk_size = 64 * 1024

                with open(dest_path, "wb") as f:
                    while True:
                        if self._is_cancelled:
                            f.close()
                            if os.path.exists(dest_path):
                                os.remove(dest_path)
                            return

                        chunk = resp.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)

                        pct = int((downloaded / total_size) * 100) if total_size > 0 else 0
                        self.progress.emit(downloaded, total_size, pct)

            self.download_finished.emit(dest_path)

        except Exception as e:
            self.download_error.emit(f"다운로드 중 오류 발생: {str(e)}")


def launch_installer_and_exit(installer_path: str, silent: bool = False):
    """다운로드된 설치 파일을 실행하고 현재 앱을 종료"""
    if not os.path.exists(installer_path):
        return False

    args = [installer_path]
    if silent:
        args.append("/SILENT")

    subprocess.Popen(args, close_fds=True)
    return True
