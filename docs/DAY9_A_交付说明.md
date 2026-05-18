# Day9 同学 A 交付说明：中心回收校验完整版

## 交付文件
- `scripts/center/receiver.py`：用本目录中的 `receiver_day9.py` 替换原 `scripts/center/receiver.py`。
- 不修改 shared 协议文件，不修改 B 负责的 importer/exporter/splitter/distributor 业务逻辑。

## Day9 完成范围
本版本在 Day8 基础回收校验上新增：
1. operator = assigned_to 校验；
2. sample_count 与 Master.sample_count 校验；
3. completed_count + invalid_count = sample_count 校验；
4. invalid_sample_ids 数量校验；
5. sample_id_hash 与 Master、原始 task_package/tasks.json 双重校验；
6. results_json_hash 与 ZIP 内真实 result_package/results.json 内容校验；
7. results.json 中所有 sample_id 必须属于原任务包；
8. duplicate_key = task_id + "|" + operator + "|" + export_version 判重；
9. invalid_count > 0 时写 Receive 为 validation_passed/skipped，并更新 Master 为 reworking/not_collected；
10. 校验失败写 Receive 为 validation_failed/skipped，failure_reason 写具体错误；
11. 重复提交写 Receive 为 duplicate/skipped，failure_reason = duplicate_submission。

## 推荐运行
```bash
python scripts/center/receiver.py --config configs/project/center_receive_merge_config.json
```

## 验收重点
- 错误包不能入池；
- 重复包不能覆盖旧结果；
- invalid_count > 0 不进入 central_result_pool；
- Receive_Registry.json 能记录失败原因；
- Day9 不实现 Day10 入池、不实现 Day11/12 merge/review_queue。
