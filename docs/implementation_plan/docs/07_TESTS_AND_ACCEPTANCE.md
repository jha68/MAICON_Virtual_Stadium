# 2D와 3D 시뮬레이터 검증 및 인수 기준

이 문서는 새 저장소의 구현자가 구현 완료 여부를 판단할 시험 명세다. 테스트의 목적은 경기 규칙, 참가팀에 제공되는 관측, 시간 경계, 재실행과 보고 흐름이 계획대로 연결됐는지 확인하는 것이다. 시뮬레이터에서 통과한 결과를 실제 로봇의 주행·인식·조준 성능으로 표시하지 않는다.

규칙의 기준은 [01 경기 규칙](01_COMPETITION_RULES.md), 이벤트 순서·자료형은 [02 구조와 계약](02_ARCHITECTURE_AND_CONTRACTS.md), 전송 형식은 [05 서버와 로봇 API](05_SERVER_AND_ROBOT_API.md)다. 다음 시험의 `SIM-*`는 대회 확정 규칙이 아닌 계획에서 선택한 시뮬레이터 가정이다. 해당 설정을 변경하면 관련 golden fixture도 버전을 올린다.

## 1 완료 수준과 실행 원칙

| 수준 | 필수 결과 | 완료를 주장할 수 있는 범위 |
| --- | --- | --- |
| G0 계약 | JSON Schema·설정·공개 API·점수 단위 시험 통과 | 규칙 엔진과 전송 형식이 구현됨 |
| G1 2D | G0 + 2D 기하·센서·상태 전이·모의 경기 통과 | 논리·전략·통합 회귀 시험 가능 |
| G2 3D | G1 + CPU headless RGB·depth·가림·좌표 시험 통과 | 영상 기반 입력과 3차원 관측 시험 가능 |
| G3 전달 | G2 + 깨끗한 환경 설치·6개 프로세스·재생·배치 보고 통과 | 다른 에이전트가 같은 버전을 설치·실행·검증 가능 |
| H 현장 | 최종 ROS SDK 연결 후 실제 장비에서 별도 체크리스트 통과 | 확인한 장비·환경·경로에 한해서 현장 연결 검증 |

필수 시험이 실패했거나 실행되지 않았다면 해당 gate는 미완료다. 테스트를 skip 하여 G1/G2/G3 성공으로 만들지 않는다. GUI가 없는 CI에서는 GUI 시험을 별도 수동 증거로 제출할 수 있지만, 3D DIRECT RGB·depth 시험은 필수다. 실제 ROS가 없는 환경에서는 fake ROS 계약 시험을 수행하고 H를 미검증으로 남긴다.

모든 시험에는 `test_id`, 소스 commit, simulator version, rule profile hash, scenario hash, seed, backend, sensor mode, 실행환경과 결과를 기록한다. 난수에 의존하는 시험은 하나의 우연한 성공으로 통과시키지 않고 명시한 seed 집합을 사용한다. 테스트 실패 때 원래 시나리오와 이벤트 로그를 보존한다.

## 2 시간과 오차의 시험 기준

- 물리·규칙 tick은 정수 10ms다. 1.99초와 2.00초는 각각 199와 200개의 완료된 tick 구간이다.
- tick 시작에 예약 관리 이벤트를 처리하고, 기한 전이, API 접수 FIFO, 로봇 명령, 구간 적분, 기하 사건, M5종료, 센서 발행 순서로 처리한다. 정확한 계약은 02를 따른다.
- `match_ms = 300000`에 접수되는 M1·M3는 409다. `reporting` 시작 tick의 M6는 허용된다. `report_elapsed_ms = 30000`에 접수되는 M6는 409다.
- 구간 끝에 발생한 M5점령은 그 끝 시각에 reporting으로 전이한다. 다음 API 접수 전에 M1·M3 마감이 확정된다. 단, 구간 끝이 정확히 300초이면 기한 종료가 우선하므로 그 시각의 hit와 M5는 무시한다. 정확히 240초이면 목표 게시가 우선하므로 그 시각의 유효 센서 edge는 점령할 수 있다.
- 마지막 eligible 팀의 M6는 먼저 저장하고 성공 응답 스냅숏을 만든 후 finished로 바꾼다. 그 요청은 200이어야 하고 후속 요청은 409다.
- 무잡음 순수 수학 시험의 위치·거리 허용 오차는 1e-6m, 각도는 1e-6rad다. 충돌 최소 간격은 2D 구현의 기하 허용 오차를 적용하되 1e-5m 초과 침투를 허용하지 않는다. 렌더링 픽셀 시험은 아래 별도 기준을 사용한다.
- real HTTP의 wait·클라이언트 timeout은 실제 monotonic wall clock이다. accelerated mode에서는 fake transport를 사용하며 wall clock timeout을 경기 시간으로 해석하지 않는다.
- 스케줄러 단위 시험은 실제 `sleep` 없이 fake clock으로 실행한다. real HTTP 120초 대기 시험만 실제 시간을 사용하며 slow 표식을 붙인다.

## 3 시험 파일과 계층

미래 구현 저장소에 다음 계층을 만든다. 계획 묶음에 실행 테스트가 이미 포함돼 있다는 의미는 아니다.

```text
tests/
  unit/             # scoring, clocks, schemas, geometry, normalization
  contracts/        # HTTP body/status and participant port compatibility
  integration/      # engine + server + workers + restart
  render/           # PyBullet DIRECT, camera/depth/occlusion
  e2e/              # subprocess matches, viewer launch, clean install
  performance/      # reproducible benchmark, separate from correctness
  fixtures/         # hand-written requests, manifests, truth-only scorer inputs
  golden/           # expected score/event summaries, no implementation-generated oracle
```

