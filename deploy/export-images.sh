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

local_images="${RGONE_USE_LOCAL_BASE_IMAGES:-0}"
use_buildx=true
if [[ "$mode" == app || "$mode" == all ]] &&
    { [[ "$local_images" == 1 ]] || ! docker buildx version >/dev/null 2>&1; }; then
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
    if [[ "$local_images" == 1 ]]; then
        printf 'Using local base images on the Docker legacy builder for %s.\n' "$native_platform" >&2
    else
        printf 'Buildx unavailable. Using the Docker legacy builder for %s.\n' "$native_platform" >&2
    fi
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
build_args=(--build-arg "PY311_BASE_IMAGE=$python_image")
if [[ -n "${RGONE_PIP_INDEX_URL:-}" ]]; then
    build_args+=(--build-arg "PIP_INDEX_URL=$RGONE_PIP_INDEX_URL")
fi
if [[ -n "${RGONE_NPM_REGISTRY:-}" ]]; then
    build_args+=(--build-arg "NPM_CONFIG_REGISTRY=$RGONE_NPM_REGISTRY")
fi

prepare_image() {
    local image="$1" image_platform
    if [[ "$local_images" != 1 ]]; then
        docker pull --platform "$platform" "$image"
        return
    fi
    if ! image_platform="$(docker image inspect --format '{{.Os}}/{{.Architecture}}' "$image" 2>/dev/null)"; then
        printf 'Required local base image is missing: %s. Load it for %s and rerun.\n' "$image" "$platform" >&2
        return 1
    fi
    if [[ "$image_platform" != "$platform" ]]; then
        printf 'Local base image %s has platform %s, expected %s.\n' "$image" "$image_platform" "$platform" >&2
        return 1
    fi
}

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
            prepare_image "$image"
            ;;
        nginx)
            image="$nginx_image"
            prepare_image "$image"
            ;;
        app)
            image="$app_image"
            if [[ "$local_images" == 1 ]]; then
                prepare_image "$python_image"
                prepare_image node:22-bookworm-slim
                prepare_image busybox:1.37.0
            fi
            if "$use_buildx"; then
                docker buildx build --platform "$platform" --load \
                    "${build_args[@]}" --tag "$image" .
            else
                DOCKER_BUILDKIT=0 DOCKER_DEFAULT_PLATFORM= docker build \
                    "${build_args[@]}" --tag "$image" .
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
