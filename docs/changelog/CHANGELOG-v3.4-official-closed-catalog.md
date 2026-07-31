# Routeco 0.3.4 — matrices fermées officielles datées

## Catalogue

- ajout d'un schéma daté pour les matrices fermées classe 1 ;
- conservation de la provenance, de la période d'effet, de la distance
  éventuelle et de la saisonnalité ;
- génération déterministe du catalogue Sanef/SAPN 2026 et ajout de la cellule
  APRR Fleury-en-Bière–Ury vérifiée dans la grille 2026 ;
- priorité aux cellules officielles applicables sur les anciennes cellules sans
  provenance.

## Alias

- registre séparé des alias physiques vers les libellés tarifaires ;
- validation par nom, opérateur, coordonnées et rayon maximal ;
- refus implicite des homonymes situés dans une autre région.

## Sélection

- une distance officielle cohérente peut départager des interprétations déjà
  valides ;
- une distance incohérente ne rejette plus, à elle seule, une matrice dont la
  continuité topologique est prouvée ;
- une matrice longue reste exclusive d'une matrice partielle chevauchante
  représentant le même voyage fermé ;
- une cellule officielle maximale qui partage la même entrée ou la même sortie
  physique remplace désormais la cellule partielle avant le classement par
  couverture, sans règle liée à un trajet particulier ;
- la référence Gold est alignée sur les tarifs officiels applicables à la date
  de validation.
