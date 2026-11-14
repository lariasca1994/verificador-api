import logging

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.exc import InterfaceError, OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

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
    # Columnas agregadas después de crear la tabla (create_all no altera tablas).
    with engine.begin() as conexion:
        conexion.execute(text("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS mfa JSONB"))
except (OperationalError, InterfaceError) as error:
    registro.warning("PostgreSQL no disponible al arrancar: %s", type(error).__name__)

app = FastAPI(title="Verificador de APIs")

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


@app.exception_handler(StarletteHTTPException)
async def error_http(request: Request, exc: StarletteHTTPException):
    """404 con página propia (no consulta la base); los demás códigos siguen como siempre."""
    if exc.status_code == 404 and not request.url.path.startswith("/api"):
        return plantillas.TemplateResponse(
            request, "no_encontrada.html", {"ruta": request.url.path[:80]}, status_code=404
        )
    return await http_exception_handler(request, exc)


# Aplicación instalable (PWA). El service worker se sirve desde la raíz para controlar todo el
# sitio; no se guarda en caché del navegador para que cada versión llegue al momento.
_PWA = "app/static/pwa"


@app.get("/sw.js", include_in_schema=False)
def service_worker():
    return FileResponse(f"{_PWA}/sw.js", media_type="text/javascript", headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"})


@app.get("/manifest.webmanifest", include_in_schema=False)
def manifiesto():
    return FileResponse(f"{_PWA}/manifest.webmanifest", media_type="application/manifest+json")


@app.get("/offline.html", include_in_schema=False)
def sin_conexion():
    return FileResponse(f"{_PWA}/offline.html", media_type="text/html")


app.include_router(web.router)
app.include_router(auth.router)
app.include_router(colecciones.router)
app.include_router(ejecuciones.router)
app.include_router(usuarios.router)