pytest markers는 `unit`, `contract`, `integration`, `render`, `e2e`, `slow`, `performance`, `manual_gui`, `hardware`로 등록한다. G0~G3 필수 목록은 테스트 ID를 가진 manifest로 관리한다. 실행 이름은 코드 리팩터링으로 바뀔 수 있지만 ID는 유지한다.

Golden의 기대값을 피시험 채점 함수를 호출해 생성하지 않는다. 예를 들어 M3 기대 점수는 표의 7·7·7·9를 사람이 검산한 값으로 저장하고, 실제 결과만 엔진에서 계산한다. JSON 키·자료형·상태코드 계약과 함수 내부 구현을 복제하는 테스트를 구분한다.

## 4 P0 규칙과 점수 시험

| ID | Given | When | Then |
| --- | --- | --- | --- |
| RULE-001 | admitted·started 6팀, 모두 미피격, 보고 없음 | 300초와 보고 창 종료 | M1/M3/M6=0, 각 M4=15. 다른 사건이 없으면 M2/M5=0. 양 진영 동점 승리 보너스는 각 5, 최종 각 20 |
| RULE-002 | M1 정답 target·sector set·base 고정 | 세 항목 모두 정답 | M1=10 |
| RULE-003 | 같은 M1 정답 | target만 정답, sectors만 정답, base만 정답을 각각 별도 run | 각각3·3·4점. 빠진 필드를 이전 제출에서 보충하지 않음 |
| RULE-004 | M1 sectors 정답 `[R-S1, CM]` | 순서만 뒤집음 / R-S2를 추가함 | 순서 변경은3점, 추가 구역은 해당 항목0점 |
| RULE-005 | M1 전체 정답 보고 저장 | base만 정답으로 재보고 | target/search_sectors=null, 최종 M1=4 |
| RULE-006 | BLUE 팀, R-S1·R-S2·R-S3·CM 정답 모두 보고 | 종료 | M3=30 |
| RULE-007 | 같은 M3 fixture | R-S1의 한 클래스 count 를1 증가 | R-S1=0, 나머지7+7+9=23 |
| RULE-008 | R-S3 정답은 빈 목록 | R-S3를 명시한 objects=[] / R-S3 자체 생략 | 전자는7, 후자는0. `SIM-M3-COUNT` |
| RULE-009 | 어떤 섹터에서 tank 정답0 | objects=[] / tank:0 / DRUM:0을 각각 제출 | 정의된 6종의 0 항목은 모두0으로 정규화해 동일 집계. 알 수 없는 type:0 은422 |
| RULE-010 | BLUE 팀이 아군 B-S1도 정확히 보고 | 상대 구역과 CM 보고는 없음 | B-S1은 저장되지만 M3=0 |
| RULE-011 | 모든 채점구역 완전 정답 보고 저장 | R-S1만 정확히 재보고 | 기존 나머지 구역은 사라짐. 최종 M3=7 |
| RULE-012 | BLUE 팀의 M1 search_sectors가 B-S1, base가 RED_COMMAND_POST | M3 R-S1/R-S2/R-S3/CM 보고, 이후 M5 RED_MAINTENANCE 공개 | M3는 정상 30점. M5 목표는 MAINTENANCE. M1 출력으로 두 목표를 덮지 않음 |
| RULE-013 | BLUE B-1의 지정표적 RED_RADAR | B-2 또는 RED로봇이 처음 파괴 | B-1개인 M2=10. 실제 사격자의 M2에는 자동10점이 붙지 않음 |
| RULE-014 | RED 세 시설이 모두 처음 파괴됨 | M2 집계 | BLUE 세 팀 각15. 세 번째 파괴 시 기존 두 팀도 보너스 5 반영 |
| RULE-015 | 이미 파괴한 표적 | 같은 표적을 반복 명중 | 추가 M2점수·파괴 개수 변화 없음 |
| RULE-016 | 각 로봇 누적 피격0·1·2·3·4회 | 보고 단계에서 M4 확정 | 각각15·12·8·3·0 |
| RULE-017 | 아군이 다른 아군 수광부에 유효 조사 | 2초 dwell 충족 | 피해 로봇 HP 감소와 M4 감점. 공격자 명중 가점 없음 |
| RULE-018 | 4분 공개된 RED_MAINTENANCE가 BLUE 목표 | 그 거점 센서를 어느 로봇이든 유효 차단 | BLUE 세 팀 각 M5=10, RED=0, 즉시 reporting |
| RULE-019 | 상대 목표가 된 BLUE 거점 | BLUE로봇이 자기 거점 센서를 유효 차단 | RED 점령으로 판정. 로봇 camp로 점령 주체를 바꾸지 않음 |
| RULE-020 | 현재 목표가 아닌 거점 | 센서 차단 | M5점수와 경기 단계 변화 없음 |
| RULE-021 | M6 순위 정답 R1>R2>R3 | 6개 전체 순열 제출 | 아래 M6 순열 기대값과 정확히 일치 |
| RULE-022 | M6 위험도 동점 | 동점 그룹 안에서만 순서 교환 | 허용 정답 순열에 대한 최대 tier 점수 적용. `SIM-M6-SCORING` |
| RULE-023 | 종료 때 HP·탄약·M3 스냅숏 확보 | reporting 중 추가 센서/교전 이벤트 주입 | M6 정답과 M1~M5점수는 바뀌지 않음 |
| RULE-024 | 아래 6팀 golden 점수 스냅숏 | M6 모두 저장 후 최종 집계 | BLUE 합214, RED 합141(보너스 전), BLUE 각+5만 적용 |
| RULE-025 | start_failure가 주입된 팀 | 보고 제출과 종료 | admission/start 정책대로 409·0점, eligible 집합에서 제외. 나머지 팀의 정상 점수를0으로 만들지 않음 |

### M6 순열 기대값

호출부호는 실제 JSON에서 `R-1`, `R-2`, `R-3`로 적는다. 아래 숫자는 이를 줄인 표기다.

