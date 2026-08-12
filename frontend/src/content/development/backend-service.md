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
| GET | `/v1/observatory/{filename}` | 观测站产物只读下载（白名单：status.json、forecasts.csv、latest-forecast.png、evaluation-history.png、dashboard.md、latest-paths.csv） |

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
| `MODEL_NAME` | `isnet-general-use` | rembg 模型名 |
| `MAX_REQUEST_BYTES` | `11534336` | 请求总体上限，默认 11 MiB |
| `MAX_FILE_BYTES` | `10485760` | 图片文件上限，默认 10 MiB |
| `MAX_PIXELS` | `40000000` | 解码后最大像素总数 |
| `MAX_UPLOAD_CONCURRENCY` | `4` | 同时接收上传的数量 |
| `MAX_INFERENCE_CONCURRENCY` | `2` | 同时执行 ONNX 推理的数量 |
| `ALLOWED_ORIGINS` | 空列表 | 逗号分隔的 CORS 白名单 |
| `OBSERVATORY_DIR` | `/data/observatory` | 观测站账本/图表输出目录（生产挂持久卷到 `/data`） |
| `OBSERVATORY_SCHEDULE` | `08:00` | 每日预测运行时刻（Asia/Shanghai，开盘前） |
| `OBSERVATORY_ENABLED` | `1` | 设 `0` 可整体停用观测站调度 |
| `KRONOS_DIR` | `/app/vendor/kronos` | vendored Kronos 模型代码位置 |
| `OBSERVATORY_SCRIPT` | `/app/observatory/csi1000_live_forecast.py` | 预测脚本位置（与 Skill 同源） |

## 模型生命周期

`isnet-general-use`（rembg）与 Kronos/HF 权重都是运行期首次调用时惰性下载，缓存到 `/data/models` / `/data/hf`（持久卷）——不在构建阶段下载：构建环境的出网与生产容器不是一回事，实测构建期连 GitHub（rembg 模型源）和 hf-mirror.com 都可能超时。下载一次后常驻 `/data`，之后重启/重新部署直接读缓存，不再重复联网。

应用启动时预热模型 session。预热失败不会杀死进程：`/livez` 仍然可用，而 `/readyz` 返回实际模型状态。推理由 `asyncio.to_thread` 放到线程执行，并由 semaphore 限制并发。

## 观测站（中证1000 Kronos 每日预测）

- 调度：`app/observatory.py` 在 lifespan 中启动每日定时任务（默认 08:00 Asia/Shanghai，开盘前）；
  启动时若从未生成过账本会先补跑一次。周末/节假日照常触发无害：脚本只认最新完整交易日，幂等空跑。
- 执行：预测跑在**子进程**里（脚本与 `skills/csi1000-kronos-forecast` 同一份，构建时复制到
  `/app/observatory/`），torch 与权重只在运行的几分钟内占内存，跑完随进程退出全部释放。
- 权重：`NeoQuasar/Kronos-Tokenizer-base` 与 `NeoQuasar/Kronos-base` 在 Docker 构建期下载进
  `HF_HOME`，运行期 `HF_HUB_OFFLINE=1` 离线复用；行情数据由 akshare 运行期在线抓取（国内源）。
- 持久化：账本 `forecasts.csv` 是追加式的，必须把持久卷挂到 `/data`（Zeabur Volume），
  否则重新部署后历史准确率从零累计。
- 模型代码：`backend/vendor/kronos/`（MIT，上游 shiyu-coder/Kronos，仅收录推理所需 `model/` 包）。

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
