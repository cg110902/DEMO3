# Novel Studio 重写规划 v1.1（定稿 + 卷一生产回流）

> 取代 v0.1/v0.2。旧工程 `/home/user/DEMO3` 只读借鉴。v1.0 定稿变化：
> ① 新增 §6.5 任务书与双重创作协议（一次性子 Agent + 每章不同的限制）；
> ② §11 四项小决策全部拍板（含题材参考并成单文件 genre_guide.md）；
> ③ status 增加逐章流水线行（断线自愈）；④ 审校由"校对"升格为"重铸"。
>
> **v1.1（2026-08-29，卷一 6 章生产暴露的问题全部修复，均为白名单内小改）**：
> ① `evidence style` "仿佛…一般"正则收紧（"仿佛那一寸"类误报清零）；
> ② `para_head_repeat` 剥引号起头（对话驱动章不再被误计，叙述段真复读仍计）；
> ③ `evidence words` 增 cjk_spread/cjk_stdev（跨章长度方差只数不判——章长均匀病的量化入口）；
> ④ `sync` 对非规范命名提案给出改正路径（在途提案每章仅一份；章后修订并入下一章提案）；
> ⑤ inbox README 样例补 place upsert 与 status 枚举警示（生产两次踩坑）；
> ⑥ craft 新增"章长方差"与"guard 选词"两条默认值；workflow Stage 1 自查加两问（带错开/人物卡承诺回写）；
> 全部改动零新命令、零新文件、零 schema 变更（words 新字段除外）。
>
> **v1.2（2026-08-29，审校语义修正，用户裁决）**：Stage 3 "审校重铸"更正为**打磨与校对**两幕——
> 审校承担商业网文级全文润色（顺/爽/去 AI 味等动态要求由主控逐章装进任务书新节「打磨重点」
> 下达，此为全章最贵的一次输出）+ 六项机械清单校对；情节事实零改动，坏在情节层 = 拒收回
> Stage 2。任务书四节→五节。check 同日兑付"front-matter 超键拦截"（AGENTS 禁令 6 落地）。
> **v1.3（2026-08-29，M6 首批落地，拍板顺序之 D1→P3→E1/E2）**：命令 9→10——新增
> `proposal new <ch>`（骨架预填 schema/chapter/operation_id，只打印不落盘）；`evidence all`
> （五件套一次聚合，单章引擎往返 4→1）；`evidence file <相对路径>`（单篇实测——起草/改稿
> 场景数 raw，与定稿同一把尺 `_stats_one`，style 各章随之带 cjk）。D1 docs-as-tests 上线：
> 规范文档教的每条命令必须过 argparse，命令目录三处（parser/help/COMMAND_HELP）互为镜像——
> "docs 说话 code 不办"自此有闸。附录 A 增第 7 条。其余批次 ch_007 收章后开实施。

> **v1.4（2026-08-29，ch_007 收章后 M6 次批）**：P1 审校合同闸门——`checks.review_gate` 于
> sync 合并前核对注记「验收打钩」覆盖（缺答/缺✓✗/✓短证据 = 拒绝封存且不落半成品；beats 无
> 验收节、注记缺席之代笔例外均不拦）；ch_008 起为硬合同，卷一旧注记不回改。P2 `guard_extra`
> 八键（竖线词表适配极简 YAML 子集）——`evidence style/file` 按本章词表计数标
> `guard_extra_scoped`，键扩容三处同步流程首走。E4 变体落地：status 下一步区账上提醒
> （failed/ 积压 + 距到期 ≤2 章的线）。均属附录 A 既有类目（校验与统计），白名单未扩。

> **v1.5（2026-08-29，M6 收官批）**：D3 存量清点——补 `candidate_leak` 拦截（禁令 6 全量
> 兑付，只扫 manuscript）、AGENTS 不变量口径改准；E3 分景起草入任务书/drafter 合同（字数自查
> 吃 `evidence file <raw> <章>`）；R1 reader 岗位 SKILL + workflow「卷末」节 + 交接"恰好三样"
> 豁免款；R2 剧透盲测协议（M/N 三档牌，只喂「目标」节防剧透）；R3 target_ch 全局章号口径
> 入 craft。M6 批次（D1–D3/P1–P3/E1–E4/R1–R3）全部落地，104 测全绿。

