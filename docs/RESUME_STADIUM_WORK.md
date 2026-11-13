# 새 실행 환경 인수인계

## 최신 운영 반영: UGV 반복 정지·M5 사진 (2026-11-13)

- 실제 공개 앱 revision은 `e7a8081238e3020263e945bbf0ef8aff7d58cfe2`, `X-Maicon-Compute: codex-cloud`, `reference_stadium`이다. 이후 bootstrap/문서 커밋은 앱 동작을 바꾸지 않는다. main은 변경하지 않았다.
- 카메라 만료와 주행 센서 만료를 분리하고 거점 센서 계산을 줄였다. 최신 overhead 드론/스레드 제한 코드는 유지했다. 4코어·6개 baseline 로컬 표본에서 출발구역 이탈은 실제 6.01~7.08초이며, 중앙 교행/경로 정체는 남는다.
- PDF 15쪽 원본 3장으로 양 진영 M5 거점 6곳의 벽면 표지판을 구현했다. 전체 이미지 16종, 2D/3D/UGV RGB에 반영되며 기존 진입 센서·채점 기하는 유지한다. 공개 이미지의 디코딩된 픽셀도 원본과 일치한다.
- 로컬 회귀 598 passed, 5 skipped, 12 deselected. 실제 여섯 참가팀 브라우저 조작·별도 baseline 드론 검사 통과. 공개 주소에서는 비밀번호 로그인·16개 이미지·WebGL·6대 RGB를 읽기 전용으로 확인했다. 운영 경기 조작은 보내지 않았다.
- CI의 1초 간격 화면 샘플링이 짧은 드론 판단을 놓치는 문제를 실제 실패 로그로 확인했다. 해당 경기의 참가팀 공개 transcript와 캡처 시각도 검증하도록 검사기를 수정했다.
- 최종 앱 CI `43379039507` 성공: core/contracts, integration/render/wheel, 실제 브라우저·6개 baseline 드론 검증을 통과했다.
- gateway 전환 Actions: `43379250566` 성공. 당시 운영 경기가 finished인 것을 확인했고, 이전 경기 결과·상태는 `work/deploy/preserved/`와 새 실행의 `private/previous-session/`에 보관했다.

### 현재 실행과 인증 파일

기존 운영 비밀번호는 그대로다. 기존 작업자가 새 작업자의 요청을 가져가지 않도록 relay 세션을 교체했다. 세션은 현재 `deploy/codex/session.json`이 기준이며 새 암호화 bootstrap은 같은 저장소 `deploy/codex/bootstrap/`에 있다.

- 현재 서버 PID 기록: `work/deploy/server-pid`; relay PID 기록: `work/deploy/worker-pid`. PID를 쓰기 전에 실제 명령이 일치하는지 확인한다.
- 현재 서버 실행 기록: `work/deploy/previous-private/current-run.json`. 이름의 previous는 비밀번호를 보존한 디렉터리이며 이 서버가 현재 공개 앱이다.
- **새 relay 자격 증명**: `work/deploy/private/credentials.json`, 비밀번호: `work/deploy/private/web.password`, 개인키: `work/deploy/private-key.pem`. 값을 출력하거나 Git에 넣지 않는다.
- 환경 변수 `MAICON_RELAY_CREDENTIALS_JSON`에는 이전 세션 값이 남아 있을 수 있다. 현재 session_id와 다르면 기존 환경 값으로 worker를 시작하지 않는다. 먼저 위 새 private 파일을 재사용하고, 없으면 보존된 개인키로 현재 bootstrap을 해독한다. 개인키도 없을 때만 기존 Actions 경로로 새 세션 bootstrap을 준비한다. 운영 중 경기는 강제로 종료하지 않는다.

---

사용자가 환경 설정을 게시했으나 이전 실행 인스턴스에는 반영되지 않아, 현재 구현을 브랜치에 보존하고 새 환경에서 이어가기로 했다. 아래는 사용자 요청과 확인된 상태다. 미완료 항목을 완료로 취급하지 않는다.

