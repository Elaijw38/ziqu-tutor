import io
p = "src/ask.py"
t = io.open(p, encoding="utf-8").read()
old = '''def _chars_in(q):
    s = q
    for w in FILLER:
        s = s.replace(w, "")
    return [c for c in dict.fromkeys(_CJK.findall(s))]'''
new = '''# 领域词本身不是"要查的字"，先剥掉再取字，否则"构件是什么"会被判成在问「构」「件」
DOMAIN_STRIP = ("甲骨文", "甲骨", "字形", "构形", "构件", "笔画", "王邑", "图卷",
                "讨伐", "象形", "会意", "假借", "通关", "弱点", "助教", "知识库")


def _chars_in(q):
    s = q
    for w in FILLER + DOMAIN_STRIP:
        s = s.replace(w, "")
    return [c for c in dict.fromkeys(_CJK.findall(s))]'''
assert t.count(old) == 1
io.open(p, "w", encoding="utf-8", newline="\n").write(t.replace(old, new))
print("  领域词不再被当成要查的字")
