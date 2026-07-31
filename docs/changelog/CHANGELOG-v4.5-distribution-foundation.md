# Détour v4.5 — fondations de distribution

## Carte

- Les contrôles Leaflet `+ / −` sont déplacés en bas à gauche.
- Le cartouche du trajet reste entièrement lisible en haut à gauche.

## Données France

- Générateur ZIP64 pour le graphe GraphHopper, la BAN et les communes.
- Fractionnement configurable, limité par défaut à 1 900 Mio par fichier.
- Manifest JSON versionné avec taille et SHA-256 de chaque partie.
- Installateur local avec reprise de téléchargement, contrôle d'intégrité,
  extraction sûre et activation atomique du pack.

## GitHub Releases

- Script de publication des parties et du manifest avec GitHub CLI.
- Tag indépendant `data-france-v<version>`.
- Les données lourdes ne sont jamais ajoutées au dépôt Git.

## Page de téléchargement

- Page statique responsive dans `site/`.
- Logo Détour provisoire cohérent avec l'interface.
- Capture officielle de l'application.
- Domaine personnalisé préparé : `detour.alexis-tissier.fr`.
- Workflow GitHub Pages.

## Validation

- 191 tests automatiques.
- Vérification Python, JavaScript, Bash et `git diff --check`.
