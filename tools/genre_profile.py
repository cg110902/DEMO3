# -*- coding: utf-8 -*-
"""
Genre Profile — P3-4 题材 Profile 配置化（全题材自适应的最后一公里）。

不同题材的"好书阈值"本就不同：玄幻靠境界推进与战斗、悬疑靠信息差与线索公平、
都市靠世情对白、科幻靠设定自洽…… 此前这些阈值/节奏全写死在通用代码里，
本模块把它们抽成随书走的「题材档案」：

- 内置档案：tools/genre_profiles/<id>.json（17 种题材 + generic 兜底）
- 随书覆盖：<workspace>/00_meta/genre_profile.json（init 时按题材拷贝，可人工微调，优先于内置）
- 全链路读取：foreshadow_scheduler（提醒窗口）、pack（注入 director_notes 题材指导）
  统一从 resolve_genre_profile() 取值。

全部纯 Python 标准库（json），零第三方依赖、零 Token。

用法：
    python tools/genre_profile.py                 # 查看当前工作区解析到的题材档案
    python tools/genre_profile.py --list          # 列出所有内置题材
    python tools/genre_profile.py --genre "科幻机甲" --json
"""

import sys
import re
import json
import copy
import argparse
from pathlib import Path

_tools_dir = Path(__file__).resolve().parent
if str(_tools_dir) not in sys.path:
    sys.path.insert(0, str(_tools_dir))

from novel_utils import resolve_workspace, reconfigure_utf8
from config_core import _deep_merge, get_engineering_defaults, load_effective_config

reconfigure_utf8()

PROFILE_SCHEMA = "novel-studio.genre-profile/v2"
WORKSPACE_PROFILE = "00_meta/genre_profile.json"

# 题材模糊匹配关键词（命中即选该内置档案）
# 注意：跨题材通用词（如"系统""模拟器"）在多个题材中都出现，靠命中总数区分
_GENRE_KEYWORDS = {
    "xuanhuan":   ["玄幻", "仙侠", "修仙", "修真", "仙武", "异界", "大陆", "宗门", "境界", "灵气", "渡劫", "金丹", "元婴", "系统模拟器"],
    "wuxia":      ["武侠", "江湖", "武林", "门派", "内功", "轻功", "剑客", "镖局", "丐帮", "少林", "武当", "真气", "点穴"],
    "urban":      ["都市", "异能", "职场", "商战", "娱乐", "现代", "重生都市", "神豪", "系统", "模拟器", "都市异能"],
    "scifi":      ["科幻", "机甲", "星际", "赛博", "末世", "废土", "未来", "科技", "太空", "进化", "义体", "星舰"],
    "mystery":    ["悬疑", "推理", "侦探", "惊悚", "犯罪", "破案", "本格", "法医", "刑警"],
    "horror":     ["恐怖", "克苏鲁", "鬼故事", "灵异", "怨灵", "凶宅", "心理恐怖", "怪谈"],
    "history":    ["历史", "架空", "穿越古代", "王朝", "种田", "权谋", "历史架空", "古代", "贞观", "大明", "大清"],
    "rulebound":  ["规则怪谈", "规则", "副本", "求生", "SCP", "异常"],
    "infinite":   ["无限流", "无限恐怖", "主神", "轮回", "任务世界", "轮回空间"],
    "romance":    ["言情", "纯爱", "恋爱", "甜宠", "虐恋", "霸总", "总裁", "古言", "现言", "耽美", "百合", "婚恋"],
    "gaming":     ["游戏", "电竞", "网游", "虚拟网游", "全息游戏", "电竞选手", "战队", "直播", "攻略", "副本开荒"],
    "sports":     ["体育", "竞技", "篮球", "足球", "网球", "赛车", "运动", "奥运", "冠军", "田径", "游泳"],
    "military":   ["军事", "战争", "军旅", "特种兵", "战场", "战役", "军装", "部队", "亮剑", "谍战"],
    "lightnovel": ["轻小说", "轻文", "异世界", "转生", "穿越异世界", "冒险者", "公会", "魔王", "勇者", "魔法学院"],
    "realism":    ["现实主义", "年代", "年代文", "知青", "改革开放", "市井", "民生", "纪实", "乡土", "工厂"],
    "iyashikei":  ["治愈", "日常", "治愈系", "慢生活", "田园", "美食", "萌宠", "温馨", "日常系", "百合日常"],
}

