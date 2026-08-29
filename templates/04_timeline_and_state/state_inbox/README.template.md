# 状态变更提案投递箱 (State Inbox)

章节定稿后的标准流水线：
1. **LLM 撰写正式提案**：同步官通读定稿 `ch_xxx`，参照 `ch_sample.proposal.template.json`
   撰写正式提案 `ch_xxx.json`；
2. **确定性合并**：运行 `python studio.py sync ch_xxx`（自动包含 apply 合并）将变更合并进
   6 大状态文件并重算余额。

> ⚠️ 注意：带 `_draft:true` 或 `candidate_*`/`*_clues` 候选字段的提案绝不会被合并，
> 只有正式 JSON 提案才会生效。
> 💡 格式参考：可查阅同目录下 `ch_sample.proposal.template.json` 获取完整结构范例。

## 提案 JSON 格式说明 (schema: novel-studio.state-mutation/v1)
- `operation_id`（正式提案必填）：稳定的章节级幂等键，格式如 `ch_012.state-sync.v1`，必须与顶层 `chapter` 对应；同一标识重复提交不得重复记账。
- `current_state`：时空锚点、在场角色、境界、伤势、资产、局势（按字段差异更新）
- `guns`：伏笔 `plant` / `update` / `resolve` / `remind`（`remind` 一键回唤为 Reminded 状态；id 可省略，引擎自动按序编号；⚠️ `update`/`resolve`/`remind` 只能作用于台账中已存在的伏笔 id——第 1 章等首章提案通常只有 `plant`）
- `misunderstandings`：误会 `plant` / `update` / `resolve`（自动编号，同样只能 `update`/`resolve` 已存在的记录）
- `growth_arcs`：角色成长轨道更新；`stage` 为**自由文本**（可为 `Stage 2【信息做庄】`，也可为 `信任·戒备第3阶`／`认知线·4` 等本书自定义轨道）；`strategy` 为覆盖式更新，历史自动归档
- `timeline`：编年史事件追加（幂等去重）
- `transactions`：复式账本流水（`delta` 正=收入负=支出，余额由流水自动重算）
- `synopsis`：（可选）本章 2~3 句精炼梗概 + `chapter_title`，登记进章节梗概脊柱（`chapter_synopsis.json`）

合并成功的提案自动归档移入 `processed/`，校验失败的移入 `failed/` 并输出错误原因。

## 回滚后如何重新合并某章提案

`rollback` 会把状态机（含幂等标记 `.applied_operations.json`）一并复原到快照时点。因此回滚后若要重新合并某章已归档的提案：把它从 `processed/ch_xxx.json` 复制回收件箱，再重跑 `sync ch_xxx` 即可——幂等标记已随快照回滚，同一 `operation_id` 不会被判为重复而跳过。
