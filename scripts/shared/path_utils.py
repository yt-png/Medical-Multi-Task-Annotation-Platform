"""
路径工具（Day1 最终冻结版）

职责：
- 所有协议路径必须是相对路径
- 必须使用 POSIX /
- 禁止绝对路径
- 禁止 URL
- 禁止 Windows 反斜杠
- 禁止 .. 路径穿越
"""

from pathlib import PurePosixPath


def is_relative_posix_path(path: str) -> bool:
    if not isinstance(path, str) or path == "":
        return False

    if "\\" in path:
        return False

    if "://" in path:
        return False

    if path.startswith("/"):
        return False

    parts = PurePosixPath(path).parts
    if ".." in parts:
        return False

    return True


def normalize_posix_path(*parts: str) -> str:
    return str(PurePosixPath(*parts))


def validate_relative_path(path: str, field_name: str = "path") -> None:
    if not is_relative_posix_path(path):
        raise ValueError(f"{field_name} 必须是相对 POSIX 路径，且不得包含 .. / 绝对路径 / URL / Windows 反斜杠: {path}")


def ensure_no_trailing_slash(path: str) -> str:
    return path.rstrip("/")