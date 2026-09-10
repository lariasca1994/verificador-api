from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import obtener_db
from app.models import Coleccion, Usuario
from app.seguridad import usuario_actual


def obtener_coleccion_visible(
    coleccion_id: int,
    db: Session = Depends(obtener_db),
    usuario: Usuario = Depends(usuario_actual),
) -> Coleccion:
    """Trae la colección si el usuario puede VERLA: es suya, o es admin.

    El admin puede mirar cualquier colección (y sus ejecuciones), pero
    las rutas que crean/editan/ejecutan usan obtener_coleccion_propia en
    su lugar — el admin no gestiona nada ajeno, solo mira.
    """
    coleccion = db.get(Coleccion, coleccion_id)
    if coleccion is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Colección no encontrada")
    if coleccion.propietario_id != usuario.id and not usuario.es_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No tienes acceso a esta colección")
    return coleccion


def obtener_coleccion_propia(
    coleccion_id: int,
    db: Session = Depends(obtener_db),
    usuario: Usuario = Depends(usuario_actual),
) -> Coleccion:
    """Para crear/editar/ejecutar: tiene que ser el dueño, sin excepción
    para el admin — su rol es de solo lectura sobre lo ajeno."""
    coleccion = db.get(Coleccion, coleccion_id)
    if coleccion is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Colección no encontrada")
    if coleccion.propietario_id != usuario.id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Solo el dueño de la colección puede modificarla o ejecutarla",
        )
    return coleccion
