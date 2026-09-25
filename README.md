# Verificador API

![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat&logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?style=flat&logo=postgresql&logoColor=white)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-D71F00?style=flat&logo=sqlalchemy&logoColor=white)
![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-06B6D4?style=flat&logo=tailwindcss&logoColor=white)

Herramienta de automatización de pruebas de API: define colecciones de
verificaciones (método, URL, headers, body, status y contenido
esperados) y ejecútalas con un clic, con historial de resultados y
tiempos de respuesta — una versión propia y simplificada de lo que hace
Postman/Newman.

## Demo en vivo

**Aplicación:** [eofvlnitsiuodup4eywdcenxwu0adgbz.lambda-url.us-east-1.on.aws](https://eofvlnitsiuodup4eywdcenxwu0adgbz.lambda-url.us-east-1.on.aws/)

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

## Arquitectura

```mermaid
flowchart TB

    subgraph Clientes["👤 Cliente"]
        Browser["🌐 Navegador Web<br/>Jinja2 + Tailwind CSS<br/>Tema claro/oscuro"]
    end

    subgraph AWSLambda["☁️ AWS Lambda (Function URL)"]
        subgraph App["Aplicación FastAPI"]
            Mangum["Mangum<br/>Adaptador ASGI"]
            Main["main.py<br/>Arranque · registro de routers"]

            subgraph Routers["Routers"]
                WebRouter["routers/web.py<br/>Página de inicio"]
                AuthRouter["routers/auth.py<br/>Registro · login · logout"]
                ColeccionesRouter["routers/colecciones.py<br/>CRUD de colecciones y pruebas"]
                EjecucionesRouter["routers/ejecuciones.py<br/>Ejecución · historial · resultados"]
            end

            subgraph Seguridad["Seguridad"]
                Security["seguridad.py<br/>JWT en cookie httponly + bcrypt"]
                Dependencias["dependencias.py<br/>Control de acceso: dueño<br/>o admin de solo lectura"]
            end

            subgraph Negocio["Lógica de negocio"]
                Ejecutor["ejecutor.py<br/>Ejecuta pruebas con requests<br/>Método · URL · headers · body<br/>Status y contenido esperados"]
            end

            subgraph Presentacion["Presentación"]
                Templates["templates/<br/>Plantillas Jinja2"]
                Static["static/js/<br/>Interactividad"]
            end
        end
    end

    subgraph Neon["🗄️ Neon (PostgreSQL Serverless)"]
        DB[("Base de datos<br/>Usuarios · Colecciones · Pruebas<br/>Ejecuciones · ResultadosPrueba")]
        Pool["pool_pre_ping=True<br/>Reconexión automática<br/>scale-to-zero")]
    end

    subgraph Externos["🔌 APIs externas verificadas"]
        API1["API 1"]
        API2["API 2"]
        API3["API N"]
    end

    %% ---- Flujo de datos ----
    Browser -->|HTTPS| Mangum
    Mangum --> Main
    Main --> WebRouter
    Main --> AuthRouter
    Main --> ColeccionesRouter
    Main --> EjecucionesRouter
    WebRouter --> Templates
    WebRouter --> Static
    AuthRouter --> Security
    ColeccionesRouter --> Dependencias
    EjecucionesRouter --> Dependencias
    Seguridad --> Dependencias
    Dependencias --> Ejecutor
    EjecucionesRouter --> Ejecutor
    Ejecutor -->|requests GET/POST/PUT/DELETE| API1
    Ejecutor -->|requests GET/POST/PUT/DELETE| API2
    Ejecutor -->|requests GET/POST/PUT/DELETE| API3
    Main --> Database["database.py<br/>SQLAlchemy + create_engine"]
    Database --> Pool
    Pool -->|sslmode=require| DB
    AuthRouter --> Database
    ColeccionesRouter --> Database
    EjecucionesRouter --> Database

    %% ---- Colores de marca (Brand Colors) ----
    classDef fastapi fill:#009688,stroke:#004D40,stroke-width:2px,color:#FFFFFF,rx:12,ry:12;
    classDef python fill:#3572A5,stroke:#1A3A5C,stroke-width:2px,color:#FFFFFF,rx:12,ry:12;
    classDef postgres fill:#336791,stroke:#1A3A5F,stroke-width:2px,color:#FFFFFF;
    classDef neon fill:#00E599,stroke:#007A4D,stroke-width:2px,color:#000000;
    classDef sqlalchemy fill:#D71F00,stroke:#7F1200,stroke-width:2px,color:#FFFFFF,rx:10,ry:10;
    classDef jinja fill:#B41717,stroke:#7F0000,stroke-width:2px,color:#FFFFFF,rx:10,ry:10;
    classDef tailwind fill:#06B6D4,stroke:#0369A1,stroke-width:2px,color:#FFFFFF,rx:10,ry:10;
    classDef aws fill:#FF9900,stroke:#B36B00,stroke-width:2px,color:#000000,rx:12,ry:12;
    classDef security fill:#333333,stroke:#000000,stroke-width:2px,color:#FFFFFF,rx:10,ry:10;
    classDef neutral fill:#F5F5F5,stroke:#CCCCCC,stroke-width:1px,color:#333333,rx:10,ry:10;

    class Browser neutral;
    class Mangum aws;
    class Main,WebRouter,AuthRouter,ColeccionesRouter,EjecucionesRouter fastapi;
    class Security,Dependencias security;
    class Ejecutor python;
    class Templates jinja;
    class Static tailwind;
    class Database sqlalchemy;
    class DB postgres;
    class Pool neon;
    class API1,API2,API3 neutral;

    %% ---- Estilos de subgráficos ----
    style Clientes fill:#FAFAFA,stroke:#DDDDDD,stroke-width:1px,rx:14,ry:14;
    style AWSLambda fill:#FFF8E1,stroke:#FF9900,stroke-width:2px,stroke-dasharray:6 4,rx:16,ry:16;
    style App fill:#E0F2F1,stroke:#009688,stroke-width:1px,rx:12,ry:12;
    style Routers fill:#E3F2FD,stroke:#009688,stroke-width:1px,rx:10,ry:10;
    style Seguridad fill:#F5F5F5,stroke:#333333,stroke-width:1px,rx:10,ry:10;
    style Negocio fill:#EDE7F6,stroke:#009688,stroke-width:1px,rx:10,ry:10;
    style Presentacion fill:#FFF3E0,stroke:#009688,stroke-width:1px,rx:10,ry:10;
    style Neon fill:#E8F5E9,stroke:#00E599,stroke-width:2px,stroke-dasharray:6 4,rx:16,ry:16;
    style Externos fill:#F0F0F0,stroke:#CCCCCC,stroke-width:1px,stroke-dasharray:4 3,rx:14,ry:14;
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

## Despliegue

La instancia pública corre en AWS Lambda (Function URL, sin API Gateway),
con PostgreSQL en Neon como base de datos.

## Autor

**Luis Felipe Arias Carriazo**
[GitHub](https://github.com/lariasca1994) · [LinkedIn](https://linkedin.com/in/lfac1)