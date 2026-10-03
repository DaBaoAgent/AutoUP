from autoup import utils


def test_srt_parse_and_format(tmp_path):
    srt = tmp_path / "a.srt"
    srt.write_text(
        "1\n00:00:01,000 --> 00:00:02,500\nHello world\n\n"
        "2\n00:00:03.000 --> 00:00:05.000\nSecond line\n",
        encoding="utf-8",
    )
    cues = utils.parse_srt(srt)
    assert len(cues) == 2
    assert cues[0]["start"] == 1.0
    assert cues[0]["duration"] == 1.5
    assert utils.fmt_ts(65.125) == "0:01:05.125"


def test_text_helpers():
    parts = utils.split_sentences("第一句。第二句！第三句没有句号")
    assert parts == ["第一句。", "第二句！", "第三句没有句号"]
    assert utils.estimate_duration("你好。") > 0


def test_hash_and_file_fingerprint(tmp_path):
    assert utils.stable_hash({"b": 2, "a": 1}) == utils.stable_hash({"a": 1, "b": 2})
    path = tmp_path / "data.bin"
    path.write_bytes(b"abc" * 100)
    first = utils.file_fingerprint(path)
    path.write_bytes(b"xyz" * 100)
    second = utils.file_fingerprint(path)
    assert first["exists"] is True
    assert first["sha256"] != second["sha256"]
    assert utils.file_fingerprint(tmp_path / "missing") == {"exists": False}


def test_json_atomic_roundtrip(tmp_path):
    path = tmp_path / "nested" / "data.json"
    utils.write_json(path, {"中文": [1, 2, 3]})
    assert utils.read_json(path) == {"中文": [1, 2, 3]}
    assert utils.read_json(tmp_path / "none.json", default={"x": 1}) == {"x": 1}
