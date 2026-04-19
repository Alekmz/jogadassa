# Jogadassa / Replay edge

Sistema para mini‑PC na quadra: **gravador RTSP** (ex.: Intelbras), **API** (FastAPI), **worker** que exporta MP4 a partir dos segmentos, **gatilho de replay** (últimos *N* segundos, configurável), pedidos com **confirmação manual** de pagamento e link **WhatsApp** no painel.

Este README descreve **todos os passos** para rodar o projeto numa máquina nova (migração ou instalação limpa).

---

## 1. O que você precisa na máquina

| Item | Uso |
|------|-----|
| **Git** | Clonar o repositório |
| **Docker** e **Docker Compose** (plugin `docker compose`) | Forma recomendada de subir gravador + API + worker |
| **Rede** | Mini‑PC na mesma rede da câmera (IP fixo ou DHCP reservado ajuda) |

Opcional (desenvolvimento sem Docker):

- **Python 3.12+** e **FFmpeg** no PATH (o worker e o gravador usam FFmpeg).

---

## 2. Obter o código

```bash
git clone <url-do-repositório> jogadassa
cd jogadassa
```

Se você copia a pasta via pendrive/zip, mantenha a estrutura do projeto e vá para a raiz (`jogadassa/`).

---

## 3. Configurar variáveis de ambiente

1. Copie o modelo:

   ```bash
   cp .env.example .env
   ```

2. Edite **`.env`** e ajuste no mínimo:

   | Variável | Descrição |
   |----------|-----------|
   | `RTSP_URL` | URL RTSP da câmera (usuário, senha, IP, path — depende do modelo; Intelbras costuma usar `/cam/realmonitor?channel=1&subtype=0` ou `subtype=1` para substream) |
   | `SECRET_KEY` | Chave longa e aleatória para JWT |
   | `ADMIN_PASSWORD` | Senha do painel admin |
   | `REPLAY_HOOK_SECRET` | Segredo do `POST /hooks/replay-trigger` (mesmo valor no `curl` e no bridge serial) |
   | `PUBLIC_BASE_URL` | URL **absoluta** da API na rede da quadra (ex.: `http://192.168.0.10:8000`) para links no WhatsApp; pode ficar vazio para usar o host da requisição ao abrir `/` |

   Outras variáveis estão comentadas em [`.env.example`](.env.example).

3. **Não commite** o arquivo `.env` (deve estar no `.gitignore`).

---

## 4. Subir tudo com Docker Compose (recomendado)

Na **raiz** do repositório:

```bash
docker compose up --build -d
```

Isso sobe três serviços:

| Serviço | Função |
|---------|--------|
| `recorder` | Lê o RTSP e grava segmentos `.mkv` em `/data/segments` |
| `api` | FastAPI + painel em `http://localhost:8000/` |
| `worker` | Processa fila de cortes e gera MP4 em `/data/clips` |

Dados persistidos no volume Docker **`replay_data`**: SQLite (`app.db`), segmentos e clips.

### Porta da API

Por padrão a API escuta na **8000** do host. Para mudar:

```bash
API_PORT=8080 docker compose up --build -d
```

Ou defina `API_PORT` no `.env`.

### Ver se está rodando

```bash
docker compose ps
docker compose logs -f api --tail 50
```

### Parar

```bash
docker compose down
```

(`down` não apaga o volume `replay_data`; os dados de gravação/banco continuam até você remover o volume manualmente.)

---

## 5. Primeiro acesso ao painel

1. Abra no navegador: **`http://localhost:8000/`** (ou `http://<IP-da-máquina>:8000` a partir de outro PC na rede).

2. Faça login com `ADMIN_USERNAME` / `ADMIN_PASSWORD` do `.env`.

3. Seções úteis:
   - **Novo pedido (público)** — escolhe replay listado e abre pedido.
   - **Painel admin** — cortes manuais, pedidos (marcar pago), jobs de clip, link WhatsApp após pagamento.

---

## 6. Testar o gatilho de replay (sem botão físico)

Com API e **worker** no ar, o mesmo segredo do `.env`:

```bash
# Carregue o .env ou exporte manualmente
set -a && source .env && set +a   # bash; no zsh: export $(grep -v '^#' .env | xargs)

curl -sS -X POST "http://localhost:8000/hooks/replay-trigger" \
  -H "X-Replay-Secret: $REPLAY_HOOK_SECRET"
```

- A janela de tempo é **`[agora − N, agora]`** com `N = REPLAY_TRIGGER_WINDOW_SECONDS` (padrão 30). Ajuste no `.env` e **recrie** o container `api` se mudar.

