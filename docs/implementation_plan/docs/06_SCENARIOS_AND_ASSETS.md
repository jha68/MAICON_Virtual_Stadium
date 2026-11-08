# 시나리오와 자산 데이터 명세

이 문서와 contracts/의 JSON Schema, examples/의 YAML·JSON은 구현 입력 계약이다. 예시는 실행 가능한 시뮬레이터 구현이 아니라 그 구현이 읽어야 하는 데이터다. 모든 경로는 해당 YAML 파일의 부모 디렉터리를 기준으로 해석한다. 절대 경로나 과거 /workspace 경로를 저장하지 않는다.

## 1 파일과 검증 순서

| 스키마 | 제공 예시 | 역할 |
| --- | --- | --- |
| rules.schema.json | rules_prestudy.yaml | 경기 시간·장치 수치·선택한 잠정 규칙 |
| arena.schema.json | arena_reference.yaml | 경계·구역·거점 센서·명목 출발점 |
| assets.schema.json | assets_synthetic.yaml | 면 이미지와 출처·분할·생성 방식 |
| sensor_profile.schema.json | sensor_profile_reference.yaml | 센서 기하·내부 파라미터·노이즈 프로필 |
| scenario.schema.json | scenario_smoke_six.yaml | 6개 로봇·상자·명령·정답·fault |
| scenario.schema.json | scenario_perception_gallery.yaml | 3D 카메라·박스 면 렌더링 fixture |
| scenario.schema.json | scenario_pause_and_drone_faults.yaml | 일시정지·드론 저하 관리자 시험 |
| m1.normalized.schema.json | m1_request.json | 입력을 정규화한 뒤의 M1 wire 형식 |
| m3.normalized.schema.json | m3_request.json | 입력을 정규화한 뒤의 M3 wire 형식 |
| m6.normalized.schema.json | m6_request.json | 입력을 정규화한 뒤의 M6 wire 형식 |
| run_result.schema.json | 미래 구현에서 생성 | 평가자 결과 저장 계약 |

원본 계획 묶음에는 9개 스키마와 11개 예시가 있다. 구현 정정 D005에서 `admin_configure.schema.json`을 추가하여 현재는 10개 스키마다. scenario는 sensor_profile_file을 필수로 지정하여 별도의 기하·내부 파라미터·노이즈 프로필을 참조한다.

스키마의 .invalid URI는 이름 식별용이며 네트워크에서 다운로드하지 않는다. JSON Schema 2020-12 로컬 validator로 검사한다. YAML safe_load 후 schema validation, 그다음 semantic validation, 참조·기하 validation, asset resolution 순서다. 추가 필드는 기본 거절한다.

normalized schema는 raw lowercase 입력을 그대로 거절하라는 의미가 아니다. handler가 타입을 엄격하게 확인한 뒤 허용 문자열에만 대소문자 정규화를 적용하고 검증한다. M3의 raw type=tank는 canonical TANK로 바뀐다. bool을 int로 취급하거나 "2"를 2로 변환하지 않는다.

## 2 반드시 추가할 의미 검증

JSON Schema만으로 끝내지 않는다. 다음은 loader의 필수 검증이다.

