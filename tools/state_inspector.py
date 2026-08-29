# -*- coding: utf-8 -*-
"""
State Inspector for Novel Workspace
Scans JSON state SSOT, active Chekhov guns, misunderstandings, finalized chapter
statistics, and provides Snapshot & Rollback capabilities for multi-branch writing.

Usage:
    python tools/state_inspector.py
    python tools/state_inspector.py --snapshot ch_003_done
    python tools/state_inspector.py --rollback ch_003_done
    python tools/state_inspector.py --list-snapshots
"""

import sys
import re
import json
import shutil
import argparse
import hashlib
import os
from datetime import datetime
from pathlib import Path

_tools_dir = Path(__file__).resolve().parent
if str(_tools_dir) not in sys.path:
    sys.path.insert(0, str(_tools_dir))

from novel_utils import resolve_workspace, reconfigure_utf8, canonical_json_hash
import state_store as ss

reconfigure_utf8()


def _snapshot_manifest(folder: Path) -> dict:
    files = {}
    for f in sorted(folder.iterdir()):
        if f.is_file() and f.name != "manifest.json":
            files[f.name] = hashlib.sha256(f.read_bytes()).hexdigest()
    return {"version": 1, "files": files, "hash": canonical_json_hash(files)}


def create_snapshot(workspace_dir: Path, snapshot_name: str):
    state_dir = workspace_dir / "04_timeline_and_state"
    if not state_dir.exists():
        print(f"[错误] 状态机目录不存在: {state_dir}")
        return False

    snapshots_dir = state_dir / "snapshots"
    snapshots_dir.mkdir(parents=True, exist_ok=True)

    if not isinstance(snapshot_name, str) or not snapshot_name.strip():
        print("[错误] 快照名称不能为空")
        return False
    clean_name = re.sub(r"[^\w\-.]", "_", snapshot_name.strip())
    if ".." in clean_name or clean_name.startswith("."):
        print("[错误] 快照名称不得包含路径片段")
        return False
    if not clean_name or clean_name in {".", ".."}:
        print("[错误] 快照名称无效")
        return False
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    snap_folder = snapshots_dir / f"{timestamp}_{clean_name}"
    if snap_folder.exists():
        print("[错误] 快照名称冲突")
        return False

    # 快照必须持锁：并发 sync 进行中打快照会得到跨文件不一致的"撕裂快照"。
    with ss.file_lock(workspace_dir):
        snap_folder.mkdir(parents=True, exist_ok=False)
        copied_files = []
        for pattern in ["*.md", "*.json"]:
            for f in state_dir.glob(pattern):
                if f.is_file():
                    shutil.copy2(f, snap_folder / f.name)
                    copied_files.append(f.name)

    manifest = _snapshot_manifest(snap_folder)
    tmp = snap_folder / ".manifest.tmp"
    tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, snap_folder / "manifest.json")
    print(f"📸 [快照创建成功] 保存至: 04_timeline_and_state/snapshots/{snap_folder.name}")
    print(f"   - 备份文件: {', '.join(copied_files)}")
    return True


def list_snapshots(workspace_dir: Path):
    snapshots_dir = workspace_dir / "04_timeline_and_state" / "snapshots"
    print("=" * 60)
    print(f" 📂 [状态机历史快照清单] 工作区: {workspace_dir.name}")
    print("=" * 60)
    if not snapshots_dir.exists() or not list(snapshots_dir.iterdir()):
        print("   (暂无任何历史快照)")
        print("=" * 60)
        return

    for item in sorted(snapshots_dir.iterdir(), reverse=True):
        if item.is_dir():
            files = [f.name for f in item.iterdir()
                     if f.is_file() and (f.suffix in [".md", ".json"])]
            print(f"   📦 [{item.name}] 包含: {', '.join(files)}")
    print("=" * 60)


def rollback_snapshot(workspace_dir: Path, snapshot_target: str):
    # Serialize rollback with sync/snapshot operations.
    with ss.file_lock(workspace_dir):
        return _rollback_snapshot_locked(workspace_dir, snapshot_target)


