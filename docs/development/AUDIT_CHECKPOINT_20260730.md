# Routeco — point de contrôle pour audit complet

Généré le `2026-07-30T08:10:18.881659+00:00`.

## Statut du code

- Tests unitaires réussis : **oui**
- Branche d'audit : définie par le script de push
- Version : état de développement 0.3.4, non déclarée stable
- Règle : aucune correction de production spécifique à une ville ou à un trajet

## Dernière validation gold stricte

- Scénarios : **10**
- Itinéraires : **51**
- Péages exacts : **21**
- Péages estimés : **6**
- Sans péage : **24**
- Erreurs : **8**
- Profils perdus : **0**

## Scénarios restant à expliquer

- Paris → Lyon (APRR): 2 erreur(s)
- Paris → Lille (Sanef): 1 erreur(s)
- Clermont-Ferrand → Montpellier: 2 erreur(s)
- Paris → Rouen (A13/A14 SAPN flux libre): 3 erreur(s)

## Ce qui s'est réellement amélioré

Par rapport au rapport strict précédent :

- les péages exacts sont passés de 18 à 21 ;
- les estimations sont passées de 9 à 6 ;
- les erreurs sont passées de 11 à 8 ;
- Paris → Bordeaux est entièrement exact ;
- Nantes → Paris est entièrement exact ;
- Bordeaux → Toulouse est entièrement exact ;
- les micro-fragments OSM sans événement de paiement ne créent plus de faux tarif.

## Risques nécessitant une revue complète

1. `app/services/tolls.py` a accumulé plusieurs heuristiques de sélection,
   normalisation, padding et fallback.
2. Des correctifs successifs ont parfois déplacé les erreurs au lieu de supprimer
   leur cause.
3. Le statut `exact` dépend encore de plusieurs chemins de sortie différents.
4. Le fallback `route_wide`, les chaînes de matrices, les péages ouverts et les
   fragments OSM doivent être modélisés comme un seul problème de facturation.
5. Les tests contiennent de bons cas de non-régression, mais l'architecture doit
   être simplifiée avant toute nouvelle règle.
6. Paris → Rouen reste le principal signal de conflit entre système fermé,
   flux libre et couverture OSM.
7. Clermont-Ferrand → Montpellier semble relever d'une donnée tarifaire absente,
   et non d'un simple défaut de sélection.
8. Les alternatives Paris → Lyon et Paris → Lille révèlent encore des corridors
   partiellement appariés.
9. Avant toute nouvelle modification, comparer chaque chemin produisant
   `TollQuote(confidence="exact")` et définir une preuve unique de complétude.

## Dernière sortie pytest

```text
........................................................................ [ 87%]
..........                                                               [100%]
=============================== warnings summary ===============================
.venv/lib64/python3.14/site-packages/fastapi/testclient.py:1
  /home/alexistissier/Téléchargements/routeco/.venv/lib64/python3.14/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
82 passed, 1 warning in 23.09s
```

## Fichiers de référence

- `docs/validation/validation-20260730-095020.json`
- `docs/validation/validation-20260730-095020.md`
- `docs/development/CODE_SNAPSHOT_SHA256_20260730.txt`
