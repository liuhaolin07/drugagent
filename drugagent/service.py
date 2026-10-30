"""Analysis lifecycle independent of HTTP transport and terminal rendering."""
import logging
from time import monotonic
from uuid import uuid4

from agents import Team
from llm import MissingProviderError, ProviderError, _default_client
from tools.molecules import load_candidates
from .errors import DataSourceError
from .reports import STAGES

logger = logging.getLogger(__name__)


class AnalysisService:
    def __init__(self, reports, team_factory=None, candidates_loader=load_candidates, client=None):
        self.reports = reports
        self.client = client or _default_client
        self.team_factory = team_factory or (lambda: Team(chat_fn=self.client.chat))
        self.candidates_loader = candidates_loader

    def events(self, topic):
        started = monotonic()
        run_id = uuid4().hex
        try:
            topic = topic.strip()
            if not topic or len(topic) > 200:
                raise ValueError("研究主题不能为空，且不能超过 200 个字符。")
            if not self.client.available():
                raise MissingProviderError()
            candidates = self.candidates_loader()
            if not candidates:
                raise ValueError("候选分子列表为空，请检查候选数据。")
            yield {"type": "start", "run_id": run_id, "topic": topic,
                   "candidates": [c["name"] for c in candidates]}
            collected = {}
            keys = [key for key, _ in STAGES]
            yield {"type": "progress", "stage": keys[0], "status": "running"}
            team = self.team_factory()
            for index, (kind, payload) in enumerate(team.analyze_iter(topic, candidates)):
                if index >= len(keys) or kind != keys[index]:
                    raise RuntimeError("Invalid analysis stage sequence")
                collected[kind] = payload
                public = {key: payload[key] for key in
                          ("text", "table_md", "refs", "analogs", "molecules", "parent", "stats", "warnings")
                          if key in payload}
                yield {"type": "stage", "stage": kind, "status": "done", **public}
                if index + 1 < len(keys):
                    yield {"type": "progress", "stage": keys[index + 1], "status": "running"}
            if list(collected) != keys:
                raise RuntimeError("Analysis did not complete all required stages")
            name = self.reports.save(topic, collected)
            yield {"type": "done", "run_id": run_id, "elapsed": round(monotonic() - started, 1),
                   "report_path": name, "report_url": f"/api/reports/{name}"}
        except MissingProviderError as error:
            yield {"type": "error", "code": "missing_provider", "message": str(error)}
        except ProviderError as error:
            yield {"type": "error", "code": "provider_unavailable", "message": str(error)}
        except DataSourceError as error:
            yield {"type": "error", "code": "data_source_unavailable", "message": str(error)}
        except ValueError as error:
            yield {"type": "error", "code": "invalid_input", "message": str(error)}
        except Exception:
            logger.exception("Analysis failed (run %s)", run_id)
            yield {"type": "error", "code": "analysis_failed",
                   "message": "分析未能完成，请重试；详细原因已记录在服务日志中。"}
