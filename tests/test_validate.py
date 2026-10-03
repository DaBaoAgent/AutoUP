from PIL import Image

from autoup import utils
from autoup.stages import validate


def _write_srt(path, count=12):
    blocks = []
    for index in range(1, count + 1):
        start = index * 2
        blocks.append(
            f"{index}\n00:00:{start:02d},000 --> 00:00:{start + 1:02d},000\nfact {index}\n"
        )
    path.write_text("\n".join(blocks), encoding="utf-8")


def test_validate_complete_topic(tmp_path, monkeypatch):
    material = tmp_path / "素材"
    subtitle_dir = tmp_path / "字幕"
    script_dir = tmp_path / "文案"
    voice_dir = tmp_path / "配音"
    publish_dir = tmp_path / "发布"
    cover_dir = tmp_path / "封面"
    for folder in (material, subtitle_dir, script_dir, voice_dir, publish_dir, cover_dir):
        folder.mkdir()

    source = material / "高清源视频.mp4"
    source.write_bytes(b"0" * 1_100_000)
    _write_srt(subtitle_dir / "字幕.srt")
    (script_dir / "爆款口播稿.txt").write_text("真实纪录片故事内容。" * 3, encoding="utf-8")

    for name in ("0001.wav", "0002.wav"):
        (voice_dir / name).write_bytes(b"R" * 2048)
    utils.write_json(
        voice_dir / "timing.json",
        {
            "total_duration": 4.3,
            "sentences": [
                {
                    "index": 1,
                    "text": "真实故事。",
                    "audio": "0001.wav",
                    "duration": 2.0,
                    "fingerprint": "a",
                },
                {
                    "index": 2,
                    "text": "继续讲述。",
                    "audio": "0002.wav",
                    "duration": 2.0,
                    "fingerprint": "b",
                },
            ],
        },
    )
    utils.write_json(
        tmp_path / "edit_decision.json",
        {
            "items": [
                {"sentence_index": 1, "start": 0.0, "end": 2.0},
                {"sentence_index": 2, "start": 3.0, "end": 5.0},
            ],
            "uncovered_sentences": [],
        },
    )

    final = tmp_path / "成片.mp4"
    final.write_bytes(b"1" * 1_100_000)
    (publish_dir / "国内平台.txt").write_text(
        "真实纪录片\n#纪录片 #历史 #故事 #人物 #档案\n",
        encoding="utf-8",
    )
    (publish_dir / "海外平台.txt").write_text(
        "A Real Documentary\n\nA factual account. #history #story #archive\n",
        encoding="utf-8",
    )

    for name, size in {
        "9x16": (1080, 1920),
        "16x9": (1920, 1080),
        "1x1": (1080, 1080),
    }.items():
        path = cover_dir / f"封面-{name}.png"
        Image.new("RGB", size, "white").save(path)
        with path.open("ab") as handle:
            handle.write(b"x" * 60_000)

    settings = {
        "script.target_chars": 30,
        "script.tolerance": 0.5,
        "video.width": 1920,
        "video.height": 1080,
    }
    monkeypatch.setattr(validate.config, "get", lambda key, default=None: settings.get(key, default))
    monkeypatch.setattr(
        validate.utils,
        "probe_video",
        lambda path: {
            "width": 1920,
            "height": 1080,
            "duration": 4.3,
            "fps": 30.0,
            "has_audio": True,
        },
    )

    report = validate.run(tmp_path)
    assert report["passed"] is True
    assert report["failed"] == []


def test_validate_rejects_missing_contracts(tmp_path):
    report = validate.run(tmp_path)
    assert report["passed"] is False
    assert "源视频" in report["failed"]
