#!/usr/bin/env python3
"""Pi Harness — CLI interactif.

Usage sur le VPS :
    export MISTRAL_API_KEY="…"
    python3 harness.py                    # nouvelle conversation
    python3 harness.py --list             # conversations existantes
    python3 harness.py --resume <id>      # reprendre une conversation
    python3 harness.py --ask "uptime ?"   # une seule question, sans REPL

Commandes du REPL : /exit, /new, /history, /tools, /context
"""
import argparse
import sys

from harness.agent import Agent
from harness.config import Config
from harness.conversation import Conversation

STYLES = {
    "dim": "\033[2m",
    "bold": "\033[1m",
    "ok": "\033[32m",
    "reset": "\033[0m",
}


def echo(text: str = "", style: str | None = None) -> None:
    if style and sys.stdout.isatty():
        print(f"{STYLES.get(style, '')}{text}{STYLES['reset']}")
    else:
        print(text)


def print_help() -> None:
    print(
        "Commandes : /exit /new /history /tools /context /help\n"
        "Sinon, parlez simplement à l'agent (français accepté)."
    )


def repl(agent: Agent) -> None:
    cfg = agent.cfg
    print(f"🧠 Pi Harness — modèle {cfg.model} | conversation {agent.conversation.id}")
    print_help()
    while True:
        try:
            user_input = input("\033[1m❯\033[0m ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user_input:
            continue
        if user_input == "/exit":
            break
        if user_input == "/help":
            print_help()
            continue
        if user_input == "/new":
            agent.conversation = Conversation(cfg)
            echo(f"✨ Nouvelle conversation {agent.conversation.id}", "ok")
            continue
        if user_input == "/history":
            for m in agent.conversation.messages:
                role = m.get("role")
                content = str(m.get("content", ""))[:120].replace("\n", " ")
                print(f"  [{role:>9}] {content}")
            continue
        if user_input == "/tools":
            for s in agent.tools.schemas():
                print(f"  • {s['function']['name']:18} {s['function']['description'][:70]}")
            continue
        if user_input == "/context":
            msgs = agent.conversation.messages
            chars = sum(len(str(m.get("content", ""))) for m in msgs)
            print(
                f"  messages: {len(msgs)} | ~{chars // 4} tokens estimés "
                f"| budget: {cfg.max_context_chars // 4} tokens"
            )
            continue

        try:
            answer = agent.run_turn(user_input)
            print()
            print(answer)
        except KeyboardInterrupt:
            echo("\n(⚠️ tour interrompu par l'utilisateur)", "dim")
        except Exception as e:  # noqa: BLE001 — le REPL ne doit jamais crasher
            print(f"\n❌ Erreur du harness : {e}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description="Pi Harness — agent CLI pour VPS")
    parser.add_argument("--resume", metavar="ID", help="reprendre une conversation")
    parser.add_argument("--list", action="store_true", help="lister les conversations")
    parser.add_argument("--ask", metavar="MSG", help="question unique, pas de REPL")
    parser.add_argument("--model", help="modèle Mistral (défaut: HARNESS_MODEL)")
    parser.add_argument(
        "--yes", action="store_true",
        help="répondre oui à toutes les confirmations des gardes-fous (à vos risques)",
    )
    args = parser.parse_args()

    cfg = Config()
    if args.model:
        cfg.model = args.model
    if not cfg.api_key:
        print(
            "❌ MISTRAL_API_KEY absente. Ajoutez-la dans ~/.bashrc ou un .env "
            "sourcé : export MISTRAL_API_KEY='…'",
            file=sys.stderr,
        )
        return 1

    if args.list:
        for f in sorted(cfg.conversations_dir.glob("*.json")):
            conv = Conversation(cfg, conversation_id=f.stem)
            print(f"  {conv.id}  {conv.title}  ({len(conv.messages)} messages)")
        return 0

    conv = Conversation(cfg, conversation_id=args.resume) if args.resume else None
    agent = Agent(cfg, conversation=conv)
    if args.yes:
        # Opt-in explicite : les confirmations des gardes-fous passent en auto.
        agent.guardrails.confirm_fn = lambda prompt: "y"

    if args.ask:
        print(agent.run_turn(args.ask))
        return 0

    repl(agent)
    return 0


if __name__ == "__main__":
    sys.exit(main())
