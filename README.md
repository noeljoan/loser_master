# Loser Master — Generateur Lotto de tickets perdus

Un système… pas pour gagner, mais pour rigoler ! permettant de
jouer plus de numéros au LOTO grâce au système des « garanties » (systèmes
réduits / *lotto wheels*).

> ⚠️ Le moteur de calcul des garanties (`wheel.py`) un algorithme classique en
> combinatoire, qui construit et **vérifie mathématiquement** chaque
> garantie. Sur les cas où l'original pouvait être comparé (garanties 3/3,
> 4/4, 5/5 avec 7 numéros), le nombre de grilles obtenu est identique au
> minimum théorique connu.

## Le principe

Une **garantie N-X/Y** signifie :

> Si, parmi vos **N** numéros joués, **Y** sortent au tirage, alors au moins
> une de vos grilles contiendra au moins **X** de ces numéros gagnants.

Exemple : garantie **9-3/4**. Vous choisissez 9 numéros. Si 4 d'entre eux
sortent au tirage, vous êtes assuré qu'au moins une de vos grilles jouées en
contient au moins 3.

Plus X et Y sont élevés, plus la garantie est « forte », mais plus il faut de
grilles (donc plus cher à jouer).

## Fonctionnalités

- Sélection des numéros joués sur une grille cliquable 1–49 (ou tirage au
  hasard pour tester).
- Garanties prédéfinies (3/3, 3/4, 4/5, 5/6, etc.) ou personnalisées (X/Y
  libres, taille de grille libre — 5, 6, 7 ou 8 numéros par grille).
- Moteur de calcul avec vérification exhaustive automatique pour les
  garanties de taille raisonnable, et vérification statistique
  pour les très grands nombres de numéros.
- Curseur qualité / temps de calcul (rapide / normal / approfondi).
- Export des grilles en **TXT** et **CSV**.
- Historique / favoris (sauvegardés localement).
- Thème clair / sombre.

## Limites assumées

Ce programme **calcule** chaque garantie à la demande avec un algorithme
heuristique. Pour de grands nombres de numéros (> 30) combinés à de fortes
exigences (Y élevé), le calcul peut :

- prendre plus de temps (réglable via le curseur qualité),
- ne pas être prouvé mathématiquement à 100 % (bascule alors en vérification
  statistique et l'indique clairement dans le statut affiché).

Ce n'est **pas un outil qui améliore vos chances de gagner** : c'est un
outil de combinatoire qui organise vos numéros en grilles selon une garantie
choisie. Jouez avec modération.

## Utilisation

```bash
python app.py
```

Aucune dépendance externe : uniquement la bibliothèque standard de Python
(`tkinter`, présent par défaut sur la plupart des installations Python sur
Windows/macOS ; sous Linux, installez `python3-tk` si besoin :
`sudo apt install python3-tk`).

## Empaqueter en .exe (Windows, via PyInstaller)

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name Loser_Master app.py
```

L'exécutable sera généré dans `dist/Loser_Master.exe`.

## Fichiers

- `app.py` — interface graphique Tkinter.
- `wheel.py` — moteur de calcul des garanties).
- `README.md` — ce fichier.

## Licence

Distribué sous licence MIT. Voir [`LICENSE`](LICENSE) pour les détails.
© 2026 - N. Joan
