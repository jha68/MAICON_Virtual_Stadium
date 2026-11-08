# 3D 경기장 시뮬레이션 구현계획

이 문서는 `maicon-sim` 저장소에 3D 경기장, 인쇄 이미지가 붙은 박스, 로봇, 카메라 및 센서 모델을 구현하는 작업 명세다. 2D와 같은 경기 코어·참가팀 프로그램·HTTP 규약을 사용하고 입력 영상과 공간 관측의 난도를 높인다. 이 파일의 기본값은 별도 표시가 없는 한 **시뮬레이터의 재현 가능한 기본 설정**이며 실제 대회 장비의 측정값이 아니다.

읽기 순서는 `00_START_HERE.md` → `01_COMPETITION_RULES.md` → `02_ARCHITECTURE_AND_CONTRACTS.md` → `03_PLAN_2D.md` → 이 파일이다. 전송 DTO와 오류 규약은 `05_SERVER_AND_ROBOT_API.md`, 시나리오·파일 형식은 `06_SCENARIOS_AND_ASSETS.md`, 최종 합격 기준은 `07_TESTS_AND_ACCEPTANCE.md`를 따른다. 공통 인터페이스와 이 문서의 표현이 충돌하면 02·05 문서의 계약을 우선하고, 구현자가 조용히 새로운 필드를 추가하지 않는다. 센서·기하·오류 주입의 직렬화 원본은 `contracts/sensor_profile.schema.json`과 `examples/sensor_profile_reference.yaml`이다. 본문의 수치는 해당 프로파일을 설명하며, 설정을 바꿀 때는 프로파일을 수정하고 관련 시험을 다시 실행한다.

## 1. 구현 결과와 충실도 범위

### 1.1 필수 결과

1. GPU 없이 Ubuntu 22.04 x86_64에서 PyBullet `DIRECT` + `ER_TINY_RENDERER`로 경기장과 여섯 로봇을 생성한다.
2. 로봇의 팬틸트에 따라 변하는 640×480 BGR 카메라 프레임을 생성한다. 참가팀의 실제 영상 인식 코드가 이 프레임을 입력받을 수 있어야 한다.
3. 상대·박스·벽·다른 면에 의한 3D 가림과 원근 축소를 재현한다.
4. 상공 카메라, 자체 오도메트리·IMU·합성 LiDAR를 참가팀 포트에 연결한다. 실제 미공개 센서 규격을 공식 규격인 것처럼 표시하지 않는다.
5. 같은 명령 기록에 대해 2D와 동일한 주행 궤적·레이저 유효피격·M5 판정·점수·상태 전이를 얻는다.
6. 경기 도중 영상 지연·중복·누락·스모그 외관 변화를 주입하고 기록 재생한다.
7. 참가팀용 영상과 평가자 전용 정답·분할 마스크·깊이·정확한 위치를 분리한다.
8. `GUI` 모드에서는 관찰자가 자유 시점으로 경기를 볼 수 있고, Pygame 관찰 창에서 참가팀 카메라와 지연 상태를 볼 수 있다. GUI 없이도 모든 필수 시험을 실행할 수 있어야 한다.

### 1.2 v1에서 의도적으로 제공하는 물리 수준

**v1의 로봇 몸체 이동은 공통 2D 운동학·충돌 코어가 결정한다.** PyBullet은 확정된 자세를 받아 공간 장면, 원근 영상, 깊이 및 비공개 레이캐스트를 제공한다. 3D 공간과 카메라가 존재하지만 검증된 6륜 접촉 동역학 시뮬레이터는 아니다.

- 모터 토크, 타이어 마찰, 스키드 스티어의 실제 슬립, 서스펜션, 전복, 오르막은 v1 합격 조건에 포함하지 않는다.
- 바퀴 여섯 개의 시각적 회전은 주행 속도에서 계산한 애니메이션이며 주행 권한이 없다.
- 이동 오차·정지 지연·오도메트리 드리프트는 공통 시뮬레이션 프로파일의 모델로 주입한다.
- `stepSimulation()` 또는 Bullet 속도·힘이 공통 코어의 위치를 다시 바꾸게 하면 실패다. 장면 동기화에는 `resetBasePositionAndOrientation()` 등 자세 지정만 사용한다.
- 휠 동역학이나 Gazebo를 추가하는 후속 버전은 별도 backend·별도 정확도 검증으로 진행한다. 해당 결과를 v1의 정확한 2D/3D 궤적 일치 시험에 섞지 않는다.

이 범위는 자료의 불확실성을 숨기지 않으면서 카메라 시점·가림·면별 관측·집계·보고를 검증하기 위한 설계 결정 `SIM-3D-FIDELITY`다.

## 2. 기술 구성과 모듈 책임

| 모듈 | 책임 | 가지면 안 되는 책임 |
| --- | --- | --- |
| `backends/bullet/backend.py` | Bullet 연결 수명, 장면 동기화, 센서 캡처 진입점 | 경기 상태·점수·HP 판정 |
| `backends/bullet/scene.py` | world entity와 Bullet body의 비공개 대응, 생성·삭제·자세 갱신 | 참가팀에게 정확한 entity 위치 제공 |
| `backends/bullet/projection.py` | 광학 프레임, intrinsics, view/projection, depth 변환 | 학습 모델 추론 |
| `backends/bullet/render_worker.py` | 캡처 작업, 단일 Bullet 소유 스레드/프로세스, 큐·지연 기록 | core tick 직접 변경 |
| `backends/bullet/asset_builder.py` | 절차적 mesh·texture 생성, asset manifest 적용, 캐시 | 인터넷에서 임의 이미지 자동 수집 |
| `core/geometry3d.py` | 2D·3D 공통 OBB·구·ray 교차, canonical blockers | 렌더러 픽셀을 통한 채점 |
| `core/laser.py` | 연속 조사 시간·쿨다운·피격·표적 파괴 공통 판정 | Bullet 별도 판정 구현 |
| `sensors/camera.py` | 캡처 계획, 노이즈, 공개 frame 생성 | segmentation truth 제공 |
| `sensors/drone.py` | 상공 카메라 캐시, 1/2/5초 정책·403·반복 정상 프레임 | 팀별로 다른 정답 장면 생성 |
| `sensors/odometry.py`, `imu.py`, `lidar.py` | 측정 모델·발행 주기·오류 주입 | 참가팀 코드에 world truth pose 노출 |

