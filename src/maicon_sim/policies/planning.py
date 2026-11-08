"""Public-observation occupancy mapping and conservative 8-neighbour A*."""
from __future__ import annotations

import heapq
import math
from typing import Iterable

import numpy as np

UNKNOWN, FREE, OCCUPIED = -1, 0, 1


def wrap(angle: float) -> float:
    return (angle + math.pi) % (2 * math.pi) - math.pi


def inside_polygon(point: tuple[float, float], polygon: Iterable) -> bool:
    """Even/odd winding test, including an exact polygon boundary."""
    vertices = list(polygon)
    x, y = point
    result = False
    for i, (ax, ay) in enumerate(vertices):
        bx, by = vertices[(i + 1) % len(vertices)]
        cross = (x - ax) * (by - ay) - (y - ay) * (bx - ax)
        if abs(cross) < 1e-9 and min(ax, bx) - 1e-9 <= x <= max(ax, bx) + 1e-9 and min(ay, by) - 1e-9 <= y <= max(ay, by) + 1e-9:
            return True
        if (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / (by - ay) + ax:
            result = not result
    return result


class OccupancyGrid:
    """Unknown cells cost three times free; only observed obstacles are inflated."""

    def __init__(self, width_m: float, height_m: float, resolution: float = .05):
        self.resolution = resolution
        self.width_m, self.height_m = width_m, height_m
        self.cells = np.full((math.ceil(height_m / resolution), math.ceil(width_m / resolution)), UNKNOWN, dtype=np.int8)
        self.revision = 0
        self._inflated_revision = -1
        self._inflated = None

    def cell(self, x: float, y: float) -> tuple[int, int]:
        return int(math.floor(x / self.resolution)), int(math.floor(y / self.resolution))

    def center(self, cell: tuple[int, int]) -> tuple[float, float]:
        return ((cell[0] + .5) * self.resolution, (cell[1] + .5) * self.resolution)

    def valid(self, cell: tuple[int, int]) -> bool:
        x, y = cell
        return 0 <= x < self.cells.shape[1] and 0 <= y < self.cells.shape[0]

    def set_cell(self, cell: tuple[int, int], value: int):
        if self.valid(cell):
            self.cells[cell[1], cell[0]] = value
            self.revision += 1

    def update_scan(self, pose: tuple[float, float, float], scan: dict):
        """Mark ray interiors free and finite returns occupied; no-return has no invented endpoint."""
        x, y, yaw = pose
        start = self.cell(x, y)
        ranges = scan.get("ranges_m", [])
        angle_min = scan.get("angle_min_rad", -math.pi)
        inc = scan.get("angle_increment_rad", 2 * math.pi / max(1, len(ranges)))
        max_range = scan.get("range_max_m", 8.)
        hits = []
        for i, distance in enumerate(ranges):
            if distance is None:
                # A no-return is unknown, not proof that the entire ray is free.
                continue
            if not math.isfinite(distance) or distance <= 0:
                continue
            distance = min(distance, max_range)
            angle = yaw + angle_min + i * inc
            end = self.cell(x + distance * math.cos(angle), y + distance * math.sin(angle))
            count = max(abs(end[0] - start[0]), abs(end[1] - start[1])) + 1
            xs = np.rint(np.linspace(start[0], end[0], count)).astype(np.int64)
            ys = np.rint(np.linspace(start[1], end[1], count)).astype(np.int64)
            valid = (xs >= 0) & (ys >= 0) & (xs < self.cells.shape[1]) & (ys < self.cells.shape[0])
            # Occupied endpoints are written together after clearing interiors.
            self.cells[ys[:-1][valid[:-1]], xs[:-1][valid[:-1]]] = FREE
            if self.valid(end):
                hits.append(end)
        for hx, hy in hits:
            self.cells[hy, hx] = OCCUPIED
        if self.valid(start):
            self.cells[start[1], start[0]] = FREE
        self.revision += 1

    def inflated(self, radius_m: float = math.hypot(.115, .125) + .01) -> np.ndarray:
        if self._inflated_revision == self.revision:
            return self._inflated
        radius = math.ceil(radius_m / self.resolution)
        result = self.cells == OCCUPIED
        occupied = np.argwhere(result)
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if math.hypot(dx, dy) * self.resolution > radius_m + self.resolution * math.sqrt(2) / 2:
                    continue
                if len(occupied):
                    ys, xs = occupied[:, 0] + dy, occupied[:, 1] + dx
                    valid = (xs >= 0) & (ys >= 0) & (xs < result.shape[1]) & (ys < result.shape[0])
                    result[ys[valid], xs[valid]] = True
        # The footprint must also remain within the known arena boundary.
        margin = math.ceil(radius_m / self.resolution)
        result[:margin, :] = result[-margin:, :] = True
        result[:, :margin] = result[:, -margin:] = True
        self._inflated, self._inflated_revision = result, self.revision
        return result

    def astar(self, start: tuple[int, int], goal: tuple[int, int], forbidden: set[tuple[int, int]] | None = None) -> list[tuple[int, int]]:
        forbidden = forbidden or set()
        blocked = self.inflated()
        def traversable(c):
            return self.valid(c) and not blocked[c[1], c[0]] and c not in forbidden
        if not traversable(start) or not traversable(goal):
            return []
        queue = [(math.dist(start, goal), 0., start)]
        costs = {start: 0.}
        previous = {}
        while queue:
            _, cost, current = heapq.heappop(queue)
            if cost != costs.get(current):
                continue
            if current == goal:
                path = [current]
                while current in previous:
                    current = previous[current]
                    path.append(current)
                return list(reversed(path))
            for dx, dy in ((-1, 0), (0, -1), (0, 1), (1, 0), (-1, -1), (-1, 1), (1, -1), (1, 1)):
                candidate = (current[0] + dx, current[1] + dy)
                if not traversable(candidate):
                    continue
                if dx and dy and (not traversable((current[0] + dx, current[1])) or not traversable((current[0], current[1] + dy))):
                    continue
                step = math.hypot(dx, dy) * (3. if self.cells[candidate[1], candidate[0]] == UNKNOWN else 1.)
                new = cost + step
                if new < costs.get(candidate, math.inf):
                    costs[candidate], previous[candidate] = new, current
                    heapq.heappush(queue, (new + math.dist(candidate, goal), new, candidate))
        return []

    def frontier(self, pose: tuple[float, float, float], sectors: list[dict]) -> tuple[float, float] | None:
        """Deterministic coarse frontier selection using distance and information gain."""
        blocked = self.inflated()
        candidates = []
        # Every fourth cell bounds the candidate set; A* verifies the winning path.
        for y in range(4, self.cells.shape[0] - 4, 4):
            for x in range(4, self.cells.shape[1] - 4, 4):
                if blocked[y, x]:
                    continue
                point = self.center((x, y))
                if not any(inside_polygon(point, s["polygon_xy_m"]) for s in sectors):
                    continue
                unknown = int(np.count_nonzero(self.cells[y - 3:y + 4, x - 3:x + 4] == UNKNOWN))
                if not unknown:
                    continue
                score = math.dist(pose[:2], point) - .03 * unknown
                candidates.append((score, x, y))
        for _, x, y in sorted(candidates)[:20]:
            if self.astar(self.cell(*pose[:2]), (x, y)):
                return self.center((x, y))
        return None


def follow_waypoint(pose: tuple[float, float, float], waypoint: tuple[float, float]) -> tuple[float, float]:
    dx, dy = waypoint[0] - pose[0], waypoint[1] - pose[1]
    if math.hypot(dx, dy) <= .08:
        return 0., 0.
    error = wrap(math.atan2(dy, dx) - pose[2])
    omega = max(-1.5, min(1.5, 2. * error))
    if abs(error) > math.radians(20):
        return 0., omega
    return .15, omega
