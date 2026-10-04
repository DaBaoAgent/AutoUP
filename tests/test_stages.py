from pathlib import Path

import pytest
from PIL import Image

from autoup.stages import cover, download, dub, match, publish, render, script


def test_download_language_manifest_and_gate(tmp_path, monkeypatch):
    assert download._choose_english_language({"en-GB", "fr"}, {"en"}) == ("en-GB", "manual")
    assert download._choose_english_language(set(), {"en-US"}) == ("en-US", "auto")
    assert download._choose_english_language({"fr"}, {"de"}) == ("", "none")

    manifest = tmp_path / "urls.txt"
    manifest.write_text(
        "# comment\nhttps://example.test/a\nhttps://example.test/a\nhttps://example.test/b\n",
        encoding="utf-8",
    )
    assert download.read_manifest(manifest) == [
        "https://example.test/a",
        "https://example.test/b",
    ]

    monkeypatch.setattr(
        download,
        "fetch_meta",
        lambda url: {
            "ok": True,
            "url": url,
            "duration": 2000,
            "height": 1080,
            "sub_kind": "manual",
        },
    )
    monkeypatch.setattr(
        download.config,
        "get",
        lambda key, default=None: {
            "download.min_duration": 1800,
            "download.min_height": 720,
        }.get(key, default),
    )
    assert download.verify_url("u")["verdict"] == "approve"


def test_script_run_uses_all_source_windows(tmp_path, monkeypatch):
    subtitle_dir = tmp_path / "字幕"
    subtitle_dir.mkdir()
    rows = []
    for index in range(1, 9):
        start = (index - 1) * 10
        rows.append(
            f"{index}\n00:00:{start:02d},000 --> 00:00:{start + 5:02d},000\nsource fact {index}\n"
        )
    (subtitle_dir / "字幕.srt").write_text("\n".join(rows), encoding="utf-8")

    settings = {
        "script.target_chars": 400,
        "script.tolerance": 0.25,
        "script.section_chars": 200,
        "script.supplement_rounds": 0,
    }
    monkeypatch.setattr(script.config, "get", lambda key, default=None: settings.get(key, default))

    prompts = []

    def fake_chat(prompt, **kwargs):
        prompts.append(prompt)
        return "真实事实推动故事继续发展" * 17 + "。"

    monkeypatch.setattr(script.llm, "chat", fake_chat)
    output = script.run(tmp_path)

    text = output.read_text(encoding="utf-8")
    assert 300 <= script._count(text) <= 500
    assert len(prompts) == 2
    assert all("<srt>" in prompt and "</srt>" in prompt for prompt in prompts)
    assert "source fact 1" in prompts[0]
    assert "source fact 8" in prompts[-1]
    assert (tmp_path / "文案" / "script_map.json").exists()


def test_dub_voice_cache_is_input_aware(tmp_path, monkeypatch):
    script_dir = tmp_path / "文案"
    script_dir.mkdir()
    (script_dir / dub.SCRIPT_NAME).write_text("第一句。第二句。", encoding="utf-8")

    settings = {
        "voice": {"engine": "edge_tts", "gap_seconds": 0.3},
        "voice.gap_seconds": 0.3,
        "voice.gpt_sovits.voices.special.ref_audio_path": "",
    }
    monkeypatch.setattr(dub.config, "get", lambda key, default=None: settings.get(key, default))
    monkeypatch.setattr(dub.utils, "audio_duration", lambda path: 1.25)

    calls = []

    def fake_synth(text, path, voice="default"):
        calls.append((text, voice))
        path.write_bytes(b"R" * 2048)
        return path, "fake"

    monkeypatch.setattr(dub, "tts_synthesize", fake_synth)

    dub.run(tmp_path, voice="special")
    assert len(calls) == 2
    assert {voice for _, voice in calls} == {"special"}

    calls.clear()
    dub.run(tmp_path, voice="special")
    assert calls == []

    (script_dir / dub.SCRIPT_NAME).write_text("第一句改了。第二句。", encoding="utf-8")
    dub.run(tmp_path, voice="special")
    assert len(calls) >= 1


