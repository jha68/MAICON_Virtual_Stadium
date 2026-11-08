# 2D 경기장 시뮬레이터 구현계획

이 문서는 `maicon-sim` 저장소의 2D 백엔드를 구현하는 작업 명세다. 경기 규칙·채점·HTTP 서버는 공통 엔진을 사용하고, 이 문서는 평면 운동, 충돌, 센서 관측, 시나리오 로봇, 화면, 기준 정책을 정의한다. [공통 계약](02_ARCHITECTURE_AND_CONTRACTS.md), [API 명세](05_SERVER_AND_ROBOT_API.md), [시나리오 명세](06_SCENARIOS_AND_ASSETS.md)를 먼저 읽는다. 이 문서의 수치 중 `SIM-2D-*`는 구현을 진행하기 위한 시뮬레이터 선택이며 대회 장비의 실측값이 아니다.

## 1. 완료했을 때 제공할 기능

1. 로봇 6대, 벽, 박스, 시설, 객체 이미지가 붙은 면, 거점 센서가 있는 경기장을 파일로 구성한다.
2. 같은 시드와 입력 이벤트로 다시 실행하면 같은 규칙 이벤트·궤적·점수를 얻는다.
3. 2D 화면 없이도 한 경기·여러 시드·여러 시나리오를 실행하고 결과를 저장한다.
4. 별도 프로세스의 참가팀 코드는 자기 센서와 공개 API만 사용한다. 평가자 화면의 정답 상태는 읽을 수 없다.
5. 참가팀의 주행, 팬틸트, 발사, M1·M3·M6 보고를 공통 엔진에 연결한다.
6. 3D에서 같은 입력을 재생하면 평면 궤적과 규칙 결과가 같다. 3D의 영상 출력과 2D의 의미 관측 결과가 같을 필요는 없다.

2D의 의미 관측은 인식 이후의 집계·전략을 시험하는 가상 입력이다. 실제 로봇에서 바로 사용할 수 있는 탐지기나 영상 모델의 정확도 증거로 취급하지 않는다. `rgb`를 요구하는 참가팀에는 빈 검정 이미지를 반환하지 말고 해당 백엔드에서 영상 채널을 사용할 수 없다는 오류를 돌려준다. 이미지 추론 시험은 3D 계획을 따른다.

## 2. 구현 파일과 책임

아래 경로는 새 저장소의 `src/maicon_sim/` 아래에 둔다. 문서와 구현 경로를 함께 유지한다.

| 경로 | 책임 | 의존할 수 없는 것 |
| --- | --- | --- |
| `core/geometry2d.py` | OBB 꼭짓점, SAT, convex hull, 거리·포함 판정 | HTTP, Pygame, 정책 |
| `core/geometry3d.py` | 공통 primitive raycast, 카메라 좌표 변환·투영 | PyBullet 전용 body ID |
| `core/planar_motion.py` | 일정 twist 적분, microstep, 동시 충돌 해결 | 점수, 이미지, 서버 시계 |
| `backends/two_d.py` | 공통 엔진의 백엔드 인터페이스 구현 | 참가팀 정책 내부 상태 |
| `sensors/semantic.py` | 면 가시성, 투영 bbox, 인식 오류 주입 | 보고서의 정답·서버 점수 |
| `sensors/lidar.py` | 수평 raycast, 거리 오차·누락 | 실제 ROS 타입 |
| `sensors/odometry.py` | 출발 좌표계 변환, 오차 모델 | HTTP mission code |
| `policies/scripted.py` | 공개된 대본을 명령으로 바꾸는 로봇 | 공통 엔진에 직접 pose 쓰기 |
| `policies/baseline.py` | 센서 기반 최소 자율 기준 프로그램 | TruthStore, 정답 manifest |
| `viewer/pygame_viewer.py` | 평가자 전용 화면과 조작 | 경기 상태 직접 변경 |

평면 기하 계산은 NumPy와 Python 표준 라이브러리로 구현한다. Shapely를 필수 의존성으로 추가하지 않는다. 표준 SAT·convex hull을 짧은 순수 함수로 작성하여 경계 조건을 직접 시험한다. 벽·박스가 축 정렬되어 있어도 로봇은 OBB로 계산한다.

## 3. 좌표와 물체 표현

공통 좌표는 남서 모서리 원점, 동쪽 `+x`, 북쪽 `+y`, 위쪽 `+z`, yaw의 양의 방향은 반시계다. BLUE는 서쪽에서 동쪽을 향하고 RED는 동쪽에서 서쪽을 향한다. 화면 y축은 아래쪽으로 증가하므로 화면 표시 때만 반전한다.

로봇 평면 footprint는 길이 0.23m, 폭 0.25m의 직사각형이다. body `+x`가 전방이므로 로컬 꼭짓점은 `(±0.115, ±0.125)`다. 물리 충돌은 이 footprint를 사용하며 3D 장식물의 모양으로 다시 계산하지 않는다. 높이 0.32m와 카메라·수광부의 위치는 3D primitive에 사용한다. 실제 장비 외곽과 동일하다고 보장하지 않는다.

