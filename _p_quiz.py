# -*- coding: utf-8 -*-
"""让出题按题型轮转，并优先考"答错过的字"。

上一版三个题全是「打法」——因为按行遍历，谁先满足条件谁入选。
现在按 comp → form → play 轮转；同时把错题字提到候选最前面。
"""
import io
import os

p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src", "quiz.py")
t = io.open(p, encoding="utf-8").read()

old_start = t.index("def make_quiz(")
old_end = t.index("def grade(")
new_fn = '''def make_quiz(n=3, seed=20261104):
    import learner
    idx = get_index()
    forms, comps, plays = _pool(idx)
    rnd = random.Random(seed)

    # 候选顺序：答错过的字 → 没学过的字 → 其它（都打散，但错题优先）
    d = learner.load()
    wrong = [a["char"] for a in (d.get("attempts") or []) if not a.get("ok") and a.get("char")]
    learned = learner.learned_chars(d)
    rows = [r for r in idx.rows if r.get("char")]
    by_char = {}
    for r in rows:
        by_char.setdefault(r["char"], r)

    def order(c):
        return (0 if c in wrong else (1 if c not in learned else 2))

    cand = sorted(by_char.values(), key=lambda r: order(r["char"]))
    # 同档内打散，避免永远考同几个字
    buckets = {}
    for r in cand:
        buckets.setdefault(order(r["char"]), []).append(r)
    cand = []
    for k in sorted(buckets):
        part = buckets[k][:]
        rnd.shuffle(part)
        cand.extend(part)

    TYPE_CYCLE = ["comp", "form", "play"]
    items, used_chars, ti = [], set(), 0
    for want in TYPE_CYCLE * max(1, n):
        if len(items) >= n:
            break
        picked = None
        for r in cand:
            ch = r["char"]
            if ch in used_chars:
                continue
            m = r.get("meta") or {}
            if want == "comp" and not (m.get("comps") and len(m["comps"]) >= 2):
                continue
            if want == "form" and not m.get("meaning"):
                continue
            if want == "play" and not (m.get("play") or m.get("tier_note")):
                continue
            picked = r
            break
        if not picked:
            continue
        r = picked
        ch = r["char"]
        m = r.get("meta") or {}
        if want == "comp":
            q = "「%s」由哪两块构件组成？" % ch
            right = " + ".join(m["comps"][:2])
            others = [c for c in _uniq(comps) if c not in m["comps"]]
            rnd.shuffle(others)
            opts = [right] + [" + ".join(others[i:i + 2]) for i in range(0, min(6, len(others)), 2)][:3]
        elif want == "form":
            q = "「%s」在王邑图卷里代表什么？" % ch
            right = m["meaning"]
            others = [x for c, x in forms if c != ch and x != right]
            rnd.shuffle(others)
            opts = [right] + _uniq(others)[:3]
        else:
            q = "打「%s」这一关，正确的破法是？" % ch
            right = m.get("play") or m.get("tier_note")
            others = [x for c, x in plays if c != ch and x != right]
            rnd.shuffle(others)
            opts = [right] + _uniq(others)[:3]

        opts = _uniq(opts)[:4]
        if len(opts) < 3:
            continue
        rnd.shuffle(opts)
        used_chars.add(ch)
        ti += 1
        items.append({
            "char": ch, "type": want, "type_label": TYPE_LABEL[want],
            "question": q, "options": opts,
            "answer": right, "answer_index": opts.index(right),
        })
    return {"items": items, "count": len(items), "seed": seed}


'''
t = t[:old_start] + new_fn + t[old_end:]
io.open(p, "w", encoding="utf-8", newline="\n").write(t)
print("  出题改为题型轮转 + 错题优先")
