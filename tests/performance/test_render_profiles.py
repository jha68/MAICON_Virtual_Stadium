"""Use MAICON_RENDER_BENCHMARK_SECONDS=300 for documented full profiles."""
import os
from pathlib import Path
import pytest
from maicon_sim.config.loader import load_scenario
from maicon_sim.backends.bullet.benchmark import benchmark_profile,BoundedFrameRecorder

pytestmark=pytest.mark.performance


@pytest.mark.parametrize('cameras,inference,record',[(1,0,False),(6,0,False),(6,2,True)])
def test_PERF_002_003_render_profiles(cameras,inference,record):
    cfg=load_scenario('examples/scenario_smoke_six.yaml')
    duration=float(os.environ.get('MAICON_RENDER_BENCHMARK_SECONDS','300'))
    out=Path('artifacts/performance')/f'render-{cameras}-{inference}-{record}-{duration}'
    metrics=benchmark_profile(cfg,out,duration_s=duration,camera_count=cameras,inference_hz=inference,record=record)
    assert metrics['duration_sim_s']==duration
    assert metrics['captures']==(int(duration*10)+1)*cameras+int(duration)+1
    assert metrics['render_latency_ms']['count']>=cameras+1
    assert metrics['step_latency']['count']==duration*100
    if record:
        assert metrics['record_queue_peak']<=metrics['record_queue_capacity']
        assert metrics['inference_frames']==int(duration*inference)*cameras
        assert metrics['recorded_frames']+metrics['record_dropped']==duration*10*cameras
