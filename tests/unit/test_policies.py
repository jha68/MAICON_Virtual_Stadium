import asyncio
import math
import time
from copy import deepcopy

import numpy as np
import pytest

from maicon_sim.policies.baseline import GimbalEstimate, ParticipantPolicy, fixture_interpret_order
from maicon_sim.policies.inference import LatestInference
from maicon_sim.policies.planning import FREE, OCCUPIED, UNKNOWN, OccupancyGrid, follow_waypoint
from maicon_sim.policies.tracking import ObjectTracker


def prior():
    return {"bounds": {"width_m": 3., "height_m": 3.}, "nominal_starts": [{"slot": "B-1", "pose": {"x_m": .4, "y_m": 1.5, "yaw_rad": 0.}}],
            "sectors": [{"sector_id": "R-S1", "polygon_xy_m": [[1., 0.], [3., 0.], [3., 3.], [1., 3.]]}],
            "bases": [{"code": "RED_MAINTENANCE", "camp": "RED", "polygon_xy_m": [[2.4, 1.], [2.8, 1.], [2.8, 2.], [2.4, 2.]]}]}


def probs(label):
    return {k: float(k == label) for k in ("military_truck", "mortar", "tank", "missile", "ammo_box", "drum")}


def test_GEO_012_repeated_surface_is_one_track():
    tracker = ObjectTracker()
    for tick in range(100):
        tracker.observe((1., 2.), math.pi, probs("tank"), tick, "R-S1")
    assert len(tracker.tracks) == 1
    assert tracker.report() == {"sectors": [{"sector": "R-S1", "objects": [{"type": "TANK", "count": 1}]}]}


def test_GEO_013_same_image_different_positions_or_normals_stays_separate():
    tracker = ObjectTracker()
    tracker.observe((1., 2.), 0., probs("tank"), 0, "R-S1")
    tracker.observe((1.4, 2.), 0., probs("tank"), 0, "R-S1")
    tracker.observe((1., 2.), math.pi, probs("tank"), 0, "R-S1")
    assert tracker.report()["sectors"][0]["objects"] == [{"type": "TANK", "count": 3}]
    assert {t.track_id for t in tracker.tracks} == {1, 2, 3}


def test_GEO_014_evidence_corrects_wrong_class_and_retracts_false_positive():
    tracker = ObjectTracker()
    identifier = tracker.observe((1., 2.), 0., probs("drum"), 0, "R-S1")
    for tick in range(1, 10):
        tracker.observe((1., 2.), 0., probs("tank"), tick, "R-S1")
    assert tracker.tracks[0].label == "tank"
    tracker.contradict(identifier)
    tracker.contradict(identifier)
    tracker.contradict(identifier)
    assert tracker.report() == {"sectors": []}


def test_GEO_015_unknown_and_observed_empty_sectors_are_distinct():
    tracker = ObjectTracker()
    tracker.mark_coverage("R-S1")
    assert tracker.coverage["R-S1"] == "partial"
    assert tracker.report()["sectors"] == []
    tracker.mark_coverage("R-S1", complete=True)
    assert tracker.report() == {"sectors": [{"sector": "R-S1", "objects": []}]}
    assert "R-S2" not in tracker.coverage


def test_mapper_marks_free_and_hit_separately_and_null_is_unknown():
    grid = OccupancyGrid(3., 3.)
    grid.update_scan((1., 1., 0.), {"ranges_m": [.5, None], "angle_min_rad": 0., "angle_increment_rad": math.pi / 2, "range_max_m": 2.})
    assert grid.cells[20, 25] == FREE
    assert grid.cells[20, 30] == OCCUPIED
    assert grid.cells[30, 20] == UNKNOWN


def test_astar_cannot_cut_diagonal_corners():
    grid = OccupancyGrid(3., 3.)
    grid.cells[:] = FREE
    # Full-height barrier except a diagonal crack cannot be crossed by footprint.
    grid.cells[:, 30] = OCCUPIED
    assert grid.astar((20, 20), (40, 20)) == []
    grid.cells[15:30, 30] = FREE
    grid.revision += 1
    path = grid.astar((20, 20), (40, 20))
    assert path
    blocked = grid.inflated()
    for a, b in zip(path, path[1:]):
        if a[0] != b[0] and a[1] != b[1]:
            assert not blocked[b[1], a[0]] and not blocked[a[1], b[0]]


