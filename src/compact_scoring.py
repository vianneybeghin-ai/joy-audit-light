"""Scoring déterministe pur — pas de LLM ici. Distillé des guardrails du
repo principal (G60/G74/G80/G91/G92/G93/G97), barème /100 frozen v1."""
from __future__ import annotations
import re
from .compact_schemas import FicheLight, PhotoTag, GBPData, ScoreBlock

_FESTIF_ADN_KW = ("concert", "dj", "live", "dansant", "club", "soirée", "soiree")
_GROUP_PROMO_RE = re.compile(
    r"(d[èe]s|à partir de|a partir de|pour les groupes?|tabl[ée]es? de)\s*\d+\s*"
    r"(pers|personnes?|pax|invit[ée]s?)",
    re.I,
)


def _has_festif_adn(fiche: FicheLight) -> bool:
    atout = (fiche.atout_signature or "").lower()
    edito = (fiche.edito_principal or "").lower()
    if any(k in atout for k in _FESTIF_ADN_KW) or any(k in edito for k in _FESTIF_ADN_KW):
        return True
    signaux = 0
    if "festive" in [a.lower() for a in fiche.ambiances_cochees]:
        signaux += 1
    if fiche.possibilite_danser:
        signaux += 1
    if fiche.horaire_fin:
        m = re.search(r"(\d{1,2})", fiche.horaire_fin)
        if m:
            h = int(m.group(1))
            if h <= 5 or h >= 23:
                signaux += 1
    if any(k in " ".join(fiche.occasions_cochees).lower() for k in _FESTIF_ADN_KW):
        signaux += 1
    if any(k in edito for k in _FESTIF_ADN_KW):
        signaux += 1
    return signaux >= 3


def score_photos(fiche: FicheLight, tags: list[PhotoTag]) -> ScoreBlock:
    """Photos /40 — applique les caps déterministes (G74/G92/G97)."""
    if not tags:
        return ScoreBlock(section="Photos", points=14.0, points_max=40,
                          commentaire="Pas d'échantillon photos exploitable.")
    n = len(tags)
    n_ai = sum(1 for t in tags if t.ai_altered)
    n_festive = sum(1 for t in tags if t.eclairage_festif)
    n_dansant = sum(1 for t in tags if t.projection_festif_dansant)
    n_group = sum(1 for t in tags if t.config_groupe)
    n_large = sum(1 for t in tags if t.plan == "large")
    ai_ratio = n_ai / n
    festive_ratio = n_festive / n
    dansant_ratio = n_dansant / n
    festif_adn = _has_festif_adn(fiche)

    score = 35.0
    comment_parts = []

    if ai_ratio > 0.20:
        score = min(score, 14.0)
        comment_parts.append(f"{n_ai}/{n} photos suspectes IA — note ramenée à 14/40.")

    if festif_adn:
        if festive_ratio < 0.30:
            score = min(score, 7.0)
            comment_parts.append("Lieu festif mais photos pas festives — note ramenée à 7/40.")
        elif dansant_ratio < 0.15:
            score = min(score, 22.0)
            comment_parts.append("Festif intimiste sans infrastructure dansante — note ramenée à 22/40.")
    else:
        if n_group == 0 and n_large == 0:
            score = min(score, 14.0)
            comment_parts.append("Aucune projection groupe ni vue large — note ramenée à 14/40.")

    return ScoreBlock(section="Photos", points=score, points_max=40,
                      commentaire=" ".join(comment_parts) or "Galerie cohérente.")


def score_video(fiche: FicheLight) -> ScoreBlock:
    pts = 10 if fiche.has_video else 0
    return ScoreBlock(section="Vidéo", points=pts, points_max=10,
                      commentaire="Vidéo présente." if pts else "Pas de vidéo (P1 à ajouter).")


