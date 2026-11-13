#!/usr/bin/env bash
# Runs as the VM's ubuntu user, after docker login and Docker group setup.
set -euo pipefail
image=${1:?Supply an immutable ghcr.io image@sha256:digest}
web_domain=${2:-}
if [[ -n "$web_domain" && ! "$web_domain" =~ ^[a-zA-Z0-9][a-zA-Z0-9.-]*\.[a-zA-Z]{2,}$ ]]; then
    echo 'Expected a DNS hostname for HTTPS' >&2
    exit 2
fi
[[ "$image" =~ ^ghcr\.io/[a-z0-9_./-]+@sha256:[a-f0-9]{64}$ ]] || { echo 'Expected immutable GHCR digest' >&2; exit 2; }
data_dir="${MAICON_DATA_DIR:-$HOME/maicon-data}"
health_attempts=${MAICON_HEALTH_ATTEMPTS:-90}
health_interval=${MAICON_HEALTH_INTERVAL:-2}
mkdir -p "$data_dir/runs"
exec 9>"$data_dir/deploy.lock"
flock -n 9 || { echo 'Another deployment is in progress' >&2; exit 3; }
docker pull "$image"
runtime_uid=$(id -u)
runtime_gid=$(id -g)
if [[ "$runtime_uid" == 0 ]]; then
    echo 'Run deployment as the non-root VM user, without sudo.' >&2
    exit 2
fi
# Bind mounts preserve numeric ownership; Ubuntu's UID may differ from image UID 1000.
# Verify writes before stopping a healthy existing match server.
docker run --rm --network none --user "$runtime_uid:$runtime_gid" \
    --mount "type=bind,src=$data_dir,dst=/data" --entrypoint /app/.venv/bin/python "$image" \
    -c 'import maicon_sim.config.loader; import pathlib,tempfile; d=tempfile.TemporaryDirectory(dir="/data/runs"); pathlib.Path(d.name,"probe").write_text("ok"); d.cleanup()'
web_args=()
if [[ -n "$web_domain" ]]; then
    docker run --rm --network none --user "$runtime_uid:$runtime_gid" \
        --mount "type=bind,src=$data_dir,dst=/data" --entrypoint /app/.venv/bin/python "$image" \
        -c 'import os,secrets,pathlib; p=pathlib.Path("/data/web.password"); f=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600) if not p.exists() else None; f is not None and os.write(f,(secrets.token_urlsafe(32)+"\n").encode()); f is not None and os.close(f); assert len(p.read_text().strip())>=24; p.chmod(0o600)'
    mkdir -p "$data_dir/proxy"
    printf '%s {\n  reverse_proxy 127.0.0.1:8080\n}\n' "$web_domain" > "$data_dir/proxy/Caddyfile.next"
    docker pull caddy:2.10.2
    docker run --rm --network none --mount "type=bind,src=$data_dir/proxy,dst=/etc/caddy,readonly" \
        --entrypoint caddy caddy:2.10.2 validate --config /etc/caddy/Caddyfile.next --adapter caddyfile
    mv "$data_dir/proxy/Caddyfile.next" "$data_dir/proxy/Caddyfile"
    web_args=(--web-port 8080)
fi
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
    --user "$runtime_uid:$runtime_gid" \
    --env MAICON_WEB_PASSWORD_FILE=/data/web.password \
    --mount "type=bind,src=$data_dir,dst=/data" \
    "$image" serve --example reference_stadium --backend 3d \
    --public-port 8000 --admin-port 8001 --out "/data/runs/$run_id" "${web_args[@]}" >/dev/null
for ((attempt=0; attempt<health_attempts; attempt++)); do
    if [[ "$(docker inspect --format '{{.State.Running}}' maicon-sim)" == true ]] && curl --fail --silent --max-time 3 \
        'http://127.0.0.1:8000/sim/session?mission_code=SIMB0001' \
        | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["capabilities"]["rgb"] and d["slot"]=="B-1"' 2>/dev/null; then
        if [[ -n "$web_domain" ]]; then
            if ! docker exec maicon-sim /app/.venv/bin/python -c 'import urllib.request,base64,pathlib; p=pathlib.Path("/data/web.password").read_text().strip(); r=urllib.request.Request("http://127.0.0.1:8080/api/state",headers={"Authorization":"Basic "+base64.b64encode(("admin:"+p).encode()).decode()}); assert urllib.request.urlopen(r,timeout=5).status==200'; then
                sleep "$health_interval"
                continue
            fi
            if docker container inspect maicon-web-proxy >/dev/null 2>&1; then
                docker start maicon-web-proxy >/dev/null
                docker exec maicon-web-proxy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile
            else
                docker run -d --name maicon-web-proxy --restart unless-stopped --network host \
                    --mount "type=bind,src=$data_dir/proxy,dst=/etc/caddy,readonly" \
                    --mount type=volume,src=maicon-caddy-data,dst=/data \
                    --mount type=volume,src=maicon-caddy-config,dst=/config caddy:2.10.2 >/dev/null
            fi
            echo "Operator URL: https://$web_domain (TLS issuance requires DNS and inbound TCP 80/443)."
            echo 'Username: admin. Read the password only on the VM: cat ~/maicon-data/web.password'
        fi
        trap - ERR
        printf '%s\n' "$image" > "$data_dir/deployed-image.txt"
        echo 'Deployment healthy. APIs remain on VM loopback 8000/8001.'
        exit 0
    fi
    sleep "$health_interval"
done
false # ERR trap restores the previous container.