| 제출 순서 | 점수 |
| --- | --- |
| 1,2,3 | 15 |
| 1,3,2 | 10 |
| 2,1,3 | 5 |
| 3,2,1 | 5 |
| 2,3,1 | 0 |
| 3,1,2 | 0 |
| 1만 제출 | 10 |
| 1,2만 제출 | 10 |
| 2,1만 제출 | 0 |

부분 제출에서 빈 뒤쪽 자리는 정답이 아니며 15점을 받을 수 없다. 중복 ID, 자기 camp ID, 섹터 이름 `R-S1`은 채점 이전 422다. 위험도는 `(30*hp + 15*ammo + 4*m3)/120`로 정수 분자를 비교한다. 예를 들어 `(hp4,ammo0,m3=0)`, `(hp0,ammo8,m3=0)`, `(hp0,ammo0,m3=30)`은 모두 정확히 동점이며 전체 순열 6개가 15점이다. 3개의 float를 각각 반올림하여 동점을 만들지 않는다.

### 6팀 golden scorer fixture

이 fixture는 채점기 단위 시험용 종료 스냅숏이다. 일반 참가팀 API로 HP·정답 점수를 설정하는 기능을 만들라는 뜻이 아니다. 입력은 평가자 전용 테스트 생성기를 통해 제공한다. M2 조건은 RED 시설3개 모두 파괴, BLUE 시설 중 R-1에게 지정된 것만 파괴다. M5는 BLUE 점령이다.

| slot | M1 | M2 | M3 | hp | ammo | M4 | M5 | M6 | 보너스 전 | 최종 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B-1 | 10 | 15 | 30 | 4 | 4 | 15 | 10 | 15 | 95 | 100 |
| B-2 | 7 | 15 | 14 | 3 | 2 | 12 | 10 | 10 | 68 | 73 |
| B-3 | 4 | 15 | 9 | 2 | 6 | 8 | 10 | 5 | 51 | 56 |
| R-1 | 10 | 10 | 21 | 3 | 4 | 12 | 0 | 15 | 68 | 68 |
| R-2 | 6 | 0 | 14 | 4 | 2 | 15 | 0 | 5 | 40 | 40 |
| R-3 | 0 | 0 | 30 | 1 | 6 | 3 | 0 | 0 | 33 | 33 |

RED 위험도 분자는 R-1=234, R-2=206, R-3=240이므로 BLUE에게 정답은 `[R-3,R-1,R-2]`다. BLUE 위험도 분자는 B-1=300, B-2=176, B-3=186이므로 RED에게 정답은 `[B-1,B-3,B-2]`다.

M6 실제 제출 fixture는 B-1=`[R-3,R-1,R-2]`, B-2=`[R-3,R-2,R-1]`, B-3=`[R-2,R-1,R-3]`, R-1=`[B-1,B-3,B-2]`, R-2=`[B-2,B-3,B-1]`, R-3=`[B-3,B-2,B-1]`를 사용한다. 합산은 BLUE 214→229, RED 141로 검산한다. 승리 보너스를 비교 점수에 먼저 넣어 순환 계산하지 않는다.

## 5 P0 시간 경계와 장치 제한

| ID | Given / When | Then |
| --- | --- | --- |
| TIME-001 | 시작 전 `/order?wait=0`, 시작 tick이후 같은 요청 | 전자는 200 accepted:false, 후자는 200 accepted:true. 최초 공개 뒤 order 불변 |
| TIME-002 | match_ms=239990과240000에 `/target?wait=0` | 전자는 미공개, 후자는 공개. polling 간격 때문에 게시가 지연되지 않음 |
| TIME-003 | match_ms=299990과300000에 유효 M3 접수 | 앞 요청만 저장. 뒤 요청은 409. 마지막 저장 보고는 앞 값 |
| TIME-004 | match_ms=245000 구간 끝에 목표 센서 차단 | reporting 시작=245000. 이후 M1·M3 거절, M6 허용, 로봇 제어 잠금 |
| TIME-005 | reporting 시작 뒤 elapsed=29990과30000에 M6 접수 | 앞 요청은 200, 뒤 요청은 409 |
| TIME-006 | 6팀 중5팀 유효 제출, 6번째 팀은 malformed M6 | reporting 유지. 422는 제출 완료로 세지 않음 |
| TIME-007 | 마지막 eligible 팀이 유효 M6 제출 | 그 요청은 200·저장값 보존 후 즉시 finished. 앞 팀의 후속 수정은 409 |
| TIME-008 | 5팀까지 M6 제출 후 한 팀이 재제출 | 최신 보고만 교체. 제출 팀 수는5 유지 |
| TIME-009 | match100초에서 pause, simulation clock10초 진행 후 resume | match·effect clock은100초 유지, HTTP phase=running, M1·M3 허용, motion 정지. `SIM-PAUSE` |
| TIME-010 | pause가 시작될 때 주행·레이저·팬틸트 동작 중 | 물리 동작 중단. resume만으로 이전 주행·발광을 재시작하지 않음 |
| TIME-011 | emitter가 같은 수광부를 연속 조사 | 199tick까지 hit 없음. 200tick=2초 완료에1hit |
| TIME-012 | 1초 조사 후1tick 단절, 다시1초 조사 | hit 없음. 마지막 재접촉부터2초 연속이어야 hit |
| TIME-013 | emitter A가1초, B가 이어서1초 동안 같은 수광부 조사 | hit 없음. `SIM-LASER`는 emitter·receiver 쌍별 시간이며 다른 emitter끼리 합산하지 않음 |
| TIME-014 | t=0 발사, 다른 제한 없음 | t=4.99 발광, t=5.00 소등. t=9.99 재요청은 reloading,10.00은 fired |
| TIME-015 | 탄약8발, t=0,10,...70에8번 fired | 총8발 감소. t=80 요청은 empty이며 발광 없음 |
| TIME-016 | t=2에 피격, 이후 계속 조사되는 평가자 전용 입력 | t<12 추가 피격 없음. 무적 중 dwell=0이므로 t=12부터 새로 누적하여 t=14에 다음 hit |
| TIME-017 | HP1로봇이 피격되어 HP0 | drive·gimbal·fire 10초 잠금. 만료 후 HP0 상태로 새 명령 허용. 보고 프로세스 유지 |
| TIME-018 | HP0로봇이 다시 피격 | HP는 음수가 되지 않음. 기능 제한10초 재발생, M4=0 유지 |
| TIME-019 | t=0에 v=.6 명령 한 번, 장애물·잡음 없음 | [0,.5) 동안만 이동해 .3m. .5초부터 정지. 새 명령 수신 후 다시 이동 |
| TIME-020 | M5 공개 전부터 센서가 가려져 있음 | `SIM-CAPTURE` 기본값은 게시 후 false→true edge만 인정. 비웠다가 다시 가려야 점령 |
| TIME-021 | 양 진영 센서 사건의 시각 차이가10ms보다 큼 / 같은 tick | 앞 경우 빠른 사건 승리. 같은 tick은 기록된 event sequence, 기본 생성은 stable base_id 정렬로 결정 |
| TIME-022 | match_ms=300000에 hit threshold와 M5 edge 발생 | timer 마감 우선. reporting으로 전이하고 해당 hit·M5는 무시 |
| TIME-023 | match_ms=240000에 새 목표의 false→true edge 발생 | target 게시 우선. edge를 판정하여 유효 점령·즉시 reporting |
| TIME-024 | admitted·started eligible 집합이 비어 있음 | 즉시 finished, 전원0점. 보고 창을 기다리지 않음. `SIM-REPORT-ELIGIBILITY` |
| TIME-025 | practice가 활성화된 idle/ready에서 발사·피격 잠금 발생 | robot effect clock이 진행하여 cooldown·lock이 만료되고 SIM-PRACTICE대로 회복. mission idle/ready에서는 물리 제어 잠금 유지 |

