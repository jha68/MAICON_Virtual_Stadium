"""Seeded, materialized layouts with conservative clearance checks."""
import copy
import math
import shutil
from pathlib import Path

import numpy as np
import yaml

from maicon_sim.config.loader import load_scenario, ConfigError
from maicon_sim.config.models import FACILITY_CODES


_FACE_ANGLES = {"east": 0., "north": math.pi/2, "west": math.pi, "south": -math.pi/2}


def _half_extents(box, yaw):
    """World-axis extents, including a paired box's reflected orientation."""
    sx, sy = np.asarray(box["size_m"][:2])/2
    c, s = abs(math.cos(yaw)), abs(math.sin(yaw))
    return np.array([c*sx+s*sy, s*sx+c*sy])


def _facility_pairs(boxes):
    """Pair facilities by code, rather than box names or template order.

    Existing face assignments remain intact. Choose the RED box yaw so that its
    facility face normal mirrors BLUE's normal across the arena's x midpoint.
    Reject templates whose shared boxes or dimensions cannot satisfy every pair.
    """
    locations = {}
    for index, box in enumerate(boxes):
        for face in box["faces"]:
            if face["kind"] == "facility":
                code = face["facility_code"]
                if code in locations:
                    raise ConfigError(f"competition layout: duplicate facility {code}")
                locations[code] = (index, face)
    if set(locations) != set(FACILITY_CODES):
        raise ConfigError("competition layout requires one BLUE/RED pair of COMMS, OUTPOST and RADAR")
    pairs, blue_partners = {}, {}
    for blue_code in sorted(code for code in locations if code.startswith("BLUE_")):
        red_code = "RED_"+blue_code.split("_", 1)[1]
        blue, blue_face = locations[blue_code]
        red, red_face = locations[red_code]
        yaw = (math.pi-_FACE_ANGLES[blue_face["side"]]-_FACE_ANGLES[red_face["side"]]+math.pi) % (2*math.pi)-math.pi
        if blue in blue_partners and blue_partners[blue] != red:
            raise ConfigError(f"competition layout: facilities on {boxes[blue]['box_id']} need different RED boxes")
        if red in pairs and (pairs[red][0] != blue or not math.isclose(pairs[red][1], yaw, abs_tol=1e-9)):
            raise ConfigError(f"competition layout: incompatible mirrored faces on {boxes[red]['box_id']}")
        if not np.allclose(_half_extents(boxes[blue], 0.), _half_extents(boxes[red], yaw), rtol=0, atol=1e-9) or not math.isclose(boxes[blue]["size_m"][2], boxes[red]["size_m"][2], abs_tol=1e-9):
            raise ConfigError(f"competition layout: {blue_code}/{red_code} box dimensions cannot mirror")
        blue_partners[blue] = red
        pairs[red] = (blue, yaw)
    return pairs


def _sampling_bounds(box, polygon, yaw=0.):
    polygon = np.asarray(polygon)
    margin = _half_extents(box, yaw)+.02
    return polygon.min(axis=0)+margin, polygon.max(axis=0)-margin


def connected(config):
    from maicon_sim.policies.planning import OccupancyGrid
    bounds = config.arena["bounds"]
    grid = OccupancyGrid(bounds["width_m"], bounds["height_m"])
    # A 0.4m diameter test disc certifies a 0.4m route, not all-pair spacing.
    for box in config.scenario["boxes"]:
        x, y = box["pose"]["x_m"], box["pose"]["y_m"]
        sx, sy = 2*_half_extents(box, box["pose"]["yaw_rad"])
        for row in range(grid.cells.shape[0]):
            for col in range(grid.cells.shape[1]):
                xx, yy = grid.center((col, row))
                if abs(xx-x) <= sx/2+.2 and abs(yy-y) <= sy/2+.2:
                    grid.set_cell((col, row), 1)
    cm = next(s for s in config.arena["sectors"] if s["sector_id"] == "CM")
    p = cm["polygon_xy_m"]
    central = (sum(x[0] for x in p)/len(p), bounds["height_m"]*.2)
    for start in config.arena["nominal_starts"]:
        position = start["pose"]
        origin = grid.cell(position["x_m"], position["y_m"])
        other = "RED" if start["slot"].startswith("B") else "BLUE"
        goals = [central] + [tuple(np.mean(b["trigger_segment_xy_m"], axis=0)) for b in config.arena["bases"] if b["camp"] == other]
        if not all(grid.astar(origin, grid.cell(*goal)) for goal in goals):
            return False
    return True


