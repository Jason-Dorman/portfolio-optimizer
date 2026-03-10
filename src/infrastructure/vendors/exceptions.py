"""Vendor-layer exceptions."""


class VendorError(Exception):
    """Base exception for all vendor errors."""


class AuthenticationRequired(VendorError):
    """User must authenticate (or re-authenticate) with the vendor."""


class RateLimitError(VendorError):
    """Vendor rate limit exceeded."""


class TickerNotFoundError(VendorError):
    """Ticker not found at vendor."""
