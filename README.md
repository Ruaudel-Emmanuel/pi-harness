# Pi Harness

Un harness d'agent LLM **minimal mais complet**, inspiré de la vidéo
« I recoded Claude Code in 278 lines: here is what a harness really is »
(Yannick Dalbin) — reconstruit en Python pour le VPS rennesdev.fr.

**Un harness, c'est la couche logicielle entre l'utilisateur et le modèle :**
contexte, conversation, outils, gardes-fous, hooks, rappels, compaction,
sous-agents. Le modèle ne fait que prédire des tokens ; tout le reste, c'est ici.

## Les 9 couches (une par étape de la vidéo)

| # | Couche | Fichier | Rôle |
|---|--------|---------|------|
| 1 | Modèle nu | `harness/model.py` | 1 fonction : `chat(messages, tools)` → API Mistral |
| 2 | Contexte | `harness/context.py` | message system reconstruit à chaque tour (état VPS frais) |
| 3 | Conversation | `harness/conversation.py` | historique persisté en JSON, titres auto |
| 4 | Outils & boucle | `harness/tools.py` + `harness/agent.py` | tool-calling en boucle jusqu'à la réponse finale |
| 5 | Gardes-fous | `harness/guardrails.py` | whitelist, chemins bloqués, confirmations, budget |
| 6 | Hooks | `harness/hooks.py` | pre/post outil, log, notification Telegram |
| 7 | Rappels | `AGENTS.md` | règles durables rechargées à chaque tour |
| 8 | Contexte géré | `harness/context.py` | compaction : vieux messages résumés par le modèle |
| 9 | Sous-agents | `harness/subagents.py` | contexte isolé, seule la conclusion remonte |

## Installation sur le VPS

```bash
cd ~
git clone <votre-repo> pi-harness  # ou dézipper l'archive livrée
cd pi-harness
python3 --version  # aucune dépendance à installer

# Clé API : jamais dans le code, jamais dans le repo
echo 'export MISTRAL_API_KEY="votre-clé"' >> ~/.bashrc
source ~/.bashrc

python3 harness.py
```

## Utilisation

```bash
python3 harness.py                     # REPL interactif
python3 harness.py --ask "uptime ?"    # question unique (pour scripts/cron)
python3 harness.py --list              # lister les conversations
python3 harness.py --resume abc123     # reprendre une conversation
python3 harness.py --model mistral-large-latest   # changer de modèle
```

Dans le REPL : `/exit`, `/new`, `/history`, `/tools`, `/context`.

Ce qui s'affiche pendant un tour :
```
❯ pourquoi le service communication-web ne démarre pas ?
  ├─ 🛠 execute_command({"command": "systemctl status communication-web"})
  ├─ 🛠 read_file({"path": "/etc/systemd/system/communication-web.service"})
  └─ 🛠 execute_command({"command": "journalctl -u communication-web -n 50"})  ← refusé par whitelist ? l'agent s'adapte

Le service échoue car…
```

## Sécurité (ce que le modèle ne peut JAMAIS faire)

- **Pas de shell** : `shlex.split` + `subprocess.run(argv)`, jamais `shell=True`.
- **Whitelist stricte** de commandes (`HARNESS_ALLOWED_COMMANDS`), tout le reste refusé.
- **Pas de pipes, expansion `$()`, backticks, `;`, `&&`** : rejetés avant exécution.
- **Chemins bloqués** : `.env`, `id_rsa`, `shadow`, `.ssh`, `authorized_keys`…
- **Confirmation interactive** pour `rm`, `mv`, `systemctl restart`, `docker restart`.
- **Budget d'outils** : 15 appels/tour max → pas de boucle infinie qui brûle des tokens.
- **Écriture interdite** dans l'espace du harness (logs, conversations).
- Les erreurs d'outils **nourrissent le modèle** au lieu de crasher le harness.

## Configuration (variables d'environnement, toutes optionnelles)

| Variable | Défaut | Rôle |
|----------|--------|------|
| `MISTRAL_API_KEY` | — | **requis** |
| `HARNESS_MODEL` | `mistral-small-latest` | modèle principal |
| `HARNESS_SUMMARY_MODEL` | `open-mistral-nemo` | modèle de compaction (étape 8) |
| `HARNESS_MAX_TOOL_CALLS` | `15` | plafond d'outils par tour |
| `HARNESS_MAX_CONTEXT_CHARS` | `48000` | budget de contexte avant compaction |
| `HARNESS_ALLOWED_COMMANDS` | liste intégrée | whitelist de commandes |
| `HARNESS_BLOCKED_PATHS` | liste intégrée | chemins interdits |
| `HARNESS_REMINDERS_FILE` | `AGENTS.md` | fichier de rappels (étape 7) |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | — | notification d'erreurs |

## Ajouter un outil (le vrai test d'un harness)

Dans `harness/tools.py`, `_register_all()` :

```python
self.register(
    "query_db",
    "Exécute une requête SQL en lecture sur PostgreSQL.",
    {
        "type": "object",
        "properties": {"sql": {"type": "string"}},
        "required": ["sql"],
    },
    self._tool_query_db,
)
```

Et ajouter la gardes-fou adapté (ex: `SELECT` uniquement). Le modèle
découvrira l'outil automatiquement au tour suivant — c'est tout l'intérêt
d'un harness : **ajouter une capacité sans toucher à la boucle**.

## Ressources

Léger par construction : un seul process Python, la stdlib uniquement, zéro RAM
significative — cohérent avec VPS-1 (pas d'inférence locale, tout via Mistral).
