#!/usr/bin/env bash
# Smoke E2E: sobe stack com mediamtx + 4 publishers ffmpeg testsrc no lugar das
# câmeras Intelbras, dispara hooks dos 2 botões, valida que 4 MP4s aparecem nos
# subdiretórios corretos.
#
# Pré-requisitos: docker compose disponível; .env.smoke preparado a partir de
# .env.smoke.example (`cp .env.smoke.example .env.smoke`).
set -euo pipefail

ENV_FILE="${ENV_FILE:-.env.smoke}"

if [ ! -f "$ENV_FILE" ]; then
  echo "ERRO: $ENV_FILE não existe. Rode: cp .env.smoke.example $ENV_FILE" >&2
  exit 2
fi

SECRET="$(grep '^REPLAY_HOOK_SECRET=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '"')"
WINDOW="$(grep '^REPLAY_TRIGGER_WINDOW_SECONDS=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '"')"
WINDOW="${WINDOW:-10}"
WAIT_RECORDER="${WAIT_RECORDER:-$((WINDOW + 30))}"
WAIT_WORKER="${WAIT_WORKER:-30}"

DC=(docker compose --env-file "$ENV_FILE")

cleanup() {
  if [ "${KEEP_UP:-0}" != "1" ]; then
    echo "→ Derrubando stack…"
    "${DC[@]}" --profile smoke down -v >/dev/null 2>&1 || true
  else
    echo "→ KEEP_UP=1; stack continua rodando. Para derrubar: ${DC[*]} --profile smoke down -v"
  fi
}
trap cleanup EXIT

echo "→ Subindo stack (recorders + api + worker + mediamtx + 4 publishers)…"
"${DC[@]}" --profile smoke up -d --build

echo "→ Aguardando ${WAIT_RECORDER}s para os recorders gerarem segmentos…"
sleep "$WAIT_RECORDER"

echo "→ Inventário de segmentos por câmera:"
for cam in cam1 cam2 cam3 cam4; do
  count=$("${DC[@]}" exec -T api sh -c "ls /data/segments/$cam 2>/dev/null | wc -l" | tr -d '[:space:]')
  printf "  • cam %s: %s segmento(s)\n" "$cam" "${count:-0}"
done

for btn in 1 2; do
  echo "→ Disparando trigger /hooks/replay-trigger/$btn …"
  resp=$(curl -fsS -X POST "http://localhost:${API_PORT:-8000}/hooks/replay-trigger/$btn" \
    -H "X-Replay-Secret: $SECRET")
  echo "  ↳ $resp"
done

echo "→ Aguardando ${WAIT_WORKER}s para o worker processar 4 jobs…"
sleep "$WAIT_WORKER"

fail=0
for spec in "1 cam1" "1 cam2" "2 cam3" "2 cam4"; do
  set -- $spec
  btn=$1; cam=$2
  out=$("${DC[@]}" exec -T api sh -c "ls /data/clips/btn$btn/$cam/ 2>/dev/null | head -1" | tr -d '[:space:]')
  if [ -z "$out" ]; then
    printf "  ✗ FALHA: nenhum MP4 em /data/clips/btn%s/%s/\n" "$btn" "$cam"
    fail=1
  else
    printf "  ✓ OK:    /data/clips/btn%s/%s/%s\n" "$btn" "$cam" "$out"
  fi
done

if [ "$fail" -ne 0 ]; then
  echo
  echo "Smoke E2E falhou. Últimos logs dos serviços-chave:"
  "${DC[@]}" logs --tail=80 worker recorder-cam1 recorder-cam2 recorder-cam3 recorder-cam4 mediamtx || true
  exit 1
fi

echo
echo "✅ Smoke E2E passou — 4 MP4s gerados nos 4 subdiretórios esperados."