---

## 1. 目标与裁决记录

### 1.1 不变的目标
- 五阶段流水线：Stage 0 初始化 → Stage 1 细纲（主控）→ Stage 2 起草（独立 Agent）→ Stage 3 审校（独立 Agent）→ Stage 4 同步（主控）。
- 开局协议：读规范（AGENTS.md）→ 地图指引 → `studio status` 看进度和下一步。
- Stage 0 = 按题材把 templates 填成真实资产。
- LLM 干一切灵活的活；Python 只干死板的活（白名单制）。
- 产出文风目标：**拟人化、章节结构与行文毫无规律**，反 AI 味、反套路复读。

### 1.2 用户裁决（v0.1 §11）
| 决策点 | 裁决 |
|---|---|
| pack | 只打包必要信息，但不能太少 → §6 三层触发装配设计 |
| 依赖 | 纯 stdlib（pytest/ruff 仅 dev） |
| 审校写入权 | 审校直接写 `final/`；主控终检，小问题直接改（§4.3） |
| 目录前缀 | 去掉 `00_meta/…` 编号（§7.1） |
| 多 Agent | 宿主负责 spawn/隔离/回收，仓库只定协议（skills = 交接合同） |
| 卷结构 | 由我定：`outlines/vol_XX/` + `manuscript/vol_XX/{raw,final}/`，状态全局不分卷 |

### 1.3 反过度工程的元原则（对"老项目搞得太复杂"的正面回应）
1. **单一知识源**：任何一条知识（规则/格式/流程）只允许存在于一个文件里，其他位置只能引用锚点，禁止复述。
2. **格式约束最小化**：只有"要被机器消费"的文档才有格式契约（state JSON、提案、evidence）；给 LLM 和人看的文档（圣经、人物卡、大纲、正文）**零格式义务**，模板只是"带几句引导语的容器"。
3. **能合并就不拆分**：新增文件必须回答"现有哪个家为什么装不下"；回答不出 = 不许建。
4. **每份文档有行数硬预算**（超预算 = 设计问题，不是排版问题）。
5. **判断权与统计权分离**：工具输出"数出来的事实"永不命名为判断（不出现 `warning/建议/疑似` 字样在 evidence 输出里；结论性语言只属于 check 的 errors，且 errors 只允许是 schema/算术类事实）。

## 2. 业界机制借鉴（研究结论 → 本设计采纳项）

| 来源 | 机制 | 我们采纳什么 |
|---|---|---|
| SillyTavern World Info（lorebook） | 条带关键词，正文中出现 key 即注入；条目可递归触发其他条目；有 token 预算规则；概率门控制造多样性 | pack 的 **P1 触发层**：beats 文本 × 实体别名表 → 确定性注入；递归深度 ≤2；预算自报 |
| Novelcrafter Codex | "静态笔记杀死动态故事"：Codex 条目 + Progressions（按时间轴赋值的动态进展） | **卡状分离**：entity 卡 = 静态底色（bible 文档），动态状态/进展一律进 state JSON；pack 同时呈现两者并标明"当前值" |
| NovelAI Lorebook | 长文一致性主要靠 lorebook；但"AI 只知道自己被喂的" | 一致性证据必须**主动进包**而非指望 LLM 记得去查（P0/P1 兜底），P2 只作补充 |
| ainovel-cli（GitHub） | 500+ 章自适应上下文：全量/滑窗/分层摘要三档；压缩后"恢复包"防失忆；从伏笔/角色/状态/关系四维推荐相关章节；draft 后强制 check_consistency | 记忆**三温度模型**（§8.2）；pack 附"相关旧章指针"（只给章号+一句话，不给全文）；Stage 4 前 sync --dry-run 即"先体检后封存" |
| Anthropic《Building Effective Agents》 | prompt chaining + 程序化 checkpoint；evaluator-optimizer 回路；"高频低复杂度任务用确定性代码而非 LLM"；评估标准不可靠时回路会空转 | Stage 0-4 = 带 checkpoint 的链；审校 = evaluator（其判据 = craft 清单 + evidence 数字，防止空转）；工具白名单正是"代码优先"原则 |
| AGENTS.md 开放规范 | 纯 markdown、无必填字段、就近文件覆盖、60k+ 仓库在用 | 我们的协议文件全部用 plain markdown + front-matter 仅存少量 key；权威层级仿"就近覆盖"：本书圣经 > 通用 craft 默认 |
| AI-Practical-Lab/novel-writer (v3.0) | Skill 化分发（宿主 Agent 执行）；YAML 角色卡；检查点快照；"经验进化"：记录用户修改意见持续改进 | 仓库=协议文档+确定性引擎、宿主=编排（已裁决）；新增：**导演日志的"纠正回流"**——用户改稿意见按卷提炼成本书红线清单，注入每章 pack（§5.6） |