박스는 기본 0.4m 정육면체지만 시나리오에 `size_m`과 `yaw_rad`를 명시한다. 벽은 경기장 외부로 진행하지 못하게 하는 고정 OBB다. 바닥의 섹터·거점 선은 충돌 물체가 아니다. 센서 띠도 통과를 감지하는 trigger일 뿐 장애물이 아니다.

면은 `box_id + face_name`으로 평가자 내부에서 식별한다. 면당 그림이 하나인 기본 fixture를 사용한다. 한 면의 그림과 반대 면의 동일 그림은 서로 다른 정답 객체다. 최종 계수 정책은 공통 규칙 프로필로 교체할 수 있다. 객체의 정답 섹터는 manifest의 명시값을 사용하고, 참가팀의 현재 위치로 정하지 않는다.

생성 시에는 물체끼리 겹치지 않는지, 로봇 출발점에 최소 10mm 여유가 있는지, 목표 접근 가능성이 있는지 검사한다. 섹터 경계에 중심이 걸친 박스를 자동으로 임의 배정하지 말고 명시적인 `sector_id`를 요구한다. 기본 fixture의 배치 좌표는 실제 경기장을 재현한 측량값이 아니다.

## 4. 평면 운동 적분

### 4.1 입력과 효과 적용

주행 입력은 `v_mps`, `omega_radps`의 unicycle twist다. ROS `/cmd_vel` 연결부는 `linear.x`, `angular.z`를 이 값으로 변환한다. 범위는 각각 `[-0.6,0.6]`, `[-3,3]`다. 유효하지 않은 NaN·무한대·범위 초과 입력을 조용히 허용하지 않는다. API 명세에 따라 검증 실패로 처리하며 실제 드라이버용 제한기는 별도로 둔다.

명령 입력에서 운동까지의 순서는 다음과 같다.

1. tick 시작에 수신 대기열의 주행 명령을 정해진 순서로 적용한다.
2. `pause/report/stop`, 피격에 따른 주행 잠금, 명령 watchdog를 확인한다.
3. 잠겨 있거나 마지막 유효 주행 명령이 0.5초 이상 오래되면 유효 twist를 0으로 만든다.
4. 허용된 twist에 프로필의 이동 오차를 적용한다.
5. 모든 로봇을 같은 microstep 길이로 적분하고 충돌을 해결한다.
6. 승인된 pose만 공통 엔진의 상태에 반영한다.

watchdog는 `sim_tick - last_velocity_received_tick >= 50`일 때 만료한다. 피격 효과 시계가 pause 동안 멈추는 것과 별개로 입력의 유효기간을 sim_tick으로 계산한다. pause에서는 보유 주행 명령을 폐기하고 resume 때 자동 복원하지 않는다. 새 명령이 들어오기 전까지 유효 twist는 0이다. HP가 0이라는 이유로 영구 잠금하거나 참가팀 프로세스를 종료하지 않는다.

### 4.2 정확한 일정 twist 해

한 microstep의 길이를 `h`초, 시작 pose를 `(x,y,theta)`라 한다. `abs(omega) < 1e-8`이면 다음 직선식을 사용한다.

```text
x_next = x + v*h*cos(theta)
y_next = y + v*h*sin(theta)
theta_next = theta
```

그 외에는 다음 원호 적분을 사용한다.

```text
theta_next = theta + omega*h
x_next = x + (v/omega)*(sin(theta_next)-sin(theta))
y_next = y - (v/omega)*(cos(theta_next)-cos(theta))
```

yaw는 상태 저장 시 `[-pi,pi)`로 정규화한다. `+pi`는 `-pi`로 저장한다. 비교용 yaw 오차는 각도 차이를 wrap한 뒤 계산한다. 운동 적분·충돌에는 float64를 사용한다.

`SIM-2D-MOTION`: 바퀴·마찰·관성·모터 응답을 실제 물리 모델로 재현하지 않는다. 기본은 이상적인 평면 속도 제어다. 오차 시험은 로봇별 고정 속도 비율, 각속도 비율, 명령 지연으로 명시적으로 주입한다. 외부 물리 엔진이 pose를 다시 움직이지 못하게 한다.

### 4.3 microstep과 관통 방지

공통 tick은 0.01초다. 로봇 외접 반지름 `r=sqrt(0.115²+0.125²)`를 사용하여 tick마다 다음을 계산한다.

```text
n = max(1, ceil(max_over_robots((abs(v)+r*abs(omega))*0.01) / 0.002))
h = 0.01/n
```

모든 로봇에 같은 `n`을 적용한다. 기본 속도 범위에서는 매우 작은 `n`이면 충분하지만, 하드코딩한 고정 상한으로 결과를 잘라내지 않는다. 잘못된 시나리오 때문에 과도한 `n`이 나오면 명확한 오류로 중단한다.

microstep의 시작·후보 끝 OBB 꼭짓점 8개를 모아 convex hull을 만든다. 원호 중간의 최대 이탈을 감싸기 위해 hull을 다음 반경의 원판만큼 보수적으로 팽창한 것으로 검사한다.

