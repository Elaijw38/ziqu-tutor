import io
p = "src/server.py"
t = io.open(p, encoding="utf-8").read()
old = """            llm = all(os.environ.get(k) for k in ("ZQ_LLM_KEY", "ZQ_LLM_BASE", "ZQ_LLM_MODEL"))
            self._json({"ok": True, "kb_rows": len(idx.rows), "chars": len(chars),
                        "llm": llm})"""
new = """            try:
                import llm as llm_mod
                st = llm_mod.status()
            except Exception:
                st = {"ready": False, "model": "", "base": ""}
            self._json({"ok": True, "kb_rows": len(idx.rows), "chars": len(chars),
                        "llm": st["ready"], "model": st["model"],
                        "llm_base": st["base"]})"""
assert t.count(old) == 1, t.count(old)
io.open(p, "w", encoding="utf-8", newline="\n").write(t.replace(old, new))
print("  /api/health 现在会报模型名")
