"""check 体检：五类埋雷必须全抓 + 健康书必须零 errors + CLI 退出码契约。

errors 只允许事实级（schema/算术/结构）；本文件同时冻结 check 的 JSON 顶层契约 key。
"""
import json
import pathlib
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


def test_beats_fm_extra_keys_rejected(tmp_path):
    # AGENTS 禁令6：front-matter 超键 = 工程痕迹，check 必须拦（白名单=craft#front-matter 键）
    book = _mkbook(tmp_path, healthy=True)
    b = book / "outlines/vol_01/beats/ch_001.md"
    b.write_text("---\nform: 单场景章\nquota: 静章\nscratch: 42\n---\n\n拍点。\n", encoding="utf-8")
    rep = checks.run_checks(book)
    hit = [e for e in rep["errors"] if e["code"] == "beats_fm_extra_keys"]
    assert len(hit) == 1 and "quota" in hit[0]["msg"] and "scratch" in hit[0]["msg"]
    # 合法六键+form_reason 必须放行（防误伤）
    b.write_text("---\nchapter: ch_001\nvol: vol_01\nform: 单场景章\npov: 甲\n"
                 "words: 20-40\nstyle_notes: 贴耳\nform_reason: 剧情需要\n---\n\n拍点。\n",
                 encoding="utf-8")
    assert [e for e in checks.run_checks(book)["errors"]
            if e["code"] == "beats_fm_extra_keys"] == []


# ---------------- P1 review_gate：验收覆盖机械核对 ----------------

def _gate_book(tmp_path, *, k_accept=3, review=None):
    book = pathlib.Path(tmp_path) / "g"
    common.dump_json(book / "project.json", {"schema": "novel-studio.project/v1",
        "title": "闸", "genre": "都市", "mode": "automatic",
        "words_target": [10, 4000], "style_guards": []})
    (book / "outlines/vol_01/beats").mkdir(parents=True, exist_ok=True)
    acc = "\n".join(f"{i}. 条目{i}。" for i in range(1, k_accept + 1))
    (book / "outlines/vol_01/beats/ch_001.md").write_text(
        f"---\nform: 单场景章\n---\n## 验收\n{acc}\n", encoding="utf-8")
    if review is not None:
        (book / "log/review").mkdir(parents=True, exist_ok=True)
        (book / "log/review/ch_001.md").write_text(review, encoding="utf-8")
    return book


def test_review_gate_rules(tmp_path):
    # 无「验收」节 → 放行
    b = _gate_book(tmp_path, k_accept=0)
    assert checks.review_gate(b, "ch_001") == []
    # 注记不存在 → 放行（代笔例外，不新增闸门）
    b = _gate_book(tmp_path)
    assert checks.review_gate(b, "ch_001") == []
    # 缺答 + 无判定符 + ✓短证据 → 三条全报
    b = _gate_book(tmp_path, review="## 验收打钩\n\n1. 条目一：✓——正文有\n2. 条目二：写过了但没有勾\n")
    issues = checks.review_gate(b, "ch_001")
    assert len(issues) == 3
    assert any("[3]" in i for i in issues) and any("判定符" in i for i in issues) \
        and any("证据线过短" in i for i in issues)
    # 全部合规 → 零问题
    ok = ("## 验收打钩\n\n"
          "1. 条目一：✓——「甲推门。」正文首段，位置明确可复查\n"
          "2. 条目二：✗ 拒收级——正文无此动作，仅计划\n"
          "3. 条目三：✓——evidence words cjk=1858 落带内，见 style 输出\n")
    b = _gate_book(tmp_path, review=ok)
    assert checks.review_gate(b, "ch_001") == []


def test_beats_guard_extra_key_allowed(tmp_path):
    # P2：guard_extra 是合法键（超出七键白名单扩展后的八键），不得误拦
    book = _mkbook(tmp_path, healthy=True)
    b = book / "outlines/vol_01/beats/ch_001.md"
    b.write_text("---\nform: 单场景章\nguard_extra: 数|灯花\n---\n\n拍点。\n", encoding="utf-8")
    assert [e for e in checks.run_checks(book)["errors"]
            if e["code"] == "beats_fm_extra_keys"] == []


def test_candidate_leak_blocked(tmp_path):
    # AGENTS 禁令6 兑付：candidate_* 工程痕迹禁入稿件（check 拦，D3 清点落地）
    book = _mkbook(tmp_path, healthy=True)
    f = book / "manuscript/vol_01/final/ch_001.md"
    f.write_text("# 第一章\n\n正文。\n\ncandidate_2 号方案\n", encoding="utf-8")
    errs = [e for e in checks.run_checks(book)["errors"] if e["code"] == "candidate_leak"]
    assert len(errs) == 1 and "ch_001" in errs[0]["msg"]
