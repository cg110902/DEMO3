# -*- coding: utf-8 -*-
"""
Deterministic State-Mutation Applier (state_apply.py)
========================================================
LLM produces a structured JSON mutation proposal; this tool deterministically
validates and merges it into the JSON SSOT via ``state_store``, then renders
the Markdown read-only views.

Design notes:
- State SSOT migrated from Markdown tables to JSON (state_store.py);
  Markdown files are now auto-generated views.
- Cross-platform file lock around inbox processing for concurrent-sync safety.
- Proposal schema unchanged (novel-studio.state-mutation/v1); ``realm`` still
  accepted as an alias for ``power_level`` for backward compatibility.

Usage:
    python tools/state_apply.py                     # merge all inbox proposals
    python tools/state_apply.py -f proposal.json    # merge one proposal
    python tools/state_apply.py --dry-run           # validate only
    python tools/state_apply.py --json
"""

import sys
import re
import json
import math
import argparse
from pathlib import Path

_tools_dir = Path(__file__).resolve().parent
if str(_tools_dir) not in sys.path:
    sys.path.insert(0, str(_tools_dir))

from novel_utils import resolve_workspace, reconfigure_utf8, atomic_write_text, canonical_json_hash
import state_store as ss

reconfigure_utf8()

MUTATION_SCHEMA = "novel-studio.state-mutation/v1"
_CHAPTER_RE = re.compile(r"^ch_\d{3,}$")


def _norm_ch(value):
    """Return canonical chapter token, rejecting path traversal and ambiguity."""
    if not isinstance(value, str) or not _CHAPTER_RE.fullmatch(value):
        return None
    return value


