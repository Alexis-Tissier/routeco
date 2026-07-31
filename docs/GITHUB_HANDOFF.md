# Publier le projet sur GitHub

Le dépôt doit rester privé au départ, car le projet est encore en développement.

## Méthode automatique

Depuis le dossier Routeco :

```bash
./scripts/publish_github.sh
```

Le script :

- initialise Git ;
- crée le premier commit ;
- crée `Alexis-Tissier/detour` en privé si GitHub CLI est installé et connecté ;
- pousse la branche `main`.

Changer le nom ou la visibilité :

```bash
REPO_NAME=detour REPO_VISIBILITY=private ./scripts/publish_github.sh
```

## Méthode manuelle

Créer un dépôt vide sur GitHub, puis :

```bash
git init -b main
git add .
git commit -m "Initial Routeco 0.3.3 import"
git remote add origin git@github.com:Alexis-Tissier/detour.git
git push -u origin main
```

## Reprendre dans une nouvelle conversation

Dans la nouvelle conversation, donner le dépôt GitHub et demander :

```text
Analyse entièrement le dépôt Alexis-Tissier/detour. Lis d'abord
CHATGPT_CONTEXT.md, README.md, docs/changelog/CHANGELOG-v3.3.md et le dernier rapport dans
docs/validation/. Reprends le développement à partir de cet état sans ajouter
de règles spécifiques à des villes.
```
