---
name: dgw-signal-checker
description: >
  DGW（域控制器网关）信号合入检查工具。自动检查指定信号是否在 mid_class_byd_idc 等仓库的
  DGW 代码中正确赋值/合入。支持单个信号名称直接输入，或从飞书文档批量提取信号列表。
  输出未合入信号清单、可信度分析、代码位置定位，并提供修复建议，可选写回飞书。
  触发词：DGW信号检查、DGW信号合入、dgw-signal-checker、检查DGW信号、信号是否合入、
  置灰信号合入、DGW是否发送
license: Proprietary
allowed-tools:
  - Bash
  - Read
  - Write
  - Glob
  - Grep
---

# DGW 信号合入检查 Skill

## 用途

自动检查指定信号是否在 MCU DGW（Domain Gateway）代码中正确赋值/合入。

**核心痛点解决**：DGW 代码运行在 MCU 上，**没有任何 print 输出**，mviz 也无法观测到 DGW 层的信号赋值逻辑。传统验证方式需要手动阅读数千行 C 代码，或者上车实测。本工具通过静态代码分析，在数分钟内给出结论。

## 触发示例

```
/dgw-signal-checker
  信号: EffIpv_Gray_Sts
  仓库: https://devops.momenta.works/Momenta/VehiclePlaftform/_git/mid_class_byd_idc
  分支: lhs/r6
  平台: SR_OrinX2
  场景: dgw_lowpower
```

```
/dgw-signal-checker
  信号文档: https://momenta.feishu.cn/wiki/N7JxwVxGSiiBVukqafjcfDWWnlh
  仓库: https://devops.momenta.works/Momenta/VehiclePlaftform/_git/mid_class_byd_idc
  分支: lhs/r6
  平台: SR_OrinX2
  场景: dgw_lowpower
  输出到飞书: https://momenta.feishu.cn/wiki/xxx
```

也可以自然语言触发：
```
帮我检查 lhs/r6 分支 SR_OrinX2 平台，节能模式下这几个信号有没有合入：
TBA_Gray_Sts、ADASLight_Gray_Sts、Ins_UI_Interface_Gray_Sts
仓库: https://devops.momenta.works/Momenta/VehiclePlaftform/_git/mid_class_byd_idc
```

## 参数说明

| 参数 | 是否必填 | 说明 |
|---|---|---|
| 信号 | 二选一 | 单个或逗号分隔的多个信号名称（直接写，如 `TBA_Gray_Sts, EffIpv_Gray_Sts`） |
| 信号文档 | 二选一 | 飞书文档 URL，工具自动提取信号名称（支持 `_Gray_Sts`、自定义后缀或指定列） |
| 仓库 | 必填 | git 仓库地址（Azure DevOps 内网） |
| 分支 | 必填 | 要检查的分支名 |
| 平台 | 必填 | 平台目录名，如 `SR_OrinX2`、`HC_OrinX2`、`HT_OrinX2` 等 |
| 场景 | 可选 | 要检查的函数/场景名，默认 `dgw_lowpower`（节能模式）。可填函数名或描述性场景 |
| 信号后缀 | 可选 | 从文档提取信号时的后缀过滤，默认 `_Gray_Sts`；可改为 `_S`、`_Sts` 等 |
| 输出到飞书 | 可选 | 目标飞书文档/wiki URL，若指定则将结果写入该文档 |

---

## 执行流程

### Step 1: 环境检查

```bash
git --version 2>/dev/null && echo "OK: git" || echo "NEED: git"
feishu-sync-cli --help 2>/dev/null && echo "OK: feishu-sync-cli" || echo "NEED: feishu-sync-cli"
# 若未安装 feishu-sync-cli：
# python3 -m pip install --extra-index-url https://artifactory.momenta.works/artifactory/api/pypi/pypi-momenta/simple feishu-sync -U
```

### Step 2: 解析信号列表

**情况 A：直接输入信号名称**

