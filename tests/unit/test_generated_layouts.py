"""Generated competition fixtures preserve the physical M2 target pairing."""
from pathlib import Path
import shutil

import numpy as np
import pytest
import yaml

from maicon_sim.cli import main, parser
from maicon_sim.config.loader import ConfigError, load_scenario
from maicon_sim.core.geometry3d import face_rectangle, receiver_primitives
from maicon_sim.evaluation.generate import generate


TEMPLATE = Path("examples/scenario_smoke_six.yaml")


def assert_mirrored_facilities(config):
    width = config.arena["bounds"]["width_m"]
    faces = {face["facility_code"]: (box, face) for box in config.scenario["boxes"]
             for face in box["faces"] if face["kind"] == "facility"}
    receivers = {p.owner: p for p in receiver_primitives({}, config.scenario["boxes"], config.sensors["geometry"])}
    reflection = np.diag([-1., 1., 1.])
    for kind in ("COMMS", "OUTPOST", "RADAR"):
        blue, blue_face = faces["BLUE_"+kind]
        red, red_face = faces["RED_"+kind]
        bc, bn, _, _, bw, bh = face_rectangle(blue, blue_face["side"])
        rc, rn, _, _, rw, rh = face_rectangle(red, red_face["side"])
        assert rc == pytest.approx(reflection@bc+[width, 0., 0.], abs=1e-9)
        assert rn == pytest.approx(reflection@bn, abs=1e-9)
        assert (rw, rh) == pytest.approx((bw, bh))
        assert receivers["RED_"+kind].center == pytest.approx(reflection@receivers["BLUE_"+kind].center+[width, 0., 0.], abs=1e-9)


def write_template(tmp_path, update):
    root = tmp_path/"template"
    root.mkdir()
    data = yaml.safe_load(TEMPLATE.read_text())
    for key in ("rules_file", "arena_file", "assets_file", "sensor_profile_file"):
        shutil.copy2(TEMPLATE.parent/data[key], root/data[key])
    update(data)
    path = root/"scenario.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False))
    return path


def test_competition_generation_mirrors_actual_facility_faces_and_receivers(tmp_path):
    paths = generate(TEMPLATE, 42, 2, tmp_path/"layouts")
    assert len(paths) == 2
    configs = [load_scenario(path) for path in paths]
    for config in configs:
        assert_mirrored_facilities(config)
        assert "layout mode: competition" in config.scenario["description"]
    assert configs[0].scenario["boxes"] != configs[1].scenario["boxes"]


def test_competition_pairs_by_facility_code_and_preserves_template_face_assignments(tmp_path):
    def update(data):
        data["boxes"].reverse()
        for box in data["boxes"]:
            box["box_id"] = "custom_"+box["box_id"]
            for face in box["faces"]:
                if face["kind"] == "facility" and face["facility_code"].startswith("RED_"):
                    face["side"] = "north"
    template = write_template(tmp_path, update)
    [path] = generate(template, 7, 1, tmp_path/"layouts")
    config = load_scenario(path)
    assert_mirrored_facilities(config)
    assert all(face["side"] == "north" for box in config.scenario["boxes"] for face in box["faces"]
               if face["kind"] == "facility" and face["facility_code"].startswith("RED_"))


@pytest.mark.parametrize("problem", ["missing_pair", "different_dimensions", "shared_box_conflict"])
def test_competition_rejects_impossible_facility_pairings_before_sampling(tmp_path, problem):
    def update(data):
        red = data["boxes"][3]
        if problem == "missing_pair":
            red["faces"] = [f for f in red["faces"] if f["kind"] != "facility"]
        elif problem == "different_dimensions":
            red["size_m"][0] = .3
        else:
            # Two BLUE targets share one box but their RED targets do not.
            data["boxes"][0]["faces"].append(data["boxes"][1]["faces"].pop())
    template = write_template(tmp_path, update)
    out = tmp_path/"layouts"
    with pytest.raises(ConfigError, match="competition layout"):
        generate(template, 42, 1, out)
    assert not out.exists()


def test_stress_mode_is_explicitly_labelled_and_independently_places_facilities(tmp_path):
    [path] = generate(TEMPLATE, 42, 1, tmp_path/"stress", layout_mode="stress")
    config = load_scenario(path)
    assert "layout mode: stress" in config.scenario["description"]
    boxes = {b["box_id"]: b for b in config.scenario["boxes"]}
    blue, red = boxes["box_B1"]["pose"], boxes["box_R1"]["pose"]
    assert (red["x_m"], red["y_m"]) != pytest.approx((config.arena["bounds"]["width_m"]-blue["x_m"], blue["y_m"]))


def test_generate_cli_defaults_to_competition_and_forwards_explicit_stress(tmp_path, monkeypatch):
    parsed = parser().parse_args(["generate", "--template", str(TEMPLATE), "--seed", "42", "--out", str(tmp_path)])
    assert parsed.layout_mode == "competition"
    calls = []
    def fake_generate(*args, **kwargs):
        calls.append((args, kwargs))
        return []
    monkeypatch.setattr("maicon_sim.evaluation.generate.generate", fake_generate)
    assert main(["generate", "--template", str(TEMPLATE), "--seed", "42", "--out", str(tmp_path), "--layout-mode", "stress"]) == 0
    assert calls[0][1] == {"layout_mode": "stress"}
