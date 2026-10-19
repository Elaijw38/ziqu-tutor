# 甲骨文 AI 助教 · 龟宝（ziqu-tutor）

**一句话定位**：郑州大学《汉字与中国文化》通识课的甲骨文学习助教——学生问字形、字义、构形，助教只答知识库里有依据的话并附出处；答完能诊断、能出题、能评讲，形成「问 → 诊 → 练 → 评」闭环。

**适配赛道**：郑州大学首届 AI 智能体创新应用大赛 **A2 · AI 助教**（教学—学习—评价闭环）。
**不依附于任何一款教学游戏**：课程案例只是知识来源之一，助教的覆盖面由上游甲骨字形数据集独立支撑。

---

## 1. 架构

```
                    浏览器（web/index.html）
                    │  静态页 + fetch JSON
                    ▼
        ┌───────────────────────────────────────────┐
        │  src/server.py                            │
        │  标准库 ThreadingHTTPServer，零依赖        │
        │  6 个接口 + 静态文件 + 邀请码/限流/访客身份 │
        └───────┬───────────────┬───────────────────┘
                │               │
      ┌─────────▼─────────┐     │
      │ src/ask.py 问答编排│     │
      │  ① Dify（可选）    │     │
      │  ② llm.py agent   │     │
      │  ③ 本地抽取式      │     │
      │  ④ 拒答 / 反问     │     │
      └───┬───────┬───────┘     │
          │       │             │
  ┌───────▼──┐ ┌──▼──────────┐  │
  │retrieval │ │llm.py agent │  │
  │中文检索   │ │function call│  │
  │1+2-gram  │ │ search_kb   │  │
  │+TF-IDF   │ │ get_learner │  │
  └────┬─────┘ │ generate_quiz│ │
       │       │ submit_answers│ │
       │       └──┬────────┬──┘  │
       │          │        │     │
       │   ┌──────▼──┐ ┌───▼─────┐│
       │   │learning │ │ quiz.py ││
       │   │诊断      │ │出题/判分 ││
       │   └──┬──────┘ └───┬─────┘│
       │      │            │      │
       │   ┌──▼────────────▼───┐  │
       │   │ learner.py SQLite  │  │
       │   │ 学情 + 题目 + 证据  │  │
       │   └───────────────────┘  │
       │                          │
  ┌────▼──────────────┐   ┌───────▼────────┐
  │ data/kb.jsonl     │   │ src/glyphs.py  │
  │ 1446 条知识条目    │   │ 字形 → SVG     │
  └───────────────────┘   └────────────────┘
```

三层降级，任一层失败自动往下退，页面不报错、不白屏：

| 链路 | 依赖 | 回答形态 |
|---|---|---|
| Dify 应用 | `ZQ_DIFY_BASE/KEY` | 自带检索来源（`retriever_resources`） |
| 直连模型 agent | `ZQ_LLM_BASE/KEY/MODEL` | function calling 调工具，事实全部来自知识库 |
| 本地抽取式 | 无 | 拼接检索命中的条目原文，不生成 |

---

## 2. 30 秒启动

```bash
python src/server.py 8770
# 浏览器打开 http://127.0.0.1:8770
```

自检（应看到 `kb_rows: 1446`、`glyph_chars: 1168`；配了模型则 `llm: true`）：

```bash
curl http://127.0.0.1:8770/api/health
# {"ok":true,"kb_rows":1446,"chars":1183,"glyph_chars":1168,"course_chars":146,
#  "llm":true,"model":"deepseek-chat","dify":false,...}
```

**零依赖**：只用 Python 标准库，不需要 `pip install`。上游字形数据已随仓库提供，断网也能跑（只是没有模型措辞，走抽取式）。

接模型（可选）：复制 `config.example.env` 为 `config.local.env`，填 `ZQ_LLM_BASE / ZQ_LLM_KEY / ZQ_LLM_MODEL`。
OpenAI 兼容协议，百炼、DeepSeek、火山方舟、智谱、本地 Ollama 都只改这三行。

---

## 3. 接口清单

| 方法 | 路径 | 入参 | 出参（关键字段） |
|---|---|---|---|
| POST | `/api/ask` | `{question, history?, conversation_id?, session_id?}` | `answer, citations[{source,title,snippet}], status(answer/refuse/clarify), mode(dify/agent/extractive/refuse), trace[], rounds` |
| GET | `/api/diagnose` | `?quiz_id=`（可选，带上就是「本次练习」口径） | `overview{range_text,answered,correct,total_items}, knowledge_points[{kp_id,name,status,answered,ok,wrong,accuracy,wrong_chars}], wrong_items[], causes[], actions[]`，另附兼容旧字段 `coverage,level,accuracy,by_kind,weak_comps,wrong_top,suggestions` |
| POST | `/api/quiz` | `{n=3, seed?, kp_id?}` | `quiz_id, items[{item_id,char,type,kp_id,kp_name,difficulty,question,options[]}], count`；`answer_index` 为兼容旧前端保留，**判分以服务端 `quiz_items` 为准**，客户端回传的选项不参与计分；走 agent 工具链路时题目交给模型、答案留在服务端 |
| POST | `/api/grade` | `{quiz_id, answers:[{item_id,choice}]}` | `score, correct, total, results[{ok,your,right,why,cause}], by_kp[]`；同时写入证据表 |
| GET | `/api/glyph/<字>` | `?size=120&download=1`（尺寸 40–1024） | `image/svg+xml` 字形图；无字形时 404 `{error,char,glyphs}` |
| GET | `/api/health` | — | `kb_rows, chars, glyph_chars, course_chars, llm, model, dify, store{attempts,learned,visitors,seeded,error}` |

