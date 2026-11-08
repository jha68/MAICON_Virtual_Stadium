"""Shared kinematic integrator; Bullet never advances these poses."""
from __future__ import annotations
import math
from functools import lru_cache
import numpy as np
from .geometry2d import pose_values, wrap_angle, obb_corners, convex_hull, sat_intersects


@lru_cache(maxsize=512)
def _cached_footprint(pose,length,width):
    return obb_corners(pose,length,width)

@lru_cache(maxsize=32)
def _cached_obstacles(signature):
    return tuple(obb_corners(pose,length,width) for pose,length,width in signature)

def _aabb(poly):
    return (float(poly[:,0].min()),float(poly[:,1].min()),float(poly[:,0].max()),float(poly[:,1].max()))

def _near_bounds(a,b,pad=0):
    return not (a[2]+pad<b[0] or b[2]+pad<a[0] or a[3]+pad<b[1] or b[3]+pad<a[1])

def make_pose_like(pose, x, y, yaw):
    if isinstance(pose,dict): return dict(x_m=float(x),y_m=float(y),yaw_rad=float(yaw))
    if hasattr(pose,'x_m'): return type(pose)(float(x),float(y),float(yaw))
    return (float(x),float(y),float(yaw))

def integrate_twist(pose, v: float, omega: float, dt: float):
    if not all(math.isfinite(float(a)) for a in (*pose_values(pose),v,omega,dt)) or dt<0:
        raise ValueError('finite pose, twist, nonnegative dt required')
    x,y,yaw=pose_values(pose); next_yaw=yaw+omega*dt
    if abs(omega)<1e-8:
        x+=v*dt*math.cos(yaw); y+=v*dt*math.sin(yaw)
    else:
        x+=v/omega*(math.sin(next_yaw)-math.sin(yaw))
        y-=v/omega*(math.cos(next_yaw)-math.cos(yaw))
    return make_pose_like(pose,x,y,wrap_angle(next_yaw))

integrate = integrate_twist

def move_robots(robots, boxes, bounds, geometry, dt=.01):
    """Simultaneous swept OBB fixed point collision resolution.

    Returns new poses. Inputs are never mutated. Conservative arcs are bounded
    by the documented sagitta plus 1 micrometre, with 2 mm corner microsteps.
    """
    length=geometry.get('footprint_length_m',.23); width=geometry.get('footprint_width_m',.25)
    radius=math.hypot(length/2,width/2)
    slots=sorted(robots)
    poses={s:robots[s].pose for s in slots}
    twists={s:(float(robots[s].v),float(robots[s].omega)) for s in slots}
    travel=max([(abs(v)+radius*abs(w))*dt for v,w in twists.values()]+[0])
    if travel == 0: return poses
    n=max(1,math.ceil(travel/.002))
    if n>100000: raise ValueError('excessive kinematic microsteps: check command units')
    h=dt/n
    signature=tuple((tuple(pose_values(b['pose'])),b['size_m'][0],b['size_m'][1]) for b in boxes)
    obstacle=_cached_obstacles(signature)
    obstacle_bounds=[_aabb(o) for o in obstacle]
    bw,bh=bounds['width_m'],bounds['height_m']
    for _ in range(n):
        starts={s:_cached_footprint(tuple(pose_values(poses[s])),length,width) for s in slots}
        moving={s for s in slots if twists[s]!=(0.,0.)}
        cand={s:integrate_twist(poses[s],*twists[s],h) if s in moving else poses[s] for s in slots}
        hulls={s:convex_hull(np.concatenate([starts[s],obb_corners(cand[s],length,width)])) if s in moving else starts[s] for s in slots}
        hull_bounds={s:_aabb(hulls[s]) for s in slots}
        start_bounds={s:_aabb(starts[s]) for s in slots}
        padding={}
        blocked=set()
        for s in slots:
            if s not in moving:
                padding[s]=0.
                continue
            v,w=twists[s]; delta=abs(w*h)
            sag=(abs(v/w)+radius)*2*math.sin(delta/4)**2 if abs(w)>=1e-8 else abs(v*w)*h*h/8+radius*delta*delta/8
            pad=padding[s]=sag+1e-6
            hull=hulls[s]
            if (hull[:,0].min()<pad or hull[:,1].min()<pad or
                hull[:,0].max()>bw-pad or hull[:,1].max()>bh-pad or
                any(_near_bounds(hull_bounds[s],ob,pad) and sat_intersects(hull,o,padding=pad) for o,ob in zip(obstacle,obstacle_bounds))):
                blocked.add(s)
        while True:
            before=set(blocked)
            for i,s in enumerate(slots):
                for t in slots[i+1:]:
                    if s not in moving and t not in moving:continue
                    a=starts[s] if s in blocked else hulls[s]
                    b=starts[t] if t in blocked else hulls[t]
                    pad=(0 if s in blocked else padding[s])+(0 if t in blocked else padding[t])
                    ba=start_bounds[s] if s in blocked else hull_bounds[s]
                    bb=start_bounds[t] if t in blocked else hull_bounds[t]
                    if _near_bounds(ba,bb,pad) and sat_intersects(a,b,padding=pad): blocked.update((s,t))
            if blocked==before: break
        poses={s:poses[s] if s in blocked else cand[s] for s in slots}
    return poses
