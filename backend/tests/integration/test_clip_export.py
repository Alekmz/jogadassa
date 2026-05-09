"""
Integration: planta segmentos sintéticos via ffmpeg testsrc, roda export_clip_mp4
de verdade e valida o MP4 resultante com ffprobe.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


pytestmark = pytest.mark.integration


def _ffprobe_duration(path: Path) -> float:
    import subprocess

    r = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True, text=True, check=True,
    )
    return float(r.stdout.strip())


def test_export_clip_from_synthetic_segments(tmp_path, make_segment):
    from app.services.clip_export import export_clip_mp4

    segments_dir = tmp_path / "segments" / "cam1"
    clips_dir = tmp_path / "clips"

    t0 = datetime(2026, 5, 8, 12, 0, 0, tzinfo=timezone.utc)
    # 3 segmentos de 10s cobrindo [t0, t0+30s]
    make_segment(segments_dir, t0, duration_s=10)
    make_segment(segments_dir, t0 + timedelta(seconds=10), duration_s=10)
    make_segment(segments_dir, t0 + timedelta(seconds=20), duration_s=10)

    # Pede [t0+5, t0+25] → ~20s de clipe
    out = export_clip_mp4(
        segments_dir,
        clips_dir,
        t0 + timedelta(seconds=5),
        t0 + timedelta(seconds=25),
        "out.mp4",
    )
    assert out.exists()
    assert out.stat().st_size > 0
    duration = _ffprobe_duration(out)
    assert 18.0 <= duration <= 22.0, f"esperava ~20s, veio {duration:.2f}s"


def test_export_raises_when_no_segments_cover_window(tmp_path, make_segment):
    from app.services.clip_export import export_clip_mp4

    segments_dir = tmp_path / "segments" / "cam1"
    clips_dir = tmp_path / "clips"
    t0 = datetime(2026, 5, 8, 12, 0, 0, tzinfo=timezone.utc)
    make_segment(segments_dir, t0, duration_s=5)

    # Janela 1 hora depois — nenhum segmento cobre
    far = t0 + timedelta(hours=1)
    with pytest.raises(RuntimeError, match="Nenhum segmento"):
        export_clip_mp4(
            segments_dir,
            clips_dir,
            far,
            far + timedelta(seconds=10),
            "out.mp4",
        )


def test_export_clamps_to_segment_bounds(tmp_path, make_segment):
    """Pedir antes do início do primeiro segmento deve clampar (não estourar)."""
    from app.services.clip_export import export_clip_mp4

    segments_dir = tmp_path / "segments" / "cam1"
    clips_dir = tmp_path / "clips"
    t0 = datetime(2026, 5, 8, 12, 0, 0, tzinfo=timezone.utc)
    make_segment(segments_dir, t0, duration_s=10)

    out = export_clip_mp4(
        segments_dir,
        clips_dir,
        t0 - timedelta(seconds=20),  # bem antes
        t0 + timedelta(seconds=5),
        "clamped.mp4",
    )
    assert out.exists()
    # Como cortou no início, não pode passar de ~5s
    duration = _ffprobe_duration(out)
    assert duration <= 6.0
