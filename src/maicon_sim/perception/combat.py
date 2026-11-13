"""Public-image reference cues for the synthetic fixture, not a real-world model.

Facility artwork, marker dimensions and LED placement are public fixture priors.
No world entities, segmentation, renderer registry or simulator truth are read.
The detector declines to provide an aim point or LED state when not resolved.
"""
from __future__ import annotations

import copy
import hashlib

import numpy as np

from maicon_sim.backends.bullet.asset_builder import synthetic_image
from .synthetic_template import SyntheticTemplateDetector, _iou


class CombatVisionDetector:
    def __init__(self, calibration=None, threshold=.75, *, robot_only=False):
        import cv2
        self.cv2 = cv2
        self._last_pixels = None
        self._last_detections = None
        self.calibration = calibration or {}
        self.robot_only = robot_only
        if robot_only:
            return
        from .reference_images import ReferenceImageDetector
        self.reference_images = ReferenceImageDetector(self.calibration) if self.calibration.get("artwork_profile") == "prestudy" else None
        self.objects = SyntheticTemplateDetector(threshold=threshold)
        self.facilities = SyntheticTemplateDetector(threshold=threshold, min_area_px=144.)
        self.facilities.templates = {
            label: cv2.resize(np.asarray(synthetic_image(label).convert('L'))[16:496,16:496],
                              (128,128), interpolation=cv2.INTER_AREA)
            for label in ('RADAR','COMMS','OUTPOST')
        }
        # A receiver can interrupt the outer registration contour. The inner
        # border is still a quadrilateral, so match its documented crop too.
        self.facilities_inner = SyntheticTemplateDetector(threshold=threshold, min_area_px=144.)
        self.facilities_inner.templates = {
            label: cv2.resize(np.asarray(synthetic_image(label).convert('L'))[28:484,28:484],
                              (128,128), interpolation=cv2.INTER_AREA)
            for label in ('RADAR','COMMS','OUTPOST')
        }

    def _components(self, mask, minimum=2):
        _, labels, stats, centers = self.cv2.connectedComponentsWithStats(mask.astype(np.uint8), 8)
        return [(stats[i], centers[i]) for i in range(1,len(stats)) if stats[i,4] >= minimum]

    def _facility_cues(self, bgr):
        result=[]
        b,g,r=[bgr[...,i].astype(float) for i in range(3)]
        receiver=(r>1.28*g)&(r>1.28*b)&(r<125)&(r>12)&(np.abs(g-b)<18)
        camera=self.calibration.get('front_camera',self.calibration)
        fx=float(camera.get('fx_px',320.))
        candidates=[(d,.352*480/512) for d in self.facilities.detect(bgr)]
        candidates += [(d,.352*456/512) for d in self.facilities_inner.detect(bgr)]
        selected=[]
        for detection,plate_width in sorted(candidates,key=lambda pair:-pair[0]['confidence']):
            if any(_iou(detection['bbox_xyxy_px'],old['bbox_xyxy_px'])>.5 for old in selected):continue
            selected.append(detection)
            item=dict(detection);item['kind']='facility'
            x1,y1,x2,y2=item['bbox_xyxy_px'];width=x2-x1;height=y2-y1
            # The fixture receiver sits near the upper centre of the plate.
            left=max(0,int(x1-.15*width));right=min(bgr.shape[1],int(x2+.15*width))
            top=max(0,int(y1-.18*height));bottom=min(bgr.shape[0],int(y1+.42*height))
            choices=[]
            for stat,center in self._components(receiver[top:bottom,left:right],minimum=3):
                sx,sy,sw,sh,area=stat
                if min(sw,sh)<2 or max(sw,sh)>max(5.,width*.28):continue
                point=np.array(center)+[left,top]
                expected=np.array([(x1+x2)/2,y1+.075*height])
                choices.append((float(np.linalg.norm((point-expected)/[max(width,1),max(height,1)])),point,sw,sh))
            if choices:
                _,point,sw,sh=min(choices,key=lambda c:c[0])
                item['aim_point_px']=list(map(float,point))
                # Image-face range is stable even when the tiny sphere is a
                # handful of pixels. It is an estimate, never depth truth.
                item['range_m']=fx*plate_width/max(1.,width)
                item['range_source']='synthetic_plate_width_prior'
                item['aim_confidence']=min(.95,float(item['confidence']))
            result.append(item)
        return result

    def _robot_cues(self,bgr):
        cv2=self.cv2;hsv=cv2.cvtColor(np.ascontiguousarray(bgr),cv2.COLOR_BGR2HSV)
        camera=self.calibration.get('front_camera',self.calibration)
        fx=float(camera.get('fx_px',320.));fy=float(camera.get('fy_px',fx))
        gray=cv2.cvtColor(np.ascontiguousarray(bgr),cv2.COLOR_BGR2GRAY)
        result=[];unidentified=[]
        for camp,mask in (('RED',((hsv[...,0]<9)|(hsv[...,0]>173))&(hsv[...,1]>140)&(hsv[...,2]>45)),
                          ('BLUE',(hsv[...,0]>100)&(hsv[...,0]<130)&(hsv[...,1]>140)&(hsv[...,2]>45))):
            joined=cv2.morphologyEx(mask.astype(np.uint8),cv2.MORPH_CLOSE,np.ones((5,3),np.uint8))
            for stat,_ in self._components(joined,minimum=18):
                x,y,w,h,area=map(int,stat)
                if w>=10 and h>=3 and w/h>=1.6:
                    unidentified.append({'kind':'ugv','bbox_xyxy_px':[float(x),float(max(0,y-2*h)),float(x+w),float(y+h)],
                                         'class_probs':{'UGV':1.},'confidence':.5,'marker_unresolved':True})
                if h<10 or w<4 or not .3<=w/h<=1.1:continue
                patch=gray[y:y+h,x:x+w]
                # Horizontal black strips are the observable call-sign cue.
                columns=patch[:,max(0,w//6):max(1,w-w//6)]
                dark_level=min(35.,float(np.percentile(columns,75))*.4)
                row_dark=np.mean(columns<dark_level,axis=1)>.65
                row_dark[:1]=False;row_dark[-1:]=False
                bands=int(np.count_nonzero(row_dark & ~np.r_[False,row_dark[:-1]]))
                if not 1<=bands<=3:continue
                runs=np.split(np.flatnonzero(row_dark),np.flatnonzero(np.diff(np.flatnonzero(row_dark))>1)+1)
                positions=np.array([np.mean(run)/h for run in runs if len(run)])
                expected={1:[.5],2:[.375,.625],3:[.25,.5,.75]}[bands]
                # Counting two visible stripes alone can confuse a partially
                # occluded three-band marker with slot2. Require their relative
                # positions to agree with a complete marker; otherwise abstain.
                identified=bool(np.all(np.abs(positions-expected)<.12))
                range_m=fx*.06/max(w,1)
                item={'kind':'ugv','bbox_xyxy_px':[float(x),float(y),float(x+w),float(y+h)],
                      'class_probs':{'UGV':1.},'confidence':.85,
                      'range_m':range_m,'range_source':'synthetic_marker_width_prior'}
                if identified:
                    item['marker_readout']={'camp':camp,'band_count':bands,'confidence':.85}
                else:
                    item['marker_unresolved']=True
                item['marker_bbox_xyxy_px']=list(item['bbox_xyxy_px'])
                item['bbox_xyxy_px']=[max(0.,x-1.8*w),float(y),min(float(bgr.shape[1]),x+2.8*w),
                                     min(float(bgr.shape[0]),y+fy*.32/max(.05,range_m))]
                # Require the two visible amber receiver disks. An isolated
                # orange pixel might instead be an HP LED or unrelated object.
                left=max(0,x-4*w);right=min(bgr.shape[1],x+5*w)
                top=max(0,y+h//2);bottom=min(bgr.shape[0],y+4*h)
                roi=hsv[top:bottom,left:right]
                amber=(roi[...,0]>=12)&(roi[...,0]<=24)&(roi[...,1]>120)&(roi[...,2]>60)
                points=[]
                for rec,center in self._components(amber,minimum=2):
                    rx,ry,rw,rh,ra=rec
                    if max(rw,rh)>max(6,.65*w) or min(rw,rh)<1:continue
                    points.append(np.asarray(center)+[left,top])
                pairs=[(a,b) for i,a in enumerate(points) for b in points[i+1:]
                       if 1.8*w<abs(a[0]-b[0])<5.5*w and abs(a[1]-b[1])<max(3,.35*w)]
                if pairs:
                    a,b=min(pairs,key=lambda pair:abs((pair[0][0]+pair[1][0])/2-(x+w/2)))
                    aim=min((a,b),key=lambda p:abs(p[0]-camera.get('cx_px',319.5)))
                    item['aim_point_px']=list(map(float,aim));item['aim_confidence']=.8
                    center=(a+b)/2
                    span=abs(a[0]-b[0])
                    item['bbox_xyxy_px']=[max(0.,min(a[0],b[0])-.12*span),float(y),
                                         min(float(bgr.shape[1]),max(a[0],b[0])+.12*span),
                                         min(float(bgr.shape[0]),center[1]+fy*.16/max(.05,range_m))]
                    state=self._visual_state(bgr,center,abs(a[0]-b[0]),range_m,fx,fy)
                    item['visual_state']=state
                    if state['hp'] is not None:item['hp_observation']=state['hp'];item['hp_confidence']=state['confidence']
                    if state['ammo'] is not None:item['ammo_observation']=state['ammo'];item['ammo_confidence']=state['confidence']
                result.append(item)
        # A mast/board can produce nested candidate outlines. Keep one marker
        # per nearby image location, without assigning simulator identities.
        selected=[]
        for item in sorted(result,key=lambda d:-d['confidence']):
            box=item['bbox_xyxy_px'];center=np.array([(box[0]+box[2])/2,(box[1]+box[3])/2])
            if all(np.linalg.norm(center-np.array([(o['bbox_xyxy_px'][0]+o['bbox_xyxy_px'][2])/2,(o['bbox_xyxy_px'][1]+o['bbox_xyxy_px'][3])/2]))>max(6,box[2]-box[0]) for o in selected):
                selected.append(item)
        for item in unidentified:
            box=item['bbox_xyxy_px'];cx=(box[0]+box[2])/2;cy=box[3]
            if not any(old['bbox_xyxy_px'][0]<=cx<=old['bbox_xyxy_px'][2] and old['bbox_xyxy_px'][1]<=cy<=old['bbox_xyxy_px'][3] for old in selected):
                selected.append(item)
        for item in selected:item['bbox_xyxy_px']=list(map(float,item['bbox_xyxy_px']))
        return selected

    def _visual_state(self,bgr,receiver_center,receiver_span,range_m,fx,fy):
        # The fixture's HP device is30mm above the receiver centre. Estimate
        # only when a saturated patch matches a documented indicator colour.
        x=int(round(receiver_center[0]));y=int(round(receiver_center[1]-fy*.03/max(.05,range_m)))
        radius=max(1,int(round(receiver_span*.012/.22)))
        patch=bgr[max(0,y-radius):min(bgr.shape[0],y+radius+1),max(0,x-radius):min(bgr.shape[1],x+radius+1)]
        hp=None
        if patch.size:
            pixels=patch.reshape(-1,3).astype(float)[:,::-1]
            pixels=pixels[(pixels.max(axis=1)>35)&((pixels.max(axis=1)-pixels.min(axis=1))>30)]
            if len(pixels)>=2:
                colour=np.median(pixels,axis=0);colour/=max(colour.max(),1)
                reference={4:np.array([.08,.25,1.]),3:np.array([.08,.95,.12]),2:np.array([1.,.90,.06]),1:np.array([1.,.42,.06]),0:np.array([1.,.06,.06])}
                distances={h:float(np.linalg.norm(colour-r/r.max())) for h,r in reference.items()}
                best=min(distances,key=distances.get)
                if distances[best]<.25:hp=best
        # Require all eight physical cells to be recognisable, including dark
        # green unlit cells. Absence of lit pixels alone never means zero ammo.
        ammo=None
        depth=fx*.22/max(receiver_span,1.)
        if receiver_span>=35 and depth>.2:
            panel_depth=depth-.095
            panel_span=fx*.126/panel_depth
            panel_y=receiver_center[1]+fy*(.092/panel_depth-.07/depth)
            hsv=self.cv2.cvtColor(np.ascontiguousarray(bgr),self.cv2.COLOR_BGR2HSV)
            cells=[]
            for xx in np.linspace(receiver_center[0]-panel_span/2,receiver_center[0]+panel_span/2,8):
                xx,yy=int(round(xx)),int(round(panel_y))
                patch=bgr[max(0,yy-2):min(bgr.shape[0],yy+3),max(0,xx-2):min(bgr.shape[1],xx+3)].astype(float)
                pp=hsv[max(0,yy-2):min(bgr.shape[0],yy+3),max(0,xx-2):min(bgr.shape[1],xx+3)]
                on=(pp[...,0]>40)&(pp[...,0]<90)&(pp[...,1]>100)&(pp[...,2]>60)
                off=(patch[...,1]>1.05*patch[...,0])&(patch[...,1]>1.05*patch[...,2])&(patch.max(axis=2)<60)
                cells.append(1 if np.any(on) else 0 if np.any(off) else None)
            if None not in cells and (cells==sorted(cells) or cells==sorted(cells,reverse=True)):
                ammo=sum(cells)
        return {'hp':hp,'ammo':ammo,'confidence':.75 if hp is not None or ammo is not None else 0.}

    def detect(self,bgr):
        if bgr.dtype!=np.uint8 or bgr.ndim!=3 or bgr.shape[2]!=3:
            raise ValueError('CombatVisionDetector expects uint8 HxWx3 BGR pixels')
        if self.robot_only:
            return self._robot_cues(bgr)
        reference = self.reference_images.detect(bgr) if self.reference_images else []
        synthetic = [] if self.reference_images else self.objects.detect(bgr)+self._facility_cues(bgr)
        return reference+[d for d in synthetic if all(_iou(d['bbox_xyxy_px'],r['bbox_xyxy_px'])<.45 for r in reference)]+self._robot_cues(bgr)

    def process(self,frame):
        # Identical *newly captured* pixels have identical image-only evidence.
        # Reuse one result, but preserve this input's original timing/sequence.
        # Never manufacture fresh capture metadata for a cached sensor packet.
        pixels = np.ascontiguousarray(frame['data'])
        key = (pixels.shape, pixels.dtype.str, hashlib.sha256(pixels).digest())
        if key != self._last_pixels:
            self._last_detections = self.detect(pixels)
            self._last_pixels = key
        return {key:frame[key] for key in ('sequence','captured_tick','received_tick','camera_id','width_px','height_px') if key in frame} | {'detections':copy.deepcopy(self._last_detections)}
