from pathlib import Path
from types import SimpleNamespace

import pytest
import yt_dlp

from autoup import run, state, tts, utils
from autoup.stages import download, render


def test_download_fetch_meta_and_verify_branches(monkeypatch):
    class FakeYDL:
        def __init__(self, opts):
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def extract_info(self, url, download=False):
            return {
                "id": "abc",
                "title": "Title",
                "uploader": "Channel",
                "duration": 2000,
                "view_count": 123,
                "upload_date": "20260101",
                "subtitles": {"en-US": [{}]},
                "automatic_captions": {},
                "formats": [{"height": 720}, {"height": 1080}],
            }

    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYDL)
    monkeypatch.setattr(download, "_base_opts", lambda: {})
    meta = download.fetch_meta("https://example.test/video")
    assert meta["ok"] is True
    assert meta["sub_lang"] == "en-US"
    assert meta["height"] == 1080

    settings = {"download.min_duration": 1800, "download.min_height": 720}
    monkeypatch.setattr(download.config, "get", lambda key, default=None: settings.get(key, default))

    monkeypatch.setattr(download, "fetch_meta", lambda url: {**meta, "duration": 10})
    assert "时长" in download.verify_url("u")["reason"]
    monkeypatch.setattr(download, "fetch_meta", lambda url: {**meta, "height": 360})
    assert "最高" in download.verify_url("u")["reason"]
    monkeypatch.setattr(download, "fetch_meta", lambda url: {**meta, "sub_kind": "none"})
    assert "字幕" in download.verify_url("u")["reason"]
    monkeypatch.setattr(download, "fetch_meta", lambda url: {"ok": False, "url": url})
    assert download.verify_url("u")["verdict"] == "reject"


def test_download_verify_batch_and_remux(tmp_path, monkeypatch):
    monkeypatch.setattr(download.config, "get", lambda key, default=None: 1 if key == "download.verify_workers" else default)
    monkeypatch.setattr(
        download,
        "verify_url",
        lambda url: {
            "url": url,
            "verdict": "approve" if url.endswith("a") else "reject",
            "reason": "x",
        },
    )
    approved = download.verify_batch(["a", "b"], tmp_path / "report.csv")
    assert [row["url"] for row in approved] == ["a"]
    assert (tmp_path / "report.csv").exists()

    source = tmp_path / "video.webm"
    source.write_bytes(b"video")

    def fake_run(command, **kwargs):
        target = Path(command[-1])
        target.write_bytes(b"mp4")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(download.utils, "run", fake_run)
    target = download._remux_to_mp4(source)
    assert target.suffix == ".mp4"
    assert target.exists()
    assert not source.exists()


def test_download_topic_with_fake_ytdlp(tmp_path, monkeypatch):
    class FakeYDL:
        def __init__(self, opts):
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def download(self, urls):
            material = tmp_path / "素材"
            material.mkdir(exist_ok=True)
            (material / "高清源视频.mp4").write_bytes(b"video")
            (material / "高清源视频.en-US.srt").write_text(
                "1\n00:00:00,000 --> 00:00:01,000\nhello\n",
                encoding="utf-8",
            )

    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYDL)
    monkeypatch.setattr(download, "_base_opts", lambda: {})
    monkeypatch.setattr(download.config, "get", lambda key, default=None: 1080 if key == "download.max_height" else default)

    result = download.download_topic("u", tmp_path, sub_lang="en-US")
    assert result["video"].name == "高清源视频.mp4"
    assert result["subtitle"].read_text(encoding="utf-8").startswith("1")


def test_run_batch_existing_and_new(tmp_path, monkeypatch):
    monkeypatch.setattr(run.config, "output_root", lambda: tmp_path)

    batch = tmp_path / "existing"
    topic = batch / "01-topic"
    topic.mkdir(parents=True)
    utils.write_json(topic / "state.json", {"url": "u"})

    downloaded = []
    monkeypatch.setattr(run, "_ensure_downloaded", lambda td, url, state_data, force: downloaded.append((td.name, url)))
    monkeypatch.setattr(run, "process_topic", lambda *args, **kwargs: {"passed": True})
    result = run.run_batch(None, "existing", ["s2", "s3"], False, "default", None)
    assert result[0]["passed"] is True
    assert downloaded == [("01-topic", "u")]

    manifest = tmp_path / "manifest.txt"
    manifest.write_text("u\n", encoding="utf-8")
    monkeypatch.setattr(run.download, "read_manifest", lambda path: ["u"])
    monkeypatch.setattr(
        run.download,
        "verify_batch",
        lambda urls, report: [
            {
                "url": "u",
                "vid": "v",
                "title": "t",
                "channel": "c",
                "duration": 2000,
                "height": 1080,
                "sub_kind": "manual",
                "sub_lang": "en",
            }
        ],
    )
    monkeypatch.setattr(run, "_topic_name", lambda url, meta, idx: "01-new")
    monkeypatch.setattr(run, "_ensure_downloaded", lambda *args, **kwargs: None)
    monkeypatch.setattr(run, "process_topic", lambda *args, **kwargs: {"passed": True})
    result = run.run_batch(manifest, "new", None, False, "default", 1)
    assert result == [{"topic": "01-new", "url": "u", "passed": True}]


