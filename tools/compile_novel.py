"""
Compile finalized chapters into a single Markdown / TXT file with natural sorting.
Supports any novel workspace directory.
Usage:
    python tools/compile_novel.py --output novel_workspace/full_novel.md
    python tools/compile_novel.py --output novel_workspace/full_novel.txt --format txt
"""

import sys
import argparse
import re
from pathlib import Path

_tools_dir = Path(__file__).resolve().parent
if str(_tools_dir) not in sys.path:
    sys.path.insert(0, str(_tools_dir))

from novel_utils import resolve_workspace, natural_chapter_sort_key, reconfigure_utf8

reconfigure_utf8()

def compile_novel(workspace_path=None, output_path_str=None, output_format="md"):
    workspace_dir = resolve_workspace(workspace_path)
    manuscript_dir = workspace_dir / "05_manuscript"
    
    if not manuscript_dir.exists():
        print(f"[错误] 未找到 05_manuscript 目录: {manuscript_dir}")
        return 1

    finalized_files = [f for f in manuscript_dir.glob("**/finalized/*.md") if not f.name.startswith(".")]
    finalized_files = sorted(finalized_files, key=natural_chapter_sort_key)

    if not finalized_files:
        print("[错误] 没有找到任何定稿章节 (finalized/*.md)。")
        return 1

    bible_file = workspace_dir / "00_meta" / "project_bible.md"
    novel_title = "未命名长篇小说"
    if bible_file.exists():
        content = bible_file.read_text(encoding="utf-8")
        match = re.search(r"(?:^|\n)\s*[-*]?\s*\*\*书名.*?\*\*\s*[:：]\s*(.*)", content)
        if match and match.group(1).strip():
            raw_title = match.group(1).strip()
            novel_title = re.sub(r"^[《<]|>>|[》>]$", "", raw_title)
        else:
            title_header_match = re.search(r"#+\s*《?(.*?)》?\s*(?:项目圣经|设定|档案)", content)
            if title_header_match and title_header_match.group(1).strip():
                novel_title = re.sub(r"^[《<]|>>|[》>]$", "", title_header_match.group(1).strip())

    total_chinese_chars = 0

    if output_format.lower() == "txt":
        # Format for standard TXT reader (with full-width Chinese indent)
        lines = [f"{novel_title}\n\n", "=" * 42 + "\n", "目  录\n\n"]
        for idx, ch_file in enumerate(finalized_files, 1):
            content = ch_file.read_text(encoding="utf-8").strip()
            first_line = content.splitlines()[0] if content else f"第 {idx} 章"
            ch_title = re.sub(r"^#+\s*", "", first_line)
            lines.append(f"{idx:03d}. {ch_title}\n")
        
        lines.append("\n" + "=" * 42 + "\n\n")

        for idx, ch_file in enumerate(finalized_files, 1):
            content = ch_file.read_text(encoding="utf-8").strip()
            paras = content.split("\n\n")
            formatted_paras = []
            for p in paras:
                p_clean = p.strip()
                if not p_clean:
                    continue
                if p_clean.startswith("#"):
                    title_clean = re.sub(r"^#+\s*", "", p_clean)
                    formatted_paras.append(f"\n\n{title_clean}\n")
                else:
                    # Add standard Chinese paragraph indent
                    formatted_paras.append(f"　　{p_clean}")
            
            chapter_text = "\n".join(formatted_paras)
            total_chinese_chars += len(re.findall(r'[\u4e00-\u9fa5]', chapter_text))
            lines.append(chapter_text + "\n\n" + "-" * 32 + "\n\n")

    else:
        # Default Markdown format
        lines = [f"# 《{novel_title}》\n\n", "## 📑 目录\n\n"]
        for idx, ch_file in enumerate(finalized_files, 1):
            content = ch_file.read_text(encoding="utf-8").strip()
            first_line = content.splitlines()[0] if content else f"第 {idx} 章"
            ch_title = re.sub(r"^#+\s*", "", first_line)
            anchor_slug = f"chapter-{idx}"
            lines.append(f"- [{ch_title}](#{anchor_slug})\n")
        
        lines.append("\n---\n\n")

        for idx, ch_file in enumerate(finalized_files, 1):
            content = ch_file.read_text(encoding="utf-8").strip()
            total_chinese_chars += len(re.findall(r'[\u4e00-\u9fa5]', content))
            anchor_slug = f"chapter-{idx}"
            lines.append(f"<a id='{anchor_slug}'></a>\n\n" + content + "\n\n---\n\n")

    full_text = "".join(lines)

    # Resolve output path
    if output_path_str:
        out_p = Path(output_path_str)
        if not out_p.is_absolute():
            out_p = (Path(__file__).parent.parent / out_p).resolve()
    else:
        ext = "txt" if output_format.lower() == "txt" else "md"
        out_p = workspace_dir / f"full_novel.{ext}"

    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(full_text, encoding="utf-8")

    print("=" * 64)
    print(f" 📖 [全书编译成功] 《{novel_title}》")
    print(f"   - 编译章节: {len(finalized_files)} 章")
    print(f"   - 中文字数: 约 {total_chinese_chars:,} 字")
    print(f"   - 导出格式: {output_format.upper()}")
    print(f"   - 输出路径: {out_p}")
    print("=" * 64)
    return 0

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Universal Novel Studio 全书编译导出工具")
    parser.add_argument("--workspace", "-w", type=str, default=None, help="目标小说工作区路径 (默认为 novel_workspace)")
    parser.add_argument("--output", "-o", type=str, default=None, help="输出文件绝对或相对路径")
    parser.add_argument("--format", "-f", type=str, default="md", choices=["md", "txt"], help="导出格式: md 或 txt")
    args = parser.parse_args()

    sys.exit(compile_novel(workspace_path=args.workspace, output_path_str=args.output, output_format=args.format) or 0)
