# Day5_B 本地导入模块校验说明（交付给 A）

## 一、目的

本说明用于指导 A 在拉取 Day5_B 最新代码后，
对【本地导入模块（importer.py）】进行**真实数据校验**，确保模块符合平台协议并可进入后续流程。

---

## 二、代码版本说明

* 分支：`feature/B-day05-importer`
* 模块：`scripts/local/importer.py`
* 配置文件：`configs/local_workspace/local_config.json`

---

## 三、前置准备（必须完成）

### 1. 拉取代码

```bash
git checkout feature/B-day05-importer
git pull
```

---

### 2. 检查确认 local_config.json 存在

必须确认以下字段：

```json
"operator": "你的姓名（必须与任务包 assigned_to 一致）",
"sync": {
  "distribution_root": "Project_Sync/01_Distribution",
  "collection_root": "Project_Sync/02_Collection"
}
```

⚠️ 强约束：

* operator ≠ User_A / user001
* operator 必须和任务包 assigned_to 完全一致

---

### 3. 准备真实任务包（前面已经校验时已生成）

目录结构必须为：

```
Project_Sync/
└── 01_Distribution/
    └── {operator}/
        └── To_Be_Labeled/
            ├── XXX.zip
            └── XXX.zip.UPLOAD_DONE.flag
```

⚠️ 必须满足：

* ZIP 和 flag **成对存在**
* flag 必须是：

```
{zip_name}.UPLOAD_DONE.flag
```

❌ 禁止：

* 单独 ZIP
* 单独 flag
* 通用 UPLOAD_DONE.flag

---

## 四、执行导入

运行：

```bash
python scripts/local/importer.py
```

---

## 五、校验通过标准（必须全部满足）

### 1. 控制台输出

```
[OK] Day5 local import completed
```

---

### 2. 本地生成目录结构

```
local/local_workspace/tasks/{task_id}/
├── task_package/
├── working/
│   ├── local_status.json
│   └── import_summary.json
├── label_studio/
│   ├── import_payload.json
│   └── project_mapping.json
└── result_package/
```

---

### 3. 关键文件校验

#### （1）local_status.json

必须：

```json
"local_status": "not_started"
```

---

#### （2）import_payload.json

必须包含：

* image
* sample_id
* case_id
* task_type
* diagnosis_raw

---

#### （3）import_summary.json

必须包含：

* source_zip_sha256
* sample_id_hash
* total_samples

---

### 4. 幂等性校验（必须执行）

再次运行：

```bash
python scripts/local/importer.py
```

结果必须：

* 不重复导入
* 输出：

```
local_import_already_exists
```

---

## 六、异常校验（必须测试）

### 1. 删除 flag 再运行

结果：

* ❌ 不导入
* ❌ 报错

---

### 2. 修改 ZIP 文件名

结果：

* ❌ 不导入
* ❌ 报错

---

### 3. 修改 assigned_to ≠ operator

结果：

* ❌ 不导入
* ❌ 报错

---

## 七、边界保证（重点）

本模块必须保证：

* ❌ 不修改 tasks.json / meta.json
* ❌ 不写入 Master_Manifest.json
* ❌ 不写入 Receive_Registry.json
* ❌ 不生成 result_package.zip
* ❌ 不进入 merged / review / final

---

## 八、通过标准

当满足：

* 正常导入 ✔
* 幂等性 ✔
* 异常拦截 ✔
* 无越权写入 ✔

则判定：

```
Day5_B 验收通过，可以进入 Day5 后续流程
```

---

## 九、补充说明

本模块职责仅为：

> 「中心 → 本地」任务包导入与校验

不包含：

* 标注
* 导出
* 回传
* 合并

---

## 十、如出现问题

优先检查：

1. ZIP + flag 是否配对
2. operator 是否一致
3. ZIP 是否损坏
4. 路径是否为相对 POSIX

---
