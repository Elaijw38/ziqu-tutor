# -*- coding: utf-8 -*-
"""用一个假的 OpenAI 兼容服务，验证 agent 链路真的跑得通。

不依赖任何真实 key：假服务第一次返回 tool_call（要求检索），
第二次看到工具结果后返回最终答案。这样能验证：
  请求格式 → 工具调用 → 工具执行 → 回填 → 最终答案 → 出处合并
全链路，而不是"代码写了就算"。
"""
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

MOCK_PORT = 8899
TUTOR_PORT = 8771


class Mock(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        msgs = body.get("messages") or []
        has_tool_result = any(m.get("role") == "tool" for m in msgs)
        if not has_tool_result:
            msg = {"role": "assistant", "content": "",
                   "tool_calls": [{
                       "id": "call_1", "type": "function",
                       "function": {"name": "search_kb",
                                    "arguments": json.dumps({"query": "家 构件"},
                                                            ensure_ascii=False)}}]}
        else:
            tool_msgs = [m for m in msgs if m.get("role") == "tool"]
            found = 0
            try:
                found = json.loads(tool_msgs[0]["content"]).get("found", 0)
            except Exception:
                pass
            msg = {"role": "assistant",
                   "content": "「家」是宀（屋顶）加豕（猪）：屋下养猪即为家。"
                              "（模型基于 %d 条知识库原文作答）" % found}
        out = json.dumps({"choices": [{"message": msg}]}, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)


def wait(port, timeout=15):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=1).close()
            return True
        except OSError:
            time.sleep(0.3)
    return False


def main():
    mock = ThreadingHTTPServer(("127.0.0.1", MOCK_PORT), Mock)
    import threading
    threading.Thread(target=mock.serve_forever, daemon=True).start()
    print("  假模型服务: http://127.0.0.1:%d/v1" % MOCK_PORT)

    env = dict(os.environ)
    env.update({"ZQ_LLM_BASE": "http://127.0.0.1:%d/v1" % MOCK_PORT,
                "ZQ_LLM_KEY": "test-key",
                "ZQ_LLM_MODEL": "mock-model"})
    srv = subprocess.Popen([sys.executable, "-X", "utf8",
                            os.path.join(ROOT, "src", "server.py"), str(TUTOR_PORT)],
                           cwd=ROOT, env=env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not wait(TUTOR_PORT):
        print("  !! 助教服务没起来")
        srv.kill()
        return 1
    try:
        h = json.loads(urllib.request.urlopen(
            "http://127.0.0.1:%d/api/health" % TUTOR_PORT, timeout=10).read())
        print("  health:", h)

        req = urllib.request.Request(
            "http://127.0.0.1:%d/api/ask" % TUTOR_PORT,
            data=json.dumps({"question": "家为什么是屋顶下有猪"}).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        a = json.loads(urllib.request.urlopen(req, timeout=40).read())
        print("  mode    :", a.get("mode"))
        print("  tools   :", a.get("hits"))
        print("  answer  :", (a.get("answer") or "")[:80])
        print("  citations:", len(a.get("citations") or []),
              (a.get("citations") or [{}])[0].get("id", ""))

        ok = (a.get("mode") == "agent" and a.get("hits") == ["search_kb"]
              and len(a.get("citations") or []) > 0)
        print("\n  结论:", "✓ agent 链路通过（工具调用→检索→出处合并）" if ok else "✗ 未通过")
        return 0 if ok else 1
    finally:
        srv.kill()
        mock.shutdown()


if __name__ == "__main__":
    sys.exit(main())
