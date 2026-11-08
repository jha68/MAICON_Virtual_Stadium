"""Headless 2D scene backend; public drone image has no observer overlays."""
import io
from PIL import Image,ImageDraw
from ..core.geometry2d import obb_corners
class TwoDBackend:
    capabilities={'rgb':False,'semantic':True,'lidar':True,'depth':False}
    def __init__(self,config):self.config=config;self.snapshot=None
    def sync_scene(self,snapshot):self.snapshot=snapshot
    def capture_rgb(self,camera_id,tick):raise RuntimeError('2D front RGB is unavailable; use semantic detections')
    def capture_drone(self,tick):
        c=self.config;w,h=640,520;scale=min(w/c.arena['bounds']['width_m'],h/c.arena['bounds']['height_m'])
        image=Image.new('RGB',(w,h),(215,213,202));draw=ImageDraw.Draw(image)
        def pixels(poly):return [(float(x*scale),float(h-y*scale)) for x,y in poly]
        for b in (self.snapshot or {}).get('boxes',c.scenario['boxes']):draw.polygon(pixels(obb_corners(b['pose'],*b['size_m'][:2])),fill=(130,124,112))
        robots=(self.snapshot or {}).get('robots',{})
        for slot,r in robots.items():
            draw.polygon(pixels(obb_corners(r['pose'])),fill=(45,80,200) if slot.startswith('B') else (195,45,45))
        return {'sequence':tick//100+1,'captured_tick':tick,'received_tick':tick,'camera_id':'main',
                'width_px':w,'height_px':h,'encoding':'bgr8','data':__import__('numpy').asarray(image)[...,::-1].copy()}
    def raycast_batch(self,rays):
        import numpy as np
        from types import SimpleNamespace
        from ..core.geometry3d import canonical_solids,raycast
        snapshot=self.snapshot or {'robots':{},'boxes':self.config.scenario['boxes']}
        robots={slot:SimpleNamespace(pose=r['pose']) for slot,r in snapshot['robots'].items()}
        solids=canonical_solids(robots,snapshot['boxes'],self.config.arena['bounds'],self.config.sensors['geometry'])
        results=[]
        for ray in rays:
            origin=np.asarray(ray['origin'] if isinstance(ray,dict) else ray[0],dtype=float)
            direction=np.asarray(ray['direction'] if isinstance(ray,dict) else ray[1],dtype=float)
            maximum=ray.get('max_distance',10) if isinstance(ray,dict) else (ray[2] if len(ray)>2 else 10)
            direction=direction/np.linalg.norm(direction)
            hit=raycast(origin,direction,solids,maximum)
            results.append({'geometry_id':hit.geometry_id if hit else None,'distance':hit.distance if hit else None,
                            'fraction':hit.distance/maximum if hit else 1.,'position':(origin+direction*(hit.distance if hit else maximum)).tolist()})
        return results
    def close(self):pass
    def __enter__(self):return self
    def __exit__(self,*args):self.close()

