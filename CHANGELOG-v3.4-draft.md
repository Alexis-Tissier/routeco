# Routeco 0.3.4 — brouillon de fiabilisation

Ce correctif reste générique : aucune origine, destination ou ville n'est utilisée dans le moteur.

## Routage

- les alternatives natives peuvent servir de géométrie de référence lorsque le profil rapide personnalisé échoue ;
- la récupération longue distance adapte le nombre de points intermédiaires à la longueur du trajet et essaie aussi un modèle assoupli ;
- les plages `toll=HGV` ne sont plus comptées pour un véhicule léger de classe 1 ;
- les plages payantes et les doublons sont comparés avec des distances métriques, y compris les kilomètres réellement marqués payants.

## Péages

- une chaîne de matrices ne déclare plus une plage intégralement couverte avec un résidu pouvant atteindre 12 % ;
- les paires fermées ne couvrent que la distance réellement justifiée par la géométrie ou par la matrice tarifaire ;
- une matrice dont la distance est manifestement incompatible est rejetée dès le premier passage ;
- un portique ouvert isolé ne suffit plus à expliquer une très longue plage payante inconnue ;
- la projection géographique utilise une marge de longitude adaptée à la latitude ;
- les plages OSM ne sont plus fusionnées à cause de la seule proximité de leurs indices dans une géométrie peu dense.

## Validation requise

```bash
./.venv/bin/python -m pytest -q
./scripts/routeco.sh restart
./scripts/routeco.sh validate-random 50
./scripts/routeco.sh validate-gold
```

Ne publier la version 0.3.4 qu'après comparaison du nouveau rapport avec `docs/validation/validation-20260729-184656.json`.
