# -*- coding: utf-8 -*-
"""
Universal Novel Initialization & Reset Tool (init_new_novel.py)
Initializes or force-resets the novel workspace by dynamically rendering templates from templates/.
Automatically syncs project metadata to novel_config.yaml.

Usage:
    python tools/init_new_novel.py --title "星际深渊" --genre "硬核科幻 / 幽闭悬疑" --protagonist "陈昂"
    python tools/init_new_novel.py --clean
"""

import sys
import shutil
import argparse
import re
from pathlib import Path

_tools_dir = Path(__file__).resolve().parent
if str(_tools_dir) not in sys.path:
    sys.path.insert(0, str(_tools_dir))

from novel_utils import resolve_workspace, reconfigure_utf8, project_root

reconfigure_utf8()

def clean_workspace_manuscripts(workspace: Path):
    """Cleans drafts and beats. Snapshots/processed-提案 are audit artifacts and are never removed here."""
    # Clean manuscripts
    ms_dir = workspace / "05_manuscript"
    if ms_dir.exists():
        for f in ms_dir.glob("**/*"):
            if f.is_file() and not f.name.startswith("."):
                try:
                    f.unlink()
                except Exception:
                    pass

    # Clean beats
    outlines_dir = workspace / "03_outlines"
    if outlines_dir.exists():
        for f in outlines_dir.glob("**/beats/*.md"):
            if not f.name.startswith("."):
                try:
                    f.unlink()
                except Exception:
                    pass

    # Clean full novel exports
    for exp_file in ["full_novel.md", "full_novel.txt"]:
        p = workspace / exp_file
        if p.exists():
            try:
                p.unlink()
            except Exception:
                pass

def sync_novel_config(title: str, genre: str, root_dir: Path):
    """Syncs novel project title and genre into root novel_config.yaml.

    - 保留原文件字节与行尾风格（CRLF/LF 不被重排版）；
    - 值未变化时完全不写盘（避免无意义的整文件 diff）；
    - 用 lambda 替换避免标题中反斜杠/引号破坏替换串。
    """
    cfg_path = root_dir / "novel_config.yaml"
    if cfg_path.exists():
        try:
            with open(cfg_path, "r", encoding="utf-8", newline="") as f:
                content = f.read()
            new_content = re.sub(r'(?m)^(\s*name:\s*)"[^"]*"',
                                 lambda m: f'{m.group(1)}"{title}"', content)
            new_content = re.sub(r'(default_genre:\s*)"[^"]*"',
                                 lambda m: f'{m.group(1)}"{genre}"', new_content)
            if new_content != content:
                with open(cfg_path, "w", encoding="utf-8", newline="") as f:
                    f.write(new_content)
            return True
        except Exception:
            pass
    return False

def render_template_file(template_path: Path, replacements: dict) -> str:
    """Reads a template file and replaces placeholders."""
    if not template_path.exists():
        return ""
    content = template_path.read_text(encoding="utf-8")
    for k, v in replacements.items():
        content = content.replace(k, v)
    return content

