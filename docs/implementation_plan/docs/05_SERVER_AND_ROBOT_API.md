# 경기 서버와 로봇 인터페이스 구현 계획

이 파일은 새 저장소에서 HTTP 모사 서버와 participant SDK를 구현하는 계약이다. 공식 형식은 main의 2026-11-04 API snapshot을 모사한다. /sim으로 시작하는 경로는 이 계획이 정의한 개발용 기능이며 실제 대회 API가 아니다. source facts는 01, 같은 시각의 처리 순서는 02를 따른다.

## 1 서버 구성과 인증

기본 public address는 http://127.0.0.1:8000, supervisor는 http://127.0.0.1:8001이다. supervisor는 loopback에만 bind하고 시작 시 생성한 admin token을 요구한다. public과 admin FastAPI app·router를 분리한다. 참가팀 process에는 자기 mission_code, public URL, 자기 output directory만 전달한다.

mission_code는 영문+숫자 8자리, 대소문자 무관. 샘플 SIMB0001~SIMB0003/SIMR0001~SIMR0003은 실제 인증정보가 아니다. GET query에 mission_code, POST JSON body에 mission_code를 포함한다. 공백은 허용하지 않는 simulator default를 택한다. 코드 자체를 요청 URL 로그·traceback·일반 event journal에 남기지 않고 slot 및 salted identifier로 치환한다. Public role이 다른 mission_code를 아는 경우 막을 수 있는 추가 인증을 공식 규약에 가정하지 않는다.

기본 엔진은 경기 세션 하나다. /api/report와 /api/rehearsal은 서로 독립 SessionRegistry entry이다. 동일한 simulator robot set을 동시에 두 세션에 배정하지 못하게 admin configure에서 409 처리한다. 두 경로의 handler/scoring 구현은 공유한다.

## 2 공식 모사 HTTP 경로

| Method 경로 | 입력 | 성공 결과 | 허용 시점 |
| --- | --- | --- | --- |
| GET /api/report/me | mission_code | slot,camp,phase,ready | 항상 |
| POST /api/report/ready | mission_code | accepted:true | ready이며 편성·설정 완료 |
| GET /api/report/order | mission_code,wait=0..120 | accepted,order 또는 reason | 게시 전 대기, 게시 뒤 같은 세션에서 조회 |
| GET /api/report/target | mission_code,wait=0..120 | accepted,order 또는 reason | M5 게시 전 대기, 게시 뒤 조회 |
| GET /api/report/drone | mission_code,camera? | JPEG + headers | running 편성팀 또는 test_mode |
| POST /api/report/interpretation | mission_code,target?,search_sectors?,base? | accepted,received | running이며 admitted/started |
| POST /api/report/detection | mission_code,sectors | accepted,received | running이며 admitted/started |
| POST /api/report/situation | mission_code,ranking | accepted,received | reporting이며 admitted/started |

/api/rehearsal에는 me,ready,order,target,interpretation,detection,situation만 같은 형식으로 제공한다. /api/rehearsal/drone은 404이다. 연습 카메라는 /api/report/drone?camera=test1 등을 이용한다.

GET /me 기본 예:

~~~json
{"slot":"B-1","camp":"BLUE","phase":"ready","ready":false}
~~~

편성 전에는 slot/camp=null. phase는 공식 6종만 반환한다. paused는 반환하지 않는다. ready는 이번 세션의 서버 수신 상태이며 모델 로딩 여부를 서버가 검증한 것이 아니다.

## 3 명령 게시와 long polling

POST ready의 body는 mission_code만 받는다. 200이면 accepted=true, 이미 ready=true인 같은 단계에서는 200 idempotent로 처리한다(SIM default). ready가 아닌 단계는 409. SDK는 모델·필수 센서 초기화 후 /me를 확인하고 실패 시 2초 뒤 상태부터 다시 확인한다.

GET /order accepted 응답:

~~~json
{"accepted":true,"order":{"tactical_command":"레이더시설을 타격하고 상대 첫째 탐색구역과 중앙을 정찰하며 군수보급소를 후속 거점으로 설정하라.","issued_at":"2026-11-18 13:00:00"}}
~~~

GET /target accepted 응답:

~~~json
{"accepted":true,"order":{"objective":"RED_MAINTENANCE","objective_label":"정비소","issued_at":"2026-11-18 13:04:00"}}
~~~

문장과 표시 시각은 예제 시나리오 값이다. M1 정답은 scenario의 per-slot expected_m1, 실제 M5는 objectives_by_camp를 사용한다. 두 거점이 다르게 설정된 fixture를 필수로 만든다.

아직 게시되지 않았으면 HTTP 200:

~~~json
{"accepted":false,"reason":"임무는 경기 진행이 시작되면 게시됩니다"}
~~~

target reason은 "M5 목표거점은 종료 60초 전에 게시됩니다", 편성 밖은 "이 경기에 편성되지 않은 팀입니다", 게시 시각 이후 누락된 운영 설정은 "게시된 임무가 없습니다"이다. 리허설이 없으면 "진행 중인 리허설이 없습니다".

wait 생략은 0이다. 정수 0..120만 허용하고 초과/음수/소수는 422로 처리한다. 게시되면 waiting 요청 모두 notify한다. 이미 게시된 내용은 running/reporting/finished 같은 세션에서 동일하게 조회 가능하다. 세션 reset 시 옛 waiter를 새 경기 명령으로 완료하지 않는다. simulator session ended reason으로 accepted=false를 완료하고 SDK가 handshake를 갱신한다.

구현은 session별 asyncio.Condition 또는 broadcast event+predicate loop다. 각 connection은 별도 deadline을 가진다. condition wake 뒤 session_id와 published 상태를 다시 검사한다. timeout이면 200 accepted=false, client disconnect면 waiter 해제. handler가 engine lock을 잡은 채 await하면 안 된다.

실제 HTTP timeout은 connect=3s, read=wait+10s 기본, cancellation 가능. 이는 SDK 기본값이지 대회 제한이 아니다. order/target wait task, 보고 task, robot control task는 독립적으로 실행한다.

## 4 M1 스키마와 정규화

~~~json
{
  "mission_code":"SIMB0001",
  "target":"RED_RADAR",
  "search_sectors":["R-S1","CM"],
  "base":"RED_SUPPLY_DEPOT"
}
~~~

target: BLUE_/RED_ + COMMS/OUTPOST/RADAR. base: BLUE_/RED_ + COMMAND_POST/MAINTENANCE/SUPPLY_DEPOT. search_sectors는 B-S1,B-S2,B-S3,CM,R-S1,R-S2,R-S3의 중복 없는 목록. 보고값은 대소문자 무관, canonical uppercase.

M1 세 field가 모두 누락이면 422이며, 일부만 있으면 수신하되 누락은 null로 덮어쓴다. 빈 search_sectors=[]는 유효하지만 정답 집합과 비교한다. 명시 null은 누락과 같게 처리하는 SIM normalization이다. 세 필드가 모두 누락 또는 null이면 422이며 빈 search_sectors=[]만 있는 것은 유효하다. unknown key는 422로 거절한다. 과거 sectors/goal_base/sector 키를 받아서 몰래 변환하지 않는다.

response:

~~~json
{"accepted":true,"received":{"target":"RED_RADAR","search_sectors":["CM","R-S1"],"base":"RED_SUPPLY_DEPOT"}}
~~~

search_sectors는 canonical 문자열 사전순으로 정렬. 표현 정규화는 정답의 진영·의미를 수정하지 않는다. BLUE 팀이 BLUE_RADAR를 보내도 enum 형식이 맞으면 저장하고 채점에서 틀리게 처리한다. 사용자에게 정답을 암시하는 검증을 하지 않는다.

## 5 M3 스키마와 정규화

~~~json
{
  "mission_code":"SIMB0001",
  "sectors":[
    {"sector":"R-S1","objects":[{"type":"tank","count":2},{"type":"drum","count":1}]},
    {"sector":"R-S2","objects":[{"type":"missile","count":1}]},
    {"sector":"R-S3","objects":[]},
    {"sector":"CM","objects":[{"type":"ammo_box","count":3}]}
  ]
}
~~~

sectors는 1..7개이며 sector 중복은 금지한다. objects는 0..6개이며 class 중복도 금지한다. type은 military_truck,mortar,tank,missile,ammo_box,drum만 허용하며 대소문자 무관. count는 bool을 제외한 엄격한 int 0..99이다. 문자열 숫자/음수/100은 422로 처리한다. 다른 진영 sector도 저장하되 채점하지 않는다.

