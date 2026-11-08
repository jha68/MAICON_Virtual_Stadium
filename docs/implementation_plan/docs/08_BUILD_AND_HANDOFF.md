# 구현 순서와 새 저장소 인계 절차

이 계획의 완료 대상은 실행 가능한 시뮬레이터다. 지금 전달하는 묶음에는 구현계획·계약·예시만 들어 있다. 아래 명령은 구현자가 만들어야 할 CLI 계약이며, 이미 존재하는 프로그램을 실행하라는 뜻이 아니다. 대상 저장소에 이 폴더 전체를 복사하면 원본 MAICON 저장소나 이전 대화 없이 구현을 시작할 수 있다.

## 1 저장소 생성과 복사

대상 저장소의 기존 AGENTS.md·라이선스·빌드 지침을 먼저 확인한다. 기존 코드를 삭제하지 않는다. 빈 저장소를 기준으로 한 구조는 다음과 같다.

~~~text
maicon-sim/
  README.md
  pyproject.toml
  uv.lock
  .python-version
  Dockerfile
  .github/workflows/ci.yml
  docs/implementation_plan/       # 이 계획 묶음을 그대로 복사
  src/maicon_sim/
    __init__.py
    cli.py
    core/
      types.py clocks.py engine.py commands.py events.py
      rules.py scoring.py sessions.py snapshots.py rng.py
      geometry2d.py geometry3d.py planar_motion.py laser.py
    config/
      models.py loader.py semantic_validation.py
    server/
      app.py report_routes.py rehearsal_routes.py sim_robot_routes.py
      admin_routes.py service.py waiters.py errors.py
    sensors/
      scheduler.py gateway.py semantic.py camera.py drone.py
      lidar.py odometry.py imu.py
    backends/
      two_d.py
      bullet/backend.py
      bullet/scene.py
      bullet/projection.py
      bullet/render_worker.py
      bullet/asset_builder.py
    sdk/
      ports.py http_port.py in_process_port.py report_worker.py session.py llm.py
    policies/
      idle.py baseline.py scripted.py
    perception/
      interfaces.py synthetic_template.py
    viewer/
      pygame_viewer.py
    evaluation/
      recorder.py replay.py batch.py metrics.py compare.py
    adapters/
      ros2/                  # 선택 의존성, 가짜 전송 계층을 이용한 테스트는 필수
    resources/
      schemas/               # 계획 묶음의 contracts/를 복사
      examples/              # 계획 묶음의 examples/를 복사
  tests/
    unit/ contracts/ integration/ render/ e2e/ performance/
    fixtures/ golden/
  scripts/
    bootstrap.sh doctor.sh
  artifacts/                 # gitignore에 등록
~~~

설명 주석은 프로젝트 문서 언어에 맞춰 조정할 수 있다. 구조 이름과 모듈 간 책임 경계는 유지한다. 작은 함수를 별도 파일로 분리하는 것은 허용한다. core가 server나 backend를 import하여 순환 의존성을 만드는 것은 금지한다.

## 2 의존성 확정

기준 환경인 Ubuntu 22.04와 Python 3.10에서 먼저 작은 호환성 검증을 수행한다. NumPy·Pydantic 2·FastAPI를 함께 실행하고, PyBullet DIRECT에 연결해 64×48 이미지 한 장을 생성하며, pygame의 dummy driver를 초기화한다. 검증을 통과한 패치 버전 조합을 uv.lock에 고정한다. PyBullet·OpenCV와 NumPy의 ABI 호환성을 실제로 확인하고, 최신 버전끼리라는 이유만으로 호환된다고 가정하지 않는다.

선택 의존성은 `viewer`에 pygame-ce, `bullet`에 pybullet, `vision`에 opencv-python-headless, `dev`에 pytest·jsonschema·httpx·build를 정의한다. ROS 2는 pip에서 임의의 rclpy 패키지를 받아 구성하지 않고 별도 컨테이너나 시스템 환경에서 관리한다.

다음 조건을 지킨다.

- Python 3.10에서 지원하는 API를 사용하고, Python 3.11 전용 문법에 의존하지 않는다.
- wheel에 스키마·기본 설정·합성 자산 생성기를 포함하여 현재 작업 디렉터리가 저장소 밖이어도 실행되게 한다.
- 설치가 끝난 환경에서는 네트워크 없이 자산을 생성하고 예제 경기를 실행할 수 있어야 한다.
- 외부 학습 모델 다운로드를 최초 실행의 필수 단계로 만들지 않는다.
- lock 파일 생성·이미지 생성·테스트를 실제로 수행하기 전에 성공 로그를 만들지 않는다.

