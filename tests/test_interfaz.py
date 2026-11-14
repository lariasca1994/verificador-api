"""Interfaz: menú lateral, tableros, aplicación instalable (PWA) y página 404 propia."""

import base64
import secrets
import time

import pytest

from app import mfa
from app.database import SessionLocal
from app.models import Usuario
from app.seguridad import hashear_password

CLAVE = "clave-de-prueba-1"


@pytest.fixture
def sesion(cliente):
    """Cliente con la sesión abierta (contraseña + código de la app)."""
    secreto = base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")
    db = SessionLocal()
    usuario = Usuario(nombre="Ana Pérez", email=f"ana{secrets.token_hex(4)}@ejemplo.com",
                      password_hash=hashear_password(CLAVE), rol="usuario",
                      mfa={"totp": mfa._cifrar(secreto), "preferido": "totp"})
    db.add(usuario)
    db.commit()
    email = usuario.email
    db.close()
    cliente.post("/login", data={"email": email, "password": CLAVE}, follow_redirects=False)
    r = cliente.post("/verificacion", data={"metodo": "totp", "codigo": mfa._totp(secreto, int(time.time()) // 30)},
                     follow_redirects=False)
    assert r.status_code == 303
    return cliente


def test_menu_lateral_con_las_mismas_opciones(sesion):
    html = sesion.get("/colecciones").text
    assert 'class="menu-nav"' in html and 'href="/colecciones"' in html
    assert 'href="/cuenta/contrasena"' in html and 'href="/cuenta/seguridad"' in html
    assert html.count('action="/logout" method="post"') == 2  # menú y hoja "Más"
    assert 'class="hoja-mas"' in html
    assert 'aria-current="page"' in html
    assert 'href="/admin/usuarios"' not in html  # solo el administrador


def test_lista_de_colecciones_con_franja(sesion):
    sesion.post("/colecciones/nueva", data={"nombre": "API pública", "descripcion": "Smoke"})
    html = sesion.get("/colecciones").text
    assert 'class="franja mb-6"' in html and "Pruebas definidas" in html


def test_pwa_service_worker_manifiesto_y_sin_conexion(cliente):
    sw = cliente.get("/sw.js")
    assert sw.status_code == 200 and "javascript" in sw.headers["content-type"]
    assert sw.headers["cache-control"] == "no-cache"
    assert "/colecciones" not in sw.text and "/api" not in sw.text.split("NUNCA")[0]
    manifiesto = cliente.get("/manifest.webmanifest")
    assert manifiesto.status_code == 200 and manifiesto.json()["display"] == "standalone"
    for icono in manifiesto.json()["icons"]:
        assert cliente.get(icono["src"]).status_code == 200
    sin_red = cliente.get("/offline.html")
    assert sin_red.status_code == 200 and "Sin conexión" in sin_red.text


def test_404_propia(cliente):
    r = cliente.get("/no-existe-esta-ruta")
    assert r.status_code == 404
    assert "Esta ruta no responde 200" in r.text and "/no-existe-esta-ruta" in r.text


def test_otros_errores_http_siguen_igual(cliente):
    assert cliente.post("/sw.js").status_code == 405
