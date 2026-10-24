# Fantome Local

Application Windows locale pour organiser des mods `.fantome`, préparer leurs overlays et piloter un moteur LTK fourni séparément.

Une interface sombre avec galerie de cartes, recherche, filtre par champion, aperçu détaillé, sélection d’un mod, commandes Démarrer/Arrêter, journal de session et guide intégré.

## Utilisation

1. Ajouter un ou plusieurs `.fantome`.
2. Rechercher un champion et cliquer sur une carte.
3. Cliquer **Activer ce mod**, puis **Démarrer** avant une nouvelle partie.
4. Attendre la confirmation du chargeur, puis lancer un entraînement avec le champion et le skin de destination du mod.
5. Vérifier le résultat sur la carte. Une redirection d’archive seule n’est pas une confirmation du rendu.

Un seul mod est sélectionné à la fois. Les aperçus intégrés aux paquets sont utilisés en priorité. Lorsqu’un portrait de champion sert de remplacement, cette distinction est affichée dans le panneau de détail. Aucun portrait n’est téléchargé à l’exécution.

## Lancer depuis les sources

Windows et Python 3.13 sont requis. Depuis le dossier du projet :

```powershell
python -m pip install --target vendor -r requirements.txt
python app.py
```

Le lanceur Windows optionnel se compile avec le compilateur .NET Framework déjà fourni sur les systèmes compatibles :

```powershell
& "$env:WINDIR\Microsoft.NET\Framework64\v4.0.30319\csc.exe" /nologo /target:winexe /reference:System.Windows.Forms.dll /out:FantomeLocal.exe Launcher.cs
```

Ce petit lanceur utilise le Python 3.13 installé pour l’utilisateur. Il n’embarque pas Python et n’est donc pas un exécutable autonome.

## Moteur de chargement

Le constructeur WAD est implémenté dans ce projet. La redirection dans le jeu dépend toujours de binaires LTK : **ce n’est pas un moteur de runtime indépendant**.

La configuration actuellement testée attend une paire officielle non modifiée issue de LTK Manager v1.28.1, placée localement dans :

```text
third_party/ltk-v1.28.1/ltk_patcher_host.exe
third_party/ltk-v1.28.1/ltk_patcher_dll.dll
```

Ces binaires ne sont pas inclus dans le dépôt. Leurs conditions de licence sont distinctes du code de cette application. Ne pas mélanger des versions de host et de DLL. Voir [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Le chemin du jeu configuré dans `core.py` est `E:\Riot Games\League of Legends`. Le runtime est limité au build PE effectivement testé, identifié dans `loader.py`. Après une mise à jour du jeu, le chargement est suspendu jusqu’à une nouvelle validation. Le moteur récent testé séparément a refusé un lanceur tiers avec VRF00000008 ; aucune compatibilité universelle n’est annoncée.

## Données locales

- `data/archives/` : copies privées des paquets importés, identifiées par SHA256.
- `data/library.json` : catalogue et mod sélectionné.
- `data/sessions/` : overlays, fingerprints et journaux des tentatives.
- `assets/previews/` : images extraites localement des paquets.
- `assets/champions/` : portraits de remplacement facultatifs, fournis séparément par l’utilisateur.

Tous ces dossiers sont ignorés par Git. Les paquets de mods, ressources Riot, moteurs binaires, journaux de jeu et fichiers personnels ne font pas partie de ce dépôt.

## Vérification et limites

La chaîne originale a été validée en entraînement avec Yasuo Héraut de la nuit sur le skin de base : overlay accepté, WAD redirigé, jeu entré en GAMESTATE_GAMELOOP, rendu confirmé par l’utilisateur. La refonte graphique conserve les modules de chargement et de construction.

Les autres mods restent à valider individuellement. Le constructeur prend en charge les WAD v3.4 empaquetés ; les entrées RAW et certains encodages multi-chunks ne sont pas gérés. Les archives originales du jeu sont lues, leurs empreintes contrôlées et les fichiers générés conservés en dehors de League.

Tests locaux sans League, sans mod personnel et sans injection :

```powershell
python -m unittest discover -s tests -v
```

## Architecture

- `visual_app.py` : interface CustomTkinter et contrôleur de session.
- `ui_assets.py` : lecture des visuels locaux et identification de leur origine.
- `core.py` : import ZIP, catalogue, intégrité et journalisation.
- `wad_builder.py` : construction et validation des overlays.
- `loader.py` : protocole du host, cycle de vie et erreurs du jeu.
- `Launcher.cs` : lanceur Windows facultatif.

Code original sous licence MIT. Aucune affiliation avec Riot Games, League Toolkit ou Celestial.