def _rollback_snapshot_locked(workspace_dir: Path, snapshot_target: str):
    state_dir = workspace_dir / "04_timeline_and_state"
    snapshots_dir = state_dir / "snapshots"

    if not snapshots_dir.exists():
        print("[错误] 没有找到任何快照目录！")
        return False

    all_dirs = [d for d in snapshots_dir.iterdir() if d.is_dir()]

    def _strip_timestamp(name: str) -> str:
        m = re.match(r"^\d{8}_\d{6}_(.+)$", name)
        return m.group(1) if m else name

    exact = [d for d in all_dirs if _strip_timestamp(d.name) == snapshot_target]
    matched_dirs = exact if exact else [d for d in all_dirs if snapshot_target in d.name]
    if not matched_dirs:
        print(f"[错误] 未找到匹配 '{snapshot_target}' 的快照！")
        list_snapshots(workspace_dir)
        return False

    if not exact and len(matched_dirs) > 1:
        print(f"⚠️ [注意] 快照名 '{snapshot_target}' 非精确匹配到 {len(matched_dirs)} 个快照，"
              f"已自动选择最新的一个: {sorted(matched_dirs, reverse=True)[0].name}")

    target_dir = sorted(matched_dirs, reverse=True)[0]

    # 回滚前校验快照完整性：manifest 哈希不符说明快照损坏，静默恢复会以损坏
    # 数据覆盖当前状态——必须拒绝并提示。
    manifest_path = target_dir / "manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            bad = [fname for fname, h in (manifest.get("files") or {}).items()
                   if not (target_dir / fname).exists()
                   or hashlib.sha256((target_dir / fname).read_bytes()).hexdigest() != h]
            if bad:
                print(f"[错误] 快照完整性校验失败（损坏/缺失: {', '.join(bad[:5])}），拒绝回滚。")
                return False
        except (json.JSONDecodeError, OSError) as exc:
            print(f"[错误] 快照 manifest 解析失败，拒绝回滚: {exc}")
            return False

    auto_backup = snapshots_dir / f"pre_rollback_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
    auto_backup.mkdir(parents=True, exist_ok=False)
    for pattern in ["*.md", "*.json"]:
        for f in state_dir.glob(pattern):
            if f.is_file():
                shutil.copy2(f, auto_backup / f.name)

    restored_files = []
    for pattern in ["*.md", "*.json"]:
        for f in target_dir.glob(pattern):
            # manifest.json 是快照审计元数据，不是状态 SSOT，不落回活动目录
            if f.is_file() and f.name != "manifest.json":
                shutil.copy2(f, state_dir / f.name)
                restored_files.append(f.name)

    # JSON 回滚后重渲染 Markdown 视图，避免"JSON 已回滚、MD 仍是新状态"的视图漂移
    try:
        ss.render_all_markdown(workspace_dir)
    except Exception as exc:
        print(f"[警告] Markdown 视图重渲染失败（JSON 状态已正确回滚）: {exc}")

    print(f"🔄 [回滚成功] 已将状态机复原至快照: {target_dir.name}")
    print(f"   - 恢复文件: {', '.join(restored_files)}")
    print(f"   - 原当前状态已自动安全备份至: {auto_backup.name}")
    return True


def _load_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8-sig"))
    except Exception:
        return None


