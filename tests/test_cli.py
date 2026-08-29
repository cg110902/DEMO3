"""CLI 壳契约：9 命令全实现、帮助目录、status/init 基本行为、退出码。"""
import json

from engine import cli


def test_help_json_lists_nine_commands(tmp_path, capsys):
    assert cli.main(["help", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    names = {c["name"] for c in payload["commands"]}
    assert names == {"status", "init", "pack", "evidence", "check", "sync", "snapshot", "export", "help"}
    assert payload["version"]


def test_no_unimplemented_commands_left():
    """M4 后契约：9 命令全部接线；重新引入 _stub 必须先改 PLAN（防偷懒回潮）。"""
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
