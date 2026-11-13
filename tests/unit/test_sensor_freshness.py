"""Loss of observations must not be hidden by a healthy command heartbeat."""
import asyncio
import threading
import time
from types import SimpleNamespace

import numpy as np
import pytest

from maicon_sim.policies import controller as controller_module
from maicon_sim.policies.baseline import PolicyDecision
from maicon_sim.policies.controller import TeamController


def frames(tick=0):
    stamp = {"captured_tick": tick, "received_tick": tick, "sequence": tick}
    return {
        "state": {**stamp, "hp": 4, "hp_max": 4, "battery_pct": 100.},
        "match": {**stamp, "mode": "mission", "cmd": "start"},
        "odom": {**stamp, "local_pose": {"x_m": 0., "y_m": 0., "yaw_rad": 0.}},
        "scan": {**stamp, "ranges_m": [2.] * 36},
    }


class Port:
    def __init__(self):
        self.commands = []
        self.gimbals = []

    async def command_velocity(self, v, w):
        self.commands.append((time.monotonic(), v, w))

    async def command_gimbal(self, *command):
        self.gimbals.append(command)
        return {"message": "ok"}


class Policy:
    def __init__(self, compute=None):
        self.calibration = {}
        self.compute = compute or (lambda *args: PolicyDecision(velocity=(.2, 0.)))

    @staticmethod
    def observation_tick(observations):
        return observations["scan"]["captured_tick"]


def configured(port, **kwargs):
    c = TeamController(port, "B-1", **kwargs)
    c.policy = Policy()
    c.me = {"phase": "running"}
    c.observations = frames()
    c._observe_sensor_progress(c.observations)
    c._check_motion_sensors()
    c.decision = PolicyDecision(velocity=(.2, 0.))
    c.report_workers = {k: SimpleNamespace(acknowledged_revision=None, update=lambda *a, **kw: None)
                        for k in ("m1", "m3", "m6")}
    return c


@pytest.mark.parametrize("failure", ["exception", "cached", "missing"])
def test_failed_or_frozen_observations_stop_while_heartbeat_remains_live(failure):
    class DropoutPort(Port):
        async def latest_observations(self):
            if failure == "exception":
                raise OSError("sensor transport unavailable")
            return frames() if failure == "cached" else {}

    async def run():
        port = DropoutPort()
        c = configured(port, sensor_timeout_s=.1)
        tasks = [asyncio.create_task(c._heartbeat())]
        try:
            # Establish healthy driving before inducing the dropout. An empty
            # match snapshot may correctly stop immediately, before its TTL.
            await asyncio.sleep(0)
            assert port.commands[0][1:] == (.2, 0.)
            tasks.append(asyncio.create_task(c._poll_observations()))
            await asyncio.sleep(.36)
            assert len(port.commands) >= 3
            assert port.commands[-1][1:] == (0., 0.)
            assert c.decision.velocity == (0., 0.)
            if failure == "exception":
                assert any(e["source"] == "observations" for e in c.errors)
        finally:
            c.closed = True
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    asyncio.run(run())