def validate_proposal(proposal: dict, expected_chapter=None) -> list:
    """Validate envelope and closed mutation fields before any writes."""
    errors = []
    if not isinstance(proposal, dict):
        return ["提案必须是 JSON 对象"]
    if proposal.get("schema") != MUTATION_SCHEMA:
        errors.append(f"schema 必须为 {MUTATION_SCHEMA}")
    chapter = proposal.get("chapter")
    if "operation_id" in proposal and (not isinstance(proposal["operation_id"], str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", proposal["operation_id"])):
        errors.append("operation_id 必须为安全 token")
    # Formal proposals must carry a stable idempotency identity. Drafts are
    # intentionally exempt because they never enter the applier.
    if not proposal.get("_draft") and not proposal.get("operation_id"):
        errors.append("正式提案必须提供 operation_id")
    if _norm_ch(chapter) is None:
        errors.append("chapter 必须匹配 ch_NNN 格式且不得包含路径片段")
    elif expected_chapter is not None and chapter != expected_chapter:
        errors.append(f"chapter 与目标章节不一致: {chapter} != {expected_chapter}")
    for key in ("transactions", "guns", "misunderstandings", "growth_arcs", "timeline"):
        if key in proposal and not isinstance(proposal[key], list):
            errors.append(f"{key} 必须为数组")
    if "current_state" in proposal and not isinstance(proposal["current_state"], dict):
        errors.append("current_state 必须为对象")
    candidate_keys = [k for k in proposal if k.startswith("candidate_")]
    if candidate_keys:
        errors.append("候选字段仅供复核，不能直接合并：" + ", ".join(candidate_keys))
    for t in proposal.get("transactions", []) or []:
        if not isinstance(t, dict):
            errors.append("交易元素必须为对象")
            continue
        if not isinstance(t.get("resource"), str) or not t.get("resource"):
            errors.append("交易字段 resource 必填且必须为字符串")
        if "delta" not in t and ("inflow" not in t or "outflow" not in t):
            errors.append("交易字段必须提供 delta 或 inflow/outflow")
        for numeric in ("delta", "inflow", "outflow"):
            if numeric in t and (isinstance(t[numeric], bool) or not isinstance(t[numeric], (int, float))
                                 or not math.isfinite(t[numeric])):
                errors.append(f"交易字段 {numeric} 必须为有限数值（NaN/Infinity 拒绝）")
        # 金额以整数记账：浮点 delta 会被静默截断造成账面与提案不一致
        delta_v = t.get("delta")
        if isinstance(delta_v, float) and math.isfinite(delta_v) and not float(delta_v).is_integer():
            errors.append(f"交易字段 delta 必须为整数: {delta_v}")
        # 记账约定：delta 正收负支。type 与符号矛盾会造成静默错账
        # （引擎按 delta 记账，type 只是标签），此处 fail-fast 并给出修正指引。
        ttype = t.get("type")
        delta = t.get("delta")
        if ttype in ("income", "expense") and isinstance(delta, (int, float)) \
                and not isinstance(delta, bool):
            if ttype == "income" and delta < 0:
                errors.append(
                    f"流水 type='income' 但 delta={delta}（约定：delta 正收负支；"
                    "收入用正数，或删掉 type 交由引擎按符号推断）")
            if ttype == "expense" and delta > 0:
                errors.append(
                    f"流水 type='expense' 但 delta=+{delta}（约定：delta 正收负支；"
                    "支出必须为负数，或删掉 type 交由引擎按符号推断）")
    return errors


# ─────────────────────────────────────────────────────────────────────
# Economy ledger (JSON) — double-entry, derived balances
# ─────────────────────────────────────────────────────────────────────
def apply_transactions(ledger_path: Path, transactions: list, chapter: str,
                       report: dict):
    if not ledger_path.exists():
        report["errors"].append(f"账本文件不存在: {ledger_path.name}")
        return
    data = json.loads(ledger_path.read_text(encoding="utf-8-sig"))
    pools = data.get("resource_pools")
    if not pools:
        report["errors"].append("economy_ledger.json 缺少 resource_pools，无法记账")
        return

    running = {k: v.get("initial", 0) for k, v in pools.items()}
    existing = data.get("transactions", [])
    for t in existing:
        rk = t.get("resource")
        if rk not in running:
            report["warnings"].append(
                f"历史流水引用了未声明资源池 '{rk}'，已跳过")
            continue
        delta = t.get("delta")
        if delta is None:
            delta = t.get("inflow", 0) - t.get("outflow", 0)
        running[rk] += delta

    added = 0
    for idx, t in enumerate(transactions, 1):
        rk = t.get("resource")
        if rk is None:
            rk = next(iter(pools))
        if rk not in running:
            report["errors"].append(
                f"流水 #{idx} 引用了 resource_pools 中不存在的资源池 '{rk}'"
                "（请先在台账登记）")
            continue
        delta = t.get("delta")
        if delta is None:
            delta = t.get("inflow", 0) - t.get("outflow", 0)
        try:
            delta = int(delta)
        except (TypeError, ValueError):
            report["errors"].append(f"流水 #{idx} 的 delta 非整数: {t.get('delta')}")
            continue
        running[rk] += delta
        tx = {
            "chapter": t.get("chapter", chapter),
            "resource": rk,
            "type": t.get("type", "income" if delta > 0 else "expense"),
            "delta": delta,
            "subject": t.get("subject", ""),
            "counterparty": t.get("counterparty", ""),
            "balance_after": running[rk],
        }
        if t.get("note"):
            tx["note"] = t["note"]
        existing.append(tx)
        added += 1
        report["updated"].append(
            f"💰 流水: {rk} {delta:+} → 余额 {running[rk]}（{tx['subject']}）")

    data["transactions"] = existing
    for k, v in pools.items():
        v["current"] = running.get(k, v.get("initial", 0))
    atomic_write_text(ledger_path,
                      json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    report["updated"].append(f"🧮 账本已记账 {added} 笔，资源池余额已按流水重算")


# ─────────────────────────────────────────────────────────────────────
# Apply one proposal
# ─────────────────────────────────────────────────────────────────────
def apply_proposal(workspace: Path, proposal: dict, dry_run: bool = False,
                   expected_chapter=None) -> dict:
    report = {"updated": [], "warnings": [], "errors": [],
              "chapter": proposal.get("chapter")}
    if proposal.get("_draft"):
        report["errors"].append(
            "这是草稿提案（_draft:true），不能直接合并；"
            "请 LLM 复核补全后另存为去掉 _draft 的正式提案。")
        return report
    report["errors"].extend(validate_proposal(proposal, expected_chapter))
    if report["errors"]:
        return report

    if proposal.get("schema") != MUTATION_SCHEMA:
        report["warnings"].append(
            f"提案 schema 为 {proposal.get('schema')!r}，期望 {MUTATION_SCHEMA}"
            "（仍尝试合并）")

    chapter = proposal.get("chapter", "")
    operation_id = proposal.get("operation_id")
    proposal_hash = canonical_json_hash({k: v for k, v in proposal.items() if k != "operation_id"})
    marker = ss.state_dir(workspace) / ".applied_operations.json"
    try:
        applied = json.loads(marker.read_text(encoding="utf-8")) if marker.exists() else {}
        if isinstance(applied, list):
            applied = {x: "legacy" for x in applied}
        if not isinstance(applied, dict):
            raise ValueError("dedupe index must be object")
        if operation_id and operation_id in applied:
            if applied[operation_id] != proposal_hash:
                report["errors"].append("operation_id 已用于不同提案，拒绝复用")
            else:
                report["warnings"].append(f"operation_id {operation_id} 已应用，跳过重复提案")
                report["duplicate"] = True
            return report
        if proposal_hash in applied.values():
            report["warnings"].append("提案 canonical hash 已应用，跳过重复提案")
            report["duplicate"] = True
            return report
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        report["errors"].append(f"操作去重记录损坏，拒绝合并: {exc}")
        return report

    if dry_run:
        for key in ("current_state", "guns", "misunderstandings",
                    "growth_arcs", "timeline", "transactions"):
            if proposal.get(key):
                report["updated"].append(f"[dry-run] 将合并 {key}")
        if proposal.get("synopsis"):
            report["updated"].append(f"[dry-run] 将登记章节梗概（{chapter}）")
        return report

    # Capture all state files before mutation. Merge helpers write individual
    # files, so restore the complete set if any later operation reports an error.
    state_root = ss.state_dir(workspace)
    rollback_files = {}
    for p in state_root.glob("*.json"):
        try:
            rollback_files[p] = p.read_bytes()
        except OSError as exc:
            report["errors"].append(f"无法建立事务备份: {p.name}: {exc}")
            return report

    # 合并阶段整体受事务保护：任何 merge 抛出异常（如 SSOT JSON 损坏、BOM、
    # 磁盘错误）都必须回滚全部状态文件，否则会留下"半合并"状态且提案不归档。
    try:
        if proposal.get("current_state"):
            ss.merge_current_state(workspace, proposal["current_state"], report)
        if proposal.get("guns"):
            ss.merge_guns(workspace, proposal["guns"], chapter, report)
        if proposal.get("misunderstandings"):
            ss.merge_misunderstandings(workspace, proposal["misunderstandings"],
                                       chapter, report)
        if proposal.get("growth_arcs"):
            ss.merge_growth_arcs(workspace, proposal["growth_arcs"], chapter, report)
        if proposal.get("timeline"):
            ss.merge_timeline(workspace, proposal["timeline"], report)
        if proposal.get("transactions"):
            ledger = ss.state_dir(workspace) / "economy_ledger.json"
            apply_transactions(ledger, proposal["transactions"], chapter, report)

        syn = proposal.get("synopsis")
        if syn:
            _merge_synopsis(workspace, chapter, syn,
                            proposal.get("chapter_title", ""), report)
    except Exception as exc:
        report["errors"].append(f"合并阶段异常，已回滚全部状态文件: {exc}")

    if report["errors"]:
        for p, content in rollback_files.items():
            try:
                p.write_bytes(content)
            except OSError:
                pass
        report["rollback"] = True
        return report

    # Persist operation identity only after all mutations completed.
    if not report["errors"] and not report.get("duplicate"):
        try:
            current = json.loads(marker.read_text(encoding="utf-8")) if marker.exists() else {}
            if isinstance(current, list):
                current = {x: "legacy" for x in current}
            current[operation_id or proposal_hash] = proposal_hash
            atomic_write_text(marker, json.dumps(current, ensure_ascii=False, indent=2) + "\n")
        except (json.JSONDecodeError, OSError, ValueError) as exc:
            # 幂等标记写失败时状态已落盘但"已应用"无据可查——重试会重复记账。
            # 必须回滚全部状态文件，让提案留在 failed/ 等待安全重放。
            report["errors"].append(f"操作去重记录写入失败，已回滚本次合并: {exc}")
            for p, content in rollback_files.items():
                try:
                    p.write_bytes(content)
                except OSError:
                    pass
            report["rollback"] = True
    return report


def _merge_synopsis(workspace: Path, chapter: str, synopsis: str, title: str,
                    report: dict):
    # 不吞异常：chapter_synopsis.json 损坏必须作为 error 触发事务回滚，
    # 而不是在空默认值上写回、静默清空全部历史梗概。
    import memory_core
    data = memory_core.load_synopsis(workspace)
    num_m = re.search(r"(\d+)", chapter or "")
    num = int(num_m.group(1)) if num_m else len(data["chapters"]) + 1
    key = f"ch_{num:03d}"
    prev = data["chapters"].get(key, {})
    prev_syn = str(prev.get("synopsis", "")).strip()
    new_syn = str(synopsis).strip()
    if prev_syn and prev_syn != new_syn and prev.get("source") == "manual":
        report["warnings"].append(
            f"⚠️ 章节 {key} 已存在人工梗概，本次提交将覆盖（旧：{prev_syn[:40]}…）。"
            "若为修正类提案，建议只携带需变更字段、省略 synopsis 以免误覆盖。")
    data["chapters"][key] = {
        "num": num,
        "title": title or prev.get("title", ""),
        "synopsis": new_syn,
        "source": "manual",
    }
    memory_core.save_synopsis(workspace, data)
    report["updated"].append(f"📖 章节梗概已登记（{key}，manual 覆盖 auto）")


def _gather_proposals(inbox: Path):
    if not inbox.exists():
        return []
    return sorted(
        p for p in inbox.glob("*.json")
        if not (p.name.endswith(".draft.json")
                or p.name.endswith(".template.json")
                or p.name.endswith(".sample.json"))
    )


def _archive_proposal(pf: Path, dst_dir: Path) -> Path:
    """把提案移动到 dst_dir；目标重名时自动加序号，绝不覆盖已有审计记录。

    （Windows 下 Path.rename 到已存在目标会抛 FileExistsError，POSIX 会静默
    覆盖旧审计文件——两者都不可接受，processed/failed 是回滚与审计依据。）
    """
    dst_dir.mkdir(parents=True, exist_ok=True)
    dest = dst_dir / pf.name
    if not dest.exists():
        return pf.rename(dest)
    stem, suffix = pf.stem, pf.suffix
    for i in range(2, 100):
        cand = dst_dir / f"{stem}.{i}{suffix}"
        if not cand.exists():
            return pf.rename(cand)
    # 兜底：同一名字失败近百次属极端情况，用时间戳保证唯一
    from datetime import datetime
    return pf.rename(dst_dir / f"{stem}.{datetime.now().strftime('%H%M%S%f')}{suffix}")


def main():
    parser = argparse.ArgumentParser(
        description="确定性状态变更合并器（State Mutation Applier）")
    parser.add_argument("--workspace", "-w", type=str, default=None,
                        help="工作区路径")
    parser.add_argument("--file", "-f", type=str, default=None,
                        help="指定单个提案 JSON 文件")
    parser.add_argument("--expect-chapter", type=str, default=None,
                        help="只合并该章节的提案（sync 模式）；其他章节提案跳过并留在收件箱")
    parser.add_argument("--dry-run", action="store_true", help="只校验与预演，不写入")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    args = parser.parse_args()

    workspace = resolve_workspace(args.workspace)
    state_dir = ss.state_dir(workspace)
    inbox = state_dir / "state_inbox"
    processed = inbox / "processed"
    failed = inbox / "failed"

    if args.file:
        files = [Path(args.file)]
    else:
        files = _gather_proposals(inbox)

    if not files and not (args.expect_chapter and (inbox / "failed" / f"{args.expect_chapter}.json").exists()):
        msg = f"state_inbox 中没有待处理提案（{inbox}）"
        if args.json:
            print(json.dumps({"status": "EMPTY", "message": msg},
                             ensure_ascii=False, indent=2))
        else:
            print(f"ℹ️ {msg}")
        sys.exit(0)

    overall = {"applied": 0, "failed": 0, "results": []}

    # Cross-platform exclusive lock: prevents two concurrent `sync` processes
    # from reading the same inbox and double-applying / overwriting each other.
    with ss.file_lock(workspace):
        # failed/ 捡回必须在锁内进行：并发 sync 同时通过存在性检查后竞争
        # rename 会在 Windows 上抛 FileExistsError，且可能重复应用。
        if args.expect_chapter and not args.file:
            failed_p = inbox / "failed" / f"{args.expect_chapter}.json"
            main_p = inbox / f"{args.expect_chapter}.json"
            if not main_p.exists() and failed_p.exists():
                failed_p.rename(main_p)
                print(f"↩️ 已从 failed/ 捡回提案 {main_p.name} 重试（若尚未修复将再次失败退回）")
                files = _gather_proposals(inbox)
        for pf in files:
            try:
                # utf-8-sig tolerates an optional BOM (some Windows editors add one)
                proposal = json.loads(pf.read_text(encoding="utf-8-sig"))
            except Exception as e:
                overall["failed"] += 1
                overall["results"].append(
                    {"file": pf.name, "updated": [], "warnings": [],
                     "errors": [f"提案 JSON 解析失败: {e}"]})
                if not args.dry_run:
                    _archive_proposal(pf, failed)
                break

            if args.expect_chapter:
                pch = proposal.get("chapter") if isinstance(proposal, dict) else None
                if pch != args.expect_chapter:
                    overall["skipped"] = overall.get("skipped", 0) + 1
                    overall["results"].append(
                        {"file": pf.name, "chapter": pch, "updated": [],
                         "warnings": [], "errors": [],
                         "skipped": f"提案章节 {pch} != 同步目标 {args.expect_chapter}，跳过（留在收件箱）"})
                    continue
            try:
                rep = apply_proposal(workspace, proposal, dry_run=args.dry_run,
                                     expected_chapter=args.expect_chapter)
            except Exception as exc:
                rep = {"file": pf.name,
                       "chapter": proposal.get("chapter") if isinstance(proposal, dict) else None,
                       "updated": [], "warnings": [],
                       "errors": [f"合并过程异常: {exc}"]}
            rep["file"] = pf.name
            overall["results"].append(rep)
            if rep["errors"]:
                overall["failed"] += 1
                if not args.dry_run:
                    _archive_proposal(pf, failed)
                break
            else:
                overall["applied"] += 1
                if not args.dry_run:
                    _archive_proposal(pf, processed)

    if args.json:
        print(json.dumps(overall, ensure_ascii=False, indent=2))
    else:
        print("=" * 72)
        print(f" 🔀 [状态变更合并器] 工作区: {workspace.name}"
              f"{'  [DRY-RUN]' if args.dry_run else ''}")
        print("=" * 72)
        for r in overall["results"]:
            print(f"\n📄 {r['file']}（章节 {r.get('chapter','-')}）")
            if r.get("skipped"):
                print(f"   ⏭️ {r['skipped']}")
            for u in r["updated"]:
                print(f"   {u}")
            for w in r["warnings"]:
                print(f"   ⚠️ {w}")
            for e in r["errors"]:
                print(f"   ❌ {e}")
        print("\n" + "=" * 72)
        skipped_note = f" | ⏭️ 跳过 {overall.get('skipped', 0)} 份" if overall.get("skipped") else ""
        print(f" ✅ 成功合并 {overall['applied']} 份 | ❌ 失败 {overall['failed']} 份{skipped_note}")
        print("=" * 72)

    sys.exit(1 if overall["failed"] else 0)


if __name__ == "__main__":
    main()
