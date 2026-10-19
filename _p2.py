import io
p = "src/build_kb.py"
t = io.open(p, encoding="utf-8").read()
old = """            if play:
                text += "打法：%s" % play"""
new = """            if play:
                text += "打法：%s" % play
            elif tier.get("note"):
                # 名录里没有这一尊时，用本阶的通则打法补上，
                # 否则"虎怎么打"这类问题会答不出东西。
                text += "本阶打法：%s" % tier["note"]"""
assert t.count(old) == 1
io.open(p, "w", encoding="utf-8", newline="\n").write(t.replace(old, new))
print("  boss 条目并入本阶通则打法")
