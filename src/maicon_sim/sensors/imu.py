"""Synthetic IMU with gravity-including specific force convention."""
import math
import numpy as np
from ..core.geometry2d import pose_values,wrap_angle
from ..core.geometry3d import rotation_z
class ImuModel:
    def __init__(self,initial_pose,noise,rng):
        self.noise=noise;self.rng=rng;self.previous_velocity=np.zeros(3);self.last_tick=None;self.previous_pose=pose_values(initial_pose)
    def measure(self,pose,tick,v,omega):
        x,y,yaw=pose_values(pose);R=rotation_z(yaw)
        dt=0 if self.last_tick is None else (tick-self.last_tick)*.01
        velocity=np.zeros(3) if dt==0 else np.array([x-self.previous_pose[0],y-self.previous_pose[1],0.])/dt
        acceleration=np.zeros(3) if dt==0 else (velocity-self.previous_velocity)/dt
        specific=R.T@(acceleration-np.array([0.,0.,-9.80665]))
        specific+=self.rng.normal(0,self.noise.get('imu_accel_sigma_mps2',0),3)
        # Differentiate accepted pose, so a blocked rotational command is not a measured turn.
        actual_omega=0 if dt==0 else wrap_angle(yaw-self.previous_pose[2])/dt
        gyro=np.array([0.,0.,actual_omega+self.noise.get('imu_yaw_bias_rps',0)])+self.rng.normal(0,self.noise.get('imu_gyro_sigma_rps',0),3)
        self.previous_velocity=velocity;self.last_tick=tick;self.previous_pose=(x,y,yaw)
        return {'orientation_xyzw':[0.,0.,math.sin(yaw/2),math.cos(yaw/2)],'angular_velocity_rps':gyro.tolist(),'linear_acceleration_mps2':specific.tolist()}
