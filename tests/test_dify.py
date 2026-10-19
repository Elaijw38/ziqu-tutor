# -*- coding: utf-8 -*-
"""Dify 接入链路测试：假 Dify 用**独立进程**起，避免 Windows 下线程/代理互相干扰。

验证：本地服务 → dify.ask() → 假 Dify /chat-messages → 解析 answer 与
metadata.retriever_resources → 转成前端 citations；并验证 // 清洗生效。
"""
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOCK_PORT = 8911
TUTOR_PORT = 8773


def wait(port, timeout=20):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=1).close()
            return True
        except OSError:
            time.sleep(0.3)
    return False


def main():
    env = dict(os.environ)
    env["no_proxy"] = "127.0.0.1,localhost"
    env["NO_PROXY"] = "127.0.0.1,localhost"
    env.pop("ZQ_LLM_BASE", None)
    env["ZQ_DIFY_BASE"] = "http://127.0.0.1:%d/v1" % MOCK_PORT
    env["ZQ_DIFY_KEY"] = "app-test"

    mock = subprocess.Popen(
        [sys.executable, "-X", "utf8",
         os.path.join(ROOT, "tests", "mock_dify_server.py"), str(MOCK_PORT)],
        cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    srv = subprocess.Popen(
        [sys.executable, "-X", "utf8",
         os.path.join(ROOT, "src", "server.py"), str(TUTOR_PORT)],
        cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        if not (wait(MOCK_PORT) and wait(TUTOR_PORT)):
            print("  !! 服务没起来")
            return 1
        base = "http://127.0.0.1:%d" % TUTOR_PORT
        h = json.loads(urllib.request.urlopen(base + "/api/health", timeout=10).read())
        print("  health : dify=%s base=%s" % (h.get("dify"), h.get("dify_base")))

        def ask(q):
            req = urllib.request.Request(
                base + "/api/ask",
                data=json.dumps({"question": q}).encode("utf-8"),
                headers={"Content-Type": "application/json"})
            return json.loads(urllib.request.urlopen(req, timeout=40).read())

        a = ask("家为什么是屋顶下有猪")
        print("  mode   :", a.get("mode"))
        print("  answer :", (a.get("answer") or "")[:70])
        for c in a.get("citations") or []:
            print("  出处   :", c.get("title") or "-", "|", c["source"][:70])

        b = ask("今天天气怎么样")
        print("  超纲   :", (b.get("answer") or "")[:40],
              "| refused=%s cites=%d" % (b.get("refused"), len(b.get("citations") or [])))

        h2 = json.loads(urllib.request.urlopen(base + "/api/health", timeout=10).read())
        print("  错误   :", h2.get("dify_error") or "（无）")

        cites = a.get("citations") or []
        # 出处必须是「字趣《…》…」这种真署名行，而不是上传的文件名
        real_src = all("字趣" in (c.get("source") or "") for c in cites)
        # 同一分段重复召回只保留一条
        uniq = len({c.get("title") for c in cites}) == len(cites)
        ok = (a.get("mode") == "dify"
              and len(cites) >= 2
              and real_src and uniq
              and all(c.get("snippet") for c in cites)
              and "//" not in (a.get("answer") or "")
              # 超纲问题：认成 refused，且不摆无关出处
              and b.get("refused") is True
              and not (b.get("citations") or []))
        print("\n  结论:", "✓ Dify 链路通过（回答 + 真署名出处 + 去重 + 拒答标记 + // 已清洗）"
              if ok else "✗ 未通过（署名=%s 去重=%s 条数=%d 拒答=%s）"
              % (real_src, uniq, len(cites), b.get("refused")))
        return 0 if ok else 1
    finally:
        srv.kill()
        mock.kill()


if __name__ == "__main__":
    sys.exit(main())
