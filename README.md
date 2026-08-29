# Universal Novel Studio

全题材自适应的 AI 协同长篇小说工作站。项目把文学判断与确定性工程工具分开：LLM 负责设定、叙事、角色和审校，Python CLI 负责文件、状态、统计、校验、账本和快照。

## 快速开始

```powershell
# 初始化新书
python studio.py init --title "书名" --genre "题材" --protagonist "主角名"

# 检查工作区
python studio.py hello --json
python studio.py doctor
```

LLM/Agent 的执行入口是 [`AGENTS.md`](AGENTS.md)，按阶段读取协议见 [`RESOURCE_MAP.md`](RESOURCE_MAP.md)。不要把本 README 当作创作规则源。

## 三方 Agent 创作流水线

```text
Stage 0  init → 设定、人设、卷纲、初始状态
Stage 1  pack → 细纲推演 → beats
Stage 2  主控任务包 → 起草 → raw_drafts
Stage 3  独立审校 → finalized
Stage 4  同步官撰写并复核提案 → 主控 sync → 状态与快照
```

起草 Agent 只写 `raw_drafts/`，审校 Agent 只写 `finalized/`，两者均不得写状态 SSOT。局部小问题由主控直接补丁，结构性问题回 raw draft 重新调用两个子 Agent。子 Agent 交付后销毁上下文，但保留生产文件和审计资料。

完整 SOP：[`agents/rules/novel_workflow.md`](agents/rules/novel_workflow.md)。

## 项目资料

- `AGENTS.md`：硬性工程规则、入口协议和资料索引。
- `RESOURCE_MAP.md`：LLM 资料地图、读取时机、命令与产出对照。
- `agents/rules/`：专题规则，按需读取。
- `agents/skills/`：总策划、编剧、主笔、审校官、同步官、编排者的角色协议。
- `templates/`：初始化母版。
- `novel_workspace/`：唯一生产工作区，默认被 Git 忽略。

状态层使用 JSON 作为机器真值源；同名 Markdown 是引擎生成的只读视图。AI 不直接修改状态 JSON，而是通过 `state_inbox` 提案和 `sync` 合并。

## 常用命令

```powershell
python studio.py --version
python studio.py help --json       # 参数不确定时使用
python studio.py mode              # 查看/切换 automatic|manual 工作模式
python studio.py status
python studio.py doctor
python studio.py pack ch_001 --json
python studio.py radar
python studio.py sync ch_001
python studio.py export
```

命令的完整列表和当前参数以 `python studio.py help --json` 为准；工程工具只提供结构化证据，语义裁决由 LLM/导演完成。

## 工作区安全

不要直接修改 `finalized/`、状态 JSON、自动生成的状态 Markdown、`processed/`、`failed/` 或 `snapshots/`。需要修改正文时回到 raw draft，重新审校；需要改变状态时提交正式提案后运行 sync。

## 开发者与维护

- **状态存储**：状态以 `04_timeline_and_state/*.json` 为机器真值，同名 Markdown 是由引擎自动生成的只读视图，不应手动编辑。
- **新书边界**：`init` 在 `novel_workspace/` 生成作品资产，并同步根目录 `novel_config.yaml` 的书名/题材。
- **公开 CLI 入口**：外部 Python 集成通过根目录 `tool_runner.py` 调用公开 CLI，不要导入 `tools/*` 内部模块，也不要用它写入状态 SSOT。
- **禁止修改核心**：`studio.py` 与 `tools/*.py` 属于禁读禁改区，Agent 一律通过 `python studio.py <command>` 使用工具能力。
