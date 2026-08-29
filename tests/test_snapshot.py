"""快照/回滚/manifest 完整性测试 + sync CLI 端到端。"""
import json
from pathlib import Path

from engine import cli, snapshot, state


def _init(tmp_path) -> Path:
    book = Path(tmp_path) / "b"
    assert cli.main(["init", "-w", str(book), "-t", "快照测试"]) == 0
    return book


def _sync_book_ready(book: Path, ch: str = "ch_001") -> None:
    (book / "manuscript" / "vol_01" / "final").mkdir(parents=True, exist_ok=True)
    (book / "manuscript" / "vol_01" / "final" / f"{ch}.md").write_text("# 第一章\n正文，字数够。", encoding="utf-8")
    prop = {"schema": "novel-studio.state-mutation/v2", "chapter": ch, "operation_id": f"{ch}.op1",
            "current": {"location": "渊口"}}
    (book / "state" / "inbox" / f"{ch}.json").write_text(json.dumps(prop, ensure_ascii=False), encoding="utf-8")


def test_create_list_and_name_safety(tmp_path):
    book = _init(tmp_path)
    ok, name = snapshot.create_snapshot(book, "ch_001_done")
    assert ok and name.endswith("_ch_001_done")
    assert snapshot.list_snapshots(book) == [name]
    manifest = json.loads((book / "state" / "snapshots" / name / "manifest.json").read_text(encoding="utf-8"))
    assert set(manifest["files"]) >= {"current.json", "ledger.json", "synopsis.json", "timeline.json"}
    for bad in ("../evil", ".hidden", ""):
        try:
            snapshot.create_snapshot(book, bad)
            raise AssertionError(f"非法名未被拒绝: {bad!r}")
        except ValueError:
            pass


def test_rollback_restores_state_and_marker(tmp_path):
    book = _init(tmp_path)
    _sync_book_ready(book)
    assert cli.main(["sync", "ch_001", "-w", str(book)]) == 0
    assert state.load_state(book, "current")["location"] == "渊口"
    marker_after_1 = json.loads((book / "state" / ".applied_operations.json").read_text(encoding="utf-8"))
    assert "ch_001.op1" in marker_after_1

    # 再推进一章
    _sync_book_ready(book, "ch_002")
    (book / "state" / "inbox" / "ch_002.json").write_text(json.dumps(
        {"schema": "novel-studio.state-mutation/v2", "chapter": "ch_002", "operation_id": "ch_002.op1",
         "current": {"location": "镇内"}}, ensure_ascii=False), encoding="utf-8")
    assert cli.main(["sync", "ch_002", "-w", str(book)]) == 0
    assert state.load_state(book, "current")["location"] == "镇内"

    ok, msg, chosen = snapshot.rollback_snapshot(book, "ch_001_done")
    assert ok, msg
    assert state.load_state(book, "current")["location"] == "渊口"
    # 幂等登记簿一起回滚：ch_002 的操作记录不应存在（否则重放 ch_002 会被误判已应用）
    marker = json.loads((book / "state" / ".applied_operations.json").read_text(encoding="utf-8"))
    assert "ch_001.op1" in marker and "ch_002.op1" not in marker
    # 回滚前现场自动备份，可再滚回去
    pre = [d for d in (book / "state" / "snapshots").iterdir() if d.name.startswith("pre_rollback_")]
    assert pre


def test_corrupt_snapshot_refuses_rollback(tmp_path):
    book = _init(tmp_path)
    ok, name = snapshot.create_snapshot(book, "chk")
    f = book / "state" / "snapshots" / name / "current.json"
    f.write_text('{"time": "篡改"}', encoding="utf-8")
    ok, msg, _ = snapshot.rollback_snapshot(book, "chk")
    assert not ok and "完整性校验失败" in msg


def test_sync_pipeline_end_to_end(tmp_path, capsys):
    book = _init(tmp_path)
    _sync_book_ready(book)
    rc = cli.main(["sync", "1", "-w", str(book)])  # 数字章节号也可
    assert rc == 0
    snaps = snapshot.list_snapshots(book)
    assert any(s.endswith("ch_001_done") for s in snaps)
    # 审计链完整：processed 有提案、status 流水线行全绿
    assert (book / "state" / "inbox" / "processed" / "ch_001.json").exists()
    capsys.readouterr()
    rc = cli.main(["status", "--json", "-w", str(book)])
    brief = json.loads(capsys.readouterr().out)
    row = {r["chapter"]: r for r in brief["pipeline"]}["ch_001"]
    assert row["final"] and row["proposal_merged"] and row["snapshot"]


def test_sync_guards(tmp_path, capsys):
    book = _init(tmp_path)
    # 无稿件无提案 → 拒
    assert cli.main(["sync", "ch_001", "-w", str(book)]) == 1
    assert "拒绝空同步" in capsys.readouterr().out
    # 非法章节号 → 退出码 2
    assert cli.main(["sync", "abc", "-w", str(book)]) == 2
    # 有稿件无提案 → 仍拒
    (book / "manuscript" / "vol_01" / "final" / "ch_001.md").write_text("# x\n中文", encoding="utf-8")
    assert cli.main(["sync", "ch_001", "-w", str(book)]) == 1
    # dry-run 不受守卫限制（允许预览）
    assert cli.main(["sync", "ch_001", "-w", str(book), "--dry-run"]) == 0


def test_sync_failure_blocks_snapshot(tmp_path):
    """提案带病 → 合并失败 → 不体检、不封存快照（sync 返回非 0）。"""
    book = _init(tmp_path)
    _sync_book_ready(book)
    bad = {"schema": "novel-studio.state-mutation/v2", "chapter": "ch_001", "operation_id": "bad.op",
           "lines": [{"kind": "foreshadow", "action": "resolve", "id": "GUN-777"}]}
    (book / "state" / "inbox" / "ch_001.json").write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
    rc = cli.main(["sync", "ch_001", "-w", str(book)])
    assert rc == 1
    assert not snapshot.list_snapshots(book)
    assert (book / "state" / "inbox" / "failed" / "ch_001.json").exists()


def test_rollback_clean_drafts(tmp_path):
    book = _init(tmp_path)
    _sync_book_ready(book)
    assert cli.main(["sync", "ch_001", "-w", str(book)]) == 0
    # 制造 ch_002 的孤立稿件与细纲
    (book / "manuscript" / "vol_01" / "raw" / "ch_002_v1.md").write_text("草稿", encoding="utf-8")
    (book / "outlines" / "vol_01" / "beats" / "ch_002.md").write_text("beats", encoding="utf-8")
    rc = cli.main(["snapshot", "rollback", "ch_001_done", "--clean-drafts", "-w", str(book)])
    assert rc == 0
    assert not (book / "manuscript" / "vol_01" / "raw" / "ch_002_v1.md").exists()
    assert not (book / "outlines" / "vol_01" / "beats" / "ch_002.md").exists()
    # 当前章稿件（≤ 快照章号）不受影响
    assert (book / "manuscript" / "vol_01" / "final" / "ch_001.md").exists()
