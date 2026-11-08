"""Latest complete snapshots, one in-flight request per mission.

Timeout is an unknown outcome, not proof of failure. Without server CAS a late
old commit can overwrite a new one; periodic current-snapshot retransmission is
best effort and cannot guarantee recovery at the deadline.
"""
import asyncio
import copy
from dataclasses import dataclass


@dataclass(frozen=True)
class ReportSnapshot:
    kind:str
    revision:int
    payload:dict
    created_tick:int=0
    session_id:str=""


def canonical_received(kind,payload):
    """Canonical wire comparison without importing evaluator or scoring modules."""
    if kind=="m1":
        sectors=payload.get("search_sectors")
        return {"target":payload.get("target").upper() if payload.get("target") is not None else None,
                "base":payload.get("base").upper() if payload.get("base") is not None else None,
                "search_sectors":sorted(item.upper() for item in sectors) if sectors is not None else None}
    if kind=="m3":
        return {"sectors":sorted([{"sector":sector["sector"].upper(),"objects":sorted(
            [{"type":obj["type"].upper(),"count":obj["count"]} for obj in sector["objects"] if obj["count"]!=0],
            key=lambda item:item["type"])} for sector in payload["sectors"]],key=lambda item:item["sector"])}
    return {"ranking":[item.upper() for item in payload["ranking"]]}


class ReportWorker:
    def __init__(self,port,kind,*,timeout_s=5,resend_interval_s=1,max_attempts=4):
        if kind not in ("m1","m3","m6"):
            raise ValueError("unknown report mission")
        self.port,self.kind=port,kind
        self.timeout_s,self.resend_interval_s=timeout_s,resend_interval_s
        self.max_attempts=max_attempts
        self.latest=None
        self.acknowledged_revision=None
        self.closed=False
        self._event=asyncio.Event()
        self._lock=asyncio.Lock()
        self.errors=[]
        self.task=None

    def update(self,payload,revision=None,created_tick=0,session_id=""):
        previous=self.latest.revision if self.latest else 0
        revision=previous+1 if revision is None else revision
        if revision<=previous:
            return
        self.latest=ReportSnapshot(self.kind,revision,copy.deepcopy(payload),created_tick,session_id)
        self._event.set()

    submit=update

    async def flush_once(self):
        async with self._lock:
            if self.closed or self.latest is None:
                return None
            snapshot=self.latest
            method=getattr(self.port,"submit_"+self.kind)
            try:
                result=await asyncio.wait_for(method(copy.deepcopy(snapshot.payload)),self.timeout_s)
            except Exception as error:
                self.errors.append({"revision":snapshot.revision,"status":getattr(error,"status",None),
                                    "kind":type(error).__name__})
                if getattr(error,"status",None) in (401,422):
                    self.closed=True
                elif getattr(error,"status",None)==409:
                    phase=(await self.port.get_me())["phase"]
                    if phase=="finished" or (self.kind in ("m1","m3") and phase!="running"):
                        self.closed=True
                return None
            if result.get("accepted") and result.get("received")==canonical_received(self.kind,snapshot.payload):
                self.acknowledged_revision=snapshot.revision
                return result
            self.errors.append({"revision":snapshot.revision,"status":200,"kind":"AcknowledgementMismatch"})
            return None

    async def run(self):
        failures=0
        while not self.closed:
            try:
                await asyncio.wait_for(self._event.wait(),self.resend_interval_s)
            except asyncio.TimeoutError:
                pass
            self._event.clear()
            if self.latest is None:
                continue
            result=await self.flush_once()
            failures=0 if result is not None else failures+1
            if failures>=self.max_attempts:
                # Keep only the latest snapshot but avoid retry storms.
                await asyncio.sleep(2)
                failures=0
            elif result is None:
                await asyncio.sleep((.2,.5,1,2)[min(failures-1,3)])

    def start(self):
        if self.task is None:
            self.task=asyncio.create_task(self.run())
        return self

    async def close(self):
        self.closed=True
        self._event.set()
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task,return_exceptions=True)


SerialReportWorker=ReportWorker
