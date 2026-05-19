# Day6_B_本地导出校验说明文档

## 一、文档目的

本说明用于指导 A 在拉取 Day6 B 分支代码后，**完成一次完整的本地导出链路校验**，确保：

* 本地 exporter.py 行为符合协议
* result_package.zip + .done 输出正确
* 结果结构可被中心 Day7 正常接收

---

## 二、校验范围（严格对应 Day6 验收）

根据开发分工文档 ：

Day6 验收核心：

* 本地生成：

  * `results.json`
  * `result_package/meta.json`
* 输出：

  * `result_package.zip`
  * `.done`
* 满足：

  * ZIP 与 `.done` 一一对应
  * `.done` 必须最后生成
  * `results_json_hash` 正确
  * `completed_count + invalid_count = sample_count`

---

## 三、环境准备

### 1. 拉取代码

```bash
git checkout feature/B-day06-exporter
git pull
```

---

### 2. 确认目录结构

必须存在：

```
project_root/
├── center/
├── local/
├── Project_Sync/
├── scripts/
├── configs/
```

---

### 3. 准备 mock 数据（如未完成 Day1~Day5，如已完成可跳过）

```bash
python scripts/center/prepare_day2_mock_samples.py
python scripts/center/splitter.py --config configs/packaging/distribution_config.json
python scripts/center/master_manager.py --config configs/packaging/distribution_config.json --build
python scripts/center/distributor.py --config configs/packaging/distribution_config.json --task-id SEG_20260425_001
```

---

### 4. 本地导入

```bash
python scripts/local/importer.py --config configs/local_workspace/local_config.json --task-id SEG_20260425_001
```

成功标志：

```
local/local_workspace/tasks/SEG_20260425_001/
```

---

## 四、执行导出

```bash
python scripts/local/exporter.py --config configs/local_workspace/local_config.json --task-id SEG_20260425_001
```

---

## 五、校验点（必须逐条验证）

### ✅ 1. Submitted 输出

路径：

```
Project_Sync/02_Collection/{operator}/Submitted/
```

应存在：

```
RESULT_SEG_20260425_001_{operator}_v1.zip
RESULT_SEG_20260425_001_{operator}_v1.done
```

要求：

* 必须一一对应
* `.done` 文件最后生成
* 不允许只有 zip 没有 done

---

### ✅ 2. ZIP 结构校验

解压后必须为：

```
result_package/
├── results.json
├── meta.json
├── README.txt
├── validation_report.json
└── results/
    └── masks/   (segmentation 必有)
```

⚠️ 不允许：

* 多一层嵌套（result_package/result_package）
* 缺少 results.json 或 meta.json

---

### ✅ 3. results.json 校验

字段必须包含（严格冻结）：

```json
sample_id
case_id
module
result
operator
timestamp
task_id
version
schema_version
```

并满足：

* module ∈ segmentation / detection / caption
* sample_id 与 task_package 一致
* operator == local_config.operator

校验逻辑由：

👉 validate_result_item / validate_results_json

---

### ✅ 4. meta.json 校验

关键字段：

```json
result_package_id
task_id
task_type
module
operator
assigned_to
sample_count
completed_count
invalid_count
sample_id_hash
results_json_hash
```

必须满足：

* operator == assigned_to
* completed_count + invalid_count == sample_count
* results_json_hash == 实际文件 hash
* sample_id_hash 与 tasks.json 一致

校验逻辑：

👉 validate_result_package_meta

---

### ✅ 5. mask / 路径规则（重点）

segmentation：

* mask_path 必须：

  * 相对路径
  * 指向 `results/masks/*.png`

验证逻辑：

👉 is_relative_posix_path + segmentation 校验

---

### ✅ 6. 本地工作区同步

路径：

```
local/local_workspace/tasks/{task_id}/result_package/
```

必须存在：

```
results.json
meta.json
results/masks/
```

说明：

* staging → workspace 同步成功
* 不允许出现脏数据或残留

---

### ✅ 7. 覆盖保护（非常关键）

再次执行 exporter：

```bash
python scripts/local/exporter.py ...
```

必须报错：

```
禁止覆盖旧结果包
```

说明：

* exporter 已正确实现冻结策略
* 不允许覆盖 `.done` / `.zip`

实现位置：

👉 assert_no_existing_submitted_output

---

### ✅ 8. 日志生成

路径：

```
local/local_workspace/logs/{task_id}/
```

应存在：

```
local_operations_{task_id}_YYYYMMDD.jsonl
```

包含字段：

* event_type = local_export_mock
* event_status = succeeded

---

## 六、成功判定标准

全部满足即通过：

* ✅ ZIP + .done 成对出现
* ✅ ZIP 结构完全正确
* ✅ results.json 符合 schema
* ✅ meta.json 校验通过
* ✅ hash 校验一致
* ✅ 不允许覆盖历史结果
* ✅ 本地工作区同步成功
* ✅ 日志正常记录

---

## 七、常见错误与定位

### ❌ 1. operator 不一致

报错：

```
assigned_to 与 operator 不一致
```

原因：

* local_config.json operator 错误

---

### ❌ 2. sample_id_hash 不一致

原因：

* tasks.json 被修改（违规）

---

### ❌ 3. results_json_hash 错误

原因：

* 手动修改 results.json

---

### ❌ 4. segmentation mask 不存在

报错：

```
禁止伪造 mock mask
```

原因：

* task_package 中 mask 缺失

---

### ❌ 5. 重复导出失败

报错：

```
禁止覆盖旧结果包
```

原因：

* 已存在 .done / zip（设计符合预期）

---

## 八、交付说明

A 在完成以上校验后，即可进入：

➡️ Day7：中心接收（receiver.py）

无需修改 B 代码。

---

## 九、结论

本文档确保：

* Day6 本地导出完全符合冻结协议
* 输出结果可直接进入中心回收链路
* 不依赖任何在线系统
* 满足 Week1 全链路闭环要求

---
