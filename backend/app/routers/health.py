import json
from pathlib import Path

from fastapi import APIRouter

from app.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    s = get_settings()
    health_path = Path(s.data_dir) / "health.json"
    recorder = {}
    if health_path.is_file():
        try:
            recorder = json.loads(health_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            recorder = {"parse_error": True}
    return {
        "status": "ok",
        "data_dir": s.data_dir,
        "recorder": recorder,
    }