1. 슬롯 B-1..B-3,R-1..R-3가 정확히 한 번씩 있고 mission_code가 대소문자 무관 유일하다.
2. 7개 sector와 6개 base code가 빠짐없이 한 번씩 있다. polygon은 단순하고 양의 면적을 가지며, 꼭짓점 순서는 반시계 방향이다.
3. sector 내부가 중첩하지 않고 경기장 안에 있다. 공유 경계는 허용한다. base strip은 채점 sector 밖이다.
4. nominal start와 실제 start footprint가 경기장·박스·다른 로봇과 충돌하지 않는다. 무작위 jitter 적용 뒤에도 검사하며, 실패 시 최대 100회 재샘플링한 후 명시적으로 실패 처리한다.
5. box_id와 face side는 각각 유일하다. 같은 box의 동일 면에 객체와 시설을 겹치지 않는다. size는 m 단위이고 fixture 기본값은 0.4m이다.
6. 일반 배치의 박스 footprint 전체가 선언한 sector_id 내부에 있어야 한다. 중심 또는 footprint가 경계에 걸친 배치는 거절한다. 경계 판정 시험은 evaluator 전용 boundary_test가 객체를 직접 구성하여 명시적 귀속을 적용하며 일반 scenario loader의 허용 조건을 바꾸지 않는다.
7. 각 진영의 시설 COMMS/OUTPOST/RADAR가 정확히 1개씩 있고, facility_code의 camp와 박스 sector의 진영이 같다.
8. 모든 face의 asset_id가 존재하고 asset kind/label이 face class/facility suffix와 일치한다. Decoy는 채점하지 않는다.
9. orders는 각 slot당 1개이다. expected_m1의 target은 상대 시설이며 같은 진영 3팀의 target은 서로 다르다. M1 search_sectors/base는 M3/M5와 일치할 필요가 없다.
10. objectives_by_camp는 상대 진영의 base이며 실제로 존재해야 한다. expected_m1은 비공개이고 tactical_command만 공개한다.
11. tick_ms=10, 모든 duration/at_ms는 10의 배수, objective_publish_ms<match_ms, report_ms>0이다. 센서 Hz는 100을 정수로 나누어 tick schedule을 만들 수 있어야 한다.
12. 모든 event_id는 유일하며 kind에 맞는 parameters를 가진다. reporting-clock 이벤트는 reporting 진입 전에 실행하지 않는다. pause 후 resume를 match-clock의 미래에만 예약하면 영원히 실행되지 않을 수 있으므로 validator 경고와 max_sim_ms 보호가 필수다.
13. requires와 backend capabilities가 맞지 않으면 실행 전에 실패 처리한다. 2D에 rgb를 요구해 놓고 oracle로 몰래 대체하지 않는다.
14. 수치에 NaN/Infinity는 허용하지 않는다. count 중복·섹터 중복·확률 합·상대 slot 검증은 서버/센서 DTO에도 적용한다.
15. rules.sensors와 sensor_profile에 중복 지정된 front width/height/FOV와 LiDAR ray 수·range는 일치해야 한다. 불일치하면 한쪽 값을 임의로 선택하지 않고 검증에 실패한다.

잘못된 설정은 파일명·JSON path·원인·수정 예시를 포함해 exit 2로 종료한다. 일부 설정을 무시하고 임의의 경기장을 만들지 않는다.

## 3 참고 경기장

SIM-ARENA의 구체값은 examples/arena_reference.yaml에 있다. world [0,6.12]×[0,5.0], 벽 높이 .4m, BLUE 서쪽, RED 동쪽이다.

| 영역 | x 범위 | y 범위 |
| --- | --- | --- |
| BLUE 거점띠 | 0..0.6 | 0..5 |
| BLUE 탐색구역 | 0.6..2.76 | S1=10/3..5, S2=5/3..10/3, S3=0..5/3 |
| CM | 2.76..3.36 | 0..5 전체 |
| RED 탐색구역 | 3.36..5.52 | BLUE와 같은 행 번호 |
| RED 거점띠 | 5.52..6.12 | 0..5 |

박스 중심은 BLUE x1.7, RED x4.4의 y4.2/2.5/.8, CM(3.06,2.5)이다. 박스들은 고정되어 있으며 충돌로 밀리지 않는다. 이는 기본 fixture일 뿐이며 랜덤 시나리오에서 변경한다.

face.side의 east/west/north/south는 각각 박스 로컬 +x/-x/+y/-y 면이다. world 방향은 박스 pose의 yaw를 적용하여 계산한다. cardinal 이름을 world 고정 방향으로 다시 해석하지 않는다.

각 진영의 북쪽/중앙/남쪽 거점은 COMMAND_POST/MAINTENANCE/SUPPLY_DEPOT이다. 각 거점 센서는 입구의 길이 .4m 선분이다. blocked는 어느 로봇의 평면 footprint와 선분이 교차하면 true이다. 게시 후 false→true edge로 점령을 판정하고, 게시 전에 막고 있으면 새 edge가 필요하다. 실제 광전센서 설치 위치·체류 규칙을 확정한 모델은 아니다.

