from pathlib import Path
import copy
import json
import shutil

import pytest
import yaml
from jsonschema import Draft202012Validator

from maicon_sim.config.loader import ConfigError, load_scenario, read_data, validate_schema


EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
SCHEMAS = Path(__file__).resolve().parents[2] / "src/maicon_sim/resources/schemas"


@pytest.fixture
def workspace(tmp_path):
    root = tmp_path / "with spaces"
    shutil.copytree(EXAMPLES, root)
    return root


def change(path, mutate):
    data = yaml.safe_load(path.read_text())
    mutate(data)
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))


@pytest.mark.unit
@pytest.mark.parametrize("path", sorted(SCHEMAS.glob("*.json")), ids=lambda p:p.stem)
def test_schema_definition(path):
    """PACK-006: every local 2020-12 schema is valid."""
    Draft202012Validator.check_schema(json.loads(path.read_text()))


@pytest.mark.unit
@pytest.mark.parametrize("name", sorted(p.name for p in EXAMPLES.glob("scenario*.yaml")))
def test_all_supplied_scenarios(name):
    """PACK-006: cross-file semantic checks apply to all shipped scenarios."""
    c=load_scenario(EXAMPLES/name)
    assert len(c.scenario["agents"])==6
    assert len(c.hashes["scenario_hash"])==64
    prior=c.public_map_prior()
    assert set(prior)=={"arena_id","bounds","sectors","bases","nominal_starts"}
    assert "boxes" not in prior and "expected_m1" not in json.dumps(prior)


@pytest.mark.unit
@pytest.mark.parametrize("file,mutate", [
    ("scenario_smoke_six.yaml", lambda d:d.update(unrecognized=True)),
    ("scenario_smoke_six.yaml", lambda d:d["agents"][0].update(slot="B-2")),
    ("scenario_smoke_six.yaml", lambda d:d["agents"][0].update(mission_code="simr0001")),
    ("scenario_smoke_six.yaml", lambda d:d["boxes"][0]["pose"].update(x_m=.6)),
    ("scenario_smoke_six.yaml", lambda d:d["boxes"][0]["faces"].append(copy.deepcopy(d["boxes"][0]["faces"][0]))),
    ("scenario_smoke_six.yaml", lambda d:d["boxes"][0]["faces"][0].update(asset_id="not_here")),
    ("scenario_smoke_six.yaml", lambda d:d["boxes"][0]["faces"][0].update(object_class="mortar")),
    ("scenario_smoke_six.yaml", lambda d:d["orders"][0]["expected_m1"].update(target="BLUE_RADAR")),
    ("scenario_smoke_six.yaml", lambda d:d["agents"][0]["start_pose"].update(x_m=0)),
    ("scenario_smoke_six.yaml", lambda d:d["agents"][0]["start_pose"].update(x_m=float('nan'))),
    ("scenario_smoke_six.yaml", lambda d:d.update(max_sim_ms=360001)),
    ("rules_prestudy.yaml", lambda d:d["timing"].update(match_ms=240000)),
    ("rules_prestudy.yaml", lambda d:d["sensors"].update(camera_hz=30)),
    ("rules_prestudy.yaml", lambda d:d["sensors"].update(camera_width_px=320)),
    ("rules_prestudy.yaml", lambda d:d["sensors"].update(lidar_rays=180)),
    ("arena_reference.yaml", lambda d:d["sectors"][0]["polygon_xy_m"].reverse()),
    ("arena_reference.yaml", lambda d:d["nominal_starts"][0]["pose"].update(x_m=0)),
    ("arena_reference.yaml", lambda d:d["bases"][0].update(camp="RED")),
    ("assets_synthetic.yaml", lambda d:d["assets"][1].update(split_group=d["assets"][0]["split_group"],split="test")),
])
def test_invalid_configuration_is_actionable(workspace,file,mutate):
    """PACK-007/GEO-010: bad geometry/contracts fail before execution."""
    change(workspace/file, mutate)
    with pytest.raises(ConfigError) as exc:
        load_scenario(workspace/"scenario_smoke_six.yaml")
    assert "$" in str(exc.value)