def test_astar_unknown_is_costlier_than_observed_free():
    grid = OccupancyGrid(3., 3.)
    grid.cells[18:23, 8:53] = FREE
    path = grid.astar((10, 20), (50, 20))
    assert path
    assert all(grid.cells[y, x] == FREE for x, y in path)


def test_follow_yaw_and_low_speed_contract():
    assert follow_waypoint((1., 1., math.pi), (2., 1.))[0] == 0.
    v, w = follow_waypoint((1., 1., 0.), (2., 1.))
    assert v == .15 and w == 0.
    assert follow_waypoint((1., 1., 0.), (1.02, 1.)) == (0., 0.)


def test_gimbal_no_true_feedback_settle_interval_and_cancel():
    gimbal = GimbalEstimate()
    gimbal.accepted(20., 20., 10., 0)
    assert not gimbal.settled(109)
    assert gimbal.settled(111)
    gimbal.update(100)
    assert gimbal.pan == 20. and gimbal.tilt == 20.
    gimbal.cancel(120)
    assert not gimbal.settled(100000)


def test_world_pose_is_nominal_plus_local_odom():
    p = prior()
    p["nominal_starts"][0]["pose"]["yaw_rad"] = math.pi / 2
    policy = ParticipantPolicy(p, {}, "B-1")
    estimate = policy.world_estimate({"local_pose": {"x_m": .2, "y_m": 0., "yaw_rad": .1}})
    assert estimate == pytest.approx((.4, 1.7, math.pi / 2 + .1))


def test_text_stub_reads_only_natural_command_not_hidden_m1():
    result = fixture_interpret_order("상대 레이더시설을 타격하라. 상대 첫째 탐색구역과 중앙을 탐색하고 상대 군수보급소를 후속 거점으로 설정하라.", "B-1")
    assert result == {"target": "RED_RADAR", "search_sectors": ["CM", "R-S1"], "base": "RED_SUPPLY_DEPOT"}
    assert fixture_interpret_order("알 수 없는 명령", "B-1") == {}


def test_idle_sends_no_mission_reports_even_reporting():
    policy = ParticipantPolicy(prior(), {}, "B-1", "idle")
    assert policy.compute({}, {"phase": "reporting"}).reports == {}


def test_baseline_uses_actual_m5_and_fallback_m6_not_m1_base():
    policy = ParticipantPolicy(prior(), {}, "B-1")
    obs = {"odom": {"sequence": 1, "captured_tick": 100, "local_pose": {"x_m": 0., "y_m": 0., "yaw_rad": 0.}}, "match": {"cmd": "start"}}
    decision = policy.compute(obs, {"phase": "running"}, {"accepted": True, "order": {"tactical_command": "상대 레이더시설과 군수보급소"}}, {"accepted": True, "order": {"objective": "RED_MAINTENANCE"}})
    assert policy.target_objective == "RED_MAINTENANCE"
    assert decision.reports["m1"]["base"] == "RED_SUPPLY_DEPOT"
    report = policy.compute(obs, {"phase": "reporting"})
    assert report.velocity == (0., 0.)
    assert report.reports["m6"] == {"ranking": ["R-1", "R-2", "R-3"]}
    assert "fallback" in report.diagnostics["rank_confidence"]
    policy.acknowledge_report("m6", {"accepted": True, "received": {"ranking": ["R-1", "R-2", "R-3"]}})
    assert policy.compute(obs, {"phase": "reporting"}).reports == {}


def test_pause_does_not_send_m6_and_blocks_drive():
    policy = ParticipantPolicy(prior(), {}, "B-1")
    decision = policy.compute({"match": {"cmd": "pause"}}, {"phase": "running"})
    assert not decision.reports and decision.velocity == (0., 0.)


def test_PERF_005_inference_latest_queue_bounded_and_timestamps_preserved():
    def slow(frame):
        time.sleep(.03)
        return frame
    worker = LatestInference(slow)
    try:
        for tick in range(100):
            worker.submit({"captured_tick": tick})
        assert worker.queue.qsize() <= 1
        time.sleep(.1)
        assert worker.latest["captured_tick"] == 99
        assert worker.dropped >= 98
    finally:
        worker.close()


