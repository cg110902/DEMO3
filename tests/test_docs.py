"""M3/M4 文档层验收：行数/token 预算、锚点可解析、同一条规则不双写、权限矩阵唯一事实。

这些检查替代旧工程"靠自觉"的文档治理——复述与断链在这里是 CI 红，不是口头约定。
"""
import re
from pathlib import Path

import pytest

from engine import common, state

ROOT = Path(__file__).resolve().parent.parent

DOCS = {
    "AGENTS": ROOT / "AGENTS.md",
    "workflow": ROOT / "agents" / "rules" / "novel_workflow.md",
    "craft": ROOT / "agents" / "rules" / "novel_craft.md",
    "genre_guide": ROOT / "agents" / "genre_guide.md",
}
SKILL_DIRS = ["director", "beats-builder", "drafter", "guard", "syncer"]
LINE_BUDGET = {"AGENTS": 120, "workflow": 260, "craft": 280, "genre_guide": 160}
SKILL_BUDGET = 70
TEMPLATE_BUDGET = 40
AGENTS_TOKEN_BUDGET = 1500  # 开局必读预算（PLAN §8.2）


def all_docs() -> dict[str, str]:
    out = {k: p.read_text(encoding="utf-8") for k, p in DOCS.items()}
    for name in SKILL_DIRS:
        out[f"skill:{name}"] = (ROOT / "agents" / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
    return out


def headings(text: str) -> list[str]:
    return [ln.lstrip("#").strip() for ln in text.splitlines() if re.match(r"^#{2,3} ", ln)]


def test_files_exist():
    for name, p in DOCS.items():
        assert p.is_file(), f"缺文档: {name} → {p}"
    for name in SKILL_DIRS:
        assert (ROOT / "agents" / "skills" / name / "SKILL.md").is_file()


def test_line_and_token_budgets():
    texts = all_docs()
    for name, budget in LINE_BUDGET.items():
        n = len(texts[name].splitlines())
        assert n <= budget, f"{name} 超行数预算: {n} > {budget}（超预算=设计问题，PLAN §1.3-4）"
    for name, text in texts.items():
        if name.startswith("skill:"):
            n = len(text.splitlines())
            assert n <= SKILL_BUDGET, f"{name} 超 {SKILL_BUDGET} 行: {n}"
    assert common.est_tokens(texts["AGENTS"]) <= AGENTS_TOKEN_BUDGET, \
        "AGENTS.md 超出开局必读 token 预算，砍解释性文字"


def test_all_anchor_references_resolve():
    """跨文档引用必须能落到目标文件的标题锚点上（禁悬空引用、禁改抄）。"""
    ref_re = re.compile(r"(workflow|craft|genre_guide|AGENTS)#([^\s、，。：（）`\"'』」]+)")
    targets = {"workflow": "workflow", "craft": "craft", "genre_guide": "genre_guide", "AGENTS": "AGENTS"}
    texts = all_docs()
    dangling = []
    for src, text in texts.items():
        for doc, anchor in ref_re.findall(text):
            if doc not in targets:
                continue
            hs = headings(texts[targets[doc]])
            if not any(anchor in h or h in anchor for h in hs):
                dangling.append(f"{src} → {doc}#{anchor}")
    assert not dangling, "悬空锚点: " + "; ".join(dangling)


def test_no_hard_constraint_double_write():
    """同一条数字约束（≤N/≥N+量词）在全部文档中至多出现一次——两处出现=两处真相。"""
    tok_re = re.compile(r"[≤≥]\s*\d+\s*[章条回次个成倍%]")
    seen: dict[str, set[str]] = {}
    for name, text in all_docs().items():
        for m in tok_re.findall(text):
            key = re.sub(r"\s+", "", m)
            seen.setdefault(key, set()).add(name)
    dupes = {k: sorted(v) for k, v in seen.items() if len(v) > 1}
    assert not dupes, f"双写约束: {dupes}——保留权威文件那处，其余改锚点引用"


def test_write_permission_matrix_single_source():
    texts = all_docs()
    owners = [n for n, t in texts.items() if re.search(r"^\| 主控（导演", t, flags=re.M)]
    assert owners == ["workflow"], f"写权限矩阵应唯一存在于 workflow，实际: {owners}"


def test_skills_self_contained_sections():
    for name in SKILL_DIRS:
        text = (ROOT / "agents" / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
        hs = set(headings(text))
        for sec in ("使命", "输入", "动作", "输出", "禁区", "退回与拒收"):
            assert any(sec in h for h in hs), f"{name} 缺岗位合同节: {sec}"


def test_workflow_covers_all_stages():
    text = DOCS["workflow"].read_text(encoding="utf-8")
    hs = " ".join(headings(text))
    for i in range(5):
        assert f"Stage {i}" in hs, f"workflow 缺 Stage {i} 小节"


def test_genre_guide_sections():
    text = DOCS["genre_guide"].read_text(encoding="utf-8")
    hs = headings(text)
    for genre in ("玄幻", "都市", "悬疑", "科幻", "言情", "武侠", "无限流", "治愈"):
        assert any(genre in h for h in hs), f"genre_guide 缺题材节: {genre}"
    # 题材参考是选择题素材：不得出现禁令式措辞
    banned = re.findall(r"必须|禁止|严禁", text)
    assert not banned, f"genre_guide 出现指令式措辞 {set(banned)}（只许「偏好/翻车/可选」）"


def test_inbox_readme_seeded_with_sample(tmp_path):
    book = Path(tmp_path) / "b"
    state.init_state(book)
    readme = book / "state" / "inbox" / "README.md"
    assert readme.is_file()
    body = readme.read_text(encoding="utf-8")
    for key in ("operation_id", "processed", "novel-studio.state-mutation/v2"):
        assert key in body


@pytest.mark.parametrize("name", sorted(SKILL_DIRS))
def test_skills_do_not_restuate_matrix_rows(name):
    """技能卡不得复述权限矩阵行（防止矩阵漂移出第二份）。"""
    text = (ROOT / "agents" / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
    assert not re.search(r"^\| (角色|主控|起草 Agent) \|", text, flags=re.M)


def test_templates_budget_and_guidance_only():
    """M4：templates 是容器不是枷锁——≤40 行、引导注释 ≤6 行、无写作教学。"""
    tdir = ROOT / "templates"
    names = sorted(p.name for p in tdir.glob("*.md"))
    assert {"project_bible.md", "main_plot.md", "volume_outline.md", "character_card.md", "beats.md"} == set(names)
    for fn in names:
        text = (tdir / fn).read_text(encoding="utf-8")
        assert len(text.splitlines()) <= TEMPLATE_BUDGET, f"{fn} 超 {TEMPLATE_BUDGET} 行"
        guid = re.findall(r"<!--.*?-->", text, flags=re.S)
        for block in guid:
            body_lines = [x for x in block.splitlines() if x.strip() not in ("<!--", "-->")]
            assert len(body_lines) <= 8, f"{fn} 引导注释超过 6~8 行（模板只说装什么）"
