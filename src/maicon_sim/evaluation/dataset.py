"""Evaluator-only initial-scene dataset export from real Bullet render passes.

Annotations use private scene IDs and the configured world manifest, never image
classification. No participant API or public output folder is involved.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from collections import Counter
import numpy as np
from PIL import Image

from maicon_sim.backends.bullet.backend import BulletBackend
from maicon_sim.backends.bullet.asset_builder import resolve_assets,manifest_sha256
from maicon_sim.core.geometry3d import camera_transform,face_rectangle,project_points


def _json(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')


def _sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def _area(polygon):
    p=np.asarray(polygon,dtype=float)
    return float(abs(np.dot(p[:,0],np.roll(p[:,1],-1))-np.dot(p[:,1],np.roll(p[:,0],-1)))/2) if len(p)>=3 else 0.


def _clip_polygon(polygon,width,height):
    points=[np.asarray(p,dtype=float) for p in polygon]
    for axis,bound,lower in ((0,-.5,True),(0,width-.5,False),(1,-.5,True),(1,height-.5,False)):
        output=[]
        if not points:break
        def inside(p):return p[axis]>=bound if lower else p[axis]<=bound
        previous=points[-1]
        for current in points:
            a,b=inside(previous),inside(current)
            if a!=b:
                ratio=(bound-previous[axis])/(current[axis]-previous[axis])
                output.append(previous+ratio*(current-previous))
            if b:output.append(current)
            previous=current
        points=output
    return np.asarray(points,dtype=float).reshape(-1,2)


def _bbox(mask):
    yy,xx=np.nonzero(mask)
    return [int(xx.min()),int(yy.min()),int(xx.max())+1,int(yy.max())+1] if len(xx) else None


def export_dataset(config,out,slots=None,tick=0):
    """Export an initial configured scene, without advancing/changing a match.

    ``tick`` is the requested capture label for this static fixture, not evidence
    of a simulated trajectory. The manifest explicitly records this distinction.
    Returned metadata and all truth files are evaluator-only under OUT/private.
    """
    if type(tick) is not int or tick<0:raise ValueError('dataset tick must be a nonnegative integer')
    out=Path(out).resolve()
    if (out/'private/dataset_manifest.json').exists():raise ValueError('dataset output already exists; use a fresh --out')
    private=out/'private';private.mkdir(parents=True,exist_ok=True)
    available={a['slot'] for a in config.scenario['agents']}
    slots=sorted(available if slots is None else set(slots))
    if not slots or any(slot not in available for slot in slots):raise ValueError('dataset slots must be nonempty known robot slots')
    assets=resolve_assets(config.assets,private/'assets',base_dir=config.path.parent)
    faces=[];counts={}
    for box in config.scenario['boxes']:
        counts.setdefault(box['sector_id'],Counter())
        for face in box['faces']:
            entry={'face_id':box['box_id']+'/'+face['side'],'box_id':box['box_id'],'side':face['side'],
                   'sector':box['sector_id'],'kind':face['kind'],'asset_id':face['asset_id']}
            if face['kind']=='object':
                entry['class']=face['object_class'].upper();counts[box['sector_id']][entry['class']]+=1
            elif face['kind']=='facility':entry['facility_code']=face['facility_code']
            faces.append(entry)
    inventory={'count_unit':'SIM-M3-COUNT/image_face','faces':faces,
               'objects_by_sector':{sector:dict(sorted(value.items())) for sector,value in sorted(counts.items())}}
    _json(private/'truth_inventory.json',inventory)
    frame_manifests=[]
    with BulletBackend(config,assets,headless=True) as backend:
        for slot in slots:
            camera_id=slot+'/front';frame=backend.capture_rgb(camera_id,tick);truth=backend.private_capture(camera_id)
            folder=private/'frames'/slot;folder.mkdir(parents=True,exist_ok=True)
            Image.fromarray(frame['data'][...,::-1]).save(folder/'rgb.png')
            np.save(folder/'depth_m.npy',truth['depth_m'],allow_pickle=False)
            np.save(folder/'invalid_mask.npy',truth['invalid_mask'],allow_pickle=False)
            np.save(folder/'segmentation.npy',truth['segmentation'],allow_pickle=False)
            masks=folder/'masks';masks.mkdir(exist_ok=True)
            robot=backend.snapshot['robots'][slot]
            origin,rotation=camera_transform(robot['pose'],robot['pan'],robot['tilt'],config.sensors['geometry'])
            k=config.sensors['front_camera'];annotations=[]
            for box in config.scenario['boxes']:
                for face in box['faces']:
                    face_id=box['box_id']+'/'+face['side'];body_id=truth['face_body_ids'][face_id]
                    mask=truth['segmentation']==body_id
                    count=int(mask.sum());center,normal,u,v,half_w,half_h=face_rectangle(box,face['side'])
                    corners=[center+sx*half_w*u+sy*half_h*v for sx,sy in ((-1,-1),(1,-1),(1,1),(-1,1))]
                    projected,depths=project_points(corners,origin,rotation,k)
                    in_depth=bool(np.all(depths>k['near_m']) and np.all(depths<k['far_m']))
                    projected_area=_area(projected) if in_depth else 0.
                    clipped=_clip_polygon(projected,k['width_px'],k['height_px']) if in_depth else np.empty((0,2))
                    clipped_area=_area(clipped)
                    projection_bbox=([float(projected[:,0].min()),float(projected[:,1].min()),
                                      float(projected[:,0].max()),float(projected[:,1].max())] if in_depth else None)
                    name=hashlib.sha256(face_id.encode()).hexdigest()[:24]+'.png'
                    Image.fromarray((mask.astype(np.uint8)*255),mode='L').save(masks/name)
                    # Pixel boundaries are discrete, polygon area is continuous.
                    # Clamping handles <=1pixel rasterization differences honestly.
                    annotation={'face_id':face_id,'box_id':box['box_id'],'side':face['side'],
                        'kind':face['kind'],'sector':box['sector_id'],'mask_file':'masks/'+name,
                        'visible_pixels':count,'visible_bbox_xyxy_px':_bbox(mask),
                        'full_projection_bbox_xyxy_px':projection_bbox,'full_projection_area_px':projected_area,
                        'in_frame_projection_area_px':clipped_area,
                        'visible_fraction':min(1.,count/projected_area) if projected_area>0 else 0.,
                        'in_frame_visible_fraction':min(1.,count/clipped_area) if clipped_area>0 else 0.,
                        'front_facing':bool(np.dot(normal,origin-center)>0),
                        'projection_status':'valid' if in_depth else 'near_or_far_clipped'}
                    if face['kind']=='object':annotation['class']=face['object_class'].upper()
                    elif face['kind']=='facility':annotation['facility_code']=face['facility_code']
                    annotations.append(annotation)
            header={'schema_version':'1.0','episode_id':config.scenario['scenario_id']+'-dataset',
                'camera_id':camera_id,'captured_tick':tick,'sequence':frame['sequence'],
                'seed':config.scenario['seed'],'asset_manifest_hash':manifest_sha256(assets.manifest),
                'scenario_hash':manifest_sha256(config.scenario),'renderer':backend.metadata,
                'full_face_count':len(faces),'visible_face_count':sum(a['visible_pixels']>0 for a in annotations),
                'visible_annotations':[a for a in annotations if a['visible_pixels']>0],
                'all_faces':annotations}
            _json(folder/'annotations.json',header)
            frame_manifests.append({'camera_id':camera_id,'captured_tick':tick,
                'annotations_file':str((folder/'annotations.json').relative_to(out)),
                'rgb_file':str((folder/'rgb.png').relative_to(out)),
                'depth_file':str((folder/'depth_m.npy').relative_to(out)),
                'segmentation_file':str((folder/'segmentation.npy').relative_to(out)),
                'invalid_mask_file':str((folder/'invalid_mask.npy').relative_to(out))})
        renderer=backend.metadata
    manifest={'schema_version':'1.0','episode_id':config.scenario['scenario_id']+'-dataset',
        'mode':'evaluator_only_initial_scene','simulated_advance':False,'captured_tick':tick,
        'seed':config.scenario['seed'],'scenario_hash':manifest_sha256(config.scenario),
        'asset_manifest_hash':manifest_sha256(assets.manifest),'renderer':renderer,
        'truth_inventory_file':'private/truth_inventory.json','frames':frame_manifests,
        'files':{str(path.relative_to(out)):_sha(path) for path in sorted(private.rglob('*')) if path.is_file()}}
    _json(private/'dataset_manifest.json',manifest)
    return manifest