## 3. 三层体系总览（各司其职的总图）

```
┌─ 文档层（LLM 的"代码"）──────────────────────────────┐
│ AGENTS.md     宪法：禁令/不变量/权威层级/开局地图       │
│ workflow.md   剧本：阶段×角色×产物×退回路径×控制语义     │
│ craft.md      内功：文学规则默认值（可被本书覆盖）       │
│ skills/×5     角色卡：岗位说明书（交接合同）             │
│ genre_guide.md 参考书：题材选择词汇+易翻车点（只供阅读） │
└──────────────────────────────────────────────────────┘
┌─ 数据层（工作区 SSOT）───────────────────────────────┐
│ bible/ characters/ outlines/ manuscript/ log/（自由文本）│
│ project.json（书配置）  state/×6 JSON（机器真值）        │
│ state/inbox（提案）  state/snapshots（审计）             │
└──────────────────────────────────────────────────────┘
┌─ 引擎层（PY，死板白名单）─────────────────────────────┐
│ studio.py 薄壳 → engine/{cli,common,state,pack,evidence,│
│ checks,snapshot,schemas}  9 命令，7 模块                 │
└──────────────────────────────────────────────────────┘
```

**一条知识往哪放（裁决程序）**：
1. 违反会导致生产事故、且可用代码强制 → AGENTS.md（禁令）+ 引擎校验；
2. 关于"什么时候谁做什么、产物交到哪" → workflow.md；
3. 关于"怎样算写得好"、可被本书推翻 → craft.md；
4. 关于"这个岗位坐下后手往哪放" → 对应 SKILL.md；
5. 关于"某题材的偏好与套路库" → genre_guide.md；
6. 关于"这本书是什么" → 工作区 bible/（本书圣经）；
7. 关于"现在世界处于什么状态" → state/ JSON（提案制）；
8. 都不是 → 不写。

## 4. 文档体系重设计（rules / skills / templates 各司其职）

### 4.1 文件清单与预算（合计 ≈ 1000 行，旧工程同层 ≈ 3000+ 行且重叠）

