# 网关（反向代理）服务构建。
# 构建上下文 = gateway/ 目录（Zeabur 该服务 Root Directory 设为 gateway）。
# 因此 COPY 路径相对 gateway/，不再带 gateway/ 前缀，避免路径解析错位。
FROM nginx:alpine
COPY nginx.conf.template /etc/nginx/nginx.conf.template
COPY start.sh /start.sh
RUN chmod +x /start.sh
ENV PORT=80
EXPOSE 80
CMD ["/start.sh"]
