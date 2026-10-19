import io, json
P = r"C:\DSH\字趣\js\core\_data.js"
t = io.open(P, encoding="utf-8", errors="replace").read()
i = t.find("App.glyphs = ") + len("App.glyphs = ")
depth, j = 0, i
while j < len(t):
    ch = t[j]
    if ch == "{": depth += 1
    elif ch == "}":
        depth -= 1
        if depth == 0:
            j += 1; break
    j += 1
d = json.loads(t[i:j])
parts = d["parts"]
print("  字形数:", len(parts))
k = "日"
print("  「%s」结构:" % k, json.dumps(parts[k], ensure_ascii=False)[:700])
print()
k2 = next(iter(parts))
print("  「%s」结构:" % k2, json.dumps(parts[k2], ensure_ascii=False)[:400])