PublicMapPrior에는 bounds, sector polygons, base labels/geometry, nominal_start_pose만 포함한다. 실제 start jitter, 실제 박스 좌표, face 목록, 정답 수량은 포함하지 않는다. baseline은 명목 시작 자세와 자기 odom으로 world 위치를 추정하며 그 오차를 평가한다.

## 4 시나리오 상태와 정책

scenario는 평가자 입력이다. participant에게 scenario 전체를 넘기지 않는다. engine loader는 PublicMapPrior와 해당 slot의 order text만 별도로 projection한다.

agents.policy:

- idle: ready만 제출하고 속도 0을 유지하며, M1/M3/M6를 제출하지 않는다. smoke 기대 점수가 각 20인 전제다.
- baseline: M1 mock/LLM, 기본 탐색·관측 집계·전체 보고·M5 이동·M6 추정 흐름이다. 고득점을 보장하지 않는다.
- patrol: 공개된 명목 waypoint를 따라 반복 이동한다. 정답 박스 좌표 사용은 금지한다.
- blocker: 지정된 공개 통로 waypoint에서 이동/정지를 반복한다. 다른 로봇과의 collision 시험용이다.
- capture_runner: 상대 거점 공개 후 공개 prior의 거점으로 이동한다. pose 직접 변경은 금지한다.

각 정책은 ParticipantPort를 사용한다. scripted fixture용 oracle 행동계획은 evaluator 도구로 분리하고 run에 oracle=true를 기록한다. oracle 값으로 baseline score를 높이지 않는다.

scenario_smoke_six는 모두 idle이며 shoot/report가 없다. 끝까지 300초+30초이므로 각 M4=15와 동점 연합 점수 5로 각 20점이다. smoke_six_expected.json은 수기 정답이다.

scenario_perception_gallery는 B-1만 박스 면 촬영 위치로 옮긴 정적 카메라 fixture다. 공개 prior의 명목 출발점과 실제 위치가 다를 수 있으므로 이 run을 자율 위치추정 성공으로 해석하지 않는다. baseline 대신 idle을 사용한다.

scenario_pause_and_drone_faults의 resume는 sim-clock에 예약한다. match-clock pause 이후 미래 match 시각에만 resume를 예약하는 오류를 피한다. sim 기준 110초가 항상 정확히 10초의 pause를 뜻하지는 않으며 start 준비 시간이 별도로 포함된다. 정확한 10초 pause unit test는 02의 fake clock으로 예약한다.

## 5 자산 생성과 반입

기본 배포에는 직접 생성한 synthetic fixture만 포함한다. 대회 PDF 사진·공식 이미지·상업 모델·인터넷 이미지를 자동 다운로드하여 배포하지 않는다. 실제 공식 이미지는 사용자가 사용 권한이 있는 파일을 manifest에 등록해 import한다.

procedural_v1은 512×512 RGBA, 밝은 균일 배경, 검은 외곽선·label별 다른 기하도형으로 생성한다. 정답 문자나 class ID를 텍스처에 렌더링하지 않는다. 재현 가능한 벡터 좌표 목록을 asset_builder.py에 고정하고 manifest에 생성기 version을 남긴다. 색상만으로 class를 구분하지 말고 흑백에서도 서로 다른 shape를 만든다.

RGB baseline용 필수 설정: 텍스처 바깥에는 모든 class에 공통인 검은 사각 테두리를 넣는다. 내부 이미지 영역은 32..480px이다. 이는 종류별 외곽 ID를 심는 방식이 아니며 synthetic 판 검출을 안정화하는 fixture 가정이다. 실제 대회 인쇄물에 같은 테두리가 있다는 보장은 없다.

generator=procedural_v1인 초기 manifest의 path/sha256=null은 생성 전 상태이다. maicon-sim assets build가 PNG를 만들고 resolved manifest에 상대 path와 실제 SHA256을 채워 넣는다. 실제 run은 resolved manifest hash와 PNG hash를 기록한다. generator=import는 path와 64자리 sha256이 필수이며 hash가 불일치하면 실패한다.

