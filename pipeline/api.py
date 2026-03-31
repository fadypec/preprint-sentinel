"""FastAPI sidecar for dashboard ↔ pipeline control.

Thin HTTP wrapper around PipelineScheduler. All endpoints require
Bearer token auth via PIPELINE_API_SECRET.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field


def _make_auth_checker(api_secret: str):
    """Return a dependency that validates the Bearer token."""

    async def check_auth(authorization: Annotated[str | None, Header()] = None):
        if not authorization or authorization != f"Bearer {api_secret}":
            raise HTTPException(status_code=401, detail="Invalid or missing API secret")

    return check_auth


class ScheduleUpdate(BaseModel):
    hour: int = Field(ge=0, le=23)
    minute: int = Field(default=0, ge=0, le=59)


def create_app(scheduler, api_secret: str) -> FastAPI:
    """Create the FastAPI app wrapping a PipelineScheduler instance."""
    app = FastAPI(title="DURC Pipeline Control", docs_url=None, redoc_url=None)
    auth = _make_auth_checker(api_secret)

    @app.get("/status", dependencies=[Depends(auth)])
    async def status():
        return scheduler.get_status()

    @app.post("/run", dependencies=[Depends(auth)])
    async def run():
        stats = await scheduler.trigger_run()
        return {
            "papers_ingested": stats.papers_ingested,
            "papers_adjudicated": stats.papers_adjudicated,
            "errors": stats.errors,
        }

    @app.post("/pause", dependencies=[Depends(auth)])
    async def pause():
        await scheduler.pause()
        return {"status": "paused"}

    @app.post("/resume", dependencies=[Depends(auth)])
    async def resume():
        await scheduler.resume()
        return {"status": "resumed"}

    @app.put("/schedule", dependencies=[Depends(auth)])
    async def update_schedule(body: ScheduleUpdate):
        await scheduler.update_schedule(body.hour, body.minute)
        return {"hour": body.hour, "minute": body.minute}

    return app