def inspect_state(workspace_path=None, as_json=False):
    workspace_dir = resolve_workspace(workspace_path)
    state_report = {
        "workspace": workspace_dir.name,
        "title": "未设置",
        "genre": "通用",
        "pov": "第三人称限制视角",
        "guns": {"planted": 0, "reminded": 0, "resolved": 0, "active_list": []},
        "spatial_temporal_anchor": {"location": "未知", "time": "未明确"},
        "misunderstandings": [],
        "character_growth_arcs": {},
        "manuscript_stats": {"total_chapters": 0, "total_words": 0, "chapters": []}
    }

    # 1. Project Bible (human-authored Markdown, not a state SSOT)
    bible_file = workspace_dir / "00_meta" / "project_bible.md"
    if bible_file.exists():
        content = bible_file.read_text(encoding="utf-8")
        title_match = re.search(r"(?:^|\n)\s*[-*]?\s*\*\*书名.*?\*\*\s*[:：]\s*(.*)", content)
        if not title_match:
            title_header = re.search(r"#+\s*《?(.*?)》?\s*(?:项目圣经|设定|档案)", content)
            title = title_header.group(1).strip() if title_header else "未设置"
        else:
            title = title_match.group(1).strip()

        genre_match = re.search(
            r"(?:^|\n)\s*[-*]?\s*\*\*(?:主类型|题材|题材定位).*?\*\*\s*[:：]\s*(.*)", content)
        pov_match = re.search(
            r"(?:^|\n)\s*[-*]?\s*\*\*视角.*?\*\*\s*[:：]\s*(.*)", content)
        genre = genre_match.group(1).strip() if genre_match else "通用"
        pov = pov_match.group(1).strip() if pov_match else "第三人称限制视角"
        state_report["title"] = title
        state_report["genre"] = genre
        state_report["pov"] = pov

    state_dir = workspace_dir / "04_timeline_and_state"

    # 2. Chekhov guns (JSON)
    guns_data = _load_json(state_dir / "chekhov_guns.json")
    if guns_data:
        for g in guns_data.get("guns", []):
            status = str(g.get("status", ""))
            sl = status.lower()
            if any(k in sl for k in ["planted", "pending", "已埋下"]):
                state_report["guns"]["planted"] += 1
            elif any(k in sl for k in ["reminded", "active", "激化", "已激化"]):
                state_report["guns"]["reminded"] += 1
            elif any(k in sl for k in ["resolved", "triggered", "已回收", "已触发"]):
                state_report["guns"]["resolved"] += 1
            if not any(k in sl for k in ["resolved", "triggered", "已回收", "已触发"]):
                state_report["guns"]["active_list"].append({
                    "id": g.get("id", ""), "name": g.get("name", ""),
                    "status": status, "target_ch": g.get("target_ch", "")})

    # 3. Current state (JSON)
    cs_data = _load_json(state_dir / "current_state.json")
    if cs_data:
        state_report["spatial_temporal_anchor"]["location"] = cs_data.get("location") or "未知"
        state_report["spatial_temporal_anchor"]["time"] = cs_data.get("time") or "未明确"

    # 4. Misunderstandings (JSON)
    mis_data = _load_json(state_dir / "misunderstandings.json")
    if mis_data:
        for m in mis_data.get("misunderstandings", []):
            status = str(m.get("status", "Active"))
            if not any(k in status.lower() for k in ["resolved", "已澄清"]):
                state_report["misunderstandings"].append({
                    "id": m.get("id", ""), "parties": m.get("parties", ""),
                    "target": m.get("target_ch", "")})

    # 5. Growth arcs (JSON)
    ga_data = _load_json(state_dir / "character_growth_arcs.json")
    if ga_data:
        for a in ga_data.get("arcs", []):
            cname = re.sub(r"[*_`]", "", str(a.get("name", ""))).strip()
            stage = re.sub(r"[*_`]", "", str(a.get("stage", ""))).strip()
            if cname:
                state_report["character_growth_arcs"][cname] = {
                    "stage": stage,
                    "strategy": a.get("strategy") or a.get("inciting_event", "")}

    # 6. Chapters & word count
    manuscript_dir = workspace_dir / "05_manuscript"
    total_words = 0
    total_chapters = 0

    if manuscript_dir.exists():
        finalized_files = sorted(
            [f for f in manuscript_dir.glob("**/finalized/*.md") if not f.name.startswith(".")])
        for ch_file in finalized_files:
            text = ch_file.read_text(encoding="utf-8")
            chinese_chars = len(re.findall(r'[\u4e00-\u9fa5]', text))
            total_words += chinese_chars
            total_chapters += 1
            first_line = text.strip().splitlines()[0] if text.strip() else ch_file.stem
            ch_title = re.sub(r"^#+\s*", "", first_line)
            state_report["manuscript_stats"]["chapters"].append({
                "stem": ch_file.stem, "title": ch_title, "words": chinese_chars})
        state_report["manuscript_stats"]["total_chapters"] = total_chapters
        state_report["manuscript_stats"]["total_words"] = total_words

    if as_json:
        print(json.dumps(state_report, ensure_ascii=False, indent=2))
        return state_report

    print("=" * 64)
    print(" 🔍 Universal Novel Studio - 状态机与双台账巡检报告")
    print(f" 📂 目标工作区: {workspace_dir.name}")
    print("=" * 64)
    print(f"📖 小说书名: {state_report['title']} | 题材: {state_report['genre']} | POV: {state_report['pov']}")
    print(f"\n🎯 契诃夫之枪 (伏笔台账与爆发雷达):")
    print(f"   - 已埋下 (Planted/Pending) : {state_report['guns']['planted']} | "
          f"已激化 (Reminded/Active): {state_report['guns']['reminded']} | "
          f"已回收/触发 (Resolved/Triggered): {state_report['guns']['resolved']}")
    for g in state_report["guns"]["active_list"]:
        print(f"   👉 [{g['status']}] {g['id']}: 《{g['name']}》 (预定引爆: {g['target_ch']})")

    print(f"\n📍 实时时空锚点: {state_report['spatial_temporal_anchor']['time']} "
          f"@ {state_report['spatial_temporal_anchor']['location']}")
    print(f"\n🎭 误会与信息差台账 (发酵中): {len(state_report['misunderstandings'])} 处")
    for m in state_report["misunderstandings"]:
        print(f"   👉 {m['id']}: {m['parties']} (计划引爆: {m['target']})")

    print(f"\n🧠 核心角色心智演进台账 (Growth Arcs):")
    for cname, arc in state_report["character_growth_arcs"].items():
        print(f"   👉 【{cname}】当前处于: {arc['stage']} (策略: {arc['strategy']})")

    print(f"\n📝 稿件进度统计:")
    ch_list = state_report["manuscript_stats"]["chapters"]
    display_list = ch_list if len(ch_list) <= 5 else ch_list[-3:]
    if len(ch_list) > 5:
        print(f"   ... (前 {len(ch_list) - 3} 章已归档收录)")
    for ch in display_list:
        print(f"   ✓ {ch['stem']}: {ch['title']} ({ch['words']} 字)")

    if total_chapters == 0:
        print("   - 暂无定稿章节 (finalized 为空)")
    else:
        print(f"\n📊 全书累计定稿: {total_chapters} 章 | 总字数: 约 {total_words} 字 "
              f"(均章: {total_words // max(1, total_chapters)} 字)")
    print("=" * 64)
    return state_report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Universal Novel Studio 状态机与双台账巡检工具")
    parser.add_argument("--workspace", "-w", type=str, default=None,
                        help="目标小说工作区路径 (默认为 novel_workspace)")
    parser.add_argument("--snapshot", type=str, nargs="?", const="manual", default=None,
                        help="保存当前状态机快照 (可指定名称)")
    parser.add_argument("--rollback", type=str, default=None, help="回滚至指定的历史快照")
    parser.add_argument("--list-snapshots", action="store_true", help="列出所有可用的历史状态机快照")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出巡检报告")
    args = parser.parse_args()

    ws = resolve_workspace(args.workspace)
    exit_code = 0
    if args.list_snapshots:
        list_snapshots(ws)
    elif args.snapshot is not None:
        exit_code = 0 if create_snapshot(ws, args.snapshot) else 1
    elif args.rollback is not None:
        exit_code = 0 if rollback_snapshot(ws, args.rollback) else 1
    else:
        report = inspect_state(workspace_path=args.workspace, as_json=args.json)
        if isinstance(report, dict) and report.get("error"):
            exit_code = 1
    sys.exit(exit_code)
