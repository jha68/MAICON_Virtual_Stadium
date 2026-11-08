"""Seeded, materialized layouts with conservative clearance checks."""
import copy
import math
import shutil
from pathlib import Path

import numpy as np
import yaml

from maicon_sim.config.loader import load_scenario, ConfigError


def connected(config):
    from maicon_sim.policies.planning import OccupancyGrid
    bounds = config.arena["bounds"]
    grid = OccupancyGrid(bounds["width_m"], bounds["height_m"])
    # A 0.4m diameter test disc certifies a 0.4m route, not all-pair spacing.
    for box in config.scenario["boxes"]:
        x, y = box["pose"]["x_m"], box["pose"]["y_m"]
        sx, sy = box["size_m"][:2]
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


def generate(template, seed, count, out):
    template, out = Path(template).resolve(), Path(out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    original = yaml.safe_load(template.read_text())
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
    arena = yaml.safe_load((out / original["arena_file"]).read_text())
    sectors = {s["sector_id"]: s["polygon_xy_m"] for s in arena["sectors"]}
    for index in range(count):
        candidate_path = out / f"generated-{seed}-{index:03d}.yaml"
        if candidate_path.exists():
            raise ConfigError(f"{candidate_path}: already exists; choose a new output directory")
        for attempt in range(1000):
            scenario = copy.deepcopy(original)
            scenario["seed"] = seed+index
            scenario["scenario_id"] = f"generated_{seed}_{index}"
            for box in scenario["boxes"]:
                polygon = np.asarray(sectors[box["sector_id"]])
                margin = np.asarray(box["size_m"][:2])/2+.02
                xy = rng.uniform(polygon.min(axis=0)+margin, polygon.max(axis=0)-margin)
                box["pose"].update(x_m=float(xy[0]), y_m=float(xy[1]), yaw_rad=0.)
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
