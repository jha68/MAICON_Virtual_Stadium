"""Actuation RPCs may complete after a new match has replaced the policy."""
import asyncio

import pytest

from maicon_sim.policies.baseline import PolicyDecision
from maicon_sim.policies.controller import TeamController


class Worker:
    acknowledged_revision = None

    def __init__(self):
        self.submitted = []

    def update(self, value, **kwargs):
        self.submitted.append((value, kwargs))


class Policy:
    def __init__(self, decision=None):
        self.decision = decision or PolicyDecision()
        self.gimbal_acks = []
        self.fire_acks = []

    def compute(self, *args):
        return self.decision

    @staticmethod
    def observation_tick(observations):
        return 5

    def acknowledge_gimbal(self, *args):
        self.gimbal_acks.append(args)

    def acknowledge_fire(self, *args):
        self.fire_acks.append(args)


@pytest.mark.parametrize("actuation", ["gimbal", "fire"])
def test_old_rpc_completion_cannot_ack_or_report_into_new_match(actuation):
    class Port:
        def __init__(self):
            self.entered = asyncio.Event()
            self.release = asyncio.Event()

        async def command_gimbal(self, *command):
            self.entered.set()
            await self.release.wait()
            return {"message": "ok"}

        async def fire(self):
            self.entered.set()
            await self.release.wait()
            return {"message": "fired", "left_ms": 10000}

    async def run():
        port = Port()
        controller = TeamController(port, "B-1")
        controller.me = {"phase": "running"}
        controller.observations = {"match": {"cmd": "start"}}
        controller._check_motion_sensors = lambda: True
        controller.session_identity = {"match_id": "old-match"}
        old_policy = Policy(PolicyDecision(
            gimbal=(10., 0., 30., 20.) if actuation == "gimbal" else None,
            fire=actuation == "fire", reports={"m1": {"target": "RED_RADAR"}}))
        controller.policy = old_policy
        controller.report_workers = {kind: Worker() for kind in ("m1", "m3", "m6")}
        task = asyncio.create_task(controller._compute_step())
        try:
            await asyncio.wait_for(port.entered.wait(), 2.)
            # This is the commit point of _initialize_session: everything after
            # it belongs to the new match, while the prior RPC is still pending.
            controller._generation += 1
            controller._motion_generation += 1
            controller.session_identity = {"match_id": "new-match"}
            controller.policy = Policy()
            new_workers = {kind: Worker() for kind in ("m1", "m3", "m6")}
            controller.report_workers = new_workers
            port.release.set()
            await asyncio.wait_for(task, 2.)
            assert controller.policy.gimbal_acks == []
            assert controller.policy.fire_acks == []
            assert all(not worker.submitted for worker in new_workers.values())
        finally:
            port.release.set()
            await task

    asyncio.run(run())


@pytest.mark.parametrize("phase,cmd", [("running", "pause"), ("reporting", "report"), ("finished", "stop")])
def test_phase_change_during_gimbal_rpc_prevents_following_fire(phase, cmd):
    class Port:
        def __init__(self):
            self.entered = asyncio.Event()
            self.release = asyncio.Event()
            self.fire_calls = 0

        async def command_gimbal(self, *command):
            self.entered.set()
            await self.release.wait()
            return {"message": "ok"}

        async def fire(self):
            self.fire_calls += 1
            return {"message": "fired", "left_ms": 10000}

    async def run():
        port = Port()
        controller = TeamController(port, "B-1")
        controller.me = {"phase": "running"}
        controller.observations = {"match": {"cmd": "start"}}
        controller._check_motion_sensors = lambda: True
        controller.policy = Policy(PolicyDecision(gimbal=(0., 0., 30., 20.), fire=True))
        controller.report_workers = {kind: Worker() for kind in ("m1", "m3", "m6")}
        task = asyncio.create_task(controller._compute_step())
        try:
            await asyncio.wait_for(port.entered.wait(), 2.)
            controller.me = {"phase": phase}
            controller.observations = {"match": {"cmd": cmd}}
            port.release.set()
            await asyncio.wait_for(task, 2.)
            assert port.fire_calls == 0
        finally:
            port.release.set()
            await task

    asyncio.run(run())