| 文件 | 职责（只写这些） | 明确不写 | 预算 |
|---|---|---|---|
| `AGENTS.md` | 硬禁令、5 条创作不变量、权威层级、开局协议、「阶段×资料×命令」地图表（吸收旧 RESOURCE_MAP，不再单独成文） | 任何解释性长文、文学建议 | ≤120 行 |
| `agents/rules/novel_workflow.md` | Stage 0–4 的唯一 SOP：输入合同/动作/输出合同/退回边；角色权限矩阵；manual/automatic；自然语言控制协议；宿主交接协议（spawn 子代理时主控传什么） | 文学规则、格式细节 | ≤260 行 |
| `agents/rules/novel_craft.md` | 文学默认规则单一集合：视角与信息差 / 能力阶梯与代价 / 钩子与爽感节奏 / 反公式化与拟人化（§5 全文）/ 角色动机与防 OOC / 句式与语域词汇表 | 流程、禁令、题材专属内容 | ≤280 行 |
| `agents/skills/{director,beats-builder,drafter,guard,syncer}/SKILL.md` | 岗位合同：使命(1 句)/输入(读哪些文件)/动作(编号步骤)/输出(写哪些路径)/禁区/退回与拒收条件 | 复述 craft 或 workflow（用锚点引用） | 各 ≤70 行 |
| `genre_guide.md`（单文件） | 每题材 ≤15 行：可玩词汇表、默认偏好（字数带/配比感/钩子习性）、常见翻车点、1~2 条反套路建议；首批 8 题材（玄幻/都市/悬疑/科幻/言情/武侠/无限流/治愈）+ 通用节；**全部是选择题素材，不是写作公式** | 任何机器消费格式 | ≤160 行 |
| `templates/*.md` | 交付物容器（§4.4） | 写作模式教学 | 各 ≤40 行 |

旧 4 份专题 rules（style/long_arc/brainhole/anti_ooc）合并为一份 `novel_craft.md`——它们互相引用、内容重叠（节奏与钩子被三个文件各说一遍），是旧项目"过度设计"的典型；合并后按主题分节，引用一律走 `#节锚`。

### 4.2 权威层级（简化为两层 + 记录义务）
`AGENTS.md 禁令` > `本书 project_bible.md 的显式覆盖` > `craft/genre_guides 默认`。
覆盖必须写在圣经"本书偏离清单"一节（一句话 + 理由），否则视为未发生——替代旧 T0–T3 四级制（过度设计）。

### 4.3 写权限矩阵（唯一事实，workflow 里只放这张表）

| 角色 | 读 | 写 |
|---|---|---|
| 主控（导演/编排一体，orchestrator skill 取消并入 AGENTS） | 一切 | `project.json`、`bible/`、`outlines/`、`state/inbox/` 提案、`log/`、final 的**文字级终检补丁**（见下） |
| 起草 Agent | 一切（读自由） | 仅 `manuscript/vol_XX/raw/` |
| 审校 Agent | 一切 + evidence | `manuscript/vol_XX/final/`（定稿直写）+ 审校注记 `log/review/ch_XXX.md` |
| 引擎 | 一切 | `state/*.json`、快照、processed/failed、evidence 缓存 |

**审校直写 + 主控终检**（用户裁决）：主控对 final 只做"落地检查"——错字/漏网格式/正文泄露工程标记，发现即直改（改动记入 `log/audit/ch_XXX.md` 一行注记）；凡涉及情节/设定的问题一律回 raw 重走审校，**不许**主控越级改内容。"文字级"与"内容级"的分界清单写进 workflow（≤10 行），避免灰色地带。

### 4.4 templates：交付物容器，不是写作枷锁（重新设计的关键）
- 旧模板把"项目圣经怎么分 9 节、人物卡怎么排表"定死了——这本身就是模板化写作的源头之一。
- 新原则：**只有两类文档需要格式**：
  1. 机器消费物：提案（JSON schema 在 `schemas/`，给同步官看的样例 `state/inbox/README.md`）；
  2. 需要被检索键定的头信息：beats 与章节的 front-matter（仅 4~6 个 key：`chapter/vol/form/voice/words_target/refs`）。
- 其余模板 = 文件名 + 一段 ≤6 行的"该装什么"引导注释，正文结构完全自由。
- 槽位协议保留 `{{slot:id|说明}}`（供 init 替换与 check 计数），但**不再用 `[中文方括号]` 正则猜占位符**。

每个 SKILL.md 是**给被 spawn 的上下文一个全新 Agent 看的唯一文件**，因此必须自足：开头 3 行交代"你在整条流水线的位置 + 你收到的 pack 里有什么"，然后才是动作步骤。规则引用一律写成"按 craft#钩子 自查"这种锚点，不复述内容——保证角色卡可以独立演进不脱节。

