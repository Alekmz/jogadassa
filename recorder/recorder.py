"""
Gravador contínuo RTSP → segmentos em disco + health + retenção.
"""
from __future__ import annotations

import json
import logging
import os
import re
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S%z",
)
log = logging.getLogger("recorder")

SEGMENT_PATTERN = re.compile(r"segment_(\d{8})_(\d{6})_part\d+\.mkv$")


def env_int(name: str, default: int) -> int:
    v = os.environ.get(name)
    return int(v) if v else default


def env_float(name: str, default: float) -> float:
    v = os.environ.get(name)
    return float(v) if v else default


def parse_segment_start(path: Path) -> datetime | None:
    m = SEGMENT_PATTERN.search(path.name)
    if not m:
        return None
    d, t = m.group(1), m.group(2)
    try:
        return datetime.strptime(d + t, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def retention_sweep(segments_dir: Path, retention_days: int) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    removed = 0
    for p in segments_dir.glob("segment_*.mkv"):
        st = parse_segment_start(p)
        if st and st < cutoff:
            try:
                p.unlink()
                removed += 1
            except OSError as e:
                log.warning("Não removi %s: %s", p, e)
    if removed:
        log.info("Retenção: removidos %s segmentos antigos", removed)


def health_write(health_path: Path, payload: dict) -> None:
    health_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = health_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(health_path)


def newest_segment(segments_dir: Path) -> Path | None:
    files = list(segments_dir.glob("segment_*.mkv"))
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)


def run_ffmpeg_loop(
    rtsp_url: str,
    segments_dir: Path,
    segment_seconds: int,
    health_path: Path,
) -> None:
    segments_dir.mkdir(parents=True, exist_ok=True)
    pattern = str(segments_dir / "segment_%Y%m%d_%H%M%S_part%03d.mkv")
    # strftime no nome + segment_time fixo
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "warning",
        "-rtsp_transport",
        "tcp",
        "-i",
        rtsp_url,
        "-map",
        "0",
        "-c",
        "copy",
        "-f",
        "segment",
        "-segment_time",
        str(segment_seconds),
        "-reset_timestamps",
        "1",
        "-strftime",
        "1",
        pattern,
    ]
    stop = threading.Event()

    def on_sig(*_args):
        stop.set()

    signal.signal(signal.SIGINT, on_sig)
    signal.signal(signal.SIGTERM, on_sig)

    while not stop.is_set():
        log.info("Iniciando ffmpeg: %s", " ".join(cmd[:6]) + " ...")
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        while proc.poll() is None and not stop.is_set():
            time.sleep(5)
            latest = newest_segment(segments_dir)
            health_write(
                health_path,
                {
                    "status": "recording",
                    "ffmpeg_pid": proc.pid,
                    "last_check_utc": datetime.now(timezone.utc).isoformat(),
                    "latest_segment": str(latest) if latest else None,
                    "segment_seconds": segment_seconds,
                },
            )
        if stop.is_set():
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
            break
        code = proc.wait()
        log.error(
            "ffmpeg encerrou com código %s. Reconectando em 5s…",
            code,
        )
        health_write(
            health_path,
            {
                "status": "reconnecting",
                "last_exit_code": code,
                "last_check_utc": datetime.now(timezone.utc).isoformat(),
            },
        )
        time.sleep(5)


def main() -> None:
    rtsp = os.environ.get("RTSP_URL")
    if not rtsp:
        log.error("RTSP_URL não definido")
        sys.exit(1)
    data = Path(os.environ.get("DATA_DIR", "/data"))
    segments = data / "segments"
    health_path = data / "health.json"
    segment_seconds = env_int("SEGMENT_SECONDS", 300)
    retention_days = env_int("RETENTION_DAYS", 14)
    retention_interval_h = env_float("RETENTION_INTERVAL_HOURS", 1.0)

    def retention_loop():
        while True:
            time.sleep(retention_interval_h * 3600)
            try:
                retention_sweep(segments, retention_days)
            except Exception:
                log.exception("Erro na retenção")

    threading.Thread(target=retention_loop, daemon=True).start()
    run_ffmpeg_loop(rtsp, segments, segment_seconds, health_path)


if __name__ == "__main__":
    main()
