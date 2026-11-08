"""Measure every 100Hz pose, not only downsampled odometry or final scores."""
import copy
from dataclasses import asdict

import numpy as np
import pytest

from maicon_sim.config.loader import load_scenario
from maicon_sim.core.engine import MatchEngine
from maicon_sim.evaluation.compare import core_event
from maicon_sim.backends.two_d import TwoDBackend
from maicon_sim.backends.bullet.backend import BulletBackend


@pytest.mark.render
def test_T3D_13_D2_P03_all_100hz_poses_and_bullet_scene_follow_same_core():
    config = load_scenario("examples/scenario_smoke_six.yaml")
    config.rules["timing"].update(match_ms=3000, objective_publish_ms=2400, report_ms=300)
    two, three = MatchEngine(config), MatchEngine(copy.deepcopy(config))
    for engine in (two, three):
        engine.request("enter_ready")
        for slot in engine.robots:
            engine.request("ready", slot)
        engine.request("start")
    with TwoDBackend(config) as planar, BulletBackend(config) as spatial:
        for tick in range(330):
            for engine in (two, three):
                if tick % 10 == 0 and engine.phase == "running":
                    engine.request("cmd_vel", "B-1", {"linear_x_mps": .6, "angular_z_rps": .1})
                    engine.request("cmd_vel", "R-1", {"linear_x_mps": .3, "angular_z_rps": -.2})
                engine.step()
            planar.sync_scene(two.snapshot())
            spatial.sync_scene(three.snapshot())
            for slot in two.robots:
                a, b = two.robots[slot], three.robots[slot]
                np.testing.assert_allclose(list(asdict(a.pose).values()), list(asdict(b.pose).values()), atol=1e-9, rtol=0)
                assert (a.hp, a.ammo) == (b.hp, b.ammo)
                chassis = spatial.scene.registry[slot+"/chassis"]
                position, quat = spatial.p.getBasePositionAndOrientation(chassis, physicsClientId=spatial.client)
                np.testing.assert_allclose(position[:2], [b.pose.x_m, b.pose.y_m], atol=1e-9, rtol=0)
                yaw = spatial.p.getEulerFromQuaternion(quat)[2]
                angular_error = (yaw-b.pose.yaw_rad+np.pi) % (2*np.pi)-np.pi
                assert abs(angular_error) <= 1e-9
            assert two.phase == three.phase and two.match_elapsed_ticks == three.match_elapsed_ticks
        assert two.result() == three.result()
        assert [core_event(e) for e in two.journal if e["category"] == "derived"] == [core_event(e) for e in three.journal if e["category"] == "derived"]
