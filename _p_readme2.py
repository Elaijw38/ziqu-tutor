# -*- coding: utf-8 -*-
"""把「接大模型」一节写进 README（用文件写，避免命令行引号问题）。"""
import io

P = r"C:\DSH\ziqu-tutor\README.md"
t = io.open(P, encoding="utf-8").read()

SEC = """## 接大模型

不接模型也能用（抽取式回答）。要接，复制 `config.example.env` 为 `config.local.env`，填三行：

```
ZQ_LLM_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1
ZQ_LLM_KEY=sk-你的key
ZQ_LLM_MODEL=qwen-plus
```

重启服务后看是否生效：

```
curl http://127.0.0.1:8770/api/health
# {"ok":true,...,"llm":true,"model":"qwen-plus"}
```

**为什么用 OpenAI 兼容协议**：百炼、火山方舟、DeepSeek、智谱、本地 Ollama/vLLM 都提供
`/chat/completions`，换平台只改三个环境变量，代码不动。

**接入后的行为（真正的 agent）**：

1. 模型自己决定调哪个工具：问字形 → `search_kb`；问「我哪里弱」 → `get_learner_state`
2. 服务执行工具，把知识库原文 / 学情以 JSON 回填给模型
3. 模型基于这些事实作答（系统提示词禁止补充事实之外内容）
4. 检索命中的条目与出处自动并入返回，前端照旧可展开核对

**降级**：未配置、超时（默认 25s）、额度用尽、返回异常 —— 一律退回本地抽取式回答，
接口不报错、页面不白屏。现场演示这点很关键。

**密钥安全**：key 只在服务端读取，前端拿不到；`config.local.env` 已加入 `.gitignore`。

**验证**：`python tests/test_agent.py` 用假模型跑通「工具调用 → 检索 → 出处合并」全链路，
不需要真 key。

"""

if "## 接大模型" not in t:
    if "## 可选：接入大模型" in t:
        t = t.replace("## 可选：接入大模型", SEC + "## 可选：接入大模型")
    else:
        t = t.rstrip() + "\n\n" + SEC
    io.open(P, "w", encoding="utf-8", newline="\n").write(t)
    print("  README 已加「接大模型」一节")
else:
    print("  README 已有该节")
