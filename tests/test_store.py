# -*- coding: utf-8 -*-
"""存储层：分人隔离、并发写不丢更新、事务原子、坏行可追溯、增长有上限。

分人之后要守住两条底线：
  1. A 交的卷不能记到 B 头上（以前所有访客共用一份 learner.json）；
  2. 并发交卷仍然一条都不能丢（SQLite BEGIN IMMEDIATE 保证）。
这些用例跑在临时库里，不碰 data/learners.db（演示数据）。
"""
import io
import json
import os
import shutil
import sqlite3
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
    real_db, real_legacy, real_corrupt = learner.DB, learner.LEGACY, learner.CORRUPT_DIR
    learner.DB = os.path.join(tmp, "learners.db")
    learner.LEGACY = os.path.join(tmp, "no-such-legacy.json")
    learner.CORRUPT_DIR = os.path.join(tmp, "corrupt")
    ok = True
    try:
        # ① 并发写：8 个线程各学一个字（同一访客），一个都不能丢
        vid = learner.new_vid()

        def w(ch):
            for _ in range(10):
                with learner.transaction(vid) as d:
                    d.setdefault("done", {}).setdefault("sky", [])
                    if ch not in d["done"]["sky"]:
                        d["done"]["sky"].append(ch)

        th = [threading.Thread(target=w, args=(chr(0x4e00 + i),)) for i in range(8)]
        [t.start() for t in th]
        [t.join() for t in th]
        got = learner.load(vid)["done"].get("sky", [])
        pass1 = len(got) == 8
        ok &= pass1
        print("① 并发写 8 个字 → 实际 %d 个 %s" % (len(got), "✓" if pass1 else "✗ 丢更新"))

        # ② 分人隔离：B 的记录不能出现在 A 上，反之亦然
        vid_b = learner.new_vid()
        with learner.transaction(vid_b) as db:
            db["attempts"].append({"char": "鼎", "ok": False, "kind": "comp"})
        a = learner.load(vid)
        b = learner.load(vid_b)
        pass2 = (not a["attempts"]) and len(b["attempts"]) == 1
        ok &= pass2
        print("② 两个访客各存各的 → A %d 条 / B %d 条 %s"
              % (len(a["attempts"]), len(b["attempts"]), "✓" if pass2 else "✗ 串了"))

        # ③ 事务原子：中途抛错必须整体回滚，不能留下半份数据
        vid_c = learner.new_vid()
        learner.save({"done": {}, "bossCleared": [], "attempts": []}, vid_c)
        try:
            with learner.transaction(vid_c) as dc:
                dc["attempts"].append({"char": "日", "ok": True, "kind": "form"})
                raise RuntimeError("模拟交卷中途失败")
        except RuntimeError:
            pass
        pass3 = learner.load(vid_c)["attempts"] == []
        ok &= pass3
        print("③ 事务中途报错 → 记录回滚 %s" % ("✓" if pass3 else "✗ 写进去了一半"))

        # ④ attempts 有上限，不会随学期无限膨胀
        big = {"done": {}, "bossCleared": [],
               "attempts": [{"char": "日", "ok": True, "kind": "form"}] * 2000}
        learner.save(big, vid_c)
        n = len(learner.load(vid_c)["attempts"])
        pass4 = n == learner.MAX_ATTEMPTS
        ok &= pass4
        print("④ 2000 条作答记录 → 保留 %d 条（上限 %d）%s"
              % (n, learner.MAX_ATTEMPTS, "✓" if pass4 else "✗"))

        # ⑤ 两个访客同时交卷（各 2 题）：各记 2 条，互不覆盖
        idx = get_index()
        v1, v2 = learner.new_vid(), learner.new_vid()
        q1 = quiz.make_quiz(2, 101, v1)
        q2 = quiz.make_quiz(2, 202, v2)
        a1 = [{"char": it["char"], "choice": 0} for it in q1["items"]]
        a2 = [{"char": it["char"], "choice": 1} for it in q2["items"]]
        t1 = threading.Thread(target=quiz.grade, args=(q1, a1, v1))
        t2 = threading.Thread(target=quiz.grade, args=(q2, a2, v2))
        t1.start(); t2.start(); t1.join(); t2.join()
        n1 = len(learner.load(v1)["attempts"])
        n2 = len(learner.load(v2)["attempts"])
        pass5 = (n1 == 2 and n2 == 2)
        ok &= pass5
        print("⑤ 两人同时交卷（各 2 题）→ %d / %d 条 %s"
              % (n1, n2, "✓" if pass5 else "✗ 有覆盖或串号"))

        # ⑥ 坏行：留证据（corrupt 备份 + LAST_LOAD_ERROR），不静默当没发生
        conn = sqlite3.connect(learner.DB)
        conn.execute("UPDATE learners SET data=? WHERE vid=?", ('{"done": {"sky": ["日"', vid_c))
        conn.commit(); conn.close()
        d = learner.load(vid_c)
        backups = os.listdir(learner.CORRUPT_DIR) if os.path.isdir(learner.CORRUPT_DIR) else []
        pass6 = (d.get("done") == {} and bool(learner.LAST_LOAD_ERROR) and bool(backups))
        ok &= pass6
        print("⑥ 坏行 → 备份 %d 个 / 错误已记录 %s %s"
              % (len(backups), bool(learner.LAST_LOAD_ERROR), "✓" if pass6 else "✗"))

        # ⑦ 老 learner.json 自动导入成「示例」，真实访客仍是空的
        tmp2 = tempfile.mkdtemp(prefix="zq_legacy_")
        legacy = os.path.join(tmp2, "learner.json")
        with io.open(legacy, "w", encoding="utf-8") as f:
            json.dump({"done": {"sky": ["日", "月"]}, "bossCleared": [0],
                       "attempts": [{"char": "日", "ok": False, "kind": "form"}]}, f)
        db2 = os.path.join(tmp2, "learners.db")
        old_db, old_legacy = learner.DB, learner.LEGACY
        learner.DB, learner.LEGACY = db2, legacy
        try:
            demo = learner.load(learner.DEMO_VID)
            fresh = learner.load(learner.new_vid())
            n_seed = learner.seed_demo(fresh_vid := learner.new_vid())
            copied = learner.load(fresh_vid)
            pass7 = (len(demo["attempts"]) == 1 and not fresh["attempts"]
                     and n_seed == 1 and len(copied["attempts"]) == 1 and copied.get("seeded"))
        finally:
            learner.DB, learner.LEGACY = old_db, old_legacy
            shutil.rmtree(tmp2, ignore_errors=True)
        ok &= pass7
        print("⑦ 旧 learner.json → 示例桶可载入、新访客仍为空 %s" % ("✓" if pass7 else "✗"))

        print("\n  结论:", "✓ 存储层通过" if ok else "✗ 未通过")
        return 0 if ok else 1
    finally:
        learner.DB, learner.LEGACY, learner.CORRUPT_DIR = real_db, real_legacy, real_corrupt
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
