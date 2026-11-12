"""Mission admission and rehearsal SDK combinations from the participant guide."""
import asyncio

import httpx
import pytest

from maicon_sim.config.loader import load_scenario
from maicon_sim.core.engine import MatchEngine
from maicon_sim.sdk.http_port import HTTPPort
from maicon_sim.server.app import create_apps
from maicon_sim.server.runtime import EngineRuntime


pytestmark = pytest.mark.contract
EXCLUDED = {"accepted": False, "reason": "이 경기에 편성되지 않은 팀입니다"}


def engine():
    config = load_scenario("examples/scenario_smoke_six.yaml")
    # Shorten only this fixture, keeping the real publication/deadline path.
    config.rules["timing"].update(objective_publish_ms=20, match_ms=10000)
    return MatchEngine(config)


def start(match, slots):
    match.request("enter_ready")
    for slot in slots:
        match.request("ready", slot)
    match.request("start")


def test_excluded_team_cannot_read_published_missions_after_start():
    match = engine()
    start(match, ["B-2"])
    match.step(2)
    assert not match.robots["B-1"].admitted
    for kind in ("order", "target"):
        assert match.request(kind, "B-1") == EXCLUDED
        assert match.request(kind, "B-2")["accepted"]
    match.request("finish")
    for kind in ("order", "target"):
        assert match.request(kind, "B-1") == EXCLUDED
    match.request("stop")
    for kind in ("order", "target"):
        assert match.request(kind, "B-1") == EXCLUDED


def test_start_failure_does_not_remove_admitted_team_mission_access():
    match = engine()
    start(match, ["B-1", "B-2"])
    match.request("start_failure", "B-1")
    match.step(2)
    assert match.robots["B-1"].admitted
    assert not match.robots["B-1"].started
    for kind in ("order", "target"):
        assert match.request(kind, "B-1")["accepted"]


@pytest.mark.parametrize("kind", ["order", "target"])
def test_longpoll_returns_exclusion_without_waiting_for_publication(kind):
    match = engine()
    match.request("enter_ready")
    app, _ = create_apps(match)

    async def case():
        service = app.state.service
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            pending = asyncio.create_task(client.get("/api/report/" + kind,
                params={"mission_code": "SIMB0001", "wait": 120}))
            try:
                # Admission pending before start must remain a normal long-poll.
                await asyncio.sleep(.08)
                assert not pending.done()
                await service.submit("ready", "B-2")
                await service.submit("start")
                result = await asyncio.wait_for(pending, 1.)
                assert result.status_code == 200
                assert result.json() == EXCLUDED
                assert service.waiters.active == 0
                # A new excluded request also returns immediately, including
                # target requests before the 240-second production deadline.
                result = await asyncio.wait_for(client.get("/api/report/" + kind,
                    params={"mission_code": "SIMB0001", "wait": 120}), 1.)
                assert result.json() == EXCLUDED
            finally:
                pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)
        await service.close()

    with EngineRuntime(match):
        asyncio.run(case())


@pytest.mark.parametrize("prefix", ["/api/report", "/api/rehearsal"])
def test_sdk_drone_uses_report_camera_route_for_both_prefixes(prefix):
    class Gateway:
        def __init__(self):
            self.calls = []

        def get_drone(self, slot, camera=None, test_mode=False):
            self.calls.append((slot, camera, test_mode))
            return b"test-jpeg-frame", {"X-Captured-At": "2026-11-18 13:00:00"}

    gateway = Gateway()
    app, _ = create_apps(engine(), gateway=gateway)
    app.state.service.test_mode = True

    async def case():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            port = HTTPPort("http://test", "SIMB0001", client=client, prefix=prefix)
            blob, headers = await port.drone(camera="test1")
            assert blob == b"test-jpeg-frame"
            assert headers["x-captured-at"] == "2026-11-18 13:00:00"
            assert gateway.calls == [("B-1", "test1", True)]
            assert port.transcript[-1]["path"] == "/api/report/drone"
        await app.state.service.close()

    asyncio.run(case())
