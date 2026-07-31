# Détour v4.6 — identité GitHub définitive

## Dépôt canonique

- La branche `main` contient désormais toute la version validée de Détour.
- Le dépôt public est renommé `Alexis-Tissier/detour`.
- L'ancien nom `Alexis-Tissier/routeco` reste redirigé par GitHub.
- Les branches d'audit sont conservées comme historique de sécurité.

## Liens et automatisation

- Les liens README, site, documentation et scripts ciblent le nouveau dépôt.
- Les workflows Tests et GitHub Pages s'exécutent depuis `main`.
- GitHub Pages reste associé à `detour.alexis-tissier.fr`.
- La release `data-france-v1` est conservée avec ses trois assets.

## Périmètre technique

Les noms internes historiques (`routeco.sh`, variables `ROUTECO_*`, module
Python) restent inchangés pour éviter une régression pendant la préparation
desktop. Ils pourront être migrés progressivement après le premier build Linux.
