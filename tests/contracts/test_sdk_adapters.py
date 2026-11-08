import asyncio
import pytest
from maicon_sim.sdk.report_worker import ReportWorker
from maicon_sim.sdk.session import SessionCache
from maicon_sim.adapters.ros2.transport import FakeRosTransport,MATCH_QOS
from maicon_sim.adapters.ros2.port import ROS2RobotPort


@pytest.mark.contract
def test_latest_report_replaces_pending_and_is_retransmitted():
    class Port:
        def __init__(self): self.values=[]
        async def submit_m3(self,value):
            self.values.append(value)
            return {"accepted":True,"received":value}
        async def get_me(self): return {"phase":"running"}
    async def case():
        port=Port(); worker=ReportWorker(port,"m3")
        worker.update({"sectors":[{"sector":"CM","objects":[{"type":"TANK","count":1}]}]})
        worker.update({"sectors":[{"sector":"CM","objects":[{"type":"TANK","count":2}]}]})
        await worker.flush_once()
        await worker.flush_once()
        assert port.values==[{"sectors":[{"sector":"CM","objects":[{"type":"TANK","count":2}]}]}]*2
        assert worker.acknowledged_revision==2
        await worker.close()
    asyncio.run(case())


@pytest.mark.contract
def test_API_011_unknown_outcome_late_A_commit_repaired_by_B_resend():
    class Port:
        def __init__(self): self.stored=None; self.calls=0; self.late=None
        async def submit_m3(self,value):
            self.calls+=1
            if self.calls==1:
                self.late=value
                raise asyncio.TimeoutError()
            self.stored=value
            return {"accepted":True,"received":value}
        async def get_me(self): return {"phase":"running"}
    async def case():
        port=Port(); worker=ReportWorker(port,"m3")
        worker.update({"sectors":[{"sector":"CM","objects":[{"type":"TANK","count":1}]}]}); await worker.flush_once()
        worker.update({"sectors":[{"sector":"CM","objects":[{"type":"TANK","count":2}]}]}); await worker.flush_once()
        assert port.stored=={"sectors":[{"sector":"CM","objects":[{"type":"TANK","count":2}]}]}
        port.stored=port.late
        assert port.stored=={"sectors":[{"sector":"CM","objects":[{"type":"TANK","count":1}]}]}
        await worker.flush_once()
        assert port.stored=={"sectors":[{"sector":"CM","objects":[{"type":"TANK","count":2}]}]}
    asyncio.run(case())


@pytest.mark.contract
def test_next_session_clears_evidence_but_same_session_preserves():
    cache=SessionCache()
    cache.accept({"match_id":"a"});cache.observations["object"]={}
    assert not cache.accept({"match_id":"a"})
    assert cache.observations
    assert cache.accept({"match_id":"b"})
    assert not cache.observations


@pytest.mark.contract
def test_fake_ROS_latched_recovery_stop_and_pan_wire_units():
    async def case():
        transport=FakeRosTransport()
        transport.publish("/mil/match",{"mode":"mission","cmd":"start"},MATCH_QOS)
        port=ROS2RobotPort(transport)
        assert (await port.latest_observations())["match"]["cmd"]=="start"
        await port.command_velocity(.1,.2)
        assert transport.published[-1]==("/cmd_vel",{"linear_x_mps":.1,"angular_z_rps":.2})
        transport.publish("/mil/match",{"mode":"mission","cmd":"pause"},MATCH_QOS)
        assert transport.published[-1][1]=={"linear_x_mps":0.0,"angular_z_rps":0.0}
        transport.register_service("/mil/gimbal",lambda request:{"message":"ok","received":request})
        result=await port.command_gimbal(20,20)
        assert result["received"]["pan"]==20 and result["received"]["tilt"]==20
        assert not port.hardware_validated
        await port.close()
        assert not any(transport.subscribers.values())
    asyncio.run(case())


@pytest.mark.contract
def test_fake_ROS_fire_timeout_not_retried():
    async def case():
        calls=[]
        async def fire(request):
            calls.append(request)
            await asyncio.sleep(2)
        transport=FakeRosTransport();transport.register_service("/mil/fire",fire)
        port=ROS2RobotPort(transport)
        with pytest.raises(asyncio.TimeoutError): await port.fire()
        assert calls==[{}]
    asyncio.run(case())
