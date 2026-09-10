from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates

from app.models import Usuario
from app.seguridad import usuario_opcional

router = APIRouter()
plantillas = Jinja2Templates(directory="app/templates")


@router.get("/")
def inicio(request: Request, usuario: Usuario | None = Depends(usuario_opcional)):
    """Página pública: cualquier visitante debe entender de qué trata el
    proyecto antes de que se le pida iniciar sesión."""
    return plantillas.TemplateResponse(request, "inicio.html", {"usuario": usuario})
