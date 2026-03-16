"""SQLAlchemy implementation of DataVendorRepository."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.repositories.vendors import DataVendorRepository
from src.infrastructure.persistence.models.reference import DataVendor as OrmDataVendor


class SqlDataVendorRepository(DataVendorRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create(self, name: str) -> UUID:
        stmt = select(OrmDataVendor).where(
            func.lower(OrmDataVendor.name) == name.lower()
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is not None:
            return row.vendor_id

        vendor = OrmDataVendor(name=name)
        self._session.add(vendor)
        await self._session.flush()  # populate vendor_id before returning
        return vendor.vendor_id
