# ROADMAP v2.0（升级计划草案）— 只从本项目自己的事故里长出来

> 定位：v1.1（初版，卷一 6 章生产 + 两轮自查修复）之上的升级提案。**批次顺序与落地时机已由
> 用户拍板采纳（2026-08-29）**；各项动码前仍须：改动先写入 PLAN 相应节（含附录 A 白名单增补），再实施。
> 立项纪律：只收三类来源——①卷一生产实录烧出来的痛；②自查/冒烟抓出的文档-代码漂移；
> ③协议"说了没做"或"做了没说"的真缺口。**外来项目的好点子不是来源**，除非本项目已因此吃过亏。
> **v1.2 已先行落地的语义修正**（当日随拍板完成，不在批次内）：Stage 3 从"审校重铸"改为
> **打磨与校对**两幕——审校 = 商业网文级全文润色（动态要求随任务书新节「打磨重点」逐章下达）
> + 六项机械清单校对；情节事实零改动（坏在情节层 = 拒收回 Stage 2，不由文笔遮）。
> P1 的结构化在此新语义之上做。
> 已了结不再列：章长方差（v1.1 已量化）、status 枚举（README 已警示）、guard 选词（craft 已裁）、
> sync 报错文案（v1.1 已补）、`snapshot list` 与 front-matter 超键（本文撰写当日当场修复，见 M6.1）。

## 批次 M6.1 契约真实性（D1/D2 ✅，D3 待做）—— 让文档每句话都有代码兑付

**来源**：两轮自查抓出两例"docs 说话、code 不办"——`snapshot list` 在 help 口径里存在但
argparse 未注册（按文档敲命令=报错）；AGENTS 禁令 6 承诺"front-matter 超键 check 拦截"但
check 不查（实测 `supernumber: 42` 畅通）。都是测试没覆盖"文档教的那一下"。

- **D1 docs-as-tests（✅ 当日落地）**：`tests/test_docs_contract.py`——扫规范文档全部
  `python studio.py …` 命令示例逐条过 argparse（占位符行跳过），并冻结"命令目录三镜像"
  （parser choices / help --json / COMMAND_HELP 互等）。上线当日即抓修一例误判。：`tests/test_docs_contract.py`——扫 AGENTS.md /
  workflow / engine/README 中所有 `studio.py` 命令示例，逐条喂给 argparse 验证"可解析"
  （`parse_args` 冒烟，不执行、不落盘）。文档杜撰命令 = 测试红。预算 ~60 行测试代码。
- **D2 超键拦截（已完成）**：`checks._BEATS_FM_KEYS` 七键白名单 + error 规则
  `beats_fm_extra_keys`，卷一回归零误伤。craft#front-matter 键的说法自此为真。
- **D3 一次性存量清点**：全库 grep"check 会查 / 引擎会拦 / sync 拒绝"类承诺，逐条对着
  test 找兑付点；无兑付的要么补实现要么改文案。做完 D1，此类漂移以后自动拦截。

## 批次 M6.2 协议闭环 —— 把"靠自觉"的环节换成"靠数数"

**来源**：卷一里审校注记是否"真审了"全靠主控读；章级禁忌（"数"、比喻字）引擎不数导致
写稿后必须人肉 python 硬查；提案字段错被闸门拒了三次才全对。

- **P1 审校注记结构化**：`log/review/ch_XXX.md` 头部加 front-matter
  `acceptance: [{item, pass, evidence}]`（条目须与任务书「验收」一一对应）。sync 新增机械核对：
  未答条目数、勾了但 evidence 行为空 → 拒绝封存。引擎仍不判文笔好坏——**只数"每问是否必答"**。
  动 checks + workflow Stage 3/4 输出合同 + templates/review.md。
- **P2 章级 guard 进 front-matter**：合法键扩一个 `guard_extra: [词1, 词2]`（本章专用、
  随 beats 进 pack P0），`evidence style` 并入逐章计数。单字/条件禁忌从此有结构化的家，
  不污染全局 style_guards（卷一"数"字两难的终解）。**键扩容流程一并立规**：加一个
  front-matter 键 = checks 常量 + craft#front-matter 键 + 回归测试三处同步，缺一即漂移。
- **P3 提案骨架生成（✅ 已落地 `proposal new <ch>`）**：在途占位拒造、骨架原样过 dry-run
  校验入测试；PLAN 附录 A 增第 7 条；workflow Stage 4 动作 1 改用之。：`studio.py proposal new ch_007` 向 stdout 打印预填 schema/chapter/
  operation_id（日期+章号自动序号）的最小合法骨架，主控填空后存 inbox。三次拒收教训
  （status 枚举、缺 chapter、字段名错）里前两类可被骨架根除；validator 逐字段报错已存在
  （实测确认），此项只补"生成"这半程。不引入写权限新通道（骨架只打印，不写盘）。

