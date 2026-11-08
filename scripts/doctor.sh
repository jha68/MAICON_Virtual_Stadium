#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
.venv/bin/python - <<'PY'
import importlib.metadata as md
import json
import os
import platform
import numpy as np
from pydantic import BaseModel
from fastapi import FastAPI
from maicon_sim.config.loader import load_scenario

class Spike(BaseModel):
    ready: bool
assert Spike(ready=True).ready
assert FastAPI().openapi()['openapi']
load_scenario('examples/scenario_smoke_six.yaml')
versions={name: md.version(name) for name in ('numpy','pydantic','fastapi','pybullet','opencv-python-headless','pygame-ce','Pillow')}
import pybullet as p
for _ in range(10):
    client=p.connect(p.DIRECT)
    try:
        shape=p.createVisualShape(p.GEOM_BOX, halfExtents=[.4,.4,.4], rgbaColor=[.2,.5,.8,1], physicsClientId=client)
        p.createMultiBody(baseMass=0,baseVisualShapeIndex=shape,physicsClientId=client)
        frame=p.getCameraImage(64,48,viewMatrix=p.computeViewMatrix([1,1,1],[0,0,0],[0,0,1]),renderer=p.ER_TINY_RENDERER,physicsClientId=client)
        rgba=np.asarray(frame[2],dtype=np.uint8).reshape(48,64,4)
        assert rgba[:,:,:3].std()>0
    finally:
        p.disconnect(client)
os.environ['SDL_VIDEODRIVER']='dummy'
os.environ['SDL_AUDIODRIVER']='dummy'
import pygame
pygame.display.init()
pygame.display.set_mode((32,32))
pygame.display.quit()
import cv2
assert cv2.cvtColor(np.zeros((8,8,3),np.uint8),cv2.COLOR_BGR2GRAY).shape==(8,8)
print(json.dumps({'status':'passed','platform':platform.platform(),'python':platform.python_version(),'versions':versions,'checks':['local_schema_and_semantics','numpy_pydantic_fastapi','bullet_direct_10_reopens','opencv_numpy_abi','pygame_dummy']},indent=2))
PY