metadata는 source, license, split_group, split을 반드시 유지한다. 같은 원본 이미지의 crop/색 변형/원근 변형은 동일 split_group이며 train/validation/test에 걸쳐 누출시키지 않는다. fixture split은 일반화 성능 주장에서 제외한다.

## 6 최소 3D RGB 인식 예제

다른 에이전트가 임의의 외부 모델 선택으로 막히지 않도록 필수 reference detector는 OpenCV template 기반으로 고정한다. 이는 synthetic gallery의 파이프라인 시험용이며 실제 M3용 최종 모델이 아니다.

1. BGR 입력을 grayscale로 변환한다.
2. 검은 테두리 후보의 contour를 추출하고 convex quadrilateral, 면적 256px 이상, 내부각 허용 범위로 filter한다.
3. corner 순서를 TL, TR, BR, BL로 정하고 128×128 canonical crop으로 perspective warp한다.
4. fixture의 내부 template와 정규화 상관도를 계산하고 class 최대값을 선택한다. 4개 회전 방향도 비교한다.
5. score<0.75는 unknown으로 버리고 IoU 0.5 NMS로 중복 후보를 정리한다. 이 임계값은 SIM-TEMPLATE 기본값이다.
6. 결과는 02의 DetectionFrame과 같은 bbox/class_probs/confidence를 반환한다. class_probs는 softmax(score/0.1)로 정규화한다.
7. 영상만 받는 callback을 사용하며 face ID, texture filename, segmentation, groundtruth rectangle을 참조하지 않는다.

필수 합격 범위는 무잡음 정면 합성 gallery의 6종 각 1개 영상에서 정답 class가 각 1개 검출되는 것이다. 임의 사선·가림·새 이미지 일반화는 측정 결과만 보고하고 필수 100%로 강제하지 않는다. 다른 모델은 같은 callback을 구현하고 run metadata에 이름·hash·입력·confidence를 기록하여 교체한다.

baseline은 현재 gimbal 위치의 정답을 센서에서 받지 않는다. accepted gimbal command와 rate model로 자세를 추정하며, 명령 후 예상 이동 시간+100ms 동안 관측을 보류한다. settled 상태의 추정 pan과 odom으로 bearing을 world 방향으로 변환한다. 실제 장치 연결 후에는 공식 feedback 유무에 맞춰 이 정책을 보정한다.

## 7 공통 기하 수치

04의 기하를 직렬화할 때 다음 SIM-GEOMETRY 수치를 사용한다. 실물 치수는 아니다.

| 항목 | 기본값 |
| --- | --- |
| planar footprint | body x 길이 .23, y 폭 .25m |
| chassis solid | 중심 (0,0,.10), half extent (.115,.09,.03) |
| upper body mast solid | 중심 (-.04,0,.19), half extent (.025,.025,.06), 즉 z .13..25 |
| gimbal pivot | body(.02,0,.23) |
| camera optical origin | gimbal(.025,0,0) |
| laser origin | gimbal(.025,0,.02),방향 gimbal+x |
| UGV receivers | body(0,±.110,.160),sphere radius .015 |
| facility receiver | 해당 box 면 중앙의 바깥쪽 .021m, z .35, radius .020 |
| marker pole | body(-.08,0), z .13..32, radius .005; visual 기본, canonical ray blocker는 mast만 |
| marker board | 중심 (-.08,.018,.27), 법선 ±body x인 양면, 폭 .06m는 body y 방향, 높이 .08m는 z 방향. 띠 높이 .004m; 1띠 z=.27, 2띠 z=.26/.28, 3띠 z=.25/.27/.29. camp 색상과 띠 수를 표시 |
| ray intersection epsilon | 1e-9m |
| endpoint/self-surface exclusion | 1e-6m |
| ray same-distance tie | 거리 차≤1e-9이면 occluder 우선, 그다음 stable private geometry_id |