用户提供的信号名称（逗号/换行分隔）直接使用，存入列表。

**情况 B：从飞书文档提取信号**

```bash
feishu-sync-cli read_page_as_markdown "FEISHU_DOC_URL" > /tmp/dgw_check_signals.md 2>/dev/null
grep -oE '[A-Za-z_][A-Za-z0-9_]*_Gray_Sts' /tmp/dgw_check_signals.md | sort -u > /tmp/dgw_signal_list.txt
cat /tmp/dgw_signal_list.txt
```

若用户指定了不同后缀（如 `_S`、`_Sts`），相应调整正则。
若从飞书表格提取特定列，用 Python 解析 markdown 表格行提取目标列值。

### Step 3: Sparse Checkout 代码仓库

```bash
REPO_URL="用户提供的仓库URL"
BRANCH="用户提供的分支"
PLATFORM="SR_OrinX2"  # 用户指定平台
WORK_DIR="/tmp/dgw_check_repo"

mkdir -p "$WORK_DIR" && cd "$WORK_DIR"
git init && git remote add origin "$REPO_URL"
git sparse-checkout init --cone
git sparse-checkout set "01_APP/${PLATFORM}/DGW/DGW_Main"
git fetch --depth=1 origin "$BRANCH"
git checkout FETCH_HEAD 2>&1 | tail -3
```

若 sparse checkout 不支持，退化为全量 clone：
```bash
git clone --depth=1 -b "$BRANCH" "$REPO_URL" "$WORK_DIR"
```

关键文件：`01_APP/{PLATFORM}/DGW/DGW_Main/dgw_mapping.c`（主映射逻辑）
和 `DGW_Cp_Main.c`（主循环调用顺序）。

### Step 4: 提取目标场景函数体

```bash
DGW_MAPPING="$WORK_DIR/01_APP/${PLATFORM}/DGW/DGW_Main/dgw_mapping.c"
SCENARIO="dgw_lowpower"  # 用户指定场景函数名

# 提取函数体
python3 -c "
import re, sys
content = open('$DGW_MAPPING').read()
m = re.search(rf'void\s+$SCENARIO\s*\([^)]*\)\s*\{{(.*?)\n\}}', content, re.DOTALL)
print(m.group(0) if m else '[未找到函数]')
"
```

### Step 5: 逐信号搜索与分类

对每个信号 SIGNAL 执行：

```bash
# 在目标函数中精确搜索
FUNC_BODY=$(python3 -c "
import re
content = open('$DGW_MAPPING').read()
m = re.search(rf'void\s+${SCENARIO}[^{{]*\{{.*?^\}}', content, re.DOTALL|re.MULTILINE)
print(m.group(0) if m else '')
")

IN_TARGET=$(echo "$FUNC_BODY" | grep -c "${SIGNAL}")

# 全文搜索赋值（排除 encode/decode 等工具行）
ALL_ASSIGNS=$(grep -n "${SIGNAL}" "$DGW_MAPPING" | grep "=" | grep -v "encode\|decode\|is_in_range\|pack_left\|pack_right\|unpack_")

# 判断分类
if echo "$FUNC_BODY" | grep -q "${SIGNAL}.*=.*1\|= 1.*${SIGNAL}"; then
    echo "✅ 已合入: $SIGNAL"
elif echo "$ALL_ASSIGNS" | grep -q "${SIGNAL}.*=.*_SR\.${SIGNAL}"; then
    echo "⚠️ pass-through: $SIGNAL (依赖MFF/SOC)"
elif echo "$ALL_ASSIGNS" | grep -q "."; then
    echo "⚠️ 有赋值但不在目标场景: $SIGNAL"
else
    echo "❌ 未合入: $SIGNAL"
fi

echo "  代码引用: $ALL_ASSIGNS"
```

### Step 6: 生成结构化报告

将所有信号的检查结果汇总，输出以下格式报告。保存到 `/tmp/dgw_check_result.md`。

