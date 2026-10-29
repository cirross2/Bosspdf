"""
자동 업데이트 모듈(core.updater) 단위 테스트
"""
import pytest
from core.updater import parse_version, is_newer_version, UpdateInfo, check_github_update
from core.version import __version__


def test_parse_version():
    assert parse_version("1.0.0") == (1, 0, 0)
    assert parse_version("v1.0.1") == (1, 0, 1)
    assert parse_version("V2.3.4") == (2, 3, 4)
    assert parse_version("v1.10.2") == (1, 10, 2)


def test_is_newer_version():
    assert is_newer_version("1.0.2", "1.0.1") is True
    assert is_newer_version("v1.1.0", "1.0.1") is True
    assert is_newer_version("2.0.0", "1.9.9") is True
    assert is_newer_version("1.0.1", "1.0.1") is False
    assert is_newer_version("1.0.0", "1.0.1") is False
    assert is_newer_version("v1.0.0", "v1.0.1") is False


def test_update_info_defaults():
    info = UpdateInfo(
        has_update=True,
        current_version="1.0.1",
        latest_version="1.0.2",
        release_title="BossPDF v1.0.2 출시",
        download_url="https://github.com/cirross2/bosspdf/releases/download/v1.0.2/BossPDF_Setup_v1.0.2.exe"
    )
    assert info.has_update is True
    assert info.current_version == "1.0.1"
    assert info.latest_version == "1.0.2"
    assert "Setup" in info.download_url
