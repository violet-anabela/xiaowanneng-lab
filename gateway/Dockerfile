# 网关（反向代理）服务构建。
# 构建上下文 = 仓库根目录，与 docker compose 及 Zeabur（Root Directory 留空）一致。
FROM nginx:alpine
COPY gateway/nginx.conf.template /etc/nginx/nginx.conf.template
COPY gateway/start.sh /start.sh
RUN chmod +x /start.sh
ENV PORT=80
EXPOSE 80
CMD ["/start.sh"]
