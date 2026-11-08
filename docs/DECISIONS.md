# 구현 중 계약 변경 기록

첨부 계획은 설계 입력이다. 아래 수정은 대회 공식 사실을 변경하지 않으며, 문서·스키마·실행 시험 사이의 누락과 모순을 해소한다.

## D001 — 산출물 경로의 권위 통일

발견: `04_PLAN_3D.md` §9.2는 `artifacts/public/<run_id>` 등 이전 형태를 사용했으나 02 §10과08 §3은 `--out`의 정확한 디렉터리를 RUN_ROOT로 정의한다. 00의 권위 규칙에 따라02/08을 적용하고04의 경로를 `RUN_ROOT/public/<slot>`, `private`, `summary`로 정정했다. private annotation을 참가팀 입력 경로로 전달하지 않는 경계는 유지한다.

관련 회귀: PACK-008/009 및 ISO-002/006, 산출물 실제 경로와 wheel 외부 실행 시험. 결과는 IMPLEMENTATION_STATUS.md와 시험 보고서에서 별도로 확인한다.

## D002 — 스모그 광로 모형의 설정 누락 보완

발견: 04 §8.2는 world AABB volume의 광로 길이와 이름이 구분된 full-scene 모형을 요구하지만 `sensor_profile.schema.json`의 render는 volume과 모형 선택 필드를 허용하지 않았다.

수정: 선택 필드 `render.fog_model` (`volume`/`full_scene`) 및 `fog_volume_world_aabb_m` (`[[min_xyz],[max_xyz]]`)를 계획 계약과 패키지 계약 양쪽에 추가했다. volume이 활성화되면 AABB가 필수이고 각 축 min<max를 의미 검증한다. 기존 schema1.0 입력에 모형 필드가 없으면 명시적으로 full_scene 모형을 사용한다. 기존 예제는 fog 비활성 상태를 유지한다. 모형과 파라미터는 실행 manifest에 남긴다.

관련 회귀: T3D-16, RENDER-018 및 보충 FOG-001(β0 항등), FOG-002(volume 앞/뒤 광로), FOG-003(잘못된 AABB 거절). RGB 대비 근사이며 레이저·LiDAR·채점의 물리 모형을 바꾸지 않는다. 실제 연기 검증은 H에 남는다.


## D003 — 동결 전 심판 정정의 명시적 계약

발견: 01 §5.6과02의 실행 순서는 동결 전 심판 정정 시험을 언급했지만, 06 예약 사건 목록과 scenario schema에는 이를 표현할 사건과 값 범위가 없었다.

수정: 평가자 전용 `robot_state_correction` 사건을 추가했다. parameters는 `slot` 및 `hp`(엄격한 정수0..4) 또는 `ammo`(엄격한 정수0..8)를 받으며, 추가 필드·전체 누락·bool·실수는 거절한다. running 중 동결 전의 상태 정정만 허용하고 reporting 이후에는 409/event_rejected로 거절한다. 이 사건은 공식 대회 wire API가 아닌 SIM-FREEZE fixture이며 참가팀 HTTP endpoint는 추가하지 않는다. 계약 스키마와 패키지 스키마, 01/06의 설명을 함께 갱신했다.

관련 회귀: RULE-023 동결 검증 및 CORRECTION-001(동결 전 실제 반영), CORRECTION-002(동결 뒤 거절·위험도 불변), CORRECTION-003(엄격한 타입·범위·공개 요청 거절). 관리자 주입을 자율 레이저 공격 성공으로 보고하지 않는다.

## D004 — 실시간 렌더러의 프로세스 격리

발견: PyBullet 연결을 한 스레드에만 맡겨도 `getCameraImage`의 C 호출이 Python GIL을 오래 점유할 수 있다. 실제 500ms 지연 시험에서 스레드 구현의 주행 heartbeat 간격이 0.513초까지 벌어져 0.5초 watchdog 요구를 만족하지 못했다. 합격 허용치를 넓히지 않았다.

수정: 실시간 `AsyncBulletBackend`는 별도 spawned process 하나가 Bullet 연결과 scene을 단독 소유한다. 부모의 작은 broker는 카메라마다 latest-only pending 1개와 completed 1개만 유지하고, 세션 generation이 다른 완료 프레임은 버린다. 오프라인 lockstep은 동기 `BulletBackend`를 사용한다. 두 경우 모두 공통 코어가 계산한 pose만 동기화하며 Bullet 동역학이나 별도 채점은 사용하지 않는다.