기본 의존성은 Python 3.10, NumPy, Pillow, PyBullet이다. 06 문서의 필수 RGB reference detector에는 `opencv-python-headless`를 사용하며 3D 비전 extra에 포함한다. 공통 프로젝트는 Pydantic 2·PyYAML·FastAPI·httpx·pytest·pygame-ce를 사용한다. 설치 시의 정확한 호환 패치 버전을 선택하고 lock 파일 및 플랫폼 정보를 남긴다. 이 계획은 특정 PyBullet 패치의 설치 성공을 이미 검증했다는 의미가 아니다. 설치가 실패하면 Python 3.10 기준 wheel 제공 여부부터 진단하고 GPU·ROS 설치를 요구하는 방향으로 임의 변경하지 않는다.

### 2.1 backend 인터페이스

다음은 역할 명세이며 전송 필드는 02 문서의 DTO가 원본이다.

```text
initialize(world_manifest, sensor_profile, asset_manifest) -> BackendReady
sync_scene(immutable_snapshot) -> None
capture_rgb(camera_id, captured_tick) -> CameraFrame
raycast_batch(rays) -> PrivateRayHits
close() -> None
```

- `initialize`는 반복 생성·종료를 시험할 수 있어야 한다. asset 불일치, 카메라 pose가 누락된 경우는 명확한 설정 오류다.
- `sync_scene`는 snapshot에 포함된 시각의 geometry만 사용한다. 캡처 중 mutable core 객체를 읽지 않는다.
- `capture_rgb`는 `sequence`, `captured_tick`, `received_tick`, `width_px`, `height_px`, `camera_id`, `encoding="bgr8"`, `data`를 가진다. in-process의 `data`는 contiguous uint8 H×W×3 배열이고, 전송 계층은 `GET /sim/robot/v1/camera`의 JPEG와 `X-Sim-Captured-Tick` 등 05 문서의 simulator metadata를 사용한다. 참가팀 adapter가 JPEG를 BGR로 decode한다. 이는 공식 대회 HTTP 카메라 API라고 주장하지 않는 simulator bridge다.
- private ray hit에는 body·link·surface 식별자가 있어도 되지만 공개 관측 DTO에 직렬화하지 않는다.
- 하나의 Bullet connection은 하나의 worker만 사용한다. HTTP handler와 코어가 같은 connection을 동시에 호출하지 않는다.
- 실행 종료·예외에서 connection, worker, 열린 파일을 정리한다. 두 번째 경기를 시작할 때 이전 body가 남지 않아야 한다.

## 3. 장면의 좌표와 기하

### 3.1 좌표계

| 프레임 | 정의 |
| --- | --- |
| World `W` | 경기장 남서 모서리 원점, +x 동쪽·BLUE→RED, +y 북쪽, +z 위 |
| Body `B` | 지면의 로봇 평면 중심 원점, +x 전방, +y 왼쪽, +z 위 |
| Gimbal `G` | 팬틸트 회전축의 기준점, 영점에서 축은 Body와 동일 |
| Optical `O` | 카메라 중심, +x 오른쪽, +y 아래, +z 영상 전방 |

길이는 m, 시간은 core tick 10ms, 회전 계산은 rad를 사용한다. yaw 양수는 반시계다. wire 팬틸트의 pan 양수는 오른쪽이므로 기하 yaw에는 음수로 들어간다. optical frame과 Body frame을 같은 축으로 취급하지 않는다.

### 3.2 경기장과 박스

- 공통 경기장은 6.12×5.00m, 벽 높이 0.40m다. 섹터·거점 수치와 fixture 배치는 06 문서에서 불러온다. 3D 파일에 같은 좌표를 다시 하드코딩하지 않는다.
- 바닥은 z=0 평면이다. 격자 0.20m와 섹터 표시를 texture로 그린다. 바닥 표식은 장애물 collider가 아니다.
- 벽은 OBB로 생성한다. 문서 기준의 벽 높이 외에 두께·재질은 합성 fixture 설정이며 world manifest에 저장한다.
- 표준 박스 크기는 0.40×0.40×0.40m다. 상면은 z=.40이고 네 수직 면에 이미지 또는 비채점 장식물을 배치한다.
- target/object/decoration 종류와 측면 `face_id`는 같은 asset manifest를 사용한다. 판에 붙은 실제 이미지가 M3 객체이고 물리 박스 자체가 하나의 객체라는 가정을 두지 않는다.
- material·texture plane은 외측으로 1mm 띄워 z-fighting을 방지한다. texture plane에 별도 물리 충돌 두께를 주지 않는다.
- 각 면별 local U/V와 outward normal은 아래 표를 따른다. `U×V=normal`이고 V는 위쪽이다.

| 면 | outward normal | U 오른쪽 | V 위쪽 |
| --- | --- | --- | --- |
| `+x` | +x | +y | +z |
| `-x` | -x | -y | +z |
| `+y` | +y | -x | +z |
| `-y` | -y | +x | +z |

이미지 파일은 행 0이 위쪽이고 mesh UV는 v=1이 위쪽이다. face별 checkerboard fixture로 좌우·상하 반전이 없는지 검증한다. 측면 이미지에 문자열 정답, class ID, object ID를 디버그 목적으로 합성해 넣지 않는다.

### 3.3 로봇의 합성 기하

다음 표 전체는 실제 장비를 측정한 사양이 아닌 `SIM-3D-GEOM` 기본값이다. 실제 자료의 전체 외형 치수 약 250×230×320mm를 바탕으로 재현 가능한 단순 도형을 정한 것이다. 모든 값은 sensor/robot profile에서 교체할 수 있어야 한다.

| 구성 | Body 기준 기본값 |
| --- | --- |
| 평면 충돌 footprint | x 길이 .23m, y 폭 .25m, centered rectangle |
| chassis ray-occluder | center `(0,0,.10)`, half extents `(.115,.09,.03)` |
| upper body mast ray-occluder | center `(-.04,0,.19)`, half extents `(.025,.025,.06)`, z=.13~.25 |
| 바퀴 | 6개, radius .045m, centers x `[-.075,0,.075]`, y `±.105`, z `.045`; 폭은 footprint 안으로 제한 |
| 팬틸트 pivot | `(.02,0,.23)` |
| 카메라 중심 | Gimbal 기준 `(.025,0,0)` |
| 레이저 발광점 | Gimbal 기준 `(.025,0,.02)`, 기본 방향 +Gx |
| 좌우 수광부 | centers `(0,±.110,.160)`, sphere radius .015m |
| LiDAR 기준점 | `(0,0,.145)` |
| IMU 기준 프레임 | Body와 동일 회전, position `(0,0,.10)` |
| marker pole | body xy `(-.08,0)`, z=.13~.32, radius=.005m; visual only |
| marker board | center `(-.08,.018,.27)`, normal=±Bx 양면, By 방향 폭 .06m, Bz 방향 높이 .08m; visual only |

