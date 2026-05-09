"""
Garante que _sqlite_migrate_clipjob adiciona as colunas novas (button_id, camera_id,
source, triggered_at_utc) numa tabela clipjob legada e é idempotente.
"""
import importlib

import pytest
from sqlalchemy import create_engine, text


pytestmark = pytest.mark.unit


def _legacy_columns(conn):
    return {row[1] for row in conn.execute(text("PRAGMA table_info(clipjob)")).fetchall()}


def test_migration_adds_new_columns_idempotent(tmp_path, monkeypatch):
    db_path = tmp_path / "legacy.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

    # Reimporta app.db para que ele leia a env nova e crie engine apontando pro arquivo
    import app.db as appdb
    importlib.reload(appdb)

    legacy_engine = create_engine(f"sqlite:///{db_path}")
    with legacy_engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE clipjob ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "start_utc TIMESTAMP NOT NULL, "
                "end_utc TIMESTAMP NOT NULL, "
                "status VARCHAR(16) NOT NULL DEFAULT 'queued', "
                "output_relpath VARCHAR(255), "
                "error_text TEXT, "
                "created_at TIMESTAMP, "
                "updated_at TIMESTAMP"
                ")"
            )
        )
        before = _legacy_columns(conn)
        assert "button_id" not in before
        assert "camera_id" not in before
        assert "source" not in before
        assert "triggered_at_utc" not in before

    appdb._sqlite_migrate_clipjob()

    with legacy_engine.begin() as conn:
        after = _legacy_columns(conn)
        assert "button_id" in after
        assert "camera_id" in after
        assert "source" in after
        assert "triggered_at_utc" in after

    # Idempotência: rodar de novo não deve falhar
    appdb._sqlite_migrate_clipjob()
    with legacy_engine.begin() as conn:
        again = _legacy_columns(conn)
        assert again == after
