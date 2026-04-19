#!/usr/bin/env bash
# POC: validar RTSP + segmentação (use com .env carregado ou exporte RTSP_URL)
set -euo pipefail
: "${RTSP_URL:?Defina RTSP_URL (ex: rtsp://user:pass@ip:554/path)}"
OUT="${1:-./poc_out}"
mkdir -p "$OUT"
echo "Gravando ~60s de teste em $OUT ..."
ffmpeg -hide_banner -y \
  -rtsp_transport tcp \
  -i "$RTSP_URL" \
  -t 60 \
  -c copy \
  "$OUT/poc_test.mkv"
echo "OK: $OUT/poc_test.mkv"
echo "---"
echo "Segmentos de 30s (exemplo de política de corte):"
ffmpeg -hide_banner -y \
  -rtsp_transport tcp \
  -i "$RTSP_URL" \
  -t 120 \
  -c copy \
  -f segment \
  -segment_time 30 \
  -reset_timestamps 1 \
  -strftime 1 \
  "$OUT/segment_%Y%m%d_%H%M%S_part%03d.mkv"
echo "Segmentos em $OUT"
