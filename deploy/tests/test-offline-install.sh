#!/usr/bin/env bash
set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.."
tmp_dir="$(cd -- "${TMPDIR:-/tmp}" && pwd -P)"
fixture="$(mktemp -d "$tmp_dir/rgone-install-test.XXXXXX")"
trap 'case "$(cd "$fixture" && pwd -P)" in "$tmp_dir"/rgone-install-test.*) rm -rf -- "$fixture";; esac' EXIT
mkdir -- "$fixture/deploy" "$fixture/docs" "$fixture/bin"
cp -- deploy/{export-images.sh,install.sh,nginx.conf} "$fixture/deploy/"
cp -- compose.yaml .env.docker.example "$fixture/"
cp -- docs/DEPLOYMENT.md "$fixture/docs/"
cd -- "$fixture"

cat > bin/docker <<'DOCKER'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "$DOCKER_TEST_LOG"
case "$1 $2" in
    'buildx version') test "${DOCKER_TEST_BUILDX:-1}" = 1 ;;
    'info --format')
        if [[ "$3" == '{{.OSType}}/{{.Architecture}}' ]]; then
            echo linux/x86_64
        fi
        ;;
    'build --build-arg') test "${DOCKER_BUILDKIT:-}" = 0 ;;
    'image save') printf 'simulated image %s\n' "$5" > "$4" ;;
    'image load') test -s "$4" ;;
    'compose port') echo "0.0.0.0:${RGONE_PORT:-8000}" ;;
    'ps --format')
        if [[ "${DOCKER_TEST_PORT_CONFLICT:-0}" == 1 ]]; then
            echo '0.0.0.0:8001->80/tcp'
        fi
        ;;
    'compose ps')
        if [[ "$3" == --status && "${DOCKER_TEST_OWN_NGINX:-0}" == 1 ]]; then
            echo rgone-nginx-fixture
        fi
        ;;
    'compose version') test "${DOCKER_TEST_COMPOSE_PLUGIN:-1}" = 1 ;;
    'compose run')
        [[ "$*" == *'app-release -ec '* ]]
        command="${!#}"
        command="${command//\/release\/current/$DOCKER_TEST_RELEASE/current}"
        sh -ec "$command"
        ;;
    'compose up') test "${DOCKER_TEST_FAIL_UP:-0}" = 0 ;;
    'pull --platform'|'buildx build'|'run --rm'|'compose config'|'compose exec'|'compose logs') ;;
    *) exit 1 ;;
esac
DOCKER
cat > bin/docker-compose <<'COMPOSE'
#!/usr/bin/env bash
DOCKER_TEST_COMPOSE_PLUGIN=1 exec docker compose "$@"
COMPOSE
cat > bin/ss <<'SS'
#!/usr/bin/env bash
if [[ "${DOCKER_TEST_PORT_CONFLICT:-0}" == 1 ]]; then
    echo 'LISTEN 0 128 0.0.0.0:8000 0.0.0.0:*'
fi
SS
chmod +x bin/docker bin/docker-compose bin/ss
export PATH="$fixture/bin:$PATH"
export DOCKER_TEST_LOG="$fixture/docker.log"
export DOCKER_TEST_RELEASE="$fixture/release-volume"
mkdir -- "$DOCKER_TEST_RELEASE"
export RGONE_PYTHON_IMAGE=registry.test/shared/python:3.11
export RGONE_NGINX_IMAGE=registry.test/shared/nginx:stable

bash deploy/export-images.sh all linux/arm64
grep -Fq 'buildx build --platform linux/arm64 --load' docker.log
test "$(find build -maxdepth 1 -name 'rgone-*.tar.gz' | wc -l)" -eq 1
tar --no-same-owner -xzf build/rgone-offline-arm64.tar.gz
cmp deploy/install.sh rgone/install.sh
if DOCKER_TEST_PORT_CONFLICT=1 bash rgone/install.sh </dev/null > preflight.log 2>&1; then
    echo "Installer continued without confirming an alternative port" >&2
    exit 1
fi
grep -Fq 'RGONE_PORT=8002 sh install.sh' preflight.log
test ! -e rgone/.env
if grep -q '^image load ' docker.log; then
    echo "Installer imported images before port confirmation" >&2
    exit 1
fi
if printf '%s\n' 'one fixture password' 'different fixture password' | bash rgone/install.sh > mismatch.log 2>&1; then
    echo "Installer accepted different confirmation" >&2
    exit 1
fi
grep -Fq 'Administrator passwords do not match.' mismatch.log
test ! -e rgone/.env
if grep -q '^image load ' docker.log; then
    echo "Installer imported images before password confirmation" >&2
    exit 1
fi
if printf '\n\n' | bash rgone/install.sh > empty.log 2>&1; then
    echo "Installer accepted an empty password" >&2
    exit 1
fi
test ! -e rgone/.env

