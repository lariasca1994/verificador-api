"""Verificacion en dos pasos (obligatoria).

Cada cuenta usa al menos uno de dos metodos y puede tener ambos:

  - App autenticadora (TOTP, RFC 6238): codigo de 6 digitos que cambia cada
    30 s. El secreto se guarda cifrado con AES-GCM; la clave se deriva del
    JWT_SECRET con HKDF, asi que un volcado de la base no basta para
    generar codigos. Un mismo codigo no se acepta dos veces.
  - Codigo por correo: 6 digitos de un solo uso que vencen en 10 minutos.
    Solo se guarda su huella (HMAC) y admite 5 intentos; se pueden pedir
    hasta 3 envios cada 10 minutos. Tras 5 codigos de la app errados, la app
    queda bloqueada 15 minutos.

"Perdi mi autenticador": codigo de un solo uso al correo de la cuenta (aunque
el metodo correo no este activo); acertarlo solo habilita configurar una app
nueva, que reemplaza a la anterior al confirmarse.

Todo vive en la columna JSONB "mfa" de la tabla usuarios.
"""

import base64
import hashlib
import hmac
import html
import secrets
import struct
import time
from urllib.parse import quote

import segno
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from sqlalchemy.orm import object_session

from app import auditoria, correo
from app.seguridad import JWT_SECRET

EMISOR = correo.NOMBRE  # emisor (issuer) que muestra la app autenticadora
METODOS = {"totp": "App autenticadora", "correo": "Código por correo"}
_PASO = 30
_CODIGO_MINUTOS = 10
_MAX_INTENTOS = 5
_MAX_ENVIOS = 3
_BLOQUEO_SEG = 15 * 60  # tras 5 códigos de la app errados

_clave = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"VerificadorAPI.MFA.v1").derive(
    JWT_SECRET.encode("utf-8")
)


# ─────────────────────────────── utilidades ───────────────────────────────


def _cifrar(texto: str) -> str:
    nonce = secrets.token_bytes(12)
    return base64.b64encode(nonce + AESGCM(_clave).encrypt(nonce, texto.encode(), None)).decode()


def _descifrar(valor: str) -> str:
    datos = base64.b64decode(valor)
    return AESGCM(_clave).decrypt(datos[:12], datos[12:], None).decode()


def _huella(codigo: str) -> str:
    return hmac.new(_clave, codigo.encode(), hashlib.sha256).hexdigest()


def _totp(secreto: str, paso: int) -> str:
    clave = base64.b32decode(secreto + "=" * (-len(secreto) % 8))
    resumen = hmac.new(clave, struct.pack(">Q", paso), hashlib.sha1).digest()
    desfase = resumen[-1] & 0x0F
    numero = struct.unpack(">I", resumen[desfase:desfase + 4])[0] & 0x7FFFFFFF
    return f"{numero % 1_000_000:06d}"


def _limpiar(codigo: str) -> str:
    return "".join(c for c in (codigo or "") if c.isdigit())


def estado(usuario) -> dict:
    return dict(usuario.mfa or {})


def metodos_activos(usuario) -> list[str]:
    m = estado(usuario)
    return [x for x in ("totp", "correo") if (x == "totp" and m.get("totp")) or (x == "correo" and m.get("correo"))]


def configurado(usuario) -> bool:
    return bool(metodos_activos(usuario))


def preferido(usuario) -> str | None:
    activos = metodos_activos(usuario)
    elegido = estado(usuario).get("preferido")
    return elegido if elegido in activos else (activos[0] if activos else None)


def _guardar(usuario, cambios: dict) -> None:
    # Se reasigna el diccionario completo para que SQLAlchemy detecte el cambio.
    usuario.mfa = {**estado(usuario), **cambios}
    object_session(usuario).commit()


# ──────────────────────────── app autenticadora ───────────────────────────


def iniciar_totp(usuario) -> dict:
    """Genera un secreto pendiente y devuelve lo necesario para escanearlo."""
    secreto = base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")
    _guardar(usuario, {"totp_pendiente": _cifrar(secreto)})
    return _datos_qr(usuario, secreto)


