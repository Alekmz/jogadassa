"""
Gatilhos externos (ex.: botão Arduino na quadra).
"""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Header, HTTPException

from app.config import get_settings
from app.deps import DbSession
from app.models import ClipJob, ClipJobSource, utcnow

router = APIRouter(prefix="/hooks", tags=["hooks"])


@router.post("/replay-trigger")
def replay_trigger(
    session: DbSession,
    x_replay_secret: str | None = Header(default=None, alias="X-Replay-Secret"),
):
    """
    Cria um job de corte dos últimos N segundos (REPLAY_TRIGGER_WINDOW_SECONDS).
    Protegido por X-Replay-Secret (mesmo valor que REPLAY_HOOK_SECRET).
    """
    s = get_settings()
    if not x_replay_secret or x_replay_secret != s.replay_hook_secret:
        raise HTTPException(status_code=401, detail="Segredo inválido")
    end = utcnow()
    start = end - timedelta(seconds=s.replay_trigger_window_seconds)
    job = ClipJob(
        start_utc=start,
        end_utc=end,
        source=ClipJobSource.replay_trigger,
        triggered_at_utc=end,
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    return {
        "id": job.id,
        "start_utc": job.start_utc,
        "end_utc": job.end_utc,
        "status": job.status.value,
        "source": job.source.value,
    }
