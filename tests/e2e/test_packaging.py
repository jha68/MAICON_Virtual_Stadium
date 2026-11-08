"""Build/install actual distributions; synthetic smoke needs no remote model."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
import yaml

ROOT=Path(__file__).resolve().parents[2]
pytestmark=pytest.mark.e2e


class SafeEnv(dict):
    """Pass inherited bindings to tools without exposing them in pytest repr."""
    def __repr__(self):
        return "<inherited environment; values hidden>"


def command(args,*,cwd=None,env=None,timeout=180):
    result=subprocess.run([str(v) for v in args],cwd=cwd,env=env,text=True,capture_output=True,timeout=timeout)
    assert result.returncode==0, result.stdout[-2000:]+result.stderr[-2000:]
    return result


@pytest.fixture(scope="module")
def wheel_install(tmp_path_factory):
    root=tmp_path_factory.mktemp("distribution")/"checkout with spaces"
    shutil.copytree(ROOT,root,ignore=shutil.ignore_patterns(".git",".venv",".cache","artifacts","__pycache__",".pytest_cache"))
    env=SafeEnv(os.environ)
    env.setdefault("UV_CACHE_DIR",str(root.parent/"uv-cache"))
    env.setdefault("UV_PYTHON_INSTALL_DIR",str(root.parent/"uv-python"))
    uv=shutil.which("uv")
    assert uv,"The documented distribution workflow requires uv"
    command([uv,"build","--wheel","--out-dir",root.parent/"dist"],cwd=root,env=env)
    wheel=next((root.parent/"dist").glob("*.whl"))
    target=root.parent/"installed with spaces"/"venv"
    command([uv,"venv","--python",sys.executable,target],env=env)
    python=target/"bin/python"
    requirements=root.parent/"requirements.txt"
    command([uv,"export","--frozen","--no-emit-project","--no-dev","--format","requirements-txt","--output-file",requirements],cwd=root,env=env)
    command([uv,"pip","install","--python",python,"--require-hashes","-r",requirements],env=env)
    command([uv,"pip","install","--python",python,"--no-deps",wheel],env=env)
    outside=root.parent/"outside working directory";outside.mkdir()
    return root,python,outside,env


def test_PACK_002_009_wheel_core_only_resources_and_lock_outside_checkout(wheel_install):
    root,python,outside,env=wheel_install
    code="""
