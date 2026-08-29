"""D1 docs-as-tests：规范文档里教每条 studio.py 命令，必须能被 argparse 解析。

来源：v1.1/v1.2 自查连抓两例"docs 说话、code 不办"（snapshot list 未注册、front-matter
超键拦截未实现）。本测试只验"可解析"（parse_args 冒烟，不执行、不落盘）——执行层契约
由各 test_* 冻结。新文档写杜撰/过期命令 = 此红。
"""
import contextlib
import io
import json
import re
from pathlib import Path

import pytest

from engine import cli

ROOT = Path(__file__).resolve().parent.parent
SOURCES = [ROOT / "AGENTS.md", ROOT / "README.md", ROOT / "engine" / "README.md"]
SOURCES += sorted((ROOT / "agents").rglob("*.md"))
SOURCES += sorted((ROOT / "templates").rglob("*.md"))

CMD_RE = re.compile(r"python3?\s+studio\.py\s+([^`\n|]+)")
SUBCOMMANDS = {"init", "check", "sync", "status", "pack", "evidence", "snapshot",
               "export", "help", "proposal"}
_TAIL = "，。；：、）)】」"


def _clean_tokens(seg: str) -> list[str]:
    seg = seg.split("#", 1)[0]
    toks = []
    for t in seg.split():
        t = t.rstrip(_TAIL).strip("`*")
        if t and t not in ("&&", ";", "&&&"):
            toks.append(t)
    return toks


@pytest.mark.parametrize("doc", SOURCES, ids=lambda p: str(p.relative_to(ROOT)))
def test_documented_commands_parse(doc):
    parser = cli._build_parser()
    text = doc.read_text(encoding="utf-8")
    bad = []
    for line in text.splitlines():
        for m in CMD_RE.finditer(line):
            toks = _clean_tokens(m.group(1))
            if not toks:
                continue
            if any("<" in t or "〈" in t for t in toks[:1]):
                continue  # 子命令位置占位（如 <命令>）不算可执行示例
            head = toks[0].strip("<>《》")
            if toks[0] not in SUBCOMMANDS and head not in SUBCOMMANDS:
                bad.append(f"{doc.name}: 未知子命令 {toks[0]!r} ← 行: {line.strip()[:60]}")
                continue
            probe = toks + (["-w", str(Path("/tmp/__doc_probe__"))] if "-w" not in toks else [])
            err = io.StringIO()
            try:
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
                    parser.parse_args(probe)
            except SystemExit:
                bad.append(f"{doc.name}: argparse 拒绝 {probe[:4]}… ← {err.getvalue().strip()[:90]}")
    assert not bad, "文档命令失配（docs 说话 code 不办）:\n" + "\n".join(bad)


def test_help_catalog_matches_parser_and_doc():
    """help --json 目录、COMMAND_DOC、argparse 子命令三者必须互为镜像。"""
    parser = cli._build_parser()
    import argparse
    subs = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    names = set(subs.choices)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        cli.main(["help", "--json"])
    catalog = {c["name"] for c in json.loads(buf.getvalue())["commands"]}
    assert names == catalog == set(cli.COMMAND_HELP), "命令目录三处失同步"
