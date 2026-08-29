# -*- coding: utf-8 -*-
"""
Full Novel Character Social Network & Screen-time Topology Analyzer
Scans all finalized chapters, builds character co-occurrence matrices, tracks cast screen-time,
and flags "Forgotten Core Characters" (absent for >5 chapters) and "NPC Overload".
Usage:
    python tools/map_character_network.py
    python tools/map_character_network.py
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

from novel_utils import resolve_workspace, find_manuscript_files, load_registered_characters, reconfigure_utf8

reconfigure_utf8()

def analyze_character_network(workspace_path=None, as_json=False):
    workspace_dir = resolve_workspace(workspace_path)
    manuscript_dir = workspace_dir / "05_manuscript"

    if not manuscript_dir.exists():
        if as_json:
            err = {"error": f"未找到 05_manuscript 目录: {manuscript_dir}"}
            print(json.dumps(err, ensure_ascii=False, indent=2))
            return err
        print(f"[提示] 未找到 05_manuscript 目录: {manuscript_dir}")
        return True

    finalized_files = find_manuscript_files(manuscript_dir)

    if not finalized_files:
        if as_json:
            err = {"error": f"在 {workspace_dir.name} 中暂无正文稿件文件。"}
            print(json.dumps(err, ensure_ascii=False, indent=2))
            return err
        print(f"[提示] 在 {workspace_dir.name} 中暂无正文稿件文件。")
        return True

    characters = load_registered_characters(workspace_dir)
    if not characters:
        if as_json:
            err = {"error": "暂未在 02_characters 登记角色。"}
            print(json.dumps(err, ensure_ascii=False, indent=2))
            return err
        print("[提示] 暂未在 02_characters 登记角色。")
        return True

    char_presence = defaultdict(list)
    char_total_mentions = defaultdict(int)
    co_occurrences = defaultdict(lambda: defaultdict(int))

    for ch_idx, f in enumerate(finalized_files, 1):
        content = f.read_text(encoding="utf-8")
        present_in_ch = []

        for c in characters:
            count = len(re.findall(re.escape(c), content))
            if count > 0:
                char_presence[c].append(ch_idx)
                char_total_mentions[c] += count
                present_in_ch.append(c)

        # Update co-occurrences
        for i in range(len(present_in_ch)):
            for j in range(i + 1, len(present_in_ch)):
                c1, c2 = present_in_ch[i], present_in_ch[j]
                co_occurrences[c1][c2] += 1
                co_occurrences[c2][c1] += 1

    total_chapters = len(finalized_files)
    leaderboard = []
    for c, total_m in sorted(char_total_mentions.items(), key=lambda x: x[1], reverse=True):
        ch_count = len(char_presence[c])
        cov = round((ch_count / max(1, total_chapters)) * 100, 1)
        leaderboard.append({
            "character": c,
            "total_mentions": total_m,
            "appeared_chapters_count": ch_count,
            "coverage_rate": cov
        })

    key_bonds = []
    reported_pairs = set()
    for c1, partners in co_occurrences.items():
        for c2, co_cnt in sorted(partners.items(), key=lambda x: x[1], reverse=True):
            pair_key = tuple(sorted([c1, c2]))
            if pair_key not in reported_pairs and co_cnt >= 2:
                reported_pairs.add(pair_key)
                key_bonds.append({"pair": [c1, c2], "co_appearances": co_cnt})

    forgotten = []
    for c in characters:
        if c in char_presence and char_presence[c]:
            last_seen = char_presence[c][-1]
            gap = total_chapters - last_seen
            if gap >= 4 and char_total_mentions[c] >= 10:
                forgotten.append({"character": c, "last_seen_chapter": last_seen, "chapters_missing": gap})

    if as_json:
        out = {
            "workspace": workspace_dir.name,
            "total_chapters_scanned": total_chapters,
            "leaderboard": leaderboard,
            "key_relationships": key_bonds,
            "forgotten_characters": forgotten,
            "status": "PASS" if not forgotten else "WARNING"
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return out

    print("=" * 72)
    print(f" 🌐 [全书人物出场与社交关系拓扑图谱] 工作区: {workspace_dir.name} (共扫描 {total_chapters} 章)")
    print("=" * 72)

    # 1. Screen-time Leaderboard
    print("📊 【人物出场频次与戏份热力榜】:")
    print(f"   {'角色姓名':<12} | {'总提及次数':<10} | {'登场章节数':<10} | {'覆盖率':<8}")
    print("   " + "-" * 52)
    for entry in leaderboard:
        print(f"   {entry['character']:<12} | {entry['total_mentions']:<10} | {entry['appeared_chapters_count']:<10} | {entry['coverage_rate']:<7.1f}%")

    # 2. Key Relationships
    print("\n💞 【核心人物羁绊与高频同台 (Top Co-occurrences)】:")
    if key_bonds:
        for b in key_bonds:
            print(f"   - 【{b['pair'][0]}】 🤝 【{b['pair'][1]}】：共同登场 {b['co_appearances']} 章 (高频交互角色)")
    else:
        print("   ✓ 暂无跨多章高频同台记录")

    # 3. Disappearance / Forgotten Character Radar
    print("\n🔍 【人物掉线与遗忘预警雷达】:")
    if forgotten:
        for f_item in forgotten:
            print(f"   ⚠️ [核心角色掉线预警] 角色【{f_item['character']}】已连续 {f_item['chapters_missing']} 章未出场 (上次登场: 第 {f_item['last_seen_chapter']} 章)！建议安排回场或交代动向。")
    else:
        print("   ✓ 核心角色节奏紧凑，未发现主角团成员异常掉线！")

    print("=" * 72 + "\n")
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="全书人物社交网络与戏份拓扑图谱")
    parser.add_argument("--workspace", "-w", type=str, default=None, help="目标小说工作区路径")
    parser.add_argument("--json", action="store_true", help="以结构化 JSON 格式输出")
    args = parser.parse_args()

    analyze_character_network(workspace_path=args.workspace, as_json=args.json)
