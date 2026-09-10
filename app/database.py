import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "Falta DATABASE_URL en el archivo .env — copia .env.example a .env "
        "y pega ahí la cadena de conexión de tu proyecto en Neon "
        "(Dashboard > Connection Details > Connection string, variante "
        "'Pooled connection')."
    )

# pool_pre_ping=True es clave trabajando contra Neon: su plan gratuito
# "suspende" el cómputo tras un rato sin uso (scale-to-zero). Si el
# proceso llevaba una conexión abierta desde antes de esa suspensión,
# queda inválida sin que SQLAlchemy lo sepa. pool_pre_ping hace un
# "SELECT 1" silencioso antes de reutilizar cualquier conexión del pool
# y la descarta si ya no sirve, en vez de fallar con un
# "server closed the connection unexpectedly" a mitad de un request.
#
# La primera consulta después de un rato de inactividad puede tardar
# unos segundos mientras Neon "despierta" el cómputo — es esperado, no
# un error de configuración.
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def obtener_db():
    """Dependencia de FastAPI: una sesión de base de datos por request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
