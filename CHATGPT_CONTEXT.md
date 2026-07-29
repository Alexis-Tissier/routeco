# Contexte de reprise — Détour / Routeco

Ce fichier est destiné à une nouvelle conversation ChatGPT. Lire également `README.md`, `CHANGELOG-v3.3.md` et le dernier rapport dans `docs/validation/` avant de modifier le code.

## Objectif produit

Construire une application française gratuite et auto-hébergeable qui propose plusieurs trajets et les classe selon le coût réel :

```text
coût carburant + coût des péages
```

L'utilisateur choisit le temps supplémentaire maximal acceptable : 20 min, 45 min, 1 h, 1 h 30 ou tout voir.

Le profil de départ est une Twingo 2 essence :

- autoroute : 6,5 L/100 km ;
- autres routes : 5,5 L/100 km ;
- carburant SP95-E10 ou SP98 ;
- classe de péage 1.

## Version de code

- Version préparée : **0.3.3**.
- Tests unitaires annoncés : **49**.
- Le dernier rapport réel joint a été produit avec la version précédente **0.3.2** avant validation de la 0.3.3.
- Ne pas considérer la 0.3.3 comme validée sur le graphe France tant que `validate-random 50` n'a pas été relancé après installation.

## Dernière validation réelle disponible

Fichiers :

- `docs/validation/validation-20260729-184656.md`
- `docs/validation/validation-20260729-184656.json`

Résumé :

- 50 scénarios ;
- 231 itinéraires ;
- 54 tarifs de péage exacts ;
- 63 estimations significatives ;
- 24 estimations mineures ;
- 90 itinéraires sans péage ;
- 0 erreur technique ;
- 32 scénarios avec avertissement ;
- 10 profils GraphHopper relancés ;
- 10 profils finalement perdus.

## Architecture actuelle

- Frontend statique : `static/`.
- API FastAPI : `app/main.py`.
- Routage : `app/services/routing.py`.
- Calcul carburant : `app/services/costs.py`.
- Péages : `app/services/tolls.py`.
- Sélection des alternatives : `app/services/pareto.py`.
- Validation : `app/services/validation.py` et `scripts/validate_routes.py`.
- GraphHopper : `infra/graphhopper/config.yml`.
- BAN SQLite configurable avec `.env`.

## Ce qui fonctionne correctement

- Paris → Lyon avec un trajet direct et un trajet mixte à deux sections payantes ;
- plusieurs réseaux APRR, ASF, SANEF et SAPN dans de nombreux cas ;
- calcul carburant autoroute / route ;
- routes sans péage ;
- alternatives GraphHopper classiques et natives ;
- détection des micro-segments OSM parasites ;
- contrôles de doublons, ordre et chevauchement des sections de péage ;
- distinction `exact`, `estimated` et `none`.

## Problèmes encore ouverts

### 1. Couverture des péages

Les principales estimations significatives concernent encore :

- Cofiroute, notamment Paris ↔ Nantes et certains axes vers Bordeaux ;
- des liaisons entre réseaux où une portion payante n'est pas expliquée ;
- des péages ouverts ou directionnels dont les alias géographiques sont ambigus ;
- AREA et certaines portions du Sud-Est.

Le statut `exact` ne doit être utilisé que lorsque toutes les portions payantes significatives sont expliquées par des sections ordonnées et non chevauchantes.

### 2. Longues distances GraphHopper

Avec la configuration 0.3.2, certains profils `light`, `balanced`, `economy` et `free` échouaient sur les très longues traversées avec :

```text
No path found due to maximum nodes exceeded 3000000
```

La 0.3.3 relève le plafond et ajoute une récupération par points intermédiaires. Cela doit être testé réellement.

### 3. Carte

Le fond est encore schématique. `static/map-adapter.js` a été isolé pour ajouter plus tard MapLibre et des tuiles locales ou PMTiles.

### 4. Déploiement

Le développement est local. Le projet devra ensuite être transféré sur un VPS, sans y committer les données lourdes.

## Priorités recommandées

1. Installer la 0.3.3 et exécuter :

```bash
./scripts/routeco.sh status
./scripts/routeco.sh validate-random 50
./scripts/routeco.sh validate-gold
```

2. Comparer les métriques à la validation 0.3.2.
3. Vérifier en priorité les itinéraires avec une estimation significative sur la route la plus rapide ou recommandée.
4. Corriger les péages de manière générale, sans condition liée aux villes.
5. Garantir au moins plusieurs alternatives sur les longues distances.
6. Ajouter la vraie carte uniquement lorsque le classement économique est suffisamment fiable.
7. Préparer ensuite le déploiement VPS.

## Contraintes de conception

- 100 % gratuit autant que possible ;
- aucune API commerciale obligatoire ;
- données France locales ;
- ne jamais coder un tarif uniquement pour faire réussir un scénario précis ;
- préférer une estimation clairement affichée à un faux tarif exact ;
- ne pas committer la BAN, le graphe GraphHopper, le PBF France, les JAR ou les logs ;
- conserver les petits CSV normalisés de péages dans Git.

## Commandes principales

```bash
./scripts/routeco.sh start
./scripts/routeco.sh status
./scripts/routeco.sh logs
./scripts/routeco.sh validate-random 50
./.venv/bin/python -m pytest -q
```
