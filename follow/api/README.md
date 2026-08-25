# Follow API + GUI

Expose une `Repository` Follow existante en REST (FastAPI), avec une petite interface web
statique servie par le même processus pour créer/consulter des expériences sans passer par le
CLI.

## Démarrer / arrêter

```bash
pip install "follow[api]"

follow_api start --repo .follow --port 8000
# -> Interface web : http://127.0.0.1:8000/

follow_api status
follow_api stop
```

Un seul serveur est suivi à la fois (pidfile + métadonnées sous `~/.follow/api/`) : `start`
échoue si un serveur tourne déjà, `stop`/`status` n'ont besoin d'aucun argument.

Un type de `Structure` déjà utilisé par une expérience du dépôt est importé automatiquement au
démarrage. Pour qu'un type **encore jamais committé** apparaisse dans le formulaire "nouvelle
expérience", listez son module avec `--structures` :

```bash
follow_api start --repo .follow --structures examples.recipe --structures examples.wafer_doe
```

## API

Toutes les routes sont sous `/api`. Points d'entrée principaux :

- `GET /api/health`, `/api/branches`, `/api/tags`, `/api/commit_form`
- `GET /api/structures`, `GET /api/structures/{key}/schema` (JSON Schema, pour générer un formulaire)
- `GET /api/log/{ref}`, `GET /api/experiments/{ref}`, `GET /api/graph`, `GET /api/diff?a=&b=`
- `GET /api/entities/{entity_id}`
- `POST /api/experiments` (créer + committer), `POST /api/experiments/{ref}/derive`, `POST /api/merge`
- `POST /api/branches`, `POST /api/tags`

Les erreurs Follow (`FollowError` et sous-classes) sont traduites en codes HTTP explicites :
404 (ref introuvable), 409 (rien à committer / conflit de fusion), 422 (formulaire ou structure
invalide), 400 (autre erreur Follow).

## GUI

`GET /` sert `follow/api/static/index.html` : liste des branches/tags, historique, fiche d'une
expérience (avec diff vs référence), et un formulaire "nouvelle expérience"/"dériver" généré
dynamiquement à partir du JSON Schema du type de structure choisi.
