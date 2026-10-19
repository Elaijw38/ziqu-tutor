# -*- coding: utf-8 -*-
"""本地/公网服务：零框架（标准库 http.server），只做三件事：

  GET  /                → web/ 静态页（助教聊天界面）
  POST /api/ask         → {"question": "..."} → 答案 + 出处
  GET  /api/health      → 自检：知识库条数、覆盖字数、LLM 是否启用

为什么不用 FastAPI：演示要在任何机器上一条命令起来，不能要求装依赖。
真正的产物是检索与问答逻辑，换框架只是换一层壳。

部署相关（都是环境变量，不配则保持本机行为）：
  PORT=8770            平台（Render/Fly/容器）通常注入 PORT
  ZQ_HOST=0.0.0.0      对外开放；默认只绑 127.0.0.1
  ZQ_ACCESS_CODE=xxx   邀请码门禁；设了之后访问页与接口都要凭码
  ZQ_RATE_PER_HOUR=60  单 IP 每小时提问上限；0 或不设表示不限
"""
import json
import os
import sys
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import ask as ask_mod          # noqa: E402
import curriculum              # noqa: E402
import learner                # noqa: E402
import learning               # noqa: E402
import quiz as quiz_mod
import glyphs as glyph_mod  # 甲骨字形渲染（上游 1203 字形）       # noqa: E402
from retrieval import get_index  # noqa: E402

WEB = os.path.join(ROOT, "web")
MIME = {".html": "text/html; charset=utf-8", ".js": "application/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8",
        ".png": "image/png", ".svg": "image/svg+xml", ".ico": "image/x-icon"}

ACCESS_CODE = (os.environ.get("ZQ_ACCESS_CODE") or "").strip()
RATE_LIMIT = int(os.environ.get("ZQ_RATE_PER_HOUR") or 0)
_HITS = {}     # ip -> [时间戳]：内存计数，单进程够用，重启即清零

