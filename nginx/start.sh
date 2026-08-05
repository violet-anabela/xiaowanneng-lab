#!/bin/sh
# 网关容器启动脚本：把环境变量注入 nginx 配置后再启动 nginx。
# 只替换 PORT / BACKEND_URL / FRONTEND_URL，避免误伤 nginx 内部变量（$host/$uri/...）。
set -e

PORT="${PORT:-80}"
# 本地未设置时给占位（compose 用 nginx.local.conf，不走本脚本的 envsubst 路径）；
# Zeabur 上由用户在 nginx 服务环境变量里填 backend/frontend 的内部地址覆盖。
BACKEND_URL="${BACKEND_URL:-http://backend:8000}"
FRONTEND_URL="${FRONTEND_URL:-http://frontend:80}"

export PORT BACKEND_URL FRONTEND_URL

envsubst '${PORT} ${BACKEND_URL} ${FRONTEND_URL}' \
    < /etc/nginx/nginx.conf.template \
    > /etc/nginx/conf.d/default.conf

exec nginx -g 'daemon off;'
