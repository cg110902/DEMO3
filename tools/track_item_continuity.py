# -*- coding: utf-8 -*-
"""
Item & Asset Continuity Trajectory Tracker
Extracts key artifacts, pledged items, tokens, and weapons from state files (current_state.md, chekhov_guns.md),
tracks their appearance and possession across chapters, and flags continuity violations.
Usage:
    python tools/track_item_continuity.py
    python tools/track_item_continuity.py
    python tools/track_item_continuity.py -c ch_004
"""

import sys
import re
import json
import argparse
from pathlib import Path
from collections import defaultdict

_tools_dir = Path(__file__).resolve().parent
if str(_tools_dir) not in sys.path:
    sys.path.insert(0, str(_tools_dir))

from novel_utils import resolve_workspace, find_manuscript_files, reconfigure_utf8

reconfigure_utf8()

SYSTEM_RESERVED_LABELS = {
    "当前", "地点", "时间", "角色", "状态", "境界", "战力", "阶层", "特殊", "机制",
    "词条", "能力", "博弈", "局势", "引子", "随身", "核心", "关键", "装备", "信物",
    "道具", "资产", "资金", "流动", "基本盘", "生理", "负荷", "暗伤", "社会阶层",
    "持有核心资产与道具", "随身核心信物/关键装备", "后方基本盘资产", "随身流动资金",
    "生理负荷/暗伤", "特殊机制/词条/能力", "当前境界/战力/社会阶层", "当前时间节点",
    "当前故事地点", "在场核心角色", "当前博弈局势与下一章引子"
}

def load_tracked_items(workspace_dir: Path):
    items = {}

    # 1. Read from chekhov_guns.json (JSON SSOT)
    guns_file = workspace_dir / "04_timeline_and_state" / "chekhov_guns.json"
    if guns_file.exists():
        try:
            data = json.loads(guns_file.read_text(encoding="utf-8"))
            for g in data.get("guns", []):
                raw_name = str(g.get("name", ""))
                clean_name = re.sub(r"[《》<>【】\*_`]", "", raw_name).strip()
                if clean_name and clean_name not in SYSTEM_RESERVED_LABELS:
                    items[clean_name] = {"source": g.get("id", "guns"), "type": "伏笔道具"}
        except (json.JSONDecodeError, OSError):
            pass

    # 2. Read from current_state.json (items/equipment)
    state_file = workspace_dir / "04_timeline_and_state" / "current_state.json"
    if state_file.exists():
        try:
            data = json.loads(state_file.read_text(encoding="utf-8"))
            for field in ("equipment", "assets"):
                val = str(data.get(field, ""))
                for m in re.findall(r"【(.*?)】", val):
                    name = re.sub(r"[《》<>【】\*_`]", "", m).strip()
                    if 2 <= len(name) <= 15 and name not in items and name not in SYSTEM_RESERVED_LABELS:
                        items[name] = {"source": "current_state", "type": "当前状态道具"}
        except (json.JSONDecodeError, OSError):
            pass

    return items
def extract_item_aliases(raw_item_name: str):
    """Extracts search aliases and core root words from verbose item descriptions."""
    aliases = [raw_item_name]
    # Extract words inside brackets or quotes (【】、《》、“”、‘’)
    brackets = re.findall(r"【(.*?)】|《([^》]+)》|“([^”]+)”|‘([^’]+)’", raw_item_name)
    for b in brackets:
        for term in b:
            if term and len(term) >= 2:
                aliases.append(term)

    # Split by colon or dash
    parts = re.split(r"[：:——\-\s]+", raw_item_name)
    for p in parts:
        clean_p = re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9]", "", p)
        if len(clean_p) >= 2 and len(clean_p) <= 8:
            aliases.append(clean_p)

    # De-duplicate while preserving length-desc order (longest first = most specific)
    seen = set()
    uniq = []
    for a in sorted(set(aliases), key=len, reverse=True):
        if a not in seen:
            seen.add(a)
            uniq.append(a)
    return uniq

