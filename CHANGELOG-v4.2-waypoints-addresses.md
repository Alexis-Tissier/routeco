# Routeco v4.2 — étapes et localisations précises

## Arrêt intermédiaire

- Un bouton « Ajouter un arrêt » affiche une étape facultative entre le départ
  et l'arrivée.
- L'API accepte jusqu'à trois étapes ordonnées afin de ne pas figer
  l'architecture à l'unique champ actuellement visible.
- Chaque profil GraphHopper reçoit les points dans leur ordre exact.
- Le fallback segmenté est désactivé pour les trajets avec étape, car une
  récupération approximative ne doit jamais perdre un arrêt imposé.
- La liste des étapes appartient à la clé du cache des tracés.

## Recherche d'adresse

- Dix suggestions au lieu de sept.
- Une saisie contenant un numéro ou un type de voie privilégie les adresses de
  la Base Adresse Nationale.
- Un simple nom de ville conserve le centre de commune comme premier résultat.
- Les suggestions indiquent clairement « Adresse précise » ou
  « Centre de commune ».

## Choix sur la carte

- Départ, arrêt et arrivée peuvent être placés au clic sur la carte existante.
- Les coordonnées exactes sont utilisées par GraphHopper, sans appel à une API
  commerciale de géocodage.
- Le curseur passe en mode précision pendant la sélection.

## Validation

- 186 tests automatiques.
- Contrôle runtime d'un trajet Versailles → Chartres → Fontainebleau.
- Vérification que la géométrie passe à moins de 1,5 km de l'étape demandée.
- Vérification du cache lors d'un changement de prix du carburant.
