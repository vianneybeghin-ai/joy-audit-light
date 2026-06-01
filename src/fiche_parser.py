"""Parse une fiche Privateaser depuis son HTML rendu (Playwright).

Stratégie : Privateaser injecte un objet JSON de 90+ champs dans un <script>.
On l'extrait en priorité (single source of truth, déterministe, robuste).
BeautifulSoup en fallback pour les champs absents du payload (ex : selections,
qui sont rendues côté serveur).

Fail-safe : chaque sous-fonction retourne la valeur par défaut du schéma si
elle ne trouve rien — jamais d'exception."""
from __future__ import annotations
import json
import logging
import re
from typing import Any, Optional

from bs4 import BeautifulSoup

from .compact_schemas import Espace, FicheLight, Promotion

logger = logging.getLogger(__name__)

_PRICE_RANGE_TO_GAMME = {
    "cheap": "€",
    "medium": "€€",
    "expensive": "€€€",
    "very_expensive": "€€€€",
}

# Liste des occasions → libellés FR lisibles
_OCCASION_LABELS = {
    "afterwork": "Afterwork",
    "afterwork_pro": "Afterwork pro",
    "baby_shower": "Baby shower",
    "bachelor_bachelorette_party": "EVG / EVJF",
    "baptism": "Baptême",
    "birthday": "Anniversaire",
    "birthday_18": "Anniversaire 18-20 ans",
    "birthday_20": "Anniversaire 20-25 ans",
    "birthday_30": "Anniversaire 30 ans",
    "birthday_40": "Anniversaire 40+ ans",
    "birthday_casual_party": "Anniversaire (soirée)",
    "business_dinner": "Dîner d'affaires",
    "casual_event": "Évènement informel",
    "casual_party": "Soirée informelle",
    "christmas_party": "Soirée de Noël",
    "cocktail_pro": "Cocktail pro",
    "communion": "Communion",
    "conference": "Conférence",
    "corporate_event": "Évènement d'entreprise",
    "drinks_with_friends": "Verre entre amis",
    "engagement": "Fiançailles",
    "evg": "EVG",
    "evjf": "EVJF",
    "family_meal": "Repas de famille",
    "graduation": "Remise de diplôme",
    "student_party": "Soirée étudiante",
    "team_building": "Team building",
    "wedding": "Mariage / PACS",
    "workshop": "Atelier",
}


def _extract_payload(soup: BeautifulSoup) -> Optional[dict]:
    """Extrait le JSON injecté par Privateaser (90 champs, source de vérité).
    Retourne None si introuvable."""
    for sc in soup.find_all("script"):
        txt = sc.get_text() or ""
        if "all_occasions" in txt and "rooms" in txt:
            start = txt.find("{")
            end = txt.rfind("}")
            if start >= 0 and end > start:
                try:
                    return json.loads(txt[start:end + 1])
                except json.JSONDecodeError:
                    logger.warning("[parser] JSON payload trouvé mais non décodable")
                    return None
    return None


def _slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or "audit"


def _ambiances_from_payload(data: dict) -> list[str]:
    """music_0=Calme, music_1=Animée, music_2=Festive — bool si coché."""
    out = []
    labels = ["Calme", "Animée", "Festive"]
    for i, label in enumerate(labels):
        if data.get(f"music_{i}"):
            out.append(label)
    return out


def _occasions_from_payload(data: dict) -> list[str]:
    raw = data.get("all_occasions") or []
    return [_OCCASION_LABELS.get(o, o) for o in raw]


def _equipements_from_payload(data: dict) -> list[str]:
    """Compose la liste depuis les flags 'service_*' du payload."""
    mapping = {
        "service_my_music": "Possibilité de diffuser sa musique",
        "service_projector": "Projecteur",
        "service_games": "Jeux",
    }
    return [
        label for key, label in mapping.items()
        if str(data.get(key) or "").strip().lower() in ("oui", "true", "si", "sí", "yes")
    ]


