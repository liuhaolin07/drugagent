"""Container readiness without forwarding loopback traffic to outbound proxies."""
import json
from urllib.request import ProxyHandler, build_opener

from config import settings


def main():
    opener = build_opener(ProxyHandler({}))
    try:
        with opener.open(f"http://127.0.0.1:{settings.port}/api/health", timeout=3) as response:
            return 0 if response.status == 200 and json.load(response).get("status") == "ok" else 1
    except (OSError, ValueError):
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
