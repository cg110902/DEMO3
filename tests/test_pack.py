"""M4 验收：pack 三层契约 + 触发命中率（beats 提及实体 100% 到包）+ templates 槽位回路 + export。"""
import json
from pathlib import Path

from engine import cli, common, pack, state

BOOK = "渊火记"


def build_book(tmp_path) -> Path:
    book = Path(tmp_path) / "b"
    common.dump_json(book / "project.json", {
        "schema": "novel-studio.project/v1", "title": BOOK, "genre": "悬疑玄幻", "protagonist": "沈拓",
        "mode": "automatic", "words_target": [20, 4500], "style_guards": ["不要复读天气比喻"]})
    state.init_state(book)
    (book / "bible").mkdir(exist_ok=True)
    (book / "bible" / "project_bible.md").write_text(
        "# 圣经\n\n## 本书偏离清单\n\n- 保留翻译腔（人物设定需要）\n", encoding="utf-8")
    (book / "characters").mkdir(exist_ok=True)
    (book / "characters" / "沈拓.md").write_text("# 沈拓\n\n- Want: 查清父案\n", encoding="utf-8")
    (book / "manuscript" / "vol_01" / "final").mkdir(parents=True)
    (book / "manuscript" / "vol_01" / "final" / "ch_001.md").write_text(
        "# 第一章\n\n村长骂了沈拓一句。黑玉佩在怀里发烫，烫得像一句没说完的警告。\n", encoding="utf-8")
    beats = book / "outlines" / "vol_01" / "beats"
    beats.mkdir(parents=True, exist_ok=True)
    (beats / "ch_001.md").write_text("---\nchapter: ch_001\nvol: vol_01\nform: 单场景章\n---\n\n夜巡。\n", encoding="utf-8")
    (beats / "ch_002.md").write_text(
        "---\nchapter: ch_002\nvol: vol_01\nform: 对话驱动章\n---\n\n村长逼问拓哥；黑玉佩的事必须摊牌。\n", encoding="utf-8")
    rep = state.apply_proposal(book, {
        "schema": "novel-studio.state-mutation/v2", "chapter": "ch_001", "operation_id": "setup.op1",
        "current": {"location": "青石镇", "present_characters": ["沈拓", "村长"]},
        "entities": [
            {"action": "upsert", "name": "沈拓", "type": "person", "aliases": ["拓哥"],
             "summary": "镇渊守卒", "card": "characters/沈拓.md"},
            {"action": "upsert", "name": "村长", "type": "person", "summary": "玉佩旧案知情人，挂线 GUN-001"},
            {"action": "upsert", "name": "黑玉佩", "type": "item", "summary": "军械司督造印信；钥匙藏在祠堂"},
            {"action": "upsert", "name": "祠堂", "type": "place", "summary": "镇北老祠，匣子供于牌位后"},
            {"action": "upsert", "name": "沈砚", "type": "person", "summary": "亡父，旧案主角"}],
        "lines": [{"kind": "foreshadow", "action": "plant", "name": "村长与黑玉佩旧案", "target_ch": 2},
                  {"kind": "misunderstanding", "action": "plant", "parties": "村长↔沈拓", "content": "玉佩是赃物"}],
        "ledger": {"transactions": [{"pool": "standard_currency", "delta": 100, "subject": "赏钱"},
                                    {"pool": "standard_currency", "delta": -40, "type": "expense", "subject": "买药"}]},
        "synopsis": {"title": "渊口", "text": "沈拓夜巡捡得黑玉佩。"}})
    assert rep["errors"] == []
    return book


# ---------------- pack ----------------

def test_pack_contract_and_hit_rate(tmp_path):
    payload = pack.build_pack(build_book(tmp_path), "ch_002")
    assert set(payload) == {"chapter", "lean", "full", "p0", "p1", "p2", "budget_report", "hits"}
    # 命中率：beats 提到「村长/拓哥(别名)/黑玉佩」→ 三个实体必到包；未提的沈砚不得进 P1
    assert set(payload["hits"]) == {"村长", "沈拓", "黑玉佩"}
    p1names = {b["name"] for b in payload["p1"]["entities"]}
    assert p1names == {"村长", "沈拓", "黑玉佩"}
    assert "沈砚" not in json.dumps(payload["p1"], ensure_ascii=False)
    # 在场标注与挂线（村长 summary 含 GUN-001 字样不算挂线，挂线按线文本匹配）
    blocks = {b["name"]: b for b in payload["p1"]["entities"]}
    assert blocks["沈拓"]["on_stage"] is True
    assert any("GUN-001" in ln for ln in blocks["村长"].get("lines", []))
    # 预算自报
    b = payload["budget_report"]
    assert set(b) == {"p0", "p1", "p2", "total", "cap", "over_budget"}
    assert b["total"] == b["p0"] + b["p1"] + b["p2"]
    assert isinstance(b["over_budget"], bool)


def test_pack_recursion_depth_two(tmp_path):
    payload = pack.build_pack(build_book(tmp_path), "ch_002")
    # 黑玉佩（直接命中）的 summary 提到祠堂 → 祠堂只以"间接一行摘要"进包（深度 ≤2）
    ind = payload["p1"]["indirect"]
    assert any(line.startswith("祠堂：") and len(line) <= 60 for line in ind)
    # 第三层不回灌：祠堂摘要里的"匣子/牌位"若被登记为实体，也不该获得独立块
    names_in_p1 = {b["name"] for b in payload["p1"]["entities"]} | {x.split("：")[0] for x in ind}
    assert "沈砚" not in names_in_p1


