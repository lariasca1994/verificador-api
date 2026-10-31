"""Registro de eventos de seguridad de las cuentas.

Guarda qué pasó, a qué cuenta y cuándo; nunca contraseñas, códigos ni datos
del equipo. Cada registro borra los eventos de más de 15 días.
Si la base no responde, el evento se pierde pero el ingreso sigue: la
auditoría nunca bloquea al usuario.
"""

import datetime
import logging

from app.database import SessionLocal
from app.models import EventoSeguridad

INGRESO = "ingreso"
CLAVE_ERRADA = "clave_errada"
CODIGO_ERRADO = "codigo_errado"
CUENTA_BLOQUEADA = "cuenta_bloqueada"
CLAVE_CAMBIADA = "clave_cambiada"
RECUPERACION = "recuperacion_solicitada"
METODO_ACTIVADO = "metodo_activado"

RETENCION_DIAS = 15

_log = logging.getLogger(__name__)


def registrar(tipo: str, usuario) -> None:
    # Sesión propia: el evento queda guardado aunque la petición termine en error.
    db = SessionLocal()
    try:
        ahora = datetime.datetime.utcnow()
        db.query(EventoSeguridad).filter(
            EventoSeguridad.fecha < ahora - datetime.timedelta(days=RETENCION_DIAS)
        ).delete(synchronize_session=False)
        db.add(EventoSeguridad(tipo=tipo, usuario_id=usuario.id, fecha=ahora))
        db.commit()
    except Exception:  # noqa: BLE001 - la auditoría no debe tumbar el ingreso
        db.rollback()
        _log.warning("No se pudo registrar el evento de seguridad %s", tipo)
    finally:
        db.close()
