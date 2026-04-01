---
name: mff-signal-checker
description: MFF 智驾状态机 HMI 信号持续发送缺陷自动检查工具。读取飞书信号规格表（B=CAN ID / C=信号名 / D=信号值），在 MFF 代码仓库中逐信号核查是否存在"触发后持续发送"缺陷（static flag 不复位、FixedFrameEmitter NP退出不重置、HmiTimingSignal 超大 max 配置等），结果写回飞书 A 列。可扩展到任意平台（BYD/EP33L/等）和任意代码分支。触发词："信号检查"、"持续发送检查"、"mff-signal-checker"、"HMI信号缺陷"、"发送缺陷核查"。
license: Proprietary
allowed-tools:
  - Bash
  - Read
  - Write
  - Glob
  - Grep
  - Edit
---

# MFF 信号持续发送缺陷检查 Skill

本 Skill 将 MFF（Main Function Framework）HMI 信号的持续发送缺陷检查过程**完全自动化**：从飞书信号规格表中读取信号列表，在代码仓库中逐信号执行 4 类缺陷模式扫描，将结论与修改建议直接写回飞书 A 列。

---

## 使用方式

```
/mff-signal-checker
  信号规格表: https://momenta.feishu.cn/wiki/WMi2wXJsFiA0hnkGYgCcDl6Nnvh?sheet=ZXXnPq
  代码仓库: https://devops.momenta.works/Momenta/msd/_git/mff
  分支: lhs/r6_mff_check_0401
  平台: byd
  写入列: A
```

### 参数说明

| 参数 | 是否必填 | 说明 |
|---|---|---|
| 信号规格表 | ✅ | 飞书表格 URL（含 sheet= 参数），B=CAN ID，C=信号名，D=值 |
| 代码仓库 | ✅ | MFF git 仓库 URL（Azure DevOps / GitHub 均可） |
| 分支 | ✅ | 要检查的代码分支名 |
| 平台 | ✅ | 适配器平台代号：`byd`（莲花山/LHUAS）、`ep33l`（EP33L）等 |
| 写入列 | 可选 | 结果写入飞书哪一列，默认 `A` |
| 行偏移 | 可选 | 飞书 sheet 数据行偏移（默认 3，即 markdown 行号 - 3 = sheet 行号） |

### 最简用法

只需提供 4 个必填参数：

```
/mff-signal-checker
  信号规格表: https://momenta.feishu.cn/wiki/XXX?sheet=YYY
  代码仓库: https://devops.momenta.works/Momenta/msd/_git/mff
  分支: main
  平台: byd
```

---

## 执行流程

### Step 0：环境准备

#### 0.1 feishu-sync-cli

```bash
feishu-sync-cli --help 2>/dev/null && echo "OK" || echo "NEED_INSTALL"
```

若 NEED_INSTALL：
```bash
python3 -m pip install --extra-index-url https://artifactory.momenta.works/artifactory/api/pypi/pypi-momenta/simple feishu-sync -U
```

> **Windows 注意**：优先使用 `py -3.12` 而非 `python3`。

#### 0.2 代码仓库 Sparse Checkout

MFF 仓库较大（>1GB），使用 sparse checkout 仅拉取平台适配器目录：

```bash
REPO_DIR="/tmp/mff_checker_$(date +%s)"
git clone --no-checkout --filter=blob:none --depth=1 \
  -b "${BRANCH}" "${REPO_URL}" "${REPO_DIR}"

cd "${REPO_DIR}"
git sparse-checkout init --cone
git sparse-checkout set \
  "adaptor/${PLATFORM}/" \
  "hmi_adaptor/${PLATFORM}/"
git checkout
```

> **已有本地副本**：若 `/tmp/mff_r6_0401/` 等目录已存在，跳过 clone 直接使用。
>
> **平台路径映射**：
> | 平台参数 | 代码路径 |
> |---|---|
> | `byd` | `adaptor/byd/` + `hmi_adaptor/byd/` |
> | `ep33l` | `adaptor/ep33l/` + `hmi_adaptor/ep33l/` |
> | `s4` | `adaptor/s4/` + `hmi_adaptor/s4/` |

---

### Step 1：读取信号规格表

```bash
feishu-sync-cli read_page_as_markdown "${SHEET_URL}" --force_refresh 2>/dev/null \
  > /tmp/mff_signals.md
```

从 markdown 中提取 B/C/D 列，构建信号列表。每行格式：

```
| [A列现有内容] | [B: CAN ID] | [C: 信号名] | [D: 值] | ... | [G: 时长 FM/5s/3s] |
```

