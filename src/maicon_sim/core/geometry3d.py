"""Canonical analytic 3D rays and camera transforms shared by both backends.

SIM-3D-GEOM and SIM-3D-CAM are synthetic assumptions, not measured hardware.
"""
from __future__ import annotations
import math
from dataclasses import dataclass
import numpy as np
from .geometry2d import pose_values

R_BO=np.array([[0.,0.,1.],[-1.,0.,0.],[0.,-1.,0.]])
EPS=1e-9

def rotation_z(a):
    c,s=math.cos(a),math.sin(a)
    return np.array([[c,-s,0.],[s,c,0.],[0.,0.,1.]])

def rotation_y(a):
    c,s=math.cos(a),math.sin(a)
    return np.array([[c,0.,s],[0.,1.,0.],[-s,0.,c]])

rz=rotation_z
ry=rotation_y

def body_transform(pose):
    x,y,yaw=pose_values(pose)
    return np.array([x,y,0.]),rotation_z(yaw)

def gimbal_rotation(pan,tilt):
    return rotation_z(-math.radians(pan*.5)) @ rotation_y(-math.radians(tilt*.15))

def camera_transform(pose,pan_wire=0.,tilt_wire=0.,geometry=None):
    geometry=geometry or {}
    p,R=body_transform(pose); G=gimbal_rotation(pan_wire,tilt_wire)
    pivot=np.asarray(geometry.get('gimbal_pivot_m',[.02,0,.23]))
    offset=np.asarray(geometry.get('camera_offset_gimbal_m',[.025,0,0]))
    return p+R@pivot+R@G@offset,R@G@R_BO

def laser_transform(pose,pan_wire=0.,tilt_wire=0.,geometry=None):
    geometry=geometry or {}
    p,R=body_transform(pose); G=gimbal_rotation(pan_wire,tilt_wire)
    return (p+R@np.asarray(geometry.get('gimbal_pivot_m',[.02,0,.23]))+
            R@G@np.asarray(geometry.get('laser_offset_gimbal_m',[.025,0,.02])),R@G@np.array([1.,0.,0.]))

def project_points(points_world,origin,R_WO,intrinsics):
    points=np.asarray(points_world,dtype=float).reshape(-1,3)
    optical=(points-np.asarray(origin))@np.asarray(R_WO)
    z=optical[:,2]
    safe=np.where(np.abs(z)<1e-15,1e-15,z)
    fx=intrinsics.get('fx_px',intrinsics.get('fx',320.))
    fy=intrinsics.get('fy_px',intrinsics.get('fy',320.))
    cx=intrinsics.get('cx_px',intrinsics.get('cx',319.5))
    cy=intrinsics.get('cy_px',intrinsics.get('cy',239.5))
    return np.column_stack([fx*optical[:,0]/safe+cx,fy*optical[:,1]/safe+cy]),z

def project(point_optical,intrinsics=None):
    return project_points([point_optical],[0,0,0],np.eye(3),intrinsics or {})[0][0]

@dataclass(frozen=True)
class Primitive:
    geometry_id: str
    kind: str
    center: object
    half_extents: object = None
    rotation: object = None
    radius: float = 0.
    owner: str = ''
    receiver: bool = False

@dataclass(frozen=True)
class RayHit:
    distance: float
    geometry_id: str
    owner: str
    kind: str
    receiver: bool = False


def ray_obb(origin,direction,center,half_extents,rotation=None):
    R=np.eye(3) if rotation is None else np.asarray(rotation)
    o=(np.asarray(origin)-center)@R; d=np.asarray(direction)@R
    near=-math.inf; far=math.inf
    for i in range(3):
        if abs(d[i])<EPS:
            if abs(o[i])>half_extents[i]+EPS: return None
        else:
            a=(-half_extents[i]-o[i])/d[i]; b=(half_extents[i]-o[i])/d[i]
            near=max(near,min(a,b)); far=min(far,max(a,b))
            if near>far+EPS: return None
    t=near if near>EPS else far
    return float(t) if t>EPS else None

def ray_sphere(origin,direction,center,radius):
    q=np.asarray(origin)-center; d=np.asarray(direction)
    b=float(np.dot(q,d)); c=float(np.dot(q,q)-radius*radius)
    disc=b*b-c
    if disc < -EPS: return None
    root=math.sqrt(max(0.,disc)); t=-b-root
    if t<=EPS: t=-b+root
    return float(t) if t>EPS else None

def ray_rectangle(origin,direction,center,u_axis,v_axis,half_width,half_height):
    u,v=np.asarray(u_axis),np.asarray(v_axis); n=np.cross(u,v)
    denom=float(np.dot(direction,n))
    if abs(denom)<EPS:return None
    t=float(np.dot(np.asarray(center)-origin,n)/denom)
    if t<=EPS:return None
    local=np.asarray(origin)+t*np.asarray(direction)-center
    return t if abs(np.dot(local,u))<=half_width+EPS and abs(np.dot(local,v))<=half_height+EPS else None

def raycast(origin,direction,primitives,max_distance=math.inf,exclude_owner=None):
    d=np.asarray(direction,dtype=float); d=d/np.linalg.norm(d)
    hits=[]
    for p in primitives:
        if exclude_owner and p.owner==exclude_owner:continue
        t=ray_sphere(origin,d,p.center,p.radius) if p.kind=='sphere' else ray_obb(origin,d,p.center,p.half_extents,p.rotation)
        if t is not None and t<=max_distance:
            hits.append(RayHit(t,p.geometry_id,p.owner,p.kind,p.receiver))
    if not hits:return None
    first=min(h.distance for h in hits)
    tied=[h for h in hits if h.distance<=first+EPS]
    return min(tied,key=lambda h:(h.receiver,h.geometry_id))

