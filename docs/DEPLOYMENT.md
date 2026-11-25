# 行内大模型自助接入与案例门户 (RgOne Portal) 部署与运行手册

## Docker 隔离内网部署

### 1. 在联网服务器打包

| 镜像 | 默认镜像引用 | 内容 |
| --- | --- | --- |
| Python | `python:3.11-slim-bookworm` | 通用 Python 3.11 运行时 |
| Nginx | `nginx:1.28-alpine` | 通用 Nginx |
| RgOne | `rgone-app:latest` | 后端源码、Python 依赖和编译好的前端 |

```bash
bash deploy/export-images.sh all   # 首次打包，一个离线包内含三个镜像
bash deploy/export-images.sh app   # 日常更新，只输出应用包
```

首次部署包在 `build/rgone-offline-amd64.tar.gz`。ARM64 使用 `bash deploy/export-images.sh all linux/arm64`，构建机须能运行目标架构的容器。构建脚本优先使用 Buildx。Buildx 不可用时，同架构可通过 Docker 的传统构建器打包，跨架构需要 Buildx。Python 和 Nginx 也可分别通过 `python`、`nginx` 参数单独导出。应用包内附 Compose、Nginx 配置、环境变量模板和部署手册。

如果构建机无法直连镜像仓库，可以先导入同架构的 Python、Nginx、`node:22-bookworm-slim` 和 `busybox:1.37.0` 镜像，再执行 `RGONE_USE_LOCAL_BASE_IMAGES=1 bash deploy/export-images.sh all`。此模式使用本地镜像和传统构建器，构建过程仍需访问 npm 和 Python 依赖源。

构建机可通过 `RGONE_PIP_INDEX_URL` 和 `RGONE_NPM_REGISTRY` 指定可访问的 Python 和 npm 镜像源。这些设置只用于当前 RgOne 镜像构建。

通过构建机环境变量 `RGONE_PYTHON_IMAGE` 和 `RGONE_NGINX_IMAGE` 可选择通用镜像，首次安装会将这些引用写入 `.env`。共享 Python 镜像须提供 Linux Python 3.11，在普通用户下可执行 `/bin/sh` 和 `python`，构建环境须支持 `pip`。

### 2. 在隔离内网首次部署

目标 Linux 服务器预装 Docker Engine 和支持 `up --wait` 的 Compose。安装脚本支持 `docker compose` 和独立的 `docker-compose`。将一个离线包传到目标服务器，在准备创建部署目录的位置执行：

```bash
tar --no-same-owner -xzf rgone-offline-amd64.tar.gz && bash rgone/install.sh
```

ARM64 使用对应文件名。离线包里的 `rgone/install.sh` 来自源码目录的 `deploy/install.sh`，只改变所在目录。首次安装时输入两次管理员密码，输入内容不会回显。密码确认后，脚本自动生成应用密钥和 JWT 密钥、导入镜像、启动 Compose 并验证首页和健康接口。重复执行会保留已有 `.env`、管理员密码、配置和数据。

如果旧版首次安装在 `app-release` 阶段出现 `mv: can't rename ... Is a directory`，将修正版 `install.sh` 放到现有部署目录并重新运行即可。脚本会备份旧的 `compose.yaml`，修正后端工作目录，并清理发布卷中的空 `current` 目录。遇到非空目录会停止并保留内容。镜像包和业务数据可继续沿用。

默认使用 `8000` 端口。安装脚本在导入镜像前检查端口，发现占用时会提示可用端口并等待确认。无人值守时可用 `RGONE_PORT=8001 sh install.sh` 显式指定端口。启动后按脚本显示的端口访问门户。

部署环境由 `.env` 中的 `APP_ENV` 控制。默认 `production` 使用真实网关和原有 `data/`。需要测试时设为 `test`，使用模拟网关，数据库和上传文件位于独立的 `data/test/`。修改后在部署目录执行 `docker compose up -d --wait`。生产环境在管理后台填写真实网关地址、服务账号令牌、用户 ID 和小秘书配置。管理员「测试网关连通性」始终发起真实探测。

SQLite、安装包和图片保存在宿主机 `data/`。迁移旧部署时，停掉旧进程，复制原数据库和整个存储目录，再授权目录。保留原 `APP_SECRET_KEY`，以便解密已有凭据。已有管理员继续使用数据库里的密码。

### 3. 已部署的环境更新应用

在现有部署目录执行。若服务器使用独立的 Compose 命令，将下方的 `docker compose` 替换为 `docker-compose`。

```bash
tar -xzf ../rgone-app-amd64.tar.gz -C incoming &&
  (cd incoming/app && sha256sum -c SHA256SUMS) &&
  docker image load -i incoming/app/image.tar &&
  docker compose stop backend &&
  docker compose up -d --force-recreate --wait app-release backend
```

应用更新会切换前端目录并重启后端，沿用现有 `.env`、`data/` 和两个通用镜像。完成后复验首页、`/health` 和已有下载文件。需要回滚时，导入上一个应用包并重复更新步骤。

