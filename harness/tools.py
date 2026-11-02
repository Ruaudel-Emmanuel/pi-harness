"""Étape 4 : les outils et la boucle.

Côté API Mistral, un outil = un schéma JSON annoncé au modèle. Côté
harness, un outil = une fonction Python. Le modèle choisit, le harness
exécute — JAMAIS l'inverse : le modèle ne touche pas au VPS directement.
"""
import subprocess
from typing import Any, Callable

from .config import Config
from .guardrails import Guardrails
from .hooks import Hooks

MAX_OUTPUT = 4000  # caractères renvoyés au modèle par outil (protection du contexte)


def _clip(text: str) -> str:
    if len(text) > MAX_OUTPUT:
        return text[:MAX_OUTPUT] + f"\n… (tronqué, {len(text)} chars au total)"
    return text


class ToolRegistry:
    def __init__(self, cfg: Config, guardrails: Guardrails, hooks: Hooks) -> None:
        self.cfg = cfg
        self.guardrails = guardrails
        self.hooks = hooks
        self._handlers: dict[str, Callable[[dict[str, Any]], str]] = {}
        self._schemas: list[dict[str, Any]] = []
        self._register_all()

    # --- déclaration -----------------------------------------------------
    def register(
        self, name: str, description: str, parameters: dict[str, Any],
        handler: Callable[[dict[str, Any]], str],
    ) -> None:
        self._handlers[name] = handler
        self._schemas.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": parameters,
                },
            }
        )

    def schemas(self) -> list[dict[str, Any]]:
        return self._schemas

    # --- exécution sécurisée d'un appel modèle ---------------------------
    def execute(self, name: str, arguments: dict[str, Any]) -> str:
        """Point d'entrée unique : gardes-fous -> hooks -> exécution -> hooks.
        Toute erreur devient une chaîne : le modèle la voit et réagit,
        le harness ne crash jamais."""
        handler = self._handlers.get(name)
        if handler is None:
            return f"Erreur : outil inconnu `{name}`."

        blocked = self.hooks.run_pre_tool(name, arguments)
        if blocked:
            self.hooks.run_on_error(name, arguments, f"bloqué: {blocked}")
            return f"Action refusée par un hook : {blocked}"

        try:
            self.guardrails.check_budget()
            result = handler(arguments)
            self.hooks.run_post_tool(name, arguments, result)
            return _clip(result)
        except Exception as e:  # noqa: BLE001 — toute erreur alimente le modèle
            msg = f"Erreur ({type(e).__name__}): {e}"
            self.hooks.run_on_error(name, arguments, msg)
            return msg

    # --- les outils concrets ---------------------------------------------
    def _register_all(self) -> None:
        self.register(
            "execute_command",
            "Exécute une commande en lecture sur le VPS. Whitelist stricte, "
            "pas de shell, pas de pipe ni expansion de variables.",
            {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Commande complète, ex: 'docker ps'",
                    }
                },
                "required": ["command"],
            },
            self._tool_execute_command,
        )
        self.register(
            "read_file",
            "Lit un fichier texte du VPS (taille limitée).",
            {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
            self._tool_read_file,
        )
        self.register(
            "write_file",
            "Écrit ou remplace un fichier texte. Interdit sur les chemins "
            "sensibles et l'espace du harness.",
            {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
            self._tool_write_file,
        )
        self.register(
            "list_dir",
            "Liste le contenu d'un répertoire (nom, type, taille).",
            {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
            self._tool_list_dir,
        )
        self.register(
            "end_turn",
            "Termine le tour immédiatement. À appeler quand la mission est "
            "accomplie et que la réponse finale est écrite.",
            {"type": "object", "properties": {}, "required": []},
            self._tool_end_turn,
        )
        self._turn_done = False

    def _tool_execute_command(self, args: dict[str, Any]) -> str:
        argv = Guardrails.parse_argv(args["command"])
        self.guardrails.check_command(argv)
        proc = subprocess.run(
            argv, capture_output=True, text=True, timeout=60, shell=False
        )
        out = proc.stdout.strip()
        err = proc.stderr.strip()
        parts = [f"exit={proc.returncode}"]
        if out:
            parts.append(f"stdout:\n{out}")
        if err:
            parts.append(f"stderr:\n{err}")
        return "\n".join(parts)

    def _tool_read_file(self, args: dict[str, Any]) -> str:
        p = self.guardrails.check_path(args["path"], for_write=False)
        if not p.is_file():
            return f"Fichier introuvable : {p}"
        return p.read_text(encoding="utf-8", errors="replace")

    def _tool_write_file(self, args: dict[str, Any]) -> str:
        p = self.guardrails.check_path(args["path"], for_write=True)
        existed = p.exists()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(args["content"], encoding="utf-8")
        return f"Fichier {'remplacé' if existed else 'créé'} : {p}"

    def _tool_list_dir(self, args: dict[str, Any]) -> str:
        p = self.guardrails.check_path(args["path"], for_write=False)
        if not p.is_dir():
            return f"Répertoire introuvable : {p}"
        lines = []
        for child in sorted(p.iterdir())[:200]:
            kind = "d " if child.is_dir() else "f "
            size = 0 if child.is_dir() else child.stat().st_size
            lines.append(f"{kind}{size:>10}  {child.name}")
        return "\n".join(lines) or "(vide)"

    def _tool_end_turn(self, args: dict[str, Any]) -> str:
        self._turn_done = True
        return "Tour terminé."

    # --- état de tour -----------------------------------------------------
    @property
    def turn_done(self) -> bool:
        return getattr(self, "_turn_done", False)

    def reset_turn(self) -> None:
        self._turn_done = False