전체 planar footprint는 충돌용이고 상부 mast/chassis/box/wall은 3D 광선용이다. decorative wheel/marker는 별도 설정이 없으면 laser 판정에 영향을 주지 않는다. 3D 렌더에는 보이지만 판정 proxy와 다를 수 있으므로 observer에 proxy overlay를 제공한다.

LiDAR z .145m는 chassis 상면 .13m보다 높지만 mast와 충돌한다. 다른 로봇이 항상 폭 .25m짜리 장애물로 스캔된다고 가정하지 않는다. 이를 통해 낮은 물체/센서 높이의 한계를 드러낸다. 자체 robot body는 LiDAR에서 제외하되 RGB에서는 실제 자기 차체가 가릴 수 있다.

## 8 오류 주입 프로필

ideal은 모든 확률 오류 0, 지연 0이며 기하적 가림만 적용한다. stress_v1의 기본 합성값은 다음과 같고 실측치는 아니다.

| 항목 | stress_v1 |
| --- | --- |
| semantic detection miss | 독립 0.10 |
| wrong object class | 검출 성공 중 0.05, 다른 5종 균일 |
| false positive | frame당 Poisson 평균 0.05, 영상 내 bbox |
| bbox noise | 각 좌표 Gaussian sigma 2px, 이후 clip |
| camera delay/drop | 100ms 고정 지연, frame 독립 drop 0.05 |
| odometry scale/yaw | 이동 scale 1.02, yaw rate bias 0.005rad/s, position increment noise sigma .001m |
| LiDAR | Gaussian sigma .01m, no-return 0.02, 범위 clip |
| IMU | yaw rate bias .005rad/s+noise sigma .002rad/s, 가속도 sigma .02m/s² |
| drone | 기본 100ms 전달 지연; 별도 fault가 frame 유실/시설 저하를 주입 |

fog는 3D depth 기반 저대비·밝기 합성 후처리로 구현한다. volumetric scattering이나 LiDAR의 실제 연기 반응을 검증한 것으로 표현하지 않는다. 옵션값은 run manifest에 모두 남긴다.

## 9 랜덤 시나리오 생성

generate 명령은 seed별 박스 위치·물체 class/면·start jitter를 생성하고 정확한 실현값을 scenario YAML로 저장한다. seed만 남기고 재생 시 다시 생성하지 않는다. 생성 후 위 검증과 A* 공간 연결성을 검사한다.

필수 제약: 박스 간 또는 박스와 벽 사이의 통과 폭이 최소 .4m인 경로가 각 nominal start에서 CM과 3개 상대 거점까지 존재해야 한다. 모든 쌍의 유클리드 간격이 무조건 .4m 이상이라는 규칙으로 과도하게 해석하지 않는다. 최대 1000개 후보까지 배치에 실패하면 실패를 보고하며 무한 loop는 금지한다.

클래스 개수 상한 99, 시설 각 1개, 실제 face 정답의 고유성, 자산 분할은 유지한다. 모든 면이 관측 가능한 시나리오와 일부 불가한 시나리오를 분리 표시하고, 불가 시나리오에서 M3 만점 실패를 모델 오류로 단정하지 않는다.

## 10 추가로 구현할 회귀 시나리오

제공된 3개 예시 외에 구현자는 tests/fixtures에 다음을 만든다. 07의 기대값을 사용한다.

early_capture: 240초 이후 제어 입력으로 실제 센서 교차. deadline_race: 299990/300000ms 제출. duplicate_faces: 동일 사진의 다른 면과 같은 면 재관측. occluded_faces: 박스가 면을 가림. drone_degrade: 1/2/5초+403. restart_same_match와 next_match_reset. laser_dwell_gap: 1.99초 후 끊김. simultaneous_capture: 동일 endpoint 두 거점. six_process_realtime: 실제 HTTP 6프로세스. report_all_early: 마지막 M6 즉시 종료.

관리자 이벤트로 점령/파괴를 주입한 시험과 물리 움직임·광선으로 달성한 시험을 결과에서 분리한다. 테스트 정답을 맞추기 위해 모사 서버가 참가팀의 오류 보고를 자동 보정하지 않는다.

## 11 예약 이벤트의 정확한 실행 의미

