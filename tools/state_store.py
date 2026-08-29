# -*- coding: utf-8 -*-
"""
Unified State Store (state_store.py)
=======================================
JSON is the single source of truth (SSOT) for all machine-readable state:
  - current_state.json
  - chekhov_guns.json
  - misunderstandings.json
  - character_growth_arcs.json
  - timeline.json
  - economy_ledger.json (already JSON, managed by state_apply.apply_transactions)

Markdown files (current_state.md, chekhov_guns.md, ...) are **auto-generated
read-only views** rendered from the JSON after every mutation. They exist for
human/LLM readability only; no tool should parse them for truth.

This module replaces the old regex/table parsing of Markdown state files with
deterministic JSON manipulation, eliminating an entire class of
column-misalignment / placeholder / split("|") bugs.
"""

import json
import os
import re
import contextlib
import time
from pathlib import Path

from novel_utils import atomic_write_text

# ---------------------------------------------------------------------------
# File names
# ---------------------------------------------------------------------------
STATE_DIR = "04_timeline_and_state"

CURRENT_STATE = "current_state"
GUNS = "chekhov_guns"
MISUNDERSTANDINGS = "misunderstandings"
GROWTH_ARCS = "character_growth_arcs"
TIMELINE = "timeline"
ECONOMY = "economy_ledger"

JSON_FILES = {
    CURRENT_STATE: "current_state.json",
    GUNS: "chekhov_guns.json",
    MISUNDERSTANDINGS: "misunderstandings.json",
    GROWTH_ARCS: "character_growth_arcs.json",
    TIMELINE: "timeline.json",
    ECONOMY: "economy_ledger.json",
}

# Markdown view names (kept for human readability / backward compat with docs)
MD_VIEWS = {
    CURRENT_STATE: "current_state.md",
    GUNS: "chekhov_guns.md",
    MISUNDERSTANDINGS: "misunderstandings.md",
    GROWTH_ARCS: "character_growth_arcs.md",
    TIMELINE: "timeline.md",
}

# Status enumerations
GUN_PLANTED = "Planted"
GUN_REMINDED = "Reminded"
GUN_RESOLVED = "Resolved"

MIS_ACTIVE = "Active"
MIS_RESOLVED = "Resolved"

# ---------------------------------------------------------------------------
# Default / empty state
# ---------------------------------------------------------------------------

def default_current_state() -> dict:
    return {
        "time": "",
        "location": "",
        "present_characters": [],
        "power_level": "",
        "abilities": "",
        "injury": "",
        "assets": "",
        "equipment": "",
        "situation": "",
    }


def default_guns() -> dict:
    return {"guns": []}


def default_misunderstandings() -> dict:
    return {"misunderstandings": []}


def default_growth_arcs() -> dict:
    return {"arcs": []}


def default_timeline() -> dict:
    return {"events": []}


def default_economy() -> dict:
    return {
        "currency_name": "多资源池复式记账台账",
        "base_unit": "标准最小单位",
        "resource_pools": {
            "standard_currency": {
                "name": "主法定货币",
                "unit": "两/点",
                "initial": 0,
                "current": 0,
            },
            "vital_points": {
                "name": "特殊点数/能量/贡献分",
                "unit": "点/分",
                "initial": 0,
                "current": 0,
            },
        },
        "transactions": [
            {
                "chapter": "ch_001",
                "resource": "standard_currency",
                "type": "opening_balance",
                "delta": 0,
                "subject": "初始随身资产",
                "counterparty": "初始基线",
                "balance_after": 0,
                "note": "开局主角初始资产",
            }
        ],
    }


DEFAULTS = {
    CURRENT_STATE: default_current_state,
    GUNS: default_guns,
    MISUNDERSTANDINGS: default_misunderstandings,
    GROWTH_ARCS: default_growth_arcs,
    TIMELINE: default_timeline,
    ECONOMY: default_economy,
}


# ---------------------------------------------------------------------------
# JSON I/O (atomic; Markdown views are read-only and never parsed as truth)
# ---------------------------------------------------------------------------

def state_dir(workspace: Path) -> Path:
    return workspace / STATE_DIR


def _json_path(workspace: Path, key: str) -> Path:
    return state_dir(workspace) / JSON_FILES[key]