# 通用兜底默认从 tools/genre_profiles/generic.json 加载（单一真值源，避免硬编码漂移）。
# 工程默认值（engine 等）由 config_core.get_engineering_defaults() 提供。
_GENERIC_CACHE = None


def _builtin_dir() -> Path:
    return _tools_dir / "genre_profiles"


def _generic_profile() -> dict:
    global _GENERIC_CACHE
    if _GENERIC_CACHE is None:
        p = _builtin_dir() / "generic.json"
        if p.exists():
            try:
                _GENERIC_CACHE = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                _GENERIC_CACHE = {}
        else:
            _GENERIC_CACHE = {}
    return copy.deepcopy(_GENERIC_CACHE)


# 向后兼容别名已移除；需要 generic 兜底时调用 _generic_profile()。


def list_builtin_profiles() -> list:
    d = _builtin_dir()
    out = []
    if d.exists():
        for p in sorted(d.glob("*.json")):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                out.append({"id": data.get("id", p.stem),
                            "label": data.get("label", p.stem),
                            "path": str(p)})
            except Exception:
                continue
    return out


def match_genre(genre_text: str) -> str:
    """把自由文本题材（如 '科幻机甲 / 末世'）模糊匹配到内置档案 id。"""
    if not genre_text:
        return "generic"
    # 子串覆盖去重：若某题材的全部命中词都是另一题材某个更长命中词的子串
    # （如"恐怖" ⊂ "无限恐怖"），泛词命中不计数——修复"无限恐怖"被
    # horror 的子串"恐怖"抢走一类错配；其余情形沿用命中数+声明序。
    matched_map = {}
    for gid, kws in _GENRE_KEYWORDS.items():
        ms = [k for k in kws if k in genre_text]
        if ms:
            matched_map[gid] = ms
    all_matched = [k for ms in matched_map.values() for k in ms]

    def _covered(ms):
        return all(any(k != longer and k in longer for longer in all_matched)
                   for k in ms)

    best, best_hits = "generic", 0
    for gid, kws in _GENRE_KEYWORDS.items():
        ms = matched_map.get(gid)
        if not ms or _covered(ms):
            continue
        if len(ms) > best_hits:
            best, best_hits = gid, len(ms)
    return best


