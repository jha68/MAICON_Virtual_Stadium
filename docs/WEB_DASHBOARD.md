# 운영자 웹 화면 계약

2026-11-08 추가. 기존 공통 MatchEngine·센서·참가팀 HTTP 포트에 연결한 SIM 운영자 UI다. 공식 대회 wire API에 새 경로나 정답 필드를 추가하지 않는다.

## 경계

`serve --web-port 8080`과 `MAICON_WEB_PASSWORD_FILE`을 지정해야 활성화한다. 비밀번호는 최소10자이며 미설정/잘못된 값이면 실행을 거절한다. 로그인 페이지에서 비밀번호만 입력하고 서명된 HttpOnly·SameSite 세션 쿠키로 페이지·정적 파일·JSON·카메라를 인증한다. HTTPS에서는 Secure 쿠키를 사용한다. 브라우저 기본 아이디/비밀번호 팝업은 사용하지 않는다. 내부 배포 상태 검사용 Basic 인증은 호환 유지한다. 화면의 비밀번호 변경은 현재 비밀번호를 확인해 파일에0600으로 원자 저장하고 기존 세션을 무효화한다. 실제 운영에서는 Caddy의 HTTPS만 공개한다. 관리자 Bearer 토큰·mission_code·비밀번호를 브라우저 JSON·스크립트·URL에 포함하지 않는다.

`/api/state`는 운영자 전용 정답 snapshot이며 참가팀 앱에는 없다. `/api/command`는 X-Maicon-Operator 헤더와 동일 origin을 검사하고, 정해진 action/policy만 허용한다. CORS·임의 경로·임의 scenario 파일·임의 shell 명령을 허용하지 않는다. 정적 파일은 패키지 web 디렉터리를 벗어날 수 없다. 응답은 no-store, CSP self, frame-ancestors none, nosniff를 적용한다. 현재는 한 명 이상의 동등한 운영자를 위한 공통 관리자 계정이며 다중 역할·SSO 기능은 없다.

## 동작

- 2D 지도·Three.js0.180.0 WebGL 장면은 같은 코어 snapshot의 위치를 표시한다. WebGL은 브라우저에서 실행하며 서버에 GPU를 요구하지 않는다. Three.js는 MIT 라이선스·npm provenance와 함께 패키지에 포함해 외부 CDN을 호출하지 않는다.
- 로봇 카메라는 실제 SensorGateway의 PyBullet JPEG를 재사용한다. 선택한 로봇 한 대를 최대2Hz로 화면 갱신하며 추가 렌더 명령을 발행하지 않는다. 캡처 tick을 표시한다. 경기 ID가 다른 응답은 버린다. 2D backend에서는 RGB를 제공하지 않는다고 표시한다.
- 준비 시작은 기존 ParticipantProcesses로 실제 프로세스 여섯 개를 실행한다. 각 팀이 공개 API·필수 센서를 확인하고 ready를 보내야 시작할 수 있다. UI가 대신 ready를 쓰거나 pose를 직접 수정하지 않는다.
- 기본 순찰 데모는 주행 확인용 정책이다. idle은 준비만 하고 baseline은 기존 합성 인식/FixtureLLM 통합 정책이다. 실제 LLM·실물 인식 성능을 의미하지 않는다.
- 준비 단계 초기화는 준비 취소다. running/reporting 중 초기화는 거절하며 종료 뒤 초기화한다. 종료 점수는 먼저 private/results에 보존하고 참가 프로세스를 닫은 뒤 코어를 reset한다. 새 경기 ID·센서 generation·정책 캐시를 기존 reset 경로로 갱신한다.
- 브라우저 지도 궤적은 로봇별350점으로 제한하고 새 경기에서 지운다. 서버 웹 모드는 이벤트 journal을 무한히 메모리에 보존하지 않는다. 이 모드가 저장하는 최종 결과·참가팀 로그는 CLI run의 전체 replay 기록과 다르며, 완전한 기록/재생은 기존 run/replay 명령을 사용한다.
- 지연·센서 누락 수치는 프로세스 수명 동안의 누적 측정이다. 브라우저 갱신율과 서버 센서 생성율은 다르다. 2 OCPU에서6대 주행+6카메라10Hz의 실시간 성능을 보장하지 않는다.
- SIGTERM 시 HTTP 서버·runtime·참가팀 프로세스·렌더러를 종료한다. 배포는 경기 프로세스를 재시작하므로 실제 경기 중 배포하지 않는다.

## 경로

| 경로 | 동작 |
|---|---|
| GET / | 운영자 웹 화면 |
| GET /assets/* | 패키지에 포함한 정적 파일 |
| GET /api/state | 코어 상태·운영자 지도·카메라 capability |
| POST /api/command | ready/start/pause/resume/finish/reset, 허용된 정책만 |
| GET /api/camera/{slot}.jpg?match_id=… | 실제 해당 경기의 RGB, timestamp 헤더 |
| GET /api/result | 종료 후 결과; 진행 중409 |

공개 참가팀 앱·기존 관리자 앱에는 이 경로들을 mount하지 않는다. 파일 시스템에서 같은 OS 사용자 간 악의적 접근을 격리하는 보안 제품은 아니다.
