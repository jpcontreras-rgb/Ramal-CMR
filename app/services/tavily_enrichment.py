from __future__ import annotations

import re
import httpx

from app.config import settings

EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
IG_RE = re.compile(r"(?:instagram\.com/|@)([A-Za-z0-9._]{2,30})", re.I)


async def enrich_company(company_name: str, website: str | None = None) -> dict:
    if not settings.tavily_api_key:
        raise RuntimeError("Falta TAVILY_API_KEY")
    query = f'"{company_name}" contacto email Instagram Chile'
    if website:
        query += f" {website}"
    headers = {"Authorization": f"Bearer {settings.tavily_api_key}", "Content-Type": "application/json"}
    payload = {"query": query, "search_depth": "basic", "max_results": 6, "include_raw_content": False}
    async with httpx.AsyncClient(timeout=25) as client:
        r = await client.post("https://api.tavily.com/search", headers=headers, json=payload)
        r.raise_for_status()
        results = r.json().get("results", [])

    text = "\n".join((x.get("content") or "") + " " + (x.get("url") or "") for x in results)
    emails = sorted(set(EMAIL_RE.findall(text)))
    igs = sorted(set("@" + m for m in IG_RE.findall(text) if m.lower() not in {"share", "explore"}))
    return {
        "email": emails[0] if emails else None,
        "instagram": igs[0] if igs else None,
        "sources": [{"title": x.get("title"), "url": x.get("url")} for x in results[:5]],
    }
