# 현장 연결과 미확정 규칙 관리

이 계획으로 완료할 대상은 2D·3D 가상 시험 환경이다. 실제 장비의 정밀한 주행·조준 성능, 공식 서버와의 완전한 호환성은 최종 SDK와 실물이 있어야 확인할 수 있다. 이 문서는 그 연결 지점을 미리 고정하여 현장에서 코어를 다시 작성하지 않게 한다.

## 1 실제 환경에서 바꾸는 부분

| 가상 환경 | 현장 연결 | 그대로 유지하는 부분 |
| --- | --- | --- |
| SimulatorRobotPort | ROS2RobotPort | 상태기계·행동 계획·관측 저장소 |
| /sim/session | 공식 런처가 제공하는 경기 식별정보 또는 현장 세션 어댑터 | 캐시와 보고의 세션 분리 |
| 모의 /api/report | 공식 HTTP 서버 주소·최종 wire adapter | 전체 보고·재시도·마감 관리 |
| 합성 RGB | /image_raw와 CvBridge | VisionCallback 출력 자료형 |
| 합성 LiDAR·odom·IMU | 공식 토픽·QoS·TF | 센서 유효기간·불확실성·계획 로직 |
| mock LLM | 주최측 제공 LLM adapter | 프롬프트·JSON 검사·시간 예산 |
| PublicMapPrior | 현장 측정 지도·명목 출발점 | 섹터·거점 의미와 경로 계획 |

공식 /me에 시뮬레이터 match_id·remaining_time·점수를 추가하여 실물 코드가 그 필드에 의존하게 만들지 않는다. simulator capability를 실제로 제공되는 센서로 착각하지 않는다.

## 2 ROS 연결 명세

현재 자료에서 확인한 경로는 다음과 같다. 사용자 정의 메시지 패키지 이름과 전체 필드는 아직 확보하지 못했다. 임의로 import 경로를 지어내어 공식 SDK라고 주장하지 않는다.

| 경로 | 연결 | 현재 확인한 의미 |
| --- | --- | --- |
| /mil/state | subscribe | hp, hp_max, battery_pct, 2Hz |
| /mil/match | subscribe | mode, cmd; 상태 depth 1·TRANSIENT_LOCAL 안내 |
| /cmd_vel | publish geometry_msgs/Twist | linear.x ±.6, angular.z ±3, 약 10Hz |
| /odom | subscribe nav_msgs/Odometry | 출발점 기준 위치·방향, 20Hz, sensor-data QoS |
| /image_raw | subscribe sensor_msgs/Image | 640×480 BGR, 최대 30FPS·10 이하 권장 |
| /imu/data | subscribe | quaternion·각속도·가속도; 정확한 SDK 타입 확인 필요 |
| /mil/gimbal | service | pan, tilt, speed, acc; ok/locked |
| /mil/fire | service | 인수 없는 요청; fired/empty/locked/reloading, left_ms |
| /mil/oled | publish | line 0..3, text≤21, 간격 .5초 이상 |
| LiDAR·Depth·TF | 최종 SDK 확인 | 현재 main만으로 토픽·frame·QoS를 완결할 수 없음 |

ROS2RobotPort는 inbound callback에서 데이터를 복사·정규화하고 짧게 반환한다. 모델 추론·HTTP·서비스 응답 대기를 callback/step 안에서 blocking하지 않는다. 단일 주행 명령 발행자를 유지하며 pause/report/stop 때 속도 0, queued actuation 취소를 적용한다.

service timeout은 동작 불명이다. gimbal ok는 도착 확인이 아니다. fire timeout은 맹목 재호출하지 않는다. QoS 설정이 맞지 않아 상태를 못 받는 문제를 doctor에서 구분한다. 같은 경기 재실행 시 odom 원점·관측 timestamp·자식 프로세스를 어떻게 복원할지 최종 SDK와 맞춘다.

H gate 이전에는 FakeRosTransport로 publish/subscribe/service completion과 timeout을 시험한다. FakeRosTransport에는 실제 ROS 타입명을 가정하지 않고 내부 DTO를 쓰며, 공식 type mapping은 별도 mapping 파일과 계약 테스트로 추가한다.

## 3 현장 보정 파일

현장별 profile에는 robot serial, 측정일, 최종 SDK 버전, 측정자, 불확실성을 기록한다.

- arena profile: 실제 외곽·섹터 다각형·거점 진입선·명목 출발점.
- robot geometry: 실제 footprint, 카메라·레이저·LiDAR·수광부 설치 위치.
- camera calibration: 영상 크기, intrinsics, 왜곡 모델, optical transform.
- actuation calibration: 선속도·회전 응답, watchdog, pan/tilt 단위·부호·도착 지연.
- sensors: 갱신 주기, timestamp 기준, 평균·상위 지연, dropout, IMU gravity convention.
- network: server/LLM 주소, timeout, 요청 한도. 키는 environment로 주입하고 파일·로그에 평문 저장하지 않음.
- rule profile: 최종 확정된 pause·출발·M5·M6·보고 규칙.