fixture_password='test ${FIXTURE_VAR} "quoted" \path'
printf '%s\n' "$fixture_password" "$fixture_password" |
    DOCKER_TEST_COMPOSE_PLUGIN=0 bash rgone/install.sh > install.log 2>&1
grep -Fq 'Set the initial administrator password:' install.log
grep -Fq 'Confirm the administrator password:' install.log
if grep -Fq "$fixture_password" install.log; then
    echo "Installer printed the password" >&2
    exit 1
fi
grep -Fxq 'INIT_ADMIN_PASSWORD="test $${FIXTURE_VAR} \"quoted\" \\path"' rgone/.env
test "$(grep -c '^image load ' docker.log)" -eq 3
grep -Fxq 'compose up -d --wait' docker.log
grep -Fq 'compose exec -T backend python -c' docker.log
grep -Fxq "RGONE_PYTHON_IMAGE=$RGONE_PYTHON_IMAGE" rgone/.env
grep -Fxq "RGONE_NGINX_IMAGE=$RGONE_NGINX_IMAGE" rgone/.env
for key in APP_SECRET_KEY JWT_SECRET; do
    grep -Eq "^${key}=[0-9a-f]{64}$" rgone/.env
done

env_checksum="$(sha256sum rgone/.env)"
printf '# local configuration\n' >> rgone/nginx.conf
printf 'existing data\n' > rgone/data/sentinel
printf '# local compose settings\n' >> rgone/compose.yaml
sed -i -e 's|^    working_dir: /$|    working_dir: /srv/rgone/current|' \
    -e '/^        cd \/srv\/rgone\/current$/d' rgone/compose.yaml
legacy_compose_checksum="$(sha256sum < rgone/compose.yaml)"
mkdir -- "$DOCKER_TEST_RELEASE/current"
sh rgone/install.sh
test ! -e "$DOCKER_TEST_RELEASE/current"
test "$legacy_compose_checksum" = "$(sha256sum < rgone/compose.yaml.before-release-fix)"
grep -Fxq '    working_dir: /' rgone/compose.yaml
test "$(grep -Fxc '        cd /srv/rgone/current' rgone/compose.yaml)" -eq 1
grep -Fxq '# local compose settings' rgone/compose.yaml
bash rgone/install.sh </dev/null
test "$(grep -Fxc '        cd /srv/rgone/current' rgone/compose.yaml)" -eq 1
test "$env_checksum" = "$(sha256sum rgone/.env)"
grep -Fxq '# local configuration' rgone/nginx.conf
grep -Fxq 'existing data' rgone/data/sentinel

starts="$(grep -c '^compose up ' docker.log)"
mkdir -- "$DOCKER_TEST_RELEASE/current"
printf 'existing release data\n' > "$DOCKER_TEST_RELEASE/current/sentinel"
if bash rgone/install.sh; then
    echo "Installer accepted a nonempty current directory" >&2
    exit 1
fi
test "$starts" -eq "$(grep -c '^compose up ' docker.log)"
grep -Fxq 'existing release data' "$DOCKER_TEST_RELEASE/current/sentinel"
rm -- "$DOCKER_TEST_RELEASE/current/sentinel"
rmdir -- "$DOCKER_TEST_RELEASE/current"

if DOCKER_TEST_FAIL_UP=1 bash rgone/install.sh; then
    echo "Installer ignored a startup failure" >&2
    exit 1
fi
grep -Eq '^compose logs --no-color --since .+ --tail 80 app-release$' docker.log

DOCKER_TEST_PORT_CONFLICT=1 DOCKER_TEST_OWN_NGINX=1 RGONE_PORT=8000 bash rgone/install.sh </dev/null
DOCKER_TEST_PORT_CONFLICT=1 RGONE_PORT=8002 sh rgone/install.sh </dev/null
grep -Fxq 'RGONE_PORT=8002' rgone/.env
grep -Fxq 'existing data' rgone/data/sentinel

loads="$(grep -c '^image load ' docker.log)"
printf 'damaged image\n' > rgone/incoming/app/image.tar
if bash rgone/install.sh; then
    echo "Installer accepted an invalid checksum" >&2
    exit 1
fi
test "$loads" -eq "$(grep -c '^image load ' docker.log)"

DOCKER_TEST_BUILDX=0 sh deploy/export-images.sh app
grep -Fxq "build --build-arg PY311_BASE_IMAGE=$RGONE_PYTHON_IMAGE --tag rgone-app:latest ." docker.log
tar -tzf build/rgone-app-amd64.tar.gz | grep -Fxq app/image.tar
pulls="$(grep -c '^pull ' docker.log)"
if DOCKER_TEST_BUILDX=0 bash deploy/export-images.sh all linux/arm64; then
    echo "Legacy builder accepted an unsupported cross-platform build" >&2
    exit 1
fi
test "$pulls" -eq "$(grep -c '^pull ' docker.log)"
echo "Offline installation tests passed"
