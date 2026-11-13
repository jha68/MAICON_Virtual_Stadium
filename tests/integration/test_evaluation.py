"""Executable handoff, replay corruption, and artifact isolation contracts."""
import copy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from maicon_sim.config.loader import load_scenario, canonical_hash, validate_schema
from maicon_sim.evaluation.runner import run_episode
from maicon_sim.evaluation.replay import replay_inputs, load_recorded_config, verify_files, replay_observations
from maicon_sim.evaluation.compare import compare


@pytest.fixture
def config():
    c = load_scenario("examples/scenario_smoke_six.yaml")
    c.rules["timing"].update(match_ms=1000, objective_publish_ms=800, report_ms=300)
    c.hashes["rule_profile_hash"] = canonical_hash(c.rules)
    return c


@pytest.mark.integration
def test_REPLAY_001_004_006_roundtrip_public_artifacts(config, tmp_path):
    original, root = run_episode(config, out=tmp_path / "original space")
    restored = load_recorded_config(root)
    replay, replay_root = run_episode(restored, out=tmp_path / "replay", replay_events=replay_inputs(root))
    assert compare(root, replay_root)["equal"]
    assert set(v["total"] for v in original["scores"].values()) == {49}
    validate_schema(original, "run_result")
    manifest = verify_files(root)
    assert manifest["sensor_mode"] == "semantic" and not manifest["oracle"]
    assert manifest["capabilities"]["rgb"] is False
    assert manifest["dependency_lock_hash"] != "not-available"
    transcript = "".join(p.read_text() for p in (root / "public").rglob("*.jsonl"))
    assert "SIMB0001" not in transcript and "expected_m1" not in transcript and "face_id" not in transcript


@pytest.mark.integration
def test_REPLAY_008_corrupted_or_missing_journal_fails(config, tmp_path):
    _, root = run_episode(config, out=tmp_path / "corrupt")
    path = root / "private/events.jsonl"
    lines = path.read_text().splitlines()
    path.write_text("\n".join(lines[1:])+"\n")
    with pytest.raises(ValueError, match="checksum"):
        replay_inputs(root)


@pytest.mark.integration
def test_ISO_003_006_007_public_child_environment(config, tmp_path, monkeypatch):
    from maicon_sim.evaluation.realtime import ParticipantProcesses
    from maicon_sim.core.engine import MatchEngine
    captured = {}
    class Child:
        pid = 123
    def popen(args, **kwargs):
        captured.update(kwargs)
        captured["args"] = args
        return Child()
    monkeypatch.setattr(subprocess, "Popen", popen)
    monkeypatch.setenv("MAICON_ADMIN_TOKEN", "sensitive-admin-value")
    monkeypatch.setenv("MAICON_LLM_PROVIDER", "openai-compatible")
    monkeypatch.setenv("MAICON_LLM_KEY_ENV", "TEST_PROVIDER_KEY")
    monkeypatch.setenv("TEST_PROVIDER_KEY", "test-only-secret")
    launcher = ParticipantProcesses(config, "http://127.0.0.1:9999", tmp_path, MatchEngine(config))
    launcher.launch(config.scenario["agents"][0])
    assert "MAICON_ADMIN_TOKEN" not in captured["env"]
    assert "MAICON_LLM_PROVIDER" not in captured["env"] and "TEST_PROVIDER_KEY" not in captured["env"]
    assert "--policy" not in captured["args"]
    assert "private" not in str(captured["args"])
    assert captured["cwd"].is_relative_to(tmp_path / "public/B-1")
    assert config.scenario["agents"][0]["mission_code"] not in str(captured["args"])
    for f in launcher.logs.values():
        f.close()


@pytest.mark.contract
def test_API_017_external_http_accelerated_cli_rejected():
    r = subprocess.run([sys.executable, "-m", "maicon_sim", "serve", "--example", "smoke_six", "--clock", "accelerated"], capture_output=True, text=True)
    assert r.returncode == 2 and "require realtime" in r.stderr


