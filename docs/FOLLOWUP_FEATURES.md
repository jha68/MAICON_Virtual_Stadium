# 관측 기반 후속 기능

2026-11-12. 기존 다섯 호환성/안정성 수정에 이어 baseline 공격·M3·M6와 영상/LLM 연결을 확장했다. 공통 코어의 채점 규칙은 유지한다. 합성 시험과 실제 장비 검증은 구분한다.

## 공격과 영상 단서

`baseline`은 지정 시설 탐색/조준, 식별된 상대 UGV 추적/조준, 단일 발사 요청, 발광 중 추적, cooldown/empty/unknown 상태를 처리한다. 캡처 시점 팬틸트와 카메라/레이저 장착 차이로 수광부를 조준한다. M5 공개 시 거점 이동을 우선한다. 센서 만료·pause·세션 변경 시 이전 공격 결정을 재사용하지 않는다.

발사 응답 누락은 자동 재시도하지 않는다. 공식 자기 상태에는 탄약이 없으므로 결과 불명 상태에서 공격을 유보한다. 전송 전에 취소한 발사 의도는 다시 준비할 수 있다. 실제 명중 API가 없으므로 시설 조사 시도와 정답 파괴 판정을 구분한다.

3D 참조 감지기는 픽셀에서 합성 시설 이미지·수광부·진영 표식·호출부호 띠·HP/탄약 LED를 찾는다. 가려진 표식은 판독을 유보한다. 차체 진영색은 고정하고 별도 HP 표시부를 파랑/초록/노랑/주황/빨강으로 표현한다. 2D semantic에는 가시 수광부의 화면 좌표만 추가하며 상대 HP/탄약 정답을 노출하지 않는다.

공식 인쇄물은 기존 assets의 `generator: import`·상대경로·SHA256·출처·split_group으로 등록할 수 있다. 현재 감지기는 합성 템플릿용이다. 실제 인쇄물용 모델/템플릿과 현장 영상에서 검증하기 전에는 실물 인식 성능을 보장하지 않는다.

## M3 시간 정합과 위치 보정

추론 전에 odom/scan 이력을 보존하고 이미지 캡처 시각의 odom·팬틸트·LiDAR를 조합한다. LiDAR 선분에 평면을 맞춰 면의 법선·구간을 추정하고 같은 면의 재방문은 구간 겹침으로 연관한다. 인접 박스/다른 면은 구분하고 오래된 역순 영상·평면 증거 부족·섹터 경계의 불확실한 귀속은 보류한다.

공개 외곽 벽이 충분히 관측될 때 작은 SE(2) 위치/yaw 오차를 보정한다. 일반 SLAM은 아니다. 새 보정 시 기존 트랙도 변환하고 오래된 occupancy grid를 초기화하여 중복·잔상을 막는다. 참가 알고리즘은 정답 pose·box ID·depth·segmentation을 사용하지 않는다.

## M6와 LLM 제공자

상대 호출부호별 HP/탄약 구간·관측 나이를 축적한다. 중복 프레임/동일 발사 장면은 중복 집계하지 않고 오래된 관측의 불확실도를 넓힌다. 상대 M3는 비공개이므로 `[0,30]`으로 둔다. 위험도 `hp/4 + ammo/8 + m3/30` 추정과 동점 가능성을 요약하여 LLM에 전달하고 경기 중 최신 순위를 준비한다.

기본 제공자는 명시적인 `fixture`이며 M6는 관측 증거의 추정 순위를 사용한다. 실제 LLM 성능으로 기록하지 않는다. 실제 제공자 실패 시 M1을 fixture로 조용히 바꾸지 않는다. M6는 오류를 기록하고 불확실한 증거 기반 순위로 보고한다.

- `json-http`: 요청 `{model, task, input}`, 응답 M1 객체 또는 `{ranking:[...]}`.
- `openai-compatible`: chat completions의 `messages`와 `response_format: json_object`; `choices[0].message.content`를 JSON/스키마/호출부호로 검증.

키 값은 안전한 환경 설정으로 공급하고 명령·저장소·로그에 넣지 않는다.

```bash
.venv/bin/maicon-sim agent --slot B-1 --policy baseline --server http://127.0.0.1:8000 \
  --llm-provider openai-compatible --llm-endpoint https://YOUR_HOST/v1/chat/completions \
  --llm-model YOUR_MODEL --llm-key-env MAICON_LLM_API_KEY --llm-timeout-s 5
```

`MAICON_SIM_MISSION_CODE`도 환경에서 공급한다. 여섯 참가팀 자동 실행은 `MAICON_LLM_PROVIDER`, `MAICON_LLM_ENDPOINT`, `MAICON_LLM_MODEL`, `MAICON_LLM_API_KEY_ENV`와 명시한 키만 전달한다. 기본 키 이름은 `MAICON_LLM_API_KEY`다. 기본 fixture에서는 부모의 LLM/GitHub/관리자 키를 물려주지 않는다. 실제 제공자 모드에는 필요한 proxy/CA 설정도 전달한다. 주최측 최종 API 형식이 다르면 LLMPort 어댑터를 추가한다. 실제 HTTP LLM 시험은 realtime/agent로 수행하고 가속 run은 동기 fixture 정책을 사용한다.

## 카메라 실측과 영상 스트레스

실제 보정판을 다른 기울기로 촬영한 이미지6장 이상, 내부 코너 수, 정사각형 한 변의 미터 단위를 입력한다.

```bash
.venv/bin/maicon-sim calibrate-camera --images '/path/to/boards/*.png' \
  --board-cols 9 --board-rows 6 --square-size-m .025 --out artifacts/measured-camera.json
.venv/bin/maicon-sim agent --slot B-1 --policy baseline --server http://127.0.0.1:8000 \
  --camera-calibration artifacts/measured-camera.json --vision-stress-seed 42
.venv/bin/maicon-sim augment-image --image /path/to/input.png \
  --seed 42 --brightness .9 --blur-sigma .5 --noise-sigma 2 --out artifacts/stress.png
```

보정 도구는 코너 검출·기울기 다양성·해상도·재투영 오차를 검증하고 intrinsics/왜곡/품질을 새 JSON에 기록한다. 기존 파일은 덮어쓰지 않는다. 정책 입력은 같은 K/해상도의 pinhole로 보정하며 정책의 K도 맞춘다. `MAICON_CAMERA_CALIBRATION`의 절대경로는 자동 참가팀에도 전달된다. 렌즈 보정은 장착 TF·시간 지연·모터 보정을 대신하지 않는다. 실제 측정 없이 실물 프로필을 생성하지 않았고160도 사양만으로 fx/왜곡을 결정하지 않는다.

`--vision-stress-seed`는 참조 감지기 입력의 밝기·블러·노이즈를 재현한다. augmentation API는 대비·화이트밸런스·렌즈 왜곡도 지원한다. 합성 보드 PNG의 코너 검출부터 K 복원까지 도구를 검증했다.

## 검증 범위

실제 PyBullet RGB → 감지 → 전체 ParticipantPolicy/dispatcher → 코어의 시설 파괴와 이동 상대 피격을 검사한다. 별도로 가림·불명 ID·지연 영상·발사 응답 누락·pause/report·세션 전환을 시험한다. M3는 재방문/면 구분/벽 보정 전후, M6는 불균등 상태/누락/동점/노화/중복을 검증한다. 제공자 요청·인증·응답·deadline은 로컬 실제 TCP 서버와 httpx로 검사한다. 실제 외부 LLM·최종 SDK·공식 인쇄물·실물 보정은 추가 입력과 현장 검증이 필요하다.
