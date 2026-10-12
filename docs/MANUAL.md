# 📘 Manual de usuario · Verificador API

Guía para usar la plataforma paso a paso: qué significa cada campo, qué datos se ingresan y qué
protege la plataforma. Para la parte técnica vuelve al [README](../README.md).

**Demo:** [Verificador API (AWS Lambda)](https://eofvlnitsiuodup4eywdcenxwu0adgbz.lambda-url.us-east-1.on.aws/)

## Contenido

1. [En pocas palabras](#1-en-pocas-palabras)
2. [Antes de empezar](#2-antes-de-empezar)
3. [Paso a paso](#3-paso-a-paso)
4. [Qué información ingresas y dónde queda](#4-qué-información-ingresas-y-dónde-queda)
5. [Seguridad: qué se garantiza](#5-seguridad-qué-se-garantiza)
6. [Límites y recomendaciones](#6-límites-y-recomendaciones)
7. [Preguntas frecuentes](#7-preguntas-frecuentes)

---

## 1. En pocas palabras

Una versión propia y simplificada de Postman: anotas qué petición hacer a una API y qué esperas
recibir, agrupas esas pruebas en **colecciones** y las ejecutas todas con un clic. Cada ejecución
queda guardada con su resultado y su tiempo de respuesta, como evidencia de pruebas.

## 2. Antes de empezar

- Solo necesitas un navegador.
- **Las peticiones las hace el servidor**, no tu navegador: la API que pruebes tiene que estar
  publicada en internet (una dirección `localhost` de tu equipo no funciona).

## 3. Paso a paso

### 3.1 Crear una cuenta

![Formulario de registro](img/manual/01-registro.png)

| # | Campo | Qué escribir | Reglas |
|:-:|---|---|---|
| 1 | Nombre | Tu nombre | Obligatorio |
| 2 | Correo | El correo con el que vas a entrar | Formato válido y único |
| 3 | Contraseña | Tu contraseña | Mínimo 8 caracteres; máximo 72 bytes |
| 4 | Crear cuenta | Botón | Crea la cuenta y te deja con la sesión iniciada |

### 3.2 Iniciar sesión

![Formulario de inicio de sesión](img/manual/02-login.png)

| # | Campo | Qué escribir |
|:-:|---|---|
| 1 | Correo | El correo de tu cuenta |
| 2 | Contraseña | Tu contraseña |
| 3 | Entrar | Abre **Mis colecciones** |

### 3.3 Mis colecciones

![Lista de colecciones](img/manual/03-colecciones.png)

| # | Elemento | Qué hace |
|:-:|---|---|
| 1 | + Nueva colección | Crea una colección de pruebas |

Solo ves **tus** colecciones.

### 3.4 Crear una colección

![Formulario de colección](img/manual/04-coleccion-nueva.png)

| # | Campo | Qué escribir |
|:-:|---|---|
| 1 | Nombre | Nombre de la colección, por ejemplo "API de reservas" |
| 2 | Descripción | Opcional: para qué sirve |
| 3 | URL base | Opcional: dirección común de la API, por ejemplo `https://mi-api.onrender.com` |
| 4 | Crear | Guarda la colección |

### 3.5 Agregar una prueba

![Formulario de prueba con sus campos numerados](img/manual/05-prueba-nueva.png)

| # | Campo | Qué escribir |
|:-:|---|---|
| 1 | Nombre | Qué verifica, por ejemplo "Listar escenarios" |
| 2 | Método | GET, POST, PUT, PATCH o DELETE |
| 3 | Ruta o URL | Ruta relativa a la URL base (`/api/escenarios`) o una URL completa |
| 4 | Headers (JSON) | Opcional: cabeceras, por ejemplo `{"Accept": "application/json"}` |
| 5 | Body (JSON) | Opcional: cuerpo de la petición para POST, PUT o PATCH |
| 6 | Status esperado | Código HTTP que debe responder, por ejemplo `200` |
| 7 | La respuesta debe contener | Opcional: texto que debe aparecer en la respuesta |
| 8 | Guardar prueba | Agrega la prueba a la colección |

### 3.6 La colección y su historial

![Detalle de una colección con sus pruebas e historial](img/manual/06-coleccion.png)

- La tabla **Pruebas** muestra nombre, método, ruta y status esperado; **Borrar** elimina una
  prueba.
- **▶ Ejecutar todo** corre todas las pruebas de la colección.
- **Ejecuciones recientes** guarda las últimas 10 ejecuciones con cuántas pasaron.

### 3.7 Resultado de una ejecución

![Detalle de una ejecución](img/manual/07-ejecucion.png)

Cada prueba aparece con ✅ o ❌, el código HTTP recibido y el tiempo de respuesta en
milisegundos. Si falló, se indica el motivo (status distinto, texto ausente o error de conexión).

## 4. Qué información ingresas y dónde queda

| Dato | Para qué se usa | Dónde se guarda | Quién lo ve |
|---|---|---|---|
| Nombre y correo | Identificar tu cuenta | PostgreSQL (Neon) | Tú y el administrador |
| Contraseña | Iniciar sesión | PostgreSQL, **solo su huella bcrypt** | Nadie: no se puede leer ni recuperar |
| Colecciones y pruebas (URL, headers, body) | Ejecutar las verificaciones | PostgreSQL, **tal cual las escribes** | Tú y el administrador (solo lectura) |
| Resultados de ejecución | Historial y evidencia | PostgreSQL | Tú y el administrador |
| Sesión | Mantenerte conectado | Cookie en tu navegador | Firmada, invisible para JavaScript, vence a las 8 horas |

## 5. Seguridad: qué se garantiza

Comprobado en el código del proyecto (`app/seguridad.py`, `app/dependencias.py`,
`app/routers/`):

- **Contraseñas con bcrypt.** Solo se guarda la huella.
- **Sesión con JWT en cookie `HttpOnly` y `SameSite=Lax`**, válida por 8 horas. Una cuenta
  suspendida por el administrador pierde el acceso de inmediato.
- **Cada colección es de su dueño:** nadie más puede verla, ejecutarla ni editarla. El
  administrador puede mirarla, pero no modificar ni ejecutar nada ajeno.
- **Tiempo máximo por petición:** cada prueba se corta a los 15 segundos, para que una API lenta no
  bloquee la ejecución.
- **Consultas a la base con ORM** (SQLAlchemy), sin concatenar texto del usuario en el SQL.
- **Plantillas con escape automático** (Jinja2): las respuestas de las APIs probadas se muestran
  como texto, no como código.
- **Secretos fuera del repositorio:** conexión a PostgreSQL y clave JWT en variables de entorno de
  AWS Lambda.

## 6. Límites y recomendaciones

Es una demo de portafolio:

- **No guardes tokens ni contraseñas reales en los headers o el body:** se almacenan sin cifrar
  para poder repetir la petición.
- Prueba solo APIs propias o públicas que tengas permiso de consultar: las peticiones salen desde
  el servidor de la demo.
- No hay recuperación de contraseña ni bloqueo por intentos fallidos.

## 7. Preguntas frecuentes

**¿Por qué falla con "error de conexión" si en mi navegador la API responde?** Si la API está en
tu equipo (`localhost`) o en una red privada, el servidor de la demo no la alcanza.

**¿Qué pasa si dejo vacío "La respuesta debe contener"?** La prueba solo compara el código HTTP.

**¿Puedo ver las ejecuciones antiguas?** La colección muestra las 10 más recientes.
