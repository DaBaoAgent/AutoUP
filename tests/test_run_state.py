from autoup import run, state, utils


def test_parse_override():
    assert run._parse_override("true") is True
    assert run._parse_override("null") is None
    assert run._parse_override("12") == 12
    assert run._parse_override("1.5") == 1.5
    assert run._parse_override("text") == "text"


def test_stage_fingerprint_changes_when_input_changes(tmp_path, monkeypatch):
    subtitle_dir = tmp_path / "字幕"
    subtitle_dir.mkdir()
    subtitle = subtitle_dir / "字幕.srt"
    subtitle.write_text("one", encoding="utf-8")

    monkeypatch.setattr(
        state.config,
        "get",
        lambda key, default=None: {
            "script": {"target_chars": 100},
            "llm.base_url": "x",
            "llm.model": "m",
            "llm.temperature": 0.1,
            "llm.max_retries": 1,
            "llm.max_tokens": 100,
        }.get(key, default),
    )
    first = state.stage_fingerprint(tmp_path, "s3")
    subtitle.write_text("two", encoding="utf-8")
    second = state.stage_fingerprint(tmp_path, "s3")
    assert first != second


def test_stage_done_checks_fingerprint(tmp_path, monkeypatch):
    script_dir = tmp_path / "文案"
    script_dir.mkdir()
    (script_dir / "爆款口播稿.txt").write_text("ok", encoding="utf-8")
    state_data = {"stages": {"s3": {"status": "done", "fingerprint": "same"}}}
    monkeypatch.setattr(run.stage_state, "stage_fingerprint", lambda *args, **kwargs: "same")
    assert run._stage_done(tmp_path, state_data, "s3", False)
    monkeypatch.setattr(run.stage_state, "stage_fingerprint", lambda *args, **kwargs: "changed")
    assert not run._stage_done(tmp_path, state_data, "s3", False)


def test_process_topic_only_does_not_force_validation(tmp_path, monkeypatch):
    called = []
    monkeypatch.setattr(run, "_load_state", lambda path: {})
    monkeypatch.setattr(run, "_stage_done", lambda *args, **kwargs: False)
    monkeypatch.setattr(run, "_mark", lambda *args, **kwargs: None)
    monkeypatch.setattr(run, "_record_metric", lambda *args, **kwargs: None)
    monkeypatch.setattr(run.script, "run", lambda path: called.append("s3"))
    monkeypatch.setattr(run.validate, "run", lambda path: (_ for _ in ()).throw(AssertionError("S9 should not run")))
    result = run.process_topic(tmp_path, ["s3"], False, "default")
    assert called == ["s3"]
    assert result["partial"] is True


def test_mark_persists_structured_stage(tmp_path, monkeypatch):
    monkeypatch.setattr(run.stage_state, "stage_fingerprint", lambda *args, **kwargs: "fp")
    data = {}
    run._mark(tmp_path, data, "s3")
    saved = utils.read_json(tmp_path / "state.json")
    assert saved["stages"]["s3"]["status"] == "done"
    assert saved["stages"]["s3"]["fingerprint"] == "fp"
