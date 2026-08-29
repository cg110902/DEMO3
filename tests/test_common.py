"""engine/common 底座不变量：章节号口径、IO 安全、哈希与锁。"""
import json

import pytest

from engine import common


def test_chapter_token_normalization():
    assert common.chapter_token_to_num("7") == 7
    assert common.chapter_token_to_num("ch_007") == 7
    assert common.chapter_token_to_num(3) == 3
    assert common.chapter_token_to_num("第 12 章") == 12
    assert common.chapter_token_to_num("chapter_005_draft") == 5
    assert common.chapter_token_to_num("abc") is None
    assert common.chapter_token_to_num(0) is None
    assert common.chapter_token_to_num(True) is None


def test_chapter_number_from_name():
    assert common.chapter_number_from_name("ch_012.md") == 12
    assert common.chapter_number_from_name("ch_012_v3.md") == 12
    assert common.chapter_number_from_name("random.md") is None


def test_file_matches_chapter():
    assert common.file_matches_chapter("ch_007_v2.md", 7)
    assert common.file_matches_chapter("ch_007.md", "ch_007")
    assert not common.file_matches_chapter("ch_008.md", "7")
    assert common.file_matches_chapter("ch_008.md", None)


def test_find_and_sort_chapter_files(tmp_path):
    d = tmp_path / "manuscript" / "vol_01" / "final"
    d.mkdir(parents=True)
    for name in ("ch_010.md", "ch_002.md", "ch_001.md"):
        (d / name).write_text("# x", encoding="utf-8")
    got = [f.name for f in common.find_chapter_files(tmp_path, "final")]
    assert got == ["ch_001.md", "ch_002.md", "ch_010.md"]
    assert [f.name for f in common.find_chapter_files(tmp_path, "final", 2)] == ["ch_002.md"]
    assert common.latest_chapter_number(tmp_path) == 10


def test_est_tokens_rounding_and_cjk():
    assert common.est_tokens("") == 0
    assert common.est_tokens("中文中文") == 4          # 纯中文不多算（历史 bug 钉死）
    assert common.est_tokens("abcd") == 1
    assert common.est_tokens("abcde") == 2              # ASCII 向上取整
    assert common.est_tokens("中ab") == 1 + 1
    assert common.cjk_count("你好,world！") == 2


def test_atomic_write_and_json_roundtrip(tmp_path):
    p = tmp_path / "a" / "b.json"
    common.dump_json(p, {"乙": 1, "甲": [1, 2]})
    assert json.loads(p.read_text(encoding="utf-8")) == {"甲": [1, 2], "乙": 1}
    assert not list(p.parent.glob("*.tmp"))             # 临时文件清干净
    assert common.load_json(p, default={})["乙"] == 1


def test_corrupt_json_raises_never_defaults(tmp_path):
    p = tmp_path / "c.json"
    p.write_text("{broken", encoding="utf-8")
    with pytest.raises(ValueError):
        common.load_json(p, default={})                 # 损坏 ≠ 缺失：default 不救损坏
    with pytest.raises(ValueError):
        common.load_json(tmp_path / "missing.json")     # 缺失无 default 也抛


def test_canonical_hash_order_insensitive():
    h1 = common.canonical_json_hash({"a": 1, "b": {"x": 1, "y": 2}})
    h2 = common.canonical_json_hash({"b": {"y": 2, "x": 1}, "a": 1})
    assert h1 == h2
    assert h1 != common.canonical_json_hash({"a": 2})


def test_file_lock_mutual_exclusion(tmp_path):
    with common.file_lock(tmp_path, name=".t.lock"), pytest.raises(TimeoutError), \
            common.file_lock(tmp_path, name=".t.lock", timeout=0.1):
        pass
    # 释放后可再拿
    with common.file_lock(tmp_path, name=".t.lock", timeout=0.5):
        pass


def test_safe_child_path_blocks_escape(tmp_path):
    (tmp_path / "ok.md").write_text("x", encoding="utf-8")
    assert common.safe_child_path(tmp_path, "ok.md").name == "ok.md"
    with pytest.raises(ValueError):
        common.safe_child_path(tmp_path, "../outside.md")


def test_parse_front_matter():
    text = "---\nchapter: ch_007\nform: 单场景章\n# comment\n---\n\n正文"
    fm = common.parse_front_matter(text)
    assert fm == {"chapter": "ch_007", "form": "单场景章"}
    assert common.parse_front_matter("没有头") == {}


def test_resolve_workspace(tmp_path):
    assert common.resolve_workspace("/abs/path", root=tmp_path) == common.Path("/abs/path")
    assert common.resolve_workspace("rel", root=tmp_path) == tmp_path / "rel"
    assert common.resolve_workspace(None, root=tmp_path) is None  # 无书不猜
    (tmp_path / "workspace" / "书A").mkdir(parents=True)
    (tmp_path / "workspace" / "书A" / "project.json").write_text("{}", encoding="utf-8")
    assert common.resolve_workspace(None, root=tmp_path).name == "书A"
