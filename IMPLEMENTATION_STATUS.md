# 구현·시험 상태

기록일: 2026-11-07. 공통 코어 → 2D 통합 → 같은 코어에 3D 연결 → 인계 순서로 **M0~M7 구현을 완료**했다. 실제 실행 결과로 G0~G3를 통과했다. 실물 장비가 필요한 H는 별도의 `not_run` 상태다.

전체 시험 **355 passed / 0 failed / 0 skipped**를 실행했고, 마지막 명령 상태·pose 정밀도·비교 진단 보완 후 관련 **176 passed / 0 failed / 0 skipped**를 재검증했다. 두 실행에는 겹치는 시험이 있으므로 서로 다른 시험 531개로 합산하지 않는다. 기본 인수 기준 152개와 2D·3D 보충 기준 34개가 모두 실행 시험에 연결되어 통과했다.

## 구현 범위와 단계별 결과

| 단계 | 상태 | 구현과 실행 근거 |
|---|---|---|
| M0 계약·설치 | passed | Python 3.10, uv.lock, 엄격한 스키마·의미 검증, 패키지 리소스, doctor, CLI. 문서를 00의 순서로 읽고 11의 검토 결과·한계를 반영했다. |
| M1 공통 코어 | passed | 단일 writer, 10ms 정수 시계, 우선순위·FIFO 입력 큐, HP·탄약·시설·M1~M6·동결·동점·보고 종료·reset. 수기 golden과 경계 시험 통과. |
| M2 HTTP·SDK | passed | 공개/관리 포트 분리, rehearsal 격리, timeout·취소·지연 commit 복구, 토큰 로그 마스킹, fake ROS 매핑. 실제 TCP 120초 대기·100회 연결 취소·여섯 프로세스 재시작 시험 통과. |
| M3 2D 운동 | passed | 공통 평면 운동학, swept SAT·동시 충돌, 공통 3D 광선 기하, 수광부별 연속 조사·레이저. 199/200틱 경계와 실제 명령 주행·점령 시험 통과. |
| M4 2D 통합 | passed | 의미 관측·odom·IMU·LiDAR, 공개 정보만 쓰는 정책, pygame viewer, run/replay/compare/batch, 5,000틱 체크포인트. 300초+30초 경기·30 seed·실제 여섯 참가팀 프로세스 검증. |
| M5 3D 기하 | passed | PyBullet DIRECT/TinyRenderer, 확정 pose 동기화, 실제 RGB·깊이·segmentation, 면별 UV, 가림·FOV·수광부 기하. 100Hz pose 동등성과 실제 렌더 시험 통과. |
| M6 3D 통합 | passed | 프로세스로 격리한 렌더 worker, bounded/latest 큐, 팬틸트·드론·노이즈·fog, 영상만 받는 template 검출기. 합성 여섯 클래스·RGB baseline·reset·지연·drop·정보 경계 검증. |
| M7 인계 | passed | wheel·Docker·CI·README, 비공개 데이터셋 내보내기, 계약 추적, 300초 성능 측정, 실제 X11 GUI. 저장소 밖 wheel과 Ubuntu 22.04 비루트·네트워크 차단 실행 통과. |
| H 실물 | not_run | 최종 SDK·실제 로봇·센서·인쇄물 미제공. [별도 검증 기록](docs/HARDWARE_VALIDATION.md)의 H-01~H-07에 필요한 장비와 절차를 남겼다. |

공통 코어가 두 백엔드의 운동·피격·채점을 결정한다. Bullet은 확정 pose에서 영상을 생성하며 별도의 동역학이나 채점을 실행하지 않는다. 코어·2D만 설치하면 PyBullet·pygame·OpenCV·ROS 없이 실행된다.

## 시험 명령과 최종 증거

전체 실행은 GUI와 느린 시험을 포함했다. PERF-001은 명시한 30 seed 산출물에서 seed·해시·300초+30초·각 20점·성능 지표를 검증해 사용했다. 필수 시험을 skip으로 통과 처리하지 않았다.

```bash
DISPLAY=:99 SDL_AUDIODRIVER=dummy \
MAICON_BATCH_EVIDENCE=/workspace/MAICON_Virtual_Stadium/artifacts/batch30 \
MAICON_RENDER_BENCHMARK_SECONDS=300 \
MAICON_TEST_RESULTS=artifacts/final-test-results.json \
.venv/bin/python -m pytest -q --junitxml=artifacts/final-tests.xml
```

결과: 355 passed, 1008.04초. [JUnit](artifacts/final-tests.xml), [기준별 결과 JSON](artifacts/final-test-results.json).

최종 소스 보완 후 해당 범위 재검증:

```bash
DISPLAY=:99 SDL_AUDIODRIVER=dummy \
MAICON_TEST_RESULTS=artifacts/final-postfix-results.json \
.venv/bin/python -m pytest \
tests/unit/test_rules_time.py tests/unit/test_sensors.py tests/render \
tests/integration/test_match_command.py tests/integration/test_evaluation.py \
tests/integration/test_http_performance.py tests/e2e/test_gui.py \
-q --junitxml=artifacts/final-postfix.xml
```

결과: 176 passed, 146.51초. [JUnit](artifacts/final-postfix.xml), [결과 JSON](artifacts/final-postfix-results.json). 마지막 wheel은 이 소스로 다시 빌드하고 별도 설치 환경에서 실행했다.

| Gate | 상태 | 누적 필수 기준 수 | 미해결 기준 |
|---|---|---:|---|
| G0 | passed | 83 | 없음 |
| G1 | passed | 121 | 없음 |
| G2 | passed | 159 | 없음 |
| G3 | passed | 186 | 없음 |

기준 수는 누적이며 서로 더하지 않는다. `scripts/update_acceptance_manifest.py`로 기본 152개·보충 34개의 시험 매핑과 존재 여부를 확인했다. 세부 결과는 위 JSON에 남겼다.

별도 설치·운영 검증:

- 코어 전용 새 환경: CI 선택 시험 251 passed, 6 deselected. 선택되지 않은 시험을 passed로 세지 않았다. PyBullet·pygame·OpenCV·rclpy 미설치 상태를 확인했다. [증거](artifacts/core-only-ci.xml)
- 최종 wheel: `/tmp`에서 패키지 내 예제·lock으로 실제 2D 경기를 실행해 여섯 팀 각 20점을 확인했다. 이 설치 시험은 명시적인 1초 경기+0.3초 보고 프로필이다. [검증 기록](artifacts/final-wheel-check.json), [wheel](artifacts/dist/maicon_sim-0.1.0-py3-none-any.whl)
- Ubuntu 22.04 / Python 3.10.12 Docker: UID 1000, `--network none`, 실제 DIRECT RGB와 경기 실행 통과. 전체 시험에도 포함된다. [시험 기록](artifacts/packaging-ubuntu.xml), [빌드 기록](artifacts/docker-build-current.log)
- 실제 X11: pygame 조작·센서/RGB/드론 패널, Bullet GUI 회전·확대·종료 통과. [시험 기록](artifacts/gui-x11.xml), [2D 화면](artifacts/evidence/viewer_x11.png), [RGB 패널](artifacts/evidence/viewer_rgb_x11.png), [3D 화면](artifacts/evidence/bullet_gui.png)
- 평가자 데이터셋: RGB·깊이·invalid mask·segmentation·면별 mask/bbox/가시 비율·전체 inventory를 `private/`에만 내보냈다. [manifest](artifacts/dataset-gallery/private/dataset_manifest.json)

## 실제 경기·정책 실행

| 실행 | 길이·조건 | 관찰 결과 | 증거 |
|---|---|---|---|
| 2D smoke | 기본 300초+30초, idle | 여섯 팀 각 20점 | [결과](artifacts/smoke2d/result.json) |
| 3D smoke | 기본 300초+30초, idle | 여섯 팀 각 20점, 공통 코어 유지 | [결과](artifacts/smoke3d/result.json) |
| 코어 재생 | 기록된 입력만 원래 틱에 재주입 | 비교 equal=true | [검증](artifacts/replay2d/summary/replay_verification.json) |
| 실제 여섯 프로세스 | 300초+30초, 벽시계 1배속 | 각 20점, RTF 0.9997, 최대 지연 0.306초, 건너뛴 틱·재시작·실패 0 | [지표](artifacts/six-process-realtime/summary/metrics.json) |
| 30 seed batch | seed 0~29, 각각 300초+30초 | 모두 완료, 평균·중앙·최소 20점. 0~19 선택 집합과 20~29 holdout 분리 | [요약](artifacts/batch30/batch_summary.json) |
| 2D baseline | 기본 300초+30초 | B-1 52점: M1 10, M3 7, M4 15, M6 15, bonus 5. B-2/3 20점, RED 각 15점 | [결과](artifacts/baseline2d/result.json) |
| 실제 RGB baseline | gallery, 명시적인 10초+3초 | B-1 45점, M3 0점. TANK를 실제 영상에서 추적했으나 명목 시작 pose와 fixture pose 차이로 섹터 B-S1에 보고 | [결과](artifacts/baseline3d-rgb/result.json) |