## 사용자 목표와 제약

1. 첨부 평면도와 `prestudy(1)_2026MAICON.pdf`의 표적·객체·비인식 장애물·수광부를 경기장에 구현한다.
2. `jha68/MAICON` 학습자료를 기준으로 실제 대회에 가깝게 개선한다. **M1 외부 LLM 연결은 보류하고 mock만 쓴다. 모바일 대응은 필요 없다.**
3. `maicon.junununseo.com`에서 새 맵이 안 보이는 원인을 확인하고 반영한다. 사용자가 이미 구현·배포 진행을 요청했다. 같은 네트워크 허용/배포 승인을 반복해서 묻지 않는다.
4. 기존 비밀번호와 비밀번호만 입력하는 로그인을 유지한다. 삭제된 비밀번호 변경·로그아웃 기능을 복구하지 않는다. 진행 중인 운영 경기를 강제로 초기화하지 않는다.

## 저장소와 브랜치

- 저장소: `https://github.com/jha68/MAICON_Virtual_Stadium.git`
- 작업 경로: `/workspace/MAICON_Virtual_Stadium`
- 이어갈 브랜치: **`feat/reference-arena-assets`**
- 맵/자산: `a683434`. main `299c9b3` 통합: `3ff6129`. 인식/제어/판정/콘솔: `e7fadff`.
- 기존 Codex 도메인 브랜치 `deploy/codex-cloud-20261112`의 `a7ce7cd`까지 `7ed656b`로 합쳤다. 다시 병합하거나 예전 코드를 덮어쓸 필요 없다. 이후 수정은 이 feature 브랜치의 최신 HEAD에 있다.
- 로컬 변경을 먼저 확인하고 보존한다. main으로 강제 reset하거나 별도 worktree를 만들지 않는다. main을 운영 배포한 것으로 가정하지 않는다.

## 구현 상태

[REFERENCE_STADIUM.md](REFERENCE_STADIUM.md), [STADIUM_FIDELITY.md](STADIUM_FIDELITY.md)를 먼저 읽는다. 새 맵은 `reference_stadium`, 박스 20개, 시설 수광부 6개, PDF 이미지 13종이다. 새 규칙 프로필은 `prestudy_20261104_stadium_v2`다.

구현된 추가 사항: PDF 이미지 특징점 검출·비인식 패널 제외, 가시 수광부 조준과 적색 파괴 LED, 기존 main의 RGB 교전/위험도 추정 통합, 감지 시각/패킷 도착 순서 거점 판정, 주행·팬틸트 가속도 모델, 드론 수신/중복/시계/중단 처리, 팀별 정책·수동 제어·제출 보고·진단·빌드 버전 웹 콘솔, 수동 개입 결과 표시.

새 프로필의 가속도/전송 지연은 측정되지 않은 SIM 가정이다. PDF 검출은 제공된 인쇄물 기준 모델이다. 실제 카메라 일반화, 실물 ROS 2/최종 SDK, 드론 기반 경로 재계획·사격, 전술 회피, 레이저 확산/수광 감도·바퀴 미끄러짐/전력 소비는 완료되지 않았다. 후속 구현은 이 한계를 유지하면서 진행한다.

## 도메인 갱신 원인과 현재 구조

- 원래 Oracle 배포 명령과 Codex `serve_session.py` 모두 `smoke_six`를 시작했다. 이 브랜치는 **두 실행 경로 모두 `reference_stadium`으로 수정**했다.
- Oracle Caddy는 loopback18090의 인증 중계기를 통해 Codex 작업자로 요청을 전달하며, Codex가 끊기면 기존 Oracle 앱으로 복귀한다. DNS를 바꾸거나 Caddy를 단순히8080으로 덮어쓰지 않는다.
- 기존 gateway 배치는 Actions43243619769에서 성공한 기록이 있다. 마지막 이전 확인값은 `X-Maicon-Compute: oracle-backup`이다. 새 맵이 현재 공개 서비스에 반영됐다는 증거는 아직 없다.
- `deploy/codex/serve_session.py`는 새 맵·mock M1·현재 Git revision을 설정한다. `prepare_session.py --from-environment`는 게시한 `MAICON_RELAY_CREDENTIALS_JSON`을 비공개 파일로 준비한다. 세션·도메인 불일치나 기존 다른 인증 파일은 덮어쓰지 않는다.
- 이전 실행 환경 상태는 revision1, 사용자 허용 도메인0개·환경 변수0개였다. `curl`의 CONNECT403은 로컬 네트워크 정책에 의한 것이므로 사이트 자체 장애로 단정하지 않는다. 사용자에게 같은 도메인을 다시 입력하거나 게시하라고 반복 요청하지 않는다.

