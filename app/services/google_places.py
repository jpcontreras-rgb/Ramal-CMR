from __future__ import annotations

import httpx

from app.config import settings

GOOGLE_TEXT_SEARCH = "https://places.googleapis.com/v1/places:searchText"


async def search_places(query: str, max_results: int = 15) -> list[dict]:
    if not settings.google_places_api_key:
        raise RuntimeError("Falta GOOGLE_PLACES_API_KEY")

    field_mask = ",".join([
        "places.id", "places.displayName", "places.formattedAddress",
        "places.location", "places.nationalPhoneNumber", "places.websiteUri",
        "places.primaryType", "places.googleMapsUri"
    ])
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": settings.google_places_api_key,
        "X-Goog-FieldMask": field_mask,
    }
    payload = {"textQuery": query, "pageSize": min(max_results, 20), "languageCode": "es"}
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(GOOGLE_TEXT_SEARCH, headers=headers, json=payload)
        response.raise_for_status()
        raw = response.json().get("places", [])

    out = []
    for p in raw:
        loc = p.get("location") or {}
        out.append({
            "google_place_id": p.get("id"),
            "company_name": (p.get("displayName") or {}).get("text"),
            "address": p.get("formattedAddress"),
            "latitude": loc.get("latitude"),
            "longitude": loc.get("longitude"),
            "phone": p.get("nationalPhoneNumber"),
            "website": p.get("websiteUri"),
            "industry": p.get("primaryType"),
            "google_maps_url": p.get("googleMapsUri"),
            "source": "Google Places",
        })
    return out
