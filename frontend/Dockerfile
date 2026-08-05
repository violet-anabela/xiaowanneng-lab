# 前端 Astro 静态站构建（Zeabur 按服务名 `frontend` 自动匹配本文件）。
# 构建根 = 仓库根（Service 不设 Root Directory），可读取 frontend/ skills/ scripts/。
# 本阶段只产出静态文件，由最终 nginx 阶段托管；/api 反代由独立的 nginx/ 网关负责。

# 阶段 1：用标准库生成 Skill zip（仅标准库，不引入前端/后端依赖）。
FROM python:3.12-alpine AS skill-builder
WORKDIR /repo
COPY skills ./skills
COPY scripts/package_skills.py ./scripts/package_skills.py
RUN python scripts/package_skills.py --output /out/skills

# 阶段 2：构建 Astro 静态站。
FROM node:22-alpine AS site-builder
WORKDIR /app
# 公开变量在构建期注入（Zeabur ARG/ENV），进入前端产物，不能放秘密。
ARG PUBLIC_API_BASE_URL
ENV PUBLIC_API_BASE_URL=${PUBLIC_API_BASE_URL}
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend ./
# 用仓库级 manifest 覆盖本地占位（避免人工维护第二份版本信息）。
COPY skills/manifest.json ./src/data/skills-manifest.json
# 放入构建好的 Skill zip。
COPY --from=skill-builder /out/skills ./public/skills
RUN npm run build

# 阶段 3：nginx 纯静态托管（不含反代）。
FROM nginx:alpine AS runtime
COPY --from=site-builder /app/dist /usr/share/nginx/html
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
