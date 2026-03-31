# Claude Skills

本仓库存放 Claude Code 的自定义 Skills，用于 Momenta HMI 开发工作流。

## 使用方式

### 一键安装单个 Skill

```bash
# Windows (Git Bash)
cp -r skills/<skill-name> ~/.claude/skills/

# macOS / Linux
cp -r skills/<skill-name> ~/.claude/skills/
```

### 一键安装全部 Skills

```bash
# clone 本仓库后执行
cp -r skills/* ~/.claude/skills/
```

之后在 Claude Code 中直接调用：

```
/<skill-name> [参数]
```

## 已有 Skills

| Skill | 触发词 | 功能描述 |
|---|---|---|
| [hmi-checklist](./skills/hmi-checklist/) | `/hmi-checklist`、`生成点检表`、`发版点检表` | 从飞书源用例文档生成 HMI 发版点检表，写入目标飞书表格，包含串联用例、文言/语音预期结果、ASCII 示意图 |
| [hmi-incident-analyzer](./skills/hmi-incident-analyzer/) | `/hmi-incident-analyzer`、`HMI事故分析`、`分析HMI工单`、`补全HMI事故字段` | 批量分析飞书Bitable中的行车/泊车碰撞事故工单，自动生成6个结构化字段（事故场景/原因/ADAS系统方案/HMI交互方案/关键词分类），批量写回飞书。500条工单 < 15分钟 |

## 依赖

- [Claude Code](https://claude.ai/claude-code) CLI
- [feishu-sync](https://momenta.feishu.cn/wiki/QT9PwFol4iZrnfkjPL4cr34Zn1b) Python 包（飞书操作类 skill 需要）

## 安装依赖

```bash
python -m pip install --extra-index-url https://artifactory.momenta.works/artifactory/api/pypi/pypi-momenta/simple feishu-sync -U
```

飞书授权（首次使用）：
```bash
python -m feishu_sync.retoken init_token --enable_autofill
```
