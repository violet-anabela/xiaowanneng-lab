# 后端 FastAPI 服务构建（Zeabur 按服务名 `backend` 自动匹配本文件）。
# 构建根 = 仓库根（Service 不设 Root Directory），故可读取 backend/、skills/ 等。
FROM python:3.12-slim AS builder
ENV PYTHONUNBUFFERED=1
WORKDIR /repo

COPY backend/pyproject.toml backend/uv.lock ./
RUN pip install --no-cache-dir uv \
    && uv sync --frozen --no-dev --no-install-project

# 运行期
FROM python:3.12-slim AS runtime
WORKDIR /app
ENV PYTHONUNBUFFERED=1
# 模型权重（rembg 抠图 + Kronos/HF）都改成运行期首次调用时惰性下载到 /data（持久卷），
# 不再在构建期下载——构建环境这边试过 github.com（rembg 模型源）和 hf-mirror.com
# 都遇到过连接问题，与其在构建期赌网络，不如放到运行期：只要生产容器的网络通，
# 下载一次后常驻 /data，之后重启/重新部署都直接读缓存，不会重复联网；构建也更快更稳。
ENV U2NET_HOME=/data/models
ENV HF_HOME=/data/hf
ENV HF_ENDPOINT=https://hf-mirror.com
# hf-mirror.com 官方推荐搭配 hf_transfer 做多线程分块下载，单线程直连很慢。
ENV HF_HUB_ENABLE_HF_TRANSFER=1
ENV PORT=8000

# 已解析的 venv（含 fastapi/rembg/onnxruntime），构建期已锁定。
COPY --from=builder /repo/.venv /app/.venv
# 唯一真源核心包：复制进镜像产物（非维护第二份代码），FastAPI 随后 import 它。
COPY skills/remove-background/remove_background_skill /app/remove_background_skill
# 观测站预测脚本（含看板模板）：与 csi1000-kronos-forecast Skill 同一份（同源原则）。
COPY skills/csi1000-kronos-forecast/scripts/ /app/observatory/
# 后端源码（含 app/ 包与 vendored Kronos 模型代码）。
COPY backend/ /app/

EXPOSE 8000
# venv 从构建阶段的 /repo/.venv 复制到 /app/.venv 后，console script 的 shebang 仍会指向旧路径；
# 直接用 venv 的 Python 以模块方式启动，避免依赖不可迁移的 /app/.venv/bin/uvicorn 脚本。
# PORT 防呆同 gateway/start.sh：Zeabur 若把未展开的占位符（如字面量 "${WEB_PORT}"）传进来，
# 直接交给 uvicorn 会启动即崩，这里统一校验为纯数字，否则回退 8000。
CMD ["sh", "-c", "case \"$PORT\" in ''|*[!0-9]*) PORT=8000 ;; esac; exec /app/.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port \"$PORT\""]
