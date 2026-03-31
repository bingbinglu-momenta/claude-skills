---
name: hmi-checklist
description: 智驾HMI版本发版点检表生成工具。从飞书源用例文档（表格/wiki）中读取测试内容，自动生成串联式发版点检表，写入目标飞书表格。每条用例包含：串联测试步骤、逐步骤详细文言/语音预期结果、ASCII示意图。支持交互类和SR渲染类点检。触发词："生成点检表"、"生成发版点检"、"hmi-checklist"、"HMI点检"、"发版点检表"。
license: Proprietary
allowed-tools:
  - Bash
  - Read
  - Write
  - Glob
  - Grep
  - Edit
---

# HMI 发版点检表生成 Skill

本 skill 根据飞书源用例文档，自动生成 HMI 发版点检表，写入目标飞书表格。

---

## 使用方式

用户调用示例：

```
/hmi-checklist
  源用例1: https://momenta.feishu.cn/sheets/XXX?sheet=YYY
  源用例2: https://momenta.feishu.cn/wiki/ZZZ
  目标表格: https://momenta.feishu.cn/wiki/AAA
  数量: 10
  重点模块: NP, ACC, SR, BSD
```

参数说明：
- `源用例`（必填）：1 个或多个飞书文档 URL（表格/wiki 均可），作为测试内容参考来源
- `目标表格`（必填）：飞书表格 wiki URL，用于写入生成的点检用例
- `数量`（可选）：生成用例条数，默认 10 条
- `重点模块`（可选）：指定要覆盖的功能模块，如 NP, ACC, SR, BSD, TSR, 泊车等

---

## 执行流程

### Step 0：环境检查

```bash
feishu-sync-cli --help 2>/dev/null && echo "OK" || echo "NEED_INSTALL"
```

若 NEED_INSTALL：
```bash
python3 -m pip install --extra-index-url https://artifactory.momenta.works/artifactory/api/pypi/pypi-momenta/simple feishu-sync -U
```

> **Windows 注意**：使用 `py -3.12` 而非 `python3`（系统 python3 可能指向 Microsoft Store 空壳）。

---

### Step 1：读取源用例

对每个源 URL，执行：
```bash
feishu-sync-cli read_page_as_markdown "<源URL>" 2>&1 | tail -n +10
```

重点提取：
- 功能分类（功能名称 / 二级功能 / 三级功能）
- 测试步骤模式
- 预期结果中的**文言提示**和**语音提示**（如「自适应巡航系统已激活」、「已退出至手动驾驶」等）
- 报警音触发条件

---

### Step 2：获取目标表格信息

```bash
feishu-sync-cli info_page "<目标URL>" 2>&1 | tail -n +10
```

提取 `obj_token`（表格 token）和 sheet_id：
```python
from feishu_sync.retoken import get_access_token
import urllib.request, json

token = get_access_token()[0]
sheet_token = '<obj_token>'
url = f'https://open.feishu.cn/open-apis/sheets/v3/spreadsheets/{sheet_token}/sheets/query'
req = urllib.request.Request(url, headers={'Authorization': f'Bearer {token}'})
resp = json.loads(urllib.request.urlopen(req).read())
for s in resp.get('data', {}).get('sheets', []):
    print(s.get('sheet_id'), s.get('title'))
```

---

### Step 3：设计串联用例

根据源文档内容，设计 N 条**串联式**点检用例，每条用例应：

1. **串联多个检查动作**为一条用例，例如：
   - NP激活 → 观察SR视角切换 → 观察引导线渲染 → 拨杆变道 → 观察侧方目标高亮
   - ACC激活 → 跟车目标渲染 → 变道 → 降级至手动 → 语音提示验证

