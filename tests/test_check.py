"""check 体检：五类埋雷必须全抓 + 健康书必须零 errors + CLI 退出码契约。

errors 只允许事实级（schema/算术/结构）；本文件同时冻结 check 的 JSON 顶层契约 key。
"""
import json
from pathlib import Path

from engine import checks, cli, common, state


def _mkbook(tmp_path, *, healthy=False) -> Path:
    book = Path(tmp_path) / "b"
    common.dump_json(book / "project.json", {
        "schema": "novel-studio.project/v1", "title": "渊火记", "genre": "悬疑玄幻",
        "mode": "automatic", "words_target": [20, 40], "style_guards": ["嘴角勾起一抹弧度"]})
    state.init_state(book)
    fin = book / "manuscript" / "vol_01" / "final"
    raw = book / "manuscript" / "vol_01" / "raw"
    beats = book / "outlines" / "vol_01" / "beats"
    for d in (fin, raw, beats):
        d.mkdir(parents=True, exist_ok=True)
    if healthy:
        (fin / "ch_001.md").write_text("第一章正文。" * 3, encoding="utf-8")
        (raw / "ch_001_v1.md").write_text("草稿", encoding="utf-8")
        (beats / "ch_001.md").write_text("---\nform: 单场景章\n---\n\n拍点。\n", encoding="utf-8")
        return book

    # ---- 埋五雷 ----
    # ① final 断档：001、003 有，002 缺
    (fin / "ch_001.md").write_text("第一章正文正文正文。" * 2, encoding="utf-8")
    (fin / "ch_003.md").write_text("短。", encoding="utf-8")  # 兼触发字数带外 warning
    # ② 未登记实体引用
    rep = state.apply_proposal(book, {"schema": "novel-studio.state-mutation/v2",
                                      "chapter": "ch_001", "operation_id": "a.op",
                                      "entities": [{"action": "upsert", "name": "沈拓", "type": "person"}],
                                      "current": {"present_characters": ["沈拓", "李四"]},
                                      "lines": [{"kind": "foreshadow", "action": "plant",
                                                 "name": "逾期线", "target_ch": 1}]})
    assert rep["errors"] == []
    # ③ 账本篡改
    state.apply_proposal(book, {"schema": "novel-studio.state-mutation/v2", "chapter": "ch_001",
                                "operation_id": "b.op",
                                "ledger": {"transactions": [{"pool": "standard_currency",
                                                             "delta": 100, "subject": "赏钱"}]}})
    led = common.load_json(book / "state" / "ledger.json")
    led["pools"]["standard_currency"]["current"] = 999
    common.dump_json(book / "state" / "ledger.json", led)
    # ④ 未填槽位
    (book / "bible").mkdir(exist_ok=True)
    (book / "bible" / "world.md").write_text("主题：{{slot:theme|一句话主题}}\n", encoding="utf-8")
    # ⑤ 同 form 连章无理由（001/002 同 form）
    (beats / "ch_001.md").write_text("---\nform: 单场景章\n---\n\n拍点。\n", encoding="utf-8")
    (beats / "ch_002.md").write_text("---\nform: 单场景章\n---\n\n拍点。\n", encoding="utf-8")
    (raw / "ch_001_v1.md").write_text("草稿草稿草稿草稿草稿草稿草稿。", encoding="utf-8")
    return book


def test_check_catches_all_planted_problems(tmp_path):
    report = checks.run_checks(_mkbook(tmp_path))
    codes = {e["code"] for e in report["errors"]}
    assert {"final_gap_chapters", "unregistered_character", "state_inconsistent",
            "unfilled_slot", "beats_form_repeat_without_reason"} <= codes
    warns = {w["code"] for w in report["warnings"]}
    assert "word_band_deviation" in warns and "line_overdue" in warns and "final_without_raw" in warns
    assert report["ok"] is False
    assert report["stats"]["errors"] == len(report["errors"])


def test_healthy_book_passes(tmp_path):
    report = checks.run_checks(_mkbook(tmp_path, healthy=True))
    assert report["errors"] == []
    assert report["ok"] is True
    assert set(report) == {"schema", "ok", "errors", "warnings", "stats"}


def test_check_output_has_zero_judgement_words(tmp_path):
    flat = json.dumps(checks.run_checks(_mkbook(tmp_path)), ensure_ascii=False)
    for banned in ("建议", "可疑", "疑似", "不宜", "最好", "达标"):
        assert banned not in flat


def test_cli_check_exit_codes_and_json(tmp_path, capsys):
    book = _mkbook(tmp_path)
    assert cli.main(["check", "-w", str(book)]) == 1
    capsys.readouterr()
    assert cli.main(["check", "--json", "-w", str(book)]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["ok"] is False and report["errors"]
    good = _mkbook(tmp_path / "h", healthy=True)
    assert cli.main(["check", "-w", str(good)]) == 0


def test_cli_evidence_exit_codes(tmp_path, capsys):
    book = _mkbook(tmp_path, healthy=True)
    assert cli.main(["evidence", "words", "-w", str(book)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["kind"] == "words" and out["chapter_count"] == 1
    assert cli.main(["evidence", "gaps", "多余参数", "-w", str(book)]) == 2
    assert cli.main(["evidence", "mentions", "路人甲", "-w", str(book)]) == 2
    capsys.readouterr()
    assert cli.main(["evidence", "mentions", "-w", str(book)]) == 0  # 空注册表总览=合法事实
