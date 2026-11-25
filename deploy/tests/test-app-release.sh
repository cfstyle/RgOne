#!/usr/bin/env bash
set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.."
publisher="$PWD/deploy/publish-app.sh"
tmp_dir="$(cd -- "${TMPDIR:-/tmp}" && pwd -P)"
fixture="$(mktemp -d "$tmp_dir/rgone-release-test.XXXXXX")"
trap 'case "$(cd "$fixture" && pwd -P)" in "$tmp_dir"/rgone-release-test.*) rm -rf -- "$fixture";; esac' EXIT
cd -- "$fixture"

mkdir -p payload/frontend release/current
printf 'example page\n' > payload/frontend/index.html
printf -v first '%064d' 1
printf -v second '%064d' 2
printf '%s\n' "$first" > id

printf 'preserve this file\n' > release/current/unexpected
if sh "$publisher" payload release id; then
    echo "Publisher replaced a nonempty current directory" >&2
    exit 1
fi
grep -Fxq 'preserve this file' release/current/unexpected
rm -- release/current/unexpected

sh "$publisher" payload release id
test "$(readlink release/current)" = "$first"
grep -Fxq 'example page' release/current/frontend/index.html

printf 'updated page\n' > payload/frontend/index.html
printf '%s\n' "$second" > id
sh "$publisher" payload release id
test "$(readlink release/current)" = "$second"
grep -Fxq 'updated page' release/current/frontend/index.html
echo "Application release tests passed"