def test_backend_requirements_are_not_silently_replaced(workspace):
    change(workspace/"scenario_smoke_six.yaml", lambda d:d.update(requires=["rgb"]))
    with pytest.raises(ConfigError,match="incompatible"):
        load_scenario(workspace/"scenario_smoke_six.yaml",backend="2d")
    load_scenario(workspace/"scenario_smoke_six.yaml",backend="3d")


def test_input_resources_stay_unchanged_and_hashes_stable(workspace):
    before={str(p.relative_to(workspace)):p.read_bytes() for p in workspace.rglob('*') if p.is_file()}
    a=load_scenario(workspace/"scenario_smoke_six.yaml")
    b=load_scenario(workspace/"scenario_smoke_six.yaml")
    assert a.hashes==b.hashes
    assert before=={str(p.relative_to(workspace)):p.read_bytes() for p in workspace.rglob('*') if p.is_file()}


def test_jitter_is_reproducible_and_realization_recorded(workspace):
    change(workspace/"scenario_smoke_six.yaml", lambda d:d["agents"][0].update(jitter_xy_m=.01))
    a=load_scenario(workspace/"scenario_smoke_six.yaml")
    b=load_scenario(workspace/"scenario_smoke_six.yaml")
    assert a.scenario==b.scenario
    assert a.hashes["scenario_hash"] != a.hashes["source_scenario_hash"]
    assert a.scenario["agents"][0]["start_pose"]["x_m"] != .4


def test_match_clock_resume_warning(workspace):
    def mutation(d):
        d["events"]=[{"event_id":"resume_later","kind":"resume","clock":"match","at_ms":1000,"parameters":{}}]
    change(workspace/"scenario_smoke_six.yaml", mutation)
    assert "unreachable" in load_scenario(workspace/"scenario_smoke_six.yaml").warnings[0]


def test_schema_error_does_not_echo_mission_code(workspace):
    change(workspace/"scenario_smoke_six.yaml", lambda d:d["agents"][0].update(mission_code="PRIVATE-CODE"))
    with pytest.raises(ConfigError) as exc:
        load_scenario(workspace/"scenario_smoke_six.yaml")
    assert "PRIVATE-CODE" not in str(exc.value)


def test_m3_normalized_schema_excludes_bool_count():
    payload={"mission_code":"SIMB0001","sectors":[{"sector":"R-S1","objects":[{"type":"TANK","count":True}]}]}
    with pytest.raises(ConfigError):
        validate_schema(payload,"m3.normalized")


def test_volume_fog_requires_valid_aabb(workspace):
    change(workspace/"sensor_profile_reference.yaml", lambda d:d["render"].update(fog_enabled=True,fog_model="volume"))
    with pytest.raises(ConfigError,match="fog_volume"):
        load_scenario(workspace/"scenario_smoke_six.yaml")
    change(workspace/"sensor_profile_reference.yaml", lambda d:d["render"].update(fog_volume_world_aabb_m=[[1,1,0],[2,2,1]]))
    load_scenario(workspace/"scenario_smoke_six.yaml")
    change(workspace/"sensor_profile_reference.yaml", lambda d:d["render"].update(fog_volume_world_aabb_m=[[1,1,0],[1,2,1]]))
    with pytest.raises(ConfigError,match="maximum greater"):
        load_scenario(workspace/"scenario_smoke_six.yaml")


@pytest.mark.parametrize("hp",[True,1.0,"1",-1,5])
def test_evaluator_correction_hp_is_strict_and_bounded(workspace,hp):
    def mutation(d):
        d["events"]=[{"event_id":"correct","kind":"robot_state_correction","clock":"match","at_ms":10,"parameters":{"slot":"B-1","hp":hp}}]
    change(workspace/"scenario_smoke_six.yaml",mutation)
    with pytest.raises(ConfigError):
        load_scenario(workspace/"scenario_smoke_six.yaml")
