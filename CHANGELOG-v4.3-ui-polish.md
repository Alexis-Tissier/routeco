# Routeco v4.3 — UI polish du panneau gauche

## Hiérarchie visuelle

- Le champ arrêt reste disponible, mais son ouverture se fait désormais via un
  petit bouton `+` placé au-dessus du bouton d'inversion départ / arrivée.
- Les gros boutons textuels « Choisir sur la carte » sont remplacés par une
  petite icône discrète à droite de chaque champ.
- Les réglages véhicule / carburant sont rangés dans un bloc repliable,
  refermé par défaut.

## Détails de l'expérience

- Les champs départ / arrêt / arrivée partagent la même grammaire visuelle.
- L'ajout d'un arrêt n'occupe plus une ligne entière quand il n'est pas utilisé.
- Le résumé du bloc repliable affiche une synthèse compacte du véhicule, des
  consommations et du prix actuel du carburant.

## Validation

- 188 tests automatiques.
- Vérification JavaScript et `git diff --check`.
- Vérification de la compatibilité des validations runtime existantes.
