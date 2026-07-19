# CROUS Alert France — MVP

Moniteur Python indépendant qui lit les offres publiques de
`trouverunlogement.lescrous.fr` et publie les nouvelles offres dans deux canaux
Telegram privés. Il utilise SQLite en local et PostgreSQL/Neon sur Render.

## Décisions MVP — 18 juillet 2026

- Source : endpoint JSON public utilisé par le site officiel.
- Périmètre : outil CROUS `47`, année 2026–2027, mécanisme `residual`.
- Une recherche nationale, pages séquentielles de 100 résultats.
- Intervalle initial : 120 secondes, minimum technique : 30 secondes.
- Premier lancement : initialisation SQLite sans publier les offres existantes.
- Publication : Trial `-1004420745494` et Premium `-1004417792221`.
- Photos : supportées avec fallback texte, désactivées par défaut en attente de
  clarification sur les droits de réutilisation de l’iconographie.
- `tzdata` est inclus pour fournir `Europe/Paris` sur Windows.
- Aucun compte CROUS, mot de passe client ou contournement de protection.

## Installation locale

```bash
python -m venv .venv
```

Windows PowerShell :

```powershell
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

Modifier `.env` localement et remplacer uniquement la valeur de
`TELEGRAM_BOT_TOKEN`. Ne jamais partager ni committer ce fichier.

## Tests

```powershell
python -m unittest discover -v
python -m app.main --once --no-publish
python -m app.main --once
```

Le premier scan affiche normalement `notified=0` car il initialise SQLite. Une
offre apparue après ce premier scan sera publiée dans les deux canaux.

## Fonctionnement continu

```bash
python -m app.main
```

Le service systemd fourni lance cette commande sur Ubuntu. Les journaux ne
contiennent pas le token Telegram.

## Déploiement Render + Neon

Le fichier `render.yaml` configure un seul worker web et la route de santé
`/healthz`. Un seul worker est volontaire : plusieurs workers lanceraient
plusieurs boucles de surveillance. PostgreSQL utilise aussi un verrou
transactionnel pour sérialiser les scans qui se chevauchent.

1. Créer un projet gratuit Neon et copier sa chaîne de connexion PostgreSQL
   **poolée**.
2. Importer ce dossier dans un dépôt GitHub privé, sans jamais ajouter `.env`.
3. Dans Render, créer un Blueprint depuis le dépôt. `render.yaml` remplit la
   configuration du service.
4. Saisir les deux secrets demandés par Render :
   `TELEGRAM_BOT_TOKEN` et `DATABASE_URL`.
5. Après le premier déploiement, ouvrir `https://NOM-DU-SERVICE.onrender.com/healthz`.
   La réponse doit contenir `"status":"ok"`.
6. Ajouter cette URL dans UptimeRobot avec un contrôle HTTP toutes les 5 minutes.

Le premier lancement sur une base Neon vide initialise les offres existantes
sans les publier. Les offres apparues ensuite sont envoyées une seule fois.
Ne jamais utiliser la base PostgreSQL gratuite temporaire de Render pour ce
projet : elle expire. La base Neon conserve l'historique entre les redémarrages
et redéploiements du service Render.

## Source et statut

Service indépendant, non affilié au CROUS. Les messages doivent garder le lien
officiel, la source et l’heure de détection. Aucune réservation ni attribution
de logement n’est garantie.
