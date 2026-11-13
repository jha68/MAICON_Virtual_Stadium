"""Private Bullet registry. Canonical ray proxies and visual detail are separate."""
from __future__ import annotations
import math
from pathlib import Path
import numpy as np
from maicon_sim.core.geometry2d import pose_values
from maicon_sim.core.geometry3d import FACE_AXES, rotation_z


# Documented hit-state colours, rendered on a dedicated device rather than
# encoding HP in the camp-coloured chassis. Placement remains a SIM fixture.
HP_LED_COLORS = {
    4: (.08, .25, 1., 1.),
    3: (.08, .95, .12, 1.),
    2: (1., .90, .06, 1.),
    1: (1., .42, .06, 1.),
    0: (1., .06, .06, 1.),
}


def _pose(value):
    if isinstance(value,dict) and 'pose' in value:value=value['pose']
    return pose_values(value)


def _quaternion_product(left,right):
    """Compose xyzw quaternions in float64, avoiding auxiliary Bullet rounding."""
    x1,y1,z1,w1=left;x2,y2,z2,w2=right
    return [w1*x2+x1*w2+y1*z2-z1*y2, w1*y2-x1*z2+y1*w2+z1*x2,
            w1*z2+x1*y2-y1*x2+z1*w2, w1*w2-x1*x2-y1*y2-z1*z2]


