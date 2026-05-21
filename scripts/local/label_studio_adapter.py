from __future__ import annotations

import argparse
import json
import os
import re
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


SCHEMA_VERSION = "v1"
VERSION = "v1"
ALLOWED_TASK_TYPES = {"segmentation", "detection", "caption"}

DET_MIN_COMPONENT_AREA = 20
DET_BOX_EXPAND_PX = 2


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def norm_rel_path(value: str) -> str:
    value = str(value).replace("\\", "/").strip()

    if not value:
        raise ValueError("路径不能为空")

    if value == ".":
        raise ValueError(f"禁止非法路径: {value}")

    if value.startswith("http://") or value.startswith("https://") or "://" in value:
        raise ValueError(f"禁止 URL 路径: {value}")

    if re.match(r"^[A-Za-z]:/", value) or value.startswith("/"):
        raise ValueError(f"禁止绝对路径: {value}")

    if "//" in value:
        raise ValueError(f"禁止连续斜杠路径: {value}")

    parts = value.split("/")
    if "." in parts or ".." in parts or any(part == "" for part in parts):
        raise ValueError(f"禁止路径穿越或非法路径片段: {value}")

    return value


def to_label_studio_local_file_url(task_dir: Path, rel_path: str) -> str:
    rel_path = norm_rel_path(rel_path).lstrip("/")
    task_id = task_dir.name
    return f"http://127.0.0.1:8766/{task_id}/task_package/{rel_path}"


def infer_task_type(task: Dict[str, Any], meta: Dict[str, Any]) -> str:
    task_type = task.get("task_type") or task.get("module") or meta.get("task_type") or meta.get("module")
    if task_type not in ALLOWED_TASK_TYPES:
        raise ValueError(f"非法 task_type/module: {task_type}")
    return task_type


def image_size_from_task(task_dir: Path, image_rel: str) -> Optional[Tuple[int, int]]:
    try:
        from PIL import Image
        image_path = task_dir / "task_package" / norm_rel_path(image_rel)
        if not image_path.exists():
            return None
        with Image.open(image_path) as im:
            return im.size
    except Exception:
        return None


def candidate_reference_mask_paths(task_dir: Path, task: Dict[str, Any], meta: Dict[str, Any]) -> List[Path]:
    task_id = meta["task_id"]
    image_id = task.get("image_id") or ""
    image_rel = str(task.get("image") or "")
    image_stem = Path(image_rel).stem if image_rel else ""
    sample_id = task.get("sample_id") or ""

    names = []
    for v in [image_id, image_stem, sample_id]:
        if v and v not in names:
            names.append(v)

    project_root = task_dir.resolve()
    while project_root.name != "local_workspace" and project_root.parent != project_root:
        project_root = project_root.parent

    repo_root = task_dir.resolve()
    for _ in range(5):
        if (repo_root / "local").exists() or (repo_root / "Project_Sync").exists():
            break
        repo_root = repo_root.parent

    candidates: List[Path] = []

    mask_rel = task.get("mask") or task.get("mask_path")
    if mask_rel:
        candidates.append(task_dir / "task_package" / norm_rel_path(mask_rel))

    for name in names:
        candidates.extend([
            repo_root / "central_data_pool" / "masks" / f"{name}.png",
            repo_root / "local" / "central_data_pool" / "masks" / f"{name}.png",
            repo_root / "data" / "central_data_pool" / "masks" / f"{name}.png",
        ])

    if task_id.startswith("DET_"):
        seg_task_id = task_id.replace("DET_", "SEG_", 1)
        for name in names:
            candidates.extend([
                repo_root / "local" / "local_workspace" / "tasks" / seg_task_id / "task_package" / "masks" / f"{name}.png",
                repo_root / "local" / "local_workspace" / "tasks" / seg_task_id / "result_package" / "results" / "masks" / f"{name}.png",
            ])

    seen = set()
    deduped = []
    for p in candidates:
        key = str(p)
        if key not in seen:
            seen.add(key)
            deduped.append(p)

    return deduped


