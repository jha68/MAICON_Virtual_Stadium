"""HTTP contract tests use the real single-writer thread, not handler mutation."""
import asyncio
import copy
import json
import time
import pytest
import httpx
from maicon_sim.config.loader import load_scenario
from maicon_sim.core.engine import MatchEngine
from maicon_sim.server.app import create_apps
from maicon_sim.server.runtime import EngineRuntime


@pytest.fixture
def setup_api():
    config=load_scenario("examples/scenario_smoke_six.yaml")
    engine=MatchEngine(config)
    engine.request("enter_ready")
    public,admin=create_apps(engine,admin_token="test-administrator")
    runtime=EngineRuntime(engine).start()
    yield engine,public,admin
    runtime.close()
    assert runtime.failure is None


def execute(public,callback,admin=None):
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=public),base_url="http://test") as client:
            if admin:
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=admin),base_url="http://test") as supervisor:
                    await callback(client,supervisor)
            else: await callback(client)
        await public.state.service.close()
    asyncio.run(run())


def post(client,path,**body):
    return client.post("/api/report/"+path,json={"mission_code":"SIMB0001",**body})


@pytest.mark.contract
@pytest.mark.parametrize("code,status",[("simb0001",200),("NOPE0001",401),("",422),("bad code",422)])
def test_API_001_002_auth_and_no_echo(setup_api,code,status):
    engine,app,_=setup_api
    async def case(client):
        response=await client.get("/api/report/me",params={"mission_code":code})
        assert response.status_code==status
        if status!=200: assert code not in response.text if code else True
    execute(app,case)


@pytest.mark.contract
def test_API_003_004_me_ready(setup_api):
    engine,app,admin=setup_api
    async def case(client,supervisor):
        response=await client.get("/api/report/me",params={"mission_code":"SIMB0001"})
        assert set(response.json())=={"slot","camp","phase","ready"}
        for _ in range(2): assert (await post(client,"ready")).json()=={"accepted":True}
        assert (await client.get("/api/report/me",params={"mission_code":"SIMB0001"})).json()["ready"]
        response=await supervisor.post("/admin/start",headers={"Authorization":"Bearer test-administrator"})
        assert response.status_code==200
        assert (await post(client,"ready")).status_code==409
    execute(app,case,admin)


@pytest.mark.contract
@pytest.mark.parametrize("payload",[
 {"sectors":["R-S1"],"goal_base":"RED_RADAR"},
 {"target":"레이더시설"}, {"search_sectors":[1]},
 {"search_sectors":["CM","cm"]},
 {"target":None,"base":None,"search_sectors":None}, {},
])
def test_API_005_006_invalid_m1(setup_api,payload):
    _,app,_=setup_api
    async def case(client):
        response=await post(client,"interpretation",**payload)
        assert response.status_code==422
        assert isinstance(response.json()["detail"],list)
    execute(app,case)


@pytest.mark.contract
@pytest.mark.parametrize("count",[-1,100,1.5,True,"2"])
def test_API_007_strict_count(setup_api,count):
    _,app,_=setup_api
    async def case(client):
        response=await post(client,"detection",sectors=[{"sector":"R-S1","objects":[{"type":"tank","count":count}]}])
        assert response.status_code==422
    execute(app,case)


@pytest.mark.contract
def test_API_008_normalize_and_replacement(setup_api):
    engine,app,admin=setup_api
    async def case(client,supervisor):
        await post(client,"ready")
        await supervisor.post("/admin/start",headers={"Authorization":"Bearer test-administrator"})
        response=await post(client,"detection",sectors=[
            {"sector":"r-s1","objects":[{"type":"tank","count":2},{"type":"drum","count":0}]},
            {"sector":"cm","objects":[]}])
        assert response.status_code==200,response.text
        assert response.json()=={"accepted":True,"received":{"sectors":[
            {"sector":"CM","objects":[]},{"sector":"R-S1","objects":[{"type":"TANK","count":2}]}]}}
        response=await post(client,"interpretation",target="red_radar",search_sectors=["r-s1","cm"],base="red_supply_depot")
        assert response.status_code==200
        response=await post(client,"interpretation",base="RED_SUPPLY_DEPOT")
        assert response.json()["received"]=={"target":None,"search_sectors":None,"base":"RED_SUPPLY_DEPOT"}
    execute(app,case,admin)