## 새 환경에서 진행할 순서

1. 실행 환경 스킬/현재 지침을 확인한다. 환경 상태의 허용 호스트와 `MAICON_RELAY_CREDENTIALS_JSON`의 **존재만** 확인한다. 값은 출력하지 않는다. 도메인 및 `api.github.com`에 새 HTTPS 요청을 보내 적용 여부를 검증한다. 프록시 해제·대체IP·임의 중계로 정책을 우회하지 않는다.
2. Git 상태 확인 → 원격 feature 브랜치 최신화 → 위 문서와 아래 검증 기록 확인. 사용자 변경을 보존한다. 의존성은 잠금 파일 기준으로 준비한다.
3. [Codex 실행 안내](../deploy/codex/README.md)를 따라 인증 파일을 준비한다. 기존 운영 비밀번호·토큰·SSH 개인키를 채팅에 붙여 넣으라고 하지 않는다. 새 환경에서는 파일이나 프로세스가 복원돼 있다고 가정하지 않는다.
4. 자격 증명이 환경에 있으면 다음 명령을 사용한다. 모두 ignored `artifacts` 안에 저장한다.

   ```bash
   .venv/bin/python deploy/codex/prepare_session.py --from-environment --out artifacts/codex-domain-session/private
   .venv/bin/python deploy/codex/serve_session.py --session-dir artifacts/codex-domain-session/private
   ```

5. 로컬 운영자18080·참가팀18000·관리자18001을 확인한 뒤, 별도 프로세스로 아래 작업자를 실행한다. 인증 파일의 내용을 로그에 쓰지 않는다.

   ```bash
   .venv/bin/python -m maicon_sim.server.cloud_relay --mode worker --credentials artifacts/codex-domain-session/private/credentials.json
   ```

6. 공개 `/login`의 `X-Maicon-Compute: codex-cloud`, 인증된 `/api/state`의 `match_id`와 `build_revision`이 로컬과 같은지 확인한다. `scenario_id=reference_stadium`, 박스20개·시설6개·이미지13종과 브라우저의 실제 맵/카메라까지 확인해야 배포 완료다. 기존 운영 경기가 진행 중이면 전환을 기다린다. 기능 시험은 먼저 별도 로컬 경기에서 한다.
7. Oracle fallback도 최신 맵으로 갱신할 필요가 있으면 CI 통과와 현재 경기 상태를 확인하고 기존 immutable image/rollback 절차를 사용한다. feature 브랜치를 main에 반영하는 과정에서 새 원격 변경을 보존한다. main 배포 workflow가 Codex 중계 구성을 유지하는지도 확인한다.
8. 남은 시뮬레이션 구현을 이어가며, 실제 SDK가 없는 부분을 FakeRosTransport 통과로 실물 검증했다고 표시하지 않는다. 최종 답변에 구현/검증/공개 배포 상태와 남은 한계를 구분한다.

## 검증 기록