> **行号计算**：飞书 sheet 行号 = markdown 行号 - ROW_OFFSET（默认 3）。

---

### Step 2：定义核心代码路径

根据平台参数设置关键文件路径：

```
BASE_DIR = /tmp/mff_*/adaptor/${PLATFORM}/mff_main/

关键文件:
- CONFIG     = ${BASE_DIR}/mfr_node/resource/mff_config.json
- COMMON_API = ${BASE_DIR}/state_machine/src/utils/common_api.cpp
- FUNC_STATE = ${BASE_DIR}/state_machine/ovrd_state/src/state_functioning.cpp
- NP_ACTIVE  = ${BASE_DIR}/state_machine/ovrd_state/src/state_mpilot/state_mpilot_active.cpp
- HMI_WIDGET = adaptor/${PLATFORM}/mff_common/hmi_adaptor_widget.hpp
- COMMON_ENUM= adaptor/${PLATFORM}/mff_common/common_enum.hpp
- COMMON_TYPE= adaptor/${PLATFORM}/mff_common/common_type.hpp
- SIGNAL_MAP = hmi_adaptor/${PLATFORM}/hmi_main/main_func/src/utils/signal_mapping.cpp
```

---

### Step 3：逐信号执行缺陷模式扫描

对规格表中每个信号，依次执行以下 4 类缺陷检测：

---

#### 🔴 模式 1：Static Flag 不复位（永久发送）

**特征**：使用 `static bool` 作为触发门控，触发后 flag 置 true 不再复位，导致目标值永久驻留 `pilot_output_info`。

**检测方法**：
```bash
# 搜索目标信号的 MREG_VALMEM_SET 赋值
grep -rn "MREG_VALMEM_SET.*${SIGNAL_FIELD}\|MREG_VAL_SET.*${SIGNAL_FIELD}" \
  ${BASE_DIR}/state_machine/ | grep -v "NO_DISPLAY\|NONE\|= 0\|= {}"

# 检查是否有 static bool 保护该赋值
grep -B10 -A5 "MREG_VALMEM_SET.*${SIGNAL_FIELD}" ${COMMON_API}
```

**判断标准**：
- 若赋值前有 `static bool has_xxx = false; if (!has_xxx) { has_xxx = true; ...SET... }` → **确认 Bug**
- 检查该枚举值是否在对应 config（如 `aln_warning_text_config`）中 → 若不在则**无超时保护**，持续发送

**输出格式**：
```
[Bug已确认] 持续发送缺陷
位置: common_api.cpp:LINE
根因: static bool has_xxx 置true后不复位，SIGNAL=VALUE永久驻留；且enum值N未在config配置，无超时控制。
修改建议: config中补充[N,0,5000,5000,0]；或在适当时机显式清零。
```

---

#### 🔴 模式 2：FixedFrameSignalEmitter NP 退出不重置

**特征**：`FixedFrameSignalEmitter{N帧}` 只在 NP Active 状态内调用 `update_interrupt`，退出 NP 时 emitter 未 reset，继续计帧发送。

**检测方法**：
```bash
# 1. 找到信号对应的 emitter 名称（在 common_type.hpp 的 EtcOutput struct）
grep -n "FixedFrameSignalEmitter\|emitter" ${COMMON_TYPE}

# 2. 确认 emitter 的唯一调用位置
grep -rn "update_interrupt\|\.update_interrupt" ${BASE_DIR}/state_machine/ | grep "${EMITTER_NAME}"

# 3. 检查 OvrdStateMPilot::on_exit 是否重置 emitter
grep -A30 "OvrdStateMPilot::on_exit" ${NP_ACTIVE} | grep -i "reset\|clear\|emitter"
```

**判断标准**：
- emitter.update_interrupt 仅在 NP Active 状态内调用（`state_mpilot_active.cpp`）
- `OvrdStateMPilot::on_exit()` / `OvrdStateNPActive::on_exit()` 中无 reset → **确认 Bug**

**输出格式**：
```
[Bug已确认] 退出NP后持续发送
位置: common_api.cpp:LINE (emitter定义), state_mpilot_active.cpp:LINE (唯一调用点)
根因: EMITTER_NAME{N帧≈Xs} 仅在NP active内触发，OvrdStateMPilot::on_exit未重置。
修改建议: 在OvrdStateMPilot::on_exit()中对所有etc_output_emitter成员调用reset()。
```

---

#### 🟡 模式 3：HmiTimingSignal 超大 Max 配置