def test_E2E_008_slow_policy_does_not_block_heartbeat_or_step():
    from maicon_sim.policies.controller import TeamController
    class FakePort:
        def __init__(self):
            self.commands = []
        async def command_velocity(self, v, w):
            self.commands.append(time.monotonic())
            return {"accepted": True}
        async def close(self):
            pass
    async def run():
        port = FakePort()
        controller = TeamController(port, "B-1")
        controller.policy = ParticipantPolicy(prior(), {}, "B-1")
        original = controller.policy.compute
        def slow(*args):
            time.sleep(.35)
            return original(*args)
        controller.policy.compute = slow
        controller.me = {"phase": "running"}
        from maicon_sim.sdk.report_worker import ReportWorker
        controller.report_workers = {k: ReportWorker(port, k) for k in ("m1", "m3", "m6")}
        heartbeat = asyncio.create_task(controller._heartbeat())
        controller.tasks = [heartbeat]
        start = time.monotonic()
        await controller.step()
        assert time.monotonic() - start < .1
        await asyncio.sleep(.47)
        await controller.close()
        assert len(port.commands) >= 5
        assert max(b - a for a, b in zip(port.commands, port.commands[1:])) < .2
    asyncio.run(run())


def test_controller_end_to_end_inprocess_public_port_ready_reports_and_stop(tmp_path):
    from pathlib import Path
    from maicon_sim.config.loader import load_scenario
    from maicon_sim.core.engine import MatchEngine
    from maicon_sim.sdk.in_process_port import InProcessPort
    from maicon_sim.sensors.gateway import SensorGateway
    from maicon_sim.policies.controller import TeamController
    config = load_scenario(Path(__file__).resolve().parents[2] / "examples/scenario_smoke_six.yaml")
    config.rules["timing"].update(match_ms=1200, objective_publish_ms=1000, report_ms=1000)
    engine = MatchEngine(config)
    gateway = SensorGateway(config)
    engine.request("enter_ready", None)
    gateway.update(engine)
    async def run():
        controller = TeamController(InProcessPort(engine, "B-1", gateway), "B-1", "baseline", output=tmp_path)
        await controller.initialize()
        assert engine.robots["B-1"].ready
        engine.request("start", None)
        controller.start()
        try:
            for _ in range(300):
                engine.step()
                gateway.update(engine)
                await asyncio.sleep(.008)
                if engine.phase == "finished":
                    break
            await asyncio.wait_for(controller.done.wait(), 1.)
            assert engine.phase == "finished"
            assert engine.reports["B-1"]["m1"] is not None
            assert engine.reports["B-1"]["m6"] is not None
            assert controller.report_workers["m1"].acknowledged_revision is not None
            assert len(controller.control_times) > 3
        finally:
            await controller.close()
            gateway.close()
        # Logs contain observations/own commands, no scenario secrets or private IDs.
        text = (tmp_path / "participant.jsonl").read_text()
        assert "SIMB0001" not in text and "box_R1" not in text
    asyncio.run(run())


@pytest.mark.render
def test_RGB_baseline_uses_pixels_without_semantic_oracle():
    from maicon_sim.backends.bullet.asset_builder import synthetic_image
    policy = ParticipantPolicy(prior(), {}, "B-1")
    bgr = np.asarray(synthetic_image("tank").convert("RGB"))[..., ::-1].copy()
    observations = {
        "odom": {"sequence": 1, "captured_tick": 100, "local_pose": {"x_m": 0., "y_m": 0., "yaw_rad": 0.}},
        "match": {"cmd": "start"},
        "scan": {"sequence": 1, "captured_tick": 100, "ranges_m": [2.] * 360, "angle_min_rad": -math.pi, "angle_increment_rad": 2 * math.pi / 360, "range_max_m": 8.},
        "rgb": {"data": bgr, "sequence": 1, "captured_tick": 100, "received_tick": 100},
    }
    decision = policy.compute(observations, {"phase": "running"})
    assert "RGB synthetic_template" in decision.diagnostics["perception"]
    assert len(policy.tracker.tracks) == 1
    assert policy.tracker.tracks[0].label == "tank"
    assert decision.reports["m3"]["sectors"][0]["objects"] == [{"type": "TANK", "count": 1}]
    assert "semantic" not in observations
