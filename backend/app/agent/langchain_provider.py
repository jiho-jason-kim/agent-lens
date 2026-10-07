"""Use LangChain for decisions while the simulation retains action execution."""

import json
from time import perf_counter
from app.agent.telemetry import error_category
from app.config import provider_settings

from app.agent.openai_provider import ProviderConfigurationError, ProviderError, decision_schema


class LangChainProvider:
    def __init__(self, model):
        # Separate structured runnables prevent tutorial actions from sending messages.
        self.model_name = getattr(model, "model_name", "unknown")
        self.settings = {"timeout_seconds": 60, "max_retries": 0, "structured_output": "json_schema", "strict": True}
        self.settings.update({key: getattr(model, key, None) for key in ("temperature", "top_p", "max_tokens", "seed", "reasoning_effort")})
        self.last_telemetry = {}
        self._decisions = {
            allow_messages: model.with_structured_output(
                {"title": "agent_decision", **decision_schema(allow_messages)},
                method="json_schema", strict=True, include_raw=True,
            ) for allow_messages in (False, True)
        }

    @classmethod
    def from_environment(cls):
        settings = provider_settings()
        key = settings["OPENAI_API_KEY"].strip()
        model = settings["OPENAI_MODEL"].strip()
        if not key or not model:
            raise ProviderConfigurationError("Set OPENAI_API_KEY and OPENAI_MODEL on the backend server.")
        try:
            from langchain_openai import ChatOpenAI
        except ImportError:
            raise ProviderConfigurationError("Install backend/requirements-langchain.txt to use LangChain.") from None
        try:
            return cls(ChatOpenAI(api_key=key, model=model, timeout=60, max_retries=0, store=False))
        except Exception:
            raise ProviderConfigurationError("Could not configure the LangChain model. Check the backend model configuration.") from None

    def generate(self, *, instructions: str, context_json: str, allow_messages: bool = False) -> str:
        started = perf_counter()
        self.last_telemetry = {}
        try:
            # Each decision receives only its recorded context, with no shared conversation.
            result = self._decisions[allow_messages].invoke([
                ("system", instructions), ("human", context_json),
            ])
            raw = result.get("raw") if isinstance(result, dict) else None
            usage = getattr(raw, "usage_metadata", None) or {}
            self.last_telemetry["usage"] = {key: usage[key] for key in ("input_tokens", "output_tokens", "total_tokens") if isinstance(usage.get(key), int)}
            if not isinstance(result, dict):
                raise ValueError("Missing structured result")
            if result.get("parsing_error"):
                raise ValueError("Structured output validation failed")
            result = result.get("parsed")
            if not isinstance(result, dict):
                raise ValueError("Missing structured decision")
            return json.dumps(result)
        except Exception as exc:
            self.last_telemetry["error_category"] = error_category(exc)
            # SDK errors can include credentials or request bodies. Keep them out of recordings.
            raise ProviderError("LangChain request failed or returned an invalid decision.") from None
        finally:
            self.last_telemetry["duration_ms"] = round((perf_counter() - started) * 1000, 2)
