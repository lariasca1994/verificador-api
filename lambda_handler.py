"""Adaptador para correr la misma app FastAPI (sin cambios) dentro de AWS
Lambda mediante una Function URL. Igual que en gestor-casos-qa: Mangum
traduce el evento de Lambda a una petición ASGI normal y la respuesta de
vuelta -- no se reimplementa nada de la lógica de la app acá, solo se
expone. La sesión de esta app va en una cookie httponly (no en un header
Authorization), y el formato de evento de una Function URL (payload
version 2.0) sí soporta cookies -- Mangum las traduce solo."""

from mangum import Mangum

from app.main import app

handler = Mangum(app)
