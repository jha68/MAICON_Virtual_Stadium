"""Incremental local odometry; no global pose leaks through the DTO."""
import math
import numpy as np
from ..core.geometry2d import pose_values,rotation2,wrap_angle
class OdometryModel:
    def __init__(self,initial_pose,noise,rng):
        self.initial=pose_values(initial_pose);self.previous=self.initial;self.local=np.zeros(3);self.noise=noise;self.rng=rng;self.last_tick=None
    def measure(self,pose,tick,v,omega):
        x,y,yaw=pose_values(pose);px,py,pyaw=self.previous
        delta=rotation2(-self.initial[2])@np.array([x-px,y-py])
        dt=0 if self.last_tick is None else (tick-self.last_tick)*.01
        self.local[:2]+=delta*self.noise.get('odom_linear_scale',1)
        if dt>0:self.local[:2]+=self.rng.normal(0,self.noise.get('odom_increment_sigma_m',0),2)
        self.local[2]=wrap_angle(self.local[2]+wrap_angle(yaw-pyaw)+self.noise.get('odom_yaw_bias_rps',0)*dt)
        self.previous=(x,y,yaw);self.last_tick=tick
        return {'local_pose':dict(zip(('x_m','y_m','yaw_rad'),map(float,self.local))),
                'linear_x_mps':float(v*self.noise.get('odom_linear_scale',1)),
                'angular_z_rps':float(omega+self.noise.get('odom_yaw_bias_rps',0))}
