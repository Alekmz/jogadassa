#!/usr/bin/env python3
"""
Bridge USB Serial → HTTP: lê linhas da porta serial (ex.: ESP32 com botão) e chama
POST /hooks/replay-trigger/{button_id} na API jogadassa. A identidade do botão vive na
URL configurada (cada instância do bridge aponta para o button_id correspondente — o
firmware do ESP32 é o mesmo nos dois botões).

Dependência: pip install pyserial

Variáveis de ambiente (sobrescritas por argumentos de linha de comando):
  SERIAL_PORT          — obrigatório se não passar --port (ex.: /dev/ttyUSB0, COM3)
  REPLAY_URL           — obrigatório, ex.: http://127.0.0.1:8000/hooks/replay-trigger/1
  REPLAY_HOOK_SECRET   — obrigatório (mesmo valor da API)
  SERIAL_BAUD          — default 115200
  REPLAY_SERIAL_COMMAND — texto da linha que dispara o POST (default REPLAY_CUT)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request


def _env(key: str, default: str | None = None) -> str | None:
    v = os.environ.get(key)
    if v is not None and v.strip() != "":
        return v
    return default


def post_replay(url: str, secret: str) -> tuple[int, str]:
    req = urllib.request.Request(
        url,
        method="POST",
        data=b"",
        headers={
            "X-Replay-Secret": secret,
            "Content-Length": "0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return resp.status, body
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        return e.code, err_body
    except urllib.error.URLError as e:
        return -1, str(e.reason)


def main() -> int:
    p = argparse.ArgumentParser(description="Serial → POST /hooks/replay-trigger/{button_id}")
    p.add_argument("--port", default=_env("SERIAL_PORT"), help="Porta serial (ou env SERIAL_PORT)")
    p.add_argument(
        "--url",
        default=_env("REPLAY_URL"),
        help="URL completa do hook incl. button_id, ex.: http://127.0.0.1:8000/hooks/replay-trigger/1 (ou env REPLAY_URL)",
    )
    p.add_argument(
        "--secret",
        default=_env("REPLAY_HOOK_SECRET"),
        help="Segredo (ou env REPLAY_HOOK_SECRET)",
    )
    p.add_argument(
        "--baud",
        type=int,
        default=int(_env("SERIAL_BAUD", "115200") or "115200"),
        help="Baud rate (ou env SERIAL_BAUD)",
    )
    p.add_argument(
        "--command",
        default=_env("REPLAY_SERIAL_COMMAND", "REPLAY_CUT"),
        help="Linha serial que dispara o POST (ou env REPLAY_SERIAL_COMMAND)",
    )
    args = p.parse_args()

    if not args.port:
        print("Defina SERIAL_PORT ou use --port", file=sys.stderr)
        return 2
    if not args.url:
        print("Defina REPLAY_URL ou use --url (incluindo /{button_id} no final)", file=sys.stderr)
        return 2
    if not args.secret:
        print("Defina REPLAY_HOOK_SECRET ou use --secret", file=sys.stderr)
        return 2

    try:
        import serial  # type: ignore[import-untyped]
    except ImportError:
        print("Instale pyserial: pip install pyserial", file=sys.stderr)
        return 2

    print(f"Abrindo {args.port} @ {args.baud} baud; aguardando linha '{args.command}'…", flush=True)
    ser = serial.Serial(args.port, args.baud, timeout=1)

    try:
        while True:
            raw = ser.readline()
            if not raw:
                continue
            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            if line != args.command:
                continue
            print(f"Comando recebido → POST {args.url}", flush=True)
            status, body = post_replay(args.url, args.secret)
            if status == 200:
                try:
                    data = json.loads(body)
                    print(f"OK job id={data.get('id')} status={data.get('status')}", flush=True)
                except json.JSONDecodeError:
                    print(f"OK {body[:500]}", flush=True)
            else:
                print(f"Erro HTTP {status}: {body[:500]}", flush=True)
    except KeyboardInterrupt:
        print("\nEncerrando.", flush=True)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