def init_novel(title="未命名新书", genre="通用题材", protagonist="主角名", clean_only=False,
               workspace_path=None, force=False):
    workspace = resolve_workspace(workspace_path)
    # 模板母版始终来自仓库根目录（脚本所在 tools/ 的上一级），与工作区位置无关。
    # 旧代码用 workspace.parent/templates，导致 -w 指向仓库外时静默退化为极简 fallback。
    root_dir = project_root()
    templates_dir = root_dir / "templates"

    if not templates_dir.exists():
        print(f"❌ [致命错误] 未找到模板母版目录: {templates_dir}")
        print("   请确认在 Universal Novel Studio 仓库根目录内运行，且 templates/ 目录完整。")
        return False

    print("=" * 68)
    print(f" 🚀 Universal Novel Studio - 全题材项目初始化与母版创生引擎")
    print(f" 📂 目标工作区: {workspace.name} (绝对路径: {workspace})")
    if clean_only:
        print(" 🧹 清理模式：仅清空手稿与分章细纲（状态/快照/processed 保留）")
    else:
        print(f" 📖 新书标题: 《{title}》 | 题材: {genre} | 核心主角: {protagonist}")
    print("=" * 68)

    # 防止误操作：工作区已存在定稿/细纲/状态机时，必须显式 --force 才会清空重建。
    existing_manuscripts = list((workspace / "05_manuscript").glob("**/ch_*.md")) if (workspace / "05_manuscript").exists() else []
    existing_beats = list((workspace / "03_outlines").glob("**/beats/ch_*_beats.md")) if (workspace / "03_outlines").exists() else []
    if (existing_manuscripts or existing_beats) and not force and not clean_only:
        print(f"⚠️ [中止] 工作区 {workspace} 已存在 {len(existing_manuscripts)} 份手稿 / {len(existing_beats)} 份细纲。")
        print("   初始化会清空这些内容。如确认要重开，请追加 --force；仅清空稿件请使用 `studio.py clean`。")
        return False

    # clean 后手稿虽空，但旧书状态机/账本/伏笔仍在：非 force 重开会导致
    # "新模板 + 旧状态机"的混合书。检测到旧书数据时同样要求 --force。
    import json as _json
    state_probe = workspace / "04_timeline_and_state"
    has_old_state = False
    if state_probe.exists():
        try:
            guns_p = state_probe / "chekhov_guns.json"
            if guns_p.exists() and (_json.loads(guns_p.read_text(encoding="utf-8-sig")).get("guns") or []):
                has_old_state = True
            led_p = state_probe / "economy_ledger.json"
            if not has_old_state and led_p.exists():
                txs = _json.loads(led_p.read_text(encoding="utf-8-sig")).get("transactions") or []
                if len(txs) > 1:
                    has_old_state = True
        except Exception:
            has_old_state = False
    if has_old_state and not force and not clean_only:
        print("⚠️ [中止] 工作区仍保留旧书状态机数据（伏笔/流水）。")
        print("   直接重开会产出『新设定 + 旧状态』的混合书。确认重开请追加 --force。")
        return False

    if force:
        # --force = 重开新书：旧书的状态机 SSOT、题材档案、梗概脊柱与未决提案
        # 一并重置，避免旧书数据（伏笔/账本/心智阶段）泄漏进新书。
        state_dir = workspace / "04_timeline_and_state"
        reset_count = 0
        if state_dir.exists():
            for key in ("current_state", "chekhov_guns", "misunderstandings",
                        "character_growth_arcs", "timeline", "economy_ledger",
                        "chapter_synopsis"):
                for suffix in (".json", ".md"):
                    p = state_dir / f"{key}{suffix}"
                    if p.exists():
                        p.unlink()
                        reset_count += 1
            inbox = state_dir / "state_inbox"
            if inbox.exists():
                for pf in inbox.glob("*.json"):
                    pf.unlink()  # 旧书未决提案绝不能被合并进新书状态机
                    reset_count += 1
                # failed/ 里的旧提案会被 sync 自动捡回，必须一并清空；
                # processed/ 属审计档案但已属旧书，同样重置（快照见下）。
                for sub in ("failed", "processed"):
                    sub_dir = inbox / sub
                    if sub_dir.exists():
                        for pf in sub_dir.glob("*.json"):
                            pf.unlink()
                            reset_count += 1
            snaps = state_dir / "snapshots"
            if snaps.exists():
                import shutil as _sh
                _sh.rmtree(snaps, ignore_errors=True)
                reset_count += 1
        gp_file = workspace / "00_meta" / "genre_profile.json"
        if gp_file.exists():
            gp_file.unlink()
            reset_count += 1
        if reset_count:
            print(f"   🧹 [--force] 已重置旧书残留 {reset_count} 个文件（状态机/只读视图/梗概脊柱/未决提案/题材档案）")

        # --force 是显式“重开新书”：旧书快照一并清除，防止 rollback 把旧书状态导入新书。
        snap_dir = state_dir / "snapshots"
        if snap_dir.exists():
            for d in snap_dir.glob("*"):
                if d.is_dir():
                    shutil.rmtree(d, ignore_errors=True)

    # 1. Ensure Full Directory Topology Exists
    # （novel_workspace 整体被 gitignore，无需 .gitkeep 占位；空目录由 mkdir 直接保证）
    dirs = [
        workspace / "00_meta",
        workspace / "01_world",
        workspace / "02_characters" / "profiles",
        workspace / "03_outlines" / "vol_01" / "beats",
        workspace / "04_timeline_and_state" / "snapshots",
        workspace / "04_timeline_and_state" / "state_inbox" / "processed",
        workspace / "04_timeline_and_state" / "state_inbox" / "failed",
        workspace / "05_manuscript" / "vol_01" / "raw_drafts",
        workspace / "05_manuscript" / "vol_01" / "finalized",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)

    # 2. Clean Existing Artifacts
    clean_workspace_manuscripts(workspace)
    
    if clean_only:
        print("✨ [清空完成] 已清空所有手稿与分章细纲（状态快照与 processed 提案保留）。")
        return True

    # Clean old character profiles when initializing
    profiles_dir = workspace / "02_characters" / "profiles"
    if profiles_dir.exists():
        for pf in profiles_dir.glob("*.md"):
            if not pf.name.startswith("."):
                try:
                    pf.unlink()
                except Exception:
                    pass

    # Replacement dictionary.
    # {{GENRE}} is the authoritative placeholder for 主类型 in project_bible;
    # [xxx] placeholders are human-fill hints and are intentionally left alone.
    replacements = {
        "[《书名》]": f"《{title}》",
        "《[书名]》": f"《{title}》",
        "[书名]": title,
        "{{GENRE}}": genre,
        "[主角姓名]": protagonist,
        "[主角名]": protagonist,
        "[角色名]": protagonist,
        "[角色姓名]": protagonist,
        "[身份定位]": "核心主角",
        "[本卷卷名]": "破局立足与名动一方",
        "《[首卷卷名]》": "破局立足与名动一方",
        "[首卷卷名]": "破局立足与名动一方",
        "[起始章]": "1",
        "[结束章]": "30",
        "[X]": "1",
        "[章节核心看点标题]": "破局之始！初显锋芒",
    }

    missing_templates = []

    # Helper function to write from template (missing templates are reported, never silent)
    def write_from_template(rel_template_path: str, target_rel_path: str, fallback_content: str):
        t_file = templates_dir / rel_template_path
        target_file = workspace / target_rel_path
        target_file.parent.mkdir(parents=True, exist_ok=True)
        if t_file.exists():
            content = render_template_file(t_file, replacements)
            target_file.write_text(content, encoding="utf-8")
        else:
            # 母版缺失属于工程异常：写入 fallback 占位并记录，最终显式告警。
            target_file.write_text(fallback_content, encoding="utf-8")
            missing_templates.append(rel_template_path)

    # 3. 00_meta/project_bible.md
    write_from_template(
        "00_meta/project_bible.template.md",
        "00_meta/project_bible.md",
        f"# 小说项目圣经 (Project Bible)\n\n## 1. 基本信息\n- **书名（主选）**：《{title}》\n- **主类型**：{genre}\n"
    )

    # 4. 01_world/
    write_from_template("01_world/world_rules.template.md", "01_world/world_rules.md", "# 世界底层规则与力量/经济体系\n")
    write_from_template("01_world/factions.template.md", "01_world/factions.md", "# 势力分布与博弈格局\n")
    write_from_template("01_world/geography.template.md", "01_world/geography.md", "# 地理空间与距离尺度\n")

    # 5. 02_characters/
    write_from_template("02_characters/character_index.template.md", "02_characters/character_index.md", "# 核心角色索引表\n")
    write_from_template("02_characters/character_card.template.md", "02_characters/profiles/protagonist.md", f"# 角色姓名：{protagonist} (主角)\n")

    # 6. 03_outlines/
    write_from_template("03_outlines/main_plot.template.md", "03_outlines/main_plot.md", "# 全书主线大纲\n")
    write_from_template("03_outlines/volume_outline.template.md", "03_outlines/vol_01_outline.md", "# 第 1 卷卷纲\n")
    write_from_template("03_outlines/chapter_beats.template.md", "03_outlines/vol_01/beats/ch_001_beats.md", "# 第 1 章 Beats 细纲\n")

    # 7. 04_timeline_and_state/（JSON SSOT + 自动渲染的 Markdown 只读视图）
    try:
        import state_store as ss
        ss.init_state_files(workspace)
        print("   - 04_timeline_and_state/ (JSON 状态 SSOT + Markdown 只读视图)")
    except Exception as e:
        print(f"   ⚠️ 状态文件初始化失败: {e}")

    # 7.4 Genre profile (P3-4)：按题材拷贝可微调的题材档案到 00_meta/
    try:
        from genre_profile import install_profile_for_genre
        gp = install_profile_for_genre(workspace, genre)
        label = gp.read_text(encoding="utf-8")
        try:
            import json as _json
            matched_label = _json.loads(label).get("label", "")
        except Exception:
            matched_label = ""
        print(f"   - 00_meta/genre_profile.json (题材档案：已按「{genre}」匹配为 {matched_label})")
    except Exception as e:
        print(f"   ⚠️ 题材档案生成失败（不影响初始化）: {e}")

    # 7.5 State-inbox guide and sample proposal
    write_from_template(
        "04_timeline_and_state/state_inbox/README.template.md",
        "04_timeline_and_state/state_inbox/README.md",
        "# 状态变更提案投递箱 (State Inbox)\n"
    )
    write_from_template(
        "04_timeline_and_state/state_inbox/ch_sample.proposal.template.json",
        "04_timeline_and_state/state_inbox/ch_sample.proposal.template.json",
        '{\n  "schema": "novel-studio.state-mutation/v1"\n}\n'
    )

    # 8. Sync Root novel_config.yaml —— 仅当工作区位于本仓库内时才回写仓库配置，
    # 避免 -w 指向仓库外（或测试临时目录）时污染仓库的 novel_config.yaml。
    synced = False
    try:
        if workspace.parent.resolve() == root_dir.resolve():
            synced = sync_novel_config(title, genre, root_dir)
    except Exception:
        synced = False

    print(f"✨ [初始化成功] 小说《{title}》全套标准化资产已从 templates/ 母版中心生成至: {workspace.name}/")
    print("   - 00_meta/project_bible.md (项目圣经)")
    print("   - 00_meta/genre_profile.json (题材档案)")
    print("   - 01_world/ (世界观、势力格局、地理空间与防通胀购买力锚定表)")
    print("   - 02_characters/ (角色索引表、主角人物卡)")
    print("   - 03_outlines/ (全局主线、首卷卷纲与第 1 章 Beats 细纲)")
    print("   - 04_timeline_and_state/ (状态机、编年史、心智台账、多资源复式账本、伏笔池、误会台账)")
    print("   - 05_manuscript/vol_01/ (手稿目录)")
    if synced:
        print("   - novel_config.yaml (全局配置已自动同步更新书名与题材)")
    print("\n📝 [Stage 0 资料支撑待填清单] 以下文件当前是模板骨架，"
          "进入 Stage 1 前必须由总策划结合用户对齐结果填成真实设定"
          "（pack 会自动装载它们作为写作支撑）：")
    print("   1. 00_meta/project_bible.md   ← 核心看点/基调/能力阶梯（全书最高锚点；字数硬门限以 genre_profile.json 为准）")
    print("   2. 01_world/world_rules.md    ← 能力阶梯/规则/经济锚点")
    print("   3. 01_world/factions.md + geography.md ← 势力与地理")
    print("   4. 02_characters/profiles/protagonist.md ← 主角性格/动机/能力/心智起点")
    print("   5. 02_characters/character_index.md ← 首卷核心人物表")
    print("   6. 03_outlines/main_plot.md + vol_01_outline.md ← 三线交织主线/卷末高潮")
    print("   7. 03_outlines/vol_01/beats/ch_001_beats.md ← 第 1 章细纲")
    if missing_templates:
        print("\n⚠️ [警告] 以下母版文件缺失，已用极简占位内容代替，请补齐 templates/ 母版：")
        for mt in missing_templates:
            print(f"   - {mt}")
    print("=" * 68)
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Universal Novel Studio 项目初始化与脚手架创生工具")
    parser.add_argument("--workspace", "-w", type=str, default=None, help="目标小说工作区路径 (默认为 novel_workspace)")
    parser.add_argument("--title", "-t", type=str, default="未命名新书", help="小说书名")
    parser.add_argument("--genre", "-g", type=str, default="通用题材", help="小说题材分类")
    parser.add_argument("--protagonist", "-p", type=str, default="主角名", help="主角姓名")
    parser.add_argument("--clean", action="store_true", help="清空已有稿件与细纲（保留状态/快照/审计资料）")
    parser.add_argument("--force", action="store_true", help="工作区已有手稿/细纲时仍强制重建（危险：会清空已有稿件）")
    args = parser.parse_args()

    ok = init_novel(title=args.title, genre=args.genre, protagonist=args.protagonist,
                    clean_only=args.clean, workspace_path=args.workspace, force=args.force)
    sys.exit(0 if ok else 1)