```text
delta = abs(omega*h)
sagitta_bound = (abs(v/omega)+r)*2*sin(delta/4)^2  # omega가 충분히 클 때
sagitta_bound = abs(v*omega)*h*h/8 + r*delta*delta/8  # near-zero 안정식
padding = sagitta_bound + 1e-6 m
```

회전 원의 반지름에 대한 삼각부등식 상한을 쓰므로 충돌을 조금 일찍 막을 수 있다. 이 보수성은 허용하지만, 물체를 통과시키는 결과는 허용하지 않는다. hull과 다른 볼록 다각형의 거리 또는 SAT projection gap으로 padding을 반영한다. 양쪽이 움직이면 두 padding을 더한다. SAT의 축은 두 hull의 모든 edge normal이며 0 길이 edge는 제거한다.

고정 장애물에 대해 swept hull이 접촉하거나 겹치면 해당 microstep의 병진과 회전을 모두 거부한다. 마찰을 흉내 내기 위해 임의로 옆으로 밀거나 자동 슬라이딩하지 않는다. 거부된 로봇은 다음 microstep에서 새 후보를 다시 계산할 수 있지만 동일 명령으로 장애물 안에 들어가지는 못한다. 초기 상태에 이미 겹침이 있으면 실행 전에 validation 실패로 처리한다.

### 4.4 로봇 간 동시 충돌 해결

슬롯 순서대로 로봇을 이동시키면 앞 슬롯이 통로를 우선 차지하게 되므로 금지한다. microstep마다 다음 알고리즘을 사용한다.

1. 모든 로봇의 시작 pose에서 후보 pose와 swept hull을 계산한다.
2. 고정 장애물에 부딪힌 로봇을 `blocked` 집합에 넣는다.
3. 아직 blocked가 아닌 로봇은 swept hull, blocked 로봇은 시작 footprint를 사용하여 모든 로봇 쌍을 검사한다.
4. 충돌하는 쌍의 두 로봇을 모두 blocked에 추가한다.
5. blocked 집합이 더 이상 커지지 않을 때까지 3~4를 반복한다. 최대 로봇 수만큼 확장하면 수렴한다.
6. blocked 로봇은 시작 pose, 나머지는 후보 pose를 한 번에 commit한다.

같은 공간을 다른 순간에 통과하는 두 경로도 한 microstep의 hull이 겹치면 보수적으로 막힐 수 있다. 2mm microstep으로 오차를 제한한다. 이 알고리즘은 실제 충돌 반발을 재현하지 않는다. 충돌 이벤트에는 슬롯쌍·tick·microstep을 기록하되 참가팀 관측에는 정답 상대 위치를 추가하지 않는다.

거점 trigger와 레이저 효과는 승인된 pose와 공통 tick 이벤트 순서로 평가한다. 같은 tick 끝점에서 경기 마감과 기하 이벤트가 겹치면 마감 전이가 우선이다. 예를 들어 정확히 경기 300.00초에 완성된 점령·피격은 인정하지 않고, 299.99초까지 완성된 이벤트는 반영한다. microstep 내부에서 생긴 이벤트도 공통 엔진에 약정된 tick으로 양자화하며 백엔드가 별도 고해상도 시계로 마감 규칙을 바꾸지 않는다.

## 5. 공통 가림과 레이저 기하

레이저의 유효피격 여부를 단순한 `거리 < 임계값`이나 `상대가 FOV 안에 있음`으로 판단하지 않는다. 2D에서도 높이를 포함하는 공통 analytic raycast를 사용한다. 평면 궤적만 2D이며, 카메라와 발광부의 위치·방향·수광부 높이는 3D 기하를 가진다.

필수 primitive는 OBB, 구, 직사각형 면이다. ray는 정규화된 방향을 사용하며 양의 교차거리 중 가장 작은 값을 고른다. OBB는 역변환 후 slab intersection, 구는 이차방정식, 면은 plane 교차 뒤 local rectangle 경계 검사로 구현한다. epsilon과 동거리 tie는 공통 계약을 따른다. 면의 시각 texture는 충돌 두께를 늘리지 않는다.

발광 원점·팬틸트 회전·수광부의 기본 설치 위치는 [3D 계획](04_PLAN_3D.md)의 공통 sensor transform을 사용한다. 2D 파일에 다른 값을 중복 정의하지 않는다. 장애물에 가려진 수광부는 유효 조사로 세지 않는다. 발사한 로봇 자신의 외장물은 ray 시작점의 자기 교차를 피하기 위해 발광 ray에서 제외하되 다른 로봇의 차체는 가림 물체다.

각 수광부의 hit 결과를 공통 규칙 엔진에 전달한다. 2초 연속 조사, 10초 무적·기능정지, 탄약, 5초 발광, 재발사 간격, M2 파괴·점수는 백엔드에서 구현하지 않는다. 두 백엔드가 같은 ray를 전달하면 같은 규칙 이벤트를 발생시켜야 한다.