30 seed는 idle 회귀 안정성 증거이며 학습 정책의 일반화 검증이 아니다. 2D baseline에는 중복 집계 오차가 있다. RGB baseline은 영상→검출→추적→보고를 실행했지만 위치 추정이나 M3 성공을 입증하지 못했다. seed 42~44 생성 배치에서도 명시적인 짧은 baseline 경기로 설정 생성·실행과 M1/M6 경로를 확인했다.

## 성능과 측정 한계

호스트: Linux x86_64, Python 3.10.22, AMD EPYC 9V74, 할당 논리 CPU 5개, GPU 불필요. doctor는 NumPy 2.2.6, Pydantic 2.14.3, FastAPI 0.162.0, Pillow 12.3.0, PyBullet 3.2.7, OpenCV headless 4.14.0.94 조합을 통과했다. [doctor](artifacts/final-doctor.json)

| 3D 프로필 | 시뮬레이션 시간 | 실제 처리 시간 | RTF | 추가 관찰 |
|---|---:|---:|---:|---|
| 640×480 10Hz 카메라 1개+드론 | 300초 | 37.08초 | 8.092 | capture 3302회, uncached render 2회 |
| 같은 카메라 6개+드론 | 300초 | 75.74초 | 3.961 | capture 18307회, uncached render 7회 |
| 6개+2Hz 영상 추론+기록 | 300초 | 235.61초 | 1.273 | 추론 3600회, 기록 큐 상한 4, 기록 drop 2341 |

표는 **정지한 idle 장면의 동일 장면 캐시를 사용하는 오프라인 lockstep 측정**이다. 주행 중 여섯 카메라의 실시간 성능을 보장하지 않는다. cache hit와 실제 render 횟수를 모두 저장했다. 세 번째 프로필은 동시 부하가 있던 이전 실행에서 RTF 0.908도 관찰되어 고정 실시간 보장으로 해석하지 않는다. [성능 산출물](artifacts/performance)에 최종 지표가 있다. 일반 run의 오프라인 영상 기록은 역압으로 보존하며 이 bounded-drop 부하 시험의 기록 정책과 구분한다.

PERF-004 실제 HTTP 부하: 일반 요청 82개 p50 15.66ms, p95 60.95ms, p99 63.19ms, 제어 요청 최대 간격 135.00ms, timeout 0, 입력 큐 최고 18. 공개 전 long-poll 12개는 별도 계측했다. [지표](artifacts/performance/http_concurrency.json)

PERF-005는 실제 10Hz 입력 50프레임에 대해 2Hz 추론 worker가 11개 처리·39개 교체, latest 큐 상한 1과 마지막 tick 490 보존을 확인했다. PERF-006은 동일 engine/runtime/gateway와 실제 렌더 프로세스로 6회 반복했다. 이는 명시적인 200ms 경기+100ms 보고 프로필이며 기본 길이 경기 여섯 회로 주장하지 않는다. body/registry 각 189, store 31, worker 수·PID 유지, waiter·미완료 요청 0이었다. [원시 RSS·반복 지표](artifacts/performance/repeated6.json)

RSS는 warm-up 2회 뒤 두 회씩의 최소/최대 envelope가 지속 증가하는지 검사한다. 렌더 RSS 일시 진폭 7064KiB를 누수로 판정했던 초기 진단도 보존하고 계획의 지속 증가 조건에 맞춰 시험을 정정했다. 4096KiB 증가 한계는 넓히지 않았다. 최종 main envelope 증가량 min 0 / max -1008KiB, render min -6456 / max -896KiB였다.

## 계약·문서 보완과 장애 기록

계획은 `docs/implementation_plan/`에 보관하고 계약·예제를 패키지 리소스에도 포함했다. 기존 manifest는 `validation/MANIFEST.original.json`으로 보존했다. 현재 manifest에는 원본 ZIP SHA256과 수정된 계획 파일 해시를 남겼다. 공식 자료의 사실과 `SIM-*` 기본 가정을 구분했다.

[결정 기록](docs/DECISIONS.md)에 이유·수정 계약·회귀 시험을 함께 남겼다.

- D001: 산출물 경로 모순을 `--out = RUN_ROOT`로 통일.
- D002: fog 모형·체적 누락을 문서·스키마·시험에 보완.
- D003: 동결 전 심판 정정을 SIM 전용 사건·엄격한 스키마·시험으로 명시.
- D004: Bullet GIL 점유의 watchdog 영향을 해결하도록 렌더러를 별도 프로세스로 격리.
- D005: 관리자 test_mode 설정 경로·보충 스키마·실제 HTTP 시험 추가.
- D006: 비공개 dataset CLI, 영상 기록·재생·체크포인트·출처 계약 보완.
- D007: Docker VFS 계층 복제의 디스크 고갈 원인 분석과 COPY/RUN 계층 축소.

