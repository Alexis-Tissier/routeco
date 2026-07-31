# Détour Desktop

Détour Desktop fournit une vraie fenêtre autonome avec :

- Electron et Chromium pour l'interface ;
- le backend Python empaqueté par PyInstaller ;
- GraphHopper 11 ;
- un runtime Java inclus ;
- le téléchargement vérifié du pack France au premier lancement.

## Construire sous Linux

```bash
bash scripts/build_desktop_linux.sh
```

Les fichiers sont créés dans `dist/desktop/`.


## Installation locale Linux

Après le build :

```bash
bash scripts/install_desktop_linux.sh
```

Détour apparaît alors dans le menu des applications.
