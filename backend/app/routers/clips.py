from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.config import get_settings
from app.deps import DbSession, get_current_admin
from app.models import ClipJob, ClipJobSource, ClipJobStatus, Order, OrderStatus
from app.security import create_download_token, decode_download_token
from sqlmodel import select

router = APIRouter(prefix="/clips", tags=["clips"])


class ClipCreate(BaseModel):
    start_utc: datetime
    end_utc: datetime


class ClipOut(BaseModel):
    id: int
    start_utc: datetime
    end_utc: datetime
    status: str
    source: str
    triggered_at_utc: datetime | None
    button_id: str | None
    camera_id: str | None
    output_relpath: str | None
    error_text: str | None
    download_token: str | None = None


class SelectableClipOut(BaseModel):
    """Lista pública: só replays do gatilho já exportados (sem token de download)."""

    id: int
    start_utc: datetime
    end_utc: datetime
    triggered_at_utc: datetime | None


@router.get("/selectable", response_model=list[SelectableClipOut])
def list_selectable_clips(session: DbSession):
    """Replays do botão já prontos — escolha do cliente no fim da partida."""
    rows = session.exec(
        select(ClipJob)
        .where(ClipJob.source == ClipJobSource.replay_trigger)
        .where(ClipJob.status == ClipJobStatus.done)
        .order_by(ClipJob.id.desc())
        .limit(100)
    ).all()
    return [
        SelectableClipOut(
            id=r.id,
            start_utc=r.start_utc,
            end_utc=r.end_utc,
            triggered_at_utc=r.triggered_at_utc,
        )
        for r in rows
    ]


def _clip_out(job: ClipJob, include_token: bool = False) -> ClipOut:
    token = None
    if include_token and job.status == ClipJobStatus.done and job.output_relpath:
        token = create_download_token(job.id)
    return ClipOut(
        id=job.id,
        start_utc=job.start_utc,
        end_utc=job.end_utc,
        status=job.status.value,
        source=job.source.value,
        triggered_at_utc=job.triggered_at_utc,
        button_id=job.button_id,
        camera_id=job.camera_id,
        output_relpath=job.output_relpath,
        error_text=job.error_text,
        download_token=token,
    )


@router.post("/admin", response_model=ClipOut)
def create_admin_clip(
    body: ClipCreate,
    session: DbSession,
    _admin: Annotated[str, Depends(get_current_admin)],
):
    """Corte sem pedido: entra na fila e processa quando não houver bloqueio de pagamento."""
    if body.end_utc <= body.start_utc:
        raise HTTPException(400, "end_utc deve ser maior que start_utc")
    job = ClipJob(
        start_utc=body.start_utc,
        end_utc=body.end_utc,
        source=ClipJobSource.admin_manual,
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    return _clip_out(job)


@router.get("/admin", response_model=list[ClipOut])
def list_clips(
    session: DbSession,
    _admin: Annotated[str, Depends(get_current_admin)],
):
    rows = session.exec(select(ClipJob).order_by(ClipJob.id.desc()).limit(200)).all()
    return [_clip_out(r, include_token=r.status == ClipJobStatus.done) for r in rows]


@router.get("/admin/{job_id}", response_model=ClipOut)
def get_clip_admin(
    job_id: int,
    session: DbSession,
    _admin: Annotated[str, Depends(get_current_admin)],
):
    job = session.get(ClipJob, job_id)
    if not job:
        raise HTTPException(404, "Job não encontrado")
    return _clip_out(job, include_token=job.status == ClipJobStatus.done)


@router.get("/files/{job_id}")
def download_clip(job_id: int, token: str, session: DbSession):
    try:
        cid = decode_download_token(token)
    except ValueError as e:
        raise HTTPException(401, str(e))
    if cid != job_id:
        raise HTTPException(401, "Token não corresponde ao clip")
    job = session.get(ClipJob, job_id)
    if not job or job.status != ClipJobStatus.done or not job.output_relpath:
        raise HTTPException(404, "Arquivo não disponível")
    # Pedido pago, se houver pedido ligado
    order = session.exec(select(Order).where(Order.clip_job_id == job_id)).first()
    if order and order.status != OrderStatus.paid:
        raise HTTPException(402, "Pagamento pendente")
    path = Path(get_settings().data_dir) / job.output_relpath
    if not path.is_file():
        raise HTTPException(404, "Arquivo ausente no disco")
    return FileResponse(
        path,
        filename=path.name,
        media_type="video/mp4",
    )
