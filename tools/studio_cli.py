# -*- coding: utf-8 -*-
"""
Universal Novel Studio - 统一总控 CLI 实现 (tools/studio_cli.py)

注意：这是根目录 studio.py 的具体实现，属于 🔴 禁读区。
AI 只需要命令地图时，请运行 `python studio.py help --json`，
请勿阅读本文件源码。

架构：状态文件以 JSON 为机器 SSOT（04_timeline_and_state/*.json），
Markdown 为自动渲染的只读视图；所有工具同进程调用，无 subprocess 开销。
"""

import sys
import json
import re
import logging
import runpy
import argparse
from pathlib import Path

# Root = repo root (studio_cli.py lives inside tools/)
_root_dir = Path(__file__).resolve().parent.parent
_tools_dir = _root_dir / "tools"
if str(_tools_dir) not in sys.path:
    sys.path.insert(0, str(_tools_dir))

from novel_utils import (resolve_workspace, reconfigure_utf8, find_manuscript_files,
                         latest_chapter_number)
from _version import __version__
from config_core import load_effective_config, clear_cache as _clear_config_cache

logger = logging.getLogger("novel_studio.studio")

reconfigure_utf8()

def _norm_ch(token: str) -> str:
    """Normalize a chapter token to 'ch_XXX' form; exit with a clean error if invalid."""
    if isinstance(token, str) and re.fullmatch(r"ch_\d{3,}", token):
        return token
    try:
        value = int(token)
        if value < 1:
            raise ValueError
        return f"ch_{value:03d}"
    except (TypeError, ValueError):
        print(f"❌ [错误] 无法解析章节编号: {token!r}（示例: 6 或 ch_006）")
        sys.exit(2)


def run_script(script_name: str, extra_args: list) -> int:
    """Executes a tool script from tools/ in-process（无 subprocess 开销）."""
    script_path = _tools_dir / script_name
    if not script_path.exists():
        print(f"❌ [错误] 未找到工具脚本: {script_path}")
        return 1

    old_argv = sys.argv[:]
    sys.argv = [str(script_path)] + list(extra_args)
    try:
        runpy.run_path(str(script_path), run_name="__main__")
        return 0
    except SystemExit as e:
        code = e.code
        if code is None:
            return 0
        return code if isinstance(code, int) else 1
    except Exception as e:
        print(f"❌ [工具执行异常] {script_name}: {e}")
        return 1
    finally:
        sys.argv = old_argv

