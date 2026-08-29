# -*- coding: utf-8 -*-
"""
Memory Core — 纯 Python（零第三方依赖）长篇记忆引擎。

只做确定性机械工作（存储/检索/统计），不做语义理解：
  1. 章节梗概脊柱：存储/渲染「同步官提案登记的人工梗概」
     （04_timeline_and_state/chapter_synopsis.json），供 pack 防情节重复参考；
  2. RAG 资料员 (BM25 Librarian)：对全部定稿章节建 BM25 索引，
     按查询词召回最相关旧段落（机械检索）。
     中文分词：优先 jieba，无 jieba 时降级为「字 bi-gram + 英文/数字词」；
  3. 跨章重复检测：12 字连续字串雷同 + 章节高频词 Jaccard 相似度
     （纯字符串/频率统计，不含语义判断）。

数据文件：
  04_timeline_and_state/chapter_synopsis.json
    {
      "schema": "novel-studio.chapter-synopsis/v1",
      "chapters": {"ch_001": {"num":1, "title":"...", "synopsis":"2~3句", "source":"manual"}},
      "book_title": "...", "book_logline": "一句话梗概（可选，manual）"
    }
"""

import re
import sys
import math
import json
from pathlib import Path

_tools_dir = Path(__file__).resolve().parent
if str(_tools_dir) not in sys.path:
    sys.path.insert(0, str(_tools_dir))

from novel_utils import (
    find_manuscript_files, natural_chapter_sort_key, chapter_number_from_name,
    atomic_write_text,
)

SYNOPSIS_SCHEMA = "novel-studio.chapter-synopsis/v1"
SYNOPSIS_FILE = "04_timeline_and_state/chapter_synopsis.json"

# 中文停用字（bi-gram 模式下过滤高频虚字，降低噪声）
_CN_STOP = set("的了是在我你他她它们这那也就都而与及和对着把被让向往从到于或若但很最不没"
               "有个么们吧啊呀呢嘛哦嗯哎")

# 章节标题（如 "# 第3章 黑市风云" / "## 第三章 …"）
_CH_TITLE_RE = re.compile(r"^#{1,3}\s*(?:第\s*[0-9零一二三四五六七八九十百千两]+\s*[章回节]?[^\n]*)$")


# ---------------------------------------------------------------------------
# 分词（jieba 优先，无则降级）
# ---------------------------------------------------------------------------
def _tokenize(text: str) -> list:
    """中文分词：有 jieba 用 jieba；否则用 字bi-gram + 英文/数字词。"""
    text = text or ""
    try:
        import jieba  # type: ignore
        toks = [t.strip() for t in jieba.lcut(text) if t.strip()]
        # jieba 单字虚字过滤
        return [t for t in toks if not (len(t) == 1 and t in _CN_STOP)]
    except Exception:
        pass
    return _fallback_tokens(text)


def _fallback_tokens(text: str) -> list:
    out = []
    # 英文单词 / 数字串整体成词
    for m in re.finditer(r"[A-Za-z0-9]+", text):
        out.append(m.group(0).lower())
    # 中文：提取连续汉字段，做相邻 bi-gram（跳过含停用字的 gram）
    for seg in re.findall(r"[\u4e00-\u9fa5]+", text):
        chars = [c for c in seg]
        for i in range(len(chars) - 1):
            a, b = chars[i], chars[i + 1]
            if a in _CN_STOP or b in _CN_STOP:
                continue
            out.append(a + b)
        # 段内单字也保留（利于专名匹配），但过滤虚字
        for c in chars:
            if c not in _CN_STOP:
                out.append(c)
    return out