TIME-013·016·020은 각각 `SIM-LASER`와 `SIM-CAPTURE`의 기본값을 시험한다. 다른 설정의 실험은 별도 profile이름과 기대값을 사용한다. 결과에 적용한 SIM-ID와 값도 기록한다.

## 6 P0 HTTP 계약과 동시성

| ID | Given / When | Then |
| --- | --- | --- |
| API-001 | 올바른 mission_code의 대소문자만 변경 | 같은 팀으로 인증. 코드 형식은 영숫자 8자리 |
| API-002 | 틀린 코드, 누락된 코드, 잘못된 body를 각각 전송 | 05의 인증·검증 우선순위에 따라 401 또는 422. traceback·secret 노출 없음 |
| API-003 | `/me` 정상 응답 확인 | 공식 필드 slot, camp, phase, ready만 제공. match_id·remaining_time·score·opponent_state 자동 추가 금지 |
| API-004 | waiting에서 ready POST, ready에서 ready POST | 전자는 409, 후자는 200 accepted:true. 이후 `/me.ready=true` |
| API-005 | M1 구식 `sectors`·`goal_base` 전송 | 새 필드로 조용히 추정·변환하지 않음. 05의 unknown-field 정책에 따라 422 |
| API-006 | M1 값에 한글 시설명, 숫자 섹터, 중복 섹터 | 422. enum 코드와 섹터 문자열 검사 |
| API-007 | M3 count=-1,100,1.5,true 또는 중복 type·sector | 각각 422. Python bool을 정수 1로 수용하지 않음 |
| API-008 | M3 type 대소문자와 섹터 순서 변경 | 수용·정규화하고 received로 실제 저장값 확인 |
| API-009 | M6에 자기 camp, 중복 ID, 잘못된 형식, 빈 ranking | 422. 제출 팀 수 증가 없음 |
| API-010 | 유효 POST의 저장 직후 응답 유실 | 저장 상태 보존. retry로 점수를 중복 추가하지 않고 최신 전체 보고만 교체 |
| API-011 | A 정상 응답 뒤 B 제출 / A 저장 전 지연·client timeout 뒤 B 제출 | 정상 경로는 SDK 직렬화로 A→B 순서. timeout 경로는 B→늦은 A 저장이 가능함을 재현하고 최신 B 재전송·received 확인으로 복구. 공식 revision/CAS 없이 마감 직전 복구를 절대 보장하지 않음 |
| API-012 | 6팀이 order와 target 각각 wait120, 총 12개 longpoll 유지 | `/me`, ready·보고, 로봇 명령 처리가 멈추지 않음. 엔진 single writer 계속 진행 |
| API-013 | wait=0,1,120,121,-1,문자열 요청 | 05의 범위 검증. 0은 즉시 응답, 1·120은 대기, 범위 밖과 비정수는 422 |
| API-014 | 실제 HTTP에서 게시 없이 wait120 지속 | wall clock 120초 이전에 timeout 응답하지 않음. 120초 후 허용 환경 오차 내 accepted:false. slow 시험 |
| API-015 | longpoll 중 클라이언트 취소·프로세스 종료를 100회 반복 | waiter 정리. 종료 후 활성 waiter=0이며 미완료 task가 늘지 않음 |
| API-016 | 구 경기 longpoll 중 다음 경기로 reset | 새 경기 order를 옛 세션 응답으로 누출하지 않음. session 교체 규칙대로 종결 |
| API-017 | realtime HTTP 서버를 accelerated 배속으로 실행 시도 | 지원하지 않는 조합으로 startup에서 명시 실패. network 시간을 임의 배속하지 않음 |
| API-018 | 같은 시각에 6팀의 M3 POST도착 | ingress 순서 기록·재생 가능. request handler가 world를 직접 변경하지 않음 |
| API-019 | rehearsal prefix로 me·ready·order·target·보고 호출 | 동일 body와 단계 규칙. 별도 공식 경기 기록을 오염시키지 않음 |
| API-020 | `/api/rehearsal/drone` 요청 | 미지원 404. 테스트 영상은 `/api/report/drone?camera=test1` 사용 |
| API-021 | order·target이 HTTP 200 accepted:false 반환 | client가 임무 수신 성공으로 해석하지 않고 reason을 구분해 재시도 |
| API-022 | report 창이 닫힌 뒤 오래된 M1·M3 retry | 409 후 재시도 폭주 없음. 저장값 변화 없음 |

