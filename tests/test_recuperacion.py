"""Recuperación de contraseña, "Perdí mi autenticador", cierre de sesiones y nombre visible."""

import base64
import re
import secrets
import time

import pytest

from app import correo, mfa
from app.database import SessionLocal
from app.models import Usuario
from app.seguridad import crear_token_recuperacion, hashear_password

CLAVE = "clave-de-prueba-1"


def _secreto_nuevo() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _codigo(secreto: str, desfase: int = 0) -> str:
    return mfa._totp(secreto, int(time.time()) // 30 + desfase)


@pytest.fixture
def cuenta():
    """Cuenta con app autenticadora activa (sin el método correo)."""
    secreto = _secreto_nuevo()
    db = SessionLocal()
    usuario = Usuario(nombre="Ana Pérez", email=f"ana{secrets.token_hex(4)}@ejemplo.com",
                      password_hash=hashear_password(CLAVE), rol="usuario",
                      mfa={"totp": mfa._cifrar(secreto), "preferido": "totp"})
    db.add(usuario)
    db.commit()
    datos = {"id": usuario.id, "email": usuario.email, "secreto": secreto}
    db.close()
    return datos


def _estado(usuario_id: int) -> dict:
    db = SessionLocal()
    try:
        return dict(db.get(Usuario, usuario_id).mfa or {})
    finally:
        db.close()


def _hash(usuario_id: int) -> str:
    db = SessionLocal()
    try:
        return db.get(Usuario, usuario_id).password_hash
    finally:
        db.close()


def _contrasena(cliente, cuenta, clave=CLAVE):
    r = cliente.post("/login", data={"email": cuenta["email"], "password": clave}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/verificacion"


def _ingresar(cliente, cuenta, clave=CLAVE, desfase=0):
    _contrasena(cliente, cuenta, clave)
    r = cliente.post("/verificacion", data={"metodo": "totp", "codigo": _codigo(cuenta["secreto"], desfase)},
                     follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/colecciones"


# ── Nombre visible ─────────────────────────────────────────────────────────


def test_nombre_visible_en_correos_y_qr(monkeypatch, cuenta):
    assert correo.NOMBRE == "Verificador de APIs"
    doc = correo.documento("Asunto", "<p>hola</p>")
    assert doc.count("Verificador de APIs") == 2  # encabezado y pie
    assert "Verificador API<" not in doc

    # Remitente: el nombre descriptivo va en el "sender" de Brevo.
    capturado = {}

    class Respuesta:
        status = 201

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def falso_urlopen(pedido, timeout=0):
        capturado["cuerpo"] = pedido.data.decode()
        return Respuesta()

    monkeypatch.setattr(correo, "BREVO_API_KEY", "clave-falsa")
    monkeypatch.setattr(correo, "BREVO_REMITENTE", "remitente@ejemplo.com")
    monkeypatch.setattr(correo.urllib.request, "urlopen", falso_urlopen)
    assert correo.enviar("usuario@ejemplo.com", "Ana", "Asunto", "texto", "<p>x</p>")
    assert '"name": "Verificador de APIs"' in capturado["cuerpo"]

    # Emisor (issuer) del QR de la app autenticadora.
    uris = []
    monkeypatch.setattr(mfa.segno, "make", lambda uri, **k: uris.append(uri) or type(
        "Q", (), {"svg_inline": lambda self, **kw: "<svg/>"})())
    db = SessionLocal()
    mfa.iniciar_totp(db.get(Usuario, cuenta["id"]))
    db.close()
    assert "otpauth://totp/Verificador%20de%20APIs:" in uris[0]
    assert "issuer=Verificador%20de%20APIs" in uris[0]


def test_asunto_de_los_correos_con_el_nombre(cliente, cuenta, correos):
    cliente.post("/recuperar", data={"email": cuenta["email"]})
    _contrasena(cliente, cuenta)
    cliente.post("/verificacion/recuperar")
    assert len(correos) == 2
    assert all("Verificador de APIs" in c["asunto"] for c in correos)


# ── Olvidé mi contraseña ───────────────────────────────────────────────────


def test_respuesta_neutra(cliente, cuenta, correos):
    existe = cliente.post("/recuperar", data={"email": cuenta["email"]})
    no_existe = cliente.post("/recuperar", data={"email": "nadie@ejemplo.com"})
    assert existe.status_code == no_existe.status_code == 200
    assert "Si el correo pertenece a una cuenta" in existe.text
    assert existe.text == no_existe.text
    assert len(correos) == 1 and correos[0]["destino"] == cuenta["email"]


def test_paso_2_solo_nueva_y_confirmar(cliente, cuenta):
    token = crear_token_recuperacion(cuenta["id"], _hash(cuenta["id"]))
    r = cliente.get(f"/restablecer?token={token}")
    campos = set(re.findall(r'<input[^>]*name="([^"]+)"', r.text))
    assert campos == {"token", "password", "confirmacion"}


def test_enlace_de_un_solo_uso_cierra_sesiones_y_mantiene_mfa(cliente, cuenta, correos):
    _ingresar(cliente, cuenta)
    assert cliente.get("/colecciones").status_code == 200
    sesion_vieja = cliente.cookies.get("sesion")

    cliente.post("/recuperar", data={"email": cuenta["email"]})
    token = re.search(r"token=([\w.\-]+)", correos[-1]["texto"]).group(1)
    r = cliente.post("/restablecer", data={"token": token, "password": "otra-clave-9", "confirmacion": "otra-clave-9"})
    assert r.status_code == 200 and "quedó actualizada" in r.text

    # La sesión abierta antes del cambio ya no sirve.
    cliente.cookies.clear()
    cliente.cookies.set("sesion", sesion_vieja)
    assert cliente.get("/colecciones").status_code == 401
    cliente.cookies.clear()

    # El enlace no se puede volver a usar.
    assert "no es válido o ya venció" in cliente.get(f"/restablecer?token={token}").text
    r = cliente.post("/restablecer", data={"token": token, "password": "tercera-1", "confirmacion": "tercera-1"})
    assert r.status_code == 400

    # La verificación en dos pasos sigue activa con la contraseña nueva.
    assert mfa.metodos_activos(type("U", (), {"mfa": _estado(cuenta["id"])})()) == ["totp"]
    _contrasena(cliente, cuenta, "otra-clave-9")
    assert cliente.get("/colecciones").status_code == 401  # aún sin sesión: falta el código
    _ingresar(cliente, cuenta, "otra-clave-9", desfase=1)


def test_enlace_vencido(cliente, cuenta, monkeypatch):
    import datetime

    import jwt

    from app import seguridad

    vencido = jwt.encode({"sub": str(cuenta["id"]), "h": seguridad._huella(_hash(cuenta["id"])), "aud": "recuperar",
                          "exp": datetime.datetime.utcnow() - datetime.timedelta(minutes=1)},
                         seguridad.JWT_SECRET, algorithm="HS256")
    r = cliente.post("/restablecer", data={"token": vencido, "password": "nueva-clave-1", "confirmacion": "nueva-clave-1"})
    assert r.status_code == 400


def test_cambiar_contrasena_cierra_las_otras_sesiones(cliente, cuenta):
    _ingresar(cliente, cuenta)
    otra = cliente.cookies.get("sesion")
    r = cliente.post("/cuenta/contrasena", data={"actual": CLAVE, "password": "nueva-clave-2", "confirmacion": "nueva-clave-2"})
    assert r.status_code == 200
    assert cliente.get("/colecciones").status_code == 200  # esta sesión sigue
    cliente.cookies.clear()
    cliente.cookies.set("sesion", otra)
    assert cliente.get("/colecciones").status_code == 401  # la otra quedó cerrada


# ── Perdí mi autenticador ──────────────────────────────────────────────────


def _pedir_codigo(cliente, cuenta, correos) -> str:
    r = cliente.post("/verificacion/recuperar")
    assert r.status_code == 200
    return re.search(r"\b(\d{6})\b", correos[-1]["texto"]).group(1)


def test_enlace_siempre_visible(cliente, cuenta):
    _contrasena(cliente, cuenta)
    r = cliente.get("/verificacion")
    assert 'action="/verificacion/recuperar"' in r.text and "Perdí mi autenticador" in r.text


def test_recuperacion_completa_reemplaza_la_app_solo_al_activar(cliente, cuenta, correos):
    _contrasena(cliente, cuenta)
    assert "correo" not in mfa.metodos_activos(type("U", (), {"mfa": _estado(cuenta["id"])})())
    codigo = _pedir_codigo(cliente, cuenta, correos)
    assert correos[-1]["destino"] == cuenta["email"]
    assert "15 minutos" in correos[-1]["texto"]

    r = cliente.post("/verificacion/recuperar/codigo", data={"codigo": codigo}, follow_redirects=False)
    assert r.status_code == 200
    assert "Configura tu app autenticadora nueva" in r.text and "<svg" in r.text
    assert "sesion" not in r.cookies and cliente.cookies.get("sesion") is None  # todavía sin sesión
    assert cliente.get("/colecciones").status_code == 401

    estado = _estado(cuenta["id"])
    assert mfa._descifrar(estado["totp"]) == cuenta["secreto"]  # la app anterior sigue hasta activar la nueva
    nuevo = mfa._descifrar(estado["totp_pendiente"])

    # Código errado: no abre sesión, vuelve a mostrar el QR y no reemplaza nada.
    r = cliente.post("/verificacion/recuperar/activar", data={"codigo": "000000"}, follow_redirects=False)
    assert r.status_code == 401 and "<svg" in r.text
    assert mfa._descifrar(_estado(cuenta["id"])["totp"]) == cuenta["secreto"]

    r = cliente.post("/verificacion/recuperar/activar", data={"codigo": _codigo(nuevo, 1)}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/colecciones"
    assert cliente.get("/colecciones").status_code == 200
    final = _estado(cuenta["id"])
    assert mfa._descifrar(final["totp"]) == nuevo and not final.get("totp_pendiente")
    assert not mfa.recuperacion_vigente(type("U", (), {"mfa": final})())


def test_activar_sin_codigo_de_recuperacion_no_sirve(cliente, cuenta):
    _contrasena(cliente, cuenta)
    r = cliente.post("/verificacion/recuperar/activar", data={"codigo": "123456"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/verificacion"
    assert cliente.get("/colecciones").status_code == 401


def test_sin_pase_de_contrasena_no_envia(cliente, cuenta, correos):
    r = cliente.post("/verificacion/recuperar", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"
    assert correos == []


def test_bloqueo_tras_5_codigos_errados(cliente, cuenta, correos, monkeypatch):
    _contrasena(cliente, cuenta)
    codigo = _pedir_codigo(cliente, cuenta, correos)
    malo = "111111" if codigo != "111111" else "222222"
    for _ in range(5):
        r = cliente.post("/verificacion/recuperar/codigo", data={"codigo": malo})
        assert r.status_code == 401
    estado = _estado(cuenta["id"])
    assert 14 * 60 < estado["bloqueo_recuperar_hasta"] - time.time() <= 15 * 60
    # Bloqueada: ni el código correcto ni un envío nuevo sirven.
    r = cliente.post("/verificacion/recuperar/codigo", data={"codigo": codigo})
    assert r.status_code == 401 and "Espera unos minutos" in r.text
    assert cliente.post("/verificacion/recuperar").status_code == 429
    # Pasados los 15 minutos se puede volver a pedir.
    futuro = time.time() + 15 * 60 + 1
    monkeypatch.setattr(mfa.time, "time", lambda: futuro)
    assert cliente.post("/verificacion/recuperar").status_code == 200


def test_limite_de_envios(cliente, cuenta, correos):
    _contrasena(cliente, cuenta)
    for _ in range(3):
        assert cliente.post("/verificacion/recuperar").status_code == 200
    r = cliente.post("/verificacion/recuperar")
    assert r.status_code == 429 and len(correos) == 3


def test_codigo_vence_a_los_15_minutos(cliente, cuenta, correos, monkeypatch):
    _contrasena(cliente, cuenta)
    codigo = _pedir_codigo(cliente, cuenta, correos)
    assert 14 * 60 < _estado(cuenta["id"])["recuperar"]["expira"] - time.time() <= 15 * 60
    futuro = time.time() + 15 * 60 + 1
    monkeypatch.setattr(mfa.time, "time", lambda: futuro)
    db = SessionLocal()
    assert not mfa.verificar_codigo_recuperacion(db.get(Usuario, cuenta["id"]), codigo)
    db.close()


def test_enlace_de_recuperacion_no_sirve_como_sesion(cliente, cuenta):
    token = crear_token_recuperacion(cuenta["id"], _hash(cuenta["id"]))
    cliente.cookies.set("sesion", token)
    assert cliente.get("/colecciones").status_code == 401
