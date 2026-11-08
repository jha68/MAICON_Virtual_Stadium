"""OpenGL camera projection and explicitly synthetic fog photometry."""
from __future__ import annotations
import numpy as np


def projection_matrix(intrinsics: dict) -> list[float]:
    k=intrinsics; w=k['width_px'];h=k['height_px'];n=k['near_m'];f=k['far_m']
    p=np.array([[2*k['fx_px']/w,0,1-2*(k['cx_px']+.5)/w,0],
                [0,2*k['fy_px']/h,2*(k['cy_px']+.5)/h-1,0],
                [0,0,-(f+n)/(f-n),-2*f*n/(f-n)], [0,0,-1,0]],dtype=float)
    return p.flatten(order='F').tolist()


def metric_depth(buffer: np.ndarray, near: float, far: float) -> np.ndarray:
    return far*near/(far-(far-near)*np.asarray(buffer,dtype=float))


def optical_rays(intrinsics: dict) -> tuple[np.ndarray,np.ndarray]:
    k=intrinsics;u,v=np.meshgrid(np.arange(k['width_px']),np.arange(k['height_px']))
    rays=np.stack(((u-k['cx_px'])/k['fx_px'],(v-k['cy_px'])/k['fy_px'],np.ones_like(u)),axis=-1)
    lengths=np.linalg.norm(rays,axis=-1)
    return rays/lengths[...,None],lengths


def fog_path_lengths(depth: np.ndarray, origin: np.ndarray, rotation: np.ndarray,
                     intrinsics: dict, volume: list | None = None) -> np.ndarray:
    rays,scales=optical_rays(intrinsics)
    surface_distance=np.asarray(depth)*scales
    if volume is None:return surface_distance
    minimum,maximum=np.asarray(volume,dtype=float)
    if np.any(maximum<=minimum):raise ValueError('fog AABB must have componentwise minimum < maximum')
    directions=rays@np.asarray(rotation).T
    origin=np.asarray(origin)
    parallel=np.abs(directions)<1e-12
    safe=np.where(parallel,1.,directions)
    a=(minimum-origin)/safe;b=(maximum-origin)/safe
    entry=np.max(np.where(parallel,-np.inf,np.minimum(a,b)),axis=-1)
    exit=np.min(np.where(parallel,np.inf,np.maximum(a,b)),axis=-1)
    outside=np.any(parallel & ((origin<minimum)|(origin>maximum)),axis=-1)
    return np.where(outside,0.,np.maximum(0.,np.minimum(exit,surface_distance)-np.maximum(entry,0.)))


def apply_fog(rgb: np.ndarray, depth: np.ndarray, origin: np.ndarray, rotation: np.ndarray,
              intrinsics: dict, render: dict) -> np.ndarray:
    if not render.get('fog_enabled') or render['fog_density_per_m']==0:return np.asarray(rgb).copy()
    model=render.get('fog_model','full_scene')
    volume=render.get('fog_volume_world_aabb_m') if model=='volume' else None
    if model=='volume' and volume is None:raise ValueError('volume fog requires fog_volume_world_aabb_m')
    distance=fog_path_lengths(depth,origin,rotation,intrinsics,volume)
    transmission=np.exp(-render['fog_density_per_m']*distance)[...,None]
    return np.clip(np.rint(transmission*rgb+(1-transmission)*np.asarray(render['fog_rgb'])),0,255).astype(np.uint8)
