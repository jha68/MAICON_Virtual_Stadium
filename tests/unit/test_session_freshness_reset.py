"""In-flight observations from an old session cannot poison the new epoch."""
import asyncio

from maicon_sim.policies.controller import TeamController


def frames(tick):
    stamp = {"captured_tick": tick, "sequence": tick, "received_tick": tick}
    return {
        "state": {**stamp, "hp": 4, "hp_max": 4, "battery_pct": 100.},
        "match": {**stamp, "mode": "mission", "cmd": "standby"},
        "odom": {**stamp, "local_pose": {"x_m": 0., "y_m": 0., "yaw_rad": 0.}},
        "scan": {**stamp, "ranges_m": [2.]},
    }


def test_old_inflight_frames_during_reset_cannot_block_new_tick_zero():
    class Port:
        def __init__(self):
            self.old_request_entered = asyncio.Event()
            self.old_request_returned = asyncio.Event()
            self.reset_map_entered = asyncio.Event()
            self.release_old_request = asyncio.Event()
            self.release_reset_map = asyncio.Event()
            self.first_observation = True

        async def latest_observations(self):
            if self.first_observation:
                self.first_observation = False
                self.old_request_entered.set()
                await self.release_old_request.wait()
                self.old_request_returned.set()
                return frames(30000)
            return frames(0)

        async def map_prior(self):
            self.reset_map_entered.set()
            await self.release_reset_map.wait()
            return {"bounds": {"width_m": 6., "height_m": 5.},
                    "nominal_starts": [], "sectors": [], "bases": []}

        async def calibration(self):
            return {}

        async def command_velocity(self, *args):
            pass

        async def close(self):
            pass

    async def run():
        port = Port()
        controller = TeamController(port, "B-1", "idle")
        controller._generation = 5
        controller.session_identity = {"match_id": "old-match"}
        poll = asyncio.create_task(controller._poll_observations())
        reset = None
        try:
            await asyncio.wait_for(port.old_request_entered.wait(), 2.)
            reset = asyncio.create_task(controller._initialize_session({
                "match_id": "new-match", "slot": "B-1", "camp": "BLUE", "capabilities": {}}))
            await asyncio.wait_for(port.reset_map_entered.wait(), 2.)
            assert controller._generation != 5
            port.release_old_request.set()
            await asyncio.wait_for(port.old_request_returned.wait(), 2.)
            await asyncio.sleep(0)  # let the polling coroutine reject its old reply
            assert controller._sensor_progress == {}

            port.release_reset_map.set()
            await asyncio.wait_for(reset, 2.)
            assert controller.session_identity["match_id"] == "new-match"
            assert controller._sensors_ready
            assert controller.observations["scan"]["captured_tick"] == 0
            assert controller._sensor_progress["scan"] == ("captured_tick", 0)
            # New-session ticks must keep advancing from zero, rather than
            # waiting five minutes to overtake the old match's final tick.
            controller._observe_sensor_progress(frames(1))
            assert controller._sensor_progress["scan"] == ("captured_tick", 1)
            assert controller._stale_sensors() == []
        finally:
            port.release_old_request.set()
            port.release_reset_map.set()
            poll.cancel()
            if reset is not None and not reset.done():
                reset.cancel()
            await asyncio.gather(poll, *([reset] if reset is not None else []), return_exceptions=True)
            await controller.close()

    asyncio.run(run())
