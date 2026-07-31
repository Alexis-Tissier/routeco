# Routeco 0.3.4 — suivi de validation

## Changements

- La recherche native d'alternatives est limitée à 3 chemins et 25 secondes.
- La limite GraphHopper de 8 000 000 de nœuds reste un plafond de sécurité.
- Les tarifs de bretelles en péage ouvert ne sont plus ajoutés lorsque la route
  continue sur la chaussée principale.
- Le coût total est la somme exacte des montants de carburant et de péage
  affichés au centime.
- La référence gold Paris–Rouen correspond désormais au chemin A14 réellement
  choisi par le profil le plus rapide.
- Trois tests de non-régression ont été ajoutés.
