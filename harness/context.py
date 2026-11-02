"""Étapes 2, 7 et 8 : le contexte, les rappels, et le contexte géré.

- Étape 2 : construire le message system (identité, environnement, outils).
- Étape 7 : les rappels = un fichier AGENTS.md rechargé à CHAQUE tour, qui
  encode les règles durables de l'agent (comme CLAUDE.md / cursor rules).
- Étape 8 : le contexte géré = quand l'historique dépasse le budget, on
  compacte les vieux messages en un résumé produit par le modèle lui-même.
"""
import platform
import socket
import subprocess
from typing import Any

from .config import Config
from .conversation import Conversation
from .model import MistralModel

SYSTEM_BASE = """Tu es Pi Harness, l'agent d'administration du VPS rennesdev.fr.
Tu opères en ligne de commande, en direct sur le serveur.

Règles de conduite :
- Tu ne modifies JAMAIS un fichier sans avoir d'abord vérifié son contenu.
- Tu préfères les commandes en lecture seule ; toute action destructive
  demande une confirmation à l'utilisateur.
- Si une commande échoue, tu diagnostiques AVANT de réessayer autrement.
- Tu réponds en français, de façon concise et technique.

Environnement : {os} | hôte : {host} | utilisateur : {user}
Date courante : {date}"""


def _short(cmd: list[str]) -> str:
    try:
        out = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10, shell=False
        )
        return (out.stdout or out.stderr).strip().splitlines()[0][:80]
    except Exception:  # noqa: BLE001 — le contexte est best-effort
        return "inconnu"


def build_system_message(cfg: Config) -> dict[str, Any]:
    """Étape 2 : le contexte de base, reconstruit à chaque tour
    (l'état du serveur change, il ne doit jamais être périmé)."""
    return {
        "role": "system",
        "content": SYSTEM_BASE.format(
            os=platform.system(),
            host=socket.gethostname(),
            user=_short(["whoami"]),
            date=_short(["date"]),
        ),
    }


def build_reminder(cfg: Config) -> dict[str, Any] | None:
    """Étape 7 : les rappels.

    AGENTS.md contient les consignes durables (archi du VPS, ports, chemins).
    Rechargé à chaque tour : l'agent ne peut jamais « oublier » les règles,
    même après 50 tours de conversation.
    """
    path = cfg.reminders_file
    if not path.exists():
        return None
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        return None
    return {
        "role": "system",
        "content": f"<rappels-durables>\n{content}\n</rappels-durables>",
    }


def build_context_messages(
    cfg: Config, conv: Conversation
) -> list[dict[str, Any]]:
    """Assemble : [system de base] + [rappels AGENTS.md] + [historique compacté]."""
    messages: list[dict[str, Any]] = [build_system_message(cfg)]
    reminder = build_reminder(cfg)
    if reminder:
        messages.append(reminder)
    messages.extend(conv.history())
    return messages


def _estimate_tokens(messages: list[dict[str, Any]]) -> int:
    """Estimation grossière : ~4 caractères par token (Mistral tokenizer)."""
    total = 0
    for m in messages:
        total += len(str(m.get("content", ""))) // 4
    return total


def compact_if_needed(
    cfg: Config, conv: Conversation, model: MistralModel
) -> str | None:
    """Étape 8 : contexte géré.

    Si l'historique dépasse le budget, les messages les plus anciens sont
    retirés et remplacés par un résumé généré par un modèle petit/rapide.
    Le résumé est réinjecté comme message system en tête d'historique.
    """
    msgs = conv.history()
    total_chars = sum(len(str(m.get("content", ""))) for m in msgs)
    if total_chars <= cfg.max_context_chars and len(msgs) <= cfg.max_context_messages:
        return None  # rien à faire

    keep = 10  # on garde les 10 derniers messages intacts
    removed = conv.trim(keep)
    if not removed:
        return None

    transcript = "\n".join(
        f"[{m.get('role')}] {str(m.get('content', ''))[:600]}" for m in removed
    )
    summary = model.chat(
        [
            {
                "role": "user",
                "content": (
                    "Résume la conversation d'administration serveur suivante "
                    "en conservant : actions effectuées, chemins mentionnés, "
                    "décisions prises, problèmes ouverts. Résume en français, "
                    "100 mots max.\n\n" + transcript
                ),
            }
        ],
        temperature=0.0,
    )
    summary_text = summary.get("content") or "(résumé indisponible)"
    conv.messages.insert(
        0,
        {
            "role": "system",
            "content": (
                "<résumé-des-tours-précédents>\n"
                f"{summary_text}\n"
                "</résumé-des-tours-précédents>"
            ),
        },
    )
    return summary_text
