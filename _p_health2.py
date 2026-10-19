import io
p = "src/server.py"
t = io.open(p, encoding="utf-8").read()
old = """            self._json({"ok": True, "kb_rows": len(idx.rows), "chars": len(chars),
                        "llm": st["ready"], "model": st["model"],
                        "llm_base": st["base"]})"""
new = """            try:
                import dify as dify_mod
                ds = dify_mod.status()
            except Exception:
                ds = {"ready": False, "base": ""}
            self._json({"ok": True, "kb_rows": len(idx.rows), "chars": len(chars),
                        "llm": st["ready"], "model": st["model"],
                        "llm_base": st["base"],
                        "dify": ds["ready"], "dify_base": ds["base"]})"""
assert t.count(old) == 1
io.open(p, "w", encoding="utf-8", newline="\n").write(t.replace(old, new))
print("  health 现在会报 dify 状态")

p2 = "tests/test_dify.py"
t2 = io.open(p2, encoding="utf-8").read()
if "health:" not in t2:
    t2 = t2.replace('        a = ask("家为什么是屋顶下有猪")',
                    '        h = json.loads(urllib.request.urlopen(\n'
                    '            "http://127.0.0.1:%d/api/health" % TUTOR_PORT, timeout=10).read())\n'
                    '        print("  health :", h)\n'
                    '        a = ask("家为什么是屋顶下有猪")')
    io.open(p2, "w", encoding="utf-8", newline="\n").write(t2)
    print("  测试会打印 health")