def find_reference_mask(task_dir: Path, task: Dict[str, Any], meta: Dict[str, Any]) -> Optional[Path]:
    for p in candidate_reference_mask_paths(task_dir, task, meta):
        if p.exists() and p.is_file() and p.suffix.lower() == ".png":
            return p
    return None


def mask_to_connected_component_boxes(
    mask_path: Path,
    image_size: Optional[Tuple[int, int]] = None,
    min_area: int = DET_MIN_COMPONENT_AREA,
    expand_px: int = DET_BOX_EXPAND_PX,
) -> List[Dict[str, Any]]:
    from PIL import Image

    with Image.open(mask_path) as im:
        gray = im.convert("L")
        width, height = gray.size
        pixels = gray.load()

        visited = set()
        boxes = []

        for y in range(height):
            for x in range(width):
                if (x, y) in visited:
                    continue
                if pixels[x, y] <= 0:
                    continue

                q = deque([(x, y)])
                visited.add((x, y))
                min_x = max_x = x
                min_y = max_y = y
                area = 0

                while q:
                    cx, cy = q.popleft()
                    area += 1
                    min_x = min(min_x, cx)
                    max_x = max(max_x, cx)
                    min_y = min(min_y, cy)
                    max_y = max(max_y, cy)

                    for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                        if nx < 0 or ny < 0 or nx >= width or ny >= height:
                            continue
                        if (nx, ny) in visited:
                            continue
                        if pixels[nx, ny] <= 0:
                            continue
                        visited.add((nx, ny))
                        q.append((nx, ny))

                if area < min_area:
                    continue

                min_x = max(0, min_x - expand_px)
                min_y = max(0, min_y - expand_px)
                max_x = min(width - 1, max_x + expand_px)
                max_y = min(height - 1, max_y + expand_px)

                box_w = max_x - min_x + 1
                box_h = max_y - min_y + 1

                if box_w <= 0 or box_h <= 0:
                    continue

                boxes.append({
                    "x": min_x,
                    "y": min_y,
                    "width": box_w,
                    "height": box_h,
                    "label": "lesion",
                    "coordinate_system": "original_image",
                    "original_width": width,
                    "original_height": height,
                    "area": area,
                })

    boxes.sort(key=lambda b: b["area"], reverse=True)

    if image_size and image_size != (boxes[0]["original_width"], boxes[0]["original_height"]) if boxes else False:
        # 不强制报错。这里保留 mask 尺寸作为 original_width/original_height，
        # Label Studio 会按 original 尺寸映射候选框。
        pass

    return boxes


