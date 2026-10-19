# -*- coding: utf-8 -*-
"""收紧字形挑选：只显示"回答真正用到的字"，不要把问句里的虚词字也画出来。

规则：
  1. 优先取出处条目对应的字（citations 的 char / id 末段）；
  2. 没有出处时，才退回问句里出现的字，且必须在**课程字表**内（王邑61+讨伐21+名录88）；
  3. 最多 4 个，去重。
"""
import io
import os

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src", "server.py")
t = io.open(P, encoding="utf-8").read()

old_start = t.index('            # 把回答涉及的字形一并返回：先看用户问到的字，再看出处里的字')
old_end = t.index('            self._json(res)', old_start)
new = '''            # 选字：先取出处对应的字（这才是"回答用到的"），没有出处才退回问句里的课程字
            course_chars = {r.get("char") for r in get_index().rows
                            if r.get("char") and r.get("kind") in ("wangyi", "boss", "codex")}
            picked, seen = [], set()

            def _push(ch):
                if len(picked) < 4 and ch and ch not in seen and glyph_mod.book.has(ch):
                    seen.add(ch)
                    picked.append(ch)

            for c in (res.get("citations") or []):
                ch = c.get("char") or str(c.get("id") or "").split(".")[-1]
                if len(ch) == 1:
                    _push(ch)
            if not picked:
                for ch in q:
                    if ch in course_chars:
                        _push(ch)
            res["glyphs"] = [
                {"char": c,
                 "strokes": glyph_mod.book.info(c).get("n_strokes"),
                 "url": "/api/glyph/" + urllib.parse.quote(c),
                 "download": "/api/glyph/" + urllib.parse.quote(c) + "?size=512&download=1"}
                for c in picked
            ]
'''
t = t[:old_start] + new + t[old_end:]
io.open(P, "w", encoding="utf-8", newline="\n").write(t)
print("  已收紧字形挑选逻辑")