- Listar replays prontos para pedido:

  ```bash
  curl -sS "http://localhost:8000/clips/selectable"
  ```

Se o gravador não estiver gerando segmentos (RTSP errado, rede, etc.), o job de clip pode falhar até existir mídia no intervalo — veja logs do `worker` e do `recorder`.

---

## 7. Bridge USB (ESP32 → serial → API)

Fluxo: placa envia uma linha (padrão **`REPLAY_CUT`**) pela USB; um script Python faz o mesmo `POST` do `curl`.

### 7.1 Rodar no host (Mac / Windows / Linux)

```bash
pip install pyserial
export SERIAL_PORT=/dev/ttyUSB0        # Linux; macOS: /dev/tty.usbserial-* ; Windows: COM3
export REPLAY_HOOK_SECRET=<igual ao .env>
export REPLAY_URL=http://127.0.0.1:8000/hooks/replay-trigger
python3 scripts/serial_replay_bridge.py
```

- O processo **fica em loop**; deixe o terminal aberto ou use **systemd** no Linux ([`scripts/serial-replay-bridge.service.example`](scripts/serial-replay-bridge.service.example)).
- Se a API estiver em outro IP, use `REPLAY_URL=http://192.168.x.x:8000/hooks/replay-trigger`.

### 7.2 Rodar o bridge junto do Docker (Linux + USB)

Só faz sentido com **dispositivo serial no host** (mini‑PC Linux):

```bash
docker compose --profile bridge up -d --build
```

Ajuste `SERIAL_DEVICE` no `.env` se a porta não for `/dev/ttyUSB0`.

No **Docker Desktop (Mac/Windows)** o mapeamento USB costuma falhar; use o script no **host** (secção 7.1).

---

## 8. Desenvolvimento local sem Docker (opcional)

Três processos: API, worker, e (se quiser testar RTSP no host) o gravador.

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
export DATA_DIR=./data
export DATABASE_URL=sqlite:///./data/app.db
mkdir -p data/segments data/clips
```

**Terminal 1 — API:**

```bash
cd backend && PYTHONPATH=. .venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Terminal 2 — worker:**

```bash
cd backend && PYTHONPATH=. .venv/bin/python -m app.worker_main
```

É necessário **FFmpeg** instalado no sistema para exportar cortes.

---

## 9. Pagamento via webhook (stub, opcional)

Defina `PAYMENT_PROVIDER=webhook_stub` no ambiente da API. Assinatura de exemplo:

```bash
PAYMENT_WEBHOOK_SECRET=seu_segredo python3 scripts/sign_webhook_body.py 1
```

---

## 10. Resumo da API HTTP

| Método | Caminho | Descrição |
|--------|---------|-----------|
| `POST` | `/auth/token` | Login admin (JWT) |
| `GET` | `/health` | Saúde + info do gravador |
| `POST` | `/hooks/replay-trigger` | Gatilho replay (header `X-Replay-Secret`) |
| `GET` | `/clips/selectable` | Lista replays do botão já exportados |
| `POST` | `/clips/admin` | Corte manual (JWT admin) |
| `POST` | `/orders` | Cria pedido com `clip_job_id` |
| `POST` | `/orders/admin/{id}/mark-paid` | Confirma pagamento (admin) |
| `GET` | `/clips/files/{id}?token=...` | Download MP4 |

---

## 11. Checklist rápido de problemas

| Sintoma | O que verificar |
|---------|------------------|
| Gravador reinicia em loop | `RTSP_URL`, usuário/senha, RTSP habilitado na câmera, firewall, `ffprobe` no host apontando para o mesmo URL |
| Clip job `failed` / selectable vazio | `docker compose logs worker`, `recorder`; pastas `segments` com arquivos; horário/NTP no mini‑PC |
| `401` no hook | `X-Replay-Secret` igual a `REPLAY_HOOK_SECRET` |
| Bridge não dispara | Script rodando; porta serial correta; linha exata (`REPLAY_SERIAL_COMMAND`) |

---

## 12. Estrutura útil do repositório

| Caminho | Conteúdo |
|---------|----------|
| `backend/app/` | API FastAPI, modelos, worker |
| `recorder/` | Gravador RTSP → segmentos |
| `scripts/` | Bridge serial, exemplos systemd, Dockerfile do bridge |
| `docker-compose.yml` | Serviços `recorder`, `api`, `worker`, opcional `replay-bridge` (perfil `bridge`) |

---

Boa migração: depois de copiar o repo e o `.env`, o passo crítico é **`docker compose up --build -d`** e validar **`/health`**, login no painel e um **`curl`** no `/hooks/replay-trigger`.
