from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .asr import select_provider
from .asr.base import Transcript
from .config import settings
from .ffmpeg_tools import extract_audio, probe
from .schemas import JobCreate
from .subtitles import to_srt
from .translator import LLMTranslator

log = logging.getLogger(__name__)

STEPS = ["probe", "extract_audio", "asr", "translate", "export"]


@dataclass
class Step:
    status: str = "pending"   # pending | running | done | failed | skipped
    progress: float = 0.0
    detail: str = ""


@dataclass
class Job:
    id: str
    video_path: str
    source_language: Optional[str]
    target_language: str
    asr_options: Dict[str, Any]
    translation_options: Dict[str, Any]
    status: str = "queued"    # queued | running | done | failed | cancelled
    steps: Dict[str, Step] = field(default_factory=lambda: {s: Step() for s in STEPS})
    error: Optional[str] = None
    artifacts: Dict[str, str] = field(default_factory=dict)
    backend: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    transcript: Optional[Transcript] = None
    cancel_requested: bool = False

    def out(self) -> dict:
        return {
            "id": self.id,
            "status": self.status,
            "video_path": self.video_path,
            "source_language": self.source_language,
            "target_language": self.target_language,
            "steps": {k: {"status": v.status, "progress": v.progress, "detail": v.detail}
                      for k, v in self.steps.items()},
            "error": self.error,
            "artifacts": self.artifacts,
            "backend": self.backend,
            "created_at": self.created_at,
        }


