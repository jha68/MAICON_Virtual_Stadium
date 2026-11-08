"""Actual X11 GUI acceptance. Separate from headless renderer correctness."""
import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

ROOT=Path(__file__).resolve().parents[2]
pytestmark=[pytest.mark.e2e,pytest.mark.manual_gui,
            pytest.mark.skipif(not os.environ.get('DISPLAY'),reason='Requires an actual X11 display; run DISPLAY=:99 pytest tests/e2e/test_gui.py')]


def config():
    from maicon_sim.config.loader import load_scenario
    return load_scenario(ROOT/'examples/scenario_smoke_six.yaml')


def start(engine):
    engine.request('enter_ready',None)
    for slot in engine.robots:engine.request('ready',slot)
    engine.request('start',None)


def key(viewer,code):
    viewer.pg.event.post(viewer.pg.event.Event(viewer.pg.KEYDOWN,key=code))
    return viewer.poll()


def test_PACK_010_E2E_011_actual_x11_observer_controls(tmp_path):
    from maicon_sim.core.engine import MatchEngine
    from maicon_sim.sensors.gateway import SensorGateway
    from maicon_sim.viewer.pygame_viewer import PygameViewer
    c=config();engine=MatchEngine(c);start(engine);gateway=SensorGateway(c);gateway.update(engine)
    viewer=PygameViewer(c,gateway=gateway)
    try:
        assert viewer.pg.display.get_driver()=='x11'
        assert viewer.pg.display.get_wm_info().get('window')
        viewer.draw(engine.snapshot())
        # User selection and layer toggles are actual events on a native window.
        key(viewer,viewer.pg.K_4);assert viewer.selected=='R-1'
        key(viewer,viewer.pg.K_t);assert viewer.truth is False
        key(viewer,viewer.pg.K_s);assert viewer.sensors is True
        key(viewer,viewer.pg.K_h);assert viewer.trajectories is False
        actions=key(viewer,viewer.pg.K_SPACE)
        assert actions==[{'kind':'debug_pause','paused':True}] and not engine.paused
        # Debug pause does not advance engine until an explicit single step.
        before=engine.sim_tick
        actions=key(viewer,viewer.pg.K_n);assert actions==[{'kind':'step'}]
        engine.step();assert engine.sim_tick==before+1 and not engine.paused
        actions=key(viewer,viewer.pg.K_p);assert actions==[{'kind':'match_pause'}]
        future=engine.enqueue('pause');engine.step();assert future.result()['accepted'] is True
        assert engine.phase=='running' and engine.paused
        frozen=engine.match_elapsed_ticks;engine.step();assert engine.match_elapsed_ticks==frozen
        actions=key(viewer,viewer.pg.K_r);assert actions==[{'kind':'match_resume'}]
        future=engine.enqueue('resume');engine.step();future.result();assert not engine.paused
        actions=key(viewer,viewer.pg.K_EQUALS);assert actions==[{'kind':'speed','factor':2}]
        actions=key(viewer,viewer.pg.K_LEFT);assert actions[0]['kind']=='event_seek'
        viewer.draw(engine.snapshot())
        path=ROOT/'artifacts/evidence/viewer_x11.png';path.parent.mkdir(parents=True,exist_ok=True);viewer.save(path)
        assert path.stat().st_size>1000
        viewer.pg.event.post(viewer.pg.event.Event(viewer.pg.QUIT))
        assert viewer.poll()==[{'kind':'close'}] and viewer.closed
    finally:viewer.close();gateway.close()
    assert not viewer.pg.display.get_init()
    # Realtime speed changes are rejected explicitly, not silently simulated.
    realtime=PygameViewer(c,clock_mode='realtime')
    try:
        actions=key(realtime,realtime.pg.K_EQUALS)
        assert actions[0]['kind']=='rejected' and realtime.speed==1
    finally:realtime.close()