canonical stored objects는 type uppercase 사전순, count 0 항목은 제거한다(SIM-M3-COUNT). response received.sectors는 sector 문자열 사전순. 누락 섹터는 이전 제출에서 유지하지 않는다. empty sector []와 미보고 sector는 서로 다르다. 전자는 정답이 0이면 일치 가능하고 후자는 항상 0점이다.

전체 body validation 완료 전에는 기존 보고를 변경하지 않는다. 422나 409로 실패한 요청은 기존 점수·stored report를 보존한다. M1/M3는 서버의 마지막 successful commit이 채점 대상이며 클라이언트 revision은 공식 wire에 넣지 않는다.

## 6 M6 스키마

~~~json
{"mission_code":"SIMB0001","ranking":["R-2","R-1","R-3"]}
~~~

상대 진영 slot 1..3개를 받으며 중복은 불가하다. 대소문자는 구분하지 않고 canonical uppercase로 저장한다. R-S1은 sector이므로 422이다. 아군 slot도 422이다. ranking 누락/빈 목록/4개 역시 422로 처리한다.

응답은 accepted:true,received.ranking. 검증·저장 성공 뒤 해당 eligible 팀을 submitted로 표시한다. 마지막 팀의 request가 조기 종료를 일으켜도 그 request의 결과는 200으로 전달해야 한다. response 작성 중 phase finished가 되었다고 409로 바꾸지 않는다.

첫 제출부터 현재 최선의 3개 순위를 보낸다. 더 좋은 결과를 다시 제출할 수 있지만 reporting이 아직 열려 있을 때뿐이다. SDK는 409이면 /me를 확인하고 running이면 잠시 대기, finished이면 전송 중단, reporting이면 transient retry한다.

## 7 드론 JPEG

test_mode는 관리자 전용 `/admin/configure`의 선택 필드 `test_mode`(엄격한 boolean)로 설정한다. 기본값은 false이며 생략하면 기존 운영자 설정을 유지한다. 설정 변경은 다른 configure와 동일하게 비활성 세션에서만 허용한다. 이 운영 설정의 보충 계약은 `contracts/admin_configure.schema.json`이다. 참가팀이 test_mode를 변경하는 경로는 없다.

test_mode=true && camera 지정이면 편성/phase와 관계없이 테스트 카메라를 1초 주기로 제공한다. camera는 main/test1/test2만 허용한다. test_mode=false이면 유효 camera 인수는 무시하고 경기 요청으로 처리한다. camera를 생략하면 test_mode에서도 경기 요청이다.

경기 요청은 running 편성팀만 가능. 우리 진영 시설물 파괴 0/1/2개에 새 frame 공개 간격은 1/2/5초이며, 3개면 403이다. 이는 자체 capture cadence와 구별되는 per-camp delivery gate이다. 같은 frame을 반복 반환할 때 X-Captured-At과 JPEG bytes를 바꾸지 않는다. 반환 성공마다 capture timestamp를 갱신하면 안 된다.

~~~http
Content-Type: image/jpeg
X-Captured-At: 2026-11-18T13:00:01.000+09:00
X-Frame-Interval-S: 1.0
X-Camera: main
X-Test-Mode: off
X-Camp: BLUE
X-Destroyed: 0
~~~

연습 응답에는 X-Camp/X-Destroyed를 생략한다. 최초 정상 frame이 없거나 카메라가 꺼졌으면 503이다. JPEG가 있어도 경기 phase가 아니면 409이다. 2D의 drone은 label 없는 topdown 기하 mock image이고 3D의 overhead perspective 영상과 시각적 동등성을 주장하지 않는다. bbox/정답 텍스트가 그려진 observer 화면을 전달하지 않는다.

## 8 오류 계약

| status | 형식 | 의미 |
| --- | --- | --- |
| 401 | detail string | 형식은 맞으나 알려지지 않은 mission_code |
| 403 | detail string | 경기 드론 시설 3개 파괴 |
| 409 | detail string | 현재 phase/편성/admission/start 상태에서 불가 |
| 422 | detail list | 스키마 오류 |
| 503 | detail string | 드론/실험 camera frame 없음 |
| 404 | detail string | 없는 endpoint |

