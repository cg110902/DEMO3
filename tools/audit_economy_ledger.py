# -*- coding: utf-8 -*-
"""
Economy Double-Entry Ledger Auditor (audit_economy_ledger.py)

只做确定性数学工作：读取 04_timeline_and_state/economy_ledger.json（复式账本 SSOT），
按 initial + Σ(delta) 逐池重算余额，逐笔核对 balance_after 与期末声明余额。
不扫描正文、不做任何内容识别——账本流水由 LLM 同步官经提案写入。

Usage:
    python tools/audit_economy_ledger.py
    python tools/audit_economy_ledger.py --json
"""

import sys
import json
import argparse
from pathlib import Path

_tools_dir = Path(__file__).resolve().parent
if str(_tools_dir) not in sys.path:
    sys.path.insert(0, str(_tools_dir))

from novel_utils import resolve_workspace, reconfigure_utf8

reconfigure_utf8()


def audit_economy_ledger(workspace_path=None, as_json=False):
    workspace_dir = resolve_workspace(workspace_path)
    ledger_json_path = workspace_dir / "04_timeline_and_state" / "economy_ledger.json"

    if not ledger_json_path.exists():
        report = {
            "workspace": workspace_dir.name,
            "mode": "JSON_LEDGER",
            "status": "SKIP",
            "note": "未找到 economy_ledger.json，跳过经济精算（题材可无经济体系）。",
        }
        if as_json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print(f"ℹ️ {report['note']}")
        return report

    try:
        ledger_data = json.loads(ledger_json_path.read_text(encoding="utf-8-sig"))
    except Exception as e:
        report = {"workspace": workspace_dir.name, "mode": "JSON_LEDGER",
                  "error": f"解析 economy_ledger.json 失败: {e}"}
        if as_json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print(f"❌ {report['error']}")
        return report

    transactions = ledger_data.get("transactions", [])
    resource_pools = ledger_data.get("resource_pools")
    if not resource_pools:
        # 单币种旧格式：合成为单一资源池视图
        currency_unit = ledger_data.get("currency_unit", "货币/点数")
        init_bal = ledger_data.get("initial_balance", 0)
        cur_bal = ledger_data.get("current_balance", init_bal)
        resource_pools = {
            "primary_currency": {
                "name": currency_unit,
                "unit": "单位",
                "initial": init_bal,
                "current": cur_bal,
            }
        }

    computed_pools = {}
    for pool_key, pool_info in resource_pools.items():
        computed_pools[pool_key] = {
            "name": pool_info.get("name", pool_key),
            "unit": pool_info.get("unit", ""),
            "initial": pool_info.get("initial", 0),
            "current_declared": pool_info.get("current", pool_info.get("initial", 0)),
            "running_balance": pool_info.get("initial", 0),
            "total_inflow": 0,
            "total_outflow": 0,
            "tx_count": 0,
        }

    arithmetic_errors = []

    def _to_num(v):
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return v
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    # 按流水顺序重算每池余额
    for idx, t in enumerate(transactions, 1):
        r_key = t.get("resource", "primary_currency")
        if r_key not in computed_pools:
            arithmetic_errors.append(
                f"第 {t.get('chapter', f'#{idx}')} 章流水引用了未声明的资源池 '{r_key}'")
            continue
        p = computed_pools[r_key]
        p["tx_count"] += 1

        if "delta" in t:
            delta = _to_num(t["delta"])
            if delta is None:
                arithmetic_errors.append(
                    f"第 {t.get('chapter', f'#{idx}')} 章【{p['name']}】流水 delta 非法: {t['delta']!r}")
                delta = 0
            if delta > 0:
                p["total_inflow"] += delta
            else:
                p["total_outflow"] += abs(delta)
        else:
            inflow = t.get("inflow", 0)
            outflow = t.get("outflow", 0)
            delta = inflow - outflow
            p["total_inflow"] += inflow
            p["total_outflow"] += outflow

        p["running_balance"] += delta

        # 逐笔核对结余
        rec_balance = _to_num(t.get("balance_after"))
        if rec_balance is not None and rec_balance != p["running_balance"]:
            arithmetic_errors.append(
                f"第 {t.get('chapter', f'#{idx}')} 章【{p['name']}】流水算术错位：记录值为 {rec_balance}，"
                f"实际精确值为 {p['running_balance']} (差额: {rec_balance - p['running_balance']})")

    # 期末余额核对
    for pool_key, p in computed_pools.items():
        if p["current_declared"] != p["running_balance"]:
            arithmetic_errors.append(
                f"资源【{p['name']}】期末余额不平衡：声明余额为 {p['current_declared']}{p['unit']}，"
                f"复式流水计算累计为 {p['running_balance']}{p['unit']}")

    is_valid = len(arithmetic_errors) == 0

    ledger_report = {
        "workspace": workspace_dir.name,
        "mode": "JSON_LEDGER",
        "resource_pools_count": len(computed_pools),
        "total_transactions": len(transactions),
        "is_balanced": is_valid,
        "anomalies": arithmetic_errors,
        "pools": computed_pools,
        "transactions": transactions,
    }

    if as_json:
        print(json.dumps(ledger_report, ensure_ascii=False, indent=2))
        return ledger_report

    print("═" * 74)
    print(f" 🧮 [全书资产、属性点与量化资源精算] 工作区: {workspace_dir.name}")
    print(f" 📦 追踪资源池: {len(computed_pools)} 个 | 登记流水: {len(transactions)} 笔")
    print("═" * 74)

    for pool_key, p in computed_pools.items():
        print(f" 🔹 【{p['name']}】 期初: {p['initial']} {p['unit']} | 当前: {p['current_declared']} {p['unit']} "
              f"(流水: {p['tx_count']} 笔, 累计变动: +{p['total_inflow']} / -{p['total_outflow']})")

    if transactions:
        print("\n   " + f"{'章节':<8} | {'资源类别':<12} | {'变动/类型':<14} | {'结余':<8} | {'变动明细与事由'}")
        print("   " + "-" * 72)
        for t in transactions:
            r_name = computed_pools.get(t.get("resource", "primary_currency"), {}).get("name", "货币")[:10]
            delta_s = f"{t.get('delta', t.get('inflow', 0) - t.get('outflow', 0)):+}"
            subj = t.get('subject', '')[:22]
            print(f"   {t.get('chapter', '未知'):<8} | {r_name:<12} | {t.get('type', '流水')}({delta_s}){'':<4} | "
                  f"{t.get('balance_after', '-'):<8} | {subj}")

    print("\n" + "─" * 74)
    if arithmetic_errors:
        print("🚨 【发现量化资源算术异常】:")
        for err in arithmetic_errors:
            print(f"   ❌ {err}")
    else:
        print("✨ [量化资源完全自洽] 货币、加点、属性值与特殊资源流水 100% 平衡自洽！")
    print("═" * 74 + "\n")
    return ledger_report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="复式账本精算器（纯 JSON 数学校验）")
    parser.add_argument("--workspace", "-w", type=str, default=None, help="目标小说工作区路径")
    parser.add_argument("--json", action="store_true", help="以结构化 JSON 格式输出")
    args = parser.parse_args()

    report = audit_economy_ledger(workspace_path=args.workspace, as_json=args.json)
    sys.exit(1 if isinstance(report, dict) and report.get("error") else 0)
