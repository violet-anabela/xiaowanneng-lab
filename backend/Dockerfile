# 后端 FastAPI 服务构建（Zeabur 按服务名 `backend` 自动匹配本文件）。
# 构建根 = 仓库根（Service 不设 Root Directory），故可读取 backend/、skills/ 等。
FROM python:3.12-slim AS builder
ENV PYTHONUNBUFFERED=1
# 模型缓存位置（构建期预置，运行时不临时联网下载，方案 §5.5）。
ENV U2NET_HOME=/repo/models
WORKDIR /repo

COPY backend/pyproject.toml backend/uv.lock ./
RUN pip install --no-cache-dir uv \
    && uv sync --frozen --no-dev --no-install-project

# 构建期下载并校验指定模型（v1 固定模型，避免运行期临时联网与体积不确定性）。
ARG MODEL_NAME=u2net
RUN uv run --no-sync python -c "from rembg import new_session; new_session('${MODEL_NAME}')" \
    && echo "model '${MODEL_NAME}' cached at ${U2NET_HOME}"

# 运行期
FROM python:3.12-slim AS runtime
WORKDIR /app
ENV PYTHONUNBUFFERED=1
ENV U2NET_HOME=/app/models
ENV PORT=8000

# 已解析的 venv（含 fastapi/rembg/onnxruntime），构建期已锁定。
COPY --from=builder /repo/.venv /app/.venv
# 构建期预置的模型权重（只读）。
COPY --from=builder /repo/models /app/models
# 唯一真源核心包：复制进镜像产物（非维护第二份代码），FastAPI 随后 import 它。
COPY skills/remove-background/remove_background_skill /app/remove_background_skill
# 后端源码（含 app/ 包）。
COPY backend/ /app/

EXPOSE 8000
# venv 从构建阶段的 /repo/.venv 复制到 /app/.venv 后，console script 的 shebang 仍会指向旧路径；
# 直接用 venv 的 Python 以模块方式启动，避免依赖不可迁移的 /app/.venv/bin/uvicorn 脚本。
CMD ["sh", "-c", "exec /app/.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port \"${PORT:-8000}\""]