# ---------------------------------------------------------------------------
# 梗概脊柱
# ---------------------------------------------------------------------------
def load_synopsis(workspace: Path) -> dict:
    p = workspace / SYNOPSIS_FILE
    if p.exists():
        try:
            d = json.loads(p.read_text(encoding="utf-8-sig"))
        except Exception as e:
            # 损坏文件静默返回空默认值会让调用方在空脊柱上写回，
            # 覆盖掉全部历史梗概——必须让调用方显式失败。
            raise ValueError(f"{SYNOPSIS_FILE} 解析失败（拒绝在损坏数据上写回）: {e}")
        d.setdefault("chapters", {})
        return d
    return {"schema": SYNOPSIS_SCHEMA, "chapters": {}, "book_title": "", "book_logline": ""}


def save_synopsis(workspace: Path, data: dict):
    p = workspace / SYNOPSIS_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(p, json.dumps(data, ensure_ascii=False, indent=2))


def _chapter_title(text: str) -> str:
    for line in text.splitlines()[:8]:
        s = line.strip()
        if _CH_TITLE_RE.match(s):
            return re.sub(r"^#+\s*", "", s).strip()
    return ""


def _clean_title(title: str) -> str:
    """去掉标题里的 '第N章/第N回' 前缀，只留章节名。"""
    t = re.sub(r"^#*\s*第\s*[0-9零一二三四五六七八九十百千两]+\s*[章回节]?\s*[：:、.\-]?\s*",
               "", (title or "").strip()).strip()
    return t


