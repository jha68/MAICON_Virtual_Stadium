"""Deterministic test transport; the controller still sees only public projection."""
import asyncio
import copy
from .session import SessionCache


class InProcessPort:
    def __init__(self,engine,slot,gateway=None):
        self._engine,self.slot,self._gateway=engine,slot,gateway
        self.cache=SessionCache()
        self.capabilities=dict(getattr(gateway,"capabilities",{}))
    async def _request(self,kind,payload=None):
        # Fast unit tests/offline controllers run on the engine writer at a boundary.
        return copy.deepcopy(self._engine.request(kind,self.slot,payload or {}))
    async def get_me(self): return await self._request("me")
    async def ready(self): return await self._request("ready")
    async def await_order(self,wait_s=0): return await self._request("order")
    async def await_target(self,wait_s=0): return await self._request("target")
    async def submit_m1(self,value): return await self._request("m1",value)
    async def submit_m3(self,value): return await self._request("m3",{"sectors":value} if isinstance(value,list) else value)
    async def submit_m6(self,ranking): return await self._request("m6",ranking if isinstance(ranking,dict) else {"ranking":list(ranking)})
    async def command_velocity(self,linear_x_mps,angular_z_rps): return await self._request("cmd_vel",{"linear_x_mps":linear_x_mps,"angular_z_rps":angular_z_rps})
    async def command_gimbal(self,pan_units,tilt_units,speed_deg_s=90,acc_units=20): return await self._request("gimbal",{"pan":pan_units,"tilt":tilt_units,"speed":speed_deg_s,"acc":acc_units})
    async def fire(self): return await self._request("fire")
    async def session(self):
        value={"match_id":self._engine.match_id,"episode_index":self._engine.episode_index,"slot":self.slot,
               "camp":"BLUE" if self.slot.startswith("B") else "RED","schema_version":"1.0","capabilities":self.capabilities}
        self.cache.accept(value)
        return value
    async def map_prior(self):
        arena=self._engine.config.arena
        return copy.deepcopy({k:arena[k] for k in ("arena_id","bounds","sectors","bases","nominal_starts")})
    async def calibration(self):
        sensor=self._engine.config.sensors
        return copy.deepcopy({"capture_clock_epoch":self._engine.config.scenario["epoch_kst"], "front_camera":sensor["front_camera"],"gimbal_pivot_m":sensor["geometry"]["gimbal_pivot_m"],
                              "artwork_profile": 'prestudy' if self._engine.config.assets['manifest_id']=='prestudy_reference_v1' else 'synthetic',
                              "actuation":sensor.get('actuation', {}),
                              "camera_offset_gimbal_m":sensor["geometry"]["camera_offset_gimbal_m"],"pan_deg_per_unit":.5,
                              "laser_offset_camera_m":[a-b for a,b in zip(sensor["geometry"]["laser_offset_gimbal_m"],sensor["geometry"]["camera_offset_gimbal_m"])],
                              "tilt_deg_per_unit":.15,"lidar":sensor["lidar"]})
    async def latest_observations(self):
        result={}
        if self._gateway is not None:
            for channel in ("state","match","odom","imu","scan","semantic"):
                try: result[channel]=self._gateway.get(self.slot,channel)
                except Exception as error:
                    if getattr(error,"status",None) not in (409,503): raise
            if self.capabilities.get("rgb",False):
                try: result["rgb"]=self._gateway.get_frame(self.slot)
                except Exception as error:
                    if getattr(error,"status",None) not in (409,503): raise
        return result
    async def drone(self, camera=None):
        return self._gateway.get_drone(self.slot, camera)
    async def close(self): pass
