"""
Valida que ClipOut expõe button_id/camera_id e que o download serve arquivos
de subdiretórios (clips/btn{N}/{cam}/clip_{id}.mp4).
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlmodel import Session


pytestmark = pytest.mark.unit


def _seed_done_job(engine, tmp_path: Path, button_id="1", camera_id="cam1", body=b"FAKEMP4DATA"):
    from app.models import ClipJob, ClipJobSource, ClipJobStatus

    rel = f"clips/btn{button_id}/{camera_id}/clip_X.mp4"
    abs_path = tmp_path / rel
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_bytes(body)

    end = datetime.now(timezone.utc)
    start = end - timedelta(seconds=30)
    with Session(engine) as s:
        job = ClipJob(
            start_utc=start,
            end_utc=end,
            source=ClipJobSource.replay_trigger,
            triggered_at_utc=end,
            button_id=button_id,
            camera_id=camera_id,
            status=ClipJobStatus.done,
            output_relpath=rel,
        )
        s.add(job)
        s.commit()
        s.refresh(job)
        return job


def test_admin_get_returns_button_and_camera(client, engine, admin_token, tmp_path):
    job = _seed_done_job(engine, tmp_path)
    r = client.get(
        f"/clips/admin/{job.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["button_id"] == "1"
    assert data["camera_id"] == "cam1"
    assert data["output_relpath"] == "clips/btn1/cam1/clip_X.mp4"
    assert data["status"] == "done"
    assert data["download_token"]  # presente porque status=done


def test_download_serves_file_from_subdirectory(client, engine, tmp_path):
    body = b"\x00\x00\x00\x18ftypisom-fake-mp4"
    job = _seed_done_job(engine, tmp_path, button_id="2", camera_id="cam3", body=body)

    # Pega token via endpoint admin (mais realista que importar create_download_token)
    from app.security import create_download_token
    token = create_download_token(job.id)

    r = client.get(f"/clips/files/{job.id}", params={"token": token})
    assert r.status_code == 200
    assert r.content == body
    assert r.headers["content-type"] == "video/mp4"


def test_download_404_when_file_missing(client, engine, tmp_path):
    from app.models import ClipJob, ClipJobSource, ClipJobStatus

    end = datetime.now(timezone.utc)
    with Session(engine) as s:
        job = ClipJob(
            start_utc=end - timedelta(seconds=10),
            end_utc=end,
            source=ClipJobSource.replay_trigger,
            button_id="1",
            camera_id="cam1",
            status=ClipJobStatus.done,
            output_relpath="clips/btn1/cam1/inexistente.mp4",
        )
        s.add(job)
        s.commit()
        s.refresh(job)
        jid = job.id

    from app.security import create_download_token
    token = create_download_token(jid)
    r = client.get(f"/clips/files/{jid}", params={"token": token})
    assert r.status_code == 404
