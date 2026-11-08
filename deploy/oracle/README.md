# Oracle ARM64 CI/CD

현재 대상: Ubuntu 24.04 ARM64, 2 OCPU, RAM 약12GB. VM에는 Docker만 설치하고 GitHub Actions가 ARM64 이미지를 빌드한다. x86 runner의 QEMU 빌드라 첫 빌드는 오래 걸릴 수 있다. Docker build 안의 doctor가 ARM64 의존성과 실제 TinyRenderer를 검사한다. ARM64 API 서버의 VM 배포 성공은 사용자의 docker ps와 /sim/session 응답으로 확인했다. 웹 화면 추가 버전의 원격 배포·공개 인증서 발급은 별도로 확인한다.

최초 원격 ARM 빌드는 PyBullet 3.2.7 컴파일 중 `Python.h` 누락으로 실패했다. 수정된 Dockerfile은 `python3.10-dev`를 설치하고 의존성 설치 전에 실제 C 컴파일러로 Python 헤더를 검사한다. 수정 후 배포 시에는 실패한 이전 실행을 Re-run하는 대신 **Run workflow → main**으로 새 실행을 만든다. 이전 실행의 Re-run은 수정 전 커밋을 사용한다.

## 1. VM 최초 준비

Cloud Shell에서 SSH 접속한 **ubuntu@VM** 터미널에서 실행한다.

```bash
sudo apt-get update
sudo apt-get install -y docker.io curl python3
sudo systemctl enable --now docker
sudo usermod -aG docker ubuntu
mkdir -p ~/.ssh ~/maicon-data
chmod 700 ~/.ssh
ssh-keygen -t ed25519 -N '' -C maicon-github-actions -f ~/.ssh/maicon-actions
cat ~/.ssh/maicon-actions.pub >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
exit
```

Cloud Shell에서 VM으로 다시 SSH 접속한 뒤 `docker run --rm hello-world`를 확인한다. Docker group 적용에는 재접속이 필요하다. 배포 전용 키 생성 명령은 최초 한 번 실행하며 기존 파일을 덮어쓰지 않는다.

## 2. GitHub repository secrets

저장소 Settings → Secrets and variables → Actions → New repository secret:

| 이름 | 값 |
|---|---|
| OCI_HOST | VM 공인 IP |
| OCI_SSH_KEY | VM에서 `cat ~/.ssh/maicon-actions`로 확인한 배포 전용 개인키 전체 |
| OCI_SSH_KNOWN_HOSTS | 아래 명령의 출력 |

신뢰한 기존 SSH 연결 안에서 VM의 host public key를 읽는다. 아래 IP는 실제 VM 공인 IP로 바꾼다.

```bash
awk '{print "144.24.89.248 " $1 " " $2}' /etc/ssh/ssh_host_ecdsa_key.pub
```

개인키는 GitHub Secret에만 입력하며 채팅·저장소·로그에 붙이지 않는다. 최초 로그인에 사용한 관리 키와 배포 키를 구분한다. VM SSH 방화벽/OCI 규칙이 Actions runner의 연결도 허용해야 한다. Cloud Shell 접속 성공만으로 Actions 접속 성공이 입증되지는 않는다. SSH timeout이면 적용된 소스 제한부터 확인한다.

## 3. 실행

main push → simulator-validation 성공 → oracle-arm64-deploy → ARM64 이미지 GHCR push → digest로 pull → 새 컨테이너 상태 검사. 수동 실행은 Actions → oracle-arm64-deploy → Run workflow. Secrets 미설정 시 빌드 전에 명확히 실패한다. GitHub Actions/GHCR 사용량은 계정 요금제의 무료 한도에 따른다.

GHCR가 비공개여도 workflow의 일회성 GITHUB_TOKEN으로 VM에서 pull하고 종료 시 logout한다. 패키지에 저장소의 Actions 접근 권한이 있어야 한다. VM에 장기 PAT를 저장하지 않는다. 배포 중에는 기존 컨테이너를 정지하므로 짧은 중단이 있으며 경기 중 자동 배포는 경기를 중단한다. 실제 경기 운영 시에는 main 병합을 세팅 시간에 하거나 배포 workflow를 수동 실행하도록 운영한다.

