# 구현계획에 사용한 사전학습자료 선택 인용

이 파일은 2D·3D 시뮬레이터 설계에 직접 사용한 자료의 필요한 부분만 모은 근거집이다. 원문 전체를 복사한 자료집이 아니며, 아래 40개 항목에서 **원문 인용**과 **편집자 해설**을 구분한다. 설계의 실행 규칙은 [01 경기 규칙](01_COMPETITION_RULES.md), 계약은 [02 공통 구조](02_ARCHITECTURE_AND_CONTRACTS.md)와 [05 API](05_SERVER_AND_ROBOT_API.md)를 따른다.

기준 저장소는 `jha68/MAICON`, 브랜치는 main, 고정 커밋은 `7c414445fcf0302620b2c89f16ce2064f91ca753`이다. 모든 줄 번호와 링크는 이 커밋을 가리킨다. 다른 브랜치나 이후 변경 내용은 포함하지 않는다.

PDF 관련 인용은 저장소의 Markdown 변환본에 실린 문구를 그대로 뽑았으며 원본 PDF의 해당 쪽수를 절 이름으로 함께 표시했다. 멘토링 인용은 저장소의 요약본 문장이다. 영상 발언의 축어록 또는 운영사무국 게시판 원문으로 취급하지 않는다. 표는 필요한 행만 선택했으며, 선택 범위가 떨어져 있으면 별도 출처와 인용 블록으로 나눴다.

인용 블록의 Markdown 기호·철자·공백은 원문대로 보존했다. 부연·권고·가정은 인용 밖의 편집자 해설에만 썼다.

## 자료 목록

| 약호 | 고정 커밋의 자료 | 자료 성격 |
| --- | --- | --- |
| A | [PARTICIPANT_API_GUIDE.md](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PARTICIPANT_API_GUIDE.md) | API 안내 HTML 변환본 |
| P1 | [PRESTUDY_1_2026.md](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PRESTUDY_1_2026.md) | 1차 사전교육 PDF 변환본 |
| P2 | [PRESTUDY_2_2026.md](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PRESTUDY_2_2026.md) | 2차 사전교육 PDF 변환본 |
| M2 | [MENTORING_2_SUMMARY.md](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/mentoring/MENTORING_2_SUMMARY.md) | 2차 멘토링 요약본 |
| M3 | [MENTORING_3_SUMMARY.md](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/mentoring/MENTORING_3_SUMMARY.md) | 3차 멘토링 요약본 |

## 선택 근거

### E01 API 자료의 기준 날짜와 원본 우선순위

