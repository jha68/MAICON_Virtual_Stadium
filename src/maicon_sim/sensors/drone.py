"""Drone delivery is owned by SensorGateway, separate from capture cadence."""
from .gateway import SensorUnavailable

def frame_interval_ticks(destroyed_count,intervals_ms=(1000,2000,5000)):
    if destroyed_count>=3:raise SensorUnavailable(403,'All camp facilities are destroyed')
    return intervals_ms[destroyed_count]//10
