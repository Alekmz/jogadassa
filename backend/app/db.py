from collections.abc import Generator

from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from app.config import get_settings


def _connect_args(url: str) -> dict:
    if url.startswith("sqlite"):
        return {"check_same_thread": False}
    return {}


settings = get_settings()
engine = create_engine(
    settings.database_url,
    echo=False,
    connect_args=_connect_args(settings.database_url),
)


@event.listens_for(Engine, "connect")
def _sqlite_fk(dbapi_connection, connection_record):  # noqa: ARG001
    if settings.database_url.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def _sqlite_migrate_clipjob() -> None:
    """Adiciona colunas novas em clipjob sem Alembic (SQLite)."""
    if not settings.database_url.startswith("sqlite"):
        return
    with engine.begin() as conn:
        rows = conn.execute(text("PRAGMA table_info(clipjob)")).fetchall()
        col_names = {r[1] for r in rows}
        if "source" not in col_names:
            conn.execute(
                text(
                    "ALTER TABLE clipjob ADD COLUMN source VARCHAR(32) NOT NULL DEFAULT 'legacy'"
                )
            )
        if "triggered_at_utc" not in col_names:
            conn.execute(text("ALTER TABLE clipjob ADD COLUMN triggered_at_utc TIMESTAMP"))
        if "button_id" not in col_names:
            conn.execute(text("ALTER TABLE clipjob ADD COLUMN button_id VARCHAR(16)"))
        if "camera_id" not in col_names:
            conn.execute(text("ALTER TABLE clipjob ADD COLUMN camera_id VARCHAR(32)"))


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
    _sqlite_migrate_clipjob()


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
