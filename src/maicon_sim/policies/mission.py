"""Fair sector survey from public map geometry and observed local obstacles."""
import math

from .planning import inside_polygon
from .scripted import nominal_pose


class MissionSurvey:
    def __init__(self, public_map, slot):
        self.slot, self.public_map = slot, public_map
        self.blue = slot.startswith('B')
        prefix = 'R-' if self.blue else 'B-'
        self.sectors = {s['sector_id']: s for s in public_map.get('sectors', [])
                        if s['sector_id'].startswith(prefix) or s['sector_id'] == 'CM'}
        self.required = sorted(self.sectors)
        row = int(slot[-1])-1
        order = [f'{prefix}S{(row+i)%3+1}' for i in range(3)] + ['CM']
        by_sector = []
        for name in order:
            if name not in self.sectors:
                continue
            poly = self.sectors[name]['polygon_xy_m']
            x0, x1 = min(p[0] for p in poly), max(p[0] for p in poly)
            y0, y1 = min(p[1] for p in poly), max(p[1] for p in poly)
            dx, dy = min(.33, (x1-x0)/3), min(.33, (y1-y0)/3)
            points = [(x0+dx, y0+dy), (x1-dx, y1-dy)]
            if not self.blue:
                points.reverse()
            by_sector.append((name, points))
        # Visit every sector before spending time on its second viewing angle.
        self.vantages = [(name, points[view]) for view in (0, 1) for name, points in by_sector]
        self.index, self.visited = 0, set()
        self.active_sector, self.target = None, None
        self.target_since = 0
        self.last_position, self.last_progress = None, 0
        self.sweep_until = None
        self.sweeping = False
        self.failed = set()
        start = nominal_pose(public_map, slot)
        bounds = public_map.get('bounds', {})
        w, h = bounds.get('width_m', 6.12), bounds.get('height_m', 5.)
        # Each camp keeps to its right on departure, using only its public prior.
        self.departure = ((.7 if self.blue else w-.7), min(h-.25, max(.25, start[1]+(-.3 if self.blue else .3)))) if start else None

    def goal(self, pose, tick, grid, hazards=()):
        for name, sector in self.sectors.items():
            if inside_polygon(pose[:2], sector['polygon_xy_m']):
                self.visited.add(name)
        self.sweeping = False
        if self.departure:
            if math.dist(pose[:2], self.departure) > .15:
                return self.departure
            self.departure = None
        if not self.vantages:
            return None
        if self.sweep_until is not None:
            if tick < self.sweep_until:
                self.sweeping = True
                return self.target
            self.sweep_until = None
            self.index += 1
            self.target = None
        if self.last_position is None or math.dist(pose[:2], self.last_position) > .06:
            self.last_position, self.last_progress = pose[:2], tick
        if self.target is not None and math.dist(pose[:2], self.target) < .18:
            self.sweep_until = tick+650
            self.sweeping = True
            return self.target
        if self.target is not None and tick-self.last_progress > 800:
            # Revisit a blocked vantage on the next circuit; do not call it surveyed.
            self.failed.add(grid.cell(*self.target))
            self.index += 1
            self.target = None
            self.last_progress = tick
        blocked = grid.inflated()
        if self.target is not None:
            cell = grid.cell(*self.target)
            if not blocked[cell[1], cell[0]] and cell not in hazards:
                return self.target
            self.target = None
        self.active_sector, desired = self.vantages[self.index % len(self.vantages)]
        polygon = self.sectors[self.active_sector]['polygon_xy_m']
        candidates = []
        for y in range(4, grid.cells.shape[0]-4, 2):
            for x in range(4, grid.cells.shape[1]-4, 2):
                cell = (x,y)
                if blocked[y,x] or cell in hazards or cell in self.failed:
                    continue
                point = grid.center(cell)
                if inside_polygon(point, polygon):
                    candidates.append((math.dist(point,desired), point))
        if candidates:
            self.target = min(candidates)[1]
            self.target_since = tick
        elif tick-self.last_progress > 400:
            self.index += 1
            self.last_progress = tick
            self.failed.clear()
        return self.target