def load_json(workspace: Path, key: str) -> dict:
    """Load a state JSON file. Returns a fresh copy of the default if absent."""
    p = _json_path(workspace, key)
    if p.exists():
        try:
            # utf-8-sig tolerates an optional BOM from Windows editors
            data = json.loads(p.read_text(encoding="utf-8-sig"))
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, OSError) as exc:
            # Corrupt SSOT must never silently turn into a fresh default.
            raise ValueError(f"状态文件损坏或不可读: {p.name}: {exc}") from exc
    return DEFAULTS[key]()


def save_json(workspace: Path, key: str, data: dict) -> None:
    atomic_write_text(_json_path(workspace, key),
                      json.dumps(data, ensure_ascii=False, indent=2) + "\n")


# ---------------------------------------------------------------------------
# Cross-platform file lock (for concurrent sync safety)
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def file_lock(workspace: Path, name: str = ".state.lock", timeout: float = 30.0):
    """Exclusive lock across processes, with a bounded wait on Windows/POSIX."""
    lock_path = state_dir(workspace) / name
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(lock_path, "a+")
    try:
        if os.name == "nt":
            import msvcrt
            # Lock 1 byte at offset 0; blocks until acquired
            fh.seek(0)
            deadline = time.monotonic() + timeout
            while True:
                try:
                    msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError(f"state lock timeout after {timeout:g}s")
                    time.sleep(0.05)
        else:
            import fcntl
            deadline = time.monotonic() + timeout
            while True:
                try:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError(f"state lock timeout after {timeout:g}s")
                    time.sleep(0.05)
        try:
            yield
        finally:
            fh.flush()
            try:
                if os.name == "nt":
                    fh.seek(0)
                    msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
    finally:
        fh.close()


# ---------------------------------------------------------------------------
# Markdown rendering (read-only views)
# ---------------------------------------------------------------------------

_AUTOGEN_HEADER = (
    "<!-- AUTO-GENERATED FROM JSON SOURCE — DO NOT EDIT THIS FILE. -->\n"
    "<!-- The source of truth is the corresponding .json file in this directory. -->\n"
    "<!-- This view is regenerated automatically after every state sync. -->\n\n"
)


def _md_table(headers: list, rows: list) -> str:
    lines = []
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join([":---"] * len(headers)) + " |")
    for r in rows:
        lines.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(lines)


def render_current_state_md(data: dict) -> str:
    pcs = data.get("present_characters") or []
    pc_lines = "\n".join(
        f"  - {c}" if isinstance(c, str)
        else f"  - {c.get('name', '')}（{c.get('state', '')}）"
        for c in pcs
    )
    if not pc_lines:
        pc_lines = "  - （待同步）"

    lines = [
        _AUTOGEN_HEADER + "# 实时状态机 (Current State)",
        "",
        f"- **当前时间节点**：{data.get('time') or '（待同步）'}",
        f"- **当前故事地点**：{data.get('location') or '（待同步）'}",
        "- **在场核心角色**：",
        pc_lines,
        "- **主角生理与战力状态**：",
        f"  - **当前能力层级**：{data.get('power_level') or '（待同步）'}",
        f"  - **特殊机制/词条/能力**：{data.get('abilities') or '（待同步）'}",
        f"  - **生理负荷/暗伤**：{data.get('injury') or '（待同步）'}",
        "- **持有核心资产与道具**：",
        f"  - **随身核心信物/关键装备**：{data.get('equipment') or '（待同步）'}",
        f"  - **随身流动资金**：{data.get('assets') or '（待同步）'}",
        "- **当前博弈局势与下一章引子**：",
        f"  - {data.get('situation') or '（待同步）'}",
        "",
    ]
    return "\n".join(lines)


def render_guns_md(data: dict) -> str:
    rows = []
    for g in data.get("guns", []):
        rows.append([
            f"**{g.get('id', '')}**",
            f"《{g.get('name', '')}》",
            f"第 {g.get('plant_ch', '?')} 章",
            f"**{g.get('status', GUN_PLANTED)}**",
            g.get("target_ch", "全局贯穿"),
            g.get("plan", "待补充闭环规划"),
        ])
    if not rows:
        rows = ["（尚无伏笔登记）"]
    return (_AUTOGEN_HEADER
            + "# 契诃夫之枪 (伏笔与悬念台账)\n\n"
            + _md_table(
                ["伏笔 ID", "伏笔名称 / 关键物件", "埋设章节", "当前状态",
                 "预定引爆章节", "闭环兑现规划与核心张力"],
                rows if rows != ["（尚无伏笔登记）"] else [["—"] * 6])
            + "\n")


