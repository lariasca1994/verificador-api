from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.models import Usuario
from app.seguridad import usuario_opcional

router = APIRouter()
plantillas = Jinja2Templates(directory="app/templates")


@router.get("/")
def inicio(request: Request, usuario: Usuario | None = Depends(usuario_opcional)):
    """La portada de acceso es la primera pantalla, igual que en el resto
    del portafolio: explica el proyecto junto al formulario. Con sesión
    abierta se va directo a las colecciones."""
    if usuario:
        return RedirectResponse(url="/colecciones", status_code=303)
    return plantillas.TemplateResponse(request, "login.html", {"error": None})


@router.get("/favicon.ico", include_in_schema=False)
def favicon():
    # Los navegadores lo piden en la raíz aunque la página declare otro ícono.
    return FileResponse("app/static/iconos/favicon.ico")
