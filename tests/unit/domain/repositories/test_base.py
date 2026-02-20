"""Tests for src/domain/repositories/base.py."""

import pytest
from uuid import uuid4

from src.domain.repositories.base import Repository


def test_repository_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        Repository()  # type: ignore[abstract]


def test_repository_concrete_subclass_must_implement_all_methods():
    class _Partial(Repository):
        async def get(self, id): return None
        # missing list, create, update, delete

    with pytest.raises(TypeError):
        _Partial()  # type: ignore[abstract]


def test_repository_full_concrete_subclass_instantiates():
    class _Full(Repository):
        async def get(self, id): return None
        async def list(self, limit=50, offset=0): return []
        async def create(self, entity): return entity
        async def update(self, entity): return entity
        async def delete(self, id): return None

    assert _Full() is not None
