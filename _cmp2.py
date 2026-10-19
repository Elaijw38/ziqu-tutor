# -*- coding: utf-8 -*-
"""对照：上游解码 vs 字趣校准字形（同字同尺寸）。"""
import io
import json
import os
import sys

ROOT = r"C:\DSH\ziqu-tutor"
sys.path.insert(0, os.path.join(ROOT, "src"))
from glyphs import GlyphBook  # noqa: E402

book = GlyphBook()
zq = {}
p = os.path.join(ROOT, "data", "glyphs.json")
if os.path.exists(p):
    d = json.loads(io.open(p, encoding="utf-8").read())
    for ch, rec in (d.get("chars") or {}).items():
        inner = rec["svg"].replace("{color}", "#1f2430")
        zq[ch] = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" '
                  'width="120" height="120">%s</svg>' % inner)

CH = [c for c in "日月水木田耳口" if c in zq]


def cell(svg, cap):
    body = svg or "<div style='width:120px;height:120px;border:1px dashed #ccc'></div>"
    return ("<div style='display:inline-block;margin:8px;text-align:center'>%s"
            "<div style='font-size:12px;color:#666'>%s</div></div>" % (body, cap))


rows = ["<html><body style='background:#fff;font-family:sans-serif;margin:12px'>"]
rows.append("<div style='font-size:13px;margin:4px 0'>① 上游解码（glyphs.py）</div>")
for ch in CH:
    rows.append(cell(book.svg(ch, width=120), ch))
rows.append("<div style='font-size:13px;margin:14px 0 4px'>② 字趣已校准（data/glyphs.json）</div>")
for ch in CH:
    rows.append(cell(zq.get(ch), ch))
rows.append("</body></html>")

out = os.path.join(ROOT, "_glyph_cmp.html")
io.open(out, "w", encoding="utf-8").write("".join(rows))
print("  对照页 →", out, " 字数", len(CH))