def render_spine_brief(data: dict, max_chapters: int = 60) -> str:
    """渲染注入 pack 的'全书梗概脊柱'：书名 logline + 每章一句话。"""
    chs = sorted(data.get("chapters", {}).values(), key=lambda c: c.get("num", 0))
    if not chs:
        return ""
    lines = []
    if data.get("book_logline"):
        lines.append(f"全书一句话：{data['book_logline']}")
    for c in chs[-max_chapters:]:
        num = c.get("num", "?")
        title = _clean_title(c.get("title"))
        syn = c.get("synopsis", "")
        # 一句话梗概：取第一句或截断
        one = re.split(r"(?<=[。！？…])", syn)[0] if syn else ""
        if len(one) > 60:
            one = one[:60] + "…"
        head = f"第{num}章《{title}》" if title else f"第{num}章"
        lines.append(f"{head}：{one}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# BM25 资料员
# ---------------------------------------------------------------------------
class BM25Index:
    """对定稿章节分块建 BM25 索引。chunk = 章节内按段落/句群切分的块。"""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.docs = []          # [{ch, num, title, text, tokens}]
        self.df = {}            # token -> 出现该 token 的文档数
        self.avgdl = 0.0

    def add_chapter(self, num: int, ch_key: str, title: str, text: str, chunk_chars: int = 320):
        paras = [p.strip() for p in re.split(r"\n\s*\n|(?<=[。！？…])\n", text) if p.strip()]
        buf, chunks = "", []
        for p in paras:
            buf += p + "\n"
            if len(buf) >= chunk_chars:
                chunks.append(buf.strip())
                buf = ""
        if buf.strip():
            chunks.append(buf.strip())
        if not chunks:
            chunks = [text]
        for idx, chunk in enumerate(chunks):
            toks = _tokenize(chunk)
            if not toks:
                continue
            self.docs.append({
                "ch": ch_key, "num": num, "title": title,
                "chunk": idx, "text": chunk, "tokens": toks,
            })

    def build(self):
        n = len(self.docs)
        total_len = 0
        for d in self.docs:
            total_len += len(d["tokens"])
            for t in set(d["tokens"]):
                self.df[t] = self.df.get(t, 0) + 1
        self.avgdl = (total_len / n) if n else 0.0
        self._idf_cache = {}

    def _idf(self, term: str) -> float:
        if term in self._idf_cache:
            return self._idf_cache[term]
        df = self.df.get(term, 0)
        idf = math.log(1 + (len(self.docs) - df + 0.5) / (df + 0.5))
        self._idf_cache[term] = idf
        return idf

    def search(self, query: str, top_k: int = 5, exclude_chapter: int = None) -> list:
        q_tokens = _tokenize(query)
        if not q_tokens or not self.docs:
            return []
        scores = []
        for d in self.docs:
            if exclude_chapter is not None and d["num"] == exclude_chapter:
                continue
            tf = {}
            for t in d["tokens"]:
                tf[t] = tf.get(t, 0) + 1
            dl = len(d["tokens"])
            score = 0.0
            for q in q_tokens:
                if q not in tf:
                    continue
                idf = self._idf(q)
                freq = tf[q]
                denom = freq + self.k1 * (1 - self.b + self.b * dl / (self.avgdl or 1))
                score += idf * (freq * (self.k1 + 1)) / denom
            if score > 0:
                scores.append((score, d))
        scores.sort(key=lambda x: -x[0])
        out = []
        seen = set()
        for score, d in scores:
            sig = (d["ch"], d["chunk"])
            if sig in seen:
                continue
            seen.add(sig)
            snippet = d["text"][:180].replace("\n", " ").strip()
            out.append({
                "chapter": d["ch"], "num": d["num"], "title": d["title"],
                "score": round(score, 3), "snippet": snippet + ("…" if len(d["text"]) > 180 else ""),
            })
            if len(out) >= top_k:
                break
        return out


def build_index(workspace: Path) -> BM25Index:
    idx = BM25Index()
    ms_dir = workspace / "05_manuscript"
    files = find_manuscript_files(ms_dir) if ms_dir.exists() else []
    for f in sorted(files, key=natural_chapter_sort_key):
        num = chapter_number_from_name(f.name)
        if num is None:
            continue
        text = f.read_text(encoding="utf-8")
        idx.add_chapter(num, f"ch_{num:03d}", _chapter_title(text) or f.name, text)
    idx.build()
    return idx


def librarian_recall(workspace: Path, query: str, top_k: int = 5,
                      exclude_chapter: int = None) -> list:
    idx = build_index(workspace)
    return idx.search(query, top_k=top_k, exclude_chapter=exclude_chapter)


# ---------------------------------------------------------------------------
# 跨章重复检测
# ---------------------------------------------------------------------------
def _content_ngrams(text: str, n: int = 12) -> set:
    """正文（去标点/空白/工程标记）的连续 n-gram 集合。"""
    clean = re.sub(r"[^\u4e00-\u9fa5A-Za-z0-9]", "", text)
    return {clean[i:i + n] for i in range(max(0, len(clean) - n + 1))}


def _content_vocab(text: str, top_k: int = 25) -> set:
    """章节高频内容词（bi-gram/词）集合，用于场景节拍相似度。"""
    toks = [t for t in _tokenize(text) if len(t) >= 2 and not re.fullmatch(r"[0-9A-Za-z]+", t)]
    freq = {}
    for t in toks:
        freq[t] = freq.get(t, 0) + 1
    top = sorted(freq.items(), key=lambda kv: -kv[1])[:top_k]
    return {t for t, _ in top}


def detect_cross_chapter_repetition(workspace: Path, ngram_size: int = 12,
                                    jaccard_threshold: float = 0.45) -> dict:
    """返回 {warnings: [...], ngram_hits: [...], similar_scenes: [...]}"""
    result = {"warnings": [], "ngram_hits": [], "similar_scenes": []}
    ms_dir = workspace / "05_manuscript"
    files = sorted(find_manuscript_files(ms_dir) if ms_dir.exists() else [],
                   key=natural_chapter_sort_key)
    if len(files) < 2:
        return result

    chapters = []  # (num, key, text)
    for f in files:
        num = chapter_number_from_name(f.name)
        if num is None:
            continue
        chapters.append((num, f"ch_{num:03d}", f.read_text(encoding="utf-8")))

    # n-gram 雷同 & 场景节拍相似度（两两比对，章距>=2 才有意义）
    ngram_sets = {}
    vocab_sets = {}
    for num, key, text in chapters:
        ngram_sets[num] = (key, _content_ngrams(text, ngram_size))
        vocab_sets[num] = (key, _content_vocab(text))

    nums = [c[0] for c in chapters]
    for i in range(len(nums)):
        for j in range(i + 1, len(nums)):
            a, b = nums[i], nums[j]
            if b - a < 2:
                continue
            ka, ga = ngram_sets[a]
            kb, gb = ngram_sets[b]
            overlap = ga & gb
            # 雷同 n-gram 去重后 >=3 条，疑似复制/自我重复
            meaningful = {g for g in overlap if not re.fullmatch(r"[0-9A-Za-z]+", g)}
            if len(meaningful) >= 3:
                sample = sorted(meaningful)[:3]
                hit = f"{ka} ↔ {kb}：发现 {len(meaningful)} 处 {ngram_size}字连续雷同（如「{sample[0]}」），疑似场景/描写重复"
                result["ngram_hits"].append(hit)
            va_key, va = vocab_sets[a]
            vb_key, vb = vocab_sets[b]
            if va and vb:
                jac = len(va & vb) / len(va | vb)
                if jac >= jaccard_threshold:
                    result["similar_scenes"].append(
                        f"{va_key} ↔ {vb_key}：场景高频词相似度 {jac:.0%}（≥{jaccard_threshold:.0%}），疑似节拍/桥段重复")

    result["warnings"] = (
        [f"📝 {h}" for h in result["ngram_hits"]] +
        [f"🎬 {h}" for h in result["similar_scenes"]]
    )
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _main():
    import argparse
    from novel_utils import resolve_workspace, reconfigure_utf8
    reconfigure_utf8()
    ap = argparse.ArgumentParser(description="长篇记忆引擎：梗概脊柱 / BM25 资料员 / 跨章重复检测")
    ap.add_argument("--workspace", "-w", help="工作区路径")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    sub = ap.add_subparsers(dest="cmd")

    sp = sub.add_parser("spine", help="查看梗概脊柱（仅收录提案登记的人工梗概）")

    q = sub.add_parser("recall", help="BM25 资料员：按查询召回相关旧段落")
    q.add_argument("query", help="查询词/问题，如 '铁壁公司 账本 伏笔'")
    q.add_argument("-k", "--top-k", type=int, default=5)
    q.add_argument("--exclude-chapter", type=int, default=None)

    sub.add_parser("repeat", help="跨章重复检测（n-gram雷同/场景相似）")

    args = ap.parse_args()
    ws = resolve_workspace(args.workspace)

    if args.cmd == "spine":
        data = load_synopsis(ws)
        n = len(data.get("chapters", {}))
        if args.json:
            print(json.dumps({"chapters": n,
                              "spine": render_spine_brief(data)}, ensure_ascii=False, indent=2))
        else:
            print(f"📖 梗概脊柱：共 {n} 章（仅收录同步官提案登记的人工梗概）")
            print(render_spine_brief(data))
        return

    if args.cmd == "recall":
        hits = librarian_recall(ws, args.query, top_k=args.top_k,
                                exclude_chapter=args.exclude_chapter)
        if args.json:
            print(json.dumps({"query": args.query, "hits": hits}, ensure_ascii=False, indent=2))
        else:
            print(f"🔎 资料员召回（查询：{args.query}）")
            for h in hits:
                print(f"  [{h['chapter']} {h.get('title','')}] score={h['score']}\n    {h['snippet']}")
        return

    if args.cmd == "repeat":
        rep = detect_cross_chapter_repetition(ws)
        if args.json:
            print(json.dumps(rep, ensure_ascii=False, indent=2))
        else:
            print("🔁 跨章重复检测：")
            for w in rep["warnings"] or ["  ✅ 未发现跨章重复"]:
                print("  " + w)
        return

    ap.print_help()


if __name__ == "__main__":
    _main()
