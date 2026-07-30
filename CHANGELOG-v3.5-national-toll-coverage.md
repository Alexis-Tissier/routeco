# Routeco v0.3.5 — couverture nationale des péages

Cette migration transforme les phénomènes répétés de l'audit aléatoire de
50 trajets en règles génériques et en données tarifaires datées.

## Données ajoutées

- 21 505 cellules classe 1 APRR 2026 ;
- 815 cellules classe 1 AREA 2026 ;
- matrice classe 1 ESCOTA A51 2026 ;
- matrice classe 1 ALIAÉ A79 2026 et six portiques physiques ;
- tarifs ouverts ESCOTA des barrières de Bandol et La Ciotat ;
- tarifs 2026 des ponts de Normandie et de Tancarville.

Le catalogue fermé généré contient 24 238 cellules datées. Chaque nouvelle
cellule conserve sa période d'application et son identifiant de source.

## Règles moteur

- un péage ouvert explicitement additif reste facturable à la borne d'un
  système fermé adjacent ;
- les lignes directionnelles d'une même barrière ne créent plus de faux
  événement sans tarif ;
- un débordement OSM contigu peut être absorbé jusqu'à 5 km par une cellule
  officielle datée, sans autre événement physique ;
- les anciennes matrices non sourcées conservent le budget historique de
  500 m ;
- le flux libre A79 est prouvé par ses portiques et sa matrice, pas par un nom
  d'autoroute.

## Limites conservées

Les tarifs A88 disponibles au moment de la migration portent sur 2025. Ils ne
sont pas promus en tarifs 2026. Les corridors sans cellule officielle
applicable restent estimés et continuent d'apparaître dans le manifeste.
