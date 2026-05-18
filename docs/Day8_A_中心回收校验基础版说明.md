# Day8 同学 A：中心回收校验基础版说明文档

---

## 一、任务目标

在 Week1 已完成“中心接收登记（pending_validation）”的基础上，实现 Day8 要求的：

> **中心回收基础校验（Basic Validation）**

确保所有从本地导出的结果包在进入中心流程前具备最基本的合法性。

---

## 二、功能范围（严格边界）

### ✅ Day8 要做

1. 扫描 `Project_Sync/02_Collection/{operator}/Submitted/`
2. 识别 `.zip + .done` 成对结果包
3. 对每个结果包执行基础校验：

#### 文件级校验

* ZIP 文件存在且可解压
* `.done` 文件存在且与 ZIP 同名

#### 结构校验

* ZIP 内必须包含：

  * `result_package/meta.json`
  * `result_package/results.json`
* ZIP 内所有路径合法（禁止绝对路径、.. 等）

#### 元数据校验

* `result_package_id` 与 ZIP 文件名一致
* `task_id` 与 ZIP 文件名一致
* `task_type` 与 task_id 前缀一致
* `module == task_type`

#### Master 校验

* `task_id` 必须存在于 `Master_Manifest.json`
* `task_type` 与 Master 一致
* `module` 与 Master 一致

---

### ❌ Day8 不做（非常关键）

* ❌ 不入池（不写 central_result_pool）
* ❌ 不 merge
* ❌ 不生成 review_queue
* ❌ 不移动 processed
* ❌ 不做质量评估

---

## 三、输入文件

```text
Project_Sync/02_Collection/{operator}/Submitted/{result_package_id}.zip
Project_Sync/02_Collection/{operator}/Submitted/{result_package_id}.done
center/manifests/Master_Manifest.json
```

---

## 四、输出文件

### 1. 接收登记表

```text
center/manifests/Receive_Registry.json
```

### 2. 错误日志

```text
center/logs/center/receive/central_receive_errors_{YYYYMMDD}.jsonl
```

### 3. 成功操作日志

```text
center/logs/center/receive/central_receive_operations_{YYYYMMDD}.jsonl
```

---

## 五、核心状态定义

### 合法结果包（校验通过）

```json
"validation_status": "validation_passed",
"import_status": "not_imported"
```

---

### 非法结果包（拒收）

不会进入 Receive_Registry，只写错误日志：

```json
"failure_reason": "xxx"
```

---

## 六、Day8 核心实现逻辑

### 1. 扫描结果包

```text
scan_submitted_result_packages()
```

识别 `.zip + .done` 配对。

---

### 2. 基础校验流程

```text
validate_day8_zip_done_pair()
assert_result_package_basic_zip()
read_result_meta_from_zip()
read_results_json_from_zip()
validate_day8_against_zip_and_master()
```

---

### 3. 生成记录

```text
build_receive_record()
```

写入：

* task_id / task_type / module
* operator / export_version
* sample_count 等统计字段
* hash 字段

---

### 4. Week1 → Day8 升级机制（重点）

```text
merge_day8_validation_result()
```

#### 行为：

| 原状态                | 新状态               |
| ------------------ | ----------------- |
| pending_validation | validation_passed |
| validation_passed  | 跳过                |

---

## 七、验收标准

### ✅ 必须满足

1. 所有合法包：

```json
"validation_status": "validation_passed"
```

2. 不存在：

* `pending_validation`
* 入池路径
* merge 结果
* review_queue

3. Receive_Registry 字段完整：

* sample_count
* completed_count
* invalid_count
* sample_id_hash
* results_json_hash

---

### ❌ 失败情况

以下情况必须拒收：

| 错误类型           | failure_reason       |
| -------------- | -------------------- |
| ZIP 损坏         | zip_corrupted        |
| 缺 meta.json    | meta_missing         |
| 缺 results.json | results_json_missing |
| task 不存在       | task_not_in_master   |
| module 错误      | module_mismatch      |

---

## 八、运行方式

### Dry-run（推荐先跑）

```bash
python scripts/center/receiver.py --config configs/project/center_receive_merge_config.json --dry-run
```

---

### 正式运行

```bash
python scripts/center/receiver.py --config configs/project/center_receive_merge_config.json
```

---

## 九、PR 提交信息

* 分支：`feature/A-day08-receiver-validation`
* Commit：

```text
feat(center): implement Day8 receiver basic validation
```

* 是否修改协议：否
* 是否修改 shared：否
* 是否提交运行数据：否
* Reviewer：同学 B

---

## 十、总结

Day8 实现了中心回收的第一道“质量闸门”，确保：

* 数据结构合法
* 任务匹配正确
* 元数据一致

并为后续：

```text
Day11 入池 → Day13 merge → Day15 review
```

提供可靠输入。

---
