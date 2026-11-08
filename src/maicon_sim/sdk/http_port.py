"""Async participant HTTP transport. No automatic actuation retries."""
import asyncio
import io
import time
import httpx
import numpy as np
from PIL import Image
from .session import SessionCache
from .logging import protect_transport_logs


class PortError(RuntimeError):
    def __init__(self,status,detail):
        super().__init__(str(detail))
        self.status,self.detail=status,detail


class HTTPPort:
    def __init__(self,server,mission_code,*,client=None,prefix="/api/report",sim_headers=True):
        protect_transport_logs()
        self.server=server.rstrip("/")
        self._mission_code=mission_code
        self.client=client or httpx.AsyncClient(base_url=self.server,trust_env=False,
            timeout=httpx.Timeout(10,connect=3))
        self._owns_client=client is None
        self.prefix=prefix
        self.sim_headers=sim_headers
        self.cache=SessionCache()
        self.capabilities={}
        self.transcript=[]

    async def _request(self,method,path,payload=None,params=None,wait_s=0,raw=False):
        fields=dict(params or {})
        body=dict(payload or {})
        if method=="GET": fields["mission_code"]=self._mission_code
        else: body["mission_code"]=self._mission_code
        headers={"X-Sim-Match-ID":self.cache.match_id} if self.cache.match_id and self.sim_headers and path!="/sim/session" else {}
        response=await self.client.request(method,path,params=fields if method=="GET" else None,
            json=body if method!="GET" else None,headers=headers,
            timeout=httpx.Timeout(wait_s+10,connect=3))
        # Deliberately record route and status only; URLs contain authentication.
        self.transcript.append({"method":method,"path":path,"status":response.status_code})
        if len(self.transcript)>20000: del self.transcript[:10000]
        if not response.is_success:
            try: detail=response.json().get("detail","request failed")
            except Exception: detail="request failed"
            raise PortError(response.status_code,detail)
        return response if raw else response.json()

    async def get_me(self): return await self._request("GET",self.prefix+"/me")
    async def ready(self): return await self._request("POST",self.prefix+"/ready")
    async def await_order(self,wait_s=120): return await self._request("GET",self.prefix+"/order",params={"wait":wait_s},wait_s=wait_s)
    async def await_target(self,wait_s=120): return await self._request("GET",self.prefix+"/target",params={"wait":wait_s},wait_s=wait_s)
    async def submit_m1(self,value): return await self._request("POST",self.prefix+"/interpretation",payload=value)
    async def submit_m3(self,value):
        return await self._request("POST",self.prefix+"/detection",payload={"sectors":value} if isinstance(value,list) else value)
    async def submit_m6(self,ranking):
        return await self._request("POST",self.prefix+"/situation",payload=ranking if isinstance(ranking,dict) else {"ranking":list(ranking)})
    async def session(self):
        value=await self._request("GET","/sim/session")
        self.cache.accept(value)
        self.identity={key:value[key] for key in ("match_id","slot","camp")}
        self.capabilities=value["capabilities"]
        return value
    async def map_prior(self): return await self._request("GET","/sim/map-prior")
    async def calibration(self): return await self._request("GET","/sim/calibration")
    async def command_velocity(self,linear_x_mps,angular_z_rps):
        return await self._request("POST","/sim/robot/v1/cmd_vel",payload={"linear_x_mps":linear_x_mps,"angular_z_rps":angular_z_rps})
    async def command_gimbal(self,pan_units,tilt_units,speed_deg_s=90,acc_units=20):
        return await self._request("POST","/sim/robot/v1/gimbal",payload={"pan":pan_units,"tilt":tilt_units,"speed":speed_deg_s,"acc":acc_units})
    async def fire(self):
        return await self._request("POST","/sim/robot/v1/fire")
    async def oled(self,line,text):
        return await self._request("POST","/sim/robot/v1/oled",payload={"line":line,"text":text})
    async def observation(self,channel):
        if channel=="camera":
            response=await self._request("GET","/sim/robot/v1/camera",raw=True)
            data=np.asarray(Image.open(io.BytesIO(response.content)).convert("RGB"))[...,::-1].copy()
            return {"data":data,"width_px":data.shape[1],"height_px":data.shape[0],
                    "camera_id":getattr(self,"identity",{}).get("slot","self")+"/front",
                    "encoding":"bgr8","captured_tick":int(response.headers["X-Sim-Captured-Tick"]),
                    "received_tick":int(response.headers["X-Sim-Received-Tick"]),
                    "sequence":int(response.headers["X-Sim-Sequence"])}
        return await self._request("GET","/sim/robot/v1/"+channel)
    async def latest_observations(self):
        channels=["state","match","odom","imu","scan"]
        if self.capabilities.get("semantic",False): channels.append("semantic")
        if self.capabilities.get("rgb",False): channels.append("camera")
        async def one(channel):
            try: return channel,await self.observation(channel)
            except PortError as error:
                if error.status in (409,503): return channel,None
                raise
        results=await asyncio.gather(*(one(c) for c in channels))
        for channel,value in results:
            if value is not None: self.cache.observations["rgb" if channel=="camera" else channel]=value
        return dict(self.cache.observations)
    async def drone(self,camera=None):
        response=await self._request("GET",self.prefix+"/drone",params={"camera":camera} if camera else {},raw=True)
        return response.content,dict(response.headers)
    async def close(self):
        if self._owns_client: await self.client.aclose()
    async def __aenter__(self): return self
    async def __aexit__(self,*args): await self.close()
