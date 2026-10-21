from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import obtener_db
from app.models import Usuario
import html
import threading
import time

from app import correo
from app.seguridad import (
    NOMBRE_COOKIE,
    RECUPERAR_MINUTOS,
    crear_token,
    crear_token_recuperacion,
    hashear_password,
    huella_coincide,
    leer_token_recuperacion,
    usuario_actual,
    verificar_password,
)

router = APIRouter()
plantillas = Jinja2Templates(directory="app/templates")


@router.get("/login")
def formulario_login(request: Request, error: str | None = None):
    return plantillas.TemplateResponse(request, "login.html", {"error": error, "centrar": True})


@router.post("/login")
def procesar_login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(obtener_db),
):
    usuario = db.query(Usuario).filter(Usuario.email == email.strip().lower()).first()
    if usuario is None or not verificar_password(password, usuario.password_hash):
        return plantillas.TemplateResponse(
            request,
            "login.html",
            {"error": "Correo o contraseña incorrectos", "centrar": True},
            status_code=401,
        )

    token = crear_token(usuario.id)
    respuesta = RedirectResponse(url="/colecciones", status_code=303)
    respuesta.set_cookie(
        NOMBRE_COOKIE, token, httponly=True, samesite="lax", max_age=8 * 3600
    )
    return respuesta


@router.get("/registro")
def formulario_registro(request: Request, error: str | None = None):
    return plantillas.TemplateResponse(request, "registro.html", {"error": error, "centrar": True})


@router.post("/registro")
def procesar_registro(
    request: Request,
    nombre: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(obtener_db),
):
    email_normalizado = email.strip().lower()
    existente = db.query(Usuario).filter(Usuario.email == email_normalizado).first()
    if existente:
        return plantillas.TemplateResponse(
            request,
            "registro.html",
            {"error": "Ese correo ya está registrado", "centrar": True},
            status_code=409,
        )

    try:
        password_hash = hashear_password(password)
    except ValueError as error:
        return plantillas.TemplateResponse(
            request,
            "registro.html",
            {"error": str(error), "centrar": True},
            status_code=400,
        )

    usuario = Usuario(
        nombre=nombre.strip(),
        email=email_normalizado,
        password_hash=password_hash,
        rol="usuario",
    )
    db.add(usuario)
    db.commit()
    db.refresh(usuario)

    token = crear_token(usuario.id)
    respuesta = RedirectResponse(url="/colecciones", status_code=303)
    respuesta.set_cookie(
        NOMBRE_COOKIE, token, httponly=True, samesite="lax", max_age=8 * 3600
    )
    return respuesta


@router.post("/logout")
def logout():
    respuesta = RedirectResponse(url="/", status_code=303)
    respuesta.delete_cookie(NOMBRE_COOKIE)
    return respuesta


# ── Recuperar y cambiar la contraseña ──────────────────────────────────────

_RESPUESTA_RECUPERAR = (
    "Si el correo pertenece a una cuenta, te enviamos un enlace para crear una contraseña nueva. "
    "Revisa tu bandeja (y la carpeta de spam)."
)
_ENVIOS: dict[str, list[float]] = {}
_CANDADO = threading.Lock()
LARGO_MINIMO = 8


def _puede_enviar(email: str) -> bool:
    """Máximo 3 enlaces cada 15 minutos por correo (no bloquea el ingreso)."""
    ahora = time.time()
    with _CANDADO:
        recientes = [t for t in _ENVIOS.get(email, []) if ahora - t < 15 * 60]
        _ENVIOS[email] = recientes if len(recientes) >= 3 else recientes + [ahora]
        return len(recientes) < 3


def _validar_nueva(password: str, confirmacion: str) -> tuple[str | None, str | None]:
    """(error, hash): valida largo, confirmación y el límite de bcrypt."""
    if password != confirmacion:
        return "La confirmación no coincide", None
    if len(password) < LARGO_MINIMO:
        return f"La contraseña debe tener al menos {LARGO_MINIMO} caracteres", None
    try:
        return None, hashear_password(password)
    except ValueError as error:
        return str(error), None


