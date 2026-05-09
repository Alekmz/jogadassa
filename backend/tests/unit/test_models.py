from datetime import datetime, timedelta, timezone

import pytest


pytestmark = pytest.mark.unit


def test_clipjob_persists_button_and_camera(session):
    from app.models import ClipJob, ClipJobSource, ClipJobStatus

    end = datetime.now(timezone.utc)
    start = end - timedelta(seconds=30)
    job = ClipJob(
        start_utc=start,
        end_utc=end,
        source=ClipJobSource.replay_trigger,
        triggered_at_utc=end,
        button_id="1",
        camera_id="cam1",
    )
    session.add(job)
    session.commit()
    session.refresh(job)

    fetched = session.get(ClipJob, job.id)
    assert fetched is not None
    assert fetched.button_id == "1"
    assert fetched.camera_id == "cam1"
    assert fetched.status == ClipJobStatus.queued
    assert fetched.source == ClipJobSource.replay_trigger


def test_clipjob_button_camera_optional_for_legacy(session):
    from app.models import ClipJob, ClipJobSource

    job = ClipJob(
        start_utc=datetime.now(timezone.utc),
        end_utc=datetime.now(timezone.utc),
        source=ClipJobSource.admin_manual,
    )
    session.add(job)
    session.commit()
    session.refresh(job)

    assert job.button_id is None
    assert job.camera_id is None