~~~json
{"detail":[{"loc":["body","sectors",0,"objects",0,"count"],"msg":"count must be an integer between 0 and 99","type":"value_error"}]}
~~~

입력에 mission_code 자체가 없거나 8자리 형식이 아니면 422, 알려지지 않은 8자리이면 401이라는 SIM 검증 순서를 고정한다. body 전체를 오류 메시지에 echo하지 않는다. 문구 완전 일치보다 status·필드 구조를 기본 테스트 대상으로 하되 source에 고정된 reason은 위 값을 쓴다.

SDK는 401 설정 오류, 422 스키마 오류를 무한 retry하지 않는다. 409는 phase를 재확인하고, 네트워크 오류/503은 bounded backoff를 적용한다. SDK default backoff는 0.2, 0.5, 1, 2s로 capped하며, ready만 공식 안내대로 2s이다. reporting에서는 마감을 고려하여 새 LLM 호출 대기 없이 준비된 결과를 제출한다.

## 9 시뮬레이터 전용 로봇 bridge

이 경로는 ROS가 없는 CPU 개발 환경을 위한 시험용이다. 실제 대회 호환 endpoint라고 표시하지 않는다. GET 인증 query/POST body mission_code 방식은 동일하다.

GET /sim/session 응답:

~~~json
{
  "match_id":"smoke_six-0001","episode_index":1,"slot":"B-1","camp":"BLUE",
  "capabilities":{"rgb":false,"semantic":true,"lidar":true,"depth":false},
  "schema_version":"1.0"
}
~~~

SDK가 X-Sim-Match-ID header를 보내면 현 세션과 불일치 시 409이다. 공식 모사 endpoint는 이 header가 없어도 동작해야 한다. header는 실제 서버 adapter에서 제거한다. reset 이전에 이미 queue에 들어온 request는 원래 session_id를 유지하고 새 경기로 이전하지 않는다.

GET /sim/map-prior는 인증된 참가팀에 arena_id,bounds,sectors,bases,nominal_starts만 반환한다. 06의 PublicMapPrior 투영이며 실제 start_pose/jitter/boxes/faces/orders/expected_m1은 포함하지 않는다. SDK는 세션 초기화 때 이 정보를 읽어 baseline의 명목 지도 입력으로 사용한다.

GET /sim/calibration은 자기 front_camera intrinsics, 명목 gimbal_pivot_m/camera_offset_gimbal_m, pan·tilt 단위 변환, 명목 LiDAR scan 파라미터만 반환한다. 실제 injected calibration bias, 현재 gimbal pose, 센서 noise의 난수 실현값은 반환하지 않는다. 이 경로도 실물 API가 아니며 현장에서는 측정·제공된 보정 파일로 대체한다.

| 경로 /sim/robot/v1 아래 | 계약 |
| --- | --- |
| GET /state | 자기 hp,hp_max,battery_pct와 sequence,captured_tick,received_tick |
| GET /match | 자기 mode,cmd와 stamp |
| GET /odom | local_pose{x_m,y_m,yaw_rad},linear_x_mps,angular_z_rps와 stamp |
| GET /imu | orientation_xyzw,angular_velocity_rps[3],linear_acceleration_mps2[3]와 stamp |
| GET /scan | angle_min_rad,angle_increment_rad,range_min_m,range_max_m,ranges_m와 stamp |
| GET /camera | JPEG+X-Sim-Captured-Tick,X-Sim-Received-Tick,X-Sim-Sequence; unavailable이면 503 |
| GET /semantic | 02의 DetectionFrame; capability=false면 409 |
| POST /cmd_vel | linear_x_mps,angular_z_rps; accepted:true |
| POST /gimbal | pan,tilt,speed,acc; message=ok/locked |
| POST /fire | mission_code만; message=fired/empty/locked/reloading,left_ms |
| POST /oled | line 0..3, text ASCII≤21; accepted:true |

cmd_vel 한계 ±0.6m/s, ±3rad/s를 초과하면 422이다. locked일 때 accepted:true는 수신 확인만 뜻한다. active_command와 last_velocity_received_tick을 갱신하지 않고 명령을 폐기하므로 재개 뒤 새 명령이 필요하다. 0.5초 이상 새 유효 명령이 없으면 속도 0이다. 각 로봇의 control arbiter 하나만 명령을 발행한다.

