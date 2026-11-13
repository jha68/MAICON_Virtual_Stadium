"""One engine writer, real wall-clock pacing, and explicit overload evidence."""
from concurrent.futures import Future
import queue
import threading
import time
import numpy as np


class EngineRuntime:
    def __init__(self, engine, gateway=None, on_tick=None):
        self.engine, self.gateway, self.on_tick = engine, gateway, on_tick
        self.failure = None
        self.thread = None
        self._stop = threading.Event()
        self.debug_paused = threading.Event()
        self._single_step = threading.Event()
        self.tick_times = []
        self.max_lag_s = 0.0
        self.overloaded = False
        self.warning_count = 0
        self.started_at = None
        self.elapsed_s = 0.0
        self.tick_count = 0
        self.extra_engines = []
        self._operations = queue.Queue()
        engine._runtime = self

    def sensor_engine(self):
        provider=getattr(self.engine,"_active_sensor_engine_provider",None)
        return provider() if provider is not None else self.engine

    def remove_engine(self,engine):
        self.extra_engines=[entry for entry in self.extra_engines if entry[0] is not engine]

    def add_engine(self, engine, gateway=None):
        self.extra_engines.append((engine,gateway))
        engine._runtime = self

    def submit_operation(self, callback):
        future=Future()
        self._operations.put((callback,future))
        return future

    def start(self):
        if self.thread and self.thread.is_alive():
            return self
        self._stop.clear()
        self.thread = threading.Thread(target=self._run, name="maicon-engine", daemon=True)
        self.thread.start()
        return self

    def _run(self):
        self.started_at = time.monotonic()
        deadline = self.started_at
        pace_deadline = deadline
        lag_since = None
        try:
            if self.gateway is not None:
                self.gateway.update(self.sensor_engine())
            while not self._stop.is_set():
                if self.debug_paused.is_set() and not self._single_step.is_set():
                    self._stop.wait(.01)
                    deadline = pace_deadline = time.monotonic()
                    continue
                self._single_step.clear()
                before = time.monotonic()
                while True:
                    try: callback,future=self._operations.get_nowait()
                    except queue.Empty: break
                    try: future.set_result(callback())
                    except Exception as error: future.set_exception(error)
                self.engine.step()
                for other, gateway in tuple(self.extra_engines):
                    other.step()
                    if gateway is not None: gateway.update(other)
                if self.gateway is not None:
                    self.gateway.update(self.sensor_engine())
                if self.on_tick is not None:
                    self.on_tick(self.engine)
                after = time.monotonic()
                self.tick_count += 1
                self.tick_times.append(after-before)
                # Bounded history, independent of episode length.
                if len(self.tick_times) > 100000:
                    del self.tick_times[:50000]
                deadline += .01
                pace_deadline += .01
                lag = max(0.0, after-deadline)
                self.max_lag_s = max(lag, self.max_lag_s)
                if lag > .5:
                    self.warning_count += 1
                if lag > 2:
                    lag_since = after if lag_since is None else lag_since
                    if after-lag_since >= 5:
                        self.overloaded = True
                else:
                    lag_since = None
                # Do not repay seconds of overload as an unbounded burst of
                # simulated time. HTTP participants need wall time to observe
                # a newly published objective and refresh their actuator TTLs.
                # Keep every physics tick and the cumulative lag evidence above.
                pace_deadline = max(pace_deadline, after-.2)
                self._stop.wait(max(0, pace_deadline-time.monotonic()))
        except BaseException as error:
            self.failure = error
            self._stop.set()
        finally:
            self.elapsed_s = time.monotonic()-self.started_at
            # Only the engine thread writes actuator state.
            try:
                for engine in (self.engine, *(other for other, _ in self.extra_engines)):
                    for robot in engine.robots.values():
                        robot.v = robot.omega = 0.0
                        robot.laser_until = 0
                        robot.target_pan,robot.target_tilt = robot.pan,robot.tilt
            except Exception:
                pass

    def step_once(self):
        self._single_step.set()

    def close(self):
        self._stop.set()
        if self.thread:
            self.thread.join(timeout=10)
            if self.thread.is_alive():
                raise RuntimeError("engine writer did not stop")

    @property
    def metrics(self):
        times = np.asarray(self.tick_times)
        elapsed = self.elapsed_s or ((time.monotonic()-self.started_at) if self.started_at else 0)
        return {"tick_p50_s":float(np.percentile(times,50)) if len(times) else 0,
                "tick_p95_s":float(np.percentile(times,95)) if len(times) else 0,
                "tick_p99_s":float(np.percentile(times,99)) if len(times) else 0,
                "max_lag_s": self.max_lag_s, "overloaded":self.overloaded,
                "real_time_factor": self.tick_count*.01/elapsed if elapsed else 0,
                "tick_count":self.tick_count,"wall_duration_s":elapsed}

    def __enter__(self):
        return self.start()

    def __exit__(self,*args):
        self.close()