2. **必须覆盖**以下类型（根据用户指定的重点模块调整）：
   - **交互类**：状态激活/退出/升降级，语音/文言提示，仪表图标变化
   - **SR渲染类**：视角切换，引导线，目标高亮，车道线染色
   - **感知元素类**：目标物识别（车/人/骑行者/障碍物），TSR，信号灯，路面元素
   - **告警类**：BSD 提示，跟距过近，接管请求

3. **测试步骤格式**：
   ```
   1. 前置条件描述
   2. 操作步骤 A
      观察：...
   3. 操作步骤 B（可含子步骤）
      a. 子操作
      b. 子操作
   4. 后续状态验证
   ```

4. **预期结果格式**（必须包含逐步骤文言提醒）：
   ```
   1. 步骤1预期
      【文言】「精确文言内容」
      【语音】「精确语音播报内容」
   2. 步骤2预期
      【文言】无
   3. 步骤3预期
      【报警音】有/无（描述）
   ```

---

### Step 4：构造数据并写入表格

#### 列结构（固定13列 + 1示意图列）

| 列 | 字段 | 说明 |
|---|---|---|
| A | 序号 | TC-01 ~ TC-N |
| B | 功能名称 | 主功能模块（如 ACC状态机/SR渲染） |
| C | 二级功能 | 串联功能描述 |
| D | 三级功能 | 一句话概述验证要点 |
| E | 测试步骤 | 详细步骤，含子步骤，使用 \n 换行 |
| F | 工作界面 | SR画面/仪表盘/后视镜BSD指示灯 等 |
| G | 预期结果 | 逐步骤预期，包含【文言】【语音】【报警音】标注 |
| H | 报警音提示 | 有/无（简述触发条件） |
| I | 语音提示 | 有/无（精确语音文案） |
| J | mviz link | 留空（测试时填写） |
| K | 测试结果 | 留空 |
| L | 问题描述 | 留空 |
| M | 修复状态 | 留空 |
| N | 示意图 | ASCII 俯视图，帮助理解场景 |

#### 写入代码模板

```python
# -*- coding: utf-8 -*-
import json, subprocess
from feishu_sync.retoken import get_access_token
import urllib.request

SHEET_URL = 'https://momenta.feishu.cn/sheets/<token>'
SHEET_TOKEN = '<obj_token>'
SHEET_ID = '<sheet_id>'

# 表头
headers = ["序号","功能名称","二级功能","三级功能","测试步骤","工作界面",
           "预期结果","报警音提示","语音提示","mviz link","测试结果","问题描述","修复状态"]

# 数据行
data_rows = [
    ["TC-01", "功能名称", "二级功能", "三级功能",
     "1. 步骤1\n2. 步骤2\n   观察：...",
     "SR画面、仪表盘",
     "1. 预期1\n   【文言】「...」\n   【语音】「...」\n2. 预期2",
     "无", "有（...）",
     "", "", "", ""],
    # ... 更多行
]

# ASCII 示意图（与数据行对应）
diagrams = [
    ["示意图"],  # 表头
    ["道路俯视图...\n  ┌──┐\n  │本车│\n  └──┘"],
    # ... 更多图
]

# 写入数据（A1:N<N+1>）
all_data = [headers] + data_rows
result = subprocess.run(
    ['feishu-sync-cli', 'write_sheet', SHEET_URL,
     f'{SHEET_ID}!A1:M{len(all_data)}',
     json.dumps(all_data, ensure_ascii=False)],
    capture_output=True, text=True, encoding='utf-8'
)
print(result.stdout)

# 写入示意图（N列）
result2 = subprocess.run(
    ['feishu-sync-cli', 'write_sheet', SHEET_URL,
     f'{SHEET_ID}!N1:N{len(diagrams)}',
     json.dumps(diagrams, ensure_ascii=False)],
    capture_output=True, text=True, encoding='utf-8'
)
print(result2.stdout)
```

#### 写入后应用样式

