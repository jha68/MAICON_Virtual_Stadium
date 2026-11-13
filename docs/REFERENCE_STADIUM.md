# 2026 기준 경기장

`reference_stadium`은 사용자가 첨부한 평면 배치도와 `prestudy(1)_2026MAICON.pdf`를 반영한 경기장입니다. 기존 `smoke_six`와 `perception_gallery`는 회귀 시험용으로 유지하고, Oracle 웹 배포의 기본 예제를 새 경기장으로 변경했습니다.

```bash
.venv/bin/maicon-sim validate --example reference_stadium
MAICON_WEB_PASSWORD_FILE=/path/to/web.password .venv/bin/maicon-sim serve \
  --example reference_stadium --backend 3d --web-port 8080 --out artifacts/reference-stadium
```

비밀번호 파일과 접속 방법은 [웹 대시보드](WEB_DASHBOARD.md)를 따릅니다. `--backend 2d`에서도 동일한 배치·충돌·레이저 판정이 적용됩니다. RGB 카메라는 3D 백엔드에서 제공됩니다.

## 배치와 이동 공간

- 경기장 6.12 × 5.00m, 외벽 높이 0.40m, 바닥 격자 0.20m.
- 왼쪽 BLUE 1·2·3, 오른쪽 RED 4·5·6, 중앙 공통 구역 7. 진영별 지휘소·정비소·군수보급소 3개.
- 좌우 각각 ㄱ자 3개 / 가로 2개 / ㄴ자 3개의 박스 구성, 중앙에 세로 2개씩 두 묶음. 총 20개이며 모두 0.40m 정육면체입니다.
- 도면상 연결된 박스들은 물리 엔진에서 겹침 없이 표현하도록 1cm 시공 간격을 둡니다. 이 간격은 통행로가 아닙니다. 묶음 간 이동 경로는 40cm 폭을 확보하며, 반경 20cm를 적용한 격자 탐색으로 모든 출발점·거점·이동 가능한 구역의 연결을 검사합니다.
- 시설의 위치·방향은 BLUE/RED 대칭입니다. 통신시설은 위쪽, 레이더시설은 중간, 감시초소는 아래쪽 박스의 중앙 통로를 향한 면에 배치합니다.
- 출발점은 각 거점 안에서 외벽으로부터 30cm 지점입니다. 벽의 LiDAR 관측을 격자로 변환하고 안전 여유를 적용한 뒤에도 여섯 로봇 모두 출발 경로를 찾을 수 있도록 확인했습니다.

좌표는 `examples/arena_stadium.yaml`, 객체는 `examples/scenario_reference_stadium.yaml`에서 조정합니다. 사진에 치수가 없는 세부 위치와 출발점은 이 그림을 미터 좌표로 옮긴 `SIM-REFERENCE-LAYOUT` 가정입니다.

## 이미지와 비인식 장애물

PDF에 명시된 방식대로 박스의 수직 측면에 이미지를 붙입니다. 한 면에 한 객체만 배치하며, 붙어 있는 박스 안쪽 면에는 인식 대상을 넣지 않습니다.

| 분류 | 구성 | PDF |
| --- | --- | --- |
| 지정 표적 | 감시초소, 레이더시설, 통신시설 | 12쪽 |
| 전장 객체 | 탄약상자, 드럼통, 박격포, 군용트럭, 전차, 미사일 | 13쪽 |
| 비인식 장애물 | 도시 나무, 차단벽, 야전진지, 파괴건물 | 25쪽 |

화면의 ‘위험물’은 `drum`, ‘군용차량’은 `military_truck`에 대응합니다. 비인식 장애물은 기존 `kind: decoy`를 사용하므로 충돌·시야 가림·레이저 차폐에는 참여하지만 M3 객체 수량이나 시설 표적에 포함되지 않습니다. 나무는 양측 상단, 차단벽/야전진지는 중단, 파괴건물은 양측 하단의 박스에 배치했습니다.

`assets_prestudy.yaml`은 `prestudy/*.png`의 SHA-256을 검증합니다. `prestudy/provenance.json`에는 원본 PDF 해시, 페이지, 추출 이미지와 각 패널의 잘라낸 좌표가 있습니다. 원본 PDF는 저장소에 포함하지 않았으며, 흰 여백·캡션을 제외한 참고 그림을 그대로 사용했습니다. 사용자 제공 자료의 권리는 원 권리자에게 남고 `LicenseRef-UserProvided-MAICON-Prestudy`로 표시합니다. 기존 합성 자료의 CC0 표기를 이 이미지에 적용하지 않습니다.

이 그림은 사전학습 자료의 참고 이미지입니다. 사진 기반 인식 모델을 학습하거나 검증한 것은 아니며, 동봉 `SyntheticTemplateDetector`의 합성 도형 성능 검증은 기존 `perception_gallery`에서 수행합니다.

## 수광부와 LED

시설 3종 × 2개 진영, 총 6개의 수광부를 구현했습니다. `sensor_profile_stadium.yaml`의 공통 기하 설정을 브라우저 3D와 PyBullet 및 실제 레이저 교차 판정이 함께 사용합니다.

- 원형 수광부 반경 2cm, 중심 높이 32cm, 박스 면에서 2.1cm 돌출. 참고 그림의 흰 원 위치에 맞춘 SIM 치수이며 PDF의 실측 규격은 아닙니다.
- 수광부 외곽 하우징, 광학부, 박스 상단 LED와 장착대가 별도 3D 형상으로 표시됩니다.
- 운영자 지도에서는 레이저가 실제 수광부에 도달하는 동안 황색으로 표시합니다. 참가팀 RGB에는 이 중간 상태를 노출하지 않으며, 2초 연속 감지 완료 시 상단 LED만 적색으로 바뀝니다. 감지 중단 시 누적 시간이 초기화됩니다. 다른 박스에 가려진 레이저는 수광되지 않습니다.
- 유효 타격은 기존 `destroyed`/M2 채점에 반영되며 중복 타격은 집계하지 않습니다. 초기화 시 LED도 대기로 돌아갑니다.
- 시설 파괴는 PyBullet RGB에 반영됩니다. 운영 화면은 시설별 상태를 표시하고, 참가팀은 RGB의 적색 LED로 파괴를 관측합니다. 운영자 상태·이미지 API는 인증 뒤에 있으며 참가팀 서버에 노출되지 않습니다.

## 검증

`tests/unit/test_reference_stadium.py`는 배치·패키지 자료 동일성·40cm 통행·비인식 객체 제외와 시설 6개 각각의 실제 레이저 판정을 검사합니다. `tests/render/test_stadium_rendering.py`는 수광부의 렌더 좌표/반경과 판정 기하의 일치, LED 상태의 RGB 변화 및 초기화를 검사합니다. `tests/integration/test_web_dashboard.py`는 기존/신규 경기장 모두에서 운영자 인증과 이미지 API를 검사합니다.
