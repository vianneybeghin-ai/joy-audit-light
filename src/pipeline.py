"""Orchestration des 4 steps. Cible : ~$0.20 / audit, ~25 s end-to-end."""
from __future__ import annotations
import logging
import re
import time

from .compact_schemas import AuditLightResult, FicheLight, GBPData, PhotoTag
from .compact_scoring import compute_score_blocks, grade_from_score
from .fiche_links import fetch_rendered_html_and_links
from .fiche_parser import parse_fiche_html
from .gbp import count_group_reviews, extract_place_id, fetch_gbp_data
from .privateaser_scraper import fetch_photos_from_html
from .steps_light import sample_photos, step3_light_vision, step4_light_scoring

logger = logging.getLogger(__name__)


def _slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or "audit"


async def _enrich_with_photos(fiche: FicheLight) -> None:
    """Complète la fiche avec photos + vidéo via fetch_photos_from_html (httpx)."""
    photo_tuples, video_url, _scraped_nom, _adresse = await fetch_photos_from_html(fiche.url)
    fiche.photos = [url for _, url in photo_tuples]
    fiche.nb_photos = len(fiche.photos)
    fiche.video_url = video_url
    fiche.has_video = bool(video_url)


async def _scrape_fiche_light(url_fiche: str) -> FicheLight:
    """Utilisé par les tests : récupère HTML rendu + parse + enrich photos.
    N'inclut pas l'appel Places API ni les steps LLM."""
    html, _links = await fetch_rendered_html_and_links(url_fiche)
    fiche = parse_fiche_html(html, url_fiche) if html else FicheLight(
        nom="Fiche Privateaser", slug="audit", url=url_fiche,
    )
    await _enrich_with_photos(fiche)
    return fiche


async def run_audit_light(url_fiche: str) -> AuditLightResult:
    cost_ledger = {"total": 0.0}
    t0 = time.time()

    # Step 1+2 — 1 seul Playwright pour le HTML rendu, parsing JSON-first, photos httpx
    html, links = await fetch_rendered_html_and_links(url_fiche)
    place_id = extract_place_id(links.get("google_maps"))
    gbp_raw = await fetch_gbp_data(place_id) if place_id else None
    gbp = None
    if gbp_raw:
        gbp = GBPData(
            rating=gbp_raw.get("rating"),
            user_ratings_total=gbp_raw.get("user_ratings_total") or 0,
            reviews_count_with_group_kw=count_group_reviews(gbp_raw.get("reviews", [])),
            permanently_closed=gbp_raw.get("permanently_closed", False),
        )

    fiche = parse_fiche_html(html, url_fiche) if html else FicheLight(
        nom="Fiche Privateaser", slug="audit", url=url_fiche,
    )
    await _enrich_with_photos(fiche)
    if gbp and gbp.permanently_closed:
        fiche.permanently_closed = True

    # Step 3 — vision Sonnet sur 5 photos (batch)
    sampled = sample_photos(fiche.photos, k=5)
    photo_tags: list[PhotoTag] = await step3_light_vision(sampled, cost_ledger)

    # Step 4 — Sonnet pour 3 actions (sur la base des scores déjà calculés)
    score_blocks = compute_score_blocks(fiche, photo_tags, gbp)
    actions = await step4_light_scoring(fiche, photo_tags, gbp, score_blocks, cost_ledger)

    score = sum(b.points for b in score_blocks)
    duration = time.time() - t0
    logger.info(f"[pipeline] {fiche.nom} score={score:.0f} duration={duration:.1f}s "
                f"cost=${cost_ledger['total']:.3f}")

    return AuditLightResult(
        url=url_fiche, score=int(round(score)), grade=grade_from_score(score),
        blocks=score_blocks, actions=actions,
        photo_tags=photo_tags, gbp=gbp, fiche=fiche,
        duration_seconds=duration,
        cost_estimate_usd=cost_ledger["total"],
    )