```python
import urllib.request, json

def apply_styles(token, sheet_token, sheet_id, row_count):
    styles = [
        {  # 表头：蓝底白字加粗居中
            'ranges': f'{sheet_id}!A1:N1',
            'style': {
                'font': {'bold': True, 'color': '#FFFFFF'},
                'backColor': '#2F54EB',
                'horizontalAlign': 'CENTER',
                'verticalAlign': 'MIDDLE',
                'textWrap': 'WRAP'
            }
        },
        {  # 数据行：自动换行、顶对齐
            'ranges': f'{sheet_id}!A2:N{row_count + 1}',
            'style': {
                'textWrap': 'WRAP',
                'verticalAlign': 'TOP'
            }
        },
        {  # 序号列：居中加粗
            'ranges': f'{sheet_id}!A2:A{row_count + 1}',
            'style': {
                'horizontalAlign': 'CENTER',
                'verticalAlign': 'MIDDLE',
                'font': {'bold': True}
            }
        }
    ]
    for style in styles:
        payload = {'data': [style]}
        body = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            f'https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/{sheet_token}/styles_batch_update',
            data=body, method='PUT',
            headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
        )
        r = json.loads(urllib.request.urlopen(req).read())
        if r.get('code') != 0:
            print(f'Style warning: {r.get("msg")}')
```

> **注意**：`styles_batch_update` 的 body 格式为 `{"data": [{...}]}`（data 是数组），不是 `{"data": {"valueRanges": [...]}}`.

---

### Step 5：验证写入

```bash
feishu-sync-cli read_page_as_markdown "<目标URL>" --force_refresh 2>&1 | tail -n +10 | head -50
```

确认表格内容正确后，返回目标表格链接给用户。

---

## 已知的文言/语音提示参考库

在生成预期结果时，优先使用以下经过验证的精确文案（来源：Momenta 筑莲山功能点检测试记录）：

### ACC 状态
| 触发场景 | 【文言】 | 【语音】 |
|---|---|---|
| ACC 激活成功 | 「自适应巡航系统已激活」 | 「自适应巡航已激活」 |
| ACC 主动退出（Cancel/刹车） | 「自适应巡航系统已退出」 | 「已退出至手动驾驶」 |
| ACC 可以激活（满足条件时） | 「自适应巡航可激活」 | 无 |
| 跟车距离过近 | 「跟前车距离过近，请接管车辆降低车速」 | 同文言 |
| 车速过高将退出 | 「车速过高时，辅助驾驶将退出」 | 同文言 |
| 设速达极限 | 「设速达到极限值」 | 无 |

### NP/LNP 状态
| 触发场景 | 【文言】 | 【语音】 |
|---|---|---|
| NP 可激活 | 「智能车道寻迹可激活」 | 无 |
| NP 激活成功 | 「导航辅助驾驶已激活」 | 「导航辅助驾驶已激活」 |
| NP 降级至 LTA/车道居中 | 「已降级至车道居中辅助」 | 同文言 |
| NP 降级至 ACC | 「已降级至自适应巡航」 | 「已降级至自适应巡航」 |
| NP 降级至 DRC | 「已降级至动态雷达巡航」 | 同文言 |
| 退出至手动驾驶 | 「已退出至手动驾驶」 | 「已退出至手动驾驶」 |
| 接管请求 | 「请接管」 | 「请接管」 |
| 立即接管 | 「请立即接管」 | 「请立即接管」 |
| 方向盘提示 | 「请控制方向盘」 | 同文言 |
| 变道执行中 | 「正在变道」 | 无 |
| 变道被取消 | 「变道已取消」 | 无 |
| 汇入主路困难 | 「汇入主路困难，建议手动变道」 | 同文言 |
| 即将汇入主路 | 「即将汇入主路」 | 同文言 |
| 路口提示 | 「前方红绿灯路口，请注意」 | 同文言 |
| 急弯提示 | 「小心急弯」 | 同文言 |
| 变道功能受限 | 「变道功能受限」 | 无 |