@pytest.mark.contract
@pytest.mark.parametrize("ranking",[[],["B-1"],["R-1","R-1"],["R-S1"],["R-1","R-2","R-3","R-1"]])
def test_API_009_m6_validation(setup_api,ranking):
    _,app,_=setup_api
    async def case(client):
        assert (await post(client,"situation",ranking=ranking)).status_code==422
    execute(app,case)


@pytest.mark.contract
@pytest.mark.parametrize("wait,status",[("0",200),("121",422),("-1",422),("1.0",422),("word",422)])
def test_API_013_wait_validation(setup_api,wait,status):
    _,app,_=setup_api
    async def case(client):
        result=await client.get("/api/report/order",params={"mission_code":"SIMB0001","wait":wait})
        assert result.status_code==status
    execute(app,case)


@pytest.mark.integration
def test_API_012_longpolls_leave_control_live(setup_api):
    engine,app,admin=setup_api
    async def case(client,supervisor):
        for camp in ("B","R"):
            for i in (1,2,3):
                await client.post("/api/report/ready",json={"mission_code":f"SIM{camp}000{i}"})
        tasks=[asyncio.create_task(client.get("/api/report/"+kind,params={"mission_code":f"SIM{camp}000{i}","wait":120}))
               for camp in ("B","R") for i in (1,2,3) for kind in ("order","target")]
        await asyncio.sleep(.1)
        before=engine.sim_tick
        response=await client.post("/sim/robot/v1/cmd_vel",json={"mission_code":"SIMB0001","linear_x_mps":0,"angular_z_rps":0})
        assert response.status_code==200
        assert engine.sim_tick>before
        response=await supervisor.post("/admin/start",headers={"Authorization":"Bearer test-administrator"})
        assert response.status_code==200
        orders=await asyncio.gather(*tasks[::2])
        assert all(r.json()["accepted"] for r in orders)
        for task in tasks[1::2]: task.cancel()
        _,pending=await asyncio.wait(tasks[1::2],timeout=1)
        assert not pending, "canceled target requests must finish promptly"
        await asyncio.gather(*tasks[1::2],return_exceptions=True)
        assert app.state.service.waiters.active==0
    execute(app,case,admin)


@pytest.mark.integration
def test_API_015_cancellation_has_no_waiter_leak(setup_api):
    _,app,_=setup_api
    async def case(client):
        for _ in range(100):
            task=asyncio.create_task(client.get("/api/report/order",params={"mission_code":"SIMB0001","wait":120}))
            await asyncio.sleep(.001)
            task.cancel()
            _,pending=await asyncio.wait({task},timeout=1)
            assert not pending, "canceled HTTP waiter must finish promptly"
            await asyncio.gather(task,return_exceptions=True)
        assert app.state.service.waiters.active==0
    execute(app,case)


@pytest.mark.integration
def test_API_016_reset_ends_old_waiter(setup_api):
    engine,app,_=setup_api
    async def case(client):
        task=asyncio.create_task(client.get("/api/report/order",params={"mission_code":"SIMB0001","wait":120}))
        await asyncio.sleep(.05)
        await app.state.service.submit("reset")
        response=await asyncio.wait_for(task,1)
        assert response.json()=={"accepted":False,"reason":"simulator session ended"}
    execute(app,case)


@pytest.mark.contract
def test_API_019_020_rehearsal_unconfigured_separate(setup_api):
    _,app,_=setup_api
    async def case(client):
        response=await client.get("/api/rehearsal/order",params={"mission_code":"SIMB0001"})
        assert response.status_code==200
        assert response.json()["accepted"] is False
        assert "리허설" in response.json()["reason"]
        assert (await client.get("/api/rehearsal/drone",params={"mission_code":"SIMB0001"})).status_code==404
    execute(app,case)


