"""Motor que corre las pruebas de una colección contra la API real,
usando la librería requests — nada de navegador ni JavaScript, solo
llamadas HTTP directas, como haría Postman/Newman por dentro."""

import time

import requests
from sqlalchemy.orm import Session

from app.models import Coleccion, Ejecucion, Prueba, ResultadoPrueba


def _url_completa(coleccion: Coleccion, prueba: Prueba) -> str:
    if prueba.ruta.startswith("http://") or prueba.ruta.startswith("https://"):
        return prueba.ruta
    base = (coleccion.url_base or "").rstrip("/")
    return f"{base}/{prueba.ruta.lstrip('/')}"


def _correr_una(coleccion: Coleccion, prueba: Prueba) -> ResultadoPrueba:
    resultado = ResultadoPrueba(nombre_prueba=prueba.nombre, prueba_id=prueba.id)
    url = _url_completa(coleccion, prueba)

    inicio = time.perf_counter()
    try:
        respuesta = requests.request(
            method=prueba.metodo,
            url=url,
            headers=prueba.headers_json or None,
            json=prueba.body_json or None,
            timeout=15,
        )
    except requests.RequestException as error:
        resultado.paso = False
        resultado.detalle_error = f"No se pudo conectar: {error}"
        resultado.tiempo_ms = (time.perf_counter() - inicio) * 1000
        return resultado

    resultado.tiempo_ms = (time.perf_counter() - inicio) * 1000
    resultado.status_obtenido = respuesta.status_code

    errores = []
    if prueba.status_esperado is not None and respuesta.status_code != prueba.status_esperado:
        errores.append(
            f"Se esperaba status {prueba.status_esperado}, llegó {respuesta.status_code}"
        )
    if prueba.contiene_esperado:
        if prueba.contiene_esperado not in respuesta.text:
            errores.append(f"La respuesta no contiene: {prueba.contiene_esperado!r}")

    resultado.paso = not errores
    resultado.detalle_error = " · ".join(errores) if errores else None
    return resultado


def ejecutar_coleccion(db: Session, coleccion: Coleccion, usuario_id: int) -> Ejecucion:
    ejecucion = Ejecucion(coleccion_id=coleccion.id, ejecutado_por_id=usuario_id)

    for prueba in coleccion.pruebas:
        resultado = _correr_una(coleccion, prueba)
        ejecucion.resultados.append(resultado)

    ejecucion.total = len(ejecucion.resultados)
    ejecucion.exitosas = sum(1 for r in ejecucion.resultados if r.paso)
    ejecucion.fallidas = ejecucion.total - ejecucion.exitosas

    db.add(ejecucion)
    db.commit()
    db.refresh(ejecucion)
    return ejecucion
