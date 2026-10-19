import io
# 1) 去掉未完成的 quiz 改动
p = "_patch_glyph2.py"
t = io.open(p, encoding="utf-8").read()
i = t.index("# ---------- 4) /api/quiz")
j = t.index('io.open(P, "w", encoding="utf-8", newline="\\n").write(t)')
t = t[:i] + t[j:]
io.open(p, "w", encoding="utf-8", newline="\n").write(t)
print("  已去掉 quiz 那步（避免改坏）")

# 2) glyphs.py 加模块级单例
p2 = "src/glyphs.py"
t2 = io.open(p2, encoding="utf-8").read()
if "book = GlyphBook()" not in t2:
    t2 = t2.rstrip() + "\n\n\n# 模块级单例：server 直接 glyphs.book.svg(ch)\nbook = GlyphBook()\n"
    io.open(p2, "w", encoding="utf-8", newline="\n").write(t2)
    print("  glyphs.py 已加 book 单例")
