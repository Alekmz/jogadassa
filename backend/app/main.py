from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from app.config import get_settings
from app.db import init_db
from app.routers import auth, clips, health, hooks, orders, payments

s = get_settings()
templates_dir = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Path(s.data_dir).mkdir(parents=True, exist_ok=True)
    Path(s.segments_dir).mkdir(parents=True, exist_ok=True)
    Path(s.clips_dir).mkdir(parents=True, exist_ok=True)
    init_db()
    yield


app = FastAPI(title="Replay Edge", lifespan=lifespan)
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(clips.router)
app.include_router(hooks.router)
app.include_router(orders.router)
app.include_router(payments.router)


@app.get("/", response_class=HTMLResponse)
def admin_home(request: Request):
    base = get_settings().public_base_url.strip()
    if not base:
        base = str(request.base_url).rstrip("/")
    return templates.TemplateResponse(
        "admin.html",
        {"request": request, "api_base": "", "public_base_url": base},
    )


static_dir = Path(__file__).resolve().parent / "static"
if static_dir.is_dir():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
