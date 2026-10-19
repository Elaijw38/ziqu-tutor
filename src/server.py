# -*- coding: utf-8 -*-
"""本地服务：零框架（标准库 http.server），只做三件事：

  GET  /                → web/ 静态页（助教聊天界面）
  POST /api/ask         → {"question": "..."} → 答案 + 出处
  GET  /api/health      → 自检：知识库条数、覆盖字数、LLM 是否启用

为什么不用 FastAPI：初赛演示要在任何机器上一条命令起来，不能要求装依赖。
真正的产物是检索与问答逻辑，换框架只是换一层壳。
"""
import json
import os
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import ask as ask_mod          # noqa: E402
import learner                # noqa: E402
import quiz as quiz_mod       # noqa: E402
from retrieval import get_index  # noqa: E402

WEB = os.path.join(ROOT, "web")
MIME = {".html": "text/html; charset=utf-8", ".js": "application/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8",
        ".png": "image/png", ".svg": "image/svg+xml", ".ico": "image/x-icon"}


class Handler(BaseHTTPRequestHandler):
    server_version = "ziqu-tutor/0.1"

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _static(self, path):
        rel = path.lstrip("/") or "index.html"
        full = os.path.normpath(os.path.join(WEB, rel))
        if not full.startswith(WEB):
            self._json({"error": "forbidden"}, 403)
            return
        if not os.path.isfile(full):
            self._json({"error": "not found", "path": rel}, 404)
            return
        data = open(full, "rb").read()
        self.send_response(200)
        self.send_header("Content-Type", MIME.get(os.path.splitext(full)[1], "application/octet-stream"))
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        p = urllib.parse.urlparse(self.path)
        if p.path == "/api/diagnose":
            try:
                self._json(learner.diagnose(get_index()))
            except Exception as e:
                self._json({"error": "internal: %s" % e}, 500)
            return
        if p.path == "/api/health":
            idx = get_index()
            chars = {r.get("char") for r in idx.rows if r.get("char")}
            try:
                import llm as llm_mod
                st = llm_mod.status()
            except Exception:
                st = {"ready": False, "model": "", "base": ""}
            self._json({"ok": True, "kb_rows": len(idx.rows), "chars": len(chars),
                        "llm": st["ready"], "model": st["model"],
                        "llm_base": st["base"]})
            return
        self._static(p.path)

    def do_POST(self):
        p = urllib.parse.urlparse(self.path)
        if p.path not in ("/api/ask", "/api/quiz", "/api/grade"):
            self._json({"error": "not found"}, 404)
            return
        try:
            n = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(n).decode("utf-8") if n else "{}"
            payload = json.loads(raw or "{}")
        except Exception as e:
            self._json({"error": "bad json: %s" % e}, 400)
            return
        if p.path == "/api/quiz":
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

        q = (payload.get("question") or "").strip()
        if not q:
            self._json({"error": "question 不能为空"}, 400)
            return
        try:
            self._json(ask_mod.answer(q))
        except Exception as e:
            self._json({"error": "internal: %s" % e}, 500)

    def log_message(self, fmt, *args):
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8770
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print("助教服务已启动： http://127.0.0.1:%d" % port)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")


if __name__ == "__main__":
    main()
