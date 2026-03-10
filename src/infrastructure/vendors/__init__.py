"""Vendor adapter package.

Public surface:
  VendorAdapter     — abstract base all market-data adapters must implement
  VendorPriceBar    — raw OHLC DTO returned by adapters (before domain mapping)
  SchwabAdapter     — Schwab MarketData v1 implementation
  FredAdapter       — FRED risk-free rate implementation (not a VendorAdapter)
  VendorError / AuthenticationRequired / RateLimitError / TickerNotFoundError
"""

from src.infrastructure.vendors.base import VendorAdapter
from src.infrastructure.vendors.exceptions import (
    AuthenticationRequired,
    RateLimitError,
    TickerNotFoundError,
    VendorError,
)
from src.infrastructure.vendors.fred import FredAdapter
from src.infrastructure.vendors.schemas import VendorPriceBar
from src.infrastructure.vendors.schwab import SchwabAdapter

__all__ = [
    "VendorAdapter",
    "VendorPriceBar",
    "SchwabAdapter",
    "FredAdapter",
    "VendorError",
    "AuthenticationRequired",
    "RateLimitError",
    "TickerNotFoundError",
]
