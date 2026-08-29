"""状态机不变量：提案校验、幂等、内存事务、账本重算、failed 捡回、跨章留置。

约定：引擎绝不带病落盘——errors 时状态文件一个字节都不动；
一切"余额"以流水重算为准；id 冲突/未知对象 = 事实冲突 → failed/ 等修复。
"""
import json
from pathlib import Path

from engine import common, state

OP = "novel-studio.state-mutation/v2"


def make_book(tmp_path) -> Path:
    book = Path(tmp_path) / "book"
    state.init_state(book)
    return book


def proposal(**kw):
    base = {"schema": OP, "chapter": "ch_001", "operation_id": kw.pop("op", "ch_001.op1")}
    base.update(kw)
    return base


def write_inbox_proposal(book, obj, name="ch_001.json"):
    (book / "state" / "inbox" / name).write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


# ---------------- 校验层 ----------------

def test_envelope_rules():
    errs, _ = state.validate_proposal({"chapter": "ch_1"})
    assert any("schema" in e for e in errs)
    errs, _ = state.validate_proposal({"schema": OP, "chapter": "ch_001"})  # 缺 operation_id
    assert any("operation_id" in e for e in errs)
    errs, _ = state.validate_proposal(proposal(**{"candidate_current": {}}))
    assert any("候选字段" in e for e in errs)
    errs, _ = state.validate_proposal(proposal(_draft=True))
    assert any("草稿提案" in e for e in errs)
    errs, _ = state.validate_proposal(proposal(), expected_chapter="ch_002")
    assert any("不一致" in e for e in errs)


def test_ledger_money_rules():
    p = proposal(ledger={"transactions": [
        {"pool": "standard_currency", "delta": 3.5, "subject": "浮点款"},
        {"pool": "standard_currency", "delta": -50, "type": "income", "subject": "负收入"},
        {"pool": "standard_currency", "delta": 10},  # 缺 subject
    ]})
    errs, _ = state.validate_proposal(p)
    assert any("整数" in e for e in errs)
    assert any("income" in e for e in errs)
    assert any("subject" in e for e in errs)


def test_lines_rules():
    errs, _ = state.validate_proposal(proposal(lines=[{"kind": "weird"}]))
    assert any("kind" in e for e in errs)
    errs, _ = state.validate_proposal(proposal(lines=[{"kind": "foreshadow", "action": "resolve"}]))
    assert any("必须提供 id" in e for e in errs)
    one = [{"kind": "misunderstanding", "action": "remind", "id": "MIS-001"}]
    errs, _ = state.validate_proposal(proposal(lines=one))
    assert any("remind 只适用于 foreshadow" in e for e in errs)
    one = [{"kind": "foreshadow", "action": "plant", "name": "x", "id": "BAD-1"}]
    errs, _ = state.validate_proposal(proposal(lines=one))
    assert any("GUN-" in e for e in errs)


def test_target_ch_normalization():
    assert state._norm_target(18) == (18, None)
    assert state._norm_target("第 18 章") == (18, None)
    assert state._norm_target("longline") == ("longline", None)
    assert state._norm_target(None) == ("longline", None)
    _, err = state._norm_target("随便写")
    assert err


# ---------------- 合并语义（内存事务） ----------------

def test_apply_merges_all_sections(tmp_path):
    book = make_book(tmp_path)
    p = proposal(
        current={"location": "青石镇", "present_characters": ["沈拓"]},
        entities=[{"action": "upsert", "name": "沈拓", "type": "person", "aliases": ["拓哥"], "summary": "镇渊守卒"}],
        lines=[{"kind": "foreshadow", "action": "plant", "name": "黑玉佩", "target_ch": "第12章"},
               {"kind": "misunderstanding", "action": "plant", "parties": "沈拓↔村长", "content": "玉佩是赃物"}],
        timeline={"events": [{"time": "第三夜", "event": "渊口异动"}],
                  "arcs": [{"name": "沈拓", "stage": "蒙昧→疑心", "strategy": "守口如瓶"}]},
        ledger={"transactions": [{"pool": "standard_currency", "delta": 100, "subject": "赏钱"},
                                 {"pool": "standard_currency", "delta": -40, "type": "expense", "subject": "买药"}]},
        synopsis={"text": "沈拓夜里巡渊，捡得黑玉佩。", "title": "渊口"},
    )
    rep = state.apply_proposal(book, p)
    assert rep["errors"] == []
    cur = state.load_state(book, "current")
    assert cur["location"] == "青石镇"
    lines = state.load_state(book, "lines")
    assert lines["foreshadows"][0]["id"] == "GUN-001"
    assert lines["foreshadows"][0]["target_ch"] == 12
    assert lines["misunderstandings"][0]["id"] == "MIS-001"
    led = state.load_state(book, "ledger")
    assert led["pools"]["standard_currency"]["current"] == 60
    assert [t["balance_after"] for t in led["transactions"]] == [100, 60]
    tl = state.load_state(book, "timeline")
    assert tl["events"][0]["chapter"] == "ch_001"
    assert tl["arcs"][0]["strategy_history"][0]["strategy"] == "守口如瓶"
    syn = state.load_state(book, "synopsis")
    assert syn["chapters"]["ch_001"]["source"] == "manual"