class EventHub:
    """Fans out job events to websocket subscribers."""

    def __init__(self) -> None:
        self._subs: Dict[str, Set[asyncio.Queue]] = {}

    def subscribe(self, job_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subs.setdefault(job_id, set()).add(q)
        return q

    def unsubscribe(self, job_id: str, q: asyncio.Queue) -> None:
        self._subs.get(job_id, set()).discard(q)

    def publish(self, job_id: str, event: dict) -> None:
        for q in list(self._subs.get(job_id, ())):
            try:
                q.put_nowait(event)
            except Exception:
                pass


class JobManager:
    def __init__(self) -> None:
        self._jobs: Dict[str, Job] = {}
        self.hub = EventHub()
        self.tasks: Dict[str, asyncio.Task] = {}

    # ---------- public API ----------

    def create(self, req: JobCreate) -> Job:
        job = Job(
            id=uuid.uuid4().hex[:12],
            video_path=req.video_path,
            source_language=req.source_language,
            target_language=req.target_language,
            asr_options=req.asr.model_dump(),
            translation_options=req.translation.model_dump(),
        )
        self._jobs[job.id] = job
        job_dir = self.job_dir(job.id)
        job_dir.mkdir(parents=True, exist_ok=True)
        return job

    def start(self, job: Job) -> None:
        self.tasks[job.id] = asyncio.get_running_loop().create_task(self._run(job))

    def get(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def list(self) -> List[dict]:
        return [j.out() for j in sorted(self._jobs.values(), key=lambda j: -j.created_at)]

    def request_cancel(self, job: Job) -> None:
        job.cancel_requested = True

    def job_dir(self, job_id: str) -> Path:
        return settings.data_dir / "jobs" / job_id

    # ---------- pipeline ----------

    def _snap(self, job: Job, event_type: str = "progress") -> dict:
        return {"type": event_type, "job": job.out()}

    def _pub_threadsafe(self, loop: asyncio.AbstractEventLoop, job: Job) -> None:
        try:
            loop.call_soon_threadsafe(self.hub.publish, job.id, self._snap(job))
        except RuntimeError:
            pass

    def _persist(self, job: Job) -> None:
        state = job.out()
        state["transcript"] = job.transcript.to_dict() if job.transcript else None
        path = self.job_dir(job.id) / "job.json"
        path.write_text(json.dumps(state, ensure_ascii=False, indent=2))

    async def _set_step(self, job: Job, loop, name: str, status: Optional[str] = None,
                        progress: Optional[float] = None, detail: Optional[str] = None) -> None:
        step = job.steps[name]
        if status:
            step.status = status
        if progress is not None:
            step.progress = progress
        if detail is not None:
            step.detail = detail
        self.hub.publish(job.id, self._snap(job))
        self._persist(job)

    def _check_cancel(self, job: Job) -> None:
        if job.cancel_requested:
            raise asyncio.CancelledError

    async def _run(self, job: Job) -> None:
        loop = asyncio.get_running_loop()
        job.status = "running"
        self.hub.publish(job.id, self._snap(job))
        job_dir = self.job_dir(job.id)
        wav_path = job_dir / "audio.wav"

        try:
            # 1. probe
            await self._set_step(job, loop, "probe", "running")
            self._check_cancel(job)
            info = await probe(job.video_path)
            fmt = info.get("format", {})
            await self._set_step(job, loop, "probe", "done",
                                 detail=f"{float(fmt.get('duration', 0)):.1f}s")

            # 2. extract audio
            await self._set_step(job, loop, "extract_audio", "running")
            self._check_cancel(job)
            await extract_audio(job.video_path, str(wav_path))
            await self._set_step(job, loop, "extract_audio", "done",
                                 detail=wav_path.name)

            # 3. ASR (GPU when available; runs in worker thread)
            await self._set_step(job, loop, "asr", "running", 0.02)
            provider = select_provider(job.asr_options.get("model"))
            job.backend = provider.info.to_dict()
            self._persist(job)
            self.hub.publish(job.id, self._snap(job))

            def asr_progress(p: float, detail: str) -> None:
                job.steps["asr"].progress = p
                job.steps["asr"].detail = detail
                self._pub_threadsafe(loop, job)

            self._check_cancel(job)
            transcript = await asyncio.to_thread(
                provider.transcribe, str(wav_path),
                job.source_language, job.asr_options.get("model"), asr_progress,
            )
            job.transcript = transcript
            tpath = job_dir / "transcript.json"
            tpath.write_text(json.dumps(transcript.to_dict(), ensure_ascii=False, indent=2))
            job.artifacts["transcript"] = str(tpath)
            await self._set_step(job, loop, "asr", "done",
                                 detail=f"{len(transcript.segments)} segments "
                                        f"[{provider.info.name}/{provider.info.device}]")

            # 4. translate (optional)
            texts: Optional[List[str]] = None
            t_opts = job.translation_options
            if t_opts.get("enabled"):
                await self._set_step(job, loop, "translate", "running")
                self._check_cancel(job)
                translator = LLMTranslator(
                    base_url=t_opts.get("base_url") or settings.translate_base_url,
                    api_key=t_opts.get("api_key") or settings.translate_api_key,
                    model=t_opts.get("model") or settings.translate_model,
                    target_lang=job.target_language,
                    source_lang=job.source_language,
                )

                def tr_progress(p: float, detail: str) -> None:
                    job.steps["translate"].progress = p
                    job.steps["translate"].detail = detail
                    self._pub_threadsafe(loop, job)

                texts = await asyncio.to_thread(translator.translate_transcript, transcript, tr_progress)
                await self._set_step(job, loop, "translate", "done")
            else:
                await self._set_step(job, loop, "translate", "skipped")

            # 5. export subtitles
            await self._set_step(job, loop, "export", "running")
            self._check_cancel(job)
            src_srt = job_dir / "source.srt"
            src_srt.write_text(to_srt(transcript.segments), encoding="utf-8")
            job.artifacts["source_srt"] = str(src_srt)
            if texts is not None:
                dst_srt = job_dir / f"{job.target_language}.srt"
                dst_srt.write_text(_srt_target(transcript, texts), encoding="utf-8")
                bi_srt = job_dir / "bilingual.srt"
                bi_srt.write_text(to_srt(transcript.segments, second_lines=texts), encoding="utf-8")
                job.artifacts["target_srt"] = str(dst_srt)
                job.artifacts["bilingual_srt"] = str(bi_srt)
            await self._set_step(job, loop, "export", "done")

            job.status = "done"
            self.hub.publish(job.id, self._snap(job, "done"))
            self._persist(job)

        except asyncio.CancelledError:
            job.status = "cancelled"
            self.hub.publish(job.id, self._snap(job))
            self._persist(job)
        except Exception as e:  # noqa: BLE001
            log.exception("job %s failed", job.id)
            job.status = "failed"
            job.error = f"{type(e).__name__}: {e}"
            self.hub.publish(job.id, self._snap(job, "failed"))
            self._persist(job)


def _srt_target(transcript: Transcript, texts: List[str]) -> str:
    """SRT containing only translated text (same timing)."""
    from .asr.base import Segment
    from .subtitles import to_srt
    segs = [Segment(start=s.start, end=s.end, text=t)
            for s, t in zip(transcript.segments, texts)]
    return to_srt(segs)