표식의 +Bx 면은 U=+By, V=+Bz이고 -Bx 면은 U=-By, V=+Bz다. 바탕은 camp 색상이며 가로 검정 띠의 두께는 .004m다. 1줄은 body z=.27, 2줄은 z=.26/.28, 3줄은 z=.25/.27/.29에 중심을 둔다. 양면은 같은 camp·띠 수를 표현한다. 이는 `SIM-3D-GEOM`의 합성 표식이며 실제 안테나 띠의 측정 규격이 아니다. 2D 의미 관측과 3D oracle parity는 같은 marker plane의 3×3 내부 표본 9점 중 5점 이상이 가시적이고 투영 bbox의 폭·높이가 각각 4px 이상일 때에만 marker_readout을 만들 수 있다. 실제 3D RGB 인식기는 이 정답 readout을 받지 않는다.

ray-sensitive primitive와 visual detail은 manifest에서 구분한다. 2D·3D의 canonical 레이저 판정은 chassis·mast·박스·벽 등 공유 primitive를 기준으로 한다. 장식 바퀴의 삼각형 mesh가 우연히 판정을 바꾸지 않도록 한다. 카메라 영상에는 바퀴·LED·안테나 같은 시각적 부분을 표시할 수 있다.

- 초기 구현에서 로봇은 하나의 고정 base와 visual shapes의 집합이어도 된다. 6개 wheel joint 동역학을 만들 필요는 없다.
- 팬틸트는 core가 계산한 실제 보간 위치를 사용한다. 명령 목표 pan/tilt를 즉시 카메라 pose에 적용하지 않는다.
- 실제 API의 `ok`는 접수 완료다. 카메라 방향이 목표에 도착했다고 간주하지 않는다.
- 한 몸체의 양쪽 수광부를 같은 tick에 맞춰도 피격은 1회만 발생한다. 무적·잠금·HP 처리는 공통 rule engine에 위임한다.
- HP 표시 색과 탄약 표시를 구현할 경우 값 자체는 truth에서 파생하지만 **영상의 외형으로만** 참가팀에게 보인다. 별도 상대 HP·탄약 숫자 DTO를 만들지 않는다.
- 탄약 LED 배열의 정확한 배치·표현은 사전 자료가 완전하지 않다. 합성 기본값은 8개 점 중 잔탄 수만큼 점등하고 `SIM-3D-LED`로 표시한다. 이 패턴에 맞춘 알고리즘의 실전 적합성은 별도 보정 대상이다.

## 4. 카메라 투영을 정확하게 구현하는 방법

### 4.1 기본 intrinsics

`SIM-3D-CAM` 기본값은 다음과 같다.

```text
width=640, height=480
fx=320.0, fy=320.0, cx=319.5, cy=239.5
near=.02m, far=10m
distortion=disabled
capture_hz=10
```

이는 horizontal FOV 90°, vertical FOV 약 73.7398°인 핀홀 카메라다. 사전자료 하드웨어의 ‘160도, 5MP’만으로 실제 송출 영상의 왜곡·intrinsics를 확정할 수 없으므로 160도 렌즈를 정확히 모사한다고 주장하지 않는다. 현장 `camera_info` 또는 별도 측정값을 받으면 별도 calibration profile로 변경한다.

왜곡 확장은 Brown–Conrady 또는 별도 fisheye model 중 명시된 모델 하나를 선택하고 calibration 파일의 모델명이 없으면 거부한다. 두 모델의 계수를 혼용하지 않는다. 왜곡 모델이 없는 기본 fixture에서 투영 시험을 먼저 통과시킨다.

### 4.2 변환식

`R_AB`는 B 좌표의 벡터를 A 좌표로 옮기는 회전행렬이다. Body에서 Optical의 기본 회전은 다음과 같다.

```text
R_BO = [[ 0,  0,  1],
        [-1,  0,  0],
        [ 0, -1,  0]]

pan_rad  = pan_wire  * 0.5  * pi/180
tilt_rad = tilt_wire * 0.15 * pi/180

R_BG = Rz(-pan_rad) @ Ry(-tilt_rad)
R_WB = Rz(body_yaw)
R_WO = R_WB @ R_BG @ R_BO
p_WO = p_WB + R_WB @ p_BG + R_WB @ R_BG @ p_GO
```

tilt 양수에서 영상 전방이 위를 향하는지, pan 양수에서 오른쪽을 향하는지 수치 시험으로 확인한다. body yaw와 pan을 독립적으로 적용해야 한다.

World 점 `P_W`를 optical 좌표로 옮긴다.

```text
P_O = transpose(R_WO) @ (P_W - p_WO)
u = fx * X_O / Z_O + cx
v = fy * Y_O / Z_O + cy
```

`Z_O<=near` 또는 `Z_O>=far`인 점은 유효 투영 대상이 아니다. 화면 내부 여부는 pixel center 기준 `-.5 <= u < width-.5`, `-.5 <= v < height-.5`로 결정한다. 부동소수점 경계 오차 허용치는 1e-9이고 최종 픽셀 인덱스는 명시된 반올림 방식으로 정한다.

### 4.3 PyBullet view/projection과 배열

카메라 방향과 up 벡터는 다음처럼 구성한다.

```text
eye = p_WO
target = eye + R_WO[:,2]
up = -R_WO[:,1]
view = computeViewMatrix(eye, target, up)
```

중앙 principal point·정사각 픽셀 기본값에서는 `computeProjectionMatrixFOV(fov=73.739795..., aspect=640/480, nearVal=.02, farVal=10)`를 사용할 수 있다. 비중앙 principal point를 지원할 때는 intrinsics 기반 행렬을 생성한다. OpenGL camera 좌표가 optical의 `(X,-Y,-Z)`라는 점을 반영한다.

```text
P = [[2fx/W, 0,        1-2(cx+.5)/W,   0],
     [0,     2fy/H,   2(cy+.5)/H-1,   0],
     [0,     0,      -(f+n)/(f-n), -2*f*n/(f-n)],
     [0,     0,      -1,              0]]
```

