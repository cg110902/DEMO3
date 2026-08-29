# -*- coding: utf-8 -*-
"""
Foreshadowing Scheduler — P2 伏笔主动调度器（纯本地，零 Token）。

为 beats-builder 提供**主动排期建议**（全部基于章节号算术与字符串检索，无语义判断）：
  - 本章应「引爆/回收」哪些伏笔（target_ch == 当前进度或已超期）；
  - 本章应「提醒/复现」哪些伏笔（长期未被提及、读者快忘了，需在爆发前 N 章回唤）；
  - 哪些伏笔可「埋设」（新章开局的钩子）；
  - 长线伏笔（全局贯穿）给出周期性提醒节奏建议。

判定基于：chekhov_guns.json（JSON SSOT）的埋设章/状态/预定引爆章 + 全书定稿正文里
该伏笔关键词的最近出现章（用 BM25/词频在定稿里回查）。

用法：
    python tools/foreshadow_scheduler.py -c ch_008          # 给第 8 章 beats 排期
    python tools/foreshadow_scheduler.py -c ch_008 --json
"""

import sys
import re
import json
import argparse
from pathlib import Path

_tools_dir = Path(__file__).resolve().parent
if str(_tools_dir) not in sys.path:
    sys.path.insert(0, str(_tools_dir))

from novel_utils import (
    resolve_workspace, reconfigure_utf8, find_manuscript_files,
    natural_chapter_sort_key, chapter_number_from_name, has_placeholder,
)

reconfigure_utf8()


def _profile_windows(workspace: Path):
    """从题材档案取调度窗口（P3-4），失败回退默认。"""
    lead, gap, longline = 3, 5, (8, 12)
    try:
        import genre_profile as gp
        prof = gp.resolve_genre_profile(workspace) or {}
        s = prof.get("scheduler", {}) or {}
        lead = int(s.get("remind_lead", lead))
        gap = int(s.get("dormant_gap", gap))
        li = prof.get("longline_interval") or s.get("longline_interval")
        if isinstance(li, (list, tuple)) and len(li) == 2:
            longline = (int(li[0]), int(li[1]))
    except Exception:
        pass
    return lead, gap, longline

_RESOLVED_MARKS = ("Resolved", "已回收", "Triggered", "已引爆", "已澄清", "Closed")
_LONG_HINTS = ("全局", "全书", "贯穿", "长线", "待定", "未定", "卷末", "第二卷", "2 卷", "2卷")


def _parse_target(target_cell: str):
    """'第 18 章' -> 18；'第 5~10 章' -> (5,10)；长线 -> None。"""
    if any(k in target_cell for k in _LONG_HINTS):
        return None
    nums = [int(x) for x in re.findall(r"\d+", target_cell)]
    if not nums:
        return None
    return (min(nums), max(nums)) if len(nums) >= 2 else (nums[0], nums[0])


def _load_gun_waivers(workspace: Path) -> list:
    """Load structured GUN exemptions from project_bible.md frontmatter/section.

    The bible may contain a JSON object in a ``gun_waivers`` fenced block or a
    simple ``GUN waiver: ...`` line; only structured entries are trusted.
    """
    p = workspace / "00_meta" / "project_bible.md"
    if not p.exists():
        return []
    text = p.read_text(encoding="utf-8")
    waivers = []
    match = re.search(r"```json\s*\n(.*?)\n```", text, re.S)
    if match:
        try:
            obj = json.loads(match.group(1))
            waivers = obj.get("gun_waivers", []) if isinstance(obj, dict) else []
        except (json.JSONDecodeError, TypeError):
            pass
    return [
        w for w in waivers
        if isinstance(w, dict)
        and w.get("gun_id")
        and w.get("reason")
        and w.get("enabled", True) is not False
    ]


_IGNORED_WAIVERS = []  # 未生效的豁免条目（缺 exempt_until/long_term），schedule() 输出可见化


