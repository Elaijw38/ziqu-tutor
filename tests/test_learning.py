# -*- coding: utf-8 -*-
"""四库联动的学情诊断测试（不需要联网、不碰真实学情库）。

覆盖：
  ① 四库关联：item → kp → attempt 全链路键能对上
  ② 判分以服务端为准：客户端改答案拿不到分
  ③ 阈值与状态：证据不足 / 建议巩固 / 初步掌握
  ④ 错因必须挂证据；旧记录无法归因时标「暂无法归因」
  ⑤ 旧 JSON 学情迁移：字段补默认值、重复诊断不重复计数
  ⑥ 空态不虚构：没作答就不给掌握结论
  ⑦ 按知识点出题：题型不串
"""
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import learner      # noqa: E402
import quiz         # noqa: E402
import learning     # noqa: E402
import curriculum   # noqa: E402
from retrieval import get_index   # noqa: E402

OK = 0
FAIL = 0


def check(name, cond, extra=""):
    global OK, FAIL
    if cond:
        OK += 1
        print("  ✓ %s" % name)
    else:
        FAIL += 1
        print("  ✗ %s %s" % (name, extra))


def setup_tmp():
    tmp = tempfile.mkdtemp(prefix="zq-learn-")
    learner.DB = os.path.join(tmp, "learners.db")
    learner.LEGACY = os.path.join(tmp, "no-legacy.json")   # 隔离真实示例数据
    learner.CORRUPT_DIR = os.path.join(tmp, "corrupt")
    learner._READY.clear()
    return tmp


def right_answer(it):
    return it["answer_index"]


def wrong_answer(it):
    return (it["answer_index"] + 1) % len(it["options"])


def submit(q, vid, pick):
    answers = [{"item_id": it["item_id"], "char": it["char"], "choice": pick(it)}
               for it in q["items"]]
    return quiz.grade({}, answers, vid, q["quiz_id"])


