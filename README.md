# Claude Skills

本仓库存放 Claude Code 的自定义 Skills，用于 Momenta HMI 开发工作流。

## 使用方式

将对应 skill 目录复制到本地：

```bash
# Windows
cp -r skills/<skill-name> %USERPROFILE%\.claude\skills\

# macOS / Linux
cp -r skills/<skill-name> ~/.claude/skills/
```

之后在 Claude Code 中直接调用：

```
/<skill-name> [参数]
```

## 已有 Skills

| Skill | 触发词 | 功能描述 |
|---|---|---|
| [hmi-checklist](./skills/hmi-checklist/) | `/hmi-checklist`、`生成点检表`、`发版点检表` | 从飞书源用例文档生成 HMI 发版点检表，写入目标飞书表格，包含串联用例、文言/语音预期结果、ASCII 示意图 |

## 依赖

- [Claude Code](https://claude.ai/claude-code) CLI
- [feishu-sync](https://momenta.feishu.cn/wiki/QT9PwFol4iZrnfkjPL4cr34Zn1b) Python 包（飞书操作类 skill 需要）
