"""FastAPI application factory and transport adapters."""
import json
import logging

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from config import BASE_DIR, settings as default_settings
from tools.literature import search_local
from tools.molecules import load_candidates
from . import __version__
from .images import molecule_png
from .reports import ReportStore
from .service import AnalysisService

logger = logging.getLogger(__name__)


def create_app(settings=None, service=None):
    settings = settings or default_settings
    reports = service.reports if service else ReportStore(settings.reports_dir)
    service = service or AnalysisService(reports)
    app = FastAPI(title="DrugAgent", version=__version__)
    app.state.analysis = service
    app.state.reports = reports
    app.mount("/static", StaticFiles(directory=BASE_DIR / "web"), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(BASE_DIR / "web" / "index.html", media_type="text/html")

    @app.get("/marked.min.js", include_in_schema=False)
    def marked_js():
        return FileResponse(BASE_DIR / "web" / "marked.min.js", media_type="application/javascript")

    @app.get("/api/health")
    def health():
        return {"status": "ok", "version": __version__,
                "analysis_configured": service.client.available(),
                "providers": service.client.provider_status(),
                "capabilities": {"local_search": True, "molecule_drawing": True},
                "note": "配置状态不代表远程服务连通性。"}

    @app.get("/api/candidates")
    def candidates():
        return {"candidates": load_candidates(), "scope": "内置 EGFR 演示候选集"}

    @app.get("/api/search")
    def local_search(query: str = Query(min_length=1, max_length=200),
                     top: int = Query(default=4, ge=1, le=20)):
        if not query.strip():
            raise HTTPException(422, "检索词不能为空")
        return {"results": search_local(query.strip(), top=top)}

    @app.get("/api/molimg")
    def molimg(name: str | None = Query(default=None, max_length=200),
               smiles: str | None = Query(default=None, max_length=4000)):
        name = name.strip() if name else None
        smiles = smiles.strip() if smiles else None
        if not name and not smiles:
            return Response(json.dumps({"error": "需要 name 或 smiles 参数"}),
                            status_code=400, media_type="application/json")
        try:
            data = molecule_png(name=None if smiles else name.lower(), smiles=smiles)
            return Response(data, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})
        except ValueError:
            raise HTTPException(404, "SMILES 解析失败") from None
        except Exception:
            logger.warning("Molecule image source unavailable")
            raise HTTPException(502, "分子数据获取失败，请检查 PubChem 访问或直接提供 SMILES。") from None

    @app.get("/api/run")
    def run(topic: str = Query(default="EGFR 抑制剂", min_length=1, max_length=200)):
        if not topic.strip():
            raise HTTPException(422, "研究主题不能为空")

        def stream():
            for event in service.events(topic):
                yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/api/reports")
    def list_reports():
        return {"reports": reports.list()}

    @app.get("/api/reports/{name}")
    def download_report(name: str):
        try:
            path = reports.resolve(name)
        except FileNotFoundError:
            raise HTTPException(404, "报告不存在") from None
        return FileResponse(path, media_type="text/markdown; charset=utf-8", filename=path.name)

    return app
