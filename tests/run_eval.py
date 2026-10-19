# -*- coding: utf-8 -*-
"""固定评测集跑分：内容质量三项（对答 / 引用 / 拒答）。

对应蓝图 §8「内容质量」：
  用 30–50 条人工核验的问题做固定评测集，包含：有明确答案、形近字、
  争议释读、库内没有的问题、错误前提问题和出处核对。

用法：
    python tests/run_eval.py                      # 跑本地服务
    python tests/run_eval.py --base http://...    # 跑别处（如公网实例）
    python tests/run_eval.py --json out.json      # 存明细

评分口径（都在 eval_set.jsonl 里声明，不在代码里写死）：
    refuse          期望拒答：返回 refused 或 mode=refuse
    must_all        所有片段都要出现
    must_any        至少出现一个片段
    must_not        一个都不能出现
    citation        是否有出处
    cite_title_any  出处标题里至少命中一个（考验"引对了没"）
"""
import argparse
import collections
import io
import json
import os
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SET = os.path.join(ROOT, "tests", "eval_set.jsonl")


def load_set():
    rows = []
    with io.open(SET, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def ask(base, q, timeout=120):
    body = json.dumps({"question": q}).encode("utf-8")
    req = urllib.request.Request(base.rstrip("/") + "/api/ask", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def check(item, res):
    """返回 (通过?, 失败原因列表)。"""
    exp = item.get("expect") or {}
    ans = (res.get("answer") or "")
    cites = res.get("citations") or []
    titles = " ".join(str(c.get("title") or "") + str(c.get("id") or "") + str(c.get("char") or "")
                      for c in cites)
    reasons = []

    if exp.get("refuse"):
        if not (res.get("refused") or res.get("mode") == "refuse"):
            reasons.append("本应拒答却作答")
        if reasons:
            return False, reasons
        return True, []

    for w in exp.get("must_all") or []:
        if w not in ans:
            reasons.append("缺「%s」" % w)
    anyw = exp.get("must_any") or []
    if anyw and not any(w in ans for w in anyw):
        reasons.append("未命中任一关键词 %s" % anyw)
    for w in exp.get("must_not") or []:
        if w in ans:
            reasons.append("不该出现「%s」" % w)
    if exp.get("citation") and not cites:
        reasons.append("没有出处")
    ct = exp.get("cite_title_any") or []
    if ct and not any(w in titles for w in ct):
        reasons.append("出处没对上 %s" % ct)
    return (not reasons), reasons


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8770")
    ap.add_argument("--json", default="")
    ap.add_argument("--only", default="")
    args = ap.parse_args()

    items = load_set()
    if args.only:
        items = [i for i in items if i["cat"] == args.only]
    print("  评测集 %d 条  →  %s" % (len(items), args.base))

    stats = collections.defaultdict(lambda: [0, 0])
    fails = []
    for it in items:
        try:
            res = ask(args.base, it["q"])
        except Exception as e:
            stats[it["cat"]][1] += 1
            fails.append({"id": it["id"], "q": it["q"], "why": ["请求失败: %s" % e]})
            print("  %-4s %-8s ✗ 请求失败" % (it["id"], it["cat"]))
            continue
        ok, why = check(it, res)
        stats[it["cat"]][1] += 1
        if ok:
            stats[it["cat"]][0] += 1
        else:
            fails.append({"id": it["id"], "cat": it["cat"], "q": it["q"], "why": why,
                          "answer": (res.get("answer") or "")[:300],
                          "n_cites": len(res.get("citations") or [])})
        print("  %-4s %-8s %s %s" % (it["id"], it["cat"], "✓" if ok else "✗",
                                     "" if ok else "；".join(why)))

    print("\n  === 分类得分 ===")
    total_ok = total_all = 0
    for cat, (ok, n) in stats.items():
        total_ok += ok
        total_all += n
        print("  %-10s %2d/%2d  %5.0f%%" % (cat, ok, n, ok * 100 / max(1, n)))
    print("  %-10s %2d/%2d  %5.0f%%" % ("合计", total_ok, total_all,
                                       total_ok * 100 / max(1, total_all)))

    if fails:
        print("\n  === 未通过 %d 条（前 8 条）===" % len(fails))
        for f in fails[:8]:
            print("  [%s] %s\n     原因：%s\n     答：%s"
                  % (f["id"], f["q"], "；".join(f["why"]), (f.get("answer") or "")[:110]))

    if args.json:
        d = os.path.dirname(args.json)
        if d and not os.path.isdir(d):
            os.makedirs(d, exist_ok=True)
        io.open(args.json, "w", encoding="utf-8", newline="\n").write(
            json.dumps({"base": args.base,
                        "score": {k: {"ok": v[0], "n": v[1]} for k, v in stats.items()},
                        "total": {"ok": total_ok, "n": total_all},
                        "fails": fails}, ensure_ascii=False, indent=1))
        print("\n  明细已写：%s" % args.json)
    return 0 if total_ok == total_all else 1


if __name__ == "__main__":
    sys.exit(main())
