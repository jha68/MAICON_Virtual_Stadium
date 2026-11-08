"""Cross-file and geometric validation beyond JSON Schema."""
from __future__ import annotations

from collections import Counter
import copy
import hashlib
import math
from pathlib import Path
import random

from .loader import ConfigError
from .models import BASE_CODES, FACILITY_CODES, SECTORS, SLOTS

EPS = 1e-9


def _cross(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _edges(poly):
    return list(zip(poly, poly[1:] + poly[:1]))


def _on_segment(p, a, b):
    return abs(_cross(a, b, p)) <= EPS and all(min(a[i], b[i])-EPS <= p[i] <= max(a[i], b[i])+EPS for i in (0, 1))


def _proper_intersection(a, b, c, d):
    return _cross(a, b, c) * _cross(a, b, d) < -EPS and _cross(c, d, a) * _cross(c, d, b) < -EPS


def _inside(p, poly, strict=False):
    if any(_on_segment(p, a, b) for a, b in _edges(poly)):
        return not strict
    inside = False
    for a, b in _edges(poly):
        if (a[1] > p[1]) != (b[1] > p[1]):
            if p[0] < (b[0]-a[0])*(p[1]-a[1])/(b[1]-a[1])+a[0]:
                inside = not inside
    return inside


def _overlap(a, b):
    # Polygons used for physical footprints are convex. Shared boundaries count
    # as contact, while the sector overlap check below distinguishes interiors.
    for poly in (a, b):
        for p, q in _edges(poly):
            axis = (-(q[1]-p[1]), q[0]-p[0])
            pa = [v[0]*axis[0]+v[1]*axis[1] for v in a]
            pb = [v[0]*axis[0]+v[1]*axis[1] for v in b]
            if max(pa) < min(pb)-EPS or max(pb) < min(pa)-EPS:
                return False
    return True


def footprint(pose, length, width):
    c, s = math.cos(pose["yaw_rad"]), math.sin(pose["yaw_rad"])
    return [[pose["x_m"] + c*x-s*y, pose["y_m"] + s*x+c*y]
            for x, y in ((-length/2, -width/2), (length/2, -width/2),
                         (length/2, width/2), (-length/2, width/2))]


def validate_semantics(cfg, backend):
    scenario, arena, rules, assets, sensors = cfg.scenario, cfg.arena, cfg.rules, cfg.assets, cfg.sensors
    warnings = []

    def require(test, path, message):
        if not test:
            raise ConfigError(f"{cfg.path}:{path}: {message}; correct the named field using the reference example")

    def unique(values, path):
        require(len(values) == len(set(values)), path, "duplicate identifiers")

    require(backend in ("2d", "3d"), "$.default_backend", "backend must be 2d or 3d")
    capabilities = {"2d": {"semantic", "lidar", "gui"}, "3d": {"rgb", "lidar", "gui"}}
    require(set(scenario["requires"]) <= capabilities[backend], "$.requires",
            f"requires {scenario['requires']} incompatible with {backend} capabilities")
    agents = scenario["agents"]
    require(Counter(a["slot"] for a in agents) == Counter(SLOTS), "$.agents", "exactly six distinct canonical slots required")
    unique([a["mission_code"].upper() for a in agents], "$.agents.mission_code")
    unique([b["box_id"] for b in scenario["boxes"]], "$.boxes.box_id")
    require(Counter(s["sector_id"] for s in arena["sectors"]) == Counter(SECTORS), "$.sectors", "all seven sectors required exactly once")
    require(Counter(b["code"] for b in arena["bases"]) == Counter(BASE_CODES), "$.bases", "all six base codes required exactly once")
    unique([b["base_id"] for b in arena["bases"]], "$.bases.base_id")
    require(Counter(s["slot"] for s in arena["nominal_starts"]) == Counter(SLOTS), "$.nominal_starts", "all six nominal starts required")
    w, h = arena["bounds"]["width_m"], arena["bounds"]["height_m"]
    sectors = {s["sector_id"]: s["polygon_xy_m"] for s in arena["sectors"]}
    polygons = [("sector", key, p) for key, p in sectors.items()]
    polygons += [("base", b["code"], b["polygon_xy_m"]) for b in arena["bases"]]
    for kind, key, p in polygons:
        area2 = sum(a[0]*b[1]-b[0]*a[1] for a,b in _edges(p))
        require(area2 > EPS, f"$.{kind}.{key}.polygon_xy_m", "polygon must have positive area and counterclockwise vertices")
        require(all(0-EPS <= a[0] <= w+EPS and 0-EPS <= a[1] <= h+EPS for a in p), f"$.{kind}.{key}.polygon_xy_m", "polygon leaves arena bounds")
        require(len({tuple(v) for v in p}) == len(p), f"$.{kind}.{key}.polygon_xy_m", "polygon has duplicate vertices")
        edges = _edges(p)
        for i, (a,b) in enumerate(edges):
            for j,(c,d) in enumerate(edges):
                if i < j and j != i+1 and not (i==0 and j==len(edges)-1):
                    require(not (_proper_intersection(a,b,c,d) or _on_segment(a,c,d) or _on_segment(c,a,b)), f"$.{kind}.{key}.polygon_xy_m", "self-intersecting polygon")
    # General polygon interiors: proper edge crossings, interior vertices, or
    # edge midpoints detect coincident rectangles without rejecting shared edges.
    for i, (kind, key, p) in enumerate(polygons):
        for kind2, key2, q in polygons[i+1:]:
            if kind == kind2 == "base":
                continue
            crosses = any(_proper_intersection(a,b,c,d) for a,b in _edges(p) for c,d in _edges(q))
            samples = p + [[(a[0]+b[0])/2,(a[1]+b[1])/2] for a,b in _edges(p)]
            samples2 = q + [[(a[0]+b[0])/2,(a[1]+b[1])/2] for a,b in _edges(q)]
            centroid = [sum(a[k] for a in p)/len(p) for k in (0,1)]
            coincident = _inside(centroid,p,True) and _inside(centroid,q,True)
            require(not(crosses or any(_inside(a,q,True) for a in samples) or any(_inside(a,p,True) for a in samples2) or coincident), "$.sectors", f"interior overlap between {key} and {key2}")
    asset_map = {a["asset_id"]: a for a in assets["assets"]}
    unique([a["asset_id"] for a in assets["assets"]], "$.assets.asset_id")
    groups = {}
    for asset in assets["assets"]:
        prior = groups.setdefault(asset["split_group"], asset["split"])
        require(prior == asset["split"], "$.assets.split_group", "same source group leaks across splits")
        if asset["generator"] == "import" or asset["path"] is not None:
            require(asset["path"] is not None and asset["sha256"] is not None, "$.assets.path", "imported/resolved assets need path and SHA256")
            location = cfg.path.parent / scenario["assets_file"]
            p = Path(asset["path"])
            require(not p.is_absolute(), "$.assets.path", "asset paths must be relative")
            p = location.parent/p
            require(p.is_file(), "$.assets.path", "asset file missing")
            require(hashlib.sha256(p.read_bytes()).hexdigest() == asset["sha256"], "$.assets.sha256", "asset digest mismatch")
    facilities = []
    box_shapes = []
    for i, box in enumerate(scenario["boxes"]):
        path = f"$.boxes[{i}]"
        shape = footprint(box["pose"], *box["size_m"][:2])
        require(all(_inside(p, sectors[box["sector_id"]], True) for p in shape), path+".sector_id", "entire box footprint must lie strictly inside declared sector")
        for old, old_shape in box_shapes:
            require(not _overlap(shape, old_shape), path+".pose", f"box touches/overlaps {old}")
        box_shapes.append((box["box_id"], shape))
        unique([f["side"] for f in box["faces"]], path+".faces.side")
        for face in box["faces"]:
            require(face["asset_id"] in asset_map, path+".faces.asset_id", "unknown asset reference")
            asset = asset_map[face["asset_id"]]
            require(face["kind"] == asset["kind"], path+".faces.kind", "asset and face kinds disagree")
            if face["kind"] == "object":
                require(face["object_class"] == asset["label"], path+".faces.object_class", "asset and face class disagree")
            if face["kind"] == "facility":
                code=face["facility_code"]
                facilities.append(code)
                require(code.split("_",1)[1] == asset["label"], path+".faces.facility_code", "facility label mismatch")
                require((code.startswith("BLUE_") and box["sector_id"].startswith("B-")) or (code.startswith("RED_") and box["sector_id"].startswith("R-")), path+".faces.facility_code", "facility camp and sector disagree")
    require(Counter(facilities) == Counter(FACILITY_CODES), "$.boxes.faces", "each camp requires exactly COMMS, OUTPOST and RADAR")
    require(Counter(o["slot"] for o in scenario["orders"]) == Counter(SLOTS), "$.orders", "one order per slot required")
    for prefix in ("B", "R"):
        orders = [o for o in scenario["orders"] if o["slot"].startswith(prefix)]
        targets = [o["expected_m1"]["target"] for o in orders]
        require(all(t.startswith("RED_" if prefix=="B" else "BLUE_") for t in targets), "$.orders.expected_m1.target", "M2 target must be enemy facility")
        unique(targets, "$.orders.expected_m1.target")
        for o in orders:
            unique(o["expected_m1"]["search_sectors"], "$.orders.expected_m1.search_sectors")
    for camp, objective in scenario["objectives_by_camp"].items():
        require(objective in BASE_CODES and not objective.startswith(camp+"_"), "$.objectives_by_camp", "objective must be an existing enemy base")
    for base in arena["bases"]:
        require(base["code"].startswith(base["camp"]+"_"), "$.bases.camp", "base code and camp disagree")
        a,b = base["trigger_segment_xy_m"]
        require(a != b and all(0-EPS <= p[0] <= w+EPS and 0-EPS <= p[1] <= h+EPS for p in (a,b)), "$.bases.trigger_segment_xy_m", "trigger must be a nonzero segment inside arena")
    timing = rules["timing"]
    require(timing["tick_ms"] == 10 and timing["objective_publish_ms"] < timing["match_ms"] and timing["report_ms"] > 0, "$.timing", "use 10ms ticks and objective before positive match/report deadline")
    for k,v in timing.items():
        require(v % 10 == 0, "$.timing."+k, "duration must be a multiple of 10ms")
    for k,v in rules["robot"].items():
        if k.endswith("_ms"):
            require(v%10==0,"$.robot."+k,"duration must be a multiple of 10ms")
    for k,v in rules["sensors"].items():
        if k.endswith("_hz"):
            require(v > 0 and 100%v == 0, "$.sensors."+k, "sensor frequency must divide 100Hz")
    require(all(v%10==0 for v in rules["sensors"]["drone_intervals_ms"]), "$.sensors.drone_intervals_ms", "durations must be multiples of 10ms")
    require(scenario["max_sim_ms"]%10==0, "$.max_sim_ms", "duration must be a multiple of 10ms")
    camera, lidar, rs = sensors["front_camera"], sensors["lidar"], rules["sensors"]
    require(camera["width_px"] == rs["camera_width_px"] and camera["height_px"] == rs["camera_height_px"], "$.front_camera", "rules and sensor profile camera sizes disagree")
    fov=math.degrees(2*math.atan(camera["width_px"]/(2*camera["fx_px"])))
    require(abs(fov-rs["camera_hfov_deg"]) <= 1e-6, "$.front_camera.fx_px", "rules and sensor profile HFOV disagree")
    for key, rkey in (("ray_count","lidar_rays"),("range_min_m","lidar_min_m"),("range_max_m","lidar_max_m")):
        require(lidar[key] == rs[rkey], "$.lidar."+key, "rules and sensor profile LiDAR values disagree")
    require(camera["near_m"] < camera["far_m"] and lidar["range_min_m"] < lidar["range_max_m"], "$.sensors", "minimum/near range must precede maximum/far")
    render=sensors["render"]
    if render.get("fog_enabled") and render.get("fog_model") == "volume":
        volume=render.get("fog_volume_world_aabb_m")
        require(volume is not None and len(volume)==2 and all(volume[1][axis]>volume[0][axis] for axis in range(3)), "$.render.fog_volume_world_aabb_m", "enabled volume fog requires an AABB with maximum greater than minimum on every axis")
    for name, noise in sensors["noise_profiles"].items():
        require(noise["camera_delay_ms"]%10==0 and noise["drone_delay_ms"]%10==0, "$.noise_profiles."+name, "sensor delay must use integer ticks")
    unique([e["event_id"] for e in scenario["events"]], "$.events.event_id")
    for event in scenario["events"]:
        p=event["parameters"]
        if event["kind"]=="robot_state_correction":
            require(all(type(p[key]) is int for key in ("hp","ammo") if key in p), "$.events.parameters", "corrected hp/ammo must be strict integers")
        require(event["at_ms"]%10 == 0 and ("duration_ms" not in p or p["duration_ms"]%10 == 0), "$.events", "event time/duration must be a multiple of 10ms")
        require(not(p.get("drop_response_after_commit") and p.get("stage")!="after_commit"), "$.events.parameters", "response drop is only valid after_commit")
        if event["kind"] == "resume" and event["clock"] == "match":
            warnings.append(f"{event['event_id']}: match-clock resume can be unreachable during pause; use sim clock")
    length=sensors["geometry"]["footprint_length_m"]
    width=sensors["geometry"]["footprint_width_m"]
    def valid_start(pose, existing):
        shape=footprint(pose,length,width)
        return (all(EPS < p[0] < w-EPS and EPS < p[1] < h-EPS for p in shape)
                and not any(_overlap(shape, other) for _,other in box_shapes)
                and not any(_overlap(shape, other) for other in existing))
    nominal=[]
    for item in arena["nominal_starts"]:
        require(valid_start(item["pose"],nominal), "$.nominal_starts", "nominal robot footprints overlap obstacles or each other")
        nominal.append(footprint(item["pose"],length,width))
    actual=[]
    for agent in agents:
        rng=random.Random(int.from_bytes(hashlib.sha256(f"{scenario['seed']}/world_generation/{agent['slot']}/start_jitter".encode()).digest(),"big"))
        original=copy.deepcopy(agent["start_pose"])
        for attempt in range(100):
            candidate = dict(original)
            if agent["jitter_xy_m"] or agent["jitter_yaw_rad"]:
                candidate["x_m"] += rng.uniform(-agent["jitter_xy_m"],agent["jitter_xy_m"])
                candidate["y_m"] += rng.uniform(-agent["jitter_xy_m"],agent["jitter_xy_m"])
                candidate["yaw_rad"] += rng.uniform(-agent["jitter_yaw_rad"],agent["jitter_yaw_rad"])
            candidate["yaw_rad"]=(candidate["yaw_rad"]+math.pi)%(2*math.pi)-math.pi
            if valid_start(candidate,actual):
                agent["start_pose"]=candidate
                actual.append(footprint(candidate,length,width))
                break
        else:
            require(False,"$.agents.start_pose",f"unable to place {agent['slot']} without collision after 100 jitter samples")
    return warnings
