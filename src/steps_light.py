"""Steps LLM : 1 appel vision batch (5 photos) + 1 appel scoring/actions.
Cible : ~$0.18 cumulé. Pricing Sonnet 4.5 input $3/Mtok, output $15/Mtok."""
from __future__ import annotations
import asyncio
import base64
import json
import logging
import os
import random

import httpx
from anthropic import AsyncAnthropic

from .compact_kb import COMPACT_KB
from .compact_schemas import PhotoTag, FicheLight, GBPData, ScoreBlock, Action

logger = logging.getLogger(__name__)

MODEL_SONNET = "claude-sonnet-4-6"

# Prix au million de tokens
_PRICE_IN = 3.0 / 1_000_000
_PRICE_OUT = 15.0 / 1_000_000


def _cost(usage) -> float:
    if usage is None:
        return 0.0
    return usage.input_tokens * _PRICE_IN + usage.output_tokens * _PRICE_OUT


def sample_photos(photos: list[str], k: int = 5) -> list[str]:
    if not photos:
        return []
    if len(photos) <= k:
        return photos
    # 1 photo de chaque "tiers" + 2 random pour couvrir la galerie
    sorted_photos = list(photos)
    n = len(sorted_photos)
    picks = [sorted_photos[0], sorted_photos[n // 3], sorted_photos[2 * n // 3]]
    remaining = [p for p in sorted_photos if p not in picks]
    picks += random.sample(remaining, min(2, len(remaining)))
    return picks[:k]


async def _fetch_image_b64(client: httpx.AsyncClient, url: str) -> tuple[str, str] | None:
    try:
        r = await client.get(url, timeout=10, follow_redirects=True)
        r.raise_for_status()
        media_type = r.headers.get("content-type", "image/jpeg").split(";")[0]
        return base64.b64encode(r.content).decode("ascii"), media_type
    except Exception as e:
        logger.warning(f"[step3] fetch photo échoué {url}: {e}")
        return None


_PHOTOS_TOOL = {
    "name": "save_photo_tags",
    "description": "Renvoie les tags pour chaque photo de l'échantillon",
    "input_schema": {
        "type": "object",
        "properties": {
            "tags": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "index": {"type": "integer"},
                        "ai_altered": {"type": "boolean"},
                        "eclairage_festif": {"type": "boolean"},
                        "projection_festif_dansant": {"type": "boolean"},
                        "config_groupe": {"type": "boolean"},
                        "plan": {"type": "string", "enum": ["large", "serré", "moyen", "autre"]},
                        "description_courte": {"type": "string"},
                    },
                    "required": ["index", "ai_altered", "eclairage_festif",
                                  "projection_festif_dansant", "config_groupe", "plan",
                                  "description_courte"],
                },
            }
        },
        "required": ["tags"],
    },
}


async def step3_light_vision(photo_urls: list[str], cost_ledger: dict) -> list[PhotoTag]:
    """Appel batch Sonnet vision sur l'échantillon (5 photos)."""
    if not photo_urls:
        return []
    client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    async with httpx.AsyncClient() as http:
        images = await asyncio.gather(*[_fetch_image_b64(http, u) for u in photo_urls])
    content: list = []
    for i, img in enumerate(images):
        if img is None:
            continue
        b64, media_type = img
        content.append({"type": "text", "text": f"Photo {i}"})
        content.append({"type": "image", "source": {
            "type": "base64", "media_type": media_type, "data": b64,
        }})
    content.append({"type": "text", "text": (
        "Tagge chaque photo. Règles strictes :\n"
        "- ai_altered : signes IA (peau lissée, doigts aberrants, poses synchronisées).\n"
        "- eclairage_festif : DOMINANTE basse/tamisée/chaude. Un seul néon dans une "
        "salle blanche diffuse = FALSE.\n"
        "- projection_festif_dansant : booth DJ / dancefloor / éclairage scénique / "
        "estrade / standing dominant visibles.\n"
        "- config_groupe : tablée longue, mange-debout, salle large dégagée.\n"
        "- plan : 'large' si vue d'ensemble, 'serré' si zoom détail.\n"
        "- description_courte : 1 phrase factuelle (< 100 caractères).\n"
        "Appelle save_photo_tags avec un tag par photo (ordre conservé)."
    )})

    resp = await client.messages.create(
        model=MODEL_SONNET,
        max_tokens=1500,
        tools=[_PHOTOS_TOOL],
        tool_choice={"type": "tool", "name": "save_photo_tags"},
        messages=[{"role": "user", "content": content}],
    )
    cost_ledger["total"] = cost_ledger.get("total", 0.0) + _cost(resp.usage)

    tool_use = next((b for b in resp.content if b.type == "tool_use"), None)
    if not tool_use:
        return []
    raw_tags = tool_use.input.get("tags", [])
    tags: list[PhotoTag] = []
    for t in raw_tags:
        idx = t.get("index", 0)
        url = photo_urls[idx] if 0 <= idx < len(photo_urls) else ""
        tags.append(PhotoTag(
            url=url,
            ai_altered=t.get("ai_altered", False),
            eclairage_festif=t.get("eclairage_festif", False),
            projection_festif_dansant=t.get("projection_festif_dansant", False),
            config_groupe=t.get("config_groupe", False),
            plan=t.get("plan", "autre"),
            description_courte=t.get("description_courte", ""),
        ))
    return tags


