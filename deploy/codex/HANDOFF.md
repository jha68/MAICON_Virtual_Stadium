# Codex 도메인 전환 인수인계

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

2026-11-13(KST) 체크포인트. 이 문서는 대화 이력을 대신하기 위한 작업 상태이며, 새 환경에서는 실제 파일·프로세스·접속 상태를 다시 확인한다.

## 목표와 유지할 조건

- `maicon.junununseo.com`의 실제 시뮬레이터·여섯 참가팀·카메라 렌더링을 Codex Cloud에서 실행한다.
- Oracle은 기존 HTTPS 입구와 연결 장애 시 대체 서버로 남긴다. DNS는 변경하지 않는다.
- 기존 운영 비밀번호와 비밀번호만 입력하는 로그인은 유지한다. 아이디 입력·비밀번호 변경·로그아웃 UI/API를 다시 추가하지 않는다.
- 사용자는 GitHub 반영과 웹 서비스 전환을 요청했다. 진행 중인 기존 경기는 강제 초기화하지 않는다.
- main에 게시된 대회 규칙·정책·CPU 최적화 수정은 이미 완료된 작업이다. 이전 수정을 다시 적용하지 않는다.

## 코드와 확인한 상태

- 작업 브랜치: `deploy/codex-cloud-20261112`. 환경의 기본 저장소 ref가 main이면 먼저 작업 트리 변경을 보존하고 해당 원격 브랜치를 가져온다. 무조건 reset하지 않는다.
- 애플리케이션 기준 main: `299c9b3`. 중계 코드: `3b063cd`, 암호화된 bootstrap 준비 결과: `3cd0186`.
- GitHub Actions `codex-domain-gateway` 실행43243619769와 같은 코드의 `simulator-validation` 실행43243619652가 성공했다.
- Oracle의 Caddy→loopback18090 중계기 배치 및 HTTPS 검사가 성공했다. 현재 공개 경로의 마지막 확인값은 `oracle-backup`이다.
- Codex 앱은 기존 비밀번호로 실행했고 Chromium에서 실제 RGB·WebGL·6팀 준비·주행·pause/resume·종료·초기화·같은 비밀번호 재로그인을 확인했다.
- 현재 Codex 작업자는 아직 시작하지 않았다. 실행환경 네트워크에서 대상 도메인이 CONNECT403으로 거절됐기 때문이다.
- 설정 초안에는 `maicon.junununseo.com`이 추가됐지만 마지막 실행환경 확인은 spec revision1·사용자 허용 호스트 없음이었다. 새 채팅에서는 환경 상태와 새 HTTPS 연결을 다시 확인해야 한다.

## 파일과 프로세스

다음은 경로만 기록한다. 파일 내용을 채팅·명령 인자·Git·로그에 출력하지 않는다.

- 세션 개인키: `artifacts/codex-domain-session/private-key.pem` (0600).
- 로컬 운영 비밀번호: `artifacts/codex-domain-session/private/web.password` (0600).
- 작업자 자격 증명: `artifacts/codex-domain-session/private/credentials.json` (0600).
- 로컬 준비 상태: `artifacts/codex-domain-session/readiness.json`.
- 서버 프로세스 기록: `artifacts/codex-domain-session/server-process.json`. 기록된 PID가 실제 같은 프로세스인지 확인하고 사용한다.
- 공개 인증서·세션 설정·암호문: `deploy/codex/session-cert.pem`, `session.json`, `bootstrap/*.cms`.

새 채팅에 파일이 복원됐다고 가정하지 않는다. 개인키나 준비된 자격 증명이 없으면 현재 암호문을 새 개인키로 해독할 수 없다. 새 세션 키·공개 인증서를 만들어 기존 GitHub Actions SSH 연결로 bootstrap을 다시 준비할 수 있다. 사용자에게 운영 비밀번호나 SSH 개인키를 채팅에 붙여 넣으라고 요청하지 않는다.

게시된 파일과 설치된 의존성은 환경 재사용의 대상이지만 실행 중인 서버·연결은 스냅샷 복원 후 유지된다고 보장되지 않는다. 실행 절차는 [README](README.md)를 따른다.

## 다음 순서

1. 현재 환경 상태·네트워크 정책과 Git 작업 트리를 확인한다. 도메인이 거절된 상태에서는 프록시 해제·다른IP·다른 엔드포인트로 우회하지 않는다. 네트워크 적용 후 상속된 프록시·CA로 새 HTTPS 요청을 확인한다.
2. private 파일과 Codex 앱을 확인한다. 필요하면 `prepare_session.py`로 bootstrap을 해독하고 `serve_session.py`로 서버를 재시작한다. 포트는 운영자18080·참가팀18000·관리자18001이고 loopback에만 바인딩한다. CPU affinity는4개다.
3. 허용된 네트워크를 확인한 뒤 `python -m maicon_sim.server.cloud_relay --mode worker --credentials <private 경로>`를 별도 프로세스로 실행한다. 현재 제어 토큰을 새로 만들거나 비밀번호를 바꾸지 않는다.
4. 공개 `/login`의 `X-Maicon-Compute: codex-cloud`와 인증된 공개 `/api/state`의 match_id가 로컬 Codex 앱과 같은지 확인한다. `oracle-backup`은 아직 전환되지 않은 상태다. 기존 경기가 ready/running/reporting이면 작업자가 종료를 기다리도록 둔다.
5. 실제 공개 도메인에서 로그인·정적 파일·RGB·경기 조작을 검증한다. 비밀번호는 코드가 private 파일에서 읽게 하고 도구 인자나 실패 로그에 노출하지 않는다.
6. 전환 검증 후 작업 브랜치를 main에 반영할 때 `deploy/oracle/deploy.sh`의 중계 경로 보존 수정도 반드시 포함한다. main의 기존 배포 스크립트만 다시 실행하면 Caddy 경로를8080으로 되돌릴 수 있다. Codex 전환 전의 main 자동 배포는 기존 경기를 재시작할 수 있어 실행 시점을 주의한다.

Codex는 세션 기반 실행환경이다. 대화가 끝나거나 환경이 교체될 때 서비스가 계속 실행된다고 보장하지 않는다. 공개 도메인이 실제 Codex 앱을 제공하는지 확인하기 전에는 전환 완료라고 보고하지 않는다.
