# -*- coding: utf-8 -*-
"""把 docs/项目进展报告.md 转成 docx，供提交/打印。

只用 python-docx：识别 # / ## 标题、| 表格 |、``` 代码块、普通段落与列表。
中文字体设为宋体正文 + 黑体标题，A4 页边距。
"""
import io
import os
import re

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Pt, Cm, RGBColor

ROOT = r"C:\DSH\ziqu-tutor"
SRC = os.path.join(ROOT, "docs", "项目进展报告.md")  # 可用 argv 覆盖
DST = os.path.join(ROOT, "out", "甲骨文AI助教-项目进展报告.docx")  # 可用 argv 覆盖


def set_cn(run, name="宋体", size=10.5, bold=False, color=None):
    run.font.name = name
    run.font.size = Pt(size)
    run.font.bold = bold
    if color:
        run.font.color.rgb = RGBColor(*color)
    run._element.rPr.rFonts.set(qn("w:eastAsia"), name)


def main():
    import sys
    src = sys.argv[1] if len(sys.argv) > 1 else SRC
    dst = sys.argv[2] if len(sys.argv) > 2 else DST
    lines = io.open(src, encoding="utf-8").read().splitlines()
    doc = Document()

    # 页面
    for s in doc.sections:
        s.left_margin = Cm(2.2)
        s.right_margin = Cm(2.2)
        s.top_margin = Cm(2.0)
        s.bottom_margin = Cm(2.0)

    # 默认样式
    st = doc.styles["Normal"]
    st.font.name = "宋体"
    st.font.size = Pt(10.5)
    st.element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
    st.paragraph_format.line_spacing = 1.45
    st.paragraph_format.space_after = Pt(3)

    i = 0
    in_code = False
    code_buf = []

    def flush_code():
        nonlocal code_buf
        if not code_buf:
            return
        p = doc.add_paragraph()
        p.paragraph_format.left_indent = Cm(0.6)
        p.paragraph_format.space_before = Pt(2)
        p.paragraph_format.space_after = Pt(6)
        r = p.add_run("\n".join(code_buf))
        set_cn(r, name="Consolas", size=9)
        code_buf = []

    while i < len(lines):
        line = lines[i]
        s = line.rstrip()

        # 代码块
        if s.strip().startswith("```"):
            if in_code:
                flush_code()
                in_code = False
            else:
                in_code = True
            i += 1
            continue
        if in_code:
            code_buf.append(line)
            i += 1
            continue

        # 表格
        if s.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s\-:|]+\|$", lines[i + 1].strip()):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not re.match(r"^[\s\-:|]+$", lines[i].strip().strip("|")):
                    rows.append(cells)
                i += 1
            if rows:
                ncol = max(len(r) for r in rows)
                t = doc.add_table(rows=len(rows), cols=ncol)
                t.style = "Table Grid"
                for ri, cells in enumerate(rows):
                    for ci in range(ncol):
                        cell = t.cell(ri, ci)
                        cell.text = ""
                        p = cell.paragraphs[0]
                        r = p.add_run(cells[ci] if ci < len(cells) else "")
                        set_cn(r, size=9, bold=(ri == 0))
                doc.add_paragraph()
            continue

        # 标题
        m = re.match(r"^(#{1,4})\s+(.*)$", s)
        if m:
            level, txt = len(m.group(1)), m.group(2).strip()
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(10 if level <= 2 else 6)
            p.paragraph_format.space_after = Pt(4)
            r = p.add_run(txt)
            size = {1: 16, 2: 13.5, 3: 12, 4: 11}[level]
            set_cn(r, name="黑体", size=size, bold=True,
                   color=(0x16, 0x33, 0x6B) if level <= 2 else None)
            if level == 1:
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            i += 1
            continue

        # 分隔线
        if s.strip() == "---":
            i += 1
            continue

        # 列表
        m = re.match(r"^\s*[-*]\s+(.*)$", s)
        if m:
            p = doc.add_paragraph(style="List Bullet")
            set_cn(p.add_run(m.group(1)))
            i += 1
            continue
        m = re.match(r"^\s*(\d+)\.\s+(.*)$", s)
        if m:
            p = doc.add_paragraph(style="List Number")
            set_cn(p.add_run(m.group(2)))
            i += 1
            continue

        if not s.strip():
            i += 1
            continue

        # 普通段落（处理 **粗体**）
        p = doc.add_paragraph()
        parts = re.split(r"(\*\*[^*]+\*\*)", s)
        for part in parts:
            if not part:
                continue
            if part.startswith("**") and part.endswith("**"):
                set_cn(p.add_run(part[2:-2]), bold=True)
            else:
                set_cn(p.add_run(part))
        i += 1

    flush_code()
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    doc.save(dst)
    print("  已生成 %s（%.0f KB）" % (dst, os.path.getsize(dst) / 1024))


if __name__ == "__main__":
    main()
