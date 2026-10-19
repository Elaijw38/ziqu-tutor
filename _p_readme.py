# -*- coding: utf-8 -*-
"""更新 README 的进度清单（用文件写，避免命令行引号问题）。"""
import io

p = r"C:\DSH\ziqu-tutor\README.md"
t = io.open(p, encoding="utf-8").read()

old = """- [ ] `/api/diagnose` 学情诊断：读前端的本地进度 → 输出薄弱构件的画像
- [ ] `/api/quiz` 按薄弱点自动组卷
- [ ] `/api/grade` 评阅并回写画像
- [ ] 前端加"画像卡 + 一键出题"，形成"问 → 诊 → 练 → 评"闭环"""
new = """- [x] `/api/diagnose` 学情诊断：覆盖率、分片掌握、构件短板、错题、给建议
- [x] `/api/quiz` 按学情自动组卷（题型轮转：构件 / 字义 / 打法，错题优先）
- [x] `/api/grade` 评阅 + 逐题讲解 + 回写 attempts
- [x] 前端三页签：问答 / 学情 / 练习，形成"问 → 诊 → 练 → 评"闭环
- [ ] 接入大模型（可选，接口已留：ZQ_LLM_KEY / ZQ_LLM_BASE / ZQ_LLM_MODEL）
- [ ] 教师端班级汇总（A2 提到的"AI 通识实验室"改造方向）"""

if old in t:
    t = t.replace(old, new)
    print("  清单已更新")
else:
    print("  未找到原清单，追加一节")
    t = t.rstrip() + "\n\n## 当前进度\n\n" + new + "\n"

t = t.replace("src/ask.py        问答编排",
              "src/learner.py    学情存取与诊断\nsrc/quiz.py       出题与评阅\nsrc/ask.py        问答编排")
io.open(p, "w", encoding="utf-8", newline="\n").write(t)
print("  写出 README.md（%d 字）" % len(t))
