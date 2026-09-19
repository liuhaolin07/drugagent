# -*- coding: utf-8 -*-
"""极简 LLM 客户端：OpenAI 兼容端点，多 provider 自动回退。"""
import json

from openai import OpenAI

from config import PROVIDERS

_clients = None


def _init():
    global _clients
    if _clients is not None:
        return
    _clients = []
    for p in PROVIDERS:
        if p["key"]:
            _clients.append((p, OpenAI(api_key=p["key"], base_url=p["base_url"], timeout=90)))
    if not _clients:
        raise RuntimeError("没有可用的 API key（检查 D:/Hermes/.env）")


def chat(messages, temperature=0.3):
    """返回文本；按 provider 顺序重试。"""
    _init()
    last = None
    for p, cli in _clients:
        try:
            r = cli.chat.completions.create(
                model=p["model"], messages=messages, temperature=temperature)
            return r.choices[0].message.content or ""
        except Exception as e:
            last = e
            print(f"  [llm] {p['name']}/{p['model']} 调用失败: {repr(e)[:110]}，切换下一个…")
    raise RuntimeError(f"所有 provider 均失败: {last!r}")


def embed(texts, model="embedding-3"):
    """GLM embedding（免费档，2048 维）；失败返回 None（调用方回退 BM25）。"""
    _init()
    for p, cli in _clients:
        if p["name"] != "glm":
            continue
        try:
            r = cli.embeddings.create(model=model, input=texts)
            return [d.embedding for d in r.data]
        except Exception as e:
            print(f"  [llm] embedding({model}) 失败: {repr(e)[:100]}，回退 BM25 检索")
            return None
    return None


def parse_json(s):
    """鲁棒解析：容忍 ```json 包裹与前后杂质。"""
    if not s:
        return None
    s = s.strip()
    if s.startswith("```"):
        s = s.strip("`")
        if s[:4].lower() == "json":
            s = s[4:]
    i, j = s.find("{"), s.rfind("}")
    if i < 0 or j <= i:
        return None
    try:
        return json.loads(s[i:j + 1])
    except Exception:
        return None
