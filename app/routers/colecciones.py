import json

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import obtener_db
from app.dependencias import obtener_coleccion_propia, obtener_coleccion_visible
from app.models import Coleccion, Prueba, Usuario
from app.seguridad import usuario_actual

router = APIRouter(prefix="/colecciones")
plantillas = Jinja2Templates(directory="app/templates")


@router.get("")
def listar(
    request: Request,
    db: Session = Depends(obtener_db),
    usuario: Usuario = Depends(usuario_actual),
):
    if usuario.es_admin:
        # Solo lectura: el admin ve las de todos, con el dueño visible.
        colecciones = db.query(Coleccion).order_by(Coleccion.creado_en.desc()).all()
    else:
        colecciones = (
            db.query(Coleccion)
            .filter(Coleccion.propietario_id == usuario.id)
            .order_by(Coleccion.creado_en.desc())
            .all()
        )
    return plantillas.TemplateResponse(
        request,
        "colecciones/lista.html",
        {"usuario": usuario, "colecciones": colecciones},
    )


@router.get("/nueva")
def formulario_nueva(request: Request, usuario: Usuario = Depends(usuario_actual)):
    return plantillas.TemplateResponse(
        request, "colecciones/formulario.html", {"usuario": usuario}
    )


@router.post("/nueva")
def crear(
    nombre: str = Form(...),
    descripcion: str = Form(""),
    url_base: str = Form(""),
    db: Session = Depends(obtener_db),
    usuario: Usuario = Depends(usuario_actual),
):
    coleccion = Coleccion(
        nombre=nombre.strip(),
        descripcion=descripcion.strip() or None,
        url_base=url_base.strip() or None,
        propietario_id=usuario.id,
    )
    db.add(coleccion)
    db.commit()
    db.refresh(coleccion)
    return RedirectResponse(url=f"/colecciones/{coleccion.id}", status_code=303)


@router.get("/{coleccion_id}")
def detalle(
    request: Request,
    usuario: Usuario = Depends(usuario_actual),
    coleccion: Coleccion = Depends(obtener_coleccion_visible),
    db: Session = Depends(obtener_db),
):
    es_propia = coleccion.propietario_id == usuario.id
    ejecuciones = sorted(coleccion.ejecuciones, key=lambda e: e.fecha, reverse=True)[:10]
    return plantillas.TemplateResponse(
        request,
        "colecciones/detalle.html",
        {
            "usuario": usuario,
            "coleccion": coleccion,
            "es_propia": es_propia,
            "ejecuciones": ejecuciones,
        },
    )


@router.get("/{coleccion_id}/pruebas/nueva")
def formulario_nueva_prueba(
    request: Request,
    usuario: Usuario = Depends(usuario_actual),
    coleccion: Coleccion = Depends(obtener_coleccion_propia),
):
    return plantillas.TemplateResponse(
        request, "colecciones/prueba_formulario.html", {"usuario": usuario, "coleccion": coleccion}
    )


@router.post("/{coleccion_id}/pruebas/nueva")
def crear_prueba(
    nombre: str = Form(...),
    metodo: str = Form("GET"),
    ruta: str = Form(...),
    headers_json: str = Form(""),
    body_json: str = Form(""),
    status_esperado: str = Form(""),
    contiene_esperado: str = Form(""),
    db: Session = Depends(obtener_db),
    coleccion: Coleccion = Depends(obtener_coleccion_propia),
):
    def _parsear_json(texto: str):
        texto = texto.strip()
        if not texto:
            return None
        return json.loads(texto)

    prueba = Prueba(
        coleccion_id=coleccion.id,
        nombre=nombre.strip(),
        metodo=metodo.upper().strip(),
        ruta=ruta.strip(),
        headers_json=_parsear_json(headers_json),
        body_json=_parsear_json(body_json),
        status_esperado=int(status_esperado) if status_esperado.strip() else None,
        contiene_esperado=contiene_esperado.strip() or None,
        orden=len(coleccion.pruebas),
    )
    db.add(prueba)
    db.commit()
    return RedirectResponse(url=f"/colecciones/{coleccion.id}", status_code=303)


@router.post("/{coleccion_id}/pruebas/{prueba_id}/borrar")
def borrar_prueba(
    prueba_id: int,
    db: Session = Depends(obtener_db),
    coleccion: Coleccion = Depends(obtener_coleccion_propia),
):
    prueba = next((p for p in coleccion.pruebas if p.id == prueba_id), None)
    if prueba:
        db.delete(prueba)
        db.commit()
    return RedirectResponse(url=f"/colecciones/{coleccion.id}", status_code=303)