gimbal 위치는 ±100, speed는 1..270deg/s, acc는 1..254이다. 입력 범위 오류는 422, 잠금이면 message locked, 접수이면 ok이다. 실제 도착을 뜻하지 않는다. SIM-GIMBAL 기본은 rate-limited position, acc는 저장하되 가속도 모델에는 사용하지 않는다는 한계를 명시한다. pan 실각=.5deg*pan, tilt 실각=.15deg*tilt이다. 잠금 시 기존 target을 취소하고 현재 위치를 유지한다.

fire 거절 우선순위는 locked→empty→reloading, 성공 시 ammo 1 감소·5초 발광·시작부터 10초 cooldown이 적용된다. left_ms는 현재 재발사까지 남은 시간, empty는 0, locked는 현재 device lock 잔여 시간(phase 잠금이면 0)으로 정의한 SIM 값이다. hp 0 자체는 영구 locked가 아니다.

scan no-return은 null이며 NaN/Infinity는 JSON에 쓰지 않는다. 공개 state에 상대 정보나 정답 M3를 추가하지 않는다.

## 10 관리자 API와 fixture 제어

admin token은 Authorization Bearer로 전달. 기본 localhost:8001 아래:

| Method path | 입력/결과 |
| --- | --- |
| POST /admin/configure | scenario_path,backend,clock_mode 및 선택 session=report/rehearsal,test_mode:boolean; match_id 반환 |
| POST /admin/ready-phase | 현 세션 ready 전환 |
| POST /admin/start | 현 세션 start |
| POST /admin/pause 및 /resume | phase 검사 후 이벤트 예약 |
| POST /admin/finish | 강제 reporting. 자동 채점은 현재 snapshot |
| POST /admin/fault | fault_id,at_tick,scope,parameters; 허용된 fault만 |
| GET /admin/snapshot | observer truth snapshot |
| GET /admin/result | finished일 때 run result, 그전에는 409 |
| POST /admin/shutdown | clean 종료 |

출발 실패·시설 파괴·센서 교차를 직접 주입하는 fault는 adjudication/control-plane test fixture로만 사용한다. 자율주행이나 조준 성공의 증거로 보고하지 않는다. admin 요청은 event journal에 기록하고 참가팀 로그에는 공개하지 않는다.

## 11 SDK 모듈별 구현

src/maicon_sim/server/app.py는 router 조립만, server/report_routes.py와 rehearsal_routes.py는 공통 service 사용, server/sim_robot_routes.py는 SIM 전용. server/service.py가 auth/session/schema 처리 후 command queue에 넣는다. server/waiters.py가 long-poll lifecycle, server/errors.py가 오류를 정규화한다.

sdk/http_port.py는 ParticipantPort 구현, sdk/report_worker.py는 전체 보고 직렬화, sdk/session.py는 sim handshake와 캐시 namespace, sdk/llm.py는 LLMPort를 담당한다. LLMPort는 parse_order(text,allowed_schema,deadline)->MissionInterpretation과 rank_threat(evidence,deadline)->ranking을 정의한다. 기본 fixture LLM은 mock이며 실제 provider 연결은 endpoint/model/key/timeouts 설정으로 교체한다. mock을 실제 LLM 검증이라고 표시하지 않는다.

## 12 완료 증거

FastAPI in-process 테스트와 실제 localhost 소켓 테스트를 모두 수행한다. 여섯 별도 프로세스의 long-poll을 열고 start 시 모두 응답하며, 다른 robot control 주기가 막히지 않아야 한다. 모든 POST의 accepted와 canonical received가 샘플 기대값에 맞아야 한다. deadline race·응답 유실·reset·M6 조기 종료를 07의 테스트로 검증한다.


보고 timeout 이후 지연된 이전 요청이 저장되는 경우는 공식 API의 revision/CAS 부재로 완전히 방지할 수 없다. 02 §13의 best-effort 복구와 unknown-outcome 시험을 적용한다. 서버 내부 ingress FIFO는 서버가 실제로 접수한 이후의 순서이며 네트워크에서 지연 중인 요청의 순서까지 보장하지 않는다.
