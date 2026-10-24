# Composants et références

## Bibliothèques Python

- CustomTkinter 6.0.0 : MIT — https://github.com/TomSchimansky/CustomTkinter
- Pillow 12.1.0 : licence HPND/Pillow — https://github.com/python-pillow/Pillow
- python-xxhash 4.0.2 : BSD-2-Clause — https://github.com/ifduyue/python-xxhash
- python-zstandard 0.25.0 : BSD-3-Clause — https://github.com/indygreg/python-zstandard

Ces bibliothèques sont installées séparément par pip ; leurs notices accompagnent les distributions installées.

## Moteur LTK, non distribué ici

Les host/DLL officiels utilisés lors de la validation locale relèvent de la [LTK Patcher License](https://github.com/LeagueToolkit/ltk-manager/blob/v1.28.1/LTK-PATCHER-LICENSE.md), distincte de la GPL du gestionnaire et de la MIT de ce code original.

Cette licence autorise usage, étude et modification sous ses conditions. Une redistribution séparée des binaires impose notamment de retirer la signature officielle et de signer avec son propre certificat si l’on signe. Le dépôt ne fournit aucun binaire LTK ni copie repackagée. La copie officielle de l’utilisateur reste locale.

## Formats et projets examinés

Le format WAD a été étudié à partir de [CSLOL toc.hpp](https://github.com/LeagueToolkit/cslol-manager/blob/master/cslol-tools/lib/lol/wad/toc.hpp) et du comportement documenté de [ltk_overlay, Apache-2.0](https://github.com/LeagueToolkit/league-mod/blob/main/crates/ltk_overlay/src/wad_builder.rs). Le constructeur de ce projet a été écrit localement, sans incorporation de code de ces projets.

Rose (MIT) et Fantome historique (GPL-3.0) ont été examinés ; leur code n’est pas incorporé. Les binaires CSLOL utilisés lors d’anciens essais ne sont ni nécessaires à la version actuelle ni inclus dans le dépôt.

## Illustrations et mods

Les aperçus éventuellement présents dans les `.fantome` appartiennent à leurs auteurs respectifs. Les portraits de remplacement téléchargés localement depuis le CDN officiel Riot ne sont pas redistribués ici. En l’absence d’illustration, l’interface crée un visuel neutre de remplacement.

Ni les mods ni les ressources de jeu ne sont couverts par la licence MIT de ce dépôt.
