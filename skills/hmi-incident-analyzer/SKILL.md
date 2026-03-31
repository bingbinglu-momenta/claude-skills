---
name: hmi-incident-analyzer
description: 智驾HMI事故工单批量分析工具。从飞书Bitable中读取行车/泊车碰撞事故工单，自动生成结构化字段：HMI事故场景、HMI事故原因、ADAS系统方案、HMI交互方案及关键词分类，并批量写回飞书Bitable。支持行车碰撞（提取/优化）、泊车碰撞（知识库补全）两种模式。触发词："HMI事故分析"、"事故工单分析"、"HMI碰撞分析"、"hmi-incident-analyzer"、"分析HMI工单"、"补全HMI事故字段"。
license: Proprietary
allowed-tools:
  - Bash
  - Read
  - Write
  - Glob
  - Grep
  - Edit
---

# HMI 事故工单批量分析 Skill

本 skill 对飞书 Bitable 中的行车/泊车碰撞事故工单进行批量结构化分析，自动生成并回写 6 个关键字段，替代人工逐条整理，单次可处理 200~500 条记录。

---

## 使用方式

### 最简调用

```
/hmi-incident-analyzer
  bitable: https://momenta.feishu.cn/wiki/XzJCw3mXIiYtWekt1Z2cqa1lnDh?table=tblUPCYZY1zQKlpu
```

### 完整参数

```
/hmi-incident-analyzer
  bitable: <飞书Bitable URL>（必填）
  mode: auto              # auto(默认) | driving | parking | all
  scene_field: HMI-事故场景  # 目标字段名，可按实际Bitable列名调整
  cause_field: HMI-事故原因
  text8_field: 文本 8
  text9_field: 文本 9
  text10_field: 文本 10
  text11_field: 文本 11
  hmi_plan_field: HMI方案      # 源字段：HMI方案文本
  func_field: 功能分类          # 源字段：功能分类（用于区分行车/泊车）
  ticket_field: 工单链接         # 源字段：工单标题/链接
  dry_run: false              # true = 仅预览，不写入
  limit: 0                    # 0=全量，正整数=处理前N条（调试用）
```

---

## 执行流程

### Step 0：环境检查

```bash
feishu-sync-cli --help 2>/dev/null && echo "OK" || echo "NEED_INSTALL"
```

若 NEED_INSTALL：
```bash
python -m pip install --extra-index-url https://artifactory.momenta.works/artifactory/api/pypi/pypi-momenta/simple feishu-sync -U
```

---

### Step 1：读取 Bitable 原始数据

```bash
feishu-sync-cli read_page "<bitable_url>" --force_refresh 2>&1 | python -c "
import sys, json
data = json.load(sys.stdin)
recs = data.get('records', [])
print(json.dumps({'records': recs}, ensure_ascii=False))
" > ~/bitable_raw.json
```

或直接用 Python 调用 feishu-sync：

```python
import subprocess, json
result = subprocess.run(
    ['feishu-sync-cli', 'read_page', bitable_url, '--force_refresh'],
    capture_output=True, text=True, encoding='utf-8'
)
data = json.loads(result.stdout.split('\n')[-1])  # last JSON line
```

提取关键信息：
- `records[].record_id`：用于写回
- `records[].fields['HMI方案']`：分析源文本
- `records[].fields['功能分类']`：区分行车/泊车
- `records[].fields['工单链接']`：提取事件描述
- `records[].fields['故障分类']`、`['二级分类']`、`['三级分类']`、`['备注']`：补充根因

统计后按模式决定处理范围：

| 模式 | 筛选条件 |
|------|---------|
| `driving` | 功能分类 ∈ {行车碰撞, 行车碰撞风险}，有 HMI方案 |
| `parking` | 功能分类 = 泊车碰撞，HMI方案 为空 |
| `auto` (默认) | driving + parking 两者都处理 |
| `all` | 对所有有 HMI方案 的记录重新生成 |

---

### Step 2：生成分析脚本

使用以下模板在本地生成 `analyze_hmi_batch.py`，根据用户传入参数替换字段名和 Bitable 信息：

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 由 hmi-incident-analyzer skill 自动生成
# 参数: bitable={bitable_url}, mode={mode}

import json, os, re, sys, time, urllib.request
from pathlib import Path

APP_TOKEN = "{app_token}"  # 从Bitable URL解析
TABLE_ID  = "{table_id}"   # 从Bitable URL解析

