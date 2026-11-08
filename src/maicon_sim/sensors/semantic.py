"""Synthetic 2D visual detections: projection and 3x3 occlusion, never IDs."""
from __future__ import annotations
import math
import numpy as np
from ..core.geometry3d import camera_transform, project_points, raycast, raycast_distances, face_rectangle, canonical_solids,body_transform

CLASSES=('military_truck','mortar','tank','missile','ammo_box','drum')
FACILITIES=('COMMS','OUTPOST','RADAR')

def visible_rectangle(origin,R,intrinsics,rectangle,solids,exclude_owner=None):
    center,n,u,v,hw,hh=rectangle
    view=np.asarray(origin)-center
    if np.linalg.norm(view)<1e-9 or np.dot(n,view)/np.linalg.norm(view)<=.1:return None
    corners=[center+a*hw*u+b*hh*v for a,b in [(-1,-1),(1,-1),(1,1),(-1,1)]]
    xy,z=project_points(corners,origin,R,intrinsics)
    if z.min()<=intrinsics.get('near_m',.02) or z.max()>=intrinsics.get('far_m',10):return None
    w,h=intrinsics.get('width_px',640),intrinsics.get('height_px',480)
    bbox=[max(0.,float(xy[:,0].min())),max(0.,float(xy[:,1].min())),
          min(float(w),float(xy[:,0].max())),min(float(h),float(xy[:,1].max()))]
    if bbox[2]-bbox[0]<4 or bbox[3]-bbox[1]<4:return None
    points=np.asarray([center+a*hw*u+b*hh*v for a in (-2/3,0,2/3) for b in (-2/3,0,2/3)])
    deltas=points-origin;distances=np.linalg.norm(deltas,axis=1)
    nearest=raycast_distances(origin,deltas/distances[:,None],solids,exclude_owner=exclude_owner)
    return bbox if int(np.count_nonzero(nearest>=distances-1e-6))>=5 else None

def semantic_candidates(robots,boxes,bounds,sensors,slot,solids=None):
    geometry=sensors['geometry']; intrinsics=sensors['front_camera']; robot=robots[slot]
    origin,R=camera_transform(robot.pose,robot.pan,robot.tilt,geometry)
    if solids is None:solids=canonical_solids(robots,boxes,bounds,geometry)
    candidates=[]
    for box in sorted(boxes,key=lambda b:b['box_id']):
        for face in sorted(box['faces'],key=lambda f:f['side']):
            if face['kind'] not in ('object','facility'):continue
            bbox=visible_rectangle(origin,R,intrinsics,face_rectangle(box,face['side']),solids)
            if bbox is None:continue
            kind=face['kind']; label=face['object_class'].lower() if kind=='object' else face['facility_code'].split('_',1)[1]
            candidates.append({'kind':kind,'bbox_xyxy_px':bbox,'label':label})
    for other,r in sorted(robots.items()):
        if other==slot:continue
        p,RB=body_transform(r.pose);spec=geometry['chassis']; center=p+RB@np.asarray(spec['center_m']);half=np.asarray(spec['half_extents_m'])
        variants=[]
        for axis in (0,1,2):
            for sign in (-1,1):
                normal=RB[:,axis]*sign
                i,j=[k for k in range(3) if k!=axis]
                variants.append((center+normal*half[axis],normal,RB[:,i],RB[:,j],half[i],half[j]))
        rect=max(variants,key=lambda rect:float(np.dot(rect[1],origin-rect[0])/np.linalg.norm(origin-rect[0])))
        bbox=visible_rectangle(origin,R,intrinsics,rect,solids,exclude_owner=other)
        if bbox is None:continue
        corners=np.array([center+RB@np.array([a*half[0],b*half[1],c*half[2]]) for a in (-1,1) for b in (-1,1) for c in (-1,1)])
        xy,z=project_points(corners,origin,R,intrinsics)
        if z.min()>.02:
            bbox=[max(0.,float(xy[:,0].min())),max(0.,float(xy[:,1].min())),min(640.,float(xy[:,0].max())),min(480.,float(xy[:,1].max()))]
        candidate={'kind':'ugv','bbox_xyxy_px':bbox,'label':'UGV'}
        if 'marker_center_m' in geometry:
            mc=p+RB@np.asarray(geometry['marker_center_m'])
            marker_rect=(mc,RB[:,0] if np.dot(RB[:,0],origin-mc)>0 else -RB[:,0],RB[:,1],RB[:,2],geometry['marker_width_m']/2,geometry['marker_height_m']/2)
            marker=visible_rectangle(origin,R,intrinsics,marker_rect,solids)
            if marker is not None:
                candidate['marker_readout']={'camp':'BLUE' if other.startswith('B') else 'RED','band_count':int(other[-1]),'confidence':1.}
        candidates.append(candidate)
    return candidates

def apply_noise(candidates,noise,rng,width=640,height=480):
    result=[]
    for candidate in candidates:
        if rng.random()<noise.get('semantic_miss_p',0):continue
        kind=candidate['kind']; label=candidate['label']
        if kind=='object' and rng.random()<noise.get('semantic_wrong_class_p',0):
            label=str(rng.choice([c for c in CLASSES if c!=label]))
        keys=CLASSES if kind=='object' else FACILITIES if kind=='facility' else ('UGV',)
        if kind=='object' and noise.get('semantic_wrong_class_p',0)>0:
            probs={key:(.95 if key==label else .01) for key in keys}
        else:probs={key:float(key==label) for key in keys}
        bbox=np.asarray(candidate['bbox_xyxy_px'])+rng.normal(0,noise.get('bbox_sigma_px',0),4)
        bbox[[0,2]]=np.clip(bbox[[0,2]],0,width);bbox[[1,3]]=np.clip(bbox[[1,3]],0,height)
        if bbox[0]>=bbox[2] or bbox[1]>=bbox[3]:continue
        d={'kind':kind,'bbox_xyxy_px':bbox.tolist(),'class_probs':probs,'confidence':max(probs.values())}
        if 'marker_readout' in candidate:d['marker_readout']=dict(candidate['marker_readout'])
        result.append(d)
    for _ in range(rng.poisson(noise.get('semantic_fp_poisson',0))):
        w,h=rng.uniform(8,80,2);x=rng.uniform(0,width-w);y=rng.uniform(0,height-h);label=str(rng.choice(CLASSES))
        result.append({'kind':'object','bbox_xyxy_px':[x,y,x+w,y+h],'class_probs':{key:float(key==label) for key in CLASSES},'confidence':.5})
    return result
