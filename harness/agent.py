"""Le cœur du harness : la boucle agent.

Boucle d'un tour (comme Claude Code) :
  1. construire le contexte (étapes 2, 7, 8) ;
  2. appeler le modèle avec les outils (étape 1, 4) ;
  3. si le modèle demande un outil : gardes-fous (5) -> hooks (6) ->
     exécution -> réinjecter le résultat -> retour au 2 ;
  4. sinon : c'est la réponse finale, on la persiste et on la renvoie.

Un tour = 1 appel utilisateur, N appels de modèle, M appels d'outils,
plafonnés par les gardes-fous.
"""
import json
from typing import Any

from .config import Config
from .context import build_context_messages, compact_if_needed
from .conversation import Conversation
from .guardrails import Guardrails
from .hooks import Hooks
from .model import MistralModel
from .subagents import SubAgentRunner
from .tools import ToolRegistry


class Agent:
    def __init__(
        self,
        cfg: Config,
        conversation: Conversation | None = None,
        parent: "Agent | None" = None,
        echo: Any = None,
        model: MistralModel | None = None,
    ) -> None:
        self.cfg = cfg
        self.parent = parent
        # Le sous-agent hérite du modèle et des outils du parent (jamais de
        # double appel API inutile, même registre d'outils, mêmes gardes-fous).
        if parent is not None:
            self.model = parent.model
            self.tools = parent.tools
            self.guardrails = parent.guardrails
            self.hooks = parent.hooks
            self.subagents = parent.subagents
        else:
            # Modèle injectable : facilite les tests et les modèles custom.
            self.model = model or MistralModel(cfg)
            self.guardrails = Guardrails(cfg)
            self.hooks = Hooks(cfg)
            self.tools = ToolRegistry(cfg, self.guardrails, self.hooks)
            self.subagents = SubAgentRunner(self)

        self.conversation = conversation or Conversation(cfg)
        self.echo = echo or (lambda *_args, **_kw: None)  # sortie CLI, injectée
        self._register_subagent_tool()

    def _register_subagent_tool(self) -> None:
        """Le sous-agent lui-même n'a PAS l'outil spawn_subagent :
        pas de récursivité non bornée."""
        if self.parent is not None:
            return
        self.tools.register(
            "spawn_subagent",
            "Délègue une tâche d'investigation à un sous-agent isolé. "
            "Utile pour un diagnostic verbeux sans alourdir ce contexte. "
            "Renvoie uniquement la conclusion finale du sous-agent.",
            {
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "Mission précise et autonome à confier.",
                    }
                },
                "required": ["task"],
            },
            self._tool_spawn_subagent,
        )

    def _tool_spawn_subagent(self, args: dict[str, Any]) -> str:
        self.echo(f"  ├─ 🤖 sous-agent : {args['task'][:80]}…", style="dim")
        return self.subagents.run(args["task"])

    # --- la boucle ----------------------------------------------------------
    def run_turn(self, user_message: str) -> str:
        """Tour complet : message utilisateur -> réponse finale (avec outils)."""
        conv = self.conversation
        conv.add("user", user_message)
        conv.auto_title(user_message)

        self.guardrails.new_turn()
        self.tools.reset_turn()

        # Étape 8 : compaction éventuelle AVANT d'envoyer le contexte.
        compact_if_needed(self.cfg, conv, self.model)

        while True:
            messages = build_context_messages(self.cfg, conv)
            assistant_msg = self.model.chat(messages, tools=self.tools.schemas())
            conv.add_assistant(assistant_msg)

            tool_calls = assistant_msg.get("tool_calls") or []
            if not tool_calls or self.tools.turn_done:
                final = assistant_msg.get("content") or "(réponse vide)"
                conv.save()
                return final

            for tc in tool_calls:
                fn = tc["function"]
                name = fn["name"]
                self.echo(f"  ├─ 🛠 {name}({fn.get('arguments', '')})", style="dim")
                try:
                    arguments = (
                        json.loads(fn.get("arguments") or "{}")
                        if isinstance(fn.get("arguments"), str)
                        else (fn.get("arguments") or {})
                    )
                except ValueError:
                    arguments = {}
                result = self.tools.execute(name, arguments)
                conv.add("tool", result, tool_call_id=tc.get("id", ""))
                conv.save()
