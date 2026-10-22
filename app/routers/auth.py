from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import obtener_db
from app.models import Usuario
import html
import threading
import time

from app import correo, mfa
from app.seguridad import (
    COOKIE_MFA,
    MFA_MINUTOS,
    NOMBRE_COOKIE,
    crear_token_mfa,
    leer_token_mfa,
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

    if not usuario.activo:
        return plantillas.TemplateResponse(
            request, "login.html", {"error": "Esta cuenta está suspendida", "centrar": True}, status_code=403
        )
    # La contraseña sola no abre sesión: falta el segundo paso.
    if mfa.preferido(usuario) == "correo":
        mfa.enviar_codigo(usuario)
    return _pase_mfa(usuario)


def _abrir_sesion(usuario: Usuario) -> RedirectResponse:
    respuesta = RedirectResponse(url="/colecciones", status_code=303)
    respuesta.set_cookie(NOMBRE_COOKIE, crear_token(usuario.id), httponly=True, samesite="lax", max_age=8 * 3600)
    respuesta.delete_cookie(COOKIE_MFA)
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

    # Antes de entrar, la cuenta elige su verificación en dos pasos.
    return _pase_mfa(usuario)


# ── Verificación en dos pasos ──────────────────────────────────────────────


def _pase_mfa(usuario: Usuario) -> RedirectResponse:
    respuesta = RedirectResponse(url="/verificacion", status_code=303)
    respuesta.set_cookie(COOKIE_MFA, crear_token_mfa(usuario.id), httponly=True, samesite="lax",
                         max_age=MFA_MINUTOS * 60)
    return respuesta


def _usuario_en_verificacion(request: Request, db: Session) -> Usuario | None:
    usuario_id = leer_token_mfa(request.cookies.get(COOKIE_MFA))
    usuario = db.get(Usuario, usuario_id) if usuario_id else None
    return usuario if usuario and usuario.activo else None


def _vencido() -> RedirectResponse:
    return RedirectResponse(url="/login", status_code=303)


def _pantalla_mfa(request: Request, usuario: Usuario, metodo: str | None = None, status_code: int = 200, **contexto):
    if not mfa.configurado(usuario):
        return plantillas.TemplateResponse(request, "mfa_elegir.html",
                                           {"metodos": mfa.METODOS, "centrar": True, **contexto}, status_code=status_code)
    metodo = metodo if metodo in mfa.metodos_activos(usuario) else mfa.preferido(usuario)
    otros = [m for m in mfa.metodos_activos(usuario) if m != metodo]
    return plantillas.TemplateResponse(
        request, "mfa_verificar.html",
        {"metodo": metodo, "otro": otros[0] if otros else None, "metodos": mfa.METODOS,
         "email": usuario.email, "centrar": True, **contexto},
        status_code=status_code,
    )


def _iniciar_metodo(request: Request, usuario: Usuario, metodo: str, accion: str, vista: str, **contexto):
    if metodo == "totp":
        return _confirmar_metodo(request, usuario, metodo, accion, vista, app=mfa.iniciar_totp(usuario), **contexto)
    if not mfa.enviar_codigo(usuario):
        contexto["error"] = "Pediste varios códigos seguidos. Espera unos minutos."
    return _confirmar_metodo(request, usuario, "correo", accion, vista, **contexto)


def _confirmar_metodo(request: Request, usuario: Usuario, metodo: str, accion: str, vista: str, **contexto):
    plantilla = "mfa_confirmar.html" if vista == "acceso" else "cuenta_seguridad.html"
    base = {"metodo": metodo, "accion": accion, "metodos": mfa.METODOS, "email": usuario.email, "centrar": vista == "acceso"}
    if vista != "acceso":
        base.update(_contexto_seguridad(usuario))
    return plantillas.TemplateResponse(request, plantilla, {**base, **contexto},
                                       status_code=401 if "error" in contexto else 200)


def _contexto_seguridad(usuario: Usuario) -> dict:
    return {"usuario": usuario, "activos": mfa.metodos_activos(usuario), "preferido": mfa.preferido(usuario)}


@router.get("/verificacion")
def form_verificacion(request: Request, metodo: str | None = None, db: Session = Depends(obtener_db)):
    usuario = _usuario_en_verificacion(request, db)
    return _pantalla_mfa(request, usuario, metodo) if usuario else _vencido()


@router.post("/verificacion")
def procesar_verificacion(request: Request, metodo: str = Form(...), codigo: str = Form(...),
                          db: Session = Depends(obtener_db)):
    usuario = _usuario_en_verificacion(request, db)
    if not usuario:
        return _vencido()
    if not mfa.verificar(usuario, metodo, codigo):
        return _pantalla_mfa(request, usuario, metodo, status_code=401, error="El código no es correcto o ya venció.")
    return _abrir_sesion(usuario)


@router.post("/verificacion/correo")
def reenviar_codigo(request: Request, db: Session = Depends(obtener_db)):
    usuario = _usuario_en_verificacion(request, db)
    if not usuario:
        return _vencido()
    if not mfa.enviar_codigo(usuario):
        return _pantalla_mfa(request, usuario, "correo", error="Pediste varios códigos seguidos. Espera unos minutos.")
    return _pantalla_mfa(request, usuario, "correo", exito=f"Te enviamos un código a {usuario.email}.")


@router.post("/verificacion/configurar")
def configurar_metodo(request: Request, metodo: str = Form(...), db: Session = Depends(obtener_db)):
    usuario = _usuario_en_verificacion(request, db)
    if not usuario:
        return _vencido()
    return _iniciar_metodo(request, usuario, metodo, "/verificacion/activar", "acceso")


@router.post("/verificacion/activar")
def activar_metodo(request: Request, metodo: str = Form(...), codigo: str = Form(...),
                   db: Session = Depends(obtener_db)):
    usuario = _usuario_en_verificacion(request, db)
    if not usuario:
        return _vencido()
    if mfa.configurado(usuario):  # ya tiene uno: este paso es solo para la primera vez
        return _pantalla_mfa(request, usuario)
    activado = mfa.activar_totp(usuario, codigo) if metodo == "totp" else mfa.activar_correo(usuario, codigo)
    if not activado:
        return _confirmar_metodo(request, usuario, metodo, "/verificacion/activar", "acceso",
                                 error="El código no es correcto o ya venció.")
    return _abrir_sesion(usuario)


@router.get("/cuenta/seguridad")
def form_seguridad(request: Request, usuario: Usuario = Depends(usuario_actual)):
    return plantillas.TemplateResponse(request, "cuenta_seguridad.html",
                                       {"metodos": mfa.METODOS, **_contexto_seguridad(usuario)})


@router.post("/cuenta/seguridad/agregar")
def agregar_metodo(request: Request, metodo: str = Form(...), usuario: Usuario = Depends(usuario_actual)):
    if metodo not in mfa.METODOS or metodo in mfa.metodos_activos(usuario):
        return RedirectResponse(url="/cuenta/seguridad", status_code=303)
    return _iniciar_metodo(request, usuario, metodo, "/cuenta/seguridad/activar", "cuenta")


@router.post("/cuenta/seguridad/activar")
def activar_en_perfil(request: Request, metodo: str = Form(...), codigo: str = Form(...),
                      usuario: Usuario = Depends(usuario_actual)):
    activado = mfa.activar_totp(usuario, codigo) if metodo == "totp" else mfa.activar_correo(usuario, codigo)
    if not activado:
        return _confirmar_metodo(request, usuario, metodo, "/cuenta/seguridad/activar", "cuenta",
                                 error="El código no es correcto o ya venció.")
    return plantillas.TemplateResponse(request, "cuenta_seguridad.html", {
        "metodos": mfa.METODOS, **_contexto_seguridad(usuario),
        "exito": f"{mfa.METODOS[metodo]} quedó activada como segundo paso.",
    })


@router.post("/cuenta/seguridad/preferido")
def cambiar_preferido(metodo: str = Form(...), usuario: Usuario = Depends(usuario_actual)):
    mfa.elegir_preferido(usuario, metodo)
    return RedirectResponse(url="/cuenta/seguridad", status_code=303)


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
