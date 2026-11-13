"""Photo-proportioned WINGBOT 6WD. Metres, +X front, +Y left, +Z up.

Envelope and API limits come from prestudy(2), pp3–4,14–16. Component
dimensions are estimates, not a measured CAD model. Shared by both viewers.
"""
from functools import lru_cache
import json
import math
import numpy as np

MODEL = 'wingbot_6wd_v1'
WHEEL_RADIUS = .04
AXLE_WIDTH = .205
PALETTE = {'rubber': [.085,.09,.095,1], 'black': [.18,.195,.21,1],
           'metal': [.32,.34,.36,1], 'silver': [.58,.61,.64,1],
           'white': [.88,.91,.96,1], 'glass': [.035,.10,.16,1],
           'camp': [.75,.08,.09,1], 'hp': [.08,.25,1.,1], 'ammo': [.15,.85,.15,1]}


def axis_rotation(normal):
    """Matrix taking local +Z to the supplied outward normal."""
    z = np.asarray(normal, dtype=float); z /= np.linalg.norm(z)
    x = np.cross([0,1,0] if abs(z[1]) < .9 else [1,0,0], z); x /= np.linalg.norm(x)
    return np.column_stack((x, np.cross(z,x), z))


def parts(geometry, bands=1):
    out = []
    def add(name, shape, center, color='black', frame='body', axis=(0,0,1), **size):
        out.append(dict(name=name, shape=shape, center=list(center), color=color,
                        frame=frame, rotation=axis_rotation(axis).tolist(), **size))
    def box(name, center, half, color='black', frame='body'):
        add(name,'bevel_box' if name in ('chassis','front_nose','camera_housing','laser_housing') else 'box',center,color,frame,half=list(half))
    def cylinder(name, center, radius, length, color='black', frame='body', axis=(0,0,1)):
        add(name,'cylinder',center,color,frame,axis,radius=radius,length=length)
    for name in ('chassis','mast'):
        spec=geometry[name]; box(name,spec['center_m'],spec['half_extents_m'])
    box('deck',[0,0,.109],[.108,.089,.006],'metal')
    box('front_nose',[.087,0,.075],[.022,.078,.024])
    box('badge',[.110,0,.079],[.001,.047,.014],'silver')
    for x in [-.085,.085]:
        for y in [-.067,.067]:add(f'deck_bolt{x}/{y}','sphere',[x,y,.117],'silver',radius=.0025)
    # Six independent rubber tyres: the dark side plate is not a tank track.
    for side,y in enumerate([AXLE_WIDTH/2,-AXLE_WIDTH/2]):
        for i,x in enumerate([-.075,0,.075]):
            frame=f'wheel{side}{i}'
            cylinder(frame,[x,y,.04],.038,.043,'rubber',frame,(0,1,0))
            cylinder(frame+'/hub',[x,y+math.copysign(.021,y),.04],.023,.002,'metal',frame,(0,1,0))
            cylinder(frame+'/axle',[x,y+math.copysign(.020,y),.04],.007,.003,'silver',frame,(0,1,0))
            for j in range(16):
                a=j*math.tau/16
                add(frame+f'/tread{j}','box',[x+.038*math.sin(a),y,.04+.038*math.cos(a)],
                    'rubber',frame,axis=(math.sin(a),0,math.cos(a)),half=[.006,.0225,.002])
        box(f'side_rail{side}',[0,math.copysign(.080,y),.077],[.095,.005,.016],'metal')
    # Short LiDAR, front stereo bar and lamps.
    cylinder('lidar_base',[.048,0,.130],.023,.028)
    cylinder('lidar',[.048,0,.150],.024,.012,'silver')
    cylinder('lidar_cap',[.048,0,.159],.024,.007)
    box('depth_camera',[.105,0,.124],[.009,.059,.014])
    for y in [-.044,0,.044]:
        cylinder('depth_lens'+str(y),[.115,y,.124],.006,.002,'glass',axis=(1,0,0))
    for side in [-1,1]:
        cylinder(f'headlight{side}',[.102,.073*side,.119],.009,.008,'white',axis=(1,0,0))
        cylinder(f'antenna{side}',[-.069,.083*side,.225],.0035,.190)
        cylinder(f'sleeve{side}',[-.069,.083*side,.236],.010,.064,'camp')
        for i in range(bands):
            z=.236+(i-(bands-1)/2)*.014
            cylinder(f'band{side}/{i}',[-.069,.083*side,z],.0105,.004,'rubber')
    cylinder('turret_base',[-.025,0,.154],.029,.074)
    cylinder('turret_ring',[-.025,0,.188],.030,.007,'silver')
    cable=[[-.075,-.027,.116],[-.081,-.030,.164],[-.073,-.031,.207],[-.049,-.031,.230]]
    for i,(a,b) in enumerate(zip(cable,cable[1:])):
        a,b=np.array(a),np.array(b)
        cylinder(f'cable{i}',(a+b)/2,.003,float(np.linalg.norm(b-a)),'rubber',axis=b-a)
    # Both optics move together; their actual lens centres define the rays.
    pivot=np.array(geometry['gimbal_pivot_m'])
    for side in [-1,1]:
        box(f'gimbal_fork{side}',(pivot+[-.015,side*.031,-.020]).tolist(),[.021,.006,.028])
    camera=np.array(geometry['camera_offset_gimbal_m'])
    laser=np.array(geometry['laser_offset_gimbal_m'])
    box('camera_housing',camera+[-.018,0,0],[.016,.023,.018],frame='gimbal')
    cylinder('camera_lens',camera,.010,.002,'glass','gimbal',(1,0,0))
    box('laser_housing',laser+[-.028,0,0],[.026,.023,.018],frame='gimbal')
    cylinder('laser_lens',laser,.010,.002,'glass','gimbal',(1,0,0))
    box('laser_bridge',(camera+laser)/2+[-.025,0,0],[.012,.020,.016],frame='gimbal')
    for i,r in enumerate(geometry['receivers']):
        center=np.array(r['center_m']); normal=np.array(r['normal_body'])
        normal=normal/np.linalg.norm(normal)
        cylinder(f'receiver_mount{i}',center-normal*.006,r['radius_m']*1.08,.012,axis=normal)
        add(f'receiver{i}','hemisphere',center,'white',axis=normal,radius=r['radius_m'])
    # Visible status devices; these are not hit receivers.
    for side in [-1,1]:
        add(f'hp_led{side}','sphere',[side*.099,0,.165],'hp',radius=.008)
    for i in range(8):
        add(f'ammo_led{i}','sphere',[.095,-.063+i*.018,.146],'ammo',radius=.003)
    return out


