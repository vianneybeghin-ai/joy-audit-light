"""KB frozen — 500 mots max, distillé des guardrails du repo principal.
Bump KB_VERSION manuellement quand un changement structurel est appliqué."""

COMPACT_KB = """
# Audit Joy Light — règles condensées (frozen v1)

## Barème /100
Médias 50 (Photos 40 + Vidéo 10) | Conditions & Promo 12 | Preuve sociale 8 |
Édito & Labels 10 | Bases 20.

## Photos — échantillonnage 5 photos
- Détection IA : peau lissée, doigts aberrants, diversité calibrée, poses
  synchronisées, ombres incohérentes. Ratio IA > 20 % → cap 14/40 + P0
  "Supprimer photos IA".
- ADN festif = concert/DJ/live/dansant dans atout/édito OU ≥3 signaux festifs
  (Festive cochée, danse, ferme tard, occasions festives, édito festif).
- ADN festif + photos pas festives (festive_ratio < 30 %) → cap 7/40.
- ADN festif + festif présent mais pas dansant (projection_festif_dansant
  < 15 %) → cap 22/40.
- Éclairage festif : DOMINANTE basse/tamisée/chaude tranche. Un seul néon
  coloré dans une salle blanche diffuse = FALSE.

## Conditions & Promo
- Sur devis capa ≤ 25 = friction (P1 "transformer en min conso").
- Sur devis privatisation ≥ 30 = acceptable mais P2 ("min conso indicatif").
- HH "large" = ≥ 4 h cumulées OU fin après minuit OU couvre vendredi-dimanche.
- HH étroit sans promo groupe = 1/4 + P1 "Étendre HH ou créer promo groupe".
- Aucune promo = 0/4 + P0 "Créer offre HH ou groupe".

## Preuve sociale
- Avis Privateaser : 0=0, 1-4=1, 5-10=2, 11-20=3, 21+=4 / 4 pts.
- Avis Google : barème équivalent. Si note < 4.0 : −1 pt.

## Édito & Labels
- Édito ≥ 3 blocs avec claim clair = 4/4.
- Concept labels Axe 1+2+3 cohérents = 6/6.

## Bases
Capa & gamme 4, horaires 2, équipements 2, apports 2, parfait pour 3,
sélections 1, carte 3, lien PDF 1, ambiances 2.

## Actions
Exactement 3 actions P0, concrètes, jamais en jargon (pas de Gxx, pas de
"cap"). Format : Titre 5-8 mots + description 1-2 phrases.

## Bruit externe — ne JAMAIS générer
Mentions immobilières (LoopNet, à louer), légales (mise en demeure,
liquidation, huissier), reprises (post-reprise, depuis la reprise,
changement de propriétaire, rachat), carte non actualisée. Seul signal
fiable de fermeture = Google permanently_closed.
"""

KB_VERSION = "v1.0.0"
