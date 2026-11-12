# MAICON Virtual Stadium

Oracle ARM64 자동 배포와 HTTPS 웹 화면 접속은 [배포 안내](deploy/oracle/README.md)를 참고하세요. 웹에서 2D 지도·3D 장면·실제 로봇 카메라와 경기 준비·시작·초기화를 사용할 수 있습니다.

공통 Python 코어를 사용하는 2D·3D 경기 시뮬레이터입니다. 2D는 의미 관측과 전략·통신을, 3D는 CPU PyBullet TinyRenderer의 RGB·가림·깊이와 영상 인식 경로를 시험합니다. ROS·GPU·외부 모델·LLM 키 없이 동봉 합성 자료로 실행할 수 있습니다.

기준 자료는 `jha68/MAICON` main의 `7c414445fcf0302620b2c89f16ce2064f91ca753`입니다. **이 구현의 SIM 기본값은 최종 대회 규정이나 실물 측정값이 아닙니다.** 출처와 가정은 [경기 규칙](docs/implementation_plan/docs/01_COMPETITION_RULES.md), [참고자료 발췌](docs/implementation_plan/docs/10_SOURCE_EXCERPTS.md)에 나뉘어 있습니다. 구현 중 보완한 계약은 [결정 기록](docs/DECISIONS.md), 실제 시험 상태는 [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md)를 확인하세요.

## 빠른 시작

Python 3.10과 uv를 사용합니다. `scripts/bootstrap.sh`는 잠금 파일로 모든 선택 의존성을 설치합니다. 다음 절차는 저장소 루트에서 실행합니다.

```bash
bash scripts/bootstrap.sh
.venv/bin/maicon-sim doctor --backend 3d --headless
.venv/bin/maicon-sim validate --scenario examples/scenario_smoke_six.yaml
.venv/bin/maicon-sim run --example smoke_six --backend 2d --headless --out artifacts/my-smoke
.venv/bin/maicon-sim run --example perception_gallery --backend 3d --headless --record-frames --out artifacts/my-gallery
.venv/bin/maicon-sim replay --run artifacts/my-smoke --backend 2d --verify --out artifacts/my-replay
.venv/bin/maicon-sim compare --left artifacts/my-smoke --right artifacts/my-replay --mode core
.venv/bin/maicon-sim batch --example smoke_six --backend 2d --seeds 0:20 --workers 2 --out artifacts/my-batch
.venv/bin/python -m pytest -m 'not slow and not performance and not manual_gui and not hardware' --junitxml=artifacts/tests.xml
```

각 출력에는 새 디렉터리를 지정하세요. `--example`은 wheel 안의 리소스를 사용하므로 설치 후 저장소 밖에서도 동작합니다.

코어·2D만 필요하면 `uv sync --frozen`으로 설치할 수 있습니다. `bullet`, `vision`, `viewer`, `dev`는 선택 extra이며 코어는 PyBullet·pygame·ROS를 import하지 않습니다. 기본 프로필의 HP·탄약·시계와 임무 채점은 두 백엔드에서 동일합니다.

## 브라우저에서 경기 운영

Oracle 배포의 기본 주소는 `https://maicon.junununseo.com`입니다. DNS A 레코드를 VM 공인 IP로 지정하고 OCI 인바운드 TCP 80·443을 허용해야 합니다. Caddy가 HTTPS 인증서를 자동 발급·갱신합니다. 아이디 없이 비밀번호만 입력합니다. 최소10자이며 기존 비밀번호는 유지됩니다. 웹 화면과 API는 비밀번호 변경 기능을 제공하지 않습니다. 최초 배포 시 생성되는10자 비밀번호는 VM에서 `cat ~/maicon-data/web.password`로 확인합니다. 비밀번호를 채팅이나 저장소에 올리지 마세요.

