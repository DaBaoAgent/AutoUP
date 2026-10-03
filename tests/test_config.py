from pathlib import Path

from autoup import config


def test_deep_merge_and_dotted_set():
    base = {"a": {"b": 1}, "x": 1}
    result = config._deep_merge(base, {"a": {"c": 2}, "x": 3})
    config._set_dotted(result, "a.d.e", 4)
    assert result == {"a": {"b": 1, "c": 2, "d": {"e": 4}}, "x": 3}


def test_load_honors_local_config_and_env(tmp_path, monkeypatch):
    default = tmp_path / "config.yaml"
    local = tmp_path / "local.yaml"
    default.write_text(
        "paths:\n  ffmpeg: ffmpeg\n  output_root: output\nllm:\n  model: base\n",
        encoding="utf-8",
    )
    local.write_text("llm:\n  model: local\n", encoding="utf-8")

    monkeypatch.setattr(config, "_CONFIG_PATH", default)
    monkeypatch.setattr(config, "_LOCAL_CONFIG_PATH", local)
    monkeypatch.setattr(config, "_REPO_ROOT", tmp_path)
    monkeypatch.setenv("AUTOUP_FFMPEG", "custom-ffmpeg")
    monkeypatch.setenv("GLM_API_KEY", "secret")
    monkeypatch.delenv("AUTOUP_CONFIG", raising=False)
    config.reset_cache()

    loaded = config.load()
    assert loaded["llm"]["model"] == "local"
    assert loaded["llm"]["api_key"] == "secret"
    assert config.ffmpeg() == "custom-ffmpeg"
    assert config.output_root() == tmp_path / "output"

    config.reset_cache()


def test_read_yaml_rejects_non_mapping(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text("- a\n- b\n", encoding="utf-8")
    try:
        config._read_yaml(path)
    except ValueError as exc:
        assert "mapping" in str(exc)
    else:
        raise AssertionError("expected ValueError")
