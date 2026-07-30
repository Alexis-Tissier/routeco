# Routeco 0.3.4 — plan tarifaire global

## Les neuf changements

1. Séparation explicite entre péage réel et bruit OSM.
2. Génération simultanée des paires de frontière, matrices longues et chaînes.
3. Prise en compte des matrices route-wide même avec plusieurs plages OSM.
4. Déduplication des interprétations tarifaires équivalentes.
5. Sélection globale par couverture exacte maximale.
6. Interdiction des chevauchements et de la réutilisation d'une gare physique.
7. Ignorance des micro-fragments uniquement sans événement de facturation.
8. Conservation en estimation des barrières réellement traversées sans tarif.
9. Mode strict : seules les estimations réelles sont des erreurs ; une route
   vérifiée sans péage reste valide.

Aucune règle ne dépend d'une ville, d'une origine, d'une destination ou d'un
trajet particulier.

## Sémantique de facturation

- Une sous-matrice incluse ne peut plus déclarer toute une plage résolue lorsqu'une matrice exacte plus large existe.
- La matrice exacte maximale peut absorber jusqu'à 25 km de balisage OSM avant et après ses gares, sauf présence d'une barrière principale sans tarif.
- Les événements ouverts distincts sont encore inspectés après la résolution d'une plage fermée.
- Les résidus inférieurs à 1 € et à 6 km sont silencieux uniquement lorsqu'aucun événement physique non tarifé n'est traversé.

## Contrôle des événements physiques sur les matrices complètes

- Toute matrice déjà marquée complète est désormais réexaminée.
- Une barrière principale non tarifée située hors de la matrice empêche l'absorption silencieuse du résidu OSM.
- Les événements situés entre l'entrée et la sortie de la matrice restent couverts par celle-ci.

<!-- ROUTECO_V034_FULL_RANGE_EVENT_GUARD_FIX -->

## Protection du dernier recours route-wide

- Retrait du garde-fou qui confondait les extrémités de chaînes exactes avec des événements non tarifés.
- Une matrice globale ne peut plus effacer un événement physique détecté sans tarif officiel.

<!-- ROUTECO_V034_ROUTEWIDE_EVENT_GUARD_FIX -->
