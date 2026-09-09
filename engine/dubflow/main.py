from __future__ import annotations

import asyncio
import logging

import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .asr import describe_backend
from .config import settings
from .downloads import downloads_snapshot, start_ffmpeg_download, start_model_download
from .jobs import JobManager
from .schemas import JobCreate

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="DubFlow Engine", version=__version__)

# GUI dev (vite :5173) and Tauri webview origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "tauri://localhost",
        "http://tauri.localhost",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

manager = JobManager()


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "version": __version__,
        "backend": describe_backend(),
        "data_dir": str(settings.data_dir),
    }


@app.post("/jobs")
async def create_job(req: JobCreate) -> dict:
    from pathlib import Path
    if not Path(req.video_path).is_file():
        raise HTTPException(status_code=400, detail=f"video not found: {req.video_path}")
    if not req.translation.enabled and req.export.variant != "source":
        raise HTTPException(status_code=400, detail="该字幕类型需要开启翻译")
    job = manager.create(req)
    manager.start(job)
    return job.out()


@app.get("/jobs")
async def list_jobs() -> dict:
    return {"jobs": manager.list()}


@app.get("/jobs/{job_id}")
async def get_job(job_id: str) -> dict:
    job = manager.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return job.out()


@app.get("/jobs/{job_id}/transcript")
async def get_transcript(job_id: str) -> dict:
    job = manager.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    if not job.transcript:
        raise HTTPException(status_code=409, detail="transcript not ready")
    return job.transcript.to_dict()


@app.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str) -> dict:
    job = manager.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    manager.request_cancel(job)
    return {"ok": True}


@app.get("/downloads")
async def downloads() -> dict:
    return downloads_snapshot()


@app.post("/downloads/models/{key}")
async def download_model(key: str) -> dict:
    try:
        return start_model_download(key)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/downloads/ffmpeg")
async def download_ffmpeg() -> dict:
    return start_ffmpeg_download()


@app.websocket("/ws/jobs/{job_id}")
async def job_events(ws: WebSocket, job_id: str) -> None:
    job = manager.get(job_id)
    if not job:
        await ws.close(code=4404)
        return
    await ws.accept()
    q = manager.hub.subscribe(job_id)
    try:
        await ws.send_json({"type": "snapshot", "job": job.out()})
        while True:
            try:
                event = await asyncio.wait_for(q.get(), timeout=15.0)
                await ws.send_json(event)
            except asyncio.TimeoutError:
                await ws.send_json({"type": "ping"})
    except WebSocketDisconnect:
        pass
    finally:
        manager.hub.unsubscribe(job_id, q)


def main() -> None:
    uvicorn.run("dubflow.main:app", host=settings.host, port=settings.port,
                log_level="info")


if __name__ == "__main__":
    main()
