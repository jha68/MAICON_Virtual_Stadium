"""Read-only observer viewport. UI actions are returned to the supervisor."""
from __future__ import annotations
import math
import numpy as np
from ..core.geometry2d import obb_corners,pose_values

class PygameViewer:
    def __init__(self,config,clock_mode='accelerated',size=(1080,820),gateway=None):
        import pygame
        self.pg=pygame;pygame.init();self.screen=pygame.display.set_mode(size,pygame.RESIZABLE)
        pygame.display.set_caption('MAICON observer | SIM assumptions')
        self.font=pygame.font.Font(None,22);self.config=config;self.clock_mode=clock_mode;self.selected='B-1';self.truth=True;self.sensors=False;self.trajectories=True;self.debug_paused=False;self.speed=1;self.closed=False;self.history={};self.event_cursor=-1;self.last_snapshot=None;self.gateway=gateway;self.panel_width=340 if gateway is not None else 0;self._panel_cache={};self._last_drone=None;self.displayed_poses={}
    def world_to_screen(self,x,y):
        w,h=self.screen.get_size();bounds=self.config.arena['bounds'];scale=min((w-100-self.panel_width)/bounds['width_m'],(h-150)/bounds['height_m'])
        return (int(45+scale*x),int(h-90-scale*y))
    def poll(self):
        p=self.pg;actions=[]
        for event in p.event.get():
            if event.type==p.QUIT:self.closed=True;actions.append({'kind':'close'})
            elif event.type==p.KEYDOWN:
                if event.key==p.K_ESCAPE:self.closed=True;actions.append({'kind':'close'})
                elif event.key==p.K_SPACE:self.debug_paused=not self.debug_paused;actions.append({'kind':'debug_pause','paused':self.debug_paused})
                elif event.key==p.K_n:actions.append({'kind':'step'})
                elif event.key==p.K_p:actions.append({'kind':'match_pause'})
                elif event.key==p.K_r:actions.append({'kind':'match_resume'})
                elif event.key==p.K_t:self.truth=not self.truth
                elif event.key==p.K_s:self.sensors=not self.sensors
                elif event.key==p.K_h:self.trajectories=not self.trajectories
                elif event.key in (p.K_LEFT,p.K_RIGHT):self.event_cursor+=(-1 if event.key==p.K_LEFT else 1);actions.append({'kind':'event_seek','index':self.event_cursor})
                elif event.key in (p.K_EQUALS,p.K_PLUS,p.K_MINUS):
                    if self.clock_mode=='accelerated':self.speed=max(.25,min(32,self.speed*(.5 if event.key==p.K_MINUS else 2)));actions.append({'kind':'speed','factor':self.speed})
                    else:actions.append({'kind':'rejected','reason':'Realtime speed is fixed at 1x'})
                elif p.K_1<=event.key<=p.K_6:self.selected=('B-1','B-2','B-3','R-1','R-2','R-3')[event.key-p.K_1]
        return actions
    def draw(self,snapshot,observations=None):
        self.last_snapshot=snapshot;p=self.pg;screen=self.screen;screen.fill((236,235,224))
        bounds=self.config.arena['bounds']
        for x in np.arange(0,bounds['width_m']+.001,.5):p.draw.line(screen,(203,203,195),self.world_to_screen(x,0),self.world_to_screen(x,bounds['height_m']))
        for y in np.arange(0,bounds['height_m']+.001,.5):p.draw.line(screen,(203,203,195),self.world_to_screen(0,y),self.world_to_screen(bounds['width_m'],y))
        for sector in self.config.arena['sectors']:
            poly=[self.world_to_screen(*q) for q in sector['polygon_xy_m']];p.draw.polygon(screen,(160,160,150),poly,1)
            center=np.mean(sector['polygon_xy_m'],axis=0);screen.blit(self.font.render(sector['sector_id'],True,(100,100,90)),self.world_to_screen(*center))
        for base in self.config.arena['bases']:p.draw.line(screen,(40,140,65),*[self.world_to_screen(*q) for q in base['trigger_segment_xy_m']],4)
        if self.truth:
            for box in snapshot.get('boxes',self.config.scenario['boxes']):p.draw.polygon(screen,(145,136,118),[self.world_to_screen(*q) for q in obb_corners(box['pose'],*box['size_m'][:2])])
        self.displayed_poses={}
        for slot,r in snapshot.get('robots',{}).items():
            if not self.truth and slot!=self.selected:continue
            display_pose=r['pose'] if self.truth else self._observed_pose(slot,observations)
            self.displayed_poses[slot]=display_pose
            x,y,yaw=pose_values(display_pose);color=(45,80,205) if slot.startswith('B') else (205,50,45)
            p.draw.polygon(screen,color,[self.world_to_screen(*q) for q in obb_corners(display_pose)],0)
            a=self.world_to_screen(x,y);b=self.world_to_screen(x+.22*math.cos(yaw),y+.22*math.sin(yaw));p.draw.line(screen,(25,25,25),a,b,2)
            if slot==self.selected:p.draw.circle(screen,(225,170,25),a,23,2)
            path=self.history.setdefault((slot,self.truth),[])
            if not path or path[-1]!=(x,y):
                path.append((x,y));path[:max(0,len(path)-2000)]=[]
            if self.trajectories and len(path)>1:p.draw.lines(screen,color,False,[self.world_to_screen(*q) for q in path],1)
            if self.truth:screen.blit(self.font.render(f'{slot} HP{r.get("hp","?")} ammo{r.get("ammo","?")}',True,(20,20,20)),(a[0]+14,a[1]-20))
        phase=snapshot.get('phase','?');tick=snapshot.get('sim_tick',0);match=snapshot.get('match_elapsed_ticks',0)
        labels=[f'OBSERVER | phase={phase} sim={tick/100:.2f}s match={match/100:.2f}s | {"truth" if self.truth else "observed"}',
                f'debug pause={self.debug_paused} (SPACE/N) | match pause/resume=P/R | rate={self.speed}x (+/-) | select=1..6',
                'T layers | S sensor rays | H trajectories | arrows event seek | ESC close']
        for i,label in enumerate(labels):screen.blit(self.font.render(label,True,(20,20,20)),(15,15+24*i))
        if self.sensors and observations and self.selected in observations:
            obs=observations[self.selected];scan=obs.get('scan');r=snapshot.get('robots',{}).get(self.selected)
            if scan and r:
                display_pose=r['pose'] if self.truth else self._observed_pose(self.selected,observations)
                x,y,yaw=pose_values(display_pose)
                for i,dist in enumerate(scan.get('ranges_m',[])):
                    if dist is None or i%5:continue
                    angle=yaw+scan['angle_min_rad']+i*scan['angle_increment_rad']
                    p.draw.line(screen,(150,195,150),self.world_to_screen(x,y),self.world_to_screen(x+dist*math.cos(angle),y+dist*math.sin(angle)),1)
        for endpoint,label in [((.4,0),'+x east'),((0,.4),'+y north')]:
            a=self.world_to_screen(0,0);b=self.world_to_screen(*endpoint);p.draw.line(screen,(30,30,30),a,b,2)
            p.draw.circle(screen,(30,30,30),b,3);screen.blit(self.font.render(label,True,(30,30,30)),(b[0]+3,b[1]+3))
        self._draw_sensor_panels(snapshot,observations)
        p.display.flip()
    def _observed_pose(self,slot,observations=None):
        nominal=next(a['pose'] for a in self.config.arena['nominal_starts'] if a['slot']==slot)
        odom=(observations or {}).get(slot,{}).get('odom')
        if self.gateway is not None:
            try:odom=self.gateway.get(slot,'odom')
            except Exception:pass
        if odom is None:return dict(nominal)
        lx,ly,lyaw=pose_values(odom['local_pose']);x,y,yaw=pose_values(nominal)
        return {'x_m':x+math.cos(yaw)*lx-math.sin(yaw)*ly,
                'y_m':y+math.sin(yaw)*lx+math.cos(yaw)*ly,'yaw_rad':yaw+lyaw}
    def set_gateway(self,gateway):
        self.gateway=gateway;self.panel_width=340;self._panel_cache.clear()
    def _draw_sensor_panels(self,snapshot,observations):
        if self.gateway is None and not observations:return
        self.panel_width=340;p=self.pg;w,h=self.screen.get_size();left=w-self.panel_width+10;panel_w=self.panel_width-20
        p.draw.rect(self.screen,(248,248,242),(left-6,100,self.panel_width,h-105))
        selected=(observations or {}).get(self.selected,{})
        frame=selected.get('rgb');drone=self._last_drone
        if self.gateway is not None:
            try:frame=self.gateway.get_frame(self.selected)
            except Exception:pass
            try:
                blob,headers=self.gateway.get_drone(self.selected)
                signature=(headers['X-Captured-At'],len(blob))
                if self._last_drone is None or self._last_drone['signature']!=signature:
                    import io
                    from PIL import Image
                    rgb=np.asarray(Image.open(io.BytesIO(blob)).convert('RGB'))
                    drone={'data':rgb,'encoding':'rgb8','signature':signature,'captured_at':headers['X-Captured-At']}
                    self._last_drone=drone
            except Exception:pass
        self.screen.blit(self.font.render(f'{self.selected} public RGB',True,(20,20,20)),(left,104))
        def image_panel(value,y,max_height):
            if value is None:
                p.draw.rect(self.screen,(45,48,50),(left,y,panel_w,max_height))
                self.screen.blit(self.font.render('Image unavailable',True,(220,220,220)),(left+8,y+14))
                return
            raw=np.asarray(value['data'])
            if value.get('encoding','bgr8')=='bgr8':raw=raw[...,::-1]
            raw=np.ascontiguousarray(raw)
            surface=p.image.frombuffer(raw.tobytes(),(raw.shape[1],raw.shape[0]),'RGB')
            ratio=min(panel_w/raw.shape[1],max_height/raw.shape[0])
            self.screen.blit(p.transform.smoothscale(surface,(int(raw.shape[1]*ratio),int(raw.shape[0]*ratio))),(left,y))
        image_panel(frame,132,240)
        tick=snapshot.get('sim_tick',0)
        if frame is not None:
            captured=frame.get('captured_tick',0);received=frame.get('received_tick',0)
            text=f'seq={frame.get("sequence",0)} cap={captured} recv={received} age={(tick-captured)*.01:.2f}s'
            self.screen.blit(self.font.render(text,True,(30,30,30)),(left,379))
        self.screen.blit(self.font.render('Public drone (last normal frame)',True,(20,20,20)),(left,412))
        image_panel(drone,438,260)
        if drone is not None:self.screen.blit(self.font.render(drone['captured_at'],True,(30,30,30)),(left,705))
        if self.gateway is not None:
            self.screen.blit(self.font.render(f'frame drops={self.gateway.dropped}',True,(30,30,30)),(left,733))
    def save(self,path):self.pg.image.save(self.screen,str(path))
    def close(self):self.pg.quit();self.closed=True

Viewer=PygameViewer
