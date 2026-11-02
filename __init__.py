"""Pi Harness — un harness d'agent LLM minimal mais complet, inspiré de
l'architecture de Claude Code (vidéo « I recoded Claude Code in 278 lines »).

Les 9 couches (une par module) :
  1. Modèle nu        -> harness/model.py
  2. Contexte         -> harness/context.py
  3. Conversation     -> harness/conversation.py
  4. Outils & boucle  -> harness/tools.py + harness/agent.py
  5. Gardes-fous      -> harness/guardrails.py
  6. Hooks            -> harness/hooks.py
  7. Rappels          -> harness/context.py (AGENTS.md rechargé à chaque tour)
  8. Contexte géré    -> harness/context.py (compaction du budget de tokens)
  9. Sous-agents      -> harness/subagents.py

Aucune inférence locale : tous les appels LLM passent par l'API Mistral
(zéro RAM/CPU du VPS au-delà du processus Python lui-même).
"""

__version__ = "0.1.0"