@router.get("/recuperar")
def formulario_recuperar(request: Request):
    return plantillas.TemplateResponse(request, "recuperar.html", {"centrar": True})


@router.post("/recuperar")
def procesar_recuperar(request: Request, email: str = Form(...), db: Session = Depends(obtener_db)):
    email = email.strip().lower()
    usuario = db.query(Usuario).filter(Usuario.email == email).first()
    if usuario is not None and usuario.activo and _puede_enviar(email):
        enlace = f"{correo.URL_PUBLICA}/restablecer?token={crear_token_recuperacion(usuario.id, usuario.password_hash)}"
        correo.enviar(
            usuario.email, usuario.nombre, "Restablece tu contraseña · Verificador API",
            f"Hola {usuario.nombre},\n\nPara crear una contraseña nueva abre este enlace (vence en "
            f"{RECUPERAR_MINUTOS} minutos y sirve una vez):\n\n{enlace}\n\n"
            "Si no fuiste tú, ignora este correo: tu contraseña no cambia.",
            f"<p>Hola {html.escape(usuario.nombre)},</p><p>Para crear una contraseña nueva en <strong>Verificador API</strong>:</p>"
            f'<p><a href="{enlace}" style="background:#336791;color:#fff;padding:10px 18px;border-radius:6px;'
            f'text-decoration:none">Crear contraseña nueva</a></p><p>El enlace vence en {RECUPERAR_MINUTOS} '
            "minutos y sirve una sola vez. Si no fuiste tú, ignora este correo.</p>",
        )
    return plantillas.TemplateResponse(request, "recuperar.html", {"centrar": True, "exito": _RESPUESTA_RECUPERAR})


@router.get("/restablecer")
def formulario_restablecer(request: Request, token: str = ""):
    error = None if leer_token_recuperacion(token) else "El enlace no es válido o ya venció. Pide uno nuevo."
    return plantillas.TemplateResponse(request, "restablecer.html", {"centrar": True, "token": token, "error": error})


@router.post("/restablecer")
def procesar_restablecer(
    request: Request,
    token: str = Form(...),
    password: str = Form(...),
    confirmacion: str = Form(...),
    db: Session = Depends(obtener_db),
):
    leido = leer_token_recuperacion(token)
    usuario = db.get(Usuario, leido[0]) if leido else None
    if usuario is None or not usuario.activo or not huella_coincide(usuario.password_hash, leido[1]):
        error, nuevo = "El enlace no es válido o ya venció. Pide uno nuevo.", None
    else:
        error, nuevo = _validar_nueva(password, confirmacion)
    if error:
        return plantillas.TemplateResponse(
            request, "restablecer.html", {"centrar": True, "token": token, "error": error}, status_code=400
        )
    usuario.password_hash = nuevo
    db.commit()
    return plantillas.TemplateResponse(
        request, "login.html", {"centrar": True, "exito": "Tu contraseña quedó actualizada. Ya puedes ingresar."}
    )


@router.get("/cuenta/contrasena")
def formulario_cambiar_contrasena(request: Request, usuario: Usuario = Depends(usuario_actual)):
    return plantillas.TemplateResponse(request, "cuenta_contrasena.html", {"usuario": usuario})


@router.post("/cuenta/contrasena")
def cambiar_contrasena(
    request: Request,
    actual: str = Form(...),
    password: str = Form(...),
    confirmacion: str = Form(...),
    usuario: Usuario = Depends(usuario_actual),
    db: Session = Depends(obtener_db),
):
    if not verificar_password(actual, usuario.password_hash):
        error, nuevo = "La contraseña actual no es correcta", None
    elif password == actual:
        error, nuevo = "La contraseña nueva debe ser distinta de la actual", None
    else:
        error, nuevo = _validar_nueva(password, confirmacion)
    if error:
        return plantillas.TemplateResponse(
            request, "cuenta_contrasena.html", {"usuario": usuario, "error": error}, status_code=400
        )
    registro = db.get(Usuario, usuario.id)
    registro.password_hash = nuevo
    db.commit()
    return plantillas.TemplateResponse(
        request, "cuenta_contrasena.html", {"usuario": usuario, "exito": "Tu contraseña quedó actualizada."}
    )