이 수식은 행 기준이다. Bullet 인수로 전달하는 flatten 순서는 해당 API의 column-major 규약을 따라 변환하고, 행렬의 모양을 눈으로 보고 정하지 않는다. projection test가 전치·좌우 반전 오류를 검출해야 한다.

`getCameraImage(..., renderer=ER_TINY_RENDERER)` 결과 RGBA를 H×W×4로 reshape한다. Alpha를 제거한 RGB와 OpenCV용 BGR을 구분하고 `frame_bgr = frame_rgba[..., :3][..., ::-1].copy()`에 해당하는 변환을 한다. 참가팀은 uint8 BGR 입력을 받는다. JPEG 드론 응답은 인코더가 기대하는 RGB/BGR 순서로 한 번만 변환한다.

metric optical depth는 depth buffer `d∈[0,1]`에서 다음처럼 구한다.

```text
z_O = far*near / (far - (far-near)*d)
```

원시 depth buffer, segmentation body/link ID, metric depth는 기본적으로 **평가자 전용**이다. `d=1`인 background를 정답 물체로 처리하지 않는다. private artifact에서는 invalid mask를 함께 저장한다. depth를 참가팀에게 주는 실험은 별도 synthetic capability를 켠 경우에만 허용하고, 공식 `/image_raw`와 동일하다고 표기하지 않는다.

## 5. 이미지·재질과 데이터 분리

### 5.1 외부 자료 없이 재현되는 기본 자산

의존성 설치가 끝난 기본 실행은 외부 자산 다운로드 없이 동작해야 한다. 합성 generator가 PNG texture를 생성한다. 06 문서의 `procedural_v1`은 512×512이고 내부 그림 영역은 x/y 32~480px이며 모든 클래스에 동일한 검정 사각 테두리를 둔다. 테두리는 합성 판 검출 fixture이며 클래스별 코드가 아니고 실제 대회 인쇄물에 같은 테두리가 있다는 보장도 없다.

- 군용트럭: 차체·운전석·바퀴의 단순 실루엣.
- 박격포: 경사진 관·받침판·지지대.
- 전차: 차체·궤도·포탑·포신.
- 미사일: 길쭉한 몸체·날개·끝부분.
- 탄약상자: 직육면체 상자·뚜껑·손잡이.
- 드럼통: 원통·상하 타원·띠.
- 시설물 3종과 비채점 그림은 별도 generator로 생성한다.

합성 texture는 배선·이미지 전송·데이터셋 파이프라인 검증용이다. 이 여섯 도형에서의 정확도를 실제 M3 인식 성능으로 보고하지 않는다. class별 고정 배경색·정답 문자·바코드를 넣지 않고 배경·명암·크기·방향은 class와 독립적으로 변형한다.

### 5.2 필수 RGB reference detector

외부 학습 모델 선택 때문에 구현이 중단되지 않도록 06 문서 §6의 contour/template baseline을 필수 예제로 제공한다. BGR→grayscale, 검정 테두리 contour 중 convex quadrilateral·면적256px 이상 선택, TL/TR/BR/BL corner 정렬, 128×128 perspective warp, 네 회전방향의 template 정규화상관도 비교, score .75 미만 unknown, IoU .5 NMS, softmax(score/.1)의 class_probs를 사용한다. threshold의 원본은 06 문서이며 중복된 별도 값을 두지 않는다.

입력은 공개 RGB 배열뿐이고 원본 texture filename·face ID·segmentation·groundtruth bbox를 읽지 않는다. template asset은 참가팀에게 제공되는 공개 합성 훈련용 그림으로만 만들며 평가 장면 정답 manifest는 읽지 않는다. 합격 조건은 무잡음 정면 gallery에서 여섯 종류 각각의 판 이미지가 정확히 검출·분류되는 것이다. 이 결과는 파이프라인 배선 검증이며 실제 M3 일반화 성능의 보장이 아니다. 다른 인식 모델은 같은 callback으로 교체한다.

### 5.3 실제 또는 사용자 제공 이미지

사용자가 사용할 권한이 있는 자료를 `assets/user/`에 넣고 manifest로 연결한다. 원본 대회 이미지나 비공개 자료는 계획 묶음·기본 저장소에 복제하지 않는다.

- asset ID, class, source, license/사용 근거, 원본 SHA256, image dimensions, variant group, split group을 기록한다.
- train/validation/test split은 원본 이미지 group 단위로 한다. 동일 이미지의 색·원근 변형본을 다른 split에 넣지 않는다.
- 동일한 texture를 다른 물리 면에 붙일 수 있다. 그 경우 평가자 private face ID는 서로 다르지만 public 영상에는 ID를 표시하지 않는다.
- `face_id`의 정답 class·sector는 world manifest의 private truth에만 존재한다. RGB frame metadata에 넣지 않는다.
- normal map·PBR·photoreal assets는 v1 필수 요건이 아니다. 먼저 면 방향·원근·가림·정답 정합성을 맞춘다.

### 5.4 정답 annotation

데이터셋 생성 명령은 참가팀 실행과 별도 mode다. private segmentation과 manifest를 사용해 visible mask, 2D bbox, occlusion fraction, face ID, class를 산출한다.

- 이미지에 투영되는 원래 면 영역과 실제 visible area를 구분한다.
- renderer의 body/link segmentation만으로 같은 박스의 네 면을 구분할 수 없으면 면별 visual body를 별도로 생성하거나 private ID render pass를 구현한다. 색상 texture의 의미를 읽어 정답을 추측하지 않는다.
- private ID render pass의 카메라·geometry·tick은 RGB pass와 같아야 한다.
- 이미지 밖 bbox는 clip하며 visible pixel 0인 면은 visible annotation에 넣지 않는다. 전체 truth inventory에는 남는다.
- 모든 dataset frame은 episode ID, captured tick, seed, manifest hash, renderer version을 기록한다.
- 참가팀 process가 private artifact 폴더나 admin endpoint를 읽는 상태에서 ‘정보 누출 없음’ 시험을 통과했다고 주장할 수 없다. 기본 실행 프로세스와 파일 권한 경계를 02·05 문서대로 적용한다.

## 6. 센서 발행과 관측 모델

### 6.1 캡처 시각과 처리 지연

core dt는 10ms다. 10Hz 카메라는 10tick, 20Hz odom/IMU는 5tick, 2Hz 자체 상태는 50tick마다 계획된다. tick 0에서 초기 측정을 생성하고 이후 주기를 유지한다. 경기/보고 단계의 장치 허용 여부는 공통 rule profile이 최종 결정한다.