def test_PACK_010_actual_x11_bullet_gui_orbit_zoom_and_close(tmp_path):
    # A separate process protects the test runner from a native window failure
    # while preserving stdout/stderr and the actual application's exit status.
    program=r'''
import json,os,time
from pathlib import Path
import numpy as np
from PIL import ImageGrab
from maicon_sim.config.loader import load_scenario
from maicon_sim.core.engine import MatchEngine
from maicon_sim.backends.bullet.backend import BulletBackend
root=Path(os.environ['MAICON_GUI_TEST_ROOT'])
c=load_scenario(root/'examples/scenario_smoke_six.yaml');engine=MatchEngine(c)
backend=BulletBackend(c,headless=False)
p=backend.p;client=backend.client
try:
 backend.sync_scene(engine.snapshot())
 p.resetDebugVisualizerCamera(cameraDistance=6,cameraYaw=45,cameraPitch=-55,cameraTargetPosition=[3.06,2.5,0],physicsClientId=client)
 first=p.getDebugVisualizerCamera(physicsClientId=client)
 p.resetDebugVisualizerCamera(cameraDistance=4.5,cameraYaw=70,cameraPitch=-40,cameraTargetPosition=[3.06,2.5,0],physicsClientId=client)
 deadline=time.monotonic()+2
 second=p.getDebugVisualizerCamera(physicsClientId=client)
 while abs(second[8]-70)>1e-5 and time.monotonic()<deadline:
  time.sleep(.02);second=p.getDebugVisualizerCamera(physicsClientId=client)
 print('camera_after_orbit',second[8:11],flush=True)
 assert abs(second[8]-70)<1e-5 and abs(second[9]+40)<1e-5 and abs(second[10]-4.5)<1e-5
 assert first[2]!=second[2]
 frame=backend.capture_rgb('B-1/front',0)
 assert frame['data'].shape==(480,640,3) and np.std(frame['data'])>1
 # Let the native application's display thread publish the changed free view.
 time.sleep(.2)
 image=ImageGrab.grab(xdisplay=os.environ['DISPLAY'])
 assert np.std(np.asarray(image))>1
 path=root/'artifacts/evidence/bullet_gui.png';path.parent.mkdir(parents=True,exist_ok=True);image.save(path)
 print(json.dumps({'gui_connected':bool(p.isConnected(client)),'camera_yaw':second[8],'camera_pitch':second[9],'camera_distance':second[10],'screenshot':str(path),'bodies':p.getNumBodies(client)}))
finally:
 backend.close()
 assert not p.isConnected(client)
'''
    cache=tmp_path/'mesa_cache';cache.mkdir()
    env=dict(os.environ,MAICON_GUI_TEST_ROOT=str(ROOT),SDL_AUDIODRIVER='dummy',MESA_SHADER_CACHE_DIR=str(cache))
    log=ROOT/'artifacts/evidence/bullet_gui.log';log.parent.mkdir(parents=True,exist_ok=True)
    try:
        result=subprocess.run([sys.executable,'-u','-c',program],cwd=tmp_path,env=env,capture_output=True,text=True,timeout=60)
    except subprocess.TimeoutExpired as exc:
        output=exc.stdout or b'';errors=exc.stderr or b''
        if isinstance(output,bytes):output=output.decode(errors='replace')
        if isinstance(errors,bytes):errors=errors.decode(errors='replace')
        log.write_text(output+'\n'+errors)
        pytest.fail('Actual Bullet GUI did not initialize within60s; see artifacts/evidence/bullet_gui.log')
    log.write_text(result.stdout+'\n'+result.stderr)
    assert result.returncode==0,result.stdout+'\n'+result.stderr
    assert (ROOT/'artifacts/evidence/bullet_gui.png').stat().st_size>1000


def test_PACK_010_actual_x11_viewer_selected_rgb_drone_panels():
    from maicon_sim.core.engine import MatchEngine
    from maicon_sim.sensors.gateway import SensorGateway
    from maicon_sim.backends.bullet.backend import BulletBackend
    from maicon_sim.viewer.pygame_viewer import PygameViewer
    c=config();engine=MatchEngine(c);start(engine)
    gateway=SensorGateway(c,BulletBackend(c));gateway.camera_slots={'B-1'};gateway.update(engine)
    viewer=PygameViewer(c,gateway=gateway)
    try:
        assert viewer.pg.display.get_driver()=='x11'
        frame=gateway.get_frame('B-1');assert frame['captured_tick']==0
        viewer.draw(engine.snapshot())
        assert viewer._last_drone is not None
        pixels=viewer.pg.surfarray.array3d(viewer.screen)
        # The RGB and drone panels contain actual camera pixels with variation.
        left=pixels.shape[0]-330
        assert np.std(pixels[left:left+300,135:365])>5
        assert np.std(pixels[left:left+300,440:690])>5
        viewer.save(ROOT/'artifacts/evidence/viewer_rgb_x11.png')
    finally:viewer.close();gateway.close()
