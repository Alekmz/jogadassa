import pytest
from sqlmodel import Session, select


pytestmark = pytest.mark.unit


def test_missing_secret_returns_401(client):
    r = client.post("/hooks/replay-trigger/1")
    assert r.status_code == 401


def test_wrong_secret_returns_401(client):
    r = client.post("/hooks/replay-trigger/1", headers={"X-Replay-Secret": "errado"})
    assert r.status_code == 401


def test_unknown_button_returns_404(client):
    r = client.post("/hooks/replay-trigger/9", headers={"X-Replay-Secret": "test-secret"})
    assert r.status_code == 404


def test_button1_creates_two_jobs_for_cam1_cam2(client, engine):
    from app.models import ClipJob, ClipJobSource, ClipJobStatus

    r = client.post("/hooks/replay-trigger/1", headers={"X-Replay-Secret": "test-secret"})
    assert r.status_code == 200
    body = r.json()
    assert body["button_id"] == "1"
    assert len(body["jobs"]) == 2
    cams_in_response = sorted(j["camera_id"] for j in body["jobs"])
    assert cams_in_response == ["cam1", "cam2"]

    with Session(engine) as s:
        rows = s.exec(select(ClipJob).order_by(ClipJob.id)).all()
        assert len(rows) == 2
        assert {r.camera_id for r in rows} == {"cam1", "cam2"}
        assert all(r.button_id == "1" for r in rows)
        assert all(r.source == ClipJobSource.replay_trigger for r in rows)
        assert all(r.status == ClipJobStatus.queued for r in rows)
        # Mesma janela de tempo nos 2 jobs
        assert rows[0].start_utc == rows[1].start_utc
        assert rows[0].end_utc == rows[1].end_utc
        assert rows[0].triggered_at_utc == rows[1].triggered_at_utc


def test_button2_creates_two_jobs_for_cam3_cam4(client, engine):
    from app.models import ClipJob

    r = client.post("/hooks/replay-trigger/2", headers={"X-Replay-Secret": "test-secret"})
    assert r.status_code == 200
    cams_in_response = sorted(j["camera_id"] for j in r.json()["jobs"])
    assert cams_in_response == ["cam3", "cam4"]

    with Session(engine) as s:
        rows = s.exec(select(ClipJob)).all()
        assert {r.camera_id for r in rows} == {"cam3", "cam4"}
        assert all(r.button_id == "2" for r in rows)


def test_trigger_window_seconds_applied(client, engine):
    from app.models import ClipJob

    r = client.post("/hooks/replay-trigger/1", headers={"X-Replay-Secret": "test-secret"})
    assert r.status_code == 200
    with Session(engine) as s:
        job = s.exec(select(ClipJob)).first()
        delta = (job.end_utc - job.start_utc).total_seconds()
        assert 29 <= delta <= 31  # padrão do .env do conftest = 30
