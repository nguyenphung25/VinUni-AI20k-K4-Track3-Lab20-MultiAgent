from multi_agent_research_lab.core.config import Settings


def test_settings_defaults() -> None:
    settings = Settings()
    assert settings.openai_model
    assert settings.max_iterations >= 1


def test_settings_accepts_langfuse_base_url() -> None:
    settings = Settings(_env_file=None, LANGFUSE_BASE_URL="https://example.langfuse.test")

    assert settings.langfuse_base_url == "https://example.langfuse.test"