def detection_boxes_to_label_studio_predictions(boxes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not boxes:
        return []

    result = []
    for i, box in enumerate(boxes):
        ow = int(box["original_width"])
        oh = int(box["original_height"])

        result.append({
            "id": f"det_candidate_{i + 1}",
            "from_name": "detection_box",
            "to_name": "image",
            "type": "rectanglelabels",
            "original_width": ow,
            "original_height": oh,
            "image_rotation": 0,
            "value": {
                "x": round(float(box["x"]) * 100.0 / ow, 6),
                "y": round(float(box["y"]) * 100.0 / oh, 6),
                "width": round(float(box["width"]) * 100.0 / ow, 6),
                "height": round(float(box["height"]) * 100.0 / oh, 6),
                "rotation": 0,
                "rectanglelabels": ["lesion"],
            },
        })

    return [{
        "model_version": "mask_to_bbox_reference_v1",
        "score": 0.5,
        "result": result,
    }]


def build_detection_prediction(task_dir: Path, task: Dict[str, Any], meta: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    mask_path = find_reference_mask(task_dir, task, meta)
    if not mask_path:
        return [], None

    image_rel = task.get("image") or ""
    image_size = image_size_from_task(task_dir, image_rel)

    boxes = mask_to_connected_component_boxes(mask_path, image_size=image_size)
    predictions = detection_boxes_to_label_studio_predictions(boxes)

    return predictions, str(mask_path).replace("\\", "/")


def tasks_to_label_studio(task_dir: Path, out_path: Path, operator: str = "") -> None:
    tasks_json = read_json(task_dir / "task_package" / "tasks.json")
    meta = read_json(task_dir / "task_package" / "meta.json")

    if not isinstance(tasks_json, list):
        raise ValueError("tasks.json 顶层必须是数组")

    payload = []

    for item in tasks_json:
        task_type = infer_task_type(item, meta)
        image_path = norm_rel_path(item.get("image") or "")
        mask_path = item.get("mask") or item.get("mask_path")

        data = {
            "sample_id": item["sample_id"],
            "case_id": item["case_id"],
            "image_id": item.get("image_id", ""),
            "task_id": meta["task_id"],
            "task_type": task_type,
            "module": task_type,
            "operator": operator or meta.get("assigned_to") or "",
            "image": to_label_studio_local_file_url(task_dir, image_path),
            "mask": mask_path,
            "diagnosis_raw": item.get("diagnosis_raw", ""),
            "check_category": item.get("check_category", ""),
            "resolution_level": item.get("resolution_level", ""),
            "prompt_version": item.get("prompt_version"),
            "context_sources": item.get("context_sources"),
            "schema_version": item.get("schema_version", SCHEMA_VERSION),
        }

        ls_item: Dict[str, Any] = {"data": data}

        if task_type == "detection":
            predictions, ref_mask = build_detection_prediction(task_dir, item, meta)
            if ref_mask:
                data["reference_mask"] = ref_mask
            if predictions:
                ls_item["predictions"] = predictions

        payload.append(ls_item)

    write_json(out_path, payload)
    print(f"[OK] wrote Label Studio import payload: {out_path}")


def get_annotations(ls_item: Dict[str, Any]) -> List[Dict[str, Any]]:
    anns = ls_item.get("annotations") or []
    if anns:
        result = anns[0].get("result") or []
        return result
    preds = ls_item.get("predictions") or []
    if preds:
        return preds[0].get("result") or []
    return []


def ls_data(ls_item: Dict[str, Any]) -> Dict[str, Any]:
    return ls_item.get("data") or {}


def pct_to_px(v: float, total: int) -> float:
    return float(v) * float(total) / 100.0


def convert_detection(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    boxes = []
    negative_confirmed = False

    for r in results:
        value = r.get("value") or {}
        r_type = r.get("type")

        if r_type == "rectanglelabels":
            ow = int(r.get("original_width") or value.get("original_width") or 0)
            oh = int(r.get("original_height") or value.get("original_height") or 0)
            if ow <= 0 or oh <= 0:
                raise ValueError("detection rectangle 缺 original_width/original_height")

            x = pct_to_px(value.get("x", 0), ow)
            y = pct_to_px(value.get("y", 0), oh)
            w = pct_to_px(value.get("width", 0), ow)
            h = pct_to_px(value.get("height", 0), oh)
            labels = value.get("rectanglelabels") or []

            boxes.append({
                "x": round(x, 3),
                "y": round(y, 3),
                "width": round(w, 3),
                "height": round(h, 3),
                "label": labels[0] if labels else "lesion",
            })

        if r_type in {"choices", "labels"}:
            choices = value.get("choices") or value.get("labels") or []
            if "negative_confirmed" in choices or "无目标" in choices or "阴性确认" in choices:
                negative_confirmed = True

    if boxes:
        negative_confirmed = False
    else:
        if not negative_confirmed:
            raise ValueError("detection 必须确认候选框/手动画框，或选择 negative_confirmed 阴性确认")

    return {
        "boxes": boxes,
        "negative_confirmed": negative_confirmed,
    }


def copy_existing_seg_mask(data: Dict[str, Any], out_root: Path) -> str:
    task_id = data["task_id"]
    mask_rel = data.get("mask")

    if not mask_rel:
        raise ValueError(f"SEG 已选择沿用已有 mask，但 data.mask 为空: sample_id={data.get('sample_id')}")

    mask_rel = norm_rel_path(mask_rel)

    task_dir = Path("local/local_workspace/tasks") / task_id
    src_mask = task_dir / "task_package" / mask_rel

    if not src_mask.exists() or not src_mask.is_file():
        raise FileNotFoundError(f"已有 mask 文件不存在: {src_mask}")

    if src_mask.suffix.lower() != ".png":
        raise ValueError(f"SEG mask 必须是 .png: {src_mask}")

    image_id = data.get("image_id") or src_mask.stem

    dst_rel = f"results/masks/{image_id}.png"
    dst_mask = out_root / dst_rel
    dst_mask.parent.mkdir(parents=True, exist_ok=True)

    content = src_mask.read_bytes()
    if not content:
        raise ValueError(f"已有 mask 文件为空: {src_mask}")

    tmp = dst_mask.with_suffix(dst_mask.suffix + ".tmp")
    tmp.write_bytes(content)
    os.replace(tmp, dst_mask)

    return dst_rel


def polygon_to_mask_png(
    sample_id: str,
    data: Dict[str, Any],
    results: List[Dict[str, Any]],
    masks_dir: Path,
) -> str:
    from PIL import Image, ImageDraw

    image_id = data.get("image_id") or sample_id
    polygons = []

    original_width = None
    original_height = None

    for r in results:
        if r.get("type") != "polygonlabels":
            continue

        value = r.get("value") or {}
        points = value.get("points") or []

        ow = int(r.get("original_width") or value.get("original_width") or 0)
        oh = int(r.get("original_height") or value.get("original_height") or 0)

        if ow <= 0 or oh <= 0:
            raise ValueError(f"polygon 缺 original_width/original_height: sample_id={sample_id}")

        original_width = ow
        original_height = oh

        polygon_px = []
        for point in points:
            if not isinstance(point, list) or len(point) != 2:
                raise ValueError(f"polygon point 非法: sample_id={sample_id}, point={point}")
            x = float(point[0]) * ow / 100.0
            y = float(point[1]) * oh / 100.0
            polygon_px.append((x, y))

        if len(polygon_px) >= 3:
            polygons.append(polygon_px)

    unsupported = [r.get("type") for r in results if r.get("type") == "brushlabels"]
    if unsupported:
        raise ValueError(
            f"当前 Day13 冻结版暂不支持 brushlabels 转 PNG，请使用 Polygon 标注: sample_id={sample_id}"
        )

    if not polygons:
        raise ValueError(f"无 mask 样本没有有效 polygon 标注: sample_id={sample_id}")

    masks_dir.mkdir(parents=True, exist_ok=True)

    mask_rel = f"results/masks/{image_id}.png"
    mask_abs = masks_dir / f"{image_id}.png"

    mask = Image.new("L", (original_width, original_height), 0)
    draw = ImageDraw.Draw(mask)

    for poly in polygons:
        draw.polygon(poly, outline=255, fill=255)

    tmp = mask_abs.with_suffix(mask_abs.suffix + ".tmp")
    mask.save(tmp, format="PNG")
    os.replace(tmp, mask_abs)

    return mask_rel


def has_seg_keep_existing_mask_choice(results: List[Dict[str, Any]]) -> bool:
    for r in results:
        if r.get("type") not in {"choices", "labels"}:
            continue
        value = r.get("value") or {}
        choices = value.get("choices") or value.get("labels") or []
        if "已有 mask 可沿用，无需手动画病灶" in choices:
            return True
    return False


def has_polygon_annotation(results: List[Dict[str, Any]]) -> bool:
    for r in results:
        if r.get("type") == "polygonlabels":
            value = r.get("value") or {}
            points = value.get("points") or []
            if len(points) >= 3:
                return True
    return False


def convert_segmentation(data: Dict[str, Any], results: List[Dict[str, Any]], out_root: Path) -> Dict[str, Any]:
    sample_id = data["sample_id"]

    # 优先使用人工 Polygon。只要画了 polygon，就认为人工修订覆盖原 mask。
    if has_polygon_annotation(results):
        mask_path = polygon_to_mask_png(
            sample_id=sample_id,
            data=data,
            results=results,
            masks_dir=out_root / "results" / "masks",
        )
        return {
            "mask_path": mask_path,
            "polygons": [],
        }

    # 只有明确选择“已有 mask 可沿用”时，才复制任务包内原 mask。
    if data.get("mask") and has_seg_keep_existing_mask_choice(results):
        mask_path = copy_existing_seg_mask(data, out_root)
        return {
            "mask_path": mask_path,
            "polygons": [],
        }

    raise ValueError(
        f"segmentation 必须画 Polygon，或明确选择“已有 mask 可沿用，无需手动画病灶”: sample_id={sample_id}"
    )


def convert_caption(results: List[Dict[str, Any]], expected_prompt_version: str = "caption_prompt_v1") -> Dict[str, Any]:
    generated = ""
    reviewed = ""
    prompt_version = ""

    for r in results:
        value = r.get("value") or {}
        texts = value.get("text") or []
        text = texts[0].strip() if texts else ""

        from_name = r.get("from_name") or ""
        if from_name in {"generated", "caption_generated"}:
            generated = text
        elif from_name in {"reviewed", "caption_reviewed"}:
            reviewed = text
        elif from_name in {"prompt_version", "caption_prompt_version"}:
            prompt_version = text

    if not reviewed:
        raise ValueError("caption.reviewed 不能为空，必须是人工修订结果")
    if not generated:
        generated = reviewed
    if not prompt_version:
        prompt_version = expected_prompt_version
    if prompt_version != expected_prompt_version:
        raise ValueError(
            f"caption.prompt_version 必须等于任务包 prompt_version: actual={prompt_version}, expected={expected_prompt_version}"
        )

    return {
        "generated": generated,
        "reviewed": reviewed,
        "prompt_version": prompt_version,
    }


def build_existing_mask_result(
    task: Dict[str, Any],
    meta: Dict[str, Any],
    operator: str,
    task_dir: Path,
    out_root: Path,
) -> Dict[str, Any]:
    mask_rel = task.get("mask") or task.get("mask_path")
    if not mask_rel:
        raise ValueError(f"已有 mask 自动结果缺少 mask 字段: {task.get('sample_id')}")

    data = {
        "sample_id": task["sample_id"],
        "case_id": task["case_id"],
        "task_id": meta["task_id"],
        "task_type": meta["task_type"],
        "module": meta["task_type"],
        "operator": operator or meta.get("assigned_to") or "",
        "mask": mask_rel,
        "image_id": task.get("image_id", ""),
    }

    # split-seg-before-ls 是自动沿用已有 mask 的分流流程，
    # 这里不能再走 convert_segmentation(results=[])，
    # 否则会被新的人工确认逻辑拦截。
    result_body = {
        "mask_path": copy_existing_seg_mask(data=data, out_root=out_root),
        "polygons": [],
    }

    return {
        "sample_id": task["sample_id"],
        "case_id": task["case_id"],
        "module": "segmentation",
        "result": result_body,
        "operator": operator or meta.get("assigned_to") or "",
        "timestamp": now_iso(),
        "task_id": meta["task_id"],
        "version": VERSION,
        "schema_version": SCHEMA_VERSION,
    }


def split_seg_before_label_studio(task_dir: Path, out_dir: Path, operator: str = "") -> None:
    tasks = read_json(task_dir / "task_package" / "tasks.json")
    meta = read_json(task_dir / "task_package" / "meta.json")

    if meta.get("task_type") != "segmentation":
        raise ValueError("split-seg-before-ls 仅用于 segmentation 任务")

    out_dir.mkdir(parents=True, exist_ok=True)

    out_root = task_dir / "result_package"
    out_root.mkdir(parents=True, exist_ok=True)

    ls_payload = []
    auto_results = []

    for task in tasks:
        mask_rel = task.get("mask") or task.get("mask_path")

        if mask_rel:
            auto_results.append(
                build_existing_mask_result(
                    task=task,
                    meta=meta,
                    operator=operator,
                    task_dir=task_dir,
                    out_root=out_root,
                )
            )
            continue

        image_path = norm_rel_path(task.get("image") or "")

        data = {
            "sample_id": task["sample_id"],
            "case_id": task["case_id"],
            "task_id": meta["task_id"],
            "task_type": "segmentation",
            "module": "segmentation",
            "operator": operator or meta.get("assigned_to") or "",
            "image": to_label_studio_local_file_url(task_dir, image_path),
            "diagnosis_raw": task.get("diagnosis_raw", ""),
            "check_category": task.get("check_category", ""),
            "resolution_level": task.get("resolution_level", ""),
            "image_id": task.get("image_id", ""),
        }

        ls_payload.append({"data": data})

    write_json(out_dir / "import_no_mask_to_ls.json", ls_payload)
    write_json(out_dir / "existing_mask_auto_results.json", auto_results)

    summary = {
        "task_id": meta["task_id"],
        "task_type": meta["task_type"],
        "total_samples": len(tasks),
        "existing_mask_count": len(auto_results),
        "need_label_studio_count": len(ls_payload),
        "label_studio_import": str(out_dir / "import_no_mask_to_ls.json"),
        "auto_results": str(out_dir / "existing_mask_auto_results.json"),
        "result_package_root": str(out_root),
        "schema_version": SCHEMA_VERSION,
    }

    write_json(out_dir / "seg_split_summary.json", summary)

    print("[OK] SEG 分流完成")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def label_studio_export_to_results(export_path: Path, out_root: Path, out_results: Path) -> None:
    ls_export = read_json(export_path)
    if not isinstance(ls_export, list):
        raise ValueError("Label Studio export 顶层必须是数组")

    final_results = []

    for item in ls_export:
        data = ls_data(item)
        sample_id = data["sample_id"]
        case_id = data["case_id"]
        task_id = data["task_id"]
        module = data["module"]

        if module not in ALLOWED_TASK_TYPES:
            raise ValueError(f"非法 module: {module}")

        ann_results = get_annotations(item)

        if module == "segmentation":
            result_body = convert_segmentation(data, ann_results, out_root)
        elif module == "detection":
            result_body = convert_detection(ann_results)
        elif module == "caption":
            expected_prompt_version = data.get("prompt_version") or "caption_prompt_v1"
            result_body = convert_caption(ann_results, expected_prompt_version=expected_prompt_version)
        else:
            raise ValueError(f"不支持 module: {module}")

        final_results.append({
            "sample_id": sample_id,
            "case_id": case_id,
            "module": module,
            "result": result_body,
            "operator": data.get("operator") or data.get("assigned_to") or "",
            "timestamp": now_iso(),
            "task_id": task_id,
            "version": VERSION,
            "schema_version": SCHEMA_VERSION,
        })

    write_json(out_results, final_results)
    print(f"[OK] wrote real results.json: {out_results}")


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    p0 = sub.add_parser("split-seg-before-ls")
    p0.add_argument("--task-dir", required=True)
    p0.add_argument("--out-dir", required=True)
    p0.add_argument("--operator", default="")

    p1 = sub.add_parser("tasks-to-ls")
    p1.add_argument("--task-dir", required=True)
    p1.add_argument("--out", required=True)
    p1.add_argument("--operator", default="")

    p2 = sub.add_parser("ls-to-results")
    p2.add_argument("--export", required=True)
    p2.add_argument("--out-root", required=True)
    p2.add_argument("--out-results", required=True)

    args = parser.parse_args()

    if args.cmd == "split-seg-before-ls":
        split_seg_before_label_studio(
            task_dir=Path(args.task_dir),
            out_dir=Path(args.out_dir),
            operator=args.operator,
        )
    elif args.cmd == "tasks-to-ls":
        tasks_to_label_studio(Path(args.task_dir), Path(args.out), args.operator)
    elif args.cmd == "ls-to-results":
        label_studio_export_to_results(
            export_path=Path(args.export),
            out_root=Path(args.out_root),
            out_results=Path(args.out_results),
        )


if __name__ == "__main__":
    main()