- `reference_stadium` 설정 검증: 통과, 경고 없음.
- 첫 전체 회귀: **556통과·3실패·12제외**, 521.43초. 실패는 합성 COMMS/OUTPOST 수광부 초기 색상 2건과, 구형 렌즈 색상 변경을 전제로 한 RGB 밝기 검사 1건이었다.
- 위 문제를 수정한 최종 인식/타격/LED/구동/센서/드론 회귀: **41통과**, 100.78초. 첫 전체 검사의 실패 3건을 모두 포함한다. 결과: `artifacts/stadium-final-targeted.xml`.
- 기존 Codex 중계 코드 병합 후 배포·rollback·gateway·새 환경 인증 준비/실행 검사: **26통과**, 12.56초. 결과: `artifacts/stadium-deployment-tests.xml`.
- Chromium 데스크톱: **통과**. 실제 참가 프로세스6개 출발, RGB/WebGL, 수동 발사·탄약 차감·개입 결과 기록, 드론 영상, pause/resume, 종료/결과, 다음 경기 초기화, 기존 비밀번호 재로그인. 브라우저 오류0개. 스크립트: `scripts/check_web_ui.cjs`; 결과: `artifacts/web-browser-evidence.json`.
- 앞의 전체 검사는 마지막 수정/배포 브랜치 병합 전 실행이다. 최종 브랜치 전체 CI 상태는 새 환경에서 확인한다. 관련 실패는 수정 후 재검증했지만, 전체 검사를 최종 HEAD에서 한 번에 모두 통과했다고 기록하지 않는다.
- `artifacts`는 Git에 포함하지 않는다. 새 환경에서 이전 로컬 결과 파일이 없으면 위 명령으로 재현한다. 운영 도메인 검증·재배포는 아직 완료하지 않았다.

재현 명령:

```bash
.venv/bin/maicon-sim validate --example reference_stadium
.venv/bin/pytest -m 'not slow and not performance and not hardware and not manual_gui'
```

브라우저 시험은 별도 로컬3D 서버에만 `scripts/check_web_ui.cjs`를 사용한다. 스크립트의 가짜 시험 비밀번호와 포트18000/18001/18080을 맞춘다. **무거운 렌더링 시험과 브라우저6팀 시험을 같은 CPU에서 동시에 실행하지 않는다.** 첫 브라우저 실행은 다른 렌더 시험과 자원을 공유해 출발 대기 시간 초과가 났다.

## 2026-11-13 새 환경에서 이어서 확인/구현한 사항

이 절은 위의 이전 인수인계보다 최신이다. 사용자에게 이미 허용한 네트워크·비밀번호·배포 설정을 다시 요구하지 않는다.

