# Verificador API

Herramienta de automatización de pruebas de API: define colecciones de
verificaciones (método, URL, headers, body, status y contenido
esperados) y ejecútalas con un clic, con historial de resultados y
tiempos de respuesta — una versión propia y simplificada de lo que hace
Postman/Newman.

`FastAPI` · `SQLAlchemy` · `PostgreSQL (Neon)` · `JWT` · `Tailwind CSS`

## Cómo se conecta a la base de datos

El proyecto usa PostgreSQL alojado en [Neon](https://neon.tech) (Postgres
serverless, con plan gratuito). La conexión se resuelve en un solo lugar,
`app/database.py`, a partir de la variable `DATABASE_URL` del `.env`:

```python
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
```

Dos detalles importan por tratarse de Neon específicamente:

- **La cadena de conexión ya debe traer `?sslmode=require`** al final —
  Neon exige TLS y así te la entrega su panel (Dashboard → tu proyecto →
  *Connection Details* → *Connection string*, variante *Pooled
  connection*).
- **`pool_pre_ping=True`** es necesario porque el plan gratuito de Neon
  "suspende" el cómputo tras un rato sin actividad (scale-to-zero). Sin
  esto, una conexión que quedó abierta antes de esa suspensión falla con
  un error confuso a mitad de un request en vez de renovarse sola.

## Ejecutar en local

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1        # Windows
source .venv/bin/activate         # Linux o macOS

pip install -r requirements.txt
cp .env.example .env
```

Completa el `.env` con tu cadena de conexión de Neon y un `JWT_SECRET`
propio. Las tablas se crean solas al arrancar (no usa Alembic todavía).

```bash
uvicorn app.main:app --reload --port 8300
```

Para crear la cuenta de revisión (rol admin, solo lectura sobre todo):

```bash
python -m scripts.crear_admin "TuPasswordAquí"
```

## Estructura

```
app/
├── main.py            Arranque de FastAPI y registro de routers
├── database.py         Conexión a PostgreSQL (Neon)
├── models.py            Usuario, Colección, Prueba, Ejecución, ResultadoPrueba
├── seguridad.py          JWT en cookie httponly + bcrypt
├── dependencias.py        Control de acceso: dueño, o admin de solo lectura
├── ejecutor.py            Corre las pruebas de una colección con requests
├── routers/               web (inicio), auth, colecciones, ejecuciones
└── templates/             Jinja2 + Tailwind, tema claro/oscuro
```

## Rol admin

Existe un único rol adicional (`admin`) pensado para revisar el
proyecto: puede ver las colecciones, pruebas y ejecuciones de **todos**
los usuarios, pero no puede crear, editar, borrar ni ejecutar nada que
no sea suyo — es una vista de solo lectura sobre el resto.