두 실행 모드를 구분한다.

| 모드 | 처리 방식 | 결정성 약속 |
| --- | --- | --- |
| Offline lockstep | scheduled snapshot마다 정해진 카메라 ID 순서로 캡처를 완료하고 다음 tick 진행 | 같은 고정 환경·seed·입력에서 센서 transcript 재현 |
| Realtime HTTP 1x | worker가 immutable snapshot 처리, 카메라별 pending latest-only 큐 1개 | 부하에 따른 frame drop·지연을 기록하며 seed만으로 동일한 drop을 보장하지 않음 |

realtime에서 core는 렌더 완료를 기다리며 멈추지 않는다. 완료된 frame은 engine event로 들어오며 `captured_tick`은 snapshot tick, `received_tick`은 실제 engine 수신 tick이다. 시간 역전·미래 frame은 validation error다. 렌더 큐에서 교체된 요청은 `capture_dropped` 이벤트로 기록한다. 이미 생성된 오래된 frame에 새로운 captured timestamp를 붙이지 않는다.

같은 connection에서 각 camera snapshot을 순서대로 sync/render한다. 서로 다른 tick의 로봇 pose와 camera pose를 섞지 않는다. renderer가 처음 생성한 영상이 black frame이면 자동으로 정상이라고 간주하지 않고 health check가 원인을 보고한다.

### 6.2 자체 카메라

- 기본 640×480 BGR, 10Hz. 실제 자료의 최대 30FPS와 권장 10FPS 이하를 구분한다.
- 카메라 pose는 실제 gimbal interpolation 상태에서 계산한다. LLM·모델 추론 완료 시점이 capture 시점을 바꾸지 않는다.
- 자체 상태 bridge는 현재 source로 확인되는 `hp`, `hp_max`, `battery_pct`만 제공한다. 잔탄은 별도 정답 field로 추가하지 않고 성공한 자기 발사 이력으로 추정할 수 있다.
- baseline perception callback은 `CameraFrame`을 받고 DetectionObservation 등 공통 관측으로 변환한다. 모델 추론은 participant 영역이며 simulator truth와 연결하지 않는다.
- 2D의 semantic observation을 3D RGB 성능 측정에 몰래 병행 제공하지 않는다. oracle 모드는 별도 run label로 표시하고 결과를 후보 시스템과 분리한다.

### 6.3 상공 카메라

`SIM-3D-DRONE` 기본 camera pose는 경기장 중심 `(3.06,2.50,2.50)`에서 지면 중심을 바라보는 nadir view다. 화면 오른쪽은 +x, 위쪽은 +y가 되게 설정한다. 해상도·FOV는 sensor profile로 정의하며 전체 6.12×5m 바닥이 들어오도록 기본 HFOV 110°, 1280×1024를 사용한다. 이 카메라의 자세·해상도·FOV는 실제 제공 영상 규격으로 확정된 값이 아니다.

- `/api/report/drone`은 이 camera의 JPEG cache를 반환한다. 팀별 프레임 생성 camera를 따로 만들지 않는다.
- 경기 요청에서는 자기 진영 파괴 시설 수 0/1/2개일 때 1/2/5초 간격의 접근 가능 프레임을 적용하고, 3개이면 403을 반환한다. 최신 정책은 공통 rule profile이 원본이다.
- 프레임 생성과 팀별 접근 갱신은 분리한다. 접근 간격 안의 반복 요청은 같은 JPEG bytes와 `X-Captured-At`을 반환한다.
- 화면이 깨졌다는 fault에서는 마지막 정상 JPEG를 유지한다. 정상 프레임이 한 번도 없으면 503이다.
- reporting부터 경기 영상 요청은 409다. `camera=`를 사용한 연습은 05 문서의 테스트 모드 규칙을 따른다.
- camera profile의 epoch로 `X-Captured-At`을 생성한다. 실제 computer wall clock을 매번 붙여 재현성을 깨지 않는다. HTTP wait timeout과 표시용 epoch는 별개다.

### 6.4 합성 LiDAR

공식 LiDAR 토픽·세부 제원은 현재 자료에 없으므로 다음은 `SIM-3D-LIDAR` 실험 프로파일이다.

```text
origin_B=(0,0,.145)
scan_hz=10
angle_min=-pi
ray_count=360
angle_increment=2*pi/360
range_min=.05m, range_max=8m
ideal: noise sigma=0, no_return_probability=0
stress_v1: Gaussian sigma=.01m, no_return_probability=.02, then range clipping
```

ray는 Body 수평면에서 쏘며 world yaw를 적용한다. 자기 body는 hit에서 제외하고 box·wall·다른 로봇의 canonical solid primitive가 range를 결정한다. 공개 값은 range 배열·각도 규격·capture tick이며 hit entity ID·class·sector는 없다. 기하 no-return 또는 stress_v1의 독립 .02 dropout은 JSON에서 `null`을 사용하고 NaN/Infinity를 쓰지 않는다. 유효거리 Gaussian noise sigma=.01m 후 [.05,8]로 clip한다. ideal에는 측정 noise와 확률 dropout을 적용하지 않는다. 프로파일 전체의 권위는 06 문서 §8이다. ROS adapter가 필요하면 최종 LaserScan 규약으로 변환한다.

2D·3D sensor parity를 요구하는 fixture에서는 같은 analytic raycast를 사용한다. Bullet `rayTestBatch`는 geometry 대조·debug 또는 명시된 별도 visual visibility profile에 쓸 수 있지만, 배치에 따라 판정 결과가 달라지는 것을 숨기지 않는다. physical fixture의 canonical solids와 Bullet proxies의 첫 hit 거리를 비교하는 시험을 둔다.

### 6.5 오도메트리

20Hz, 자기 경기 시작 위치를 원점으로 하는 측정 pose를 제공한다. world 정확한 좌표를 참가팀에게 직접 넘기지 않는다.

- canonical profile에서는 시작 pose 기준 상대 운동을 정확하게 적분한다.
- stress_v1에서는 이동 scale=1.02, yaw rate bias=.005rad/s, position increment noise sigma=.001m를 사용한다(06 문서 §8). 추가 random walk는 별도 이름의 명시된 실험 프로파일만 사용할 수 있다. truth 이동을 바꾸는 actuator error와 센서 오차를 구분한다.
- restart 후 odom 원점이 바뀌는지 여부는 profile에 명시한다. 기본값은 같은 match에서 보존, 새 match에서 초기화다.
- odom pose, quaternion, twist, covariance(모델에 맞는 값), frame 이름의 변환은 공통 DTO와 ROS adapter가 담당한다.

