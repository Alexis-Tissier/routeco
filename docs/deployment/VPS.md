# Déployer Routeco sur un VPS personnel

## Cible minimale

La cible prévue pour le graphe France est :

- 2 OCPU ;
- 12 Gio de RAM ;
- 100 Gio de disque ;
- 8 à 12 Gio de swap de sécurité ;
- un seul calcul Routeco lourd à la fois.

Un serveur de 4 Gio déjà occupé par d'autres applications n'est pas une cible
fiable pour GraphHopper France.

## Répartition conseillée

- GraphHopper : heap Java de 6 Gio en fonctionnement normal ;
- import du graphe : 8 à 10 Gio, de préférence lorsque les autres applications
  lourdes sont arrêtées ;
- API Routeco : un processus Uvicorn ;
- cache de huit couples départ–arrivée pendant 30 minutes ;
- GraphHopper et l'API écoutent uniquement sur `127.0.0.1`.

Exemple `/etc/routeco/routeco.env` :

```env
GRAPHHOPPER_URL=http://127.0.0.1:8989
GRAPHHOPPER_RAM=6g
GRAPHHOPPER_IMPORT_RAM=10g
JAVA_TOOL_OPTIONS=-Xms1g -Xmx6g
ROUTECO_MAX_CONCURRENT_CALCULATIONS=1
ROUTECO_ROUTING_CACHE_TTL=1800
ROUTECO_ROUTING_CACHE_ENTRIES=8
ROUTECO_TOLL_ESTIMATE_EUR_PER_KM=0.105
```

Le cache ne contient que les géométries et les détails routiers. Le carburant,
les péages, le temps maximal et le classement sont recalculés à chaque réponse.

## Vérifications avant démarrage

```bash
./scripts/routeco.sh doctor
./scripts/routeco.sh status
```

Un démarrage normal refuse désormais de reconstruire silencieusement un graphe
absent. L'import lourd doit être demandé explicitement :

```bash
./scripts/routeco.sh rebuild-graph
```

## Services

Les exemples dans `infra/systemd/` séparent GraphHopper et l'API. Cela permet à
systemd de redémarrer un composant sans interrompre inutilement l'autre.

Le proxy HTTPS doit uniquement exposer `127.0.0.1:8000`. Les ports 8989 et 8990
restent privés. Pour un usage personnel, conserver l'authentification existante
devant le sous-domaine Routeco et limiter les journaux par rotation.

## Mise à jour

1. valider la nouvelle version et reconstruire le graphe sur le PC local si le
   profil GraphHopper change ;
2. sauvegarder `data/graph-cache` ou conserver l'ancien cache jusqu'au contrôle ;
3. déployer le code et les petites matrices tarifaires ;
4. ne remplacer le graphe du VPS qu'après une validation locale complète ;
5. exécuter `validate-gold`, puis un échantillon aléatoire avant réouverture.
