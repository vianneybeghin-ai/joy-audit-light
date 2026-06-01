"""
Scraping de la page Privateaser (HTML brut).

Les IDs S3 des photos et l'URL de la vidéo ne sont PAS visibles dans le rendu
visuel (donc inaccessibles à Sonnet vision sur le screenshot). On les récupère
ici via les balises <meta itemprop="image|video"> du HTML de la fiche.

Cf. framework.md §0 (Récupération médias) pour la spec des URLs.
"""

import logging
import re

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

_RE_MEDIA = re.compile(
    r'<meta\s+itemprop="(image|video)"\s+content="([^"]+)"',
    re.IGNORECASE,
)
_RE_PHOTO_ID = re.compile(r"/etab_photos/[^/]+/[^/]+/([^/.]+)\.")


def _meta_content(html: str, prop: str) -> str | None:
    m = re.search(
        rf'<meta\s+itemprop="{prop}"\s+content="([^"]+)"', html, re.IGNORECASE
    )
    return m.group(1).strip() if m else None


def _extract_h1(html: str) -> str | None:
    m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.DOTALL | re.IGNORECASE)
    if not m:
        return None
    text = re.sub(r"<[^>]+>", " ", m.group(1))
    return re.sub(r"\s+", " ", text).strip() or None


class PhotoRef(BaseModel):
    photo_id: str
    url: str


class HtmlPhotos(BaseModel):
    """Output du scraper HTML — caché sous 'html_photos' par l'orchestrator."""
    photos: list[PhotoRef]
    video_url: str | None = None
    # G89 — identité de l'établissement extraite du HTML Privateaser.
    # Permet à step 1 de cibler la recherche web sur la BONNE ville (pas un
    # homonyme). Cf. cas Brasserie du Trône / Charenton vs Café du Trône Paris.
    nom_lieu: str | None = None
    adresse_complete: str | None = None  # ex "28 Rue de Verdun, 94220 Charenton-le-Pont"


async def fetch_photos_from_html(
    url_fiche: str,
) -> tuple[list[tuple[str, str]], str | None]:
    """
    Récupère la page Privateaser et extrait photos + vidéo source.

    Returns:
        (photos, video_url) avec photos = liste dédupliquée de (photo_id, url)
        au format 1500x750, et video_url = mp4 SD 480p (préféré : Cloudinary
        bloque désormais l'URL "marketplace_media/offerings/" avec HTTP 401
        "Transformation /mp4 is not allowed"). Fallback sur source originale si
        pas de SD. Les posters .jpg vidéo et tailles intermédiaires sont
        ignorés.
    """
    async with httpx.AsyncClient(
        timeout=20.0,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    ) as http:
        r = await http.get(url_fiche)
        r.raise_for_status()
        html = r.text

    photos: list[tuple[str, str]] = []
    seen: set[str] = set()
    video_source: str | None = None
    video_sd: str | None = None

    for kind, url in _RE_MEDIA.findall(html):
        if kind.lower() == "image":
            # On ne garde que la taille 1500x750 (cf. framework.md §0).
            # Les autres tailles (original ~15MB, 750x375, etc.) sont ignorées :
            # original dépasse les 5 MB max de l'API Anthropic vision.
            if "/1500x750/" not in url:
                continue
            m = _RE_PHOTO_ID.search(url)
            if not m:
                continue
            pid = m.group(1)
            if pid in seen:
                continue
            seen.add(pid)
            photos.append((pid, url))
        else:  # video
            if not url.endswith(".mp4"):
                continue
            if "marketplace_media/offerings/" in url and video_source is None:
                video_source = url
            elif "t_video-delivery-sd480-mp4" in url and video_sd is None:
                video_sd = url

    # SD d'abord : l'URL originale "marketplace_media/offerings/" renvoie HTTP
    # 401 sur les fiches récentes (verrou Cloudinary). La SD 480p est largement
    # suffisante pour Sonnet vision sur les frames extraites (~2 MB vs ~15 MB).
    video_url = video_sd or video_source

    # G89 — identité du lieu : nom (h1) + adresse postale (meta itemprop).
    # Compose l'adresse complète pour la passer à step 1 (web search).
    nom_lieu = _extract_h1(html)
    street = _meta_content(html, "streetAddress")
    postal = _meta_content(html, "postalCode")
    locality = _meta_content(html, "addressLocality")
    adresse_complete: str | None = None
    if street and locality:
        adresse_complete = f"{street}, {postal or ''} {locality}".strip().replace("  ", " ")

    logger.info(
        f"[scraper] {len(photos)} photos · vidéo: {'oui' if video_url else 'non'}"
        f" · lieu={nom_lieu!r} · adresse={adresse_complete!r}"
    )
    return photos, video_url, nom_lieu, adresse_complete