### LTA 状态
| 触发场景 | 【文言】 | 【语音】 |
|---|---|---|
| LTA 可激活 | 「智能车道循迹可激活」 | 无 |
| LTA 取消/退出 | 「车道居中辅助系统已取消」 | 同文言 |
| LTA 系统异常 | 「车道居中辅助系统异常，请前往经销店」 | 同文言 |

### BSD 状态
| 触发场景 | 【文言】 | 【视觉】 | 【报警音】 |
|---|---|---|---|
| BSD 一级（盲区有车，未打转向灯） | 无 | 后视镜BSD灯黄/白常亮，SR侧方橙色高亮 | 无 |
| BSD 二级（盲区有车 + 打转向灯） | 「注意！左/右侧盲区有车辆」 | BSD灯闪烁/变红，SR高亮加深 | 有（滴滴音） |

---

## ASCII 示意图设计规范

每条用例的示意图应包含：

1. **场景标注**：如「道路方向 →」、「路口场景:」、「高速全流程:」
2. **车辆位置**：用 `┌──┐ / │本车│ / └──┘` 表示本车，同样格式表示他车
3. **动作箭头**：`→` 或 `↓` 表示流程走向
4. **SR画面框**：用 `┌───────┐ / │       │ / └───────┘` 表示SR屏幕内容
5. **高亮标注**：用 `←─高亮` 或 `← 一级图标亮` 注释关键要素

示例：
```
道路方向 →
  ┌────┐
  │ 前车│ ← ┌─高亮跟车框─┐
  └────┘
     ↑ ACC设定跟车距离
  ┌────┐   拨ACC拨杆       ┌──────────────┐
  │ 本车│ ─────────────→  │ SR: 低速视角  │
  └────┘                  │ [前车高亮框]  │
                           └──────────────┘
```

---

## 典型用例模板参考

以下是经过验证的串联用例模板，可在此基础上根据源文档内容调整：

### 模板 A：激活 + SR视角 + 目标渲染
- 激活 ACC/NP → 观察SR视角自动切换 → 观察目标高亮出现 → 验证对应文言/语音

### 模板 B：状态升降级
- NP激活（高速） → 踩刹车/Cancel降级至ACC → 观察SR连续性 + 语音提示 → 再次退出至手动

### 模板 C：变道全流程
- NP激活 → 拨杆/自主变道 → SR切变道视角 → 侧后目标高亮 → 变道完成恢复 → 变道取消场景

### 模板 D：路口综合感知
- NP接近路口 → TSR识别限速 → 信号灯渲染 → 斑马线/停止线/地面箭头 → 通过后更新

### 模板 E：全流程串联
- 激活NP → 跟车 → 变道 → 降级 → 退出，全程SR无断帧 + 每节点文言/语音验证

### 模板 F：BSD告警
- 人驾/智驾行驶 → 左/右侧车进入盲区（一级） → 打转向灯（二级）→ 目标离开（提示消退）

---

## 常见错误与解决方案

| 问题 | 原因 | 解决 |
|---|---|---|
| `python3` 返回 exit code 49 | Windows Microsoft Store 空壳 | 改用 `py -3.12` |
| `feishu-sync-cli` 找不到 | PATH 未配置 | 用 `python3 -m feishu_sync.skill` |
| `get_access_token()` 报错 | token 已过期 | 运行 `python3 -m feishu_sync.retoken init_token` |
| styles API 返回 400 | body 格式错误 | data 用数组 `[{...}]`，不是 `{"valueRanges": [...]}` |
| `dimension_range` 返回 `Invalid parameter value: "ROWS"` | 该 API 在 wiki 嵌套表格上有权限/格式限制 | 跳过行高/列宽设置，不影响核心功能 |
| write_sheet 写入中文乱码 | Python 脚本编码问题 | 将脚本保存为 UTF-8 文件后用 `py -3.12 script.py` 运行，避免 inline `-c` 方式 |
