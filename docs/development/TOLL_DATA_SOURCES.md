# Sources tarifaires de Routeco

## Source de vérité

Routeco calcule les itinéraires avec GraphHopper et conserve localement les
tarifs classe 1 provenant des grilles officielles des concessionnaires et de
l'ASFA.

En France, les sociétés concessionnaires soumettent chaque année à l'État des
grilles détaillées pour chaque trajet et chaque classe de véhicule. Ces grilles
constituent la référence tarifaire.

## Ce que font les grands calculateurs

- Mappy indique utiliser les données routières TomTom et recevoir directement
  les tarifs de péage de l'ASFA.
- Google Routes API peut renvoyer un prix de péage estimé pour un itinéraire,
  mais ne fournit pas une base nationale téléchargeable de matrices
  entrée-sortie. Ce service est payant et peut signaler un prix inconnu.
- Une réponse Google ne doit donc servir que d'oracle externe optionnel de
  comparaison, pas de base locale ni de preuve des événements physiques.

## Architecture Routeco

1. GraphHopper/OSM : géométrie et états `toll` du trajet.
2. Données publiques : localisation des gares et portiques.
3. ASFA/concessionnaires : matrices et tarifs officiels classe 1.
4. `TollPlan` : preuve que chaque événement traversé est expliqué.
5. API externe facultative : comparaison de contrôle, jamais correction
   automatique des données locales.

## États GraphHopper

- `ALL` : péage applicable aux voitures classe 1.
- `HGV` : péage poids lourds uniquement, donc gratuit pour la classe 1.
- `NO` : explicitement non payant.
- `MISSING` ou valeur inconnue : information insuffisante, jamais une preuve de
  gratuité.

Le seuil temporaire `MAX_UNVERIFIED_CLOSED_CONNECTOR_KM` reste utilisé
uniquement lorsque GraphHopper ne fournit aucune preuve positive. Il doit être
supprimé lorsque tous les connecteurs disposent d'un état exploitable.
