"""FastAPI entry — POST /audit-light, GET /healthz."""
from __future__ import annotations
import logging
import time

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl

from src.pipeline import run_audit_light
from src.render import render_html_light
from src.storage import publish_html

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s · %(message)s",
)
log = logging.getLogger("audit_light")

app = FastAPI(title="Joy Audit Light", version="0.1.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"],
    allow_methods=["POST", "GET"], allow_headers=["*"],
)


class AuditLightRequest(BaseModel):
    url: HttpUrl


class AuditLightResponse(BaseModel):
    score: int
    grade: str
    html_url: str
    duration_seconds: float
    cost_estimate_usd: float
    actions: list[dict]
    blocks: list[dict]


@app.get("/healthz")
def healthz():
    return {"ok": True, "service": "joy-audit-light"}


@app.post("/audit-light", response_model=AuditLightResponse)
async def audit_light(req: AuditLightRequest):
    t0 = time.time()
    try:
        result = await run_audit_light(str(req.url))
    except Exception as e:
        log.exception("pipeline failed")
        raise HTTPException(status_code=500, detail=str(e))

    html = render_html_light(result)
    html_url = await publish_html(html, slug=result.fiche.slug)
    duration = round(time.time() - t0, 1)

    log.info(
        f"audit done: score={result.score} grade={result.grade} "
        f"duration={duration}s cost=${result.cost_estimate_usd:.3f}"
    )

    return AuditLightResponse(
        score=result.score, grade=result.grade, html_url=html_url,
        duration_seconds=duration, cost_estimate_usd=result.cost_estimate_usd,
        actions=[a.model_dump() for a in result.actions],
        blocks=[b.model_dump() for b in result.blocks],
    )
