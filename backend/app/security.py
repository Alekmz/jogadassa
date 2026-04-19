from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def create_access_token(subject: str, expires_seconds: int | None = None) -> str:
    s = get_settings()
    exp = expires_seconds or 60 * 60 * 12
    payload = {
        "sub": subject,
        "exp": datetime.now(timezone.utc) + timedelta(seconds=exp),
        "typ": "admin",
    }
    return jwt.encode(payload, s.secret_key, algorithm="HS256")


def decode_token(token: str) -> dict:
    s = get_settings()
    return jwt.decode(token, s.secret_key, algorithms=["HS256"])


def create_download_token(clip_job_id: int) -> str:
    s = get_settings()
    exp = s.download_token_expire_seconds
    payload = {
        "cid": clip_job_id,
        "exp": datetime.now(timezone.utc) + timedelta(seconds=exp),
        "typ": "download",
    }
    return jwt.encode(payload, s.secret_key, algorithm="HS256")


def decode_download_token(token: str) -> int:
    s = get_settings()
    try:
        data = jwt.decode(token, s.secret_key, algorithms=["HS256"])
    except JWTError as e:
        raise ValueError("token inválido") from e
    if data.get("typ") != "download":
        raise ValueError("tipo de token incorreto")
    return int(data["cid"])
