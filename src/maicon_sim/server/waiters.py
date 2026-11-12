"""Per-connection wall-clock waits; no engine lock survives an await."""
import asyncio
import time


class WaiterHub:
    def __init__(self):
        self.changed = asyncio.Event()
        self.active = 0
        self.closed = False
        self.loop = None

    async def _notify_local(self):
        changed = self.changed
        self.changed = asyncio.Event()
        changed.set()

    async def notify(self):
        loop=asyncio.get_running_loop()
        if self.loop is not None and self.loop is not loop and not self.loop.is_closed():
            await asyncio.wrap_future(asyncio.run_coroutine_threadsafe(self._notify_local(),self.loop))
        else:
            await self._notify_local()

    async def wait(self, predicate, wait_s, session_id, current_session, disconnected=None, terminal=None):
        loop=asyncio.get_running_loop()
        if self.loop is not loop and not self.active:
            self.loop=loop
            self.changed=asyncio.Event()
        deadline = time.monotonic() + wait_s
        self.active += 1
        try:
            while True:
                changed = self.changed
                if self.closed or session_id != current_session():
                    return {"accepted": False, "reason": "simulator session ended"}
                try:
                    answer = await predicate()
                except Exception:
                    if session_id != current_session():
                        return {"accepted": False, "reason": "simulator session ended"}
                    raise
                if session_id != current_session():
                    return {"accepted": False, "reason": "simulator session ended"}
                if answer.get("accepted") or wait_s == 0 or (terminal is not None and terminal(answer)):
                    return answer
                if disconnected is not None and await disconnected():
                    raise asyncio.CancelledError()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return answer
                # Python 3.10 wait_for can swallow outer cancellation when its
                # inner future completes concurrently (bpo-42130). Explicit
                # task cleanup preserves disconnect/reset cancellation here.
                waiter = asyncio.create_task(changed.wait())
                try:
                    await asyncio.wait({waiter}, timeout=min(.05, remaining))
                finally:
                    waiter.cancel()
                    await asyncio.gather(waiter, return_exceptions=True)
        finally:
            self.active -= 1

    async def close(self):
        self.closed = True
        await self.notify()
