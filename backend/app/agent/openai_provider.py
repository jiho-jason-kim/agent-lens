"""Small Responses API adapter. Credentials never enter decision context or recordings."""

from typing import Any

import httpx
from app.agent.telemetry import error_category
from app.config import provider_settings


class ProviderConfigurationError(ValueError):
    """Server configuration is missing."""


class ProviderError(RuntimeError):
    """A provider request failed or produced no complete decision."""


def decision_schema(allow_messages: bool = False) -> dict[str, Any]:
    # Nested anyOf supports the three exact action shapes in strict Structured Outputs.
    actions = []
    for action in ("move", "collect", "wait"):
        properties: dict[str, Any] = {"type": {"type": "string", "enum": [action]}}
        if action == "move":
            properties["direction"] = {"type": "string", "enum": ["north", "south", "east", "west"]}
        actions.append({"type": "object", "properties": properties,
                        "required": list(properties), "additionalProperties": False})
    if allow_messages:
        actions.append({"type": "object", "properties": {
            "type": {"type": "string", "enum": ["send_message"]},
            "recipient": {"type": "string"}, "message": {"type": "string"},
        }, "required": ["type", "recipient", "message"], "additionalProperties": False})
    return {"type": "object", "properties": {"plan": {"type": "string"}, "action": {"anyOf": actions}},
            "required": ["plan", "action"], "additionalProperties": False}


class OpenAIProvider:
    def __init__(self, *, api_key: str, model: str, transport: httpx.BaseTransport | None = None) -> None:
        if not api_key.strip() or not model.strip():
            raise ProviderConfigurationError("Set OPENAI_API_KEY and OPENAI_MODEL on the backend server.")
        self._api_key = api_key.strip()
        self._model = model.strip()
        self._transport = transport
        self.settings = {"timeout_seconds": 60, "max_retries": 0, "max_output_tokens": 2048, "structured_output": "json_schema", "strict": True}
        self.last_telemetry = {}

    @classmethod
    def from_environment(cls) -> "OpenAIProvider":
        settings = provider_settings()
        return cls(api_key=settings["OPENAI_API_KEY"], model=settings["OPENAI_MODEL"])

    def generate(self, *, instructions: str, context_json: str, allow_messages: bool = False) -> str:
        self.last_telemetry = {}
        try:
            # Each request is independent. No provider-side conversation or tools are used.
            with httpx.Client(timeout=60, transport=self._transport) as client:
                response = client.post("https://api.openai.com/v1/responses",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json={"model": self._model, "store": False, "instructions": instructions,
                          "input": [{"role": "user", "content": context_json}],
                          "max_output_tokens": 2048,
                          "text": {"format": {"type": "json_schema", "name": "agent_decision",
                                               "strict": True, "schema": decision_schema(allow_messages)}}})
                response.raise_for_status()
                data = response.json()
            usage = data.get("usage") or {}
            self.last_telemetry["usage"] = {key: usage[key] for key in ("input_tokens", "output_tokens", "total_tokens") if isinstance(usage.get(key), int)}
            if data.get("status") != "completed":
                raise ProviderError("Provider did not complete the decision.")
            output = []
            for item in data.get("output", []):
                # Ignore reasoning items. Only explicit assistant output enters validation.
                if item.get("type") != "message" or item.get("role") != "assistant":
                    continue
                if item.get("status") != "completed":
                    raise ProviderError("Provider message was incomplete.")
                for content in item.get("content", []):
                    if content.get("type") == "refusal":
                        raise ProviderError("Provider declined the decision.")
                    if content.get("type") == "output_text":
                        output.append(content["text"])
            if len(output) != 1 or not isinstance(output[0], str):
                raise ProviderError("Provider returned no single decision.")
            return output[0]
        except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError) as exc:
            self.last_telemetry["error_category"] = error_category(exc)
            # Do not propagate response bodies, headers, or credentials to API clients.
            raise ProviderError("Provider request failed or returned an invalid response.") from None
