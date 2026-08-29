# Gemini 入口垫片

本项目的唯一执行入口是 [`AGENTS.md`](AGENTS.md)。

## 开局

1. 读取 `AGENTS.md`。
2. 运行 `python studio.py hello --json`。
3. 按当前任务读取 [`RESOURCE_MAP.md`](RESOURCE_MAP.md) 指向的 Stage SOP、角色 Skill 或专题规则。
4. 只有不确定命令参数时才运行 `python studio.py help --json`。

不要读取 `studio.py`、`tools/*.py`；不要直接修改 `04_timeline_and_state/*.json` 或自动生成的状态 Markdown。完整的规则仍然保留，只按当前工作阶段加载。