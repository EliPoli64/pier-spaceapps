"""Local market price fetcher for dollar savings estimates (BR-11).

Cache-first, API-second pattern with synthetic fallback.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date

import pandas as pd

logger = logging.getLogger("pier.tools.fetch_market_price")

# Typical market prices (USD/ton) by crop — used when no live API is available
DEFAULT_PRICES = {
    "Sorghum": 250.0,
    "Millet": 220.0,
    "Buckwheat": 400.0,
    "Cowpea": 500.0,
    "Cereal rye (cover)": 150.0,
}


def fetch_market_price(
    crop: str,
    region: str = "global",
    date_str: str | None = None,
) -> dict[str, Any]:
    """Fetch market price for a crop.

    Args:
        crop: crop name.
        region: region/market identifier (for future live API).
        date_str: ISO date (for future historical pricing).

    Returns:
        dict with keys: crop, price_per_unit, currency, source, region, date.
    """
    from datetime import date as _date
    today = date_str or _date.today().isoformat()

    price = DEFAULT_PRICES.get(crop, 200.0)
    source = "default_table"

    # TODO: hook into live market API when available (e.g., FAO GIEWS, local exchange)
    # if MARKET_API_KEY:
    #     ...

    logger.info("Market price for %s in %s: %.2f %s (source=%s)", crop, region, price, "USD", source)

    return {
        "crop": crop,
        "price_per_unit": round(price, 2),
        "currency": "USD",
        "source": source,
        "region": region,
        "date": today,
    }


def compute_dollar_savings(
    crop: str,
    expected_yield_tons_per_ha: float,
    region: str = "global",
    date_str: str | None = None,
) -> dict[str, Any]:
    """Compute estimated dollar savings from rescuing a crop vs. total loss.

    Args:
        crop: crop name.
        expected_yield_tons_per_ha: expected yield in tons/hectare.
        region: market region.
        date_str: ISO date.

    Returns:
        dict with price info and estimated savings per hectare.
    """
    price_info = fetch_market_price(crop, region, date_str)
    revenue_per_ha = price_info["price_per_unit"] * expected_yield_tons_per_ha
    # Total loss = 0 revenue if no crop planted
    savings_per_ha = revenue_per_ha

    return {
        "crop": crop,
        "price_per_unit": price_info["price_per_unit"],
        "currency": price_info["currency"],
        "expected_yield_tons_per_ha": expected_yield_tons_per_ha,
        "estimated_revenue_usd_per_ha": round(revenue_per_ha, 2),
        "estimated_savings_usd_per_ha": round(savings_per_ha, 2),
        "note": "Estimated revenue if crop matures; total loss = $0 if no rescue crop planted.",
    }


from typing import Any  # noqa: E402

__all__ = ["fetch_market_price", "compute_dollar_savings", "DEFAULT_PRICES"]
