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


@router.post("/replay-trigger/{button_id}")
def replay_trigger(
    button_id: str,
    session: DbSession,
    x_replay_secret: str | None = Header(default=None, alias="X-Replay-Secret"),
):
    """
    Cria 1 job de corte por câmera conectada ao botão (últimos N segundos).
    Protegido por X-Replay-Secret (mesmo valor que REPLAY_HOOK_SECRET).
    """
    s = get_settings()
    if not x_replay_secret or x_replay_secret != s.replay_hook_secret:
        raise HTTPException(status_code=401, detail="Segredo inválido")
    cameras = s.button_camera_map.get(button_id)
    if not cameras:
        raise HTTPException(status_code=404, detail=f"Botão desconhecido: {button_id}")
    end = utcnow()
    start = end - timedelta(seconds=s.replay_trigger_window_seconds)
    jobs: list[ClipJob] = []
    for camera_id in cameras:
        job = ClipJob(
            start_utc=start,
            end_utc=end,
            source=ClipJobSource.replay_trigger,
            triggered_at_utc=end,
            button_id=button_id,
            camera_id=camera_id,
        )
        session.add(job)
        jobs.append(job)
    session.commit()
    for job in jobs:
        session.refresh(job)
    return {
        "button_id": button_id,
        "jobs": [
            {
                "id": j.id,
                "camera_id": j.camera_id,
                "start_utc": j.start_utc,
                "end_utc": j.end_utc,
                "status": j.status.value,
                "source": j.source.value,
            }
            for j in jobs
        ],
    }