def raycast_distances(origin,directions,primitives,max_distance=math.inf,exclude_owner=None):
    """Vectorised OBB slabs for a full LiDAR scan; no entity IDs escape."""
    directions=np.asarray(directions,dtype=float)
    result=np.full(len(directions),np.inf)
    for p in primitives:
        if (exclude_owner and p.owner==exclude_owner) or p.receiver:continue
        R=np.eye(3) if p.rotation is None else np.asarray(p.rotation)
        o=(np.asarray(origin)-p.center)@R; d=directions@R
        parallel=np.abs(d)<EPS
        safe=np.where(parallel,1.,d)
        lo=(-np.asarray(p.half_extents)-o)/safe; hi=(np.asarray(p.half_extents)-o)/safe
        near=np.where(parallel,-np.inf,np.minimum(lo,hi)).max(axis=1)
        far=np.where(parallel,np.inf,np.maximum(lo,hi)).min(axis=1)
        parallel_out=np.any(parallel & (np.abs(o)>np.asarray(p.half_extents)+EPS),axis=1)
        t=np.where(near>EPS,near,far)
        valid=(~parallel_out)&(near<=far+EPS)&(t>EPS)&(t<=max_distance)
        result=np.minimum(result,np.where(valid,t,np.inf))
    return result

def canonical_solids(robots,boxes,bounds,geometry):
    out=[]
    for b in boxes:
        p,R=body_transform(b['pose']); size=np.asarray(b['size_m'])
        out.append(Primitive(b['box_id'],'obb',p+[0,0,size[2]/2],size/2,R,owner=b['box_id']))
    w,h=bounds['width_m'],bounds['height_m']; z=bounds.get('wall_height_m',.4)/2
    t=geometry.get('wall_thickness_m',.02)
    for key,c,e in [('west',[-t/2,h/2,z],[t/2,h/2,z]),('east',[w+t/2,h/2,z],[t/2,h/2,z]),
                    ('south',[w/2,-t/2,z],[w/2,t/2,z]),('north',[w/2,h+t/2,z],[w/2,t/2,z])]:
        out.append(Primitive('wall_'+key,'obb',np.asarray(c),np.asarray(e),np.eye(3),owner='wall'))
    for slot,r in sorted(robots.items()):
        p,R=body_transform(r.pose)
        for name in ('chassis','mast'):
            spec=geometry.get(name,{'center_m':[0,0,.10],'half_extents_m':[.115,.09,.03]})
            out.append(Primitive(slot+'/'+name,'obb',p+R@np.asarray(spec['center_m']),
                                 np.asarray(spec['half_extents_m']),R,owner=slot))
    return out

FACE_AXES={
 'east':([1,0,0],[0,1,0],[0,0,1],0,1),
 'west':([-1,0,0],[0,-1,0],[0,0,1],0,-1),
 'north':([0,1,0],[-1,0,0],[0,0,1],1,1),
 'south':([0,-1,0],[1,0,0],[0,0,1],1,-1)}

def face_rectangle(box,side,image_fraction=.88):
    n,u,v,axis,sign=FACE_AXES[side]
    p,R=body_transform(box['pose']); size=np.asarray(box['size_m'])
    center_local=np.array([0.,0.,size[2]/2]); center_local[axis]=sign*(size[axis]/2+.001)
    horizontal=size[1-axis]
    return p+R@center_local,R@np.asarray(n),R@np.asarray(u),R@np.asarray(v),horizontal*image_fraction/2,size[2]*image_fraction/2

def receiver_primitives(robots,boxes,geometry):
    out=[]
    for slot,r in sorted(robots.items()):
        p,R=body_transform(r.pose)
        for i,receiver in enumerate(geometry.get('receivers',[])):
            out.append(Primitive(slot+'/receiver/'+str(i),'sphere',p+R@np.asarray(receiver['center_m']),
                                 radius=receiver['radius_m'],owner=slot,receiver=True))
    for box in boxes:
        for face in box['faces']:
            if face['kind']!='facility':continue
            n,u,v,axis,sign=FACE_AXES[face['side']]
            p,R=body_transform(box['pose'])
            local=np.array([0.,0.,geometry.get('facility_receiver_z_m',.35)])
            local[axis]=sign*(box['size_m'][axis]/2+geometry.get('facility_receiver_offset_m',.021))
            code=face['facility_code']
            out.append(Primitive(code+'/receiver','sphere',p+R@local,
                                 radius=geometry.get('facility_receiver_radius_m',.02),owner=code,receiver=True))
    return out

def laser_contacts(robots,boxes,bounds,sensors):
    geometry=sensors.get('geometry',sensors)
    shapes=canonical_solids(robots,boxes,bounds,geometry)+receiver_primitives(robots,boxes,geometry)
    out=set()
    for slot,r in sorted(robots.items()):
        o,d=laser_transform(r.pose,r.pan,r.tilt,geometry)
        hit=raycast(o,d,shapes,max_distance=20,exclude_owner=slot)
        if hit is not None and hit.receiver:
            receiver_key=hit.geometry_id if '/receiver/' in hit.geometry_id else hit.owner
            out.add((slot,receiver_key))
    return out