def test_run_helpers_and_topic_stage(tmp_path, monkeypatch):
    voice_dir = tmp_path / "配音"
    voice_dir.mkdir()
    audio = voice_dir / "0001.wav"
    audio.write_bytes(b"x" * 2048)
    utils.write_json(
        voice_dir / "timing.json",
        {"sentences": [{"index": 1, "audio": "0001.wav"}]},
    )
    assert run._timing_artifacts_ok(tmp_path)

    monkeypatch.setattr(run, "_stage_done", lambda *args, **kwargs: False)
    monkeypatch.setattr(run, "_record_metric", lambda *args, **kwargs: None)
    marks = []
    monkeypatch.setattr(run, "_mark", lambda *args, **kwargs: marks.append(args[2:4]))
    run._run_topic_stage(
        tmp_path,
        {},
        "s3",
        lambda: None,
        force=False,
        voice="default",
    )
    assert marks

    monkeypatch.setattr(run, "_mark", lambda *args, **kwargs: None)
    with pytest.raises(ValueError):
        run._run_topic_stage(
            tmp_path,
            {},
            "s3",
            lambda: (_ for _ in ()).throw(ValueError("bad")),
            force=False,
            voice="default",
        )


def test_state_all_stage_fingerprints(tmp_path, monkeypatch):
    for folder in ("素材", "字幕", "文案", "配音", "发布", "封面"):
        (tmp_path / folder).mkdir()
    (tmp_path / "素材" / "高清源视频.mp4").write_bytes(b"v")
    (tmp_path / "字幕" / "字幕.srt").write_text("s", encoding="utf-8")
    (tmp_path / "文案" / "爆款口播稿.txt").write_text("p", encoding="utf-8")
    utils.write_json(tmp_path / "配音" / "timing.json", {"x": 1})
    utils.write_json(tmp_path / "edit_decision.json", {"x": 1})
    (tmp_path / "成片.mp4").write_bytes(b"f")
    (tmp_path / "发布" / "国内平台.txt").write_text("c", encoding="utf-8")
    (tmp_path / "发布" / "海外平台.txt").write_text("e", encoding="utf-8")
    (tmp_path / "发布" / "封面文案.txt").write_text("x", encoding="utf-8")
    for name in ("9x16", "16x9", "1x1"):
        (tmp_path / "封面" / f"封面-{name}.png").write_bytes(b"i")

    monkeypatch.setattr(state.config, "get", lambda key, default=None: default)
    values = {
        stage: state.stage_fingerprint(tmp_path, stage, voice="default", url="u")
        for stage in ("s2", "s3", "s4", "s5", "s6", "s7", "s8", "s9", "other")
    }
    assert len(set(values.values())) == len(values)


def test_tts_engine_fallbacks(tmp_path, monkeypatch):
    out = tmp_path / "a.wav"

    settings = {
        "voice.engine": "gpt_sovits",
        "voice.fallback_engine": "edge_tts",
        "voice.gpt_sovits.voices": {"special": {"ref_audio_path": "x"}},
    }
    monkeypatch.setattr(tts.config, "get", lambda key, default=None: settings.get(key, default))
    monkeypatch.setattr(tts.gpt_sovits, "ensure_server", lambda: False)

    def edge_ok(text, path):
        path.write_bytes(b"x")
        return True

    monkeypatch.setattr(tts.edge, "synth", edge_ok)
    result, engine = tts.synth("hello", out, voice="special")
    assert result == out
    assert engine == "edge_tts"

    settings["voice.engine"] = "unknown"
    settings["voice.fallback_engine"] = ""
    result, engine = tts.synth("hello", out, voice="special")
    assert result is None
    assert engine == "all_engines_failed"


def test_render_helpers_and_run(tmp_path, monkeypatch):
    workdir = tmp_path / "work"
    workdir.mkdir()
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")

    settings = {
        "video.width": 640,
        "video.height": 360,
        "video.fps": 30,
        "video.crf": 18,
        "video.preset": "fast",
        "video.prefer_gpu": False,
        "voice.gap_seconds": 0.3,
    }
    monkeypatch.setattr(render.config, "get", lambda key, default=None: settings.get(key, default))

    def fake_run(command, **kwargs):
        target = Path(command[-1])
        if target.suffix:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"x")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(render.utils, "run", fake_run)
    segments = render.cut_segments(
        source,
        [{"src_start": 0.0, "src_end": 2.0}, {"src_start": 3.0, "src_end": 5.0}],
        workdir,
    )
    assert len(segments) == 2
    assert render.concat_segments(segments, workdir).exists()

    ass = workdir / "subs.ass"
    render.build_ass([{"start": 0.0, "end": 2.0, "text": "这是字幕测试。"}], ass)
    assert "Dialogue:" in ass.read_text(encoding="utf-8")

    topic = tmp_path / "topic"
    material = topic / "素材"
    material.mkdir(parents=True)
    (material / "高清源视频.mp4").write_bytes(b"source")
    (topic / "配音").mkdir()
    utils.write_json(
        topic / "配音" / "timing.json",
        {"sentences": [{"index": 1, "text": "甲", "audio": "1.wav", "duration": 1.0}]},
    )
    utils.write_json(
        topic / "edit_decision.json",
        {"items": [{"sentence_index": 1, "start": 0.0, "end": 2.0}]},
    )

    monkeypatch.setattr(render.utils, "probe_video", lambda path: {"duration": 10.0})
    monkeypatch.setattr(render, "cut_segments", lambda *args: [workdir / "seg_0001.mp4"])
    monkeypatch.setattr(render, "concat_segments", lambda *args: workdir / "picture.mp4")
    monkeypatch.setattr(render, "build_voice_track", lambda *args: workdir / "voice.wav")
    monkeypatch.setattr(render, "build_ass", lambda subs, path: path)
    monkeypatch.setattr(render, "_stage_font", lambda path: path / "fonts")
    monkeypatch.setattr(render, "_pick_bgm", lambda path: None)
    monkeypatch.setattr(render, "_video_codec_args", lambda: ("libx264", ["-crf", "18"]))
    settings["bgm.enabled"] = False

    output = render.run(topic)
    assert output.exists()
    assert (topic / "成片工程" / "render_report.json").exists()