def generate(template, seed, count, out, *, layout_mode="competition"):
    if layout_mode not in ("competition", "stress"):
        raise ConfigError("layout_mode must be competition or stress")
    template, out = Path(template).resolve(), Path(out).resolve()
    original = yaml.safe_load(template.read_text())
    pairs = _facility_pairs(original["boxes"]) if layout_mode == "competition" else {}
    arena = yaml.safe_load((template.parent / original["arena_file"]).read_text())
    sectors = {s["sector_id"]: s["polygon_xy_m"] for s in arena["sectors"]}
    width = arena["bounds"]["width_m"]
    sampling = {i: _sampling_bounds(box, sectors[box["sector_id"]], pairs.get(i, (None, 0.))[1])
                for i, box in enumerate(original["boxes"])}
    for red, (blue, _) in pairs.items():
        red_low, red_high = sampling[red]
        mirror_low = np.array([width-red_high[0], red_low[1]])
        mirror_high = np.array([width-red_low[0], red_high[1]])
        sampling[blue] = (np.maximum(sampling[blue][0], mirror_low), np.minimum(sampling[blue][1], mirror_high))
    for index, (low, high) in sampling.items():
        if np.any(low >= high):
            raise ConfigError(f"{original['boxes'][index]['box_id']}: no placement region for {layout_mode} layout")
    out.mkdir(parents=True, exist_ok=True)
    for key in ("rules_file", "arena_file", "assets_file", "sensor_profile_file"):
        source = template.parent / original[key]
        dest = out / source.name
        if source != dest:
            if dest.exists() and dest.read_bytes() != source.read_bytes():
                raise ConfigError(f"{dest}: existing dependency differs; select a new output directory")
            shutil.copy2(source, dest)
        original[key] = source.name
    rng = np.random.default_rng(seed)
    paths = []
    for index in range(count):
        candidate_path = out / f"generated-{seed}-{index:03d}.yaml"
        if candidate_path.exists():
            raise ConfigError(f"{candidate_path}: already exists; choose a new output directory")
        for attempt in range(1000):
            scenario = copy.deepcopy(original)
            scenario["seed"] = seed+index
            scenario["scenario_id"] = f"generated_{seed}_{index}"
            layout_note = ("M2 facility pairs mirror across the arena x midpoint" if pairs
                           else "independent asymmetric placement for stress testing")
            scenario["description"] = original.get("description", "")+f" Generated layout mode: {layout_mode}; {layout_note}."
            for box_index, box in enumerate(scenario["boxes"]):
                if box_index in pairs:
                    continue
                xy = rng.uniform(*sampling[box_index])
                box["pose"].update(x_m=float(xy[0]), y_m=float(xy[1]), yaw_rad=0.)
            for red, (blue, yaw) in pairs.items():
                blue_pose = scenario["boxes"][blue]["pose"]
                scenario["boxes"][red]["pose"].update(x_m=width-blue_pose["x_m"], y_m=blue_pose["y_m"], yaw_rad=yaw)
            for box in scenario["boxes"]:
                for face in box["faces"]:
                    if face["kind"] == "object":
                        label = str(rng.choice(("military_truck", "mortar", "tank", "missile", "ammo_box", "drum")))
                        face["object_class"] = label
                        face["asset_id"] = "object_"+label
            candidate_path.write_text(yaml.safe_dump(scenario, allow_unicode=True, sort_keys=False))
            try:
                cfg = load_scenario(candidate_path)
                if connected(cfg):
                    paths.append(str(candidate_path))
                    break
            except ConfigError:
                pass
        else:
            candidate_path.unlink(missing_ok=True)
            raise ConfigError(f"{candidate_path}: failed to place a connected valid layout after 1000 attempts")
    return paths
