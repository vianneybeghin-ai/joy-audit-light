"""
Upload du rapport HTML.

Mode automatique:
- Si vars R2 présentes (R2_ACCOUNT_ID + R2_ACCESS_KEY_ID + R2_SECRET_ACCESS_KEY)
  → upload vers Cloudflare R2, retourne URL publique
- Sinon → écrit en local dans LOCAL_HTML_OUTPUT_DIR (ou ./output/audits/)
  retourne le chemin absolu (utilisable comme file://...)

Pour démarrer rapidement sans R2, ne définis aucune des vars R2_*
et laisse le pipeline tourner en mode local.
"""

import asyncio
import logging
import re
import unicodedata
from pathlib import Path

from .config import (
    LOCAL_HTML_OUTPUT_DIR,
    PROJECT_ROOT,
    R2_ACCESS_KEY_ID,
    R2_ACCOUNT_ID,
    R2_BUCKET,
    R2_PUBLIC_DOMAIN,
    R2_SECRET_ACCESS_KEY,
    USE_R2,
)

logger = logging.getLogger(__name__)


def _slugify(text: str) -> str:
    """Convertit 'Les Foodies' en 'les-foodies'."""
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    text = re.sub(r"[-\s]+", "-", text)
    return text


def _local_output_dir() -> Path:
    """Détermine le dossier de sortie local."""
    if LOCAL_HTML_OUTPUT_DIR:
        return Path(LOCAL_HTML_OUTPUT_DIR)
    return PROJECT_ROOT / "output" / "audits"


async def _upload_local(audit_id: str, nom_lieu: str, html: str) -> str:
    """Mode local : écrit le HTML sur disque, retourne le chemin absolu."""
    slug = _slugify(nom_lieu)
    short_id = audit_id[:8]
    output_dir = _local_output_dir()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{short_id}-{slug}.html"

    output_path.write_text(html, encoding="utf-8")

    abs_url = f"file://{output_path.absolute()}"
    logger.info(f"HTML écrit en local: {output_path}")
    return abs_url


async def _upload_r2(audit_id: str, nom_lieu: str, html: str) -> str:
    """Mode R2 : upload vers Cloudflare R2, retourne URL publique."""
    import boto3

    slug = _slugify(nom_lieu)
    short_id = audit_id[:8]
    key = f"audits-light/{short_id}-{slug}.html"

    def _put():
        client = boto3.client(
            "s3",
            endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
            aws_access_key_id=R2_ACCESS_KEY_ID,
            aws_secret_access_key=R2_SECRET_ACCESS_KEY,
            region_name="auto",
        )
        client.put_object(
            Bucket=R2_BUCKET,
            Key=key,
            Body=html.encode("utf-8"),
            ContentType="text/html; charset=utf-8",
            CacheControl="public, max-age=300",
        )

    await asyncio.to_thread(_put)

    public_url = f"https://{R2_PUBLIC_DOMAIN}/{key}"
    logger.info(f"HTML uploadé sur R2: {public_url}")
    return public_url


async def upload_html(audit_id: str, nom_lieu: str, html: str) -> str:
    """
    Upload le HTML. Bascule auto local/R2 selon les vars d'env présentes.
    """
    if USE_R2:
        return await _upload_r2(audit_id, nom_lieu, html)
    return await _upload_local(audit_id, nom_lieu, html)


async def publish_html(html: str, slug: str) -> str:
    """Adapter pour main.py — génère un audit_id à la volée."""
    import uuid
    return await upload_html(uuid.uuid4().hex, slug, html)