**特征**：信号值在 `xxx_config` 中配置了极大的 `max_time_ms`（如 3600000ms = 1小时），触发后若无显式 clear，HmiTimingSignal 将持续输出长达数小时。

**检测方法**：
```bash
# 1. 查找信号对应的 config 字段名
grep -n "xxx_config\|signal.*config" ${BASE_DIR}/state_machine/src/utils/system_process.cpp | grep -i "${SIGNAL_KEYWORD}"

# 2. 读取 config 值
python3 -c "
import json, sys
with open('${CONFIG}') as f: cfg = json.load(f)
vals = cfg.get('hmi', {}).get('${CONFIG_KEY}', [])
# 格式: [enum_val, default, min_ms, max_ms, cooldown_ms, ...]
it = iter(vals)
for chunk in zip(*[it]*5):
    print(f'  value={chunk[0]}: min={chunk[2]}ms, max={chunk[3]}ms')
"

# 3. 检查 NP 退出时是否有显式 clear
grep -n "on_exit" ${NP_ACTIVE} | grep -v "//\|#"
```

**判断标准**：
- `max_time_ms > 60000`（1分钟）且 NP Active 退出时无显式清零 → **疑问项**
- `max_time_ms > 600000`（10分钟）→ **高风险疑问项**
- 特别关注：ManMachineCoDriving(23)=3600000ms、ROAD_CONDITION_COMPLICATED(59)=3600000ms、TLCTrafficLightNotice(8)=3600000ms

**输出格式**：
```
[疑问项] SIGNAL_NAME=VALUE(ENUM_NAME)
位置: FUNC:LINE
问题: config max=Nms(X小时/分钟)，[else-clear描述]，NP退出后若条件仍存在可持续发送X时间。
修改建议: config中将max改为5000ms；或在NP exit时显式清零。
```

---

#### 🟡 模式 4：Active State 内 SET，无对应 CLEAR

**特征**：信号在 NP/HNP/UNP Active 的 routine 函数中设置，但缺少 `else` 分支清零，或 `else` 清零逻辑在退出状态后不再执行。

**检测方法**：
```bash
# 1. 找到信号赋值位置
grep -rn "MREG_VALMEM_SET.*${SIGNAL_FIELD}" ${BASE_DIR}/state_machine/ovrd_state/ \
  | grep -v "NO_DISPLAY\|NONE"

# 2. 检查赋值上下文（有无 else 清零）
grep -B5 -A15 "MREG_VALMEM_SET.*${SIGNAL_FIELD}.*${ENUM_VALUE}" \
  ${FUNC_STATE} ${NP_ACTIVE}

# 3. 检查 on_exit 是否有清零
grep -A20 "on_exit" ${NP_ACTIVE} | grep "${SIGNAL_FIELD}"
```

**判断标准**：
- 有 `if (condition) { SET(value); } else if (current == value) { SET(NONE); }` → **OK**
- 只有 SET，无 else 清零，且 NP 退出后不再执行该函数 → **疑问项**

---

### Step 4：汇总结果并写回飞书

```python
import subprocess, json

SHEET_URL = "https://momenta.feishu.cn/sheets/${SPREADSHEET_TOKEN}"

findings = {}
# 填充每行的结论: {sheet_row: "findings text"}

for sheet_row, content in findings.items():
    range_str = f"{SHEET_ID}!{WRITE_COL}{sheet_row}:{WRITE_COL}{sheet_row}"
    vals = json.dumps([[content]])
    subprocess.run(
        ['feishu-sync-cli', 'write_sheet', SHEET_URL, range_str, vals],
        capture_output=True
    )
```

> **行号换算**：`sheet_row = markdown_line_number - ROW_OFFSET`
>
> 默认 ROW_OFFSET=3（markdown 第1行=标题，第2行=空行，第3行=表头，第4行=分隔符，第5行=第2行数据）。
>
> 请通过写入测试值验证行偏移：先写 A2 确认对应哪条记录，再调整偏移。

---

## 平台扩展指南

### 新增平台适配

在使用本 Skill 时，若目标平台不是 `byd`，按以下方式调整：

```
平台代码路径：adaptor/${PLATFORM}/
信号映射文件：hmi_adaptor/${PLATFORM}/hmi_main/main_func/src/utils/signal_mapping.cpp
Config 文件：adaptor/${PLATFORM}/mff_main/mfr_node/resource/mff_config.json
```

### 已验证平台

