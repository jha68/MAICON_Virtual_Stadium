"""Internal DTO transport, deliberately not a fabricated official SDK mapping."""
import asyncio
import copy
from dataclasses import dataclass


@dataclass(frozen=True)
class QoS:
    depth:int=1
    transient_local:bool=False
    best_effort:bool=False


MATCH_QOS=QoS(depth=1,transient_local=True)
SENSOR_QOS=QoS(depth=5,best_effort=True)


class FakeRosTransport:
    def __init__(self):
        self.subscribers={}
        self.latched={}
        self.published=[]
        self.services={}
        self.closed=False
    def subscribe(self,topic,callback,qos=SENSOR_QOS):
        self.subscribers.setdefault(topic,[]).append(callback)
        if qos.transient_local and topic in self.latched:
            callback(copy.deepcopy(self.latched[topic]))
        def unsubscribe(): self.subscribers[topic].remove(callback)
        return unsubscribe
    def publish(self,topic,value,qos=SENSOR_QOS):
        if self.closed: raise RuntimeError("transport closed")
        value=copy.deepcopy(value)
        self.published.append((topic,value))
        if qos.transient_local: self.latched[topic]=value
        for callback in tuple(self.subscribers.get(topic,[])):
            callback(copy.deepcopy(value))
    def register_service(self,name,handler): self.services[name]=handler
    async def call(self,name,value,timeout_s=1):
        if name not in self.services: raise RuntimeError("service unavailable")
        async def invoke():
            result=self.services[name](copy.deepcopy(value))
            if asyncio.iscoroutine(result): result=await result
            return copy.deepcopy(result)
        return await asyncio.wait_for(invoke(),timeout_s)
    def close(self):
        self.closed=True
        self.subscribers.clear()
        self.services.clear()
