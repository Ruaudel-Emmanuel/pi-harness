# Pi Harness — rappels durables (rechargés à chaque tour)

Ce fichier est injecté dans le contexte de l'agent à CHAQUE tour (étape 7).
Modifie-le pour donner à l'agent des règles ou des connaissances persistantes.

## Architecture du VPS rennesdev.fr (rappel permanent)

- VPS-1 : 4 vCores, 8 Go RAM, 75 Go disque. Ressources limitées : prudence.
- Aucun LLM auto-hébergé (Ollama abandonné le 31/10/2026) : l'IA passe par l'API Mistral.
- Services en place : n8n, PostgreSQL, Caddy (reverse proxy), Cloudflare devant.
- Agent web existant : agent.rennesdev.fr (FastAPI, port 5000) — repo Ruaudel-Emmanuel/agent-rennesdev.
- Passerelle API : repo Ruaudel-Emmanuel/API_VPS (JWT, Tailscale only).

## Règles métier

- Ne jamais redémarrer n8n ni PostgreSQL sans confirmation explicite.
- Toute modification de fichier de config (Caddy, systemd) : faire une copie
  .bak avant, et signaler le rollback à l'utilisateur.
- Les secrets vivent dans les .env du serveur : ne jamais les afficher en entier.
- Après une action destructive, toujours vérifier l'état du service concerné.