def test_match_run_requires_complete_semantic_coverage(tmp_path, monkeypatch):
    subtitle_dir = tmp_path / "字幕"
    subtitle_dir.mkdir()
    blocks = []
    for index in range(1, 7):
        start = (index - 1) * 10
        blocks.append(
            f"{index}\n00:00:{start:02d},000 --> 00:00:{start + 9:02d},000\nfact {index}\n"
        )
    (subtitle_dir / "字幕.srt").write_text("\n".join(blocks), encoding="utf-8")

    timing = {
        "sentences": [
            {"index": 1, "text": "甲。", "duration": 2.0, "audio": "0001.wav"},
            {"index": 2, "text": "乙。", "duration": 2.0, "audio": "0002.wav"},
            {"index": 3, "text": "丙。", "duration": 2.0, "audio": "0003.wav"},
        ]
    }
    (tmp_path / "配音").mkdir()
    from autoup import utils

    utils.write_json(tmp_path / "配音" / "timing.json", timing)

    settings = {
        "match.batch_sentences": 2,
        "match.repair_attempts": 1,
        "voice.gap_seconds": 0.3,
    }
    monkeypatch.setattr(match.config, "get", lambda key, default=None: settings.get(key, default))

    def fake_call(topic, srt, sentences, total_sentences, repair):
        return [
            {
                "sentence_index": item["index"],
                "start": f"0:00:{(item['index'] - 1) * 10:02d}.000",
                "end": f"0:00:{(item['index'] - 1) * 10 + 4:02d}.000",
            }
            for item in sentences
        ]

    monkeypatch.setattr(match, "_call_match", fake_call)
    output = match.run(tmp_path)
    edit = utils.read_json(output)
    assert len(edit["items"]) == 3
    assert edit["uncovered_sentences"] == []


def test_render_plan_and_deterministic_bgm(tmp_path, monkeypatch):
    timing = {
        "sentences": [
            {"index": 1, "text": "甲", "audio": "1.wav", "duration": 1.0},
            {"index": 2, "text": "乙", "audio": "2.wav", "duration": 1.5},
        ]
    }
    edit = {
        "items": [
            {"sentence_index": 1, "start": 0.0, "end": 2.0},
            {"sentence_index": 2, "start": 3.0, "end": 5.0},
        ]
    }
    monkeypatch.setattr(
        render.config,
        "get",
        lambda key, default=None: {"voice.gap_seconds": 0.3}.get(key, default),
    )
    plan = render.plan_timeline(edit, timing, 20.0)
    assert len(plan["cuts"]) == 2
    assert plan["voice"][1]["t_start"] == pytest.approx(2.3)

    bgm_dir = tmp_path / "bgm"
    bgm_dir.mkdir()
    (bgm_dir / "a.mp3").write_bytes(b"a")
    (bgm_dir / "b.mp3").write_bytes(b"b")
    values = {"bgm.directory": str(bgm_dir), "bgm.pick": "random"}
    monkeypatch.setattr(render.config, "get", lambda key, default=None: values.get(key, default))
    first = render._pick_bgm(Path("topic-A"))
    second = render._pick_bgm(Path("topic-A"))
    assert first == second


def test_publish_validation_and_write(tmp_path, monkeypatch):
    valid = {
        "cn_title": "真实纪录片标题",
        "cn_tags": ["纪录片", "历史", "故事", "人物", "档案"],
        "en_title": "A Real Documentary Story",
        "en_description": "A factual documentary account. #history #story #archive",
        "cover_main": "历史真相浮现",
        "cover_sub": "档案揭开尘封往事",
    }
    assert publish._validate(valid) == []
    invalid = {**valid, "cn_tags": ["重复"] * 5}
    assert publish._validate(invalid)

    script_dir = tmp_path / "文案"
    script_dir.mkdir()
    (script_dir / "爆款口播稿.txt").write_text("真实事实。" * 50, encoding="utf-8")
    monkeypatch.setattr(publish.llm, "chat_json", lambda *args, **kwargs: valid.copy())
    monkeypatch.setattr(
        publish.config,
        "get",
        lambda key, default=None: {"publish.repair_attempts": 1}.get(key, default),
    )
    output = publish.run(tmp_path)
    assert (output / "国内平台.txt").read_text(encoding="utf-8").count("#") == 5


def test_cover_crop_and_text_layer():
    image = Image.new("RGB", (800, 600), "white")
    assert cover._crop_ratio(image, 1080, 1920).size == (1080, 1920)
    layer = cover._draw_text_layer(600, "历史真相浮现", "档案揭开尘封往事")
    assert layer.width > 0
    assert layer.height > 0
