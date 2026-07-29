# Routeco 0.2.3

## Corrections

- calcul exact du flux libre A13 en additionnant les portiques officiels traversés ;
- ajout des tarifs 2026 de Buchelay, Heudebouville, Beuzeville et Dozulé ;
- suppression d'un faux appariement possible entre un micro-segment OSM et une longue paire de gares fermées ;
- contrôle de cohérence entre kilomètres payants OSM et distance tarifaire ;
- fusion prudente de plages OSM voisines lorsqu'elles décrivent un seul corridor tarifaire ;
- déduplication géographique des portiques ouverts présents dans plusieurs sources.

## Validation

- 29 tests automatiques ;
- régression dédiée au faux tarif `St-Denis-Les-Sens → Tournus` sur 100 m payants ;
- régression dédiée à Paris → Rouen : `Buchelay 3,00 € + Heudebouville 4,50 €`.
