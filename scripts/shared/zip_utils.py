"""
ZIP 工具（Day1 最终冻结版）

职责：
- 创建 task_package / result_package ZIP
- 使用 .tmp 原子写入，防止半成品 ZIP
- 安全解压 ZIP
- 校验 ZIP 完整性
- 校验 ZIP + UPLOAD_DONE.flag / .done 成对存在
- 校验 task_package.zip / result_package.zip 的真实内部结构

平台冻结规则：
1. task_package.zip 解压后根目录必须是 task_package/
2. result_package.zip 解压后根目录必须是 result_package/
3. ZIP 内所有路径必须：
   - 使用 /
   - 为相对路径
   - 不得包含 ..
   - 不得为绝对路径
   - 不得使用 Windows 反斜杠
   - 不得使用 URL
   - 不得使用 Windows 盘符
4. ZIP 内可以存在目录项，例如 task_package/images/
5. 目录项不是业务依据，业务校验以关键文件和关键目录内容为准
"""

import json
import os
import re
import shutil
import zipfile
from typing import Iterable, List

from .hash_utils import compute_sample_id_hash


_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:")


def _is_directory_member(member: str) -> bool:
    return isinstance(member, str) and member.endswith("/")


def _normalize_member_for_check(member: str) -> str:
    """
    ZIP 内目录项允许以 / 结尾。
    校验路径片段时去掉末尾 /。
    """
    return member.rstrip("/")


def _validate_zip_member_path(member: str) -> None:
    """
    校验 ZIP 内单个路径是否合法。

    注意：
    - 文件项：task_package/tasks.json
    - 目录项：task_package/images/
    二者都允许，但都必须满足安全路径规则。
    """
    if not isinstance(member, str) or member == "":
        raise ValueError("ZIP 内路径不能为空")

    if "\\" in member:
        raise ValueError(f"ZIP 内路径禁止 Windows 反斜杠: {member}")

    if member.startswith("/"):
        raise ValueError(f"ZIP 内路径禁止绝对路径: {member}")

    if "://" in member:
        raise ValueError(f"ZIP 内路径禁止 URL: {member}")

    if _WINDOWS_DRIVE_RE.match(member):
        raise ValueError(f"ZIP 内路径禁止 Windows 盘符路径: {member}")

    if member.startswith("./"):
        raise ValueError(f"ZIP 内路径禁止 ./ 前缀: {member}")

    if "//" in member:
        raise ValueError(f"ZIP 内路径禁止连续斜杠: {member}")

    normalized = _normalize_member_for_check(member)

    if normalized == "":
        raise ValueError(f"ZIP 内路径非法: {member}")

    parts = normalized.split("/")

    if "." in parts:
        raise ValueError(f"ZIP 内路径禁止 . 路径片段: {member}")

    if ".." in parts:
        raise ValueError(f"ZIP 内路径禁止 .. 路径穿越: {member}")

    if any(part == "" for part in parts):
        raise ValueError(f"ZIP 内路径存在空路径片段: {member}")


def _get_zip_names(zip_path: str) -> List[str]:
    if not zip_exists_and_valid(zip_path):
        raise ValueError(f"ZIP 不存在、为空或损坏: {zip_path}")

    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()

    if not names:
        raise ValueError(f"ZIP 内容为空: {zip_path}")

    for name in names:
        _validate_zip_member_path(name)

    return names


def _get_zip_file_names(zip_path: str) -> List[str]:
    """
    返回 ZIP 内真实文件项，排除目录项。
    """
    names = _get_zip_names(zip_path)
    return [name for name in names if not _is_directory_member(name)]

