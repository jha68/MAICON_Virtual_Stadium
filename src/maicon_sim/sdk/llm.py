"""Replaceable text provider boundary; fixture output is not an AI benchmark."""
import asyncio
import json
from typing import Protocol
import httpx


class LLMPort(Protocol):
    async def parse_order(self,text,allowed_schema=None,deadline=None): ...
    async def rank_threat(self,evidence,deadline=None): ...


class FixtureLLM:
    model_name="fixture_text_parser"
    mock=True
    def __init__(self,camp="BLUE",delay_s=0):
        self.camp=camp
        self.delay_s=delay_s
    async def parse_order(self,text,allowed_schema=None,deadline=None):
        if self.delay_s: await asyncio.sleep(self.delay_s)
        enemy="RED" if self.camp=="BLUE" else "BLUE"
        sector_prefix="R" if self.camp=="BLUE" else "B"
        target=next((code for name,code in (("레이더","RADAR"),("통신","COMMS"),("감시초소","OUTPOST")) if name in text),None)
        base=next((code for name,code in (("군수보급","SUPPLY_DEPOT"),("정비소","MAINTENANCE"),("작전지휘","COMMAND_POST")) if name in text),None)
        sectors=[]
        for name,index in (("첫째",1),("둘째",2),("셋째",3)):
            if name in text: sectors.append(f"{sector_prefix}-S{index}")
        if "중앙" in text: sectors.append("CM")
        if target is None or base is None:
            raise ValueError("fixture parser does not understand this command")
        return {"target":enemy+"_"+target,"search_sectors":sorted(sectors),"base":enemy+"_"+base}
    async def rank_threat(self,evidence,deadline=None):
        enemy="R" if self.camp=="BLUE" else "B"
        return [f"{enemy}-{i}" for i in (1,2,3)]


class HTTPLLM:
    """Configured JSON text endpoint; key is process-only and never logged."""
    mock=False
    def __init__(self,endpoint,model,key=None,timeout_s=5):
        self.endpoint,self.model,self._key,self.timeout_s=endpoint,model,key,timeout_s
    async def _call(self,task,value):
        headers={"Authorization":"Bearer "+self._key} if self._key else {}
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            response=await client.post(self.endpoint,headers=headers,json={"model":self.model,"task":task,"input":value})
            response.raise_for_status()
            result=response.json()
            if not isinstance(result,dict): raise ValueError("LLM must return a JSON object")
            return result
    async def parse_order(self,text,allowed_schema=None,deadline=None):
        return await self._call("parse_order",{"text":text,"schema":allowed_schema})
    async def rank_threat(self,evidence,deadline=None):
        return (await self._call("rank_threat",evidence))["ranking"]


MockLLM=FixtureLLM
