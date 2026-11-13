"""Information boundaries concern normal participant DTOs, not OS sandboxing."""
import json
from copy import deepcopy
import pytest
from maicon_sim.config.loader import load_scenario
from maicon_sim.core.engine import MatchEngine
from maicon_sim.core.events import canonical
from maicon_sim.core.types import SLOTS
from maicon_sim.sensors.gateway import SensorGateway, SensorUnavailable

pytestmark=pytest.mark.unit


def running(config):
    e=MatchEngine(config)
    e.request('enter_ready')
    for slot in SLOTS:e.request('ready',slot)
    e.request('start')
    return e


def forbidden_keys(value):
    forbidden={'face_id','box_id','world_pose','true_pose','opponent_state','opponent_hp',
               'opponent_ammo','opponent_m3','segmentation','body_id','facility_id','actual_start_pose',
               'expected_m1','objects_truth','score','scores'}
    if isinstance(value,dict):
        return (set(value)&forbidden)|set().union(*(forbidden_keys(v) for v in value.values()),set())
    if isinstance(value,list):return set().union(*(forbidden_keys(v) for v in value),set())
    return set()


def test_ISO_001_participant_dtos_have_no_truth_fields():
    config=load_scenario('examples/scenario_smoke_six.yaml')
    e=running(config);g=SensorGateway(config)
    try:
        g.update(e)
        for slot in SLOTS:
            me=e.request('me',slot)
            assert set(me)=={'slot','camp','phase','ready'}
            for channel in ('state','match','odom','imu','scan','semantic'):
                value=g.get(slot,channel)
                assert not forbidden_keys(value)
                if channel not in ('state',):
                    assert '"hp":' not in canonical(value) and '"ammo":' not in canonical(value)
            assert set(g.get(slot,'state'))=={'hp','hp_max','battery_pct','sequence','captured_tick','received_tick'}
            semantic=g.get(slot,'semantic')
            assert all('sector' not in d and 'world' not in d for d in semantic['detections'])
            order=e.request('order',slot)['order']
            assert set(order)=={'target','search_sectors','base','tactical_command','issued_at'}
            assert not forbidden_keys(order)
        with pytest.raises(SensorUnavailable) as err:g.get('B-1','camera')
        assert err.value.status==503
    finally:g.close()


def test_ISO_008_hidden_reports_do_not_change_public_observations():
    config=load_scenario('examples/scenario_smoke_six.yaml')
    a=running(config);b=running(config)
    # The opponent's stored M3 score changes the private M6 answer, while its
    # physical appearance and all allowed inputs remain exactly the same.
    b.reports['R-1']['m3']={'sectors':[{'sector':'B-S1','objects':[{'type':'TANK','count':1}]}]}
    ga,gb=SensorGateway(config),SensorGateway(config)
    try:
        ga.update(a);gb.update(b)
        for channel in ('state','match','odom','imu','scan','semantic'):
            assert canonical(ga.get('B-1',channel))==canonical(gb.get('B-1',channel))
        assert ga.get_drone('B-1')==gb.get_drone('B-1')
        assert a.request('me','B-1')==b.request('me','B-1')
        assert a.request('order','B-1')==b.request('order','B-1')
        a.request('finish');b.request('finish')
        assert a._base_scores()['R-1']['m3']==0
        assert b._base_scores()['R-1']['m3']==7
    finally:ga.close();gb.close()
