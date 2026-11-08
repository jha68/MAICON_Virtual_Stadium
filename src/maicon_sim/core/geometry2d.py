"""Deterministic planar convex geometry. Lengths are metres, yaw is CCW."""
from __future__ import annotations
import math
from typing import Sequence
import numpy as np

EPS = 1e-9

def pose_values(pose):
    if isinstance(pose, dict):
        return pose['x_m'], pose['y_m'], pose['yaw_rad']
    if hasattr(pose, 'x_m'):
        return pose.x_m, pose.y_m, pose.yaw_rad
    return pose

def wrap_angle(angle: float) -> float:
    return (angle + math.pi) % (2 * math.pi) - math.pi

def rotation2(yaw: float) -> np.ndarray:
    c, s = math.cos(yaw), math.sin(yaw)
    return np.array([[c, -s], [s, c]], dtype=np.float64)

def obb_corners(pose, length: float = .23, width: float = .25) -> np.ndarray:
    x, y, yaw = pose_values(pose)
    local = np.array([[-length/2,-width/2],[length/2,-width/2],
                      [length/2,width/2],[-length/2,width/2]], dtype=np.float64)
    return local @ rotation2(yaw).T + [x, y]

footprint = obb_corners

def convex_hull(points: Sequence) -> np.ndarray:
    points = sorted(set(tuple(map(float, p)) for p in points))
    if len(points) < 3:
        return np.asarray(points, dtype=np.float64)
    def cross(o,a,b): return (a[0]-o[0])*(b[1]-o[1])-(a[1]-o[1])*(b[0]-o[0])
    lower = []
    for p in points:
        while len(lower)>=2 and cross(lower[-2],lower[-1],p)<=0: lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(points):
        while len(upper)>=2 and cross(upper[-2],upper[-1],p)<=0: upper.pop()
        upper.append(p)
    return np.asarray(lower[:-1]+upper[:-1],dtype=np.float64)

def sat_intersects(a, b, padding: float = 0.0, touching: bool = True) -> bool:
    """Separating-axis test, with conservative Minkowski padding."""
    a,b=np.asarray(a,dtype=np.float64),np.asarray(b,dtype=np.float64)
    for p in (a,b):
        for d in np.roll(p,-1,axis=0)-p:
            n=np.array([-d[1],d[0]])
            norm=np.linalg.norm(n)
            if norm<EPS: continue
            n/=norm
            ap,bp=a@n,b@n
            gap=max(float(bp.min()-ap.max()),float(ap.min()-bp.max()))
            if gap > padding+EPS if touching else gap >= padding-EPS:
                return False
    return True

polygons_intersect = sat_intersects

def point_in_polygon(point, polygon, strict: bool = False) -> bool:
    p=np.asarray(point,dtype=float); poly=np.asarray(polygon,dtype=float)
    inside=False
    for a,b in zip(poly,np.roll(poly,-1,axis=0)):
        ab=b-a; ap=p-a
        cross=ab[0]*ap[1]-ab[1]*ap[0]
        if abs(cross)<EPS and np.dot(ap,p-b)<=EPS:
            return not strict
        if (a[1]>p[1]) != (b[1]>p[1]):
            x=(b[0]-a[0])*(p[1]-a[1])/(b[1]-a[1])+a[0]
            if p[0]<x: inside=not inside
    return inside

def segments_intersect(a,b,c,d) -> bool:
    a,b,c,d=map(lambda p:np.asarray(p,dtype=float),(a,b,c,d))
    def orient(p,q,r):
        x=q-p; y=r-p
        return float(x[0]*y[1]-x[1]*y[0])
    o1,o2,o3,o4=orient(a,b,c),orient(a,b,d),orient(c,d,a),orient(c,d,b)
    if o1*o2 < -EPS and o3*o4 < -EPS: return True
    for o,p,q,r in ((o1,a,b,c),(o2,a,b,d),(o3,c,d,a),(o4,c,d,b)):
        if abs(o)<=EPS and np.all(r>=np.minimum(p,q)-EPS) and np.all(r<=np.maximum(p,q)+EPS): return True
    return False

def segment_intersects_polygon(segment, polygon) -> bool:
    a,b=segment
    return point_in_polygon(a,polygon) or point_in_polygon(b,polygon) or any(
        segments_intersect(a,b,c,d) for c,d in zip(polygon,np.roll(polygon,-1,axis=0)))

def polygon_area(polygon) -> float:
    p=np.asarray(polygon,dtype=float)
    return float(np.sum(p[:,0]*np.roll(p[:,1],-1)-p[:,1]*np.roll(p[:,0],-1))/2)
