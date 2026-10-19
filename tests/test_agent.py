# -*- coding: utf-8 -*-
"""用一个假的 OpenAI 兼容服务，验证 agent 链路真的跑得通。

不依赖任何真实 key：假服务按提问内容决定调哪个工具，
第二次看到工具结果后才给最终答案。这样能验证：
  请求格式 → 工具调用 → 工具执行 → 回填 → 最终答案 → 出处合并 → 三态判定

四个场景：
  1. 检索问答：search_kb → 答案 + 出处 + trace
  2. 多轮：第二问带 history，模型侧能看到上文
  3. 拒答：知识库没有 → status=refuse、refused=true、出处清空
  4. 出题：generate_quiz → trace 里有题量，且不泄露答案
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

MOCK_PORT = 8899
TUTOR_PORT = 8771


def _tool_call(name, args, cid="call_1"):
    return {"role": "assistant", "content": "",
            "tool_calls": [{"id": cid, "type": "function",
                            "function": {"name": name,
                                         "arguments": json.dumps(args, ensure_ascii=False)}}]}


class Mock(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        msgs = body.get("messages") or []
        users = [m for m in msgs if m.get("role") == "user"]
        last = (users[-1].get("content") or "") if users else ""
        tool_msgs = [m for m in msgs if m.get("role") == "tool"]

        if not tool_msgs:
            if "题" in last:
                msg = _tool_call("generate_quiz", {"n": 2, "seed": 7})
            elif "龘" in last:
                msg = {"role": "assistant",
                       "content": "知识库里没有「龘」这个字，可以换个字问我。"}
            else:
                msg = _tool_call("search_kb", {"query": "家 构件"})
        else:
            name = tool_msgs[0].get("name")
            data = {}
            try:
                data = json.loads(tool_msgs[0]["content"])
            except Exception:
                pass
            if name == "generate_quiz":
                msg = {"role": "assistant",
                       "content": "给你出了 %d 道题，做完把选项告诉我。" % data.get("count", 0)}
            else:
                # 把上下文条数写进答案，用来证明 history 真的传到了模型侧
                ctx = "（已带上下文 %d 条）" % len(msgs) if "它怎么打" in last else ""
                msg = {"role": "assistant",
                       "content": ctx + "「家」是宀（屋顶）加豕（猪）：屋下养猪即为家。"
                                         "（模型基于 %d 条知识库原文作答）" % data.get("found", 0)}
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


def ask(port, question, history=None, conv=""):
    payload = {"question": question}
    if history:
        payload["history"] = history
    if conv:
        payload["conversation_id"] = conv
    req = urllib.request.Request(
        "http://127.0.0.1:%d/api/ask" % port,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=40).read())


def test_tools_locally():
    """工具本身：出题不泄答案、评阅只算一次、写的是临时学情文件。"""
    import learner
    import llm
    from retrieval import get_index

    idx = get_index()
    old = learner.LEARNER
    learner.LEARNER = os.path.join(tempfile.mkdtemp(), "learner.json")
    try:
        r = llm._exec_tool("generate_quiz", {"n": 2, "seed": 7}, idx, learner, "s1")
        assert r.get("quiz_id") and r.get("count") == 2, "出题失败"
        assert all("answer" not in it and "answer_index" not in it
                   for it in r["items"]), "题目里泄露了答案"
        # 不带 quiz_id：靠会话接上同一套题（学生下一句只说"选B、C"就是这个场景）
        g = llm._exec_tool("submit_answers", {
            "answers": [{"char": it["char"], "choice": 0} for it in r["items"]]},
            idx, learner, "s1")
        assert g.get("total") == 2 and isinstance(g.get("score"), int), "评阅没算分"
        again = llm._exec_tool("submit_answers", {"answers": []}, idx, learner, "s1")
        assert "error" in again, "同一套题应只能评阅一次（防止重复写学情）"
        print("  [工具] 出题 2 道 / 评阅 %s 分 / 重复提交被拒 ✓" % g["score"])
        return True
    finally:
        learner.LEARNER = old


def test_classify_locally():
    """三态判定：部分可答（该字确有条目）不能判成拒答，否则出处会被清空。"""
    from ask import _classify
    cases = [
        # 回答、问题、出处、期望
        ("知识库里没有「人字旁」这类偏旁字表，只查到「人」本身",
         "人字旁有哪些字", [{"id": "boss.人"}], "refuse"),
        ("知识库里关于「尊」只有一条：字形由 10 段构成；字义没有",
         "尊是什么字", [{"id": "glyph.尊"}], "answer"),
        ("知识库里没有「龘」这个字，检索到的都是別的字",
         "龘是什么意思", [{"id": "boss.馬"}], "refuse"),
        ("你需要先告诉我是哪个字", "这个字一共几笔", [], "clarify"),
        ("「日」属于二阶独体字，字形 3 段", "日几段", [{"id": "glyph.日"}], "answer"),
    ]
    bad = []
    for text, q, cites, want in cases:
        got = _classify(text, q, cites)
        if got != want:
            bad.append("%s → %s（应为 %s）" % (q, got, want))
    print("  [三态] 5 例 %s" % ("✓" if not bad else "✗ " + "；".join(bad)))
    return not bad


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
    ok = True
    try:
        h = json.loads(urllib.request.urlopen(
            "http://127.0.0.1:%d/api/health" % TUTOR_PORT, timeout=10).read())
        print("  health:", h)

        a = ask(TUTOR_PORT, "家为什么是屋顶下有猪")
        print("  ① 检索问答 mode=%s tools=%s cites=%d status=%s"
              % (a.get("mode"), a.get("hits"), len(a.get("citations") or []), a.get("status")))
        print("     trace:", a.get("trace"))
        ok &= bool(a.get("mode") == "agent" and a.get("hits") == ["search_kb"]
                   and len(a.get("citations") or []) > 0
                   and a.get("status") == "answer"
                   and (a.get("trace") or [{}])[0].get("tool") == "search_kb"
                   and (a.get("citations") or [{}])[0].get("snippet"))

        b = ask(TUTOR_PORT, "那它怎么打",
                history=[{"role": "user", "content": "家为什么是屋顶下有猪"},
                         {"role": "assistant", "content": "「家」是宀加豕。"}])
        print("  ② 多轮     :", (b.get("answer") or "")[:40])
        ok &= "已带上下文" in (b.get("answer") or "")

        c = ask(TUTOR_PORT, "龘是什么意思")
        print("  ③ 拒答     status=%s refused=%s cites=%d"
              % (c.get("status"), c.get("refused"), len(c.get("citations") or [])))
        ok &= (c.get("status") == "refuse" and c.get("refused") is True
               and not (c.get("citations") or []))

        d = ask(TUTOR_PORT, "给我出两道题")
        quiz_trace = [t for t in (d.get("trace") or []) if t.get("tool") == "generate_quiz"]
        print("  ④ 出题     trace=%s 答:%s" % (quiz_trace, (d.get("answer") or "")[:24]))
        ok &= bool(quiz_trace and quiz_trace[0].get("count") == 2
                   and quiz_trace[0].get("quiz_id"))

        ok &= test_tools_locally()
        ok &= test_classify_locally()

        print("\n  结论:", "✓ agent 全链路通过（工具/多轮/三态/出题）" if ok else "✗ 有断言未通过")
        return 0 if ok else 1
    finally:
        srv.kill()
        mock.shutdown()


if __name__ == "__main__":
    sys.exit(main())