실제 장치 명령의 재시도는 보고 POST와 구분한다. `fire` 응답 유실을 주입했을 때 SDK가 자동으로 두 번째 발사 요청을 보내지 않는지 확인한다. wire에 idempotency key가 없으면 존재하는 것처럼 가정하지 않는다.

## 7 P0 참가팀 관측과 정답의 분리

이 절은 의도치 않은 정보 누출을 방지하는 자료형·프로세스 계약 시험이다. 같은 OS 계정에서 악의적으로 모든 파일을 읽는 공격까지 막는 보안 샌드박스 인증을 의미하지 않는다.

| ID | Given / When | Then |
| --- | --- | --- |
| ISO-001 | 참가팀 public API·robot bridge·SDK 객체 순회 | 상대 true pose·HP·ammo·score, M3 정답, 원본 face ID, segmentation ID를 찾을 수 없음 |
| ISO-002 | 평가자 renderer가 segmentation·depth truth 생성 | 평가자 전용 경로에만 기록. RGB 응답·메타데이터·픽셀 파일명에 정답 라벨을 넣지 않음 |
| ISO-003 | 2D semantic 모드 실행 | run 결과에 semantic 모드 명시. 실제 카메라 AI 검증으로 표시하지 않음 |
| ISO-004 | oracle 평가 policy 실행 | oracle 표식과 별도 결과 그룹 사용. candidate leaderboard 기본 비교에서 제외 |
| ISO-005 | B-1 토큰으로 B-2로봇 조회·명령 | 05의 팀 범위 검사로 거절. 다른 팀 정보와 동작에 변화 없음 |
| ISO-006 | 참가팀 서브프로세스 시작 | admin 자격증명과 truth 경로를 환경·인수·작업 경로로 전달하지 않음 |
| ISO-007 | 일반 로그·HTTP access log·예외 로그 수집 | mission_code와 admin token 마스킹. query string으로 코드가 새지 않음 |
| ISO-008 | 허용 관측은 같고 숨은 truth만 다른 두 세계 | 참가팀 DTO 직렬화 결과 동일. 숨은 truth는 평가자 채점에만 영향을 줄 수 있음 |
| ISO-009 | 3D camera-only profile에서 semantic endpoint 조회 | 거절. detector 없이 정답 객체를 자동 주입하지 않음 |

## 8 P1 2D 기하와 관측

| ID | Given / When | Then |
| --- | --- | --- |
| GEO-001 | 장애물 없는 world, pose(1,1,0), v=.2,w=0을 1초 | pose(1.2,1,0), 허용 오차 1e-6 |
| GEO-002 | pose(1,1,0), v=0,w=pi/2를 1초 | 위치 불변, yaw=pi/2 |
| GEO-003 | pose(1,1,0), v=.2,w=.5를 2초 | x=1+.4sin(1), y=1+.4(1-cos(1)), yaw=1 |
| GEO-004 | 양의 yaw 회전과 양의 pan 명령 | yaw는 왼쪽, pan은 오른쪽으로 방향 변화. 동일 부호로 처리하지 않음 |
| GEO-005 | 25×23cm footprint가 회전하며 벽·박스에 접근 | 중심점이 아닌 회전 footprint로 충돌 판정. 1e-5m 초과 침투 없음 |
| GEO-006 | 한 tick에 얇은 장애물을 건너뛰는 큰 시험 속도 | 명령 제한 또는 swept·substep 검사로 관통 방지 |
| GEO-007 | 두 로봇이 같은 통로에서 정면 접근 | iteration 순서를 바꿔도 결과 동일. 상호 침투 없음 |
| GEO-008 | 40cm 통로 중앙으로 직진 | 25cm 폭 로봇 통과. 회전할 때도 대각 footprint 검사 |
| GEO-009 | 박스에 sector_id 명시, 카메라는 다른 섹터에 위치 | 정답은 manifest의 박스 섹터. 보고를 로봇의 현재 섹터로 강제 변환하지 않음 |
| GEO-010 | 생성기가 박스 중심을 섹터 경계에 배치 | 06의 검증에 따라 거절·재생성. 부동소수점 경계로 결과가 흔들리지 않음 |
| GEO-011 | frustum 안 객체 앞에 불투명 박스 추가 | semantic가림 정책에 따라 미관측 처리. 카메라 뒤 객체는 항상 미관측 |
| GEO-012 | 같은 face를 100프레임에서 재관측 | baseline 집계 1. 프레임 수만큼 누적하지 않음 |
| GEO-013 | 동일 클래스·동일 texture를 서로 다른 두 face에 배치 | 물리 관측을 구별할 수 있으면 집계 2. texture이름으로 합치지 않음 |
| GEO-014 | false positive 뒤에 반증 관측 제공 | baseline 집계 수정 가능. 과거 최대 count를 고정하지 않음 |
| GEO-015 | 미관측 섹터와 충분히 관측한 빈 섹터 | 내부 상태 구분. 미관측을 자동으로 빈 정답이라고 확정하지 않음 |