_ACTIONS_TOOL = {
    "name": "save_actions",
    "description": "Renvoie exactement 3 actions P0 concrètes",
    "input_schema": {
        "type": "object",
        "properties": {
            "actions": {
                "type": "array",
                "minItems": 3,
                "maxItems": 3,
                "items": {
                    "type": "object",
                    "properties": {
                        "titre": {"type": "string"},
                        "description": {"type": "string"},
                        "section": {"type": "string"},
                    },
                    "required": ["titre", "description", "section"],
                },
            }
        },
        "required": ["actions"],
    },
}


async def step4_light_scoring(fiche: FicheLight, tags: list[PhotoTag],
                                gbp: GBPData | None, blocks: list[ScoreBlock],
                                cost_ledger: dict) -> list[Action]:
    """Sonnet ne joue PAS le rôle de scorer ici (déjà fait en code) — il
    génère uniquement 3 actions P0 concrètes basées sur les blocs."""
    client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    blocks_md = "\n".join(
        f"- **{b.section}** : {b.points:.0f}/{b.points_max} — {b.commentaire}"
        for b in blocks
    )
    tags_md = "\n".join(
        f"- {t.description_courte} (festif={t.eclairage_festif}, "
        f"dansant={t.projection_festif_dansant}, groupe={t.config_groupe}, "
        f"ia={t.ai_altered})"
        for t in tags
    )

    prompt = f"""{COMPACT_KB}

# Fiche auditée : {fiche.nom}
- URL : {fiche.url}
- Type : {fiche.type_lieu or "?"} · capa max : {fiche.capa_max or "?"} · {fiche.nb_photos} photos
- ADN : atout = « {fiche.atout_signature or "—"} » · édito = {len(fiche.edito_principal or "")} chars
- Privateaser : {fiche.nb_avis_privateaser} avis
- Google : {gbp.user_ratings_total if gbp else 0} avis · note {gbp.rating if gbp else "?"}

## Photos échantillonnées
{tags_md or "(pas d'échantillon)"}

## Scores déterministes (DÉJÀ calculés en Python — ne RE-score PAS)
{blocks_md}

## Ta mission
Génère exactement **3 actions P0** concrètes pour faire monter le score, en
priorisant les blocs les plus en retrait. Règles dures :
- Titre = 5-8 mots, verbe à l'infinitif.
- Description = 1-2 phrases, action concrète, jamais en jargon (pas de Gxx, pas de "cap").
- AUCUNE mention de bruit externe (LoopNet, à louer, post-reprise, rachat,
  changement de propriétaire, carte non actualisée, ancien).
- AUCUNE action de maintien (« continuer », « garder »).
- AUCUNE action sur l'ordre des photos.

Appelle save_actions."""

    resp = await client.messages.create(
        model=MODEL_SONNET,
        max_tokens=800,
        tools=[_ACTIONS_TOOL],
        tool_choice={"type": "tool", "name": "save_actions"},
        messages=[{"role": "user", "content": prompt}],
    )
    cost_ledger["total"] = cost_ledger.get("total", 0.0) + _cost(resp.usage)

    tool_use = next((b for b in resp.content if b.type == "tool_use"), None)
    if not tool_use:
        return []
    raw = tool_use.input.get("actions", [])[:3]
    return [Action(titre=a["titre"], description=a["description"],
                   priorite="P0", section=a.get("section", ""))
            for a in raw]
