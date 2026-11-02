"""Étape 3 : la conversation.

Historique de messages persistant (JSON sur disque), avec titres et horodatage.
Rôles supportés : system / user / assistant / tool (résultats d'outils).
"""
import json
import time
import uuid
from pathlib import Path
from typing import Any

from .config import Config

# Rôles acceptés par l'API Mistral pour l'historique.
VALID_ROLES = {"system", "user", "assistant", "tool"}


class Conversation:
    def __init__(self, cfg: Config, conversation_id: str | None = None) -> None:
        self.cfg = cfg
        self.id = conversation_id or uuid.uuid4().hex[:12]
        self.path: Path = cfg.conversations_dir / f"{self.id}.json"
        self.messages: list[dict[str, Any]] = []
        self.title: str = ""
        self.created_at: float = time.time()
        self.updated_at: float = self.created_at
        self.token_usage: int = 0
        self.load()

    # --- persistance -------------------------------------------------
    def load(self) -> None:
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self.messages = [
                    m for m in data.get("messages", []) if m.get("role") in VALID_ROLES
                ]
                self.title = data.get("title", "")
                self.created_at = data.get("created_at", self.created_at)
                self.updated_at = data.get("updated_at", self.updated_at)
                self.token_usage = data.get("token_usage", 0)
            except (json.JSONDecodeError, OSError):
                # Fichier corrompu : on repart d'un historique vide plutôt que crasher.
                self.messages = []

    def save(self) -> None:
        self.updated_at = time.time()
        self.path.write_text(
            json.dumps(
                {
                    "id": self.id,
                    "title": self.title or self.id,
                    "created_at": self.created_at,
                    "updated_at": self.updated_at,
                    "token_usage": self.token_usage,
                    "messages": self.messages,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    # --- manipulation de l'historique --------------------------------
    def add(self, role: str, content: str, **extra: Any) -> dict[str, Any]:
        msg: dict[str, Any] = {"role": role, "content": content, **extra}
        self.messages.append(msg)
        return msg

    def add_assistant(self, message: dict[str, Any]) -> None:
        """Ajoute le message assistant brut renvoyé par le modèle
        (peut contenir `tool_calls`)."""
        self.messages.append(message)

    def history(self) -> list[dict[str, Any]]:
        """Historique sérialisable pour l'API (sans le message system,
        qui est reconstruit à chaque tour par la couche contexte)."""
        return self.messages

    def trim(self, keep_last: int) -> list[dict[str, Any]]:
        """Tronque l'historique en conservant les `keep_last` derniers messages.
        Renvoie la liste des messages retirés (pour compaction)."""
        if len(self.messages) <= keep_last:
            return []
        removed = self.messages[:-keep_last]
        self.messages = self.messages[-keep_last:]
        return removed

    def auto_title(self, first_user_message: str) -> str:
        if not self.title:
            words = first_user_message.split()[:6]
            self.title = " ".join(words)[:60]
        return self.title
