#!/bin/sh
set -eu

payload_dir="${1:-/payload}"
release_dir="$(cd "${2:-/release}" && pwd -P)"
release_id="$(cat "${3:-/payload-id}")"

if [ "${#release_id}" -ne 64 ]; then
    echo "Invalid application release ID" >&2
    exit 1
fi
case "$release_id" in
    *[!0-9a-f]*) echo "Invalid application release ID" >&2; exit 1 ;;
esac

current="$release_dir/current"
version="$release_dir/$release_id"
if [ "$(readlink "$current" || true)" = "$release_id" ] && [ -d "$version" ]; then
    exit 0
fi

stage="$(mktemp -d "$release_dir/.publish.XXXXXX")"
trap 'case "$(cd "$stage" && pwd -P)" in "$release_dir"/.publish.*) rm -rf -- "$stage";; esac' EXIT
if [ ! -d "$version" ]; then
    mkdir "$stage/payload"
    cp -a "$payload_dir/." "$stage/payload/"
    chmod 755 "$stage/payload"
    mv -T "$stage/payload" "$version"
fi

ln -s "$release_id" "$stage/current"
if [ -d "$current" ] && [ ! -L "$current" ]; then
    if ! rmdir "$current"; then
        echo "Cannot replace application release directory: $current" >&2
        exit 1
    fi
fi
mv -Tf "$stage/current" "$current"