def _apports_from_payload(data: dict) -> list[str]:
    """Compose depuis bring_in_food / drinks / cake."""
    mapping = {
        "bring_in_food": "Nourriture",
        "bring_in_drinks": "Boissons",
        "bring_in_cake": "Gâteau d'anniversaire",
    }
    out = []
    for key, label in mapping.items():
        val = (data.get(key) or "").strip()
        if val and val.lower() not in ("non", "no"):
            out.append(label)
    return out


def _espaces_from_payload(data: dict) -> list[Espace]:
    """Lit booking_options_data_aggregated (3 espaces typiques : area, room:*, complete)."""
    raw = data.get("booking_options_data_aggregated") or []
    out: list[Espace] = []
    for opt in raw:
        if not isinstance(opt, dict):
            continue
        nom = opt.get("title") or "Espace"
        cmin = opt.get("pax_min") or 0
        cmax = opt.get("pax_max") or 0
        # Conditions : on lit le 1er set du 1er weekday_group
        conds = None
        instant = False
        for grp in (opt.get("weekdays_groups") or []):
            for s in (grp.get("sets") or []):
                cfg = s.get("config") or {}
                conds = cfg.get("conditions") or {}
                instant = bool(cfg.get("instant_booking_enabled"))
                break
            if conds:
                break
        cond_str = _format_condition(conds or {})
        out.append(Espace(
            nom=nom, capa_min=int(cmin), capa_max=int(cmax),
            condition_reservation=cond_str, instant_booking_enabled=instant,
        ))
    return out


def _format_condition(c: dict) -> str:
    """Formate une chaîne lisible depuis le dict conditions du payload."""
    if c.get("mandatory_quote"):
        msf = c.get("minimum_spend_fixed") or 0
        if msf > 0:
            return f"Sur devis, à partir de {int(msf)} € TTC"
        return "Sur devis"
    if c.get("dry_hire"):
        return "Réservation gratuite"
    msp = c.get("minimum_spend_per_pax") or 0
    msf = c.get("minimum_spend_fixed") or 0
    if msp > 0:
        return f"Minimum de consommation {int(msp)} €/pers"
    if msf > 0:
        return f"Minimum de consommation {int(msf)} € total"
    return "Réservation gratuite"


def _promotions_from_payload(data: dict) -> list[Promotion]:
    """Combine enabled_promotions + Happy Hours."""
    out: list[Promotion] = []
    _DAYS = ["lun", "mar", "mer", "jeu", "ven", "sam", "dim"]

    for p in (data.get("enabled_promotions") or []):
        if not isinstance(p, dict) or p.get("disabled"):
            continue
        titre = p.get("nom") or p.get("name") or "Promotion"
        nb_min = p.get("nb_min")
        days_idx = p.get("index_days_available") or []
        fen = " ".join(_DAYS[i] for i in days_idx if 0 <= i < 7) if days_idx else None
        conds = p.get("conditions") or ""
        if nb_min and not conds:
            conds = f"Groupe à partir de {nb_min} personnes"
        out.append(Promotion(
            titre=titre, conditions=conds, fenetre=fen, nb_min=nb_min,
        ))

    if data.get("has_happy_hours"):
        ranges = data.get("happy_hours_weekday_ranges") or []
        days_str = ""
        if ranges and isinstance(ranges[0], list) and len(ranges[0]) == 2:
            a, b = ranges[0]
            if 0 <= a <= 6 and 0 <= b <= 6:
                if a == 0 and b == 6:
                    days_str = "lun-dim"
                else:
                    days_str = f"{_DAYS[a]}-{_DAYS[b]}"
        out.append(Promotion(
            titre="Happy Hour", conditions="", fenetre=days_str or None,
        ))

    return out


def _horaire_fin_from_dom(soup: BeautifulSoup) -> Optional[str]:
    """Extrait la fin d'ouverture depuis itemprop=openingHours (ex 'Mo-Su 09:00-02:00')."""
    el = soup.find(attrs={"itemprop": "openingHours"})
    if not el:
        return None
    val = el.get("content") or el.get_text(" ", strip=True)
    m = re.search(r"\d{1,2}:\d{2}-(\d{1,2}:\d{2})", val)
    return m.group(1) if m else None


