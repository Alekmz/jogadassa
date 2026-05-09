# Jogadassa / Replay edge

Sistema para mini‑PC na quadra: **gravadores RTSP** (ex.: Intelbras) — **2 botões físicos, cada um com 2 câmeras dedicadas** (4 câmeras no total) — **API** (FastAPI), **worker** que exporta MP4 a partir dos segmentos, **gatilho de replay** (últimos *N* segundos, configurável) que ao ser apertado gera **2 clipes simultâneos** (um por câmera do botão), pedidos com **confirmação manual** de pagamento e link **WhatsApp** no painel.

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
   | `RTSP_URL_CAM1` … `RTSP_URL_CAM4` | URLs RTSP das **4 câmeras** (uma por câmera; Intelbras costuma usar `/cam/realmonitor?channel=1&subtype=0` ou `subtype=1` para substream) |
   | `BUTTON1_CAMERAS` / `BUTTON2_CAMERAS` | Lista CSV das câmeras conectadas a cada botão (padrão: `cam1,cam2` e `cam3,cam4`). Os IDs precisam bater com os `RTSP_URL_CAMx`. |
   | `SECRET_KEY` | Chave longa e aleatória para JWT |
   | `ADMIN_PASSWORD` | Senha do painel admin |
   | `REPLAY_HOOK_SECRET` | Segredo do `POST /hooks/replay-trigger/{button_id}` (mesmo valor no `curl` e nos bridges seriais) |
   | `PUBLIC_BASE_URL` | URL **absoluta** da API na rede da quadra (ex.: `http://192.168.0.10:8000`) para links no WhatsApp; pode ficar vazio para usar o host da requisição ao abrir `/` |
   | `COMPOSE_PROFILES` | Defina `bridge` para subir os serviços **replay-bridge-1/2** (USB dos botões) junto com `docker compose up`, sem passar `--profile` na linha de comando |
   | `SERIAL_DEVICE_BUTTON1` / `SERIAL_DEVICE_BUTTON2` | (Opcional) Caminhos dos dispositivos seriais no host Linux (padrão `/dev/ttyUSB0` e `/dev/ttyUSB1`) quando usa os bridges no Docker |

   Outras variáveis estão comentadas em [`.env.example`](.env.example).

3. **Não commite** o arquivo `.env` (deve estar no `.gitignore`).

---

## 4. Subir tudo com Docker Compose (recomendado)

Na **raiz** do repositório:

```bash
docker compose up --build -d
```

O [`.env.example`](.env.example) inclui **`COMPOSE_PROFILES=bridge`**, então esse comando também sobe o **replay-bridge** (escuta a USB e envia o POST do botão). Se não quiser o bridge no Docker (ex.: Mac sem serial), remova ou comente `COMPOSE_PROFILES` no `.env`.

Isso sobe os serviços principais:

| Serviço | Função |
|---------|--------|
| `recorder-cam1` … `recorder-cam4` | Cada um lê seu RTSP e grava segmentos `.mkv` em `/data/segments/{camera_id}/` |
| `api` | FastAPI + painel em `http://localhost:8000/` |
| `worker` | Processa fila de cortes e gera MP4 em `/data/clips/btn{N}/{camera_id}/` |
| `replay-bridge-1` / `replay-bridge-2` | (Com perfil `bridge` ativo) Bridge serial USB → `POST /hooks/replay-trigger/{button_id}` |

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

curl -sS -X POST "http://localhost:8000/hooks/replay-trigger/1" \
  -H "X-Replay-Secret: $REPLAY_HOOK_SECRET"

# Para o botão 2:
curl -sS -X POST "http://localhost:8000/hooks/replay-trigger/2" \
  -H "X-Replay-Secret: $REPLAY_HOOK_SECRET"
