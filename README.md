# xiaowanneng-lab

小完能实验室 —— 个人文档 + 小工具 + 可下载 Agent Skill 的静态站点。

## 这个仓库是什么

一个**内容型工具箱站点**：

- **文档**：用 Markdown 写，存 Git，跟着镜像一起重生（容器重启不丢）。
- **小工具**：纯前端的工具（JSON 格式化、Base64 等）零成本跑在浏览器里；需算力的工具（如抠图）走后端服务。
- **Skills 画廊**：把兼容 Agent Skills 规范的 Skill 打包成 zip，访客可下载后交给支持该规范的 Agent 使用。

架构宪法（详见 `proposals/`，不进 git）：

- **三个独立 Service，同一仓库**：`frontend`（Astro 静态站）、`backend`（FastAPI 推理）、`gateway`（反向代理网关）。结构参考 `quant-strategy-lab`。
- **Skill 包 = 唯一真源**：网站后端 `import` 它，下载 zip 也打包它，改一处处处生效。
- **无状态优先**：需要长期保留的数据（模型权重、配置）随镜像构建或挂持久卷，不依赖容器本地盘。
- **每个服务一个目录、自带 `Dockerfile`**：`backend/Dockerfile`、`frontend/Dockerfile`、`gateway/Dockerfile`。

## 目录结构

```
frontend/                 前端 Astro 静态站（纯静态，由网关反代访问）
  src/pages/              首页 / docs / development / tools / skills
  src/content/docs/       个人文章、笔记与内容
  src/content/development/ frontend/backend/gateway 项目开发文档
  src/data/tools.ts       工具清单（新增纯前端工具只改这里）
  public/skills/          构建期生成的 Skill zip（可下载）
  src/data/skills-manifest.json  从 skills/manifest.json 覆盖而来
  nginx.conf              前端容器内纯静态托管配置（不含反代）
  Dockerfile              Zeabur 用 `ZBPACK_DOCKERFILE_PATH=frontend/Dockerfile` 指定
backend/                  后端 FastAPI（只服务需算力的工具）
  app/main.py             /livez /readyz /v1/remove-background
  app/middleware.py       ASGI 请求级大小限制（防上传 DoS）
  app/adapters/           纯适配层，调用 Skill 核心
  pyproject.toml/uv.lock  后端 + 核心依赖（python，uv 管理）
  Dockerfile              Zeabur 用 `ZBPACK_DOCKERFILE_PATH=backend/Dockerfile` 指定
gateway/                  网关（反向代理）服务
  nginx.conf.template     配置模板（envsubst 注入 PORT/BACKEND_URL/FRONTEND_URL）
  nginx.local.conf        备用本地调试配置（当前 compose 不使用）
  start.sh                启动时 envsubst 注入变量后拉起 nginx
  Dockerfile              Zeabur 用 `ZBPACK_DOCKERFILE_PATH=gateway/Dockerfile` 指定
skills/                   可下载 Skill（唯一真源）
  remove-background/      ← 核心包 remove_background_skill/ + CLI + SKILL.md
  manifest.json           版本清单（下载页与打包脚本共读）
scripts/package_skills.py 生成版本化 Skill zip（仅标准库）
docker-compose.yml        本地三服务编排（非 Zeabur 部署方式）
```

## 本地开发

### 前端

```bash
cd frontend
npm install
npm run dev          # 本地预览，默认 http://localhost:4321
npm run build        # 输出 dist/
```

抠图页通过 `import.meta.env.PUBLIC_API_BASE_URL` 找后端；本地未设置时默认相对路径 `/api`，需经下方网关访问（或在直接运行 Backend 源码时用 `PUBLIC_API_BASE_URL=http://localhost:8000 npm run dev` 直连）。

`npm run build` 会先执行开发文档契约检查，核对三个服务的端口、Backend 路由与环境变量、Gateway 路由和变量。代码变了但文档没更新时，构建会列出缺失内容。

### 后端

```bash
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r <(uv export --frozen --no-dev)   # 或 pip install fastapi uvicorn python-multipart pillow rembg onnxruntime
# 需把 Skill 核心包加入路径
PYTHONPATH=$(pwd)/../skills/remove-background uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
# 健康检查
curl http://127.0.0.1:8000/livez
curl http://127.0.0.1:8000/readyz
```

> 后端 `import remove_background_skill`，故需把 `skills/remove-background` 加入 `PYTHONPATH`（如上）。

