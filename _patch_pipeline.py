# -*- coding: utf-8 -*-
"""给 build_kb.py 与 retrieval.py 打补丁：
  1) kb 条目里补 meta.comps / meta.tier_note / meta.zone_id，供出题与诊断用；
  2) retrieval 里加 get_kb_meta()，供 learner 诊断时取分区与构件统计。
"""
import io
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)


def patch_build_kb():
    p = "src/build_kb.py"
    t = io.open(p, encoding="utf-8").read()

    t = t.replace(
        '"meta": {"zone": zname, "meaning": o.get("meaning"), "form": o.get("form")},',
        '"meta": {"zone": zname, "zone_id": zone.get("id"),\n'
        '                          "meaning": o.get("meaning"), "form": o.get("form")},')

    t = t.replace(
        '"meta": {"tier": tier.get("name"), "play": play, "form": form},',
        '"meta": {"tier": tier.get("name"), "play": play, "form": form,\n'
        '                          "comps": comps, "tier_note": tier.get("note") or ""},')
    io.open(p, "w", encoding="utf-8", newline="\n").write(t)
    print("  build_kb.py 已补 meta")


def patch_retrieval():
    p = "src/retrieval.py"
    t = io.open(p, encoding="utf-8").read()
    if "def get_kb_meta" in t:
        print("  retrieval.py 已有 get_kb_meta")
        return
    add = '''

_META_CACHE = {}


def get_kb_meta(path=KB_PATH):
    """分区与构件统计，给学情诊断用（懒构建，只算一次）。"""
    if path in _META_CACHE:
        return _META_CACHE[path]
    rows = load_kb(path)
    zones, zone_chars, comp_chars = [], {}, {}
    seen_zone = set()
    for r in rows:
        m = r.get("meta") or {}
        zid, zname = m.get("zone_id"), m.get("zone")
        if zid and zid not in seen_zone:
            seen_zone.add(zid)
            zones.append((zid, zname or zid))
        if zid and r.get("char"):
            zone_chars.setdefault(zid, []).append(r["char"])
        for c in (m.get("comps") or []):
            if r.get("char"):
                comp_chars.setdefault(c, [])
                if r["char"] not in comp_chars[c]:
                    comp_chars[c].append(r["char"])
    out = {"zones": zones, "zone_chars": zone_chars, "comp_chars": comp_chars}
    _META_CACHE[path] = out
    return out
'''
    io.open(p, "w", encoding="utf-8", newline="\n").write(t.rstrip() + add)
    print("  retrieval.py 已加 get_kb_meta")


def patch_server():
    p = "src/server.py"
    t = io.open(p, encoding="utf-8").read()
    if "/api/diagnose" in t:
        print("  server.py 已有新接口")
        return

    t = t.replace("import ask as ask_mod          # noqa: E402",
                  "import ask as ask_mod          # noqa: E402\n"
                  "import learner                # noqa: E402\n"
                  "import quiz as quiz_mod       # noqa: E402")

    t = t.replace('''    def do_GET(self):
        p = urllib.parse.urlparse(self.path)
        if p.path == "/api/health":''',
'''    def do_GET(self):
        p = urllib.parse.urlparse(self.path)
        if p.path == "/api/diagnose":
            try:
                self._json(learner.diagnose(get_index()))
            except Exception as e:
                self._json({"error": "internal: %s" % e}, 500)
            return
        if p.path == "/api/health":''')

    t = t.replace('''        q = (payload.get("question") or "").strip()''',
'''        if p.path == "/api/quiz":
            try:
                self._json(quiz_mod.make_quiz(int(payload.get("n") or 3),
                                              int(payload.get("seed") or 20261104)))
            except Exception as e:
                self._json({"error": "internal: %s" % e}, 500)
            return
        if p.path == "/api/grade":
            try:
                self._json(quiz_mod.grade(payload.get("quiz") or {},
                                          payload.get("answers") or []))
            except Exception as e:
                self._json({"error": "internal: %s" % e}, 500)
            return

        q = (payload.get("question") or "").strip()''')

    t = t.replace('        if p.path != "/api/ask":',
                  '        if p.path not in ("/api/ask", "/api/quiz", "/api/grade"):')
    io.open(p, "w", encoding="utf-8", newline="\n").write(t)
    print("  server.py 已加 /api/diagnose /api/quiz /api/grade")


if __name__ == "__main__":
    patch_build_kb()
    patch_retrieval()
    patch_server()
    print("  补丁完成；接着要重新 build_kb 并重启服务")