def _parse_guns(workspace: Path) -> list:
    """Read chekhov_guns.json (JSON SSOT) and return a list of gun dicts."""
    guns = []
    # 生效门槛：豁免必须声明期限（exempt_until）或长线性质（long_term）才接管调度。
    # 仅有 gun_id+reason 的条目（含项目圣经模板里的示例 JSON）不生效，避免
    # 模板示例误伤同名伏笔；未生效条目由 schedule() 输出 waiver_ignored 可见化。
    effective, ignored = {}, []
    for w in _load_gun_waivers(workspace):
        if w.get("exempt_until") or w.get("long_term") is True:
            effective[str(w["gun_id"])] = w
        else:
            ignored.append(w)
    p = workspace / "04_timeline_and_state" / "chekhov_guns.json"
    if not p.exists():
        _IGNORED_WAIVERS[:] = ignored
        return guns
    try:
        data = json.loads(p.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        _IGNORED_WAIVERS[:] = ignored
        return guns
    for g in data.get("guns", []):
        status = str(g.get("status", "Planted"))
        resolved = any(m in status for m in _RESOLVED_MARKS)
        target_raw = str(g.get("target_ch", "全局贯穿"))
        guns.append({
            "id": str(g.get("id", "")),
            "name": str(g.get("name", "")).strip("《》"),
            "plant_ch": g.get("plant_ch"),
            "status": status,
            "target": _parse_target(target_raw),
            "target_raw": target_raw,
            "plan": str(g.get("plan", "")),
            "resolved": resolved,
            "waiver": effective.get(str(g.get("id"))),
        })
    _IGNORED_WAIVERS[:] = ignored
    return guns


def _last_mention_chapter(workspace: Path, name: str):
    """在定稿正文中回查伏笔名（取书名号内核心词）最后出现的章号。"""
    # 取 2~4 字关键词：去掉"《》"后按非中文切，取最长的中文片段
    core = name
    m = re.findall(r"[\u4e00-\u9fa5]{2,}", name)
    if m:
        core = max(m, key=len)
    last = None
    ms_dir = workspace / "05_manuscript"
    for f in find_manuscript_files(ms_dir):
        num = chapter_number_from_name(f.name)
        if num is None:
            continue
        if core and core in f.read_text(encoding="utf-8"):
            last = num if last is None else max(last, num)
    return last, core


def schedule(workspace: Path, target_chapter: int) -> dict:
    guns = _parse_guns(workspace)
    current = target_chapter
    REMIND_LEAD, DORMANT_GAP, LONGLINE = _profile_windows(workspace)

    detonate, remind, dormant, plant_suggest, longline = [], [], [], [], []

    for g in guns:
        if g["resolved"]:
            continue
        if g.get("waiver"):
            longline.append({
                "id": g["id"], "name": g["name"], "last_mention": None,
                "waived": True, "waiver_ref": g["waiver"].get("ref", "project_bible"),
                "reason": g["waiver"]["reason"],
                "note": "已按项目圣经结构化豁免，保留证据不触发调度",
            })
            continue
        last_mention, core = _last_mention_chapter(workspace, g["name"])
        g["last_mention"] = last_mention
        g["keyword"] = core
        tgt = g["target"]

        # 1) 应引爆/回收：目标章已到或超期
        if tgt is not None:
            lo, hi = tgt
            if current >= lo:
                detonate.append({
                    "id": g["id"], "name": g["name"], "target": g["target_raw"],
                    "overdue": current > hi, "plan": g["plan"],
                    "note": (f"已超期 {current - hi} 章，务必本章/近期引爆" if current > hi
                             else f"到达预定引爆窗口 {g['target_raw']}，本章应安排引爆/回收"),
                })
                continue
            # 2) 临近引爆（lead 窗口内）：提醒复现，别让读者忘了
            if lo - current <= REMIND_LEAD:
                remind.append({
                    "id": g["id"], "name": g["name"], "target": g["target_raw"],
                    "chapters_to_detonation": lo - current,
                    "note": f"距预定引爆（{g['target_raw']}）仅剩 {lo - current} 章，本章应回唤/铺垫一次",
                })
                continue

        # 3) 沉睡伏笔：埋了很久、最近 DORMANT_GAP 章没提过，且有明确引爆窗口
        #    （长线伏笔 tgt is None 走单独的保温逻辑，不在此重复告警）
        if tgt is not None:
            ref = last_mention if last_mention is not None else (g["plant_ch"] or 0)
            if ref and current - ref >= DORMANT_GAP:
                dormant.append({
                    "id": g["id"], "name": g["name"], "plant_ch": g["plant_ch"],
                    "last_mention": last_mention,
                    "note": (f"自第 {ref} 章后 {current - ref} 章未被提及，读者可能已遗忘；"
                             "建议在近期场景自然回唤一次"),
                })

        # 4) 长线伏笔：周期提醒（周期取题材档案 longline_interval，缺省 8~12）
        if tgt is None:
            longline.append({
                "id": g["id"], "name": g["name"], "last_mention": last_mention,
                "note": f"长线/全书伏笔，建议每 {LONGLINE[0]}~{LONGLINE[1]} 章回唤一次，保持温度不断线",
            })

    result = {
        "target_chapter": f"ch_{current:03d}",
        "current_progress": current,
        "detonate_now": detonate,
        "remind_soon": remind,
        "dormant_wakeup": dormant,
        "longline_maintain": longline,
        "active_gun_count": len([g for g in guns if not g["resolved"]]),
    }
    if _IGNORED_WAIVERS:
        result["waiver_ignored"] = [
            {"gun_id": w.get("gun_id"), "reason": w.get("reason"),
             "note": "豁免缺少 exempt_until 或 long_term 字段，未生效（调度照常进行）"}
            for w in _IGNORED_WAIVERS]
    return result


def _main():
    ap = argparse.ArgumentParser(description="P2 伏笔主动调度器（为 beats-builder 排期）")
    ap.add_argument("--workspace", "-w", help="工作区路径")
    ap.add_argument("--chapter", "-c", required=True, help="目标章节，如 ch_008 或 8")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    args = ap.parse_args()

    ws = resolve_workspace(args.workspace)
    m = re.search(r"\d+", str(args.chapter))
    if not m:
        print("❌ 无法解析章节号", file=sys.stderr)
        sys.exit(2)
    target = int(m.group(0))
    sched = schedule(ws, target)

    if args.json:
        print(json.dumps(sched, ensure_ascii=False, indent=2))
        # 调度建议是咨询性输出（含超期提醒），不作为失败，始终 0；参数错误才 2
        sys.exit(0)

    print("=" * 72)
    print(f" 🪶 伏笔主动调度器 · 为 {sched['target_chapter']} Beats 排期")
    print(f" 活跃伏笔 {sched['active_gun_count']} 处 | 当前进度 第 {target} 章")
    print("=" * 72)

    if sched["detonate_now"]:
        print("\n💥【本章应引爆 / 回收】")
        for g in sched["detonate_now"]:
            tag = "🚨 超期！" if g["overdue"] else "⏰ 到期"
            print(f"  {tag} {g['id']}《{g['name']}》（{g['target']}）")
            print(f"       闭环规划：{g['plan']} ｜ {g['note']}")
    if sched["remind_soon"]:
        print("\n🔔【临近引爆 · 本章回唤铺垫】")
        for g in sched["remind_soon"]:
            print(f"  🔔 {g['id']}《{g['name']}》（{g['target']}）：{g['note']}")
    if sched["dormant_wakeup"]:
        print("\n😴【沉睡伏笔 · 需要唤醒】")
        for g in sched["dormant_wakeup"]:
            lm = f"第{g['last_mention']}章" if g["last_mention"] else f"埋设(第{g['plant_ch']}章)后从未提及"
            print(f"  😴 {g['id']}《{g['name']}》{lm}：{g['note']}")
    if sched["longline_maintain"]:
        print("\n🌌【长线伏笔 · 保温维护】")
        for g in sched["longline_maintain"]:
            lm = f"最近第{g['last_mention']}章提及" if g["last_mention"] else "尚未在正文提及"
            print(f"  🌌 {g['id']}《{g['name']}》{lm}：{g['note']}")

    if not (sched["detonate_now"] or sched["remind_soon"] or sched["dormant_wakeup"]):
        print("\n✅ 当前无急需调度的伏笔，可安心推进新情节。")
    print("=" * 72)

    # 咨询性调度建议，不作为退出失败
    sys.exit(0)


if __name__ == "__main__":
    _main()
