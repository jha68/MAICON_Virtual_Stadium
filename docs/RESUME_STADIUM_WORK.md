# 새 실행 환경 인수인계

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

새 증거는 ignored `artifacts`에 저장한다. `drone-tactics.xml`, `stadium-followup-targeted.xml`, `stadium-resumed-full.xml`, `public-stadium-evidence.json`, `evidence/public-reference-*.png`를 확인한다. 전체 검사는 실행 완료와 실제 결과를 확인한 뒤에만 통과로 보고한다. 최종 코드 CI는 이 feature 브랜치의 최신 SHA에 해당하는 실행을 조회한다.

공개 사이트 읽기 전용 재검증:

```bash
NODE_PATH=/workspace/maicon-browser/node_modules CHROMIUM_BIN=/usr/bin/chromium \
  node scripts/check_public_stadium.cjs
```

이 명령은 비밀번호를 기본 private 파일에서 읽는다. 필요하면 `MAICON_PUBLIC_PASSWORD_FILE`로 파일 경로만 지정한다. Chromium은 환경 프록시와 영구 CA를 사용하며, TLS 검증을 끄지 않는다. NSS 접근이 제한되는 sandbox에서는 승인된 실행 권한으로 동일 명령을 실행한다.

### 여전히 완료되지 않은 실물 항목

실제 카메라/출력물/조명 일반화, 공식 `rclpy` 메시지·서비스·QoS 및 최종 SDK 통합, 실제 바퀴 슬립·전력/배터리 소모, 레이저 확산·수광 감도/각도 응답은 장비·공식 타입·측정자료가 없어 완료로 표시하지 않는다. 드론 차체 중심으로 발사하거나 관측되지 않은 상대 HP/탄약/방향을 추정하지 않는다. H-01~H-07은 `HARDWARE_VALIDATION.md`의 not_run을 유지한다. M1은 계속 mock이고 모바일 대응은 범위 밖이다.
