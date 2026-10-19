# -*- coding: utf-8 -*-
"""补模块级单例 book（上次判断条件写错，因为 __main__ 里也有一行同名赋值，被误判为已存在）。"""
import io

P = r"C:\DSH\ziqu-tutor\src\glyphs.py"
t = io.open(P, encoding="utf-8").read()

mark = "\n\nif __name__ == \"__main__\":"
if "\nbook = GlyphBook()" in t.split(mark)[0]:
    print("  已有模块级单例")
else:
    head, sep, tail = t.partition(mark)
    head = head.rstrip() + "\n\n\n# 模块级单例：server 里直接用 glyphs.book.svg(ch)\nbook = GlyphBook()\n"
    io.open(P, "w", encoding="utf-8", newline="\n").write(head + sep + tail)
    print("  已在 __main__ 之前插入模块级 book 单例")
