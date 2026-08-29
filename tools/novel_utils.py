# -*- coding: utf-8 -*-
"""
Universal Novel Studio - Shared Utilities (novel_utils.py)
Centralizes deterministic infrastructure shared by all tools:
- Workspace path resolution & fallback
- Natural alphanumeric chapter sorting
- Clean manuscript file discovery
- Registered character extraction from index and profiles (substring matching)
- UTF-8 console reconfiguration

设计原则：本模块只做确定性结构工作（路径/编号/文件/字符串匹配/原子写），
不做任何语义理解或内容识别——语义判断一律交给 LLM/导演。
"""

import sys
import re
import logging
import json
import hashlib
from pathlib import Path
from collections import defaultdict

# 模块级 logger（统一挂在 novel_studio 日志树）
logger = logging.getLogger("novel_studio.novel_utils")


def reconfigure_utf8():
    """Ensure UTF-8 encoding on Windows consoles."""
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception as e:
            logger.debug("stdout 重配置为 UTF-8 失败（可忽略）: %s", e)


def project_root() -> Path:
    """Returns the repository root (parent of the tools/ directory)."""
    return Path(__file__).resolve().parent.parent


def resolve_workspace(workspace_arg=None) -> Path:
    """Resolves target workspace directory.

    Resolution order:
      1. Explicit --workspace argument (relative paths are anchored at repo root).
      2. ``workspace_dir`` declared in novel_config.yaml (anchored at repo root).
      3. Default ``<repo_root>/novel_workspace``.
    """
    base_dir = project_root()
    if workspace_arg:
        w_path = Path(workspace_arg)
        if not w_path.is_absolute():
            w_path = (base_dir / w_path).resolve()
        return w_path
    from config_core import load_effective_config
    cfg = load_effective_config()
    declared = cfg.get("project", {}).get("workspace_dir")
    if declared:
        return (base_dir / declared).resolve()
    return (base_dir / "novel_workspace").resolve()


# ---------------------------------------------------------------------------
# Chapter identity helpers (boundary-safe, works past chapter 100)
# ---------------------------------------------------------------------------
def chapter_token_to_num(token) -> int:
    """Extracts the chapter number from a token like 'ch_004', 'ch-12', '4' or 4."""
    if token is None:
        return None
    if isinstance(token, int):
        return token
    m = re.search(r"(\d+)", str(token))
    return int(m.group(1)) if m else None


def chapter_number_from_name(name: str):
    """Extracts the chapter number embedded in a file/directory name (None if absent)."""
    m = re.search(r"ch[_-]?0*(\d+)(?![0-9])", str(name), re.IGNORECASE)
    if not m:
        m = re.search(r"chapter[_-]?0*(\d+)(?![0-9])", str(name), re.IGNORECASE)
    return int(m.group(1)) if m else None


def file_matches_chapter(path: Path, target_chapter) -> bool:
    """Boundary-safe chapter match.

    ``ch_001`` / ``1`` only matches files whose chapter token is exactly 1,
    so 'ch_001' no longer accidentally matches 'ch_010' or 'ch_0010'.
    """
    target_num = chapter_token_to_num(target_chapter)
    if target_num is None:
        return str(target_chapter) in str(path).replace("\\", "/")
    return chapter_number_from_name(path.name) == target_num


def latest_chapter_number(manuscript_dir: Path, require_finalized: bool = True):
    """Highest chapter number present in the manuscript tree (0 if none)."""
    if not manuscript_dir or not manuscript_dir.exists():
        return 0
    if require_finalized:
        files = manuscript_dir.glob("**/finalized/ch_*.md")
    else:
        files = manuscript_dir.glob("**/ch_*.md")
    nums = [chapter_number_from_name(f.name) for f in files
            if not f.name.startswith(".") and chapter_number_from_name(f.name) is not None]
    return max(nums) if nums else 0


# ---------------------------------------------------------------------------
# Template placeholder detection
# ---------------------------------------------------------------------------
PLACEHOLDER_RE = re.compile(r"\[[^\[\]]*[\u4e00-\u9fa5][^\[\]]*\]")


def has_placeholder(text) -> bool:
    """True if the text still contains an unfilled [中文] template placeholder."""
    if text is None:
        return False
    return bool(PLACEHOLDER_RE.search(str(text)))


_SEPARATOR_CELL_RE = re.compile(r"^:?-{2,}:?$")


def is_table_separator(line: str) -> bool:
    """True for markdown table separator rows like '|---|:---:|---|' (any spacing)."""
    if not line or not line.strip().startswith("|"):
        return False
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    return all(_SEPARATOR_CELL_RE.match(c) for c in cells if c != "") and any(cells)


# ---------------------------------------------------------------------------
# Atomic file writes (never leave a half-written state file on crash)
# ---------------------------------------------------------------------------
def canonical_json_hash(value) -> str:
    """Return a stable SHA-256 hash for JSON-compatible values."""
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def safe_child_path(root, relative, *, allow_missing=True) -> Path:
    """Resolve a path beneath root, rejecting traversal and absolute paths."""
    root = Path(root).resolve()
    candidate = Path(relative)
    if candidate.is_absolute():
        raise ValueError("path must be relative")
    resolved = (root / candidate).resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError("path escapes root")
    if not allow_missing and not resolved.exists():
        raise FileNotFoundError(resolved)
    return resolved


