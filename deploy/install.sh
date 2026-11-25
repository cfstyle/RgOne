#!/usr/bin/env bash
if [ -z "${BASH_VERSION:-}" ]; then
    exec bash "$0" "$@"
fi
set -euo pipefail

app_archive="${2:-}"
if (( $# > 2 )) || { (( $# > 0 )) && [[ "$1" != app ]]; }; then
    echo "Usage: sh install.sh [app [rgone-app-ARCH.tar.gz]]" >&2
    exit 2
fi
if [[ -n "$app_archive" && "$app_archive" != /* ]]; then
    app_archive="$PWD/$app_archive"
fi

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
cd -P -- .

docker info --format '{{.ServerVersion}}' >/dev/null
compose=(docker compose)
if ! "${compose[@]}" version >/dev/null 2>&1; then
    compose=(docker-compose)
    "${compose[@]}" version >/dev/null
fi

start_and_check() {
    local started_at
    started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    if ! "${compose[@]}" up -d --wait "$@"; then
        "${compose[@]}" ps -a >&2 || true
        "${compose[@]}" logs --no-color --since "$started_at" --tail 80 app-release >&2 || true
        return 1
    fi
    "${compose[@]}" exec -T backend python -c '
from urllib.request import build_opener, ProxyHandler

opener = build_opener(ProxyHandler({}))
for path in ("/", "/health"):
    with opener.open("http://nginx" + path, timeout=5) as response:
        if response.status != 200:
            raise RuntimeError(f"{path}: HTTP {response.status}")
'
}

if [[ "${1:-}" == app ]]; then
    if [[ ! -f .env || ! -f compose.yaml || ! -f nginx.conf || ! -d data ]]; then
        echo "An existing RgOne deployment is required. Run sh install.sh with the full offline bundle first." >&2
        exit 1
    fi
    if [[ -z "$app_archive" ]]; then
        architecture="$(docker info --format '{{.Architecture}}')"
        case "$architecture" in
            x86_64|amd64) architecture=amd64 ;;
            aarch64|arm64) architecture=arm64 ;;
            *)
                printf 'Unsupported Docker architecture: %s\n' "$architecture" >&2
                exit 1
                ;;
        esac
        app_archive="../rgone-app-$architecture.tar.gz"
    fi
    if [[ ! -f "$app_archive" ]]; then
        printf 'Application update package not found: %s\n' "$app_archive" >&2
        exit 1
    fi
    "${compose[@]}" config --quiet
    stage="$(mktemp -d "$PWD/.rgone-app.XXXXXX")"
    trap 'if [[ "${stage%/*}" == "$PWD" && "${stage##*/}" == .rgone-app.* ]]; then rm -rf -- "$stage"; fi' EXIT
    tar --no-same-owner -xzf "$app_archive" -C "$stage" app
    (cd -- "$stage/app" && sha256sum -c SHA256SUMS)
    docker image load -i "$stage/app/image.tar"
    "${compose[@]}" stop backend
    start_and_check --force-recreate app-release backend
    echo "RgOne application updated. Published address:"
    "${compose[@]}" port nginx 80
    exit 0
fi

for component in python nginx app; do
    (cd -- "incoming/$component" && sha256sum -c SHA256SUMS)
done

env_source=incoming/app/.env.docker.example
[[ ! -f .env ]] || env_source=.env
configured_port="$(awk '
    /^[[:space:]]*(export[[:space:]]+)?RGONE_PORT[[:space:]]*=/ {
        port = $0
        sub(/^[^=]*=[[:space:]]*/, "", port)
        sub(/[[:space:]]+#.*/, "", port)
        sub(/[[:space:]]+$/, "", port)
        gsub(/^["\047]|["\047]$/, "", port)
    }
    END {print port}
' "$env_source")"
configured_port="${configured_port:-8000}"
port="${RGONE_PORT:-$configured_port}"
if [[ ! "$port" =~ ^[1-9][0-9]{0,4}$ ]] || (( port > 65535 )); then
    echo "RGONE_PORT must be a TCP port from 1 to 65535." >&2
    exit 1
fi

if command -v ss >/dev/null 2>&1; then
    listeners="$(ss -H -ltn)"
elif command -v netstat >/dev/null 2>&1; then
    listeners="$(netstat -ltn)"
else
    echo "Cannot check host ports. Install ss (iproute2) or netstat and run install.sh again." >&2
    exit 1
fi
published_ports="$(docker ps --format '{{.Ports}}')"
own_port=
if [[ -f compose.yaml && -f .env ]]; then
    running_nginx="$("${compose[@]}" ps --status running --quiet nginx 2>/dev/null || true)"
    if [[ -n "$running_nginx" ]]; then
        own_port="$("${compose[@]}" port nginx 80 2>/dev/null || true)"
    fi
fi
port_in_use() {
    grep -Eq ":${1}([[:space:]]|$)" <<< "$listeners" ||
        grep -Fq ":${1}->" <<< "$published_ports"
}
if ! grep -Eq ":${port}$" <<< "$own_port" && port_in_use "$port"; then
    candidate="$port"
    while (( ++candidate <= 65535 )) && port_in_use "$candidate"; do
        :
    done
    if (( candidate > 65535 )); then
        echo "Port $port is in use. Set RGONE_PORT to an available port and run install.sh again." >&2
        exit 1
    fi
    if [[ ! -t 0 ]]; then
        printf 'Port %s is in use. Confirm an available port by running RGONE_PORT=%s sh install.sh.\n' \
            "$port" "$candidate" >&2
        exit 1
    fi
    printf 'Port %s is in use. Install RgOne on port %s instead? [y/N] ' "$port" "$candidate"
    read -r confirmation
    if [[ "$confirmation" != [yY] && "$confirmation" != [yY][eE][sS] ]]; then
        echo "Installation cancelled."
        exit 1
    fi
    port="$candidate"
fi
printf 'RgOne host port: %s\n' "$port"

if [[ ! -e .env ]]; then
    set +x
    printf 'Set the initial administrator password: ' >&2
    if ! IFS= read -rs admin_password; then
        printf '\nInstallation cancelled before setting the administrator password.\n' >&2
        exit 1
    fi
    printf '\nConfirm the administrator password: ' >&2
    if ! IFS= read -rs admin_password_confirmation; then
        printf '\nInstallation cancelled before confirming the administrator password.\n' >&2
        exit 1
    fi
    printf '\n' >&2
    if [[ "$admin_password" != "$admin_password_confirmation" ]]; then
        echo "Administrator passwords do not match." >&2
        exit 1
    fi
    if [[ -z "$admin_password" || "$admin_password" == *$'\r'* ]] ||
        (( $(printf '%s' "$admin_password" | wc -c) > 72 )); then
        echo "The administrator password must be 1 to 72 bytes and contain no carriage return." >&2
        exit 1
    fi
    encoded_admin_password="$(printf '%s' "$admin_password" | sed -e 's/[\\"]/\\&/g' -e 's/[$]/&&/g')"
    unset admin_password admin_password_confirmation
fi

for component in python nginx app; do
    docker image load -i "incoming/$component/image.tar"
done

for config in compose.yaml nginx.conf; do
    if [[ ! -e "$config" ]]; then
        cp -- "incoming/app/$config" "$config"
    fi
done

if grep -Fxq '    working_dir: /srv/rgone/current' compose.yaml; then
    changes=(-e 's|^    working_dir: /srv/rgone/current$|    working_dir: /|')
    if ! grep -Fxq '        cd /srv/rgone/current' compose.yaml; then
        if ! grep -q '^        export PYTHONPATH=' compose.yaml; then
            echo "Cannot update the backend working directory in the customized compose.yaml." >&2
            exit 1
        fi
        changes+=(-e '/^        export PYTHONPATH=/i\        cd /srv/rgone/current')
    fi
    if [[ ! -e compose.yaml.before-release-fix ]]; then
        cp -p -- compose.yaml compose.yaml.before-release-fix
    fi
    sed -i "${changes[@]}" compose.yaml
    echo "Updated the backend working directory in compose.yaml."
fi

if [[ ! -e .env ]]; then
    temp_env="$(mktemp .env.XXXXXX)"
    trap 'rm -f -- "$temp_env"' EXIT
    while IFS= read -r line || [[ -n "$line" ]]; do
        case "$line" in
            APP_SECRET_KEY=|JWT_SECRET=)
                value="$(od -An -v -N32 -tx1 /dev/urandom | tr -d '[:space:]')"
                printf '%s%s\n' "$line" "$value"
                ;;
            INIT_ADMIN_PASSWORD=)
                printf 'INIT_ADMIN_PASSWORD="%s"\n' "$encoded_admin_password"
                ;;
            *) printf '%s\n' "$line" ;;
        esac
    done < incoming/app/.env.docker.example > "$temp_env"
    ln -- "$temp_env" .env
    rm -f -- "$temp_env"
    trap - EXIT
    unset encoded_admin_password INIT_ADMIN_PASSWORD
