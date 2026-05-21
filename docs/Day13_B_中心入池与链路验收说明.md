# Day13 中心入池与链路验收说明（A 侧执行文档）

## 【一、目标】

在 B 已完成 Day13 本地链路交付的基础上，由 A 在中心端完成以下流程闭环：

三个 result_package.zip + .done
→ receiver.py
→ Receive_Registry.json validation_passed
→ result_pool_writer.py 入池
→ Master.result_status = collected
→ merger.py
→ merged/{sample_id}.json
→ review_queue

最终完成 Day13 从“本地标注结果”到“中心入池+合并”的全链路验收。

---

## 【二、当前交付边界】

B 已冻结范围：
```bash
label_studio_adapter.py
exporter.py
label_config.xml
run_ls_export_to_results.py
run_image_server.py
以及三个中心交付结果包
```

B 已完成：

真实 Label Studio 导出 → 转换为冻结 results.json
SEG / DET / CAP 三类结果结构符合协议
exporter.py 可生成标准 result_package.zip + .done

说明：

results.json 由 label_studio_adapter.py 生成，结构已冻结 
结果包由 exporter.py 校验并打包输出 

---

## 【三、A 需要处理的核心任务】

A 负责完成中心端以下模块：
```bash
receiver.py
result_pool_writer.py（必须修改）
Master_Manifest.json 状态更新
Receive_Registry.json 状态更新
merger.py
```

重点：**result_pool_writer.py 必须改为冻结入池结构**

---

## 【四、输入数据准备】

将 B 交付的结果包放入：
```bash
Project_Sync/02_Collection/{operator}/Submitted/
```

示例：
```bash
Project_Sync/02_Collection/张三/Submitted/RESULT_SEG_20260425_001_张三_v1.zip
Project_Sync/02_Collection/张三/Submitted/RESULT_SEG_20260425_001_张三_v1.done

Project_Sync/02_Collection/李四/Submitted/RESULT_DET_20260425_001_李四_v1.zip
Project_Sync/02_Collection/王五/Submitted/RESULT_CAP_20260425_001_王五_v1.zip
```

必须满足：

1. ZIP 和 .done 同名
2. 位于同一 Submitted 目录
3. operator 与目录一致

---

## 【五、运行 receiver.py】

执行：
```bash
python scripts/center/receiver.py 
--config configs/project/center_receive_merge_config.json
```

成功标志：

Receive_Registry.json 中三条记录：
```bash
validation_status = validation_passed
```

如果失败，重点检查：

* operator 目录是否匹配
* ZIP 与 .done 是否同名
* results_json_hash 是否一致
* sample_id_hash 是否一致

---

## 【六、result_pool_writer.py 必须修改】

当前如果仍是旧结构（错误）：

center/central_result_pool/{module}/{result_package_id}.json

必须改为冻结结构（正确）：

center/central_result_pool/{module}/{task_id}/results.json
center/central_result_pool/{module}/{task_id}/package_meta.json

---

## 【七、入池代码核心修改要求】

路径函数必须改为：
```bash
def result_task_dir(root, record):
return root / record["module"] / record["task_id"]

def result_record_path(root, record):
return result_task_dir(root, record) / "results.json"

def result_package_meta_path(root, record):
return result_task_dir(root, record) / "package_meta.json"
```

写入逻辑必须为：
```bash
task_dir = result_task_dir(result_pool_root, record)

if task_dir.exists():
raise Exception("禁止覆盖已有任务结果")

task_dir.mkdir(parents=True, exist_ok=True)
```

写入：

results.json
package_meta.json

---

## 【八、执行入池】
```bash
python scripts/center/result_pool_writer.py 
--config configs/project/center_receive_merge_config.json
```

成功标志：

[OK] imported: 3
[OK] failed: 0

并生成：
```bash
center/central_result_pool/segmentation/SEG_xxx/results.json
center/central_result_pool/detection/DET_xxx/results.json
center/central_result_pool/caption/CAP_xxx/results.json
```

---

## 【九、状态检查】

Receive_Registry.json：
```bash
validation_status = validation_passed
import_status = imported
```

Master_Manifest.json：
```bash
result_status = collected
```

---

## 【十、执行 merge】
```bash
python scripts/center/merger.py 
--config configs/project/center_receive_merge_config.json 
--replace-generated
```

成功标志：

生成：

merged/{sample_id}.json
review_queue/{sample_id}.json

---

## 【十一、最终验收标准】

必须全部满足：

1. 三个结果包通过 receiver 校验
2. 入池结构为 {module}/{task_id}/results.json
3. 不存在扁平结构文件
4. Receive_Registry.json 状态正确
5. Master.result_status = collected
6. merger 成功运行
7. merged 文件生成
8. review_queue 生成

---

## 【十二、常见问题】

1. receiver 报 operator 错误
   → 检查目录名是否一致

2. hash 校验失败
   → 不允许手改 ZIP，必须重新导出

3. merge 报错
   → result_pool_writer 未改结构

4. SEG mask 错误
   → mask_path 指向不存在文件

---

## 【十三、A 的最终输出结论】

A 完成后必须确认：

B 交付的 Day13 本地结果包已通过中心 receiver 校验；
result_pool_writer 已按冻结结构完成入池；
Master 与 Receive 状态闭环正确；
merger 成功生成 merged 与 review_queue；
Day13 全链路验收通过。

---

## 【十四、职责边界】

B 不再修改中心逻辑

A 负责：

receiver
result_pool_writer
入池结构
merge
review_queue

B 负责：

Label Studio → results.json → result_package.zip + .done

---