## 3 CLI 완료 계약

모든 하위 명령은 `--help`를 제공한다. 기본 종료 코드는 성공 0, 입력·설정 오류 2, 실행·의존성 오류 3, 검증 실패 4, 사용자 중단 130이다. 로그에 mission code나 admin secret을 출력하지 않는다.

~~~bash
maicon-sim doctor --backend 2d
maicon-sim doctor --backend 3d --headless
maicon-sim validate --scenario examples/scenario_smoke_six.yaml
maicon-sim assets build --manifest examples/assets_synthetic.yaml --out artifacts/assets
maicon-sim run --scenario examples/scenario_smoke_six.yaml --backend 2d --clock accelerated --headless --out artifacts/smoke
maicon-sim run --scenario examples/scenario_smoke_six.yaml --backend 2d --clock realtime --viewer --out artifacts/interactive
maicon-sim run --scenario examples/scenario_perception_gallery.yaml --backend 3d --clock accelerated --headless --out artifacts/gallery
maicon-sim serve --scenario examples/scenario_smoke_six.yaml --backend 2d --public-port 8000 --admin-port 8001
maicon-sim agent --slot B-1 --policy baseline --server http://127.0.0.1:8000
maicon-sim replay --run artifacts/smoke --backend 2d --verify --out artifacts/replay
maicon-sim compare --left artifacts/smoke --right artifacts/replay --mode core
maicon-sim batch --scenario examples/scenario_smoke_six.yaml --backend 2d --seeds 0:20 --out artifacts/batch
maicon-sim generate --template examples/scenario_smoke_six.yaml --seed 42 --count 5 --out artifacts/scenarios
maicon-sim benchmark --scenario examples/scenario_smoke_six.yaml --backend 3d --duration-s 60 --out artifacts/benchmark
maicon-sim dataset --scenario examples/scenario_perception_gallery.yaml --out artifacts/private-dataset
maicon-sim replay --run artifacts/smoke --backend 2d --checkpoint-tick 5000 --verify --out artifacts/resumed
~~~

위 명령의 `examples`는 구현 저장소에 복사한 사용자용 예제 디렉터리다. 패키지에 포함된 리소스를 사용하는 `--example smoke_six`도 제공하는 것을 권장한다(SHOULD). `--scenario`와 `--example`은 동시에 사용할 수 없다.

`run`은 supervisor와 내장 agent를 관리하며 `configure → ready → 준비완료 대기 → start → finished`까지 수행한다. accelerated 모드는 프로세스 내부의 결정적 정책을 사용하고, realtime 모드는 별도 프로세스 6개를 실행한다. idle 정책도 ready는 전송한다. 준비완료 대기 제한은 기본 벽시계 10초이며 설정으로 바꿀 수 있다. 실패한 슬롯은 이유를 로그에 명시하고 제외한다. 전원이 실패하면 종료 코드 3으로 끝내고 `no_eligible` 결과를 저장한다. 엔진 초기화와 ready 단계에 소요된 시간도 sim_tick에는 포함되며, 최종 match_elapsed·reporting_elapsed와 구분한다.

`serve`는 경기를 자동으로 시작하지 않고 admin 명령으로 제어한다. `agent` 명령은 환경변수 `MAICON_SIM_MISSION_CODE`에서 코드를 읽으며, 비밀값을 CLI 인수로 반드시 전달하게 만들지 않는다. 실제 HTTP 참가팀은 1배속 실행에서만 허용한다. accelerated 모드와 외부 HTTP agent를 함께 사용하면 시작 시 거부한다.

`run`이 끝나면 `result.json`, `run_manifest.json`, `private/events.jsonl`, `public/slot/` 아래 관측 로그, `score_summary.csv`를 저장한다. 이미지는 `record_frames=true`일 때만 저장하고, 저장 위치와 공개·비공개 경계를 지킨다. `max_sim_ms`에 도달하면 실행이 멈춘 것으로 판단하여 종료 코드 3으로 끝내고 마지막 snapshot과 원인을 저장한다.