## 5. 拟人化风格引擎（反毫无规律 → 制造有记录的"无规律"）

> 洞察：AI 文章不像人，根源不是文笔而是**流程本身就是模板**——每章同样的三段式、每章末尾同一种钩子、句式长度均匀。因此反公式化必须在流程上有机制，而不能只靠"写得生动点"的口号。以下机制全部落在 LLM 协议层（craft + workflow），引擎只提供两项机械辅助（style 指纹统计、避免记录查询），零判断。

1. **结构形态库（form dice）**：craft 提供 ≥8 种章型（单场景章/双线剪辑/静水流日常章/插叙回溯章/对话驱动章/动作长镜头/书信文书章/中间开始型…），Stage 1 主控为每章选 form 写入 beats front-matter；硬约束只有两条：与上一章同 form 需在 beats 头写明理由；同卷内单一 form ≤40%（占比是 `evidence style` 数出来的，谁超了主控在下卷调整）。
2. **章级风格档（style_notes）**：每章 beats 附带 4 个旋钮——视角距离（贴耳/旁观/远观）、句长倾向（短促/绵长/交替）、章首手段、章尾方式（强钩/弱收/悬置/反高潮）；主控在题材允许域内轮换着取，避免连章同档。
3. **钩子强度正弦**：废除旧 `ending_style: strong_hook` 一票制；craft 默认"连续强钩 ≤2 章、每 5 章至少 1 次弱收或静章"——节奏本身不规律。
4. **字数反均匀**：pack 报告字数带仅作参照；craft 明示"同卷章字数方差过大不扣分、过小才呆板"；evidence `words` 逐章报数供主控与审校看趋势（不判达标与否）。
5. **语癖黑名单（tics）**：本书级"禁用句式/口癖/高频喻体"清单存 `project.json.style_guards`（主控按卷从 director_log 的用户修改意见中提炼回流——借鉴 novel-writer 的"经验进化"）；起草与审校各自对照自查；`evidence dup` 的 n-gram 重合数只兜底抓复制级雷同。
6. **反思节拍**：每卷终，主控写 10 行内"本卷模式自查"入 director_log（哪类章型/钩子用多了、读者向反馈），影响下卷 dice 权重——生成性 Agent 的 reflection 环，人写死的是节拍，内容判断全在 LLM。
7. **拟人保险丝（机械，不裁决）**：`evidence style ch_X` 输出句长分布（均值/方差/最长句占比）、对白行占比、段首 2 字模式重复率、"不是…而是…"等 6 个 AI 高频句式计数。审校拿数字判"像不像人"，引擎永不说"可疑"。

## 6. pack 设计（必要，且不能太少）

`studio pack ch_XXX [--lean|--full] [--open <相对路径>] --json`

```
P0 热层（恒全给，≈1.5~2.5k tok）
  ├─ current.json 全量摘录（状态小，永不裁）
  ├─ 本章 beats 原文
  ├─ 上一章 final 尾 600 字（衔接余温）
  └─ 硬提醒（纯算术事实）：目标章号==本章或已过期的线、未澄清误会、style_guards 清单、
     本书偏离清单标题行、"form 与上章相同"提示
P1 温层（触发装配，≈2~4k tok）—— lorebook 机制
  ├─ 扫描 beats 文本 × entities.json 别名表（最长匹配优先，确定性）
  ├─ 命中实体 → 注入「卡片摘要（静态，取 entity.summary）+ 动态状态（state 内当前值）」
  ├─ 递归一层：注入内容再命中新实体 → 只补其一行摘要（深度 ≤2，防膨胀）
  └─ 梗概脊柱：全书每章一句话（上限 40 章，超出取最近）
P2 冷层（索引，恒 ≤1k tok）
  ├─ 工作区文件清单：路径+估算 tokens+一句话描述
  ├─ 相关旧章指针：命中实体在近 10 章的出现分布（章号+出现次数，不给正文）
  └─ 扩展指令：--open <path> 由调用方显式取原文
```
- 输出尾部自报 `budget_report`（各层实算 tokens）；`--lean` 只给 P0+硬提醒；`--full` 把 P1 命中的卡全文附送。
- 设计论证：必要性由**触发完备性**保证（beats 提到的实体必到包，NovelAI 教训——一致性不能赌 LLM 记得去查）；不臃肿由"没提到的一律只给指针"保证。相比旧 pack 的"相关性打分+预算裁剪"启发式，别名触发是 100% 可解释、可在 entities.json 修复的——**语义上移给"注册别名"这个动作本身（LLM 维护表），匹配永远是死板字符串**。

