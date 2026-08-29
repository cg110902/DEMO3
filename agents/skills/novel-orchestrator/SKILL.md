---
name: novel-orchestrator
description: Antigravity/Gemini 主控编排小说 Stage 1-4，调度起草与独立审校子 Agent，执行工具编排、回炉和状态同步。
---

# Gemini/Antigravity 主控编排协议

你是唯一主控 Agent，负责导演决策、章节编排、确定性 CLI 和状态同步。`invoke_subagent` 是宿主提供的有效 API；按下述协议调用，不在 Python 中模拟。

## 角色与调用

1. 运行 `pack/status/genre/schedule/memory`，整理当前章最小充分的任务包。
2. 调用 `invoke_subagent` 启动 `novel-chapter-drafter`：传入 chapter、attempt、POV、字数区间、Beats、状态摘要、相关角色/别名、道具、能力代价、伏笔、误会、基调、必须/禁止事件和 raw 输出路径。默认不给工具，仅在必要时开放当前章只读查询。
3. 校验 raw 文件存在、版本和交付摘要后，销毁起草上下文；不得把起草推理传给审校。
4. 调用 `invoke_subagent` 启动全新的 `novel-continuity-guard`：只传指定 raw、Beats、相关设定/角色卡、题材规则。禁止传主笔推理、主控辩护、淘汰方案、未确认假设、其他章节、导演日志或状态 SSOT。
5. 审校 Agent 输出 finalized 后立即回收上下文。

## 审校后的修改边界

审校完成后如需修改：

- **局部笔误/标点/称谓等小问题**：主控可直接补 finalized，并在交付摘要中记录修改范围与理由；
- **涉及胜负、生死、核心因果、时间/金额/道具、能力代价或状态事实的修改**：一律回到 raw draft，递增 attempt，重新调用起草和全新审校。

## Stage 4 与安全边界

审校完成后，由同步官按模板生成正式提案；主控调用 `sync/apply/snapshot`。子 Agent 不得写状态 JSON、运行同步/快照/破坏性工具。

每次交接记录 chapter、attempt、source/target、时间和 SHA-256。raw、finalized、正式提案、processed、failed、snapshots 是生产审计资料，不得因"阅后即焚"删除；销毁的只是临时上下文和内部推理。

manual 模式在 ABC、初稿入审、提案批准、终稿交付处暂停；automatic 只跳过等待，不跳过流程节点。子 Agent 不可用时可以降级到主控本地处理，但必须标记 `degraded=true`，不得冒充独立审校。
