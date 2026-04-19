from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    secret_key: str = "dev-secret-change-me"
    database_url: str = "sqlite:///./data/app.db"
    data_dir: str = "/data"
    segment_seconds: int = 300
    admin_username: str = "admin"
    admin_password: str = "changeme"
    download_token_expire_seconds: int = 86400
    # Replay na quadra (Arduino / curl)
    replay_trigger_window_seconds: int = 30
    replay_hook_secret: str = "dev-replay-secret-change-me"
    # URL absoluta para links (WhatsApp, etc.); se vazio, o painel usa o host da requisição
    public_base_url: str = ""
    payment_provider: str = "manual"
    # Webhook stub secret (MVP)
    payment_webhook_secret: str = "webhook-secret-change"
    # Fluxo comercial: custom (padrão) — use customer_order.metadata_json para regras específicas
    business_mode: str = "custom"

    @property
    def segments_dir(self) -> str:
        return f"{self.data_dir.rstrip('/')}/segments"

    @property
    def clips_dir(self) -> str:
        return f"{self.data_dir.rstrip('/')}/clips"


@lru_cache
def get_settings() -> Settings:
    return Settings()
