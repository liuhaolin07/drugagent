# -*- coding: utf-8 -*-
"""DrugAgent Web UI（v0.3）：FastAPI + SSE 实时进度 + RDKit 分子结构图。

启动： python web.py     → http://127.0.0.1:8077
"""
import io
import json
import os
import time
from datetime import datetime

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse
from rdkit import Chem
from rdkit.Chem import Draw

from agents import Team
from tools.molecules import load_candidates, smiles_from_pubchem

BASE = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(BASE, "web")
REPORTS_DIR = os.path.join(BASE, "reports")

app = FastAPI(title="DrugAgent", version="0.3")
_mol_img_cache = {}


@app.get("/")
def index():
    with open(os.path.join(WEB_DIR, "index.html"), encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.get("/marked.min.js")
def marked_js():
    """本地化的 marked（离线可用的 Markdown 渲染，演示更稳）。"""
    return FileResponse(os.path.join(WEB_DIR, "marked.min.js"),
                        media_type="application/javascript")


@app.get("/api/molimg")
def molimg(name: str):
    """按分子名返回二维结构图 PNG（PubChem 取 SMILES + RDKit 绘制，带缓存）。"""
    key = name.strip().lower()
    if key in _mol_img_cache:
        return Response(_mol_img_cache[key], media_type="image/png")
    try:
        smi = smiles_from_pubchem(name)
        m = Chem.MolFromSmiles(smi)
        img = Draw.MolToImage(m, size=(260, 200))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        data = buf.getvalue()
        _mol_img_cache[key] = data
        return Response(data, media_type="image/png")
    except Exception as e:
        return Response(status_code=404,
                        content=json.dumps({"error": repr(e)[:150]}).encode("utf-8"),
                        media_type="application/json")


def _sse(obj):
    return "data: " + json.dumps(obj, ensure_ascii=False) + "\n\n"


@app.get("/api/run")
def run(topic: str = Query(default="EGFR 抑制剂")):
    """SSE 流：start → 各阶段 stage(done) → done / error。"""
    def gen():
        team = Team()
        cands = load_candidates()
        t0 = time.time()
        collected = {}
        try:
            yield _sse({"type": "start", "topic": topic,
                        "candidates": [c["name"] for c in cands]})
            for kind, payload in team.analyze_iter(topic, cands):
                collected[kind] = payload
                if kind in ("literature", "molecules"):
                    yield _sse({"type": "stage", "stage": kind, "status": "done",
                                "text": payload.get("text", "")})
                elif kind == "report":
                    yield _sse({"type": "stage", "stage": "report", "status": "done",
                                "text": payload.get("text", ""),
                                "refs": payload.get("refs", "")})
            # 存档
            os.makedirs(REPORTS_DIR, exist_ok=True)
            out = os.path.join(REPORTS_DIR, f"report_{datetime.now():%Y%m%d_%H%M%S}.md")
            with open(out, "w", encoding="utf-8") as f:
                f.write(f"# 候选分子分析报告（{topic}）\n\n")
                f.write("## 文献要点\n\n" + collected.get("literature", {}).get("text", "") + "\n\n")
                f.write("## 分子分析\n\n" + collected.get("molecules", {}).get("text", "") + "\n\n")
                f.write("## 综合报告\n\n" + collected.get("report", {}).get("text", "") + "\n\n"
                        + collected.get("report", {}).get("refs", "") + "\n")
            yield _sse({"type": "done", "elapsed": round(time.time() - t0, 1),
                        "report_path": os.path.basename(out)})
        except Exception as e:
            yield _sse({"type": "error", "message": repr(e)[:300]})

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache"})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8077, log_level="info")
