"""Base declarativa de SQLAlchemy 2.0 para todos los modelos ORM."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base común de los modelos ORM de EventPro."""
