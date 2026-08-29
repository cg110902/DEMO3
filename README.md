# Novel Studio（DEMO4 重写工程）

> 五阶段流水线：Stage 0 初始化 → 1 细纲+任务书（主控）→ 2 起草（一次性子代理）→
> 3 审校重铸（一次性子代理）→ 4 同步（主控）。LLM 干一切灵活的活，Python 只做白名单死板事。
> 设计定稿见 `docs/PLAN.md`（v1.0）；创作规则入口是仓库根 `AGENTS.md`。

## 快速上手（宿主 Agent / 人类通用）

```bash
python studio.py init -w workspace/我的书 -t 书名 -g 题材 -p 主角名   # Stage 0
python studio.py status                                             # 开局必读：进度+下一步
python studio.py pack ch_001          # 装配子代理上下文（P0/P1/P2 三层，自报预算）
python studio.py evidence words       # 机械证据：字数/提及/线状态/查重/风格指纹（纯 JSON）
python studio.py check                # 事实级体检：errors 阻断，warnings 只报数
python studio.py sync ch_001          # 提案合并 → 状态体检 → 快照（Stage 4）
python studio.py snapshot rollback ch_001_done --clean-drafts      # 回滚
python studio.py export --txt         # 全书编译
```

## 文档地图

| 层 | 文件 | 一句话 |
|---|---|---|
| 文档层 | `AGENTS.md` | 宪法：禁令/不变量/开局地图（≤1.5k tok） |
| | `agents/rules/novel_workflow.md` | 流水线剧本（Stage 0–4 SOP） |
| | `agents/rules/novel_craft.md` | 文学默认值（可被「本书偏离清单」覆盖） |
| | `agents/skills/*/SKILL.md` | 5 张岗位合同（director/beats-builder/drafter/guard/syncer） |
| | `agents/genre_guide.md` | 8 题材选择题素材（非公式） |
| 引擎层 | `studio.py` + `engine/` | 9 命令薄壳；纯 stdlib；模块依赖 cli → 各领域 → common |
| 数据层 | `workspace/<书>/` | 圣经/大纲/稿件自由文本；`state/` 6 JSON = 机器真值（提案制写入） |

## 里程碑

（见 PLAN §10）

- [x] M0 骨架：studio.py 薄壳、engine/common（IO 安全底座）、CLI 壳、契约测试、CI
- [x] M1 状态机：schemas/ + state.py（提案合并/幂等/账本重算）+ snapshot.py + init/sync 完整化
- [x] M2 证据与体检：evidence 五 kind + check 体检（errors 事实级）
- [x] M3 文档层：AGENTS/workflow/craft/5 skills/genre_guide 全套新写；tests/test_docs.py 交叉检查
- [x] M4 装配层：pack 三层 + templates 槽位化 + export
- [x] M5 端到端试点 + 拟人度盲测（examples/渊火记 卷一 6 章全闭环收卷：单章 LLM 调用恒为 4、
  check 零 errors、账本重算/提案拒收/回流警告实证；examples/盲测 六维评分表 11.5:3。
  注：盲测为单模型自评，n=1，待人工抽检加固）
- [x] M5.1 卷一生产回流（PLAN v1.1 六项修复：regex 误报/段首豁免/跨章方差/提案命名提示/样例警示/craft 升格）

## 开发

```bash
python3 -m venv .venv && .venv/bin/pip install pytest ruff
.venv/bin/pytest          # 全量测试（含文档交叉检查）
.venv/bin/ruff check engine tests studio.py
```

> 沙箱重置事故记录：原 /home/user/DEMO4（M0–M3 四个提交）未推送被重置清空，
> 本仓库为按会话历史逐字重建 + M4。