정책 선택 → 준비 시작 → 여섯 팀 준비 완료 → 경기 시작 순서입니다. 실제 참가팀 프로세스 여섯 개를 실행하며 pose를 직접 움직이지 않습니다. 일시정지·재개·종료 후 점수 JSON 확인, 다음 경기 초기화를 지원합니다. 세팅/준비 중에는 제한 시간이 줄어들지 않습니다. 준비가 실패하면 초기화로 취소할 수 있습니다. 기본 순찰 데모와 실제 LLM을 쓰지 않는 baseline을 구분하세요.

2D 지도와 브라우저 WebGL 3D 장면은 같은 core snapshot을 그립니다. 오른쪽 카메라는 실제 PyBullet RGB이며 화면 갱신은 최대 2Hz입니다. 서버 센서 프로필·규칙은 바꾸지 않습니다. 브라우저 3D는 wheel 동역학이나 서버 렌더 영상이 아닙니다. 모든 화면은 인증된 운영자 정답 시점이며 참가팀 공개 API에 정답 endpoint를 추가하지 않습니다.

자세한 보안·기록 범위와 시험은 [웹 화면 계약](docs/WEB_DASHBOARD.md)에 있습니다.

## 화면과 실제 프로세스 실행

GUI 디스플레이가 있는 환경에서는 다음과 같이 실행합니다.

```bash
.venv/bin/maicon-sim run --example smoke_six --backend 2d --clock realtime --viewer --out artifacts/my-viewer
.venv/bin/maicon-sim run --example perception_gallery --backend 3d --clock realtime --viewer --out artifacts/my-3d-viewer
```

숫자 1~6으로 로봇을 선택하고, `T`는 truth/observed 전환, `S`는 센서, `H`는 궤적, `P/R`은 경기 pause/resume, `Space/N`은 디버깅 정지/한 틱 진행입니다. `+/-` 배속은 가속 모드에서만 허용됩니다. 화살표는 보관된 관찰 스냅숏을 탐색하고 `Esc`는 관찰 창을 닫습니다. 경기 pause와 디버깅 정지는 다른 기능입니다. 관찰자에게 보이는 정답 HUD는 참가팀 영상에 합성하지 않습니다.

`run --clock realtime`은 실제 로컬 HTTP 서버와 **여섯 별도 참가팀 프로세스**를 실행합니다. 벽시계 1배속이며 300초 경기와 최대 30초 보고 창이 실제로 걸립니다. `accelerated`는 공개 DTO를 받는 in-process 정책과 결정적 입력을 사용합니다. 외부 HTTP와 가속 시계의 조합은 거절합니다. 과부하에서도 틱이나 시간을 건너뛰지 않고 지연과 실제 배율을 기록합니다.

서버를 수동으로 운영하려면:

```bash
.venv/bin/maicon-sim serve --example smoke_six --backend 2d --public-port 8000 --admin-port 8001 --out artifacts/my-server
# 다른 터미널에서 자기 코드만 환경변수로 설정한 뒤 실행합니다.
MAICON_SIM_MISSION_CODE=SIMB0001 .venv/bin/maicon-sim agent --slot B-1 --policy baseline --server http://127.0.0.1:8000
```

샘플 `SIMB0001` 등은 실제 자격 증명이 아닙니다. 관리자 토큰은 화면에 출력하지 않고 `--out/private/admin.token`에 0600 권한으로 저장합니다. 관리자는 별도 loopback 포트에서 Bearer 인증 후 `ready-phase`, `start`, `pause`, `resume`, `finish`, `fault`, `snapshot`, `result`, `shutdown`을 사용합니다. `serve`는 자동으로 경기를 시작하지 않습니다.

공식 모사 API는 `/api/report/{me,ready,order,target,drone,interpretation,detection,situation}`이며 M2/M4/M5 자가 신고 경로는 없습니다. `/api/rehearsal`은 독립 보고 세션을 사용하고 drone 경로는 제공하지 않습니다. `/sim/session`, `/sim/map-prior`, `/sim/calibration`, `/sim/robot/v1/*`는 **시뮬레이터 전용**이며 실제 대회 API로 주장하지 않습니다. 예시:

```bash
curl --get --data-urlencode 'mission_code=SIMB0001' http://127.0.0.1:8000/api/report/me
curl -H 'Content-Type: application/json' -d '{"mission_code":"SIMB0001","target":"RED_RADAR","search_sectors":["R-S1","CM"],"base":"RED_SUPPLY_DEPOT"}' http://127.0.0.1:8000/api/report/interpretation
```

## 시나리오·센서·정책

`examples/`의 YAML 참조는 각 파일의 부모 디렉터리를 기준으로 해석합니다. 스키마, 교차 참조, 박스 면·시설·진영, 초기 충돌·섹터 포함, 센서 중복값과 주기를 실행 전에 검증합니다. 설정 오류는 경로와 원인을 표시하고 종료 코드 2로 끝납니다. 새 배치를 만들려면:

```bash
.venv/bin/maicon-sim generate --template examples/scenario_smoke_six.yaml --seed 42 --count 5 --out artifacts/my-layouts
.venv/bin/maicon-sim assets build --manifest examples/assets_synthetic.yaml --out artifacts/my-assets
.venv/bin/maicon-sim benchmark --example smoke_six --backend 3d --camera-count 1 --duration-s 300 --out artifacts/my-benchmark
.venv/bin/maicon-sim dataset --example perception_gallery --out artifacts/my-private-dataset
```

`idle`은 ready만 보내며 미션 보고·사격을 하지 않습니다. 따라서 동봉 smoke의 기대값은 각 20점입니다. `baseline`은 공개 명목 지도와 자기 odom·LiDAR·관측을 이용하는 최소 정책입니다. A*, 객체 증거 집계, 전체 M1/M3 보고, 실제 M5 목표 수신, 낮은 신뢰도의 M6 fallback을 연결하며 고득점을 보장하지 않습니다. `patrol`, `blocker`, `capture_runner`도 pose를 직접 변경하지 않습니다.

2D 의미 관측은 합성 인식 이후 로직 시험입니다. 3D는 기본적으로 semantic endpoint를 닫고 실제 RGB에 contour/원근 보정/template 검출기를 적용합니다. 합성 여섯 도형 gallery의 성공은 실물 인쇄물 일반화 성능이 아닙니다. 기본 `FixtureLLM`은 통합용 stub이며 실제 LLM 성능이나 대회 LLM 의무 준수 증거가 아닙니다. 별도 비동기 `LLMPort`를 주입할 수 있고 오류·시간 초과는 제어 heartbeat를 막지 않습니다.

사용 권한이 있는 실제 이미지는 `generator: import`, 상대 `path`, SHA256, source/license/split 메타데이터로 등록할 수 있습니다. 해시가 틀리면 실패합니다. 공식 이미지나 모델은 자동으로 내려받지 않습니다. 카메라·레이저·수광부·LiDAR, FOV, 노이즈, fog는 센서 프로필에서 바꾸며 새 프로필과 회귀 결과를 함께 보존합니다.

`generate`의 기본 `--layout-mode competition`은 BLUE/RED 지정표적을 시설 코드로 짝지어 위치·표적면·수광부를 반사 대칭으로 배치합니다. 비시설 박스와 M3 객체 종류까지 동일하게 만들지는 않습니다. 비대칭 스트레스 시험은 `--layout-mode stress`로 명시하며 생성 YAML에도 모드를 기록합니다. 기존 수동 시나리오는 그대로 사용합니다.

참가팀 컨트롤러는 필수 센서 프레임이 진행하지 않으면 주행과 새 조준 명령을 중단합니다. 기본 만료시간은 odom/LiDAR 0.5초, baseline 영상 1초, 2Hz 상태·경기 신호 1.5초입니다. 같은 캐시 프레임의 재수신은 시간을 갱신하지 않습니다. 센서 복구 뒤 새 정책 판단부터 동작하며, 센서 중단 중에도 M6 보고는 계속 처리합니다. 이 시간은 컨트롤러의 `sensor_timeout_s`(기본0.5초)를 기준으로 설정합니다.