### 6.6 IMU

20Hz, quaternion과 angular velocity 및 specific force를 만든다. `SIM-3D-IMU` 기본 convention에서 gravity world vector는 `(0,0,-9.80665)`이고 다음을 사용한다.

```text
specific_force_B = transpose(R_WB) @ (acceleration_W - gravity_W)
```

따라서 정지 상태의 z축 값은 +9.80665m/s²다. gravity removed data를 쓰는 profile은 반드시 별도로 이름 붙인다. angular velocity 단위는 rad/s, acceleration 단위는 m/s²다. yaw 차이는 unwrap 후 차분하고 tick dt를 사용한다. 센서가 정지됐을 때 마지막 측정을 새 시각으로 재발행하지 않는다. stress_v1은 yaw rate bias=.005rad/s, angular noise sigma=.002rad/s, acceleration noise sigma=.02m/s²이며 06 문서 §8의 값을 단일 설정으로 참조한다.

## 7. 레이저와 판정의 공통 기하

3D 렌더된 빨간 점이나 화면상의 밝은 pixel을 판정에 사용하지 않는다. **2D와 3D 모두 같은 analytic ray–receiver 교차 판정**을 사용한다. 시각적 레이저 광선은 해당 판정을 설명하는 debug layer이며 참가팀 camera에 보이게 할지는 synthetic scene profile이 결정한다.

기본 laser origin과 direction:

```text
p_WL = p_WB + R_WB @ p_BG + R_WB @ R_BG @ p_GL
d_WL = R_WB @ R_BG @ [1,0,0]
```

- 시설 수광부는 해당 표적 면의 외측 normal 방향으로 .021m 떨어진 높이 z=.35m, radius=.02m 구를 기본 fixture로 사용한다. receiver pose는 box pose를 적용한다.
- 로봇 수광부는 3.3의 좌우 구를 사용하고 robot pose를 적용한다. sphere radius·위치는 모두 보정 가능한 가정이다.
- ray가 receiver보다 먼저 wall·box·다른 robot canonical blocker를 만나면 유효 조사가 아니다. 발사 로봇 자기 몸체는 기본 판정에서 제외한다.
- 한 ray가 여러 receiver를 향하면 가장 가까운 가리지 않은 receiver만 조사된다. ray intersection epsilon=1e-9m, endpoint/self-surface exclusion=1e-6m다. 거리 차이가 1e-9m 이하인 hit tie에서는 occluder를 먼저 적용하고, 그다음 stable private geometry_id로 정렬한다. targeted surface 가시성의 blocker는 target 거리보다 1e-6m 이상 앞선 교차만 인정한다. 이 값은 06 문서 §7의 공유 상수로 사용한다.
- 연속 조사 2초는 200개의 10ms 유효 interval이다. 중간에 target 변경·가림·발광 중단·pause·잠금이 들어오면 공통 01·02 문서의 dwell 정책을 따른다.
- 피해·점수는 3D backend가 직접 변경하지 않는다. shared laser event만 rule engine에 전달한다.
- Bullet world와 ray 판정 primitive가 다르게 구성된 경우 scene validation이 실패해야 한다. 머리·안테나 등의 장식은 canonical blocker 여부를 manifest에 명시한다.

실제 레이저 확산각, 수광부 shape·각도 응답, 빛의 반사, 연기 중 감쇠는 알려진 값이 아니다. v1은 직선 ray와 receiver sphere를 사용한다. 확산각이 필요하면 별도 beam model을 추가하되 기본 채점 회귀시험과 섞지 않는다. 연기에 레이저 감쇠를 추가하는 것은 공식 규칙 재현으로 표기하지 않는다.

## 8. 조명·스모그·영상 오류

### 8.1 변경 가능한 요소

각 요소는 독립 seed stream을 가진다. class나 정답 개수에 따라 노이즈 세기를 바꾸지 않는다. named profile `ideal`과 `stress_v1`의 수치 원본은 06 문서 §8이다. `stress_v1`에서 camera delivery delay=100ms, independent frame drop=.05, drone delivery delay=100ms를 사용한다. 아래의 조명·blur·왜곡 확장값은 명시된 별도 profile이 켠 경우만 적용하고 stress_v1에 임의의 기본값을 추가하지 않는다.

- 광원 방향, ambient/diffuse 세기, 바닥·벽 albedo.
- 노출·white balance·gamma·Gaussian noise·JPEG quality.
- 카메라 pose의 작은 calibration bias.
- blur와 프레임 드롭. 기본 canonical profile은 모두 off.
- 이미지 source group·표면 각도·거리·가림.

노이즈 적용 순서는 render RGB → optional lens warp → depth-based fog → exposure/white balance/gamma → blur → sensor noise → uint8 clip → BGR/JPEG 변환으로 고정한다. 같은 seed에서 순서가 바뀌어 다른 결과가 생기지 않도록 profile version을 기록한다.

### 8.2 스모그의 정직한 모델

자료에는 중앙 측면의 포그머신이 있지만 입자·농도·광학 모델은 없다. `SIM-3D-FOG`는 RGB robustness용 근사다.

```text
T = exp(-beta * path_length_in_fog)
I_fog = T * I + (1-T) * fog_rgb
```

fog volume은 `render.fog_model=volume`, `render.fog_volume_world_aabb_m=[[min_x,min_y,min_z],[max_x,max_y,max_z]]`로 설정한다. 모든 축에서 min<max여야 한다. `fog_model=full_scene`은 카메라부터 표면까지 전체 광로에 적용하는 별도 모형이며, 기존 schema 1.0 설정에서 fog_model이 생략되면 이 full_scene 모형을 사용한다. 두 모형은 실행 metadata에 구분해 기록한다. 카메라 ray와 fog AABB의 교차 길이 중 해당 pixel surface까지의 길이를 `path_length_in_fog`로 쓴다. `beta=0`이면 pixel 값이 변하지 않는다. 공간 volume이 없는 간단한 full-scene fog profile도 이름을 구분한다.

이 모델은 volumetric scattering이나 실제 LiDAR interference를 검증한 것이 아니다. canonical fixture에서 fog는 RGB만 바꾸고 geometry, M3 truth, laser 판정, LiDAR는 바꾸지 않는다. LiDAR dropout을 함께 시험하려면 독립 fault를 명시적으로 켠다. 반사·레이저 감쇠까지 자동으로 바꿔 실제 규칙인 것처럼 만들지 않는다.