def load_builtin(profile_id: str) -> dict:
    p = _builtin_dir() / f"{profile_id}.json"
    if p.exists():
        try:
            return _deep_merge(_generic_profile(), json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            pass
    return _generic_profile()


def _read_workspace_genre(ws) -> str:
    """推断工作区题材：优先读随书的 project_bible.md「主类型」，
    其次回退仓库根 novel_config.yaml 的 default_genre。"""
    try:
        bible = Path(ws) / "00_meta" / "project_bible.md"
        if bible.exists():
            for line in bible.read_text(encoding="utf-8").splitlines():
                s = line.strip().lstrip("-*").strip()
                if not re.match(r"\*?\*?主类型\*?\*?\s*[：:]", s):
                    continue
                m = re.search(r"[：:]\s*(.+)$", s)
                if m:
                    val = m.group(1).strip().strip("*《》 ")
                    if val and "[" not in val and "如：" not in val:
                        return val
    except Exception:
        pass
    try:
        return (load_effective_config().get("project", {}) or {}).get("default_genre", "") or ""
    except Exception:
        return ""


def resolve_genre_profile(workspace=None) -> dict:
    """解析当前应使用的题材档案：
    1) 工作区 00_meta/genre_profile.json（随书、可人工微调，最高优先）；
    2) 按 novel_config.yaml 的 default_genre 匹配内置档案；
    3) generic 兜底。
    返回的 dict 始终包含全部通用字段（深合 generic 兜底档案）。
    """
    profile = None
    try:
        ws = resolve_workspace(workspace)
        wp = ws / WORKSPACE_PROFILE
        if wp.exists():
            profile = json.loads(wp.read_text(encoding="utf-8"))
    except Exception:
        profile = None

    if not profile:
        genre = _read_workspace_genre(ws)
        gid = match_genre(genre)
        profile = load_builtin(gid)
        profile["matched_from"] = genre
        # 工程默认值在最底层，题材档案覆盖之
        return _deep_merge(get_engineering_defaults(), profile)

    # 工作区 profile：以其声明的 id 内置档案为底，再叠加工作区覆盖
    base = load_builtin(profile.get("id", "generic"))
    merged = _deep_merge(base, profile)
    return _deep_merge(get_engineering_defaults(), merged)


def install_profile_for_genre(workspace: Path, genre_text: str) -> Path:
    """init 时调用：按题材把内置档案拷贝到工作区 00_meta/genre_profile.json。
    已存在则不覆盖（保留人工微调）。返回写入路径。"""
    gid = match_genre(genre_text)
    data = load_builtin(gid)
    data["matched_genre"] = genre_text
    ws = Path(workspace)
    target = ws / WORKSPACE_PROFILE
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
    return target


def _main():
    ap = argparse.ArgumentParser(description="P3-4 题材 Profile 配置化（全题材自适应）")
    ap.add_argument("--workspace", "-w", help="工作区路径")
    ap.add_argument("--list", action="store_true", help="列出所有内置题材档案")
    ap.add_argument("--genre", help="按题材文本解析（不读工作区）")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    args = ap.parse_args()

    if args.list:
        items = list_builtin_profiles()
        if args.json:
            print(json.dumps(items, ensure_ascii=False, indent=2))
        else:
            print(f"内置题材档案（共 {len(items)} 种）：")
            for it in items:
                print(f"  - {it['id']:<14} {it['label']}")
        return

    if args.genre:
        gid = match_genre(args.genre)
        prof = load_builtin(gid)
        prof["matched_genre"] = args.genre
        prof["matched_from"] = args.genre  # 与工作区模式字段名统一
        # 工程默认值在最底层，题材档案覆盖之——与 resolve_genre_profile 同 schema
        prof = _deep_merge(get_engineering_defaults(), prof)
    else:
        ws = resolve_workspace(args.workspace)
        prof = resolve_genre_profile(ws)
        if args.json is False:
            print(f"📂 工作区: {ws.name}")

    if args.json:
        print(json.dumps(prof, ensure_ascii=False, indent=2))
    else:
        print("=" * 70)
        print(f" 🎭 题材档案: {prof.get('label')} (id={prof.get('id')})")
        if prof.get("matched_genre") or prof.get("matched_from"):
            print(f"   匹配自: {prof.get('matched_genre') or prof.get('matched_from')}")
        print(f"   创作目标: {prof.get('creation_goal')} | 视角默认: {prof.get('pov_default')}")
        print(f"   基调策略: {prof.get('tone_policy', {}).get('mode')} (明快={prof.get('tone_policy', {}).get('bright_allowed')} 阴暗={prof.get('tone_policy', {}).get('dark_allowed')})")
        print("=" * 70)
        wc = prof.get("word_count", {})
        print(f" 字数：下限 {wc.get('min')} / 建议 {wc.get('recommended')} / 上限 {wc.get('max')}")
        rb = prof.get("ratio_baseline", {})
        print(f" 配比基线：对白 {rb.get('dialogue')} | 推进 {rb.get('action')} | 描写 {rb.get('describe')}")
        print(f" 掉线提醒窗口：{prof.get('stall_window')} 章 | 对白地板 {prof.get('dialogue_floor')}% | 描写天花板 {prof.get('describe_ceiling')}%")
        sc = prof.get("scheduler", {})
        print(f" 伏笔调度：回唤提前 {sc.get('remind_lead')} 章 / 沉睡 {sc.get('dormant_gap')} 章 / 长线周期 {sc.get('longline_interval')}")
        comps = prof.get("state_components", [])
        print(f" 状态组件：{', '.join(comps)}")
        print(f"\n 📝 导演指导 (director_notes)：\n   {prof.get('director_notes','')}")


if __name__ == "__main__":
    _main()
