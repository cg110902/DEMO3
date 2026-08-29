# director_log — 渊火记

## 生产审计（M5 验收口径：每章 LLM 调用 ≤4）
| 章 | LLM 调用（岗位） | 引擎 CLI（确定性，不计入上限） |
|---|---|---|
| ch_001 | director(beats+任务书) / drafter(raw) / guard(final+注记) / syncer(提案) | gaps, pack, style, dup, sync×2（一次红→修→绿）, check |
| ch_002 | 同上 4 | pack, style, dup, sync, check |
| ch_003 | 同上 4 | style, dup, sync×2（status 枚举红→修→绿）, check |
| ch_004 | （beats 草稿已备，下一会话续） | pack 触发率演示 6/6 |

结论：单章 LLM 调用恒为 4；引擎调用全为无状态读或唯一写入口（sync）。

## 改稿教训（卷内回流）
- "灯油"两章各 1 次，自查定为 tic → 已入 style_guards（ch_004 起 pack 硬提醒携带；
  ch_001/002 各挂 style_guard_hit 警告留档——历史章不回改，留警告即账）。
- 人物卡"改口常翁"未在 ch_003 落地（审校注记⑤）：称谓进度条顺延 ch_006 堂前戏——
  beats-builder 的"新实体标记"要含"称谓变更"类承诺，否则 Stage 1 会漏账（下卷在任务书模板加一行自查）。
- entities.status 是枚举非自由文本，连踩两次（ch_001/ch_003）：属模板缺口——
  inbox/README 样例已含正确写法，但示例只演示了 item；下版样例补一条 place 的 upsert（工程待办，不改引擎）。

## 反思（十行内）
三章闭环证明流程可跑且引擎够薄：真正吃工的是 Stage 1 的任务书设计与 Stage 3 的重铸幅度，
两处都不可外包给校验。下一步 ch_004 起执行卷纲既定"主角会输"线；若 ch_006 前 GUN-001 出现
第二张牌未动，按 overdue 提醒在 ch_005 强制 remind 一次。
