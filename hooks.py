"""Étape 6 : les hooks.

Points d'extension exécutés par le harness lui-même :
  - `pre_tool`  : avant chaque exécution d'outil (retourner "blocked: motif"
                  pour refuser, ou rien pour laisser passer) ;
  - `post_tool` : après exécution (traçabilité, notifications) ;
  - `on_error`  : quand un outil échoue.

Hook par défaut : journalisation horodatée dans ~/.pi-harness/harness.log
+ notification Telegram optionnelle si TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID
sont définis dans l'environnement.
"""
import datetime
import json
import os
import time
import urllib.request
from typing import Any, Callable

from .config import Config

HookFn = Callable[[dict[str, Any]], Any]


class Hooks:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.pre_tool: list[HookFn] = [self._log_pre]
        self.post_tool: list[HookFn] = [self._log_post]
        self.on_error: list[HookFn] = [self._log_error, self._notify_error]

    # --- infrastructure ------------------------------------------------
    def _log(self, kind: str, payload: dict[str, Any]) -> None:
        line = json.dumps(
            {"ts": datetime.datetime.now().isoformat(timespec="seconds"), "kind": kind, **payload},
            ensure_ascii=False,
        )
        try:
            with self.cfg.log_file.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass  # jamais faire crasher l'agent pour un log

    def run_pre_tool(self, tool_name: str, arguments: dict[str, Any]) -> str | None:
        """Renvoie un motif de blocage si un hook refuse l'action."""
        for hook in self.pre_tool:
            try:
                result = hook({"tool": tool_name, "arguments": arguments})
            except Exception:  # noqa: BLE001 — un hook ne doit jamais casser le tour
                continue
            if isinstance(result, str) and result.startswith("blocked:"):
                return result[len("blocked:"):].strip() or "bloqué par hook"
        return None

    def run_post_tool(self, tool_name: str, arguments: dict[str, Any], outcome: str) -> None:
        for hook in self.post_tool:
            try:
                hook(
                    {
                        "tool": tool_name,
                        "arguments": arguments,
                        "status": "ok",
                        "outcome": outcome[:500],
                    }
                )
            except Exception:  # noqa: BLE001
                continue

    def run_on_error(self, tool_name: str, arguments: dict[str, Any], error: str) -> None:
        for hook in self.on_error:
            try:
                hook(
                    {
                        "tool": tool_name,
                        "arguments": arguments,
                        "status": "error",
                        "error": error[:500],
                    }
                )
            except Exception:  # noqa: BLE001
                continue

    # --- hooks par défaut ----------------------------------------------
    def _log_pre(self, event: dict[str, Any]) -> None:
        self._log("pre_tool", event)

    def _log_post(self, event: dict[str, Any]) -> None:
        self._log("post_tool", event)

    def _log_error(self, event: dict[str, Any]) -> None:
        self._log("tool_error", event)

    def _notify_error(self, event: dict[str, Any]) -> None:
        """Notification Telegram quand un outil échoue (config optionnelle)."""
        token = os.environ.get("TELEGRAM_BOT_TOKEN")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID")
        if not token or not chat_id:
            return
        text = (
            f"🔴 Pi Harness — erreur outil `{event['tool']}`\n"
            f"{event.get('error', '')[:300]}"
        )
        try:
            urllib.request.urlopen(
                urllib.request.Request(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    data=json.dumps({"chat_id": chat_id, "text": text}).encode(),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                ),
                timeout=10,
            )
        except Exception:  # noqa: BLE001
            pass

    # --- exemple d'usage : ajouter son propre hook ----------------------
    @staticmethod
    def make_rate_limiter(max_per_minute: int = 12) -> HookFn:
        """Hook `pre_tool` exemple : limite le débit d'exécution d'outils."""
        state = {"window_start": time.time(), "count": 0}

        def hook(event: dict[str, Any]) -> str | None:
            now = time.time()
            if now - state["window_start"] > 60:
                state["window_start"] = now
                state["count"] = 0
            state["count"] += 1
            if state["count"] > max_per_minute:
                return f"blocked: débit dépassé ({max_per_minute} outils/min)"
            return None

        return hook
