# -*- coding: utf-8 -*-
"""对照验证：同一批字，上半用上游数据解码，下半用字趣已校准的字形。

如果两排形状一致，说明我的 stroke 解码与 y 轴朝向是对的。
"""
import io
import json
import os

from glyphs import GlyphBook

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZQ_GLYPHS = os.path.join(ROOT, "data", "glyphs.json")   # 我从字趣导出的那份（已校准）
CHARS = list("日月水木田耳")

book = GlyphBook()
zq = {}
if os.path.exists(ZQ_GLYPHS):
    d = json.loads(io.open(ZQ_GLYPHS, encoding="utf-8").read())
    for ch, rec in (d.get("chars") or {}).items():
        inner = rec["svg"].replace("{color}", "#1f2430")
        zq[ch] = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" '
                  'width="130" height="130">%s</svg>' % inner)


def cell(svg, label):
    return ("<div style='display:inline-block;margin:10px;text-align:center'>"
            "%s<div style='font-size:12px;color:#666'>%s</div></div>"
            % (svg or "<div style='width:130px;height:130px;border:1px dashed #ccc'></div>", label))


h = ["<html><body style='background:#fff;font-family:sans-serif;margin:10px'>"]
h.append("<div style='font-size:13px;color:#333;margin:6px 0'>① 上游数据集解码（我的渲染）</div>")
for ch in CHARS:
    h.append(cell(book.svg(ch, width=130), ch + " · %s笔" % (book.info(ch)["n_strokes"])))
h.append("<div style='font-size:13px;color:#333;margin:16px 0 6px'>② 字趣已校准字形（对照）</div>")
for ch in CHARS:
    h.append(cell(zq.get(ch), ch))
h.append("</body></html>")

out = os.path.join(ROOT, "_glyph_cmp.html")
io.open(out, "w", encoding="utf-8").write("".join(h))
print("  对照页 →", out)
