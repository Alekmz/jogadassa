# Replay edge — gravação e venda de cortes

Sistema para mini-PC na quadra: **gravador RTSP** (Intelbras), **API** com pedidos e cortes MP4, **worker** que exporta trechos a partir de segmentos, **pagamento manual** ou **webhook stub**.

## Requisitos

- Docker e Docker Compose (recomendado), ou Python 3.12 + FFmpeg instalados no host.

## Configuração

1. Copie `.env.example` para `.env` e defina `RTSP_URL`, `SECRET_KEY`, `ADMIN_PASSWORD`, etc.
2. POC sem Docker: `chmod +x scripts/poc_rtsp.sh` e execute com `RTSP_URL` exportado.

## Docker Compose

```bash
docker compose up --build -d
```

- API: `http://localhost:8000` — painel em `/`.
- Gravador grava em volume `replay_data` em `/data/segments`.
- Banco SQLite: `/data/app.db` no mesmo volume.

Serviços: `recorder`, `api`, `worker`.

## Desenvolvimento local (venv)

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
export DATA_DIR=./data
export DATABASE_URL=sqlite:///./data/app.db
mkdir -p data/segments data/clips
PYTHONPATH=. .venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Em outro terminal, o worker:

```bash
cd backend && PYTHONPATH=. .venv/bin/python -m app.worker_main
```

É necessário **FFmpeg** no PATH para exportar cortes.

## Pagamento webhook (stub)

Defina `PAYMENT_PROVIDER=webhook_stub`. O cliente envia `POST /payments/webhook` com corpo JSON e cabeçalho `X-Signature: hex(HMAC-SHA256(body))` usando `PAYMENT_WEBHOOK_SECRET`.

Exemplo de assinatura:

```bash
PAYMENT_WEBHOOK_SECRET=seu_segredo python3 scripts/sign_webhook_body.py 1
```

Envie o corpo impresso com `curl` e o header `X-Signature`.

## API principal

- `POST /auth/token` — login admin (JWT).
- `GET /health` — inclui `health.json` do gravador.
- `POST /clips/admin` — novo corte (admin, sem pedido).
- `POST /orders` — novo pedido (público no MVP; proteja em produção).
- `POST /orders/admin/{id}/mark-paid` — confirma pagamento.
- `GET /clips/files/{id}?token=...` — download MP4 (JWT de download).