관련 회귀: RENDER-011/T3D-15의 실제 1초·100Hz 코어와 10Hz 명령 heartbeat, 500ms 지연 중 큐 상한·capture timestamp 보존 시험. T3D-18은 참가팀 객체를 같은 scene에서 실제 두 번 초기화·종료하고 새 경기 reset 후 프레임/sequence 분리를 확인한다. 프로세스 격리는 특정 CPU에서 6개 카메라×10Hz 성능을 보장하는 주장이 아니며, 렌더 지연·drop·queue peak를 별도 측정한다.


## D005 — 드론 연습 모드의 운영 설정 경로 보완

발견: 05 §7은 test_mode=true에서 지정한 연습 카메라를 경기 단계·시설 저하와 무관하게 제공하도록 정의했지만, 해당 운영 설정을 켜는 입력 경로가 없었다. Python 내부 필드만 변경할 수 있으면 문서의 기능을 외부 운영자가 재현할 수 없다.

수정: SIM 관리자 `/admin/configure`에 선택 필드 `test_mode`(엄격한 boolean)를 추가하고 보충 `admin_configure.schema.json`을 계획 계약과 패키지 리소스에 함께 제공한다. 기본 false, 생략 시 기존 설정 유지이며 비활성 세션에서만 변경한다. 참가팀 API나 공식 대회 규칙에는 필드를 추가하지 않는다. true이면서 camera를 명시한 요청만 연습 우회가 적용되며, camera 생략 요청은 기존 경기 제한을 적용한다.

관련 회귀: ADMIN-TEST-MODE-001은 실제 관리자 설정으로 활성화한 후 경기 밖 연습 JPEG 200, camera 생략 경기 요청 409, 잘못된 bool 422, 진행 중 재설정 409를 검증한다. ISO-009는 실제 3D backend로 전환한 HTTP 카메라 전용 세션에서 semantic 409를 검증한다.
## D006 — 평가자 dataset 명령과 기록·재생 경계

04 §5.4는 참가팀과 분리된 데이터셋 내보내기를 요구하지만 08의 CLI 목록에는 대응 명령이 없었다. `maicon-sim dataset --scenario ... --out ...`와 `--example`을 추가했다. 초기 장면의 실제 RGB/depth/segmentation, 분석 기하와 face body ID로 만든 면별 mask/bbox/가시 비율, 전체 inventory를 `private/`에만 저장한다. 파일 해시·가림·비공개 경계 시험을 추가했다. 공식 참가팀 API는 바꾸지 않았다.

오프라인 `--record-frames`는 제한된 큐에서 역압을 적용해 실제 영상 기록을 보존하고, 실시간 기록은 제한된 큐에서 drop과 오류를 계측해 코어를 막지 않는다. 프레임은 내용 해시로 중복 저장을 피한다. 코어 재생에서도 공개 관측 transcript를 기록하도록 수정했다. 5,000틱 체크포인트와 `replay --checkpoint-tick`을 연결했고, RGB 기록을 끈 3D 실행은 전체 센서 체크포인트를 생략한다. 재생·손상 로그·관측 기록·두 백엔드 동등성·중간 복원 시험으로 경계를 검증한다.

구현 커밋이 없는 초기 저장소에서도 출처를 꾸며내지 않도록 `unborn-working-tree`/`installed-distribution-no-vcs`를 명시하고 구현 패키지 파일의 해시를 별도로 기록한다. 공식 근거 커밋은 `reference_source_commit`으로 분리한다.

## D007 — VFS Docker 환경의 빌드 공간 사용

전체 인수 시험의 반복 빌드에서 63GB 작업 디스크가 고갈되었다. 관리 Docker daemon의 VFS 저장 방식은 각 COPY/RUN 단계마다 설치된 가상환경을 포함한 전체 파일 트리를 복사하므로, 여러 번의 13단계 빌드가 작은 논리 이미지 크기보다 훨씬 큰 물리 공간을 차지했다. 해당 실행은 ENOSPC로 중단된 환경 오류로 기록하고 통과로 처리하지 않았다.

이 작업에서 생성한 maicon-sim 이미지와 검사로 확인한 해당 빌드 캐시만 정리했다. Dockerfile은 의존성 설치 캐시를 분리한 채 소스·문서·예시·시험 COPY를 한 단계로 합치고, 프로젝트 설치·doctor·출력 디렉터리 준비를 한 RUN으로 합쳤다. .dockerignore는 환경값 파일을 제외한다. 저장 드라이버·daemon 설정·TLS 검증을 바꾸지 않았다. 소스와 시험 증거를 보존하고 공간을 확보한 뒤 Ubuntu 비루트·네트워크 차단 렌더/경기와 전체 시험을 다시 실행했다. 최종 전체 시험 355개 통과를 확인했으며 JUnit과 기준별 결과는 IMPLEMENTATION_STATUS.md에 연결했다.