최종 검증에서 OwnMatch.cmd의 resume 상태·체크포인트 호환, 비교 오류의 원래 event_seq, 100Hz core/Bullet pose 동등성을 보완했다. Bullet 보조 quaternion 함수의 정밀도 손실은 float64 Hamilton 곱으로 해결했고 1e-9 허용치를 넓히지 않았다. PERF-004의 공식 근거 커밋과 구현 출처도 분리했다.

중간 전체 시험은 63GB 디스크의 Docker VFS 복제 공간 부족으로 한 번 중단됐다. [중단 JUnit](artifacts/enospc-interrupted-tests.xml)은 통과 증거가 아니다. 이 작업의 이미지·확인된 해당 빌드 캐시만 정리하고 Dockerfile을 줄인 뒤 전체 시험을 다시 실행해 위 355개 통과 결과를 얻었다.

## 남은 항목과 인계

장비 없이 가능한 M0~M7 구현과 필수 소프트웨어 합격 기준에 미해결 항목은 없다. 다음은 적용 범위와 별도 검증 과제다.

- H-01~H-07 최종 SDK·실물 센서/좌표/지연/주행/레이저·운영 규칙 확인은 모두 `not_run`. [필요 장비·절차](docs/HARDWARE_VALIDATION.md)
- FixtureLLM은 통합용 stub이다. 외부 실제 LLM 호출·품질·대회 준수 여부는 미검증이다.
- 합성 여섯 클래스 렌더 영상 시험은 공식 인쇄물·조명·연기에서의 일반화 검증이 아니다. baseline의 집계·자기 위치 추정 성능 개선이 가능하다.
- 6륜 마찰·슬립·전복, 실제 광학·연기·LiDAR 물리는 평면 운동학+영상 모형의 범위 밖이다. fog는 문서화한 RGB 대비 근사다.
- 같은 OS 계정의 악의적 파일 접근을 막는 보안 제품은 아니다. 공개 DTO/SDK와 평가자 산출물의 정보 경계를 시험했다.

실행 방법은 [README](README.md)에 있다. 코드는 로컬 작업 트리에 있으며 아직 구현 커밋·원격 push는 없다. `7c414445fcf0302620b2c89f16ce2064f91ca753`은 공식 참고 저장소 커밋으로 이 구현의 커밋이 아니다. [release manifest](artifacts/release_manifest.json)에 구현 트리·lock·최종 wheel·시험 보고서 해시를 남겼다.

환경 재사용용 install_script와 start_skill 초안은 클라우드 설정에 저장했다. 아직 Publish하지 않았고 새 작업의 자동 복원은 미검증이다. 재사용하려면 환경 설정에서 초안을 검토하고 저장·Publish하면 된다.

## 2026-11-08 Oracle 배포 준비

Ubuntu 24.04 ARM64 VM(2코어, 메모리 약12GB, 루트48GB)에 사용자 본인이 Cloud Shell에서 SSH 접속하고 사양을 확인했다. 아직 이 VM에 시뮬레이터를 설치하거나 ARM 성능을 측정하지 않았다.

`.github/workflows/oracle-deploy.yml`과 `deploy/oracle/deploy.sh`를 추가했다. main의 기존 CI 성공 뒤 ARM64 이미지 빌드·GHCR push·SSH pull·digest 배포·상태 확인·이전 컨테이너 복구를 수행한다. 개인키와 고정 host key는 GitHub Secrets를 사용한다. ARM에서 PyBullet 소스 빌드가 가능하도록 Dockerfile에 build-essential을 추가했다. 이 변경의 ARM 이미지 빌드·실제 GitHub/VM 배포는 별도 실행 전이다.

배포 shell의 성공·pull 실패·컨테이너 실행 실패·상태 확인 실패·rename 실패와 mutable tag 거절을 실제 subprocess+가짜 Docker 상태로 검증했다. 6개 통과: `artifacts/oracle-deploy.xml`. 두 workflow는 체크섬을 검증한 actionlint 1.7.7로 검사해 통과했다(shellcheck 제외). 이는 실제 Oracle 배포 성공 증거가 아니다. 기존 355개 전체 시험/176개 재검증 결과는 앞 날짜의 소프트웨어 검증 기록이다.

API는 VM loopback으로 유지한다. 공인 IP에서 브라우저 경기 화면을 제공하는 웹 viewer는 아직 없으며 후속 구현이 필요하다. 경기 중 main 배포는 컨테이너를 재시작하므로 세팅 시간에 배포하도록 운영한다. 상세 최초 설정은 `deploy/oracle/README.md`를 따른다.