def atomic_write_text(path, text: str, encoding: str = "utf-8") -> None:
    """Writes text to `path` atomically (temp file + os.replace).

    Guarantees readers never see a truncated/half-written ledger or state file.
    """
    import os
    import tempfile
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # A unique sibling temp file prevents concurrent writers from clobbering
    # one another (the old fixed ``.tmp`` name was unsafe).
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="") as f:
            f.write(text)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        os.replace(tmp_name, path)
    finally:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass


def natural_chapter_sort_key(file_path: Path) -> tuple:
    """Generates natural sort key (volume_num, chapter_num, filename) for chapters."""
    path_str = str(file_path).replace("\\", "/")
    vol_match = re.search(r"vol[_-]?(\d+)", path_str, re.IGNORECASE)
    vol_num = int(vol_match.group(1)) if vol_match else 1

    ch_num = chapter_number_from_name(file_path.name)
    if ch_num is None:
        m = re.search(r"(\d+)", file_path.name)
        ch_num = int(m.group(1)) if m else 9999
    return (vol_num, ch_num, file_path.name)


def find_manuscript_files(manuscript_dir: Path, target_chapter: str = None, single_latest: bool = False) -> list:
    """Finds valid novel chapter manuscript files (finalized or raw_drafts)."""
    if not manuscript_dir.exists():
        return []

    def _excluded(f: Path) -> bool:
        norm = str(f).replace("\\", "/")
        return ("snapshots" in norm
                or f.name.startswith("."))

    if target_chapter:
        matches = [
            f for f in manuscript_dir.glob("**/ch_*.md")
            if not _excluded(f) and file_matches_chapter(f, target_chapter)
        ]
        finalized = [f for f in matches if "finalized" in str(f).replace("\\", "/")]
        res = finalized if finalized else matches
        return sorted(res, key=natural_chapter_sort_key)

    finalized = sorted(
        [
            f for f in manuscript_dir.glob("**/finalized/ch_*.md")
            if not f.name.startswith(".")
        ],
        key=natural_chapter_sort_key
    )
    if finalized:
        return [finalized[-1]] if single_latest else finalized

    raw_drafts = sorted(
        [
            f for f in manuscript_dir.glob("**/raw_drafts/ch_*.md")
            if not f.name.startswith(".")
        ],
        key=natural_chapter_sort_key
    )
    if raw_drafts:
        return [raw_drafts[-1]] if single_latest else raw_drafts

    all_md = sorted(
        [
            f for f in manuscript_dir.glob("**/*.md")
            if "snapshots" not in str(f).replace("\\", "/")
            and not f.name.startswith(".")
        ],
        key=natural_chapter_sort_key
    )
    if all_md:
        return [all_md[-1]] if single_latest else all_md
    return []


def strip_name_title(name: str) -> str:
    """去掉角色名最前面的「头衔·」前缀，用于正文匹配与展示。

    角色表首列常写作「村长·张老爹」「游方道人·玄清」，但正文只以短名
    「张老爹」「玄清」称呼。若原样注册，全文匹配会因前缀不同而失配，
    导致角色被误判为从未登场。此函数去掉第一个「·」之前的部分；
    无「·」的名字原样返回。
    """
    if not name:
        return name
    stripped = re.sub(r"^[^·\s]+·", "", name).strip()
    return stripped or name


def load_character_registry(workspace_dir: Path) -> dict:
    """Return canonical character names mapped to registered aliases."""
    registry = defaultdict(set)
    def add(raw, aliases=()):
        name = strip_name_title(re.sub(r"[*_`#]", "", str(raw)).strip())
        if not name or len(name) > 10 or has_placeholder(name):
            return
        registry[name].add(name)
        for alias in re.split(r"[、,，/；;\s]+", str(aliases or "")):
            alias = strip_name_title(re.sub(r"[*_`#\[\]（）()]", "", alias).strip())
            if alias and len(alias) <= 10 and not has_placeholder(alias):
                registry[name].add(alias)
    index_file = workspace_dir / "02_characters" / "character_index.md"
    if index_file.exists():
        for line in index_file.read_text(encoding="utf-8").splitlines():
            if not line.startswith("|") or is_table_separator(line):
                continue
            parts = [p.strip() for p in line.strip().strip("|").split("|")]
            if parts and "角色" not in parts[0] and "姓名" not in parts[0]:
                add(parts[0], parts[1] if len(parts) > 1 else "")
    profiles_dir = workspace_dir / "02_characters" / "profiles"
    if profiles_dir.exists():
        for pfile in sorted(profiles_dir.glob("*.md")):
            if not pfile.name.startswith("."):
                m = re.search(r"#+\s*(?:角色(?:姓名|名|卡)?[：:]\s*)?([^\n(（\s#*]+)", pfile.read_text(encoding="utf-8"))
                if m: add(m.group(1))
    # 确定性排序：先按别名长度降序（匹配时优先长别名），同长按字典序——
    # 不可依赖 set 迭代顺序（PYTHONHASHSEED 随机化会让输出顺序逐次漂移）。
    return {k: sorted(v, key=lambda x: (-len(x), x)) for k, v in registry.items()}


def load_registered_characters(workspace_dir: Path) -> list:
    """Extract canonical character names (compatibility wrapper)."""
    return sorted(load_character_registry(workspace_dir))