## 6.5 任务书与双重创作（一次性子 Agent 协议）

> 用户既定原则：起草与审校都**只做一件事、交付即销毁**——算力单点足额花在每一章上；
> 同一章被完整创作两次，审校不是校对而是再创作。子 Agent 不自由发挥：全部限制由主控在
> 派发时随任务书传递，**每章的限制均不一样**，这本身就是灵活性的来源。

**任务书（brief）= beats 文件尾部区块**（不新建文件，主控在 Stage 1 末尾写好，pack 的 P0 整块投递）：

```
---
chapter: ch_007
vol: vol_01
form: 双线剪辑                 # 结构形态（§5.1 章型库）
pov: 林逐夜·贴身第三人称        # 本章视角
words: 2600-4200              # 目标带（仅参照，§5.4 反均匀）
style_notes: 短句急雨 | 章首中间开始 | 章尾弱收      # 三旋钮（§5.2）
---
## 目标            ← 本章必须达成什么，可核查条目列表（推进了什么、兑现了什么线）
## 必须保留         ← 起草与审校都不得违反的事实不变量（如：主角仍不知 B 身份）
## 本章禁忌         ← 本书语癖红线（style_guards）+ 主控追加的本章特定禁忌
## 验收             ← 主控写给审校的逐条判据：≤6 条，每条可在正文中核查，禁形容词
```

**交接协议**（宿主负责 spawn/隔离/回收，主控负责装配，本仓库只定合同）：
- 起草 Agent 输入 = 任务书 + pack P0 + P1（自足，**不可反问**）；只写 `raw/ch_XXX_vN.md`；交付即销毁，文件留审计。
- 审校 Agent 输入 = 任务书 + raw + P0 + 可自跑只读 `evidence`；有**完整重铸权**（调结构、改句法节奏皆可），
  唯一硬约束是不得违反「必须保留」「目标」两节；写 `final/ch_XXX.md` + `log/review/ch_XXX.md`
  （逐条对照「验收」打钩并留一行证据引用）。
- 拒收语义：审校判定 raw 不可救 → 写 `log/review/ch_XXX.reject.md`（理由+缺什么语境），主控决定补派
  起草或先修 beats；**同章拒收 ≤2 次**，第 3 次主控亲自改写或升级问人，禁止无界循环。
- 算力配比（写进 workflow 的指引，不代码强制）：Stage 1/2/3 是重载环节（规划、初创作、再创作）；
  Stage 4 主控是文书工作，轻输出；两个子 Agent 各拿"一次全功率"，不安排多轮对话磨稿。

## 7. 数据层与工作区布局

### 7.1 工作区（去编号，前缀问题裁决后）
```
workspace/<slug>/
  project.json          # 书配置：题名/题材/模式/字数带/风格旋钮默认/style_guards
  bible/                # 圣经+世界+势力+地理（自由文本；含"本书偏离清单"）
  characters/           # 人物卡 md（自由文本；别名等机器字段在 entities.json，不在卡上解析）
  outlines/main_plot.md, vol_XX/outline.md, vol_XX/beats/ch_XXX.md
  manuscript/vol_XX/raw/ch_XXX_vN.md | final/ch_XXX.md
  state/
    current.json         # 时空锚点+在场+能力/伤势/资产摘要
    entities.json        # 统一注册表：人物/道具/地点/组织 {name,type,aliases,card,summary,status}
    lines.json           # 双线台账：foreshadows[]（原 guns）+ misunderstandings[]
    timeline.json        # events[]（编年）+ arcs{}（心智/能力阶梯里程碑）
    ledger.json          # 复式账本：pools+transactions（余额永由流水重算）
    synopsis.json        # 章节梗概脊柱 + 全书 logline
    inbox/ {processed/, failed/, README.md 样例}
    snapshots/
  log/                   # director_log.md, review/, audit/
```
- v0.1 的 8 个状态文件合并为 **6 个**（characters 并进 entities；guns+mis 并为 lines；timeline+arcs 并为 timeline 文件）。文件越少，跨文件一致性检查越少，提案越简单。
- 取消自动 MD 视图（LLM 直读 JSON 更省；人要视图跑 `export --views` 顺手渲染即可，不作常态义务）。