| 平台参数 | 项目名称 | 适配器路径 | 备注 |
|---|---|---|---|
| `byd` | 莲花山 / LHUAS | `adaptor/byd/` | 已完整验证 |
| `ep33l` | EP33L | `adaptor/ep33l/` | 路径已知，逻辑类似 |

### 信号规格表格式

本 Skill 默认处理如下列布局：

| 列 | 内容 |
|---|---|
| A | 检查结论（写入列） |
| B | CAN ID |
| C | 信号名称 |
| D | 信号值（十六进制） |
| G | 时长标注（FM / 5s / 3s） |

若表格列顺序不同，在参数中声明：
```
信号规格表: https://...
列映射: B=CAN_ID, C=Signal, D=Value, G=Timing
```

---

## 缺陷模式快速参考

### 已知高风险信号类型

| 信号字段 | Config Key | 高风险值 | max_time_ms |
|---|---|---|---|
| `aln_warning_text_v2` | `aln_warning_text_config` | 23 (ManMachineCoDriving) | 3,600,000 |
| `aln_warning_text_v2` | `aln_warning_text_config` | 59 (ROAD_CONDITION_COMPLICATED) | 3,600,000 |
| `aln_warning_text_v2` | `aln_warning_text_config` | 5 (BIG_THROTTLE_OVERRIDE) | 600,000 |
| `aln_warning_text_v2` | `aln_warning_text_config` | 61 (LONG_PRESS_HEADWAY_DEC_TO_UPLOAD) | ❌ 不在配置中 |
| `tlc_tl_notice` | `tlc_tl_notice_config` | 8 (SLOW_DOWN_IMMEDIATELY) | 3,600,000 |
| `noa_tl_notice` | `noa_tl_notice_config` | 1 (RedLightStop) | 5,000 ✅ |
| `traffic_speed_limit_on_state_prompt` | `traffic_speed_limit_config` | 1 | 1,200 ✅ |

### FixedFrameSignalEmitter 清单（BYD 平台）

| emitter 字段 | 帧数 | ≈时间@400Hz | 对应信号 | NP exit 是否重置 |
|---|---|---|---|---|
| `enter_toll_emitter` | 2000 | ~5s | Enter_toll_booth_status_prompt | ❌ 未重置 |
| `looking_for_channel_emitter` | 2000 | ~5s | Look_for_lane_status_cues | ❌ 未重置 |
| `enter_channel_emiter` | 2000 | ~5s | Toll_booth_channel_type_hint | ❌ 未重置 |
| `toll_take_over_emitter` | 2000 | ~5s | Toll_booth_traffic_control_tips | ❌ 未重置 |
| `bus_lane_change_warning_emitter` | 5000 | ~12.5s | (已注释，未使用) | N/A |

---

## Config 值解析工具

`mff_config.json` 中 config 为扁平数组，每 5 个元素为一组：
```
[enum_val, default_val, min_ms, max_ms, cooldown_ms, ...]
```

解析脚本：
```python
def parse_hmi_config(flat_list, stride=5):
    """解析 MFF HMI config 数组"""
    it = iter(flat_list)
    results = []
    for chunk in zip(*[it] * stride):
        results.append({
            "value": chunk[0],
            "default": chunk[1],
            "min_ms": chunk[2],
            "max_ms": chunk[3],
            "cooldown_ms": chunk[4]
        })
    return results

# 使用示例
import json
with open("mff_config.json") as f:
    cfg = json.load(f)
aln_config = cfg["hmi"]["aln_warning_text_config"]
for entry in parse_hmi_config(aln_config):
    if entry["max_ms"] > 60000:
        print(f"  ⚠️ value={entry['value']}: max={entry['max_ms']}ms ({entry['max_ms']//3600000:.1f}h)")
```

---

## 常见错误与解决

| 错误 | 原因 | 解决方法 |
|---|---|---|
| `wrong range=ZXXnPq!A277` | feishu write_sheet range 格式错误 | 使用 `A277:A277` 格式；先写 A2 验证行偏移 |
| sparse checkout 后目录为空 | 平台路径拼写错误 | 检查 `adaptor/byd/` vs `adaptor/BYD/` |
| config 解析结果为空 | config key 名称错误 | 先 `grep -n "xxx_config" mff_config.json` 确认 key |
| 信号值找不到 MREG_VALMEM_SET | 信号在父类或其他文件 | 扩大搜索范围到 `BASE_DIR` 全目录 |
| feishu 写入内容乱码 | Windows GBK 终端 | 用 Python 写入文件再用 UTF-8 读取，避免终端转码 |
