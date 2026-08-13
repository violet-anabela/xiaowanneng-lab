import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .adapters.remove_background_api import process_upload
from .middleware import RequestSizeLimitMiddleware
from .observatory import router as observatory_router, scheduler_loop
from .settings import settings
from . import warehouse


def _load_session():
    from rembg import new_session

    return new_session(settings.model_name)


async def _warm_session(app: FastAPI) -> None:
    try:
        app.state.session = await asyncio.to_thread(_load_session)
    except Exception as e:  # noqa: BLE001
        app.state.session = None
        print(f"[warn] model session not loaded at startup: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 模型首次运行时惰性下载（见 backend/Dockerfile），权重不小、下载可能要几分钟；
    # 放后台任务预热，不卡启动——否则整个服务（含 /livez 和观测站调度）都会被这一次
    # 下载堵住。/readyz 和 /v1/remove-background 已经各自兜底：session 还没好会各自重试。
    app.state.session = None
    warm_task = asyncio.create_task(_warm_session(app))
    app.state.infer_sem = asyncio.Semaphore(settings.max_inference_concurrency)
    app.state.upload_sem = asyncio.Semaphore(settings.max_upload_concurrency)
    # 观测站每日预测调度（子进程执行，失败只记日志，不影响 API 服务）。
    observatory_task = None
    if settings.observatory_enabled:
        observatory_task = asyncio.create_task(scheduler_loop())
    # 个人数据仓库同步（全市场 A 股日线，纯背景任务，不对外暴露接口）。
    warehouse_task = None
    if settings.warehouse_enabled:
        warehouse_task = asyncio.create_task(warehouse.scheduler_loop())
    yield
    warm_task.cancel()
    if observatory_task is not None:
        observatory_task.cancel()
    if warehouse_task is not None:
        warehouse_task.cancel()
    app.state.session = None


app = FastAPI(title="小完能实验室 API", lifespan=lifespan)
app.include_router(observatory_router)
app.add_middleware(RequestSizeLimitMiddleware, max_bytes=settings.max_request_bytes)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/livez")
async def livez():
    return {"status": "alive"}


@app.get("/readyz")
async def readyz(request: Request):
    session = getattr(request.app.state, "session", None)
    if session is None:
        try:
            session = _load_session()
            request.app.state.session = session
        except Exception:  # noqa: BLE001
            raise HTTPException(status_code=503, detail="Model not ready")
    return {"status": "ready"}


@app.post("/v1/remove-background")
async def remove_background_endpoint(request: Request, file: UploadFile = File(...)):
    async with request.app.state.upload_sem:
        session = getattr(request.app.state, "session", None)
        if session is None:
            try:
                session = _load_session()
                request.app.state.session = session
            except Exception:  # noqa: BLE001
                raise HTTPException(status_code=503, detail="Model not ready")
        async with request.app.state.infer_sem:
            try:
                return await process_upload(file, session)
            except HTTPException:
                raise
            except Exception as e:  # noqa: BLE001
                # 不向客户端暴露 Python 堆栈（方案 §8.7）。
                print(f"[error] remove-background failed: {type(e).__name__}: {e}")
                raise HTTPException(status_code=500, detail="Processing failed")