def _datos_qr(usuario, secreto: str) -> dict:
    uri = (
        f"otpauth://totp/{quote(EMISOR)}:{quote(usuario.email)}"
        f"?secret={secreto}&issuer={quote(EMISOR)}&digits=6&period={_PASO}"
    )
    return {"qr": segno.make(uri, error="m").svg_inline(scale=5, dark="#0f172a", light="#ffffff"), "secreto": secreto}


def _verificar_totp(usuario, secreto_cifrado: str | None, codigo: str) -> bool:
    if not secreto_cifrado or len(codigo) != 6:
        return False
    secreto = _descifrar(secreto_cifrado)
    actual = int(time.time()) // _PASO
    ultimo = estado(usuario).get("ultimo_paso", 0)
    for paso in (actual - 1, actual, actual + 1):
        if paso > ultimo and hmac.compare_digest(_totp(secreto, paso), codigo):
            _guardar(usuario, {"ultimo_paso": paso})
            return True
    return False


def _activar_totp(usuario, codigo: str) -> bool:
    pendiente = estado(usuario).get("totp_pendiente")
    if not _verificar_totp(usuario, pendiente, _limpiar(codigo)):
        return False
    cambios = {"totp": pendiente, "totp_pendiente": None}
    if not configurado(usuario):
        cambios["preferido"] = "totp"
    _guardar(usuario, cambios)
    return True


# ──────────────────────────── codigo por correo ───────────────────────────


def enviar_codigo(usuario) -> bool:
    """Envia un codigo nuevo. False si ya se pidieron demasiados."""
    ahora = time.time()
    envios = [t for t in estado(usuario).get("envios", []) if ahora - t < _CODIGO_MINUTOS * 60]
    if len(envios) >= _MAX_ENVIOS:
        return False
    codigo = f"{secrets.randbelow(1_000_000):06d}"
    _guardar(usuario, {
        "codigo": {
            "huella": _huella(codigo),
            "expira": ahora + _CODIGO_MINUTOS * 60,
            "intentos": 0,
        },
        "envios": envios + [ahora],
    })
    nombre = usuario.nombre or ""
    correo.enviar(
        usuario.email, nombre, f"Tu código de acceso · {EMISOR}",
        f"Hola {nombre},\n\nTu código de verificación de {EMISOR} es: {codigo}\n\n"
        f"Vence en {_CODIGO_MINUTOS} minutos y sirve una sola vez. Si no intentaste ingresar, "
        "cambia tu contraseña.",
        f"<p>Hola {html.escape(nombre)},</p><p>Tu código de verificación de <strong>{EMISOR}</strong> es:</p>"
        f'<p style="font-size:28px;font-weight:700;letter-spacing:6px">{codigo}</p>'
        f"<p>Vence en {_CODIGO_MINUTOS} minutos y sirve una sola vez. Si no intentaste ingresar, "
        "cambia tu contraseña.</p>",
    )
    return True


def _verificar_correo(usuario, codigo: str) -> bool:
    guardado = estado(usuario).get("codigo")
    if not guardado or guardado.get("intentos", 0) >= _MAX_INTENTOS:
        return False
    if guardado["expira"] < time.time():
        return False
    if not hmac.compare_digest(guardado["huella"], _huella(codigo)):
        _guardar(usuario, {"codigo": {**guardado, "intentos": guardado.get("intentos", 0) + 1}})
        return False
    _guardar(usuario, {"codigo": None})
    return True


def _activar_correo(usuario, codigo: str) -> bool:
    if not _verificar_correo(usuario, _limpiar(codigo)):
        return False
    cambios = {"correo": True}
    if not configurado(usuario):
        cambios["preferido"] = "correo"
    _guardar(usuario, cambios)
    return True


# ─────────────────────────────── verificacion ──────────────────────────────


