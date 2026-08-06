# 网关（反向代理）服务构建。
# 构建上下文 = gateway/ 目录（自包含）：
#   - 本地 compose：build.context 指向 ./gateway
#   - Zeabur：服务 Root Directory 必须设为 gateway，zbpack 才会找到并使用本 Dockerfile；
#     否则 zbpack 会退回自动检测，生成自带 ${WEB_PORT} 模板的静态站镜像（启动即崩）。
FROM nginx:alpine
COPY nginx.conf.template /etc/nginx/nginx.conf.template
COPY start.sh /start.sh
RUN chmod +x /start.sh
ENV PORT=80
EXPOSE 80
CMD ["/start.sh"]
