import datetime
import hashlib
import hmac
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


# ── Recuperación de cuenta ─────────────────────────────────────────────────
# Enlace firmado, con vencimiento y de un solo uso: lleva la huella de la
# contraseña actual (al cambiarla deja de servir) y una audiencia propia, así
# que _decodificar_token (sesiones) lo rechaza.
_AUDIENCIA_RECUPERAR = "recuperar"
RECUPERAR_MINUTOS = 30


def _huella(password_hash: str) -> str:
    return hashlib.sha256((password_hash or "").encode()).hexdigest()[:24]


def crear_token_recuperacion(usuario_id: int, password_hash: str) -> str:
    return jwt.encode(
        {"sub": str(usuario_id), "h": _huella(password_hash), "aud": _AUDIENCIA_RECUPERAR,
         "exp": datetime.datetime.utcnow() + datetime.timedelta(minutes=RECUPERAR_MINUTOS)},
        JWT_SECRET, algorithm=JWT_ALGORITMO,
    )


def leer_token_recuperacion(token: str) -> tuple[int, str] | None:
    try:
        carga = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITMO], audience=_AUDIENCIA_RECUPERAR)
        return int(carga["sub"]), str(carga["h"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None


_AUDIENCIA_MFA = "mfa"
COOKIE_MFA = "verificador_mfa"
MFA_MINUTOS = 10


def crear_token_mfa(usuario_id: int) -> str:
    """Pase de 10 minutos entre la contraseña y el código de la verificación en dos
    pasos. No sirve como sesión: _decodificar_token lo rechaza por llevar audiencia."""
    return jwt.encode(
        {"sub": str(usuario_id), "aud": _AUDIENCIA_MFA,
         "exp": datetime.datetime.utcnow() + datetime.timedelta(minutes=MFA_MINUTOS)},
        JWT_SECRET, algorithm=JWT_ALGORITMO,
    )


def leer_token_mfa(token: str | None) -> int | None:
    if not token:
        return None
    try:
        return int(jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITMO], audience=_AUDIENCIA_MFA)["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None


def huella_coincide(password_hash: str, huella: str) -> bool:
    return hmac.compare_digest(_huella(password_hash), huella)


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
    usuario = db.get(Usuario, usuario_id)
    if usuario is not None and not usuario.activo:
        # Cuenta suspendida por un admin: se trata igual que "no hay
        # sesión" — el token puede seguir siendo válido, pero la cuenta
        # ya no. Efecto inmediato porque acá se consulta la DB fresca.
        return None
    return usuario


def usuario_actual(
    usuario: Usuario | None = Depends(usuario_opcional),
) -> Usuario:
    """Para páginas privadas: exige sesión válida o corta con 401."""
    if usuario is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No autenticado")
    return usuario
