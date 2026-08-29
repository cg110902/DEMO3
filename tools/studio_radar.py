# -*- coding: utf-8 -*-
"""
Studio Master Radar - One-Click All-Dimension Novel Health Inspector (Third-Gen Agent-First)
Aggregates Doctor, Double Ledgers, State Machine, Economy, Character
Decay/Network, Cross-Chapter Repetition and Item Tracking into a unified,
ultra-high signal-to-noise executive scorecard (supports --json for agentic
consumption).
Usage:
    python tools/studio_radar.py
    python tools/studio_radar.py -c ch_004
    python tools/studio_radar.py -c ch_004 --json
"""

import sys
import argparse
import io as _io
import json
import runpy
import contextlib
from pathlib import Path

# Ensure UTF-8 output on Windows console
_tools_dir = Path(__file__).resolve().parent
if str(_tools_dir) not in sys.path:
    sys.path.insert(0, str(_tools_dir))

from novel_utils import resolve_workspace, reconfigure_utf8

reconfigure_utf8()

def _run_inprocess(cmd: list):
    """Run a tool script in-process（无 subprocess 开销）.

    cmd is the legacy list [python_exe, script_path, *args]; only script_path
    and args are used. Returns (returncode, stdout_text, stderr_text).
    """
    script_path = cmd[1]
    extra_args = cmd[2:]
    old_argv = sys.argv[:]
    sys.argv = [script_path] + list(extra_args)
    out_buf, err_buf = _io.StringIO(), _io.StringIO()
    rc = 0
    try:
        with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
            runpy.run_path(str(script_path), run_name="__main__")
    except SystemExit as e:
        code = e.code
        rc = 0 if code is None else (code if isinstance(code, int) else 1)
    except Exception as e:
        rc = 1
        err_buf.write(f"{type(e).__name__}: {e}")
    finally:
        sys.argv = old_argv
    return rc, out_buf.getvalue(), err_buf.getvalue()


def run_subtool_json(cmd: list) -> dict:
    """Runs a subtool in-process and parses its JSON payload（无 subprocess 开销）."""
    try:
        rc, stdout_text, stderr_text = _run_inprocess(cmd)
        text = (stdout_text or "").strip()
        parsed = None
        if text:
            idx_obj = text.find("{")
            idx_arr = text.find("[")
            start = -1
            if idx_obj != -1 and (idx_arr == -1 or idx_obj < idx_arr):
                start = idx_obj
            elif idx_arr != -1:
                start = idx_arr
            if start != -1:
                try:
                    parsed = json.loads(text[start:])
                except json.JSONDecodeError as e:
                    return {"error": f"\u5b50\u5de5\u5177\u8f93\u51fa\u65e0\u6cd5\u89e3\u6790\u4e3a JSON: {e}",
                            "raw_output": text[:300]}
        if parsed is None:
            if rc != 0:
                return {"error": (stderr_text.strip() or text or f"\u5b50\u5de5\u5177\u9000\u51fa\u7801 {rc}")[:300]}
            return {"status": "SKIP", "note": (text or "\u65e0\u8f93\u51fa")[:200]}
        if rc != 0 and isinstance(parsed, dict) and "error" not in parsed:
            parsed["_exit_code"] = rc
        return parsed
    except Exception as e:
        return {"error": str(e)}


def _run_subtool_text(cmd: list):
    """Run a subtool in-process, letting its output stream directly to stdout."""
    script_path = cmd[1]
    extra_args = cmd[2:]
    old_argv = sys.argv[:]
    sys.argv = [script_path] + list(extra_args)
    try:
        runpy.run_path(str(script_path), run_name="__main__")
    except SystemExit:
        pass
    except Exception as e:
        print(f"\u274c [\u5b50\u5de5\u5177\u6267\u884c\u5f02\u5e38] {Path(script_path).name}: {e}")
    finally:
        sys.argv = old_argv

def _is_blocking(report) -> bool:
    """Determines whether a subtool report represents a blocking failure."""
    if not isinstance(report, dict):
        return True
    if report.get("error"):
        return True
    # 子工具非零退出码视为阻断
    if report.get("_exit_code", 0) not in (0, None):
        return True
    if report.get("status") in ("FAIL",):
        return True
    if report.get("is_balanced") is False:
        return True
    if report.get("status") == "ERRORS" or report.get("error_count", 0):
        return True
    # 只有错误/FAIL/不平衡类硬信号才阻断总雷达。
    return False

