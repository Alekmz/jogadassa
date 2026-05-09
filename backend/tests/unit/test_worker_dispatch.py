"""
Valida que worker.run_job dispara export_clip_mp4 com os diretórios corretos
(camera/button) e que o fallback legacy funciona quando os campos são None.
O ffmpeg real NÃO é chamado aqui — export_clip_mp4 está mockado.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest


pytestmark = pytest.mark.unit


def _make_job(session, button_id, camera_id):
    from app.models import ClipJob, ClipJobSource

    end = datetime.now(timezone.utc)
    start = end - timedelta(seconds=30)
    job = ClipJob(
        start_utc=start,
        end_utc=end,
        source=ClipJobSource.replay_trigger,
        triggered_at_utc=end,
        button_id=button_id,
        camera_id=camera_id,
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def test_run_job_uses_camera_subdir_for_buttoned_job(session, tmp_path):
    from app.models import ClipJobStatus
    from app.worker_main import run_job

    job = _make_job(session, "1", "cam1")
    expected_segments = Path(str(tmp_path)) / "segments" / "cam1"
    expected_clips = Path(str(tmp_path)) / "clips" / "btn1" / "cam1"

    with patch("app.worker_main.export_clip_mp4") as mock_export:
        mock_export.return_value = expected_clips / f"clip_{job.id}.mp4"
        run_job(session, job)

    mock_export.assert_called_once()
    call_args = mock_export.call_args
    # signature: (segments_dir, clips_dir, start_utc, end_utc, name)
    assert call_args.args[0] == expected_segments
    assert call_args.args[1] == expected_clips
    assert call_args.args[4] == f"clip_{job.id}.mp4"

    session.refresh(job)
    assert job.status == ClipJobStatus.done
    assert job.output_relpath == f"clips/btn1/cam1/clip_{job.id}.mp4"
    assert job.error_text is None


def test_run_job_legacy_fallback_when_no_camera_id(session, tmp_path):
    from app.models import ClipJob, ClipJobSource, ClipJobStatus
    from app.worker_main import run_job

    job = ClipJob(
        start_utc=datetime.now(timezone.utc) - timedelta(seconds=10),
        end_utc=datetime.now(timezone.utc),
        source=ClipJobSource.admin_manual,
    )
    session.add(job)
    session.commit()
    session.refresh(job)

    expected_segments = Path(str(tmp_path)) / "segments"
    expected_clips = Path(str(tmp_path)) / "clips"

    with patch("app.worker_main.export_clip_mp4") as mock_export:
        mock_export.return_value = expected_clips / f"clip_{job.id}.mp4"
        run_job(session, job)

    call_args = mock_export.call_args
    assert call_args.args[0] == expected_segments
    assert call_args.args[1] == expected_clips

    session.refresh(job)
    assert job.status == ClipJobStatus.done
    assert job.output_relpath == f"clips/clip_{job.id}.mp4"


def test_run_job_marks_failed_on_export_error(session):
    from app.models import ClipJobStatus
    from app.worker_main import run_job

    job = _make_job(session, "1", "cam1")

    with patch("app.worker_main.export_clip_mp4", side_effect=RuntimeError("sem mídia")):
        run_job(session, job)

    session.refresh(job)
    assert job.status == ClipJobStatus.failed
    assert "sem mídia" in (job.error_text or "")
    assert job.output_relpath is None


def test_claim_next_picks_oldest_queued(session):
    from app.models import ClipJobStatus
    from app.worker_main import claim_next

    j1 = _make_job(session, "1", "cam1")
    j2 = _make_job(session, "1", "cam2")

    claimed = claim_next(session)
    assert claimed.id == j1.id
    assert claimed.status == ClipJobStatus.processing

    claimed2 = claim_next(session)
    assert claimed2.id == j2.id
