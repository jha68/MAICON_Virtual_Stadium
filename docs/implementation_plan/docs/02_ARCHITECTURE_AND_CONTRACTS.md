# 공통 아키텍처와 실행 계약

이 문서는 2D와 3D 구현이 공유해야 하는 규범이다. 01의 사실·가정 구분을 유지하면서 이 문서의 자료형, 시계, 좌표, 이벤트 순서를 구현한다. 외부 원본이나 이전 대화 없이 구현할 수 있어야 한다. MUST는 필수, SHOULD는 특별한 이유 없으면 적용, MAY는 선택이다.

## 1 구현 범위와 기술 결정

새 저장소 이름은 maicon-sim, Python 패키지는 maicon_sim, CLI는 maicon-sim이다. 기준 개발 환경은 Ubuntu 22.04 x86_64, Python 3.10이다. 핵심과 2D는 ROS·GPU 없이 실행되어야 한다.

| 구성 | 선택 | 경계 |
| --- | --- | --- |
| 공통 엔진 | Python dataclass, NumPy | 물리·시계·규칙의 유일한 상태 변경자 |
| 설정·검증 | Pydantic 2, PyYAML, JSON Schema 2020-12 | 알 수 없는 필드 거부, 단위·범위 검사 |
| HTTP | FastAPI, Uvicorn, httpx | 공식 모사 API와 시뮬레이터 전용 API 구분 |
| 2D | NumPy SAT 충돌, pygame-ce 뷰어 | GUI 없어도 배치 실행 가능 |
| 3D | PyBullet DIRECT, TinyRenderer | 원근 영상·가림·레이캐스트. 바퀴 동역학은 필수 범위 밖 |
| 이미지 | Pillow, NumPy | JPEG·PNG, 생성 텍스처, OpenCV는 비전 예제 선택 의존성 |
| 검증 | pytest, jsonschema | API·규칙·재생·기하 회귀검사 |
| 실제 로봇 연결 | 별도 선택 ROS 2 Humble 어댑터 | 최종 SDK가 없으면 fake transport까지 검증 |

정확한 패치 버전은 구현 시작 시 실제 설치 검증 후 lock 파일에 고정한다. 아직 설치하지 않은 조합을 검증 완료라고 표시하지 않는다. 핵심 패키지는 rclpy, pybullet, pygame를 import하지 않고 선택 어댑터만 해당 의존성을 import한다. Bullet은 3D extra, pygame는 viewer extra로 분리한다.

3D 첫 버전은 공통 평면 운동 엔진이 계산한 위치를 3D 장면에 동기화하는 방식이다. Bullet의 stepSimulation으로 별도 위치를 결정하지 않는다. 3D 객체·광학 투영·광선 가림은 실제 3차원으로 계산하지만 바퀴 마찰·미끄러짐·차체 전복을 검증했다고 주장하지 않는다. 미래 dynamics backend는 별도 프로필과 별도 합격 기준을 갖는다.

## 2 프로세스와 의존 방향

~~~text
participant process x 6
  TeamController -> ParticipantPort -> HTTPClient or InProcessPort
                                      |
public server ingress -> immutable request queue
                                      |
                         single-writer MatchEngine
                         Rules + Clock + World + Scoring
                           |                    |
                    SensorScheduler      private event journal
                           |
                2D sensor model or 3D render worker
                           |
                      public observations

admin loopback server -> supervisor commands -> same queue
observer viewer <- immutable observer snapshots (privileged)
~~~

필수 금지:
- API request handler, renderer, viewer가 WorldState를 직접 수정하지 않는다.
- 참가팀 SDK가 TruthWorld, 실제 객체 ID, 실제 상대 상태, 채점 정답을 import하거나 반환받지 않는다.
- 2D와 3D에 별도 채점 함수를 만들지 않는다.
- 단일 이벤트 루프에서 long-poll 응답을 기다리며 엔진을 멈추지 않는다.
- 보고 POST를 재전송하는 SDK가 오래된 본문을 최신 본문 뒤에 보내지 않는다.