원문 인용 · API 안내 HTML 변환본 · `docs/materials/PARTICIPANT_API_GUIDE.md` · **참가팀 단계별 API 안내 / 머리말** · [L3](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PARTICIPANT_API_GUIDE.md#L3)

<!-- source-excerpt path="docs/materials/PARTICIPANT_API_GUIDE.md" start="3" end="3" -->
```text
2026 국방AI경진대회 본선 · 참가팀용 · **2026-11-04 기준**
```

원문 인용 · API 안내 HTML 변환본 · `docs/materials/PARTICIPANT_API_GUIDE.md` · **부록 — 오류 · 섹터 · 객체 · 리허설 / 알아 둘 것** · [L948](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PARTICIPANT_API_GUIDE.md#L948)

<!-- source-excerpt path="docs/materials/PARTICIPANT_API_GUIDE.md" start="948" end="948" -->
```text
근거 — 경기 룰북 · SERVER ↔ UGV 통신 규약(2026-11-04 정리판) · 경기운영 서버 코드(2026-11-04 대조, 예시 응답은 시험용 임시 DB에서 실제로 받은 것을 줄인 것). 이 파일은 2026-11-04 기준 스냅숏이며 이후 바뀐 내용은 위 두 문서가 원본입니다.
```

편집자 해설: 2026-11-04 프로필을 보존하고, 현장 최종 규약은 별도 버전으로 반영한다. 이 계획을 최종 대회 규정이라고 표시하지 않는다.

설계 반영: [01 문서](01_COMPETITION_RULES.md), [09 문서](09_FIELD_ADAPTER_AND_QUESTIONS.md).

### E02 OT에서 최종 API 재배포

원문 인용 · 3차 멘토링 요약본 · `docs/mentoring/MENTORING_3_SUMMARY.md` · **질의응답** · [L140](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/mentoring/MENTORING_3_SUMMARY.md#L140)

<!-- source-excerpt path="docs/mentoring/MENTORING_3_SUMMARY.md" start="140" end="140" -->
```text
**53:28~54:00 문서 변경 안내:** 네트워크 최적화를 위해 API 내용이나 일부 절차가 바뀔 수 있으며, 사전 자료를 최종본으로 보지 말라고 명시했다. 실제 임무는 **본선 오리엔테이션 당일 다시 제공하는 최종 API 문서**를 기준으로 수행해야 한다.
```

편집자 해설: API·절차가 바뀔 수 있으므로 HTTP 변환 계층과 핵심 임무 로직을 분리한다. 이 구절은 영상 발언 자체의 새 전사가 아니라 저장소 멘토링 요약본 인용이다.

설계 반영: [01 문서](01_COMPETITION_RULES.md), [05 문서](05_SERVER_AND_ROBOT_API.md), [09 문서](09_FIELD_ADAPTER_AND_QUESTIONS.md).

### E03 과거 M1 예시와 현재 제출 키의 충돌

원문 인용 · 1차 사전교육 PDF 변환본 · `docs/materials/PRESTUDY_1_2026.md` · **11쪽 · M1 전술명령 해석** · [L150–L154](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PRESTUDY_1_2026.md#L150-L154)

<!-- source-excerpt path="docs/materials/PRESTUDY_1_2026.md" start="150" end="154" -->
```text
{
  "target": "RADAR_FACILITY",
  "sectors": ["CHARLIE", "DELTA"],
  "goal_base": "SUPPLY_BASE"
}
```

원문 인용 · API 안내 HTML 변환본 · `docs/materials/PARTICIPANT_API_GUIDE.md` · **5. M1 명령 해석 보고 / 요청 필드** · [L394–L396](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PARTICIPANT_API_GUIDE.md#L394-L396)

<!-- source-excerpt path="docs/materials/PARTICIPANT_API_GUIDE.md" start="394" end="396" -->
```text
| `target` | 지정표적 **보고값** — 예 `RED_RADAR`(아래 표). **명칭(「레이더시설」)은 받지 않습니다**(422) |
| `search_sectors` | 탐색 섹터 이름 **목록** — 예 `["R-S1", "CM"]`(부록 7구역). 순서는 보지 않고, 빠지거나 더 있으면 틀립니다 |
| `base` | 목표거점 **보고값** — 예 `RED_SUPPLY_DEPOT`(아래 표). 명칭은 받지 않습니다(422) |
```

편집자 해설: 과거 RADAR_FACILITY/sectors/goal_base 예시를 현재 제출 계약으로 사용하지 않는다. 현재 target/search_sectors/base와 진영을 포함한 시설 코드로 검증한다.

설계 반영: [01 문서](01_COMPETITION_RULES.md), [05 문서](05_SERVER_AND_ROBOT_API.md), [07 문서](07_TESTS_AND_ACCEPTANCE.md).

### E04 초기 M4 평가 표현과 현재 배점의 충돌

원문 인용 · 1차 사전교육 PDF 변환본 · `docs/materials/PRESTUDY_1_2026.md` · **14쪽 · M4 상대 UGV 타격** · [L202–L203](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PRESTUDY_1_2026.md#L202-L203)

<!-- source-excerpt path="docs/materials/PRESTUDY_1_2026.md" start="202" end="203" -->
```text
- **원문 평가방식:** UGV 유효타격 누적.
- UGV 수광센서에 **2초 이상 연속 감지**되면 1회 유효피격.
```

원문 인용 · API 안내 HTML 변환본 · `docs/materials/PARTICIPANT_API_GUIDE.md` · **8. M4 상대 UGV 타격** · [L603](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PARTICIPANT_API_GUIDE.md#L603)

<!-- source-excerpt path="docs/materials/PARTICIPANT_API_GUIDE.md" start="603" end="603" -->
```text
상대 UGV를 레이저로 맞히고, 우리 UGV는 덜 맞도록 움직입니다. **참가팀이 API로 보고하는 것은 없습니다** — 맞은 UGV의 주최측 장치(ESP)가 판정합니다. 배점 **15** — 경기 끝에 **우리 UGV가 맞은 횟수**로 정합니다.
```

원문 인용 · API 안내 HTML 변환본 · `docs/materials/PARTICIPANT_API_GUIDE.md` · **8. M4 상대 UGV 타격 / 점수 — 우리 UGV가 맞은 횟수** · [L607–L609](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PARTICIPANT_API_GUIDE.md#L607-L609)

<!-- source-excerpt path="docs/materials/PARTICIPANT_API_GUIDE.md" start="607" end="609" -->
```text
| 유효피격 | 0회 | 1회 | 2회 | 3회 | 4회 이상 |
| --- | --- | --- | --- | --- | --- |
| M4 점수 | 15 | 12 | 8 | 3 | 0 |
```

편집자 해설: M4는 우리 유효피격 수에 따른 생존 점수로 구현한다. 공격자에게 명중 가점을 추가하지 않는다. 같은 사실을 두 독립 규칙으로 동시에 적용하지 않는다.

설계 반영: [01 문서](01_COMPETITION_RULES.md), [03 문서](03_PLAN_2D.md), [07 문서](07_TESTS_AND_ACCEPTANCE.md).

### E05 노트북 역할 그림과 실제 임무 실행 위치

원문 인용 · 1차 사전교육 PDF 변환본 · `docs/materials/PRESTUDY_1_2026.md` · **6쪽 · 명령 / 제어 / 데이터 흐름** · [L81](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PRESTUDY_1_2026.md#L81)

<!-- source-excerpt path="docs/materials/PRESTUDY_1_2026.md" start="81" end="81" -->
```text
| 임무용 노트북 | 임무코드 실행, AI모델 실행, 경로설정·모니터링, LLM 연동 |
```

원문 인용 · 2차 멘토링 요약본 · `docs/mentoring/MENTORING_2_SUMMARY.md` · **질의응답** · [L82](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/mentoring/MENTORING_2_SUMMARY.md#L82)

<!-- source-excerpt path="docs/mentoring/MENTORING_2_SUMMARY.md" start="82" end="82" -->
```text
| 38:52–39:50 | 외부 PC가 처리한 결과로 로봇을 제어할 수 있는가 | 불가. 노트북은 실행·디버깅 용도이고 임무 처리는 UGV에서 수행. 외부 LLM API는 예외적으로 허용. |
```

원문 인용 · 2차 멘토링 요약본 · `docs/mentoring/MENTORING_2_SUMMARY.md` · **질의응답** · [L92](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/mentoring/MENTORING_2_SUMMARY.md#L92)

<!-- source-excerpt path="docs/mentoring/MENTORING_2_SUMMARY.md" start="92" end="92" -->
```text
| 46:28–46:56 | LLM API를 외부 PC에서 호출한 뒤 결과만 보내도 되는가 | 불가. **API 호출 자체도 UGV 내부에서** 수행해야 함. |
```

편집자 해설: 데스크톱에서 개발용 시뮬레이션을 실행할 수 있지만, 실제 경기의 임무 처리·LLM 호출 주체는 UGV로 연결한다. 초기 도식의 노트북 역할을 외부 실시간 제어 허용으로 확대하지 않는다.

설계 반영: [02 문서](02_ARCHITECTURE_AND_CONTRACTS.md), [08 문서](08_BUILD_AND_HANDOFF.md), [09 문서](09_FIELD_ADAPTER_AND_QUESTIONS.md).

### E06 문서에 남아 있는 미확정 항목

원문 인용 · API 안내 HTML 변환본 · `docs/materials/PARTICIPANT_API_GUIDE.md` · **부록 — 오류 · 섹터 · 객체 · 리허설 / 아직 정하지 않은 것** · [L911–L912](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PARTICIPANT_API_GUIDE.md#L911-L912)

<!-- source-excerpt path="docs/materials/PARTICIPANT_API_GUIDE.md" start="911" end="912" -->
```text
- M1·M3·M6 JSON 형식 확정 · 주최측 LLM API 주소·키 안내
- M6 동점 · M5 센서 앞에 머물러야 하는 시간
```

편집자 해설: M1/M3/M6 스키마·LLM 주소·키·M6 동점·M5 체류시간의 확정 수준을 구분한다. 공백은 SIM 가정으로 명시하고 대회 확정 사실로 포장하지 않는다.

설계 반영: [01 문서](01_COMPETITION_RULES.md), [05 문서](05_SERVER_AND_ROBOT_API.md), [09 문서](09_FIELD_ADAPTER_AND_QUESTIONS.md).

### E07 경기 구성과 데이터 흐름의 책임

원문 인용 · 1차 사전교육 PDF 변환본 · `docs/materials/PRESTUDY_1_2026.md` · **4쪽 · 대회방식** · [L43–L49](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PRESTUDY_1_2026.md#L43-L49)

<!-- source-excerpt path="docs/materials/PRESTUDY_1_2026.md" start="43" end="49" -->
```text
| 참가 규모 | 총 10개 팀, 팀당 5명, 총 50명 |
| 경기 구성 | 경기당 6개 팀: BLUE 3팀 대 RED 3팀 |
| 경기시간 | 5분 |
| 전체 경기 | 총 10경기 |
| 팀별 출전 | 총 6경기, BLUE 3회 / RED 3회 |
| 경기 운영 | 시작 후 자율 임무 수행: 자율주행·객체인식·주요시설 타격·UGV 타격·상황보고 등 |
| 연속 출전 | 최대 2경기, 3경기 연속 출전 금지 |
```

원문 인용 · API 안내 HTML 변환본 · `docs/materials/PARTICIPANT_API_GUIDE.md` · **한눈에 보기 / 경기 흐름도 — 단계마다 누가 무엇을 주고받나** · [L39](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PARTICIPANT_API_GUIDE.md#L39)

<!-- source-excerpt path="docs/materials/PARTICIPANT_API_GUIDE.md" start="39" end="39" -->
```text
**실선** = 보냄 — **분홍**은 참가팀 프로그램이, **초록**은 주최측이 보냅니다 · **점선** = 서버의 응답 · **빨강** = 레이저 · 회색 상자 = 장치·서버의 판정. 서버는 먼저 보내지 않으므로 **참가팀이 요청해야 받습니다**. **M2·M4는 참가팀이 API로 보고하지 않고** 장치가 판정합니다. API 경로는 모두 `/api/report/` 아래이고 `mission_code`를 함께 보냅니다 · 로봇이 받는 시작·일시정지·보고 신호와 주행·발사는 **젯슨 API 규격서**를 따릅니다. 왼쪽 단계 이름을 누르면 그 장으로 넘어갑니다.
```

편집자 해설: 기본 fixture는 6개 로봇과 3대3이다. 참가팀은 임무를 pull하고 장치 판정과 참가팀 보고의 경로를 분리한다. 전체 대진 편성은 단일 경기 엔진과 독립한다.

설계 반영: [01 문서](01_COMPETITION_RULES.md), [02 문서](02_ARCHITECTURE_AND_CONTRACTS.md), [05 문서](05_SERVER_AND_ROBOT_API.md).

### E08 정상 경기 시간표

원문 인용 · API 안내 HTML 변환본 · `docs/materials/PARTICIPANT_API_GUIDE.md` · **한눈에 보기 / 시간 — 미리 알려 드립니다** · [L69–L74](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PARTICIPANT_API_GUIDE.md#L69-L74)

<!-- source-excerpt path="docs/materials/PARTICIPANT_API_GUIDE.md" start="69" end="74" -->
```text
| 시작 신호부터 | 일 |
| --- | --- |
| 0:00 | 경기 시작 · **1차 임무(전술명령) 게시** · UGV 출발(잠금 해제) — 2·3단계 |
| 4:00 | **2차 임무(M5 목표거점) 게시** — 종료 60초 전, 9단계 |
| 5:00 | 진행 끝 → **보고 30초**(M6) — 10·11단계 |
| 5:30 | 보고 끝 — 팀 프로그램 종료 |
```

편집자 해설: 0초 명령, 240초 M5, 300초 진행 종료, 이후 최대30초 보고를 시간 경계 시험으로 만든다.

설계 반영: [01 문서](01_COMPETITION_RULES.md), [02 문서](02_ARCHITECTURE_AND_CONTRACTS.md), [07 문서](07_TESTS_AND_ACCEPTANCE.md).

### E09 서버 수신 마감과 조기 종료

원문 인용 · API 안내 HTML 변환본 · `docs/materials/PARTICIPANT_API_GUIDE.md` · **한눈에 보기 / 공통 규칙** · [L61](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PARTICIPANT_API_GUIDE.md#L61)

<!-- source-excerpt path="docs/materials/PARTICIPANT_API_GUIDE.md" start="61" end="61" -->
```text
- **마감은 서버가 받은 시각 기준**입니다 — 단계가 바뀐 뒤 도착한 보고는 409로 받지 않습니다(5·7·11단계)
```

원문 인용 · API 안내 HTML 변환본 · `docs/materials/PARTICIPANT_API_GUIDE.md` · **한눈에 보기 / 시간은 팀이 잽니다** · [L78–L80](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PARTICIPANT_API_GUIDE.md#L78-L80)

<!-- source-excerpt path="docs/materials/PARTICIPANT_API_GUIDE.md" start="78" end="80" -->
```text
- **서버는 남은 시간을 주지 않습니다** — 로봇이 **시작 신호를 받은 순간부터** 팀 프로그램이 자기 시계로 잽니다
- 경기는 **시작 후 5분 진행**, **4:00에 2차 임무**, 끝나면 **보고 30초**입니다
- **M5 점령이 나오면 5:00 전에 끝날 수 있습니다** — 끝은 팀 시계가 아니라 보고(`report`) 신호로 압니다(10단계)
```

편집자 해설: 클라이언트 전송 시작 시각이 아니라 서버 처리 단계로 제출을 판단한다. 300초를 기다리지 않고 외부 report/phase 전이를 처리한다. pause 동안의 시계 정책은 이 구절에서 정하지 않았다.

설계 반영: [01 문서](01_COMPETITION_RULES.md), [02 문서](02_ARCHITECTURE_AND_CONTRACTS.md), [05 문서](05_SERVER_AND_ROBOT_API.md), [07 문서](07_TESTS_AND_ACCEPTANCE.md).

### E10 초기화 이후 준비완료와 재실행

원문 인용 · API 안내 HTML 변환본 · `docs/materials/PARTICIPANT_API_GUIDE.md` · **1. 준비완료** · [L91](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PARTICIPANT_API_GUIDE.md#L91)

<!-- source-excerpt path="docs/materials/PARTICIPANT_API_GUIDE.md" start="91" end="91" -->
```text
준비 단계가 되면 주최측 경기 노드가 팀 프로그램(`team_node.py`)을 실행합니다. 프로그램은 **모델·필수 센서 초기화가 성공한 뒤** `/me`로 지금 단계를 보고, **임무코드만 실어 준비완료를 보냅니다.** 사람이 누르는 단추가 아닙니다. 안 보내면 그 팀을 빼고 시작할 수 있고, **빠진 경기는 0점**입니다.
```

원문 인용 · API 안내 HTML 변환본 · `docs/materials/PARTICIPANT_API_GUIDE.md` · **1. 준비완료 / 알아 둘 것** · [L175–L176](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PARTICIPANT_API_GUIDE.md#L175-L176)

<!-- source-excerpt path="docs/materials/PARTICIPANT_API_GUIDE.md" start="175" end="176" -->
```text
- 프로그램이 도중에 다시 실행돼도 위 순서대로 `/me`부터 보면 됩니다 — 이미 받아 둔 준비완료는 `ready: true`로 보입니다
- 서버는 「모델이 정말 다 불러졌는지」 알 수 없습니다 — **초기화가 끝난 뒤 보내는 것은 팀이 지킵니다**
```

편집자 해설: 모델·센서 초기화 성공 이후 준비완료를 보내고 재실행 시 서버 상태를 복구한다. 준비완료 성공과 별도의 출발 센서 성공을 동일시하지 않는다.

설계 반영: [01 문서](01_COMPETITION_RULES.md), [02 문서](02_ARCHITECTURE_AND_CONTRACTS.md), [05 문서](05_SERVER_AND_ROBOT_API.md), [07 문서](07_TESTS_AND_ACCEPTANCE.md).

### E11 Long polling과 제어 루프 분리

원문 인용 · API 안내 HTML 변환본 · `docs/materials/PARTICIPANT_API_GUIDE.md` · **2. 임무(전술명령) 받기 / 기다리는 요청 — `wait`** · [L197–L203](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PARTICIPANT_API_GUIDE.md#L197-L203)

<!-- source-excerpt path="docs/materials/PARTICIPANT_API_GUIDE.md" start="197" end="203" -->
```text
| `wait` 생략 · `0` | 바로 답합니다 — 게시 전이면 `accepted: false` |
| `wait=1`~`120` | 게시될 때까지 최대 그 초만큼 기다렸다가, **게시되는 즉시 기다리던 모든 팀에 같은 순간** 돌려줍니다. 이미 게시됐거나 편성 밖이면 바로 답합니다 |

- **최대 120초**입니다 — 그 안에 게시가 없으면 `accepted: false`가 오니 **다시 요청**합니다(같은 요청에는 늘 같은 답)
- **HTTP 클라이언트 타임아웃은 `wait`보다 길게** 잡습니다 — 짧으면 서버가 답하기 전에 클라이언트가 먼저 끊습니다
- 기다리는 동안 응답이 오지 않으므로 **주행·인식 같은 메인 루프를 막지 않게 따로(배경에서)** 기다립니다
- 프로그램이 다시 실행돼 시작 시각을 잃어도, **시작부터 `wait`를 걸어 두면** 게시되는 순간에 받습니다
```

편집자 해설: wait≤120초와 더 긴 HTTP 타임아웃을 구현한다. long poll을 제어 루프에서 기다리지 않고 별도 작업으로 실행한다.

설계 반영: [02 문서](02_ARCHITECTURE_AND_CONTRACTS.md), [05 문서](05_SERVER_AND_ROBOT_API.md), [07 문서](07_TESTS_AND_ACCEPTANCE.md).

### E12 M1 LLM 활용과 부분 배점

원문 인용 · API 안내 HTML 변환본 · `docs/materials/PARTICIPANT_API_GUIDE.md` · **5. M1 명령 해석 보고** · [L381](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PARTICIPANT_API_GUIDE.md#L381)

<!-- source-excerpt path="docs/materials/PARTICIPANT_API_GUIDE.md" start="381" end="381" -->
```text
2단계에서 받은 명령문을 **주최측 LLM API**(텍스트 LLM만)로 해석해 **지정표적 · 탐색 섹터 · 목표거점**을 보고합니다. 배점 **10** — 지정표적 3 · 탐색 섹터 3 · 목표거점 4. 보고하지 않으면 0점입니다.
```

원문 인용 · API 안내 HTML 변환본 · `docs/materials/PARTICIPANT_API_GUIDE.md` · **5. M1 명령 해석 보고 / 요청 필드** · [L398](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PARTICIPANT_API_GUIDE.md#L398)

<!-- source-excerpt path="docs/materials/PARTICIPANT_API_GUIDE.md" start="398" end="398" -->
```text
`target` · `search_sectors` · `base`를 **모두** 넣습니다 — 빠진 항목은 미보고(그 항목 0점)입니다. 하나도 없으면 422.
```

편집자 해설: M1의3/3/4점 항목 채점과 누락 처리 계약을 구현한다. 제공 텍스트 LLM 어댑터는 stub과 교체 가능하게 하되 stub 성공을 실제 자연어 성능으로 평가하지 않는다.

설계 반영: [01 문서](01_COMPETITION_RULES.md), [05 문서](05_SERVER_AND_ROBOT_API.md), [07 문서](07_TESTS_AND_ACCEPTANCE.md).

### E13 M1 전체 교체와 실제 임무의 분리

원문 인용 · API 안내 HTML 변환본 · `docs/materials/PARTICIPANT_API_GUIDE.md` · **5. M1 명령 해석 보고 / 알아 둘 것** · [L429–L432](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PARTICIPANT_API_GUIDE.md#L429-L432)

<!-- source-excerpt path="docs/materials/PARTICIPANT_API_GUIDE.md" start="429" end="432" -->
```text
- 다시 보내면 **통째로 바뀝니다**(M3와 같다) — 빠뜨린 항목은 지난 값이 남지 않습니다
- 보고값 앞의 진영은 **그 시설이 놓인 진영**입니다 — BLUE 팀이 치는 표적·가는 거점은 `RED_…`
- 정답은 **명령문마다** 주최측이 정합니다 — **지정표적은 그 팀의 M2 지정표적과 같습니다**(명령문에서 읽은 표적이 6단계에서 칠 표적). 탐색 섹터·목표거점은 M3 정찰 구역·M5 목표거점과 다를 수 있습니다
- **진행 중에만** 받습니다 — 마감은 **서버가 받은 시각** 기준이라, 5:00에 보고 단계로 바뀐 뒤 도착하면 409입니다. **마지막 순간에 보내지 말고 미리·자주** 보내세요(다시 보내면 통째로 바뀝니다)
```

편집자 해설: 부분 갱신을 서버에서 병합하지 않는다. M1 지정표적은 M2로 연결하지만 M1 탐색구역·base는 M3 채점구역·M5 목표와 별도 자료형으로 보관한다.

설계 반영: [01 문서](01_COMPETITION_RULES.md), [02 문서](02_ARCHITECTURE_AND_CONTRACTS.md), [05 문서](05_SERVER_AND_ROBOT_API.md), [07 문서](07_TESTS_AND_ACCEPTANCE.md).

### E14 M2 점수 수령자와 최초 파괴

원문 인용 · API 안내 HTML 변환본 · `docs/materials/PARTICIPANT_API_GUIDE.md` · **6. M2 지정표적 타격** · [L484](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PARTICIPANT_API_GUIDE.md#L484)

<!-- source-excerpt path="docs/materials/PARTICIPANT_API_GUIDE.md" start="484" end="484" -->
```text
서버가 팀마다 지정한 **상대 진영 표적 1개**를 레이저로 맞힙니다. **참가팀이 API로 보고하는 것은 없습니다** — 표적 장치가 판정해 서버로 보냅니다. 배점 **15** — 지정표적 유효타격 10 + 연합 세 팀의 지정표적이 모두 성공하면 각 5.
```

원문 인용 · API 안내 HTML 변환본 · `docs/materials/PARTICIPANT_API_GUIDE.md` · **6. M2 지정표적 타격 / 판정 순서** · [L488–L491](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PARTICIPANT_API_GUIDE.md#L488-L491)

<!-- source-excerpt path="docs/materials/PARTICIPANT_API_GUIDE.md" start="488" end="491" -->
```text
1. 표적의 수광부에 **2초 연속** 비추면 표적 장치가 피격으로 판정합니다
2. 판정 결과는 표적 장치가 서버로 보냅니다
3. **누가 쏘든**(상대 팀·아군 오사 포함) 지정표적이 부서지면 **그 표적을 지정받은 팀**의 점수입니다 — 연합 보너스도 같은 방식으로 셉니다
4. 표적은 경기마다 **처음 부서질 때 한 번만** 인정됩니다 — 부서진 표적을 다시 맞혀도 점수가 더 오르지 않습니다
```

편집자 해설: 레이저를 쏜 로봇이 아니라 지정표적을 배정받은 팀에 점수를 준다. 연속2초, 최초파괴1회, 연합15점 구조를 공통 코어에서 처리한다.

설계 반영: [01 문서](01_COMPETITION_RULES.md), [03 문서](03_PLAN_2D.md), [04 문서](04_PLAN_3D.md), [07 문서](07_TESTS_AND_ACCEPTANCE.md).

### E15 M3 완전 일치 채점과 전체 보고

원문 인용 · API 안내 HTML 변환본 · `docs/materials/PARTICIPANT_API_GUIDE.md` · **7. M3 객체 인식 보고** · [L506](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PARTICIPANT_API_GUIDE.md#L506)

<!-- source-excerpt path="docs/materials/PARTICIPANT_API_GUIDE.md" start="506" end="506" -->
```text
카메라로 본 **섹터별 객체 종류·개수**를 보고합니다. 배점 **30** — 상대 진영 3구역 각 7 + 공통 CM 9, 종류·수량 **완전 일치**만. 경기 중 언제든 다시 보낼 수 있고 **마지막 제출**을 채점합니다.
```

원문 인용 · API 안내 HTML 변환본 · `docs/materials/PARTICIPANT_API_GUIDE.md` · **7. M3 객체 인식 보고 / `type` 값 — 객체 6종** · [L527–L536](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PARTICIPANT_API_GUIDE.md#L527-L536)

<!-- source-excerpt path="docs/materials/PARTICIPANT_API_GUIDE.md" start="527" end="536" -->
```text
| 명칭 | `type` | 비고 |
| --- | --- | --- |
| 군용트럭 | `military_truck` |  |
| 박격포 | `mortar` |  |
| 전차 | `tank` | UGV가 아니라 판에 붙은 그림 |
| 미사일 | `missile` |  |
| 탄약상자 | `ammo_box` |  |
| 드럼통 | `drum` |  |

대소문자는 가리지 않습니다(응답에는 대문자로). **6종이 아닌 그림·장애물**(파괴건물·방호벽·야전진지·차단벽 등)은 이 목록에 없습니다.
```

원문 인용 · API 안내 HTML 변환본 · `docs/materials/PARTICIPANT_API_GUIDE.md` · **7. M3 객체 인식 보고 / 알아 둘 것** · [L547–L549](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PARTICIPANT_API_GUIDE.md#L547-L549)

<!-- source-excerpt path="docs/materials/PARTICIPANT_API_GUIDE.md" start="547" end="549" -->
```text
- 다시 보내면 **통째로 바뀝니다** — 빠뜨린 섹터는 지난 값이 남지 않습니다
- **정찰(채점) 구역은 진영으로 고정** — BLUE 팀 `R-S1`·`R-S2`·`R-S3` + `CM`, RED 팀 `B-S1`·`B-S2`·`B-S3` + `CM`. 다른 섹터도 받지만 채점하지 않습니다
- **6종이 아닌 그림·장애물**(파괴건물·방호벽 등)과 블록 겉면은 보고하면 틀립니다
```

편집자 해설: 6개 클래스의 섹터별 개수 벡터를 채점한다. 객체가 붙은 박스 면과 경기 UGV를 구분한다. 재제출 전체 교체·진영별 고정 채점구역도 함께 적용한다.

설계 반영: [01 문서](01_COMPETITION_RULES.md), [02 문서](02_ARCHITECTURE_AND_CONTRACTS.md), [03 문서](03_PLAN_2D.md), [06 문서](06_SCENARIOS_AND_ASSETS.md), [07 문서](07_TESTS_AND_ACCEPTANCE.md).

### E16 M4 피격 무적과 아군 피격

원문 인용 · API 안내 HTML 변환본 · `docs/materials/PARTICIPANT_API_GUIDE.md` · **8. M4 상대 UGV 타격 / 점수 — 우리 UGV가 맞은 횟수** · [L611–L617](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PARTICIPANT_API_GUIDE.md#L611-L617)

<!-- source-excerpt path="docs/materials/PARTICIPANT_API_GUIDE.md" start="611" end="617" -->
```text
목숨 4로 시작해 맞을 때마다 하나씩 줄어듭니다. 경기 끝의 **남은 목숨**으로 맞은 횟수를 셉니다(심판 정정 반영). 서버는 경기 중 점수·목숨을 참가팀 API로 주지 않습니다.

### 판정 — 주최측 장치가 합니다

- 수광부에 **2초 연속** 비춰야 유효피격입니다
- 맞은 뒤 **10초 무적** — 그동안 더 맞아도 세지 않습니다
- **아군이 쏴도** 맞은 것으로 셉니다
```

편집자 해설: HP 기반 채점, 연속2초 피격, 10초 무적, 아군 피격을 적용한다. 여러 레이저의 접촉을 합산하는 세부 방식은 이 인용에 없으므로 SIM-LASER로 따로 정한다.

설계 반영: [01 문서](01_COMPETITION_RULES.md), [03 문서](03_PLAN_2D.md), [04 문서](04_PLAN_3D.md), [07 문서](07_TESTS_AND_ACCEPTANCE.md).

### E17 M5 연합 득점과 별도 연합 보너스

원문 인용 · API 안내 HTML 변환본 · `docs/materials/PARTICIPANT_API_GUIDE.md` · **9. M5 목표거점 받기** · [L625](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PARTICIPANT_API_GUIDE.md#L625)

<!-- source-excerpt path="docs/materials/PARTICIPANT_API_GUIDE.md" start="625" end="625" -->
```text
**종료 60초 전**에 진영별 목표거점 한 곳이 게시됩니다. 2단계와 같은 방식으로 **팀이 요청해서 받습니다.** 그 거점에 **가장 먼저 들어간 연합**이 M5 점수를 받고, **점령하는 순간 진행이 끝납니다**(10단계). 배점 **10** — 점령한 연합의 세 팀이 각 10(점령한 팀 몫이 따로 있지 않습니다). 경기가 끝나면 두 연합의 합계를 비교해 **이긴 연합 세 팀이 각 5**(연합 승리 — 무승부면 양쪽 모두 5)를 더 받습니다.
```

편집자 해설: 점령 연합3팀 각10점과 연합승리5점을 분리한다. 이 문장은 연합합계의 정확한 구성 항목까지 열거하지 않으므로 합계 범위는 SIM-ALLIANCE 가정으로 관리한다.

설계 반영: [01 문서](01_COMPETITION_RULES.md), [02 문서](02_ARCHITECTURE_AND_CONTRACTS.md), [07 문서](07_TESTS_AND_ACCEPTANCE.md).

### E18 M5 센서 신원 미구분과 동시 점령

원문 인용 · API 안내 HTML 변환본 · `docs/materials/PARTICIPANT_API_GUIDE.md` · **9. M5 목표거점 받기 / 점령 판정 — 거점 센서** · [L706–L711](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PARTICIPANT_API_GUIDE.md#L706-L711)

<!-- source-excerpt path="docs/materials/PARTICIPANT_API_GUIDE.md" start="706" end="711" -->
```text
- 진입은 **거점마다 달린 센서**가 판정합니다 — 참가팀은 보고하지 않습니다
- 게시(4:00) 뒤 목표거점의 센서가 **처음 가려지는 순간**, 그 거점을 목표로 받은 **연합의 점령**입니다 → 진행이 끝나고 보고 단계(10단계)
- **센서는 어느 UGV가 들어왔는지 모릅니다** — 상대 연합의 목표거점이 된 **우리 거점에 우리 UGV가 다시 들어가도 상대 연합의 점령**입니다
- 목표가 아닌 거점에 들어가면 점령이 아닙니다 — 아무 UGV도 멈추지 않고 경기는 계속되며, 점수도 없습니다
- 두 연합이 거의 동시에 들어오면 **센서가 감지한 시각이 이른 쪽**의 점령입니다 — 그 차이가 센서 시각 오차(약 10 ms) 안이면 서버에 먼저 도착한 쪽입니다
- 센서 앞에 머물러야 하는 시간은 아직 정하지 않았습니다 — 지금은 **가려지는 순간** 점령입니다
```

편집자 해설: 자기 진영 로봇의 재진입도 상대 점령을 만들 수 있다. 거점 중심 도달 대신 센서 가림을 판정한다. 게시전 점유·고정틱 tie-break는 원문에 없는 구현 가정이다.

설계 반영: [01 문서](01_COMPETITION_RULES.md), [03 문서](03_PLAN_2D.md), [04 문서](04_PLAN_3D.md), [07 문서](07_TESTS_AND_ACCEPTANCE.md).

### E19 보고 전이 순서와 최대 30초

원문 인용 · API 안내 HTML 변환본 · `docs/materials/PARTICIPANT_API_GUIDE.md` · **10. 경기 종료 / 순서** · [L730–L732](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PARTICIPANT_API_GUIDE.md#L730-L732)

<!-- source-excerpt path="docs/materials/PARTICIPANT_API_GUIDE.md" start="730" end="732" -->
```text
1. 진행이 끝나면 서버가 **먼저** `/api/report/me`의 `phase`를 `"reporting"`(보고)으로 바꾸고, 그다음 로봇에 보고(`report`) 신호를 보냅니다
2. 로봇이 `/mil/match`로 **`report`**(경기 끝)를 알리면 11단계 M6를 보냅니다 — 로봇 쪽 처리는 젯슨 API 규격서를 따릅니다
3. 보고 시간이 끝나면 `phase`가 `"finished"`(종료)가 되고 주최측이 팀 프로그램을 종료합니다
```

원문 인용 · API 안내 HTML 변환본 · `docs/materials/PARTICIPANT_API_GUIDE.md` · **10. 경기 종료 / 보고 단계 확인** · [L736–L738](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PARTICIPANT_API_GUIDE.md#L736-L738)

<!-- source-excerpt path="docs/materials/PARTICIPANT_API_GUIDE.md" start="736" end="738" -->
```text
- **`report` = 경기 끝**입니다. 일시정지 `pause`는 경기 중 잠깐 멈춤(주최측과의 통신이 끊겼을 때 등 — 이어서 재개나 `report`가 옵니다)이라 M6를 보내지 않습니다 2026-10-27
- 서버 `GET /api/report/me`의 `phase`가 `"reporting"`인지로도 알 수 있습니다 — 보고 단계가 아니면 서버가 M6를 409로 받지 않습니다
- **M5 점령이 나오면 5:00 전에 끝날 수 있습니다** — 팀 시계로 5:00을 기다리지 말고 `report` 신호로 압니다
```

원문 인용 · API 안내 HTML 변환본 · `docs/materials/PARTICIPANT_API_GUIDE.md` · **10. 경기 종료 / 지킬 것** · [L742–L745](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PARTICIPANT_API_GUIDE.md#L742-L745)

<!-- source-excerpt path="docs/materials/PARTICIPANT_API_GUIDE.md" start="742" end="745" -->
```text
- **경기 종료는 `/me`의 `phase`로 압니다** — `"running"`에서 `"reporting"`으로 바뀐 때
- 이때부터 **M1·M3는 받지 않습니다**(409). 받는 것은 11단계 M6뿐입니다
- M6 보고 시간은 **30초**입니다. 남은 시간은 따로 알려 주지 않습니다 — **서버가 보고 단계로 바꾼 순간부터** 셉니다. 여섯 팀이 다 내면 바로 끝납니다
- 보고 시간이 끝나면 팀 프로그램이 끝나므로 **그 뒤에는 보고가 나가지 않습니다**
```

편집자 해설: 서버 reporting이 먼저이고 로봇 report가 뒤따른다. pause를 report와 구분한다. 6팀이 모두 제출하면 보고창이 일찍 닫히므로 마지막 필요한 제출은 저장·ACK 후 종료한다.

설계 반영: [01 문서](01_COMPETITION_RULES.md), [02 문서](02_ARCHITECTURE_AND_CONTRACTS.md), [05 문서](05_SERVER_AND_ROBOT_API.md), [07 문서](07_TESTS_AND_ACCEPTANCE.md).

### E20 M6 실제 위험도와 동점 설명

원문 인용 · API 안내 HTML 변환본 · `docs/materials/PARTICIPANT_API_GUIDE.md` · **11. M6 위험도 보고** · [L787](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PARTICIPANT_API_GUIDE.md#L787)

<!-- source-excerpt path="docs/materials/PARTICIPANT_API_GUIDE.md" start="787" end="787" -->
```text
경기가 끝난 뒤 **상대 세 팀의 위협도 1·2·3순위**를 보고합니다. 배점 **15** — 셋 다 일치 15 · 1순위만 10 · 2·3순위 중 하나 5. 서버 정답은 **상대 세 팀의 위험도가 높은 순**입니다 — **위험도 = 남은 목숨/4 + 남은 탄/8 + M3 점수/30**(셋이 같은 무게, 0 밑으로 내려가지 않음). 여섯 팀이 다 내면 보고 시간이 바로 끝납니다.
```

원문 인용 · API 안내 HTML 변환본 · `docs/materials/PARTICIPANT_API_GUIDE.md` · **11. M6 위험도 보고 / 알아 둘 것** · [L814–L816](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PARTICIPANT_API_GUIDE.md#L814-L816)

<!-- source-excerpt path="docs/materials/PARTICIPANT_API_GUIDE.md" start="814" end="816" -->
```text
- `R-2`는 **상대 팀 호출부호**입니다 — 섹터 이름은 `R-S2`처럼 `S`가 붙습니다
- 참가팀 API로는 점수를 주지 않습니다(자기 점수도) — 경기 중 관찰(드론 화면·교전·표적 파괴 등)로 팀이 추정합니다
- 동점은 서로 바꿔도 맞음
```

편집자 해설: HP/4+탄약/8+M3/30으로 정답을 계산하고 상대 호출부호 순위만 받는다. 정수 numerator 비교와 동점 순열별 최대 부분점수는 계획에서 정한 구체화이며, 미확정 항목 인용 E06과 함께 읽는다.

설계 반영: [01 문서](01_COMPETITION_RULES.md), [02 문서](02_ARCHITECTURE_AND_CONTRACTS.md), [07 문서](07_TESTS_AND_ACCEPTANCE.md).

### E21 경기 드론과 연습 드론의 차이

원문 인용 · API 안내 HTML 변환본 · `docs/materials/PARTICIPANT_API_GUIDE.md` · **4. 드론 화면 받기 / 요청 두 가지** · [L305–L306](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PARTICIPANT_API_GUIDE.md#L305-L306)

<!-- source-excerpt path="docs/materials/PARTICIPANT_API_GUIDE.md" start="305" end="306" -->
```text
| 경기 | `camera` **없음** | 지금 경기에 **편성된 팀**이 **진행 중**일 때만(그 밖에는 409). 본선 카메라. 우리 진영 시설물(상대 팀의 지정표적)이 **1개 파괴되면 2초 · 2개면 5초** 간격으로만 새 장, **3개면 받을 수 없습니다(403)** |
| 연습 | `camera` **붙임** | 주최측이 **테스트 모드**를 켠 연습 기간에만. 편성·경기와 상관없이 **1초마다 최신 장**, 저하 없음 |
```

원문 인용 · API 안내 HTML 변환본 · `docs/materials/PARTICIPANT_API_GUIDE.md` · **4. 드론 화면 받기 / `camera` 값** · [L316–L317](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PARTICIPANT_API_GUIDE.md#L316-L317)

<!-- source-excerpt path="docs/materials/PARTICIPANT_API_GUIDE.md" start="316" end="317" -->
```text
- **연습 기간 테스트는 `camera`를 반드시 붙입니다.** 안 붙이면 테스트 모드여도 경기 요청으로 보고 편성·진행을 확인합니다 — 경기 밖이면 409
- **경기 때는 `camera`를 빼고 부르세요.** 테스트 모드가 꺼져 있으면 `camera`는 무시되고 경기 규칙이 적용됩니다
```

편집자 해설: 경기에서는 camera를 생략하고 자기 시설 파괴 수에 따라 2초·5초·403을 적용한다. 테스트 모드의 연습 요청을 경기 조건과 혼동하지 않는다.

설계 반영: [01 문서](01_COMPETITION_RULES.md), [04 문서](04_PLAN_3D.md), [05 문서](05_SERVER_AND_ROBOT_API.md), [07 문서](07_TESTS_AND_ACCEPTANCE.md).

### E22 드론 반복 프레임과 캡처 시간

원문 인용 · API 안내 HTML 변환본 · `docs/materials/PARTICIPANT_API_GUIDE.md` · **4. 드론 화면 받기 / 알아 둘 것** · [L321–L323](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PARTICIPANT_API_GUIDE.md#L321-L323)

<!-- source-excerpt path="docs/materials/PARTICIPANT_API_GUIDE.md" start="321" end="323" -->
```text
- **깨진 화면은 주지 않습니다** — 영상이 깨지면 다음 정상 화면까지(몇 초) 마지막 정상 화면이 옵니다. `X-Captured-At`으로 찍힌 시각을 확인하세요
- 1초보다 자주 불러도 새 장이 더 빨리 나오지는 않습니다
- 점수와 직접 관계는 없고, 판단(M6 등)에 쓰고 싶은 팀이 씁니다
```

원문 인용 · API 안내 HTML 변환본 · `docs/materials/PARTICIPANT_API_GUIDE.md` · **4. 드론 화면 받기 / 응답 머리** · [L358–L359](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PARTICIPANT_API_GUIDE.md#L358-L359)

<!-- source-excerpt path="docs/materials/PARTICIPANT_API_GUIDE.md" start="358" end="359" -->
```text
| `X-Captured-At` | 그 장의 캡처 시각 — 한국 시간 `+09:00` |
| `X-Frame-Interval-S` | 지금 새 장이 나오는 간격(초) — `1.0` · `2.0` · `5.0` |
```

편집자 해설: 같은 정상 JPEG가 반복될 때 새 관측으로 누적하지 않는다. 응답 수신시각과 X-Captured-At을 분리하고 stale-frame 시험을 만든다.

설계 반영: [02 문서](02_ARCHITECTURE_AND_CONTRACTS.md), [04 문서](04_PLAN_3D.md), [05 문서](05_SERVER_AND_ROBOT_API.md), [07 문서](07_TESTS_AND_ACCEPTANCE.md).

### E23 리허설 요청 형식과 드론 경로

원문 인용 · API 안내 HTML 변환본 · `docs/materials/PARTICIPANT_API_GUIDE.md` · **부록 — 오류 · 섹터 · 객체 · 리허설 / 창구 — 주소 앞부분만 바꿉니다** · [L918](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PARTICIPANT_API_GUIDE.md#L918)

<!-- source-excerpt path="docs/materials/PARTICIPANT_API_GUIDE.md" start="918" end="918" -->
```text
운영자가 리허설을 켜 두면 참가팀 포털 › **테스트 대시보드**(운영진이 열어 둔 때에만 보입니다)에서 **「리허설 준비」 → 「시작」**으로 **경기와 같은 조건의 한 판**을 엽니다(점수 없음). 팀 코드는 창구 주소 앞부분만 `/api/report` → `/api/rehearsal`로 바꿔 부릅니다 — **요청·응답 형식은 같습니다**.
```

원문 인용 · API 안내 HTML 변환본 · `docs/materials/PARTICIPANT_API_GUIDE.md` · **부록 — 오류 · 섹터 · 객체 · 리허설 / 창구 — 주소 앞부분만 바꿉니다** · [L930](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PARTICIPANT_API_GUIDE.md#L930)

<!-- source-excerpt path="docs/materials/PARTICIPANT_API_GUIDE.md" start="930" end="930" -->
```text
임무코드도 경기 때와 같이 싣습니다(GET은 `?mission_code=`, POST는 본문). 드론 화면은 리허설 창구에 없습니다 — 연습용 카메라는 4단계의 `camera` 요청을 씁니다.
```

편집자 해설: 리허설은 같은 형식을 다른 접두사로 사용한다. 존재하지 않는 /api/rehearsal/drone을 공식 창구처럼 구현하지 않는다.

설계 반영: [01 문서](01_COMPETITION_RULES.md), [05 문서](05_SERVER_AND_ROBOT_API.md), [07 문서](07_TESTS_AND_ACCEPTANCE.md).

### E24 M2 표적 이미지와 임의 배치

원문 인용 · 1차 사전교육 PDF 변환본 · `docs/materials/PRESTUDY_1_2026.md` · **12쪽 · M2 지정표적 타격** · [L167–L168](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PRESTUDY_1_2026.md#L167-L168)

<!-- source-excerpt path="docs/materials/PRESTUDY_1_2026.md" start="167" end="168" -->
```text
- 사전 제공 데이터와 동일한 표적 이미지 사용.
- 위치는 임의 배치하며, 정육면체 장애물 박스의 측면 한 면에 부착. 양 진영의 대칭되는 동일 위치 조건으로 배치.
```

편집자 해설: 동일 이미지 사용과 동일 위치 사용은 다르다. 시설 이미지 자산과 배치 manifest를 분리한다.

설계 반영: [03 문서](03_PLAN_2D.md), [04 문서](04_PLAN_3D.md), [06 문서](06_SCENARIOS_AND_ASSETS.md).

### E25 M3 박스 면과 이미지 변경

원문 인용 · 1차 사전교육 PDF 변환본 · `docs/materials/PRESTUDY_1_2026.md` · **13쪽 · M3 전장객체 인식** · [L185–L187](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PRESTUDY_1_2026.md#L185-L187)

<!-- source-excerpt path="docs/materials/PRESTUDY_1_2026.md" start="185" end="187" -->
```text
- 위치와 수량은 섹터별 임의 배치.
- 정육면체 장애물 박스의 측면 4면에 배치, 각 면에는 객체 한 개.
- 클래스 6종은 같지만 실제 이미지는 변경될 수 있음.
```

편집자 해설: 3D 모델의 박스 면에 이미지 자산을 부착한다. 같은 면 재관측 중복과 다른 면의 동일 클래스는 구분하고, 학습·검증 원본 이미지를 분리한다.

설계 반영: [03 문서](03_PLAN_2D.md), [04 문서](04_PLAN_3D.md), [06 문서](06_SCENARIOS_AND_ASSETS.md), [07 문서](07_TESTS_AND_ACCEPTANCE.md).

### E26 M6의 비공개 정답 상태

원문 인용 · 1차 사전교육 PDF 변환본 · `docs/materials/PRESTUDY_1_2026.md` · **16쪽 · M6 전장 위험도 분석** · [L246–L249](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PRESTUDY_1_2026.md#L246-L249)

<!-- source-excerpt path="docs/materials/PRESTUDY_1_2026.md" start="246" end="249" -->
```text
- **정답 기준:** 각 UGV의 생존점수·잔여탄약·객체인식점수로 상대 위험도 순위를 산정해 제출 결과와 비교.
- 상대 생존점수·잔여탄약·객체인식점수는 **비공개**.
- 고정정찰 UAV 영상, UGV 카메라·LiDAR, 경기 중 획득한 정보 등을 관측에 사용.
- 가장 위협적인 상대 UGV를 선정하고 JSON으로 서버 전송.
```

편집자 해설: 운영자 truth와 참가팀 observation을 분리한다. 실제 HP·탄약·M3점수를 참가팀 SDK에 직접 넘겨 추정 과제를 없애지 않는다.

설계 반영: [02 문서](02_ARCHITECTURE_AND_CONTRACTS.md), [04 문서](04_PLAN_3D.md), [07 문서](07_TESTS_AND_ACCEPTANCE.md).

### E27 경기장과 통로의 크기 및 참고 이미지

원문 인용 · 1차 사전교육 PDF 변환본 · `docs/materials/PRESTUDY_1_2026.md` · **23쪽 · 대회 경기장 사양** · [L371](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PRESTUDY_1_2026.md#L371)

<!-- source-excerpt path="docs/materials/PRESTUDY_1_2026.md" start="371" end="371" -->
```text
| 크기 | 약 612cm(가로) × 500cm(세로) × 40cm(높이) |
```

원문 인용 · 1차 사전교육 PDF 변환본 · `docs/materials/PRESTUDY_1_2026.md` · **23쪽 · 대회 경기장 사양** · [L375–L376](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PRESTUDY_1_2026.md#L375-L376)

<!-- source-excerpt path="docs/materials/PRESTUDY_1_2026.md" start="375" end="376" -->
```text
| 장애물 | 정육면체 박스 40cm × 40cm × 40cm |
| 벽면 | 높이 40cm, 프로파일 + 포맥스 |
```

원문 인용 · 1차 사전교육 PDF 변환본 · `docs/materials/PRESTUDY_1_2026.md` · **23쪽 · 대회 경기장 사양** · [L381](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PRESTUDY_1_2026.md#L381)

<!-- source-excerpt path="docs/materials/PRESTUDY_1_2026.md" start="381" end="381" -->
```text
원문 경기장 이미지는 참고용이며 실제 경기장과 다를 수 있습니다.
```

원문 인용 · 1차 사전교육 PDF 변환본 · `docs/materials/PRESTUDY_1_2026.md` · **24쪽 · 경기장 구역 · 바닥 구성** · [L394–L396](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PRESTUDY_1_2026.md#L394-L396)

<!-- source-excerpt path="docs/materials/PRESTUDY_1_2026.md" start="394" end="396" -->
```text
| 트랙 표시 | 섹터 경계선, 중앙선, 거점 진입구역을 바닥 그래픽으로 명확히 구분 |
| 바닥 격자 | 가로·세로 20cm 기준 |
| 이동공간 | 박스 간 또는 박스·벽체 간 최소 40cm 이상 |
```

편집자 해설: 6.12×5m,0.4m 박스·벽을 초기 형상으로 사용한다. 정확한 섹터 폭·거점 띠·박스 좌표는 공개 그림을 실측한 값이 아니므로 fixture 가정으로 분리한다.

설계 반영: [03 문서](03_PLAN_2D.md), [04 문서](04_PLAN_3D.md), [06 문서](06_SCENARIOS_AND_ASSETS.md).

### E28 스모그와 테스트장 장치 차이

원문 인용 · 1차 사전교육 PDF 변환본 · `docs/materials/PRESTUDY_1_2026.md` · **25쪽 · 미션 이벤트 장치** · [L410–L414](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PRESTUDY_1_2026.md#L410-L414)

<!-- source-excerpt path="docs/materials/PRESTUDY_1_2026.md" start="410" end="414" -->
```text
| 환경효과 | 비인식용 박스 | 파괴건물·방호벽·야전진지·차단벽 등 전장환경 모사 장애물 |
| 환경효과 | 스모그 발생장치 | 포그머신 방식, 경기장 중앙 측면 1개소, 연기량·분출시간 조절 |
| 환경효과 | 이벤트제어장치 | 서버 연동, 원격 ON/OFF, 시간·주기 설정, 비상정지 |

테스트 경기장은 일부 이벤트 장치를 제외합니다. 원문에 출발·목표거점 센서/LED, 지정표적 시그널 LED, 비인식용 장애물, 이벤트제어장치의 사진이 있습니다.
```

편집자 해설: 가림·저대비·센서 누락 fault를 준비하고 실물에서 효과를 재검증한다. 포그머신 설명만으로 LiDAR나 카메라 노이즈의 물리 분포를 확정하지 않는다.

설계 반영: [04 문서](04_PLAN_3D.md), [06 문서](06_SCENARIOS_AND_ASSETS.md), [07 문서](07_TESTS_AND_ACCEPTANCE.md), [09 문서](09_FIELD_ADAPTER_AND_QUESTIONS.md).

### E29 로봇 크기와 소프트웨어 환경 및 배터리

원문 인용 · 2차 사전교육 PDF 변환본 · `docs/materials/PRESTUDY_2_2026.md` · **4쪽 · UGV 하드웨어 · 소프트웨어** · [L46](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PRESTUDY_2_2026.md#L46)

<!-- source-excerpt path="docs/materials/PRESTUDY_2_2026.md" start="46" end="46" -->
```text
| 메인 컴퓨팅 | NVIDIA Jetson Orin Nano 8GB |
```

원문 인용 · 2차 사전교육 PDF 변환본 · `docs/materials/PRESTUDY_2_2026.md` · **4쪽 · UGV 하드웨어 · 소프트웨어** · [L60](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PRESTUDY_2_2026.md#L60)

<!-- source-excerpt path="docs/materials/PRESTUDY_2_2026.md" start="60" end="60" -->
```text
| 크기 | 250(가로) × 230(세로) × 320(높이)mm |
```

원문 인용 · 2차 사전교육 PDF 변환본 · `docs/materials/PRESTUDY_2_2026.md` · **4쪽 · UGV 하드웨어 · 소프트웨어** · [L64–L68](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PRESTUDY_2_2026.md#L64-L68)

<!-- source-excerpt path="docs/materials/PRESTUDY_2_2026.md" start="64" end="68" -->
```text
| OS | Ubuntu 22.04 |
| 미들웨어 | ROS2-HUMBLE-LTS, Docker 기반 |
| 언어 | Python, C++ |
| ROS 실행환경 | ROS2 Docker |
| SLAM / Mapping | Gmapping 2D, Cartographer 2D, RTAB-Map 3D |
```

원문 인용 · 2차 사전교육 PDF 변환본 · `docs/materials/PRESTUDY_2_2026.md` · **6쪽 · 배터리 충전방법 / 배터리 기본 사양** · [L100–L103](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PRESTUDY_2_2026.md#L100-L103)

<!-- source-excerpt path="docs/materials/PRESTUDY_2_2026.md" start="100" end="103" -->
```text
| 사용시간 | 최대 소비전력 기준 약 40분 |
| 충전시간 | 100% 약 3시간 내외, 80% 약 1시간 30분 |

UGV는 **배터리 교체가 아닌 충전 방식**입니다. 준비기간·본선 중 배터리 부족에 따른 별도 교체는 불가합니다. 잔량을 수시로 확인하고 불필요한 AI 연산·Depth 카메라 사용 등 전력 소모를 줄여야 합니다. 모터·Jetson AI 연산·팬틸트 서보·Depth 카메라 사용량과 환경에 따라 운용시간은 달라집니다.
```

편집자 해설: 로봇 외곽 근사와 Ubuntu22.04·ROS2 Humble 연결 경계를 정한다. 나열된 SLAM 이름이 완성 launch/config 제공을 보장하지는 않는다. 약40분 안내값으로 정확한 전력 모델을 만들지 않는다.

설계 반영: [02 문서](02_ARCHITECTURE_AND_CONTRACTS.md), [04 문서](04_PLAN_3D.md), [08 문서](08_BUILD_AND_HANDOFF.md), [09 문서](09_FIELD_ADAPTER_AND_QUESTIONS.md).

### E30 상태·주행·IMU 주기

원문 인용 · 2차 사전교육 PDF 변환본 · `docs/materials/PRESTUDY_2_2026.md` · **10쪽 · UGV ROS2 API 전체** · [L151](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PRESTUDY_2_2026.md#L151)

<!-- source-excerpt path="docs/materials/PRESTUDY_2_2026.md" start="151" end="151" -->
```text
| 상태·경기 | `/mil/state` · `/mil/match` | Subscribe | `hp`, `hp_max`, `battery_pct`(2Hz), `mode`(practice/mission), `cmd` |
```

원문 인용 · 2차 사전교육 PDF 변환본 · `docs/materials/PRESTUDY_2_2026.md` · **10쪽 · UGV ROS2 API 전체** · [L154](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PRESTUDY_2_2026.md#L154)

<!-- source-excerpt path="docs/materials/PRESTUDY_2_2026.md" start="154" end="154" -->
```text
| 주행·위치 | `/cmd_vel` · `/odom` | Pub·Sub | linear.x ±0.6m/s, angular.z ±3rad/s(+좌회전), 명령 10Hz 반복, 위치 20Hz |
```

원문 인용 · 2차 사전교육 PDF 변환본 · `docs/materials/PRESTUDY_2_2026.md` · **10쪽 · UGV ROS2 API 전체** · [L157](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PRESTUDY_2_2026.md#L157)

<!-- source-excerpt path="docs/materials/PRESTUDY_2_2026.md" start="157" end="157" -->
```text
| IMU | `/imu/data` | Subscribe | 자세(쿼터니언 → roll·pitch·yaw), 각속도·가속도, 20Hz |
```

편집자 해설: 상태2Hz·odom20Hz·IMU20Hz·주행명령10Hz를 스케줄러 기본 주기로 설정한다. 각각의 시각·신선도를 보관한다.

설계 반영: [02 문서](02_ARCHITECTURE_AND_CONTRACTS.md), [03 문서](03_PLAN_2D.md), [04 문서](04_PLAN_3D.md), [05 문서](05_SERVER_AND_ROBOT_API.md), [07 문서](07_TESTS_AND_ACCEPTANCE.md).

### E31 상태 QoS와 연습·경기 모드

원문 인용 · 2차 사전교육 PDF 변환본 · `docs/materials/PRESTUDY_2_2026.md` · **11쪽 · API — 상태확인** · [L187–L188](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PRESTUDY_2_2026.md#L187-L188)

<!-- source-excerpt path="docs/materials/PRESTUDY_2_2026.md" start="187" end="188" -->
```text
- QoS: `depth=1`, `TRANSIENT_LOCAL` — 마지막 상태를 바로 받음.
- 연습 모드에는 단계별 잠금이 없지만 피격 후 잠금·재발사 대기는 적용.
```

원문 인용 · 2차 사전교육 PDF 변환본 · `docs/materials/PRESTUDY_2_2026.md` · **12쪽 · API — 경기모드** · [L203–L210](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PRESTUDY_2_2026.md#L203-L210)

<!-- source-excerpt path="docs/materials/PRESTUDY_2_2026.md" start="203" end="210" -->
```text
| 탄약·HP | 자동 회복 | 회복 없음 |
| 주행·조준·발사 | 반복 실습 가능 | `start`·`resume`에서만 |
| 대기·정지·보고 | 잠금 미적용 | 주행 무시, 조준·발사 `locked` |
| 공통 적용 | 발사 간격 10초, 피격 후 잠금, 팬틸트 범위 | 동일 |

- 참가자가 직접 모드를 바꿀 수 없음. `/mil/match`로 확인.
- 일시정지 시 레이저가 꺼지고 모터·팬틸트가 정지.
- 재개 시 자동으로 움직이지 않으므로 주행·팬틸트 명령을 다시 전송.
```

편집자 해설: 상태 구독의 마지막 값 수신, 연습의 HP·탄약 회복, 경기 제어 잠금을 구분한다. 회복 시점과 pause 시계는 별도 SIM 가정이다.

설계 반영: [01 문서](01_COMPETITION_RULES.md), [02 문서](02_ARCHITECTURE_AND_CONTRACTS.md), [05 문서](05_SERVER_AND_ROBOT_API.md), [07 문서](07_TESTS_AND_ACCEPTANCE.md), [09 문서](09_FIELD_ADAPTER_AND_QUESTIONS.md).

### E32 팬틸트 단위와 접수 응답

원문 인용 · 2차 사전교육 PDF 변환본 · `docs/materials/PRESTUDY_2_2026.md` · **14쪽 · API — 팬틸트 제어** · [L253–L256](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PRESTUDY_2_2026.md#L253-L256)

<!-- source-excerpt path="docs/materials/PRESTUDY_2_2026.md" start="253" end="256" -->
```text
| `pan` | 좌우, +오른쪽, 1단위=0.5도 | −100~100 |
| `tilt` | 상하, +위쪽, 1단위=0.15도 | −100~100 |
| `speed` | 이동 속도(도/초) | 1~270 |
| `acc` | 가속도, 권장 20 | 1~254 |
```

원문 인용 · 2차 사전교육 PDF 변환본 · `docs/materials/PRESTUDY_2_2026.md` · **14쪽 · API — 팬틸트 제어** · [L273](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PRESTUDY_2_2026.md#L273)

<!-- source-excerpt path="docs/materials/PRESTUDY_2_2026.md" start="273" end="273" -->
```text
`pan`·`tilt`는 **각도가 아닌 위치값**입니다. `ok`는 목표 도착이 아니라 접수를 뜻합니다.
```

편집자 해설: 팬틸트 명령 위치값을 각도로 변환하고 ok를 즉시 도착으로 취급하지 않는다. 실제 가속도 단위·응답 모델은 별도 보정 대상이다.

설계 반영: [02 문서](02_ARCHITECTURE_AND_CONTRACTS.md), [03 문서](03_PLAN_2D.md), [04 문서](04_PLAN_3D.md), [05 문서](05_SERVER_AND_ROBOT_API.md), [07 문서](07_TESTS_AND_ACCEPTANCE.md).

### E33 주행과 팬틸트 부호 및 watchdog

원문 인용 · 2차 사전교육 PDF 변환본 · `docs/materials/PRESTUDY_2_2026.md` · **15쪽 · API — 주행** · [L284](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PRESTUDY_2_2026.md#L284)

<!-- source-excerpt path="docs/materials/PRESTUDY_2_2026.md" start="284" end="284" -->
```text
위에서 본 UGV 기준으로 `linear.x +`는 앞, `angular.z +`는 좌회전, **팬틸트 `pan +`는 오른쪽**입니다.
```

원문 인용 · 2차 사전교육 PDF 변환본 · `docs/materials/PRESTUDY_2_2026.md` · **15쪽 · API — 주행** · [L300–L303](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PRESTUDY_2_2026.md#L300-L303)

<!-- source-excerpt path="docs/materials/PRESTUDY_2_2026.md" start="300" end="303" -->
```text
- 속도 명령 약 **10Hz** 반복. **0.5초 끊기면 자동 정지**.
- 여러 노드에서 `/cmd_vel` 동시 전송 금지(명령 충돌).
- 충전 케이블을 분리한 뒤 안전한 장소에서 저속 시험.
- `/odom`은 **20Hz**, `qos_profile_sensor_data` 사용.
```

편집자 해설: pan 양수와 yaw 양수의 회전 방향이 다르다. 단일 주행 발행자와0.5초 watchdog, sensor-data QoS를 검증한다.

설계 반영: [02 문서](02_ARCHITECTURE_AND_CONTRACTS.md), [03 문서](03_PLAN_2D.md), [04 문서](04_PLAN_3D.md), [05 문서](05_SERVER_AND_ROBOT_API.md), [07 문서](07_TESTS_AND_ACCEPTANCE.md).

### E34 발광 시간과 재발사 및 공유 탄약

원문 인용 · 1차 사전교육 PDF 변환본 · `docs/materials/PRESTUDY_1_2026.md` · **14쪽 · M4 상대 UGV 타격** · [L207–L208](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PRESTUDY_1_2026.md#L207-L208)

<!-- source-excerpt path="docs/materials/PRESTUDY_1_2026.md" start="207" end="208" -->
```text
- UGV당 탄창 **8발**, 1회 발사 **5초 발광**, 재발사 대기 **5초**. 규정 출력·시간 초과 금지.
- 아군 오사도 유효피격으로 포함.
```

원문 인용 · 2차 사전교육 PDF 변환본 · `docs/materials/PRESTUDY_2_2026.md` · **16쪽 · API — 레이저 발사** · [L307](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PRESTUDY_2_2026.md#L307)

<!-- source-excerpt path="docs/materials/PRESTUDY_2_2026.md" start="307" end="307" -->
```text
파라미터 없이 **`Fire.Request()`**를 보냅니다. 1회 **5초 발광**, 발사 시작 **10초 후 재발사** 가능합니다. 응답의 `left_ms`로 남은 대기를 확인합니다.
```

원문 인용 · 2차 사전교육 PDF 변환본 · `docs/materials/PRESTUDY_2_2026.md` · **16쪽 · API — 레이저 발사** · [L324–L328](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PRESTUDY_2_2026.md#L324-L328)

<!-- source-excerpt path="docs/materials/PRESTUDY_2_2026.md" start="324" end="328" -->
```text
- 경기 모드에서는 탄약·HP가 회복되지 않으므로 발사 타이밍 최적화 필요.
- 피격 시 조준·발사 10초 제한.
- **HP 0이라도 탄약이 있고 다른 제한이 없으면 발사 가능**.
- 일시정지 시 레이저가 꺼지며 재개 뒤 명령을 다시 전송.
- 발사 주기: 0초 발사 → 5초 레이저 꺼짐 → 10초 재발사 가능.
```

원문 인용 · 2차 멘토링 요약본 · `docs/mentoring/MENTORING_2_SUMMARY.md` · **질의응답** · [L90](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/mentoring/MENTORING_2_SUMMARY.md#L90)

<!-- source-excerpt path="docs/mentoring/MENTORING_2_SUMMARY.md" start="90" end="90" -->
```text
| 45:14–45:43 | 지정표적 사격도 8발에서 차감되는가 | 지정표적과 상대 UGV 공격을 **모두 합쳐 8발**. |
```

편집자 해설: 총8발을 M2·M4가 공유한다. 발광5초와 발사시작후10초 재발사를 구분하고, HP0을 영구 발사불가로 구현하지 않는다.

설계 반영: [01 문서](01_COMPETITION_RULES.md), [03 문서](03_PLAN_2D.md), [04 문서](04_PLAN_3D.md), [05 문서](05_SERVER_AND_ROBOT_API.md), [07 문서](07_TESTS_AND_ACCEPTANCE.md).

### E35 RGB 형식과 Depth API 범위

원문 인용 · 2차 사전교육 PDF 변환본 · `docs/materials/PRESTUDY_2_2026.md` · **17쪽 · API — 카메라 · IMU / 카메라 `/image_raw` — `sensor_msgs/Image`** · [L336–L339](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PRESTUDY_2_2026.md#L336-L339)

<!-- source-excerpt path="docs/materials/PRESTUDY_2_2026.md" start="336" end="339" -->
```text
- **640×480, BGR(OpenCV), 최대 30FPS**. CPU 부담 때문에 **10FPS 이하 권장**.
- `CvBridge().imgmsg_to_cv2(msg, 'bgr8')`로 NumPy 배열 변환.
- 팬틸트 카메라 영상이며 **Depth 카메라는 이 토픽이 아님**.
- OpenCV·AI 객체 인식(M3)에 활용.
```

원문 인용 · 3차 멘토링 요약본 · `docs/mentoring/MENTORING_3_SUMMARY.md` · **개발 환경과 ROS 2 API** · [L56](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/mentoring/MENTORING_3_SUMMARY.md#L56)

<!-- source-excerpt path="docs/mentoring/MENTORING_3_SUMMARY.md" start="56" end="56" -->
```text
멘토는 **Depth 카메라에 별도 API를 제공하지 않는다**고 설명했다. 전류 소비가 크므로 임무에 꼭 필요한 경우 사용하고 배터리를 관리해야 한다. 일반 카메라도 모든 프레임을 처리하기보다 팀의 모델 처리 속도에 맞춰 필요한 프레임만 사용해 실시간 성능을 유지하라고 권했다. (27:16~28:10)
```

편집자 해설: 실제 RGB 계약은640×480 BGR이다. 가상 depth·segmentation을 만들더라도 실제 참가팀에 제공되는 확정 API로 취급하지 않는다.

설계 반영: [02 문서](02_ARCHITECTURE_AND_CONTRACTS.md), [04 문서](04_PLAN_3D.md), [05 문서](05_SERVER_AND_ROBOT_API.md), [09 문서](09_FIELD_ADAPTER_AND_QUESTIONS.md).

### E36 팀 노드 실행 수명과 연산 예산

원문 인용 · 2차 사전교육 PDF 변환본 · `docs/materials/PRESTUDY_2_2026.md` · **18쪽 · 팀 노드(`team_node.py`) 수행 기준** · [L375–L381](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PRESTUDY_2_2026.md#L375-L381)

<!-- source-excerpt path="docs/materials/PRESTUDY_2_2026.md" start="375" end="381" -->
```text
| 코드 경로 | `~/team/team_node.py` |
| 실행 시점 | 경기 시작 대기(`standby`)에 운영 프로그램이 자동 실행 |
| 실행 형태 | Python ROS 2 노드, 하위 프로그램은 팀 노드가 실행·관리 |
| 경기 상태 | `/mil/match` 구독 |
| 경기 종료 | `report` 후 `stop` 수신 시 팀 노드 종료 |
| 오류 | 비정상 종료 시 경기당 최대 3회 자동 재실행 |
| 성능 | `step()` 0.1초 이내, AI 추론은 별도 스레드 |
```

편집자 해설: standby 자동실행, report 후 stop 종료, 최대3회 재실행과0.1초 step 조건을 프로그램 수명 시험에 반영한다. 엔진·GUI·추론을 이 제어 루프에서 기다리지 않는다.

설계 반영: [02 문서](02_ARCHITECTURE_AND_CONTRACTS.md), [05 문서](05_SERVER_AND_ROBOT_API.md), [07 문서](07_TESTS_AND_ACCEPTANCE.md), [08 문서](08_BUILD_AND_HANDOFF.md), [09 문서](09_FIELD_ADAPTER_AND_QUESTIONS.md).

### E37 호출부호 식별과 HP0 뒤 동작

원문 인용 · 3차 멘토링 요약본 · `docs/mentoring/MENTORING_3_SUMMARY.md` · **질의응답** · [L131](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/mentoring/MENTORING_3_SUMMARY.md#L131)

<!-- source-excerpt path="docs/mentoring/MENTORING_3_SUMMARY.md" start="131" end="131" -->
```text
| **54:07~54:32, 56:43~57:18** | 안테나 띠 개수와 상대 UGV ID는 어떻게 대응하는가? | RED 진영 예시로 **1줄=R-1, 2줄=R-2, 3줄=R-3**라고 답한다. 제출 시에는 문서의 호출부호 형식을 따른다. |
```

원문 인용 · 3차 멘토링 요약본 · `docs/mentoring/MENTORING_3_SUMMARY.md` · **질의응답** · [L133](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/mentoring/MENTORING_3_SUMMARY.md#L133)

<!-- source-excerpt path="docs/mentoring/MENTORING_3_SUMMARY.md" start="133" end="133" -->
```text
| **57:18~58:08** | 아군 UGV가 기능정지되어도 M6를 제출할 수 있는가? | **가능하다.** 모터·카메라 같은 물리 장치가 정지해도 메인 프로그램 `team_node.py`는 종료되지 않는다고 설명한다. |
```

원문 인용 · 3차 멘토링 요약본 · `docs/mentoring/MENTORING_3_SUMMARY.md` · **질의응답** · [L136](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/mentoring/MENTORING_3_SUMMARY.md#L136)

<!-- source-excerpt path="docs/mentoring/MENTORING_3_SUMMARY.md" start="136" end="136" -->
```text
| **58:55~59:34** | HP4회분을 모두 소진한 뒤 다시 맞으면 어떻게 되는가? | 4회 피격 뒤 **모터를 포함해10초간 기능정지**, 이후 다시 움직일 수 있다. 그 뒤에도 추가 피격 때마다 같은10초 기능정지가 반복된다고 설명한다. |
```

편집자 해설: 안테나 띠와 캠프로 상대 ID를 표현한다. HP0 뒤 재피격 기능정지와 메인프로그램 생존을 구분하여 M6 제출이 남도록 한다.

설계 반영: [01 문서](01_COMPETITION_RULES.md), [03 문서](03_PLAN_2D.md), [04 문서](04_PLAN_3D.md), [07 문서](07_TESTS_AND_ACCEPTANCE.md).

### E38 LLM 허용 범위의 서로 다른 확정 수준

원문 인용 · 2차 멘토링 요약본 · `docs/mentoring/MENTORING_2_SUMMARY.md` · **질의응답** · [L84](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/mentoring/MENTORING_2_SUMMARY.md#L84)

<!-- source-excerpt path="docs/mentoring/MENTORING_2_SUMMARY.md" start="84" end="84" -->
```text
| 41:53, 44:45–45:14 | LLM 모델·API·사용 용도의 제한 | 특정 API·모델을 지정하지 않으며 자유롭게 사용. 자연어 처리뿐 아니라 영상·객체 인식 등 다른 용도로도 사용할 수 있다고 답변. |
```

원문 인용 · 2차 멘토링 요약본 · `docs/mentoring/MENTORING_2_SUMMARY.md` · **질의응답** · [L95](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/mentoring/MENTORING_2_SUMMARY.md#L95)

<!-- source-excerpt path="docs/mentoring/MENTORING_2_SUMMARY.md" start="95" end="95" -->
```text
| 49:20–50:45 | 개인 서버에 학습시킨 자체 AI 모델을 API로 불러도 되는가 | **미확정.** 규정 검토 후 다음 멘토링이나 사전 안내로 답변하겠다고 남김. 일반 LLM API 허용과 동일한 결론으로 간주하면 안 됨. |
```

원문 인용 · 3차 멘토링 요약본 · `docs/mentoring/MENTORING_3_SUMMARY.md` · **불일치·확인이 필요한 부분** · [L147](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/mentoring/MENTORING_3_SUMMARY.md#L147)

<!-- source-excerpt path="docs/mentoring/MENTORING_3_SUMMARY.md" start="147" end="147" -->
```text
- **LLM 사용 범위:** M1 화면에는 주최측 제공 API가 **‘텍스트 LLM만’**이라고 표시된다. 이번 음성에서는 **다른 API의 사용 허용·금지를 확정하는 추가 답변을 확인하지 못했다.** 제공 API의 기능 범위를 외부 API 전면 금지 규칙으로 확대해 해석하지 않았다.
```

편집자 해설: 제공 API의 텍스트 전용 설명을 외부API 전면금지로 확대하지 않는다. 개인 모델 서버는 별도 미확정이다. 실제 adapter 제공자와 사용 의무는 주최측에 확인한다.

설계 반영: [01 문서](01_COMPETITION_RULES.md), [05 문서](05_SERVER_AND_ROBOT_API.md), [08 문서](08_BUILD_AND_HANDOFF.md), [09 문서](09_FIELD_ADAPTER_AND_QUESTIONS.md).

### E39 상대 위치와 타격 이벤트 정보의 출처

원문 인용 · 3차 멘토링 요약본 · `docs/mentoring/MENTORING_3_SUMMARY.md` · **게시판의 네 질문과 영상의 대응** · [L165](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/mentoring/MENTORING_3_SUMMARY.md#L165)

<!-- source-excerpt path="docs/mentoring/MENTORING_3_SUMMARY.md" start="165" end="165" -->
```text
이어지는 **58:30~58:50**에는 표적·상대 명중 여부를 알려 주는 별도 API가 없다고 답변합니다. 사용자가 제시한 **11월 7일 운영사무국 게시판 답변**은 상대 UGV 위치와 타격 이벤트 기록을 API로 제공하지 않는다고 더 구체적으로 명시합니다. 이 문장은 게시판 답변에 근거하며, 영상의 네 번째 답변을 그대로 인용한 문장은 아닙니다.
```

편집자 해설: 이 인용은 main의 요약본이 게시판 답변을 구분하여 기록한 것이다. 직접 읽은 게시판 원문이나 영상 답변으로 바꿔 인용하지 않는다. simulator truth 이벤트를 실제 참가팀 API처럼 제공하지 않는다.

설계 반영: [02 문서](02_ARCHITECTURE_AND_CONTRACTS.md), [04 문서](04_PLAN_3D.md), [05 문서](05_SERVER_AND_ROBOT_API.md), [07 문서](07_TESTS_AND_ACCEPTANCE.md), [09 문서](09_FIELD_ADAPTER_AND_QUESTIONS.md).

### E40 서버 예제코드와 공개 정보의 범위

원문 인용 · API 안내 HTML 변환본 · `docs/materials/PARTICIPANT_API_GUIDE.md` · **부록 — 오류 · 섹터 · 객체 · 리허설 / 서버가 주지 않는 것 — 대신 이렇게** · [L882–L884](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PARTICIPANT_API_GUIDE.md#L882-L884)

<!-- source-excerpt path="docs/materials/PARTICIPANT_API_GUIDE.md" start="882" end="884" -->
```text
| 남은 시간 | 표지 「시간」을 보고, **시작 신호를 받은 때부터 팀이 잽니다** · 1·2차 임무는 `wait`로 게시 순간에 받습니다(2·9단계) |
| 자기 점수 | 주지 않습니다 — M6는 팀이 추정합니다(11단계) |
| 예제 코드 | JSON 형식과 API 주소만 드립니다 — 구현은 참가팀이 합니다 |
```

편집자 해설: 서버는 JSON/API 형식을 주지만 구현 예제는 참가팀이 작성한다는 범위의 근거다. 이 문장을 모든 ROS starter·SDK의 영구 미제공으로 확대하지 않는다. 실제 패키지·메시지 정의는 별도로 확보한다.

설계 반영: [02 문서](02_ARCHITECTURE_AND_CONTRACTS.md), [05 문서](05_SERVER_AND_ROBOT_API.md), [08 문서](08_BUILD_AND_HANDOFF.md), [09 문서](09_FIELD_ADAPTER_AND_QUESTIONS.md).

## 원문 사실과 설계 가정의 경계

**PyBullet·Pygame·FastAPI 선택, 공통 10ms 고정틱, 3D optical 변환행렬, 카메라 내부파라미터, 정밀 로봇 센서 위치, 세계좌표계 원점·축, 섹터·거점 fixture 좌표는 본 계획의 설계 결정이며 학습자료 원문에서 제공한 값이 아니다.**

마찬가지로 pause 시계, 게시 전 거점 점유 처리, 동일 틱 마감 우선순위, 결손팀 M6 처리, 레이저 다중발신기 누적 규칙, practice 회복 시점, 배터리 모델은 [01 문서의 SIM 가정](01_COMPETITION_RULES.md)에 따라 구현한다. 원문에서 확인한 것은 위 인용의 범위이며, 구현 가능한 기본값을 덧붙였다는 사실을 숨기지 않는다.

## 인용 검증

작성 시 고정 커밋의 다섯 파일을 Git 객체에서 직접 읽어 지정한 1-based 줄 범위를 추출했다. 각 인용 블록의 `source-excerpt` 메타데이터와 블록 본문을 다시 파싱하여 원문 해당 범위와 문자 단위로 비교했다. 저장소의 PDF 변환본·멘토링 요약본이라는 출처 성격은 이 검증으로 바뀌지 않는다.
