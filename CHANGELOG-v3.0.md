# Routeco 0.3.0 — moteur générique de péage

Cette version abandonne les corrections fondées sur des couples de villes.

- les matrices fermées entrée→sortie sont résolues avant les péages ouverts sur les longues sections ;
- un péage ouvert doit être une station explicitement typée `open` et réellement traversée à moins de 200 m du tracé ;
- les stations et tarifs ouverts provenant de sources séparées sont rapprochés automatiquement par alias non ambigu ;
- aucune ville, origine, destination ou trajet de validation n'est utilisé dans le moteur de production ;
- `validate` effectue des contrôles structurels ;
- `validate-gold` exécute séparément les montants de référence ;
- `validate-random N` teste N couples de villes tirés de façon déterministe.

Les données peuvent rester incomplètes. Dans ce cas Routeco doit afficher `estimated`, jamais fabriquer un tarif `exact`.