산출물은 `~/maicon-data/runs/`에 보존한다. 웹 경기별 최종 결과는 해당 서버 run의 `private/results/`에 저장한다. 실패하면 이전 컨테이너를 복구한다. 직전 이미지와 실행 기록을 자동 삭제하지 않으므로 디스크 사용량을 관찰한다. 배포는 API readiness 검사이며 6대 주행/3D 실시간 성능 시험을 대신하지 않는다.

VM 사용자의 UID/GID는 이미지 기본값 1000과 다를 수 있다(현재 Oracle ubuntu는 1001:1001). 배포 스크립트가 `id -u`/`id -g`를 읽어 컨테이너의 `--user`에 적용한다. 기존 서버를 정지하기 전에 같은 사용자로 `/data/runs`에 임시 파일을 쓰고 지우는 검사를 한다. 배포 스크립트는 ubuntu로 실행하며 sudo로 실행하지 않는다. 데이터 폴더의 권한을 777로 넓히거나 앱을 root로 실행하지 않는다.

## 4. HTTPS 웹 화면

기본 주소: **https://maicon.junununseo.com**. Actions variable `MAICON_DOMAIN`으로 도메인을 바꿀 수 있다. A 레코드는 VM 공인 IP로 지정하고 Cloudflare는 DNS only를 사용한다. OCI subnet Security List 또는 NSG에서 소스 `0.0.0.0/0`, TCP 목적지 포트80·443을 허용한다. 기존 SSH 규칙은 유지한다. 8000/8001/8080은 공개할 필요가 없다. VM 내부 방화벽이 웹 포트를 막는 경우에도80·443만 허용해야 한다.

자동 배포가 수행하는 일:

- `/data/web.password`를 최초 한 번만 생성(0600); 이후 배포에서는 유지.
- 별도 운영자 웹 앱을 VM loopback8080에서 실행. 기존 참가팀8000·관리자8001도 loopback 유지.
- Caddy2.10.2를 `maicon-web-proxy` 컨테이너로 실행하고 HTTPS→8080 프록시. 인증서는 named volume에 보존하고 자동 갱신.
- 내부 API와 인증된 웹 상태를 검사. 공개 DNS/OCI 방화벽/ACME 성공은 브라우저 접속으로 별도 확인.

VM에서 비밀번호 확인:

```bash
cat ~/maicon-data/web.password
```

브라우저 로그인 사용자명은 `admin`이다. 비밀번호 출력은 채팅에 보내지 않는다. 관리자 API의 admin.token과는 다른 자격 증명이다. 정책을 선택한 뒤 준비 시작→여섯 팀 준비 완료→경기 시작을 누른다. 2D 지도/3D 장면 전환, 로봇 선택·실제 RGB, 일시정지·재개·종료·결과·다음 경기 초기화를 지원한다. 시작 전 준비를 취소할 때도 초기화할 수 있다.

상태 확인:

```bash
docker ps --filter name=maicon
curl --fail 'http://127.0.0.1:8000/sim/session?mission_code=SIMB0001'
docker logs --tail 60 maicon-web-proxy
getent ahostsv4 maicon.junununseo.com
```

HTTPS가 안 열리면 DNS가 실제 공인 IP를 가리키는지, OCI와 VM 방화벽80/443, Caddy 로그를 확인한다. SSH fingerprint나 GitHub Secrets는 다시 만들지 않는다.

## 5. 웹 화면 시험

`tests/integration/test_web_dashboard.py`는 운영자 인증·CSRF·참가팀 정보 경계·실제 writer 큐 조작·결과 보존·준비 취소·SIGTERM 종료를 검증한다. `scripts/check_web_ui.cjs`는 별도 로컬3D 서버(18000/18001/18080)에서 실제 Chromium·WebGL·RGB·여섯 참가 프로세스·주행·pause/resume·종료·초기화를 검사한다. CI는 고정 Playwright1.62.1을 RUNNER_TEMP에 설치하고 이 브라우저 시험까지 통과한 뒤 배포한다. 해당 스크립트의 자격 증명은 테스트 전용이며 운영 웹 비밀번호로 사용하지 않는다.
