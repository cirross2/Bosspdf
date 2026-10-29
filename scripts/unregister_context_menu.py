import sys
import os
import winreg

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

IMAGE_EXTENSIONS = [".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tiff", ".tif"]


def _delete_key_recursive(root_key, sub_key: str):
    try:
        with winreg.OpenKey(root_key, sub_key, 0, winreg.KEY_ALL_ACCESS) as key:
            while True:
                try:
                    child_key = winreg.EnumKey(key, 0)
                    _delete_key_recursive(root_key, f"{sub_key}\\{child_key}")
                except OSError:
                    break
        winreg.DeleteKey(root_key, sub_key)
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"삭제 건너뜀: {sub_key} ({e})")


def unregister_context_menu():
    print("[BossPDF] 윈도우 우클릭 메뉴 등록 정보 삭제 중...")

    # 1. SystemFileAssociations\\image
    _delete_key_recursive(
        winreg.HKEY_CURRENT_USER,
        r"Software\Classes\SystemFileAssociations\image\shell\BossPDF.MergeToPdf"
    )

    # 2. 이미지 확장자별 키
    for ext in IMAGE_EXTENSIONS:
        _delete_key_recursive(
            winreg.HKEY_CURRENT_USER,
            f"Software\\Classes\\SystemFileAssociations\\{ext}\\shell\\BossPDF.MergeToPdf"
        )

    # 3. PDF 연결 키
    _delete_key_recursive(
        winreg.HKEY_CURRENT_USER,
        r"Software\Classes\SystemFileAssociations\.pdf\shell\BossPDF.Open"
    )

    print("✅ 윈도우 우클릭 메뉴 삭제 완료!")
    return True


if __name__ == "__main__":
    unregister_context_menu()
