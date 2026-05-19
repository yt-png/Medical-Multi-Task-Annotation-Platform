# Day11 / Day12 交付运行说明

中心结果池按 sample_id 合并与 review_queue 生成

版本：v1.0  
生成日期：2026-05-19

---

## 1. 交付范围

- Day11：实现按 sample_id 聚合 segmentation、detection、caption、downsample 与 central_data_pool 基础信息，生成 merged/{sample_id}.json。
- Day12：在 Day11 基础上生成 review_queue/{sample_id}.json，并生成 merge_error_report.json，同时把完整样本对应任务推进到 Master.center_status = to_review。
- 本交付文件只覆盖 merge 与 review_queue 生成，不覆盖 Day15 review_results.json，也不覆盖 Day17/18 final.json。
- 本阶段不允许从本地 results.json、Submitted 目录、Receive_Registry 直接生成 final，也不允许把任务写成 completed。

---

## 2. 本次交付文件清单

| 文件 | 应放置位置 | 用途 |
|---|---|---|
| merger.py | scripts/center/merger.py | Day11/Day12 主脚本：读取 central_result_pool，生成 merged、review_queue、merge_error_report，并更新 Master。 |
| center_receive_merge_config.json | configs/project/center_receive_merge_config.json | 中心回收与 merge 配置文件，定义输入、输出、merge 目录、状态策略和路径规则。 |
| repair_result_pool_layout.py | scripts/center/repair_result_pool_layout.py | 兼容修复工具：把旧版扁平结果池迁移为 Day10 冻结结构。仅历史数据修复时使用。 |
| repair_master_status_from_result_pool.py | scripts/center/repair_master_status_from_result_pool.py | 一致性修复工具：当结果已入池但 Master 未同步 collected 时使用。仅修复状态，不替代正常流程。 |

---

## 3. 平台工作流位置

中心回收校验  
→ central_result_pool 入池  
→ Day11 按 sample_id merge  
→ Day12 review_queue  
→ Day15 review_results.json  
→ Day17/18 final.json 导出  

- Day11/Day12 的输入只能来自已经入池的 central_result_pool 与 central_data_pool。
- Day11/Day12 不读取 Project_Sync/02_Collection/Submitted。
- Day11/Day12 不直接生成 final.json。
- merged 只表示多模块合并完成，不表示审核通过。

---

## 4. 运行前目录要求

```bash
project_root/
├── center/
│   ├── central_data_pool/
│   │   ├── metadata/samples_index.json
│   │   └── downsample_candidates/
│   │       ├── x2/
│   │       └── x4/
│   ├── central_result_pool/
│   │   ├── segmentation/{task_id}/results.json
│   │   ├── segmentation/{task_id}/package_meta.json
│   │   ├── detection/{task_id}/results.json
│   │   ├── detection/{task_id}/package_meta.json
│   │   ├── caption/{task_id}/results.json
│   │   └── caption/{task_id}/package_meta.json
│   └── manifests/Master_Manifest.json
├── configs/project/center_receive_merge_config.json
└── scripts/center/merger.py
```

