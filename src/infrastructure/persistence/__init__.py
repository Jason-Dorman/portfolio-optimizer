"""Persistence package — re-exports all ORM model classes.

Importing this package is sufficient to register every mapper with
Base.metadata, which is required for Alembic autogenerate and
SQLAlchemy mapper configuration.
"""

from src.infrastructure.persistence.models import *  # noqa: F401, F403
from src.infrastructure.persistence.models import __all__