若发布修改了部署配置，从新包复制对应配置文件再启动。Nginx 配置有变化时，执行 `docker compose up -d --no-deps --force-recreate --wait nginx` 重新加载。

## 一、 运行环境要求

* **操作系统**：Windows Server 2016+ / Linux (CentOS 7+, RHEL 8+, Ubuntu 20.04+)
* **Python 环境**：Python 3.9+ (本行内已适配 Python 3.9.7 `dev` Conda 环境)
* **Node.js 环境**：Node.js 18+ (用于前端本地打包，离线生产构建)
* **网络环境**：纯局域网环境（支持 100% 离线脱机运行）

---

## 二、 快速启动指南 (开发联调)

### 1. 激活 Python 环境并检查依赖
```powershell
# 激活 Conda 环境
conda activate dev

# 切换至项目根目录
cd c:\Users\chenfei\Desktop\workspace\aiprojects\RgOne

# 验证核心依赖
python -c "import fastapi, sqlalchemy, httpx, cryptography; print('环境就绪')"
```

### 2. 检查与调整配置文件 `.env`
系统在根目录下已提供预置好的 `.env` 配置，支持开箱即用：
```ini
# 应用模式与秘钥
APP_ENV=development
APP_SECRET_KEY=bW9ja19zZWNyZXRfa2V5X2Zvcl9kZXZlbG9wbWVudF8zMndpdGhfMDA=
JWT_SECRET=super_secret_jwt_key_for_rgone_portal_2026

# 初始化管理员凭证
INIT_ADMIN_USERNAME=admin
INIT_ADMIN_PASSWORD=Admin@RgOne2026

# new-api 聚合网关对接 (生产真实联调时设为 false，并配置 ACCESS_TOKEN)
NEW_API_BASE_URL=http://30.20.4.144:3001
NEW_API_ACCESS_TOKEN=
NEW_API_USER_ID=1
MOCK_NEW_API=true

# 小秘书推送接口配置 (行内即时通信)
XIAOMISHU_API=http://30.20.x.x/api/send_message
XIAOMISHU_SEND_USER=
XIAOMISHU_SOURCE=金融市场部RPA
# 生产模式下默认为 false（验证码严格直投给工号名下 touser=emp_no）
# 仅在联调演练与测试环境中设为 true，此时路由至 XIAOMISHU_SEND_USER
XIAOMISHU_TEST_MODE=false
```

### 3. 运行自动化测试与工程检查
在完全隔离的临时数据库环境与 Mock 服务下执行全套质量门禁（绝不写入现有 `data/app.db`）：
```powershell
# 1. 激活环境
conda activate dev

# 2. 运行后端全量测试套件 (覆盖 Phase 1 与 Phase 2 全量 16 项用例)
python -m pytest backend/tests -v

# 3. 运行前端类型检查、ESLint 代码规范与生产打包
Push-Location frontend
npm run check
npm run build
Pop-Location
```

### 4. 启动后端 API 服务 (多 Worker 支持与互斥保障)
SQLite 已开启 `PRAGMA journal_mode=WAL`，支持多进程并发读写与共享验证码/状态存储。全行日志增量拉取内置基于 DB 的 120 秒超时单例互斥锁，多 Worker 部署下依然安全互斥：
```powershell
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --workers 4
```
服务启动后，可在浏览器访问：
* API 交互文档 (Swagger)：`http://127.0.0.1:8000/docs`
* 健康检查：`http://127.0.0.1:8000/health`

---

## 三、 生产部署方案 (Nginx 反向代理模式)

在生产环境中，推荐使用 Nginx 托管前端构建产物 `frontend/dist`，并将 `/api/` 转发给 Uvicorn 服务进程。

### 1. Nginx 配置文件示例 (`/etc/nginx/conf.d/rgone_portal.conf`)
```nginx
server {
    listen 80;
    server_name rgone-ai.bank.local;

    # 客户端上传安装包大小限制 (允许 1GB)
    client_max_body_size 1024M;

    # 前端静态单页应用
    location / {
        root /opt/rgone/frontend/dist;
        index index.html;
        try_files $uri $uri/ /index.html;
    }

    # 后端 API 接口反向代理
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # 支持流式响应与长连接
        proxy_buffering off;
        proxy_read_timeout 300s;
    }

    # 静态上传资源托管
    location /api/v1/static/ {
        proxy_pass http://127.0.0.1:8000/api/v1/static/;
        proxy_buffering on;
        proxy_cache_valid 200 30d;
    }
}
```

### 2. 后端服务守护进程 (Linux systemd 示例)
创建文件 `/etc/systemd/system/rgone.service`：
```ini
[Unit]
Description=RgOne AI Onboarding Portal FastAPI Service
After=network.target

[Service]
Type=simple
User=appuser
WorkingDirectory=/opt/rgone
ExecStart=/opt/miniforge3/envs/dev/bin/uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --workers 4
Restart=always
RestartSec=5
EnvironmentFile=/opt/rgone/.env

[Install]
WantedBy=multi-user.target
```
启动并自启：
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now rgone
```
