# Day10_B 校验说明文档（交付给A）

## 一、目的

本说明文档用于指导 A 在获取 Day10_B 代码后，完成：

 - 本地真实结果包（result_package）的统一校验
 - 确保所有导出数据满足 Day10 入池标准
 - 为 Day11（merge / review / final）提供干净输入

---

## 二、前置条件（必须完成）

### 1. 拉取最新代码

```bash
git pull
```

---

### 2. 项目根目录

```bash
Medical-Multi-Task-Annotation-Platform/
```

---

### 3. 准备真实数据（必须提前完成 ⚠️）

必须提前将所有真实导出结果包放入：

```bash
Project_Sync/
└── 02_Collection/
    ├── 张三/
    │   └── Submitted/
    │       ├── RESULT_SEG_*.zip + .done
    │       ├── RESULT_DET_*.zip + .done
    │       └── RESULT_CAP_*.zip + .done
    │
    ├── 李四/
    │   └── Submitted/
    │       ├── RESULT_SEG_*.zip + .done
    │       ├── RESULT_DET_*.zip + .done
    │       └── RESULT_CAP_*.zip + .done
    │
    └── 王五/
        └── Submitted/
            ├── RESULT_SEG_*.zip + .done
            ├── RESULT_DET_*.zip + .done
            └── RESULT_CAP_*.zip + .done
```

---

### 4. 数据数量要求

必须严格满足：

| 类型 | 数量 |
| ---- | ---- |
| SEG  | 9    |
| DET  | 9    |
| CAP  | 9    |
| 总计 | 27   |

---

### 5. 每个结果包必须成对存在

```bash
RESULT_xxx.zip
RESULT_xxx.done
```

缺少 .done 会直接校验失败!

---

### 6. 本地任务包必须存在

```bash
local/local_workspace/tasks/{task_id}/task_package/
    ├── tasks.json
    └── meta.json
```

---

## 三、校验逻辑说明

核心校验函数：

```bash
assert_day10_export_contract(...)
```

会校验：

 - ZIP结构（必须为 result_package/ 根目录）
 - meta.json 完整性
 - results.json 完整性
 - sample_id_hash 一致性
 - results_json_hash 一致性
 - 与 task_package 对齐
 - invalid_count 必须为 0

三大任务类型专项校验：

 - segmentation（mask）
 - detection（boxes）
 - caption（prompt_version）

---

## 四、运行方式（重点）

### 1. 在项目根目录创建临时运行脚本 (注意：完成本次校验后要删除！)

文件名：
```bash
run_day10_check.py
```
---

### 2. 脚本内容（直接复制使用）

```python
from __future__ import annotations

import json
import zipfile
from pathlib import Path

from scripts.local.validators.day10_export_contract import assert_day10_export_contract


submitted_root = Path("Project_Sync/02_Collection")
workspace_root = Path("local/local_workspace/tasks")


def read_task_id_from_result_zip(zip_path: Path) -> str:
    with zipfile.ZipFile(zip_path, "r") as zf:
        try:
            raw = zf.read("result_package/meta.json")
        except KeyError as exc:
            raise ValueError(f"ZIP 缺少 result_package/meta.json: {zip_path}") from exc

    meta = json.loads(raw.decode("utf-8"))
    task_id = meta.get("task_id")

    if not isinstance(task_id, str) or not task_id:
        raise ValueError(f"result_package/meta.json.task_id 必须是非空字符串: {zip_path}")

    return task_id


def main() -> None:
    zip_paths = sorted(submitted_root.rglob("*.zip"))

    if not zip_paths:
        raise SystemExit(f"[FAILED] 未找到 Submitted 结果包: {submitted_root}")

    passed = 0
    failed = 0

    for zip_path in zip_paths:
        try:
            task_id = read_task_id_from_result_zip(zip_path)
            task_package_dir = workspace_root / task_id / "task_package"

            assert_day10_export_contract(
                zip_path=zip_path,
                task_package_dir=task_package_dir,
                require_done=True,
            )

            print(f"[OK] {zip_path}")
            passed += 1

        except Exception as exc:
            print(f"[FAILED] {zip_path} -> {exc}")
            failed += 1

    print(f"[SUMMARY] passed={passed}, failed={failed}, total={len(zip_paths)}")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
```
---

### 3. PowerShell 执行

```bash
python run_day10_check.py
```
---

## 五、运行结果说明

成功（必须达到）

```bash
[SUMMARY] passed=27, failed=0, total=27
```

失败示例

```bash
[FAILED] xxx.zip -> 错误原因
```
---

## 六、必须满足的通过标准

```bash
passed = 27
failed = 0
```

否则禁止进入 Day11。

---

## 七、常见错误（非常重要 ⚠️）

### 1. 没有提前准备数据

```bash
[FAILED] 未找到 Submitted 结果包
```
---

### 2. 缺少 .done 文件

→ 直接失败

---

### 3. invalid_count ≠ 0

→ 直接失败（Day10硬性要求）

---

### 4. results.json 与 tasks.json 不一致

→ 常见问题：

 - sample_id 缺失
 - sample_id 多余
 - hash 不一致

---

### 5. segmentation 问题

 - mask_path 不存在
 - mask 不在 ZIP 内
 - 非 png

---

### 6. detection 问题

 - negative_confirmed 不匹配
 - boxes 非法

---

### 7. caption 问题

prompt_version 与任务不一致

---

## 八、校验完成后

可删除临时脚本：
```bash
run_day10_check.py
```

---

## 九、下一步

全部通过后：
进入 Day11（merge / review / final）

---

## 十、总结

Day10_B 校验是：

入池前的最终强校验（Gatekeeper）

确保：

 - 数据正确
 - 数据完整
 - 数据一致

可安全进入中心结果池