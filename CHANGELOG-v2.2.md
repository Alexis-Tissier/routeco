# Routeco 0.2.2

## Péages

- Ajout de **673 emplacements officiels** de gares de péage issus du ministère.
- Ajout des matrices officielles 2026 :
  - Sanef : A1, A2, A16, A26 et A29 ;
  - SAPN : A13, A14 et A29 Nord/Sud.
- Correspondance par alias entre les noms des PDF tarifaires et les noms géographiques :
  `Chamant`, `Fresnes`, `Courcy`, `Setques`, etc.
- Prise en charge du groupe tarifaire en flux libre Paris–Normandie sur l'A13.
- Les micro-segments OSM inférieurs ou égaux à 500 m ne créent plus de faux péages de quelques centimes, sauf lorsqu'un tarif ouvert exact est reconnu.
- Les fichiers officiels complètent OpenTollData sans l'écraser.

## Classement

- Un itinéraire dont le péage est estimé ne reçoit plus le badge **Recommandé** lorsqu'une alternative fiable existe dans la limite de temps.
- Les itinéraires incertains sont signalés par **Péage estimé** ou **À vérifier**.

## Validation

- Le rapport distingue les estimations significatives des reliquats inférieurs à 1 € et 5 km.
- Les scénarios Paris–Lille, Reims–Calais et Paris–Rouen exigent désormais un péage exact.
- 26 tests automatisés.

## Sources intégrées

- Ministère de la Transition écologique : gares de péage du réseau concédé, millésime 2025.
- Sanef : grille classe 1 applicable au 1er février 2026.
- SAPN : grille classe 1 applicable au 1er février 2026.
