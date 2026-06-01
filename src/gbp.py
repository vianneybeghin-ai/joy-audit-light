"""Google Places Details API — extraction du place_id depuis l'URL Google Maps
de la fiche Privateaser, puis fetch rating + reviews."""
from __future__ import annotations
import logging
import os
import re

import httpx

logger = logging.getLogger(__name__)

_PLACE_ID_RE = re.compile(r'query_place_id=([^&"\']+)', re.I)


def extract_place_id(google_maps_url: str | None) -> str | None:
    if not google_maps_url:
        return None
    m = _PLACE_ID_RE.search(google_maps_url)
    return m.group(1) if m else None


async def fetch_gbp_data(place_id: str) -> dict | None:
    """Fail-open : timeout / no-key / status != OK → None."""
    api_key = os.getenv("GOOGLE_PLACES_API_KEY")
    if not api_key or not place_id:
        return None
    url = "https://maps.googleapis.com/maps/api/place/details/json"
    params = {
        "place_id": place_id,
        "fields": "name,rating,user_ratings_total,reviews,formatted_address,permanently_closed",
        "language": "fr",
        "key": api_key,
    }
    try:
        async with httpx.AsyncClient(timeout=10) as h:
            r = await h.get(url, params=params)
            data = r.json()
        if data.get("status") != "OK":
            logger.warning(f"[gbp] status={data.get('status')} sur {place_id}")
            return None
        result = data["result"]
        return {
            "rating": result.get("rating"),
            "user_ratings_total": result.get("user_ratings_total"),
            "reviews": result.get("reviews", [])[:5],
            "address": result.get("formatted_address"),
            "permanently_closed": result.get("permanently_closed", False),
        }
    except Exception as e:
        logger.warning(f"[gbp] fetch échoué ({e}) sur {place_id}")
        return None


_GROUP_KW = ("groupe", "anniversaire", "evg", "evjf",
             "afterwork", "soirée privée", "soiree privee", "événement", "evenement")


def count_group_reviews(reviews: list[dict]) -> int:
    return sum(
        1 for r in reviews
        if any(kw in (r.get("text") or "").lower() for kw in _GROUP_KW)
    )