# ── 字段映射 ──────────────────────────────
F_SCENE   = "{scene_field}"   # HMI-事故场景
F_CAUSE   = "{cause_field}"   # HMI-事故原因
F_TEXT8   = "{text8_field}"   # ADAS系统方案
F_TEXT9   = "{text9_field}"   # 文本8关键词
F_TEXT10  = "{text10_field}"  # HMI交互方案
F_TEXT11  = "{text11_field}"  # 文本10关键词
F_HMI     = "{hmi_plan_field}"  # HMI方案（源）
F_FUNC    = "{func_field}"    # 功能分类（源）
F_TICKET  = "{ticket_field}"  # 工单链接（源）

# ── 泊车场景知识库 ────────────────────────
PARKING_KB = {
    "台阶": { ... },
    "地锁": { ... },
    "路沿": { ... },
    # ... 完整知识库见 scripts/parking_kb.py
}

# ── 行车优化模板 ──────────────────────────
DRIVING_TEMPLATES = {
    "故障诊断漏报/误报/延迟": "【ADAS系统层面】①建立完整的感知/控制/传感器故障诊断上报链路...",
    "未打开降级": "【ADAS系统层面】①完善降级触发条件...",
    "非故障相关": "【ADAS系统层面】①感知模型迭代...",
}

# ── 核心分析函数 ──────────────────────────
def analyze_record(fields, mode): ...
def update_record(rec_id, patch, token): ...
def main(): ...
```

> **AI 在此步骤的作用**：根据用户提供的实际字段名、app_token、table_id，动态填充脚本模板，并将 `PARKING_KB` 从 `scripts/parking_kb.py` 完整内嵌。

---

### Step 3：干运行预览（可选）

当 `dry_run: true` 时，打印前 5 条分析结果，不调用写入 API：

```
[预览 1/5] recABCDEF
  工单: XXXXX-MK-0123 # 20240315-上海 - cut-in急刹车
  HMI-事故场景: cut-in急刹车。AEB触发后HMI未给出明确降级提示
  HMI-事故原因: 故障诊断漏报；制动力不足
  文本8: 【ADAS系统层面】①建立故障诊断上报链路...
  文本9: 功能类[AEB]；场景类[cut-in, 急刹]；根因类[感知漏检]
  文本10: 【HMI交互层面】①仪表红色告警...
  文本11: 功能类[AEB]；告警类型[视觉告警, 语音告警]；触发条件[TTC]
```

---

### Step 4：批量写回

```python
PYTHONUTF8=1 python analyze_hmi_batch.py
```

写回使用飞书 Bitable Record PUT API：

```
PUT https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}
Authorization: Bearer {feishu_access_token}
Content-Type: application/json

{
  "fields": {
    "HMI-事故场景": "...",
    "HMI-事故原因": "...",
    "文本 8": "...",
    "文本 9": "...",
    "文本 10": "...",
    "文本 11": "..."
  }
}
```

> Token 来源：`~/.feishu/access_token.json`（由 feishu-sync `get_access_token()` 自动管理）

进度输出：
```
[行车优化] 待处理: 285 条
  行车进度: 30/285 | ok=30 fail=0
  ...
[泊车补全] 待处理: 208 条
  泊车进度: 30/208 | ok=30 fail=0
  ...
