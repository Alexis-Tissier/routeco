# Routeco v3.8 — géocodage national et alternatives utiles

## Géocodage

- Ajout d'un index SQLite indépendant contenant toutes les communes françaises.
- Construction atomique depuis l'API Découpage administratif officielle.
- La BAN locale reste prioritaire pour les adresses détaillées.
- Une commune peut être validée directement au clavier sans cliquer sur une
  suggestion.
- Les communes homonymes produisent un choix explicite avec code postal et
  département.
- `./scripts/routeco.sh start` construit l'index s'il est absent.
- `./scripts/routeco.sh update-communes` permet de l'actualiser.

## Alternatives

- Le trajet réellement le plus rapide reste toujours la référence.
- Les variantes suivantes sont orientées vers le coût total.
- Une variante plus lente doit créer un nouveau palier d'économie au moins égal
  au seuil choisi.
- Les cartes sont ordonnées avec la référence rapide en premier, puis par coût.
- Le compteur distingue les routes calculées, hors critères, regroupées et
  affichées.

## Interface

- Aucun trajet n'est calculé automatiquement au chargement.
- Le message interne concernant l'annulation d'une variante native n'est plus
  présenté à l'utilisateur.
- Autocomplétion utilisable au clavier et erreurs affichées dans le formulaire.
- Carte recentrable et agrandissable, avec tracés cliquables.
- Les liens Google Maps, Waze et Apple Plans suivent le trajet sélectionné.

## Validation

- 160 tests automatiques.
- Vérification réelle disponible via `./scripts/routeco.sh verify-geocoding`.
- Compilation Python.
- Ruff sur tous les fichiers modifiés.
- Vérification syntaxique JavaScript et Bash.
- Référentiel réel : 34 969 communes.
- Cas vérifiés : Versailles, 78000 Versailles, Prunay-le-Temple et Saint-Aubin.