def render_misunderstandings_md(data: dict) -> str:
    rows = []
    for m in data.get("misunderstandings", []):
        rows.append([
            f"**{m.get('id', '')}**",
            m.get("parties", ""),
            m.get("content", ""),
            m.get("truth", ""),
            f"**{m.get('level', '1 级 (潜伏发酵)')}**",
            m.get("target_ch", ""),
        ])
    if not rows:
        rows = [["—"] * 6]
    return (_AUTOGEN_HEADER
            + "# 误会与信息差台账 (Misunderstandings Ledger)\n\n"
            + _md_table(
                ["ID", "误会主体与对象", "误会核心内容", "现实真相",
                 "发酵等级", "计划引爆章节"],
                rows)
            + "\n")


def render_growth_arcs_md(data: dict) -> str:
    rows = []
    for a in data.get("arcs", []):
        rows.append([
            f"**{a.get('name', '')}**",
            a.get("baseline", "初始基线"),
            f"**{a.get('stage', '')}**" if a.get("stage") else "待定",
            a.get("inciting_event", "待记录"),
            a.get("ultimate", "（长线成长）"),
        ])
    if not rows:
        rows = [["—"] * 5]
    return (_AUTOGEN_HEADER
            + "# 核心人物动态成长与心智演进总台账 (Character Mindset Growth Arcs)\n\n"
            + _md_table(
                ["角色姓名", "初始基线", "当前阶段与防御机制",
                 "最近跃迁事件 (Inciting Event)", "终极成长方向"],
                rows)
            + "\n")


def render_timeline_md(data: dict) -> str:
    lines = [_AUTOGEN_HEADER + "# 故事编年史 (Timeline Log)", ""]
    events = data.get("events", [])
    if not events:
        lines.append("- （尚无重大事件记录）")
    else:
        for e in events:
            t = e.get("time", "未标注时间")
            ev = e.get("event", "")
            lines.append(f"- **【{t}】**：{ev}")
    lines.append("")
    return "\n".join(lines)


_RENDERERS = {
    CURRENT_STATE: render_current_state_md,
    GUNS: render_guns_md,
    MISUNDERSTANDINGS: render_misunderstandings_md,
    GROWTH_ARCS: render_growth_arcs_md,
    TIMELINE: render_timeline_md,
}


def render_markdown(workspace: Path, key: str) -> None:
    """Render one JSON state file to its Markdown read-only view."""
    if key not in _RENDERERS:
        return
    data = load_json(workspace, key)
    md = _RENDERERS[key](data)
    atomic_write_text(state_dir(workspace) / MD_VIEWS[key], md)


def render_all_markdown(workspace: Path) -> None:
    """Re-render all Markdown views from JSON sources."""
    for key in _RENDERERS:
        if _json_path(workspace, key).exists():
            render_markdown(workspace, key)


# ---------------------------------------------------------------------------
# ID helpers
# ---------------------------------------------------------------------------

def _norm_id(cell: str) -> str:
    return re.sub(r"[*_`\s]", "", cell or "")


def _next_id(items: list, id_key: str, prefix: str, width: int = 3) -> str:
    maxn = 0
    for it in items:
        m = re.search(prefix + r"[-_]?(\d+)", _norm_id(str(it.get(id_key, ""))))
        if m:
            maxn = max(maxn, int(m.group(1)))
    return f"{prefix}-{maxn + 1:0{width}d}"


def _find_item_index(items: list, id_key: str, target_id: str) -> int:
    t = _norm_id(target_id)
    for i, it in enumerate(items):
        if _norm_id(str(it.get(id_key, ""))) == t:
            return i
    return -1


# ---------------------------------------------------------------------------
# Merge operations (migrated from state_apply.py, now JSON-native)
# ---------------------------------------------------------------------------

