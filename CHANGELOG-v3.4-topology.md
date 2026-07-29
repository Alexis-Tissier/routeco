# Routeco 0.3.4 — topologie des péages ouverts

## Changements

- conservation du type physique d'une gare lorsqu'un tarif ouvert lui est associé ;
- distinction générique entre une barrière principale et une gare de bretelle,
  même lorsque le libellé ne contient pas « entrée » ou « sortie » ;
- une gare d'échangeur seulement longée n'est plus ajoutée au péage principal ;
- adaptation à trois alternatives régionales et quatre alternatives longue distance,
  toujours bornées par le délai supplémentaire de 25 secondes ;
- ajout d'un test de non-régression sur les tarifs ouverts matérialisés.