def _collect_anomalies(name: str, report) -> list:
    """Extracts human-readable anomaly strings from a subtool report."""
    out = []
    if not isinstance(report, dict):
        return [f"[{name}] 无结构化输出"]
    if report.get("error"):
        out.append(f"[{name}] {report['error']}")
    for a in (report.get("anomalies") or []):
        out.append(f"[{name}] {a}")
    # memory_core 跨章重复检测用 warnings 字段（WARNING 级，提示而非硬阻断）；
    # 其字符串已自带 🔁/📝/🎬 前缀，直接用、不再加 ⚠️
    if name == "cross_chapter_repetition":
        for w in (report.get("warnings") or []):
            out.append(f"[{name}] {w}")
    for e in (report.get("errors") or []):
        out.append(f"[{name}] ❌ {e}")
    for w in (report.get("warnings") or []):
        # 新书模板里的 [方括号] 占位符属于“待填写”正常空态，只在 scorecard 里可见，
        # 不把总控雷达打成 ATTENTION（有 ERROR 仍会阻断）。
        if name == "workspace_doctor" and "占位符" in w:
            continue
        # 跨章重复已在上方专门处理（字符串自带前缀），此处跳过避免重复
        if name == "cross_chapter_repetition":
            continue
        out.append(f"[{name}] ⚠️ {w}")
    if report.get("status") == "FAIL":
        out.append(f"[{name}] 状态 FAIL")
    if report.get("is_balanced") is False:
        out.append(f"[{name}] 复式账本不平衡")
    return out

