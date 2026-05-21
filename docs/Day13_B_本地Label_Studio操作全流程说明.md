# Day13 本地标注链路（Label Studio → results.json → result_package.zip + .done）复现操作说明

## 【一、目标】

在 A 的电脑上完整跑通以下流程：

task_package
→ Label Studio 导入
→ 人工标注
→ Label Studio 导出 JSON
→ 转换为 results.json
→ exporter.py 打包
→ 生成 result_package.zip + .done

最终得到 SEG / DET / CAP 三个标准交付结果包。

---

## 【二、环境准备（必须完成）】

### 1. Python 环境
python >= 3.9

安装依赖：
```bash
pip install label-studio pillow
```

---

### 2. 项目目录结构必须如下（关键）

```bash
project_root/
├── local/
│   ├── local_workspace/
│   │   └── tasks/
│   │       ├── SEG_20260425_001/
│   │       ├── DET_20260425_001/
│   │       └── CAP_20260425_001/
│   └── label_studio/
│       ├── configs/
│       ├── converted_results/
|       ├── exports/
|       ├── import_payloads/
|       └── scripts/
├── scripts/
│   └── local/
│       ├── label_studio_adapter.py
│       ├── exporter.py
```

---

### 3. 必须包含以下文件（来自 B 的交付）

* scripts\local\label_studio_adapter.py
* scripts\local\exporter.py
* local\label_studio\scripts\run_ls_export_to_results.py
* scripts\local\run_image_server.py
* local\label_studio\configs\label_config.xml

---

## 【三、启动图片服务（必须）】

作用：让 Label Studio 能加载本地图片

执行：

python scripts/local/run_image_server.py

成功标志：
```bash
[OK] Serving ... at http://127.0.0.1:8766
```

注意：启动成功后该终端保留，另开一个新的终端完成下面的操作
---

## 【四、生成 Label Studio 导入文件】

对每个任务执行（示例 SEG）：
```bash
python scripts/local/label_studio_adapter.py tasks-to-ls 
--task-dir local/local_workspace/tasks/SEG_20260425_001 
--out local/label_studio/import_payloads/SEG_20260425_001_import_payload.json
```

成功标志：
```bash
[OK] wrote Label Studio import payload
```

---

## 【五、启动 Label Studio】

执行：

label-studio start

浏览器打开：

http://localhost:8080

---

## 【六、创建项目】

1. 点击：Create Project

2. Labeling Config：

粘贴 local\label_studio\configs\label_config.xml 内容

3. 导入数据：

Import → Upload Files
上传：
```bash
local/label_studio/import_payloads/SEG_20260425_001_import_payload.json
```

成功标志：

* 页面出现任务列表
* 图片正常显示

---

## 【七、标注规则（必须严格遵守）】

SEG：

二选一：

① 有 mask
勾选：已有 mask 可沿用

② 无 mask
使用 Polygon 画病灶

禁止：不画 polygon 且不选 mask

---

DET：

二选一：

① 有目标
画 Rectangle 框（系统会自动根据已有mask生成病灶框，可人工微调或直接保存）

② 无目标
选择 negative_confirmed

禁止：既画框又选 negative

---

CAP：

必须填写：

reviewed（人工最终结果）
prompt_version（必须 = caption_prompt_v1）

---

## 【八、导出 Label Studio 结果】

Export → JSON

保存为：
```bash
local\label_studio\exports\SEG_20260425_001_export.json
```

---

## 【九、转换为 results.json】

执行：
```bash
python local/label_studio/scripts/run_ls_export_to_results.py 
--task-id SEG_20260425_001 
--export-name SEG_20260425_001_export.json
```

成功标志：
```bash
[OK] results.json 已生成
```

输出路径：
```bash
local/local_workspace/tasks/.../result_package/results.json
```

---

## 【十、导出结果包】

注意：不同任务在导出结果包之前需要在configs\local_workspace\local_config.json中修改对应任务的operator，否则任务结果包会导出失败

执行：
```bash
python scripts/local/exporter.py 
--task-id SEG_20260425_001
```

成功标志：

[OK] 导出完成

生成：
```bash
Project_Sync/.../Submitted/
├── RESULT_XXX.zip
└── RESULT_XXX.done
```

---

## 【十一、重复执行三个任务】

依次执行：
```bash
SEG_20260425_001
DET_20260425_001
CAP_20260425_001
```

---

## 【十二、最终验收标准（必须全部满足）】

1. 生成三个 ZIP：

SEG / DET / CAP 各一个

2. ZIP 内结构必须为：
```bash
result_package/
├── meta.json
├── results.json
├── README.txt
└── results/
└── masks/*.png（仅 SEG）
```

3. 必须存在 .done 文件

4. results.json 内容正确：

* SEG：包含 mask_path
* DET：包含 boxes / negative_confirmed
* CAP：包含 generated / reviewed / prompt_version

---

## 【十三、常见问题排查】

1. 图片打不开
   → 未启动 image server

2. results.json 生成失败
   → SEG 没画 polygon 或未选 mask

3. CAP 报错
   → prompt_version 不等于 caption_prompt_v1

4. exporter 报错
   → operator 不匹配 / sample_id 不一致

5. ZIP 无法生成
   → export_version 未修改（重复导出）

---

## 【十四、交付说明】

Day13 本地标注链路（Label Studio → results.json → result_package.zip + .done）已完成并冻结。

请你在本地按文档完整跑一遍 SEG / DET / CAP 三个任务的导入 → 标注 → 导出 → 打包流程，确认：

1. Label Studio 能正确加载图片
2. 标注后可生成合法 results.json
3. exporter.py 能生成标准 result_package.zip + .done
4. 三个任务均成功

通过后，你再继续进行：

receiver → result_pool_writer → merger

完成中心端入池与合并链路验证。
