"""Authentication, session boundaries and immutable ingress queue submission."""
import asyncio
import copy
import math
import re
import secrets
import time
from fastapi import HTTPException
from .errors import invalid, public_error
from .waiters import WaiterHub
from .metrics import HTTPMetrics


class ServerService:
    def __init__(self, engine, gateway=None, admin_token=None, rehearsal_engine=None):
        self.engine, self.gateway = engine, gateway
        self.rehearsal_engine = rehearsal_engine
        self.active_session = "report"
        self.rehearsal_generation = 0
        engine._active_sensor_engine_provider = lambda: self.active_engine
        self.admin_token = admin_token or secrets.token_urlsafe(32)
        self.waiters = WaiterHub()
        self.pending = set()
        self.shutdown_requested = False
        self.test_mode = False
        self._fault_counters = {}
        self.request_latencies = []
        self.http_stats = HTTPMetrics()

    @property
    def http_metrics(self):
        return self.http_stats.snapshot

    @property
    def active_engine(self):
        return self.rehearsal_engine if self.active_session=="rehearsal" and self.rehearsal_engine is not None else self.engine

    def select_engine(self, rehearsal=False):
        if rehearsal:
            if self.rehearsal_engine is None:
                raise HTTPException(409, "진행 중인 리허설이 없습니다")
            return self.rehearsal_engine
        return self.engine

    def authenticate(self, code, engine=None):
        if not isinstance(code, str) or not re.fullmatch(r"[A-Za-z0-9]{8}", code):
            invalid("mission_code", "mission_code must contain exactly eight ASCII letters or digits")
        engine = engine or self.active_engine
        codes = getattr(engine,"codes",None)
        if codes is None:
            codes = {a["mission_code"].upper():a["slot"] for a in engine.config.scenario["agents"]}
        slot = codes.get(code.upper())
        if slot is None:
            raise HTTPException(401, "unknown mission code")
        return slot

    def check_session(self, request, engine):
        expected = request.headers.get("x-sim-match-id")
        if expected and expected != engine.match_id:
            raise HTTPException(409, "simulator session ended")

    async def body(self, request, allowed=None):
        try:
            body = await request.json()
        except Exception:
            invalid("body", "a JSON object is required")
        if not isinstance(body,dict):
            invalid("body", "a JSON object is required")
        def nonfinite(value):
            if isinstance(value,dict):return any(nonfinite(item) for item in value.values())
            if isinstance(value,list):return any(nonfinite(item) for item in value)
            return type(value) is float and not math.isfinite(value)
        if nonfinite(body):
            invalid("body","NaN and Infinity are not permitted in JSON requests")
        if allowed is not None and set(body)-set(allowed):
            invalid(sorted(set(body)-set(allowed))[0], "unknown field")
        return body

    def _fault(self, engine, slot, path):
        # Each configured fault counts only requests after activation.
        clocks = {"sim":engine.sim_tick*10,"match":engine.match_elapsed_ticks*10,
                  "reporting":engine.reporting_elapsed_ticks*10}
        for event in engine.config.scenario.get("events",[]):
            if event["kind"] != "http_delay":
                continue
            if event["clock"] == "reporting" and engine.phase not in ("reporting","finished"):
                continue
            if clocks[event["clock"]] < event["at_ms"]:
                continue
            p=event["parameters"]
            if p["slot"] != slot or p["path"] != path:
                continue
            key=(engine.match_id,event["event_id"])
            count=self._fault_counters.get(key,0)+1
            self._fault_counters[key]=count
            if count == p["match_occurrence"]:
                return p
        return None

    async def submit(self, kind, slot=None, payload=None, engine=None, session_id=None, path=None, request=None):
        engine = engine or self.engine
        original_session = session_id or engine.match_id
        clean = copy.deepcopy(payload or {})
        clean.pop("mission_code",None)
        fault = self._fault(engine,slot,path) if path and slot else None
        started=time.monotonic()
        async def commit():
            if fault and fault["stage"] == "before_ingress":
                await asyncio.sleep(fault["duration_ms"]/1000)
            try:
                runtime=getattr(engine,"_runtime",None)
                if runtime is not None and runtime.failure is not None:
                    raise HTTPException(503,"engine writer is unavailable")
                future = engine.enqueue(kind,slot,clean,session_id=original_session)
                result = await asyncio.wait_for(asyncio.shield(asyncio.wrap_future(future)),10)
            except asyncio.TimeoutError:
                raise HTTPException(503,"engine request outcome is unknown after timeout") from None
            except Exception as error:
                if isinstance(error,HTTPException):
                    raise
                raise public_error(error) from None
            if kind not in {"me","order","target","snapshot","result"}:
                await self.waiters.notify()
            if fault and fault["stage"] == "after_commit":
                await asyncio.sleep(fault["duration_ms"]/1000)
                if fault.get("drop_response_after_commit"):
                    # The client observes an unknown outcome; the committed report remains.
                    if request is not None:
                        while True:
                            message=await request.receive()
                            if message["type"]=="http.disconnect":
                                break
                    raise HTTPException(503,"response lost after commit")
            return result
        task=asyncio.create_task(commit())
        self.pending.add(task)
        def completed(done):
            self.pending.discard(done)
            if not done.cancelled():
                done.exception()  # consume background exceptions after client cancellation
        task.add_done_callback(completed)
        try:
            return await asyncio.shield(task)
        finally:
            self.request_latencies.append(time.monotonic()-started)
            if len(self.request_latencies)>10000:
                del self.request_latencies[:5000]

    async def close(self):
        await self.waiters.close()
        current=asyncio.get_running_loop()
        groups={}
        for task in tuple(self.pending):
            groups.setdefault(task.get_loop(),[]).append(task)
        async def cancel_group(tasks):
            for task in tasks:task.cancel()
            await asyncio.gather(*tasks,return_exceptions=True)
        waits=[]
        for loop,tasks in groups.items():
            if loop is current:
                waits.append(cancel_group(tasks))
            elif loop.is_running():
                waits.append(asyncio.wrap_future(asyncio.run_coroutine_threadsafe(cancel_group(tasks),loop)))
        if waits:await asyncio.gather(*waits,return_exceptions=True)

    def close_threadsafe(self, timeout_s=5):
        """Call from the launcher's main thread before shutting down HTTP loops."""
        self.waiters.closed=True
        loops=[self.waiters.loop]+[task.get_loop() for task in tuple(self.pending)]
        for loop in loops:
            if loop is not None and loop.is_running():
                asyncio.run_coroutine_threadsafe(self.close(),loop).result(timeout_s)
                return

    async def report_get(self, kind, request, rehearsal=False):
        if rehearsal and self.rehearsal_engine is None:
            self.authenticate(request.query_params.get("mission_code"))
            if kind in ("order","target"):
                raw=request.query_params.get("wait","0")
                if not re.fullmatch(r"[0-9]+",raw) or not 0<=int(raw)<=120:
                    invalid("wait", "wait must be an integer between 0 and 120")
                return {"accepted":False,"reason":"진행 중인 리허설이 없습니다"}
            return {"slot":None,"camp":None,"phase":"idle","ready":False}
        engine=self.select_engine(rehearsal)
        code=request.query_params.get("mission_code")
        slot=self.authenticate(code,engine)
        self.check_session(request,engine)
        if kind not in ("order","target"):
            return await self.submit(kind,slot,engine=engine)
        raw=request.query_params.get("wait","0")
        if not re.fullmatch(r"[0-9]+",raw) or not 0<=int(raw)<=120:
            invalid("wait", "wait must be an integer between 0 and 120")
        match_id=engine.match_id
        async def disconnected():
            while True:
                message = await request.receive()
                if message["type"] == "http.disconnect":
                    return
        watcher=asyncio.create_task(disconnected())
        polling=asyncio.create_task(self.waiters.wait(
            lambda:self.submit(kind,slot,engine=engine,session_id=match_id), int(raw),
            match_id,lambda:engine.match_id))
        try:
            done,_=await asyncio.wait((watcher,polling),return_when=asyncio.FIRST_COMPLETED)
            if polling in done:
                return polling.result()
            # A socket disconnect is normal lifecycle cleanup. Returning ends
            # ASGI quietly; raising CancelledError here makes Uvicorn log an
            # application exception for every participant process restart.
            return {"accepted":False,"reason":"client disconnected"}
        finally:
            watcher.cancel()
            polling.cancel()
            await asyncio.gather(watcher,polling,return_exceptions=True)

    async def report_post(self, kind, request, rehearsal=False):
        engine=self.select_engine(rehearsal)
        body=await self.body(request)
        slot=self.authenticate(body.get("mission_code"),engine)
        self.check_session(request,engine)
        if kind == "ready" and set(body)!={"mission_code"}:
            invalid("body", "ready accepts mission_code only")
        return await self.submit(kind,slot,body,engine=engine,path=request.url.path,request=request)

    def sensor(self, slot, channel):
        if self.gateway is None:
            raise HTTPException(503,"sensor has not produced a frame")
        try:
            return self.gateway.get(slot,channel)
        except Exception as error:
            raise public_error(error) from None

    def public_map(self):
        return copy.deepcopy({k:self.active_engine.config.arena[k] for k in
                              ("arena_id","bounds","sectors","bases","nominal_starts")})

    def calibration(self):
        sensors=self.active_engine.config.sensors
        geom=sensors["geometry"]
        return copy.deepcopy({"front_camera":sensors["front_camera"],
                 "gimbal_pivot_m":geom["gimbal_pivot_m"],
                 "camera_offset_gimbal_m":geom["camera_offset_gimbal_m"],
                 "pan_deg_per_unit":.5,"tilt_deg_per_unit":.15,
                 "lidar":sensors["lidar"]})

    @staticmethod
    def validate_robot(kind, body):
        fields={"cmd_vel":{"linear_x_mps","angular_z_rps"},
                "gimbal":{"pan","tilt","speed","acc"},"fire":set(),"oled":{"line","text"}}[kind]
        payload={k:v for k,v in body.items() if k!="mission_code"}
        if set(payload)!=fields:
            invalid("body", "missing or unknown robot command field")
        limits={"linear_x_mps":(-.6,.6),"angular_z_rps":(-3,3),
                "pan":(-100,100),"tilt":(-100,100),"speed":(1,270),"acc":(1,254)}
        for key,value in payload.items():
            if key in limits:
                lo,hi=limits[key]
                if type(value) not in (int,float) or not math.isfinite(value) or not lo<=value<=hi:
                    invalid(key,f"must be a finite number in [{lo}, {hi}]")
        if kind=="oled":
            if type(payload["line"]) is not int or not 0<=payload["line"]<=3:
                invalid("line","line must be an integer from 0 to 3")
            text=payload["text"]
            if not isinstance(text,str) or not text.isascii() or len(text)>21:
                invalid("text","text must be ASCII with at most 21 characters")
        return payload