def score_conditions_promo(fiche: FicheLight) -> ScoreBlock:
    """Conditions & Promo /12 — friction sur devis (G93) + graduation HH (G60)."""
    pts = 12.0
    notes = []

    # G93 — sur devis
    sur_devis = [
        e for e in fiche.espaces
        if re.search(r"sur\s*devis|on\s*estimate|presupuesto", (e.get("condition_reservation") or ""), re.I)
    ]
    if sur_devis:
        petit = [e for e in sur_devis if (e.get("capa_max") or 0) <= 25]
        if petit:
            pts -= 3
            notes.append(f"{len(petit)} petit(s) espace(s) en sur devis (friction).")
        if len(sur_devis) == len(fiche.espaces) and fiche.espaces:
            pts -= 2
            notes.append("Aucun espace instantanément réservable.")

    # G60 — promo
    promos = fiche.promotions or []
    group_promo = any(_GROUP_PROMO_RE.search(f"{p.get('titre','')} {p.get('conditions','')}") for p in promos)
    if not promos:
        pts -= 3
        notes.append("Aucune promo ni HH affiché.")
    elif not group_promo:
        # check HH large
        hh_hours = 0.0
        hh_late = False
        for p in promos:
            if "happy" not in (p.get("titre", "")).lower():
                continue
            fen = (p.get("fenetre") or p.get("conditions") or "")
            hours = [int(x) for x in re.findall(r"\d{1,2}", fen)]
            if len(hours) >= 2:
                start, end = hours[0], hours[-1]
                duration = (end - start) if end > start else (24 - start + end)
                hh_hours = max(hh_hours, duration)
                if end <= 4 or end >= 23:
                    hh_late = True
        if hh_hours < 4 and not hh_late:
            pts -= 2
            notes.append(f"HH étroit (~{int(hh_hours)}h) sans promo groupe.")

    pts = max(0.0, pts)
    return ScoreBlock(section="Conditions & Promo", points=pts, points_max=12,
                      commentaire=" ".join(notes) or "Conditions claires, promo lisible.")


def _bucket_avis(n: int) -> int:
    if n == 0:  return 0
    if n <= 4:  return 1
    if n <= 10: return 2
    if n <= 20: return 3
    return 4


def score_preuve_sociale(fiche: FicheLight, gbp: GBPData | None) -> ScoreBlock:
    """Preuve sociale /8 — moitié avis PA, moitié avis Google."""
    pts_pa = _bucket_avis(fiche.nb_avis_privateaser)
    pts_google = _bucket_avis(gbp.user_ratings_total or 0) if gbp else 0
    if gbp and gbp.rating and gbp.rating < 4.0:
        pts_google = max(0, pts_google - 1)
    pts = pts_pa + pts_google
    notes = [
        f"{fiche.nb_avis_privateaser} avis Privateaser",
        f"{gbp.user_ratings_total or 0} avis Google" if gbp else "0 avis Google trouvé",
    ]
    return ScoreBlock(section="Preuve sociale", points=float(pts), points_max=8,
                      commentaire=" · ".join(notes))


def score_edito_labels(fiche: FicheLight) -> ScoreBlock:
    """Édito & Labels /10 — heuristique simple sur la longueur édito + atout signature."""
    edito = (fiche.edito_principal or "")
    n_paragraphs = len([p for p in edito.split("\n\n") if p.strip()])
    pts_edito = 4 if n_paragraphs >= 3 else max(0, n_paragraphs)
    pts_labels = 6 if fiche.atout_signature else 3
    notes = [
        f"Édito {n_paragraphs} bloc(s)",
        "atout signature présent" if fiche.atout_signature else "atout signature manquant",
    ]
    return ScoreBlock(section="Édito & Labels", points=float(pts_edito + pts_labels),
                      points_max=10, commentaire=" · ".join(notes))


def score_bases(fiche: FicheLight) -> ScoreBlock:
    """Bases /20 — heuristique présence/absence des champs structurants."""
    pts = 0
    if fiche.capa_max:        pts += 4
    if fiche.horaire_fin:     pts += 2
    if fiche.espaces:         pts += 2
    if fiche.has_pdf_carte:   pts += 3
    if fiche.occasions_cochees: pts += 3
    if fiche.ambiances_cochees: pts += 2
    pts += 4  # baseline (apports, équipements, sélections, lien)
    pts = min(20, pts)
    return ScoreBlock(section="Bases", points=float(pts), points_max=20,
                      commentaire="Présence des champs structurants.")


def compute_score_blocks(fiche: FicheLight, tags: list[PhotoTag],
                          gbp: GBPData | None) -> list[ScoreBlock]:
    """5 blocs scorés purement en Python."""
    return [
        score_photos(fiche, tags),
        score_video(fiche),
        score_conditions_promo(fiche),
        score_preuve_sociale(fiche, gbp),
        score_edito_labels(fiche),
        score_bases(fiche),
    ]


def grade_from_score(score: float) -> str:
    if score >= 85: return "A"
    if score >= 70: return "B"
    if score >= 55: return "C"
    if score >= 40: return "D"
    return "E"