GEO-012~015는 함께 제공하는 demo baseline의 회귀 기준이다. 외부 참가팀 알고리즘이 실패하면 해당 알고리즘의 측정 결과이며 시뮬레이터 구현 불합격과 혼동하지 않는다. 이 시험의 관측 입력은 semantic fixture로 고정한다. 03의 D2-* 단위 시험도 G1에 포함한다.

## 9 P1 3D 렌더링과 센서

| ID | Given / When | Then |
| --- | --- | --- |
| RENDER-001 | PyBullet DIRECT, DISPLAY와 GPU 없음 | GUI 호출 없이 640×480 uint8 BGR frame 생성 |
| RENDER-002 | optical 좌표 (0,0,2)의 점 투영 | 주점(cx,cy)에 표시. +x는 이미지 오른쪽, +y는 아래쪽 |
| RENDER-003 | fx=fy=320,cx=319.5,cy=239.5, 점(.5,0,2) | 예상 u=399.5,v=239.5. landmark 검출 오차 ≤2px |
| RENDER-004 | 카메라 앞 2m의 정면 평면, 04 fixture의 near·far | depth 역변환의 중심 오차 ≤0.01m. depth buffer를 미터로 직접 해석하지 않음 |
| RENDER-005 | RGB 빨강·초록·파랑 색 패치 | SDK BGR 채널 순서 정확. raw 색 시험과 JPEG 손실 시험 분리 |
| RENDER-006 | 같은 장면에서 pan=+20, tilt=+20 | pan 물리각 -10deg, tilt +3deg. 04 행렬의 투영 예측과 차이 ≤2px |
| RENDER-007 | 불투명 박스가 객체 face를 완전히 가림 | 참가팀 영상에서 해당 face가 보이지 않고 평가자 visible 면적=0 |
| RENDER-008 | 박스 앞면과 뒷면의 texture가 다름 | 뒷면 이미지가 앞면에 뒤집혀 나타나지 않음. face 방향·UV 정확 |
| RENDER-009 | 카메라 시야에 자기 차체를 놓고, LiDAR ray 앞에 다른 로봇을 놓음 | RGB는 실제 visual mesh의 가림을 반영. LiDAR는 04의 기본값대로 자기 body를 제외하고 다른 로봇은 차폐물로 판정 |
| RENDER-010 | camera10Hz, odom·IMU20Hz, state2Hz, 1초 구간 | t=0 샘플을 제외한 (0,1]에서 각각 10·20·20·2개. timestamp는 생성 시각 |
| RENDER-011 | image worker를 500ms 지연 | 센서 큐 상한 유지, 최신 frame 정책 동작. motion100Hz 유지 |
| RENDER-012 | drone의 마지막 정상 frame 반복 반환 | JPEG bytes와 X-Captured-At 동일. 새 관측으로 중복 추정하지 않음 |
| RENDER-013 | 우리 시설 파괴 수 0→1→2→3 | 새 drone frame 간격 1→2→5초, 마지막 403. 상대 시설 수로 우리 간격을 바꾸지 않음 |
| RENDER-014 | 카메라 초기 미수신·일시 손상·진행 외 요청 | 각각 503·마지막 정상 frame 반복·409로 구분 |
| RENDER-015 | test mode on, camera=test1, 경기 밖 | 연습 영상은 1초 간격. camera를 생략한 경기 요청과 구분 |
| RENDER-016 | noise=0인 평면 LiDAR ray, 벽까지 1m | 거리 오차 ≤1e-5m. miss sentinel은 계약 형식 |
| RENDER-017 | offline lockstep에서 고정 seed로 noise·drift 적용 | 동일 센서 시퀀스 재현. RGB 렌더 빈도가 odom 난수를 바꾸지 않음 |
| RENDER-018 | smoke proxy 강도 증가 | profile에 정의한 영상 감쇠 재현. 실제 연기·LiDAR 물리 검증으로 표시하지 않음 |
| RENDER-019 | texture asset 누락 또는 digest 불일치 | 실행 전 검증 실패. 별도로 명시한 placeholder 모드만 허용 |
| RENDER-020 | 매 engine tick마다 3D scene 동기화 | visual body pose와 truth pose 차이가 허용 오차 이내. PyBullet이 base를 별도로 이동시키지 않음 |

RENDER-003의 intrinsics는 투영 단위 시험용이다. 기본 FOV와 다르면 fixture가 K를 override한다. 실제 로봇 보정값으로 주장하지 않는다. 전체 픽셀 hash는 동일 renderer·driver·library lock에서만 비교한다. 일반 CI는 landmark·shape·채널·가림·depth 오차를 비교한다. 04의 3D 단위 시험도 G2에 포함한다.

## 10 P1 재생과 2D 3D 일관성

| ID | Given / When | Then |
| --- | --- | --- |
| REPLAY-001 | 동일 scenario·rules·seed·backend에서 offline lockstep 또는 기록된 ingress·actions·drops 재생 | phase 전이·접수 순서·점수·shot/hit/capture event·state hash 동일. realtime OS 스케줄링을 seed만으로 재현한다고 주장하지 않음 |
| REPLAY-002 | 같은 action과 공통 semantic·oracle 입력을 2D·3D에 재생 | 공통 base pose·제한 상태·점수·종료 이유 동일. 이미지 추론 결과는 이 시험 입력에서 제외 |
| REPLAY-003 | 같은 3D RGB를 후보 모델 2종에 재생 | 입력 frame와 시각 동일. 검출·보고·점수 차이는 허용하며 비교 측정 |
| REPLAY-004 | 기록된 API 접수 순서를 CPU 부하가 다른 환경에서 재생 | 저장 순서·deadline 판정 동일. 실시간 네트워크 도착 순서의 동일성은 요구하지 않음 |
| REPLAY-005 | 로그 중간 snapshot에서 resume | 처음부터 재생한 동일 tick의 상태와 일치. 난수 상태·pending effect 복원 |
| REPLAY-006 | frame 렌더를 끄거나 viewer를 닫음 | 고정 action trace의 규칙·채점 결과 불변 |
| REPLAY-007 | run seed 변경 | 랜덤화 대상만 바뀌고 스키마·크기·충돌·배치 제약은 유지 |
| REPLAY-008 | 로그를 수정하거나 일부 누락 | checksum·sequence 검사에서 명시 실패. 손상 로그를 정상 재현으로 표시하지 않음 |