```

A resposta lista os jobs criados (1 por câmera do botão). A janela de tempo é **`[agora − N, agora]`** com `N = REPLAY_TRIGGER_WINDOW_SECONDS` (padrão 30). Ajuste no `.env` e **recrie** o container `api` se mudar.

- Listar replays prontos para pedido:

  ```bash
  curl -sS "http://localhost:8000/clips/selectable"
  ```

Se o gravador não estiver gerando segmentos (RTSP errado, rede, etc.), o job de clip pode falhar até existir mídia no intervalo — veja logs do `worker` e do `recorder`.

---

## 7. Bridge USB (2 ESP32 → serial → API)

Fluxo: cada placa envia uma linha (padrão **`REPLAY_CUT`**) pela USB; um script Python faz o mesmo `POST` do `curl`. Com **2 botões**, há **2 instâncias** do bridge — uma por porta USB. O **firmware nos 2 ESP32 é idêntico**: a identidade do botão é resolvida no servidor pela URL para onde cada bridge faz POST.

### 7.1 Rodar no host (Mac / Windows / Linux)

Para cada botão, abra um processo:

```bash
pip install pyserial

# Botão 1:
export SERIAL_PORT=/dev/ttyUSB0        # Linux; macOS: /dev/tty.usbserial-* ; Windows: COM3
export REPLAY_HOOK_SECRET=<igual ao .env>
export REPLAY_URL=http://127.0.0.1:8000/hooks/replay-trigger/1
python3 scripts/serial_replay_bridge.py

# Em outro terminal, botão 2:
export SERIAL_PORT=/dev/ttyUSB1
export REPLAY_HOOK_SECRET=<igual ao .env>
export REPLAY_URL=http://127.0.0.1:8000/hooks/replay-trigger/2
python3 scripts/serial_replay_bridge.py
```

- Cada processo **fica em loop**; use **systemd** no Linux para subir os 2 ([`scripts/serial-replay-bridge.service.example`](scripts/serial-replay-bridge.service.example)).
- Se a API estiver em outro IP, troque `127.0.0.1` pelo IP do mini-PC.

### 7.2 Bridges dentro do Docker (Linux + USB)

Com **`COMPOSE_PROFILES=bridge`** no `.env` (já vem no [`.env.example`](.env.example)), o comando usual já sobe os 2 bridges:

```bash
docker compose up -d --build
```

Equivalente explícito: `docker compose --profile bridge up -d --build`.

Ajuste **`SERIAL_DEVICE_BUTTON1`** e **`SERIAL_DEVICE_BUTTON2`** no `.env` se as portas não forem `/dev/ttyUSB0` e `/dev/ttyUSB1`. Recomendado fixar a ordem com regras `udev` por serial number do conversor USB-serial — caso contrário, reiniciar o host pode trocar a numeração.

No **Docker Desktop (Mac/Windows)** o mapeamento USB costuma falhar — **comente ou remova** `COMPOSE_PROFILES=bridge` no `.env` e use o script no **host** (secção 7.1).

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
| `POST` | `/hooks/replay-trigger/{button_id}` | Gatilho replay do botão (header `X-Replay-Secret`); cria 1 job por câmera do botão |
| `GET` | `/clips/selectable` | Lista replays do botão já exportados |
| `POST` | `/clips/admin` | Corte manual (JWT admin) |
| `POST` | `/orders` | Cria pedido com `clip_job_id` |
| `POST` | `/orders/admin/{id}/mark-paid` | Confirma pagamento (admin) |
| `GET` | `/clips/files/{id}?token=...` | Download MP4 |

---

## 11. Checklist rápido de problemas

| Sintoma | O que verificar |
|---------|------------------|
| Algum gravador reinicia em loop | `RTSP_URL_CAMx` da câmera afetada, usuário/senha, RTSP habilitado na câmera, firewall, `ffprobe` no host apontando para o mesmo URL |
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
| `docker-compose.yml` | Serviços `recorder-cam1..4`, `api`, `worker`, `replay-bridge-1/2` (bridges ativados por `COMPOSE_PROFILES=bridge` no `.env`) |

---

Boa migração: depois de copiar o repo e o `.env`, o passo crítico é **`docker compose up --build -d`** e validar **`/health`**, login no painel e um **`curl`** em `/hooks/replay-trigger/1` e `/hooks/replay-trigger/2`.
