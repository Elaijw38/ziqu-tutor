# -*- coding: utf-8 -*-
"""修 put()：先清空单元格原有内容再写，避免占位说明残留在正文里。"""
import io

P = r"C:\DSH\ziqu-tutor\_fill_form.py"
t = io.open(P, encoding="utf-8").read()

start = t.index("def put(cell, text, size=9.5):")
end = t.index("def tick(cell, label):")
new = '''def put(cell, text, size=9.5):
    """写进单元格：**先清空原有段落与文字**（表里那些"可填写 Demo、视频…"
    的占位说明必须清掉，否则会和填入内容混在一起），再按段落写入。"""
    for p in cell.paragraphs[1:]:
        p._element.getparent().remove(p._element)
    p = cell.paragraphs[0]
    for r in list(p.runs):
        r._element.getparent().remove(r._element)
    run = p.add_run(text)
    run.font.size = Pt(size)
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(2)


'''
t = t[:start] + new + t[end:]
io.open(P, "w", encoding="utf-8", newline="\n").write(t)
print("  put() 已改为先清空")
