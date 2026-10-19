# -*- coding: utf-8 -*-
"""独立的假 Dify 服务（单独进程跑，避免和测试进程的线程/代理纠缠）。"""
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Mock(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        q = body.get("query") or ""
        if "天气" in q:
            answer = "课程资料里没有这方面内容。可以问我：日为什么写成圆的、家为什么是屋顶下有猪。"
        else:
            answer = "家由「宀」和「豕」组成，屋下养猪就是「家」。"
        out = json.dumps({
            "answer": answer,
            "conversation_id": "conv-123",
            "metadata": {"retriever_resources": [
                {"document_name": "dify-kb-merged.md",
                 "content": "## 构件讨伐 · 家（一阶 · 合体字）\n\n「家」属于一阶 · 合体字，字形构成：构件 宀+豕。\n\n"
                            "出处：字趣《构件讨伐》一阶 · 合体字 · CC BY 4.0, "
                            "DOI 10.5281/zenodo.22467946",
                 "score": 0.8231},
                {"document_name": "dify-kb-merged.md",
                 "content": "## 王邑实物 · 宀（人居器物）\n\n「宀」代表屋舍的屋顶。\n\n"
                            "出处：字趣《殷商王邑》人居器物区实物点 · 教学示意图（非考古复原）",
                 "score": 0.7712},
                # 同一分段被重复召回：应被去重，不能出现两条一样的出处
                {"document_name": "dify-kb-merged.md",
                 "content": "## 构件讨伐 · 家（一阶 · 合体字）\n\n「家」属于一阶 · 合体字，字形构成：构件 宀+豕。",
                 "score": 0.7900},
            ]},
        }, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8909
    print("mock dify on %d" % port, flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Mock).serve_forever()
