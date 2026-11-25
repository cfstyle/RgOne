ARG PY311_BASE_IMAGE=python:3.11-slim-bookworm

FROM node:22-bookworm-slim AS frontend-build
ARG NPM_CONFIG_REGISTRY=https://registry.npmjs.org/
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --include=dev --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM ${PY311_BASE_IMAGE} AS backend-deps
ARG PIP_INDEX_URL=https://pypi.org/simple/
USER root
WORKDIR /build
COPY backend/requirements.txt ./requirements.txt
RUN python -c "import sys; assert sys.version_info[:2] == (3, 11)" \
    && python -m pip install --no-cache-dir --target /deps -r requirements.txt

FROM busybox:1.37.0
COPY --from=backend-deps /deps/ /payload/deps/
COPY --from=frontend-build /build/dist/ /payload/frontend/
COPY backend/__init__.py /payload/backend/__init__.py
COPY backend/app/ /payload/backend/app/
COPY deploy/publish-app.sh /publish-app.sh
RUN set -o pipefail; tar -cf - -C /payload . | sha256sum | cut -d ' ' -f 1 > /payload-id
ENTRYPOINT ["/bin/sh", "/publish-app.sh"]