def primitive_mesh(part):
    """Small indexed triangles, identical in TinyRenderer and WebGL."""
    vertices=[];faces=[]
    if part['shape']=='bevel_box':
        hx,hy,hz=part['half'];bevel=min(hy,hz)*.30
        ring=[[-hy+bevel,-hz],[hy-bevel,-hz],[hy,-hz+bevel],[hy,hz-bevel],
              [hy-bevel,hz],[-hy+bevel,hz],[-hy,hz-bevel],[-hy,-hz+bevel]]
        vertices=[[x,y,z] for x in [-hx,hx] for y,z in ring]
        for j in range(8):
            k=(j+1)%8;faces.extend([[j,k,k+8],[j,k+8,j+8]])
        for j in range(1,7):faces.extend([[0,j+1,j],[8,8+j,8+j+1]])
    elif part['shape']=='box':
        h=part['half']
        vertices=[[x*h[0],y*h[1],z*h[2]] for x,y,z in
                  [(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]]
        faces=[[0,2,1],[0,3,2],[4,5,6],[4,6,7],[0,1,5],[0,5,4],
               [1,2,6],[1,6,5],[2,3,7],[2,7,6],[3,0,4],[3,4,7]]
    else:
        n=16;r=part['radius']
        if part['shape']=='cylinder':
            for z in [-part['length']/2,part['length']/2]:
                vertices.extend([[r*math.cos(j*math.tau/n),r*math.sin(j*math.tau/n),z] for j in range(n)])
            for j in range(n):
                k=(j+1)%n;faces.extend([[j,k,n+k],[j,n+k,n+j]])
            for j in range(1,n-1):faces.extend([[0,j+1,j],[n,n+j,n+j+1]])
        else:
            rings=5 if part['shape']=='hemisphere' else 10
            span=math.pi/2 if part['shape']=='hemisphere' else math.pi
            for i in range(rings+1):
                a=i*span/rings
                vertices.extend([[r*math.sin(a)*math.cos(j*math.tau/n),r*math.sin(a)*math.sin(j*math.tau/n),r*math.cos(a)] for j in range(n)])
            for i in range(rings):
                for j in range(n):
                    a=i*n+j;b=i*n+(j+1)%n
                    faces.extend([[a,a+n,b+n],[a,b+n,b]])
    vertices=np.asarray(vertices)@np.asarray(part['rotation']).T+part['center']
    return vertices.tolist(),faces


@lru_cache(maxsize=12)
def _meshes(encoded, bands):
    groups={}
    for part in parts(json.loads(encoded),bands):
        # Keep sensor and status devices individually addressable for validation.
        key=part['name'] if part['name'].startswith(('receiver','hp_led','ammo_led','laser_lens','camera_lens')) else part['frame']+'/'+part['color']
        group=groups.setdefault(key,dict(name=key,frame=part['frame'],color=part['color'],vertices=[],faces=[]))
        vertices,faces=primitive_mesh(part);start=len(group['vertices'])
        group['vertices'].extend(vertices);group['faces'].extend([[v+start for v in f] for f in faces])
    for group in groups.values():
        frame=group['frame'];name=group['name']
        if frame.startswith('wheel'):
            side,i=int(frame[5]),int(frame[6]);origin=[[-.075,0,.075][i],[AXLE_WIDTH/2,-AXLE_WIDTH/2][side],.04]
        elif name.startswith(('receiver','hp_led','ammo_led','laser_lens','camera_lens')):
            origin=next(p['center'] for p in parts(json.loads(encoded),bands) if p['name']==name)
        else:origin=[0,0,0]
        group['origin']=origin
        group['vertices']=(np.asarray(group['vertices'])-origin).tolist()
    return list(groups.values())


def meshes(geometry,bands=1):
    return _meshes(json.dumps(geometry,sort_keys=True),bands)


def solid_specs(geometry):
    """Opaque body/turret and receiver backing, excluding transparent domes.

    OBBs conservatively approximate housings, not the whole robot envelope;
    air between sensors therefore stays shootable.
    """
    out=[]
    for name in ('chassis','mast'):
        s=geometry[name];out.append((name,s['center_m'],s['half_extents_m'],np.eye(3),'body'))
    out.extend([('deck',[0,0,.109],[.108,.089,.006],np.eye(3),'body'),
                ('turret_base',[-.025,0,.154],[.027,.027,.037],np.eye(3),'body'),
                ('lidar',[.048,0,.143],[.024,.024,.020],np.eye(3),'body'),
                ('depth_camera',[.105,0,.124],[.009,.059,.014],np.eye(3),'body')])
    for side in [-1,1]:
        out.append((f'antenna{side}',[-.069,side*.083,.225],[.0035,.0035,.095],np.eye(3),'body'))
        out.append((f'sleeve{side}',[-.069,side*.083,.236],[.010,.010,.032],np.eye(3),'body'))
    for name,offset,half in [('camera_housing',geometry['camera_offset_gimbal_m'],[.016,.023,.018]),
                             ('laser_housing',geometry['laser_offset_gimbal_m'],[.026,.023,.018])]:
        out.append((name,np.array(offset)+[-half[0]-.002,0,0],half,np.eye(3),'gimbal'))
    for i,r in enumerate(geometry['receivers']):
        R=axis_rotation(r['normal_body']);radius=r['radius_m']
        out.append((f'receiver_mount{i}',np.array(r['center_m'])-R[:,2]*.006,[radius,radius,.006],R,'body'))
    return out


def wheel_speeds(v,omega):
    """Left/right rim speeds for the documented differential 6WD layout."""
    return v-omega*AXLE_WIDTH/2,v+omega*AXLE_WIDTH/2
