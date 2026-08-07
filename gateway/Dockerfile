# 网关（反向代理）服务构建。
# 构建上下文 = 仓库根目录，与 backend/frontend 的约定一致：
#   - 本地 compose：build.context = .，dockerfile = gateway/Dockerfile
#   - Zeabur：Root Directory 留空 + 服务环境变量 ZBPACK_DOCKERFILE_PATH=gateway/Dockerfile
#     （三个服务统一用 ZBPACK_DOCKERFILE_PATH 指定各自的 Dockerfile）
FROM nginx:alpine
COPY gateway/nginx.conf.template /etc/nginx/nginx.conf.template
COPY gateway/start.sh /start.sh
RUN chmod +x /start.sh
ENV PORT=80
EXPOSE 80
CMD ["/start.sh"]
