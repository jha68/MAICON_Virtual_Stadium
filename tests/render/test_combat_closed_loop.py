"""A real rendered own camera drives gimbal/fire; engine truth is evaluation only."""
from copy import deepcopy
import math

import pytest

from maicon_sim.backends.bullet.backend import BulletBackend
from maicon_sim.config.loader import load_scenario
from maicon_sim.core.engine import MatchEngine
from maicon_sim.perception.combat import CombatVisionDetector
from maicon_sim.policies.baseline import GimbalEstimate
from maicon_sim.policies.combat import CombatPolicy


pytestmark = pytest.mark.render


def test_real_rgb_facility_tracking_fire_causes_actual_engine_destruction():
    config = load_scenario("examples/scenario_smoke_six.yaml")
    # Evaluator arranges a visible target. The participant gets only its public
    # nominal start, camera calibration, actual RGB and own state.
    start = {"x_m": 5.4, "y_m": 4.2, "yaw_rad": math.pi}
    next(a for a in config.scenario["agents"] if a["slot"] == "B-1")["start_pose"] = deepcopy(start)
    next(a for a in config.arena["nominal_starts"] if a["slot"] == "B-1")["pose"] = deepcopy(start)
    engine = MatchEngine(config)
    engine.request("enter_ready")
    engine.request("ready", "B-1")
    engine.request("start")
    calibration = {"front_camera": config.sensors["front_camera"], "laser_offset_camera_m": [0., 0., .02]}
    detector = CombatVisionDetector(calibration)
    policy = CombatPolicy("B-1", {"sectors": deepcopy(config.arena["sectors"])})
    estimate = GimbalEstimate()
    fired = []
    commands = []
    with BulletBackend(config) as backend:
        for tick in range(600):
            if tick % 10 == 0:
                backend.sync_scene(engine.snapshot())
                frame = backend.capture_rgb("B-1/front", tick)
                visual = detector.process(frame)
                estimate.update(tick)
                observations = {"combat": visual, "state": {"hp": 4, "captured_tick": tick, "received_tick": tick}}
                decision = policy.update(observations, calibration, target="RED_RADAR",
                                         gimbal={"pan": estimate.pan, "tilt": estimate.tilt},
                                         pose=(start["x_m"], start["y_m"], start["yaw_rad"]))
                commands.append(decision.state)
                if decision.gimbal:
                    pan, tilt, speed, acc = decision.gimbal
                    response = engine.request("gimbal", "B-1", {"pan": pan, "tilt": tilt, "speed": speed, "acc": acc})
                    estimate.accepted(pan, tilt, speed, tick)
                    policy.acknowledge_gimbal(decision.gimbal, response, tick)
                if decision.fire:
                    response = engine.request("fire", "B-1")
                    policy.acknowledge_fire(response, tick)
                    fired.append(response["message"])
            engine.step()
            if "RED_RADAR" in engine.destroyed_facilities:
                break
    assert fired == ["fired"], commands
    assert "RED_RADAR" in engine.destroyed_facilities, commands
    assert engine.robots["B-1"].ammo == 7


def test_real_rgb_tracks_a_moving_identified_opponent_and_causes_engine_hit():
    config = load_scenario("examples/scenario_smoke_six.yaml")
    starts = {"B-1": {"x_m": 3.6, "y_m": 3.4, "yaw_rad": 0.},
              "R-1": {"x_m": 4.8, "y_m": 3.4, "yaw_rad": math.pi}}
    for slot, start in starts.items():
        next(a for a in config.scenario["agents"] if a["slot"] == slot)["start_pose"] = deepcopy(start)
    engine = MatchEngine(config)
    engine.request("enter_ready")
    for slot in starts:
        engine.request("ready", slot)
    engine.request("start")
    calibration = {"front_camera": config.sensors["front_camera"], "laser_offset_camera_m": [0., 0., .02]}
    detector = CombatVisionDetector(calibration)
    policy, estimate = CombatPolicy("B-1"), GimbalEstimate()
    fired, diagnostics = [], []
    with BulletBackend(config) as backend:
        for tick in range(700):
            if tick % 10 == 0:
                # The opposing process supplies a valid slow drive heartbeat.
                engine.request("cmd_vel", "R-1", {"linear_x_mps": .025, "angular_z_rps": 0.})
                backend.sync_scene(engine.snapshot())
                visual = detector.process(backend.capture_rgb("B-1/front", tick))
                estimate.update(tick)
                result = policy.update({"combat": visual, "state": {"hp": 4, "captured_tick": tick}}, calibration,
                                       gimbal={"pan": estimate.pan, "tilt": estimate.tilt})
                diagnostics.append((result.state, result.diagnostics))
                if result.gimbal:
                    pan, tilt, speed, acc = result.gimbal
                    response = engine.request("gimbal", "B-1", {"pan": pan, "tilt": tilt, "speed": speed, "acc": acc})
                    estimate.accepted(pan, tilt, speed, tick)
                    policy.acknowledge_gimbal(result.gimbal, response, tick)
                if result.fire:
                    response = engine.request("fire", "B-1")
                    policy.acknowledge_fire(response, tick)
                    fired.append(response["message"])
            engine.step()
            if engine.robots["R-1"].hp < 4:
                break
    assert fired == ["fired"], diagnostics
    assert engine.robots["R-1"].hp == 3, diagnostics
    assert engine.robots["R-1"].pose.x_m < starts["R-1"]["x_m"]-.01


def test_full_participant_policy_and_dispatcher_destroy_facility_from_public_rgb():
    from maicon_sim.evaluation.runner import apply_decision, calibration, public_observations
    from maicon_sim.policies.baseline import ParticipantPolicy
    from maicon_sim.sensors.gateway import SensorGateway
    config = load_scenario("examples/scenario_smoke_six.yaml")
    start = {"x_m": 5.4, "y_m": 4.2, "yaw_rad": math.pi}
    next(a for a in config.scenario["agents"] if a["slot"] == "B-1")["start_pose"] = deepcopy(start)
    next(a for a in config.arena["nominal_starts"] if a["slot"] == "B-1")["pose"] = deepcopy(start)
    engine = MatchEngine(config)
    engine.request("enter_ready")
    engine.request("ready", "B-1")
    engine.request("start")
    # The policy receives only public arena geometry and its own nominal start.
    public_map = {k: deepcopy(config.arena[k]) for k in ("bounds", "sectors", "bases", "nominal_starts")}
    policy = ParticipantPolicy(public_map, calibration(config), "B-1", "baseline")
    policy.m1_interpretation = {"target": "RED_RADAR"}
    decisions = []
    with BulletBackend(config) as backend:
        gateway = SensorGateway(config, backend)
        gateway.camera_slots = {"B-1"}
        for tick in range(500):
            gateway.update(engine)
            if tick % 10 == 0:
                observations = public_observations(gateway, "B-1")
                assert "semantic" not in observations
                decision = policy.compute(observations, engine.request("me", "B-1"), engine.request("order", "B-1"))
                decisions.append(decision)
                apply_decision(engine, "B-1", decision, policy)
            engine.step()
            if "RED_RADAR" in engine.destroyed_facilities:
                break
    assert "RED_RADAR" in engine.destroyed_facilities, [d.diagnostics for d in decisions]
    assert sum(d.fire for d in decisions) == 1
    assert engine.robots["B-1"].ammo == 7
