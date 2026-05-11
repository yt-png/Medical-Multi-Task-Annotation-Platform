# 医学多任务离线标注平台（Medical Multi-Task Annotation Platform）

## 一、项目简介

本项目是一个**离线任务包驱动的医学多任务标注平台**，支持：

- segmentation（分割）
- detection（检测）
- caption（描述生成）

平台采用：

> 离线任务包 + 本地独立标注 + 中心统一回收与汇总

不依赖在线数据库，不做实时调度，不做多人在线协作。

---

## 二、整体数据流（必须理解）


中心预处理
→ central_data_pool
→ 拆包 task_package
→ Project_Sync 分发
→ 本地导入
→ 本地标注
→ 本地导出 result_package
→ 中心回收
→ Receive_Registry
→ central_result_pool
→ merge
→ review_queue
→ review_results.json
→ final.json


⚠️ **任何代码必须严格遵循此数据流**

---

## 三、核心协议（已冻结，不允许修改）

以下文件为全项目协议基石：

- tasks.json :contentReference[oaicite:0]{index=0}  
- results.json :contentReference[oaicite:1]{index=1}  
- task_package/meta.json :contentReference[oaicite:2]{index=2}  
- result_package/meta.json :contentReference[oaicite:3]{index=3}  
- Master_Manifest.json  
- Receive_Registry.json  
- review_results.json  
- final.json  

### ❗冻结原则

- 不允许修改字段名
- 不允许新增字段
- 不允许改变语义
- 不允许本地端写中心文件

---

## 四、项目结构


project_root/
├── center/ # 中心端数据
├── local/ # 本地端
├── Project_Sync/ # 数据交换目录
├── scripts/ # 所有脚本
│ ├── center/
│ ├── local/
│ └── shared/
├── configs/
├── docs/
├── logs/
├── tmp/
└── README.md


---

## 五、A / B 分工（必须严格遵守）

### A（中心负责人）

负责：

- 中心预处理
- Master_Manifest.json
- Receive_Registry.json
- 中心回收校验
- central_result_pool
- merge
- review
- final
- rework

### B（本地负责人）

负责：

- task_package 生成
- importer / exporter
- results.json 生成
- result_package/meta.json
- 本地 API / 页面

### 共同维护：


scripts/shared/


---

## 六、shared 层（Day1 核心成果）

shared 是：

> ❗全项目唯一“协议执行层”

所有脚本必须依赖 shared，不允许重复实现。

---

### 1️⃣ constants.py（枚举冻结）

定义：

- TASK_TYPES = segmentation / detection / caption :contentReference[oaicite:4]{index=4}  
- 状态枚举（Master / Receive / Review）
- schema_version = v1

---

### 2️⃣ schemas.py（字段冻结）

定义：

- tasks.json 字段集合 :contentReference[oaicite:5]{index=5}  
- results.json 字段集合 :contentReference[oaicite:6]{index=6}  
- Master 字段集合

👉 用于：

- 校验字段完整性
- 禁止未定义字段

---

### 3️⃣ path_utils.py（路径规则）

规则：

- 必须是相对路径
- 必须使用 `/`
- 禁止：
  - 绝对路径
  - URL
  - Windows `\`

实现见：:contentReference[oaicite:7]{index=7}  

---

### 4️⃣ hash_utils.py（哈希规则）

唯一规则：


sample_id 升序
→ "\n" 拼接
→ SHA256


实现见：:contentReference[oaicite:8]{index=8}  

---

### 5️⃣ zip_utils.py（包规则）

规则：

- ZIP 与 flag / done 一一对应
- .done 必须最后生成
- ZIP 必须可解压

实现见：:contentReference[oaicite:9]{index=9}  

---

### 6️⃣ config_loader.py（配置加载）

规则：

- 支持 json / yaml
- 配置不能改变协议

实现见：:contentReference[oaicite:10]{index=10}  

---

### 7️⃣ validators.py（协议校验）

核心职责：

- 校验 tasks.json 合法性 :contentReference[oaicite:11]{index=11}  
- 校验字段完整性
- 校验路径合法性
- 校验 task_type 规则

---

## 七、最重要的开发红线（必须遵守）

### ❌ 禁止行为

- 自己定义字段
- 修改 schema_version
- 修改 sample_id
- 使用绝对路径
- 使用 URL
- 使用 Windows 路径
- 本地写 Master / Receive
- 从 results.json 直接生成 final

---

### ❗字段规则（重点）

#### tasks.json

- 顶层必须数组 :contentReference[oaicite:12]{index=12}  
- sample_id + task_type 唯一  
- 路径必须相对路径  

---

#### results.json

- module 必须等于 task_type :contentReference[oaicite:13]{index=13}  
- 一个 sample 只能一条结果  
- segmentation 必须有 mask_path  
- detection 必须满足 boxes / negative_confirmed 规则  
- caption 必须有 generated + reviewed  

---

#### meta.json

- sample_id_hash 必须一致 :contentReference[oaicite:14]{index=14}  
- completed + invalid = total  
- operator 必须等于 assigned_to  

---

## 八、Day1 A 同学完成内容

Day1 已完成：

- shared/constants.py
- shared/schemas.py
- shared/path_utils.py
- shared/hash_utils.py
- shared/zip_utils.py
- shared/config_loader.py
- shared/validators.py

👉 完成内容：

- 协议冻结
- 字段冻结
- 路径规则冻结
- hash 规则冻结
- 校验逻辑冻结

---

## 九、对 B 同学的开发约束（非常重要）

B 必须遵守：


必须使用 shared 层：

constants

schemas

hash_utils

path_utils

validators


禁止：

- 自己写字段
- 自己写 hash
- 自己写路径规则

---

## 十、当前阶段（Week1 Day1）

当前完成：

> ✅ 协议层冻结

下一步：

- Day2：中心预处理
- Day3：拆包
- Day4：分发
- Day5：本地导入

---

## 十一、最终目标

平台必须实现：

- 全链路 sample_id 一致
- task_id 一致
- operator 一致
- ZIP / flag / done 正确
- 错误数据不可入池
- final 只来自审核通过

---

## 十二、总结（最重要一句话）

> 本项目不是“写代码”，而是  
> ❗**构建一个“不可被破坏的数据协议系统”**

shared 层 = 全系统唯一规则源

任何绕过 shared 的代码 = 错误实现