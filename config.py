# -*- coding: utf-8 -*-
"""配置：从 D:/Hermes/.env 读 API key（不回显、不落盘）与 LLM provider 列表。"""
import os

ENV_PATH = r"D:/Hermes/.env"


def _load_env(path=ENV_PATH):
    d = {}
    try:
        for line in open(path, encoding="utf-8", errors="replace"):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            d[k.strip()] = v.strip().strip('"').strip("'")
    except Exception:
        pass
    return d


_ENV = {**_load_env(), **os.environ}

# 优先智谱免费档（GLM_API_KEY），失败自动回退 DeepSeek
PROVIDERS = [
    {
        "name": "glm",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model": _ENV.get("DRUGAGENT_MODEL", "glm-4-flash"),
        "key": _ENV.get("GLM_API_KEY", ""),
    },
    {
        "name": "deepseek",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
        "key": _ENV.get("DEEPSEEK_API_KEY", ""),
    },
]
