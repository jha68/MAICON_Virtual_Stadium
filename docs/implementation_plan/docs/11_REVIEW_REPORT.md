# 구현계획 완성 후 검토 결과

검토 대상은 이 묶음의 2D·3D 구현계획, 공통 계약, 스키마와 예시, 참고자료 발췌다. 작성 후 독립 검토와 교차 검증을 진행했고 아래 문제를 수정했다. 검토 범위에서 별도 세션의 구현 착수를 막는 미해결 공백은 발견하지 못했다. 실제 프로그램 설치·실행·렌더링·현장 성능은 아직 구현되지 않은 별도 검증 대상이다.

기준 자료는 main 커밋 7c414445fcf0302620b2c89f16ce2064f91ca753이며 archive는 사용하지 않았다. 검토 기준일은 2026-11-07이다.

## 1 수정한 주요 문제

| 검토에서 발견한 문제 | 반영한 수정 |
| --- | --- |
| practice의 제어는 가능하지만 effect clock이 running에서만 흘러 cooldown이 만료되지 않을 가능성 | practice 활성화 중 별도 효과 시계 진행, TIME-025 회귀 기준 추가 |
| 마감과 센서 교차·보고가 같은 tick에 발생할 때 우선순위 불명확 | deadline 우선,240초 게시 후 교차 가능·300초 교차 불가,one-shot phase 전이 명시 |
| 보고 직렬화가 timeout 뒤 늦은 commit까지 막는다고 오해할 가능성 | 정상 경로 순서 보장과 unknown-outcome의 best-effort 복구를 구분,API-011에 지연 commit 시험 |
| pause 동안 받은 cmd_vel이 재개 때 적용될 가능성 | 잠금 중 command/watchdog 시각 갱신 금지,기존 명령 폐기,재개 후 새 명령 필요 |
| M1의 모든 필드가 명시 null일 때 처리 모호 | 모두 누락/null이면422,스키마 negative test 추가 |
| baseline이 실제 gimbal 위치를 받는다고 가정 | 접수 명령·속도 모델로 추정하고 예상 이동시간+100ms 후 관측 채택 |
| baseline의 시작 위치·지도·보정 정보 전달 경로 누락 | PublicMapPrior 명목 출발점과 /sim/map-prior·/sim/calibration을 명시,실제 jitter/정답 pose는 비공개 |
| 3D RGB 경로의 최소 인식기 선택이 불명확 | 합성 사각 테두리·원근 보정·template 기준 검출기와 제한된 합격 범위 고정 |
| 합성 텍스처의 class 문자와 정답 문자 금지 규칙 충돌 | 텍스처의 정답 문자·ID를 제거하고 도형 기반 fixture로 통일 |
| 센서 기하를 설정으로 바꿀 수 있으나 스키마가 없음 | sensor_profile 스키마·예시·scenario 참조 추가 |
| mast·marker·광선 epsilon·LiDAR 높이 모델 불완전 | 공유 proxy 기하·표식 위치·띠·오차상수 수치 고정,시각 형상과 판정 형상 차이 명시 |
| 문서별 noisy 기본값과 policy 이름이 달랐음 | stress_v1과5개 policy enum을06·schema·2D·3D에서 통일 |
| fault의 대상 요청·지연 위치·시간 기준이 모호 | http_delay의 stage·occurrence와 robot_command heartbeat,종료·reset 처리 명시 |
| 자산 생성 결과와 원본 scenario manifest의 연결이 불명확 | run의 자동 resolve와 private asset 경로,원본 미수정·hash 검증 절차 명시 |
| 산출물 경로와 섹터 경계 검증 표현의 불일치 | RUN_ROOT 기준 경로 통일,일반 박스 footprint 전체 sector 포함 조건 통일 |
| replay에서 입력과 파생 사건을 중복 적용할 위험 | input/derived/measurement 분리,core replay와 관측 재생의 범위·필수 파일 명시 |
| 언어·띄어쓰기·리터럴 개행·문서 연결 문제 | 한국어 문장 교정,코드 fence·내부 링크·개행 검사 |

이 수정들은 구현 단계에서 발견할 수 있는 모순을 줄이기 위한 문서 변경이다. 실제 대회 규칙을 임의로 확정한 것이 아니며 SIM 가정은 별도로 유지했다.

