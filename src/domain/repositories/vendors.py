"""Data vendor repository interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID


class DataVendorRepository(ABC):
    """Read/write interface for data_vendors reference records.

    Vendors are registered lazily: the first time a ticker ingest references
    a vendor name, the vendor record is created automatically.  Subsequent
    calls for the same name are pure lookups (idempotent).
    """

    @abstractmethod
    async def get_or_create(self, name: str) -> UUID:
        """Return the vendor_id for *name*, creating the record if it does not exist.

        *name* is matched case-insensitively so 'Schwab' and 'schwab' resolve to
        the same vendor.  The canonical stored form is the first name used to
        create the record.
        """
