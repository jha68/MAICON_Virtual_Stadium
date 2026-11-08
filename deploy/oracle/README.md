# Oracle ARM64 CI/CD

현재 대상: Ubuntu 24.04 ARM64, 2 OCPU, RAM 약12GB. VM에는 Docker만 설치하고 GitHub Actions가 ARM64 이미지를 빌드한다. x86 runner의 QEMU 빌드라 첫 빌드는 오래 걸릴 수 있다. Docker build 안의 doctor가 ARM64 의존성과 실제 TinyRenderer를 검사한다. 아직 원격 ARM 빌드·Oracle 배포는 실행하지 않았다.

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

산출물은 `~/maicon-data/runs/`에 보존한다. 실패하면 이전 컨테이너를 복구한다. 직전 이미지와 실행 기록을 자동 삭제하지 않으므로 디스크 사용량을 관찰한다. 배포는 API readiness 검사이며 6대 주행/3D 실시간 성능 시험을 대신하지 않는다.

## 4. 접속 범위와 웹 화면

이 단계는 기존 3D API 서버를 배포한다. **브라우저 viewer는 아직 구현되지 않았다.** Docker host network를 사용하지만 API 자체가 VM loopback 8000/8001에만 bind한다. 관리자 포트를 공인 IP에 공개하지 않는다. 외부에서 사용하려면 후속 웹 viewer와 인증/HTTPS reverse proxy를 연결한다. 서버 설치만으로 공인 IP에 경기 화면이 생기지는 않는다.

VM 상태 확인:

```bash
docker ps
docker logs --tail 50 maicon-sim
curl --fail 'http://127.0.0.1:8000/sim/session?mission_code=SIMB0001'
```