import importlib.resources as r, importlib.util, json, sys
from maicon_sim.config.loader import load_scenario, canonical_hash
from maicon_sim.core.engine import MatchEngine
p=r.files('maicon_sim').joinpath('resources/examples/scenario_smoke_six.yaml')
cfg=load_scenario(p)
engine=MatchEngine(cfg)
assert len(engine.robots)==6
assert r.files('maicon_sim').joinpath('resources/uv.lock').read_bytes()
assert importlib.util.find_spec('pybullet') is None
assert importlib.util.find_spec('pygame') is None
assert importlib.util.find_spec('rclpy') is None
assert 'pybullet' not in sys.modules and 'pygame' not in sys.modules
print(json.dumps({'scenario':cfg.scenario['scenario_id'],'core_only':True,'packaged_lock':True}))
"""
    result=command([python,"-c",code],cwd=outside,env=env)
    assert json.loads(result.stdout)["core_only"]
    result=command([python,"-m","maicon_sim","run","--example","smoke_six","--backend","2d","--clock","accelerated","--headless","--out",outside/"full smoke"],cwd=outside,env=env)
    score=json.loads((outside/"full smoke/result.json").read_text())
    assert {v["total"] for v in score["scores"].values()}=={20}


def test_PACK_005_008_complete_cli_workflow_in_spaced_paths(wheel_install):
    root,python,outside,env=wheel_install
    # Explicitly shortened clock fixture keeps the CLI plumbing check bounded;
    # PACK-002 above separately executes the unmodified 330-second sample.
    data=yaml.safe_load((root/"examples/rules_prestudy.yaml").read_text())
    data["timing"].update(match_ms=1000,objective_publish_ms=800,report_ms=300)
    (root/"examples/rules_prestudy.yaml").write_text(yaml.safe_dump(data,sort_keys=False))
    def cli(*args):
        return command([python,"-m","maicon_sim",*args],cwd=outside,env=env)
    cli("doctor","--backend","2d")
    cli("validate","--scenario",root/"examples/scenario_smoke_six.yaml")
    cli("assets","build","--manifest",root/"examples/assets_synthetic.yaml","--out",outside/"assets")
    cli("run","--scenario",root/"examples/scenario_smoke_six.yaml","--backend","2d","--clock","accelerated","--headless","--out",outside/"smoke")
    cli("replay","--run",outside/"smoke","--backend","2d","--verify","--out",outside/"replay")
    compared=cli("compare","--left",outside/"smoke","--right",outside/"replay","--mode","core")
    assert json.loads(compared.stdout)["equal"]
    cli("batch","--scenario",root/"examples/scenario_smoke_six.yaml","--backend","2d","--seeds","0:2","--out",outside/"batch")
    cli("generate","--template",root/"examples/scenario_smoke_six.yaml","--seed","42","--count","1","--out",outside/"generated")
    assert (outside/"smoke/result.json").is_file() and (outside/"replay/result.json").is_file()
    assert list((outside/"batch").rglob("result.json"))


@pytest.fixture(scope="module")
def ubuntu_image():
    docker=shutil.which("docker")
    assert docker,"PACK-001 requires the managed Docker capability"
    env=SafeEnv(os.environ)
    for name in ("DOCKER_HOST","DOCKER_CONTEXT","DOCKER_TLS","DOCKER_TLS_VERIFY","DOCKER_CERT_PATH"):
        env.pop(name,None)
    base=[docker,"--host=unix:///var/run/docker.sock"]
    command(base+["info","--format","{{.ServerVersion}}"],env=env)
    tag="maicon-sim:acceptance"
    args=base+["build","-t",tag]
    ca=Path("/etc/ssl/certs/ca-certificates.crt")
    if ca.is_file():args += ["--secret",f"id=proxy_ca,src={ca}"]
    command(args+["."],cwd=ROOT,env=env,timeout=900)
    return base,tag,env


@pytest.mark.slow
def test_PACK_001_003_004_clean_ubuntu_frozen_install_and_offline_3d(ubuntu_image):
    docker,tag,env=ubuntu_image
    code="""
import json, os, pathlib, platform, subprocess, sys
import numpy as np
from maicon_sim.config.loader import load_scenario, canonical_hash
from maicon_sim.backends.bullet.backend import BulletBackend
from maicon_sim.evaluation.runner import run_episode
assert '22.04' in pathlib.Path('/etc/os-release').read_text()
assert sys.version_info[:2]==(3,10)
assert 'DISPLAY' not in os.environ
cfg=load_scenario('examples/scenario_perception_gallery.yaml')
with BulletBackend(cfg) as backend:
    frame=backend.capture_rgb('B-1/front',0)
    assert frame['data'].shape==(480,640,3)
    assert frame['data'].dtype==np.uint8 and frame['data'].std()>5
cfg.rules['timing'].update(match_ms=100,objective_publish_ms=80,report_ms=100)
cfg.hashes['rule_profile_hash']=canonical_hash(cfg.rules)
result,root=run_episode(cfg,backend='3d',out=pathlib.Path('/app/artifacts/offline-gallery'))
assert {v['total'] for v in result['scores'].values()}=={20}
print(json.dumps({'ubuntu':'22.04','python':platform.python_version(),'offline':True,'headless_rgb':True}))
"""
    result=command(docker+["run","--rm","--network","none","--entrypoint","/app/.venv/bin/python",tag,"-c",code],env=env,timeout=180)
    assert '"offline": true' in result.stdout