참가팀은 별도 프로세스에서 실행한다. 빠른 unit test만 in-process 포트를 허용한다. viewer/admin은 평가자 권한이고 참가팀 화면이 아니다. 같은 OS 계정의 악의적인 파일 접근을 막는 보안 제품은 범위 밖이지만, 기본 launcher는 private 파일 경로·admin token을 참가팀 환경에 주지 않는다.

## 3 좌표와 단위

| 프레임 | 정의 |
| --- | --- |
| world | 경기장 남서쪽 원점, x 동쪽 BLUE→RED, y 북쪽, z 위 |
| robot base | x 전방, y 왼쪽, z 위; yaw 0은 world +x, +yaw는 반시계 |
| odom | 각 로봇 시작 자세를 원점으로 하는 로컬 프레임; 경기마다 초기화 |
| optical | x 영상 오른쪽, y 아래, z 광축 전방 |
| gimbal | pan+ 오른쪽, tilt+ 위쪽; 전송 위치 단위는 pan 0.5도, tilt 0.15도 |

내부 길이 m, 시간 integer tick(10ms), 속도 m/s, 각도 rad, 각속도 rad/s, 밝기·확률 0~1. 외부 서비스의 pan/tilt 위치 단위는 연결부에서만 변환한다. 내부 yaw 정규화는 [-pi,pi). 위치는 double precision, 직렬화 시 불필요한 반올림 금지.

기본 경기장 수치와 구역 경계는 examples/arena_reference.yaml의 SIM-ARENA 가정이다. 공식 크기를 참고한 시험 배치이며 실제 경기장 좌표가 아니다. S1은 북쪽 행, S3은 남쪽 행. 객체 귀속은 시나리오에 명시된 sector_id가 채점의 권위이고 로봇 위치로 결정하지 않는다.

T_WO = T_WB * T_BG(pan,tilt) * T_GO를 사용한다. 광학 회전행렬·수신부·카메라 위치는 04의 SIM-3D-GEOM 계약을 적용한다. 구현에 row/column vector를 혼용하지 않는다. 모든 수학 예시는 column vector이다.

## 4 정수 시계

dt_ms=10 고정. 전체 sim_tick은 정지 상태에도 진행한다. 별도 카운터:

- match_elapsed_ticks: running && !paused인 interval만 증가.
- reporting_elapsed_ticks: reporting interval만 증가.
- robot_effect_ticks: mission 모드는 running && !paused인 interval에서 증가한다. practice 모드는 세션의 자유연습이 활성화된 동안 phase와 관계없이 증가하여 idle/ready에서도 cooldown과 피격 잠금이 만료된다. 두 모드 모두 명시적 supervisor pause는 정지한다. 발광·재발사·피격 잠금에 사용.
- wall_monotonic: 실제 HTTP wait 및 네트워크 timeout만 계산.
- timestamp_epoch: 시나리오의 epoch_kst에 sim_tick*10ms를 더한 가상 캡처 시각. 실제 실행 날짜를 혼입하지 않는다.

SIM-PAUSE 기본은 경기·로봇 효과 시계를 멈추고 레이저를 즉시 끈다. 재개 시 발사 자동 재개는 없고, 기존 cooldown/lock 잔여 시간은 이어 간다. reporting에는 pause를 받지 않는다. 실제 대회 pause의 시계 정책은 확인되지 않았으므로 rules profile에 이 가정을 기록한다.

realtime 모드는 wall clock 기준 1배속이고 실제 HTTP를 사용한다. 과부하 시 timestep을 키우거나 시간을 건너뛰지 않고 real_time_factor가 낮아진다. 참가팀 호출량이 달라도 엔진 tick은 단일 순서로 처리한다.

accelerated 모드는 in-process fake transport와 deterministic scheduled actions만 사용한다. 실시간 120초 HTTP long-poll을 가상 120초로 줄여서 공식 API처럼 주장하면 안 된다. 물리·규칙 시간을 검사하는 빠른 테스트는 fake transport에서 wall wait 없이 scheduled completion을 사용한다.

## 5 같은 시각의 처리 순서