完成！总成功: 493, 总失败: 0
```

---

### Step 5：结果验证

```bash
feishu-sync-cli read_page_as_markdown "<bitable_url>" --force_refresh 2>&1 | tail -20
```

或输出统计摘要：
- 已填写条数 vs 空白条数
- 各字段覆盖率

---

## 字段生成逻辑说明

### HMI-事故场景

```
工单标题关键词 + HMI方案首句问题描述（去除重复）
```
示例：`cut-in急刹车。AEB触发后HMI未给出明确降级提示，驾驶员未及时接管`

### HMI-事故原因

优先级排序：
1. `备注` 字段（人工填写的直接根因）
2. `二级分类` / `三级分类`（结构化根因标签）
3. `故障分类`（排除"非故障相关"）
4. HMI方案中含"原因/导致/异常/漏检"的句子

### 文本 8（ADAS 系统整体解决方案）

```
[故障分类对应系统模板] + 原始HMI方案中的系统层句子 + 验证方式
```

故障分类 → 系统模板映射：

| 故障分类 | 系统模板方向 |
|---------|------------|
| 故障诊断漏报/误报/延迟 | 感知/控制故障诊断上报链路完善 |
| 未打开降级 | 降级触发条件优化，自动降级机制 |
| 非故障相关 | 感知模型迭代，扩展系统工作包线 |

### 文本 9（文本8关键词分类）

从文本8 + HMI方案中提取：
- `功能类[AEB, FCW, ...]`
- `场景类[cut-in, 急刹, ...]`
- `根因类[感知漏检, failsafe未报, ...]`
- `方案类[故障诊断, 感知模型迭代, ...]`

### 文本 10（HMI 交互解决方案）

从 HMI方案中提取含 HMI 关键词的句子（仪表/告警/语音/弹窗/震动/接管等）

### 文本 11（文本10关键词分类）

从文本10中提取：
- `功能类[AEB, ...]`
- `告警类型[视觉告警, 语音告警, 三联告警, ...]`
- `触发条件[TTC, 系统上限, 感知目标骤减, ...]`

---

## 泊车事故知识库

当功能分类 = 泊车碰撞 且 HMI方案 为空时，通过工单关键词匹配知识库生成完整内容：

| 场景类型 | 匹配关键词 | 典型根因 |
|---------|-----------|---------|
| 台阶/高差 | 台阶, 高差, 坡道 | 低矮高对比差目标，感知漏检 |
| 地锁/限位器 | 地锁, 限位, 地桩 | 小目标金属物，超声波盲区 |
| 路沿/路边石 | 路沿, 路边石, 揉库 | 近距离纵向距离估算误差 |
| 消防箱/悬空物 | 消防箱, 悬挂, 悬空 | 中高位盲区，超声波上限 |
| 低矮柱子 | 柱子, 矮柱, 停车柱 | 柱子底部超声波盲区 |
| 异形障碍物 | 障碍物, 异形, 购物车 | 非规则形状感知弱势 |
| 墙壁/角落 | 墙壁, 墙角, 死角 | 贴近墙壁时传感器盲区 |
| 底盘/斜坡 | 底盘, 斜坡, 减速带 | 底盘高度感知缺失 |
| RPA 远程泊车 | RPA, 远程 | 用户介入时机不明确，低速HMI告警不足 |
| HPA 记忆泊车 | HPA, 记忆泊车 | 场景变化感知不足，缺乏重新学习提示 |
| 系统故障 | 故障, 传感器异常, 超声波故障 | 传感器/域控故障未提示 |

---

## 适用场景

- **行车碰撞事故复盘**：批量提取和结构化事故特征，用于 HMI 改进方向研究
- **泊车事故分析补全**：对无 HMI 方案记录的泊车工单自动生成标准化分析
- **多项目横向对比**：统一 6 字段格式后，可按关键词分类做跨项目事故频次统计
- **HMI 改进 Backlog 生成**：从文本9/11关键词提取高频问题，形成 HMI 优化优先级矩阵

---

## 注意事项

1. **Token 有效期**：feishu-sync access token 有效期 2 小时，超时自动刷新；若 refresh token 过期（7天未用），需重新执行 `python -m feishu_sync.retoken init_token`
2. **字段名大小写敏感**：写回时使用字段名（如 `文本 8` 含空格），不是字段 ID
3. **网络中断重试**：脚本遇到单条网络错误时仅记录跳过，不中断批处理；完成后可对 `fail` 条目重跑
4. **速率限制**：每处理 20~30 条后有 0.3~0.5s 延迟，避免触发飞书 API 限速（100 req/min）
5. **幂等性**：重复运行会覆盖之前生成的内容，不会产生重复数据

---

## 扩展定制

### 自定义知识库

修改 `PARKING_KB` 或在调用时追加场景：
```
/hmi-incident-analyzer
  bitable: https://...
  extra_kb: |
    推挤: 泊车过程中车辆被其他车推挤导致碰撞
    斜坡: 坡道停车场斜坡溜车碰撞
```

### 接入其他 Bitable

只需调整 `bitable` 参数和字段名映射，无需修改核心逻辑。

### 输出到 Excel

添加 `output: excel` 参数，将生成结果保存到本地 `.xlsx` 文件而非写回 Bitable。

---

*skill version: 1.0.0 | 适用于 Claude Code + feishu-sync*