## 2 계획 파일에 실제 수행한 검증

| 검사 | 결과 |
| --- | --- |
| JSON Schema 2020-12 정의 유효성 | 9개 PASS |
| YAML 설정·시나리오의 해당 스키마 검증 | 7개 PASS |
| M1·M3·M6 요청 예시의 정규화 후 검증 | 3개 PASS |
| 시나리오 참조 파일·slot·mission code·시설 배정·자산 연결·센서 중복값·기본 배치 | 3개 시나리오 PASS |
| 음수/초과 count,bool·문자열 count,잘못된sector,전체null,중복ranking 등 잘못된 입력 거절 | 13개 negative case PASS |
| 참고자료 인용과 main Git 객체의 원문 비교 | 5개 자료의78개 인용 블록 문자 단위 일치 |
| Markdown 내부 파일 링크·코드 블록·언어 잔재 | PASS |
| 수기 점수와 테스트 ID | smoke 각20점,6팀 golden 합계214/141→보너스 후229/141 검산,152개 고유 시험 ID 확인 |

기계 검증 상세는 [계획 파일 검증 기록](../validation/plan_validation.json)에 포함했다. 152개 시험은 향후 구현체가 수행해야 할 명세이며, 지금 해당 시뮬레이터 시험을 실행했다는 뜻이 아니다. 현재 수행한 것은 문서·스키마·예시·원문 인용의 검증이다.

## 3 원문 근거의 추적

[참고자료 발췌](10_SOURCE_EXCERPTS.md)는 설계에 사용한40개 근거 항목과78개 선택 인용을 포함한다. 원문 파일·절·PDF 쪽수·고정 커밋의 행 링크를 남기고 편집자 해설을 분리했다. PDF 인용은 저장소의 변환본, 멘토링 인용은 저장소의 요약본이라는 성격을 유지한다.

Python/PyBullet 선택,10ms tick,광학 행렬,정밀 센서 위치,참고 경기장 좌표,오류 분포는 계획의 설계 결정이다. 출처 자료에 해당 정밀값이 있는 것처럼 연결하지 않았다.

## 4 남아 있는 조건과 구현자 책임

다음은 문서 모순이 아니라 의도적으로 분리한 후속 검증이다.

- Python·NumPy·PyBullet·OpenCV의 정확한 패치 버전은 M0 설치 spike에서 검증한 뒤 lock한다.
- CPU 렌더러의 실시간 처리량은 구현 환경에서 측정한다.6대×10Hz를 보장하지 않는다.
- 실제 바퀴 동역학,카메라 왜곡,레이저 광학,연기와 센서의 물리 상호작용은 v1의 검증 범위 밖이다.
- 최종 SDK·스키마·출발 판정·pause·M3 계수·M5 선점유·M6 동점 규칙은 운영진 확인 뒤 새 profile로 반영한다.
- 외부 AI 사용 허용 범위와 LLM 의무는 실제 규정에 따른다. mock LLM은 통합 시험용이다.
- 실제 장비 연결은 H gate로 따로 기록한다. G0~G3 통과가 실물 검증을 대신하지 않는다.

새 에이전트는 [시작 안내](../00_START_HERE.md)와 [구현·인계 절차](08_BUILD_AND_HANDOFF.md)에 따라 M0부터 착수할 수 있다. 검토 후에도 구현 중 새 문제가 발견되면 관련 계약·스키마·시험을 함께 수정하고 변경 이유를 기록한다.

## 5 구현 과정에서의 후속 정정

위 PASS는 첨부 당시의 계획 검토 기록으로 보존한다. 실제 구현에서는 산출물 경로, fog volume 설정, 동결 전 심판 정정 사건, 실시간 렌더러의 GIL 간섭, 드론 연습 모드의 운영 입력, dataset CLI와 체크포인트 경계를 보완했다. 변경 이유와 계약·시험 연결은 [구현 결정 기록](../../DECISIONS.md)의 D001~D006, 실제 실행·남은 항목은 저장소 루트 IMPLEMENTATION_STATUS.md에 기록한다. 관리자 설정 스키마를 추가하여 현재 계약 스키마는 10개이며, 원본 ZIP 해시 목록은 `validation/MANIFEST.original.json`에 보존했다.
