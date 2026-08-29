"""evidence 五 kind 的契约冻结与数值正确性。

契约：输出为纯 JSON 语义的 dict；kind 恒在；零判断词（本文件同时断言 key 名防漂移）。
数值：对 fixtures 手算——regex 计数必须与 Python 直数一致，绝不允许"大概对"。
"""
import json

from engine import evidence, state


def build_book(tmp_path):
    """三章小书：ch_001/002/003 定稿 + 伏笔/误会 + 实体注册。"""
    from pathlib import Path

    book = Path(tmp_path) / "b"
    state.init_state(book)
    (book / "manuscript" / "vol_01" / "final").mkdir(parents=True, exist_ok=True)
    texts = {
        "ch_001": "# 第一章 渊口\n\n沈拓夜里巡渊。黑玉佩在掌心发烫。\n\n「站住！」他喝道。\n\n沈拓夜里巡渊。黑玉佩在掌心发烫。\n",
        "ch_002": "# 第二章 当铺\n\n当铺赵四眯着眼。仿佛雾里看花一般。\n\n沈拓不是来赎刀的，而是来卖命的。\n",
        "ch_003": "# 第三章 雨夜\n\n村长站在檐下。雨声盖过更鼓。\n",
    }
    for tok, txt in texts.items():
        (book / "manuscript" / "vol_01" / "final" / f"{tok}.md").write_text(txt, encoding="utf-8")
    beats = book / "outlines" / "vol_01" / "beats"
    beats.mkdir(parents=True, exist_ok=True)
    (beats / "ch_001.md").write_text("---\nform: 单场景章\nhook: 强钩\n---\n\n渊口夜巡。\n",
                                    encoding="utf-8")
    (beats / "ch_002.md").write_text("---\nform: 对话驱动章\n---\n\n当铺交锋。\n", encoding="utf-8")
    (beats / "ch_003.md").write_text("---\nform: 静水流日常章\n---\n\n雨夜对峙。\n", encoding="utf-8")
    rep = state.apply_proposal(book, {
        "schema": "novel-studio.state-mutation/v2", "chapter": "ch_001", "operation_id": "setup.op1",
        "entities": [{"action": "upsert", "name": "沈拓", "type": "person", "aliases": ["拓哥"]},
                     {"action": "upsert", "name": "赵四", "type": "person", "aliases": ["当铺赵四"]}],
        "lines": [{"kind": "foreshadow", "action": "plant", "name": "黑玉佩来历", "target_ch": 2},
                  {"kind": "foreshadow", "action": "plant", "name": "父亲旧案", "target_ch": 40},
                  {"kind": "misunderstanding", "action": "plant", "parties": "村长↔沈拓",
                   "content": "玉佩是赃物", "target_ch": 1}],
    })
    assert rep["errors"] == []
    return book


def test_words_contract_and_counts(tmp_path):
    ev = evidence.words(build_book(tmp_path))
    assert set(ev) == {"kind", "chapter_count", "total_cjk", "chapters"}
    assert ev["kind"] == "words" and ev["chapter_count"] == 3
    ch1 = ev["chapters"][0]
    assert set(ch1) == {"chapter", "cjk", "sentences"}
    # ch_001 正文 CJK 手算：6+8+2+3+6+8=33
    assert ch1["cjk"] == 33
    assert ev["total_cjk"] == sum(c["cjk"] for c in ev["chapters"])


def test_mentions(tmp_path):
    book = build_book(tmp_path)
    ev = evidence.mentions(book, "沈拓")
    assert set(ev) == {"kind", "target", "aliases", "total", "first_chapter", "last_chapter", "chapters"}
    assert ev["target"] == "沈拓" and ev["aliases"] == ["沈拓", "拓哥"]
    assert ev["chapters"][0]["total"] == 2  # ch_001 两次
    by_alias = ev["chapters"][0]["by_alias"]
    assert by_alias == {"沈拓": 2, "拓哥": 0}
    # 别名检索：「当铺赵四」在 ch_002（最长优先非重叠）
    ev2 = evidence.mentions(book, "赵四")
    assert ev2["total"] == 1
    # 总览模式
    ev3 = evidence.mentions(book)
    assert ev3["mode"] == "registry_overview" and ev3["entities"] == 2
    # 未登记 → unknown（CLI 转 rc 2）
    assert evidence.mentions(book, "路人甲")["unknown"] is True


def test_gaps(tmp_path):
    ev = evidence.gaps(build_book(tmp_path))
    assert ev["max_final_chapter"] == 3
    fs = {g["id"]: g for g in ev["foreshadows"]}
    assert fs["GUN-001"]["overdue"] is True   # target 2 < 3，未回收
    assert fs["GUN-002"]["overdue"] is False  # longline 40 未到
    assert fs["GUN-001"]["idle_chapters"] == 2
    ms = ev["misunderstandings"][0]
    assert ms["overdue"] is True and ms["status"] == "Active"
    assert ev["summary"]["overdue_foreshadows"] == 1


def test_dup_catches_copy_paste(tmp_path):
    ev = evidence.dup(build_book(tmp_path))
    assert set(ev) == {"kind", "shingle_n", "scope", "within", "adjacent_pairs"}
    w = {x["chapter"]: x for x in ev["within"]}
    assert "ch_001" in w and w["ch_001"]["repeated_sentences"] == 1  # 整句自重复
    # 单章模式带相邻对
    one = evidence.dup(build_book(tmp_path), "ch_001")
    assert one["within"][0]["chapter"] == "ch_001"


def test_style_metrics(tmp_path):
    book = build_book(tmp_path)
    ev = evidence.style(book, "ch_002")
    assert ev["kind"] == "style" and len(ev["chapters"]) == 1
    c = ev["chapters"][0]
    for key in ("len_mean", "len_stdev", "max_share", "dialogue_line_ratio", "para_head_repeat"):
        assert key in c
    assert c["ai_constructions"]["不是…而是…"] == 1
    assert c["ai_constructions"]["仿佛…一般"] == 1
    dist = ev["form_distribution"]["vol_01"]
    assert dist["forms"] == {"单场景章": 1, "对话驱动章": 1, "静水流日常章": 1}
    assert all(abs(sum(dist["shares"].values()) - 1.0) < 0.01 for _ in [0])
    assert dist["count"] == 3 and dist["missing_form"] == []


def test_evidence_is_json_serializable(tmp_path):
    book = build_book(tmp_path)
    for payload in (evidence.words(book), evidence.gaps(book), evidence.style(book),
                    evidence.dup(book), evidence.mentions(book)):
        json.dumps(payload, ensure_ascii=False)  # 不许混进 Path/集合等不可序列化对象
    flat = json.dumps(evidence.style(book), ensure_ascii=False)
    for banned in ("建议", "可疑", "疑似", "不宜", "达标"):
        assert banned not in flat  # 零语义词红线
