#!/usr/bin/env bash
# Runs as the VM's ubuntu user, after docker login and Docker group setup.
set -euo pipefail
image=${1:?Supply an immutable ghcr.io image@sha256:digest}
[[ "$image" =~ ^ghcr\.io/[a-z0-9_./-]+@sha256:[a-f0-9]{64}$ ]] || { echo 'Expected immutable GHCR digest' >&2; exit 2; }
data_dir="${MAICON_DATA_DIR:-$HOME/maicon-data}"
health_attempts=${MAICON_HEALTH_ATTEMPTS:-90}
health_interval=${MAICON_HEALTH_INTERVAL:-2}
mkdir -p "$data_dir/runs"
exec 9>"$data_dir/deploy.lock"
flock -n 9 || { echo 'Another deployment is in progress' >&2; exit 3; }
docker pull "$image"
old=false
if docker container inspect maicon-sim >/dev/null 2>&1; then
    docker rm -f maicon-sim-previous >/dev/null 2>&1 || true
    docker stop --time 45 maicon-sim >/dev/null
    if ! docker rename maicon-sim maicon-sim-previous; then
        docker start maicon-sim >/dev/null
        exit 1
    fi
    old=true
fi
rollback() {
    trap - ERR
    docker logs --tail 60 maicon-sim >&2 || true
    docker rm -f maicon-sim >/dev/null 2>&1 || true
    if "$old"; then
        docker rename maicon-sim-previous maicon-sim
        docker start maicon-sim >/dev/null
        echo 'Previous container restored; deployment failed.' >&2
    fi
}
trap 'rollback; exit 1' ERR
run_id="$(date -u +%Y%m%dT%H%M%S)-${image##*:}-$$"
# Both APIs bind loopback. No public admin port or unauthenticated web UI.
docker run -d --name maicon-sim --restart unless-stopped --network host \
    --mount "type=bind,src=$data_dir,dst=/data" \
    "$image" serve --example smoke_six --backend 3d \
    --public-port 8000 --admin-port 8001 --out "/data/runs/$run_id" >/dev/null
for ((attempt=0; attempt<health_attempts; attempt++)); do
    if [[ "$(docker inspect --format '{{.State.Running}}' maicon-sim)" == true ]] && curl --fail --silent --max-time 3 \
        'http://127.0.0.1:8000/sim/session?mission_code=SIMB0001' \
        | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["capabilities"]["rgb"] and d["slot"]=="B-1"' 2>/dev/null; then
        trap - ERR
        printf '%s\n' "$image" > "$data_dir/deployed-image.txt"
        echo 'Deployment healthy. APIs: VM loopback 8000/8001. Web viewer is a separate step.'
        exit 0
    fi
    sleep "$health_interval"
done
false # ERR trap restores the previous container.
