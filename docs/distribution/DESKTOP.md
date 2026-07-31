# Distribution desktop de Détour

## Architecture retenue

L'application desktop sera un petit installateur multiplateforme. Au premier
lancement, elle téléchargera le pack France publié sur GitHub Releases, vérifiera
chaque partie par SHA-256 et installera les données dans le dossier utilisateur.

Les données sont ensuite locales :

- graphe GraphHopper prêt à l'emploi ;
- Base Adresse Nationale ;
- index des communes ;
- matrices de péage déjà incluses avec l'application.

Le fichier OSM `.pbf` brut n'est pas distribué aux utilisateurs finaux.

## Emplacements prévus

```text
Windows : %LOCALAPPDATA%\Detour
Linux   : ~/.local/share/detour
macOS   : ~/Library/Application Support/Detour
```

Chaque version de données est installée sous :

```text
packs/france-v<version>/
```

Le fichier `current-france.json` indique le pack actif.

## Construire le pack France

Depuis la machine qui possède le graphe, la BAN et les communes :

```bash
./.venv/bin/python scripts/build_data_release.py \
  --version 1 \
  --output dist/data-release
```

Le script lit `.env` pour retrouver `ROUTECO_BAN_DB` et
`ROUTECO_COMMUNES_DB`. La taille maximale d'une partie est de 1 900 Mio par
défaut :

```bash
./.venv/bin/python scripts/build_data_release.py \
  --version 1 \
  --chunk-mib 1900
```

## Publier sur GitHub Releases

```bash
bash scripts/publish_data_release.sh \
  dist/data-release/data-france-v1
```

Cela crée ou met à jour le tag `data-france-v1` et envoie :

- le manifest JSON ;
- toutes les parties du ZIP ;
- `SHA256SUMS`.

## Tester l'installation

```bash
./.venv/bin/python scripts/install_release_data.py \
  dist/data-release/data-france-v1/detour-data-france-v1.json \
  --data-root /tmp/detour-test
```

## Application desktop

L'étape suivante est la création du shell desktop Tauri :

1. fenêtre native Détour ;
2. moteur Python empaqueté ;
3. Java Runtime et GraphHopper embarqués ;
4. écran de premier lancement utilisant `install_release_data.py` ;
5. builds GitHub Actions pour Windows, Linux et macOS ;
6. publication dans une GitHub Release d'application.

## GitHub Pages

Le site statique se trouve dans `site/`. Le workflow
`.github/workflows/pages.yml` le publie automatiquement.

Domaine prévu :

```text
detour.alexis-tissier.fr
```

DNS à créer chez le registrar :

```text
Type  : CNAME
Nom   : detour
Cible : alexis-tissier.github.io
```

Dans les paramètres GitHub Pages, la source doit être **GitHub Actions**.

## Domaine GitHub Pages

Le fichier `site/CNAME` indique à GitHub Pages que le site public utilise
`detour.alexis-tissier.fr`. Il ne crée aucun enregistrement DNS.

Dans IONOS, il faut créer un enregistrement CNAME :

- hôte : `detour`
- cible : `alexis-tissier.github.io`

Le domaine personnalisé doit ensuite être confirmé dans les paramètres
GitHub Pages du dépôt.

## Première publication des données France

La publication de données utilise désormais un orchestrateur unique :

```bash
./.venv/bin/python scripts/prepare_data_release.py \
  --version 1 \
  --output /chemin/avec/assez/d-espace \
  --publish
```

Avant l'envoi, le script vérifie chaque partie, reconstitue l'archive complète,
contrôle son SHA-256 et teste toutes les entrées ZIP. Après l'envoi, il retélécharge
le manifest depuis GitHub Releases et compare son empreinte au fichier local.

Les releases `data-france-v*` sont explicitement créées avec `--latest=false` :
elles ne remplacent donc jamais la dernière release de l'application Détour.
