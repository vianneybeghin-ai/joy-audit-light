"""Golden tests — chaque URL doit retourner un score dans la fourchette attendue
en moins de 30 s et moins de $0.30, sans aucune mention de bruit externe."""
import time

import pytest

from src.pipeline import run_audit_light


GOLDEN_CASES = [
    ("https://www.privateaser.com/lieu/52456-chez-eloise", {"score_range": (55, 75)}),
    ("https://www.privateaser.es/local/52379-Gabys-club", {"score_range": (65, 85)}),
    ("https://www.privateaser.es/local/55798-lina-restaurante", {"score_range": (60, 80)}),
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