엔진은 tick boundary t에서 다음 순서를 유지한다. 모든 접수 요청은 processed_tick과 ingress_seq가 붙는다. HTTP 도착 시각은 로그용이고 phase 판정의 권위는 단일 writer가 접수한 tick이다.

1. t에 예약된 supervisor 이벤트를 적용: reset/start_failure/stop/pause/resume. reset은 이전 세션 queue를 폐기하고 모든 pending request를 세션 종료로 완료한다.
2. t에서 만료한 단계 시계를 먼저 처리. 240초면 M5 게시, 300초면 reporting, reporting 30초면 finished. 마감과 같은 시각의 보고는 늦은 보고이다.
3. HTTP queue를 ingress_seq 순서로 처리. 인증·스키마 검증 후 현재 phase 확인, 보고 저장. 마지막 필수 M6는 저장과 성공 응답 결과를 먼저 확정하고 all-submitted 종료를 적용한다.
4. robot action queue를 ingress_seq 순서로 처리. 같은 로봇의 마지막 유효 cmd_vel이 유지된다. 각 fire 요청은 별도 동작이며 자동 합치기·자동 재시도 금지.
5. [t,t+dt] 운동·연속 광선 점유·센서 교차 후보를 계산한다. 파생 이벤트는 endpoint 또는 substep crossing의 정수 tick으로 올림한다.
6. t+dt의 단계 deadline을 먼저 적용한 뒤 아직 허용되는 geometric 이벤트를 적용한다. 따라서 240초 교차는 게시 후 인정하고 300초 교차·피격은 진행 종료 후라 인정하지 않는다. M5 성공이면 즉시 reporting으로 전환한다.
7. 해당 boundary의 최종 상태로 sensor snapshot을 만들고 구독자/렌더러에 보낸다. private event journal을 flush한다.

동일 boundary를 단계2와6에서 보더라도 게시·phase 전이는 one-shot/idempotent이다. published flag와 transition generation으로 중복 명령·중복 점수를 막는다.

이는 SIM-TICK-ORDER이며 실제 서버·장치의 모든 동시성 판정을 재현한 것은 아니다. 같은 endpoint에서 여러 거점 이벤트가 발생하면 event tick, 그다음 stable base_id 정렬 순서로 최초 이벤트를 고른다. 변경 가능한 정책으로 분리한다.

laser 만료와 hit가 같은 시각이면 만료가 우선한다. 단, uninterrupted 2초가 t=2.00에 충족되고 그때 레이저가 켜져 있으면 hit는 성립한다. M6 이후 정정된 scoring 정답을 참가팀에게 역공개하지 않는다.

## 6 상태기계

HTTP phase는 idle/waiting/ready/running/reporting/finished만 사용한다. paused는 running의 내부 substate이며 공식 HTTP phase에 paused를 추가하지 않는다.

| 동작 | 사전 조건 | 결과 |
| --- | --- | --- |
| configure | idle 또는 finished | 새 match_id, waiting, 세션·점수·관측 초기화 |
| enter_ready | waiting | ROS standby, team launcher 실행, ready 수신 가능 |
| start | ready | ready accepted 팀 admitted. 기본은 즉시 started, ROS start, order 게시 |
| pause | running && !paused | cmd_vel zero, laser off, gimbal stop, ROS pause |
| resume | running && paused | ROS resume, 최신 제어명령 새로 필요 |
| M5 성공 또는 300초 | running | M1/M3 정답·최종 보고·HP·탄약 동결, ROS report |
| 30초 또는 전원 M6 | reporting | M6 채점·연합 점수 산정, ROS stop, finished |

미준비 팀 제외, 미출발 판정, 예외적인 편성 인원은 01의 SIM 기본값을 따른다. start failure는 로봇 제어와 보고 적격성을 제거하지만 경기 전체를 종료하지 않는다. HP0은 started/admitted를 취소하지 않는다.

## 7 내부 자료형

