"""Analytic canonical horizontal LiDAR. No-return serialises as null."""
import math
import numpy as np
from ..core.geometry3d import body_transform,raycast_distances

def scan(robots,solids,slot,profile,noise,rng):
    p,R=body_transform(robots[slot].pose);origin=p+R@np.asarray(profile['origin_body_m'])
    angles=profile['angle_min_rad']+np.arange(profile['ray_count'])*2*math.pi/profile['ray_count']
    directions=np.column_stack([np.cos(angles),np.sin(angles),np.zeros(len(angles))])@R.T
    ranges=raycast_distances(origin,directions,solids,profile['range_max_m'],exclude_owner=slot)
    valid=np.isfinite(ranges)
    ranges[valid]+=rng.normal(0,noise.get('lidar_sigma_m',0),int(valid.sum()))
    ranges[valid]=np.clip(ranges[valid],profile['range_min_m'],profile['range_max_m'])
    dropped=rng.random(len(ranges))<noise.get('lidar_no_return_p',0)
    return {'angle_min_rad':profile['angle_min_rad'],'angle_increment_rad':2*math.pi/profile['ray_count'],
            'range_min_m':profile['range_min_m'],'range_max_m':profile['range_max_m'],
            'ranges_m':[float(v) if math.isfinite(v) and not dropped[i] else None for i,v in enumerate(ranges)]}
