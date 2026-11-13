"""Single writer, fixed-tick engine shared by 2D and 3D.

HTTP threads submit immutable requests to the queue. Only step()/request() in the
engine thread may mutate truth. SIM policies are the supplied rules profile.
"""
from concurrent.futures import Future
from collections import deque
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timedelta
import math
import threading

from .clocks import ticks
from .events import canonical
from .laser import accumulate_contacts
from .rules import EngineError, normalize_m1, normalize_m3, normalize_m6, keys, finite_number, invalid
from .scoring import inventory_from_boxes, score_m1, score_m3, risk_numerator, score_m6, finalize_scores
from .types import Pose2, RobotTruth, SLOTS, camp_for_slot, FACILITIES

ROBOT_COMMANDS = {'cmd_vel', 'gimbal', 'fire', 'oled'}
SUPERVISOR_COMMANDS = {'configure', 'enter_ready', 'start', 'pause', 'resume', 'finish', 'stop', 'reset', 'start_failure', 'fault', 'operator_control'}


class MatchEngine:
    def __init__(self, config, event_sink=None, retain_journal=True, session_namespace=''):
        self.config = config
        self.session_namespace = session_namespace
        self.event_sink = event_sink
        self.retain_journal = retain_journal
        self.journal = []
        self._queue = deque()
        self._queue_lock = threading.Lock()
        self._ingress_seq = 0
        self.queue_peak = 0
        self._event_seq = 0
        self.episode_index = 0
        self._replay_mode = False
        self._reset(config)

    def _reset(self, config):
        self.config = config
        self.episode_index += 1
        suffix = f"-{self.session_namespace}" if self.session_namespace else ""
        self.match_id = f"{config.scenario['scenario_id']}{suffix}-{self.episode_index:04d}"
        self.run_id = self.match_id
        self.phase = 'waiting'
        self._match_command = 'standby'
        self.paused = False
        self.sim_tick = self.match_elapsed_ticks = self.reporting_elapsed_ticks = self.robot_effect_ticks = 0
        self.robots = {}
        self.codes = {}
        for agent in config.scenario['agents']:
            pose = Pose2(**agent['start_pose'])
            pose = Pose2(pose.x_m, pose.y_m, (pose.yaw_rad + math.pi) % (2 * math.pi) - math.pi)
            slot = agent['slot']
            self.robots[slot] = RobotTruth(slot, camp_for_slot(slot), pose, pose,
                                           hp=config.rules['robot']['hp_max'], ammo=config.rules['robot']['ammo_initial'])
            self.codes[agent['mission_code'].upper()] = slot
        self.boxes = deepcopy(config.scenario['boxes'])
        self.orders = {o['slot']: deepcopy(o) for o in config.scenario['orders']}
        self.reports = {s: {'m1': None, 'm3': None, 'm6': None} for s in SLOTS}
        self.submitted_m6 = set()
        self.destroyed = set()
        self.target_published = False
        self.order_published = False
        self.order_issued_at = None
        self.target_issued_at = None
        self.capture_camp = None
        self.capture_pending = []
        self.manual_until = {}
        self.manual_interventions = 0
        self._operator_dispatching = False
        self.end_reason = None
        self.frozen = None
        self.scores = None
        self.dwell = {}
        self.executed_events = set()
        self.dynamic_events = []
        self.command_scripts = []
        self.sensor_dropouts = {}
        self.transport_faults = []
        self.inventory = inventory_from_boxes(self.boxes)
        self.report_rejections = 0
        self.queue_peak = 0
        self.collision_events = 0
        self._base_pose_signature = None
        self.base_blocked = self._blocked_bases()
        self.emit('phase_changed', payload={'phase': self.phase})

    @property
    def destroyed_facilities(self):
        return self.destroyed

    @property
    def cmd(self):
        if self.paused:
            return 'pause'
        fallback = {'idle': 'idle', 'waiting': 'standby', 'ready': 'standby',
                    'running': 'start', 'reporting': 'report', 'finished': 'stop'}[self.phase]
        if self.phase == 'running':
            command = getattr(self, '_match_command', fallback)
            return command if command in ('start', 'resume') else fallback
        return fallback

    def record(self, kind, payload=None, category='measurement', actor='sensor'):
        return self.emit(kind, actor=actor, payload=payload, category=category)

    @property
    def eligible(self):
        return {s for s, r in self.robots.items() if r.admitted and r.started}

    @property
    def mode(self):
        return self.config.scenario.get('mode', 'mission')

    def timestamp(self, tick=None):
        epoch = datetime.fromisoformat(self.config.scenario['epoch_kst'])
        return epoch + timedelta(milliseconds=10 * (self.sim_tick if tick is None else tick))

    def issued_at(self):
        return self.timestamp().strftime('%Y-%m-%d %H:%M:%S')

    def emit(self, kind, actor='engine', payload=None, category='derived'):
        self._event_seq += 1
        event = {'schema_version': '1.0', 'run_id': self.run_id, 'match_id': self.match_id,
                 'event_seq': self._event_seq, 'sim_tick': self.sim_tick,
                 'match_elapsed_ticks': self.match_elapsed_ticks,
                 'reporting_elapsed_ticks': self.reporting_elapsed_ticks,
                 'category': category, 'kind': kind, 'actor': actor, 'payload': deepcopy(payload or {})}
        if self.retain_journal:
            self.journal.append(event)
        if self.event_sink:
            self.event_sink(deepcopy(event))
        return event

    def enqueue(self, kind, slot=None, payload=None, session_id=None):
        future = Future()
        with self._queue_lock:
            self._ingress_seq += 1
            self._queue.append((self._ingress_seq, kind, slot, deepcopy(payload or {}), session_id or self.match_id, future))
            self.queue_peak = max(self.queue_peak, len(self._queue))
        return future

    def request(self, kind, slot=None, payload=None, _ingress_seq=None):
        """Synchronous writer API for accelerated mode and the queue consumer."""
        payload = deepcopy(payload or {})
        with self._queue_lock:
            if _ingress_seq is None:
                self._ingress_seq += 1
                _ingress_seq = self._ingress_seq
            else:
                self._ingress_seq = max(self._ingress_seq, _ingress_seq)
        safe = {k: v for k, v in payload.items() if k not in ('mission_code', 'admin_token', 'config')}
        if kind == 'configure' and 'config' in payload:
            safe['scenario_path'] = str(payload['config'].path)
        category_kind = 'process_lifecycle' if kind == 'process_lifecycle' else 'supervisor_command' if kind in SUPERVISOR_COMMANDS else 'robot_command' if kind in ROBOT_COMMANDS else 'http_request_ingress'
        record = {'kind': kind, 'slot': slot, 'payload': safe, 'ingress_seq': _ingress_seq}
        nonfinite_path = self._nonfinite_path(payload)
        if nonfinite_path is not None:
            # Invalid JSON numbers cannot enter a strict canonical journal. Keep
            # replayable rejection metadata rather than the invalid body/value.
            record['payload'] = {}
            record['validation_error'] = {'type': 'nonfinite', 'loc': list(nonfinite_path)}
        self.emit(category_kind, slot or 'supervisor', record, 'input')
        try:
            if nonfinite_path is not None:
                invalid('non-finite numbers are forbidden', nonfinite_path)
            return self._request(kind, slot, payload)
        except EngineError:
            if kind in {'m1', 'm3', 'm6'}:
                self.report_rejections += 1
            raise

    @classmethod
    def _nonfinite_path(cls, value, path=()):
        if isinstance(value, float) and not math.isfinite(value):
            return path
        if isinstance(value, dict):
            for key, item in value.items():
                found = cls._nonfinite_path(item, (*path, key))
                if found is not None:
                    return found
        elif isinstance(value, (list, tuple)):
            for index, item in enumerate(value):
                found = cls._nonfinite_path(item, (*path, index))
                if found is not None:
                    return found
        return None

    def _request(self, kind, slot, payload):
        if kind == 'snapshot':
            return self.snapshot()
        if kind == 'result':
            return self.result()
        if kind in SUPERVISOR_COMMANDS:
            return self._supervisor(kind, slot, payload)
        if slot not in self.robots:
            raise EngineError(409, '이 경기에 편성되지 않은 팀입니다')
        robot = self.robots[slot]
        if kind in ROBOT_COMMANDS and not self._operator_dispatching and self.manual_until.get(slot, 0) > self.sim_tick:
            return {'accepted': False, 'message': 'locked', 'reason': 'operator_control'}
        if kind == 'process_lifecycle':
            keys(payload, ('event', 'generation', 'exit_code', 'pid'), ('event',))
            if payload['event'] not in {'started', 'exited', 'restarted', 'failed', 'restart_limit_reached', 'terminated'}:
                invalid('unknown process lifecycle event', ('event',))
            if 'generation' in payload and (type(payload['generation']) is not int or not 0 <= payload['generation'] <= 3):
                invalid('generation must be an integer 0..3', ('generation',))
            if 'exit_code' in payload and payload['exit_code'] is not None and type(payload['exit_code']) is not int:
                invalid('exit_code must be an integer or null', ('exit_code',))
            if 'pid' in payload and (type(payload['pid']) is not int or payload['pid'] < 1):
                invalid('pid must be a positive integer', ('pid',))
            return {'accepted': True}
        if kind == 'me':
            return {'slot': slot, 'camp': robot.camp, 'phase': self.phase, 'ready': robot.ready}
        if kind == 'ready':
            if self.phase != 'ready':
                raise EngineError(409, '준비 단계가 아닙니다')
            keys(payload, ('mission_code',))
            robot.ready = True
            return {'accepted': True}
        if kind in {'order', 'target'}:
            # Admission is decided at start. Before that, assigned teams may
            # wait for publication even though admitted is still false.
            if self.phase in {'running', 'reporting', 'finished'} and not robot.admitted:
                return {'accepted': False, 'reason': '이 경기에 편성되지 않은 팀입니다'}
            if kind == 'order' and self.order_published:
                return {'accepted': True, 'order': {**deepcopy(self.orders[slot]['expected_m1']), 'tactical_command': self.orders[slot]['tactical_command'], 'issued_at': self.order_issued_at}}
            if kind == 'target' and self.target_published:
                objective = self.config.scenario['objectives_by_camp'][robot.camp]
                labels = {'COMMAND_POST': '작전지휘소', 'MAINTENANCE': '정비소', 'SUPPLY_DEPOT': '군수보급소'}
                return {'accepted': True, 'order': {'objective': objective, 'objective_label': labels[objective.split('_', 1)[1]], 'issued_at': self.target_issued_at}}
            return {'accepted': False, 'reason': '임무는 경기 진행이 시작되면 게시됩니다' if kind == 'order' else 'M5 목표거점은 종료 60초 전에 게시됩니다'}
        if kind in {'m1', 'm3', 'm6'}:
            value = normalize_m1(payload) if kind == 'm1' else normalize_m3(payload) if kind == 'm3' else normalize_m6(payload, robot.camp)
            required_phase = 'reporting' if kind == 'm6' else 'running'
            if self.phase != required_phase or slot not in self.eligible:
                raise EngineError(409, '현재 단계 또는 출발 상태에서 보고할 수 없습니다')
            self.reports[slot][kind] = value
            self.emit('report_committed', slot, {'kind': kind, 'received': value})
            result = {'accepted': True, 'received': deepcopy(value)}
            if kind == 'm6':
                self.submitted_m6.add(slot)
                if self.eligible <= self.submitted_m6:
                    self._finish()
            return result
        if kind == 'cmd_vel':
            keys(payload, ('mission_code', 'linear_x_mps', 'angular_z_rps'), ('linear_x_mps', 'angular_z_rps'))
            v = finite_number(payload['linear_x_mps'], -.6, .6, ('linear_x_mps',))
            w = finite_number(payload['angular_z_rps'], -3., 3., ('angular_z_rps',))
            if self._drive_allowed(robot):
                robot.command_v, robot.command_omega = v, w
                if not self.config.sensors.get('actuation', {}).get('drive_accel_mps2', 0):
                    robot.v, robot.omega = v, w
                robot.last_velocity_received_tick = self.sim_tick
            return {'accepted': True}
        if kind == 'gimbal':
            keys(payload, ('mission_code', 'pan', 'tilt', 'speed', 'acc'), ('pan', 'tilt', 'speed', 'acc'))
            for field, low, high in (('pan', -100, 100), ('tilt', -100, 100), ('speed', 1, 270), ('acc', 1, 254)):
                finite_number(payload[field], low, high, (field,))
            if not self._device_allowed(robot):
                return {'message': 'locked'}
            robot.target_pan, robot.target_tilt = payload['pan'], payload['tilt']
            robot.gimbal_speed, robot.gimbal_acc = payload['speed'], payload['acc']
            return {'message': 'ok'}
        if kind == 'fire':
            keys(payload, ('mission_code',))
            return self.fire(slot)
        if kind == 'oled':
            keys(payload, ('mission_code', 'line', 'text'), ('line', 'text'))
            if type(payload['line']) is not int or not 0 <= payload['line'] <= 3:
                invalid('line must be an integer 0..3', ('line',))
            if not isinstance(payload['text'], str) or not payload['text'].isascii() or len(payload['text']) > 21:
                invalid('text must be ASCII with at most 21 characters', ('text',))
            robot.oled[payload['line']] = payload['text']
            return {'accepted': True}
        raise EngineError(404, 'Unknown engine request')

    def _supervisor(self, kind, slot, payload):
        if kind == 'operator_control':
            keys(payload, ('command', 'parameters'), ('command',))
            command = payload['command']
            if slot not in self.robots or command not in ('cmd_vel', 'gimbal', 'fire', 'release'):
                invalid('unknown operator command or slot')
            if self.phase != 'running' or self.paused:
                raise EngineError(409, 'manual control requires running')
            robot = self.robots[slot]
            if command == 'release':
                self.manual_until.pop(slot, None)
                robot.v = robot.omega = robot.command_v = robot.command_omega = 0.
                robot.target_pan, robot.target_tilt = robot.pan, robot.tilt
                robot.pan_velocity = robot.tilt_velocity = 0.
                return {'accepted': True}
            self._operator_dispatching = True
            try:
                value = self._request(command, slot, payload.get('parameters', {}))
            finally:
                self._operator_dispatching = False
            if self.manual_until.get(slot, 0) <= self.sim_tick:
                self.manual_interventions += 1
                self.emit('operator_intervention', slot, {'command': command})
            self.manual_until[slot] = self.sim_tick+50
            return value
        if kind in {'reset', 'configure'}:
            if kind == 'configure' and self.phase not in {'idle', 'finished'}:
                raise EngineError(409, 'configure requires idle or finished')
            with self._queue_lock:
                old_requests = list(self._queue)
                self._queue.clear()
            for *_, future in old_requests:
                if not future.done():
                    future.set_exception(EngineError(409, 'simulator session ended'))
            self._reset(payload.get('config', self.config))
            return {'match_id': self.match_id}
        if kind == 'enter_ready':
            if self.phase != 'waiting':
                raise EngineError(409, 'ready phase requires waiting')
            self._phase('ready')
        elif kind == 'start':
            if self.phase != 'ready':
                raise EngineError(409, 'start requires ready')
            for r in self.robots.values():
                r.admitted = r.started = r.ready
            self._phase('running')
            self.order_published = True
            self.order_issued_at = self.issued_at()
            self.emit('order_published')
            if not self.eligible:
                self.end_reason = 'no_eligible'
                self._enter_reporting()
                self._finish()
        elif kind == 'pause':
            if self.phase != 'running' or self.paused:
                raise EngineError(409, 'pause requires running')
            self.paused = True
            self._match_command = 'pause'
            self._stop_actions()
            self.emit('paused')
        elif kind == 'resume':
            if self.phase != 'running' or not self.paused:
                raise EngineError(409, 'resume requires paused running')
            self.paused = False
            self._match_command = 'resume'
            self.emit('resumed')
        elif kind == 'finish':
            if self.phase != 'running':
                raise EngineError(409, 'finish requires running')
            self.end_reason = 'admin'
            self._enter_reporting()
        elif kind == 'stop':
            self.end_reason = self.end_reason or 'admin'
            if self.frozen is None:
                self._enter_reporting()
            self._finish()
        elif kind == 'start_failure':
            slot = slot or payload.get('slot')
            if slot not in self.robots or self.phase not in {'ready', 'running'}:
                raise EngineError(409, 'start_failure requires active team before reporting')
            robot = self.robots[slot]
            robot.started = False
            robot.v = robot.omega = 0.
            robot.laser_until = self.robot_effect_ticks
            self.emit('start_failed', slot)
            if self.phase == 'running' and not self.eligible:
                self.end_reason = 'no_eligible'
                self._enter_reporting()
                self._finish()
        elif kind == 'fault':
            event = deepcopy(payload)
            if 'at_tick' in event and (type(event['at_tick']) is not int or event['at_tick'] < 0):
                invalid('at_tick must be a nonnegative integer', ('at_tick',))
            if 'kind' not in event:
                event['kind'] = event.get('fault_id')
            event.setdefault('clock', 'sim')
            event.setdefault('at_ms', event.pop('at_tick', self.sim_tick) * 10)
            event.setdefault('event_id', f'fault-{self._ingress_seq}')
            event.setdefault('parameters', {})
            allowed = {'pause', 'resume', 'force_reporting', 'start_failure', 'sensor_dropout',
                       'drone_facility_destroyed', 'robot_command', 'http_delay', 'robot_state_correction'}
            if event['kind'] not in allowed:
                invalid('unknown fault_id', ('fault_id',))
            if type(event['at_ms']) is not int or event['at_ms'] < 0 or event['at_ms'] % 10:
                invalid('at_tick must be a nonnegative integer', ('at_tick',))
            if event.get('scope') in self.robots and 'slot' not in event['parameters']:
                event['parameters']['slot'] = event['scope']
            if event['kind'] == 'robot_state_correction':
                self._validate_correction(event['parameters'])
            self.dynamic_events.append(event)
        return {'accepted': True}

    def _phase(self, value):
        self.phase = value
        self._match_command = {'idle': 'idle', 'waiting': 'standby', 'ready': 'standby',
                               'running': 'start', 'reporting': 'report', 'finished': 'stop'}[value]
        self.emit('phase_changed', payload={'phase': value})

    def _stop_actions(self):
        self.manual_until.clear()
        for r in self.robots.values():
            r.v = r.omega = 0.
            r.command_v = r.command_omega = r.pan_velocity = r.tilt_velocity = 0.
            r.target_pan, r.target_tilt = r.pan, r.tilt
            r.laser_until = self.robot_effect_ticks
        self.dwell.clear()

    def _motion_phase_allowed(self, robot):
        return not self.paused and (self.mode == 'practice' or (self.phase == 'running' and robot.slot in self.eligible))

    def _drive_allowed(self, robot):
        return self._motion_phase_allowed(robot) and self.robot_effect_ticks >= robot.drive_locked_until

    def _device_allowed(self, robot):
        return self._motion_phase_allowed(robot) and self.robot_effect_ticks >= robot.device_locked_until

    def fire(self, slot):
        r = self.robots[slot]
        now = self.robot_effect_ticks
        if not self._device_allowed(r):
            return {'message': 'locked', 'left_ms': max(0, r.device_locked_until - now) * 10}
        if r.ammo == 0:
            return {'message': 'empty', 'left_ms': 0}
        if now < r.next_fire_tick:
            return {'message': 'reloading', 'left_ms': (r.next_fire_tick - now) * 10}
        r.ammo -= 1
        r.laser_until = now + ticks(self.config.rules['robot']['laser_on_ms'])
        r.next_fire_tick = now + ticks(self.config.rules['robot']['fire_period_ms'])
        self.emit('laser_fired', slot, {'ammo_remaining': r.ammo, 'laser_until': r.laser_until})
        return {'message': 'fired', 'left_ms': (r.next_fire_tick - now) * 10}

    def _deadlines(self):
        timing = self.config.rules['timing']
        if self.phase == 'running':
            if not self.target_published and self.match_elapsed_ticks >= ticks(timing['objective_publish_ms']):
                self.target_published = True
                self.target_issued_at = self.issued_at()
                self.emit('target_published')
            if self.match_elapsed_ticks >= ticks(timing['match_ms']):
                self.end_reason = 'timeout'
                self._enter_reporting()
        elif self.phase == 'reporting' and self.reporting_elapsed_ticks >= ticks(timing['report_ms']):
            self._finish()

    def _enter_reporting(self):
        if self.frozen is not None:
            return
        self.paused = False
        self._stop_actions()
        self._phase('reporting')
        self.reporting_elapsed_ticks = 0
        self.frozen = {'reports': deepcopy(self.reports), 'robots': {s: {'hp': r.hp, 'ammo': r.ammo} for s, r in self.robots.items()},
                       'destroyed': sorted(self.destroyed), 'capture_camp': self.capture_camp,
                       'eligible': sorted(self.eligible), 'inventory': deepcopy(self.inventory)}
        self.emit('score_frozen', payload=deepcopy(self.frozen))
        if not self.eligible:
            self.end_reason = 'no_eligible'
            self._finish()

    def _finish(self):
        if self.phase == 'finished':
            return
        if self.frozen is None:
            self._enter_reporting()
            if self.phase == 'finished':
                return
        base = self._base_scores()
        risks = {s: risk_numerator(v['hp'], v['ammo'], base[s]['m3']) for s, v in self.frozen['robots'].items()}
        for s in SLOTS:
            opponents = {o: risks[o] for o in SLOTS if camp_for_slot(o) != camp_for_slot(s)}
            base[s]['m6'] = score_m6(self.reports[s]['m6'], opponents)
        self.scores = finalize_scores(base, set(self.frozen['eligible']))
        self._phase('finished')
        self.emit('match_finished', payload={'scores': self.scores, 'end_reason': self.end_reason or 'admin'})

    def _base_scores(self):
        f = self.frozen
        base = {}
        for s in SLOTS:
            camp = camp_for_slot(s)
            target = self.orders[s]['expected_m1']['target']
            alliance_targets = [self.orders[x]['expected_m1']['target'] for x in SLOTS if camp_for_slot(x) == camp]
            report = f['reports'][s]
            base[s] = {'m1': score_m1(report['m1'], self.orders[s]['expected_m1']),
                       'm2': 10 * (target in f['destroyed']) + 5 * all(t in f['destroyed'] for t in alliance_targets),
                       'm3': score_m3(report['m3'], f['inventory'], camp) if s in f['eligible'] else 0,
                       'm4': {4: 15, 3: 12, 2: 8, 1: 3, 0: 0}[f['robots'][s]['hp']],
                       'm5': 10 * (camp == f['capture_camp']), 'm6': 0}
        return base

    def _validate_correction(self, payload):
        keys(payload, ('slot', 'hp', 'ammo'), ('slot',))
        if payload['slot'] not in self.robots:
            invalid('unknown slot', ('slot',))
        if not any(k in payload for k in ('hp', 'ammo')):
            invalid('hp or ammo is required')
        for key, limit in (('hp', 4), ('ammo', 8)):
            if key in payload and (type(payload[key]) is not int or not 0 <= payload[key] <= limit):
                invalid(f'{key} must be an integer between 0 and {limit}', (key,))

    def _correct_robot_state(self, payload):
        """Evaluator-only adjudication; never exposed by the participant bridge."""
        self._validate_correction(payload)
        if self.phase != 'running' or self.frozen is not None:
            raise EngineError(409, 'adjudication is closed after score freeze')
        robot = self.robots[payload['slot']]
        changed = {}
        for key in ('hp', 'ammo'):
            if key in payload:
                setattr(robot, key, payload[key])
                changed[key] = payload[key]
        self.emit('robot_state_corrected', 'supervisor', {'slot': robot.slot, **changed})

    def destroy_facility(self, facility_code, actor='supervisor'):
        if self.phase != 'running' or facility_code in self.destroyed:
            return False
        if facility_code not in FACILITIES:
            invalid('unknown facility')
        self.destroyed.add(facility_code)
        self.emit('facility_destroyed', actor, {'facility_code': facility_code})
        return True

    def apply_hit(self, receiver, actor='engine', at_effect_tick=None):
        if self.phase != 'running' and self.mode != 'practice':
            return False
        r = self.robots[receiver]
        now = self.robot_effect_ticks if at_effect_tick is None else at_effect_tick
        if now < r.invulnerable_until:
            return False
        r.hp = max(0, r.hp - 1)
        policy = self.config.rules['robot']
        r.invulnerable_until = now + ticks(policy['invulnerability_ms'])
        r.device_locked_until = now + ticks(policy['hit_lock_ms'])
        if r.hp == 0:
            r.drive_locked_until = now + ticks(policy['hit_lock_ms'])
            r.v = r.omega = 0.
        r.target_pan, r.target_tilt = r.pan, r.tilt
        r.laser_until = now
        self.dwell = {p: n for p, n in self.dwell.items() if self._receiver_owner(p[1]) != receiver}
        self.emit('hit_applied', actor, {'receiver': receiver, 'hp': r.hp})
        return True

    def _blocked_bases(self):
        from .geometry2d import footprint, segment_intersects_polygon
        signature = tuple((s, r.pose) for s, r in sorted(self.robots.items()))
        if getattr(self, '_base_pose_signature', None) == signature:
            return dict(self.base_blocked)
        self._base_pose_signature = signature
        g = self.config.sensors['geometry']
        footprints = []
        for robot in self.robots.values():
            polygon = footprint(robot.pose, g['footprint_length_m'], g['footprint_width_m'])
            footprints.append((polygon, polygon.min(axis=0), polygon.max(axis=0)))
        blocked = {}
        for base in self.config.arena['bases']:
            segment = base['trigger_segment_xy_m']
            ax, ay = segment[0]
            bx, by = segment[1]
            left, right, bottom, top = min(ax, bx), max(ax, bx), min(ay, by), max(ay, by)
            # Reject distant footprints before the exact contact test. The
            # micrometre slack preserves the exact test's contact tolerances.
            blocked[base['code']] = any(
                low[0] <= right + 1e-6 and high[0] >= left - 1e-6
                and low[1] <= top + 1e-6 and high[1] >= bottom - 1e-6
                and segment_intersects_polygon(segment, polygon)
                for polygon, low, high in footprints)
        return blocked

    def _capture_edges(self, blocked):
        if self.config.rules['policy']['m5_capture'] == 'sensor_timestamp_first':
            self._capture_sensor_events(blocked)
            self.base_blocked = blocked
            return
        if self.phase == 'running' and not self.paused and self.target_published:
            objectives = self.config.scenario['objectives_by_camp']
            for base in sorted(self.config.arena['bases'], key=lambda b: b['base_id']):
                code = base['code']
                if blocked[code] and not self.base_blocked.get(code, False):
                    camps = [camp for camp, target in objectives.items() if target == code]
                    if camps:
                        self.capture_camp = camps[0]
                        self.end_reason = 'capture'
                        self.emit('base_captured', payload={'base': code, 'camp': self.capture_camp})
                        self._enter_reporting()
                        break
        self.base_blocked = blocked

    def _capture_sensor_events(self, blocked):
        from .capture import crossing_fraction, event_nonce, select_capture
        if self.phase != 'running' or self.paused or not self.target_published:
            return
        settings = self.config.rules.get('capture', {})
        tolerance = settings.get('timestamp_tolerance_ms', 10.)
        latency = settings.get('latency_ms_by_base', {})
        offsets = settings.get('sensor_offset_ms_by_base', {})
        default_latency = settings.get('default_latency_ms', 20.)
        now = self.sim_tick*10.
        for base in self.config.arena['bases']:
            code = base['code']
            if not blocked[code] or self.base_blocked.get(code, False):
                continue
            camps = [camp for camp, objective in self.config.scenario['objectives_by_camp'].items() if objective == code]
            if not camps:
                continue
            fractions = [crossing_fraction(getattr(self, '_interval_poses', {}).get(s, r.pose), r.pose,
                         base['trigger_segment_xy_m'], self.config.sensors['geometry']) for s, r in self.robots.items()]
            fraction = min((f for f in fractions if f is not None), default=1.)
            detected = now-10.+fraction*10.
            event = {'base': code, 'camp': camps[0], 'crossed_ms': detected,
                     'detected_ms': detected+offsets.get(code, 0.),
                     'arrived_ms': detected+latency.get(code, default_latency)}
            event['nonce'] = event_nonce(self.config.scenario['seed'], code, detected)
            self.capture_pending.append(event)
            self.emit('base_sensor_edge', payload=event)
        if not self.capture_pending:
            return
        # Explicit SIM buffering horizon: allow all packets in the documented
        # timestamp tolerance to arrive before adjudicating. Exact hardware
        # buffering is not published, so it stays a profile assumption.
        horizon = tolerance+max([default_latency, *latency.values()])+2*max([0., *map(abs, offsets.values())])
        if now < min(e['crossed_ms'] for e in self.capture_pending)+horizon:
            return
        winner = select_capture([e for e in self.capture_pending if e['arrived_ms'] <= now], tolerance)
        if winner:
            self.capture_camp, self.end_reason = winner['camp'], 'capture'
            self.emit('base_captured', payload={**winner, 'arbitration': 'sensor_timestamp_then_arrival'})
            self._enter_reporting()

    def _scheduled(self):
        values = {'sim': self.sim_tick, 'match': self.match_elapsed_ticks, 'reporting': self.reporting_elapsed_ticks}
        for event in self.config.scenario.get('events', []) + self.dynamic_events:
            ident = event['event_id']
            clock = event['clock']
            if ident in self.executed_events or (clock == 'reporting' and self.frozen is None):
                continue
            if values[clock] < ticks(event['at_ms']):
                continue
            self.executed_events.add(ident)
            kind, p = event['kind'], event.get('parameters', {})
            self.emit('transport_fault' if kind == 'http_delay' else 'supervisor_command', 'supervisor',
                      {'kind': 'scheduled_event', 'event_id': ident, 'event': event}, 'input')
            self._apply_scheduled_event(event)
        self._advance_scripts()

    def _apply_scheduled_event(self, event):
        ident, kind, p = event['event_id'], event['kind'], event.get('parameters', {})
        try:
            if kind in {'pause', 'resume', 'start_failure'}:
                self._supervisor(kind, p.get('slot'), p)
            elif kind == 'force_reporting':
                self._supervisor('finish', None, {})
            elif kind == 'drone_facility_destroyed':
                self.destroy_facility(p['facility_code'])
            elif kind == 'sensor_dropout':
                self.sensor_dropouts[(p['slot'], p['sensor'])] = self.sim_tick + ticks(p['duration_ms'])
            elif kind == 'robot_command':
                self.command_scripts.append({'slot': p['slot'], 'linear_x_mps': p['linear_x_mps'],
                                            'angular_z_rps': p['angular_z_rps'],
                                            'end': self.sim_tick + ticks(p['duration_ms']), 'next': self.sim_tick})
            elif kind == 'http_delay':
                self.transport_faults.append(deepcopy(event))
            elif kind == 'robot_state_correction':
                self._correct_robot_state(p)
        except EngineError as e:
            self.emit('event_rejected', payload={'event_id': ident, 'status': e.status})
    def _advance_scripts(self, replay=False):
        remaining = []
        for script in self.command_scripts:
            if self.sim_tick >= script['end']:
                if not replay:
                    self.request('cmd_vel', script['slot'], {'linear_x_mps': 0., 'angular_z_rps': 0.})
            else:
                if self.sim_tick >= script['next']:
                    if not replay:
                        self.request('cmd_vel', script['slot'], {'linear_x_mps': script['linear_x_mps'], 'angular_z_rps': script['angular_z_rps']})
                    script['next'] = self.sim_tick + 10
                remaining.append(script)
        self.command_scripts = remaining

    def step(self, count=1):
        for _ in range(count):
            self._step()

    def _step(self):
        if self._replay_mode:
            self._advance_scripts(replay=True)
        else:
            self._scheduled()
        self._deadlines()
        queue_session = self.match_id
        with self._queue_lock:
            pending = list(self._queue)
            self._queue.clear()
        # Distinct action classes have contract priority; ingress FIFO applies
        # within a class, rather than allowing an early action to bypass a report.
        priority = lambda item: (0 if item[1] in SUPERVISOR_COMMANDS else 2 if item[1] in ROBOT_COMMANDS else 1, item[0])
        for seq, kind, slot, payload, session, future in sorted(pending, key=priority):
            if future.cancelled():
                continue
            try:
                if session != self.match_id:
                    raise EngineError(409, 'simulator session ended')
                value = self.request(kind, slot, payload, _ingress_seq=seq)
            except Exception as exc:
                future.set_exception(exc)
            else:
                future.set_result(value)
        if self.match_id != queue_session:
            # Publish the new session's tick-zero sensor boundary before its
            # first interval. Queued reset must not silently skip that sample.
            return
        effect_start = self.robot_effect_ticks
        active = self.phase == 'running' and not self.paused
        effect_active = (active or self.mode == 'practice') and not self.paused
        contacts = set()
        self._interval_poses = {s: r.pose for s, r in self.robots.items()}
        dynamics = self.config.sensors.get('actuation', {})
        from .actuation import approach, servo_step
        for r in self.robots.values():
            if not self._drive_allowed(r) or self.sim_tick - r.last_velocity_received_tick >= ticks(self.config.rules['robot']['watchdog_ms']):
                r.v = r.omega = 0.
                r.command_v = r.command_omega = 0.
            elif dynamics.get('drive_accel_mps2', 0):
                r.v = approach(r.v, r.command_v, dynamics['drive_accel_mps2']*.01)
                r.omega = approach(r.omega, r.command_omega, dynamics.get('turn_accel_rps2', 6.)*.01)
            if not self._device_allowed(r):
                r.target_pan, r.target_tilt = r.pan, r.tilt
                r.pan_velocity = r.tilt_velocity = 0.
                r.laser_until = effect_start
            else:
                for attr, target, deg_per_unit in (('pan', r.target_pan, .5), ('tilt', r.target_tilt, .15)):
                    old = getattr(r, attr)
                    position, velocity = servo_step(old*deg_per_unit, getattr(r, attr+'_velocity'),
                        target*deg_per_unit, r.gimbal_speed,
                        r.gimbal_acc*dynamics.get('gimbal_acc_deg_s2_per_unit', 0.), .01,
                        limits=(-100*deg_per_unit, 100*deg_per_unit))
                    setattr(r, attr, position/deg_per_unit)
                    setattr(r, attr+'_velocity', velocity)
        if any(r.v or r.omega for r in self.robots.values()):
            from .planar_motion import move_robots
            poses = move_robots(self.robots, self.boxes, self.config.arena['bounds'], self.config.sensors['geometry'], dt=.01)
            for slot, pose in poses.items():
                if pose == self.robots[slot].pose and (self.robots[slot].v or self.robots[slot].omega):
                    self.collision_events += 1
                self.robots[slot].pose = pose
        if effect_active and any(r.laser_until > effect_start for r in self.robots.values()):
            from .geometry3d import laser_contacts
            contacts = laser_contacts(self.robots, self.boxes, self.config.arena['bounds'], self.config.sensors)
        self.sim_tick += 1
        if active:
            self.match_elapsed_ticks += 1
        if self.phase == 'reporting':
            self.reporting_elapsed_ticks += 1
        if effect_active:
            self.robot_effect_ticks += 1
        self._deadlines()
        # Expiration wins over same-boundary contact. Receiver invulnerability is
        # tested at interval start, so its first new dwell interval starts at expiry.
        if effect_active and (self.phase == 'running' or self.mode == 'practice') and not self.paused:
            self._laser_dwell(contacts, effect_start)
        else:
            self.dwell.clear()
        self._capture_edges(self._blocked_bases())
        if self.mode == 'practice' and effect_active:
            for r in self.robots.values():
                if self.robot_effect_ticks >= max(r.next_fire_tick, r.device_locked_until, r.drive_locked_until):
                    r.hp = self.config.rules['robot']['hp_max']
                    r.ammo = self.config.rules['robot']['ammo_initial']

    @staticmethod
    def _receiver_owner(receiver_key):
        return receiver_key.split('/receiver/', 1)[0]

    def _laser_dwell(self, contacts, effect_start):
        good = set()
        for emitter, receiver in contacts:
            r = self.robots[emitter]
            if r.laser_until <= self.robot_effect_ticks or not self._device_allowed(r):
                continue
            owner = self._receiver_owner(receiver)
            if owner in self.robots and self.robots[owner].invulnerable_until > effect_start:
                continue
            if owner in self.destroyed:
                continue
            good.add((emitter, receiver))
        self.dwell, candidates = accumulate_contacts(self.dwell, good, ticks(self.config.rules['robot']['hit_dwell_ms']))
        # Collect first; applying one hit must not remove another emitter's same-tick hit.
        hit_receivers = set()
        for emitter, receiver in candidates:
            owner = self._receiver_owner(receiver)
            if owner in hit_receivers:
                continue
            hit_receivers.add(owner)
            if owner in self.robots:
                self.apply_hit(owner, emitter)
            else:
                self.destroy_facility(owner, emitter)
            self.dwell = {pair: count for pair, count in self.dwell.items() if self._receiver_owner(pair[1]) != owner}

    def begin_replay(self):
        """Disable autonomous scheduler; journal inputs become the sole authority."""
        self._replay_mode = True

    def replay_input(self, event):
        """Reinject one input at its recorded processed boundary, exactly once.

        Derived events are never accepted as inputs. Call step() to advance up to
        event.sim_tick first; no transport sleeps or policy callbacks are needed.
        Scenario wrapper and its recorded heartbeats are replayed separately.
        """
        if event.get('category') != 'input':
            raise ValueError('only recorded input events may be replayed')
        if event['sim_tick'] != self.sim_tick:
            raise ValueError('replay input must be applied at its recorded sim_tick')
        self.begin_replay()
        p = event['payload']
        if p.get('validation_error', {}).get('type') == 'nonfinite':
            with self._queue_lock:
                self._ingress_seq = max(self._ingress_seq, p['ingress_seq'])
            self.emit(event['kind'], event['actor'], p, 'input')
            if p['kind'] in {'m1', 'm3', 'm6'}:
                self.report_rejections += 1
            invalid('non-finite numbers are forbidden', tuple(p['validation_error']['loc']))
        if p.get('kind') == 'scheduled_event':
            self.emit(event['kind'], event['actor'], p, 'input')
            scheduled = deepcopy(p['event'])
            self.executed_events.add(scheduled['event_id'])
            self._apply_scheduled_event(scheduled)
            return None
        return self.request(p['kind'], p.get('slot'), p.get('payload', {}),
                            _ingress_seq=p.get('ingress_seq'))

    def snapshot(self):
        receiving = {self._receiver_owner(receiver) for _, receiver in self.dwell}
        return {'match_id': self.match_id, 'episode_index': self.episode_index, 'phase': self.phase,
                'manual_slots': [s for s,t in self.manual_until.items() if t > self.sim_tick],
                'manual_interventions': self.manual_interventions,
                'paused': self.paused, 'match_command': self.cmd, 'sim_tick': self.sim_tick, 'match_elapsed_ticks': self.match_elapsed_ticks,
                'reporting_elapsed_ticks': self.reporting_elapsed_ticks, 'robot_effect_ticks': self.robot_effect_ticks,
                'robots': {s: asdict(r) for s, r in self.robots.items()}, 'boxes': deepcopy(self.boxes),
                'destroyed': sorted(self.destroyed), 'reports': deepcopy(self.reports), 'scores': deepcopy(self.scores),
                'facility_signals': {code: 'hit' if code in self.destroyed else 'receiving' if code in receiving else 'idle'
                                     for code in FACILITIES},
                'capture_camp': self.capture_camp, 'end_reason': self.end_reason,
                'target_published': self.target_published, 'order_published': self.order_published}

    def result(self):
        if self.phase != 'finished':
            raise EngineError(409, 'match has not finished')
        result = {'scores': deepcopy(self.scores), 'end_reason': self.end_reason,
                  'final_match_ms': self.match_elapsed_ticks * 10, 'final_report_ms': self.reporting_elapsed_ticks * 10}
        if self.manual_interventions:
            result['operator_interventions'] = self.manual_interventions
        return result

    def export_state(self):
        """JSON serializable checkpoint of core state; no locks/process handles."""
        fields = ('phase', 'paused', '_match_command', 'sim_tick', 'match_elapsed_ticks', 'reporting_elapsed_ticks', 'robot_effect_ticks',
                  'match_id', 'run_id', 'episode_index', 'session_namespace', 'reports', 'submitted_m6', 'destroyed', 'target_published',
                  'order_published', 'order_issued_at', 'target_issued_at', 'capture_camp', 'end_reason', 'frozen', 'scores',
                  'executed_events', 'dynamic_events', 'command_scripts', 'transport_faults', 'base_blocked',
                  'inventory', 'report_rejections', 'collision_events', 'queue_peak', '_ingress_seq', '_event_seq', 'capture_pending',
                  'manual_until', 'manual_interventions')
        state = {k: deepcopy(getattr(self, k)) for k in fields}
        for k in ('submitted_m6', 'destroyed', 'executed_events'):
            state[k] = sorted(state[k])
        state['robots'] = {s: asdict(r) for s, r in self.robots.items()}
        state['dwell'] = [[list(pair), count] for pair, count in sorted(self.dwell.items())]
        state['sensor_dropouts'] = [[list(pair), end] for pair, end in sorted(self.sensor_dropouts.items())]
        return state

    def restore_state(self, state):
        with self._queue_lock:
            if self._queue:
                raise ValueError('cannot restore with pending requests')
        for key, value in state.items():
            if key == 'robots':
                self.robots = {}
                for slot, data in value.items():
                    data = deepcopy(data)
                    data['pose'] = Pose2(**data['pose'])
                    data['initial_pose'] = Pose2(**data['initial_pose'])
                    self.robots[slot] = RobotTruth(**data)
            elif key in ('submitted_m6', 'destroyed', 'executed_events'):
                setattr(self, key, set(value))
            elif key in ('dwell', 'sensor_dropouts'):
                setattr(self, key, {tuple(pair): n for pair, n in value})
            else:
                setattr(self, key, deepcopy(value))

        if '_match_command' not in state:
            # Older checkpoints exposed start for every unpaused running state.
            self._match_command = ('pause' if self.paused else {'idle': 'idle',
                'waiting': 'standby', 'ready': 'standby', 'running': 'start',
                'reporting': 'report', 'finished': 'stop'}[self.phase])
