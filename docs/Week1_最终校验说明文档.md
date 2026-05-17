# Week1 最终验收说明文档

## 一、文档目的

本说明用于指导 A 在本地环境中：

* 正确执行 Week1 全链路
* 避免常见错误
* 成功运行 `week1_acceptance_check.py`
* 完成 Week1 最终验收

---

## 二、核心前提（必须理解）

Week1 验收脚本会做一个**强约束检查**：

👉 **Master_Manifest.json 中的所有任务，都必须有对应 result_package.zip + .done**

否则会报错：

```
存在 Master 任务没有回传 result_package.zip + .done
```

该逻辑来自验收脚本：

* 会收集 Master 中所有 task_id
* 会收集所有 result_package 中的 task_id
* 两者必须完全一致 

---

## 三、运行前准备

### 1. 确保代码版本一致

必须包含以下文件：

* scripts/center/receiver.py
* scripts/tools/week1_acceptance_check.py 
* scripts/shared/*（全部）

---

### 2. 清理旧数据（强烈建议）

在项目根目录执行（CMD）：

```powershell
# 清理中心结果相关
Remove-Item -Recurse -Force center/central_result_pool -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force center/received_packages -ErrorAction SilentlyContinue
Remove-Item -Force center/manifests/Receive_Registry.json -ErrorAction SilentlyContinue

# 清理回传区
Remove-Item -Recurse -Force Project_Sync/02_Collection -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path Project_Sync/02_Collection | Out-Null
```

👉 目的：避免旧数据影响验收

---

### 3. 确保 Master 已完成 Day4

必须满足：

* 已完成 splitter（Day3）
* 已完成分发（Day4）
* Master_Manifest.json 已存在
* Project_Sync/01_Distribution 已生成 ZIP + flag

---

## 四、执行步骤（必须按顺序）

---

## Step 1：本地导入 + 导出（所有任务）

⚠️ **关键点：必须导出所有任务，而不是只导出一个**

---

### 1. 查看所有任务

```powershell
python -c "import json; m=json.load(open('center/manifests/Master_Manifest.json',encoding='utf-8')); [print(t['task_id'], t['task_type'], t['assigned_to']) for t in m['tasks']]"
```

---

### 2. 按 operator 分别执行

#### （1）张三

修改：

```json
configs/local_workspace/local_config.json
```

```json
"operator": "张三"
```

执行：

```powershell
$tasks = python -c "import json; m=json.load(open('center/manifests/Master_Manifest.json',encoding='utf-8')); [print(t['task_id']) for t in m['tasks'] if t['assigned_to']=='张三']"

foreach ($taskId in $tasks) {
  python scripts\local\importer.py --config configs\local_workspace\local_config.json --task-id $taskId
}

foreach ($taskId in $tasks) {
  python scripts\local\exporter.py --config configs\local_workspace\local_config.json --task-id $taskId
}
```

---

#### （2）李四（DET）

把 local_config.json 中的 "operator" 改为 "李四"

```json
"operator": "李四"
```

执行:

```powershell
$tasks = python -c "import json; m=json.load(open('center/manifests/Master_Manifest.json',encoding='utf-8')); [print(t['task_id']) for t in m['tasks'] if t['assigned_to']=='李四']"

foreach ($taskId in $tasks) {
  python scripts\local\importer.py --config configs\local_workspace\local_config.json --task-id $taskId
}

foreach ($taskId in $tasks) {
  python scripts\local\exporter.py --config configs\local_workspace\local_config.json --task-id $taskId
}
```

---

#### （3）王五（CAP）

把 local_config.json 中的 "operator" 改为 "王五"

```json
"operator": "王五"
```

执行:

```powershell
$tasks = python -c "import json; m=json.load(open('center/manifests/Master_Manifest.json',encoding='utf-8')); [print(t['task_id']) for t in m['tasks'] if t['assigned_to']=='王五']"

foreach ($taskId in $tasks) {
  python scripts\local\importer.py --config configs\local_workspace\local_config.json --task-id $taskId
}

foreach ($taskId in $tasks) {
  python scripts\local\exporter.py --config configs\local_workspace\local_config.json --task-id $taskId
}
```

---

## Step 2：中心接收（Day7）

先清除旧的Receive：

```powershell
Remove-Item center\manifests\Receive_Registry.json -Force -ErrorAction SilentlyContinue
```

然后重新运行：

```cmd
python scripts\center\receiver.py --config configs\local_workspace\local_config.json
```

---

### 正确输出应类似：

```
[OK] Day7 receiver 扫描完成
[OK] 新增 Receive 记录: N
[OK] 已存在跳过: 0
[OK] 失败跳过: 0
```

---

### Receive 状态必须为：

```json
validation_status = "pending_validation"
import_status = "not_imported"
```

👉 这是 Day7 强约束 

---

## Step 3：运行 Week1 验收

```cmd
python scripts\tools\week1_acceptance_check.py
```

---

## 五、成功结果（必须完全一致）

---

### 1. 每个结果包输出：

```
[OK] Week1 package passed: RESULT_XXX
```

---

### 2. 最终总结：

```
[SUMMARY] Week1 acceptance passed. checked=XXX
```

---

## 六、常见错误 & 解决方案

---

### ❌ 错误 1：missing_result_tasks

```
存在 Master 任务没有回传 result_package.zip + .done
```

### 原因：

* 没有导出所有任务（只导出了一部分）

### 解决：

👉 必须对所有 operator 执行 importer + exporter

---

### ❌ 错误 2：ModuleNotFoundError: scripts.shared

### 原因：

没有在项目根目录运行

### 解决：

```cmd
cd 项目根目录
python scripts\tools\week1_acceptance_check.py
```

---

### ❌ 错误 3：DET / CAP 导出失败

```
本地任务目录不存在
```

### 原因：

没有先执行 importer

### 解决：

👉 必须先 importer，再 exporter

---

### ❌ 错误 4：.done 缺失

```
缺少 .done 文件
```

### 原因：

exporter 没执行成功 / 手动删了

---

## 七、最终验收标准

必须全部满足：

* 所有 task_id 均有 result_package.zip + .done
* Receive_Registry.json 正确记录
* validation_status = pending_validation
* import_status = not_imported
* 无任何 AssertionError
* 输出：

```
[SUMMARY] Week1 acceptance passed
```

---

## 八、结论

当上述流程全部通过后：

✅ Week1 可以正式冻结
✅ 可以进入 Week2（中心强校验 + 入池 + merge）

---

## 九、特别提醒

👉 Week1 验收不是“单任务测试”，而是：

**全量任务一致性验证**

必须保证：

```
Master == Result Packages（100% 覆盖）
```

否则验收一定失败（设计如此，不是 bug）

---