def create_zip(source_dir: str, output_zip_path: str, include_root_dir: bool = True) -> None:
    """
    原子生成 ZIP。

    默认 include_root_dir=True：
    - source_dir = ".../task_package" 时，ZIP 内部结构为 task_package/...
    - source_dir = ".../result_package" 时，ZIP 内部结构为 result_package/...

    注意：
    - 本函数只打包文件项，不强制写入空目录项。
    - detection / caption 的 masks/ 可不存在或为空，因此不依赖空目录项。
    """
    if not os.path.isdir(source_dir):
        raise FileNotFoundError(f"source_dir 不存在或不是目录: {source_dir}")

    output_dir = os.path.dirname(output_zip_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    tmp_zip_path = output_zip_path + ".tmp"

    if os.path.exists(tmp_zip_path):
        os.remove(tmp_zip_path)

    source_dir = os.path.normpath(source_dir)

    if include_root_dir:
        base_dir = os.path.dirname(source_dir)
    else:
        base_dir = source_dir

    with zipfile.ZipFile(tmp_zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(source_dir):
            for file_name in files:
                full_path = os.path.join(root, file_name)
                rel_path = os.path.relpath(full_path, base_dir).replace("\\", "/")
                _validate_zip_member_path(rel_path)

                info = zipfile.ZipInfo(rel_path)
                info.flag_bits |= 0x800  # UTF-8 filename flag

                with open(full_path, "rb") as f:
                    zf.writestr(info, f.read(), compress_type=zipfile.ZIP_DEFLATED)

    if not zip_exists_and_valid(tmp_zip_path):
        if os.path.exists(tmp_zip_path):
            os.remove(tmp_zip_path)
        raise ValueError(f"生成的临时 ZIP 不完整: {tmp_zip_path}")

    os.replace(tmp_zip_path, output_zip_path)


def zip_exists_and_valid(zip_path: str) -> bool:
    if not os.path.exists(zip_path):
        return False

    if os.path.getsize(zip_path) <= 0:
        return False

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            return zf.testzip() is None
    except Exception:
        return False


def assert_zip_has_single_root(zip_path: str, expected_root: str) -> None:
    """
    校验 ZIP 内所有文件项都位于 expected_root/ 下。

    示例：
    - task_package.zip 必须全部位于 task_package/
    - result_package.zip 必须全部位于 result_package/
    """
    if not expected_root.endswith("/"):
        expected_root = expected_root + "/"

    file_names = _get_zip_file_names(zip_path)

    if not file_names:
        raise ValueError(f"ZIP 中没有任何文件项: {zip_path}")

    for name in file_names:
        if not name.startswith(expected_root):
            raise ValueError(
                f"ZIP 根目录错误，期望所有文件位于 {expected_root} 下，实际发现: {name}"
            )


def assert_zip_contains_files(zip_path: str, required_files: Iterable[str]) -> None:
    """
    校验 ZIP 内必须存在指定文件项。
    """
    file_names = set(_get_zip_file_names(zip_path))

    for required_file in required_files:
        _validate_zip_member_path(required_file)

        if required_file.endswith("/"):
            raise ValueError(f"required_files 只能传文件路径，不能传目录路径: {required_file}")

        if required_file not in file_names:
            raise ValueError(f"ZIP 缺少必需文件: {required_file}")
        
def assert_file_not_empty_in_zip(zip_path: str, file_path: str):
    """
    校验 ZIP 内某个文件内容非空（用于 README.txt）
    """
    if not zip_exists_and_valid(zip_path):
        raise ValueError(f"ZIP 不存在或损坏: {zip_path}")

    with zipfile.ZipFile(zip_path, "r") as zf:
        try:
            content = zf.read(file_path)
        except KeyError:
            raise ValueError(f"ZIP 缺少文件: {file_path}")

        if not content or not content.strip():
            raise ValueError(f"{file_path} 不得为空")

def assert_readme_contains_keywords(zip_path: str, readme_path: str, keywords: Iterable[str]) -> None:
    """
    校验 README.txt 不只是非空，还必须包含关键语义字段。

    用于：
    - task_package/README.txt
    - result_package/README.txt
    """
    if not zip_exists_and_valid(zip_path):
        raise ValueError(f"ZIP 不存在或损坏: {zip_path}")

    with zipfile.ZipFile(zip_path, "r") as zf:
        try:
            content = zf.read(readme_path).decode("utf-8")
        except KeyError:
            raise ValueError(f"ZIP 缺少文件: {readme_path}")

    for keyword in keywords:
        if keyword not in content:
            raise ValueError(f"{readme_path} 缺少关键说明字段: {keyword}")


def assert_zip_has_file_under_dir(zip_path: str, required_dir: str) -> None:
    """
    校验 ZIP 内某个目录下至少存在一个文件。

    用于：
    - task_package/images/
    - segmentation task_package/masks/
    - segmentation result_package/results/masks/
    """
    if not required_dir.endswith("/"):
        required_dir = required_dir + "/"

    _validate_zip_member_path(required_dir)

    file_names = _get_zip_file_names(zip_path)

    for name in file_names:
        if name.startswith(required_dir):
            return

    raise ValueError(f"ZIP 目录下缺少文件: {required_dir}")


def assert_task_package_json_hash_consistency(zip_path: str) -> None:
    """
    校验 task_package.zip 内部：
    tasks.json 与 meta.json 的 sample_id_hash 是否一致。
    """
    if not zip_exists_and_valid(zip_path):
        raise ValueError(f"ZIP 不存在或损坏: {zip_path}")

    with zipfile.ZipFile(zip_path, "r") as zf:
        try:
            tasks = json.loads(zf.read("task_package/tasks.json").decode("utf-8"))
            meta = json.loads(zf.read("task_package/meta.json").decode("utf-8"))
        except KeyError as exc:
            raise ValueError(f"ZIP 缺少必要 JSON 文件: {exc}")

    if not isinstance(tasks, list) or not tasks:
        raise ValueError("task_package/tasks.json 顶层必须是非空数组")

    if not isinstance(meta, dict):
        raise ValueError("task_package/meta.json 顶层必须是 object")

    sample_ids = [item["sample_id"] for item in tasks]
    computed_hash = compute_sample_id_hash(sample_ids)

    if meta.get("sample_id_hash") != computed_hash:
        raise ValueError(
            "task_package.zip 内 sample_id_hash 不一致: "
            f"meta={meta.get('sample_id_hash')}, computed={computed_hash}"
        )


def assert_task_package_zip_structure(zip_path: str, task_type: str | None = None) -> None:
    """
    校验 task_package.zip 的真实内部结构。

    冻结结构：
    task_package/
    ├── tasks.json
    ├── meta.json
    ├── README.txt
    ├── images/
    └── masks/   # segmentation 必须存在并有文件；detection/caption 可不存在或为空

    注意：
    - ZIP 内可以没有显式目录项 task_package/images/
    - 只要存在 task_package/images/xxx.jpg 或 xxx.png，即认为 images 有内容
    """
    assert_zip_has_single_root(zip_path, "task_package")

    assert_zip_contains_files(
        zip_path,
        [
            "task_package/tasks.json",
            "task_package/meta.json",
            "task_package/README.txt",
        ],
    )

    assert_file_not_empty_in_zip(zip_path, "task_package/README.txt")

    assert_readme_contains_keywords(
    zip_path,
    "task_package/README.txt",
    ["task_id", "task_type", "assigned_to"],
)

    assert_zip_has_file_under_dir(zip_path, "task_package/images/")

    if task_type == "segmentation":
        assert_zip_has_file_under_dir(zip_path, "task_package/masks/")

    elif task_type in {"detection", "caption"}:
        # detection / caption 的 masks/ 可不存在或为空，不强制校验
        pass

    elif task_type is None:
        # Day1 工具层允许不传 task_type，只校验通用结构
        pass

    else:
        raise ValueError(f"非法 task_type: {task_type}")

    assert_task_package_json_hash_consistency(zip_path)


def assert_result_package_zip_structure(zip_path: str, module: str | None = None) -> None:
    """
    校验 result_package.zip 的真实内部结构。

    冻结结构：
    result_package/
    ├── meta.json
    ├── results.json
    ├── results/
    │   └── masks/      # segmentation 结果包必须存在并有文件
    └── README.txt

    注意：
    - detection / caption 结果包不要求 results/masks/
    - segmentation 结果包必须有 result_package/results/masks/ 下的 mask 文件
    """
    assert_zip_has_single_root(zip_path, "result_package")

    assert_zip_contains_files(
        zip_path,
        [
            "result_package/meta.json",
            "result_package/results.json",
            "result_package/README.txt",
        ],
    )

    assert_file_not_empty_in_zip(zip_path, "result_package/README.txt")

    if module == "segmentation":
        assert_zip_has_file_under_dir(zip_path, "result_package/results/masks/")

    elif module in {"detection", "caption"}:
        pass

    elif module is None:
        # Day1 工具层允许不传 module，只校验通用结构
        pass

    else:
        raise ValueError(f"非法 module: {module}")
    
def assert_task_package_content_consistency(zip_path: str, tasks: list):
    """
    校验 ZIP 内 images / masks 是否与 tasks.json 一致
    """
    file_names = set(_get_zip_file_names(zip_path))

    for item in tasks:
        image_path = f"task_package/{item['image']}"
        if image_path not in file_names:
            raise ValueError(f"ZIP 缺少 image: {image_path}")

        if item["task_type"] == "segmentation":
            mask_path = f"task_package/{item['mask']}"
            if mask_path not in file_names:
                raise ValueError(f"ZIP 缺少 mask: {mask_path}")


def extract_zip_safe(zip_path: str, target_dir: str, expected_root: str | None = None) -> None:
    """
    安全解压 ZIP。

    expected_root 可选：
    - task_package
    - result_package

    如果传入 expected_root，则解压前强制校验所有文件项都在该根目录下。
    """
    if not zip_exists_and_valid(zip_path):
        raise ValueError(f"ZIP 不存在、为空或损坏: {zip_path}")

    _get_zip_names(zip_path)

    if expected_root is not None:
        assert_zip_has_single_root(zip_path, expected_root)

    os.makedirs(target_dir, exist_ok=True)

    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(target_dir)


def get_upload_done_flag_path(zip_path: str) -> str:
    return f"{zip_path}.UPLOAD_DONE.flag"


def get_done_file_path(zip_path: str) -> str:
    if not zip_path.endswith(".zip"):
        raise ValueError(f"结果包必须以 .zip 结尾: {zip_path}")
    return zip_path[:-4] + ".done"


def check_upload_done_flag(zip_path: str) -> bool:
    return zip_exists_and_valid(zip_path) and os.path.exists(get_upload_done_flag_path(zip_path))


def check_done_file(zip_path: str) -> bool:
    return zip_exists_and_valid(zip_path) and os.path.exists(get_done_file_path(zip_path))


def create_upload_done_flag(zip_path: str) -> str:
    """
    仅允许在 task_package.zip 完整后生成 UPLOAD_DONE.flag。
    """
    if not zip_exists_and_valid(zip_path):
        raise ValueError(f"ZIP 不完整，禁止生成 UPLOAD_DONE.flag: {zip_path}")

    flag_path = get_upload_done_flag_path(zip_path)

    with open(flag_path, "w", encoding="utf-8") as f:
        f.write("")

    return flag_path


def create_done_file(zip_path: str) -> str:
    """
    仅允许在 result_package.zip 完整后生成 .done。
    """
    if not zip_exists_and_valid(zip_path):
        raise ValueError(f"ZIP 不完整，禁止生成 .done: {zip_path}")

    done_path = get_done_file_path(zip_path)

    with open(done_path, "w", encoding="utf-8") as f:
        f.write("")

    return done_path


def move_file_atomic(src: str, dst: str) -> None:
    """
    同盘原子移动，用于 .tmp -> 正式文件。
    """
    dst_dir = os.path.dirname(dst)

    if dst_dir:
        os.makedirs(dst_dir, exist_ok=True)

    os.replace(src, dst)


def move_file(src: str, dst: str) -> None:
    """
    普通移动，用于归档 processed / failed / duplicate 等。
    """
    dst_dir = os.path.dirname(dst)

    if dst_dir:
        os.makedirs(dst_dir, exist_ok=True)

    shutil.move(src, dst)