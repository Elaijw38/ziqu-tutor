# -*- coding: utf-8 -*-
"""甲骨字形渲染：把上游 stroke 字段解析成 SVG。

字段编码（实测 1203 条推出）：
    "8,-64,0,-10,0,12,0,-64,-64"
     └ 第一个数 = n_points
       之后按**成对**数读坐标
       笔画分隔符 = (-64, 0)
       结束符     = (-64, -64)

坐标系：上游取值大致在 -64..64，原点居中；SVG 是 y 向下，所以要翻转 y。
"""
import io
import json
import os

DEFAULT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "data", "upstream", "jgw_1203_labeled.json")

SEP = (-64.0, 0.0)
END = (-64.0, -64.0)


def parse_strokes(stroke_str):
    toks = [t.strip() for t in (stroke_str or "").split(",")]
    nums = []
    for t in toks:
        if not t:
            continue
        try:
            nums.append(float(t))
        except ValueError:
            pass
    if not nums:
        return []
    body = nums[1:]  # 去掉开头的 n_points
    strokes, cur = [], []
    i = 0
    while i + 1 < len(body):
        a, b = body[i], body[i + 1]
        i += 2
        if (a, b) == END:
            if cur:
                strokes.append(cur)
            cur = []
            break
        if (a, b) == SEP:
            if cur:
                strokes.append(cur)
            cur = []
            continue
        cur.append((a, b))
    if cur:
        strokes.append(cur)
    return strokes


def bounds(strokes):
    xs = [p[0] for s in strokes for p in s]
    ys = [p[1] for s in strokes for p in s]
    if not xs:
        return (0, 0, 1, 1)
    return min(xs), min(ys), max(xs), max(ys)


def to_svg(strokes, color="#1f2430", width=120, pad=8, flip_y=True):
    """返回独立的 SVG 字符串（等比缩放进正方形，居中）。"""
    if not strokes:
        return None
    x0, y0, x1, y1 = bounds(strokes)
    w = max(x1 - x0, 1e-6)
    h = max(y1 - y0, 1e-6)
    size = max(w, h)
    px = (100 - 2 * pad) / size
    cx = (x0 + x1) / 2.0
    cy = (y0 + y1) / 2.0

    def px_of(x):
        return 50 + (x - cx) * px

    def py_of(y):
        yy = -y if flip_y else y
        return 50 + (yy + cy) * px if flip_y else 50 + (yy - cy) * px

    parts = []
    for s in strokes:
        if len(s) == 1:
            x, y = s[0]
            parts.append('<circle cx="%.2f" cy="%.2f" r="1.4" fill="%s"/>'
                         % (px_of(x), py_of(y), color))
            continue
        d = "M " + " L ".join("%.2f %.2f" % (px_of(x), py_of(y)) for x, y in s)
        parts.append('<path d="%s" fill="none" stroke="%s" stroke-width="3.2" '
                     'stroke-linecap="round" stroke-linejoin="round"/>' % (d, color))
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" '
            'width="%d" height="%d">%s</svg>' % (width, width, "".join(parts)))


class GlyphBook:
    """按现代字取字形；同字多形时取笔画数最多的那个（信息量更大，也更好看）。"""

    def __init__(self, path=DEFAULT):
        self.records = json.loads(io.open(path, encoding="utf-8").read())
        self.by_char = {}
        for r in self.records:
            ch = r.get("modern_char") or ""
            if not ch:
                continue
            cur = self.by_char.get(ch)
            if cur is None or (r.get("n_strokes") or 0) > (cur.get("n_strokes") or 0):
                self.by_char[ch] = r

    def has(self, ch):
        return ch in self.by_char

    def svg(self, ch, color="#1f2430", width=120):
        r = self.by_char.get(ch)
        if not r:
            return None
        return to_svg(parse_strokes(r.get("stroke")), color=color, width=width)

    def info(self, ch):
        r = self.by_char.get(ch) or {}
        return {"char": ch, "glyph_id": r.get("glyph_id"),
                "n_strokes": r.get("n_strokes"), "n_points": r.get("n_points"),
                "pinyin": r.get("pinyin")}


# 模块级单例：server 里直接用 glyphs.book.svg(ch)
book = GlyphBook()


if __name__ == "__main__":
    book = GlyphBook()
    print("  覆盖现代字：%d 个" % len(book.by_char))
    out = os.path.join(os.path.dirname(DEFAULT), "..", "..", "_glyph_test.html")
    html = ["<html><body style='background:#fff;font-family:sans-serif'>"]
    for ch in "日月家虎水木田":
        svg = book.svg(ch, width=140)
        if not svg:
            html.append("<div style='color:#c00'>%s 无字形</div>" % ch)
            continue
        i = book.info(ch)
        html.append("<div style='display:inline-block;margin:8px;text-align:center'>"
                    "%s<div style='font-size:12px;color:#666'>%s 笔</div></div>"
                    % (svg, i["n_strokes"]))
    html.append("</body></html>")
    io.open(out, "w", encoding="utf-8").write("".join(html))
    print("  预览 ——>", os.path.abspath(out))
