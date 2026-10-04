# Verificador API

<p>
  <a href="https://eofvlnitsiuodup4eywdcenxwu0adgbz.lambda-url.us-east-1.on.aws/"><img src="docs/demo-badge.svg" alt="Abrir la demo en vivo" height="32"></a>
  <a href="https://frontend-nine-topaz-99.vercel.app"><img src="https://portafolio-status.onrender.com/api/status/verificador-api/badge.svg" alt="Estado en vivo del proyecto" height="32"></a>
  <a href="https://d4i3vsgw7xwmh.cloudfront.net"><img src="https://portafolio-status.onrender.com/api/status/verificador-api/qa-badge.svg" alt="Fecha y resultado de la última prueba E2E" height="32"></a>
</p>

![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-D71F00?style=for-the-badge&logo=sqlalchemy&logoColor=white)
![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-06B6D4?style=for-the-badge&logo=tailwindcss&logoColor=white)

Herramienta de automatización de pruebas de API: define colecciones de
verificaciones (método, URL, headers, body, status y contenido
esperados) y ejecútalas con un clic, con historial de resultados y
tiempos de respuesta — una versión propia y simplificada de lo que hace
Postman/Newman.

### En pocas palabras

- **Qué hace:** sirve para comprobar que una API funciona. Anotas qué petición
  hacer (por ejemplo `GET /usuarios/1`) y qué esperas recibir (código 200, cierto
  texto en la respuesta); luego ejecutas toda la colección con un clic y ves
  qué pasó, qué falló y cuánto tardó cada una.
- **Para qué sirve:** detectar rápido si un cambio rompió algo, y guardar un
  historial de resultados como evidencia de pruebas.
- **Cómo probarlo:** entra a la [demo](https://eofvlnitsiuodup4eywdcenxwu0adgbz.lambda-url.us-east-1.on.aws/),
  crea una cuenta, arma una colección y ejecútala. Para correrlo en tu equipo,
  ve a [Ejecutar en local](#ejecutar-en-local).

## Demo en vivo

**Aplicación:** [abrir la demo en vivo](https://eofvlnitsiuodup4eywdcenxwu0adgbz.lambda-url.us-east-1.on.aws/)

## Cómo se conecta a la base de datos

El proyecto usa PostgreSQL alojado en [Neon](https://neon.tech) (Postgres
serverless). La conexión se resuelve en un solo lugar,
`app/database.py`, a partir de la variable `DATABASE_URL` del `.env`:

```python
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
```

Dos detalles importan por tratarse de Neon específicamente:

- **La cadena de conexión ya debe traer `?sslmode=require`** al final —
  Neon exige TLS y así te la entrega su panel (Dashboard → tu proyecto →
  *Connection Details* → *Connection string*, variante *Pooled
  connection*).
- **`pool_pre_ping=True`** es necesario porque Neon
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

## Arquitectura

<p align="center">
  <img src="docs/arquitectura.svg" alt="Diagrama de arquitectura: FastAPI con Mangum en AWS Lambda detrás de una Function URL, sesión JWT, SQLAlchemy hacia PostgreSQL en Neon y un ejecutor que llama a las APIs bajo prueba" width="100%">
</p>

- **AWS Lambda** ejecuta la app FastAPI (con Mangum) detrás de una Function URL;
  las páginas usan Jinja2 + Tailwind y la sesión viaja en un JWT dentro de una
  cookie.
- El **ejecutor** recorre la colección, llama a cada endpoint con `requests` y
  compara el código de estado y el contenido con lo esperado.
- **SQLAlchemy** guarda colecciones, pruebas y resultados en **PostgreSQL
  serverless de Neon**, por TLS y con `pool_pre_ping` para sobrevivir a la
  suspensión por inactividad.
- **qa-evidencia** prueba la demo automáticamente dos veces al día.

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

## Despliegue

La instancia pública corre en AWS Lambda (Function URL, sin API Gateway),
con PostgreSQL en Neon como base de datos.

## Autor

**Luis Felipe Arias Carriazo**
[GitHub](https://github.com/lariasca1994) · [LinkedIn](https://linkedin.com/in/lfac1)