def test_pack_hard_reminders(tmp_path):
    p0 = pack.build_pack(build_book(tmp_path), "ch_002")["p0"]
    joined = "\n".join(p0["hard_reminders"])
    assert "GUN-001" in joined and "本章引爆" in joined          # target==2
    assert "MIS-001 未澄清" in joined                              # 误会未了
    assert "不要复读天气比喻" in joined                             # style_guards
    assert "本书偏离：保留翻译腔" in joined                          # 偏离清单注入
    assert p0["beats"].startswith("---")                            # beats 原文整块


def test_pack_prev_tail_and_beats_required(tmp_path):
    book = build_book(tmp_path)
    p1 = pack.build_pack(book, "ch_001")
    assert p1["p0"]["prev_tail"] == ""  # 首章无上章
    p2 = pack.build_pack(book, "ch_002")
    assert "黑玉佩在怀里发烫" in p2["p0"]["prev_tail"]
    import pytest
    with pytest.raises(ValueError):
        pack.build_pack(book, "ch_009")  # 无 beats 不放行


def test_pack_lean_and_full(tmp_path):
    book = build_book(tmp_path)
    lean = pack.build_pack(book, "ch_002", lean=True)
    assert lean["p1"] is None and lean["p2"] is None and lean["budget_report"]["p1"] == 0
    full = pack.build_pack(book, "ch_002", full=True)
    block = {b["name"]: b for b in full["p1"]["entities"]}["沈拓"]
    assert "Want: 查清父案" in block["card_text"]


def test_cli_pack_json_and_open(tmp_path, capsys):
    book = build_book(tmp_path)
    assert cli.main(["pack", "2", "-w", str(book), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["chapter"] == "ch_002"
    assert cli.main(["pack", "-w", str(book), "--open", "characters/沈拓.md"]) == 0
    assert "查清父案" in capsys.readouterr().out
    assert cli.main(["pack", "-w", str(book), "--open", "../escape.md"]) == 1
    assert cli.main(["pack", "-w", str(book)]) == 2  # 既无章号也无 open


# ---------------- templates / init 槽位回路 ----------------

def test_init_instantiates_slots_and_check_supervises(tmp_path, capsys):
    book = Path(tmp_path) / "nb"
    assert cli.main(["init", "-w", str(book), "-t", BOOK, "-g", "悬疑玄幻", "-p", "沈拓"]) == 0
    bible = (book / "bible" / "project_bible.md").read_text(encoding="utf-8")
    assert BOOK in bible and "{{slot:title" not in bible       # 已知槽位被替换
    assert "{{slot:logline" in bible                            # 未提供的槽位保留，等 Stage 0 填
    assert "沈拓" in (book / "characters" / "protagonist.md").read_text(encoding="utf-8")
    assert "悬疑玄幻" in (book / "outlines" / "main_plot.md").read_text(encoding="utf-8")
    # check 督战：未填 → errors；填上 → 绿
    assert cli.main(["check", "-w", str(book)]) == 1
    assert "unfilled_slot" in capsys.readouterr().out
    (book / "bible" / "project_bible.md").write_text(bible.replace("{{slot:logline|主角+欲望+障碍，一句话}}",
                                                                   "守卒捡得督造印，旧案翻出镇底。"), encoding="utf-8")
    (book / "outlines" / "main_plot.md").write_text(
        (book / "outlines" / "main_plot.md").read_text(encoding="utf-8")
        .replace("{{slot:title|书名}}", BOOK), encoding="utf-8")
    (book / "characters" / "protagonist.md").write_text(
        (book / "characters" / "protagonist.md").read_text(encoding="utf-8")
        .replace("{{slot:protagonist|角色名}}", "沈拓"), encoding="utf-8")
    vol = book / "outlines" / "vol_01" / "outline.md"
    vol.write_text(vol.read_text(encoding="utf-8").replace("{{slot:title|书名}}", BOOK), encoding="utf-8")
    report = cli.main(["check", "--json", "-w", str(book)])
    assert report == 0


# ---------------- export ----------------

def test_export_txt_and_views(tmp_path, capsys):
    book = build_book(tmp_path)
    (book / "manuscript" / "vol_01" / "final" / "ch_002.md").write_text("# 第二章 摊牌\n\n村长拍桌。\n", encoding="utf-8")
    assert cli.main(["export", "-w", str(book)]) == 0
    txt = (book / "export" / f"{BOOK}.txt").read_text(encoding="utf-8")
    assert txt.index("第一章") < txt.index("摊牌") and BOOK in txt
    views = (book / "export" / "views" / "state_view.md").read_text(encoding="utf-8")
    assert "GUN-001" in views and "**60**" in views and "沈拓" in views
    # 确定性：同状态重渲染字节一致
    before = (book / "export" / "views" / "state_view.md").read_bytes()
    assert pack.export_views(book).read_bytes() == before
    # 单项导出
    (book / "export").mkdir(exist_ok=True)
    capsys.readouterr()
    assert cli.main(["export", "--views", "-w", str(book)]) == 0
    assert "state_view.md" in capsys.readouterr().out
