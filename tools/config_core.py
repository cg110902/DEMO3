# -*- coding: utf-8 -*-
"""
统一配置层 (config_core.py)
===========================
把分散在三处的配置来源合并为单一「生效配置」视图，并明确优先级：

    CLI 参数  >  工作区 00_meta/genre_profile.json  >  全局 novel_config.yaml  >  内置默认值

- 全局配置：仓库根目录 ``novel_config.yaml``（工程配置：工作区、字数阈值、工作流开关等）；
- 工作区配置：``<workspace>/00_meta/genre_profile.json``（随书题材档案：配比/基调等）；
- 内置默认：``tools/genre_profiles/generic.json`` + 本模块硬编码工程默认值。

YAML 解析：优先使用 ``pyyaml``（若已安装）；不可用时回退到本模块自带的增强版
手写解析器，支持：
- 嵌套映射（缩进）；
- 列表（``- item``，含「列表项为映射」）；
- 标量：布尔（true/false/yes/no/on/off）、整数、浮点、null、单/双引号字符串；
- 行内注释（``# comment``，引号内的 # 不当注释）；
- 块标量（``|`` 字面量 / ``>`` 折叠量，含 chomping 指示符 ``-``/``+``）；
- 简单的流式集合（``[a, b]`` / ``{k: v}``）。

手写解析器遇到无法解析的语法时抛出 ``YAMLParseError``（含行号与原始行），
**绝不静默返回空字典**。

零第三方依赖（pyyaml 为可选增强）。

用法::

    from config_core import load_effective_config

    cfg = load_effective_config("/path/to/workspace")
    mode = cfg.get("workflow", {}).get("mode")
"""
import sys
import json
import copy
from pathlib import Path

# ---------------------------------------------------------------------------
# 日志（惰性导入，避免循环依赖）
# ---------------------------------------------------------------------------
def _logger():
    import logging
    return logging.getLogger("novel_studio.config_core")


# ---------------------------------------------------------------------------
# 路径工具
# ---------------------------------------------------------------------------
def project_root() -> Path:
    """返回仓库根目录（tools/ 的父目录）。"""
    return Path(__file__).resolve().parent.parent


def _tools_dir() -> Path:
    return Path(__file__).resolve().parent


# ---------------------------------------------------------------------------
# YAML 解析：优先 pyyaml，不可用时用增强手写解析器
# ---------------------------------------------------------------------------
class YAMLParseError(Exception):
    """YAML 子集解析失败，携带行号与原始行内容。"""

    def __init__(self, message, line_no=None, line=None):
        self.line_no = line_no
        self.line = line
        if line_no is not None:
            msg = f"YAML 解析错误（第 {line_no} 行）: {message}"
            if line is not None:
                msg += f"\n    原始行: {line!r}"
        else:
            msg = f"YAML 解析错误: {message}"
        super().__init__(msg)


def parse_yaml(text: str):
    """解析 YAML 子集文本。优先 pyyaml，否则用手写解析器。

    解析失败时抛出 ``YAMLParseError``。
    """
    try:
        import yaml  # type: ignore
        try:
            return yaml.safe_load(text)
        except Exception as e:  # pyyaml 自身的解析错误也统一包装
            raise YAMLParseError(f"pyyaml 解析失败: {e}")
    except ImportError:
        return _handwritten_yaml_parse(text)


# -- 手写解析器 ---------------------------------------------------------------

def _strip_yaml_comment(line: str) -> str:
    """剥离行内注释，正确跳过单/双引号内的 ``#``。

    仅当 ``#`` 位于行首或前面是空白字符时才视为注释起始。
    """
    in_single = False
    in_double = False
    for i, ch in enumerate(line):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double:
            if i == 0 or line[i - 1] in " \t":
                return line[:i]
    return line


def _parse_yaml_scalar(val: str):
    """把 YAML 标量字符串转换为 bool/int/float/None/str。"""
    if val is None:
        return None
    s = val.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        return s[1:-1]
    low = s.lower()
    if low in ("true", "yes", "on"):
        return True
    if low in ("false", "no", "off"):
        return False
    if low in ("null", "~", ""):
        return None
    # 整数（支持正负号）
    try:
        return int(s)
    except ValueError:
        pass
    # 浮点
    try:
        return float(s)
    except ValueError:
        pass
    return s


def _split_flow(s: str) -> list:
    """按逗号切分流式集合内容，忽略引号内的逗号。"""
    parts = []
    buf = []
    in_single = False
    in_double = False
    depth = 0
    for ch in s:
        if ch == "'" and not in_double:
            in_single = not in_single
            buf.append(ch)
        elif ch == '"' and not in_single:
            in_double = not in_double
            buf.append(ch)
        elif ch in "[{":
            depth += 1
            buf.append(ch)
        elif ch in "]}":
            depth -= 1
            buf.append(ch)
        elif ch == "," and depth == 0 and not in_single and not in_double:
            parts.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    tail = "".join(buf).strip()
    if tail:
        parts.append(tail)
    return parts