fi

if [[ "$port" != "$configured_port" ]]; then
    temp_env="$(mktemp .env.XXXXXX)"
    trap 'rm -f -- "$temp_env"' EXIT
    awk -v port="$port" '
        /^[[:space:]]*(export[[:space:]]+)?RGONE_PORT[[:space:]]*=/ {
            if (!written++) print "RGONE_PORT=" port
            next
        }
        {print}
        END {if (!written) print "RGONE_PORT=" port}
    ' .env > "$temp_env"
    mv -f -- "$temp_env" .env
    trap - EXIT
fi
export RGONE_PORT="$port"

"${compose[@]}" config --quiet
mkdir -p -- data
docker run --rm --pull=never --network none --user 0 \
    --mount "type=bind,src=$PWD/data,dst=/data" --entrypoint /bin/sh rgone-app:latest -ec '
        entries="$(ls -A /data)"
        if [ -z "$entries" ]; then
            chown 10001:10001 /data
        fi
    '
"${compose[@]}" run --rm --no-deps -T --entrypoint /bin/sh app-release -ec '
    current=/release/current
    if [ -d "$current" ] && [ ! -L "$current" ]; then
        if ! rmdir "$current"; then
            echo "Cannot publish over a nonempty release directory: $current" >&2
            exit 1
        fi
    fi
'
start_and_check

echo "RgOne installed. Published address:"
"${compose[@]}" port nginx 80
echo "Initial administrator settings are in .env (INIT_ADMIN_USERNAME and INIT_ADMIN_PASSWORD)."
