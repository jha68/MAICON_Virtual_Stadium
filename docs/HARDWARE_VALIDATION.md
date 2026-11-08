# 실물 검증 기록

기록일: 2026-11-07 (한국시간). 실제 로봇·경기장·최종 SDK가 제공되지 않아 아래 항목은 모두 `not_run`이다. 합성 시험이나 fake ROS 통과로 대체하지 않는다. 소프트웨어 M0~M7/G0~G3와 분리된 H gate다.

| ID | 상태 | 필요한 입력·장비 | 실제 확인할 내용 |
|---|---|---|---|
| H-01 | not_run | 최종 API·SDK·운영 규약 | 메시지/서비스 전체 타입, 확정 버전과 SIM 프로필 차이 |
| H-02 | not_run | 실제 카메라·IMU·odom·LiDAR·서버 | intrinsics/왜곡/TF/QoS, 타임스탬프·지연·중단, IMU gravity convention |
| H-03 | not_run | 안전한 저속 시험 공간·로봇 | 전진/회전 부호, 실제 footprint·정지·watchdog·주행 지연 |
| H-04 | not_run | 허가된 실제 인쇄물·장면 | 여러 면의 인식·중복 집계·가림·섹터 귀속, 조명/연기의 영향 |
| H-05 | not_run | 공식 리허설 서버·제공 LLM | ready→start→M1/M3→report→M6→stop의 실제 저장·ACK |
| H-06 | not_run | 실제 운영 노드·팬틸트·레이저·수광부 | pause/resume/report/stop·피격 잠금, 팬/틸트 영점·도착 지연·광학 보정 |
| H-07 | not_run | 공식 런처·동일/다음 경기 | 최대 재실행, latched 상태 복원, odom 원점·경기 ID·캐시 분리 |

현재 확인한 범위는 내부 DTO 기반 FakeRosTransport의 publish/subscribe·latched 상태·서비스 timeout·부호/단위 계약이다. 실제 ROS 패키지나 서비스 타입은 지어내지 않았다. 버전별 시험 근거는 `tests/contracts/test_sdk_adapters.py`, 실행 결과는 `artifacts/final-tests.xml`과 `IMPLEMENTATION_STATUS.md`에서 확인한다.

실제 바퀴 마찰·슬립·전복·타이어 접촉 동역학, 전력 소비·배터리 수명, 레이저 확산·수광 각도 응답, 연기의 입자 광학·LiDAR 간섭은 v1 충실도 범위 밖이다. 최종 규정이 확정되면 기존 synthetic 프로필을 덮어쓰지 않고 새 프로필·계약·fixture·회귀 결과를 함께 추가한다.
