from autoup import __version__, config, llm, run, state, utils
from autoup.stages import cover, download, dub, match, publish, render, script, validate


def test_import_surface():
    assert __version__
    assert run.STAGES == ["s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8", "s9"]
    assert callable(config.get)
    assert callable(llm.chat_json)
    assert callable(state.stage_fingerprint)
    assert callable(utils.stable_hash)
    assert callable(download.read_manifest)
    assert callable(script.run)
    assert callable(dub.run)
    assert callable(match.run)
    assert callable(render.plan_timeline)
    assert callable(publish.run)
    assert callable(cover.run)
    assert callable(validate.run)
