"""Étape 9 : les sous-agents.

Un sous-agent = une instance de boucle d'agent avec son PROPRE contexte,
isolée de la conversation principale. Cas d'usage :
  - diagnostic long et verbeux (ramener uniquement la conclusion au parent) ;
  - investigation exploratoire sans polluer le contexte principal ;
  - tâche fortement outillée (le parent garde un contexte économe).

Le parent n'enregistre dans son historique QUE la réponse finale du
sous-agent : c'est le principe du « context quarantine ».
"""
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # import de type uniquement : pas de dépendance circulaire
    from .agent import Agent


class SubAgentRunner:
    def __init__(self, agent: "Agent") -> None:
        self.agent = agent

    def run(self, task: str, max_tool_calls: int | None = None) -> str:
        """Exécute un sous-agent de manière synchrone et renvoie sa réponse finale."""
        from .agent import Agent  # import tardif : casse la boucle d'imports

        sub_agent = Agent(
            cfg=self.agent.cfg,
            parent=self.agent,  # partage le modèle + les outils + gardes-fous
        )
        if max_tool_calls:
            sub_agent.guardrails.cfg.max_tool_calls = max_tool_calls
        return sub_agent.run_turn(
            f"Tâche confiée par l'agent principal : {task}\n"
            "Fais le travail de façon autonome, puis donne ta conclusion finale. "
            "Ta réponse finale sera le SEUL élément transmis à l'agent parent : "
            "sois précis et complet.",
        )
