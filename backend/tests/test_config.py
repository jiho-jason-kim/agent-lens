"""Check local configuration without using or printing real credentials."""

from app import config
from app.agent.openai_provider import OpenAIProvider


def test_env_file_works_from_another_directory(tmp_path, monkeypatch):
    settings = tmp_path / ".env"
    settings.write_text('OPENAI_API_KEY="local-test-key"\nOPENAI_MODEL=test-model\n')
    monkeypatch.setattr(config, "ENV_FILE", settings)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    assert config.provider_settings() == {"OPENAI_API_KEY": "local-test-key", "OPENAI_MODEL": "test-model"}
    assert OpenAIProvider.from_environment()._model == "test-model"


def test_environment_wins_and_missing_file_is_allowed(tmp_path, monkeypatch):
    settings = tmp_path / ".env"
    settings.write_text('OPENAI_API_KEY=file-key\nOPENAI_MODEL=file-model\n')
    monkeypatch.setattr(config, "ENV_FILE", settings)
    monkeypatch.setenv("OPENAI_API_KEY", "environment-key")
    monkeypatch.setenv("OPENAI_MODEL", "environment-model")
    assert config.provider_settings()["OPENAI_API_KEY"] == "environment-key"
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / "missing.env")
    assert config.provider_settings()["OPENAI_MODEL"] == "environment-model"
