"""Private offline checkpoints, with profile identity and integrity validation."""
import json
from pathlib import Path
from .metrics import digest, write_json


IDENTITY_HASHES=('scenario_hash','rule_profile_hash','arena_hash','sensor_profile_hash','asset_manifest_hash')


def save_checkpoint(path,engine,gateway,config=None):
    """Persist a boundary after gateway.update; processes are deliberately excluded.

    Realtime render tasks have wall-time outcomes and cannot be checkpointed as
    if their live process handles were deterministic. Core replay remains available.
    """
    config=config or engine.config
    if getattr(gateway.backend,'asynchronous',False):
        raise ValueError('sensor checkpoints require offline synchronous rendering')
    if gateway._last_tick!=engine.sim_tick:
        raise ValueError('checkpoint requires gateway.update at the current engine boundary')
    state={'schema_version':'1.0','mode':'offline_core_and_sensors','match_id':engine.match_id,
           'sim_tick':engine.sim_tick,'event_seq':engine._event_seq,'hashes':{key:config.hashes[key] for key in IDENTITY_HASHES},
           'capabilities':gateway.capabilities,'core_state':engine.export_state(),
           'sensor_state':gateway.export_state()}
    state['state_sha256']=digest(state)
    write_json(path,state)
    return {'path':str(path),'sim_tick':state['sim_tick'],'event_seq':state['event_seq'],
            'mode':state['mode'],'state_sha256':state['state_sha256']}


def read_checkpoint(path,config):
    state=json.loads(Path(path).read_text())
    if state.get('schema_version')!='1.0' or state.get('mode')!='offline_core_and_sensors':
        raise ValueError('unsupported checkpoint schema or mode')
    expected=state.pop('state_sha256',None)
    if expected!=digest(state):
        raise ValueError('checkpoint state checksum mismatch')
    for key in IDENTITY_HASHES:
        if state['hashes'].get(key)!=config.hashes.get(key):
            raise ValueError(f'checkpoint profile mismatch: {key}')
    if state['core_state']['sim_tick']!=state['sim_tick']:
        raise ValueError('checkpoint tick mismatch')
    return state


def restore_checkpoint(path,engine,gateway,config=None):
    if getattr(gateway.backend,'asynchronous',False):
        raise ValueError('sensor checkpoints require offline synchronous rendering')
    state=read_checkpoint(path,config or engine.config)
    if state['capabilities']!=gateway.capabilities:
        raise ValueError('checkpoint sensor capabilities mismatch')
    engine.restore_state(state['core_state'])
    gateway.restore_state(state['sensor_state'])
    return {'sim_tick':state['sim_tick'],'event_seq':state['event_seq'],'mode':state['mode']}
