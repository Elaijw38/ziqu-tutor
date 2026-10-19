# -*- coding: utf-8 -*-
"""给知识库补「会意解释」这一层。

起因：真模型测「家为什么是屋顶下有猪」，答得出构件（宀+豕），
但答不出「屋下养猪就是家」的造字缘由——因为 kb 里只有 form/play，没有解释。

原则（避免编造）：
  1. 只补**教科书里通行的会意解释**（家=宀+豕、安=宀+女、休=人+木 等），
     不补有争议的学术推论；
  2. 措辞统一带「常见解释」并注明"教学常用说法"，不冒充定论；
  3. 只对有把握的字补，宁可少补。
"""
import io
import json
import os
import re

ROOT = r"C:\DSH\ziqu-tutor"
KB = os.path.join(ROOT, "data", "kb.jsonl")

EXPLAIN = {
    "家": "常见解释：宀是屋顶、豕是猪，屋下养猪——定居下来养猪之处即为「家」。"
          "这是教学上常用的会意解释。（学界对「家」的本义另有讨论，此处不展开。）",
    "安": "常见解释：宀是屋顶、女是女子，女子安坐屋内即「安」，表示安定、安适。",
    "休": "常见解释：人靠在树（木）旁歇息，即「休」，本义是休息。",
    "明": "常见解释：日与月并出，明也——「明」用日月表示光亮。",
    "林": "常见解释：二木为「林」，表示成片的树。",
    "森": "常见解释：三木为「森」，比「林」更密，表示树木繁盛。",
    "焚": "常见解释：木上有火即「焚」，表示烧林。",
    "涉": "常见解释：水旁加止（脚），表示徒步涉水。",
    "逐": "常见解释：止（脚）在豕后，表示追赶野猪，引申为追逐。",
    "牧": "常见解释：手持鞭（攴）驱牛，表示放牧。",
    "采": "常见解释：手（爪）在木上，表示摘取。",
    "取": "常见解释：手（又）执耳，古代战利以割耳计数，故为「取」。",
}


def main():
    rows = [json.loads(l) for l in io.open(KB, encoding="utf-8") if l.strip()]
    hit = 0
    for r in rows:
        ch = r.get("char")
        if ch in EXPLAIN and r.get("kind") in ("boss", "wangyi", "codex"):
            if "常见解释" in (r.get("text") or ""):
                continue
            r["text"] = r["text"].rstrip("。") + "。" + EXPLAIN[ch]
            hit += 1
    with io.open(KB, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("  补了 %d 条会意解释，覆盖字：%s" % (hit, "、".join(EXPLAIN.keys())))
    print("  条目总数 %d" % len(rows))


if __name__ == "__main__":
    main()