@pytest.mark.contract
def test_ISO_005_007_no_cross_robot_or_credentials(setup_api):
    _,app,admin=setup_api
    async def case(client,supervisor):
        r=await client.get("/sim/robot/v1/state",params={"mission_code":"SIMB0001","slot":"B-2"})
        assert r.status_code==403
        r=await client.post("/sim/robot/v1/cmd_vel",json={"mission_code":"SIMB0001","slot":"B-2","linear_x_mps":0,"angular_z_rps":0})
        assert r.status_code==422
        assert "SIMB0001" not in r.text
        assert (await supervisor.get("/admin/snapshot")).status_code==401
        assert (await client.get("/admin/snapshot")).status_code==404
    execute(app,case,admin)


@pytest.mark.slow
@pytest.mark.integration
def test_API_014_real_wall_120_second_wait(setup_api):
    _,app,_=setup_api
    async def case(client):
        before=time.monotonic()
        response=await client.get("/api/report/order",params={"mission_code":"SIMB0001","wait":120})
        elapsed=time.monotonic()-before
        assert elapsed>=120
        assert elapsed<123
        assert response.status_code==200 and not response.json()["accepted"]
    execute(app,case)


@pytest.mark.integration
def test_API_011_real_service_delayed_ingress_unknown_outcome_repair(setup_api):
    engine,app,admin=setup_api
    async def case(client,supervisor):
        await post(client,"ready")
        await supervisor.post("/admin/start",headers={"Authorization":"Bearer test-administrator"})
        engine.config.scenario["events"].append({"event_id":"late-A","clock":"sim","at_ms":0,
            "kind":"http_delay","parameters":{"slot":"B-1","path":"/api/report/detection",
            "duration_ms":200,"stage":"before_ingress","match_occurrence":1,"drop_response_after_commit":False}})
        def report(count):return {"sectors":[{"sector":"R-S1","objects":[{"type":"tank","count":count}]}]}
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(post(client,"detection",**report(1)),.03)
        response=await post(client,"detection",**report(2))
        assert response.json()["received"]["sectors"][0]["objects"][0]["count"]==2
        await asyncio.sleep(.25)
        assert engine.reports["B-1"]["m3"]["sectors"][0]["objects"][0]["count"]==1
        response=await post(client,"detection",**report(2))
        assert engine.reports["B-1"]["m3"]["sectors"][0]["objects"][0]["count"]==2
        assert response.json()["accepted"]
    execute(app,case,admin)


