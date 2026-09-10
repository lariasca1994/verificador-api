import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.database import Base


class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True)
    nombre = Column(String(120), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    # "admin" solo puede MIRAR las colecciones y ejecuciones de todos los
    # usuarios (de solo lectura) — no crea, edita ni ejecuta nada ajeno.
    # Cualquier otro valor ("usuario") solo ve y gestiona lo propio.
    rol = Column(String(20), nullable=False, default="usuario")
    creado_en = Column(DateTime, default=datetime.datetime.utcnow)

    colecciones = relationship("Coleccion", back_populates="propietario")

    @property
    def es_admin(self) -> bool:
        return self.rol == "admin"


class Coleccion(Base):
    """Un grupo de pruebas de API, equivalente a una "colección" de Postman."""

    __tablename__ = "colecciones"

    id = Column(Integer, primary_key=True)
    nombre = Column(String(150), nullable=False)
    descripcion = Column(Text, nullable=True)
    url_base = Column(String(500), nullable=True)  # opcional, se antepone a rutas relativas
    propietario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    creado_en = Column(DateTime, default=datetime.datetime.utcnow)

    propietario = relationship("Usuario", back_populates="colecciones")
    pruebas = relationship(
        "Prueba", back_populates="coleccion", cascade="all, delete-orphan", order_by="Prueba.orden"
    )
    ejecuciones = relationship(
        "Ejecucion", back_populates="coleccion", cascade="all, delete-orphan"
    )


class Prueba(Base):
    """Una verificación puntual: método + URL + qué se espera de vuelta."""

    __tablename__ = "pruebas"

    id = Column(Integer, primary_key=True)
    coleccion_id = Column(Integer, ForeignKey("colecciones.id"), nullable=False)
    nombre = Column(String(150), nullable=False)
    metodo = Column(String(10), nullable=False, default="GET")  # GET/POST/PUT/PATCH/DELETE
    ruta = Column(String(500), nullable=False)  # absoluta, o relativa a url_base
    headers_json = Column(JSON, nullable=True)
    body_json = Column(JSON, nullable=True)
    status_esperado = Column(Integer, nullable=True)  # None = no valida el status
    contiene_esperado = Column(String(300), nullable=True)  # texto que debe aparecer en la respuesta
    orden = Column(Integer, default=0)

    coleccion = relationship("Coleccion", back_populates="pruebas")


class Ejecucion(Base):
    """Una corrida de todas las pruebas de una colección, en un momento dado."""

    __tablename__ = "ejecuciones"

    id = Column(Integer, primary_key=True)
    coleccion_id = Column(Integer, ForeignKey("colecciones.id"), nullable=False)
    ejecutado_por_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    fecha = Column(DateTime, default=datetime.datetime.utcnow)
    total = Column(Integer, default=0)
    exitosas = Column(Integer, default=0)
    fallidas = Column(Integer, default=0)

    coleccion = relationship("Coleccion", back_populates="ejecuciones")
    ejecutado_por = relationship("Usuario")
    resultados = relationship(
        "ResultadoPrueba", back_populates="ejecucion", cascade="all, delete-orphan"
    )


class ResultadoPrueba(Base):
    """El resultado de UNA prueba dentro de una ejecución."""

    __tablename__ = "resultados_prueba"

    id = Column(Integer, primary_key=True)
    ejecucion_id = Column(Integer, ForeignKey("ejecuciones.id"), nullable=False)
    prueba_id = Column(Integer, ForeignKey("pruebas.id"), nullable=True)  # nullable: la prueba pudo borrarse luego
    nombre_prueba = Column(String(150), nullable=False)  # copia del nombre, sobrevive si se borra la prueba
    paso = Column(Boolean, default=False)
    status_obtenido = Column(Integer, nullable=True)
    tiempo_ms = Column(Float, nullable=True)
    detalle_error = Column(Text, nullable=True)

    ejecucion = relationship("Ejecucion", back_populates="resultados")
