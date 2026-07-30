# Routeco v3.9 — diversité réelle des itinéraires

## Génération

- Ajout d'un profil générique `motorway` qui recherche une option largement
  autoroutière sans modifier le temps annoncé par GraphHopper.
- La référence `fastest` reste strictement optimisée sur le temps.
- Les profils économiques `light`, `balanced`, `economy` et `free` restent
  inchangés.
- Une requête native en attente n'est annulée que si les profils personnalisés
  couvrent déjà le temps, l'autoroute et l'économie.

## Sélection

- Jusqu'à cinq choix réellement différents sont affichés.
- Les rôles « plus rapide », « autoroute » et « moins de kilomètres » sont
  conservés même s'ils ne créent pas un nouveau palier d'économie.
- Le seuil d'économie reste appliqué aux alternatives financières.
- Les variantes sans péage séparées de quelques centimes restent regroupées.
- La limite de temps reste respectée, sauf pour la référence rapide elle-même.

## Interface

- Nouveaux badges `Autoroute` et `Moins de km`.
- Le compteur distingue désormais les routes hors limite de temps des routes
  moins pertinentes regroupées.
- L'aide du seuil d'économie explique les rôles qui restent visibles.

## Validation

- Cas de non-régression Grasse → Megève pour vérifier la coexistence du grand
  détour autoroutier et du trajet direct.
- Le contrôle accepte qu'une variante économiquement utile soit très
  légèrement plus courte sans monopoliser le badge « Moins de km » ; ce badge
  reste obligatoire dès que l'écart de distance devient significatif.
- Aucune règle liée à ces villes n'est utilisée dans le moteur de production.
- Aucun changement du profil GraphHopper préparé ni reconstruction du graphe.