def test_idempotent_duplicate_skipped(tmp_path):
    book = make_book(tmp_path)
    p = proposal(ledger={"transactions": [{"pool": "standard_currency", "delta": 100, "subject": "赏钱"}]})
    assert state.apply_proposal(book, p)["errors"] == []
    rep2 = state.apply_proposal(book, p)  # 同 op 同内容 → duplicate skip
    assert rep2.get("duplicate") is True
    led = state.load_state(book, "ledger")
    assert len(led["transactions"]) == 1  # 不重复记账


def test_operation_id_conflict_rejected(tmp_path):
    book = make_book(tmp_path)
    assert state.apply_proposal(book, proposal(current={"location": "A"}))["errors"] == []
    rep = state.apply_proposal(book, proposal(current={"location": "B"}))  # 同 op 异内容
    assert any("拒绝复用" in e for e in rep["errors"])
    assert state.load_state(book, "current")["location"] == "A"


def test_same_content_hash_dedupe_across_op_ids(tmp_path):
    book = make_book(tmp_path)
    state.apply_proposal(book, proposal(op="a1", current={"location": "A"}))
    rep = state.apply_proposal(book, proposal(op="a2", current={"location": "A"}))
    assert rep.get("duplicate") is True


def test_fact_conflict_blocks_all_writes(tmp_path):
    """事务性：lines 分区出错时，同提案里合法的 current/ledger 也必须一个字节不落。"""
    book = make_book(tmp_path)
    p = proposal(
        current={"location": "青石镇"},
        ledger={"transactions": [{"pool": "standard_currency", "delta": 100, "subject": "赏钱"}]},
        lines=[{"kind": "foreshadow", "action": "resolve", "id": "GUN-999"}],
    )
    rep = state.apply_proposal(book, p)
    assert any("GUN-999" in e for e in rep["errors"])
    assert state.load_state(book, "current")["location"] == ""
    assert state.load_state(book, "ledger")["transactions"] == []


def test_unknown_pool_error(tmp_path):
    book = make_book(tmp_path)
    led = {"transactions": [{"pool": "ghost", "delta": 10, "subject": "x"}]}
    rep = state.apply_proposal(book, proposal(ledger=led))
    assert any("未声明资源池" in e for e in rep["errors"])


def test_pool_declaration_in_proposal(tmp_path):
    book = make_book(tmp_path)
    p = proposal(ledger={"pools": {"spirit_stones": {"name": "灵石", "unit": "枚", "initial": 5}},
                         "transactions": [{"pool": "spirit_stones", "delta": -2, "subject": "买符"}]})
    assert state.apply_proposal(book, p)["errors"] == []
    led = state.load_state(book, "ledger")
    assert led["pools"]["spirit_stones"]["current"] == 3
    assert led["transactions"][0]["type"] == "expense"  # 引擎按符号补全 type


def test_ledger_tampering_detected_by_verify(tmp_path):
    """状态文件被手改（伪报余额）→ 只读体检必须抓出（下次合并时引擎会重算自纠）。"""
    book = make_book(tmp_path)
    state.apply_proposal(book, proposal(
        ledger={"transactions": [{"pool": "standard_currency", "delta": 100, "subject": "赏钱"}]}))
    lp = book / "state" / "ledger.json"
    led = json.loads(lp.read_text(encoding="utf-8"))
    led["pools"]["standard_currency"]["current"] = 999
    common.dump_json(lp, led)
    errors = state.verify_state(book)
    assert any("流水累计" in e for e in errors)