## 批次 M6.3 产能与成本 —— 压缩 LLM 往返，不新增裁决

**来源**：三章初稿实测都只有目标一半、盲改扩容时 replace MISS（2/10）；单章"恒 4 调用"
是设计口径，实操常 split 补跑 words/style/form/dup 各一遍。

- **E1 `evidence all`（✅ 已落地）**：一次输出 words+style+form+dup+gaps 全套 JSON。纯聚合
  零新算，单章引擎往返 4→1（切片场景用原有单 kind）。
- **E2 `evidence file <相对路径>`（✅ 已落地——接口从 --file 改为 kind 统一）**：单篇实测
  复用定稿同一 `_stats_one`（cjk/句式/tic/段首全套）；路径逃逸拒 rc1。起草当场看实数，
  "写到一半猜字数"消灭；审校打磨时的对照尺。
- **E3 分景起草协议（纯文档）**：任务书「目标」按场景分块并各配字数带建议；起草代理逐景写、
  合成一个 raw vN（版本制不变）。craft 加两行、workflow Stage 2 加一句。治截断与整章返工，
  引擎零改动。
- **E4（变体，已裁决）**：pack 保持纯上下文不动——"本章还欠什么"（gaps 快到期、failed/
  件数、待合并提案）并入 **status 的"下一步"区**（status 本就是主控仪表盘，该逻辑位已存在）。
  裁决理由：信息归位优先于省一次调用——发给子代理的包不该混入主控的账。

## 批次 M6.4 质量视角 —— 项目"可以复杂"的第一实体

**来源**：盲测 n=1 自评是 README 里自己留的"待加固"；信息差验证目前只有作者视角。

- **R1 读者代理**：`agents/skills/reader/SKILL.md`——卷末 spawn 一次性"纯读者"，
  **只喂 export 卷文本，不给 state/pack**，产出困惑清单（这人谁/这东西哪来的/哪段像硬安排）。
  主控卷末反思吸收之，可复用教训按现行流程升 craft。同一引擎多跑一个角色，即
  "简单可以复杂"的示范：复杂度长在协议上，不长在代码上。
- **R2 剧透盲测**：评分协议改版——给被测模型"前 3 章 + 各章任务书"，让它预测后 3 章拍点，
  与真 beats 对比：猜中 8 条中的 6 条 = 公式化实锤。替代六维自评，可每卷末执行一次，
  结果进 director_log。零引擎改动。
- **R3 target_ch 语义成文**：lines 的 target_ch 事实全局章号（卷一 ch_012 即证），跨卷续写
  有歧义风险。裁决并写进 craft#伏笔：全局编号为准，卷内章号仅作显示糖。不改引擎。

## M6.5 明确不做（升级后的否决清单，防未来的我）

自动 git 提交（引擎不碰业务仓库）· epub/pdf 渲染 · 虚构历法日期校验 · embedding/检索 ·
提案 Markdown 双通道 · pack 智能截断 · cjk_spread 阈值 checker（"均匀=坏"的裁决留给卷末
反思，v1.1 决策重申）· 审校文笔评分 · 引擎管模型温度 · 多书并发。

## 实施顺序与量级

| 序 | 项 | 量级 | 依赖 |
|---|---|---|---|
| 1 | D1 docs-as-tests | ✅ 已落地 | — |
| 2 | P3 proposal new | ✅ 已落地 | — |
| 3 | E1+E2 evidence 聚合与单文件实测 | ✅ 已落地 | 附录 A 已补第 7 条 |
| 4 | P2 guard_extra（含键扩容流程） | 半天 | D1 已立（craft 同步改） |
| 5 | P1 审校结构化 | 1 天 | 动 sync 闸门，排在卷二 ch_007 收章之后落地（旧章注记不回改） |
| 6 | E3+E4 | 半天 | 纯文档+小改 |
| 7 | R1+R2+R3 | 1 天 | 文档与模板为主 |

统一闸门（每项验收线）：纯 stdlib；附录 A 白名单先行；引擎零判断词；test_docs 行数预算不破
（craft ≤280 / workflow ≤260 / 模板 ≤40）；全量 pytest + ruff 绿；卷一历史产物不回改
（审计留痕，新规则对新书与新章生效）；里程碑完成即推 demo4-backup。
