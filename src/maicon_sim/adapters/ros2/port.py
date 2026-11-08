import copy
import math
from .transport import MATCH_QOS,SENSOR_QOS


class ROS2RobotPort:
    """Tested internal mapping only; final official custom message types are pending."""
    hardware_validated=False
    def __init__(self,transport):
        self.transport=transport
        self.observations={}
        self._unsubscribers=[]
        for topic,channel,qos in (("/mil/state","state",SENSOR_QOS),("/mil/match","match",MATCH_QOS),
                                  ("/odom","odom",SENSOR_QOS),("/image_raw","rgb",SENSOR_QOS),
                                  ("/imu/data","imu",SENSOR_QOS)):
            def callback(value,channel=channel):
                self.observations[channel]=copy.deepcopy(value)
                if channel=="match" and value.get("cmd") in ("pause","report","stop"):
                    self.transport.publish("/cmd_vel",{"linear_x_mps":0.0,"angular_z_rps":0.0})
            self._unsubscribers.append(transport.subscribe(topic,callback,qos))
    async def latest_observations(self): return copy.deepcopy(self.observations)
    async def command_velocity(self,linear_x_mps,angular_z_rps):
        if not all(type(x) in (float,int) and math.isfinite(x) for x in (linear_x_mps,angular_z_rps)):
            raise ValueError("velocity must be finite")
        if abs(linear_x_mps)>.6 or abs(angular_z_rps)>3:
            raise ValueError("velocity outside documented limits")
        cmd=self.observations.get("match",{}).get("cmd")
        if cmd in ("pause","report","stop","standby","idle"):
            linear_x_mps=angular_z_rps=0.0
        self.transport.publish("/cmd_vel",{"linear_x_mps":linear_x_mps,"angular_z_rps":angular_z_rps})
    async def command_gimbal(self,pan_units,tilt_units,speed_deg_s=90,acc_units=20):
        if not -100<=pan_units<=100 or not -100<=tilt_units<=100 or not 1<=speed_deg_s<=270 or not 1<=acc_units<=254:
            raise ValueError("gimbal outside documented wire limits")
        return await self.transport.call("/mil/gimbal",{"pan":pan_units,"tilt":tilt_units,"speed":speed_deg_s,"acc":acc_units})
    async def fire(self):
        # Exactly one service call; timeout means an unknown actuation outcome.
        return await self.transport.call("/mil/fire",{})
    async def oled(self,line,text):
        if type(line) is not int or not 0<=line<=3 or not isinstance(text,str) or not text.isascii() or len(text)>21:
            raise ValueError("invalid OLED payload")
        self.transport.publish("/mil/oled",{"line":line,"text":text})
    async def close(self):
        for unsubscribe in self._unsubscribers: unsubscribe()
        self._unsubscribers=[]