기본 ray는 폭이 없는 중심 ray다. `SIM-2D-LASER`로 명시하고 실제 레이저 빔 직경·광량·펄스 신호를 검증했다는 표현을 사용하지 않는다. 장비 보정 이후 pointing offset 또는 beam spread 모델을 독립 파라미터로 추가할 수 있지만 기본 회귀 시험은 중심 ray로 고정한다.

## 6. 센서 생성과 정보 경계

### 6.1 채널

| 채널 | 기본 주기 | 참가팀에 허용되는 정보 |
| --- | --- | --- |
| 자기 상태 | 2Hz | 자기 HP·최대 HP·배터리·자기 제어 상태; 상세 wire는 API 계약 |
| odometry | 20Hz | 출발 좌표계의 잡음 포함 pose·twist |
| IMU | 20Hz | 잡음 포함 자세·각속도·가속도 |
| LiDAR | 프로필 설정 | 자기 센서 좌표계의 거리 배열·측정 시각 |
| 의미 인식 | 10Hz | 화면 bbox·클래스 확률·confidence·시각; SIM 전용 |
| 전방 RGB | 지원하지 않음 | 명시적인 unavailable 결과 |
| 드론 JPEG | 1/2/5초·차단 | 참가팀 카메라용 overhead 이미지; 정답 overlay 제외 |

드론 JPEG는 물체를 단순한 색·도형으로 렌더링한 synthetic 영상이어도 된다. 좌표·ID·HP·미관측 객체·점수 같은 평가자 annotation은 넣지 않는다. 색상 표식이나 상태 LED를 그릴 때는 시나리오에 정의된 실제 보이는 표식만 표현한다. 2D overhead가 3D 실제 카메라 영상과 같다고 취급하지 않는다.

센서 cadence는 integer tick으로 표현한다. 측정 `captured_tick`과 전달 `received_tick`을 구분한다. 전달 지연·drop은 측정 후 transport queue에 적용한다. 프레임 반복은 이전 bytes와 `captured_tick`을 그대로 재사용하며 새 관측으로 계산하지 않는다. 세부 wire field는 공통 계약이 최종 기준이다.

### 6.2 2D 의미 인식

`DetectedFace`라는 내부 이름은 데이터 종류를 설명할 뿐 실제 face ID를 담는다는 뜻이 아니다. JSON envelope는 다음 필드를 가진다.

```text
sequence, captured_tick, received_tick,
width_px=640, height_px=480, camera_id,
detections=[{kind, bbox_xyxy_px, class_probs, confidence, marker_readout?}, ...]
```

각 detection은 `kind='object'|'facility'|'ugv'`를 가진다. `class_probs`의 키는 object에서는 6종 객체의 lowercase 코드, facility에서는 `COMMS/OUTPOST/RADAR`, ugv에서는 `UGV`이며 값의 합은 1이다. `bbox_xyxy_px`는 화면 내부의 float 좌표 `[x1,y1,x2,y2]`, `x1<x2`, `y1<y2`다. 좌표 원점은 좌상단이다. `face_id`, `box_id`, 정답 `sector`, world pose, 실제 count, 상대 HP·탄약·점수는 포함하지 않는다. 이미지 밖 물체를 별도 힌트로 반환하지 않는다.

UGV detection에만 선택적인 `marker_readout={camp,band_count,confidence}`를 넣을 수 있다. 실제 표식이 화면에 보이고 읽혔을 때에만 전달한다. 가려진 표식의 진영·띠 수를 정답 상태에서 채워 넣지 않는다. 읽기 실패는 필드 생략으로 표현하며, 띠 수·색상 오인식도 noise 프로필로 주입한다. 이 readout은 측정 결과이지 영구 track ID가 아니다. 참가팀이 track과 호출부호를 연결해야 한다.

기본 camera projection은 640×480, horizontal FOV 90°, `fx=fy=320`, `cx=319.5`, `cy=239.5`, near 0.02m, far 10m다. 이는 `SIM-2D-CAMERA`이며 실제 광각 렌즈 사양을 재현한 값이 아니다. optical frame은 +x 오른쪽, +y 아래쪽, +z 전방이다. `u=fx*X/Z+cx`, `v=fy*Y/Z+cy`로 투영한다.

가시성 알고리즘은 다음과 같다.

1. 면의 외향 normal과 카메라 방향을 비교하여 뒷면을 제외한다. 면에서 카메라를 향한 단위 벡터와 normal의 내적이 0.1 이하이면 제외한다.
2. 그림 rectangle 안에 3×3 표본점을 균등하게 배치한다. edge 위가 아닌 내부 1/6, 1/2, 5/6 위치를 사용한다.
3. 카메라에서 각 표본점까지 raycast한다. 표본점 앞에 다른 불투명 물체가 있으면 가린 것으로 센다. 대상 면 자체와의 끝점 교차는 가림으로 세지 않는다.
4. 9점 중 5점 이상이 보이고 그림의 투영 bbox가 영상과 겹치면 관측 후보로 만든다. bbox는 투영된 그림의 네 꼭짓점 범위를 영상에 clip한다. near plane에 걸친 후보는 기본 구현에서 제외하고 제외 이유를 평가자 로그에 기록한다.
5. 폭 또는 높이가 4픽셀 미만이면 제외한다. 이상적인 테스트 프로필에서는 남은 후보를 정확한 클래스 확률 one-hot으로 반환한다.
6. `stress_v1` 프로필이면 dropout·confusion·bbox noise·false positive를 적용한다. noise RNG는 관측 후보를 stable internal ID로 정렬한 다음 사용하며 이 정렬용 ID를 참가팀에 내보내지 않는다.

