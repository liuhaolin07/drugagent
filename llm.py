"""OpenAI-compatible providers with lazy clients and explicit failure semantics."""
import json
import logging
from threading import Lock

from openai import OpenAI
from config import PROVIDERS

logger = logging.getLogger(__name__)


class MissingProviderError(RuntimeError):
    def __init__(self):
        super().__init__("请在环境变量或项目 .env 中配置 GLM_API_KEY 或 DEEPSEEK_API_KEY，再启动分析。")


class ProviderError(RuntimeError):
    pass


class LLMClient:
    def __init__(self, providers=None, client_factory=OpenAI):
        self.providers = PROVIDERS if providers is None else providers
        self.client_factory = client_factory
        self._clients = None
        self._lock = Lock()

    def available(self):
        return any(p.get("key") for p in self.providers)

    def provider_status(self):
        # Only public metadata, never keys or exception strings from remote APIs.
        return [{"name": p["name"], "model": p["model"], "configured": bool(p.get("key"))}
                for p in self.providers]

    def _init(self):
        with self._lock:
            if self._clients is None:
                clients = [(p, self.client_factory(api_key=p["key"], base_url=p["base_url"],
                                                  timeout=90, max_retries=1))
                           for p in self.providers if p.get("key")]
                if not clients:
                    raise MissingProviderError()
                self._clients = clients
            return self._clients

    def chat(self, messages, temperature=0.3):
        for provider, client in self._init():
            try:
                response = client.chat.completions.create(
                    model=provider["model"], messages=messages, temperature=temperature)
                content = response.choices[0].message.content
                if not content or not content.strip():
                    raise ValueError("empty response")
                return content
            except Exception:
                logger.warning("Provider %s chat failed; trying fallback", provider["name"])
        raise ProviderError("模型服务调用失败，请检查凭证、网络访问和模型配额后重试。")

    def embed(self, texts, model="embedding-3"):
        try:
            clients = self._init()
        except MissingProviderError:
            return None
        for provider, client in clients:
            if provider["name"] == "glm":
                try:
                    result = client.embeddings.create(model=model, input=texts)
                    return [item.embedding for item in sorted(result.data, key=lambda d: d.index)]
                except Exception:
                    logger.info("Embedding unavailable; using BM25 retrieval")
                    return None
        return None


_default_client = LLMClient()


def chat(messages, temperature=0.3):
    return _default_client.chat(messages, temperature)


def embed(texts, model="embedding-3"):
    return _default_client.embed(texts, model)


def parse_json(text):
    if not isinstance(text, str):
        return None
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        result = json.loads(text[start:end + 1])
        return result if isinstance(result, dict) else None
    except (ValueError, TypeError):
        return None
