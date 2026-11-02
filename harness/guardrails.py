"""Étape 5 : les gardes-fous.

Chaque appel d'outil traverse cette couche AVANT exécution :
  - whitelist de commandes (préfixe exact, arguments shell-safe) ;
  - chemins bloqués (.env, clés SSH, shadow...) en lecture ET écriture ;
  - confirmation interactive pour les commandes destructives ;
  - plafond d'appels d'outils par tour (anti-boucle infinie).
"""
import shlex
from pathlib import Path

from .config import Config


class GuardrailError(RuntimeError):
    """Rejet explicite d'une action — remonté au modèle comme résultat d'outil."""


class Guardrails:
    def __init__(self, cfg: Config, confirm_fn=input) -> None:
        self.cfg = cfg
        self.confirm_fn = confirm_fn  # injecté pour rester testable
        self._tool_calls_this_turn = 0

    # --- compteur anti-boucle ---------------------------------------
    def new_turn(self) -> None:
        self._tool_calls_this_turn = 0

    def check_budget(self) -> None:
        self._tool_calls_this_turn += 1
        if self._tool_calls_this_turn > self.cfg.max_tool_calls:
            raise GuardrailError(
                f"Budget d'outils dépassé ({self.cfg.max_tool_calls} appels ce tour). "
                "Conclus maintenant avec ce que tu sais."
            )

    # --- validation des commandes ------------------------------------
    def check_command(self, argv: list[str]) -> None:
        if not argv:
            raise GuardrailError("Commande vide.")
        if argv[0] == "bash" or argv[0] == "sh":
            raise GuardrailError("Interpréteur de shell interdit.")
        cmd_line = " ".join(argv)
        allowed = any(
            cmd_line == prefix or cmd_line.startswith(prefix + " ")
            for prefix in self.cfg.allowed_commands
        )
        if not allowed:
            raise GuardrailError(
                f"Commande `{argv[0]}` absente de la whitelist. "
                f"Autorisées : {', '.join(self.cfg.allowed_commands)}"
            )
        # Interdiction d'injection même avec shlex : motifs d'expansion shell.
        for token in argv[1:]:
            if any(c in token for c in "$(`|;&<>"):
                raise GuardrailError(
                    f"Caractère d'interprétation shell interdit dans `{token}`."
                )
        # Confirmation pour les commandes destructives.
        for pattern in self.cfg.confirm_patterns:
            if cmd_line == pattern or cmd_line.startswith(pattern + " "):
                answer = self.confirm_fn(
                    f"⚠️  Autoriser `{cmd_line}` ? [y/N] "
                ).strip().lower()
                if answer not in ("y", "yes", "o", "oui"):
                    raise GuardrailError(
                        f"L'utilisateur a refusé `{cmd_line}`. Propose une alternative."
                    )

    # --- validation des chemins ---------------------------------------
    def check_path(self, raw_path: str, for_write: bool = False) -> Path:
        p = Path(raw_path).expanduser().resolve()
        # Containment : interdire de sortir de la racine autorisée.
        try:
            p.relative_to(self.cfg.files_root)
        except ValueError:
            raise GuardrailError(
                f"Chemin hors de la racine autorisée : {raw_path}"
            )
        p_str = str(p)
        for blocked in self.cfg.blocked_paths:
            b = blocked.rstrip("/")
            if b and (b in p.parts or p.name == b or p_str.endswith(b)):
                raise GuardrailError(f"Chemin sensible bloqué : {blocked}")
        if for_write:
            # Interdiction d'écrire dans les répertoires système du harness.
            home_str = str(self.cfg.home)
            if p_str.startswith(home_str):
                raise GuardrailError("Écriture interdite dans l'espace du harness.")
        return p

    # --- utilitaire pour parse sûr ------------------------------------
    @staticmethod
    def parse_argv(command: str) -> list[str]:
        """shlex.split : jamais de shell=True, jamais de ré-interprétation."""
        return shlex.split(command)