报告包含：
1. **检查摘要**（仓库、分支、平台、场景、检查时间）
2. **✅ 已合入信号表格**（信号名、赋值位置、赋值值）
3. **❌ 未合入信号表格**（信号名、分析结论、可信度、修复建议）
4. **⚠️ Pass-through 信号表格**（信号名、来源、可信度、修复建议）
5. **修复代码模板**（可直接添加到目标函数的 C 代码片段）

### Step 7: 写入飞书（可选）

若用户指定了输出目标：

```bash
# 创建独立文档
feishu-sync-cli create_doc   --title="DGW信号检查报告-${PLATFORM}-${BRANCH}-$(date +%Y%m%d)"   --markdown="@/tmp/dgw_check_result.md"

# 或创建 wiki 子页面
feishu-sync-cli create_page "WIKI_URL" "DGW信号检查报告" "@/tmp/dgw_check_result.md"
```

---

## 可信度等级

| 等级 | 含义 | 典型场景 |
|---|---|---|
| 🔴 高 | 无任何有效赋值路径，100% 确认缺失 | dgw_lowpower() 中完全不存在该信号赋值 |
| 🟡 中 | 存在条件性赋值，但目标场景可能未覆盖 | 在其他函数有赋值，但不在目标场景函数中 |
| 🟢 低 | 存在赋值但逻辑复杂，需人工二次确认 | 嵌套条件或运行时计算决定的赋值 |

---

## 平台目录映射

| 平台参数 | 目录路径 | 车型/项目 |
|---|---|---|
| `SR_OrinX2` | `01_APP/SR_OrinX2/DGW/DGW_Main/` | BYD 莲花山（LHUAS） |
| `HC_OrinX2` | `01_APP/HC_OrinX2/DGW/DGW_Main/` | BYD 汉城 |
| `HT_OrinX2` | `01_APP/HT_OrinX2/DGW/DGW_Main/` | BYD 汉唐 |
| `SQ_SF_OrinX2` | `01_APP/SQ_SF_OrinX2/DGW/DGW_Main/` | BYD 宋/秦 SF |
| `UFE` | `01_APP/UFE/DGW/DGW_Main/` | UFE 平台 |
| `UFE_OrinN2` | `01_APP/UFE_OrinN2/DGW/DGW_Main/` | UFE OrinN2 |
| `UXE_OrinX2` | `01_APP/UXE_OrinX2/DGW/DGW_Main/` | UXE OrinX2 |
| `RCAR` | `01_APP/RCAR/DGW/DGW_Main/` | R-Car 平台 |

---

## 重要注意事项

1. **0x2F2 消息特殊处理**：AES_Gray_Sts、AIEM_Gray_Sts、APA_Gray_Sts 位于 0x2F2 消息，通过 `memcpy` 直接转发 MFF 共享内存，不走结构体赋值。节能模式下需直接修改 `DGW_Msg_HMI_2F2_S4_data` 对应字节位。

2. **0x1FF 子ID 区分**：`ADS_0x1FF_S1_SR`（MFF 子ID 1 输入）、`ADS_0x1FF_S4_SR`（MFF 子ID 4 输入）、`ADS_0x1FF_SR`（最终 CAN 输出）是不同结构体。节能模式下需赋值给最终输出结构体 `ADS_0x1FF_SR`。

3. **Pass-through 信号**：部分信号在正常模式下由 MFF（SOC 侧）通过共享内存传递给 DGW，DGW 只做 pass-through。SOC 断电后这些信号无法收到新值，必须在 `dgw_lowpower()` 中显式覆盖赋值。

4. **Sparse Checkout 加速**：仓库约 1GB+，全量 clone 约需 20 分钟。Sparse checkout 只拉取目标平台的 DGW 目录（~50MB），约 2 分钟完成。

5. **静态分析局限**：本工具为静态代码分析，运行时动态条件（信号值由计算决定）需人工确认。🟡 中可信度结论建议结合实车测试。
