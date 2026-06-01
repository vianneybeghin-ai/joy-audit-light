"""Golden tests — chaque URL doit retourner un score dans la fourchette attendue
en moins de 30 s et moins de $0.30, sans aucune mention de bruit externe.

Tests parser : vérifient que les champs critiques (capa, espaces, ambiances,
horaire, édito) sont extraits depuis le HTML rendu."""
import time

import pytest

from src.pipeline import _scrape_fiche_light, run_audit_light


GOLDEN_CASES = [
    ("https://www.privateaser.com/lieu/52456-chez-eloise", {"score_range": (70, 90)}),
    ("https://www.privateaser.es/local/52379-Gabys-club", {"score_range": (70, 90)}),
    ("https://www.privateaser.es/local/55798-lina-restaurante", {"score_range": (65, 88)}),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("url,expectations", GOLDEN_CASES)
async def test_golden_case(url, expectations):
    t0 = time.time()
    result = await run_audit_light(url)
    duration = time.time() - t0

    lo, hi = expectations["score_range"]
    assert lo <= result.score <= hi, f"score {result.score} hors [{lo}, {hi}]"
    assert len(result.actions) == 3, f"exactement 3 actions, vu {len(result.actions)}"
    assert duration < 30, f"durée {duration:.1f}s > 30s"
    assert result.cost_estimate_usd < 0.30, f"coût ${result.cost_estimate_usd:.3f} > $0.30"

    forbidden = ("reprise", "rachat", "ancien", "loopnet", "mise en demeure")
    full_text = " ".join(a.titre + " " + a.description for a in result.actions).lower()
    for kw in forbidden:
        assert kw not in full_text, f"bruit externe : « {kw} » dans actions"


@pytest.mark.asyncio
async def test_parser_chez_eloise():
    """Sur Chez Eloise, on doit récupérer les champs critiques."""
    fiche = await _scrape_fiche_light("https://www.privateaser.com/lieu/52456-chez-eloise")
    assert fiche.nom and "Eloise" in fiche.nom
    assert len(fiche.ambiances_cochees) >= 1
    assert fiche.horaire_fin
    assert fiche.capa_max == 80
    assert len(fiche.espaces) >= 2
    assert len(fiche.promotions) >= 1
    assert fiche.edito_principal


@pytest.mark.asyncio
async def test_parser_gabys():
    fiche = await _scrape_fiche_light("https://www.privateaser.es/local/52379-Gabys-club")
    assert "Gaby" in fiche.nom
    assert fiche.capa_max == 65
    assert len(fiche.espaces) >= 2
    assert fiche.edito_principal


@pytest.mark.asyncio
async def test_parser_lina():
    fiche = await _scrape_fiche_light("https://www.privateaser.es/local/55798-lina-restaurante")
    assert "Lina" in fiche.nom
    assert fiche.capa_max == 45
    assert len(fiche.espaces) >= 2
    assert fiche.edito_principal