def _selections_from_dom(soup: BeautifulSoup) -> list[str]:
    """Sélections Privateaser (h2 'Ce lieu fait partie de nos sélections').
    On limite aux liens immédiatement sous le h2 — pas tous les liens du parent."""
    for h2 in soup.find_all("h2"):
        t = h2.get_text(strip=True).lower()
        if "fait partie" not in t:
            continue
        out: list[str] = []
        # Scanne les siblings du h2 jusqu'au prochain h2/h3
        for sib in h2.find_next_siblings():
            if sib.name in ("h2", "h3"):
                break
            for a in sib.find_all("a"):
                txt = a.get_text(strip=True)
                if 5 < len(txt) < 120 and "voir" not in txt.lower() and "tout" not in txt.lower()[:5]:
                    out.append(txt)
        # Dédup en gardant l'ordre, limite 12
        seen, uniq = set(), []
        for s in out:
            if s not in seen:
                seen.add(s); uniq.append(s)
        return uniq[:12]
    return []


def _capa_max_from_payload(data: dict) -> Optional[int]:
    v = data.get("complete_capacity") or data.get("nbr_max")
    return int(v) if v else None


def _atout_from_edito(edito: str) -> Optional[str]:
    """Extrait la 1re phrase de l'atout (après 'Pourquoi organiser… : ').
    Multi-langue : FR (Pourquoi organiser), ES (Por qué organizar)."""
    if not edito:
        return None
    # Pattern principal : capture jusqu'au séparateur (paragraphe / **bloc / emoji)
    m = re.search(
        r"(?:Pourquoi\s+organiser|Por\s+qu[ée]\s+organizar)[^:]*:\s*\*{0,2}\s*(.{40,600}?)(?:\r?\n\r?\n|\*\*|🎉|✨)",
        edito, re.I | re.S,
    )
    if m:
        return re.sub(r"\s+", " ", m.group(1)).strip(" *")
    # Fallback : 1re ligne non vide, après le ': ' s'il y en a un (skip le préfixe entête)
    for line in edito.splitlines():
        line = line.strip(" *🍺🎉✨🍷🍸")
        if len(line) <= 30:
            continue
        if ": " in line:
            line = line.split(": ", 1)[1].strip(" *")
        return line[:300]
    return None


def parse_fiche_html(html: str, url: str) -> FicheLight:
    """Parse le HTML rendu d'une fiche Privateaser. Fail-safe."""
    soup = BeautifulSoup(html, "html.parser")
    data = _extract_payload(soup) or {}

    if not data:
        logger.warning(f"[parser] JSON payload introuvable pour {url}")

    nom = data.get("name") or data.get("nom") or "Fiche Privateaser"
    edito = data.get("editorial_description") or data.get("catch_phrase") or None
    danse = data.get("dancing_possible")
    danse_detail = danse if isinstance(danse, str) and danse.strip() else None
    has_danse = bool(danse and (not isinstance(danse, str) or "non" not in danse.lower()
                                and "no, " not in danse.lower()))

    return FicheLight(
        url=url,
        nom=nom,
        slug=_slugify(nom),
        type_lieu=(data.get("concept_labels") or [{}])[0].get("displayed_label")
                  if data.get("concept_labels") else None,
        capa_max=_capa_max_from_payload(data),
        nb_avis_privateaser=int(data.get("approved_review_count") or 0),
        note_privateaser=data.get("review_score"),
        edito_principal=edito,
        atout_signature=_atout_from_edito(edito or ""),
        horaire_fin=_horaire_fin_from_dom(soup),
        gamme=_PRICE_RANGE_TO_GAMME.get(data.get("price_range") or "", None),
        occasions_cochees=_occasions_from_payload(data),
        possibilite_danser=has_danse,
        possibilite_danser_detail=danse_detail,
        ambiances_cochees=_ambiances_from_payload(data),
        equipements_services=_equipements_from_payload(data),
        apports_autorises=_apports_from_payload(data),
        selections=_selections_from_dom(soup),
        espaces=_espaces_from_payload(data),
        promotions=_promotions_from_payload(data),
        permanently_closed=bool(data.get("permanently_closed")),
    )
