# Joy Audit Light

Audit rapide d'une fiche Privateaser : score /100, 3 priorités, diagnostic flash.
Cible : ~$0.20 / audit, ~25 s end-to-end.

## Stack

FastAPI + Playwright + Sonnet vision + Google Places API + R2 storage.

Pipeline 4 steps :
1. `fiche_links` (Playwright) + Google Places API → liens externes + GBP rating/reviews
2. `privateaser_scraper` (httpx + regex) → photos + vidéo
3. Sonnet vision batch sur 5 photos → tags (IA, festif, dansant, groupe, plan)
4. Scoring déterministe pur Python + Sonnet pour 3 actions P0

## Run local

```bash
cp .env.example .env  # remplir les clés
pip install -r requirements.txt
playwright install chromium
uvicorn main:app --reload --port 8080
curl -X POST http://localhost:8080/audit-light \
  -H 'Content-Type: application/json' \
  -d '{"url": "https://www.privateaser.com/lieu/52456-chez-eloise"}'
```

Sans vars `R2_*` configurées, le HTML est écrit en local dans `./output/audits/`.

## Déploiement Railway

1. Créer un nouveau projet Railway, source = ce repo GitHub.
2. Railway détecte le `Dockerfile` et build automatiquement.
3. Renseigner les variables d'env (Settings → Variables) :
   `ANTHROPIC_API_KEY`, `GOOGLE_PLACES_API_KEY`, `R2_*`, `FULL_AUDIT_BASE_URL`.
4. Le service est accessible sur `https://<service>.up.railway.app`.
5. Chaque push sur `main` redéploie automatiquement.

## Endpoint

```
POST /audit-light
body : {"url": "https://www.privateaser.com/lieu/..."}
```

Retourne `{score, grade, html_url, duration_seconds, cost_estimate_usd, actions, blocks}`.

## Tests

```bash
pytest tests/
```

Les tests golden vérifient pour 3 fiches : score dans la fourchette, exactement
3 actions, < 30 s, < $0.30, aucun bruit externe dans les actions.

## Relation avec `joy-audit-pipeline`

Ce service est **autonome** : pas d'import croisé. `fiche_links.py`,
`privateaser_scraper.py` et `storage.py` sont **dupliqués** du repo principal au
commit de scaffold. Si une évolution est faite côté principal (ex : nouveau
filtre CDN dans fiche_links), la copier manuellement ici.
