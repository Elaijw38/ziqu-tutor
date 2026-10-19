# -*- coding: utf-8 -*-
"""模型接入体检：换模型（尤其是校内本地部署）之前先跑这个。

为什么需要：我们这套智能体靠 4 个工具（检索/学情/出题/判分）运转。
如果校内推理服务没开 tools 支持，换过去"能聊天但不会调工具"，整条链路就废了。
这个脚本一次把关键项都测出来：

    python tools/probe_model.py --base https://api.deepseek.com/v1 --key sk-xxx --model deepseek-chat
    python tools/probe_model.py --base http://10.x.x.x:8000/v1 --key 校内key --model deepseek-v3

检查项：
  1. 连通性 / 模型名是否可用
  2. 普通对话是否正常、延迟多少
  3. **是否支持 tools（函数调用）** ← 最关键
  4. 是否支持 JSON 输出（判分/出题用得上）
  5. 上下文长度（用一个较长输入探边界）
"""
import argparse
import json
import time
import urllib.error
import urllib.request


def _post(base, key, path, payload, timeout=60):
    req = urllib.request.Request(
        base.rstrip("/") + path,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + key})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8"))
    return data, time.time() - t0


def _get(base, key, path, timeout=30):
    req = urllib.request.Request(base.rstrip("/") + path,
                                 headers={"Authorization": "Bearer " + key})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--key", required=True)
    ap.add_argument("--model", required=True)
    args = ap.parse_args()

    ok_all = True

    # 1) 连通性与模型列表
    print("  ① 连通性")
    try:
        models = _get(args.base, args.key, "/models")
        ids = [m.get("id") for m in (models.get("data") or [])][:8]
        print("     ✓ 可访问，模型列表：%s" % (", ".join(ids) or "（空）"))
        if args.model not in ids and ids:
            print("     ⚠ 你指定的模型名不在列表里，确认是否要写成 %s" % ids[0])
    except urllib.error.HTTPError as e:
        print("     ✗ HTTP %s（有些服务不开放 /models，可忽略）" % e.code)
    except Exception as e:
        ok_all = False
        print("     ✗ 连不上：%s" % e)

    # 2) 普通对话 + 延迟
    print("  ② 普通对话")
    try:
        data, dt = _post(args.base, args.key, "/chat/completions",
                         {"model": args.model,
                          "messages": [{"role": "user", "content": "只回两个字：收到"}],
                          "max_tokens": 16})
        txt = data["choices"][0]["message"].get("content", "")
        print("     ✓ %.2fs，返回：%s" % (dt, txt.strip()[:30]))
    except Exception as e:
        ok_all = False
        print("     ✗ 失败：%s" % e)

    # 3) tools 支持（最关键）
    print("  ③ 函数调用（tools）—— 本项目的命门")
    tool = [{
        "type": "function",
        "function": {
            "name": "search_kb",
            "description": "检索课程知识库",
            "parameters": {"type": "object",
                           "properties": {"query": {"type": "string"}},
                           "required": ["query"]},
        },
    }]
    try:
        data, dt = _post(args.base, args.key, "/chat/completions", {
            "model": args.model,
            "messages": [{"role": "user", "content": "帮我查一下「家」这个字的构件"}],
            "tools": tool,
            "tool_choice": "auto",
            "max_tokens": 128,
        })
        msg = data["choices"][0]["message"]
        calls = msg.get("tool_calls") or []
        if calls:
            fn = calls[0].get("function") or {}
            print("     ✓ 支持 tools（%.2fs）示例调用：%s(%s)"
                  % (dt, fn.get("name"), (fn.get("arguments") or "")[:60]))
        else:
            print("     ⚠ 没触发调用（可能是它觉得不需要；再试一次强制）")
            data, dt = _post(args.base, args.key, "/chat/completions", {
                "model": args.model,
                "messages": [{"role": "user", "content": "必须调用 search_kb 查「家」"}],
                "tools": tool,
                "tool_choice": {"type": "function", "function": {"name": "search_kb"}},
                "max_tokens": 128,
            })
            calls = data["choices"][0]["message"].get("tool_calls") or []
            if calls:
                print("     ✓ 强制后支持 tools（%.2fs）" % dt)
            else:
                ok_all = False
                print("     ✗ **不支持 tools**：换过去后出题/判分/学情都会失效，需要改提示词模拟方案")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:160]
        ok_all = False
        print("     ✗ 请求被拒：HTTP %s %s" % (e.code, body))
    except Exception as e:
        ok_all = False
        print("     ✗ 失败：%s" % e)

    # 4) JSON 输出
    print("  ④ JSON 输出")
    try:
        data, dt = _post(args.base, args.key, "/chat/completions", {
            "model": args.model,
            "messages": [{"role": "user", "content": "输出一个 JSON：{\"ok\":true}"}],
            "response_format": {"type": "json_object"},
            "max_tokens": 64,
        })
        print("     ✓ 支持（%.2fs）" % dt)
    except Exception as e:
        print("     ⚠ 不支持或不接受该参数（不影响主流程）：%s" % str(e)[:80])

    print("\n  结论：%s" % ("全部通过，可以直接换" if ok_all
                          else "有项目不通过，换之前先看上面 ✗ / ⚠ 的项"))
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
