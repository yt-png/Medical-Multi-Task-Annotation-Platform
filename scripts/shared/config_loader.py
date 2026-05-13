"""
config_loader.py

配置加载器（Day1 冻结版）

职责：
- 加载 configs/*.json / *.yaml / *.yml
- 统一要求配置顶层为 object
- 配置只能影响运行行为，不能替代协议字段

注意：
- 配置文件可以保存脚本运行参数；
- 配置文件不得替代 tasks.json / results.json / Master / Receive / review_results / final。
"""

import json
import os
from typing import Any, Dict

try:
    import yaml
except ImportError:
    yaml = None


_FORBIDDEN_CONFIG_TOP_KEYS = {
    "tasks",
    "records",
    "results",
    "final",
    "Master_Manifest",
    "Receive_Registry",
    "review_results",
    "final_json",
    "tasks_json",
    "results_json",
}


def _ensure_config_object(data: Any, path: str) -> Dict[str, Any]:
    if data is None:
        raise ValueError(f"配置文件为空: {path}")

    if not isinstance(data, dict):
        raise ValueError(f"配置文件顶层必须是 object: {path}")

    forbidden = set(data.keys()) & _FORBIDDEN_CONFIG_TOP_KEYS
    if forbidden:
        raise ValueError(
            f"配置文件不得替代协议文件或协议顶层结构: {path}, forbidden={sorted(forbidden)}"
        )

    return data


def load_json_config(path: str) -> Dict[str, Any]:
    if not isinstance(path, str) or path == "":
        raise ValueError("配置文件路径必须是非空字符串")

    if not os.path.exists(path):
        raise FileNotFoundError(f"配置文件不存在: {path}")

    if not os.path.isfile(path):
        raise FileNotFoundError(f"配置路径不是普通文件: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return _ensure_config_object(data, path)


def load_yaml_config(path: str) -> Dict[str, Any]:
    if yaml is None:
        raise ImportError("请安装 PyYAML 后再读取 yaml/yml 配置文件")

    if not isinstance(path, str) or path == "":
        raise ValueError("配置文件路径必须是非空字符串")

    if not os.path.exists(path):
        raise FileNotFoundError(f"配置文件不存在: {path}")

    if not os.path.isfile(path):
        raise FileNotFoundError(f"配置路径不是普通文件: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    return _ensure_config_object(data, path)


def load_config(path: str) -> Dict[str, Any]:
    if not isinstance(path, str) or path == "":
        raise ValueError("配置文件路径必须是非空字符串")

    lower_path = path.lower()

    if lower_path.endswith(".json"):
        return load_json_config(path)

    if lower_path.endswith(".yaml") or lower_path.endswith(".yml"):
        return load_yaml_config(path)

    raise ValueError(f"不支持的配置格式，仅支持 .json / .yaml / .yml: {path}")