def _verificar_metodo(usuario, metodo: str, codigo: str) -> bool:
    """Comprueba el codigo de un metodo ya activo."""
    codigo = _limpiar(codigo)
    if metodo not in metodos_activos(usuario):
        return False
    if metodo == "totp":
        # Sin este freno, con la contraseña bastaría probar códigos hasta acertar.
        if estado(usuario).get("bloqueo_hasta", 0) > time.time():
            return False
        if _verificar_totp(usuario, estado(usuario).get("totp"), codigo):
            if estado(usuario).get("fallos"):
                _guardar(usuario, {"fallos": 0})
            return True
        fallos = estado(usuario).get("fallos", 0) + 1
        _guardar(usuario, {"fallos": 0, "bloqueo_hasta": time.time() + _BLOQUEO_SEG}
                 if fallos >= _MAX_INTENTOS else {"fallos": fallos})
        return False
    return _verificar_correo(usuario, codigo)


def elegir_preferido(usuario, metodo: str) -> bool:
    if metodo not in metodos_activos(usuario):
        return False
    _guardar(usuario, {"preferido": metodo})
    return True


# ───────────────────── auditoría y bloqueo por contraseña ─────────────────────

_MAX_FALLOS_CLAVE = 5
_BLOQUEO_CLAVE_SEG = 15 * 60
MENSAJE_BLOQUEO = "Demasiados intentos fallidos. Espera unos minutos e inténtalo de nuevo."


def verificar(usuario, metodo: str, codigo: str) -> bool:
    """Comprueba el código de un método ya activo y deja el intento en la auditoría."""
    if _verificar_metodo(usuario, metodo, codigo):
        auditoria.registrar(auditoria.INGRESO, usuario)
        return True
    auditoria.registrar(auditoria.CODIGO_ERRADO, usuario)
    return False


def activar_totp(usuario, codigo: str) -> bool:
    if not _activar_totp(usuario, codigo):
        return False
    auditoria.registrar(auditoria.METODO_ACTIVADO, usuario)
    return True


def activar_correo(usuario, codigo: str) -> bool:
    if not _activar_correo(usuario, codigo):
        return False
    auditoria.registrar(auditoria.METODO_ACTIVADO, usuario)
    return True


def clave_bloqueada(usuario) -> bool:
    """True si la cuenta está bloqueada por contraseñas erradas seguidas."""
    return estado(usuario).get("bloqueo_clave_hasta", 0) > time.time()


def fallo_de_clave(usuario) -> None:
    """Suma una contraseña errada; la quinta seguida bloquea la cuenta un tiempo."""
    auditoria.registrar(auditoria.CLAVE_ERRADA, usuario)
    fallos = estado(usuario).get("fallos_clave", 0) + 1
    if fallos >= _MAX_FALLOS_CLAVE:
        _guardar(usuario, {"fallos_clave": 0, "bloqueo_clave_hasta": time.time() + _BLOQUEO_CLAVE_SEG})
        auditoria.registrar(auditoria.CUENTA_BLOQUEADA, usuario)
    else:
        _guardar(usuario, {"fallos_clave": fallos})


def clave_correcta(usuario) -> None:
    """La contraseña fue correcta: el contador vuelve a cero."""
    if estado(usuario).get("fallos_clave"):
        _guardar(usuario, {"fallos_clave": 0})


def clave_restablecida(usuario) -> None:
    """Contraseña nueva (recuperación o cambio): se levanta el bloqueo y queda en la auditoría."""
    _guardar(usuario, {"fallos_clave": 0, "bloqueo_clave_hasta": 0})
    auditoria.registrar(auditoria.CLAVE_CAMBIADA, usuario)


# ───────────────────── recuperación: "Perdí mi autenticador" ─────────────────────
# Código de 6 dígitos al correo de la cuenta, aunque el método "correo" no esté
# activo. Acertarlo NO abre sesión: solo habilita configurar una app nueva, y la
# anterior se reemplaza recién cuando la nueva queda confirmada.

_RECUPERAR_SEG = 15 * 60
_MAX_ENVIOS_RECUPERAR = 3
_BLOQUEO_RECUPERAR_SEG = 15 * 60
RECUPERAR_MINUTOS = _RECUPERAR_SEG // 60


def recuperacion_bloqueada(usuario) -> bool:
    return estado(usuario).get("bloqueo_recuperar_hasta", 0) > time.time()


