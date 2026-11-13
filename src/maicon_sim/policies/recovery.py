"""Bounded stall recovery using only the participant's fresh LiDAR and odometry."""
import math

from .planning import wrap


class MotionRecovery:
    def __init__(self):
        self.anchor = None
        self.progress_tick = None
        self.until = 0
        self.mode = None

    def command(self, pose, goal, scan, tick, *, holding=False):
        if holding or goal is None or math.dist(pose[:2], goal) < .18:
            self.anchor, self.progress_tick, self.until = pose[:2], tick, 0
            return None
        if self.anchor is None or math.dist(self.anchor, pose[:2]) > .06:
            self.anchor, self.progress_tick = pose[:2], tick
        if tick >= self.until and tick-self.progress_tick < 300:
            return None
        captured = scan.get('captured_tick')
        if type(captured) is not int or not 0 <= tick-captured <= 20:
            return None
        ranges = scan.get('ranges_m', [])
        amin = scan.get('angle_min_rad', -math.pi)
        step = scan.get('angle_increment_rad', 2*math.pi/max(1, len(ranges)))
        rear = [r for i, r in enumerate(ranges) if abs(wrap(amin+i*step-math.pi)) < math.radians(30)]
        rear_clear = len(rear) >= 3 and all(type(r) in (int, float) and math.isfinite(r) and r > .5 for r in rear)
        if tick >= self.until:
            if not rear_clear:
                return None
            self.until, self.mode = tick+200, 'reverse'
        if self.mode == 'reverse':
            if not rear_clear:
                self.until = 0
                return None
            return (-.12, 0.)
        return None