def _parse_flow_value(s: str):
    """解析流式集合（``[...]`` 列表 / ``{...}`` 映射），非流式则按标量处理。"""
    s = s.strip()
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        if not inner:
            return []
        return [_parse_flow_value(x) for x in _split_flow(inner)]
    if s.startswith("{") and s.endswith("}"):
        inner = s[1:-1].strip()
        if not inner:
            return {}
        result = {}
        for pair in _split_flow(inner):
            if ":" not in pair:
                raise YAMLParseError(f"流式映射项缺少 ':' : {pair!r}")
            k, _, v = pair.partition(":")
            result[k.strip()] = _parse_flow_value(v.strip())
        return result
    return _parse_yaml_scalar(s)


def _looks_like_map_entry(s: str) -> bool:
    """判断字符串是否形如 ``key: value`` 的映射项（用于列表项为映射的情况）。"""
    if not s or s[0] in ("'", '"', "[", "{", "|", ">"):
        return False
    # 未加引号的 key：到第一个冒号为止，冒号后须为空白或行尾
    for i, ch in enumerate(s):
        if ch == ":":
            if i + 1 >= len(s) or s[i + 1] in " \t":
                return True
            return False
        if ch in " \t":
            # key 中遇到空白说明不是简单 key
            return False
    return False


def _handwritten_yaml_parse(text: str):
    """增强版手写 YAML 子集解析器。

    支持嵌套映射、列表（含列表项为映射）、块标量、流式集合、行内注释。
    语法错误时抛出 ``YAMLParseError``。
    """
    # 预处理：保留原始行（含前导空格），计算缩进，跳过空行/纯注释行
    raw_lines = text.splitlines()
    lines = []  # (line_no, indent, content_rstripped)
    for idx, raw in enumerate(raw_lines, 1):
        stripped = _strip_yaml_comment(raw).rstrip()
        if not stripped.strip():
            continue
        indent = len(stripped) - len(stripped.lstrip(" "))
        lines.append((idx, indent, stripped))

    if not lines:
        return None

    result, next_idx = _parse_block(lines, 0, lines[0][1])
    if next_idx < len(lines):
        ln, ind, content = lines[next_idx]
        raise YAMLParseError(
            f"意外的缩进层级（期望 ≤ {lines[0][1]}，实际 {ind}）",
            line_no=ln, line=content,
        )
    return result


def _parse_block(lines, start, indent):
    """解析一个块（映射或列表），返回 (value, next_index)。"""
    if start >= len(lines):
        return None, start
    first_content = lines[start][2].lstrip(" ")
    if first_content.startswith("- ") or first_content == "-":
        return _parse_list(lines, start, lines[start][1])
    return _parse_map(lines, start, lines[start][1])


def _parse_map(lines, start, indent):
    """解析映射块，返回 (dict, next_index)。"""
    result = {}
    i = start
    while i < len(lines):
        lineno, ind, raw_content = lines[i]
        if ind < indent:
            break
        if ind > indent:
            raise YAMLParseError(
                f"意外的缩进（期望 {indent}，实际 {ind}）",
                line_no=lineno, line=raw_content,
            )
        content = raw_content.strip()
        if content.startswith("- ") or content == "-":
            raise YAMLParseError(
                "映射块中出现列表项 '-'，缩进可能不正确",
                line_no=lineno, line=raw_content,
            )
        if ":" not in content:
            raise YAMLParseError(
                "期望 'key: value' 映射项",
                line_no=lineno, line=raw_content,
            )
        key, _, val = content.partition(":")
        key = key.strip()
        if not key:
            raise YAMLParseError(
                "映射键为空",
                line_no=lineno, line=raw_content,
            )
        val = val.strip()

        if val == "":
            # 子块（映射或列表）。YAML 标准允许列表项与父键同级缩进
            # （keys: 后直接跟 - a - b 的 GitHub Actions 风格），不能只认更深一层。
            nxt = lines[i + 1] if i + 1 < len(lines) else None
            same_indent_list = (nxt is not None and nxt[1] == indent
                                and nxt[2].strip() in ("-",) or
                                (nxt is not None and nxt[1] == indent
                                 and nxt[2].strip().startswith("- ")))
            if nxt is not None and (nxt[1] > indent or same_indent_list):
                child, i = _parse_block(lines, i + 1, nxt[1])
                result[key] = child
            else:
                result[key] = None
                i += 1
        elif val[0] in ("|", ">"):
            # 块标量
            block, i = _parse_block_scalar(lines, i + 1, indent, val)
            result[key] = block
        else:
            result[key] = _parse_flow_value(val)
            i += 1
    return result, i