def merge_current_state(workspace: Path, cs: dict, report: dict) -> None:
    if not cs:
        return
    data = load_json(workspace, CURRENT_STATE)
    field_map = {
        "time": "time",
        "location": "location",
        "power_level": "power_level",
        "realm": "power_level",  # backward compat: realm -> power_level
        "abilities": "abilities",
        "injury": "injury",
        "assets": "assets",
        "equipment": "equipment",
        "situation": "situation",
    }
    for prop_key, data_key in field_map.items():
        if cs.get(prop_key):
            data[data_key] = str(cs[prop_key])
            report["updated"].append(f"📍 状态机 [{data_key}] 已更新")
    if cs.get("present_characters"):
        data["present_characters"] = cs["present_characters"]
        report["updated"].append(
            f"📍 在场角色更新为 {len(cs['present_characters'])} 人")
    save_json(workspace, CURRENT_STATE, data)
    render_markdown(workspace, CURRENT_STATE)


def merge_guns(workspace: Path, guns: list, chapter: str, report: dict) -> None:
    if not guns:
        return
    data = load_json(workspace, GUNS)
    items = data.setdefault("guns", [])
    ch_num = re.search(r"(\d+)", chapter or "")
    here_ch = int(ch_num.group(1)) if ch_num else 0

    for g in guns:
        action = (g.get("action") or "plant").lower()
        gid = _norm_id(g.get("id", ""))
        if action == "plant":
            if not gid:
                gid = _next_id(items, "id", "GUN")
            if _find_item_index(items, "id", gid) >= 0:
                report["warnings"].append(f"伏笔 {gid} 已存在，plant 被忽略")
                continue
            target = g.get("target_ch", "全局贯穿")
            target_cell = f"第 {target} 章" if isinstance(target, int) else str(target)
            items.append({
                "id": gid,
                "name": g.get("name", "未命名伏笔"),
                "plant_ch": g.get("plant_ch", here_ch) or here_ch,
                "status": GUN_PLANTED,
                "target_ch": target_cell,
                "plan": g.get("plan", "待补充闭环规划"),
            })
            report["updated"].append(
                f"🕸️ 新伏笔 {gid}《{g.get('name','')}》（计划 {target_cell} 引爆）")
        else:
            idx = _find_item_index(items, "id", gid)
            if idx < 0:
                report["warnings"].append(f"伏笔 {gid} 不存在，无法 {action}")
                continue
            if action == "resolve":
                items[idx]["status"] = GUN_RESOLVED
                report["updated"].append(f"✅ 伏笔 {gid} 已回收/引爆")
            elif action == "update":
                if g.get("status"):
                    items[idx]["status"] = str(g["status"])
                if g.get("target_ch") is not None:
                    t = g["target_ch"]
                    items[idx]["target_ch"] = (
                        f"第 {t} 章" if isinstance(t, int) else str(t))
                if g.get("plan"):
                    items[idx]["plan"] = g["plan"]
                report["updated"].append(
                    f"🔁 伏笔 {gid} 状态更新为 {items[idx].get('status')}")
            elif action == "remind":
                items[idx]["status"] = GUN_REMINDED
                report["updated"].append(f"🔔 伏笔 {gid} 已回唤/激化")
    save_json(workspace, GUNS, data)
    render_markdown(workspace, GUNS)


def merge_misunderstandings(workspace: Path, items_in: list, chapter: str,
                            report: dict) -> None:
    if not items_in:
        return
    data = load_json(workspace, MISUNDERSTANDINGS)
    items = data.setdefault("misunderstandings", [])
    ch_num = re.search(r"(\d+)", chapter or "")
    here_ch = int(ch_num.group(1)) if ch_num else 0

    for m in items_in:
        action = (m.get("action") or "plant").lower()
        mid = _norm_id(m.get("id", ""))
        if action == "plant":
            if not mid:
                mid = _next_id(items, "id", "MIS")
            if _find_item_index(items, "id", mid) >= 0:
                report["warnings"].append(f"误会 {mid} 已存在，plant 被忽略")
                continue
            target = m.get("target_ch", here_ch + 3)
            target_cell = f"第 {target} 章" if isinstance(target, int) else str(target)
            items.append({
                "id": mid,
                "parties": m.get("parties", ""),
                "content": m.get("content", ""),
                "truth": m.get("truth", ""),
                "level": m.get("level", "1 级 (潜伏发酵)"),
                "target_ch": target_cell,
                "status": MIS_ACTIVE,
            })
            report["updated"].append(f"🎭 新误会 {mid}：{m.get('content','')}")
        else:
            idx = _find_item_index(items, "id", mid)
            if idx < 0:
                report["warnings"].append(f"误会 {mid} 不存在，无法 {action}")
                continue
            if action == "resolve":
                items[idx]["status"] = MIS_RESOLVED
                report["updated"].append(f"✅ 误会 {mid} 已澄清")
            elif action == "update":
                if m.get("level"):
                    items[idx]["level"] = m["level"]
                if m.get("content"):
                    items[idx]["content"] = m["content"]
                report["updated"].append(f"🔁 误会 {mid} 已更新")
    save_json(workspace, MISUNDERSTANDINGS, data)
    render_markdown(workspace, MISUNDERSTANDINGS)


