import logging

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import InterfaceError, OperationalError

from app.database import Base, engine
from app.routers import auth, colecciones, ejecuciones, usuarios, web

registro = logging.getLogger("verificador")

# Sin Alembic por ahora, a propósito: para el tamaño de este proyecto,
# crear las tablas que falten al arrancar (idempotente: no toca las que
# ya existen) es suficiente y evita añadir una herramienta de migraciones
# antes de tener datos reales que migrar.
# Si la base no responde al arrancar (Neon suspendido o sin cuota), la app
# arranca igual: las peticiones muestran la pantalla de mantenimiento en vez
# de un error 502 de la plataforma.
try:
    Base.metadata.create_all(bind=engine)
except (OperationalError, InterfaceError) as error:
    registro.warning("PostgreSQL no disponible al arrancar: %s", type(error).__name__)

app = FastAPI(title="Verificador API")

app.mount("/static", StaticFiles(directory="app/static"), name="static")

plantillas = Jinja2Templates(directory="app/templates")


@app.exception_handler(OperationalError)
@app.exception_handler(InterfaceError)
def base_no_disponible(request: Request, exc: Exception):
    """PostgreSQL apagado, sin cuota o inalcanzable: pantalla de mantenimiento (503)."""
    registro.warning("PostgreSQL no disponible: %s", type(exc).__name__)
    return plantillas.TemplateResponse(
        request, "mantenimiento.html", status_code=503, headers={"Retry-After": "300"}
    )


app.include_router(web.router)
app.include_router(auth.router)
app.include_router(colecciones.router)
app.include_router(ejecuciones.router)
app.include_router(usuarios.router)
