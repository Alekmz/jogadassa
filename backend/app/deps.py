from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session

from app.db import get_session
from app.security import decode_token

security = HTTPBearer(auto_error=False)


def get_db():
    yield from get_session()


def get_current_admin(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
) -> str:
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token ausente",
        )
    try:
        data = decode_token(credentials.credentials)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido",
        )
    if data.get("typ") != "admin":
        raise HTTPException(status_code=403, detail="Acesso negado")
    sub = data.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="Token inválido")
    return str(sub)


DbSession = Annotated[Session, Depends(get_db)]
