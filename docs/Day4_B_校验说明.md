# Day4_B 校验说明（给 A）

## 1. 目的

验证 B 侧 Day4 代码（任务包分发）在你本地可以正常运行并通过校验。

---

## 2. 拉取代码

```bash
git fetch origin
git checkout feature/B-day04-distributor
git pull origin feature/B-day04-distributor
```

确认文件存在：

```bash
scripts/center/distributor.py
scripts/center/validators/validate_day4.py
```

---

## 3. 前置条件

确保你本地已经完成：

```bash
Day3（splitter + master）
```

存在：
```bash
center/task_packages/.tmp/
center/manifests/Master_Manifest.json
configs/packaging/distribution_config.json
```

---

## 4.（可选）如果之前跑过 Day4，先清理

Windows：

```bash
del /q center\task_packages\*.zip 2>nul
del /q Project_Sync\01_Distribution\*\To_Be_Labeled\*.zip 2>nul
del /q Project_Sync\01_Distribution\*\To_Be_Labeled\*.UPLOAD_DONE.flag 2>nul
```

并重置 Master 状态：

```bash
python -c "import json; from pathlib import Path; p=Path('center/manifests/Master_Manifest.json'); d=json.loads(p.read_text(encoding='utf-8')); [t.update({'center_status':'undistributed','result_status':'not_collected'}) for t in d['tasks']]; p.write_text(json.dumps(d, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')"
```

---

## 5. 运行 Day4 分发

```bash
python scripts/center/distributor.py --config configs/packaging/distribution_config.json
```

---

## 6. 运行 Day4 校验

```bash
python scripts/center/validators/validate_day4.py
```

---

## 7. 验收标准

看到：

```bash
[OK] Day4 validation passed
```

即可认为：
 - distributor.py 正常
 - validate_day4.py 正常
 - Day4 分发逻辑 OK

---

## 8. 注意

 - 不要删除 center/task_packages/.tmp/（这是 Day3 输入）
 - 不要手动修改 Master / tasks.json / meta.json