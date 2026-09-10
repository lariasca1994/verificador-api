from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.database import Base, engine
from app.routers import auth, colecciones, ejecuciones, web

# Sin Alembic por ahora, a propósito: para el tamaño de este proyecto,
# crear las tablas que falten al arrancar (idempotente: no toca las que
# ya existen) es suficiente y evita añadir una herramienta de migraciones
# antes de tener datos reales que migrar.
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Verificador API")

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(web.router)
app.include_router(auth.router)
app.include_router(colecciones.router)
app.include_router(ejecuciones.router)
