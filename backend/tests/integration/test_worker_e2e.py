"""
Integration end-to-end do worker: insere ClipJobs reais (button/camera), planta
segmentos sintéticos, roda claim_next + run_job, valida MP4s nos subdiretórios
corretos e estados no banco.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlmodel import Session, select


pytestmark = pytest.mark.integration


def test_worker_processes_two_camera_jobs_into_subdirs(tmp_path, engine, make_segment):
    from app.models import ClipJob, ClipJobSource, ClipJobStatus
    from app.worker_main import claim_next, run_job

    t0 = datetime(2026, 5, 8, 12, 0, 0, tzinfo=timezone.utc)
    end = t0 + timedelta(seconds=25)
    start = t0 + timedelta(seconds=5)

    # Planta segmentos para cam1 e cam2
    for cam in ("cam1", "cam2"):
        seg_dir = tmp_path / "segments" / cam
        make_segment(seg_dir, t0, duration_s=10)
        make_segment(seg_dir, t0 + timedelta(seconds=10), duration_s=10)
        make_segment(seg_dir, t0 + timedelta(seconds=20), duration_s=10)

    # Insere 2 jobs (como faria o hook do botão 1)
    with Session(engine) as s:
        for cam in ("cam1", "cam2"):
            s.add(ClipJob(
                start_utc=start,
                end_utc=end,
                source=ClipJobSource.replay_trigger,
                triggered_at_utc=end,
                button_id="1",
                camera_id=cam,
            ))
        s.commit()

    # Drena fila
    processed = 0
    while True:
        with Session(engine) as s:
            job = claim_next(s)
        if job is None:
            break
        with Session(engine) as s:
            j = s.get(ClipJob, job.id)
            run_job(s, j)
        processed += 1

    assert processed == 2

    # Valida MP4s nos subdiretórios certos
    for cam in ("cam1", "cam2"):
        out_dir = tmp_path / "clips" / "btn1" / cam
        files = list(out_dir.glob("clip_*.mp4"))
        assert len(files) == 1, f"esperava 1 MP4 em {out_dir}, achei {files}"
        assert files[0].stat().st_size > 0

    # Banco: ambos done com output_relpath coerente
    with Session(engine) as s:
        rows = s.exec(select(ClipJob).order_by(ClipJob.id)).all()
        assert all(r.status == ClipJobStatus.done for r in rows)
        for r in rows:
            assert r.output_relpath == f"clips/btn1/{r.camera_id}/clip_{r.id}.mp4"
            assert r.error_text is None