def _est_tokens_of(text: str) -> int:
    """粗略 token 估算：中文 1 字 ≈ 1 token，ASCII 约 4 字符 ≈ 1 token。"""
    if not text:
        return 0
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    return cjk + max(1, (len(text) - cjk) // 4)


# hello 导览的阅读价目表：(层级, 路径, 何时读)
_DOC_READING_LIST = [
    ("🟢 开局必读", "AGENTS.md", "开局 1 次（法典+地图+纪律）"),
    ("🟢 开局必读", "agents/rules/novel_workflow.md", "开局 1 次（Stage 0-4 全流程 SOP）"),
    ("🟡 按需·文风", "agents/rules/novel_style.md", "做文风/基调判断时"),
    ("🟡 按需·长线", "agents/rules/novel_long_arc_and_pacing.md", "规划卷纲/能力阶梯/经济体系时"),
    ("🟡 按需·爽点", "agents/rules/novel_brainhole_and_pacing.md", "策划看点/推演细纲时"),
    ("🟡 按需·防OOC", "agents/rules/novel_anti_ooc.md", "写角色/审校行为一致性时"),
    ("🟡 角色·总策划", "agents/skills/novel-director/SKILL.md", "扮演总策划（新书策划）时"),
    ("🟡 角色·编剧", "agents/skills/novel-beats-builder/SKILL.md", "扮演编剧（推细纲）时"),
    ("🟡 角色·主笔", "agents/skills/novel-chapter-drafter/SKILL.md", "扮演主笔（写正文）时"),
    ("🟡 角色·审校官", "agents/skills/novel-continuity-guard/SKILL.md", "扮演审校官（定稿重铸）时"),
    ("🟡 角色·同步官", "agents/skills/novel-state-syncer/SKILL.md", "扮演同步官（状态提案）时"),
]


def _project_brief(workspace_dir: Path) -> dict:
    """采集轻量项目事实，供 `status` 与 `hello` 共用（一次磁盘扫描，两处消费）。"""
    state_dir = workspace_dir / "04_timeline_and_state"
    manuscript_dir = workspace_dir / "05_manuscript"

    # 1. Project Bible Info
    bible_file = workspace_dir / "00_meta" / "project_bible.md"
    title = "未命名小说"
    genre = "通用"
    if bible_file.exists():
        c = bible_file.read_text(encoding="utf-8")
        tm = re.search(r"-\s*\*\*书名.*?\*\*\s*[:：]\s*(.*)", c)
        if tm:
            title = re.sub(r"[《》]", "", tm.group(1).strip())
        gm = re.search(r"-\s*\*\*主类型.*?\*\*\s*[:：]\s*(.*)", c)
        if gm:
            genre = gm.group(1).strip()

    # 2. Manuscript Stats
    finalized_files = find_manuscript_files(manuscript_dir)
    total_words = 0
    for f in finalized_files:
        txt = f.read_text(encoding="utf-8")
        total_words += len(re.findall(r"[\u4e00-\u9fa5]", txt))
    latest = latest_chapter_number(manuscript_dir, require_finalized=True)

    # 3. Double Ledger Pools
    ledger_file = state_dir / "economy_ledger.json"
    pools_summary = []
    if ledger_file.exists():
        try:
            ldata = json.loads(ledger_file.read_text(encoding="utf-8"))
            if "resource_pools" in ldata:
                for k, v in ldata["resource_pools"].items():
                    pools_summary.append(f"{v.get('name', k)}: {v.get('current', 0)} {v.get('unit', '')}")
            elif "current_balance" in ldata:
                pools_summary.append(f"基础货币: {ldata.get('current_balance', 0)}")
        except Exception as e:
            logger.warning("economy_ledger.json 解析失败，资产池信息不可用: %s", e)

    # 4. Active Guns & Misunderstandings （JSON SSOT；Planted/Reminded 均为活跃态）
    guns_file = state_dir / "chekhov_guns.json"
    active_guns = 0
    if guns_file.exists():
        try:
            gdata = json.loads(guns_file.read_text(encoding="utf-8"))
            active_guns = sum(
                1 for g in gdata.get("guns", [])
                if str(g.get("status", "")).lower() in ("planted", "reminded", "active", "pending")
            )
        except Exception as e:
            logger.warning("chekhov_guns.json 解析失败，活跃伏笔计数不可用: %s", e)

    # 5. Pending proposals in state_inbox (excluding drafts/templates/samples)
    pending = []
    inbox = state_dir / "state_inbox"
    if inbox.exists():
        pending = [p.name for p in inbox.glob("*.json")
                   if not p.name.endswith((".draft.json", ".template.json", ".sample.json"))]

    return {
        "exists": workspace_dir.exists(),
        "workspace": workspace_dir.name,
        "title": title,
        "genre": genre,
        "finalized_chapters": len(finalized_files),
        "latest_chapter": latest,
        "total_words": total_words,
        "pools_summary": pools_summary,
        "active_guns": active_guns,
        "pending_proposals": pending,
    }


def _hello_next_actions(brief: dict) -> list:
    """按当前进度给出最小可行的下一步动作清单（只给当前场景需要的）。"""
    acts = []
    if not brief["exists"]:
        acts.append('Stage 0｜工作区不存在：python studio.py init -t "书名" -g "题材" -p "主角名"')
        acts.append("Stage 0｜与用户对齐核心设定 → 只读 agents/skills/novel-director/SKILL.md")
        return acts
    if brief["pending_proposals"]:
        acts.append(f"Stage 4｜state_inbox 有 {len(brief['pending_proposals'])} 份未决提案："
                    "按模板复核撰写正式提案后，python studio.py sync ch_xxx 合并")
    if brief["latest_chapter"] == 0:
        acts.append("Stage 1｜从第 1 章开始：python studio.py pack ch_001 --json（装载语境推演细纲）")
        acts.append("配套：读 agents/rules/novel_workflow.md §Stage 1 + agents/skills/novel-beats-builder/SKILL.md")
    else:
        n = brief["latest_chapter"] + 1
        acts.append(f"Stage 1｜下一章 ch_{n:03d}：python studio.py pack ch_{n:03d} --json")
        acts.append(f"流程：beats 细纲 → 起草 raw_drafts → 审校 finalized"
                    f"→ 正式提案 → sync ch_{n:03d}（SOP 见 novel_workflow.md，逐角色读 SKILL）")
    return acts


def cmd_hello(args):
    """AI 入口导览：当前进度 + 下一步动作 + 文档 token 价目 + 禁读区提醒。"""
    workspace_dir = resolve_workspace(args.workspace)
    brief = _project_brief(workspace_dir)
    brief["workflow_mode"] = _workflow_mode(workspace_dir)

    # 阅读价目（实时计算，随文档演进自动更新）
    reading = []
    for tier, rel, when in _DOC_READING_LIST:
        p = _root_dir / rel
        tokens = _est_tokens_of(p.read_text(encoding="utf-8")) if p.exists() else 0
        reading.append({"tier": tier, "path": rel, "tokens": tokens, "when": when})
    forbidden_tokens = sum(
        _est_tokens_of(p.read_text(encoding="utf-8"))
        for p in list(_tools_dir.glob("*.py")) + [_root_dir / "studio.py"]
        if p.exists()
    )

    if args.json:
        print(json.dumps({
            "workspace": brief["workspace"],
            "project": brief,
            "next_actions": _hello_next_actions(brief),
            "reading_list": reading,
            "forbidden_zone": {
                "paths": ["tools/*.py", "studio.py"],
                "total_tokens": forbidden_tokens,
                "rule": "禁读源码；只通过 python studio.py <命令> 调用，仅付出输出 token",
            },
        }, ensure_ascii=False, indent=2))
        return 0

    print("=" * 68)
    print(" 🏠 Universal Novel Studio — AI 入口导览 (hello)")
    print("=" * 68)
    print(" ① 你在哪：AI-First 小说工业化流水线（确定性工具 + JSON 状态机）")
    print("    边界与禁区 → AGENTS.md ｜ 流程 SOP → agents/rules/novel_workflow.md")
    print()
    print(" ② 当前项目：")
    if brief["exists"]:
        pools = " | ".join(brief["pools_summary"]) if brief["pools_summary"] else "未建立"
        print(f"    《{brief['title']}》· {brief['genre']} ｜ 工作区 {brief['workspace']}")
        print(f"    定稿 {brief['finalized_chapters']} 章（最新 ch_{brief['latest_chapter']:03d}）· 约 {brief['total_words']:,} 字"
              f" ｜ 活跃伏笔 {brief['active_guns']} ｜ 未决提案 {len(brief['pending_proposals'])}")
        print(f"    资产池：{pools}")
    else:
        print(f"    工作区 {brief['workspace']} 尚未初始化（不妨碍你先读地图，见 ④）")
    print()
    print(" ③ 下一步（只做当前场景需要的）：")
    for i, a in enumerate(_hello_next_actions(brief), 1):
        print(f"    {i}. {a}")
    print()
    print(" ④ 阅读价目表（按需加载，禁止通读；价目实时计算）：")
    for r in reading:
        print(f"    {r['tier']} {r['path']:<52} ≈{r['tokens']/1000:.1f}k tok  {r['when']}")
    print()
    print(" ⑤ 禁读区（只调用，不阅读）：")
    print(f"    🔴 tools/*.py + studio.py 合计 ≈ {forbidden_tokens/1000:.0f}k tok")
    print("       → 一律通过 python studio.py <命令> 调用：只付输出 token，不付源码 token")
    print("       → status ≈0.2k ｜ hello ≈0.6k ｜ pack 全量约 2~8k（--budget 可裁）")
    print("=" * 68)
    return 0


def _workflow_mode(workspace_dir):
    return load_effective_config(str(workspace_dir)).get("workflow", {}).get("mode", "automatic")


def cmd_mode(args):
    """查看或切换当前工作区的 manual/automatic 模式。"""
    workspace_dir = resolve_workspace(args.workspace)
    mode_file = workspace_dir / "00_meta" / "workflow_mode.json"
    current = _workflow_mode(workspace_dir)
    if args.set_mode:
        if args.set_mode not in {"manual", "automatic"}:
            print(f"❌ [配置错误] mode 必须是 manual 或 automatic: {args.set_mode}")
            return 2
        mode_file.parent.mkdir(parents=True, exist_ok=True)
        mode_file.write_text(json.dumps({"mode": args.set_mode}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        _clear_config_cache()
        current = args.set_mode
    if args.json:
        if mode_file.exists():
            src = "workspace_mode_file"
        else:
            try:
                gp = workspace_dir / "00_meta" / "genre_profile.json"
                ws_mode = json.loads(gp.read_text(encoding="utf-8-sig")).get("workflow", {}).get("mode") if gp.exists() else None
            except Exception:
                ws_mode = None
            src = "workspace_profile" if ws_mode else "global_default"
        print(json.dumps({"workspace": workspace_dir.name, "mode": current, "source": src}, ensure_ascii=False, indent=2))
    else:
        print(f"当前工作模式: {current}")
    return 0


def cmd_status(args):
    """View quick dashboard status of the novel workspace."""
    workspace_dir = resolve_workspace(args.workspace)
    brief = _project_brief(workspace_dir)
    brief["workflow_mode"] = _workflow_mode(workspace_dir)

    print("=" * 64)
    print(f" 📊 Universal Novel Studio - 项目状态简报")
    print("=" * 64)
    print(f" 📖 书名: 《{brief['title']}》")
    print(f" 🎭 题材: {brief['genre']}")
    print(f" 📂 工作区: {brief['workspace']}")
    print(f" ⚙️ 工作模式: {brief['workflow_mode']}")
    print(f" 📝 定稿进度: {brief['finalized_chapters']} 章 | 总字数: 约 {brief['total_words']:,} 字")
    print(f" 💰 量化资产池: {' | '.join(brief['pools_summary']) if brief['pools_summary'] else '未建立'}")
    print(f" 🎯 活跃伏笔: {brief['active_guns']} 处")
    print("=" * 64)
    return 0


def cmd_pack(args):
    """Stage 2: Package full context for a chapter."""
    ch = _norm_ch(args.chapter)
    extra = ["-c", ch]
    if args.json:
        extra.append("--json")
    if getattr(args, "budget", 0):
        extra.extend(["--budget", str(args.budget)])
    if args.workspace:
        extra.extend(["-w", args.workspace])
    return run_script("package_context.py", extra)

def cmd_memory(args):
    """P1 memory engine: synopsis spine view / BM25 recall / cross-chapter repetition."""
    # memory_core.py 全局参数（-w/--json）须位于子命令之前
    extra = []
    if args.workspace:
        extra.extend(["-w", args.workspace])
    if args.json:
        extra.append("--json")
    extra.append(args.sub)
    if args.sub == "recall":
        if not args.query:
            print("❌ [USAGE] memory recall 需要查询词：python studio.py memory recall <query> [-k N]")
            return 2
        extra.append(args.query)
        if args.top_k:
            extra.extend(["-k", str(args.top_k)])
    return run_script("memory_core.py", extra)

def cmd_apply(args):
    """Stage 4: Apply a structured state-mutation proposal (deterministic state engine)."""
    extra = []
    if getattr(args, "file", None):
        extra.extend(["-f", args.file])
    if getattr(args, "dry_run", False):
        extra.append("--dry-run")
    if args.workspace:
        extra.extend(["-w", args.workspace])
    return run_script("state_apply.py", extra)

def cmd_doctor(args):
    """Health check: validate workspace structure, ledgers, and state files."""
    extra = []
    if args.workspace:
        extra.extend(["-w", args.workspace])
    return run_script("validate_state.py", extra)

def cmd_schedule(args):
    """P2 foreshadowing scheduler: proactive gun scheduling for beats-builder."""
    ch = _norm_ch(args.chapter)
    extra = ["-c", ch]
    if args.json:
        extra.append("--json")
    if args.workspace:
        extra.extend(["-w", args.workspace])
    return run_script("foreshadow_scheduler.py", extra)

def cmd_genre(args):
    """P3-4 genre profile: view / list configured genre profile."""
    extra = []
    if args.list:
        extra.append("--list")
    if args.genre:
        extra.extend(["--genre", args.genre])
    if args.json:
        extra.append("--json")
    if args.workspace:
        extra.extend(["-w", args.workspace])
    return run_script("genre_profile.py", extra)

def cmd_sync(args):
    """Stage 4: Verify ledgers, track continuity, and automatically snapshot."""
    ch = _norm_ch(args.chapter)
    w_arg = ["-w", args.workspace] if args.workspace else []
    
    print("=" * 72)
    print(f" 🔄 [Stage 4 · 状态自同步流水线] 目标章节: {ch}")
    print("=" * 72)

    # A sync must correspond to real chapter output and a real proposal.
    workspace_dir = resolve_workspace(args.workspace)
    if not find_manuscript_files(workspace_dir / "05_manuscript", ch):
        print(f"❌ 未找到章节稿件 {ch}，拒绝空同步。")
        return 1
    inbox = workspace_dir / "04_timeline_and_state" / "state_inbox"
    proposal = inbox / f"{ch}.json"
    failed_proposal = inbox / "failed" / f"{ch}.json"
    if not proposal.exists() and not failed_proposal.exists():
        print(f"❌ 未找到正式状态提案 {proposal}，拒绝空同步。")
        return 1
    if failed_proposal.exists():
        # SOP：修复 failed/ 中的正式提案后直接重跑 sync——由合并器在文件锁内捡回。
        print("↩️ 检测到 failed/ 中的本章提案，将在文件锁内自动捡回重试")

    # 0. Apply any pending structured state-mutation proposals (deterministic engine)
    #    --expect-chapter：只合并本章提案，收件箱中其他章节的提案跳过并留在原地
    print("\n[1/4] 正在合并状态变更提案 (state_apply)...")
    rc0 = run_script("state_apply.py", w_arg + ["--expect-chapter", ch])
    # Any failed proposal means the state transition is incomplete; never seal it.
    if rc0 != 0:
        print("❌ 状态提案未通过校验，已中止同步；请修复 failed/ 后重试。")
        return rc0

    # 1. Verify Double Ledgers
    print("\n[2/4] 正在校验双台账平衡 (verify_double_ledgers)...")
    rc1 = run_script("verify_double_ledgers.py", w_arg)
    if rc1 != 0:
        print("❌ 双台账校验未通过，中断同步！")
        return rc1

    # 2. Track Item Continuity
    print("\n[3/4] 正在核验道具流转轨迹 (track_item_continuity)...")
    rc2 = run_script("track_item_continuity.py", w_arg)
    if rc2 != 0:
        print("❌ 道具轨迹校验未通过，中断同步！")
        return rc2

    # 3. Snapshot
    snapshot_tag = f"{ch}_done"
    print(f"\n[4/4] 正在封存版本快照 ({snapshot_tag})...")
    rc3 = run_script("state_inspector.py", w_arg + ["--snapshot", snapshot_tag])

    print("\n" + "=" * 72)
    if rc3 == 0:
        print(f" ✨ [同步完成] {ch} 状态自同步与版本快照全部就绪！")
    else:
        print(f"❌ [同步失败] {ch} 快照封存失败（退出码 {rc3}），未宣布同步成功。")
    print("=" * 72)
    return rc3

def cmd_radar(args):
    """Run all 14 studio radars."""
    extra = []
    if args.chapter:
        ch = _norm_ch(args.chapter)
        extra.extend(["-c", ch])
    if args.json:
        extra.append("--json")
    if args.workspace:
        extra.extend(["-w", args.workspace])
    return run_script("studio_radar.py", extra)

def cmd_export(args):
    """Export whole novel."""
    extra = []
    if args.txt:
        extra.extend(["--format", "txt"])
    if args.workspace:
        extra.extend(["-w", args.workspace])
    return run_script("compile_novel.py", extra)

def cmd_init(args):
    """Stage 0: Initialize novel workspace scaffolding for ANY genre."""
    extra = ["--title", args.title, "--genre", args.genre, "--protagonist", args.protagonist]
    if args.clean:
        extra.append("--clean")
    if getattr(args, "force", False):
        extra.append("--force")
    if args.workspace:
        extra.extend(["-w", args.workspace])
    return run_script("init_new_novel.py", extra)

def cmd_snapshots(args):
    """List all state-machine snapshots."""
    extra = ["--list-snapshots"]
    if args.workspace:
        extra.extend(["-w", args.workspace])
    return run_script("state_inspector.py", extra)

def cmd_clean(args):
    """Clean drafts or full manuscript."""
    extra = ["--clean"]
    if args.workspace:
        extra.extend(["-w", args.workspace])
    return run_script("init_new_novel.py", extra)

def cmd_snapshot(args):
    """Create a named snapshot."""
    extra = ["--snapshot", args.name]
    if args.workspace:
        extra.extend(["-w", args.workspace])
    return run_script("state_inspector.py", extra)

def cmd_rollback(args):
    """Rollback to a snapshot and optionally clean newer drafts."""
    extra = ["--rollback", args.name]
    if args.workspace:
        extra.extend(["-w", args.workspace])
    rc = run_script("state_inspector.py", extra)
    
    if rc == 0 and getattr(args, "clean_drafts", False):
        workspace_dir = resolve_workspace(args.workspace)
        ch_match = re.search(r"ch_(\d+)", args.name)
        if ch_match:
            base_num = int(ch_match.group(1))
            # Scan all manuscript directories (raw_drafts & finalized across all volumes)
            manuscript_dir = workspace_dir / "05_manuscript"
            for f in manuscript_dir.glob("**/ch_*.md"):
                fm = re.search(r"ch_(\d+)", f.name)
                if fm and int(fm.group(1)) > base_num:
                    f.unlink()
                    print(f"   🧹 [清理孤立手稿] 已删除超出快照版本的章节: {f.relative_to(workspace_dir)}")
            # Scan all beats directories across all volumes
            outlines_dir = workspace_dir / "03_outlines"
            for f in outlines_dir.glob("**/beats/ch_*_beats.md"):
                fm = re.search(r"ch_(\d+)", f.name)
                if fm and int(fm.group(1)) > base_num:
                    f.unlink()
                    print(f"   🧹 [清理孤立细纲] 已删除超出快照版本的细纲: {f.relative_to(workspace_dir)}")
    return rc


# ---------------------------------------------------------------------------
# 命令目录（机器可读）：让 AI 用 `studio.py help --json` 获取命令地图，
# 代替阅读源码，避免为理解 CLI 而读 10k+ token。
# ---------------------------------------------------------------------------


def _command_catalog(parser=None):
    """从 argparse 结构提取全部子命令清单，不重复维护第二份列表。"""
    parser = parser or _build_parser()
    catalog = []
    for action in parser._actions:
        if not isinstance(action, argparse._SubParsersAction):
            continue
        for ca in action._choices_actions:
            name = ca.dest
            sub = action.choices.get(name)
            if sub is None:
                continue
            positionals = []
            options = []
            for a in sub._actions:
                if a.option_strings and not set(a.option_strings) & {"-h", "--help"}:
                    options.append(",".join(a.option_strings))
                elif not a.option_strings and isinstance(a, argparse._StoreAction):
                    positionals.append(a.dest)
            catalog.append({
                "name": name,
                "help": ca.help,
                "aliases": [],
                "positionals": positionals,  # 保持声明顺序（自动化按序拼命令）
                "options": sorted(options),
            })
    return catalog


def cmd_help(args):
    """输出命令目录（--json 机读，代读源码）。"""
    catalog = _command_catalog()
    if getattr(args, "json", False):
        print(json.dumps({"commands": catalog}, ensure_ascii=False, indent=2))
        return 0
    for c in catalog:
        alias_note = f"  （别名: {', '.join(c['aliases'])}）" if c["aliases"] else ""
        print(f"{c['name']:<12} {c['help']}{alias_note}")
        if c["positionals"]:
            print(f"            args: {' '.join(c['positionals'])}")
        if c["options"]:
            print(f"            opts: {' '.join(c['options'])}")
    return 0


def _build_parser():
    parser = argparse.ArgumentParser(
        description=f"Universal Novel Studio v{__version__} - 统一工程总控 CLI (studio.py)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="完整工作流见 AGENTS.md；结构性命令地图请运行 `studio.py help --json`。"
    )
    parser.add_argument("--version", "-V", action="version",
                        version=f"Universal Novel Studio v{__version__}")
    subparsers = parser.add_subparsers(dest="command", help="可用命令 (输入 `python studio.py <cmd> -h` 查看单项帮助)")

    # hello（AI 入口导览：每次开局的第一条命令）
    p_hello = subparsers.add_parser("hello", help="[通用] AI 入口导览：当前进度/下一步/文档 token 价目/禁读区")
    p_hello.add_argument("-w", "--workspace", help="指定工作区路径")
    p_hello.add_argument("--json", action="store_true", help="以结构化 JSON 格式输出 (Agent 首选用例)")
    p_hello.set_defaults(func=cmd_hello)

    # mode
    p_mode = subparsers.add_parser("mode", help="查看或切换 manual/automatic 工作模式")
    p_mode.add_argument("--set", dest="set_mode", choices=["manual", "automatic"], help="切换当前工作区模式")
    p_mode.add_argument("-w", "--workspace", help="指定工作区路径")
    p_mode.add_argument("--json", action="store_true", help="以结构化 JSON 格式输出")
    p_mode.set_defaults(func=cmd_mode)

    # status
    p_status = subparsers.add_parser("status", help="[通用] 查看当前小说项目状态概览与资产指标")
    p_status.add_argument("-w", "--workspace", help="指定工作区路径")
    p_status.set_defaults(func=cmd_status)

    # pack
    p_pack = subparsers.add_parser("pack", help="[Stage 1] 一键装载单章全量创作语境 (用于Beats细纲推演)")
    p_pack.add_argument("chapter", help="目标章节 (如 6 或 ch_006)")
    p_pack.add_argument("-w", "--workspace", help="指定工作区路径")
    p_pack.add_argument("--json", action="store_true", help="以结构化 JSON 格式输出 (Agent 首选用例)")
    p_pack.add_argument("--budget", type=int, default=0, help="token 预算；>0 时按相关性裁剪并报告裁掉了什么 (0=全量)")
    p_pack.set_defaults(func=cmd_pack)

    # memory (P1: synopsis spine / BM25 librarian / cross-chapter repetition)
    p_mem = subparsers.add_parser("memory", help="[P1 记忆引擎] 梗概脊柱查看 / BM25 资料员召回 / 跨章重复检测")
    p_mem.add_argument("sub", choices=["spine", "recall", "repeat"], help="spine=查看梗概脊柱; recall=BM25召回; repeat=跨章重复检测")
    p_mem.add_argument("query", nargs="?", help="recall 子命令的查询词")
    p_mem.add_argument("-k", "--top-k", type=int, default=5, help="recall 返回条数")
    p_mem.add_argument("-w", "--workspace", help="指定工作区路径")
    p_mem.add_argument("--json", action="store_true", help="以结构化 JSON 格式输出")
    p_mem.set_defaults(func=cmd_memory)

    # apply
    p_apply = subparsers.add_parser("apply", help="[Stage 4] 确定性合并 state_inbox 中的结构化状态变更提案")
    p_apply.add_argument("-f", "--file", help="指定单个提案 JSON 文件（默认处理整个 state_inbox/）")
    p_apply.add_argument("--dry-run", action="store_true", help="只校验预演，不写入")
    p_apply.add_argument("-w", "--workspace", help="指定工作区路径")
    p_apply.set_defaults(func=cmd_apply)

    # doctor
    p_doc = subparsers.add_parser("doctor", help="工作区健康自检（结构/台账/占位符/快照）")
    p_doc.add_argument("-w", "--workspace", help="指定工作区路径")
    p_doc.set_defaults(func=cmd_doctor)

    # schedule (P2: foreshadowing scheduler)
    p_sched = subparsers.add_parser("schedule", help="[P2 伏笔调度器] 为指定章 Beats 主动排期待引爆/回唤/沉睡伏笔")
    p_sched.add_argument("chapter", help="目标章节 (如 8 或 ch_008)")
    p_sched.add_argument("-w", "--workspace", help="指定工作区路径")
    p_sched.add_argument("--json", action="store_true", help="以结构化 JSON 格式输出")
    p_sched.set_defaults(func=cmd_schedule)

    # genre (P3-4: genre profile)
    p_genre = subparsers.add_parser("genre", help="[P3-4 题材档案] 查看当前题材 profile（配比/调度窗口/导演指导）")
    p_genre.add_argument("--list", action="store_true", help="列出所有内置题材档案")
    p_genre.add_argument("--genre", help="按题材文本解析匹配（不读工作区）")
    p_genre.add_argument("-w", "--workspace", help="指定工作区路径")
    p_genre.add_argument("--json", action="store_true", help="以结构化 JSON 格式输出")
    p_genre.set_defaults(func=cmd_genre)

    # sync
    p_sync = subparsers.add_parser("sync", help="[Stage 4] 双台账校验、道具流转核验与版本快照自同步")
    p_sync.add_argument("chapter", help="目标章节 (如 4 或 ch_004)")
    p_sync.add_argument("-w", "--workspace", help="指定工作区路径")
    p_sync.set_defaults(func=cmd_sync)

    # radar
    p_radar = subparsers.add_parser("radar", help="运行全维工程雷达总控仪表盘（聚合 doctor/台账/经济/角色/重复/道具等子工具）")
    p_radar.add_argument("chapter", nargs="?", help="指定章节 (可选)")
    p_radar.add_argument("-w", "--workspace", help="指定工作区路径")
    p_radar.add_argument("--json", action="store_true", help="输出 JSON 格式")
    p_radar.set_defaults(func=cmd_radar)

    # export
    p_export = subparsers.add_parser("export", help="编译并导出全书手稿")
    p_export.add_argument("--txt", action="store_true", help="导出为标准缩进 TXT 格式")
    p_export.add_argument("-w", "--workspace", help="指定工作区路径")
    p_export.set_defaults(func=cmd_export)

    # init
    p_init = subparsers.add_parser("init", help="[Stage 0] 初始化全题材新书脚手架工程资产")
    p_init.add_argument("--title", "-t", default="未命名新书", help="小说书名")
    p_init.add_argument("--genre", "-g", default="通用题材", help="小说题材分类")
    p_init.add_argument("--protagonist", "-p", default="主角名", help="主角姓名")
    p_init.add_argument("--clean", action="store_true", help="清空已有稿件与细纲，保留母版")
    p_init.add_argument("--force", action="store_true", help="工作区已有手稿/细纲时仍强制重建（危险）")
    p_init.add_argument("-w", "--workspace", help="指定工作区路径")
    p_init.set_defaults(func=cmd_init)

    # snapshots (list)
    p_snaps = subparsers.add_parser("snapshots", help="列出状态机所有历史版本快照")
    p_snaps.add_argument("-w", "--workspace", help="指定工作区路径")
    p_snaps.set_defaults(func=cmd_snapshots)

    # clean
    p_clean = subparsers.add_parser("clean", help="清空已有稿件与单章细纲")
    p_clean.add_argument("-w", "--workspace", help="指定工作区路径")
    p_clean.set_defaults(func=cmd_clean)

    # snapshot
    p_snap = subparsers.add_parser("snapshot", help="创建指定名称的状态机快照")
    p_snap.add_argument("name", help="快照名称 (如 ch_003_done)")
    p_snap.add_argument("-w", "--workspace", help="指定工作区路径")
    p_snap.set_defaults(func=cmd_snapshot)

    # rollback
    p_roll = subparsers.add_parser("rollback", help="回滚到指定快照")
    p_roll.add_argument("name", help="目标快照名称")
    p_roll.add_argument("--clean-drafts", action="store_true", help="自动清理大于该快照版本的孤立章节稿件")
    p_roll.add_argument("-w", "--workspace", help="指定工作区路径")
    p_roll.set_defaults(func=cmd_rollback)

    # help（机器可读命令目录，代读源码）
    p_help = subparsers.add_parser("help", help="[通用] 命令目录（--json 机读，代读源码）")
    p_help.add_argument("--json", action="store_true", help="输出结构化 JSON 命令目录")
    p_help.set_defaults(func=cmd_help)

    return parser


def main():
    parser = _build_parser()
    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(0)

    rc = args.func(args)
    sys.exit(rc or 0)


if __name__ == "__main__":
    main()