실시간 렌더링의 처리 시간과 frame drop은 OS 부하에 따라 달라질 수 있으므로 capture·drop·전달 순서를 기록한다. seed만 같은 두 realtime 실행의 픽셀·타이밍 동일성은 요구하지 않는다. 결정성 보장은 offline lockstep와 기록된 입력 재생에 적용한다.

2D semantic 결과와 3D 실제 모델 결과의 점수 일치는 요구하지 않는다. 전자는 탐색·보고 로직 시험이고 후자는 시각 인식이 포함된 시험이다. backend 비교표에는 sensor mode를 반드시 기록한다.

## 11 P1 통합과 장애 시나리오

| ID | 시나리오 | 합격 조건 |
| --- | --- | --- |
| E2E-001 | 서로 다른 mission_code로 참가팀 6개를 별도 프로세스로 실행 | 임무·slot·camp 혼선 없이 ready→running→reporting→finished. 각 프로세스는 자기 정보만 획득 |
| E2E-002 | 245초에 M5로 조기 종료, 모든 팀이 M6 준비 완료 | M1·M3 저장 보존, 제어 즉시 잠금, 첫 M6에 최선 결과 제출, 전원 제출 시 조기 finished |
| E2E-003 | 한 팀만 준비 실패 또는 미출발 | 다른 팀 계속 진행. admission·eligible 정책 기록. 보고 창에서 무한 대기하지 않음 |
| E2E-004 | 경기 중 참가팀 하나를 강제 종료, 최대 3회 자동 재시작 | 현재 phase·session 확인 후 복구. 자식 worker와 motion publisher 중복 없음 |
| E2E-005 | 4번째 비정상 종료 | 무한 재시작 없음. 다른 팀·서버 유지. 실패 원인 기록 |
| E2E-006 | 보고 직후 응답 유실과 프로세스 재실행 | 저장 보고 보존. 새 보고는 전체 snapshot. 재실행을 새 경기로 오인하지 않음 |
| E2E-007 | 다음 경기에서 camp·slot 변경, 코드 재사용 profile 적용 | 과거 object·rank·timer·ready·cache 무효화. 새 session 확인 |
| E2E-008 | 구조화 명령 직접 수신·M6 mock, 지연 LLM 어댑터가 주입되어도 호출 없음 | LLM 호출·M1 제출 0회, 제어 루프 유지. 외부 어댑터 자체의 timeout·JSON 검사는 SDK 계약 시험에서 수행 |
| E2E-009 | 두 개의 wait120과 camera 추론 병행 | 명시적인 pause를 제외하고 주행 명령 공백이 0.5초를 넘지 않음 |
| E2E-010 | stale POST·드론 중단·pause·restart를 고정 seed로 복합 주입 | trace 재생 가능. 마감 후 재시도 폭주와 메모리 무한 증가 없음 |
| E2E-011 | observer UI에서 일시정지·배속 조작 | realtime의 금지 조합 차단. simulation pause와 match pause를 구분해 표시 |
| E2E-012 | 참가팀 HP0·물리 잠금 중 reporting | 프로세스가 살아 있고 M6 제출. HP0을 경기 종료로 오인하지 않음 |

6팀 시험을 한 프로세스에서 함수 6개를 호출하는 것으로만 대체하지 않는다. 직렬화·포트 충돌·재시작·HTTP 동시성을 검증해야 한다. 모든 단위 시험을 6개 프로세스로 실행할 필요는 없다.

## 12 성능 시험과 배치 비교

성능 목표와 실측 결과를 분리한다. 측정하지 않은 CPU의 속도를 보장하지 않는다. 기준 환경은 Ubuntu22.04 x86_64·Python3.10·GPU 없음이며, 결과에 CPU 모델·논리 코어·RAM·renderer·package lock·프로세스 수·해상도를 기록한다.

| ID | 측정 | 합격 또는 기록 기준 |
| --- | --- | --- |
| PERF-001 | 2D headless, 로봇 6대, 300초, seed 10개 | wall duration·sim/wall 배율·tick p50/p95/p99 기록. realtime 누적 lag를 감추지 않음 |
| PERF-002 | 3D DIRECT, camera 1개 640×480@10Hz와 drone, 300초 | 생성·전달 지연, drop 수, sim/wall 배율 기록. realtime을 못 맞추면 overload 명시 |
| PERF-003 | 3D DIRECT, camera 6개, 같은 기간 | 확장성 별도 측정. camera 1개 결과를 6개 성능으로 표시하지 않음 |
| PERF-004 | longpoll 12개, 팀별 me1Hz, 변경 보고 병행 | request p95/p99·timeout·queue 최대 길이 기록. control 처리 기아 없음 |
| PERF-005 | 추론 worker2FPS, 입력10FPS | queue 상한 유지, 최신 frame 선택, drop 계수 정확 |
| PERF-006 | 같은 simulator 프로세스에서 6경기 반복 | reset 후 worker·waiter·subscriber 수 복원. warmup이후 RSS가 지속해서 선형 증가하지 않음 |

G3 correctness 합격이 매우 빠른 CPU에만 의존해서는 안 된다. realtime으로 제공하는 모드는 300초 동안 wall clock과 simulation clock 차이가 허용 lag를 넘으면 실패로 표시한다. tick을 조용히 건너뛰거나 dt를 늘려 속도를 맞추지 않는다. lag의 기본 한도와 warning·abort 정책은 02·08을 따른다.

