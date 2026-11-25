#!/usr/bin/env bash
if [ -z "${BASH_VERSION:-}" ]; then
    exec bash "$0" "$@"
fi
set -euo pipefail

usage() {
    echo "Usage: bash deploy/export-images.sh [app|all|python|nginx] [linux/amd64|linux/arm64]"
}

mode="${1:-app}"
case "$mode" in
    -h|--help) usage; exit 0 ;;
    all) components=(python nginx app) ;;
    app|python|nginx) components=("$mode") ;;
    *) usage >&2; exit 2 ;;
esac
platform="${2:-linux/amd64}"
case "$platform" in
    linux/amd64|linux/arm64) ;;
    *) usage >&2; exit 2 ;;
esac
if (( $# > 2 )); then
    usage >&2
    exit 2
fi

use_buildx=true
if [[ "$mode" == app || "$mode" == all ]] && ! docker buildx version >/dev/null 2>&1; then
    use_buildx=false
    native_platform="$(docker info --format '{{.OSType}}/{{.Architecture}}')"
    case "$native_platform" in
        linux/x86_64) native_platform=linux/amd64 ;;
        linux/aarch64) native_platform=linux/arm64 ;;
    esac
    if [[ "$native_platform" != "$platform" ]]; then
        printf 'Buildx is required to build %s on a %s Docker engine.\n' "$platform" "$native_platform" >&2
        exit 1
    fi
    printf 'Buildx unavailable. Using the Docker legacy builder for %s.\n' "$native_platform" >&2
fi

cd -- "$(dirname "${BASH_SOURCE[0]}")/.."
cd -P -- .
build_dir="$PWD/build"
mkdir -p -- "$build_dir"
if [[ "$(cd -- "$build_dir" && pwd -P)" != "$build_dir" ]]; then
    echo "The build directory must be inside the project." >&2
    exit 1
fi
stage="$(mktemp -d "$build_dir/.rgone-export.XXXXXX")"
cleanup() {
    if [[ "$stage" == "$build_dir"/.rgone-export.* && "$(cd -- "$stage" && pwd -P)" == "$stage" ]]; then
        rm -rf -- "$stage"
    fi
}
trap cleanup EXIT

arch="${platform#linux/}"
python_image="${RGONE_PYTHON_IMAGE:-python:3.11-slim-bookworm}"
nginx_image="${RGONE_NGINX_IMAGE:-nginx:1.28-alpine}"
app_image=rgone-app:latest

payload_dir="$stage"
archive_root="$mode"
filename="rgone-$mode-$arch.tar.gz"
if [[ "$mode" == all ]]; then
    archive_root=rgone
    filename="rgone-offline-$arch.tar.gz"
    payload_dir="$stage/$archive_root/incoming"
    mkdir -p -- "$payload_dir"
    cp -- deploy/install.sh "$stage/$archive_root/"
fi

for component in "${components[@]}"; do
    payload="$payload_dir/$component"
    mkdir -- "$payload"
    package_files=(image.tar)
    case "$component" in
        python)
            image="$python_image"
            docker pull --platform "$platform" "$image"
            ;;
        nginx)
            image="$nginx_image"
            docker pull --platform "$platform" "$image"
            ;;
        app)
            image="$app_image"
            if "$use_buildx"; then
                docker buildx build --platform "$platform" --load \
                    --build-arg "PY311_BASE_IMAGE=$python_image" --tag "$image" .
            else
                DOCKER_BUILDKIT=0 DOCKER_DEFAULT_PLATFORM= docker build \
                    --build-arg "PY311_BASE_IMAGE=$python_image" --tag "$image" .
            fi
            cp -- compose.yaml .env.docker.example deploy/nginx.conf docs/DEPLOYMENT.md "$payload/"
            printf '\nRGONE_PYTHON_IMAGE=%s\nRGONE_NGINX_IMAGE=%s\n' "$python_image" "$nginx_image" \
                >> "$payload/.env.docker.example"
            package_files+=(compose.yaml .env.docker.example nginx.conf DEPLOYMENT.md)
            ;;
    esac
    docker image save --output "$payload/image.tar" "$image"
    (cd -- "$payload" && sha256sum -- "${package_files[@]}" > SHA256SUMS)
done

tar -czf "$stage/$filename" -C "$stage" "$archive_root"
mv -f -- "$stage/$filename" "$build_dir/$filename"
echo "Created build/$filename"
