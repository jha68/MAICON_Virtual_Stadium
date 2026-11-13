# Codex Cloud 실행과 기존 도메인 연결

`maicon.junununseo.com`의 HTTPS 입구는 기존 Oracle Caddy에 둔다. 실제 시뮬레이터·참가팀 프로세스·카메라 렌더링은 Codex Cloud의4코어 예산에서 실행한다. 이 환경에는 직접 사용할 공인 ingress 주소가 제공되지 않으므로 Codex 작업자가 허용된 도메인으로 HTTPS 요청을 보내 운영자 요청·응답을 중계한다. 일반 TCP·SSH 프록시나 임의 목적지 프록시는 제공하지 않는다.

Oracle gateway는 기본적으로 기존 서버를 제공한다. Codex 작업자가 로컬 앱 인증과 연결 상태를 확인한 뒤에도 기존 경기가 ready/running/reporting 단계이면 전환을 기다린다. 대기·종료 상태에서 전환하며, Codex 연결이20초 이상 갱신되지 않으면 Oracle로 돌아간다. 앱의 match_id가 바뀌고 세션 재로그인이 필요할 수 있다. 서버 간 진행 중 경기의 메모리를 복제하는 기능은 아니다.

## 자격 증명과 준비

현재 운영 비밀번호는 변경하지 않는다. GitHub Actions의 기존 pinned SSH 연결로 Oracle gateway를 배치한다. 암호화용 공개 인증서만 저장소에 올리고 개인키는 Codex의 ignored artifacts 폴더에0600으로 둔다. 기존 비밀번호·작업자 토큰은 CMS AES256-GCM·RSA-OAEP로 암호화한 bootstrap만 저장소로 전달한다. 원문·개인키는 Git·채팅·로그에 출력하지 않는다.

현재 세션의 개인키 파일이 있는 환경에서 bootstrap을 가져온 뒤 다음을 실행한다.

```bash
SESSION=$(python -c 'import json; print(json.load(open("deploy/codex/session.json"))["session_id"])')
.venv/bin/python deploy/codex/prepare_session.py \
  --encrypted "deploy/codex/bootstrap/$SESSION.cms" \
  --private-key artifacts/codex-domain-session/private-key.pem \
  --out artifacts/codex-domain-session/private
.venv/bin/python deploy/codex/serve_session.py \
  --session-dir artifacts/codex-domain-session/private
```

앱은 loopback18080, 참가팀 API18000, 관리자 API18001에서 실행한다. 운영자 비밀번호 파일은 private 폴더에0600으로 보존하며 기본 자율 정책·실제 RGB·2D/3D 화면은 기존 앱 그대로다. 비밀번호 변경·로그아웃 UI나 API를 다시 추가하지 않는다.

## 네트워크와 작업자

Codex 환경에서 `https://maicon.junununseo.com`이 허용되어야 한다. 설정 초안 저장과 현재 실행환경에 적용되는 것은 다르다. 프록시가403으로 거절하면 환경 설정에서 허용 도메인을 검토·저장·게시하고 새 연결로 확인한다. 프록시 해제·대체IP·다른 엔드포인트로 정책을 우회하지 않는다. 외부 HTTPS에는 상속된 프록시·CA를 그대로 사용한다.

앱과 네트워크를 확인한 뒤 별도 프로세스로 작업자를 실행한다.

```bash
.venv/bin/python -m maicon_sim.server.cloud_relay --mode worker \
  --credentials artifacts/codex-domain-session/private/credentials.json
```

`/login` 응답의 `X-Maicon-Compute: codex-cloud`와 인증된 공개 `/api/state`의 match_id가 로컬 Codex 앱과 같은지 검증해야 전환 완료로 판단한다. `oracle-backup`은 아직 Oracle을 제공하는 상태다. 제어용 `/_codex_bridge/*`는 별도 토큰으로 인증하며 브라우저 요청에는 운영자 인증을 그대로 적용한다.

요청·응답 크기, 대기 큐, 요청 시간은 제한한다. 브라우저의 POST 명령은 중계 오류 때 자동으로 반복하지 않는다. 작업자의 응답 전송만 같은 ID로 재시도할 수 있다. 브라우저별 Cookie를 명시적으로 전달해 HTTP 클라이언트의 공용 Cookie 저장소가 다른 사용자를 인증하지 않도록 한다.

Codex는 세션 기반 환경이다. 환경 재시작·종료 후 프로세스가 유지되는 상시 호스팅을 보장하지 않는다. 개인키를 잃으면 새 공개키로 bootstrap을 다시 준비해야 한다. DNS·기존 비밀번호는 이 연결 방식으로 변경하지 않는다.
