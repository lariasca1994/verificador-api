"""Entorno de pruebas: SQLite local y sin correos reales.

Las variables se fijan ANTES de importar la app; load_dotenv no pisa las que
ya existen, así que el .env local (con la base y Brevo de verdad) no se usa.
"""

import os
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parent.parent
BASE_PRUEBAS = RAIZ / "tests" / ".pruebas.sqlite"
if BASE_PRUEBAS.exists():
    BASE_PRUEBAS.unlink()

os.environ["DATABASE_URL"] = f"sqlite:///{BASE_PRUEBAS.as_posix()}"
os.environ["JWT_SECRET"] = "secreto-solo-para-pruebas-automaticas"
os.environ["BREVO_API_KEY"] = ""
os.environ["BREVO_REMITENTE"] = ""
os.environ["URL_PUBLICA"] = "http://prueba.local"
os.chdir(RAIZ)  # las plantillas se buscan en app/templates

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture
def cliente():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def correos(monkeypatch):
    """Captura los correos en vez de enviarlos."""
    from app import correo

    enviados = []

    def falso(destino, nombre, asunto, texto, html):
        enviados.append({"destino": destino, "asunto": asunto, "texto": texto, "html": html})
        return True

    monkeypatch.setattr(correo, "enviar", falso)
    return enviados


def pytest_sessionfinish(session, exitstatus):
    from app.database import engine

    engine.dispose()
    if BASE_PRUEBAS.exists():
        BASE_PRUEBAS.unlink()