## 9. 관찰 UI와 실행 기록

### 9.1 관찰자 기능

- PyBullet GUI 자유 시점, camera orbit·zoom, 일시정지·단계 진행은 admin command를 통해서만 요청한다.
- Pygame 창에는 선택한 로봇 카메라, drone, backend fps, captured/received tick, dropped count를 표시한다.
- true pose·class·receiver·laser ray overlay는 `observer_truth` 옵션으로 켜며 participant frame에는 합성하지 않는다.
- 동일한 HUD 숫자가 screenshot에 보인다고 참가팀 입력 이미지에 붙이지 않는다.
- pause·reset·step·seed 변경은 로그에 남긴다. GUI의 manual control이 후보 autonomous run에 섞이면 해당 run을 `manual_intervention=true`로 표시하고 자율 점수 비교에서 제외한다.

### 9.2 저장해야 할 artifact

`RUN_ROOT/public/<slot>/`, `RUN_ROOT/private/`, `RUN_ROOT/summary/` 경계와 이름은 02·08 문서의 기준을 따른다. `RUN_ROOT`는 `--out`으로 지정한 정확한 디렉터리다. 최소 필드는 다음과 같다.

- 공개 입력·출력 event transcript, frame index와 content hash.
- run config, rule/schema/asset hashes, seed, package lock·platform·renderer 정보.
- 참가팀 RGB 샘플 또는 압축 영상, capture/received tick 대응표.
- evaluator private truth, masks, metric depth, canonical ray hits.
- render latency p50/p95/p99, dropped request 수, peak RSS, real-time factor.
- 정확한 pixel hash 일치는 동일 pinned 환경에서만 검증한다. 다른 OS·renderer의 작은 pixel 차이는 geometric acceptance로 대조한다.

raw frame을 무조건 모두 RAM에 보관하지 않는다. 지속 recording은 bounded writer queue를 사용하고 queue 가득 참 정책·drop count를 기록한다. recording 실패가 주행 core를 멈추게 하지 않는다.

## 10. 구현 단계와 완료 조건

### B3-01 최소 headless renderer

작업: PyBullet DIRECT 연결, 바닥·벽·박스 1개, 고정 camera, RGB 저장, 반복 close/reopen 구현.

완료 조건: 네트워크·GPU 없이 640×480 uint8 frame 생성; scene 생성/종료 10회 뒤 body·worker 누수 없음; screenshot이 all-black 또는 all-white가 아님; 실패 시 명확한 exit code.

### B3-02 scene manifest와 asset builder

작업: 공통 world manifest로 모든 entity 생성; 여섯 robot; 면별 이미지; UV orientation; seed 기반 synthetic assets.

완료 조건: manifest entity 수와 scene registry 대응 일치; face마다 checkerboard 방향 정확; 같은 box의 서로 다른 면이 다른 이미지를 표시; asset 누락 시 조용한 fallback 대신 validation error 또는 명시된 placeholder 모드.

### B3-03 camera/gimbal·shared integrator 연결

작업: core snapshot sync, Body/Gimbal/Optical transforms, projection, actual gimbal pose 캡처.

완료 조건: 아래 T3D-01~05 통과; 2D와 3D root trajectories 일치; Bullet가 core pose를 변경하지 않음.

### B3-04 public sensors·private truth 분리

작업: camera·drone·odom·IMU·LiDAR cadence, image blob delivery, private annotation.

완료 조건: sensor timestamp·배열 dtype·색 순서 시험; participant 응답에서 entity ID·true global pose·opponent state·segmentation field 누출 없음; RGB baseline이 oracle endpoint 없이 동작.

### B3-05 faults·replay·realtime worker

작업: bounded capture 큐, drop·latency·duplicate faults, fog/noise profiles, deterministic offline replay.

완료 조건: 느린 렌더러에도 command heartbeat 유지; 반복 drone frame bytes와 timestamp 유지; fault schedule을 재생하면 같은 공개 event transcript 복원; pause/reporting 정책 유지.

### B3-06 full episode·batch·handoff

작업: six-agent scripted fixture, 실제 vision callback, full match·조기 종료·M6 보고, headless batch, GUI observer.

완료 조건: 06 §6 RGB reference detector의 6종 정면 gallery 시험, 07 문서의 공통 acceptance와 아래 모든 필수 T3D 통과; canonical oracle 결과는 2D와 점수 일치; RGB 후보 점수는 별도 결과로 기록; exact build/run commands·보정 profile 변경법·기하 충실도 한계를 README에 명시.

## 11. 수치 검증과 회귀시험

아래 ID는 07 문서의 시험 목록에 매핑한다. tolerance를 넓혀 실패를 숨기지 않고 transform·렌더링 경계 원인을 수정한다.

| ID | 입력·절차 | 합격 결과 |
| --- | --- | --- |
| T3D-01 | canonical camera, optical point `(0,0,1)` | 연속 투영 `(319.5,239.5)` 오차 1e-6px 이하 |
| T3D-02 | optical points `(.1,0,1)`, `(0,.1,1)` | 각각 `(351.5,239.5)`, `(319.5,271.5)` 오차 1e-6px 이하 |
| T3D-03 | yaw=0, pan_wire=+20, tilt=0 | optical forward world yaw=-10°; positive pan이 오른쪽임 |
| T3D-04 | yaw=0, pan=0, tilt_wire=+20 | optical forward elevation=+3° |
| T3D-05 | camera forward plane z_O=2m, center pixel depth | depth buffer 역변환 2m 오차 1mm 이하; RGB 투영과 private mask 경계 1px 이내 |
| T3D-06 | 적·청 checker texture, 네 면 각각 정면 캡처 | BGR 채널·좌우·상하 방향 일치, grayscale 채널 기준 fixture 오차 범위 내 |
| T3D-07 | 동일 시야 대상 앞에 완전 차폐 box 삽입 | 뒤쪽 대상 visible pixel=0, private full inventory 유지 |
| T3D-08 | 앞 box를 옮겨 대상의 절반만 보이게 함 | visible fraction 감소, full instance count는 변하지 않음 |
| T3D-09 | 1초=100tick canonical run | camera tick0 포함 11개, odom/IMU21개, state3개; endpoint convention 동일 |
| T3D-10 | drone 2초 제한 중 여러 GET | 새 허용 capture 전에는 동일 JPEG hash·X-Captured-At; 파괴3개403 |
| T3D-11 | laser 조준·가림·연속 199/200interval fixture | 2D와 같은 hit/no-hit, 이벤트 tick·HP·M2 점수 정확 일치 |
| T3D-12 | RGB public request·로그·오류 응답 검사 | opponent HP/ammo/M3, entity truth ID, segmentation/depth truth 미노출 |
| T3D-13 | canonical 2D/3D에 동일 action transcript | 모든 core pose 1e-9m/rad 이내, 판정 이벤트·점수·종료 tick 일치 |
| T3D-14 | same pinned renderer·seed·snapshot 2회 | RGB hash 일치; 다른 플랫폼은 geometric tests로 대체하고 pixel 재현 한계 기록 |
| T3D-15 | 렌더에 500ms 지연 fault | realtime core 10Hz command 처리 유지, capture queue bounded, 오래된 frame timestamp 유지 |
| T3D-16 | fog beta0 및 beta 증가 | beta0 RGB와 동일; 증가 시 지정 volume 뒤 contrast 감소; 판정 geometry/점수 불변 |
| T3D-17 | stationary IMU 및 yaw 회전 | canonical specific_force z=+9.80665, angular rate rad/s; deg/rad 혼용 없음 |
| T3D-18 | same match participant restart, then new match | renderer instance 중복 없음; 이전 frame/scene/session 데이터가 새 경기로 누출되지 않음 |

