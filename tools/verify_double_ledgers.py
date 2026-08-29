# -*- coding: utf-8 -*-
"""
Double Ledgers & State Machine Cross-Consistency Verifier
Cross-audits the JSON state SSOT:
- Expired Chekhov guns whose target resolution chapter has passed without firing
- Misunderstandings / timeline coverage hints
- Economy ledger arithmetic balance

Usage:
    python tools/verify_double_ledgers.py
    python tools/verify_double_ledgers.py --json
"""

import sys
import re
import json
import argparse
from pathlib import Path

_tools_dir = Path(__file__).resolve().parent
if str(_tools_dir) not in sys.path:
    sys.path.insert(0, str(_tools_dir))

from novel_utils import resolve_workspace, find_manuscript_files, reconfigure_utf8, latest_chapter_number

reconfigure_utf8()


def _load_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8-sig"))
    except Exception:
        return None


def verify_ledgers(workspace_path=None, as_json=False):
    workspace_dir = resolve_workspace(workspace_path)
    state_dir = workspace_dir / "04_timeline_and_state"

    if not state_dir.exists():
        if as_json:
            err = {"error": f"未找到 04_timeline_and_state 目录: {state_dir}"}
            print(json.dumps(err, ensure_ascii=False, indent=2))
            return err
        print(f"[错误] 未找到 04_timeline_and_state 目录: {state_dir}")
        return False

    manuscript_dir = workspace_dir / "05_manuscript"
    finalized_files = find_manuscript_files(manuscript_dir)
    latest_chapter_num = latest_chapter_number(manuscript_dir, require_finalized=True)

    audit_results = {
        "workspace": workspace_dir.name,
        "latest_finalized_chapter": latest_chapter_num,
        "guns_health": "PASS",
        "misunderstandings_health": "PASS",
        "timeline_health": "PASS",
        "anomalies": [],
        "warnings": []
    }

    # 1. Chekhov guns (JSON)
    guns_data = _load_json(state_dir / "chekhov_guns.json")
    if guns_data:
        for g in guns_data.get("guns", []):
            status = str(g.get("status", ""))
            is_resolved = any(k in status.lower()
                              for k in ["resolved", "triggered", "已回收", "已触发"])
            target_ch = str(g.get("target_ch", ""))
            target_nums = re.findall(r"\d+", target_ch)
            if target_nums and not is_resolved:
                target_num = int(target_nums[-1])
                if latest_chapter_num > target_num + 3:
                    audit_results["warnings"].append(
                        f"⚠️ [伏笔超期未爆] 伏笔【{g.get('id')}: {g.get('name')}】"
                        f"预定第 {target_num} 章引爆，当前已至第 {latest_chapter_num} 章仍处于 {status} 状态！")

    # 2. Misunderstandings (JSON)
    mis_data = _load_json(state_dir / "misunderstandings.json")
    if mis_data is not None:
        active_mis = sum(
            1 for m in mis_data.get("misunderstandings", [])
            if not any(k in str(m.get("status", "")).lower()
                       for k in ["resolved", "已澄清"]))
        if active_mis == 0 and latest_chapter_num >= 5:
            audit_results["warnings"].append(
                "💡 [戏剧张力偏弱] 当前误会与信息差台账为空，建议补充 1~2 处核心人物认知错位，"
                "提升喜剧与反差爽感！")

    # 3. Timeline (JSON)
    tl_data = _load_json(state_dir / "timeline.json")
    if tl_data is not None:
        n_events = len(tl_data.get("events", []))
        if n_events < max(1, latest_chapter_num // 2) and latest_chapter_num >= 5:
            audit_results["warnings"].append(
                f"💡 [编年史提示] 当前定稿已达第 {latest_chapter_num} 章，timeline.json 记录了 "
                f"{n_events} 条重大事件，请按需保持重大节点同步！")

    # 4. Growth arcs existence
    if not (state_dir / "character_growth_arcs.json").exists() and latest_chapter_num >= 3:
        audit_results["warnings"].append(
            "💡 [心智演进台账缺失] 建议创建 character_growth_arcs.json，追踪核心角色的阶段心智与成长弧线！")

    # 5. Economy ledger
    econ_file = state_dir / "economy_ledger.json"
    if econ_file.exists():
        econ_data = _load_json(econ_file)
        if econ_data is not None:
            pools = econ_data.get("resource_pools")
            transactions = econ_data.get("transactions", [])
            if pools:
                pool_balances = {k: v.get("initial", 0) for k, v in pools.items()}
                for t in transactions:
                    r_key = t.get("resource")
                    if r_key is None:
                        r_key = next(iter(pools))
                    # 与 validate_state 口径一致：null delta 视为 0（inflow-outflow），
                    # 浮点金额按整数复核，避免与 state_apply 的记账结果出现尾差分歧。
                    delta = t.get("delta")
                    if delta is None:
                        delta = t.get("inflow", 0) - t.get("outflow", 0)
                    if isinstance(delta, float):
                        delta = int(delta)
                    if r_key not in pool_balances:
                        audit_results["anomalies"].append(
                            f"❌ [资源池未声明] 第 {t.get('chapter', '?')} 章流水引用了 resource_pools 中"
                            f"不存在的资源池 '{r_key}'（请在台账中登记该资源池或修正 resource 字段）")
                        continue
                    pool_balances[r_key] += delta
                for k, v in pools.items():
                    declared = v.get("current", v.get("initial", 0))
                    if declared != pool_balances.get(k, 0):
                        audit_results["anomalies"].append(
                            f"❌ [量化资源算术不平衡] 资源【{v.get('name', k)}】声明余额 {declared}，"
                            f"实际流水累计 {pool_balances.get(k, 0)}")
            else:
                init_bal = econ_data.get("initial_balance", 0)
                cur_bal = econ_data.get("current_balance", init_bal)
                calc_bal = init_bal
                for t in transactions:
                    calc_bal += t.get("delta", t.get("inflow", 0) - t.get("outflow", 0))
                if cur_bal != calc_bal:
                    audit_results["anomalies"].append(
                        f"❌ [经济台账算术不平衡] economy_ledger.json 声明结余 {cur_bal}，"
                        f"复式流水计算值为 {calc_bal} (差额: {cur_bal - calc_bal})")
        else:
            audit_results["warnings"].append("💡 [经济台账读取异常] economy_ledger.json 解析失败")

    has_fatal = len(audit_results["anomalies"]) > 0

    if as_json:
        print(json.dumps(audit_results, ensure_ascii=False, indent=2))
        return audit_results

    print("═" * 74)
    print(f" 🔍 [双台账与状态机交叉一致性校验报告] 工作区: {workspace_dir.name}")
    print(f" 📖 当前定稿进度: 第 {latest_chapter_num} 章")
    print("═" * 74)

    if audit_results["warnings"] or audit_results["anomalies"]:
        print("🚨 【交叉一致性预警清单】:")
        for w in audit_results["warnings"]:
            print(f"   {w}")
        for a in audit_results["anomalies"]:
            print(f"   {a}")
    else:
        print("✨ [状态机双台账完美自洽] 伏笔爆发周期合理，信息差发酵充分，未发现吃设定或超期遗忘！")

    print("═" * 74 + "\n")
    return not has_fatal


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="双台账与状态机交叉一致性校验器")
    parser.add_argument("--workspace", "-w", type=str, default=None, help="目标小说工作区路径")
    parser.add_argument("--json", action="store_true", help="以结构化 JSON 格式输出")
    args = parser.parse_args()

    ok = verify_ledgers(workspace_path=args.workspace, as_json=args.json)
    if isinstance(ok, dict):
        sys.exit(1 if (ok.get("anomalies") or ok.get("error")) else 0)
    sys.exit(0 if ok else 1)
