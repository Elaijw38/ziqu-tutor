import io
p = "src/ask.py"
t = io.open(p, encoding="utf-8").read()

old = """    # 用户点了名（问句里出现了知识库里的字）：只答这些字，别扯别的
    if chars:
        named = [(r, s) for r, s in hits if r.get("char") in chars]
        if named:
            hits = named
    else:
        # 没点名 → 相关度还低，就反问，不要硬凑
        if best_score < MIN_SCORE:
            return _refuse(
                "我不确定你问的是哪个字。可以说具体一点，比如："
                "「日为什么写成圆的」「家为什么是屋顶下有猪」「虎怎么打」。", chars)
"""
new = """    # 用户点了名（问句里出现了知识库里的字）：只答这些字，别扯别的
    named = [(r, s) for r, s in hits if r.get("char") in chars]
    if chars:
        # 出现了"像字"的词、但知识库里没有这个字 → 直接说没有，别拿别的字凑
        if not named:
            return _refuse(
                "知识库里没有%s这个字。现在覆盖 %d 个字（王邑 61 个实物、讨伐 21 关、"
                "名录 88 尊），可以换个字试试。"
                % ("「" + "」「".join(chars[:3]) + "」" if chars else "你说的", len(
                    {r.get("char") for r in idx.rows if r.get("char")})), chars)
        hits = named
    else:
        # 没点名：必须是本领域的问题（否则就是"今天天气"这类），且相关度够
        if best_score < MIN_SCORE or not any(w in q for w in DOMAIN_WORDS):
            return _refuse(
                "我是甲骨文助教，只回答与汉字字形、王邑图卷、构件讨伐相关的问题。"
                "试试：「家为什么是屋顶下有猪」「日为什么写成圆的」「虎怎么打」。", chars)
"""
assert t.count(old) == 1
t = t.replace(old, new)

# 领域词表
t = t.replace('MIN_SCORE = 7.0      # 低于这个分视为"知识库里没有"',
              'MIN_SCORE = 7.0      # 低于这个分视为"知识库里没有"\n'
              'DOMAIN_WORDS = ("甲骨", "字形", "构形", "构件", "笔画", "王邑", "图卷", "讨伐",\n'
              '                "Boss", "boss", "象形", "会意", "假借", "字", "打", "通关", "几笔")')

# 意图：问"怎么打"优先给带 play 的条目；问"怎么写的"优先给带"构形"的
old2 = """def _dedupe_by_char(hits, limit):"""
new2 = """def _intent(q):
    if any(w in q for w in ("打", "击破", "通关", "弱点", "怎么过", "Boss", "boss")):
        return "fight"
    if any(w in q for w in ("怎么写", "怎么写", "构形", "象形", "为什么", "几笔", "笔画", "意思", "代表")):
        return "form"
    return "any"


def _dedupe_by_char(hits, limit, intent="any"):"""
assert t.count(old2) == 1
t = t.replace(old2, new2)

old3 = """            r0, s0 = best[key]
            if len(row["text"]) > len(r0["text"]):
                best[key] = (row, score)"""
new3 = """            r0, s0 = best[key]
            def rank(r):
                txt = r["text"]
                if intent == "fight":
                    return (1 if "打" in txt or "击破" in txt else 0, len(txt))
                if intent == "form":
                    return (1 if ("构形" in txt or "象" in txt) else 0, len(txt))
                return (0, len(txt))
            if rank(row) > rank(r0):
                best[key] = (row, score)"""
assert t.count(old3) == 1
t = t.replace(old3, new3)
t = t.replace("    picks = _dedupe_by_char(hits, 3)", "    picks = _dedupe_by_char(hits, 3, _intent(q))")
io.open(p, "w", encoding="utf-8", newline="\n").write(t)
print("  已加：同名拒答、领域词门槛、意图优先")
