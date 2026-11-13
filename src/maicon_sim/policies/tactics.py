"""Conservative navigation/evasion from public pixels and scan returns only."""
import math

from .planning import OccupancyGrid, FREE, OCCUPIED, inside_polygon, wrap


class TacticalNavigator:
    def __init__(self, camp):
        self.camp = camp
        self.last_hp = None
        self.last_state_tick = -1
        self._obstacle_key = None
        self._obstacle_cells = set()
        self.damage_until = -1

    def navigation(self, drone, tick, own_capture_pose, grid):
        """One transient layer: never mark unseen floor free or mutate LiDAR map.

        Robot observations expire after 1.5s even on the 5s degraded feed. Loss
        of service drops the entire layer; the local scan remains authoritative.
        """
        frame = drone.get('visual') or {}
        captured = frame.get('captured_tick')
        if drone.get('status') != 'available' or type(captured) is not int or not 0 <= tick-captured <= 150:
            return set(), [], None
        navigation = frame.get('navigation', {})
        if navigation.get('source') != 'calibrated_overhead_pixels':
            return set(), [], None
        key = (captured, grid.width_m, grid.height_m, grid.resolution)
        if self._obstacle_key != key:
            self._obstacle_cells = self._static_obstacles(navigation, grid)
            self._obstacle_key = key
        # LiDAR-confirmed free centre cells take precedence over the uncertain
        # overhead height/footprint prior. The grid still inflates actual scan
        # obstacles, preserving narrow measured corridors without inventing free space.
        inflated = grid.inflated()
        forbidden = {c for c in self._obstacle_cells
                     if grid.cells[c[1], c[0]] != FREE or inflated[c[1], c[0]]}
        opponents = []
        for robot in navigation.get('robots', [])[:24]:
            point = robot.get('position_xy_m', [])
            if len(point) != 2 or not all(math.isfinite(v) for v in point) or not grid.valid(grid.cell(*point)):
                continue
            # A coloured overhead body has no call sign. Ignore only the body
            # consistent with our own capture-time odometry, not all teammates.
            if robot.get('camp') == self.camp and own_capture_pose and math.dist(point, own_capture_pose[:2]) < .35:
                continue
            uncertainty = robot.get('uncertainty_m', .18)
            radius = .36 + max(.1, min(.3, uncertainty)) + .6*(tick-captured)/100
            a, b = grid.cell(point[0]-radius, point[1]-radius), grid.cell(point[0]+radius, point[1]+radius)
            for y in range(max(0, a[1]), min(grid.cells.shape[0], b[1]+1)):
                for x in range(max(0, a[0]), min(grid.cells.shape[1], b[0]+1)):
                    if math.dist(grid.center((x, y)), point) <= radius:
                        forbidden.add((x, y))
            if robot.get('camp') in ('BLUE', 'RED') and robot['camp'] != self.camp:
                opponents.append(tuple(point))
        return forbidden, opponents, captured

    @staticmethod
    def _static_obstacles(navigation, grid):
        layer = OccupancyGrid(grid.width_m, grid.height_m, grid.resolution)
        for obstacle in navigation.get('obstacles', [])[:64]:
            polygon = obstacle.get('polygon_xy_m', [])
            if not 4 <= len(polygon) <= 16 or not all(len(p) == 2 and all(math.isfinite(v) for v in p) for p in polygon):
                continue
            xs, ys = [p[0] for p in polygon], [p[1] for p in polygon]
            a, b = layer.cell(min(xs), min(ys)), layer.cell(max(xs), max(ys))
            for y in range(max(0, a[1]), min(layer.cells.shape[0], b[1]+1)):
                for x in range(max(0, a[0]), min(layer.cells.shape[1], b[0]+1)):
                    if inside_polygon(layer.center((x, y)), polygon):
                        layer.cells[y, x] = OCCUPIED
        blocked = layer.inflated(radius_m=.25)
        boundary = OccupancyGrid(grid.width_m, grid.height_m, grid.resolution).inflated(radius_m=.25)
        blocked = blocked & ~boundary
        return {(int(x), int(y)) for y, x in zip(*blocked.nonzero())}

    @staticmethod
    def cue_gimbal(pose, opponents):
        """Search cue only. Firing still needs fresh front-camera receiver proof."""
        if not opponents:
            return None
        point = min(opponents, key=lambda p: math.dist(pose[:2], p))
        angle = wrap(math.atan2(point[1]-pose[1], point[0]-pose[0])-pose[2])
        return (max(-100., min(100., -math.degrees(angle)/.5)), 0., 60., 20.)

    @staticmethod
    def _clear_path(pose, angle, scan, grid, forbidden):
        """Require actual LiDAR samples for an entire swept retreat corridor."""
        ranges = scan.get('ranges_m', [])
        if not ranges:
            return False
        amin, step = scan.get('angle_min_rad', -math.pi), scan.get('angle_increment_rad', 2*math.pi/len(ranges))
        relevant = [r for i, r in enumerate(ranges) if abs(wrap(amin+i*step-angle)) < math.radians(28)]
        if len(relevant) < 3 or any(type(r) not in (int, float) or not math.isfinite(r) or r < .65 for r in relevant):
            return False
        for distance in (.1, .2, .3):
            cell = grid.cell(pose[0]+distance*math.cos(pose[2]+angle), pose[1]+distance*math.sin(pose[2]+angle))
            if not grid.valid(cell) or grid.inflated()[cell[1], cell[0]] or cell in forbidden:
                return False
        return True

    def evade(self, pose, observations, semantic, tick, grid, forbidden, opponents):
        state = observations.get('state', {})
        hp = state.get('hp')
        state_tick = state.get('captured_tick')
        if type(hp) is int and type(state_tick) is int and state_tick > self.last_state_tick and 0 <= tick-state_tick <= 150:
            self.last_state_tick = state_tick
            if self.last_hp is not None and hp < self.last_hp:
                self.damage_until = tick+150
            self.last_hp = hp
        close = any(math.dist(pose[:2], p) < 1.1 for p in opponents)
        captured = semantic.get('captured_tick')
        if type(captured) is int and 0 <= tick-captured <= 30:
            for item in semantic.get('detections', []):
                marker = item.get('marker_readout', {})
                distance = item.get('range_m')
                if item.get('kind') == 'ugv' and marker.get('camp') != self.camp and marker.get('camp') in ('BLUE', 'RED') and marker.get('confidence', 0) >= .75 and type(distance) in (int, float) and .15 < distance < 1.1:
                    close = True
        if not close and tick >= self.damage_until:
            return None
        scan = observations.get('scan', {})
        if type(scan.get('captured_tick')) is not int or not 0 <= tick-scan['captured_tick'] <= 20:
            return (0., 0.)
        # Differential drive can retreat without an unsafe lateral translation.
        # With unknown/blocked rear clearance, stop; do not guess a free escape.
        if self._clear_path(pose, math.pi, scan, grid, forbidden):
            return (-.12, 0.)
        return (0., 0.)