`SIM-2D-VISIBILITY`: 3×3 표본 방식은 픽셀 단위 segmentation의 근사다. 작은 가림의 정밀한 영상 효과는 3D에서 시험한다. 최소 5/9·4px 값은 설정으로 분리하며 하나의 프로필 안에서는 고정한다.

facility 후보는 같은 rectangle 알고리즘을 시설 그림 면에 적용한다. ugv 후보는 공통 chassis OBB의 카메라를 향한 면들 중 normal과 시선의 내적이 가장 큰 면을 고르고, 그 면의 3×3 가림 검사로 생성한다. UGV bbox는 해당 chassis OBB 꼭짓점 8개를 투영한 범위다. 장식 바퀴·안테나를 포함한 영상 검출 bbox와 같다고 가정하지 않는다. marker_readout은 chassis 검출 성공만으로 자동 생성하지 않고, 공통 geometry manifest의 marker rectangle 자체에 별도의 3×3 가림·4px 최소크기 검사를 적용하여 성공했을 때만 추가한다. marker geometry가 없는 프로필은 readout을 지원하지 않는다.

오류 프로필의 권위는 [시나리오 명세 8절](06_SCENARIOS_AND_ASSETS.md#8-오류-주입-프로필)이다. `ideal`은 확률 오류와 지연이 모두 0이다. `stress_v1`은 detection miss 0.10, 검출 성공한 object의 wrong class 확률 0.05, bbox 각 좌표 Gaussian 표준편차 2px, false positive 수 `Poisson(0.05/frame)`를 적용한다. wrong class이면 다른 5종 중 균등 선택한다. 예측 label을 먼저 샘플링한 뒤 반환 확률 벡터는 그 예측 label에 0.95·나머지 각 클래스에 0.01을 둔다. 모든 반환 벡터의 최대값을 진짜 label에 두어 confusion이 사라지는 구현은 금지한다. `stress_v1`의 facility·UGV는 detection miss를 적용하되 별도 class confusion을 추가하지 않는다. 가시성이 충족된 marker readout에도 이 프로필에 없는 추가 확률 오류를 몰래 넣지 않는다. 시설·표식의 오류 실험이 필요하면 별도 이름의 명시적 프로필로 정의하고 run manifest에 기록한다.

false positive bbox는 최소 8×8px·최대 80×80px로 영상 안에서 생성하고 기본 kind는 object, 클래스는 균등 선택한다. 이 값들은 합성 시험 설정이며 실측 성능 추정값이 아니다. 깨끗한 테스트와 `stress_v1` 실험 결과를 같은 조건의 점수로 섞지 않는다. noise 적용 후 bbox 유효성을 다시 검사한다. camera 전달은 100ms 지연과 프레임 독립 drop 0.05를 적용하며, 의미 관측도 같은 전방 camera transport 정책을 사용한다.

### 6.3 odometry와 LiDAR

기본 odometry는 시작 true pose를 원점으로 한 상대 pose를 반환하되 이름은 odometry다. 완전한 world true pose를 반환하는 oracle 채널과 구분한다. `stress_v1`은 이동 scale 1.02, yaw rate bias 0.005rad/s, position increment noise 표준편차 0.001m를 적용하여 noisy increment를 누적한다. position noise는 20Hz odometry 측정 간격의 x·y increment 각각에 독립 적용한다. yaw bias는 경과한 측정 간격만큼 적분한다. 세계 정답 pose에 독립 잡음을 매번 붙이는 방식으로 drift 누적을 대체하지 않는다. 이 프로필에 별도의 무작위 로봇별 scale 샘플링을 추가하지 않는다.

LiDAR는 공통 높이의 수평 원형 raycast다. 빔 수·높이·범위·주기는 robot profile의 명시값을 사용한다. 거리값만 참가팀에 전달하고 맞은 object ID·class·sector는 evaluator 전용이다. `stress_v1`은 유효 hit 거리마다 Gaussian 표준편차 0.01m를 적용한 뒤 범위에 clip하고 독립 확률 0.02로 no-return을 만든다. 원래 no-return인 빔에 가짜 hit를 생성하지 않는다. no-return은 API 계약의 null 표현을 따른다. JSON에 NaN/Infinity를 쓰지 않는다. robot own geometry는 제외하고 벽·박스·다른 로봇의 공통 primitive와 교차한다. 3D renderer의 debug mesh가 센서 범위를 바꾸지 않아야 한다.

## 7. 시나리오 로봇과 기준 참가팀

### 7.1 대본 로봇

최소한 아래 정책을 제공한다. 모두 자기 슬롯 명령 어댑터로 twist·gimbal·fire를 보내며 엔진 pose를 직접 변경하지 않는다.

| 정책 | 목적 | 행동 |
| --- | --- | --- |
| `idle` | 기본 격리 시험 | ready만 제출, 속도 0 유지, M1·M3·M6 미제출 |
| `baseline` | 최소 자율 통합 시험 | 다음 절의 기본 탐색·집계·보고·M5 이동 수행 |
| `patrol` | 혼잡·추월 시험 | 공개된 waypoint 목록을 순서대로 이동, 도착 radius 0.08m |
| `blocker` | 막힌 경로 시험 | 지정 공개 지점까지 이동한 뒤 설정 시간 대기 |
| `capture_runner` | 조기 종료 시험 | 실제 `/target`을 받고 공개된 거점 좌표로 이동 |

위 다섯 이름이 `agents.policy`의 canonical 값이다. 다른 문자열 alias를 자동 수용하지 않는다. 지정 tick에 팬틸트·발사 명령을 보내는 사격 fixture는 별도 evaluator action trace로 구성하며 새 policy enum을 추가하지 않는다. 테스트 fixture의 대본은 정답 세계정보를 사용하는 evaluator script일 수 있다. 그 경우 run metadata에 `controller_kind=scripted_fixture`, `oracle=true`로 표시하고 자율 알고리즘의 성능으로 집계하지 않는다. 관측 제한 정책과 truth 기반 fixture를 같은 이름으로 부르지 않는다.

### 7.2 최소 자율 기준 정책

baseline은 제품을 완성했다는 smoke test에 필요한 수준으로 구현한다. 우승 전략이나 높은 점수를 완료 조건으로 삼지 않는다. 최소 정책은 상태·서버·센서 연결, M1·M3·M6 제출, 장애물 앞 정지, 목표 변경을 실제 코드 경로로 수행해야 한다.

- 지도는 `PublicMapPrior`의 경기장 외곽·섹터·거점과 슬롯별 `nominal_start_pose`를 받는다. 이 pose는 실제 배치 jitter 적용 전 명목 위치·방향이다. baseline은 명목 시작 pose와 local odometry를 합성하여 world pose를 추정한다. 실제 시작 pose·jitter·박스 좌표·정답 객체 목록은 받지 않는다. 시작 오차와 drift는 localization_error 평가에 남기며 이를 제거한 정답 pose로 몰래 보정하지 않는다.
- LiDAR로 0.05m 해상도 occupancy grid를 만든다. unknown/free/occupied를 구분한다. ray의 끝점 이전을 free, 유효 hit 끝점을 occupied로 갱신한다.
- 경로 계획은 8방향 A*를 사용한다. 대각선 이동은 인접한 두 직교 셀이 모두 통과 가능할 때만 허용한다. 점유 셀은 로봇 외접 반지름+0.01m만큼 보수적으로 팽창한다. unknown 이동 비용은 free의 3배로 두고 공개된 경기장 경계 밖은 금지한다.
- 10Hz 제어에서 waypoint 추종을 수행한다. yaw 오차 20°보다 크면 제자리 회전, 그 이하면 제한 속도 0.15m/s로 이동한다. 최종 정지 거리 0.08m다. 전방 예상 footprint에 새 장애물이 있으면 0속도를 보내고 재계획한다.
- 탐색 목표는 채점 섹터 안의 frontier 후보를 고른다. 후보별 경로 길이·미관측 주변 셀 수로 간단히 우선순위를 정하고, 결정 tie는 좌표 순으로 풀어 재현성을 유지한다. M1 탐색 섹터를 M3 채점 구역으로 사용하지 않는다.
- baseline은 현재 gimbal 위치의 정답 feedback을 받지 않는다. accepted gimbal command의 목표와 rate model로 자세를 추정한다. 직전 추정 각도에서 새 목표까지의 pan·tilt 각도 차 중 큰 값을 `speed_deg_s`로 나눈 예상 이동시간에 100ms를 더한 뒤 settled로 취급한다. 그 이전에 캡처된 관측은 위치 추정에 사용하지 않는다. locked·pause·report에서는 진행 중인 명령 추정을 취소하고 추정 불확실성을 유지한다. 실제 장비 feedback이 확보되면 현장 어댑터 정책으로 교체한다.
- 의미 bbox 중심에서 카메라 bearing을 얻고, settled 상태의 추정 pan과 자기 odometry로 world 방향을 계산한다. 같은 방향의 LiDAR 유효 range로 관측 위치를 대략 추정하되 대응 range가 없으면 bearing-only 관측으로 보관하고 정확한 세계 위치처럼 쓰지 않는다. pan 추정 오차·자기 odometry 오차를 함께 고려한다.
- 객체 track은 참가팀 코드가 생성한다. 추정 위치·면 normal·클래스 증거로 연결하며 단순히 클래스가 같다는 이유로 합치지 않는다. 초기 기준은 거리 0.12m 이하 및 면 normal 차이 30° 이하일 때 후보 매칭이다. 불확실한 연관은 보류한다. 이 값은 baseline 휴리스틱이지 정답 매칭 규칙이 아니다.
- 같은 track의 class evidence를 갱신하여 오인식을 수정할 수 있게 한다. 현재 최선의 track들을 섹터별로 집계하고 전체 M3 snapshot을 직렬 제출한다. 아직 보지 못한 영역을 ‘확실히 0개’로 내부 확정하지 않는다.
- M5 목표 수신 후 탐색을 중단하고 실제 게시된 목표로 이동한다. 4분 이후 자기 거점 strip을 회피 영역으로 취급한다.
- M6는 관측 이력 기반 기본 순위를 유지한다. 정보가 없으면 명시된 낮은 신뢰도의 결정적 fallback 순위를 사용한다. fallback을 정답 상태 추정으로 기록하지 않는다. 공식 LLM 사용 요건을 충족한 현장 대체 구현이라고 주장하지 않는다.

첫 baseline은 고정 소형 fixture에서 통합을 검증하고, 이어 랜덤 배치·시드에서도 crash 없이 끝나는지 시험한다. 인식 성능·경로 성공률은 별도 지표로 기록한다. 낮은 점수를 통합 실패로 숨기지 않는다.

## 8. 평가자용 2D 화면

Pygame-ce 화면은 read-only snapshot을 그린다. 렌더링 주기 기본 30Hz, 엔진 tick과 분리한다. 화면이 느리면 중간 snapshot을 버리고 최신 것만 표시하며 엔진을 느리게 하거나 시간을 건너뛰지 않는다.

화면에는 경기장, 섹터 경계, 물체 footprint, 로봇 진행 방향, 선택 로봇의 실제 시야·센서 ray, HP·탄약·단계·시간, 최근 이벤트, 저장된 보고와 평가 점수를 표시할 수 있다. 이 정보는 평가자 화면 전용이다. 참가팀용 드론 프레임이나 카메라 JPEG에 같은 overlay 함수를 재사용하지 않는다.

필수 조작은 재생/일시정지, 한 tick 전진, 배속 선택(가속 in-process 모드만), 로봇 선택, truth/observed layer 전환, 센서·궤적 표시 켜기, 이벤트 시점 이동이다. 경기 운영의 pause와 사용자 디버깅용 엔진 일시정지는 구분하여 별도 버튼·상태로 표시한다. 키보드 수동 주행을 켠 실행은 `controller_kind=manual_debug`로 기록한다.

화면 좌표 변환은 `px=origin_px+scale*x`, `py=origin_py-scale*y` 하나의 함수로 통일한다. 0.5m 격자와 축 화살표를 표시하여 좌우·상하 반전 실수를 찾게 한다. 화면 크기 변경은 viewport만 바꾸며 시뮬레이션 공간의 수치를 변경하지 않는다. 헤드리스 실행에서는 pygame import와 display 초기화를 하지 않는다.

## 9. 구현 단계와 단계별 합격 조건

| 단계 | 구현 산출물 | 다음 단계로 넘어가기 전 합격 조건 |
| --- | --- | --- |
| 2D-1 | 좌표·OBB·SAT·ray 순수 함수 | 경계·회전·가림 golden test 통과 |
| 2D-2 | 일정 twist 적분·공통 microstep | 직선·원호 수치 시험, 얇은 벽 관통 방지, 슬롯 순서 교환 시험 통과 |
| 2D-3 | 엔진 연결·watchdog·잠금 | pause/resume·report·피격 잠금 중 유효 twist가 규칙과 일치 |
| 2D-4 | odom·LiDAR·의미 관측 | FOV·가림·부호·중복 프레임 시험 및 truth 누출 검사 통과 |
| 2D-5 | 모의 경기 서버·대본 6대 | 5분 경기·조기 종료·M6 완료까지 헤드리스 실행 |
| 2D-6 | baseline·보고 집계 | 외부 참가팀 프로세스로 실제 API를 사용하며 정상 종료 |
| 2D-7 | viewer·replay·batch | viewer 유무에 따라 이벤트 hash가 같고 시드별 결과 보존 |
| 2D-8 | 3D 공통성 확인 | 같은 명령 replay에서 궤적·피격·채점 결과 동일 |

HTTP 서버·채점 엔진을 2D 안에 다시 구현하지 않는다. 공통 모듈이 아직 없으면 정의된 port의 fake를 테스트에만 사용하고, 통합 완료 단계에서는 실제 공통 모듈로 교체한다.

## 10. 최소 수치 회귀 시험

아래 ID는 전체 테스트 계획에서 추적한다. 모든 길이 단위는 m, 각도는 rad다.

| ID | 입력 | 기대 결과 |
| --- | --- | --- |
| D2-K01 | `(x,y,yaw)=(1,1,0)`, `v=.2,w=0`, 1초 | `(1.2,1,0)`, pose 오차 각 `1e-9` 이하 |
| D2-K02 | `(1,1,0)`, `v=0,w=1`, 1초 | 위치 동일, yaw 1, 오차 `1e-9` 이하 |
| D2-K03 | `(1,1,0)`, `v=.2,w=1`, 1초 | `x=1+.2*sin(1)`, `y=1+.2*(1-cos(1))`, yaw 1 |
| D2-K04 | yaw `pi-.01`, `w=1`, .02초 | 저장 yaw `-pi+.01`, 각도 비교 정상 |
| D2-C01 | 2cm 두께 고정벽에 최고속도로 전진 | 벽의 반대편으로 이동하지 않음; 승인 pose의 footprint 비겹침 |
| D2-C02 | 대칭 위치 두 로봇이 서로 접근 | 충돌 microstep에서 양쪽 정지; 슬롯 이름 바꿔도 대응 궤적 동일 |
| D2-C03 | A→B→고정벽 연쇄 후보 | 고정점 해결 후 모든 승인 footprint 비겹침 |
| D2-C04 | 장애물 옆 제자리 회전 | 코너가 스칠 swept bound이면 회전 거부, 중심만 보고 통과시키지 않음 |
| D2-S01 | 카메라 optical `(0,0,1)` 점 | 화면 중심 `(319.5,239.5)`에 투영 |
| D2-S02 | 팬 +20 wire units, yaw0 | 카메라 전방 yaw -10°; 차량 angular.z+와 부호 다름 |
| D2-S03 | 그림과 카메라 사이 불투명 박스 | 5/9 표본을 가리면 해당 detection 없음 |
| D2-S04 | 동일 그림이 서로 다른 두 면에 존재 | evaluator 정답은 2; participant detection에는 진짜 면 ID 없음 |
| D2-S05 | 드론 프레임 반복 장애 | JPEG와 captured timestamp 동일; 요청 횟수만 늘어남 |
| D2-P01 | viewer 끔/켬, 같은 seed·입력 | canonical event hash와 점수 동일 |
| D2-P02 | `stress_v1` 프로필 동일 seed 2회 | 같은 플랫폼·잠긴 의존성에서 관측 sequence 동일 |
| D2-P03 | 2D/3D 동일 명령 replay | 평면 pose와 공통 규칙 이벤트 동일; pixel hash 비교는 하지 않음 |

수치 오차 허용치는 순수 운동 ideal 시험에만 적용한다. 충돌 근처에서 실제 경로를 1e-9로 맞춘다는 뜻이 아니다. 전체 수용 기준과 실행 명령은 [테스트 계획](07_TESTS_AND_ACCEPTANCE.md)을 따른다.

## 11. 성능·기록·한계

성능 목표는 CPU 환경에서 6대·기본 fixture·의미 관측으로 1배속을 유지하는 것이다. 개발자가 사용한 CPU·OS·Python·의존성 버전·센서 설정을 결과에 남긴다. 공통 엔진 tick, 센서 생성, HTTP 처리, 화면 그리기의 p50/p95 지연을 분리한다. 느린 실행에서 tick을 건너뛰어 시간상 1배속처럼 보이게 하지 않는다. 헤드리스 가속 성능은 측정 지표이며 근거 없이 배수를 보장하지 않는다.

run에는 시드, 규칙/arena/robot/scenario hash, 참가팀 프로그램 버전, 명령·관측 이벤트, 종료 이유, 마지막 저장 보고, 미션별 점수, 충돌·미제출·재시작 수를 저장한다. 원본 mission code는 로그에서 마스킹한다. replay는 저장 명령과 결정적 sensor seed로 엔진을 재생하는 모드와 저장 관측을 참가팀에 재생하는 모드를 구분한다.

2D 점수는 시뮬레이터 규칙·가정 아래의 결과다. 원문에 없는 출발 판정·M3 계수·일시정지 시계 등은 [규칙 프로필](01_COMPETITION_RULES.md)의 SIM 선택을 사용한다. 실제 경기 정밀 주행·실물 카메라 인식·레이저 보정의 검증은 [현장 어댑터 계획](09_FIELD_ADAPTER_AND_QUESTIONS.md)에 남겨둔다.

## 12. 근거 자료

- [main 7c41444의 1차 사전교육](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PRESTUDY_1_2026.md): 12~16쪽 임무, 23~25쪽 경기장·박스·격자·스모그.
- [main 7c41444의 2차 사전교육](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PRESTUDY_2_2026.md): 10~18쪽 ROS, 주행 범위·watchdog·팬틸트 단위·카메라·재실행.
- [main 7c41444의 API 안내](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PARTICIPANT_API_GUIDE.md): 4~11단계 드론·보고·채점·종료.

구현에 필요한 조건은 이 계획 묶음에 포함되어 있다. 링크는 근거 확인용이며, 구현 중 원본 저장소의 코드나 archive 브랜치를 찾아 복사하는 것을 전제로 하지 않는다.
