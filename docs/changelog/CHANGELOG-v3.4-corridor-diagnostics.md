# Routeco 0.3.4 — diagnostic géographique des corridors

## Résultat de la validation précédente

- 10 scénarios et 51 itinéraires conservés ;
- 26 péages exacts, 1 estimé et 24 sans péage ;
- aucun profil GraphHopper perdu ;
- Paris–Rouen est désormais exact à 18,30 € ;
- un seul intervalle reste volontairement estimé, faute de borne physique.

## Diagnostic

- demande des détails GraphHopper `street_name` et `street_ref` ;
- propagation de ces détails jusqu'au moteur de péages ;
- ajout des coordonnées début, milieu et fin aux intervalles non résolus ;
- conservation des noms et références de route avec leurs positions ;
- ajout de liens OpenStreetMap dans le manifeste Markdown.

Ces données orientent la vérification du corridor. Elles ne changent ni le
prix ni le niveau de confiance et ne peuvent donc pas promouvoir une estimation
en tarif exact.

Documentation GraphHopper :
https://docs.graphhopper.com/openapi/routing
