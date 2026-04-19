"""
Exporta MP4 a partir de segmentos gravados e intervalo UTC [start_utc, end_utc].
"""
from __future__ import annotations

import re
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

SEGMENT_RE = re.compile(r"segment_(\d{8})_(\d{6})_part\d+\.mkv$", re.I)


def parse_segment_start(path: Path) -> datetime | None:
    m = SEGMENT_RE.search(path.name)
    if not m:
        return None
    d, t = m.group(1), m.group(2)
    try:
        return datetime.strptime(d + t, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def ffprobe_duration_seconds(path: Path) -> float:
    r = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(r.stdout.strip())


def list_segments(segments_dir: Path) -> list[tuple[Path, datetime, float]]:
    out: list[tuple[Path, datetime, float]] = []
    for p in sorted(segments_dir.glob("segment_*.mkv")):
        st = parse_segment_start(p)
        if not st:
            continue
        try:
            dur = ffprobe_duration_seconds(p)
        except (subprocess.CalledProcessError, ValueError):
            continue
        out.append((p, st, dur))
    return out


def pick_segments(
    segments: list[tuple[Path, datetime, float]],
    start_utc: datetime,
    end_utc: datetime,
) -> list[tuple[Path, datetime, float]]:
    if start_utc.tzinfo is None:
        start_utc = start_utc.replace(tzinfo=timezone.utc)
    if end_utc.tzinfo is None:
        end_utc = end_utc.replace(tzinfo=timezone.utc)
    picked: list[tuple[Path, datetime, float]] = []
    for path, st, dur in segments:
        en = st + timedelta(seconds=dur)
        if en > start_utc and st < end_utc:
            picked.append((path, st, dur))
    return picked


def export_clip_mp4(
    segments_dir: Path,
    clips_dir: Path,
    start_utc: datetime,
    end_utc: datetime,
    output_name: str,
) -> Path:
    """
    Gera arquivo MP4 em clips_dir / output_name. Levanta RuntimeError se não houver mídia.
    """
    segments_dir = segments_dir.resolve()
    clips_dir.mkdir(parents=True, exist_ok=True)
    all_seg = list_segments(segments_dir)
    picked = pick_segments(all_seg, start_utc, end_utc)
    if not picked:
        raise RuntimeError(
            "Nenhum segmento cobre o intervalo solicitado. Verifique datas e retenção."
        )

    first_start = picked[0][1]
    last_end = picked[-1][1] + timedelta(seconds=picked[-1][2])
    if start_utc < first_start:
        start_utc = first_start
    if end_utc > last_end:
        end_utc = last_end

    rel_clip_start = (start_utc - first_start).total_seconds()
    rel_clip_end = (end_utc - first_start).total_seconds()

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        merged = td_path / "merged.mkv"
        list_file = td_path / "list.txt"
        lines = []
        for path, _st, _d in picked:
            lines.append(f"file '{path.as_posix()}'")
        list_file.write_text("\n".join(lines), encoding="utf-8")

        subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(list_file),
                "-c",
                "copy",
                str(merged),
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        out_path = clips_dir / output_name
        subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-y",
                "-i",
                str(merged),
                "-ss",
                str(max(0.0, rel_clip_start)),
                "-to",
                str(max(rel_clip_start + 0.1, rel_clip_end)),
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "23",
                "-c:a",
                "aac",
                "-movflags",
                "+faststart",
                str(out_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )

    return out_path.resolve()
