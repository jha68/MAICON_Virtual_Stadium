"""Calibratable actuator response. Gains are SIM values until measured."""
import math
from dataclasses import dataclass


def approach(current, target, maximum_delta):
    if abs(target-current) <= maximum_delta+1e-10:
        return target
    return current + max(-maximum_delta, min(maximum_delta, target-current))


def servo_step(position, velocity, target, speed, acceleration, dt, limits=None):
    """Degrees / seconds. Braking-limited trapezoid, clamped exactly at target."""
    error = target-position
    if abs(error) < 1e-10:
        return target, 0.
    if acceleration <= 0:
        next_position = approach(position, target, speed*dt)
        return next_position, 0. if next_position == target else math.copysign(speed, error)
    wanted = math.copysign(min(speed, math.sqrt(2*acceleration*abs(error))), error)
    next_velocity = approach(velocity, wanted, acceleration*dt)
    delta = (velocity+next_velocity)*.5*dt
    if delta*error > 0 and abs(delta) >= abs(error):
        return target, 0.
    position += delta
    if limits and not limits[0] <= position <= limits[1]:
        return max(limits[0], min(limits[1], position)), 0.
    return position, next_velocity


@dataclass
class GimbalModel:
    acceleration_gain: float = 0.
    pan: float = 0.
    tilt: float = 0.
    target_pan: float = 0.
    target_tilt: float = 0.
    pan_velocity: float = 0.
    tilt_velocity: float = 0.
    speed: float = 90.
    acc: float = 20.
    last_tick: int = 0
    settled_tick: float = 0
    certain: bool = True

    def update(self, tick):
        for _ in range(max(0, tick-self.last_tick)):
            if self.pan == self.target_pan and self.tilt == self.target_tilt:
                break
            for name, unit in (('pan', .5), ('tilt', .15)):
                position, velocity = servo_step(getattr(self, name)*unit, getattr(self, name+'_velocity'),
                    getattr(self, 'target_'+name)*unit, self.speed, self.acc*self.acceleration_gain, .01,
                    limits=(-100*unit, 100*unit))
                setattr(self, name, position/unit)
                setattr(self, name+'_velocity', velocity)
        self.last_tick = tick

    def accepted(self, pan, tilt, speed, tick, acc=20.):
        self.update(tick)
        travel = max(abs(pan-self.pan)*.5, abs(tilt-self.tilt)*.15)/speed
        ramp = 2*speed/(acc*self.acceleration_gain) if self.acceleration_gain else 0.
        self.target_pan, self.target_tilt, self.speed, self.acc = pan, tilt, speed, acc
        self.settled_tick = tick+math.ceil((travel+ramp+.1)*100)
        self.certain = True

    def cancel(self, tick):
        self.update(tick)
        self.target_pan, self.target_tilt = self.pan, self.tilt
        self.pan_velocity = self.tilt_velocity = 0.
        self.certain, self.settled_tick = False, math.inf

    def settled(self, captured_tick):
        return self.certain and captured_tick >= self.settled_tick