### 7.2 提案协议（继承旧工程精华，schema v2）
`state-mutation/v2`：`chapter/operation_id/` + 上述 6 文件的分区 delta（`current/entities/lines/timeline/ledger/synopsis`）；继承：原子写+文件锁、canonical-hash 幂等、candidate_* 禁并、delta 整数符号即收支、balance_after 引擎重算、失败入 failed/ 自动捡回、processed/ 审计不可删。**新增**：引擎级 schema 校验（`engine/schemas/proposal.schema.json` + 自带 ≈150 行 mini-validator）——手写逐字段校验代码退役。跨字段业务规则（id 冲突、未知对象）在 state.py 分区校验里做，带准确中文报错。

## 8. 引擎与工具面（终版：9 命令）

### 8.1 命令表
```
status                      # 进度+逐章流水线行(§11.6)+下一步+阅读指向（吸收 hello）
init -t -g -p [--clean|--force]   # 脚手架+槽位实例化（继承旧 init 全部守卫）
pack ch_XXX [opts]          # §6
evidence <kind>             # mentions|gaps|dup|style|words（§5.7 与计数查询；纯 JSON）
check [--json]              # 结构+schema+算术体检（吸收旧 doctor/verify/audit/radar；errors 只允许事实级）
sync ch_XXX [--dry-run]     # 合并提案→check(state 段)→snapshot <ch>_done（继承四步流水线）
snapshot [create NAME|list|rollback NAME [--clean-drafts]]
export [--txt|--views]      # 全书编译（--views 按需渲染 md 视图）
help --json                 # argparse 反推命令目录（继承）
```
- 已删：`hello`（并入 status）、`mode`（project.json 一个字段，主控直接编辑，workflow 注明）、`apply`（=sync --dry-run）、`views`（=export --views）、`genre`/`schedule`/`memory`/`radar`（v0.1 已裁）。
- 引擎文件：`cli.py common.py state.py pack.py evidence.py checks.py snapshot.py schemas/`——7 个模块预计合计 <2000 行（旧工程 6773 行）。

### 8.2 LLM 适配与效率（可验收的硬指标）
- **单章闭环工具调用 ≤4 次**：pack →（起草 0 次）→（审校 ≤1 次 evidence）→ sync --dry-run → sync。旧流程同环节 ≈10+ 次。
- **上下文预算**：开局必读 ≤1.5k tok（AGENTS）；角色上岗增量 ≤1.7k（skill+workflow 对应节）；单章 pack ≤8k（自报）；起草子代理总输入 ≤12k。
- **记忆三温度**（ainovel-cli/MemGPT 思路的工程化）：热=P0 恒注入；温=P1 触发；冷=P2 指针 + evidence 现查。规则：任何"必须知道的事"不允许依赖温度 2 以下。
- **契约稳定**：全部 --json 输出字段名被 tests 快照冻结；schema 带 `version`；退出码 0=ok/1=阻断/2=用法。
- **失败语义**：check errors → 暂停等人（automatic 模式的少数安全点之一）；sync 失败提案留 failed/；evidence 空结果 = 合法事实（退出码 0）。

