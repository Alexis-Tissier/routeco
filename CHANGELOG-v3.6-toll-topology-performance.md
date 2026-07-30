# Routeco v3.6 — topologie tarifaire et latence

## Résultat visé

Cette passe corrige les phénomènes génériques répétés dans les deux audits
nationaux de 50 trajets, sans ajouter de règle liée à une ville, une autoroute
ou un opérateur.

## Péages

- Une barrière principale présente à la fois dans l'inventaire officiel et
  dans le catalogue concessionnaire n'est plus interprétée comme deux
  événements lorsque ses deux projections sont distantes de moins de 500 m
  et partagent un nom de lieu significatif. Un second portique distinct reste
  explicitement non résolu.
- Une plage OSM courte peut être absorbée lorsqu'elle est adjacente à un
  événement ouvert ou fermé déjà facturé et qu'aucun autre événement physique
  n'y subsiste.
- Un événement tarifé connu mais non sélectionné bloque explicitement cette
  absorption.
- Une matrice officielle résiduelle peut se terminer sur une barrière
  principale interne lorsque son autre borne touche le composant, qu'elle en
  couvre au moins 35 %, que le reliquat est inférieur à 25 km et qu'aucun
  événement inexpliqué ne subsiste.
- Cette tolérance est refusée aux matrices historiques non sourcées.
- Le point physique de la barrière d'Haudricourt et les deux gares d'Aumale
  sont reliés à la cellule tarifaire SANEF « Aumale n°12 » par des alias
  géographiques datés et sourcés. La matrice Poix-de-Picardie–Aumale peut
  ainsi être sélectionnée sans règle liée au trajet Lille–Rouen.

## Routage

- Les cinq profils Routeco restent exécutés.
- La requête native supplémentaire est annulée lorsqu'au moins quatre tracés
  distincts sont déjà disponibles et qu'elle est encore en cours.
- Elle reste utilisée si les profils sont insuffisants, échouent ou produisent
  trop de doublons.
- Les appels au GraphHopper local ignorent les proxies système.

## Mesure

Les rapports JSON et Markdown exposent désormais :

- le temps de routage cumulé, moyen et maximal ;
- le temps consacré au calcul des péages ;
- le nombre de requêtes natives annulées parce qu'elles étaient redondantes.

La sortie terminal affiche également les durées pour chaque scénario.

## Vérification

- 146 tests réussis ;
- compilation Python réussie ;
- contrôle `git diff --check` réussi ;
- tests négatifs dédiés aux portiques non sélectionnés et aux matrices non
  sourcées.