def merge_growth_arcs(workspace: Path, arcs: list, chapter: str,
                      report: dict) -> None:
    if not arcs:
        return
    data = load_json(workspace, GROWTH_ARCS)
    items = data.setdefault("arcs", [])

    for a in arcs:
        name = (a.get("name") or "").strip()
        if not name:
            report["warnings"].append("成长弧线缺少 name，已跳过")
            continue
        idx = -1
        for i, it in enumerate(items):
            if _norm_id(it.get("name", "")) == _norm_id(name):
                idx = i
                break
        stage = a.get("stage", "")
        if idx < 0:
            new_arc = {
                "name": name,
                "baseline": a.get("baseline", stage or "初始基线"),
                "stage": stage,
                "inciting_event": a.get("inciting_event", "待记录"),
                "strategy": a.get("strategy", ""),
                "ultimate": a.get("ultimate", "（长线成长）"),
            }
            if a.get("strategy"):
                new_arc["strategy_history"] = [{
                    "chapter": chapter, "strategy": a["strategy"],
                }]
            items.append(new_arc)
            report["updated"].append(f"🧠 新建心智台账：{name} → {stage}")
        else:
            if stage:
                items[idx]["stage"] = stage
            if a.get("inciting_event"):
                items[idx]["inciting_event"] = a["inciting_event"]
            if a.get("strategy"):
                # 覆盖式：strategy 只保留「当前」策略，历史按章归档到 strategy_history，
                # 避免每章用「；」无上限追加、字段退化成流水账（可读性优先）。
                items[idx]["strategy"] = a["strategy"]
                hist = items[idx].setdefault("strategy_history", [])
                hist.append({"chapter": chapter, "strategy": a["strategy"]})
            if a.get("baseline"):
                items[idx]["baseline"] = a["baseline"]
            if a.get("ultimate"):
                items[idx]["ultimate"] = a["ultimate"]
            report["updated"].append(f"🧠 {name} 心智阶段 → {stage}")
    save_json(workspace, GROWTH_ARCS, data)
    render_markdown(workspace, GROWTH_ARCS)


def merge_timeline(workspace: Path, entries: list, report: dict) -> None:
    if not entries:
        return
    data = load_json(workspace, TIMELINE)
    events = data.setdefault("events", [])
    existing_keys = {
        re.sub(r"\s", "", f"{e.get('time','')}|{e.get('event','')}")
        for e in events
    }
    added = 0
    for e in entries:
        event = (e.get("event") or "").strip()
        if not event:
            continue
        time_lbl = e.get("time", "未标注时间")
        key = re.sub(r"\s", "", f"{time_lbl}|{event}")
        if key in existing_keys:
            continue
        events.append({"time": time_lbl, "event": event})
        existing_keys.add(key)
        added += 1
    if added:
        report["updated"].append(f"📜 编年史追加 {added} 条事件")
    save_json(workspace, TIMELINE, data)
    render_markdown(workspace, TIMELINE)


# ---------------------------------------------------------------------------
# Workspace initialization (JSON seed files)
# ---------------------------------------------------------------------------

def init_state_files(workspace: Path) -> None:
    """Create all JSON state files with defaults and render Markdown views."""
    sd = state_dir(workspace)
    sd.mkdir(parents=True, exist_ok=True)
    for key, default_fn in DEFAULTS.items():
        p = _json_path(workspace, key)
        if not p.exists():
            save_json(workspace, key, default_fn())
    # Render all Markdown views
    render_all_markdown(workspace)
    # state_inbox dirs
    (sd / "state_inbox" / "processed").mkdir(parents=True, exist_ok=True)
    (sd / "state_inbox" / "failed").mkdir(parents=True, exist_ok=True)
    # snapshots dir
    (sd / "snapshots").mkdir(parents=True, exist_ok=True)
