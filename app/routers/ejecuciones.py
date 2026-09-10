from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import obtener_db
from app.dependencias import obtener_coleccion_propia
from app.ejecutor import ejecutar_coleccion
from app.models import Coleccion, Ejecucion, Usuario
from app.seguridad import usuario_actual

router = APIRouter()
plantillas = Jinja2Templates(directory="app/templates")


@router.post("/colecciones/{coleccion_id}/ejecutar")
def ejecutar(
    db: Session = Depends(obtener_db),
    usuario: Usuario = Depends(usuario_actual),
    coleccion: Coleccion = Depends(obtener_coleccion_propia),
):
    ejecucion = ejecutar_coleccion(db, coleccion, usuario.id)
    return RedirectResponse(url=f"/ejecuciones/{ejecucion.id}", status_code=303)


@router.get("/ejecuciones/{ejecucion_id}")
def detalle(
    ejecucion_id: int,
    request: Request,
    db: Session = Depends(obtener_db),
    usuario: Usuario = Depends(usuario_actual),
):
    ejecucion = db.get(Ejecucion, ejecucion_id)
    if ejecucion is None:
        return RedirectResponse(url="/colecciones", status_code=303)

    es_propia = ejecucion.coleccion.propietario_id == usuario.id
    if not es_propia and not usuario.es_admin:
        return RedirectResponse(url="/colecciones", status_code=303)

    return plantillas.TemplateResponse(
        request,
        "ejecuciones/detalle.html",
        {"usuario": usuario, "ejecucion": ejecucion, "coleccion": ejecucion.coleccion},
    )