- 선택된 새 실행환경은 게시 revision1이 적용된 running 상태다. `observations_current=true`, 네트워크 `enforced`, `api.github.com`·공개 도메인 허용 및 `MAICON_RELAY_CREDENTIALS_JSON=ready`를 확인했다. 두 대상에 새 HTTPS 연결이 성공했다. 인증 값은 기록하지 않는다.
- 원격 feature HEAD `54a5dc0`의 CI [43368048253](https://github.com/jha68/MAICON_Virtual_Stadium/actions/runs/43368048253)는 성공했다. core-contracts, 전체 integration/render, wheel 격리 설치 및 6개 실제 참가 프로세스 Chromium 시험이 성공했고 slow longpoll은 push의 기본 조건에 따라 제외됐다.
- 기존 운영 비밀번호/작업자 토큰으로 private 파일을 준비하고 서버·작업자를 시작했다. 전환 직전 Oracle은 `smoke_six-0004`, `finished`였다. 진행 중 경기를 초기화하지 않고 Codex로 전환했다.
- 공개 `/login`의 `X-Maicon-Compute=codex-cloud`, 공개/로컬 `/api/state`의 동일한 match/revision, `reference_stadium`, 박스20·시설6·이미지13·M1 mock을 확인했다. Chromium 데스크톱에서 비밀번호만으로 로그인, 이미지13종 로드, 실제 WebGL 지도 및 6대 RGB JPEG를 확인했다. 공개 검사는 로그인 외 경기 명령을 보내지 않는다.
- 사용자가 CA 영구 신뢰 등록을 명시적으로 요청했다. 제공된 환경 CA는 Chromium NSS 저장소의 trusted CA와 동일함을 확인했고, 등록 후 저장소를 열 수 있는 실행 권한으로 Chromium의 직접 HTTPS 접속이 성공했다. 인증서 오류 무시나 네트워크 우회는 사용하지 않는다. 기본 filesystem sandbox는 홈의 NSS DB 쓰기를 제한하므로 브라우저 실행 권한 문제와 TLS 문제를 구별한다.
- 공개 경기 `reference_stadium-0001`이 운영 중인 것을 관측하여 재시작하지 않았고, 자연 종료와 저장된 결과를 확인했다. 기존 run 폴더를 삭제하지 않는다. 이후 서버를 갱신할 때도 waiting/finished를 다시 확인한다.
- 후속 구현: 보정된 공개 드론 JPEG의 상자 묶음/익명 기체 검출·XY 추정, 임시 회피 영역 기반 A* 재계획, 관측 노후화/중단 시 LiDAR 복귀, 상대 위치를 향한 팬틸트 탐색, 전방 RGB 근접 상대/자기 HP 감소에 반응하는 보수적 후퇴를 추가했다. LiDAR로 확인된 통행 가능 셀은 불확실한 드론 윗면/높이 추정보다 우선한다. 드론만으로 발사하지 않는다. 상세 한계·모델은 `STADIUM_FIDELITY.md`의 후속 절에 있다.
- Oracle 배포는 준비 전과 컨테이너 정지 직전에 기존 Oracle 앱 자체의 상태를 인증해 확인한다. ready/running/reporting/알 수 없는 상태/조회 실패이면 기존 컨테이너를 정지하지 않고 보류한다. 비밀번호 파일, Caddy→18090 중계 경로, immutable image/rollback을 유지한다.

6개 실제 baseline 프로세스의 로컬 연결 시험에서 초기 센서 캐시 교체 후 최신 드론 관측이 정책에 합류되지 않는 누락을 발견해 수정했다. 계획 계산 시마다 독립 드론 수신기의 최신 상태를 합류하며, cache 교체/노후화 단위 검사와 6개 실제 프로세스 시험을 CI에 추가했다. `scripts/check_baseline_drone.py`는 운영 비밀번호를 거부하고 알려진 시험 비밀번호의 loopback 서버에만 동작한다. 로컬 6팀 모두 공개 드론 항법 관측을 사용하고 종료·보고 완료까지 확인했다.

최종 6팀 CI(98c034f)는 전체 회귀·패키징은 성공했으나 브라우저/드론 단계에서 실패했다. 2코어 로컬 재현에서 드론 프레임이 3~5초 지연되는 CPU 포화가 확인됐다. 참가 프로세스의 OpenCV/BLAS 스레드를 1개로 제한하고 완전히 같은 새 RGB 픽셀의 이미지 전용 추론 결과를 재사용하도록 개선했다. 원래 capture tick/sequence는 유지하며, 센서 캐시 자체를 새 관측으로 바꾸지 않는다. 신선도 기준을 느슨하게 하지 않는다. 로그 다운로드의 results-receiver 호스트는 현재 네트워크 허용 범위 밖이므로 같은 설정을 반복 요구하지 않고 로컬 재현과 GitHub API 검사 결과를 이용했다. CI 실패 단계는 이제 안전한 고정 문자열 annotation으로도 남긴다. 최적화 후 렌더 시험과 겹치지 않는 2코어 로컬 trial에서 데스크톱 6팀 조작과 6개 baseline의 최신 드론 항법 수신·경기 종료까지 통과했다. `disposable-2cpu-isolated-*.log`에 근거가 있다.

새 증거는 ignored `artifacts`에 저장한다. `drone-tactics.xml`, `stadium-followup-targeted.xml`, `stadium-resumed-full.xml`, `public-stadium-evidence.json`, `evidence/public-reference-*.png`를 확인한다. 전체 검사는 실행 완료와 실제 결과를 확인한 뒤에만 통과로 보고한다. 최종 코드 CI는 이 feature 브랜치의 최신 SHA에 해당하는 실행을 조회한다.

공개 사이트 읽기 전용 재검증:

```bash
NODE_PATH=/workspace/maicon-browser/node_modules CHROMIUM_BIN=/usr/bin/chromium \
  node scripts/check_public_stadium.cjs
```

이 명령은 비밀번호를 기본 private 파일에서 읽는다. 필요하면 `MAICON_PUBLIC_PASSWORD_FILE`로 파일 경로만 지정한다. Chromium은 환경 프록시와 영구 CA를 사용하며, TLS 검증을 끄지 않는다. NSS 접근이 제한되는 sandbox에서는 승인된 실행 권한으로 동일 명령을 실행한다.

### 여전히 완료되지 않은 실물 항목

실제 카메라/출력물/조명 일반화, 공식 `rclpy` 메시지·서비스·QoS 및 최종 SDK 통합, 실제 바퀴 슬립·전력/배터리 소모, 레이저 확산·수광 감도/각도 응답은 장비·공식 타입·측정자료가 없어 완료로 표시하지 않는다. 드론 차체 중심으로 발사하거나 관측되지 않은 상대 HP/탄약/방향을 추정하지 않는다. H-01~H-07은 `HARDWARE_VALIDATION.md`의 not_run을 유지한다. M1은 계속 mock이고 모바일 대응은 범위 밖이다.


### ARM64 이미지 빌드 캐시

기능 커밋 `abf21eb`의 최종 CI43375325714는 전체 회귀·wheel·데스크톱·6개 baseline 드론 연결까지 성공했고, Codex 공개 앱도 이 revision으로 전환해 실제 맵/6대 RGB를 재검증했다. 전환 전 finished 상태를 다시 확인했고 운영 결과2개를 해시로 보존했다. main은 병합하지 않았다. Oracle 갱신은 feature ref의 수동 workflow를 사용한다.

Oracle ARM64 빌드 중 Dockerfile의 revision ARG/ENV/LABEL이 의존성 설치보다 앞에 있어 커밋마다 의존성 캐시를 무효화하는 구조를 확인했다. 메타데이터 설정을 모든 빌드 RUN 뒤로 옮겼다. 런타임 ENV와 OCI revision label은 유지한다. 이 변경은 앱 동작 변경이 아니며, 공개 앱의 현재 revision과 ARM64 배포 workflow의 실제 성공 상태는 각각 확인한다. 진행 중인 경기는 재시작하지 않는다.


## 최신 기능 main/Oracle 통합 (2026-11-13)

사용자가 다른 세션의 최신 기능까지 main과 Oracle에 모두 반영하도록 요청했다.
원격 feature의 f0e65f9까지 보존하며 통합한다. 공개 Codex e7a8081과 이 feature의 앱 코드는 같고,
이후 추가분은 암호화 bootstrap/배포 증거/인수인계다. 활성 중계 세션을 다시 설치하거나
이 채팅의 오래된 자격 증명을 덮어쓰지 않는다. 새 Codex 연결과 기존 비밀번호를 유지한다.

Oracle 배포 검사를 최신 구성인 박스20·시설 수광부6·이미지16·M5 패널6으로 갱신했다.
기존 13종 검사는 최신 이미지의 정상 배포를 거부할 수 있으므로, 실제 배포용 Python 검사를
실행하는 회귀 시험으로 정상16종, 구형13종, 패널 누락, 잘못된 build revision을 검증한다.
main CI 성공 후 기존 immutable image/rollback 절차로 Oracle만 갱신하며 진행 중 경기 보호는 유지한다.
공개 Codex의 빌드 표시는 e7a8081로 남을 수 있으나 앱 소스의 동일성을 Git tree로 확인한다.


## 자동 임무 실행과 M6 mock 적용 (2026-11-13, 최신)

사용자 요청으로 모든 UGV를 `mission` 한 가지 실행 흐름으로 통합했다. `idle/baseline/patrol/blocker/capture_runner` 선택 메뉴·CLI 옵션·구현을 제거했다. M1의 세 필드 `target/search_sectors/base`를 시작 시 직접 받으며 LLM 호출과 interpretation 제출은 생략한다. M2는 target, M3는 상대 세 구역+CM, M5는 기준 경기장 240초에 실제 게시된 objective를 사용한다. M6는 상대 호출부호 1/2/3 순서 mock이다. 자세한 계약은 [자동 임무 흐름](AUTOMATIC_MISSIONS.md)을 따른다.

공개 Codex 앱은 `f34c74bc366116c8cee6af2a60c81d0508df2966`으로 전환했다. `waiting` 상태에서 기존 결과/상태를 보존했으며 비밀번호·중계 세션·작업자는 그대로다. 이 작업에서는 main/Oracle을 변경하지 않았다. 공개 URL에서 같은 비밀번호, 로컬과 같은 revision/match, 실제 6대 RGB, WebGL, 이미지16종과 M5 패널6개를 읽기 전용 브라우저로 확인했다. 운영 경기를 시험 목적으로 시작하지 않았다.

이 환경의 앱은 편집 가능한 checkout 대신 `work/releases/mission-5b752ba/venv/bin/python`의 고정 소스를 실행한다. 이 디렉터리의 앱 소스는 f34c74b와 동일하며 두 커밋 차이는 패키지 시험뿐이다. `work/releases/mission-5b752ba/deployment.json`과 `work/deploy/server-pid`가 실제 실행 정보를 가진다. 변경한 checkout이 다음 참가 프로세스에 섞이지 않는다. 활성 자격 증명은 `work/deploy/private/credentials.json`, 비밀번호는 같은 디렉터리 `web.password`다. 환경변수에 남은 오래된 relay 자격 증명으로 덮어쓰지 않는다. 비밀 값은 출력하거나 Git에 올리지 않는다.

검증 자료는 무시되는 `work/mission-validation-summary.json`, `work/mission-validated-match`, `artifacts/public-stadium-evidence.json`에 있다. 6개 실제 3D 참가 프로세스 경기에서 경기 시계267.73초(실제325.47초)에 M5 점령으로 종료했고, 모든 기체가 초기 SUPPLY와 다른 MAINTENANCE 목표를 받았으며 M6 mock을 제출했다. M1 제출과 LLM 호출은 모두0회였다. 200ms로 따라잡기 폭을 제한해 과부하 뒤 마지막60초를 몇 초에 소모하지 않으며, 물리 틱과 누적 지연 계측은 유지한다.

남은 성능 한계를 성공으로 기록하지 않는다. 이 경기에서 네 구역을 모두 방문한 기체는4/6이고, B-1과 R-2는 중앙 교행·경로 정체로 일부 구역을 방문하지 못했다. 시설 타격 M2 점수는 전원0으로, 대상 전달과 개별 타격 폐루프 회귀 통과가 실제 경기장 인식·타격 성공을 의미하지 않는다. RGB 지연, 중앙 경로 추종, 시설 관측 위치를 다음 개선 대상으로 남긴다. M3 보고는 실제 관측 증거만 반영한다.

최종 변경 CI: https://github.com/jha68/MAICON_Virtual_Stadium/actions/runs/43393951330 . 완료 상태는 아래 추가 기록을 확인한다. 이전 실패는 직접 명령 DTO와 활성 M3/M6 점수에 대한 과거 기대값, 그리고 M5 점령으로 정상 조기 종료된 wheel 경기를 반드시300초라고 검사한 항목이었다. 관련 기대값은 현재 임무 계약에 맞게 갱신했다.

최종 CI43393951330은 성공했다. core-contracts, 전체 integration/render 회귀, wheel 격리 설치, 실제6개 프로세스 Chromium 조작과 공개 드론 연결 검사가 통과했다. real-longpoll은 push 기본 조건에 따라 실행 대상에서 제외됐다. 운영 앱 f34c74b는 이 성공한 CI의 앱 소스와 같고, 이후 인수인계 커밋은 문서만 바꾼다.
