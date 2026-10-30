"""Portable application configuration. Environment variables override a local .env."""
from dataclasses import dataclass
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = Path(os.environ.get("DRUGAGENT_ENV_FILE", BASE_DIR / ".env"))


def _load_env(path=ENV_PATH):
    values = {}
    try:
        with open(path, encoding="utf-8") as source:
            for line in source:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.removeprefix("export ").split("=", 1)
                values[key.strip()] = value.strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return values


_ENV = {**_load_env(), **os.environ}


@dataclass(frozen=True)
class Settings:
    host: str = "127.0.0.1"
    port: int = 8077
    reports_dir: Path = BASE_DIR / "reports"
    cache_dir: Path = BASE_DIR / "data"

    @classmethod
    def from_env(cls):
        reports = Path(_ENV.get("DRUGAGENT_REPORTS_DIR", str(BASE_DIR / "reports")))
        if not reports.is_absolute():
            reports = BASE_DIR / reports
        cache = Path(_ENV.get("DRUGAGENT_CACHE_DIR", str(BASE_DIR / "data")))
        if not cache.is_absolute():
            cache = BASE_DIR / cache
        port = int(_ENV.get("DRUGAGENT_PORT", "8077"))
        if not 1 <= port <= 65535:
            raise ValueError("DRUGAGENT_PORT 必须介于 1 与 65535 之间")
        return cls(_ENV.get("DRUGAGENT_HOST", "127.0.0.1"), port, reports, cache)


PROVIDERS = [
    {"name": "glm", "base_url": "https://open.bigmodel.cn/api/paas/v4",
     "model": _ENV.get("DRUGAGENT_MODEL", "glm-4-flash"), "key": _ENV.get("GLM_API_KEY", "")},
    {"name": "deepseek", "base_url": "https://api.deepseek.com",
     "model": "deepseek-chat", "key": _ENV.get("DEEPSEEK_API_KEY", "")},
]
settings = Settings.from_env()