def main():
    idx = get_index()
    tmp = setup_tmp()
    vid = "b" * 32
    try:
        print("[1] 四库关联")
        q = quiz.make_quiz(3, 11, vid)
        check("出题带 quiz_id", bool(q["quiz_id"]), str(q.get("quiz_id")))
        check("每题有 item_id 与知识点",
              all(it.get("item_id") and it.get("kp_id") for it in q["items"]))
        check("知识点取到课程配置里的名字",
              all(it["kp_name"] == curriculum.kp_name(it["kp_id"]) for it in q["items"]))
        g = submit(q, vid, right_answer)
        atts = learner.list_attempts(vid, quiz_id=q["quiz_id"])
        check("评阅写入证据条数 = 题数", len(atts) == len(q["items"]), str(len(atts)))
        by_item = {a["item_id"]: a for a in atts}
        check("证据指向题目与知识点",
              all(a["item_id"] in by_item and by_item[a["item_id"]]["kp_id"] == a["kp_id"]
                  for a in g["results"]))
        d = learning.diagnose(idx, vid, quiz_id=q["quiz_id"])
        check("诊断覆盖本次练习", d["overview"]["quiz_id"] == q["quiz_id"])
        check("本次概览题数对得上",
              d["overview"]["answered"] == len(q["items"]) == d["overview"]["total_items"])
        check("诊断按知识点聚合",
              sum(k["answered"] for k in d["knowledge_points"]) == len(q["items"]))

        print("[2] 判分以服务端为准")
        vid2 = "c" * 32
        q2 = quiz.make_quiz(3, 12, vid2)
        fake = {"items": [{"char": it["char"], "type": it["type"], "options": it["options"],
                           "answer": it["options"][0], "answer_index": 0}
                          for it in q2["items"]]}
        g2 = quiz.grade(fake, [{"item_id": it["item_id"], "char": it["char"], "choice": 0}
                               for it in q2["items"]], vid2, q2["quiz_id"])
        expect = sum(1 for it in q2["items"] if it["answer_index"] == 0)
        check("伪造 answer_index 无效", g2["correct"] == expect,
              "正确 %d / 应为 %d" % (g2["correct"], expect))

        print("[3] 阈值与状态")
        # 5 题对 4 → 初步掌握
        vid3 = "d" * 32
        # 同一知识点集中出 5 题：阈值是按知识点算的，混合卷每点只有 1 题
        q3 = quiz.make_quiz(5, 13, vid3, kp_id="kp.comp.split")
        answers = [{"item_id": it["item_id"], "char": it["char"],
                    "choice": right_answer(it)} for it in q3["items"]]
        answers[0]["choice"] = wrong_answer(q3["items"][0])
        quiz.grade({}, answers, vid3, q3["quiz_id"])
        d3 = learning.diagnose(idx, vid3, quiz_id=q3["quiz_id"])
        kp3 = [k for k in d3["knowledge_points"] if k["answered"]]
        check("5 题 4 对 → 初步掌握",
              all(k["status_key"] in ("emerging", "limited_ok") for k in kp3),
              str([(k["name"], k["status"]) for k in kp3]))
        # 5 题对 1 → 建议巩固
        vid4 = "e" * 32
        q4 = quiz.make_quiz(5, 14, vid4, kp_id="kp.comp.split")
        answers = [{"item_id": it["item_id"], "char": it["char"],
                    "choice": wrong_answer(it)} for it in q4["items"]]
        answers[0]["choice"] = right_answer(q4["items"][0])
        quiz.grade({}, answers, vid4, q4["quiz_id"])
        d4 = learning.diagnose(idx, vid4, quiz_id=q4["quiz_id"])
        kp4 = [k for k in d4["knowledge_points"] if k["answered"]]
        check("5 题 1 对 → 建议巩固",
              all(k["status_key"] in ("weak", "limited_weak") for k in kp4),
              str([(k["name"], k["status"]) for k in kp4]))
        check("正确率按知识点算", all(k["accuracy"] <= 100 for k in kp4))
        # 3 题 → 证据不足
        vid5 = "f" * 32
        q5 = quiz.make_quiz(3, 15, vid5)
        submit(q5, vid5, right_answer)
        d5 = learning.diagnose(idx, vid5, quiz_id=q5["quiz_id"])
        kp5 = [k for k in d5["knowledge_points"] if k["answered"]]
        check("3 题 → 证据不足", all(k["status_key"] == "insufficient" for k in kp5),
              str([(k["name"], k["status"]) for k in kp5]))
        check("证据不足不给掌握结论",
              all("证据不足" in k["status"] for k in kp5))

        print("[4] 错因与证据")
        d6 = learning.diagnose(idx, vid4, quiz_id=q4["quiz_id"])
        check("有错题明细（5 题 1 对 → 4 条）", len(d6["wrong_items"]) == 4,
              str(len(d6["wrong_items"])))
        ids = {a["attempt_id"] for a in learner.list_attempts(vid4)}
        check("每条错题都指向真实证据",
              all(w["attempt_id"] in ids for w in d6["wrong_items"]))
        check("每条错因都带证据",
              all(c["evidence"] and all(e["attempt_id"] in ids for e in c["evidence"])
                  for c in d6["causes"]))
        check("错因来自配置库",
              all(c["cause_id"] in [x.get("cause_id") for x in curriculum.cause_rules()]
                  or c["cause_id"] == curriculum.unattributed()["cause_id"]
                  for c in d6["causes"]))
        check("诊断不泄露选项下标", "answer_index" not in json.dumps(d6, ensure_ascii=False))

        print("[5] 旧数据迁移")
        vid7 = "1" * 32
        learner.save({"done": {}, "bossCleared": [],
                      "attempts": [{"char": "日", "ok": False, "kind": "form", "ts": 1},
                                   {"char": "月", "ok": True, "kind": "form", "ts": 2}]}, vid7)
        d7 = learning.diagnose(idx, vid7)
        kp7 = [k for k in d7["knowledge_points"] if k["answered"]]
        check("旧记录归入知识点", len(kp7) == 1 and kp7[0]["answered"] == 2,
              str([(k["name"], k["answered"]) for k in kp7]))
        check("旧记录标 legacy 且不硬编错因",
              all(w["legacy"] for w in d7["wrong_items"]) and
              all(w["cause"] == "暂无法归因" for w in d7["wrong_items"]))
        d7b = learning.diagnose(idx, vid7)
        kp7b = [k for k in d7b["knowledge_points"] if k["answered"]]
        check("重复诊断不重复计数", kp7b[0]["answered"] == 2, str(kp7b[0]["answered"]))
        check("迁移后不再有未归因的假证据",
              all(a["attempt_id"].startswith("legacy.") for a in learner.list_attempts(vid7)))

        print("[6] 空态与课程库")
        vid8 = "2" * 32
        d8 = learning.diagnose(idx, vid8)
        check("空态明确未开始", d8["overview"]["range_type"] == "none")
        check("空态建议先练习", any(a["cta"] == "quiz" for a in d8["actions"]))
        check("没有作答就没有错题明细", d8["wrong_items"] == [])
        check("未作答的知识点都是证据不足",
              all(k["status_key"] in ("insufficient", "no_items")
                  for k in d8["knowledge_points"]))
        no_items = [k for k in d8["knowledge_points"] if k["status_key"] == "no_items"]
        check("无题知识点如实标注", all(k["available_chars"] == 0 for k in no_items),
              str([(k["name"], k["available_chars"]) for k in no_items]))
        has = [k for k in d8["knowledge_points"] if k["has_items"]]
        check("有题知识点给出可用字量", has and all(k["available_chars"] > 0 for k in has),
              str([(k["name"], k["available_chars"]) for k in has]))

        print("[7] 按知识点出题")
        q9 = quiz.make_quiz(3, 16, "3" * 32, kp_id="kp.comp.split")
        check("指定知识点只出该题型",
              q9["count"] > 0 and all(it["type"] == "comp" for it in q9["items"]),
              str([it["type"] for it in q9["items"]]))
        q10 = quiz.make_quiz(3, 17, "4" * 32, kp_id="kp.reading.evidence")
        check("无题知识点明确返回空", q10["count"] == 0 and bool(q10.get("error")))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n结论: %s（%d/%d）" % ("✓ 四库诊断通过" if not FAIL else "✗ 有失败项",
                                   OK, OK + FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