sensor count 시험은 닫힌 구간 `[tick0,tick100]`을 관측한 결과다. batch가 마지막 tick sensor를 출력하기 전에 종료되는 설정에서는 합격 수치를 바꾸지 말고 capture API의 종료 구간을 명시하여 같은 convention으로 검사한다.

### 11.1 성능 측정과 기능 합격의 구분

CPU TinyRenderer가 임의 하드웨어에서 여섯 카메라×10Hz를 충족한다고 보장하지 않는다. 구현자는 다음 세 profile을 각각 측정한다.

1. headless core+3D, 참가팀 camera 1대 10Hz, drone1Hz.
2. camera6대10Hz+drone1Hz.
3. camera6대+RGB inference+recording.

필수 기능 합격은 offline lockstep에서 의미가 동일하게 끝까지 실행되는 것이다. realtime profile은 해당 machine의 p95 render time·dropped fraction·real-time factor를 보고한다. 1x를 만족하지 못하면 `not realtime capable at this profile`이라고 표시하고 fps를 몰래 낮추거나 capture tick을 조작하지 않는다. 관측 정책을 바꾼 저부하 실험은 별도 profile 이름으로 저장한다.

메모리 큐 상한은 명시적이며 full episode 길이에 비례해 RAM이 계속 증가하면 실패다. 고정 입력 반복 실행에서 process 누수 여부도 검사한다.

## 12. 현장 연결과 추가로 필요한 보정

3D에서 검증한 participant core를 실제 로봇에 가져갈 때 renderer를 ROS adapter로 교체한다. 다음 값은 현장에서 얻어야 한다.

- 실제 camera intrinsics·왜곡 모델, `/image_raw` 인코딩·노출·실제 cadence.
- 카메라·팬틸트·레이저·LiDAR·수광부의 상대 위치와 영점 오차.
- 팬틸트 speed·acc 실제 응답과 도착 지연.
- odom frame 초기화, yaw convention, LiDAR topic/type/QoS, IMU gravity convention.
- 실제 상공 camera pose·해상도·calibration, 영상 지연·저하 조건.
- 인쇄 원본의 크기·해상도·표면 반사, 본선 조명·스모그의 영향.

이 값을 바꾸면 simulator calibration profile을 새 버전으로 저장하고 T3D projection·시야·주행 기록 회귀시험을 다시 돌린다. 실물에서 검증하지 않은 물리 fidelity를 ‘디지털 트윈 검증 완료’라고 표현하지 않는다.

## 13. 근거와 가정 추적

근거 commit은 `7c414445fcf0302620b2c89f16ce2064f91ca753`이다. 아래 출처 없이도 이 구현 명세와 fixture만으로 합성 시뮬레이터를 만들 수 있어야 한다. 출처는 공식 정보와 가정을 구분하기 위한 참조다.

- [1차 사전교육 12·13쪽](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PRESTUDY_1_2026.md#L161): 지정표적 이미지와 박스 면의 객체 그림, M3 이미지 변경 가능성.
- [1차 사전교육 21~25쪽](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PRESTUDY_1_2026.md#L309): 장비 외형, UAV, 경기장, 스모그. 정확한 sensor extrinsics는 여기서 확정되지 않는다.
- [2차 사전교육 10~18쪽](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PRESTUDY_2_2026.md#L145): 관측 주기, wire pan/tilt 단위·부호, `/image_raw` 640×480 BGR, 팀 노드 제어 요구.
- [API 안내 4단계](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/materials/PARTICIPANT_API_GUIDE.md#L297): JPEG, X-Captured-At, 진영별 영상 저하·반복 정상 프레임.
- [3차 멘토링](https://github.com/jha68/MAICON/blob/7c414445fcf0302620b2c89f16ce2064f91ca753/docs/mentoring/MENTORING_3_SUMMARY.md): 최종 API 재배포, Depth 별도 API 미제공, 상대 정보 접근 범위.

| 가정 ID | 이 문서에서 결정한 값 | 구현자가 지켜야 할 경계 |
| --- | --- | --- |
| SIM-3D-FIDELITY | 공통 planar dynamics + 실제 3D sensing/render | wheel 동역학 정확성을 주장하지 않음 |
| SIM-3D-GEOM | 로봇·수광부·laser 설치점의 기본 primitive | profile로 변경, 공식 측정값처럼 표시하지 않음 |
| SIM-3D-CAM | 90°HFOV pinhole,640×480,기본 왜곡없음 | 160° 실제 렌즈와 동일시하지 않음 |
| SIM-3D-DRONE | 중앙2.5m nadir,1280×1024,110°HFOV | 실제 영상 sample로 보정 필요 |
| SIM-3D-LIDAR | 360rays,10Hz,.05~8m | 미공개 공식 LiDAR 규약으로 위장하지 않음 |
| SIM-3D-IMU | specific force에 gravity 포함 | SDK convention 확인 후 adapter 변환 |
| SIM-3D-LED | 합성 HP/탄약 외형 | 실제 패턴 학습 성능으로 주장하지 않음 |
| SIM-3D-FOG | depth/path 기반 RGB contrast 근사 | 레이저·LiDAR 물리를 자동 변경하지 않음 |
