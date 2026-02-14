"""Validation helpers for addresses and condition IDs."""

from __future__ import annotations

from typing import Any


def is_hex_address(addr: Any) -> bool:
    """Return True if addr is a valid 0x wallet address (42 chars)."""
    if not isinstance(addr, str):
        return False
    s = addr.strip()
    if len(s) != 42:
        return False
    if not s.startswith("0x"):
        return False
    try:
        int(s[2:], 16)
        return True
    except ValueError:
        return False


def is_condition_id(x: Any) -> bool:
    """Return True if x is a valid condition ID (0x + 64 hex chars = 66 chars)."""
    if not isinstance(x, str):
        return False
    s = x.strip()
    return s.startswith("0x") and len(s) == 66


def mask_address(addr: str | None) -> str:
    """Return a masked wallet address for logging (e.g. 0x1234...abcd)."""
    if not addr or len(addr) < 10:
        return "***"
    return f"{addr[:6]}...{addr[-4:]}"