정책 비교 batch의 기본 회귀 세트는 seed0~29의 30개 배치다. seed0~19로 파라미터를 선택하고 20~29를 보류 검증으로 구분한다. 이는 실제 대회 분포에 대한 통계적 보장이 아니다. 평균·중앙값·최솟값·하위10% 점수, 미제출률, 출발 실패, 충돌, 재시작, M3 섹터 완전 일치율, M6 정확도, 첫 유효 보고 시각을 함께 기록한다. oracle·semantic·RGB 후보는 별도 표로 비교한다.

## 13 설치와 전달 검증

실행 CLI와 설치 명령의 단일 기준은 [08 빌드와 인수인계](08_BUILD_AND_HANDOFF.md)다. 구현자는 그 명령을 CI와 사용자 안내에서 그대로 사용하고 여기에서 별도 명령 체계를 만들지 않는다.

| ID | Given / When | Then |
| --- | --- | --- |
| PACK-001 | 저장소가 없는 깨끗한 Ubuntu22.04·Python3.10 | 08의 설치와 lock 동기화로 필수 의존성 설치. 개발자 개인 경로·원본 대화·기존 MAICON checkout 불필요 |
| PACK-002 | core·2D만 설치 | PyBullet·ROS·CUDA import 없이 core 시험과 2D headless 실행 |
| PACK-003 | 3D 선택 의존성 설치, DISPLAY 없음 | headless RGB demo와 render 시험 통과 |
| PACK-004 | 네트워크 차단 후 동봉 demo 실행 | 외부 LLM·모델 다운로드·공식 비공개 이미지 없이 fixture와 demo 동작 |
| PACK-005 | 공백을 포함한 임의 경로에 clone | 상대경로와 CLI 정상. `/workspace`나 작성자 home 하드코딩 없음 |
| PACK-006 | 모든 sample config와 scenario 검증 | schema·참조 무결성·asset digest·배치 검증 통과 |
| PACK-007 | 잘못된 config·없는 asset·지원하지 않는 version | 실행 전 원인·필드 경로를 제시하고 nonzero exit. 조용한 대체와 traceback-only 금지 |
| PACK-008 | README의 처음 사용자 절차 실행 | 2D 보기·3D frame·모의 경기·재생·batch 결과 파일 실제 생성 |
| PACK-009 | wheel을 설치하고 repo 밖에서 실행 | 필요한 default schema·asset·config가 package에 포함돼 정상 동작 |
| PACK-010 | GUI 환경에서 2D viewer와 3D GUI 실행 | 선택 로봇·phase·시계·시점 표시. 창 닫기 후 정상 종료·로그 보존 |

최종 납품에는 설치 로그, 테스트 summary JSON·JUnit, 2D와 3D run manifest 각 1개 이상, golden 비교표, 재생 성공 증거, GUI 스크린샷 또는 녹화, 성능 환경표를 포함한다. 증거가 없는 항목을 완료 체크하지 않는다.

## 14 현장 어댑터 검증과 변경 관리

H gate 전에도 fake ROS로 topic·service mapping, QoS, timeout, latched match 상태 복구, 부호·단위 변환을 시험한다. 실제 서비스 타입이 확정되지 않았으면 placeholder 연결을 실물 호환 완료로 표시하지 않는다.

현장 최소 검증 순서는 zero-motion 상태 수신 → 저속 직선·회전 → 정지 watchdog → 팬틸트 부호 → 카메라 형식 → 최종 서버 ready·보고 → pause·resume → report → 재실행이다. 각 단계는 [09 현장 연결](09_FIELD_ADAPTER_AND_QUESTIONS.md)을 따른다. 실물에서 truth 주입·배속·가상 관리 API를 사용할 수 없도록 backend를 분리한다.

최종 규정이 바뀌면 01의 사실·가정표, rule profile, 05 API 계약, 관련 fixture, 시험 기대값, 변경 전후 회귀 결과를 한 변경 단위로 갱신한다. 규칙은 공통 엔진 한 곳에서 바꾸고 2D·3D에 각각 구현하지 않는다.

## 15 인수인계 최종 체크리스트

- [ ] 모든 P0 시험과 G0~G3 필수 시험이 pass이며 skip 사유를 완료로 세지 않았다.
- [ ] 2D/3D 공통 규칙 엔진과 동일 action replay 결과를 확인했다.
- [ ] semantic·oracle·RGB 평가 결과와 실제 하드웨어 검증을 명확히 구분했다.
- [ ] M1/M3 전체 교체, 수신 시각 마감, M6 조기 마감, M5 자진영 오진입을 시험했다.
- [ ] 실제 HTTP longpoll, 6개 별도 참가팀 프로세스, 재시작·다음 경기 reset을 시험했다.
- [ ] 참가팀 API·SDK·기본 로그에 정답과 토큰이 섞이지 않았다.
- [ ] 원본 대화·원래 저장소·외부 비공개 자료 없이 설치와 기본 demo를 재현했다.
- [ ] 고정 seed의 실패 로그를 다른 환경에서 재생했다.
- [ ] 규정 미확정 사항의 적용 기본값과 관련 SIM-ID를 run manifest에 남겼다.
- [ ] 실행하지 않은 실물 검증과 성능은 미검증으로 보고했다.

## 근거

대회 사실은 main commit `7c414445fcf0302620b2c89f16ce2064f91ca753`의 [참가팀 API 안내](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PARTICIPANT_API_GUIDE.md) §1~11 및 부록, [2차 사전교육](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PRESTUDY_2_2026.md) 11~18쪽을 따른다. 위 테스트 ID·fixture·허용 오차·gate·benchmark seed는 이 계획의 구현 계약이다.
