# engine/ — 确定性引擎（纯 stdlib，零运行时依赖）

入口 `python studio.py <cmd>`（根壳转发 `engine.cli.main`）。能力封顶 = docs/PLAN.md 附录 A：
新增能力先改附录再写码（AGENTS 硬禁令 5）。引擎只数数与校验，一切判断留给 LLM——
见到"裁决式代码"就是越界。

| 模块 | 职责 | 契约测试 |
|---|---|---|
| cli.py | 9 命令 argparse 目录、闸门与文案 | tests/test_cli.py |
| common.py | 工作区定位、JSON 读写（坏文件入 failed/）、幂等登记簿 | tests/test_common.py |
| state.py | 五表结构、提案合并（upsert/append/resolve…）、inbox README 播种 | tests/test_state.py |
| validator.py + schemas/ | 提案/schema 机械校验（结构级，不判事实真伪） | tests/test_validator.py |
| checks.py | check：结构/schema/算术/逾期/form 占比 | tests/test_checks.py |
| evidence.py | words/style/form/dup/mentions/gaps——只输出数 | tests/test_evidence.py |
| pack.py | P0 任务书整块 / P1 触发 / P2 索引，超预算按优先级硬裁 | tests/test_pack.py |
| snapshot.py | 快照 create/list/rollback（pre_rollback 保护；不碰 manuscript） | tests/test_snapshot.py |

输出契约：数据类命令 stdout 单个 JSON；status/check 为人读表（断言在 test_cli 冻结）。
退出码：0=成功；1=业务拒绝（校验失败/闸门）；2=用法错误。
