"""CLI 壳契约：9 命令全实现、帮助目录、status/init 基本行为、退出码。"""
import json

from engine import cli


def test_help_json_lists_all_commands(tmp_path, capsys):
    assert cli.main(["help", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    names = {c["name"] for c in payload["commands"]}
    assert names == {"status", "init", "pack", "evidence", "check", "sync", "snapshot",
                     "export", "help", "proposal"}   # M6-P3：9→10，提案骨架入列
    assert payload["version"]


def test_no_unimplemented_commands_left():
    """M4 后契约：全部命令接线；重新引入 _stub 必须先改 PLAN（防偷懒回潮）。"""
    assert cli.NOT_IMPLEMENTED == {}


def test_status_without_any_book(tmp_path, capsys):
    rc = cli.main(["status", "--json", "-w", str(tmp_path / "nonexistent")])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["exists"] is False
    assert "init" in out["next_action"]  # 断线自愈：第一步永远是给到 init 指向


def test_init_creates_and_guards(tmp_path, capsys):
    book = tmp_path / "b"
    assert cli.main(["init", "-w", str(book), "-t", "测试书"]) == 0
    assert (book / "project.json").is_file()
    for key in cli.state.STATE_KEYS if hasattr(cli, "state") else ("current", "entities", "lines", "timeline", "ledger", "synopsis"):
        assert (book / "state" / f"{key}.json").is_file()
    # 重复 init → 拒绝；--force 放行
    assert cli.main(["init", "-w", str(book)]) == 1
    out = capsys.readouterr().out
    assert "--force" in out
    assert cli.main(["init", "-w", str(book), "--force", "-t", "测试书"]) == 0
    # --clean 清稿保留书
    draft = book / "manuscript" / "vol_01" / "final" / "ch_001.md"
    draft.write_text("草稿", encoding="utf-8")
    assert cli.main(["init", "-w", str(book), "--clean"]) == 0
    assert not draft.exists()
    assert (book / "project.json").is_file()


def test_missing_book_blocks_commands(tmp_path, capsys):
    ghost = str(tmp_path / "ghost")
    assert cli.main(["pack", "ch_001", "-w", ghost]) == 1
    assert cli.main(["check", "-w", ghost]) == 1
    assert cli.main(["sync", "ch_001", "-w", ghost]) == 1
    assert cli.main(["export", "-w", ghost]) == 1


def test_snapshot_list_explicit_subcommand(tmp_path):
    book = tmp_path / "b"
    rc = cli.main(["init", "-w", str(book), "-t", "列表", "-g", "都市", "-p", "甲"])
    assert rc == 0
    (book / "state" / "snapshots").mkdir(parents=True, exist_ok=True)
    (book / "state" / "snapshots" / "20260101_000000_ch_001_done").mkdir()
    import contextlib
    import io
    import json
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = cli.main(["snapshot", "list", "-w", str(book)])
    assert rc == 0 and "ch_001_done" in buf.getvalue()   # 文档口径的显式 list 必须可用
    buf2 = io.StringIO()
    with contextlib.redirect_stdout(buf2):
        rc = cli.main(["snapshot", "list", "-w", str(book), "--json"])
    data = json.loads(buf2.getvalue())
    assert rc == 0 and any(n.endswith("ch_001_done") for n in data["snapshots"])


def test_proposal_new_skeleton(tmp_path):
    book = tmp_path / "b"
    assert cli.main(["init", "-w", str(book), "-t", "骨", "-g", "都市", "-p", "甲"]) == 0
    import contextlib
    import io
    buf, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
        rc = cli.main(["proposal", "new", "7", "-w", str(book)])
    sk = json.loads(buf.getvalue())
    assert rc == 0
    assert sk["chapter"] == "ch_007" and sk["operation_id"].startswith("ch_007.syncer.")
    assert sk["schema"] == "novel-studio.state-mutation/v2"
    assert set(sk) >= {"current", "entities", "lines", "ledger", "timeline", "synopsis"}
    # 骨架原样提交必须能通过校验（预填即合法形状）
    from engine import state
    (book / "state" / "inbox").mkdir(parents=True, exist_ok=True)
    (book / "state" / "inbox" / "ch_007.json").write_text(json.dumps(sk), encoding="utf-8")
    rep = state.apply_inbox(book, expect_chapter="ch_007", dry_run=True)
    assert rep["applied"] + rep["skipped"] + rep["failed"] >= 0 and rep["failed"] == 0
    # 在途提案占位时拒绝再造骨架（与 sync 闸门同一事实）
    assert cli.main(["proposal", "new", "7", "-w", str(book)]) == 1


def test_evidence_all_and_file(tmp_path):
    from engine import common
    book = tmp_path / "b"
    common.dump_json(book / "project.json", {"schema": "novel-studio.project/v1",
        "title": "双", "genre": "都市", "mode": "automatic",
        "words_target": [20, 4000], "style_guards": ["嘴角勾起一抹弧度"]})
    from engine import state
    state.init_state(book)
    fin = book / "manuscript/vol_01/final"
    fin.mkdir(parents=True)
    (fin / "ch_001.md").write_text("# 第一章\n\n他说好。\n\n他说行。嘴角勾起一抹弧度。\n", encoding="utf-8")
    raw = book / "manuscript/vol_01/raw"
    raw.mkdir(parents=True)
    (raw / "ch_002_v1.md").write_text("# 第二章\n\n阿冒掀开抽屉。空的。\n", encoding="utf-8")
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = cli.main(["evidence", "all", "-w", str(book)])
    payload = json.loads(buf.getvalue())
    assert rc == 0 and set(payload) == {"kind", "words", "style", "form", "dup", "gaps"}
    assert payload["style"]["chapters"][0]["style_guards_hits"] == {"嘴角勾起一抹弧度": 1}
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = cli.main(["evidence", "file", "manuscript/vol_01/raw/ch_002_v1.md", "-w", str(book)])
    f = json.loads(buf.getvalue())
    assert rc == 0 and f["kind"] == "file" and f["cjk"] > 0
    assert "error" not in f
    # 路径逃逸与缺失 → rc1
    assert cli.main(["evidence", "file", "../../etc/passwd", "-w", str(book)]) == 1
    assert cli.main(["evidence", "file", "no/such.md", "-w", str(book)]) == 1
