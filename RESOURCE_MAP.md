# Universal Novel Studio 资料地图

> 本文件是 LLM 的按需导航，不是新的规则源。冲突时以 `AGENTS.md` 的硬性不变量、当前书的 `project_bible.md`、题材档案和对应专题规则为准。

## 一、启动协议

1. 读取 `AGENTS.md`（只读入口与不可违反的工程规则）。
2. 运行 `python studio.py hello --json`（当前进度、下一步、可用资料提示）。
3. 按当前任务只读取下表对应的 Stage SOP 和角色 Skill。
4. 需要项目事实时使用 `status`、`pack`、`doctor`、`radar`；不要直接 glob 全部工作区。
5. 不确定命令参数时才运行 `python studio.py help --json`。

## 二、权威层级

1. `AGENTS.md`：全局硬性不变量、禁止操作、入口协议。
2. `novel_workspace/00_meta/project_bible.md`：本书个性化设定与覆盖规则。
3. `novel_workspace/00_meta/genre_profile.json`：题材文风、字数、配比、调度参数。
4. `agents/rules/novel_workflow.md`：Stage 0–4 唯一工程 SOP。
5. `agents/skills/*/SKILL.md`：当前角色的操作协议。
6. `agents/rules/novel_*.md`：文学规则，按需读取。
7. `README.md`：面向人类的项目说明，不作为创作规则依据。

## 三、按阶段读取

| 场景 | 必读 | 按需资料 | 主要命令 | 产出 |
|---|---|---|---|---|
| 新书初始化 | workflow Stage 0、`novel-director` | style、long_arc、brainhole、anti_ooc | `init`、`genre`、`doctor` | 设定、人设、卷纲、初始状态 |
| 细纲推演 | workflow Stage 1、`novel-beats-builder` | brainhole、long_arc、anti_ooc | `pack`、`schedule` | `03_outlines/**/beats/` |
| 正文起草 | workflow Stage 2、`novel-chapter-drafter` | style、anti_ooc、long_arc | `pack`、`memory` | `raw_drafts/` |
| 独立审校 | workflow Stage 3、`novel-continuity-guard` | style、anti_ooc | — | `finalized/` |
| 状态同步 | workflow Stage 4、`novel-state-syncer` | long_arc | `sync` | 提案、JSON SSOT、快照 |
| 体检/诊断 | 相关命令说明 | `help --json` | `doctor`、`radar` | 结构化诊断 |

## 四、三方 Agent 协作索引

- **主控 Agent**：负责导演、编排、工具调用、同步与快照；读取当前 Stage 所需资料。
- **起草 Agent**：`agents/skills/novel-chapter-drafter/SKILL.md`；使用全新物理隔离上下文，接收主控生成的最小充分章节任务包，只写 `raw_drafts/`。
- **审校 Agent**：`agents/skills/novel-continuity-guard/SKILL.md`；使用全新物理隔离上下文，读取指定 raw draft，输出 `finalized/`。
- **交接唯一规范**：`agents/rules/novel_workflow.md` 的“Agent 权限矩阵与交接协议”。
- **状态同步**：由主控调用 `sync/snapshot`；子 Agent 不写状态 SSOT。

## 五、按问题查资料

不确定现在该读哪份，先查这张表。

| 遇到问题 | 优先读取/运行 |
|---|---|
| 新书初始化和设定 | workflow Stage 0 + novel-director + `init` |
| 单章怎么写、细纲怎么推 | workflow Stage 1 + beats-builder + `pack`/`schedule` |
| 正文怎么起草、字数/文风 | workflow Stage 2 + drafter + style + `pack` |
| 角色会不会 OOC | anti_ooc + 该角色人物卡 |
| 能力升级/长线节奏掌握不准 | long_arc_and_pacing |
| 看点不够/套路化 | brainhole_and_pacing |
| 审校怎么执行 | workflow Stage 3 + continuity-guard |
| 状态怎么提案和同步 | workflow Stage 4 + state-syncer + `sync` |
| 伏笔沉睡/未回收 | schedule + chekhov_guns 视图 + long_arc |
| 状态/账本/道具不一致 | `doctor`、`rollback` |
| 想切手动/自动模式 | workflow SOP「工作模式」+ `python studio.py mode` |
| 用户说不满意/重写/暂停/继续 | workflow SOP「自然语言控制协议」；重写必须回 raw_drafts 重新审校 |
| 命令参数不确定 | `help --json` 代读源码 |

## 六、专题规则索引

- `novel_style.md`：题材文风、基调、配比、断章。
- `novel_long_arc_and_pacing.md`：长线、能力阶梯、经济和节奏。
- `novel_brainhole_and_pacing.md`：核心看点、爽点、反套路。
- `novel_anti_ooc.md`：角色动机、心智阶段、防 OOC。

专题规则是默认/参考层，不会取代本书设定或场景心流；完整文件保留，避免为了省 Token 丢失细节。

## 七、工作区资料边界

- `novel_workspace/`：唯一生产工作区。状态 JSON 是机器真值，Markdown 状态视图由引擎生成。
- `templates/`：初始化母版，只在 Stage 0 或模板维护时读取。
- `04_timeline_and_state/state_inbox/`：提案入口；AI 提案，不直接改状态 JSON。
- `05_manuscript/vol_*/raw_drafts/`：可修改初稿。
- `05_manuscript/vol_*/finalized/`：审校后的定稿，只能由 raw draft 重新审校生成。

## 八、禁止区

永远不要读取或直接编辑：`studio.py`、`tools/*.py`，以及状态 JSON/自动生成的状态 Markdown。工具行为通过公开 CLI 获取；状态变化通过提案和 `sync` 完成。