另有 `POST /api/reset`（清空我这个访客的记录）、`POST /api/seed-demo`（载入示例学情，页面会标注「含示例数据」）。

口径提醒（三个数字不能混用）：

| 字段 | 值 | 含义 |
|---|---|---|
| `kb_rows` | 1446 | 知识库条目总数 |
| `glyph_chars` | 1168 | **真有甲骨字形数据**的字数（`kind=glyph`） |
| `chars` | 1183 | 知识库出现过的全部字（含 15 个只有课程/通识描述、无字形的字） |
| `course_chars` | 146 | 课程字表，**学情覆盖率的分母只按它算** |

---

## 4. 数据来源与许可

| 层 | 规模 | 来源与许可 |
|---|---|---|
| 甲骨字形 | **1,203 个字形 / 1,168 个字** | Oracle Bone Glyphs v0.3（Li & Bian, *npj Heritage Science* 2026），**CC BY 4.0**，DOI `10.5281/zenodo.22467946`；原样保存在 `data/upstream/jgw_1203_labeled.json`，署名见 `data/upstream/ATTRIBUTION.md` |
| 甲骨文通识 | 24 条 | 王宇信《甲骨学通论》、裘锡圭《文字学概要》、董作宾《甲骨文断代研究例》、《说文解字·叙》等，逐条标出处 |
| 字源解读 | 29 条 | 《说文解字》 + 裘锡圭《文字学概要》 |
| 构件拆分 | 61 个字（55 条 `comp` 条目 + 6 条内嵌） | 按甲骨字形结构拆分，参《说文解字》形义分析与裘锡圭《文字学概要》；有释读分歧的不录 |
| 课程案例 | 170 条 / 146 字 | 只读导出自本人另一件作品「字趣」的《殷商王邑》《构件讨伐》，**原作品未改动** |

**王邑实物点标注**：地图类条目一律写「教学示意图（非考古复原）」，不冒充考古结论。
每条知识库条目都带 `source` 字段，前端「出处」折叠条直接展示，答辩可逐条核对。

---

## 5. 评测方法

固定评测集 `tests/eval_set.jsonl`，六类共 **45 条**，评分口径写在数据集里、不写死在代码：

| 类别 | 条数 | 考什么 |
|---|---|---|
| 直接回答 | 12 | 字形、字义、构形、构件是否答对且带出处 |
| 形近字 | 8 | 人和大、日和曰这类易混字能否分清 |
| 库外问题 | 8 | 知识库没有的是否老实拒答，不拿别的条目凑 |
| 错误前提 | 6 | 学生问句里含错误前提（如「甲骨文都是刻在竹简上的吧」）能否纠正而不是顺着答 |
| 出处核对 | 6 | 引的出处是否对得上条目 |
| 争议与限制 | 5 | 学界有分歧的释读是否并列说明、不下定论 |

```bash
python tests/run_eval.py                          # 跑本地 8770
python tests/run_eval.py --base http://1.2.3.4:8770   # 跑公网实例
python tests/run_eval.py --json out/eval.json     # 存逐条明细
```

判定项：`refuse`（期望拒答）、`must_all` / `must_any`（必含片段）、`must_not`（禁出片段）、`citation`（必须带出处）、`cite_title_any`（出处标题命中）。

**当前结果：45/45 通过。** 另有三套工程测试不依赖真 key：

```bash
python tests/test_kb.py        # 知识库结构：覆盖、来源、分母口径、检索命中
python tests/test_store.py     # SQLite 存储：并发写、分人隔离、事务回滚、坏行备份
python tests/test_learning.py  # 四库诊断：关联键、阈值、错因证据、旧数据迁移
python tests/test_agent.py     # agent 全链路（假模型）：工具调用、多轮、三态、出题不泄答案
python tests/test_dify.py      # Dify 链路（假服务）：出处还原、去重、拒答标记
```

---

## 6. 已知限制

