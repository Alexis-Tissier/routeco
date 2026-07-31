# Routeco 0.2.1

- Ajout d'une configuration par variables d'environnement pour déplacer BAN, péages et rapports hors de la partition Linux.
- Ajout de `scripts/routeco.sh` pour démarrer, arrêter, redémarrer, diagnostiquer et suivre les logs sans retrouver les terminaux.
- Ajout de dix scénarios de validation France et d'un générateur de rapports Markdown/JSON.
- Ajout du mode strict pour repérer toute estimation de péage restante.
- Ajout du détail structuré des sections de péage dans l'API et l'interface.
- Vérification automatique que la somme des sections correspond au péage total.
- Isolation du rendu cartographique dans `static/map-adapter.js`, prête pour MapLibre/PMTiles.
- Mise à jour de la documentation et de la version du projet.
- 20 tests unitaires validés.