@pytest.mark.integration
def test_PACK_005_cli_space_path(config, tmp_path):
    # Entire dependency tree is copied into a path containing spaces.
    import shutil
    dest = tmp_path / "project with spaces"
    shutil.copytree("examples", dest)
    r = subprocess.run([sys.executable, "-m", "maicon_sim", "validate", "--scenario", str(dest / "scenario_smoke_six.yaml")], cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["valid"]


@pytest.mark.integration
def test_PACK_008_readme_cli_help_and_assets(tmp_path):
    from maicon_sim.cli import main
    for name in ("doctor", "validate", "run", "serve", "agent", "replay", "compare", "batch", "generate", "benchmark"):
        with pytest.raises(SystemExit) as e:
            main([name, "--help"])
        assert e.value.code == 0
    assert main(["assets", "build", "--manifest", "examples/assets_synthetic.yaml", "--out", str(tmp_path / "assets")]) == 0
    assert (tmp_path / "assets/resolved_manifest.yaml").exists()


@pytest.mark.integration
def test_REPLAY_007_materialized_generation_deterministic(tmp_path):
    from maicon_sim.evaluation.generate import generate
    left = generate("examples/scenario_smoke_six.yaml", 42, 1, tmp_path / "a")
    right = generate("examples/scenario_smoke_six.yaml", 42, 1, tmp_path / "b")
    assert Path(left[0]).read_bytes() == Path(right[0]).read_bytes()
    load_scenario(left[0])


@pytest.mark.integration
def test_ISO_004_oracle_groups_separate(config, tmp_path):
    from maicon_sim.evaluation.batch import seeded
    config.scenario["events"] = [{"event_id": "truth-fixture", "clock": "match", "at_ms": 100,
                                  "kind": "drone_facility_destroyed", "parameters": {"facility_code": "RED_RADAR"}}]
    result, root = run_episode(config, out=tmp_path / "oracle", oracle=True)
    manifest = json.loads((root / "run_manifest.json").read_text())
    assert manifest["oracle"] is True
    assert result["scores"]["B-1"]["m2"] == 10
    assert all(a["policy"] == "mission" for a in seeded(config, 99).scenario["agents"])


@pytest.mark.integration
def test_REPLAY_002_D2_P03_T3D_13_same_actions_two_backends(config, tmp_path):
    config.scenario["events"] = [{"event_id": "move", "clock": "match", "at_ms": 100,
                                  "kind": "robot_command", "parameters": {"slot": "B-1", "linear_x_mps": .1,
                                  "angular_z_rps": .2, "duration_ms": 300}}]
    first, left = run_episode(config, backend="2d", out=tmp_path / "two")
    second, right = run_episode(load_recorded_config(left), backend="3d", out=tmp_path / "three", replay_events=replay_inputs(left))
    assert compare(left, right)["equal"]
    def odom(path):
        values = [json.loads(line) for line in (path / "public/B-1/observations.jsonl").read_text().splitlines()]
        return [e["value"] for e in values if e["channel"] == "odom"]
    assert odom(left) == odom(right)


@pytest.mark.render
@pytest.mark.integration
def test_D2_P01_viewer_does_not_change_fixed_trace(config, tmp_path, monkeypatch):
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    monkeypatch.setenv("SDL_AUDIODRIVER", "dummy")
    _, headless = run_episode(config, out=tmp_path / "headless")
    _, observed = run_episode(config, out=tmp_path / "observed", viewer=True)
    assert compare(headless, observed)["equal"]
    for slot in ("B-1", "B-2", "B-3", "R-1", "R-2", "R-3"):
        assert (headless / "public" / slot / "observations.jsonl").read_bytes() == (observed / "public" / slot / "observations.jsonl").read_bytes()


@pytest.mark.integration
def test_REPLAY_003_same_recorded_rgb_two_callbacks(config, tmp_path):
    from maicon_sim.perception.synthetic_template import SyntheticTemplateDetector
    _, root = run_episode(config, backend="3d", out=tmp_path / "rgb", record_frames=True)
    frozen_result = (root / "result.json").read_bytes()
    seen_a, seen_b = [], []
    detector_a, detector_b = SyntheticTemplateDetector(threshold=.75), SyntheticTemplateDetector(threshold=.99)
    def callback(target, detector):
        def apply(slot, channel, value):
            if channel == "camera":
                target.append((slot, value["captured_tick"], detector.detect(value["data"]), value["frame_pixels_sha256"]))
        return apply
    replay_observations(root, callback(seen_a, detector_a))
    replay_observations(root, callback(seen_b, detector_b))
    assert seen_a and [x[:2]+x[3:] for x in seen_a] == [x[:2]+x[3:] for x in seen_b]
    assert detector_a.threshold != detector_b.threshold
    assert (root / "result.json").read_bytes() == frozen_result


@pytest.mark.integration
def test_REPLAY_005_recorded_checkpoint_cli_resume(config, tmp_path):
    config.rules["timing"].update(match_ms=60000, objective_publish_ms=48000, report_ms=1000)
    config.hashes["rule_profile_hash"] = canonical_hash(config.rules)
    _, original = run_episode(config, out=tmp_path / "full")
    saved = original / "private/checkpoints/tick-00005000.json"
    assert saved.is_file()
    _, resumed = run_episode(load_recorded_config(original), out=tmp_path / "resumed", replay_events=replay_inputs(original), checkpoint=saved)
    assert compare(original, resumed)["equal"]
    verify_files(resumed)


@pytest.mark.integration
def test_baseline_random_layouts_complete_reports_without_oracle(tmp_path):
    from maicon_sim.evaluation.generate import generate
    paths = generate("examples/scenario_smoke_six.yaml", 42, 3, tmp_path / "layouts")
    for i, path in enumerate(paths):
        cfg = load_scenario(path)
        cfg.scenario["agents"][0]["policy"] = "mission"
        cfg.rules["timing"].update(match_ms=2000, objective_publish_ms=1600, report_ms=500)
        result, root = run_episode(cfg, out=tmp_path / f"baseline-{i}")
        assert all(score["m1"] == 0 for score in result["scores"].values())
        assert result["final_match_ms"] == 2000 and 0 < result["final_report_ms"] <= 500
        manifest = verify_files(root)
        assert not manifest["oracle"]
        events = [json.loads(line) for line in (root / "private/events.jsonl").read_text().splitlines()]
        assert any(e["kind"] == "report_committed" and e["actor"] == "B-1" and e["payload"]["kind"] == "m6" for e in events)


@pytest.mark.integration
def test_replay_difference_reports_original_event_sequence(config, tmp_path):
    _, left = run_episode(config, out=tmp_path / "left")
    _, right = run_episode(config, out=tmp_path / "right")
    path = right / "private/events.jsonl"
    events = [json.loads(line) for line in path.read_text().splitlines()]
    first = next(e for e in events if e["category"] == "derived")
    first["payload"]["phase"] = "corrupted_phase"
    path.write_text("".join(json.dumps(e)+"\n" for e in events))
    difference = compare(left, right)
    assert not difference["equal"]
    assert difference["event_seq"] == difference["actual_event_seq"] == first["event_seq"]
