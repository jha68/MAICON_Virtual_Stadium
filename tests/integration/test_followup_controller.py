"""Controller dispatches public combat intent once and cancels unsent intent."""
import asyncio
from types import SimpleNamespace

from maicon_sim.policies.baseline import PolicyDecision
from maicon_sim.policies.combat import CombatPolicy
from maicon_sim.policies.controller import TeamController


def frames(tick):
    stamp = {"captured_tick": tick, "received_tick": tick, "sequence": tick}
    return {"state": {**stamp, "hp": 4, "hp_max": 4, "battery_pct": 100.},
            "match": {**stamp, "mode": "mission", "cmd": "start"},
            "odom": {**stamp, "local_pose": {"x_m": 0., "y_m": 0., "yaw_rad": 0.}},
            "scan": {**stamp, "ranges_m": [1.] * 36},
            "semantic": {**stamp, "detections": [{"kind": "facility", "confidence": 1.,
                "class_probs": {"RADAR": 1.}, "camp_readout": {"camp": "RED", "confidence": 1.},
                "aim_point_px": [319.5, 233.1], "bbox_xyxy_px": [260., 190., 380., 310.], "range_m": 1.}]}}


class Port:
    def __init__(self):
        self.fires = 0

    async def fire(self):
        self.fires += 1
        raise asyncio.TimeoutError()


class Policy:
    def __init__(self):
        self.combat = CombatPolicy("B-1")

    @staticmethod
    def observation_tick(observations):
        return observations["semantic"]["captured_tick"]

    def compute(self, observations, *args):
        action = self.combat.update(observations, {"front_camera": {}}, target="RED_RADAR")
        return PolicyDecision(gimbal=action.gimbal, fire=action.fire)

    def acknowledge_fire(self, response, tick):
        self.combat.acknowledge_fire(response, tick)


def test_actual_controller_never_retries_unknown_fire_outcome():
    async def run():
        port = Port()
        controller = TeamController(port, "B-1")
        controller.policy = Policy()
        controller.me = {"phase": "running"}
        controller.report_workers = {kind: SimpleNamespace(acknowledged_revision=None) for kind in ("m1", "m3", "m6")}
        for tick in (0, 20, 100, 1100):
            controller.observations = frames(tick)
            controller._observe_sensor_progress(controller.observations)
            await controller._compute_step()
        assert port.fires == 1
        assert controller.policy.combat.unknown_outcome
        assert any(error["source"] == "fire" for error in controller.errors)
    asyncio.run(run())


def test_motion_guard_discards_known_unsent_fire_and_allows_fresh_attempt():
    async def run():
        port = Port()
        controller = TeamController(port, "B-1")
        controller.policy = Policy()
        controller.me = {"phase": "running"}
        controller.report_workers = {kind: SimpleNamespace(acknowledged_revision=None) for kind in ("m1", "m3", "m6")}
        controller.observations = frames(0)
        controller._observe_sensor_progress(controller.observations)
        await controller._compute_step()
        # The policy sees a settled target, but the sensor deadline already
        # expired. It must not leave a pending request that was never dispatched.
        controller.observations = frames(20)
        controller._sensor_seen_at.clear()
        await controller._compute_step()
        assert port.fires == 0
        assert not controller.policy.combat.pending_fire
        assert not controller.policy.combat.unknown_outcome
        for tick in (40, 60):
            controller.observations = frames(tick)
            controller._observe_sensor_progress(controller.observations)
            await controller._compute_step()
        assert port.fires == 1
    asyncio.run(run())