@pytest.mark.integration
def test_API_019_independent_rehearsal_and_active_robot_conflict(setup_api):
    engine,app,admin=setup_api
    async def case(client,supervisor):
        auth={"Authorization":"Bearer test-administrator"}
        # Existing report session remains ready; sharing robots must fail.
        response=await supervisor.post("/admin/configure",headers=auth,json={
            "scenario_path":"examples/scenario_smoke_six.yaml","clock_mode":"realtime","session":"rehearsal"})
        assert response.status_code==409
        await app.state.service.submit("stop")
        response=await supervisor.post("/admin/configure",headers=auth,json={
            "scenario_path":"examples/scenario_smoke_six.yaml","clock_mode":"realtime","session":"rehearsal"})
        assert response.status_code==200,response.text
        response=await supervisor.post("/admin/ready-phase?session=rehearsal",headers=auth)
        assert response.status_code==200
        response=await client.post("/api/rehearsal/ready",json={"mission_code":"SIMB0001"})
        assert response.status_code==200
        response=await supervisor.post("/admin/start?session=rehearsal",headers=auth)
        assert response.status_code==200
        response=await client.get("/api/rehearsal/me",params={"mission_code":"SIMB0001"})
        assert response.json()["phase"]=="running"
        response=await client.get("/api/report/me",params={"mission_code":"SIMB0001"})
        assert response.json()["phase"]=="finished"
        response=await supervisor.post("/admin/configure",headers=auth,json={
            "scenario_path":"examples/scenario_smoke_six.yaml","clock_mode":"realtime"})
        assert response.status_code==409
        params={"mission_code":"SIMB0001"}
        order=await client.get("/api/rehearsal/order",params=params)
        assert order.json()["accepted"] and "tactical_command" in order.json()["order"]
        target=await client.get("/api/rehearsal/target",params=params)
        assert target.json()["accepted"] is False
        m1=await client.post("/api/rehearsal/interpretation",json={**params,"target":"red_radar","base":"red_supply_depot","search_sectors":["r-s1","cm"]})
        assert m1.json()=={"accepted":True,"received":{"target":"RED_RADAR","base":"RED_SUPPLY_DEPOT","search_sectors":["CM","R-S1"]}}
        m3=await client.post("/api/rehearsal/detection",json={**params,"sectors":[{"sector":"cm","objects":[]}]})
        assert m3.json()=={"accepted":True,"received":{"sectors":[{"sector":"CM","objects":[]}]}}
        rehearsal=app.state.service.rehearsal_engine
        assert rehearsal.match_id!=engine.match_id
        handshake=await client.get("/sim/session",params=params)
        assert handshake.json()["match_id"]==rehearsal.match_id
        command=await client.post("/sim/robot/v1/cmd_vel",json={**params,"linear_x_mps":0,"angular_z_rps":.1})
        assert command.status_code==200
        assert rehearsal.robots["B-1"].omega==.1 and engine.robots["B-1"].omega==0
        runtime=engine._runtime
        # A writer-owned fixture advances to the exact publication boundary.
        await asyncio.wrap_future(runtime.submit_operation(lambda:setattr(rehearsal,"match_elapsed_ticks",24000)))
        target=await client.get("/api/rehearsal/target",params=params)
        assert target.json()["accepted"] and target.json()["order"]["objective"]=="RED_MAINTENANCE"
        assert (await supervisor.post("/admin/finish?session=rehearsal",headers=auth)).status_code==200
        late=await client.post("/api/rehearsal/detection",json={**params,"sectors":[{"sector":"CM","objects":[]}]})
        assert late.status_code==409
        m6=await client.post("/api/rehearsal/situation",json={**params,"ranking":["R-1","R-2","R-3"]})
        assert m6.status_code==200 and m6.json()["accepted"]
        assert rehearsal.phase=="finished" and engine.phase=="finished"
        assert all(not any(reports.values()) for reports in engine.reports.values())
    execute(app,case,admin)


@pytest.mark.contract
@pytest.mark.parametrize('body',[
 {},{'mission_code':None},{'mission_code':'short'},
 {'mission_code':'UNKNOWN1'},{'mission_code':'SIMB0001','ready':True},
])
def test_API_002_missing_bad_or_unknown_body(setup_api,body):
    _,app,_=setup_api
    async def case(client):
        response=await client.post('/api/report/ready',json=body)
        assert response.status_code==(401 if body.get('mission_code')=='UNKNOWN1' else 422)
        assert isinstance(response.json()['detail'],str if response.status_code==401 else list)
        assert all(str(value) not in response.text for key,value in body.items() if key=='mission_code' and value)
    execute(app,case)


@pytest.mark.contract
def test_API_004_waiting_rejects_ready():
    engine=MatchEngine(load_scenario('examples/scenario_smoke_six.yaml'))
    app,_=create_apps(engine)
    with EngineRuntime(engine):
        async def case(client):
            assert (await post(client,'ready')).status_code==409
        execute(app,case)


@pytest.mark.contract
@pytest.mark.parametrize('sectors',[
 [{'sector':'R-S1','objects':[{'type':'tank','count':1},{'type':'TANK','count':1}]}],
 [{'sector':'R-S1','objects':[]},{'sector':'r-s1','objects':[]}],
])
def test_API_007_duplicate_normalized_class_and_sector(setup_api,sectors):
    _,app,_=setup_api
    async def case(client):
        assert (await post(client,'detection',sectors=sectors)).status_code==422
    execute(app,case)


