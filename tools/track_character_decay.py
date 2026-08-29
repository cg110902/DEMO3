# -*- coding: utf-8 -*-
"""
Character Ebbinghaus Memory Decay & Fade Radar
1. Scans all manuscript chapters to track the last appearance and mention of each character.
2. Applies the Ebbinghaus Exponential Memory Decay formula (R = e^(-Δc / S)) to model reader retention.
3. Automatically flags characters at risk of being forgotten (Retention < 35%) and suggests re-activation hooks.
Usage:
    python tools/track_character_decay.py
    python tools/track_character_decay.py
    python tools/track_character_decay.py --json
"""

import sys
import re
import math
import json
import argparse
from pathlib import Path
from collections import defaultdict

_tools_dir = Path(__file__).resolve().parent
if str(_tools_dir) not in sys.path:
    sys.path.insert(0, str(_tools_dir))

from novel_utils import (
    resolve_workspace, find_manuscript_files, reconfigure_utf8, strip_name_title,
    is_table_separator,
)

reconfigure_utf8()

def load_characters(workspace_dir: Path):
    chars = {}
    index_file = workspace_dir / "02_characters" / "character_index.md"
    if index_file.exists():
        content = index_file.read_text(encoding="utf-8")
        for line in content.splitlines():
            # 跳过表头/表体分隔行（兼容 `| --- |`、`|:---|`、`| :--- |` 等变体）
            if line.startswith("|") and not line.startswith("| 角色") and not is_table_separator(line):
                parts = [p.strip() for p in line.split("|") if p.strip()]
                if len(parts) >= 3:
                    # 首列仅由分隔符符号组成（如 :---）不是角色名，过滤
                    if re.fullmatch(r"[\s:\-]+", parts[0]):
                        continue
                    cname = re.sub(r"[*_`]", "", parts[0]).strip()
                    cname = re.sub(r"\s*[（(].*?[）)]", "", cname).strip()
                    cname = strip_name_title(cname)
                    role_type = parts[1].strip()
                    # Assign Memory Strength (S) based on role
                    if "主角" in role_type or "男主" in role_type:
                        s = 15.0
                    elif "女一" in role_type or "女主" in role_type or "重要女配" in role_type or "剑仙" in role_type:
                        s = 6.0
                    elif "核心配角" in role_type or "管账" in role_type or "助手" in role_type or "师妹" in role_type or "师弟" in role_type:
                        s = 4.5
                    elif "反派" in role_type or "执事" in role_type:
                        s = 4.0
                    else:
                        s = 3.0
                    if cname and len(cname) <= 10:
                        chars[cname] = {"role": role_type, "strength": s}

    # Fallback to profiles directory if index didn't yield characters
    if not chars:
        profiles_dir = workspace_dir / "02_characters" / "profiles"
        if profiles_dir.exists():
            for pfile in sorted(profiles_dir.glob("*.md")):
                if not pfile.name.startswith("."):
                    content = pfile.read_text(encoding="utf-8")
                    m = re.search(r"#+\s*(?:角色(?:姓名|名|卡)?[：:]\s*)?([^\n(（\s#*]+)", content)
                    if m:
                        cname = m.group(1).strip()
                        cname = re.sub(r"[*_`#]", "", cname).strip()
                        if cname and len(cname) <= 10:
                            is_lead = "主角" in content or "protagonist" in pfile.stem.lower()
                            chars[cname] = {"role": "主角" if is_lead else "核心角色", "strength": 15.0 if is_lead else 5.0}

    return chars

def track_memory_decay(workspace_path=None, as_json=False, print_output=True):
    workspace_dir = resolve_workspace(workspace_path)
    characters = load_characters(workspace_dir)
    if not characters:
        characters = {
            "主角": {"role": "核心主角", "strength": 15.0}
        }

    manuscript_dir = workspace_dir / "05_manuscript"
    if not manuscript_dir.exists():
        if as_json:
            err = {"error": f"未找到稿件目录: {manuscript_dir}"}
            if print_output:
                print(json.dumps(err, ensure_ascii=False, indent=2))
            return err
        print(f"[错误] 未找到稿件目录: {manuscript_dir}")
        return False

    files = find_manuscript_files(manuscript_dir)

    total_chapters = len(files)
    if total_chapters == 0:
        if as_json:
            err = {"error": f"在 {workspace_dir.name} 中暂无正文稿件。"}
            if print_output:
                print(json.dumps(err, ensure_ascii=False, indent=2))
            return err
        print(f"[提示] 在 {workspace_dir.name} 中暂无正文稿件。")
        return False

    last_seen_chapter = {}
    mention_history = defaultdict(list)

    for idx, f in enumerate(files, 1):
        content = f.read_text(encoding="utf-8")
        for cname in characters.keys():
            if cname in content:
                last_seen_chapter[cname] = idx
                mention_history[cname].append(idx)

    decay_results = []
    warnings = []

    for cname, meta in characters.items():
        last_ch = last_seen_chapter.get(cname, 0)
        delta_c = max(0, total_chapters - last_ch)
        strength = meta["strength"]
        
        # Ebbinghaus Decay: R = e^(-delta / S)
        retention = math.exp(-delta_c / strength) * 100.0

        status = "活跃登场" if delta_c == 0 else f"掉线 {delta_c} 章"
        if retention < 35.0:
            warnings.append(f"⚠️ [角色掉线预警] 【{cname} ({meta['role']})】已连续 {delta_c} 章未出场 (读者记忆留存率仅 {retention:.1f}%)！建议在下章安排同台或侧面提及唤醒！")

        decay_results.append({
            "character": cname,
            "role": meta["role"],
            "last_seen_chapter": last_ch,
            "chapters_since_last": delta_c,
            "retention_rate": round(retention, 1),
            "status": status
        })

    decay_results.sort(key=lambda x: x["retention_rate"], reverse=True)

    report_payload = {
        "workspace": workspace_dir.name,
        "total_chapters": total_chapters,
        "results": decay_results,
        "warnings": warnings
    }

    if as_json:
        if print_output:
            print(json.dumps(report_payload, ensure_ascii=False, indent=2))
        return report_payload

    print("═" * 74)
    print(f" 🧠 [核心角色艾宾浩斯记忆衰减雷达] 工作区: {workspace_dir.name} | 当前进度: 第 {total_chapters} 章")
    print("═" * 74)
    print(f"   {'角色姓名':<10} | {'角色定位':<14} | {'最近登场':<10} | {'记忆留存率':<12} | {'读者心智状态'}")
    print("   " + "-" * 66)

    for r in decay_results:
        bar_len = int(r["retention_rate"] / 10)
        bar_str = "█" * bar_len + "░" * (10 - bar_len)
        print(f"   {r['character']:<10} | {r['role']:<14} | 第 {r['last_seen_chapter']:<8} 章 | [{bar_str}] {r['retention_rate']:>5.1f}% | {r['status']}")

    print("\n" + "─" * 74)
    if warnings:
        print("🚨 【掉线唤醒建议清单】:")
        for w in warnings:
            print(f"   {w}")
    else:
        print("✨ [全员活跃健康] 核心角色戏份交织紧密，读者心智记忆留存率全员高位！")
    print("═" * 74 + "\n")
    return report_payload

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="核心角色艾宾浩斯记忆衰减与掉线雷达")
    parser.add_argument("--workspace", "-w", type=str, default=None, help="目标小说工作区路径")
    parser.add_argument("--json", action="store_true", help="以结构化 JSON 格式输出")
    args = parser.parse_args()

    track_memory_decay(workspace_path=args.workspace, as_json=args.json)
