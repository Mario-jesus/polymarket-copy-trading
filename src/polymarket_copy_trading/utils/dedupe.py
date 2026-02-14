"""Deduplication key for trades."""

from __future__ import annotations

from typing import Any


def trade_key(t: dict[str, Any]) -> str:
    """Return a stable key to identify a trade (for deduplication).

    Prefers transaction hash, then id, then composite of timestamp|conditionId|outcome|price|size.
    """
    tx = t.get("transactionHash") or t.get("txHash") or t.get("hash")
    if isinstance(tx, str) and tx:
        return f"tx:{tx}"

    tid = t.get("id")
    if tid is not None:
        return f"id:{tid}"

    ts = str(t.get("timestamp") or "")
    cid = str(t.get("conditionId") or t.get("market") or "")
    outcome = str(t.get("outcome") or "")
    price = str(t.get("price") or "")
    size = str(t.get("size") or "")
    return f"cmp:{ts}|{cid}|{outcome}|{price}|{size}"
