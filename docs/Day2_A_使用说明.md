# 同学 A - Day2 中心预处理使用说明

## 1. 放置文件

把文件放入仓库：

```text
project_root/
├── scripts/
│   ├── center/
│   │   └── preprocess.py
│   └── shared/
│       ├── config_loader.py
│       ├── constants.py
│       ├── id_utils.py
│       └── ...
├── configs/
│   └── preprocess_config.json
└── center/
    └── raw_input/
        ├── selected_patients.xlsx
        ├── images/
        └── masks/
```

## 2. 安装依赖

```bash
pip install openpyxl pillow
```

## 3. 运行

```bash
python scripts/center/preprocess.py --config configs/preprocess_config.json
```

## 4. 预期输出

```text
center/central_data_pool/images/
center/central_data_pool/masks/
center/central_data_pool/metadata/samples_index.json
center/central_data_pool/metadata/cases_index.json
center/central_data_pool/metadata/preprocess_manifest.json
center/central_data_pool/downsample_candidates/x2/
center/central_data_pool/downsample_candidates/x4/
logs/preprocess/{source_batch}/error_report.json
```

## 5. Day2 验收重点

- sample_id = {检查分类}_{检查HIS号}_{图片编号}
- diagnosis_raw 来源固定为 Excel 的“检查提示”
- resolution_level 只能是 S/M/L
- samples_index.json 按 sample_id 升序输出
- cases_index.json 按 case_id 升序输出
- 异常样本进入 error_report.json，不进入 samples_index.json
- preprocess.py 不生成 tasks.json / Master_Manifest.json / Receive_Registry.json / final.json
