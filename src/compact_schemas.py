"""Pydantic compacts — schema interne du module light.
Pas de couplage avec les schemas du repo principal (intentionnel)."""
from __future__ import annotations
from typing import Optional, Literal
from pydantic import BaseModel, Field


class PhotoTag(BaseModel):
    """Tags Sonnet vision sur une photo (5 batch en step 3)."""
    url: str
    ai_altered: bool = False
    eclairage_festif: bool = False
    projection_festif_dansant: bool = False
    config_groupe: bool = False
    plan: Literal["large", "serré", "moyen", "autre"] = "autre"
    description_courte: str = Field("", description="1 phrase factuelle")


class ScoreBlock(BaseModel):
    """Un bloc de score déterministe (5 blocs au total)."""
    section: str
    points: float
    points_max: int
    commentaire: str = ""


class Action(BaseModel):
    """Une action P0 (exactement 3 par audit)."""
    titre: str = Field(description="5-8 mots, verbe à l'infinitif")
    description: str = Field(description="1-2 phrases concrètes")
    priorite: Literal["P0", "P1", "P2"] = "P0"
    section: str = ""


class FicheLight(BaseModel):
    """Fiche Privateaser allégée (juste ce dont on a besoin pour scorer)."""
    nom: str
    slug: str = ""
    url: str
    type_lieu: Optional[str] = None
    capa_max: Optional[int] = None
    nb_photos: int = 0
    photos: list[str] = Field(default_factory=list)
    nb_avis_privateaser: int = 0
    edito_principal: Optional[str] = None
    atout_signature: Optional[str] = None
    has_video: bool = False
    has_pdf_carte: bool = False
    horaire_fin: Optional[str] = None
    occasions_cochees: list[str] = Field(default_factory=list)
    possibilite_danser: bool = False
    ambiances_cochees: list[str] = Field(default_factory=list)
    espaces: list[dict] = Field(default_factory=list)
    promotions: list[dict] = Field(default_factory=list)
    permanently_closed: bool = False


class GBPData(BaseModel):
    rating: Optional[float] = None
    user_ratings_total: Optional[int] = None
    reviews_count_with_group_kw: int = 0
    permanently_closed: bool = False


class AuditLightResult(BaseModel):
    url: str
    score: int
    grade: str
    blocks: list[ScoreBlock]
    actions: list[Action]
    photo_tags: list[PhotoTag] = Field(default_factory=list)
    gbp: Optional[GBPData] = None
    fiche: FicheLight
    duration_seconds: float = 0.0
    cost_estimate_usd: float = 0.0
