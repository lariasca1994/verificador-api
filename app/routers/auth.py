from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import obtener_db
from app.models import Usuario
from app.seguridad import NOMBRE_COOKIE, crear_token, hashear_password, verificar_password

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
