# -*- coding: utf-8 -*-
"""存储层：并发写不丢更新、原子写、损坏可追溯、增长有上限。

这些用例跑在临时目录里，不碰 data/learner.json（演示数据）。
"""
import io
import json
import os
import shutil
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

import learner  # noqa: E402
import quiz     # noqa: E402
from retrieval import get_index  # noqa: E402


def main():
    tmp = tempfile.mkdtemp(prefix="zq_store_")
    real = learner.LEARNER
    learner.LEARNER = os.path.join(tmp, "learner.json")
    ok = True
    try:
        # ① 并发写：8 个线程各学一个字，一个都不能丢
        def w(ch):
            for _ in range(10):
                with learner.transaction() as d:
                    d.setdefault("done", {}).setdefault("sky", [])
                    if ch not in d["done"]["sky"]:
                        d["done"]["sky"].append(ch)

        th = [threading.Thread(target=w, args=(chr(0x4e00 + i),)) for i in range(8)]
        [t.start() for t in th]
        [t.join() for t in th]
        d = learner.load()
        got = d["done"].get("sky", [])
        pass1 = len(got) == 8
        ok &= pass1
        print("① 并发写 8 个字 → 实际 %d 个 %s" % (len(got), "✓" if pass1 else "✗ 丢更新"))

        # ② 原子写：save 后不存在残留临时文件，且文件始终是合法 JSON
        for i in range(5):
            with learner.transaction() as x:
                x.setdefault("bossCleared", []).append(i)
        leftovers = [f for f in os.listdir(tmp) if f.endswith(".tmp")]
        try:
            json.loads(io.open(learner.LEARNER, encoding="utf-8").read())
            pass2 = not leftovers
        except Exception:
            pass2 = False
        ok &= pass2
        print("② 原子写 → 残留临时文件 %d 个，JSON 可解析 %s"
              % (len(leftovers), "✓" if pass2 else "✗"))

        # ③ 文件损坏：留 .corrupt 证据并记错误，而不是静默清空
        with io.open(learner.LEARNER, "w", encoding="utf-8") as f:
            f.write('{"done": {"sky": ["日"')          # 半截 JSON
        d = learner.load()
        pass3 = (os.path.exists(learner.LEARNER + ".corrupt")
                 and bool(learner.LAST_LOAD_ERROR)
                 and d["done"] == {})
        ok &= pass3
        print("③ 半截文件 → 备份 .corrupt=%s 错误已记录=%s %s"
              % (os.path.exists(learner.LEARNER + ".corrupt"),
                 bool(learner.LAST_LOAD_ERROR), "✓" if pass3 else "✗"))

        # ④ attempts 有上限，不会随学期无限膨胀
        big = {"done": {}, "bossCleared": [],
               "attempts": [{"char": "日", "ok": True, "kind": "form"}] * 2000}
        learner.save(big)
        n = len(learner.load()["attempts"])
        pass4 = n == learner.MAX_ATTEMPTS
        ok &= pass4
        print("④ 2000 条作答记录 → 保留 %d 条（上限 %d）%s"
              % (n, learner.MAX_ATTEMPTS, "✓" if pass4 else "✗"))

        # ⑤ 两人同时交卷：两条记录都要在
        learner.save({"done": {}, "bossCleared": [], "attempts": []})
        idx = get_index()
        q1 = quiz.make_quiz(2, 101)
        q2 = quiz.make_quiz(2, 202)
        a1 = [{"char": it["char"], "choice": 0} for it in q1["items"]]
        a2 = [{"char": it["char"], "choice": 1} for it in q2["items"]]
        t1 = threading.Thread(target=quiz.grade, args=(q1, a1))
        t2 = threading.Thread(target=quiz.grade, args=(q2, a2))
        t1.start(); t2.start(); t1.join(); t2.join()
        n = len(learner.load()["attempts"])
        pass5 = n == 4
        ok &= pass5
        print("⑤ 两人同时交卷（各 2 题）→ 记录 %d 条 %s"
              % (n, "✓" if pass5 else "✗ 有覆盖"))

        print("\n  结论:", "✓ 存储层通过" if ok else "✗ 未通过")
        return 0 if ok else 1
    finally:
        learner.LEARNER = real
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