구현 정정 D006: `dataset`은 04 §5.4의 평가자 전용 초기 장면 내보내기다. 주행 성공을 의미하지 않으며 RGB·depth·마스크·annotation·inventory를 OUT/private에만 저장한다. 2D 및 영상 기록을 켠 오프라인 3D는 5,000틱마다 전체 코어·센서 체크포인트를 남긴다. `--checkpoint-tick`은 해당 파일의 해시·프로필·센서 capability를 검증한 뒤 중간 상태에서 재개한다. 영상 기록을 끈 3D에서는 RGB를 몰래 기록하지 않도록 전체 센서 체크포인트를 생략한다.

## 4 구현 마일스톤

의존 순서를 지킨다. 각 마일스톤을 작은 커밋으로 나누고, 기능이 통합되지 않은 별도 브랜치를 완성본으로 처리하지 않는다.

| 단계 | 구현 내용 | 선행 조건 | 합격 증거 |
| --- | --- | --- | --- |
| M0 계약 고정 | 프로젝트 골격, lock, 스키마, loader, CLI help, 산출물 공개 범위 | 00~10 문서 읽기 완료 | 전체 예제 검증, 설치 호환성 검증, doctor 결과 |
| M1 규칙 core | 시계, 상태, 이벤트 큐, 채점, reset, 비공개 이벤트 기록 | M0 | G0의 채점·시간 기준 테스트 |
| M2 HTTP와 SDK | 공식 모사 경로 전체, long-poll, 시뮬레이터 로봇 bridge, report worker | M1 | 응답 status·body, 동시 대기 6개, 마감, timeout 테스트 |
| M3 2D 운동 | 적분기, SAT, swept collision, raycast, 레이저, 거점 진입 감지 | M1 | 03의 D2 수치 테스트와 공통 채점 결과 |
| M4 2D 통합 | 의미 관측·LiDAR·odometry, 정책, viewer, run·replay·batch | M2+M3 | G1, 전원 idle일 때 각 20점, baseline 전체 수행 흐름 |
| M5 3D 기하 | Bullet scene, 자산 면, 좌표 변환, RGB·depth | M4 | 04의 투영·가림·DIRECT 테스트 |
| M6 3D 통합 | 드론, 팬틸트, render worker, template vision, noise·fog | M5 | G2, RGB 입력 baseline, 공통 core 결과 일치 |
| M7 인계 | 전체 시나리오, 프로세스 6개, benchmark, CI, wheel, Docker, 문서 | M6 | G3, 깨끗한 환경에서 설치, 검토 보고서 |
| H 실제 장비 | 최종 SDK 매핑, ROS 어댑터, 보정 | G3 + 장비 사용 허용·SDK 확보 | 09의 실제 장비 체크리스트를 별도로 기록 |

M4까지 마치면 2D 완성본을 독립적으로 전달할 수 있다. 3D는 M4의 core를 복제하지 않고 같은 패키지에 백엔드를 추가한다. M7까지가 요청된 2D·3D 구현의 완료 범위다. H를 수행하지 못했다는 이유로 가상환경에 필요한 구현을 미완성으로 남겨두지 않는다.

## 5 병렬 작업의 담당 경계

engine 담당은 core·rules·scoring·types를 관리한다. server 담당은 server·sdk와 API 테스트, 2D 담당은 planar·geometry2d·semantic·viewer, 3D 담당은 bullet·camera·assets, QA 담당은 fixture·기대 결과·replay·CI를 맡는다.

공통 자료형을 바꿀 때는 해당 담당자가 먼저 02의 계약과 스키마를 갱신하고 영향을 받는 담당자에게 알린다. 각 담당자가 API 상수·점수표·enum을 독립적으로 복사하지 않는다. 병합 전에 같은 예제를 두 백엔드에서 실행한다. geometry3d와 laser는 공통 core 담당자가 검토한다.

## 6 성능과 과부하

측정 결과에 CPU·GPU·RAM·OS·Python·lock hash·해상도·카메라 수·시드·시계 모드를 반드시 남긴다. 측정하지 않은 FPS를 보장값으로 제시하지 않는다.

필수 정확성 기준과 성능 목표를 구분한다.

