"""Measure six real participant processes on a chosen local CPU budget."""
import argparse
import asyncio
import cProfile
import json
import os
from pathlib import Path
import pstats
import subprocess
import sys
import time

from maicon_sim.backends.bullet import render_worker
from maicon_sim.config.loader import load_scenario
from maicon_sim.core.engine import MatchEngine
from maicon_sim.evaluation.realtime import LocalServers, ParticipantProcesses
from maicon_sim.sensors.gateway import SensorGateway
from maicon_sim.server.app import create_apps
from maicon_sim.server.runtime import EngineRuntime
from maicon_sim.server.web import DashboardManager

ORIGINAL_RENDER = render_worker._render_process


def profile_render(connection, config, assets, headless):
    profiler = cProfile.Profile()
    try:
        profiler.runcall(ORIGINAL_RENDER, connection, config, assets, headless)
    finally:
        profiler.dump_stats(os.environ['MAICON_PROFILE_RENDER_FILE'])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--policy', choices=['idle', 'patrol', 'baseline'], required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--seconds', type=float, default=20)
    parser.add_argument('--no-profile', action='store_true')
    parser.add_argument('--cpus', type=int, default=2)
    parser.add_argument('--sample-resources', action='store_true')
    args = parser.parse_args()
    root = Path(args.out).resolve()
    root.mkdir(parents=True, exist_ok=False)
    if args.cpus < 1 or args.seconds <= 0:
        parser.error('--cpus and --seconds must be positive')
    cpus = sorted(os.sched_getaffinity(0))[:args.cpus]
    os.sched_setaffinity(0, cpus)
    os.environ['MAICON_LLM_PROVIDER'] = 'fixture'
    os.environ['MAICON_PROFILE_RENDER_FILE'] = str(root / 'render.pstats')
    if not args.no_profile: render_worker._render_process = profile_render
    original_run = EngineRuntime._run
    def profile_core(runtime):
        profiler = cProfile.Profile()
        try: profiler.runcall(original_run, runtime)
        finally: profiler.dump_stats(str(root / 'core.pstats'))
    if not args.no_profile: EngineRuntime._run = profile_core
    original_popen = subprocess.Popen
    def profile_agent(command, **kwargs):
        if 'agent' in command and '--slot' in command:
            slot = command[command.index('--slot') + 1]
            command = [command[0], '-m', 'cProfile', '-o', str(root / (slot+'.pstats')), *command[1:]]
        return original_popen(command, **kwargs)
    if not args.no_profile: subprocess.Popen = profile_agent
    config = load_scenario('examples/scenario_smoke_six.yaml')
    engine = MatchEngine(config, retain_journal=False)
    backend = render_worker.AsyncBulletBackend(config)
    gateway = SensorGateway(config, backend)
    public, admin = create_apps(engine, gateway, 'profile-only-admin')
    manager = DashboardManager(public.state.service, root)
    runtime = EngineRuntime(engine, gateway, on_tick=manager.on_tick)
    data = {}
    try:
        with runtime, LocalServers(public, admin) as servers:
            manager.public_url = servers.public_url
            async def exercise():
                await manager.command('ready', args.policy)
                end = time.monotonic()+90
                while not all(r.ready for r in engine.robots.values()):
                    if runtime.failure: raise runtime.failure
                    if time.monotonic()>end: raise RuntimeError('Participants not ready')
                    manager.maintain()
                    await asyncio.sleep(.1)
                await manager.command('start')
                start = time.monotonic()
                initial_tick = engine.match_elapsed_ticks
                initial_drops = gateway.dropped
                initial_poses = {s:(r.pose.x_m,r.pose.y_m) for s,r in engine.robots.items()}
                sampler = None
                if args.sample_resources:
                    from resource_usage import ProcessSampler
                    sampler = ProcessSampler(os.getpid())
                    sampler.sample()
                while time.monotonic() - start < args.seconds:
                    await asyncio.sleep(min(1., max(0., args.seconds - (time.monotonic() - start))))
                    if sampler:
                        sampler.sample()
                elapsed=time.monotonic()-start
                from maicon_sim.evaluation.metrics import machine
                data.update(environment=machine(), scenario_seed=config.scenario['seed'],
                            policy=args.policy, cpu_affinity=cpus, profiled=not args.no_profile, wall_s=elapsed,
                            simulated_s=(engine.match_elapsed_ticks-initial_tick)/100,
                            real_time_factor=(engine.match_elapsed_ticks-initial_tick)/100/elapsed,
                            frame_drops=gateway.dropped-initial_drops,
                            runtime=runtime.metrics, renderer=backend.metrics,
                            movement_m={s:((r.pose.x_m-initial_poses[s][0])**2+(r.pose.y_m-initial_poses[s][1])**2)**.5 for s,r in engine.robots.items()})
                if sampler:
                    data['resources'] = sampler.summary()
                await manager.service.submit('finish')
                await manager.service.submit('stop')
                await asyncio.sleep(1)
                await asyncio.to_thread(manager.close)
            asyncio.run(exercise())
    finally:
        manager.close()
        runtime.close()
        backend.close()
    for profile in root.glob('*.pstats'):
        stats=pstats.Stats(str(profile))
        rows=[]
        for (file,line,name),(primitive,calls,total,cumulative,_) in stats.stats.items():
            rows.append(dict(function=f'{file}:{line}:{name}', calls=calls, self_s=total, cumulative_s=cumulative))
        data[profile.stem+'_top_self']=sorted(rows,key=lambda r:r['self_s'],reverse=True)[:15]
        data[profile.stem+'_top_cumulative']=sorted(rows,key=lambda r:r['cumulative_s'],reverse=True)[:15]
    (root/'metrics.json').write_text(json.dumps(data,indent=2)+'\n')
    print(json.dumps({k:data[k] for k in ['policy','wall_s','simulated_s','real_time_factor','frame_drops','movement_m']},indent=2),flush=True)


if __name__ == '__main__': main()