시나리오 event는 event_id로 한 번만 실행한다. clock은 sim/match/reporting 중 하나이며 at_ms가 해당 누적 시각에 도달한 첫 boundary에서 활성화한다. 같은 boundary에서는 시나리오 배열 순서로 처리하되 02의 phase deadline 우선순위를 유지한다. reporting 시계가 시작되기 전에는 reporting event가 활성화되지 않는다.

| kind | parameters와 동작 |
| --- | --- |
| pause/resume | parameters={}. 현재 phase에 맞는 supervisor 전이. 부적절한 phase는 event_rejected 로그만 남김 |
| force_reporting | parameters={}. running에서 강제 reporting. 성능 성공 사례와 구분 |
| start_failure | slot. 해당 팀의 started를 false로 만들고 보고 적격성·조기종료 집합에서 제외 |
| sensor_dropout | slot,sensor,duration_ms. 활성화 sim_tick부터 지정 기간 새 측정 생성/전달 중단. 과거 관측을 새 timestamp로 갱신하지 않음 |
| drone_facility_destroyed | facility_code. 평가자 전용으로 최초 파괴 사건 주입. 자율 표적 타격 증거가 아님 |
| robot_command | slot,linear_x_mps,angular_z_rps,duration_ms. 시나리오 대본이100ms마다 새 명령을 제출하고 sim 기준 기간 종료 때 속도0을 한 번 보냄. 단발 명령을 강제로 유지하여 watchdog를 우회하지 않음 |
| http_delay | slot,path,duration_ms,stage,match_occurrence,drop_response_after_commit. 아래 규칙 적용 |
| robot_state_correction | slot 및 hp(엄격한 정수 0..4) 또는 ammo(엄격한 정수 0..8), 둘 다 가능. 평가자 전용 심판 정정 fixture. running이며 동결 전일 때만 반영하고 reporting 이후에는 거절한다. 참가팀 API가 아니며 자율주행·공격 성공의 증거로 사용하지 않는다. |

http_delay는 활성화 이후 같은 세션·slot·path에서 match_occurrence번째로 일치하는 요청 단 한 개를 대상으로 한다. 카운터는 성공 여부와 무관하게 인증된 요청의 도착마다 증가한다. stage=before_ingress는 엔진 접수 전에 지연하며, client가 timeout되어도 이미 받은 요청을 지연 후 접수할 수 있어 오래된 보고의 늦은 commit을 재현한다. stage=after_commit은 저장 후 응답만 지연한다. drop_response_after_commit=true는 after_commit에서만 허용하고 응답을 client에게 반환하지 않는 장애를 모사한다.

실제 HTTP의 duration_ms는 wall monotonic 기준이다. accelerated fake transport에서는 독립 virtual transport clock으로 같은 순서를 예약하고 실제 sleep을 하지 않는다. reset 때 미완료 fault와 counter를 폐기하고 session_ended를 기록한다. 무한대기·죽은 waiter를 방치하지 않는다.

watchdog·sensor_dropout·robot_command 지속기간은 sim clock이므로 pause 동안에도 만료할 수 있다. pause는 명령을 폐기하고, 이후 대본의 새 heartbeat가 도착하더라도 pause 상태에서는 적용되지 않는다. resume 후 도착한 새 heartbeat부터 제어 가능하다.


## 12 실행 시 자산 해석과 원본 보존

run은 원본 assets_file을 읽고 모든 procedural 자산을 RUN_ROOT/private/assets/에 생성하며 resolved_manifest.yaml에 실제 상대경로와 SHA256을 기록한다. 원본 examples YAML과 원본 manifest는 수정하지 않는다. assets build는 같은 resolver를 독립적으로 실행하는 명령이다. 이미 만든 산출물을 재사용할 때는 --resolved-assets 경로를 명시하고 manifest_id·생성기버전·원본manifesthash·PNGhash를 검증한다. 이 옵션이 없으면 run이 자동 생성하므로 제공 sample scenario만으로 실행할 수 있다. 공개 카메라는 이미지 픽셀만 전달하며 private 자산의 파일명·label·hash를 참가팀에게 보내지 않는다.
