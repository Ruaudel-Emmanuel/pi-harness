"""Étape 1 : le modèle nu.

La couche la plus basse du harness : un client HTTP minimaliste qui sait
faire UN appel de completion à l'API Mistral, avec ou sans outils.
Tout le reste du harness s'appuie uniquement sur cette fonction.
"""
import json
import urllib.error
import urllib.request
from typing import Any

from .config import Config


class ModelError(RuntimeError):
    pass


def http_post_json(url: str, payload: dict[str, Any], headers: dict[str, str], timeout: int) -> dict[str, Any]:
    """POST JSON en stdlib pur (urllib) — zéro dépendance tierce."""
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:400]
        raise ModelError(f"HTTP {e.code}: {body}") from e
    except urllib.error.URLError as e:
        raise ModelError(f"Erreur réseau : {e.reason}") from e


class MistralModel:
    """Un modèle nu = une fonction `chat(messages, tools) -> réponse brute`.

    Le harness ne connaît le modèle QUE par cette interface. Changer de
    fournisseur = réécrire ce fichier uniquement.
    """

    def __init__(self, cfg: Config, model: str | None = None) -> None:
        if not cfg.api_key:
            raise ModelError(
                "MISTRAL_API_KEY absente. Exportez-la dans votre environnement "
                "(jamais en dur dans le code)."
            )
        self.cfg = cfg
        self.model = model or cfg.model

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
    ) -> dict[str, Any]:
        """Appelle l'API et renvoie le message assistant brut.

        Le message contient soit `content`, soit `tool_calls`, soit les deux.
        """
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.cfg.temperature if temperature is None else temperature,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        data = http_post_json(
            self.cfg.api_url,
            payload,
            headers={"Authorization": f"Bearer {self.cfg.api_key}"},
            timeout=self.cfg.request_timeout,
        )
        return data["choices"][0]["message"]