### 一键本地编排（推荐）

```bash
docker compose up --build
# 访问 http://localhost:18080 （网关）-> 前端静态站 + /api 反代到后端
```

> 后端在构建期下载 u2net 模型（需网络，约百 MB）；无网络时后端镜像构建会失败。
>
> 本地调试端口：gateway `18080`、backend `18000`、frontend `18081`。容器内部仍使用 `80/8000`，Zeabur 配置不受影响。

### 打包 Skill（生成下载用 zip）

```bash
python scripts/package_skills.py        # 输出到 frontend/public/skills/
```

## 部署（Zeabur）

GitHub 推送 `main` 自动部署。仓库根需有 `backend/Dockerfile`、`frontend/Dockerfile`、`gateway/Dockerfile`。

### 建三个 Service

在 Zeabur Project 里 **Add Service** 三次，都选**同一个 GitHub 仓库**，并在高级设置里把 **Dockerfile 路径**分别设为：

| 项 | 网关 Service | 前端 Service | 后端 Service |
|---|---|---|---|
| 服务名 | `gateway` | `frontend` | `backend` |
| Dockerfile 路径 | `gateway/Dockerfile` | `frontend/Dockerfile` | `backend/Dockerfile` |
| Root Directory | **不设**（构建根=仓库根，否则读不到 `skills/`） | **不设** | **不设** |
| 端口 | `80`（网关，读 `PORT`） | `80`（nginx 纯静态，内部） | `8000`（uvicorn，读 `PORT`） |

> 若 Zeabur 框架自动检测误判（仓库根有 `pyproject.toml`/`package.json`），在高级设置显式锁定 Dockerfile 路径即可。

### 域名与变量

**网关由独立的 `gateway` 服务充当**（配置见 `gateway/nginx.conf.template`）：它把 `/api/*` 反代到 `backend`、把 `/` 反代到 `frontend`。**因此你不需要在 Zeabur 配任何路径路由 / Path 规则**，只要做三件事：

1. **域名只绑 `gateway` 服务**（浏览器全程只跟本站同源通信，`frontend`/`backend` 不必绑公网子域）。
2. 在 **`gateway` 服务**设两个环境变量，指向 `backend` / `frontend` 的**内部地址**（Zeabur 服务设置里可见，通常形如 `http://<service>.zeabur.internal:<port>`，具体前缀随项目而定）：
   - `BACKEND_URL` = `http://backend.zeabur.internal:8000`（或 backend 服务的实际内部地址）
   - `FRONTEND_URL` = `http://frontend.zeabur.internal:80`（或 frontend 服务的实际内部地址）
   - 网关会把 `本站域名/api/v1/remove-background` 转成 `BACKEND_URL/v1/remove-background` 发给后端。
3. `backend` 服务可选设 `MAX_REQUEST_BYTES` / `MAX_FILE_BYTES` / `MAX_PIXELS` / `MAX_UPLOAD_CONCURRENCY` / `MAX_INFERENCE_CONCURRENCY` / `ALLOWED_ORIGINS` / `MODEL_NAME`（见 `backend/app/settings.py`）。

前端默认走相对路径 `/api`（无需任何构建变量）；只有当你想强制指定后端时才设 `PUBLIC_API_BASE_URL` 覆盖。因为走网关同源反代，**无需 CORS**。

### 模型权重

`backend/Dockerfile` 在**构建期**下载并固定 `u2net` 模型到镜像（`U2NET_HOME`），运行时不临时联网。换模型改 `ARG MODEL_NAME`。

## 加新工具

- **纯前端工具**：写一个 Astro 组件 + 在 `frontend/src/data/tools.ts` 加一行，完事。
- **需后端工具**：新增 `backend/app/adapters/xxx.py` + 在 `main.py` 加一个显式路由（YAGNI：v1 不引通用执行器）。

## 安全要点（公开站点）

- 两层上传大小限制：ASGI 中间件在 multipart 解析前按原始请求体累计字节（~11MiB）；路由内再按实际图片文件（10MiB）+ 真实像素校验。
- 不信任扩展名 / Content-Type，解码后校验真实格式与尺寸。
- 忙时返 429 / 503；错误信息不暴露 Python 堆栈；日志不含图片内容。
- 抠图响应带 `Cache-Control: no-store`，避免私有图片被缓存。