LOGIN_HTML = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>甲骨文 AI 助教 · 请输入邀请码</title>
<style>
 body{margin:0;min-height:100vh;display:grid;place-items:center;
   background:linear-gradient(180deg,#fff 0%,#eef4fc 60%,#e8f0fa 100%);
   font:15px/1.75 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif;color:#1b2432}
 .box{background:#fff;border:1px solid #e2e9f3;border-radius:16px;padding:28px 30px;
   box-shadow:0 10px 30px rgba(22,51,107,.08);width:min(92vw,380px)}
 h1{font-size:17px;margin:0 0 6px;color:#16336b;letter-spacing:.5px}
 p{font-size:13px;color:#5c6b80;margin:0 0 16px}
 input{width:100%;padding:11px 13px;border:1px solid #e2e9f3;border-radius:10px;
   font-size:14.5px;outline:none;box-sizing:border-box}
 input:focus{border-color:#16336b;box-shadow:0 0 0 3px rgba(22,51,107,.12)}
 button{width:100%;margin-top:10px;padding:11px;border:0;border-radius:10px;
   background:#16336b;color:#fff;font-size:14.5px;cursor:pointer}
 button:disabled{opacity:.6;cursor:default}
 .err{color:#a4231f;font-size:12.5px;margin-top:9px;min-height:18px}
</style></head><body>
<form class="box" method="post" action="/api/login">
  <h1>甲骨文 AI 助教</h1>
  <p>郑州大学汉字通识课 · 请输入课程邀请码</p>
  <input name="code" type="password" placeholder="邀请码" autofocus required>
  <button type="submit">进入</button>
  <div class="err">__ERR__</div>
  <p style="margin:14px 0 0;font-size:12px;color:#8a97a8">
    没有邀请码？向任课教师索取，或直接打开老师发的带码链接。</p>
</form></body></html>"""


class Handler(BaseHTTPRequestHandler):
    server_version = "ziqu-tutor/0.1"

    # ---------------- 访客身份（学情按人分开的前提） ----------------

    def _visitor(self):
        """每个浏览器一个随机 vid；只当钥匙用，不含任何个人信息。

        没有 cookie（curl、脚本、禁用 cookie 的浏览器）时落到共享的本机桶，
        学情不再能当个人证据用——这种情况在接口返回里会说清楚。
        """
        if getattr(self, "_vid", None):
            return self._vid
        raw = ""
        for part in (self.headers.get("Cookie") or "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == "zq_vid":
                raw = v.strip()
                break
        if learner.is_valid_vid(raw):
            self._vid = raw
            self._new_vid = False
        else:
            self._vid = learner.new_vid()
            self._new_vid = True
        return self._vid

    def end_headers(self):
        # 首次访问即签发，避免"第一次交卷记到公共桶、第二次才有自己的记录"
        if getattr(self, "_new_vid", False):
            self._new_vid = False
            self.send_header("Set-Cookie",
                             "zq_vid=%s; Path=/; HttpOnly; SameSite=Lax; Max-Age=31536000"
                             % self._vid)
        BaseHTTPRequestHandler.end_headers(self)

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _code_ok(self):
        """邀请码校验：未设码则全放行；设了码就认 cookie。"""
        if not ACCESS_CODE:
            return True
        for part in (self.headers.get("Cookie") or "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == "zq_code" and v == ACCESS_CODE:
                return True
        return False

    def _client_ip(self):
        """限流要按真实访客分桶。

        走 cloudflared/反代时 client_address 恒为 127.0.0.1，全班会共用一个桶，
        60 次/小时几秒钟就打满；真实来源在 CF-Connecting-IP / X-Forwarded-For。
        只在本机转发进来时才采信这些头，否则外部随手伪造一个 IP 就绕过限流了。
        """
        peer = self.client_address[0]
        if peer in ("127.0.0.1", "::1", "::ffff:127.0.0.1"):
            for h in ("CF-Connecting-IP", "X-Forwarded-For"):
                v = (self.headers.get(h) or "").strip()
                if v:
                    return v.split(",")[0].strip()
        return peer

    def _rate_ok(self):
        """单 IP 每小时提问上限，防止公开链接被刷模型额度。"""
        if not RATE_LIMIT:
            return True
        ip = self._client_ip()
        now = time.time()
        q = [t for t in _HITS.get(ip, []) if now - t < 3600]
        if len(q) >= RATE_LIMIT:
            _HITS[ip] = q
            return False
        q.append(now)
        _HITS[ip] = q
        return True

    def _login_page(self, err=""):
        body = LOGIN_HTML.replace("__ERR__", err).encode("utf-8")
        self.send_response(401 if err else 200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
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
        vid = self._visitor()
        if p.path == "/api/diagnose":
            if not self._code_ok():
                self._json({"error": "需要邀请码：请从带邀请码的链接进入"}, 401)
                return
            # quiz_id 可选：带上就是「本次练习」口径，不带则取最近一次/最近 N 次
            qid = (urllib.parse.parse_qs(p.query).get("quiz_id") or [""])[0]
            qid = "".join(ch for ch in qid[:40] if ch.isalnum() or ch in "-_.") 
            try:
                self._json(learning.diagnose(get_index(), vid, quiz_id=qid))
            except Exception as e:
                self._json({"error": "internal: %s" % e}, 500)
            return
        if p.path.startswith("/api/glyph/"):
            qs = urllib.parse.parse_qs(p.query)
            ch = urllib.parse.unquote(p.path.split("/api/glyph/", 1)[1] or "")[:1]
            try:
                size = int((qs.get("size") or ["120"])[0])
            except ValueError:
                size = 120
            size = max(40, min(size, 1024))
            svg = glyph_mod.book.svg(ch, width=size) if glyph_mod.book.has(ch) else None
            if not svg:
                self._json({"error": "该字暂无甲骨字形", "char": ch,
                            "glyphs": len(glyph_mod.book.by_char)}, 404)
                return
            body = svg.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "image/svg+xml; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "public, max-age=86400")
            if qs.get("download"):
                fn = urllib.parse.quote("甲骨文字形-%s.svg" % ch)
                self.send_header("Content-Disposition",
                                 "attachment; filename*=UTF-8''%s" % fn)
            self.end_headers()
            self.wfile.write(body)
            return
        if p.path == "/api/health":
            idx = get_index()
            chars = {r.get("char") for r in idx.rows if r.get("char")}
            # 「字形库」只算真有甲骨字形数据的字，不能拿知识库去重字数顶替
            glyph_chars = {r.get("char") for r in idx.rows
                           if r.get("char") and r.get("kind") == "glyph"}
            try:
                course_n = len(learner.course_chars(idx.rows))
            except Exception:
                course_n = 0
            try:
                import llm as llm_mod
                st = llm_mod.status()
            except Exception:
                st = {"ready": False, "model": "", "base": ""}
            try:
                import dify as dify_mod
                ds = dify_mod.status()
            except Exception:
                ds = {"ready": False, "base": ""}
            # 学情坏行会静默清零，必须在自检里看得见；分人之后再看访客数
            try:
                store = learner.stats(vid)
            except Exception as e:
                store = {"error": str(e)[:120]}
            # 公开自检只回答「能不能用」，不暴露模型地址、密钥或学生作答明细
            self._json({"ok": True, "kb_rows": len(idx.rows), "chars": len(chars),
                        "glyph_chars": len(glyph_chars),
                        "course_chars": course_n,
                        "llm": st["ready"], "model": st["model"],
                        "dify": ds["ready"],
                        "dify_error": getattr(dify_mod, "LAST_ERROR", ""),
                        "store": store})
            return
        # 分享用的直达链接：/?code=xxx 校验通过就种 cookie 再跳到干净地址。
        # 否则每发一条链接，对方都要先手输一次邀请码。
        if p.path in ("/", "/index.html") and ACCESS_CODE:
            code = (urllib.parse.parse_qs(p.query).get("code") or [""])[0].strip()
            if code:
                if code != ACCESS_CODE:
                    self._login_page("链接里的邀请码不对，请向任课教师重新索取。")
                    return
                self.send_response(303)
                # 与表单登录一致：口令只放 HttpOnly cookie，前端脚本读不到
                self.send_header("Set-Cookie",
                                 "zq_code=%s; Path=/; HttpOnly; SameSite=Lax; Max-Age=604800"
                                 % urllib.parse.quote(code))
                self.send_header("Location", "/")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
        # 首页要过邀请码；校徽/龟宝等静态图放行（页面本身拿不到就没意义）
        if p.path in ("/", "/index.html") and not self._code_ok():
            self._login_page()
            return
        self._static(p.path)

    def do_POST(self):
        p = urllib.parse.urlparse(self.path)
        vid = self._visitor()
        if p.path == "/api/login":
            n = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(n).decode("utf-8", "replace") if n else ""
            code = urllib.parse.parse_qs(raw).get("code", [""])[0].strip()
            if ACCESS_CODE and code != ACCESS_CODE:
                self._login_page("邀请码不对，请向任课教师索取。")
                return
            self.send_response(303)
            # 邀请码等价于口令，只放 HttpOnly cookie，不让前端脚本读到
            self.send_header("Set-Cookie", "zq_code=%s; Path=/; HttpOnly; SameSite=Lax; Max-Age=604800"
                             % urllib.parse.quote(code))
            self.send_header("Location", "/")
            self.end_headers()
            return
        if p.path not in ("/api/ask", "/api/quiz", "/api/grade",
                          "/api/reset", "/api/seed-demo"):
            self._json({"error": "not found"}, 404)
            return
        if not self._code_ok():
            self._json({"error": "需要邀请码：请从带邀请码的链接进入"}, 401)
            return
        try:
            n = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(n).decode("utf-8") if n else "{}"
            payload = json.loads(raw or "{}")
        except Exception as e:
            self._json({"error": "bad json: %s" % e}, 400)
            return
        if p.path == "/api/reset":
            # 只清当前这一个访客的记录，不动别人的
            try:
                learner.reset(vid)
                self._json({"ok": True})
            except Exception as e:
                self._json({"error": "internal: %s" % e}, 500)
            return
        if p.path == "/api/seed-demo":
            # 课堂演示用：把示例学情复制给当前访客，页面会标明「含示例数据」
            try:
                n = learner.seed_demo(vid)
                self._json({"ok": True, "attempts": n} if n else
                           {"error": "示例数据不存在（data/learner.json 已移除？）"}, 200 if n else 404)
            except Exception as e:
                self._json({"error": "internal: %s" % e}, 500)
            return
        if p.path == "/api/quiz":
            try:
                kp = (payload.get("kp_id") or "").strip()
                if kp and kp not in curriculum.kp_index():
                    self._json({"error": "未知知识点：%s" % kp[:40]}, 400)
                    return
                r = quiz_mod.make_quiz(int(payload.get("n") or 3),
                                       int(payload.get("seed") or 20261104), vid, kp)
                if r.get("error"):
                    self._json(r, 400)
                else:
                    self._json(r)
            except Exception as e:
                self._json({"error": "internal: %s" % e}, 500)
            return
        if p.path == "/api/grade":
            try:
                qid = "".join(ch for ch in str(payload.get("quiz_id") or "")[:40]
                              if ch.isalnum() or ch in "-_.")
                if qid and not learner.get_quiz(qid):
                    # 服务端不认这套题（过期/伪造）：不让客户端回传的题目参与判分
                    self._json({"error": "这套题已过期，请重新出题后再交。"}, 410)
                    return
                self._json(quiz_mod.grade(payload.get("quiz") or {},
                                          payload.get("answers") or [], vid, qid))
            except Exception as e:
                self._json({"error": "internal: %s" % e}, 500)
            return

        q = (payload.get("question") or "").strip()
        if not q:
            self._json({"error": "question 不能为空"}, 400)
            return
        if not self._rate_ok():
            self._json({"error": "提问太快了：每个 IP 每小时 %d 次，请稍后再问。" % RATE_LIMIT}, 429)
            return
        # 多轮上下文：只认 user/assistant，最多 6 条、每条 600 字（防止前端塞超长内容）
        hist = []
        raw_hist = payload.get("history")
        if isinstance(raw_hist, list):
            for m in raw_hist[-6:]:
                if not isinstance(m, dict):
                    continue
                role = m.get("role")
                content = m.get("content")
                if role in ("user", "assistant") and isinstance(content, str) and content.strip():
                    hist.append({"role": role, "content": content.strip()[:600]})
        conv = payload.get("conversation_id")
        conv = conv.strip()[:200] if isinstance(conv, str) else ""
        # 会话标识：让"出题 → 下一句作答 → 评阅"能跨请求接上；只允许安全字符
        sid = payload.get("session_id")
        sid = "".join(ch for ch in (sid if isinstance(sid, str) else "")[:64]
                      if ch.isalnum() or ch in "-_")
        try:
            mode = payload.get("mode")
            mode = mode.strip().lower()[:10] if isinstance(mode, str) else ""
            res = ask_mod.answer(q, history=hist, conversation_id=conv,
                                 session_id=sid, vid=vid, mode=mode)
            # 选字：先取出处对应的字（这才是"回答用到的"），没有出处才退回问句里的课程字
            course_chars = {r.get("char") for r in get_index().rows
                            if r.get("char") and r.get("kind") in ("wangyi", "boss", "codex")}
            picked, seen = [], set()

            def _push(ch):
                if len(picked) < 4 and ch and ch not in seen and glyph_mod.book.has(ch):
                    seen.add(ch)
                    picked.append(ch)

            # 辨形题：只出目标字这一个字形（出处已被隐藏，不能靠出处挑字）
            _quiz = res.get("quiz") or {}
            if _quiz.get("answer") and glyph_mod.book.has(_quiz["answer"]):
                _push(_quiz["answer"])
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
            self._json(res)
        except Exception as e:
            self._json({"error": "internal: %s" % e}, 500)

    def log_message(self, fmt, *args):
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))


def main():
    port = (int(sys.argv[1]) if len(sys.argv) > 1
            else int(os.environ.get("PORT") or 8770))
    host = os.environ.get("ZQ_HOST") or "127.0.0.1"
    srv = ThreadingHTTPServer((host, port), Handler)
    print("助教服务已启动： http://%s:%d" % (host, port))
    if host not in ("127.0.0.1", "localhost"):
        print("对外开放：邀请码 %s / 单 IP 每小时 %s 次"
              % ("已启用" if ACCESS_CODE else "未设置（任何人可调用，会消耗模型额度）",
                 RATE_LIMIT or "不限"))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")


if __name__ == "__main__":
    main()
