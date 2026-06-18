from dffrnt_assistant.config import Settings, load_settings


def test_llm_model_is_independent_of_environment():
    # No per-environment model presets: the model is the same regardless of target.
    default = Settings().llm_model
    assert Settings(environment="macbook").llm_model == default
    assert Settings(environment="aws").llm_model == default
    assert Settings(environment="local-cuda").llm_model == default


def test_llm_model_from_toml(monkeypatch, tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text('llm_model = "qwen3:4b"\n')
    monkeypatch.setenv("DFFRNT_CONFIG", str(cfg))
    monkeypatch.delenv("LLM_MODEL", raising=False)
    assert load_settings().llm_model == "qwen3:4b"


def test_env_overrides_are_typed(monkeypatch, tmp_path):
    monkeypatch.setenv("DFFRNT_CONFIG", str(tmp_path / "absent.toml"))
    monkeypatch.setenv("API_PORT", "9999")
    monkeypatch.setenv("TOP_K", "12")
    monkeypatch.setenv("LLM_TEMPERATURE", "0.7")
    monkeypatch.setenv("LLM_MODEL", "custom-model")
    settings = load_settings()
    assert settings.api_port == 9999 and isinstance(settings.api_port, int)
    assert settings.top_k == 12
    assert settings.llm_temperature == 0.7
    assert settings.llm_model == "custom-model"


def test_precedence_env_beats_toml(monkeypatch, tmp_path):
    config = tmp_path / "config.toml"
    config.write_text('api_port = 7000\ncollection_name = "from_toml"\n')
    monkeypatch.setenv("DFFRNT_CONFIG", str(config))
    monkeypatch.delenv("API_PORT", raising=False)

    settings = load_settings()
    assert settings.api_port == 7000
    assert settings.collection_name == "from_toml"

    monkeypatch.setenv("API_PORT", "7001")
    assert load_settings().api_port == 7001


def test_local_cuda_enables_gpu():
    assert Settings(environment="local-cuda").gpu is True


def test_gpu_off_by_default_for_other_environments():
    assert Settings(environment="aws").gpu is False
    assert Settings(environment="macbook").gpu is False
