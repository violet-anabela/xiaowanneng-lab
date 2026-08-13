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
| `WAREHOUSE_DIR` | `/data/warehouse` | 个人数据仓库 SQLite 文件目录（生产挂持久卷到 `/data`） |
| `WAREHOUSE_SCRIPT` | `/app/warehouse/stock_daily_sync.py` | 同步脚本位置 |
| `WAREHOUSE_BATCH_SIZE` | `300` | 每批处理的股票数 |
| `WAREHOUSE_POLL_INTERVAL` | `15` | 存量历史没追平前，两批之间等待的秒数 |
| `WAREHOUSE_SCHEDULE` | `16:30` | 追平之后，每天增量更新的时刻（Asia/Shanghai，收盘后） |
| `WAREHOUSE_ENABLED` | `1` | 设 `0` 可整体停用数据仓库同步 |

## 模型生命周期

`isnet-general-use`（rembg）与 Kronos/HF 权重都是运行期首次调用时惰性下载，缓存到 `/data/models` / `/data/hf`（持久卷）——不在构建阶段下载：构建环境的出网与生产容器不是一回事，实测构建期连 GitHub（rembg 模型源）和 hf-mirror.com 都可能超时。下载一次后常驻 `/data`，之后重启/重新部署直接读缓存，不再重复联网。

应用启动时在后台任务里预热模型 session（`asyncio.to_thread`），不阻塞启动——首次下载权重可能要几分钟，放前台会连 `/livez` 和观测站调度一起卡住。预热期间 `/readyz` 与 `/v1/remove-background` 各自兜底：session 还没好就现场同步加载一次（等于把下载耗时转嫁到那次请求上），之后复用。推理本身仍由 `asyncio.to_thread` 放线程执行，并由 semaphore 限制并发。

## 观测站（中证1000 Kronos 每日预测）

- 调度：`app/observatory.py` 在 lifespan 中启动每日定时任务（默认 08:00 Asia/Shanghai，开盘前）；
  启动时若从未生成过账本会先补跑一次。周末/节假日照常触发无害：脚本只认最新完整交易日，幂等空跑。
- 执行：预测跑在**子进程**里（脚本与 `skills/csi1000-kronos-forecast` 同一份，构建时复制到
  `/app/observatory/`），torch 与权重只在运行的几分钟内占内存，跑完随进程退出全部释放。
- 权重：`NeoQuasar/Kronos-Tokenizer-base` 与 `NeoQuasar/Kronos-base` 运行期首次调用时惰性下载
  （见上方"模型生命周期"），常驻 `HF_HOME`；行情数据由 akshare 运行期在线抓取（国内源）。
- 持久化：账本 `forecasts.csv` 是追加式的，必须把持久卷挂到 `/data`（Zeabur Volume），
  否则重新部署后历史准确率从零累计。
- 模型代码：`backend/vendor/kronos/`（MIT，上游 shiyu-coder/Kronos，仅收录推理所需 `model/` 包）。

## 个人数据仓库（全市场 A 股日线）

- 这是 violet 自己攒着玩的数据仓库，**不对外暴露任何接口**——现在只是把数据存下来，
  查询接口以后再单独做。跟观测站/抠图共用同一个 backend 服务是权衡后的选择（省一份基础设施），
  代价是三者共享同一个容器/资源，任何一方出问题理论上都可能连累另外两个。
- 数据源：`baostock`（免费、无需 token），只存不复权原始成交价（`adjustflag=3`）——
  复权是分析时的派生选择，不是历史事实本身。
- 范围：只到股票（baostock `type=1`），暂不含指数/ETF/可转债/基金净值/宏观数据，
  以后要加再扩展。
- 存储：SQLite，`WAREHOUSE_DIR/warehouse.db`（生产挂持久卷到 `/data`），三张表
  `stocks`（股票名单，含已退市）/ `daily_bars`（日线）/ `sync_state`（每只股票同步进度）。
- 调度：`app/warehouse.py` 按批调用 `backend/warehouse/stock_daily_sync.py`（子进程，
  一批处理 `WAREHOUSE_BATCH_SIZE` 只股票）；股票名单几千只，一次全量回填要跑很久，
  按批跑、进度记在 `sync_state` 表里，容器重启也不丢进度。存量历史没追平前每
  `WAREHOUSE_POLL_INTERVAL` 秒跑一批；追平之后（某一批"nothing to sync"）退化成
  每天 `WAREHOUSE_SCHEDULE`（默认收盘后）跑一次增量更新。

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
