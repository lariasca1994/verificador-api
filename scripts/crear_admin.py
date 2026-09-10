"""Crea (o promueve a rol admin) la cuenta ariascluisf@proton.me, usada
para revisar este proyecto — solo lectura sobre las colecciones y
ejecuciones de todos los usuarios, sin gestionar nada ajeno.

Uso (desde la raíz del proyecto, con el venv activado):
    python -m scripts.crear_admin <password>
"""

import sys

from app.database import Base, SessionLocal, engine
from app.models import Usuario
from app.seguridad import hashear_password

EMAIL = "ariascluisf@proton.me"
NOMBRE = "Luis Felipe Arias Carriazo"


def main() -> None:
    if len(sys.argv) != 2:
        print("Uso: python -m scripts.crear_admin <password>")
        sys.exit(1)
    password = sys.argv[1]

    try:
        password_hash = hashear_password(password)
    except ValueError as error:
        print(f"Contraseña rechazada: {error}")
        sys.exit(1)

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        usuario = db.query(Usuario).filter(Usuario.email == EMAIL).first()
        if usuario:
            usuario.rol = "admin"
            usuario.password_hash = password_hash
            db.commit()
            print(f"'{EMAIL}' ya existía — se actualizó su contraseña y se confirmó el rol admin.")
        else:
            usuario = Usuario(
                nombre=NOMBRE,
                email=EMAIL,
                password_hash=password_hash,
                rol="admin",
            )
            db.add(usuario)
            db.commit()
            print(f"Cuenta admin '{EMAIL}' creada correctamente.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
