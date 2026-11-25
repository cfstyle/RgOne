# 行内大模型自助接入与案例门户 (RgOne Portal)

[![Python](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109%2B-009688.svg)](https://fastapi.tiangolo.com/)
[![Vue](https://img.shields.io/badge/Vue-3.5%2B-4FC08D.svg)](https://vuejs.org/)
[![Material 3](https://img.shields.io/badge/Design-Material%203-6750A4.svg)](https://m3.material.io/)
[![Offline](https://img.shields.io/badge/Deployment-100%25%20Offline-success.svg)](#)

本系统专为银行纯内网环境下员工高效、安全接入自建 `DeepSeek Harness` 客户端与 `new-api` 聚合网关而设计。具备**工号免密双向核验**、**纯 API 下细颗粒度增量用量分析**、**一键客户端参数复制与配置补丁**及**100% 离线脱机**四大核心特性。

---

## 目录结构

```text
RgOne/
├── backend/                  # 后端源码目录 (FastAPI + SQLAlchemy 2.0)
│   ├── app/
│   │   ├── api/              # RESTful API 路由 (v1/auth, me, guide, admin)
│   │   ├── core/             # 配置中心、安全加密 (Fernet+bcrypt+JWT)、数据库引擎 (SQLite WAL)
│   │   ├── models/           # 数据库实体表 (employees, user_tokens, usage_logs_cache 等)
│   │   ├── schemas/          # Pydantic 校验与响应模型
│   │   ├── services/         # 核心业务服务 (new_api_client 适配层、auth_service、init_db)
│   │   └── main.py           # FastAPI 入口与静态文件挂载
│   ├── tests/                # 自动化测试套件 (Phase 1 全流程覆盖验证)
│   └── requirements.txt      # 后端依赖清单
├── frontend/                 # 前端源码目录 (基于 my-vue3-m3-starter，100% 离线化)
│   ├── src/                  # Vue 3 + Material 3 组件库与页面
│   ├── index.html            # 已移除外网 CDN 与在线字体，完全基于本地中文字体栈
│   └── package.json
├── data/                     # 数据与文件持久化目录
│   ├── app.db                # SQLite 数据库文件 (自动生成)
│   └── storage/
│       ├── downloads/        # 客户端安装包与共享资料托管 (支持大文件流式传输)
│       └── images/           # 案例文章插图
├── docs/                     # 完整工程落地文档
│   ├── ARCHITECTURE.md       # 系统架构设计、数据库模型与接口规范
│   ├── DEPLOYMENT.md         # 内网环境部署、服务配置与 Nginx 示例
│   └── USER_GUIDE.md          # 员工快速上手手册与管理员操作指南
├── .env.example              # 环境变量模板
└── README.md
```

---

## 快速开始

隔离内网首次部署时，联网构建机运行 `bash deploy/export-images.sh all`，得到包含三个镜像的 `build/rgone-offline-amd64.tar.gz`。将包传入内网后运行 `tar --no-same-owner -xzf rgone-offline-amd64.tar.gz && bash rgone/install.sh`。日常代码更新只打 `app` 包。详见[离线部署手册](docs/DEPLOYMENT.md#docker-隔离内网部署)。

### 1. 激活环境并启动后端
```powershell
# 激活本机的 dev 环境 (Python 3.9.7)
conda activate dev

# 运行 Phase 1 自动化测试 (包含加解密、防暴破锁定、工号双向核验、网关适配测试)
python -m pytest backend/tests/test_phase1.py -v

# 启动服务
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 2. 访问服务
* **API 文档 (Swagger UI)**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
* **默认超级管理员**: 用户名 `admin`，密码 `Admin@RgOne2026`
* **预置示范员工**: 
  - 工号 `06700956`（姓名 `陈飞`，部门 `金融科技部 · 核心架构组`）
  - 工号 `06701099`（姓名 `李晓华`，部门 `网络金融部 · 产品运营组`）

---

## 详细文档链接
* [架构与数据模型规范文档](file:///docs/ARCHITECTURE.md)
* [生产与离线部署手册](file:///docs/DEPLOYMENT.md)
* [员工与管理员使用指南](file:///docs/USER_GUIDE.md)
