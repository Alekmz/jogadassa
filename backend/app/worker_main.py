"""
Processa jobs de clip na fila (um worker; escalar com fila externa depois).
"""
from __future__ import annotations

import logging
import time
import traceback
from pathlib import Path

from sqlmodel import Session, select

from app.config import get_settings
from app.db import engine, init_db
from app.models import ClipJob, ClipJobStatus, Order, OrderStatus, utcnow
from app.services.clip_export import export_clip_mp4

logging.basicConfig(level=logging.INFO, format="%(asctime)s [worker] %(message)s")
log = logging.getLogger("worker")


def should_process(session: Session, job: ClipJob) -> bool:
    order = session.exec(
        select(Order).where(Order.clip_job_id == job.id)
    ).first()
    if order is None:
        return True
    return order.status == OrderStatus.paid


def claim_next(session: Session) -> ClipJob | None:
    jobs = session.exec(
        select(ClipJob)
        .where(ClipJob.status == ClipJobStatus.queued)
        .order_by(ClipJob.id.asc())
    ).all()
    for job in jobs:
        if not should_process(session, job):
            continue
        job.status = ClipJobStatus.processing
        job.updated_at = utcnow()
        session.add(job)
        session.commit()
        session.refresh(job)
        return job
    return None


def run_job(session: Session, job: ClipJob) -> None:
    s = get_settings()
    name = f"clip_{job.id}.mp4"
    if job.camera_id and job.button_id:
        segments_dir = Path(s.segments_dir) / job.camera_id
        clips_dir = Path(s.clips_dir) / f"btn{job.button_id}" / job.camera_id
        rel = f"clips/btn{job.button_id}/{job.camera_id}/{name}"
    else:
        segments_dir = Path(s.segments_dir)
        clips_dir = Path(s.clips_dir)
        rel = f"clips/{name}"
    try:
        export_clip_mp4(
            segments_dir,
            clips_dir,
            job.start_utc,
            job.end_utc,
            name,
        )
        job.status = ClipJobStatus.done
        job.output_relpath = rel
        job.error_text = None
    except Exception as e:
        job.status = ClipJobStatus.failed
        job.error_text = f"{e}\n{traceback.format_exc()}"[-8000:]
        log.exception("Falha no job %s", job.id)
    job.updated_at = utcnow()
    session.add(job)
    session.commit()


def main() -> None:
    init_db()
    log.info("Worker iniciado; DATA_DIR=%s", get_settings().data_dir)
    while True:
        try:
            with Session(engine) as session:
                job = claim_next(session)
            if job is None:
                time.sleep(2)
                continue
            log.info("Processando clip job %s", job.id)
            with Session(engine) as session:
                j = session.get(ClipJob, job.id)
                if j:
                    run_job(session, j)
        except Exception:
            log.exception("Erro no loop do worker")
            time.sleep(5)


if __name__ == "__main__":
    main()
