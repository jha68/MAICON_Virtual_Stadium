"""Reference layout, navigable passages and actual facility receiver hits."""
from collections import Counter, deque
from importlib.resources import files
import math
from pathlib import Path

import numpy as np
import pytest

from maicon_sim.config.loader import load_scenario
from maicon_sim.core.engine import MatchEngine
from maicon_sim.core.geometry3d import FACE_AXES, laser_contacts, laser_transform, receiver_primitives
from maicon_sim.core.scoring import inventory_from_boxes
from maicon_sim.core.types import FACILITIES, OBJECT_CLASSES, Pose2


@pytest.fixture
def reference():
    return load_scenario('examples/scenario_reference_stadium.yaml')


def test_reference_geometry_and_packaged_assets(reference):
    packaged = load_scenario(Path(str(files('maicon_sim') / 'resources/examples/scenario_reference_stadium.yaml')))
    assert packaged.hashes == reference.hashes
    assert reference.arena['bounds'] == dict(width_m=6.12, height_m=5., wall_height_m=.4)
    boxes = reference.scenario['boxes']
    assert Counter(b['sector_id'] for b in boxes) == {'B-S1': 3, 'B-S2': 2, 'B-S3': 3,
                                                    'R-S1': 3, 'R-S2': 2, 'R-S3': 3, 'CM': 4}
    assert all(b['size_m'] == [.4, .4, .4] for b in boxes)
    for blue in (b for b in boxes if b['box_id'].startswith('B')):
        red = next(b for b in boxes if b['box_id'] == 'R' + blue['box_id'][1:])
        assert blue['pose']['x_m'] + red['pose']['x_m'] == pytest.approx(6.12)
        assert blue['pose']['y_m'] == red['pose']['y_m']
    labels = {a['label'] for a in reference.assets['assets'] if a['kind'] == 'decoy'}
    assert labels == {'urban_tree', 'barrier', 'field_position', 'ruined_building'}
    faces = [f for b in boxes for f in b['faces']]
    assert {f['facility_code'] for f in faces if f['kind'] == 'facility'} == set(FACILITIES)
    assert {f['object_class'].upper() for f in faces if f['kind'] == 'object'} == set(OBJECT_CLASSES)
    assert {a['asset_id'] for a in reference.assets['assets'] if a['kind'] != 'base'} == {f['asset_id'] for f in faces}
    assert {a['label'] for a in reference.assets['assets'] if a['kind'] == 'base'} == {
        'COMMAND_POST', 'MAINTENANCE', 'SUPPLY_DEPOT'}
    inventory = inventory_from_boxes(boxes)
    assert inventory['CM'] == {'MILITARY_TRUCK': 1, 'MORTAR': 2, 'TANK': 3,
                               'MISSILE': 1, 'AMMO_BOX': 2, 'DRUM': 3}
    assert sum(sum(row.values()) for row in inventory.values()) == 26
    # Cropped reference images ship with the wheel, with exactly the same bytes.
    for asset in reference.assets['assets']:
        assert (reference.path.parent / asset['path']).read_bytes() == (packaged.path.parent / asset['path']).read_bytes()


def test_reference_has_40cm_routes_to_every_base_and_sector(reference):
    """Flood a 5 cm grid with a 20 cm radius, including boundary clearance.

    One-centimetre seams within L/bar clusters are construction joints, not
    corridors. All starts and every traversable sector cell must be connected.
    """
    resolution, radius = .05, .2
    w, h = 6.12, 5.
    xs, ys = (np.arange(math.ceil(w/resolution))+.5)*resolution, (np.arange(round(h/resolution))+.5)*resolution
    xx, yy = np.meshgrid(xs, ys)
    free = (xx >= radius) & (xx <= w-radius) & (yy >= radius) & (yy <= h-radius)
    for box in reference.scenario['boxes']:
        x, y = box['pose']['x_m'], box['pose']['y_m']
        free &= ~((abs(xx-x) <= box['size_m'][0]/2+radius) & (abs(yy-y) <= box['size_m'][1]/2+radius))
    def cell(x, y): return (int(x/resolution), int(y/resolution))
    starts = [cell(s['pose']['x_m'], s['pose']['y_m']) for s in reference.arena['nominal_starts']]
    reached, queue = {starts[0]}, deque([starts[0]])
    while queue:
        x, y = queue.popleft()
        for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            p = (x+dx, y+dy)
            if 0 <= p[0] < free.shape[1] and 0 <= p[1] < free.shape[0] and free[p[1], p[0]] and p not in reached:
                reached.add(p)
                queue.append(p)
    assert all(p in reached for p in starts)
    for base in reference.arena['bases']:
        assert cell(*np.mean(base['trigger_segment_xy_m'], axis=0)) in reached
    for sector in reference.arena['sectors']:
        poly = np.array(sector['polygon_xy_m'])
        left, bottom = poly.min(axis=0)
        right, top = poly.max(axis=0)
        cells = np.argwhere(free & (xx >= left) & (xx <= right) & (yy >= bottom) & (yy <= top))
        assert len(cells) > 0
        assert all((int(x), int(y)) in reached for y, x in cells)