def _parse_list(lines, start, indent):
    """解析列表块，返回 (list, next_index)。"""
    result = []
    i = start
    while i < len(lines):
        lineno, ind, raw_content = lines[i]
        if ind != indent:
            break
        content = raw_content.strip()
        if not content.startswith("-"):
            break
        # 去掉 '-' 前缀
        item_raw = content[1:].lstrip()
        if item_raw == "":
            # '-' 后无子内容：下一行是更深的子块
            i += 1
            if i < len(lines) and lines[i][1] > indent:
                child, i = _parse_block(lines, i, lines[i][1])
                result.append(child)
            else:
                result.append(None)
        elif _looks_like_map_entry(item_raw):
            # 列表项是映射：首行 "- key: val"，后续同缩进+2 的行属于同一映射
            map_indent = indent + 2
            synthetic = [(lineno, map_indent, " " * map_indent + item_raw)]
            i += 1
            while i < len(lines) and lines[i][1] > indent:
                synthetic.append(lines[i])
                i += 1
            child, _ = _parse_map(synthetic, 0, map_indent)
            result.append(child)
        else:
            result.append(_parse_flow_value(item_raw))
            i += 1
    return result, i


def _parse_block_scalar(lines, start, parent_indent, indicator):
    """解析块标量（``|`` 字面量 / ``>`` 折叠量）。

    indicator 形如 ``|``、``|-``、``|+``、``>``、``>-`` 等。
    返回 (字符串, next_index)。
    """
    style = indicator[0]  # '|' or '>'
    chomp = "clip"  # 默认 clip：保留末尾一个换行
    if len(indicator) > 1:
        if "-" in indicator[1:]:
            chomp = "strip"
        elif "+" in indicator[1:]:
            chomp = "keep"

    # 收集所有缩进大于 parent_indent 的行
    block_lines = []
    i = start
    block_indent = None
    while i < len(lines):
        lineno, ind, raw = lines[i]
        if ind <= parent_indent:
            break
        if block_indent is None:
            block_indent = ind
        # 保留相对缩进（去掉 block_indent 个前导空格）
        if ind >= block_indent:
            block_lines.append(raw[block_indent:])
        else:
            # 比首行缩进少但仍大于 parent_indent：视为块内的缩进保留
            block_lines.append(raw[parent_indent + 1:])
        i += 1

    if style == "|":
        text = "\n".join(block_lines)
    else:  # '>' 折叠：换行变空格，空行变换行
        paragraphs = []
        current = []
        for ln in block_lines:
            if ln.strip() == "":
                if current:
                    paragraphs.append(" ".join(current))
                    current = []
            else:
                current.append(ln.strip())
        if current:
            paragraphs.append(" ".join(current))
        text = "\n\n".join(paragraphs)

    if chomp == "keep":
        text += "\n"
    elif chomp == "clip":
        text = text.rstrip("\n") + "\n"
    else:  # strip
        text = text.rstrip("\n")
    return text, i


# ---------------------------------------------------------------------------
# 配置合并
# ---------------------------------------------------------------------------
def _deep_merge(base: dict, override: dict) -> dict:
    """递归合并：override 覆盖 base；dict 深合，其余整体覆盖。"""
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


# 内置工程默认值（当 novel_config.yaml 缺失时的兜底）
_BUILTIN_ENGINEERING_DEFAULTS = {
    "project": {
        "workspace_dir": "novel_workspace",
        "default_genre": "通用自适应",
    },
    "generation": {
        "target_word_count": {"min": 2200, "max": 4000, "recommended": 3200},
    },
    "workflow": {
        "mode": "automatic",
    },
}


def _load_builtin_genre_defaults() -> dict:
    """加载内置 generic 题材档案（tools/genre_profiles/generic.json）。"""
    p = _tools_dir() / "genre_profiles" / "generic.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            _logger().warning("内置 generic.json 读取失败: %s", e)
    return {}


def _load_global_config() -> dict:
    """加载仓库根目录的 novel_config.yaml。文件不存在返回空 dict。"""
    cfg_path = project_root() / "novel_config.yaml"
    if not cfg_path.exists():
        return {}
    text = cfg_path.read_text(encoding="utf-8")
    try:
        data = parse_yaml(text)
    except YAMLParseError as exc:
        print(f"❌ [CONFIG] novel_config.yaml 解析失败（第 {getattr(exc, 'line_no', '?')} 行）: {exc}")
        print("   请修正配置文件后重试；全部命令依赖该配置，无法跳过。")
        sys.exit(2)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise YAMLParseError(
            f"novel_config.yaml 顶层必须是映射（dict），实际为 {type(data).__name__}"
        )
    return data


