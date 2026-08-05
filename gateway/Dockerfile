# 网关（反向代理）服务构建（Zeabur 按服务名 `gateway` 自动匹配本文件）。
# 构建根 = 仓库根（Service 不设 Root Directory）。
FROM nginx:alpine
COPY gateway/nginx.conf.template /etc/nginx/nginx.conf.template
COPY gateway/start.sh /start.sh
RUN chmod +x /start.sh
ENV PORT=80
EXPOSE 80
CMD ["/start.sh"]
