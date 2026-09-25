from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import obtener_db
from app.models import Ejecucion, Usuario
from app.seguridad import usuario_actual

router = APIRouter(prefix="/admin/usuarios")
plantillas = Jinja2Templates(directory="app/templates")


def _exigir_admin(usuario: Usuario) -> None:
    # No hay un guard reusable de FastAPI para esto en el proyecto (a
    # diferencia de obtener_coleccion_propia/visible, acá no hace falta
    # resolver un recurso por id), así que se replica el mismo chequeo
    # inline que ya usan colecciones.py/ejecuciones.py con es_admin.
    if not usuario.es_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo un admin puede gestionar usuarios")


@router.get("")
def listar(
    request: Request,
    db: Session = Depends(obtener_db),
    usuario: Usuario = Depends(usuario_actual),
):
    _exigir_admin(usuario)
    usuarios = db.query(Usuario).order_by(Usuario.creado_en.desc()).all()
    return plantillas.TemplateResponse(
        request,
        "admin/usuarios.html",
        {"usuario": usuario, "usuarios": usuarios},
    )


@router.post("/{usuario_id}/suspender")
def suspender(
    usuario_id: int,
    db: Session = Depends(obtener_db),
    usuario: Usuario = Depends(usuario_actual),
):
    _exigir_admin(usuario)
    if usuario_id == usuario.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No podés suspender tu propia cuenta")
    objetivo = db.get(Usuario, usuario_id)
    if objetivo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario no encontrado")
    objetivo.activo = False
    db.commit()
    return RedirectResponse(url="/admin/usuarios", status_code=303)


@router.post("/{usuario_id}/reactivar")
def reactivar(
    usuario_id: int,
    db: Session = Depends(obtener_db),
    usuario: Usuario = Depends(usuario_actual),
):
    _exigir_admin(usuario)
    objetivo = db.get(Usuario, usuario_id)
    if objetivo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario no encontrado")
    objetivo.activo = True
    db.commit()
    return RedirectResponse(url="/admin/usuarios", status_code=303)


@router.post("/{usuario_id}/eliminar")
def eliminar(
    usuario_id: int,
    db: Session = Depends(obtener_db),
    usuario: Usuario = Depends(usuario_actual),
):
    _exigir_admin(usuario)
    if usuario_id == usuario.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No podés eliminar tu propia cuenta")
    objetivo = db.get(Usuario, usuario_id)
    if objetivo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario no encontrado")

    # Coleccion.propietario_id y Ejecucion.ejecutado_por_id son FKs
    # NOT NULL hacia usuarios.id, y Usuario.colecciones no tiene cascade
    # configurado (a diferencia de Coleccion -> Prueba/Ejecucion, que sí
    # usa cascade="all, delete-orphan"). Borrar un usuario con colecciones
    # propias, o con ejecuciones registradas a su nombre (por ejemplo, un
    # admin que ejecutó una colección ajena), violaría esa FK y volaría
    # con un 500 de integridad referencial. En vez de cascadear el borrado
    # (destruiría colecciones/pruebas/ejecuciones sin que el admin lo haya
    # pedido explícitamente), se opta por el camino simple y no
    # destructivo: no permitir eliminar mientras existan esos vínculos, y
    # sugerir suspender la cuenta en su lugar.
    tiene_colecciones = bool(objetivo.colecciones)
    tiene_ejecuciones = (
        db.query(Ejecucion).filter(Ejecucion.ejecutado_por_id == usuario_id).first() is not None
    )
    if tiene_colecciones or tiene_ejecuciones:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "No se puede eliminar: el usuario tiene colecciones o ejecuciones "
            "registradas. Suspendé la cuenta en su lugar.",
        )

    db.delete(objetivo)
    db.commit()
    return RedirectResponse(url="/admin/usuarios", status_code=303)
