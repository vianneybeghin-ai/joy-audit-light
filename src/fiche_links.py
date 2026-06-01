"""Extrait les liens externes (Google Maps, Instagram, Facebook, site officiel) depuis
le HTML *rendu* (Playwright) de la fiche Privateaser. Indispensable car les icônes
'Enlaces útiles' sont hydratées côté client → un GET httpx ne les voit pas.

Bonus Fix 3 (Chez Eloise post-refresh) : extraction du place_id Google Maps + call
Places Details API → on récupère note, nb_avis, 5 derniers avis. Évite que web_fetch
reçoive la coquille JS vide de l'URL maps/search?query_place_id=...

Fail-open : timeout / erreur Chromium / pas d'API key → tous None, step 1 retombe
sur sa recherche web habituelle (Fix 3.A du brief_3_fixes_v2)."""
from __future__ import annotations
import html as _html_lib
import os
import re
import logging

import httpx
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

_PATTERNS = {
    "google_maps":   re.compile(r'https?://(?:www\.)?(?:google\.[a-z.]+/maps/[^"\s\']+|maps\.app\.goo\.gl/\S+|g\.co/kgs/\S+|goo\.gl/maps/\S+)', re.I),
    "instagram":     re.compile(r'https?://(?:www\.)?instagram\.com/[A-Za-z0-9_.]+/?', re.I),
    "facebook":      re.compile(r'https?://(?:www\.)?facebook\.com/[A-Za-z0-9.\-_]+/?', re.I),
    "thefork":       re.compile(r'https?://(?:www\.)?(?:thefork|lafourchette)\.[a-z.]+/[^"\s\']+', re.I),
}

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

_SKIP_DOMAINS = (
    "privateaser.", "google.", "instagram.", "facebook.",
    "tiktok.", "twitter.", "x.com/", "thefork.", "lafourchette.",
    "pagesjaunes.", "tripadvisor.", "mappy.", "yelp.", "viamichelin.",
    # CDN / assets / fonts / analytics / vidéo — pas un site officiel
    "amazonaws.com", "cloudfront.net", "cloudinary.com",
    "imgix.net", "cdninstagram.com", "cdnjs.cloudflare", "cloudflare.com",
    "fonts.googleapis", "fonts.gstatic", "googletagmanager",
    "google-analytics", "gstatic.com", "jsdelivr.net", "unpkg.com",
    "youtu.be", "youtube.com",
    # Auto-promo Joy laissée en pied de page des fiches PA
    "joy.io",
)


def _extract_links_from_html(html: str) -> dict[str, str | None]:
    """Applique les regex + sélection du site officiel sur le HTML rendu."""
    out: dict[str, str | None] = {k: None for k in _PATTERNS}
    out["site_officiel"] = None
    for key, pat in _PATTERNS.items():
        m = pat.search(html)
        if m:
            out[key] = _html_lib.unescape(m.group(0).rstrip('".\',;:)'))
    for href in re.findall(r'href=["\'](https?://[^"\'<> ]+)', html):
        d = href.lower()
        if any(skip in d for skip in _SKIP_DOMAINS):
            continue
        out["site_officiel"] = _html_lib.unescape(href)
        break
    found = [k for k, v in out.items() if v]
    logger.info(f"[fiche_links] {len(found)} liens externes rendus : {found}")
    return out


async def fetch_rendered_html_and_links(
    url_fiche: str, timeout: float = 15.0,
) -> tuple[str, dict[str, str | None]]:
    """Un seul appel Playwright : retourne (html_rendu, links_dict).
    Indispensable pour parse_fiche_html qui lit le JSON injecté côté client.
    Fail-open : si Chromium plante, retourne ('', {tous None})."""
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            ctx = await browser.new_context(user_agent=_USER_AGENT)
            page = await ctx.new_page()
            await page.goto(url_fiche, wait_until="networkidle", timeout=int(timeout * 1000))
            html = await page.content()
            await browser.close()
        return html, _extract_links_from_html(html)
    except Exception as e:
        logger.warning(f"[fiche_links] Playwright échoué ({e}) — fallback")
        empty = {k: None for k in _PATTERNS}
        empty["site_officiel"] = None
        return "", empty


async def extract_fiche_links(url_fiche: str, timeout: float = 15.0) -> dict[str, str | None]:
    """API legacy : un seul Playwright, on garde uniquement les links."""
    _, links = await fetch_rendered_html_and_links(url_fiche, timeout=timeout)
    return links


_PLACE_ID_RE = re.compile(r'query_place_id=([^&"\']+)', re.I)


def extract_place_id(google_maps_url: str | None) -> str | None:
    """Extrait le place_id depuis une URL Google Maps de la fiche Privateaser."""
    if not google_maps_url:
        return None
    m = _PLACE_ID_RE.search(google_maps_url)
    return m.group(1) if m else None


async def fetch_gbp_data(place_id: str) -> dict | None:
    """Récupère note + nb d'avis + 5 derniers avis via Google Places Details API.
    Fail-open : timeout/erreur/no-key → None, step 1 retombe sur web_search."""
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
