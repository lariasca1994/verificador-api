import datetime
import os

import jwt
from fastapi import Depends, HTTPException, Request, status
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.database import obtener_db
from app.models import Usuario

JWT_SECRET = os.getenv("JWT_SECRET")
if not JWT_SECRET:
    raise RuntimeError("Falta JWT_SECRET en el archivo .env")

JWT_ALGORITMO = "HS256"
JWT_HORAS_VALIDEZ = 8
NOMBRE_COOKIE = "sesion"

_contexto_password = CryptContext(schemes=["bcrypt"], deprecated="auto")

# bcrypt trunca (o directamente rechaza, según la versión) cualquier
# contraseña de más de 72 BYTES — no caracteres: una tilde, la ñ o un
# emoji ocupan 2 a 4 bytes en UTF-8. Se valida acá para dar un mensaje
# claro en español, en vez de dejar que reviente con un ValueError de
# passlib a mitad del hash.
LARGO_MAXIMO_PASSWORD_BYTES = 72


def hashear_password(password: str) -> str:
    if len(password.encode("utf-8")) > LARGO_MAXIMO_PASSWORD_BYTES:
        raise ValueError(
            f"La contraseña no puede pesar más de {LARGO_MAXIMO_PASSWORD_BYTES} bytes "
            "(límite de bcrypt). Si usa tildes, ñ o emojis cuentan doble o más — "
            "prueba con una más corta."
        )
    return _contexto_password.hash(password)


def verificar_password(password: str, password_hash: str) -> bool:
    if len(password.encode("utf-8")) > LARGO_MAXIMO_PASSWORD_BYTES:
        # Ninguna contraseña así de larga pudo haberse registrado nunca
        # (hashear_password la habría rechazado antes) — así que jamás
        # puede ser la correcta. Se responde "no coincide" en vez de
        # dejar que bcrypt reviente al intentar verificarla.
        return False
    return _contexto_password.verify(password, password_hash)


def crear_token(usuario_id: int) -> str:
    payload = {
        "sub": str(usuario_id),
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=JWT_HORAS_VALIDEZ),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITMO)


def _decodificar_token(token: str) -> int | None:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITMO])
        return int(payload["sub"])
    except jwt.PyJWTError:
        return None


def usuario_opcional(request: Request, db: Session = Depends(obtener_db)) -> Usuario | None:
    """Para páginas públicas: da el usuario si hay sesión, o None sin fallar."""
    token = request.cookies.get(NOMBRE_COOKIE)
    if not token:
        return None
    usuario_id = _decodificar_token(token)
    if usuario_id is None:
        return None
    return db.get(Usuario, usuario_id)


def usuario_actual(
    usuario: Usuario | None = Depends(usuario_opcional),
) -> Usuario:
    """Para páginas privadas: exige sesión válida o corta con 401."""
    if usuario is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No autenticado")
    return usuario
