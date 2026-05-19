# Day3_B 校验说明文档（中心拆包 / splitter）

## 一、目的

本说明用于指导 A 在拉取 Day3 最新代码后，完成 **真实数据下的中心拆包校验**，并确认 Day3 是否达到冻结标准，从而进入 Day4。

---

## 二、本次交付内容（B 提供）

本次提交实现内容：

* scripts/center/splitter.py
* scripts/center/validators/validate_day3.py
* 依赖 shared：

  * validators.py
  * hash_utils.py
  * path_utils.py

功能：

* 从 central_data_pool/samples_index.json 拆包
* 生成 task_package 目录结构（.tmp）
* 写入：

  * tasks.json
  * meta.json
  * README.txt
* 拷贝 images / masks
* 执行完整一致性校验（双校验）

---

## 三、输入数据要求（A 需要准备）

必须已有：

```
center/central_data_pool/
├── images/
├── masks/
└── metadata/
    ├── samples_index.json
    ├── preprocess_manifest.json
```

要求：

* 已通过 Day2 preprocess
* samples_index.json 无重复 sample_id
* image_path / mask_path 可访问

---

## 四、运行 splitter（真实数据）

在项目根目录执行：

```bash
python scripts/center/splitter.py
```

如需覆盖 tmp 目录（仅允许 tmp）：

```bash
python scripts/center/splitter.py --overwrite-tmp
```

---

## 五、输出结构（必须严格一致）

生成目录：

```
center/task_packages/.tmp/
  ├── {task_id}_{task_type}_{assigned_to}/
  │   └── task_package/
  │       ├── tasks.json
  │       ├── meta.json
  │       ├── README.txt
  │       ├── images/
  │       └── masks/（segmentation 必须存在）
```

⚠️ 注意：

* 当前阶段 **不生成 ZIP**
* 不生成 UPLOAD_DONE.flag
* 不写 Master / Receive

---

## 六、执行验收脚本

```bash
python scripts/center/validators/validate_day3.py
```

必须输出：

```
[OK] ...
[OK] Day3 validation passed
```

否则视为失败。

---

## 七、人工重点检查项（必须逐条确认）

### 1. tasks.json

* 顶层是数组
* 每个 item 包含：

  * sample_id
  * case_id
  * image
  * mask（按 task_type 规则）
* 单文件内 task_type 唯一
* sample_id + task_type 无重复

---

### 2. meta.json

必须满足：

* total_samples == len(tasks.json)
* sample_id_hash 可复算一致
* assigned_to == assigned_to_snapshot
* is_rework == false
* parent_task_id == null

---

### 3. 路径规范

* image: `images/xxx.jpg`
* mask: `masks/xxx.png`
* 全部为相对路径
* 不允许：

  * 绝对路径
  * Windows 路径
  * URL

---

### 4. 文件完整性

必须存在：

* 所有 image 文件
* segmentation 必须有 mask
* README.txt 非空

---

### 5. README 内容

必须包含：

```
task_id
task_type
assigned_to
```

---

## 八、通过标准（满足全部才算通过）

满足以下全部条件：

* validate_day3.py 完全通过
* 无异常 / 无报错
* 任务包结构正确
* 样本数量正确
* hash 一致
* 路径规范正确
* 无重复 / 无缺失

👉 才允许进入 Day4

---

## 九、禁止行为（非常重要）

A 在校验过程中：

禁止：

* 修改 tasks.json
* 修改 meta.json
* 修改 sample_id
* 手动修补任务包

如发现问题：

👉 必须打回给 B 修复

---

## 十、Day3 → Day4 交接说明

Day3 完成后：

下一步由 B 实现：

* ZIP 打包（task_package.zip）
* UPLOAD_DONE.flag 生成
* 分发到 Project_Sync

A 不负责 ZIP 生成逻辑

---

## 十一、结论

本阶段目标：

✔ 拆包正确
✔ 数据一致
✔ 协议不破坏

不是：

❌ 分发
❌ 回收
❌ merge
❌ final

---