def run_master_radar(target_chapter=None, workspace_path=None, as_json=False):
    workspace_dir = resolve_workspace(workspace_path)
    tools_dir = Path(__file__).parent
    python_exe = sys.executable

    if as_json:
        # Collect real structured telemetry across all subtools
        scorecard = {}
        anomalies = []
        blocking_tools = []

        subtools = [
            ("workspace_doctor", [python_exe, str(tools_dir / "validate_state.py"), "-w", str(workspace_dir), "--json"]),
            ("double_ledgers", [python_exe, str(tools_dir / "verify_double_ledgers.py"), "-w", str(workspace_dir), "--json"]),
            ("state_machine", [python_exe, str(tools_dir / "state_inspector.py"), "-w", str(workspace_dir), "--json"]),
            ("economy_ledger", [python_exe, str(tools_dir / "audit_economy_ledger.py"), "-w", str(workspace_dir), "--json"]),
            ("memory_decay", [python_exe, str(tools_dir / "track_character_decay.py"), "-w", str(workspace_dir), "--json"]),
            ("character_network", [python_exe, str(tools_dir / "map_character_network.py"), "-w", str(workspace_dir), "--json"]),
            ("cross_chapter_repetition", [python_exe, str(tools_dir / "memory_core.py"), "-w", str(workspace_dir), "--json", "repeat"]),
        ]

        ch_subtools = [
            ("item_continuity", [python_exe, str(tools_dir / "track_item_continuity.py"), "-w", str(workspace_dir), "--json"]),
        ]

        all_tools = subtools + ch_subtools
        for name, cmd in all_tools:
            if name in {n for n, _ in ch_subtools} and target_chapter:
                cmd = cmd + ["-c", target_chapter]
            res = run_subtool_json(cmd)
            scorecard[name] = res
            tool_anoms = _collect_anomalies(name, res)
            # “无稿件”属于全新书的正常空态，不算阻断。
            empty = isinstance(res, dict) and (
                res.get("status") == "SKIP" or
                (res.get("error") and ("未找到" in str(res.get("error")) or "未在" in str(res.get("error")) or "暂无" in str(res.get("error"))))
            )
            if tool_anoms and not empty:
                anomalies.extend(tool_anoms)
            if _is_blocking(res) and not empty:
                blocking_tools.append(name)

        finalized_files = [
            f for f in (workspace_dir / "05_manuscript").glob("**/finalized/*.md")
            if not f.name.startswith(".")
        ] if (workspace_dir / "05_manuscript").exists() else []
        has_finalized = bool(finalized_files)
        master_report = {
            "workspace": workspace_dir.name,
            "target_chapter": target_chapter or "latest",
            "overall_status": ("ALL_GREEN" if has_finalized and not anomalies
                               else "ATTENTION_REQUIRED" if anomalies
                               else "NO_DATA"),
            "data_status": "ready" if has_finalized else "no_finalized_manuscript",
            "finalized_present": has_finalized,
            "blocking": bool(blocking_tools),
            "blocking_tools": blocking_tools,
            "anomalies_count": len(anomalies),
            "anomalies": anomalies,
            "scorecard": scorecard
        }
        print(json.dumps(master_report, ensure_ascii=False, indent=2))
        return master_report

    print("\n" + "═" * 76)
    print(f" 🚀 Universal Novel Studio - 全维健康巡检总控仪表盘 (Master Studio Radar)")
    print(f" 📂 目标工作区: {workspace_dir.name} | 🎯 巡检目标: {target_chapter or '全书最新进度'}")
    print("═" * 76)

    # 0. Workspace structure & ledger health (P0 deterministic doctor)
    print("\n" + "─" * 76)
    print(" 0️⃣ 【工作区结构完整性与复式账本自检 (Doctor)】")
    print("─" * 76)
    cmd_doctor = [python_exe, str(tools_dir / "validate_state.py"), "-w", str(workspace_dir)]
    _run_subtool_text(cmd_doctor)

    # 1. State & Guns & Double Ledgers
    print("\n" + "─" * 76)
    print(" 1️⃣ 【状态机与双台账交叉一致性校验】")
    print("─" * 76)
    cmd_ledger = [python_exe, str(tools_dir / "verify_double_ledgers.py"), "-w", str(workspace_dir)]
    _run_subtool_text(cmd_ledger)

    cmd_state = [python_exe, str(tools_dir / "state_inspector.py"), "-w", str(workspace_dir)]
    _run_subtool_text(cmd_state)

    # 2. Item Continuity
    print("\n" + "─" * 76)
    print(" 2️⃣ 【关键道具与资产时空流转轨迹】")
    print("─" * 76)
    cmd_items = [python_exe, str(tools_dir / "track_item_continuity.py"), "-w", str(workspace_dir)]
    if target_chapter:
        cmd_items.extend(["-c", target_chapter])
    _run_subtool_text(cmd_items)

    # 3. Character Social Network
    print("\n" + "─" * 76)
    print(" 3️⃣ 【全书人物戏份热力榜与社交图谱】")
    print("─" * 76)
    cmd_net = [python_exe, str(tools_dir / "map_character_network.py"), "-w", str(workspace_dir)]
    _run_subtool_text(cmd_net)

    # 4. Economy Double-Entry Ledger
    print("\n" + "─" * 76)
    print(" 4️⃣ 【全书资产与货币复式流水精算】")
    print("─" * 76)
    cmd_econ = [python_exe, str(tools_dir / "audit_economy_ledger.py"), "-w", str(workspace_dir)]
    _run_subtool_text(cmd_econ)

    # 5. Ebbinghaus Memory Decay Radar
    print("\n" + "─" * 76)
    print(" 5️⃣ 【核心角色艾宾浩斯记忆衰减雷达】")
    print("─" * 76)
    cmd_decay = [python_exe, str(tools_dir / "track_character_decay.py"), "-w", str(workspace_dir)]
    _run_subtool_text(cmd_decay)

    # 6. Cross-Chapter Repetition (P1 memory engine)
    print("\n" + "─" * 76)
    print(" 6️⃣ 【跨章重复检测：n-gram 雷同 / 场景节拍相似】")
    print("─" * 76)
    cmd_rep = [python_exe, str(tools_dir / "memory_core.py"), "-w", str(workspace_dir), "repeat"]
    _run_subtool_text(cmd_rep)

    print("\n" + "═" * 76)
    print(" ✨ [全维巡检完成] 结构/台账/经济/角色/重复/道具 全部巡检完毕。")
    print("═" * 76 + "\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Universal Novel Studio 全维健康巡检总控面板")
    parser.add_argument("--workspace", "-w", type=str, default=None, help="目标小说工作区路径")
    parser.add_argument("--chapter", "-c", type=str, default=None, help="指定章节，例如: ch_004")
    parser.add_argument("--json", action="store_true", help="以结构化 JSON 格式输出")
    args = parser.parse_args()

    report = run_master_radar(target_chapter=args.chapter, workspace_path=args.workspace, as_json=args.json)
    if isinstance(report, dict) and report.get("blocking"):
        sys.exit(1)
    sys.exit(0)