def test_duplicate_plant_id_rejected(tmp_path):
    book = make_book(tmp_path)
    p = proposal(lines=[{"kind": "foreshadow", "action": "plant", "id": "GUN-001", "name": "玉佩"}])
    assert state.apply_proposal(book, p)["errors"] == []
    rep = state.apply_proposal(book, proposal(
        op="x2", lines=[{"kind": "foreshadow", "action": "plant", "id": "GUN-001", "name": "撞车"}]))
    assert any("已存在" in e for e in rep["errors"])


def test_corrupt_state_file_refuses_merge(tmp_path):
    book = make_book(tmp_path)
    (book / "state" / "lines.json").write_text("{broken", encoding="utf-8")
    rep = state.apply_proposal(book, proposal(current={"location": "X"}))
    assert any("SSOT 不可用" in e for e in rep["errors"])
    assert not (book / "state" / ".applied_operations.json").exists()  # 异常路径不写 marker


# ---------------- 收件箱 / sync 语义 ----------------

def test_apply_inbox_archive_to_failed(tmp_path):
    book = make_book(tmp_path)
    inbox = book / "state" / "inbox"
    write_inbox_proposal(book, proposal(lines=[{"kind": "foreshadow", "action": "resolve", "id": "GUN-777"}]))
    overall = state.apply_inbox(book, expect_chapter="ch_001")
    assert overall["failed"] == 1
    assert (inbox / "failed" / "ch_001.json").exists()
    assert not (inbox / "ch_001.json").exists()


def test_failed_pickup_then_success(tmp_path):
    book = make_book(tmp_path)
    inbox = book / "state" / "inbox"
    write_inbox_proposal(book, proposal(lines=[{"kind": "foreshadow", "action": "resolve", "id": "GUN-777"}]))
    state.apply_inbox(book, expect_chapter="ch_001")  # → failed/
    # 修复：直接改写 failed/ 里的提案（SOP 允许），sync 自动捡回
    (inbox / "failed" / "ch_001.json").write_text(
        json.dumps(proposal(current={"location": "渊口"}), ensure_ascii=False), encoding="utf-8")
    overall = state.apply_inbox(book, expect_chapter="ch_001")
    assert overall["picked_up"] is True
    assert overall["applied"] == 1
    assert state.load_state(book, "current")["location"] == "渊口"
    assert (inbox / "processed" / "ch_001.json").exists()


def test_other_chapter_stays_in_inbox(tmp_path):
    book = make_book(tmp_path)
    inbox = book / "state" / "inbox"
    write_inbox_proposal(book, proposal(op="c2", chapter="ch_002", current={"location": "A"}), "ch_002.json")
    write_inbox_proposal(book, proposal(op="c3", chapter="ch_003", current={"location": "B"}), "ch_003.json")
    overall = state.apply_inbox(book, expect_chapter="ch_002")
    assert overall["applied"] == 1 and overall["skipped"] == 1
    assert (inbox / "ch_003.json").exists()
    assert state.load_state(book, "current")["location"] == "A"  # 只合并了 ch_002 的提案


def test_draft_and_template_not_merged(tmp_path):
    book = make_book(tmp_path)
    inbox = book / "state" / "inbox"
    (inbox / "ch_002.draft.json").write_text("{}", encoding="utf-8")
    (inbox / "ch_sample.template.json").write_text("{}", encoding="utf-8")
    overall = state.apply_inbox(book, expect_chapter="ch_002")
    assert overall["applied"] == 0 and overall["failed"] == 0
    assert (inbox / "ch_002.draft.json").exists()  # 不消费、不归档


def test_dry_run_touches_nothing(tmp_path):
    book = make_book(tmp_path)
    write_inbox_proposal(book, proposal(current={"location": "青石镇"}))
    state.apply_inbox(book, expect_chapter="ch_001", dry_run=True)
    assert state.load_state(book, "current")["location"] == ""
    assert (book / "state" / "inbox" / "ch_001.json").exists()  # 未归档


def test_archive_collision_never_overwrites(tmp_path):
    """failed/ 已有同名审计文件时，第二个失败提案必须编号共存，绝不覆盖。"""
    book = make_book(tmp_path)
    inbox = book / "state" / "inbox"
    for _ in range(2):
        write_inbox_proposal(book, proposal(
            op="x", lines=[{"kind": "foreshadow", "action": "resolve", "id": "GUN-777"}]))
        state.apply_inbox(book, expect_chapter="ch_001")
        assert (inbox / "failed" / "ch_001.json").exists() or (inbox / "failed" / "ch_001.2.json").exists()
    assert (inbox / "failed" / "ch_001.json").exists()
    assert (inbox / "failed" / "ch_001.2.json").exists()