baseline 공격·M3 시간 정합/면 추적·M6 시각 증거·실제 LLM 선택·카메라 보정 사용법은 [후속 기능](docs/FOLLOWUP_FEATURES.md)에, 설계 배경은 [개선 설계안](docs/COMPETITION_IMPROVEMENT_IDEAS.md)에 정리했습니다.

## 기록과 재현

`--out`은 정확한 RUN_ROOT입니다.

- `result.json`, `score_summary.csv`: 종료 점수와 핵심 지표
- `run_manifest.json`: 규칙·시나리오·자산·lock 해시, seed, 모드·가정·환경·파일 해시
- `private/events.jsonl`: 입력/파생/측정 사건을 구분한 평가자 기록
- `private/assets/`: 생성 이미지와 검증된 resolved manifest
- `public/<slot>/`: 자기 관측과 참가팀 로그, 선택적 RGB 파일
- `summary/metrics.json`: 실제 처리 시간·배율·누락 등 성능 기록

재생은 기록된 **입력만** 같은 처리 틱과 순서로 다시 주입합니다. 파생 피격·점수를 재주입하지 않습니다. 파일 누락·변조·잘못된 순서는 검증 실패입니다. 관측 재생 `replay --mode observations`는 open-loop이며 RGB가 필요하면 실제 기록 파일이 있어야 합니다. 실시간 OS 스케줄링이나 다른 렌더러의 픽셀까지 seed만으로 재현된다고 주장하지 않습니다.

`--record-frames`는 실제 공개 영상과 캡처·수신 시각을 저장합니다. 정답 segmentation/depth와 상대 HP·탄약·M3는 공개 SDK 입력에 넣지 않습니다. 같은 OS 계정의 악의적 파일 접근까지 막는 보안 제품은 아닙니다.

오프라인 센서 체크포인트는 5,000틱마다 저장하며 `replay --checkpoint-tick 5000`으로 중간 상태부터 검증할 수 있습니다. 3D에서 영상 기록을 끈 경우에는 RGB 캐시를 몰래 저장하지 않으며 전체 센서 체크포인트도 생략합니다. 실시간 프로세스 자체의 스냅숏 복원은 지원 범위가 아닙니다.

`dataset`은 초기 장면을 평가자 전용으로 내보내는 별도 명령입니다. `private/` 아래 RGB·미터 깊이·invalid mask·segmentation·면별 가시 마스크·bbox·가시 비율·전체 inventory와 해시를 저장합니다. 경기 주행이나 자율 정책 성공을 의미하지 않습니다.

종료 코드는 성공 0, 설정 2, 실행·의존성 3, 검증 실패 4, 사용자 중단 130입니다. 필수 시험은 skip으로 성공 처리하지 않습니다. 실제 시험 결과 JSON과 JUnit, 기준별 누락 항목은 `artifacts/`에 기록하며 최종 목록은 상태 문서를 따릅니다.

## 범위와 현장 연결

운동은 공통 10ms 평면 운동학·보수적 swept 충돌이 결정합니다. PyBullet은 확정된 pose를 받아 영상과 비공개 깊이를 생성하며 바퀴 동역학으로 위치를 다시 움직이지 않습니다. 6륜 마찰·슬립·전복, 실물 레이저 광학, 실제 연기와 LiDAR 물리를 검증한 디지털 트윈은 아닙니다. Fog는 명시된 깊이/체적 기반 RGB 대비 모델입니다.

최종 ROS 메시지·서비스·QoS·LiDAR 규약, camera_info, 센서 영점·부호·지연, 출발·pause·M3/M5/M6 최종 규칙은 실제 장비와 최종 SDK로 확인해야 합니다. Fake ROS는 publish/subscribe·latched 상태·서비스 timeout 경계를 시험하며 실제 타입을 지어내지 않습니다. H-01~H-07은 [현장 절차](docs/implementation_plan/docs/09_FIELD_ADAPTER_AND_QUESTIONS.md)에 따라 별도로 기록합니다.