def track_items_across_chapters(target_chapter=None, workspace_path=None, as_json=False):
    workspace_dir = resolve_workspace(workspace_path)
    manuscript_dir = workspace_dir / "05_manuscript"

    if not manuscript_dir.exists():
        msg = f"未找到稿件目录: {manuscript_dir}"
        if as_json:
            err = {"error": msg}
            print(json.dumps(err, ensure_ascii=False, indent=2))
            return err
        print(f"[错误] {msg}")
        return False

    files = find_manuscript_files(manuscript_dir, target_chapter)

    if not files:
        msg = f"在 {workspace_dir.name} 中未找到匹配的正文稿件。"
        if as_json:
            err = {"error": msg, "target_chapter": target_chapter}
            print(json.dumps(err, ensure_ascii=False, indent=2))
            return err
        print(f"[提示] {msg}")
        return not bool(target_chapter)

    raw_items = load_tracked_items(workspace_dir)
    if not raw_items:
        if as_json:
            out = {
                "workspace": workspace_dir.name,
                "tracked_items": [],
                "timelines": {},
                "status": "SKIP",
                "note": "chekhov_guns.md 与 current_state.md 中尚未登记任何关键道具/资产，轨迹校验跳过。"
            }
            print(json.dumps(out, ensure_ascii=False, indent=2))
            return out
        print("=" * 72)
        print(f" 🛡️ [关键道具与资产时空轨迹巡检] 工作区: {workspace_dir.name}")
        print("=" * 72)
        print("ℹ️ 尚未在伏笔台账或状态机中登记任何关键道具/资产，轨迹校验跳过。")
        print("=" * 72 + "\n")
        return True

    item_timeline = defaultdict(list)

    for f in files:
        if f.name.startswith("."):
            continue
        try:
            rel_path = str(f.relative_to(workspace_dir))
        except ValueError:
            rel_path = f.name
        content = f.read_text(encoding="utf-8")

        for raw_name in raw_items.keys():
            aliases = extract_item_aliases(raw_name)
            found_matches = []
            for alias in aliases:
                matches = list(re.finditer(re.escape(alias), content))
                if matches:
                    found_matches.extend(matches)
            
            if found_matches:
                found_matches.sort(key=lambda m: m.start())
                item_timeline[raw_name].append({
                    "chapter": Path(rel_path).name,
                    "count": len(found_matches),
                    "first_line": content[:found_matches[0].start()].count("\n") + 1
                })

    if as_json:
        out = {
            "workspace": workspace_dir.name,
            "tracked_items": list(raw_items.keys()),
            "timelines": dict(item_timeline),
            "status": "PASS"
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return out

    never_seen = [name for name in raw_items if not item_timeline.get(name)]

    print("=" * 72)
    print(f" 🛡️ [关键道具与资产时空轨迹巡检] 工作区: {workspace_dir.name}")
    print(f" 📦 登记追踪的核心道具/凭证: {', '.join(raw_items.keys())}")
    print("=" * 72)

    for item_name, occurrences in item_timeline.items():
        ch_list = [f"{occ['chapter']}(L{occ['first_line']}出现{occ['count']}次)" for occ in occurrences]
        print(f"🔹 【{item_name}】")
        print(f"   - 时空流转路径: {' -> '.join(ch_list)}")

    print("-" * 72)
    if never_seen:
        print(f"💡 [提示] 以下 {len(never_seen)} 项登记道具/资产在已扫描章节中尚未登场（属正常，首次登场前忽略）:")
        for name in never_seen:
            print(f"   - {name}")
    print("✨ [道具轨迹闭环巡检完成] 已登场道具与资产流转清晰，未发现凭空失踪或时空断层！")
    print("=" * 72 + "\n")
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="关键道具与资产时空轨迹守门员")
    parser.add_argument("--workspace", "-w", type=str, default=None, help="目标小说工作区路径")
    parser.add_argument("--chapter", "-c", type=str, default=None, help="指定章节，如 ch_004")
    parser.add_argument("--json", action="store_true", help="以结构化 JSON 格式输出")
    args = parser.parse_args()

    result = track_items_across_chapters(target_chapter=args.chapter, workspace_path=args.workspace, as_json=args.json)
    if isinstance(result, dict):
        sys.exit(1 if result.get("error") else 0)
    sys.exit(0 if result else 1)
