"""
Fixtures compartilhadas. Cada teste roda isolado em tmp_path com SQLite próprio
e settings carregadas a partir de env vars (sem .env do repo).
"""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable

import pytest

# Garante que `app.*` seja importável quando rodando direto do diretório backend/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    """Isola cada teste: tmp_path como DATA_DIR, SQLite próprio, settings determinísticas."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("REPLAY_HOOK_SECRET", "test-secret")
    monkeypatch.setenv("SECRET_KEY", "unit-test-secret")
    monkeypatch.setenv("BUTTON1_CAMERAS", "cam1,cam2")
    monkeypatch.setenv("BUTTON2_CAMERAS", "cam3,cam4")
    monkeypatch.setenv("REPLAY_TRIGGER_WINDOW_SECONDS", "30")
    # Limpa o lru_cache de get_settings para que ele leia as envs deste teste
    from app.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def engine(tmp_path):
    """Engine SQLite isolada por teste, com schema criado via metadata.create_all."""
    from sqlmodel import SQLModel, create_engine
    from app import models  # noqa: F401 — registra metadata

    eng = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(eng)
    return eng


@pytest.fixture
def session(engine):
    from sqlmodel import Session
    with Session(engine) as s:
        yield s


@pytest.fixture
def client(engine):
    """TestClient com get_db sobrescrito para usar o engine de teste."""
    from fastapi.testclient import TestClient
    from sqlmodel import Session

    from app.deps import get_db
    from app.main import app

    def _override():
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def admin_token():
    from app.security import create_access_token
    return create_access_token("admin")


@pytest.fixture
def make_segment() -> Callable[[Path, datetime, int], Path]:
    """
    Gera um segment_YYYYMMDD_HHMMSS_part001.mkv sintético usando ffmpeg testsrc.
    O nome do arquivo carrega o start UTC, conforme parser do recorder/clip_export.
    """

    def _make(segments_dir: Path, start_dt: datetime, duration_s: int = 10) -> Path:
        segments_dir.mkdir(parents=True, exist_ok=True)
        name = f"segment_{start_dt.strftime('%Y%m%d_%H%M%S')}_part001.mkv"
        out = segments_dir / name
        subprocess.run(
            [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", f"testsrc=duration={duration_s}:size=320x180:rate=10",
                "-f", "lavfi", "-i", f"sine=duration={duration_s}:frequency=300",
                "-c:v", "libx264", "-preset", "ultrafast",
                "-c:a", "aac",
                str(out),
            ],
            check=True,
            capture_output=True,
        )
        return out

    return _make