@pytest.mark.integration
def test_API_013_wait_one_second_without_early_timeout(setup_api):
    _,app,_=setup_api
    async def case(client):
        before=time.monotonic()
        response=await client.get('/api/report/order',params={'mission_code':'SIMB0001','wait':1})
        assert time.monotonic()-before>=1
        assert response.json()['accepted'] is False
    execute(app,case)


@pytest.mark.integration
def test_API_021_false_order_is_not_success(setup_api):
    from maicon_sim.sdk.http_port import HTTPPort
    _,app,_=setup_api
    async def case(client):
        port=HTTPPort('http://test','SIMB0001',client=client)
        result=await port.await_order(0)
        assert result['accepted'] is False
        assert result['reason']=='임무는 경기 진행이 시작되면 게시됩니다'
        assert 'order' not in result
    execute(app,case)


@pytest.mark.integration
def test_API_022_finished_retries_do_not_mutate_reports(setup_api):
    engine,app,admin=setup_api
    async def case(client,supervisor):
        auth={'Authorization':'Bearer test-administrator'}
        await post(client,'ready');await supervisor.post('/admin/start',headers=auth)
        await post(client,'interpretation',target='RED_RADAR')
        await supervisor.post('/admin/finish',headers=auth)
        before=copy.deepcopy(engine.reports)
        for _ in range(3):
            assert (await post(client,'interpretation',target='RED_COMMS')).status_code==409
            assert (await post(client,'detection',sectors=[{'sector':'CM','objects':[]}])).status_code==409
        assert engine.reports==before
    execute(app,case,admin)


@pytest.mark.integration
def test_API_012_slow_sensor_copy_does_not_block_command_ingress():
    class SlowGateway:
        capabilities={'rgb':False,'semantic':True,'lidar':True,'depth':False}
        def get(self,slot,channel):
            time.sleep(.5)
            return {'hp':4,'hp_max':4,'battery_pct':100,'sequence':1,'captured_tick':0,'received_tick':0}
    engine=MatchEngine(load_scenario('examples/scenario_smoke_six.yaml'))
    engine.request('enter_ready');engine.request('ready','B-1');engine.request('start')
    app,_=create_apps(engine,gateway=SlowGateway())
    async def case(client):
        image=asyncio.create_task(client.get('/sim/robot/v1/state',params={'mission_code':'SIMB0001'}))
        await asyncio.sleep(.05)
        before=time.monotonic()
        response=await client.post('/sim/robot/v1/cmd_vel',json={'mission_code':'SIMB0001','linear_x_mps':0,'angular_z_rps':.1})
        assert response.status_code==200
        assert time.monotonic()-before<.25
        assert not image.done()
        assert (await image).status_code==200
    with EngineRuntime(engine):execute(app,case)


@pytest.mark.integration
@pytest.mark.render
def test_ISO_009_admin_backend_switch_rebuilds_shared_sensor_gateway():
    from maicon_sim.sensors.gateway import SensorGateway
    engine=MatchEngine(load_scenario('examples/scenario_smoke_six.yaml'))
    gateway=SensorGateway(engine.config)
    app,admin=create_apps(engine,gateway,admin_token='test-administrator')
    async def case(client,supervisor):
        auth={'Authorization':'Bearer test-administrator'}
        await app.state.service.submit('stop')
        response=await supervisor.post('/admin/configure',headers=auth,json={
            'scenario_path':'examples/scenario_smoke_six.yaml','backend':'3d','clock_mode':'realtime'})
        assert response.status_code==200,response.text
        session=await client.get('/sim/session',params={'mission_code':'SIMB0001'})
        assert session.json()['capabilities']['rgb'] is True
        response=await client.get('/sim/robot/v1/semantic',params={'mission_code':'SIMB0001'})
        assert response.status_code==409
        deadline=time.monotonic()+5
        while True:
            response=await client.get('/sim/robot/v1/camera',params={'mission_code':'SIMB0001'})
            if response.status_code==200:break
            assert response.status_code==503 and time.monotonic()<deadline
            await asyncio.sleep(.05)
        assert response.headers['content-type']=='image/jpeg'
        await app.state.service.submit('stop')
        response=await supervisor.post('/admin/configure',headers=auth,json={
            'scenario_path':'examples/scenario_smoke_six.yaml','backend':'2d','clock_mode':'realtime'})
        assert response.status_code==200,response.text
        session=await client.get('/sim/session',params={'mission_code':'SIMB0001'})
        assert session.json()['capabilities']['rgb'] is False
        assert session.json()['capabilities']['semantic'] is True
    try:
        with EngineRuntime(engine,gateway) as runtime:
            execute(app,case,admin)
            assert runtime.failure is None
    finally:gateway.close()


