#!/bin/sh
# 网关容器启动脚本：把环境变量注入 nginx 配置后再启动 nginx。
# 只替换 PORT / BACKEND_URL / FRONTEND_URL，避免误伤 nginx 内部变量（$host/$uri/...）。
set -e

PORT="${PORT:-80}"
# 防呆：PORT 必须是纯数字。Zeabur 等平台若把未展开的占位符（如字面量 "${WEB_PORT}"）
# 传进来，直接写入 nginx 的 listen 指令会导致启动即崩，这里统一回退 80。
case "$PORT" in
  ''|*[!0-9]*)
    echo "[start.sh] WARN: PORT='$PORT' 不是合法端口，回退为 80" >&2
    PORT=80
    ;;
esac
# 默认值对应本地 compose 服务名；Zeabur 上由 gateway 服务环境变量里的实际内部地址覆盖。
BACKEND_URL="${BACKEND_URL:-http://backend:8000}"
FRONTEND_URL="${FRONTEND_URL:-http://frontend:80}"

# resolver：nginx 变量形式 proxy_pass 必须配 resolver 才能运行期解析上游。
# 优先读容器 /etc/resolv.conf 的 IPv4 nameserver（排除 IPv6，因 resolver 配了 ipv6=off），
# 兜底 Docker 内置 DNS 127.0.0.11。
RESOLVER="$(awk '/^nameserver/ && $2 !~ /:/ {print $2; exit}' /etc/resolv.conf 2>/dev/null)"
RESOLVER="${RESOLVER:-127.0.0.11}"

export PORT BACKEND_URL FRONTEND_URL RESOLVER

envsubst '${PORT} ${BACKEND_URL} ${FRONTEND_URL} ${RESOLVER}' \
    < /etc/nginx/nginx.conf.template \
    > /etc/nginx/conf.d/default.conf

exec nginx -g 'daemon off;'
