# -*- coding: utf-8 -*-
"""从字趣只读导出甲骨字形（逐笔几何），供助教按需渲染字形图。

为什么不导出图片：字趣里存的是**逐笔路径 + 变换**，导出成 SVG 可以任意缩放、
任意配色（深色/浅色主题都能用），体积也只有几 KB；导出 PNG 反而更重更糊。

产出 data/glyphs.json：
    {"canvas":100,
     "attribution":{...},
     "chars":{"日":{"svg":"<g transform=...><path .../></g>","strokes":3}, ...}}
"""
import io
import json
import os

ZQ = r"C:\DSH\字趣\js\core\_data.js"
OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
os.makedirs(OUT_DIR, exist_ok=True)
OUT = os.path.join(OUT_DIR, "glyphs.json")


def main():
    t = io.open(ZQ, encoding="utf-8", errors="replace").read()
    i = t.find("App.glyphs = ") + len("App.glyphs = ")
    depth, j = 0, i
    while j < len(t):
        ch = t[j]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                j += 1
                break
        j += 1
    g = json.loads(t[i:j])
    parts = g.get("parts") or {}
    canvas = g.get("canvas") or 100

    chars = {}
    for name, rec in parts.items():
        pieces = rec.get("pieces") or []
        if not pieces:
            continue
        ds = " ".join(p.get("d") or "" for p in pieces)
        svg = ('<g transform="%s"><path d="%s" fill="none" stroke="{color}" '
               'stroke-width="%s" stroke-linecap="round" stroke-linejoin="round"/></g>'
               % (rec.get("transform") or "", ds, rec.get("strokeWidth") or 0.15))
        chars[name] = {"svg": svg, "strokes": len(pieces),
                       "strokeWidth": rec.get("strokeWidth")}

    out = {
        "_note": "由字趣 js/core/_data.js 的 App.glyphs 只读导出；逐笔几何 + 变换，勿手改",
        "canvas": canvas,
        "attribution": g.get("attribution") or {},
        "chars": chars,
    }
    io.open(OUT, "w", encoding="utf-8", newline="\n").write(
        json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    print("  导出 %d 个甲骨字形 → %s  %.0f KB"
          % (len(chars), OUT, os.path.getsize(OUT) / 1024))
    a = out["attribution"]
    print("  授权：%s / %s / DOI %s"
          % (a.get("dataset", "?"), a.get("license", "?"), a.get("doi", "?")))


if __name__ == "__main__":
    main()
