"""Read backend settings from a fixed local file and the process environment."""

import os
from pathlib import Path

from dotenv import dotenv_values

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


def provider_settings() -> dict[str, str]:
    # Explicit environment variables take priority. Never copy secrets into global state.
    values = dotenv_values(ENV_FILE)
    return {name: os.environ.get(name, values.get(name) or "")
            for name in ("OPENAI_API_KEY", "OPENAI_MODEL")}
