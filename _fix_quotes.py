# -*- coding: utf-8 -*-
"""修正 _fill_form.py 里被写成半角引号的中文引号（会破坏字符串字面量）。"""
import io

P = r"C:\DSH\ziqu-tutor\_fill_form.py"
Q = chr(34)   # 半角引号，避免本文件里出现同类问题

t = io.open(P, encoding="utf-8").read()
pairs = [
    ("约束为" + Q + "只允许使用给定事实作答" + Q, "约束为「只允许使用给定事实作答」"),
    ("以" + Q + "不编造" + Q + "为硬约束", "以「不编造」为硬约束"),
    ("不只报" + Q + "覆盖率" + Q, "不只报「覆盖率」"),
    ("标注为" + Q + "示例课程，可配置" + Q, "标注为「示例课程，可配置」"),
    ("（如" + Q + "今天天气" + Q + "）", "（如「今天天气」）"),
    ("给出构件短板——", "给出构件短板——"),
]
n = 0
for old, new in pairs:
    if old in t:
        t = t.replace(old, new)
        n += 1
        print("  替换：", old[:24])
io.open(P, "w", encoding="utf-8", newline="\n").write(t)
print("  共替换 %d 处" % n)