def _load_workspace_profile(workspace_path) -> dict:
    """加载工作区 00_meta/genre_profile.json。不存在返回空 dict。"""
    if workspace_path is None:
        return {}
    wp = Path(workspace_path) / "00_meta" / "genre_profile.json"
    if not wp.exists():
        return {}
    try:
        data = json.loads(wp.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            _logger().warning("工作区 genre_profile.json 顶层不是对象，已忽略")
            return {}
        mode_file = wp.parent / "workflow_mode.json"
        if mode_file.exists():
            mode_data = json.loads(mode_file.read_text(encoding="utf-8"))
            if isinstance(mode_data, dict) and "mode" in mode_data:
                data.setdefault("workflow", {})["mode"] = mode_data["mode"]
        return data
    except Exception as e:
        _logger().error("工作区 genre_profile.json 解析失败: %s", e)
        return {}


# ---------------------------------------------------------------------------
# 生效配置缓存
# ---------------------------------------------------------------------------
_EFFECTIVE_CACHE = {}


def get_engineering_defaults() -> dict:
    """返回内置工程默认值的深拷贝（与题材无关的引擎配置）。"""
    return copy.deepcopy(_BUILTIN_ENGINEERING_DEFAULTS)


def clear_cache():
    """清空配置缓存（测试或配置热更时使用）。"""
    _EFFECTIVE_CACHE.clear()


def load_effective_config(workspace_path=None, cli_overrides: dict = None) -> dict:
    """加载并合并全部配置层，返回生效配置（深拷贝，调用方可安全修改）。

    优先级从高到低：CLI 参数 > 工作区 genre_profile.json > 全局 novel_config.yaml
    > 内置默认值（工程默认 + generic 题材档案）。

    :param workspace_path: 工作区路径；None 时跳过工作区层
    :param cli_overrides: CLI 显式覆盖的键值对（最高优先级，深合并）
    """
    cache_key = (str(Path(workspace_path).resolve()) if workspace_path else None,
                 json.dumps(cli_overrides or {}, sort_keys=True, ensure_ascii=False))
    if cache_key in _EFFECTIVE_CACHE:
        return copy.deepcopy(_EFFECTIVE_CACHE[cache_key])

    # 1. 内置默认（工程默认 + generic 题材档案）
    cfg = _deep_merge(_BUILTIN_ENGINEERING_DEFAULTS, _load_builtin_genre_defaults())
    # 2. 全局 novel_config.yaml
    cfg = _deep_merge(cfg, _load_global_config())
    # 3. 工作区 genre_profile.json
    cfg = _deep_merge(cfg, _load_workspace_profile(workspace_path))
    # 4. CLI 覆盖
    if cli_overrides:
        cfg = _deep_merge(cfg, cli_overrides)

    workflow = cfg.setdefault("workflow", {})
    mode = workflow.get("mode", "automatic")
    aliases = {"autonomous_creation": "automatic", "auto": "automatic", "manual": "manual", "automatic": "automatic"}
    if mode not in aliases:
        raise ValueError(f"workflow.mode 必须是 manual 或 automatic，实际为: {mode!r}")
    workflow["mode"] = aliases[mode]
    _EFFECTIVE_CACHE[cache_key] = copy.deepcopy(cfg)
    return cfg


# ---------------------------------------------------------------------------
# CLI 自检
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse
    from novel_utils import reconfigure_utf8  # 复用 UTF-8 控制台配置
    reconfigure_utf8()

    ap = argparse.ArgumentParser(description="统一配置层自检：打印当前生效配置")
    ap.add_argument("-w", "--workspace", help="工作区路径（含 00_meta/genre_profile.json）")
    ap.add_argument("--key", help="只打印指定点分键的值，例如 generation.target_word_count.min")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    args = ap.parse_args()

    if args.key:
        val = get_config(args.key, workspace_path=args.workspace)
        if args.json:
            print(json.dumps({args.key: val}, ensure_ascii=False, indent=2))
        else:
            print(f"{args.key} = {val!r}")
    else:
        cfg = load_effective_config(args.workspace)
        if args.json:
            print(json.dumps(cfg, ensure_ascii=False, indent=2))
        else:
            print("=" * 64)
            print(" 📐 当前生效配置（CLI > 工作区 > 全局 > 内置）")
            print("=" * 64)
            print(json.dumps(cfg, ensure_ascii=False, indent=2))