@pytest.mark.contract
@pytest.mark.parametrize('number',['NaN','Infinity','-Infinity'])
def test_API_007_nonfinite_JSON_rejected_before_journal(setup_api,number):
    engine,app,_=setup_api
    async def case(client):
        before=len(engine.journal)
        content='{"mission_code":"SIMB0001","sectors":[{"sector":"CM","objects":[{"type":"tank","count":'+number+'}]}]}'
        response=await client.post('/api/report/detection',content=content,headers={'Content-Type':'application/json'})
        assert response.status_code==422
        assert 'SIMB0001' not in response.text
        # Invalid transport JSON never reaches the core's canonical event sink.
        assert len(engine.journal)==before
    execute(app,case)


@pytest.mark.integration
def test_ADMIN_TEST_MODE_001_configure_drone_practice_only():
    from maicon_sim.sensors.gateway import SensorGateway
    from jsonschema import Draft202012Validator
    from pathlib import Path
    schema=json.loads(Path('src/maicon_sim/resources/schemas/admin_configure.schema.json').read_text())
    Draft202012Validator.check_schema(schema)
    validator=Draft202012Validator(schema)
    assert not list(validator.iter_errors({'scenario_path':'scenario.yaml','test_mode':True}))
    assert list(validator.iter_errors({'scenario_path':'scenario.yaml','test_mode':'true'}))
    engine=MatchEngine(load_scenario('examples/scenario_smoke_six.yaml'))
    gateway=SensorGateway(engine.config)
    app,admin=create_apps(engine,gateway,admin_token='test-administrator')
    async def case(client,supervisor):
        auth={'Authorization':'Bearer test-administrator'}
        await app.state.service.submit('stop')
        config={'scenario_path':'examples/scenario_smoke_six.yaml','backend':'2d','clock_mode':'realtime','test_mode':True}
        response=await supervisor.post('/admin/configure',headers=auth,json=config)
        assert response.status_code==200,response.text
        params={'mission_code':'SIMB0001'}
        deadline=time.monotonic()+3
        while True:
            response=await client.get('/api/report/drone',params={**params,'camera':'test1'})
            if response.status_code==200:break
            assert response.status_code==503 and time.monotonic()<deadline
            await asyncio.sleep(.05)
        assert response.status_code==200
        assert response.headers['X-Test-Mode']=='on'
        assert 'X-Camp' not in response.headers and 'X-Destroyed' not in response.headers
        assert (await client.get('/api/report/drone',params=params)).status_code==409
        response=await supervisor.post('/admin/configure',headers=auth,json={**config,'test_mode':'true'})
        assert response.status_code==422
        await app.state.service.submit('enter_ready');await post(client,'ready');await app.state.service.submit('start')
        response=await supervisor.post('/admin/configure',headers=auth,json={**config,'test_mode':False})
        assert response.status_code==409
        assert app.state.service.test_mode is True
    try:
        with EngineRuntime(engine,gateway) as runtime:
            execute(app,case,admin)
            assert runtime.failure is None
    finally:gateway.close()