class BulletScene:
    def __init__(self,p,client,config,assets):
        self.p=p;self.client=client;self.config=config;self.assets=assets
        self.registry={};self.faces={};self.robot_parts={};self.box_parts={};self.gimbal_parts={}
        self.textures={};self._meshes={};self.led_parts={};self.facility_parts={};self.hp_led_parts={};self._mesh_root=assets.root/'meshes';self._mesh_root.mkdir(exist_ok=True)
        self._build()

    def _box(self,key,half,position,color,collision=True,orientation=(0,0,0,1)):
        p=self.p;c=self.client
        visual=p.createVisualShape(p.GEOM_BOX,halfExtents=list(half),rgbaColor=list(color),physicsClientId=c)
        collider=p.createCollisionShape(p.GEOM_BOX,halfExtents=list(half),physicsClientId=c) if collision else -1
        body=p.createMultiBody(baseMass=0,baseCollisionShapeIndex=collider,baseVisualShapeIndex=visual,
            basePosition=list(position),baseOrientation=list(orientation),physicsClientId=c)
        self.registry[key]=body;return body

    def _sphere(self,key,radius,position,color):
        p=self.p;c=self.client
        shape=p.createVisualShape(p.GEOM_SPHERE,radius=radius,rgbaColor=list(color),physicsClientId=c)
        body=p.createMultiBody(baseVisualShapeIndex=shape,basePosition=list(position),physicsClientId=c)
        self.registry[key]=body;return body

    def _cylinder(self,key,radius,length,position,color,quaternion=(0,0,0,1)):
        p=self.p;c=self.client
        shape=p.createVisualShape(p.GEOM_CYLINDER,radius=radius,length=length,rgbaColor=list(color),physicsClientId=c)
        body=p.createMultiBody(baseVisualShapeIndex=shape,basePosition=list(position),baseOrientation=quaternion,physicsClientId=c)
        self.registry[key]=body;return body

    def _quad(self,key,center,u,v,width,height,color=(1,1,1,1),texture=None):
        """U×V outward normal, file row0 maps to mesh v=1 (top)."""
        p=self.p;c=self.client;center=np.asarray(center);u=np.asarray(u);v=np.asarray(v)
        vertices=[center+sx*width/2*u+sy*height/2*v for sx,sy in [(-1,-1),(1,-1),(1,1),(-1,1)]]
        normal=np.cross(u,v)
        text=''.join('v '+' '.join(map(str,vertex))+'\n' for vertex in vertices)
        text+='vt 0 0\nvt 1 0\nvt 1 1\nvt 0 1\n'
        text+='vn '+' '.join(map(str,normal))+'\n'
        text+='f 1/1/1 2/2/1 3/3/1\nf 1/1/1 3/3/1 4/4/1\n'
        name=key.replace('/','_')+'.obj';path=self._mesh_root/name
        path.write_text(text)
        shape=p.createVisualShape(p.GEOM_MESH,fileName=str(path.resolve()),rgbaColor=list(color),physicsClientId=c)
        body=p.createMultiBody(baseVisualShapeIndex=shape,physicsClientId=c)
        if texture is not None:
            if str(texture) not in self.textures:self.textures[str(texture)]=p.loadTexture(str(Path(texture).resolve()),physicsClientId=c)
            p.changeVisualShape(body,-1,textureUniqueId=self.textures[str(texture)],physicsClientId=c)
        self.registry[key]=body;return body

    def _build(self):
        cfg=self.config;g=cfg.sensors['geometry'];bounds=cfg.arena['bounds'];p=self.p;c=self.client
        w,h=bounds['width_m'],bounds['height_m'];wall_h=bounds.get('wall_height_m',.4);thick=g['wall_thickness_m']
        self._box('floor_solid',[w/2,h/2,.005],[w/2,h/2,-.005],[.78,.79,.78,1],collision=False)
        # Public geometric floor markings; no hidden object or scoring annotation.
        from maicon_sim.backends.arena_art import arena_floor
        floor_image=arena_floor(cfg.arena)
        floor_texture=self._mesh_root/'floor.png';floor_image.save(floor_texture)
        self._quad('floor',[w/2,h/2,.00001],[1,0,0],[0,1,0],w,h,texture=floor_texture)
        for name,half,pos in [('west',[thick/2,h/2,wall_h/2],[-thick/2,h/2,wall_h/2]),
                              ('east',[thick/2,h/2,wall_h/2],[w+thick/2,h/2,wall_h/2]),
                              ('south',[w/2,thick/2,wall_h/2],[w/2,-thick/2,wall_h/2]),
                              ('north',[w/2,thick/2,wall_h/2],[w/2,h+thick/2,wall_h/2])]:
            self._box('wall_'+name,half,pos,[.7,.7,.68,1])
        for box in cfg.scenario['boxes']:
            key=box['box_id'];sx,sy,sz=box['size_m'];x,y,yaw=_pose(box['pose'])
            quat=p.getQuaternionFromEuler([0,0,yaw]);origin=np.array([x,y,0.])
            body=self._box(key,[sx/2,sy/2,sz/2],[x,y,sz/2],[.38,.40,.43,1],orientation=quat)
            parts=[(body,np.array([0.,0.,sz/2]))]
            for face in box['faces']:
                side=face['side'];n,u,v,axis,sign=FACE_AXES[side]
                center=np.array([0.,0.,sz/2]);center[axis]=sign*(box['size_m'][axis]/2+.001)
                face_key=key+'/'+side
                body=self._quad(face_key,center,u,v,box['size_m'][1-axis]*.88,sz*.88,texture=self.assets.path_for(face['asset_id']))
                self.faces[face_key]=body;parts.append((body,np.zeros(3)))
                if face['kind']=='facility':
                    center=np.array([0.,0.,g['facility_receiver_z_m']]);center[axis]=sign*(box['size_m'][axis]/2+g['facility_receiver_offset_m'])
                    code=face['facility_code'];radius=g['facility_receiver_radius_m']
                    housing=self._sphere(code+'/housing',radius*1.4,[0,0,0],[.82,.84,.86,1])
                    parts.append((housing,center-np.asarray(n)*radius*.6))
                    receiver=self._sphere(code+'/receiver',radius,[0,0,0],[.48,.57,.63,1])
                    parts.append((receiver,center))
                    led_center=np.array([0.,0.,sz+.018]);led_center[axis]=sign*box['size_m'][axis]*.35
                    mount=self._box(code+'/signal_mount',[.055,.035,.008],[0,0,0],[.12,.14,.16,1],collision=False)
                    parts.append((mount,led_center-np.array([0,0,.01])))
                    led=self._box(code+'/signal_led',[.04,.022,.012],[0,0,0],[.16,.06,.05,1],collision=False)
                    parts.append((led,led_center))
                    self.facility_parts[code]=(receiver,led)
            self.box_parts[key]=parts
            for part,offset in parts:p.resetBasePositionAndOrientation(part,(origin+rotation_z(yaw)@offset).tolist(),quat,physicsClientId=c)
        for agent in cfg.scenario['agents']:
            slot=agent['slot'];blue=slot.startswith('B-');color=[.12,.27,.73,1] if blue else [.75,.14,.11,1]
            parts=[]
            for name in ('chassis','mast'):
                spec=g[name]
                body=self._box(slot+'/'+name,spec['half_extents_m'],[0,0,0],color)
                parts.append((body,np.asarray(spec['center_m']),[0,0,0,1]))
            wheel_quat=p.getQuaternionFromEuler([math.pi/2,0,0])
            for i,x in enumerate([-.075,0,.075]):
                for j,y in enumerate([-.105,.105]):
                    body=self._cylinder(slot+f'/wheel{i}{j}',.045,.035,[0,0,0],[.08,.08,.08,1],wheel_quat)
                    parts.append((body,np.array([x,y,.045]),wheel_quat))
            for i,receiver in enumerate(g['receivers']):
                body=self._sphere(slot+f'/receiver{i}',receiver['radius_m'],[0,0,0],[.9,.6,.08,1])
                parts.append((body,np.array(receiver['center_m']),[0,0,0,1]))
            pole=self._cylinder(slot+'/marker_pole',.005,.19,[0,0,0],[.2,.2,.2,1]);parts.append((pole,np.array([-.08,0,.225]),[0,0,0,1]))
            center=np.array(g['marker_center_m']);width=g['marker_width_m'];height=g['marker_height_m']
            bands=int(slot[-1]);heights={1:[.27],2:[.26,.28],3:[.25,.27,.29]}[bands]
            for sign in (-1,1):
                board_center=center.copy();board_center[0]+=sign*.0005
                body=self._quad(slot+f'/marker{sign}',board_center,[0,sign,0],[0,0,1],width,height,color)
                parts.append((body,np.zeros(3),[0,0,0,1]))
                for i,z in enumerate(heights):
                    strip=board_center.copy();strip[0]+=sign*.0001;strip[2]=z
                    body=self._quad(slot+f'/marker{sign}/band{i}',strip,[0,sign,0],[0,0,1],width,g['marker_band_height_m'],[.03,.03,.03,1])
                    parts.append((body,np.zeros(3),[0,0,0,1]))
            # Visual gimbal extends rearward from pivot; optical origin is outside.
            head=self._box(slot+'/gimbal',[.015,.025,.012],[0,0,0],[.18,.18,.18,1],collision=False)
            self.gimbal_parts[slot]=head
            leds=[]
            for i in range(8):
                body=self._sphere(slot+f'/ammo_led{i}',.004,[0,0,0],[.15,.85,.15,1])
                parts.append((body,np.array([.095,-.063+i*.018,.138]),[0,0,0,1]));leds.append(body)
            self.led_parts[slot]=leds
            hp_leds=[]
            for sign in (-1,1):
                body=self._sphere(slot+f'/hp_led{sign}',.012,[0,0,0],HP_LED_COLORS[4])
                # Keep the front indicator behind the camera optical origin;
                # a device in front of it would obscure the robot's own image.
                parts.append((body,np.array([.02 if sign>0 else -.119,0,.19]),[0,0,0,1]));hp_leds.append(body)
            self.hp_led_parts[slot]=hp_leds
            self.robot_parts[slot]=parts
        self.sync({'robots':{a['slot']:{'pose':a['start_pose'],'pan':0.,'tilt':0.} for a in cfg.scenario['agents']}})

    def sync(self,snapshot):
        p=self.p;c=self.client;g=self.config.sensors['geometry']
        from maicon_sim.core.geometry3d import gimbal_rotation
        for code,(receiver,led) in self.facility_parts.items():
            signal=snapshot.get('facility_signals',{}).get(code,'hit' if code in snapshot.get('destroyed',[]) else 'idle')
            color={'idle':[.16,.06,.05,1],'receiving':[1.,.58,.05,1],'hit':[1.,.02,.03,1]}[signal]
            p.changeVisualShape(led,-1,rgbaColor=color,physicsClientId=c)
            p.changeVisualShape(receiver,-1,rgbaColor=[.48,.57,.63,1] if signal=='idle' else color,physicsClientId=c)
        for slot,robot in snapshot.get('robots',{}).items():
            x,y,yaw=_pose(robot);R=rotation_z(yaw);origin=np.array([x,y,0.]);quat=p.getQuaternionFromEuler([0,0,yaw])
            for body,offset,localquat in self.robot_parts.get(slot,[]):
                # multiplyTransforms rounds through Bullet's auxiliary float
                # representation. Compose in float64 so visual base yaw retains
                # the same precision as the shared planar pose.
                worldquat=_quaternion_product(quat,localquat)
                p.resetBasePositionAndOrientation(body,(origin+R@offset).tolist(),worldquat,physicsClientId=c)
            ammo=robot.get('ammo',8) if isinstance(robot,dict) else robot.ammo
            for i,led in enumerate(self.led_parts.get(slot,[])):
                p.changeVisualShape(led,-1,rgbaColor=[.15,.85,.15,1] if i<ammo else [.08,.1,.08,1],physicsClientId=c)
            hp=robot.get('hp',4) if isinstance(robot,dict) else robot.hp
            for led in self.hp_led_parts.get(slot,[]):
                p.changeVisualShape(led,-1,rgbaColor=HP_LED_COLORS[max(0,min(4,int(hp)))],physicsClientId=c)
            pan=robot.get('pan',0) if isinstance(robot,dict) else robot.pan
            tilt=robot.get('tilt',0) if isinstance(robot,dict) else robot.tilt
            # yaw + pan + tilt composition in quaternion form matches shared matrix.
            headquat=_quaternion_product(quat,p.getQuaternionFromEuler([0,-math.radians(tilt*.15),-math.radians(pan*.5)]))
            location=origin+R@np.array(g['gimbal_pivot_m'])+R@gimbal_rotation(pan,tilt)@np.array([-.012,0,0])
            p.resetBasePositionAndOrientation(self.gimbal_parts[slot],location.tolist(),headquat,physicsClientId=c)
        for box in snapshot.get('boxes',[]):
            x,y,yaw=_pose(box['pose']);R=rotation_z(yaw);origin=np.array([x,y,0]);quat=p.getQuaternionFromEuler([0,0,yaw])
            for body,offset in self.box_parts[box['box_id']]:p.resetBasePositionAndOrientation(body,(origin+R@offset).tolist(),quat,physicsClientId=c)

    def validate(self):
        expected_boxes={b['box_id'] for b in self.config.scenario['boxes']}
        if set(self.box_parts)!=expected_boxes:raise ValueError('scene box registry differs from world manifest')
        expected_faces={b['box_id']+'/'+f['side'] for b in self.config.scenario['boxes'] for f in b['faces']}
        if set(self.faces)!=expected_faces:raise ValueError('scene face registry differs from world manifest')
        if len(self.robot_parts)!=len(self.config.scenario['agents']):raise ValueError('scene robot registry differs from world manifest')
