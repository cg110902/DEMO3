# -*- coding: utf-8 -*-
"""
Agent-First Dynamic Context Packager
Packages all required context for drafting a chapter in a single call:
- Current State Machine (current_state.md)
- Active Chekhov Guns & Misunderstandings
- Previous Chapter Finalized Ending (Emotional warmth & voice continuity)
- Target Chapter Beats Outline
- Relevant Character Profile Cards
Saves 5-6 separate tool view roundtrips and protects context window hygiene.
Usage:
    python tools/package_context.py -c ch_004
    python tools/package_context.py -c ch_004 --json
"""

import sys
import re
import logging
import json
import argparse
from pathlib import Path

_tools_dir = Path(__file__).resolve().parent
if str(_tools_dir) not in sys.path:
    sys.path.insert(0, str(_tools_dir))

from novel_utils import (
    resolve_workspace, natural_chapter_sort_key, find_manuscript_files,
    reconfigure_utf8, file_matches_chapter, chapter_token_to_num,
    load_character_registry
)
logger = logging.getLogger("novel_studio.package_context")

reconfigure_utf8()

# ---------------------------------------------------------------------------
# Token 预算模式（P1）
# ---------------------------------------------------------------------------
def _est_tokens(text: str) -> int:
    """粗略 token 估算：中文约 1 字 ≈ 1 token，ASCII 约 4 字符 ≈ 1 token。"""
    if not text:
        return 0
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    other = len(text) - cjk
    return cjk + max(1, other // 4)


def _apply_budget(package: dict, budget: int) -> dict:
    """按区块优先级把总 token 控制在 budget 内，返回带 budget_report 的 package。

    优先级（越靠前越不可裁）：
      0 target_beats（本章必须写什么）
      1 high_priority_story_alerts / cross_chapter_warnings（硬性预警）
      2 current_state / resource_pools（当前真值）
      3 synopsis_spine（全书梗概脊柱，防重复）
      4 previous_chapter_ending（衔接余温）
      5 active_guns / active_misunderstandings
      6 character_growth_arcs / librarian_recall（长，可压缩）
      7 relevant_character_profiles（最长，最先被裁）

    预算耗尽（剩余 room≤0）时的兜底：细纲/预警仍绝不裁；current_state（状态真值）
    整块保留；梗概脊柱为防重复刚需，无论预算多紧都至少保留"全书一句话 + 最近一章"，
    预算越紧丢的越是更早章节、绝不返回空串；上一章余温保留末段最小锚点；其余低优先级
    区块清空。被裁内容只是不进本次打包、原文件完好，budget_report 逐项记录并给出
    找回提示（hint），可按需直读原文件或调高预算重跑。
    """
    report = {"budget_tokens": budget, "sections": []}

    def _log(section, kept, dropped_tokens, note=""):
        report["sections"].append({
            "section": section, "kept_tokens": kept,
            "dropped_tokens": dropped_tokens, "note": note,
        })

    used = 0

    def _room():
        return budget - used

    def _fit_text(text: str, room: int, tail: bool = True, factor: float = 1.6) -> str:
        """截取不超过 room token 的片段（tail=True 取尾部，用于余温衔接）。

        先按 factor 粗取字符数（ASCII 混排时 token<字符数），再用 _est_tokens
        实测收缩到预算内——修复旧版 `room*2` 固定倍率在中文正文（1字≈1token）下
        必然超支 ~2 倍的问题。
        """
        if not text or room <= 0:
            return ""
        n = min(len(text), int(room * factor))
        keep = text[-n:] if tail else text[:n]
        est = _est_tokens(keep)
        while keep and est > room:
            n = max(1, int(n * room / est))
            keep = text[-n:] if tail else text[:n]
            est = _est_tokens(keep)
        return keep

    # --- 不可裁剪的核心：beats + 预警（超限也保留，只记录） ---
    core_text = package.get("target_beats", "")
    ct = _est_tokens(core_text)
    used += ct
    _log("target_beats", ct, 0, "本章细纲，不裁剪")

    alerts = list(package.get("high_priority_story_alerts", []))
    at = _est_tokens("\n".join(alerts))
    used += at
    _log("story_alerts", at, 0, "硬性预警，不裁剪")

    # --- current_state：状态真值，整块保留但可尾部裁剪 ---
    cs = package.get("current_state", "")
    cst = _est_tokens(cs)
    room = _room()
    if cst > room > 0:
        # 按行保留到预算
        lines = cs.splitlines()
        kept_lines, klen = [], 0
        for ln in lines:
            lt = _est_tokens(ln)
            if klen + lt > room:
                break
            kept_lines.append(ln)
            klen += lt
        package["current_state"] = "\n".join(kept_lines)
        _log("current_state", klen, cst - klen, "超预算，按行截断")
        used += klen
    elif room <= 0 and cst > 0:
        # 预算已被不可裁核心（细纲+预警）耗尽：状态真值体积小且是因果一致性的
        # 关键依据，整块保留并在报告中如实记录（绝不静默丢弃）。
        used += cst
        _log("current_state", cst, 0, "预算已耗尽，仍整块保留状态真值（体积小、防吃设定）")
    else:
        used += cst
        _log("current_state", cst, 0)

    # --- resource_pools 很短，全留 ---
    rp = package.get("resource_pools", {})
    rpt = _est_tokens(json.dumps(rp, ensure_ascii=False))
    used += rpt
    _log("resource_pools", rpt, 0)

    # --- story_bible：全书最高设定锚点，预算紧张时按行保留头部总纲 ---
    sb = package.get("story_bible", "")
    sbt = _est_tokens(sb)
    room = _room()
    if sbt > room > 0:
        lines = sb.splitlines()
        kept_lines, klen = [], 0
        for ln in lines:
            lt = _est_tokens(ln)
            if klen + lt > room:
                break
            kept_lines.append(ln)
            klen += lt
        package["story_bible"] = "\n".join(kept_lines)
        used += klen
        _log("story_bible", klen, sbt - klen, "预算紧张，项目圣经按行保留头部（原文件仍可读取）")
    else:
        used += sbt
        _log("story_bible", sbt, 0, "项目圣经，整块保留（防吃设定）")

    # --- 梗概脊柱：防重复刚需，始终至少保留最近一章，预算紧才丢旧章，绝不出空 ---
    spine = package.get("synopsis_spine", "")
    spt = _est_tokens(spine)
    room = _room()
    if not spine:
        _log("synopsis_spine", 0, 0)
    else:
        lines = spine.splitlines()
        head = [lines[0]] if lines[0].startswith("全书") else []
        body = [l for l in lines if l not in head]
        keep_body, klen = [], _est_tokens("\n".join(head))
        for i, ln in enumerate(reversed(body)):
            lt = _est_tokens(ln)
            # 最近一章（i==0）无条件保留，守住防重复下限；其余仅当预算允许
            if i != 0 and klen + lt > room:
                break
            keep_body.append(ln)
            klen += lt
        package["synopsis_spine"] = "\n".join(head + list(reversed(keep_body)))
        dropped = spt - klen
        _log("synopsis_spine", klen, dropped,
             "预算紧张：保留最近章节梗概（防重复），丢弃更早章节" if dropped else "")
        used += klen

    # --- previous_chapter_ending：可裁剪长度 ---
    pe = package.get("previous_chapter_ending", "")
    pet = _est_tokens(pe)
    room = _room()
    if pet > room > 0:
        # 不设最小 room 门槛：历史版本的 room>80 守卫会让"预算更小反而整块
        # 保留"（反单调），_fit_text 对极小 room 已安全。
        keep = _fit_text(pe, room, tail=True)
        package["previous_chapter_ending"] = keep
        _log("previous_chapter_ending", _est_tokens(keep), pet - _est_tokens(keep), "超预算，缩短余温")
        used += _est_tokens(keep)
    elif room <= 0 and pe:
        # 预算耗尽：保留上一章结尾最后一小段，守住视角/情绪衔接的最小锚点
        keep = pe[-240:]
        package["previous_chapter_ending"] = keep
        _log("previous_chapter_ending", _est_tokens(keep), pet - _est_tokens(keep), "预算耗尽，仅保留末尾最小余温")
        used += _est_tokens(keep)
    else:
        used += pet
        _log("previous_chapter_ending", pet, 0)

    # --- active guns / misunderstandings：逐条裁 ---
    for key in ("active_chekhov_guns", "active_misunderstandings"):
        items = package.get(key, [])
        room = _room()
        kept, klen = [], 0
        for it in items:
            it_t = _est_tokens(it)
            # room<=0 时同样截断：修复旧逻辑"预算越小反而保留越多"的反单调问题。
            # （到期/超期伏笔已注入 high_priority_story_alerts，属于绝不裁的核心，不受此影响）
            if klen + it_t > room:
                break
            kept.append(it)
            klen += it_t
        dropped = len(items) - len(kept)
        package[key] = kept
        _log(key, klen, _est_tokens("\n".join(items)) - klen,
             f"裁掉 {dropped} 条" if dropped else "")
        used += klen

    # --- growth arcs：整块可尾部裁 ---
    ga = package.get("character_growth_arcs", "")
    gat = _est_tokens(ga)
    room = _room()
    if gat > room > 0:
        keep = _fit_text(ga, room, tail=False)
        package["character_growth_arcs"] = keep
        _log("character_growth_arcs", _est_tokens(keep), gat - _est_tokens(keep), "超预算截断")
        used += _est_tokens(keep)
    elif room <= 0 and ga:
        package["character_growth_arcs"] = ""
        _log("character_growth_arcs", 0, gat, "预算耗尽，整块裁剪（台账原文件仍可按需读取）")
    else:
        used += gat
        _log("character_growth_arcs", gat, 0)

    # --- world_settings / volume_outline：设定与卷纲，超预算保留头部总纲 ---
    for key in ("world_settings", "volume_outline"):
        block = package.get(key, "")
        bt = _est_tokens(block)
        room = _room()
        if bt > room > 0:
            keep = _fit_text(block, room, tail=False)
            package[key] = keep
            _log(key, _est_tokens(keep), bt - _est_tokens(keep), "超预算，保留头部（原文件完好）")
            used += _est_tokens(keep)
        elif room <= 0 and block:
            package[key] = ""
            _log(key, 0, bt, "预算耗尽，整块裁剪（原文件仍可按需读取）")
        else:
            used += bt
            _log(key, bt, 0)

    # --- librarian_recall：已按 score 排序，逐条保留 ---
    rec = package.get("librarian_recall", [])
    room = _room()
    kept, klen = [], 0
    for h in rec:
        ht = _est_tokens(h.get("snippet", ""))
        if klen + ht > room:
            break
        kept.append(h)
        klen += ht
    dropped = len(rec) - len(kept)
    package["librarian_recall"] = kept
    _log("librarian_recall", klen,
         sum(_est_tokens(h.get("snippet", "")) for h in rec) - klen,
         f"裁掉 {dropped} 条召回" if dropped else "")
    used += klen

    # --- character profiles：最长，最后裁，按是否主角/被提及排序 ---
    profiles = package.get("relevant_character_profiles", {})
    room = _room()
    if room <= 0:
        dropped_names = list(profiles.keys())
        package["relevant_character_profiles"] = {}
        _log("relevant_character_profiles", 0,
             sum(_est_tokens(v) for v in profiles.values()),
             f"预算用尽，裁掉人物卡: {', '.join(dropped_names)}")
    else:
        # 主角优先（protagonist / 主角）
        def _prio(item):
            name, txt = item
            return 0 if ("主角" in txt or "protagonist" in name.lower()) else 1
        kept_profiles, klen = {}, 0
        dropped_names = []
        for name, txt in sorted(profiles.items(), key=_prio):
            tt = _est_tokens(txt)
            if klen + tt > room:
                dropped_names.append(name)
                continue
            kept_profiles[name] = txt
            klen += tt
        package["relevant_character_profiles"] = kept_profiles
        _log("relevant_character_profiles", klen,
             sum(_est_tokens(v) for v in profiles.values()) - klen,
             f"裁掉人物卡: {', '.join(dropped_names)}" if dropped_names else "")
        used += klen

    # --- 不参与裁剪但必须计入预算的整块保留区 ---
    # （cross_chapter_warnings/foreshadow_schedule/genre_profile/high_priority_story_alerts
    #   装配进 package 后历史版本不计数、不进 budget_report，导致 within_budget 严重低估）
    for key in ("high_priority_story_alerts", "cross_chapter_warnings",
                "foreshadow_schedule", "genre_profile"):
        block = package.get(key)
        if not block:
            continue
        if not isinstance(block, str):
            block = json.dumps(block, ensure_ascii=False)
        bt = _est_tokens(block)
        used += bt
        _log(key, bt, 0, "整块保留，不参与裁剪")

    report["total_kept_tokens"] = used
    report["within_budget"] = used <= budget
    if any(s["dropped_tokens"] for s in report["sections"]) or not report["within_budget"]:
        report["hint"] = (
            "被裁剪的内容并未删除，仍完整保留在工作区对应文件中"
            "（人物卡在 02_characters/profiles/、心智台账与伏笔池在 04_timeline_and_state/）；"
            "如本章确有需要，可直接读取原文件、调高 --budget，或去掉 --budget 取全量。"
        )
    package["budget_report"] = report
    return package


def package_context_for_chapter(target_chapter_str: str, workspace_path=None, as_json=False,
                                budget: int = 0, print_output: bool = True):
    """打包单章创作语境。

    budget>0 时启用「token 预算模式」：所有可裁剪区块按相关性排序后截断到预算内，
    并在 package['budget_report'] 里记录裁掉了什么（借鉴 Novel-OS context_pack）。
    budget=0（默认）保持原有全量行为，向后兼容。
    """
    workspace_dir = resolve_workspace(workspace_path)

    package = {
        "workspace": workspace_dir.name,
        "target_chapter": target_chapter_str or "next_chapter",
        "current_state": "",
        "character_growth_arcs": "",
        "active_chekhov_guns": [],
        "active_misunderstandings": [],
        "previous_chapter_ending": "",
        "target_beats": "",
        "relevant_character_profiles": {},
        "synopsis_spine": "",
        "librarian_recall": [],
        "story_bible": "",
        "world_settings": "",
        "volume_outline": "",
        "cross_chapter_warnings": [],
    }

    # 1. Load Current State（JSON SSOT，回退到 Markdown 只读视图）
    state_json = workspace_dir / "04_timeline_and_state" / "current_state.json"
    state_md = workspace_dir / "04_timeline_and_state" / "current_state.md"
    if state_json.exists():
        try:
            cs = json.loads(state_json.read_text(encoding="utf-8"))
            # Render a compact human-readable block for the LLM pack
            pcs = cs.get("present_characters") or []
            pc_lines = "\n".join(
                f"  - {c}" if isinstance(c, str)
                else f"  - {c.get('name','')}（{c.get('state','')}）" for c in pcs)
            package["current_state"] = (
                f"时间：{cs.get('time','')}\n"
                f"地点：{cs.get('location','')}\n"
                f"能力层级：{cs.get('power_level','')}\n"
                f"能力/词条：{cs.get('abilities','')}\n"
                f"伤势/负荷：{cs.get('injury','')}\n"
                f"装备：{cs.get('equipment','')}\n"
                f"资产：{cs.get('assets','')}\n"
                f"在场角色：\n{pc_lines if pc_lines else '  - （待同步）'}\n"
                f"局势：{cs.get('situation','')}"
            )
        except Exception:
            if state_md.exists():
                package["current_state"] = state_md.read_text(encoding="utf-8").strip()
    elif state_md.exists():
        package["current_state"] = state_md.read_text(encoding="utf-8").strip()

    # 1.5 Load Character Growth Arcs（JSON SSOT）
    growth_json = workspace_dir / "04_timeline_and_state" / "character_growth_arcs.json"
    growth_md = workspace_dir / "04_timeline_and_state" / "character_growth_arcs.md"
    if growth_json.exists():
        try:
            ga = json.loads(growth_json.read_text(encoding="utf-8"))
            lines = []
            for a in ga.get("arcs", []):
                lines.append(
                    f"- {a.get('name','')}：{a.get('stage','')} "
                    f"（跃迁事件：{a.get('inciting_event','')}；策略：{a.get('strategy','')}）")
            package["character_growth_arcs"] = "\n".join(lines)
        except Exception:
            if growth_md.exists():
                package["character_growth_arcs"] = growth_md.read_text(encoding="utf-8").strip()
    elif growth_md.exists():
        package["character_growth_arcs"] = growth_md.read_text(encoding="utf-8").strip()

    # 1.6 Load Quantitative Resource Pools & Economy Ledger
    package["resource_pools"] = {}
    econ_file = workspace_dir / "04_timeline_and_state" / "economy_ledger.json"
    if econ_file.exists():
        try:
            econ_data = json.loads(econ_file.read_text(encoding="utf-8"))
            if "resource_pools" in econ_data:
                package["resource_pools"] = econ_data["resource_pools"]
            elif "current_balance" in econ_data:
                package["resource_pools"] = {
                    "currency": {
                        "name": "货币结余",
                        "unit": "单位",
                        "current": econ_data.get("current_balance", 0)
                    }
                }
        except Exception as e:
            logger.warning("economy_ledger.json 解析失败，资源池信息不可用: %s", e)

    # 2. Load Active Guns（JSON SSOT）
    guns_json = workspace_dir / "04_timeline_and_state" / "chekhov_guns.json"
    if guns_json.exists():
        try:
            gd = json.loads(guns_json.read_text(encoding="utf-8"))
            for g in gd.get("guns", []):
                status = str(g.get("status", ""))
                if any(k in status for k in ("Planted", "Reminded", "Active")):
                    package["active_chekhov_guns"].append(
                        f"| {g.get('id','')} | {g.get('name','')} | 第 {g.get('plant_ch','?')} 章 "
                        f"| {status} | {g.get('target_ch','')} | {g.get('plan','')} |")
        except Exception:
            pass

    # 3. Load Active Misunderstandings（JSON SSOT）
    mis_json = workspace_dir / "04_timeline_and_state" / "misunderstandings.json"
    if mis_json.exists():
        try:
            md = json.loads(mis_json.read_text(encoding="utf-8"))
            for m in md.get("misunderstandings", []):
                status = str(m.get("status", "Active"))
                if "Resolved" not in status and "已澄清" not in status:
                    package["active_misunderstandings"].append(
                        f"| {m.get('id','')} | {m.get('parties','')} | {m.get('content','')} "
                        f"| {m.get('truth','')} | {m.get('level','')} | {m.get('target_ch','')} |")
        except Exception:
            pass

    # 4. Find Previous Chapter Ending
    manuscript_dir = workspace_dir / "05_manuscript"
    if manuscript_dir.exists():
        finalized_files = sorted(list(manuscript_dir.glob("**/finalized/ch_*.md")), key=natural_chapter_sort_key)
        if finalized_files:
            # If target_chapter is specified, find the one before it
            prev_file = None
            if target_chapter_str:
                target_num = chapter_token_to_num(target_chapter_str)
                if target_num is not None:
                    for f in finalized_files:
                        if file_matches_chapter(f, target_num - 1):
                            prev_file = f
                            break
            if not prev_file:
                prev_file = finalized_files[-1]

            if prev_file:
                prev_text = prev_file.read_text(encoding="utf-8").strip()
                # Get last 1000 chars for continuity
                package["previous_chapter_ending"] = f"【上一章（{prev_file.name}）末尾余温】:\n" + prev_text[-1000:].strip()

    # 4.5 Load Story Bible / World Settings / Volume Outline（Stage 0 资料支撑）
    # 这些是 init 生成的设定资产：圣经是全书最高锚点（小，整块保留），
    # 世界观与卷纲较大，进入预算裁剪（保留头部：设定总纲在前）。
    package["story_bible"] = ""
    bible_file = workspace_dir / "00_meta" / "project_bible.md"
    if bible_file.exists():
        package["story_bible"] = bible_file.read_text(encoding="utf-8").strip()

    package["world_settings"] = ""
    world_parts = []
    for wname, wlabel in (("world_rules.md", "世界规则与能力阶梯"),
                          ("factions.md", "势力格局"),
                          ("geography.md", "地理空间")):
        wfile = workspace_dir / "01_world" / wname
        if wfile.exists():
            wtext = wfile.read_text(encoding="utf-8").strip()
            if wtext:
                world_parts.append(f"【{wlabel}】\n{wtext}")
    package["world_settings"] = "\n\n".join(world_parts)

    package["volume_outline"] = ""
    outline_parts = []
    outlines_dir = workspace_dir / "03_outlines"
    if outlines_dir.exists():
        main_plot = outlines_dir / "main_plot.md"
        if main_plot.exists():
            mtext = main_plot.read_text(encoding="utf-8").strip()
            if mtext:
                outline_parts.append(f"【全书主线】\n{mtext}")
        for vol_file in sorted(outlines_dir.glob("vol_*_outline.md")):
            vtext = vol_file.read_text(encoding="utf-8").strip()
            if vtext:
                outline_parts.append(f"【{vol_file.stem}】\n{vtext}")
    package["volume_outline"] = "\n\n".join(outline_parts)

    # 5. Load Target Chapter Beats (boundary-safe: ch_001 won't match ch_010)
    beats_dir = workspace_dir / "03_outlines"
    if beats_dir.exists() and target_chapter_str:
        beat_files = [
            f for f in beats_dir.glob("**/*.md")
            if "beats" in str(f).replace("\\", "/") and file_matches_chapter(f, target_chapter_str)
        ]
        if beat_files:
            package["target_beats"] = sorted(beat_files)[0].read_text(encoding="utf-8").strip()

    # 6. Load Relevant Character Cards
    profiles_dir = workspace_dir / "02_characters" / "profiles"
    character_registry = load_character_registry(workspace_dir)
    if profiles_dir.exists():
        for pfile in sorted(profiles_dir.glob("*.md")):
            if not pfile.name.startswith("."):
                p_text = pfile.read_text(encoding="utf-8").strip()
                # Extract canonical character name; aliases are registered centrally.
                name_match = re.search(r"#+\s*(?:角色(?:姓名|名|卡)?[：:]\s*)?([^\n(（\s#*]+)", p_text)
                char_real_name = name_match.group(1).strip() if name_match else ""
                char_real_name = re.sub(r"[*_`#]", "", char_real_name)
                
                is_protagonist = "protagonist" in pfile.stem.lower() or "主角" in p_text
                
                # Check if character is mentioned in target beats, state, or is protagonist
                search_scope = (package["target_beats"] or "") + "\n" + (package["current_state"] or "")
                
                matched = False
                aliases = character_registry.get(char_real_name, [char_real_name])
                if any(a and a in search_scope for a in aliases):
                    matched = True
                elif pfile.stem in search_scope or pfile.name in search_scope:
                    matched = True
                elif not package["target_beats"] and is_protagonist:
                    matched = True
                elif is_protagonist and len(package["relevant_character_profiles"]) == 0:
                    matched = True
                    
                if matched:
                    display_key = char_real_name if char_real_name else pfile.stem
                    package["relevant_character_profiles"][display_key] = p_text

    # 7. Compute High-Priority Story Alerts (Ebbinghaus Decay + Urgent DAG Guns)
    story_alerts = []
    
    # Check decaying characters
    try:
        from track_character_decay import track_memory_decay
        decay_data = track_memory_decay(workspace_path=str(workspace_dir), as_json=True, print_output=False)
        if decay_data and "warnings" in decay_data:
            for w in decay_data["warnings"]:
                story_alerts.append(f"🧠 [角色掉线唤醒提醒] {w}")
    except ImportError as e:
        logger.warning("可选模块 track_character_decay 不可用，该功能已降级跳过: %s", e)
    except Exception as e:
        logger.warning("角色掉线检测运行失败: %s", e)

    package["high_priority_story_alerts"] = story_alerts

    # 8. P1 记忆引擎：梗概脊柱 + RAG 资料员召回 + 跨章重复预警（纯本地零 Token）
    target_num = chapter_token_to_num(target_chapter_str) if target_chapter_str else None
    try:
        import memory_core
        # 8a. 梗概脊柱（只渲染提案登记的人工梗概；pack 为只读，不落盘）
        spine_data = memory_core.load_synopsis(workspace_dir)
        package["synopsis_spine"] = memory_core.render_spine_brief(spine_data)

        # 8b. RAG 资料员：用本章 beats + 上一章结尾做查询，召回相关旧段落
        query_parts = [package.get("target_beats", ""), package.get("previous_chapter_ending", "")]
        query = "\n".join(p for p in query_parts if p)
        if query.strip():
            package["librarian_recall"] = memory_core.librarian_recall(
                workspace_dir, query, top_k=6,
                exclude_chapter=(target_num - 1) if target_num else None)

        # 8c. 跨章重复检测（n-gram 雷同 / 场景相似）
        rep = memory_core.detect_cross_chapter_repetition(workspace_dir)
        package["cross_chapter_warnings"] = rep.get("warnings", [])
        if rep.get("warnings"):
            story_alerts.append(
                f"🔁 [跨章重复预警] 检测到 {len(rep['warnings'])} 处疑似重复（雷同/场景相似），"
                "写新章时务必换桥段、勿重新介绍已登场角色")
    except ImportError as e:
        logger.warning("可选模块 memory_core 不可用，该功能已降级跳过: %s", e)
        package["memory_engine_error"] = str(e)
    except Exception as e:
        logger.warning("记忆引擎运行失败: %s", e)
        package["memory_engine_error"] = str(e)

    # 8d. P3-4 题材档案指导（注入题材专属导演提示，随书 00_meta/genre_profile.json 可微调）
    try:
        import genre_profile as gp
        gprof = gp.resolve_genre_profile(workspace_dir)
        package["genre_profile"] = {
            "id": gprof.get("id"), "label": gprof.get("label"),
            "director_notes": gprof.get("director_notes", ""),
            "word_count": gprof.get("word_count", {}),
            "ratio_baseline": gprof.get("ratio_baseline", {}),
        }
    except ImportError as e:
        logger.warning("可选模块 genre_profile 不可用，该功能已降级跳过: %s", e)
        package["genre_profile_error"] = str(e)
    except Exception as e:
        logger.warning("题材档案加载失败: %s", e)
        package["genre_profile_error"] = str(e)

    # 8e. P2 伏笔主动调度（为 beats-builder 排期：本章该引爆/回唤/唤醒哪些伏笔）
    try:
        import foreshadow_scheduler as fs
        if target_num is not None:
            package["foreshadow_schedule"] = fs.schedule(workspace_dir, target_num)
            sched = package["foreshadow_schedule"]
            for g in sched.get("detonate_now", []):
                tag = "🚨超期" if g.get("overdue") else "⏰到期"
                story_alerts.append(
                    f"💥 [伏笔调度] {tag} {g['id']}《{g['name']}》{g['target']}：{g['note']}")
            for g in sched.get("remind_soon", [])[:3]:
                story_alerts.append(f"🔔 [伏笔回唤] {g['id']}《{g['name']}》：{g['note']}")
    except ImportError as e:
        logger.warning("可选模块 foreshadow_scheduler 不可用，该功能已降级跳过: %s", e)
        package["scheduler_error"] = str(e)
    except Exception as e:
        logger.warning("伏笔调度器运行失败: %s", e)
        package["scheduler_error"] = str(e)

    # 9. Token 预算模式：按相关性裁剪（在所有内容装配完成后）
    if budget and budget > 0:
        package = _apply_budget(package, budget)

    if as_json:
        if print_output:
            print(json.dumps(package, ensure_ascii=False, indent=2))
        return package

    # Render Clean Markdown Output for Agent Consumption
    if not print_output:
        return package
    print("═" * 72)
    print(f" 📦 [动态创作上下文极速打包] 工作区: {package['workspace']} | 目标: {package['target_chapter']}")
    print("═" * 72)

    if package["high_priority_story_alerts"]:
        print("\n🚨 【高优先级剧情导航预警 (角色唤醒 & 临界伏笔)】:")
        for al in package["high_priority_story_alerts"]:
            print(f"   👉 {al}")
        print("─" * 72)
    
    gp = package.get("genre_profile")
    if gp and gp.get("director_notes"):
        wc = gp.get("word_count", {})
        print(f"\n## 🎭 题材档案: {gp.get('label','')} (id={gp.get('id','')})"
              f"  字数下限 {wc.get('min','-')} / 建议 {wc.get('recommended','-')}")
        print("   📝 " + gp["director_notes"])
        print("─" * 72)

    if package.get("synopsis_spine"):
        print("\n## 📚 全书梗概脊柱 (Synopsis Spine · 防场景/情节重复):\n" + package["synopsis_spine"])
        print("─" * 72)

    if package.get("librarian_recall"):
        print("\n## 🔎 RAG 资料员召回 (BM25 相关旧伏笔/人物/设定):")
        for h in package["librarian_recall"]:
            print(f"   - [{h['chapter']} {h.get('title','')}] (score {h['score']}) {h['snippet']}")
        print("─" * 72)

    if package.get("cross_chapter_warnings"):
        print("\n## 🔁 跨章重复预警 (写新章务必规避):")
        for w in package["cross_chapter_warnings"]:
            print(f"   {w}")
        print("─" * 72)

    sched = package.get("foreshadow_schedule")
    if sched and (sched.get("detonate_now") or sched.get("remind_soon")
                  or sched.get("dormant_wakeup")):
        print("\n## 🪶 伏笔主动调度 (本章 Beats 排期建议):")
        for g in sched.get("detonate_now", []):
            tag = "🚨 超期" if g.get("overdue") else "⏰ 到期"
            print(f"   💥 {tag} {g['id']}《{g['name']}》（{g['target']}）：{g['note']}")
        for g in sched.get("remind_soon", []):
            print(f"   🔔 回唤 {g['id']}《{g['name']}》：{g['note']}")
        for g in sched.get("dormant_wakeup", [])[:4]:
            print(f"   😴 沉睡 {g['id']}《{g['name']}》：{g['note']}")
        print("─" * 72)

    if package["target_beats"]:
        print("\n## 🎯 本章细纲与 Beats:\n" + package["target_beats"])
        print("─" * 72)

    if package.get("budget_report"):
        br = package["budget_report"]
        print(f"\n## 🪙 Token 预算: {br['total_kept_tokens']}/{br['budget_tokens']}"
              f" ({'✅ 在内' if br['within_budget'] else '⚠️ 超出'})")
        for s in br["sections"]:
            if s["dropped_tokens"] or s.get("note"):
                line = f"   - {s['section']}: 保留 {s['kept_tokens']}"
                if s["dropped_tokens"]:
                    line += f"，裁掉 {s['dropped_tokens']}"
                if s.get("note"):
                    line += f"（{s['note']}）"
                print(line)
        if br.get("hint"):
            print(f"\n   💡 {br['hint']}")
        print("─" * 72)

    if package["current_state"]:
        print("\n## 📍 当前实时状态机:\n" + package["current_state"])
        print("─" * 72)

    if package["character_growth_arcs"]:
        print("\n## 🧠 核心角色心智演进台账 (Growth Arcs):\n" + package["character_growth_arcs"])
        print("─" * 72)

    if package.get("resource_pools"):
        print("\n## 💰 核心资产与量化资源池 (Resource Pools):")
        for p_id, p_info in package["resource_pools"].items():
            name = p_info.get("name", p_id)
            cur = p_info.get("current", 0)
            unit = p_info.get("unit", "")
            print(f"   - {name}: {cur} {unit}".strip())
        print("─" * 72)

    if package.get("story_bible"):
        print("\n## 📖 项目圣经 (Story Bible · 全书最高锚点):\n" + package["story_bible"])
        print("─" * 72)

    if package.get("world_settings"):
        print("\n## 🌍 世界观设定 (World Settings):\n" + package["world_settings"])
        print("─" * 72)

    if package.get("volume_outline"):
        print("\n## 🗺️ 主线与卷纲 (Volume Outline):\n" + package["volume_outline"])
        print("─" * 72)

    if package["active_chekhov_guns"]:
        print("\n## 🎯 活跃契诃夫之枪 (伏笔池):\n" + "\n".join(package["active_chekhov_guns"]))
        print("─" * 72)

    if package["active_misunderstandings"]:
        print("\n## 🎭 活跃误会与信息差台账:\n" + "\n".join(package["active_misunderstandings"]))
        print("─" * 72)

    if package["previous_chapter_ending"]:
        print("\n## 🔗 上一章情绪余温衔接:\n" + package["previous_chapter_ending"])
        print("─" * 72)

    if package["relevant_character_profiles"]:
        print("\n## 👤 本章涉及核心人物卡:")
        for cname, ptext in package["relevant_character_profiles"].items():
            print(f"\n### 【{cname}】\n" + ptext)

    print("\n═" * 72)
    print(" ✨ [上下文打包就绪] 1 次调用装载全量语境，算力全量留给情节起草！")
    print("═" * 72 + "\n")
    return package

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Agent-First 动态创作上下文极速打包器")
    parser.add_argument("--workspace", "-w", type=str, default=None, help="目标小说工作区路径")
    parser.add_argument("--chapter", "-c", type=str, default=None, help="目标章节序号，例如: ch_004")
    parser.add_argument("--json", action="store_true", help="以结构化 JSON 格式输出")
    parser.add_argument("--budget", type=int, default=0,
                        help="token 预算；>0 时按相关性裁剪并报告裁掉了什么（0=全量，默认）")
    args = parser.parse_args()

    package_context_for_chapter(target_chapter_str=args.chapter, workspace_path=args.workspace,
                                as_json=args.json, budget=args.budget)
