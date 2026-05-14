import json
import sys
from pathlib import Path

def find_project_root(start: Path) -> Path:
    cur = start.resolve()
    for candidate in [cur, *cur.parents]:
        if (candidate / "scripts").exists() and (candidate / "center").exists():
            return candidate
    raise RuntimeError("无法定位项目根目录：未找到同时包含 scripts/ 和 center/ 的目录")

PROJECT_ROOT = find_project_root(Path(__file__).parent)

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.shared.validators import validate_tasks_json, validate_task_package_meta
from scripts.shared.hash_utils import compute_sample_id_hash


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


root = PROJECT_ROOT / "center" / "task_packages" / ".tmp"

if not root.exists():
    raise FileNotFoundError(f"Day3 输出目录不存在: {root}")

found = False

for tasks_path in root.glob("*/task_package/tasks.json"):
    found = True
    meta_path = tasks_path.parent / "meta.json"
    readme_path = tasks_path.parent / "README.txt"

    if not meta_path.exists():
        raise FileNotFoundError(f"缺少 meta.json: {meta_path}")

    if not readme_path.exists() or not readme_path.read_text(encoding="utf-8").strip():
        raise ValueError(f"README.txt 缺失或为空: {readme_path}")

    tasks = json.loads(tasks_path.read_text(encoding="utf-8"))
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    validate_tasks_json(tasks)
    validate_task_package_meta(meta)

    task_types = {item["task_type"] for item in tasks}
    require(len(task_types) == 1, f"同一个 tasks.json 中出现多个 task_type: {task_types}")

    task_type = next(iter(task_types))

    task_keys = {(item["sample_id"], item["task_type"]) for item in tasks}
    require(len(task_keys) == len(tasks), f"存在重复 sample_id + task_type: {tasks_path}")

    require(
        meta["task_type"] == task_type,
        f"meta.task_type 与 tasks.json.task_type 不一致: meta={meta['task_type']}, tasks={task_type}",
    )

    require(
        meta["total_samples"] == len(tasks),
        f"total_samples 不一致: meta={meta['total_samples']}, tasks={len(tasks)}",
    )

    computed_hash = compute_sample_id_hash([item["sample_id"] for item in tasks])
    require(
        meta["sample_id_hash"] == computed_hash,
        f"sample_id_hash 不一致: meta={meta['sample_id_hash']}, computed={computed_hash}",
    )

    require(meta["assigned_to"] not in {"User_A", "user001"}, "assigned_to 不得使用占位名")
    require(meta["assigned_to"] == meta["assigned_to_snapshot"], "assigned_to_snapshot 必须等于 assigned_to")

    require(meta["is_rework"] is False, "Day3 普通任务包 is_rework 必须为 false")
    require(meta["parent_task_id"] is None, "Day3 普通任务包 parent_task_id 必须为 null")
    require(meta["rework_reason"] is None, "Day3 普通任务包 rework_reason 必须为 null")

    image_paths = set()
    mask_paths = set()

    for item in tasks:
        image_path = tasks_path.parent / item["image"]
        require(image_path.exists() and image_path.is_file(), f"image 文件不存在: {image_path}")
        require(item["image"] not in image_paths, f"包内 image 路径重复: {item['image']}")
        image_paths.add(item["image"])

        if item["task_type"] == "segmentation":
            require(item["mask"] is not None, f"segmentation mask 不得为 null: {item['sample_id']}")
            mask_path = tasks_path.parent / item["mask"]
            require(mask_path.exists() and mask_path.is_file(), f"mask 文件不存在: {mask_path}")
            require(item["mask"] not in mask_paths, f"包内 mask 路径重复: {item['mask']}")
            mask_paths.add(item["mask"])
        elif item["task_type"] in {"detection", "caption"}:
            require(item["mask"] is None, f"detection/caption mask 必须为 null: {item['sample_id']}")

    print("[OK]", tasks_path.relative_to(PROJECT_ROOT))

if not found:
    raise FileNotFoundError(f"未找到任何 tasks.json，请检查 splitter 输出目录: {root}")

print("[OK] Day3 validation passed")