def test_each_channel_expires_and_only_source_progress_can_refresh_it(monkeypatch):
    clock = [0.]
    monkeypatch.setattr(controller_module, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    c = configured(Port())
    c._observe_sensor_progress(frames(10))
    # Re-stamping delivery or incrementing sequence on the same capture is not
    # evidence of a new scan; other channels continue normally.
    clock[0] = .51
    current = frames(51)
    current["scan"] = {**frames(10)["scan"], "received_tick": 51, "sequence": 51}
    c._observe_sensor_progress(current)
    assert c._stale_sensors() == ["scan"]
    assert not c._check_motion_sensors()
    assert c.decision.velocity == (0., 0.)
    # Late frames cannot bring the motion guard back to life.
    c._observe_sensor_progress({**current, "scan": {**current["scan"], "captured_tick": 9}})
    assert c._stale_sensors() == ["scan"]
    c._observe_sensor_progress(frames(52))
    assert c._check_motion_sensors()
    assert c.decision.velocity == (0., 0.)  # never replay the old command
    c.observations = frames(52)
    asyncio.run(c._compute_step())
    assert c.decision.velocity == (.2, 0.)


@pytest.mark.parametrize("channel", ["semantic", "rgb"])
def test_camera_dropout_blocks_vision_but_preserves_lidar_navigation(monkeypatch, channel):
    clock = [0.]
    monkeypatch.setattr(controller_module, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    c = configured(Port())
    c.session_identity = {"capabilities": {channel: True}}
    camera = {"captured_tick": 0, "sequence": 1}
    if channel == "rgb":
        camera["data"] = np.zeros((480, 640, 3), dtype=np.uint8)
    else:
        camera["detections"] = []
    c._observe_sensor_progress({**frames(), channel: camera})
    assert c._check_motion_sensors()
    assert c._check_vision_sensors()
    c.policy = Policy(lambda *args: PolicyDecision(velocity=(.2, 0.), gimbal=(10., 0., 30., 20.), fire=True))
    clock[0] = 1.01
    c._observe_sensor_progress({**frames(101), channel: camera})
    c.observations = frames(101)
    assert c._stale_sensors() == [channel]
    assert c._check_motion_sensors()
    assert not c._check_vision_sensors()
    asyncio.run(c._compute_step())
    assert c.decision.velocity == (.2, 0.)
    assert c.decision.gimbal is None and not c.decision.fire
    assert c.decision.diagnostics['stale_sensors'] == [channel]
    assert 'vision_blocked' in c.decision.diagnostics
    assert c.port.gimbals == []
    c._observe_sensor_progress({**frames(102), channel: {**camera, "captured_tick": 102}})
    assert c._check_motion_sensors()
    assert c._check_vision_sensors()


def test_camera_dropout_and_recovery_invalidates_inflight_aim_without_stopping_drive(monkeypatch):
    clock = [0.]
    monkeypatch.setattr(controller_module, 'time', SimpleNamespace(monotonic=lambda: clock[0]))
    entered, release = threading.Event(), threading.Event()
    def delayed(*args):
        entered.set()
        assert release.wait(2.)
        return PolicyDecision(velocity=(.2, 0.), gimbal=(10., 0., 30., 20.), fire=True)

    async def run():
        c = configured(Port())
        c.session_identity = {'capabilities': {'semantic': True}}
        camera = {'captured_tick': 0, 'detections': []}
        c._observe_sensor_progress({**frames(), 'semantic': camera})
        c.policy = Policy(delayed)
        task = asyncio.create_task(c._compute_step())
        try:
            assert await asyncio.to_thread(entered.wait, 2.)
            clock[0] = 1.01
            c.observations = frames(101)
            c._observe_sensor_progress(c.observations)
            assert c._check_motion_sensors()
            assert not c._check_vision_sensors()
            c._observe_sensor_progress({**frames(102), 'semantic': {**camera, 'captured_tick': 102}})
            assert c._check_vision_sensors()
            release.set()
            await task
            assert c.decision.velocity == (.2, 0.)
            assert not c.decision.fire and c.decision.gimbal is None
            assert c.port.gimbals == []
        finally:
            release.set()
            await task
    asyncio.run(run())


def test_low_rate_state_and_match_have_three_period_grace(monkeypatch):
    clock = [0.]
    monkeypatch.setattr(controller_module, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    c = configured(Port())
    clock[0] = 1.4
    current = frames(140)
    current["state"], current["match"] = frames()["state"], frames()["match"]
    c._observe_sensor_progress(current)
    assert c._check_motion_sensors()
    clock[0] = 1.51
    c._observe_sensor_progress({**frames(151), "state": current["state"], "match": current["match"]})
    assert set(c._stale_sensors()) == {"state", "match"}


def test_inflight_old_plan_cannot_restart_motion_after_dropout_and_recovery(monkeypatch):
    clock = [0.]
    monkeypatch.setattr(controller_module, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    entered, release = threading.Event(), threading.Event()

    def delayed(*args):
        entered.set()
        assert release.wait(2.)
        return PolicyDecision(velocity=(.2, 0.), gimbal=(10., 0., 30., 20.), reports={"m1": {"target": "RED_RADAR"}})

    async def run():
        port = Port()
        c = configured(port)
        c.policy = Policy(delayed)
        reports = []
        c.report_workers["m1"].update = lambda payload, **kwargs: reports.append(payload)
        task = asyncio.create_task(c._compute_step())
        try:
            assert await asyncio.to_thread(entered.wait, 2.)
            clock[0] = .51
            assert not c._check_motion_sensors()
            c.observations = frames(51)
            c._observe_sensor_progress(c.observations)
            assert c._check_motion_sensors()
            release.set()
            await task
            assert c.decision.velocity == (0., 0.)
            assert port.gimbals == []
            assert reports == [{"target": "RED_RADAR"}]
        finally:
            release.set()
            await task

    asyncio.run(run())


def test_reporting_still_submits_m6_with_expired_sensors(monkeypatch):
    clock = [0.]
    monkeypatch.setattr(controller_module, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    c = configured(Port())
    c.me = {"phase": "reporting"}
    c.policy = Policy(lambda *args: PolicyDecision(reports={"m6": {"ranking": ["R-1", "R-2", "R-3"]}}))
    submitted = []
    c.report_workers["m6"].update = lambda payload, **kwargs: submitted.append(payload)
    clock[0] = 2.
    asyncio.run(c._compute_step())
    assert submitted == [{"ranking": ["R-1", "R-2", "R-3"]}]


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf")])
def test_sensor_timeout_must_be_positive_and_finite(value):
    with pytest.raises(ValueError, match="sensor_timeout_s"):
        TeamController(Port(), "B-1", sensor_timeout_s=value)