- 헤드리스 2D의 시드 20개 배치 실행이 멈추지 않고 완료되며 결정성을 유지하는 것은 필수다.
- 2D 가속 모드의 10배속 이상은 참고 목표다. 성능을 모르는 CPU에 고정 합격 조건으로 적용하지 않는다.
- 3D의 로봇 6대 × 10Hz는 부하 측정 조건이며 CPU TinyRenderer에서의 달성을 보장하는 값이 아니다.
- realtime lag는 벽시계 기준으로 진행했어야 할 가상시간에서 실제 가상 진행시간을 뺀 값으로 측정한다. lag가 0.5초보다 크면 경고하고, 2초보다 큰 상태가 벽시계 기준 5초간 지속되면 해당 benchmark를 overloaded로 표시하여 성능 시험에서 불합격 처리한다.
- 과부하를 숨기기 위해 dt를 키우거나 시각을 건너뛰지 않는다. 일반 run은 문제를 기록하면서 계속 실행한다. `--abort-on-overload`를 지정했으면 종료 코드 3으로 끝내고 결과를 저장한다.
- 3D 부하를 줄이려면 카메라 수·주기·해상도를 명시적으로 바꾸고 새 run profile에 기록한다. 알리지 않고 화질이나 FPS를 낮추지 않는다.

worker queue 최대 길이, frame age, step 시간의 p50·p95·p99, HTTP 응답 지연, frame drop, real_time_factor, peak RSS를 보고한다. 실제 장비의 step 0.1초 제약과 데스크톱 renderer의 속도를 혼동하지 않는다.

## 7 구현자가 남길 증거

`IMPLEMENTATION_STATUS.md`에 각 M 단계와 G 합격 기준의 상태를 `not_started`, `in_progress`, `passed`, `blocked` 중 하나로 기록한다. 테스트 명령, 커밋, 산출물 경로, 아직 검증하지 못한 범위도 함께 적는다.

최종 README에는 설치, 2D 데모, 3D 헤드리스 데모, viewer 조작, agent 6개 실행, 시나리오 편집, API 예제, 공통 core 설계, 시뮬레이션 가정, 실제 장비에서 검증하지 않은 범위를 설명한다. 제삼자가 처음으로 실행에 성공하는 최소 절차는 명령 10개 이내로 구성한다.

CI는 push마다 unit·contract 테스트를 수행한다. integration·render 테스트는 Linux runner에서 실행하고, slow·실시간 120초 테스트는 nightly 또는 명시적인 job에서 수행한다. manual_gui·hardware 결과는 별도 증거로 관리한다. render 테스트를 건너뛰고 G2를 passed로 표시해서는 안 된다.

## 8 새 에이전트에게 전달할 시작 프롬프트

다음 문장을 그대로 새 세션에 전달할 수 있다. 상대경로는 계획 묶음을 복사한 위치에 맞춘다.

~~~text
이 저장소에 MAICON용 2D·3D 시뮬레이터를 구현해 주세요.
docs/implementation_plan/00_START_HERE.md부터 안내된 순서대로 모든 파일을
읽고, contracts와 examples를 구현의 입력 계약으로 사용하세요. 이전 대화나
원본 MAICON 저장소는 필요하지 않습니다. 대상 저장소의 기존 지침을 지키며,
공통 core → 2D 완성 → 3D 추가 순서로 구현하세요.
01에 기록된 자료의 사실과 SIM 가정을 구분하고, 미확정 항목은 명시된 기본값을
사용하여 가상환경을 완성하세요. 실제로 수행하지 않은 장비 검증이나 테스트를
성공했다고 보고하지 마세요. 07의 G0~G3과 08의 M0~M7을 충족할 때까지
구현을 계속하고, 각 단계의 구현 내용·테스트·결과를 기록하세요.
실제 장비 검증 H는 별도 조건입니다.
~~~

## 9 완료를 대신할 수 없는 결과물

정지 화면만 있는 프로그램, GUI만 있는 프로그램, 무작위 점수 표시, 정답 상태를 아는 bot만 있는 프로그램, API stub만 있는 프로그램, 2D core를 복사하고 3D라고 이름 붙인 구현은 요구사항을 충족하지 않는다. 3D는 이미지 생성부터 그 이미지를 이용하는 기준 인식 경로까지 연결해야 한다. 실제 6륜 동역학이나 모든 임무를 잘 수행하도록 학습된 agent를 이번 필수 범위에 추가하지 않는다.