def enviar_codigo_recuperacion(usuario) -> bool:
    """Envía el código de recuperación. False si está bloqueada o se pidieron demasiados."""
    if recuperacion_bloqueada(usuario):
        return False
    ahora = time.time()
    envios = [t for t in estado(usuario).get("envios_recuperar", []) if ahora - t < _RECUPERAR_SEG]
    if len(envios) >= _MAX_ENVIOS_RECUPERAR:
        return False
    codigo = f"{secrets.randbelow(1_000_000):06d}"
    _guardar(usuario, {
        "recuperar": {"huella": _huella(codigo), "expira": ahora + _RECUPERAR_SEG, "intentos": 0},
        "envios_recuperar": envios + [ahora],
    })
    nombre = usuario.nombre or ""
    correo.enviar(
        usuario.email, nombre, f"Código para recuperar tu acceso · {EMISOR}",
        f"Hola {nombre},\n\nPediste entrar a {EMISOR} sin tu app autenticadora. Tu código es: {codigo}\n\n"
        f"Vence en {RECUPERAR_MINUTOS} minutos y sirve una sola vez. Después tendrás que configurar "
        "una app autenticadora nueva. Si no fuiste tú, cambia tu contraseña.",
        f"<p>Hola {html.escape(nombre)},</p><p>Pediste entrar a <strong>{EMISOR}</strong> sin tu app "
        "autenticadora. Tu código es:</p>"
        f'<p style="font-size:28px;font-weight:700;letter-spacing:6px">{codigo}</p>'
        f"<p>Vence en {RECUPERAR_MINUTOS} minutos y sirve una sola vez. Después tendrás que configurar "
        "una app autenticadora nueva. Si no fuiste tú, cambia tu contraseña.</p>",
    )
    auditoria.registrar(auditoria.RECUPERACION_MFA, usuario)
    return True


def verificar_codigo_recuperacion(usuario, codigo: str) -> bool:
    """True si el código es correcto: habilita configurar la app nueva por un tiempo."""
    if recuperacion_bloqueada(usuario):
        return False
    guardado = estado(usuario).get("recuperar")
    if not guardado or guardado["expira"] < time.time():
        return False
    if not hmac.compare_digest(guardado["huella"], _huella(_limpiar(codigo))):
        intentos = guardado.get("intentos", 0) + 1
        auditoria.registrar(auditoria.CODIGO_ERRADO, usuario)
        if intentos >= _MAX_INTENTOS:
            _guardar(usuario, {"recuperar": None, "bloqueo_recuperar_hasta": time.time() + _BLOQUEO_RECUPERAR_SEG})
            auditoria.registrar(auditoria.CUENTA_BLOQUEADA, usuario)
        else:
            _guardar(usuario, {"recuperar": {**guardado, "intentos": intentos}})
        return False
    _guardar(usuario, {"recuperar": None, "recuperado_hasta": time.time() + _RECUPERAR_SEG})
    return True


def recuperacion_vigente(usuario) -> bool:
    """El código de recuperación ya se acertó y falta confirmar la app nueva."""
    return estado(usuario).get("recuperado_hasta", 0) > time.time()


def reemplazar_totp(usuario, codigo: str) -> bool:
    """Confirma la app nueva y recién ahí reemplaza a la anterior."""
    if not recuperacion_vigente(usuario):
        return False
    pendiente = estado(usuario).get("totp_pendiente")
    if not _verificar_totp(usuario, pendiente, _limpiar(codigo)):
        return False
    _guardar(usuario, {"totp": pendiente, "totp_pendiente": None, "recuperado_hasta": 0,
                       "preferido": "totp", "fallos": 0, "bloqueo_hasta": 0})
    auditoria.registrar(auditoria.METODO_ACTIVADO, usuario)
    return True


def qr_pendiente(usuario) -> dict | None:
    """Vuelve a mostrar el QR de la app que se está configurando (tras un código errado)."""
    pendiente = estado(usuario).get("totp_pendiente")
    return _datos_qr(usuario, _descifrar(pendiente)) if pendiente else None
