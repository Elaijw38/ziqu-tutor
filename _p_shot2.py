# -*- coding: utf-8 -*-
"""修正 tests/shot.py：截图文件名用命令行参数，别在 JS 里引用 Python 变量。"""
import io

P = r"C:\DSH\ziqu-tutor\tests\shot.py"
t = io.open(P, encoding="utf-8").read()
bad = "OUTDIR + '/tutor-' + W + 'x' + H + '.png'"
good = "OUTDIR + '/tutor-' + process.argv[5] + 'x' + process.argv[6] + '.png'"
if bad in t:
    t = t.replace(bad, good)
    print("  已修正 JS 里的文件名拼接")
elif good in t:
    print("  已是修正后的写法")
else:
    print("  !! 没找到目标字符串，请人工检查")
io.open(P, "w", encoding="utf-8", newline="\n").write(t)