새 profile을 추가할 때 기존 synthetic reference profile을 덮어쓰지 않는다. 변경 후 기존 golden 시험과 새 현장 계약 시험을 각각 수행한다.

## 4 장비를 받은 직후 순서

1. 최종 규약 버전과 현재 계획의 차이를 01의 SIM 표와 대조한다.
2. robot doctor로 Python·ROS·GPU·모델 파일·토픽·QoS·서비스 가용성을 확인한다.
3. 모터를 쓰지 않고 카메라·IMU·odom·상태 수신, HTTP /me, LLM 최소 요청을 확인한다.
4. 허용된 시험 공간에서 저속 전진·회전·정지·watchdog와 pan/tilt 부호를 확인한다.
5. 실제 시야로 한 박스의 여러 면을 촬영하고 중복 집계·섹터 귀속을 검증한다.
6. 리허설에서 ready→start→M1/M3→report→M6→stop을 연결한다.
7. pause/resume, 영상 중단, 통신 timeout, 프로세스 재실행을 운영진이 허용하는 방식으로 시험한다.
8. 실물 결과를 녹화·재생 fixture로 추가하고, 실제로 확인한 범위만 H 결과에 기록한다.

충전 중 모터를 구동하지 않는 안내, 개인 PC 금지, UGV 내부 실행 조건을 준수한다. 개발 PC의 시뮬레이터는 사전 개발·리플레이 용도이며 실제 경기에서 외부 PC가 임무를 계산하도록 연결하지 않는다.

## 5 우선 문의할 사항

질문은 현재 자료에 없는 부분에 집중한다. 답이 늦어도 시뮬레이터는 아래 SIM default로 완성한다.

| 우선 | 질문 | 답변 전 구현 기본값 | 답변 후 영향 |
| --- | --- | --- | --- |
| P0 | 출발 센서·유예 시간·미출발 0점의 정확한 조건은? | ready admitted 자동 출발, 실패는 fault | admission과 start detector |
| P0 | starter, 전체 msg/srv, JetPack/CUDA/TensorRT/Python/컨테이너 버전은? | 내부 DTO+fake ROS | ROS adapter·배포 |
| P0 | LiDAR·TF·camera_info·Nav2·지도 제공 범위는? | 합성 sensor profile·공개 명목 지도 | 센서·위치추정 |
| P0 | 제공 LLM의 모델·호출 한도·지연·M1/M6 사용 의무·장애 시 대체 처리는? 외부 VLM/개인 서버 허용은? | mock LLM+교체 포트, 허용 여부를 추정하지 않음 | LLM adapter·계획 예산 |
| P0 | M3 이미지 면·동일 사진·가림·경계·0개 판정은? | image face 단위, 명시 sector, 미보고 0 | 데이터·집계·채점 |
| P1 | pause 중 시계와 보고 허용, 재실행 시 경기 ID/시각은? | 01의 SIM-PAUSE, sim handshake | clocks·session |
| P1 | POST 재시도·저장 순서·revision·저장 결과 조회 규약은? | 전체 snapshot best-effort | report worker |
| P1 | M5 선점유·체류 시간·자책 점령·동시 감지 규칙은? | 게시 후 rising edge, 체류 0 | base detector |
| P1 | M6 상태 동결 시점·동점·부분 점수·전원 제출 종료는? | 01의 SIM-M6-SCORING/FREEZE | scorer |
| P1 | 시설/상대 명중의 로컬 피드백·자기 잔탄 필드는? | 공개된 자기 hp, 발사 이력으로 탄약 추정 | own observations |
| P1 | P2P/DDS/소켓과 경기 전 연합 역할 합의가 허용되는가? | 무통신 독립 정책 | 협력 전략 |
| P2 | 실전 연기·센서 저하·조기 종료 리허설 가능 시간은? | 합성 fault 시험 | H gate |
| P2 | 연합 합계·6경기 환산·최종 동점 기준은? | M1~M6 비교 후 +5, 6경기 통계만 | 평가 보고 |

상대 위치·타격 이벤트 API 미제공, 띠 1/2/3과 호출부호, 기능정지 중 M6 가능 여부는 main 요약에 이미 답이 있다. 새 질문으로 반복할 필요는 없다.

## 6 현장 합격 증거

H-01 최종 API/SDK 버전 기록. H-02 실제 센서 지연과 좌표 점검. H-03 저속 운동과 정지. H-04 실제 그림 인식/집계. H-05 실제 리허설 보고 수신 확인. H-06 pause/report/stop 동작. H-07 재실행과 다음 경기 분리.

각 항목은 날짜·장비·입력·결과·영상/로그·미확인 조건을 남긴다. 가상 시험 통과로 H 항목을 대신 채우지 않는다. 현장 전까지 H는 not_run이어도 2D·3D 구현 G3 완료와 양립한다.
