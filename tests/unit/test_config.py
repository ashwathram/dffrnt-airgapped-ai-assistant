from dffrnt_assistant.config import Settings, load_settings


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


def test_gpu_is_a_plain_flag(monkeypatch, tmp_path):
    # No environment presets: GPU comes only from the `gpu` flag (default off).
    assert Settings().gpu is False

    cfg = tmp_path / "config.toml"
    cfg.write_text("gpu = true\n")
    monkeypatch.setenv("DFFRNT_CONFIG", str(cfg))
    monkeypatch.delenv("GPU", raising=False)
    assert load_settings().gpu is True

    # Env still beats the file, with bool coercion.
    monkeypatch.setenv("GPU", "false")
    assert load_settings().gpu is False