- central_result_pool 必须是 Day10 冻结结构：{module}/{task_id}/results.json + package_meta.json。
- 如果还存在 segmentation/*.json、detection/*.json、caption/*.json 这种扁平文件，需要先运行 repair_result_pool_layout.py 修复。
- Master 中参与 merge 的任务必须满足 result_status = collected，且 center_status 不能是 undistributed、reworking、completed。

---

## 5. 配置文件要求

| 配置项 | 要求值 / 说明 |
|---|---|
| project_id | MED_IMG_V1 |
| schema_version | v1 |
| input.master_manifest | center/manifests/Master_Manifest.json |
| input.central_data_pool | center/central_data_pool |
| output.central_result_pool | center/central_result_pool |
| merge.one_file_per_sample | true |
| merge.merged_dir | center/central_result_pool/merged |
| merge.review_queue_dir | center/central_result_pool/review_queue |
| merge.merge_error_report | center/central_result_pool/merged/merge_error_report.json |
| duplicate_policy.allow_overwrite | false |
| duplicate_policy.duplicate_key | task_id\|operator\|export_version |
| status_policy.max_center_status | to_review |
| status_policy.forbid_completed_update | true |
| path_rules.path_separator | / |

---

## 6. 标准运行流程

### 6.1 备份关键状态文件

```bash
copy center\manifests\Master_Manifest.json center\manifests\Master_Manifest.backup_before_day12.json
```

- 如果使用 PowerShell，也可以使用 Copy-Item。备份是为了避免误操作后无法回滚 Master 状态。

---

### 6.2 先执行 dry-run

```bash
python scripts/center/merger.py --config configs/project/center_receive_merge_config.json --dry-run
```

- dry-run 只检查输入、配置、Master 状态、结果池结构、样本完整性，不写入 merged、review_queue、merge_error_report、Master、logs。
- 如果 dry-run 报错，禁止直接加 --replace-generated，应先根据错误修复输入或状态。

---

### 6.3 首次正式运行

```bash
python scripts/center/merger.py --config configs/project/center_receive_merge_config.json
```

- 首次运行时，如果 merged、review_queue、merge_error_report 不存在，会直接生成。
- 正式运行会写入 merged、review_queue、merge_error_report，并可能更新 Master.center_status。

---

### 6.4 重新生成 Day12 输出

```bash
python scripts/center/merger.py --config configs/project/center_receive_merge_config.json --replace-generated
```

- --replace-generated 只删除并重建 merged/*.json、review_queue/*.json 和 merge_error_report.json。
- --replace-generated 不删除 central_result_pool 原始入池结果，不修改 segmentation/detection/caption 原始 results。

---

## 7. 可选修复流程

### 7.1 修复旧版扁平结果池结构

- 适用场景：merger.py 报错提示检测到非冻结结构的中心结果池文件。

```bash
python scripts/center/repair_result_pool_layout.py --root center/central_result_pool --dry-run
python scripts/center/repair_result_pool_layout.py --root center/central_result_pool
```

- 该脚本会把旧文件迁移为 {module}/{task_id}/results.json + package_meta.json，并把旧扁平文件移动到 _legacy_flat_archived。
- 这是历史兼容修复，不应替代 Day10 result_pool_writer.py 的正常入池逻辑。

---

### 7.2 修复 Master 与结果池状态不一致

- 适用场景：central_result_pool 已存在结果，但 merger.py 报错 Master.result_status 不是 collected。

```bash
copy center\manifests\Master_Manifest.json center\manifests\Master_Manifest.backup_before_repair.json
python scripts/center/repair_master_status_from_result_pool.py
python scripts/center/repair_master_status_from_result_pool.py --apply
```

- 该脚本只用于把已经入池成功但 Master 未同步的任务补回 collected。
- 如果任务处于 completed 或 reworking，脚本会拒绝自动修复，避免破坏审核或返工流程。
- 修复后重新执行 merger.py 的 dry-run，再正式运行。

---

## 8. 运行后输出产物

| 产物 | 路径 | 说明 |
|---|---|---|
| merged 样本文件 | center/central_result_pool/merged/{sample_id}.json | 每个 sample_id 一个合并文件。缺模块、冲突、downsample 缺失时也会生成 merged 文件，但不能进入 review_queue。 |
| review_queue 样本文件 | center/central_result_pool/review_queue/{sample_id}.json | 只有 merge_status = merged 且 can_enter_review_queue = true 的样本才会进入。 |
| merge_error_report.json | center/central_result_pool/merged/merge_error_report.json | 记录总样本数、完整数、缺模块数、冲突数、downsample 缺失数、孤儿结果数和错误列表。 |
| 中心日志 | center/logs/center/merge/central_merge_operations_YYYYMMDD.jsonl | 记录本次 merge 成功事件。日志只追加，不作为状态机。 |
| Master_Manifest.json | center/manifests/Master_Manifest.json | 完整进入 review_queue 的任务会推进到 center_status = to_review。 |

---

## 9. merged/{sample_id}.json 字段要求

| 字段 | 要求 |
|---|---|
| sample_id / case_id / check_category / image_id | 来自 central_data_pool/metadata/samples_index.json。 |
| image | 统一写为 images/{sample_id}.jpg 或 images/{sample_id}.png。 |
| segmentation | 必须包含 polygons 和 mask_path。合并后 mask_path 统一写为 masks/{sample_id}.png。 |
| detection | 必须包含 boxes 和 negative_confirmed。negative_confirmed 为 true 时 boxes 必须为空；为 false 时 boxes 不能为空。 |
| caption | 必须包含 generated、reviewed、prompt_version，且均为非空字符串。 |
| downsample | S 级为 {enabled:false, reason:resolution_level_s}；M 级要求 x2；L 级要求 x2 和 x4。 |
| source | 记录 segmentation_task_id、detection_task_id、caption_task_id。 |
| source_detail | 记录 result_package_id、pool_record_path、export_version、imported_at、operator、timestamp 等追溯信息。 |
| merge_status | 只能按实际情况为 merged、incomplete、conflict、downsample_missing。 |
| can_enter_review_queue | 仅 merge_status = merged 时为 true。 |

---

## 10. review_queue/{sample_id}.json 字段要求

- review_queue 文件以 merged 文件为基础复制。
- 必须额外包含 review_queue_item_path、merged_path、queued_at。
- merged 目录中的原始合并文件不应包含 review_queue_item_path、merged_path、queued_at。
- review_queue 只表示等待中心审核，不表示审核通过。

---

## 11. Day11 / Day12 验收标准

| 验收项 | 通过标准 |
|---|---|
| Day11 merged 文件 | 每个 samples_index 中的 sample_id 都生成一个 merged/{sample_id}.json。 |
| 缺模块处理 | 缺 segmentation、detection 或 caption 的样本 merge_status = incomplete，写入 merge_error_report，不进入 review_queue。 |
| 冲突处理 | 同一 sample_id + module 出现多个结果时 merge_status = conflict，写入 conflicts，不静默覆盖。 |
| downsample 处理 | M/L 缺少必要 downsample 时 merge_status = downsample_missing，不进入 review_queue。 |
| review_queue | 只包含 merge_status = merged 且 can_enter_review_queue = true 的完整样本。 |
| Master 状态 | 进入 review_queue 的相关 task_id 推进到 center_status = to_review，不写 completed。 |
| final 边界 | Day12 不生成 final.json。 |
| 路径规则 | 所有输出路径使用 /，不得出现绝对路径、URL、Windows 反斜杠。 |
| 错误报告 | merge_error_report.json 能准确反映 total、merged、incomplete、conflict、downsample_blocked、orphan_result。 |

---

## 12. 快速检查命令

- 检查 merged 数量：

```bash
python -c "from pathlib import Path; print(len(list(Path('center/central_result_pool/merged').glob('*.json')))-1)"
```

- 检查 review_queue 数量：

```bash
python -c "from pathlib import Path; print(len(list(Path('center/central_result_pool/review_queue').glob('*.json'))))"
```

- 查看错误报告摘要：

```bash
python -c "import json; p='center/central_result_pool/merged/merge_error_report.json'; r=json.load(open(p,encoding='utf-8')); print({k:r[k] for k in ['total_samples','merged_complete_samples','incomplete_samples','conflict_samples','downsample_blocked_samples','review_queue_samples','orphan_result_samples']})"
```

- 抽查 review_queue 是否只包含完整样本：

```bash
python -c "import json; from pathlib import Path; bad=[]
for p in Path('center/central_result_pool/review_queue').glob('*.json'):
    x=json.load(open(p,encoding='utf-8'))
    if x.get('merge_status')!='merged' or x.get('can_enter_review_queue') is not True: bad.append(p.name)
print('bad=', bad[:10], 'count=', len(bad))"
```

---

## 13. 常见错误与处理

| 错误现象 | 原因 | 处理方式 |
|---|---|---|
| 检测到非冻结结构的中心结果池文件 | 结果池仍是旧版扁平 JSON。 | 先运行 repair_result_pool_layout.py，之后再运行 merger.py。 |
| 只有 Master.result_status=collected 的任务结果允许参与 merge | 结果已入池，但 Master 未同步 collected；或 Day10 未成功完成。 | 优先重新跑 Day10；若确认只是状态断裂，运行 repair_master_status_from_result_pool.py。 |
| 当前 Master.center_status 不允许参与 Day12 merge | 任务仍是 undistributed、reworking 或 completed。 | 检查流程是否跳步；reworking/completed 不应自动 merge。 |
| downsample_missing | M/L 样本缺少必要 x2/x4 downsample 文件。 | 补齐 center/central_data_pool/downsample_candidates 后重新运行。 |
| conflict | 同一个 sample_id 的同一模块存在多个入池结果。 | 人工判定保留哪一个结果，不能静默覆盖。 |
| Day12 输出已存在，默认禁止覆盖 | merged/review_queue/report 已存在。 | 确认要重跑时使用 --replace-generated。 |

---

## 14. 冻结建议

- 如果 dry-run 通过，正式运行成功，并且 merge_error_report 中 incomplete_samples、conflict_samples、downsample_blocked_samples、orphan_result_samples 均为 0，则可以冻结 Day12。
- 冻结后，不再修改 merger.py 的状态校验逻辑；后续问题优先从 Day9/Day10 输入质量、Master 状态、结果池结构修复。
- 冻结后，Day15 review_manager.py 应只读取 review_queue、merged 和 review_results.json，不应绕过 Day12 直接读取本地结果。
- 如果还有 mock caption 或 mock 标注结果，可冻结流程能力，但需要在交付备注中说明数据内容仍是 mock，不代表真实标注质量冻结。

---

## 15. 推荐一键运行顺序

### 1. 备份 Master
```bash
copy center\manifests\Master_Manifest.json center\manifests\Master_Manifest.backup_before_day12.json
```

---

### 2. 可选：修复旧版扁平结果池，仅在 merger.py 报结构错误时执行
```bash
python scripts/center/repair_result_pool_layout.py --root center/central_result_pool --dry-run
python scripts/center/repair_result_pool_layout.py --root center/central_result_pool
```

---

### 3. 可选：修复 Master 状态，仅在确认结果已入池但 Master 未同步 collected 时执行
```bash
python scripts/center/repair_master_status_from_result_pool.py
python scripts/center/repair_master_status_from_result_pool.py --apply
```

---

### 4. Day11/Day12 检查
```bash
python scripts/center/merger.py --config configs/project/center_receive_merge_config.json --dry-run
```

---

### 5. Day11/Day12 正式运行
```bash
python scripts/center/merger.py --config configs/project/center_receive_merge_config.json --replace-generated
```