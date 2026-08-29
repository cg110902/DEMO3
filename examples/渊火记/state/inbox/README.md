# state/inbox — 提案收件箱（同步官的工位）

一切状态修改从这里进：每章一个 `ch_XXX.json`（schema: engine/schemas/proposal.schema.json，
业务规则见 engine/state.py 分区校验）。processed/ = 已应用的审计记录（永不删改）；
failed/ = 失败提案，就地处修复后重跑 `sync`，引擎自动捡回。

正式提案必须带 operation_id；`*.draft.json`/`*.template.json`/`*.sample.json` 不参与合并，
可放这里当草稿。最小样例（各分区都给了最短合法形状）：

```json
{
  "schema": "novel-studio.state-mutation/v2",
  "chapter": "ch_007",
  "operation_id": "ch_007.syncer.0829a",
  "current": {"location": "青石镇·祠堂", "present_characters": ["沈拓", "村长"]},
  "entities": [{"action": "upsert", "name": "村长", "type": "person",
               "summary": "青石镇村长，玉佩旧案的知情人"}],
  "lines": [
    {"kind": "foreshadow", "action": "plant", "name": "祠堂牌位下的匣子", "target_ch": 12},
    {"kind": "foreshadow", "action": "resolve", "id": "GUN-003"}
  ],
  "timeline": {"events": [{"time": "次日清晨", "event": "开祠堂"}]},
  "ledger": {"transactions": [{"pool": "standard_currency", "delta": -30,
                  "subject": "香火钱", "counterparty": "祠堂"}]},
  "synopsis": {"title": "祠堂", "text": "沈拓借赔罪进祠堂，瞥见牌位下露出半角匣子。"}
}
```

写提案的纪律：只写增量；事实必须能在本章 final 正文找到出处；不确定就不上账。