## 9. 工程底线（继承 v0.1，缩减到必要项）
- tests/：状态机不变量（幂等/回滚/锁并发/账本对 fixtures 手算值/损坏拒绝）+ CLI JSON 契约快照 + 章节号边界测试 + 文档层交叉检查。GitHub Actions: pytest + ruff。
- 引擎模块单向依赖：cli → {state,pack,evidence,checks,snapshot} → common；禁止反向 import。

## 10. 里程碑（v0.2 调整）

| M | 内容 | 验收 |
|---|---|---|
| M0 骨架 | 仓库/包结构/common/CLI 壳/help --json | pytest 绿；`studio help --json` |
| M1 状态机 | schemas+state（合并/幂等/账本重算）+snapshot+init/sync | 不变量测试全绿；空书 init→提案→sync→rollback 闭环 |
| M2 证据与体检 | evidence 五 kind + check | 对 fixtures 工作区输出冻结契约；check 零语义词 |
| M3 文档层 | AGENTS/workflow/craft/5 skills/genre_guides 全套**新写**（不复用旧文，只对照） | 行数预算达标；知识源交叉检查脚本（同一条规则不双写）通过 |
| M4 装配层 | pack 三层 + templates 槽位化 + export | init→填槽→pack 演示；触发命中率测试（beats 提及实体 100% 到包） |
| M5 试点 | 真 LLM 跑 1 卷 3 章 + **盲测**：3 章与旧工程产物混排给不知情读者挑"哪章像 AI" | 单章 ≤4 次调用达标；盲测不劣于旧工程 |

## 11. 已拍板决策（v1.0 定稿，由工程侧裁决）
1. 反公式化保持 craft.md 内独立成节，**不**单开文件。
2. 伏笔与误会并档 `lines.json`（同为"埋→发酵→爆"三段线，省一套合并与互查逻辑）。
3. 审校注记单文件 `log/review/ch_XXX.md`，final 保持纯净正文（export 直接可用）。
4. 题材参考并成单文件 `genre_guide.md`（每题材 ≤15 行）——8 个题材各开一个文件本身就是过度设计。
5. 审校为"重铸"而非"校对"：完整改写权 + must_keep 护栏（§6.5）；同章拒收 ≤2 次。
6. `status` 输出逐章流水线行（beats/raw/final/proposal/merged/snapshot 分格 ✓/✗）：会话随时可断，
   重开即从流水线行恢复现场——automatic 长跑的自愈生命线。

---

## 附录 A：PY 死板白名单（v0.2，收敛版）
1. 目录/树创建、模板实例化（纯替换）、复制/移动/删除、原子写、文件锁。
2. JSON schema 校验（type/enum/required/pattern/items 子集）、提案幂等合并、账本流水重算、自动编号。
3. 快照/manifest 哈希校验/回滚/按需视图渲染。
4. 字符串检索与统计：出现位置/次数/字数/占比/n-gram 重合数/句长分布/槽位计数/别名最长匹配。
5. 章节卷号解析与自然排序；token 粗估；文件清单生成。
6. 编译拼接导出；CLI 参数解析；JSON 序列化；退出码。
7. 提案骨架生成（只预填结构，不判断内容）；统计聚合与任意单文件统计（与定稿扫描同一把尺）。
**白名单外的一律不得进入引擎；被否决先例见 §2 表格反面与 v0.1 §7（保持）。**

## 附录 B：v0.1 → v0.2 变化摘要
- RESOURCE_MAP.md 取消独立成文（并入 AGENTS.md 地图节）；orchestrator skill 取消；4 专题 rules → 1 craft；
- pack 从"manifest 为主"升级为"P0/P1/P2 三层触发装配"（lorebook 机制）；
- 新增 §5 拟人风格引擎（form dice/style_notes/钩子正弦/语癖回流/反思节拍/风格指纹）；
- 命令 11 → 9；状态文件 8 → 6；引擎预算 <2000 行；
- 写权限按用户裁决改为"审校直写 final + 主控文字级终检"；
- 新增知识治理元原则（§1.3）与效率硬指标（§8.2）；里程碑加入盲测验收。