1. **单机 SQLite**。学情按浏览器随机 `zq_vid`（HttpOnly cookie）分开，存 `data/learners.db`；换设备、清缓存、无痕窗口就等于从头开始。没有账号体系，不能跨设备同步。
2. **没有教师端**。班级汇总、题目录入、课程知识点维护都得改 JSON 或直接读库；教师目前只能看单台设备的学情页。
3. **课程外的新字只能给字形层事实**。1,168 个字里多数只有形/音/笔画（标注 N 画、N 个折线点），没有释读。问「这个字像什么」时助教会照实说「材料只标注了 N 画，没有说明」，**不会自编象形描述**；想讲字源得有教师提供的释读材料。
4. **依赖 function calling**。学情诊断、出题、判分靠模型调工具。模型不支持工具调用、或额度用尽时，会降级成抽取式问答——能答知识题，但不会诊断、不会出题。
5. **公网演示靠临时隧道**。cloudflared 临时域名随进程变、本机必须开机；长期对外需要固定域名部署（`Dockerfile` 已备）。
6. **题库偏薄**。字义题 61 字、构件题 61 字、字形笔画题 137 字，都是程序从知识库字段生成的；情境题、材料释读题、商文化背景题还没有可自动判分的题型，学情页会如实标「本课暂无题目」。
7. **不做图片识别**。学生发拓片截图时，助教会先说明这一点，再请对方用文字描述或报字形编号。

---

## 7. 目录结构

```
ziqu-tutor/
├─ src/
│  ├─ server.py       标准库 HTTP 服务：6 个接口 + 静态页 + 邀请码/限流/访客 cookie
│  ├─ ask.py          问答编排：Dify → agent → 本地抽取式 → 拒答（逐级降级）+ 三态判定
│  ├─ llm.py          OpenAI 兼容客户端 + 工具调用 agent（search_kb / get_learner_state /
│  │                  generate_quiz / submit_answers）+ 系统提示词（证据规则、格式分派）
│  ├─ dify.py         Dify 原生 chat-messages 接入，解析 retriever_resources 还原出处
│  ├─ retrieval.py    中文检索：字 1-gram + 2-gram + TF-IDF（零依赖，可解释）
│  ├─ glyphs.py       解析上游 stroke 字段 → SVG 字形（含笔顺分组）
│  ├─ learner.py      SQLite：学情 JSON、quiz_items（题目）、attempts（证据）
│  ├─ curriculum.py   加载 data/curriculum.json 与 data/diagnosis.json（配置写坏有兜底）
│  ├─ learning.py     四库联动诊断：按知识点统计、阈值判状态、错因归因、证据回溯
│  ├─ quiz.py         出题（题型轮转、错题优先、可按知识点）+ 服务端判分
│  ├─ build_kb.py     三源合并 → data/kb.jsonl
│  └─ build_glyphs.py 上游字形 → data/glyphs.json
├─ web/
│  ├─ index.html      单文件前端（问答 / 学情 / 练习三页签，空态欢迎区，回答旁小头像）
│  └─ assets/         校徽、龟宝形象
├─ data/
│  ├─ kb.jsonl        知识库 1446 条 / 1183 字，每条带 source
│  ├─ upstream/       上游 1,203 字形数据集 + ATTRIBUTION.md（CC BY 4.0）
│  ├─ comps_extra.json 构件拆分补充数据
│  ├─ curriculum.json 课程目标、能力维度、知识点、题型→知识点（可编辑）
│  ├─ diagnosis.json  诊断阈值、状态文案、错因规则、补练动作（可编辑）
│  └─ learners.db     运行期生成：learners / quiz_items / attempts 三表
├─ tests/
│  ├─ eval_set.jsonl  固定评测集 45 条（六类）
│  └─ run_eval.py     评测跑分脚本
├─ out/               Dify 知识库导出、提示词、演示材料、离线包
├─ docs/              演示脚本、项目进展报告
├─ config.example.env 配置模板（复制成 config.local.env 使用）
├─ Dockerfile         容器部署
└─ start-public.bat   本机公网演示启动脚本（带邀请码与限流）
```

---

## 8. 安全说明

- **`config.local.env` 已被 `.gitignore` 排除，任何情况下不得提交**。真实密钥只写在本地这个文件里，或通过部署平台的环境变量注入。
- 密钥只在服务端读取，前端拿不到；`/api/health` 不输出 `llm_base` / `dify_base` / key 这类部署配置。
- 对外必须设 `ZQ_ACCESS_CODE`（邀请码门禁）与 `ZQ_RATE_PER_HOUR`（单 IP 每小时提问上限），否则任何人拿到链接都能耗你的模型额度。分享链接可用 `/?code=xxx` 直达，邀请码只放 HttpOnly cookie。
- 学情只用一个随机 `zq_vid` 当钥匙，**不含姓名、学号、联系方式**；`/api/diagnose` 只返回当前浏览器的数据，不暴露他人作答明细。
- 若仓库曾推送到公开平台，先确认 git 历史里没有明文 key；换过 key 的旧 key 应视为已泄露。
- 上游字形数据 CC BY 4.0，转载或再分发须保留署名（见 `data/upstream/ATTRIBUTION.md`）。

---

## 9. 更多文档

- `AGENT_HANDOFF.md` — 接口契约、数据结构、踩坑记录（给接手的工程师）
- `docs/演示脚本.md` — 答辩演示的提问顺序与讲解点
- `docs/项目进展报告.md` — 项目阶段记录
