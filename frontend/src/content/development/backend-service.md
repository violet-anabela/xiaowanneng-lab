---
title: Backend 服务
description: FastAPI 推理服务的接口、限制、环境变量和模型生命周期
service: backend
order: 2
---

# Backend 服务

Backend 是网站的**推理适配层**：接收 HTTP 上传、执行安全校验和并发控制，然后调用 `remove_background_skill` 的同源核心代码。协议逻辑不进入 Skill 核心。

## 当前技术与端口

| 项目 | 当前实现 |
|---|---|
| Python | Python 3.12 slim 镜像 |
| API | FastAPI + Uvicorn |
| 推理 | rembg 2.x + ONNX Runtime CPU |
| 依赖管理 | uv + `backend/uv.lock` |
| 容器端口 | `8000` |
| 本机调试映射 | `18000:8000` |
| Dockerfile | `backend/Dockerfile` |

## 当前接口

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/livez` | 进程存活检查，不要求模型已经就绪 |
| GET | `/readyz` | 模型就绪检查；必要时再次尝试加载模型 |
| POST | `/v1/remove-background` | 接收图片并返回透明 PNG |

通过 gateway 访问业务接口时，外部路径是 `/api/v1/remove-background`；gateway 会剥掉 `/api` 前缀后再交给 Backend。

## 上传和安全限制

当前实现有两层大小限制：

1. `RequestSizeLimitMiddleware` 在 multipart 解析前按实际收到的请求体累计字节；
2. `process_upload` 再对图片文件自身做分块计数、真实格式解码和像素检查。

只接受真实格式为 JPEG、PNG、WEBP 的图片。成功响应为 `image/png`，并带有 `Cache-Control: no-store`。

## 环境变量

所有运行配置由 `backend/app/settings.py` 读取：

| 变量 | 默认值 | 含义 |
|---|---:|---|
| `PORT` | `8000` | Uvicorn 监听端口 |
| `MODEL_NAME` | `u2net` | rembg 模型名 |
| `MAX_REQUEST_BYTES` | `11534336` | 请求总体上限，默认 11 MiB |
| `MAX_FILE_BYTES` | `10485760` | 图片文件上限，默认 10 MiB |
| `MAX_PIXELS` | `40000000` | 解码后最大像素总数 |
| `MAX_UPLOAD_CONCURRENCY` | `4` | 同时接收上传的数量 |
| `MAX_INFERENCE_CONCURRENCY` | `2` | 同时执行 ONNX 推理的数量 |
| `ALLOWED_ORIGINS` | 空列表 | 逗号分隔的 CORS 白名单 |

## 模型生命周期

`backend/Dockerfile` 在构建阶段下载 `u2net` 到 `/repo/models`，运行镜像将其复制到 `/app/models`，因此正式运行不依赖临时联网下载模型。

应用启动时预热模型 session。预热失败不会杀死进程：`/livez` 仍然可用，而 `/readyz` 返回实际模型状态。推理由 `asyncio.to_thread` 放到线程执行，并由 semaphore 限制并发。

## 本地运行

推荐完整联调：

```bash
docker compose up --build
curl http://localhost:18000/livez
curl http://localhost:18000/readyz
```

直接运行源码时，需要让 Python 找到共享 Skill：

```bash
cd backend
PYTHONPATH=../skills/remove-background \
  uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## 修改入口

- 路由与模型生命周期：`backend/app/main.py`
- 环境变量：`backend/app/settings.py`
- 请求体硬限制：`backend/app/middleware.py`
- 图片校验与响应：`backend/app/adapters/remove_background_api.py`
- 共享核心：`skills/remove-background/remove_background_skill/`

新增接口或环境变量时必须同步更新本页；构建前的一致性检查会核对当前 FastAPI 路由、Settings 环境变量和 Compose 端口。
