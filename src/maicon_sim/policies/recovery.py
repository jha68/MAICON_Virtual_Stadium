"""Bounded stall recovery using only the participant's fresh LiDAR and odometry."""
import math

from .planning import wrap


class MotionRecovery:
    def __init__(self):
        self.anchor = None
        self.progress_tick = None
        self.until = 0
        self.mode = None
        self.heading = None

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
        def valid(r):
            return type(r) in (int, float) and math.isfinite(r)
        def clearance(angle):
            values = [r for i, r in enumerate(ranges) if abs(wrap(amin+i*step-angle)) < math.radians(30)]
            return min(values) if len(values) >= 3 and all(valid(r) for r in values) else 0.
        # A complete revolution must be sampled before rotating a rectangular
        # footprint. This margin includes its circumscribed radius and LiDAR offset.
        rotation_room = (len(ranges) >= 36 and abs(step)*len(ranges) >= 2*math.pi-.1
                         and all(valid(r) and r > .22 for r in ranges))
        if tick >= self.until:
            if clearance(math.pi) > .5:
                self.until, self.mode = tick+200, 'reverse'
            elif rotation_room:
                angles = [math.radians(v) for v in (-135, -90, -45, 0, 45, 90, 135)]
                angle = max(angles, key=clearance)
                if clearance(angle) <= .5:
                    return None
                self.heading, self.mode, self.until = wrap(pose[2]+angle), 'turn', tick+600
            else:
                return None
        if self.mode == 'turn':
            error = wrap(self.heading-pose[2])
            if abs(error) > .15:
                if not rotation_room:
                    self.until = 0
                    return None
                return (0., max(-.8, min(.8, error*2)))
            self.mode, self.until = 'forward', tick+200
        direction = math.pi if self.mode == 'reverse' else 0.
        if clearance(direction) <= .5:
            self.until = 0
            return None
        return (-.12 if self.mode == 'reverse' else .12, 0.)