def aim_at_facility(engine, code):
    geometry = engine.config.sensors['geometry']
    box = next(b for b in engine.boxes if any(f.get('facility_code') == code for f in b['faces']))
    face = next(f for f in box['faces'] if f.get('facility_code') == code)
    normal = np.array(FACE_AXES[face['side']][0])
    target = next(p for p in receiver_primitives(engine.robots, engine.boxes, geometry) if p.owner == code)
    center = target.center
    robot = engine.robots['B-1']
    pos = center + normal*.75
    robot.pose = Pose2(float(pos[0]), float(pos[1]), math.atan2(-normal[1], -normal[0]))
    lo, hi = -100., 100.
    for _ in range(60):
        mid = (lo+hi)/2
        origin, direction = laser_transform(robot.pose, 0, mid, geometry)
        distance = np.dot(center[:2]-origin[:2], direction[:2]) / np.dot(direction[:2], direction[:2])
        if origin[2]+distance*direction[2] < center[2]: lo = mid
        else: hi = mid
    robot.tilt = robot.target_tilt = (lo+hi)/2
    return robot


def test_patrol_can_leave_all_six_reference_starts(reference):
    """Real LiDAR wall samples must not inflate over a nominal start cell."""
    from maicon_sim.core.geometry3d import canonical_solids
    from maicon_sim.policies.baseline import ParticipantPolicy
    from maicon_sim.sensors.lidar import scan
    engine = MatchEngine(reference)
    solids = canonical_solids(engine.robots, engine.boxes, reference.arena['bounds'], reference.sensors['geometry'])
    for slot, robot in engine.robots.items():
        observation = scan(engine.robots, solids, slot, reference.sensors['lidar'], {}, np.random.default_rng(0))
        policy = ParticipantPolicy(reference.public_map_prior(), {}, slot, 'patrol')
        pose = (robot.pose.x_m, robot.pose.y_m, robot.pose.yaw_rad)
        policy.grid.update_scan(pose, observation)
        goal = policy.waypoints.goal(pose, 0, None)
        assert policy._navigate(pose, 0, goal, False) != (0., 0.), slot


@pytest.mark.parametrize('code', FACILITIES)
def test_each_reference_receiver_requires_real_uninterrupted_two_second_hit(reference, code):
    engine = MatchEngine(reference)
    engine.request('enter_ready')
    for slot in engine.robots: engine.request('ready', slot)
    engine.request('start')
    robot = aim_at_facility(engine, code)
    assert ('B-1', code) in laser_contacts(engine.robots, engine.boxes, reference.arena['bounds'], reference.sensors)
    assert engine.snapshot()['facility_signals'][code] == 'idle'
    engine.request('fire', 'B-1')
    engine.step(100)
    assert engine.snapshot()['facility_signals'][code] == 'receiving'
    # Looking away breaks contact; two partial exposures must not add up.
    tilt = robot.tilt
    robot.tilt = robot.target_tilt = -100.
    engine.step()
    assert engine.snapshot()['facility_signals'][code] == 'idle'
    robot.tilt = robot.target_tilt = tilt
    engine.step(199)
    assert code not in engine.destroyed
    engine.step()
    assert engine.snapshot()['facility_signals'][code] == 'hit'
    assert code in engine.destroyed
    assert len([e for e in engine.journal if e['kind'] == 'facility_destroyed']) == 1