Python frozen dataclass 또는 immutable Pydantic 모델을 사용한다. 아래 필드는 개념 설명이 아니라 구현 계약이다. 저장 wire schema는 contracts/*.schema.json을 따른다.

| 자료형 | 필수 필드 |
| --- | --- |
| Pose2 | x_m:float, y_m:float, yaw_rad:float |
| SessionIdentity | match_id:str, episode_index:int, slot:Slot, camp:Camp |
| TimedEnvelope | sequence:int, captured_tick:int, received_tick:int, source_id:str |
| WorldState private | robots, boxes, faces, facilities, bases, active_lasers, sensor_dwell, current_match |
| RobotTruth private | slot, pose, hp, ammo, lock_deadlines, active_command, last_velocity_received_tick, gimbal_pose, odom_model |
| ObservationStore participant | self_state, match_status, own_odom, own_imu, scan, rgb, detections, drone; each stamped/optional |
| MissionInterpretation | target:FacilityCode or None, search_sectors:tuple[Sector] or None, base:BaseCode or None |
| SectorInventory | map[Sector,map[ObjectClass,int]], observed_coverage, evidence_revision; latter two never report JSON |
| PublishedObjective | objective:BaseCode, objective_label:str, issued_at:str |
| ThreatEstimate participant | slot, hp_distribution, ammo_distribution, m3_distribution, evidence_tick, confidence |
| ReportSnapshot | kind:m1/m3/m6, revision:int, payload, created_tick, session_id |
| SubmittedReport private | same canonical payload, processed_tick, ingress_seq; latest one per mission/team |

Stable entity IDs exist only in private scenario/evaluator: box_id, face_id, facility_id, base_id. Participant tracking IDs are generated by the participant and cannot be copied from these IDs.

## 8 공개 관측 계약

OwnState는 hp int0..4, hp_max=4, battery_pct float0..100, stamp를 가진다. ammo는 기본 공개하지 않는다. 자기 발사 성공 이력으로 추정할 수 있다. 실제 state 메시지는 최종 SDK로 교체한다.

OwnMatch는 mode practice/mission, cmd idle/standby/start/pause/resume/report/stop, stamp를 가진다. Simulator SessionIdentity는 별도 handshake로 전달하고 공식 /me에 match_id를 추가하지 않는다.

Odometry는 local_pose=inv(initial_world_pose)*current_world_pose + configured drift, linear_x_mps, angular_z_rps, stamp를 가진다. 시작점의 실제 world 좌표를 노출하지 않는다. 경기 reset 때 로컬 원점을 초기화한다.

CameraFrame은 sequence,captured_tick,received_tick,camera_id,width_px,height_px,encoding=bgr8,data를 가진다. In-process data는 uint8 H×W×3, HTTP는 JPEG를 decode하고 BGR로 변환한다. JPEG와 원본 배열에 동일 byte hash를 요구하지 않는다.

DetectionFrame은 SIM 전용이다.

~~~json
{
  "sequence": 1, "captured_tick": 10, "received_tick": 12,
  "camera_id": "B-1/front", "width_px": 640, "height_px": 480,
  "detections": [
    {
      "kind": "object", "bbox_xyxy_px": [100.0,80.0,160.0,150.0],
      "class_probs": {"military_truck":0.0,"mortar":0.0,"tank":0.9,"missile":0.0,"ammo_box":0.1,"drum":0.0},
      "confidence": 0.9
    }
  ]
}
~~~

kind=facility이면 class_probs keys는 COMMS/OUTPOST/RADAR, kind=ugv이면 UGV이다. 표식이 실제 시야에 있는 경우만 marker_readout={camp,band_count,confidence}를 추가한다. 얼굴ID·정답sector·world좌표·상대HP/탄약/M3는 금지한다. bbox는 영상 좌표, 상좌 포함·하우 미포함, 영상 경계에 clip, 면적은 양수. class_probs 합은 1±1e-6이다. confidence는 검출 신뢰도로 클래스 확률과 별개다.

2D는 front RGB capability=false, semantic=true. 3D 평가 기본값은 RGB=true, semantic=false. 3D에서 같은 semantic oracle을 쓰는 것은 명시적인 parity 시험에서만 허용하며 영상 인식 성능 증거로 쓰지 않는다. LiDAR/IMU 합성 규격과 Depth 실험 채널은 04를 따른다.

## 9 포트 인터페이스

~~~python
class ParticipantPort(Protocol):
    async def get_me(self) -> MeResponse: ...
    async def ready(self) -> Accepted: ...
    async def await_order(self, wait_s: int = 120) -> OrderResponse: ...
    async def await_target(self, wait_s: int = 120) -> TargetResponse: ...
    async def submit_m1(self, value: MissionInterpretation) -> ReceivedM1: ...
    async def submit_m3(self, value: SectorInventory) -> ReceivedM3: ...
    async def submit_m6(self, ranking: tuple[str, ...]) -> ReceivedM6: ...
    async def latest_observations(self) -> ObservationStore: ...
    async def command_velocity(self, linear_x_mps: float, angular_z_rps: float) -> None: ...
    async def command_gimbal(self, pan_units: float, tilt_units: float,
                             speed_deg_s: float, acc_units: float) -> GimbalResponse: ...
    async def fire(self) -> FireResponse: ...

class SceneBackend(Protocol):  # privileged internal interface
    def sync_scene(self, snapshot: RenderSnapshot) -> None: ...
    def capture_rgb(self, camera_id: str, tick: int) -> CameraFrame: ...
    def raycast_batch(self, rays: Sequence[Ray]) -> Sequence[PrivateRayHit]: ...
    def close(self) -> None: ...
~~~

SceneBackend는 점수나 위치를 변경하지 않는다. laser 판정은 core/geometry3d.py로 수행하여 Bullet 영상이나 GPU에 따라 바뀌지 않는다. 공개 DTO 변환은 SensorGateway 한 곳에서 처리한다.

## 10 난수와 결정성

scenario에 seed가 필수다. 난수 stream은 (world_generation,slot,sensor_kind,noise_kind)를 stable SHA256으로 파생한다. Python hash()나 모든 센서가 공유하는 난수생성기 하나를 쓰지 않는다. 센서 하나를 꺼도 다른 센서의 난수열이 바뀌지 않아야 한다.

offline의 동일 seed+config+scheduled actions+software lock은 canonical event journal과 점수가 동일해야 한다. JSON은 keysort, 비유한 float 금지. realtime OS 스케줄링/HTTP 도착/렌더 drop은 seed만으로 결정되지 않으므로 실제 ingress와 frame delivery를 기록하고 재생하여 재현한다.

RUN_ROOT는 --out으로 지정한 정확한 디렉터리다. 생략하면 artifacts/runs/run_id를 사용한다. 그 아래 파일 경계:
- RUN_ROOT/public/slot/: 자기 관측과 전송 로그만 저장.
- RUN_ROOT/private/: truth, 전체 이벤트, 영상 annotation, 정답·점수. participant launcher에 경로를 주지 않는다.
- RUN_ROOT/summary/: 경기 종료 후 평가자 보고서. 경기 중 참가팀 입력으로 역유입하지 않는다.

replay에는 schema_version,source_commit,rule_profile_hash,arena_hash,asset_manifest_hash,seed,dependency_lock_hash,backend_mode,clock_mode를 포함한다. 다른 profile을 같은 조건의 run처럼 비교하지 않는다.

## 11 자원과 종료 처리

종료 순서는 engine→workers→HTTP long-poll→children→backend이다. 중간 예외에도 속도0 처리를 적용하고 로그를 flush한다. thread/process는 context manager 또는 명시 close를 가진다.

render worker가 Bullet connection을 단독 소유한다. realtime에서는 camera별 pending latest-only queue 1개를 두고 오래된 미처리 frame은 버린 뒤 drop event를 기록한다. snapshot은 immutable이며 captured_tick을 작업 완료 시각으로 바꾸지 않는다. offline은 필요한 frame을 동기 생성해 순서를 고정한다.

cmd_vel watchdog은 sim_tick-last_velocity_received_tick >= 50일 때 속도0이다. 잠금 중 수신한 명령은 active_command와 watchdog 시각을 갱신하지 않는다. pause는 기존 명령을 폐기한다.

참가팀 report worker는 M1/M3 각각 inflight 1개다. 새 revision이 생기면 pending을 교체하고 timeout 후에는 최신 snapshot으로 재시도한다. phase가 바뀌면 해당 mission 전송을 중단한다. fire는 비멱등 동작이므로 응답 불명 시 맹목 재시도하지 않는다. M6 첫 보고는 현재 최선인 상대 3개 slot 전체 순위다.

## 12 구현 완료 조건

두 backend는 같은 rules.py와 scoring.py를 사용한다. 동일 action trace에 대한 score·phase·hit 시각이 같아야 한다. 영상 인식 결과까지 같을 필요는 없다. 공개 observations에 truth 필드가 없는지 구조와 runtime에서 모두 검사한다. 실제 장치 미접속 상태에서는 adapter contract validated와 hardware validated를 별개로 기록한다.



## 13 보고 timeout의 불확실성

inflight 직렬화는 정상 응답 경로의 역전을 막지만, timeout된 오래된 POST가 실제 서버에서 나중에 저장되는 경우까지 완전히 막지는 못한다. 공식 API에는 revision/CAS 계약이 없다. SDK는 최신 전체 snapshot을 다시 보내고 received를 확인하며 진행 중 같은 최신 snapshot을 주기적으로 재전송하는 best-effort 복구를 수행한다. 그 복구가 완료되기 전에 마감되면 최신 보고 보장을 할 수 없다. 시뮬레이터 fault test는 A 저장 지연→클라이언트 timeout→B 저장→A 늦은 저장→B 재전송 순서를 재현해야 한다. 시뮬레이터 전용 header나 내부 revision을 실제 서버의 보장인 것처럼 사용하지 않는다.

## 14 이벤트 로그와 재생 계약

RUN_ROOT/private/events.jsonl의 각 줄은 schema_version,run_id,match_id,event_seq,sim_tick,match_elapsed_ticks,reporting_elapsed_ticks,category,kind,actor,payload를 가진다. category는 input/derived/measurement이며 actor는 slot 또는 supervisor/engine/sensor이다. event_seq는 세션 전체에서 단조 증가한다. mission_code 대신 slot을 남긴다.

input kind는 supervisor_command,robot_command,http_request_ingress,transport_fault,process_lifecycle이다. derived kind는 phase_changed,order_published,target_published,report_committed,laser_fired,hit_applied,facility_destroyed,base_captured,score_frozen,match_finished이다. measurement kind는 sensor_captured,sensor_delivered,sensor_dropped,render_overload이다. kind별 payload는 원래의 검증된 command/DTO, 원인 event_seq와 결과를 포함한다. 모든 좌표·시간의 단위는 기존 계약을 그대로 사용한다.

replay --verify의 기본 mode=core는 기록된 input만 같은 processed_tick/ingress_seq로 다시 주입하고 derived journal과 최종 score를 대조한다. derived를 다시 input으로 주입하여 피격·점령이 두 번 발생하게 만들지 않는다. 기록된 participant commands를 재생하므로 LLM·정책·영상 모델을 다시 실행할 필요가 없다. wall timestamp·관측된 처리 시간은 core hash 비교에서 제외한다.

mode=observations는 실제 participant에 기록 관측을 재전달하여 알고리즘을 비교한다. RGB가 필요하면 record_frames=true로 저장한 frame bytes와 SHA256이 있어야 한다. 파일이 없으면 명시적으로 실패하고 임의의 새 합성 영상으로 대체하지 않는다. 새 정책의 행동은 기존 세계 상태를 바꾸지 않는 open-loop 관측 재생 평가로 표시한다. 새 정책의 closed-loop 평가는 별도 fresh run이다.

run_manifest.json에는 프로필/시나리오/자산/lock hash,seed,backend,clock_mode,sensor_mode,oracle,capabilities,software_version,source_commit,실행환경,명령행,각 파일의 상대경로를 필수 기록한다. result.json은 contracts/run_result.schema.json에 맞는 종료 점수·핵심 지표이며 상세 지표는 summary/metrics.json에 저장한다. 잘못된 replay는 최초로 달라진 event_seq와 기대/실제값을 보고한다.
