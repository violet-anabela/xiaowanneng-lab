---
title: Frontend 服务
description: Astro 静态站的页面结构、构建流程、端口与开发方式
service: frontend
order: 1
---

# Frontend 服务

Frontend 是网站的**静态展示层**：负责首页、文档、工具界面和 Skill 下载页，不直接承载推理计算。生产镜像最终只运行 Nginx。

## 当前技术与职责

| 项目 | 当前实现 |
|---|---|
| 页面框架 | Astro 5（纯静态输出） |
| 构建环境 | Node.js 22 Alpine |
| Skill 打包环境 | Python 3.12 Alpine |
| 运行环境 | Nginx Alpine |
| 容器端口 | `80` |
| 本机调试映射 | `18081:80` |
| Dockerfile | `frontend/Dockerfile` |

主要页面来自 `frontend/src/pages/`：

- `/`：实验室首页；
- `/docs/`：你的个人文章、笔记和内容；
- `/development/`：项目自身的开发文档；
- `/tools/`：工具列表；
- `/tools/remove-background/`：图片去背景工作台；
- `/tools/desktop-pet/`：桌宠领养处（复用去背景 API，配置存 localStorage，引擎在 `public/pet/xwn-pet.js`）；
- `/tools/observatory/`：中证1000观测站（装备之一），浏览器端拉取 `/api/v1/observatory/*` 展示中证1000 每日预测（静态壳 + 客户端渲染）；
- `/skills/`：Skill 下载页；
- `/gallery/`：猫片墙。照片放在 `frontend/public/gallery/` 目录即自动上墙，文件名（不含扩展名）作为配文，构建期读取目录生成。

## 请求如何流动

正常访问应经过 gateway：

```text
浏览器 → gateway:80 → frontend:80
```

本地可以通过 `http://localhost:18081` 直连 frontend，但该入口绕过 gateway，只适合检查静态页面。需要调用后端的工具应从 `http://localhost:18080` 进入。

图片去背景页使用公开构建变量 `PUBLIC_API_BASE_URL`。未设置时默认请求相对路径 `/api`，由 gateway 转发；只有需要绕过 gateway 时才覆盖该变量。它会进入浏览器产物，因此不能放秘密。

静态 Nginx 设置了 `absolute_redirect off`。因此访问 `/docs` 这类目录地址时，补斜杠响应使用相对地址 `/docs/`，不会在本地非标准端口下丢失 `:18080`。

## 镜像如何构建

`frontend/Dockerfile` 分三阶段：

1. Python 阶段读取 `skills/manifest.json`，生成稳定别名 ZIP、版本化 ZIP 和 SHA-256 文件；
2. Node.js 阶段执行 `npm ci` 与 `astro build`，生成静态目录；
3. Nginx 阶段只复制静态产物与 `frontend/nginx.conf`。

版本化 Skill ZIP 长期缓存；不带版本号的最新版别名使用 `no-cache`。页面 `/skills/` 不属于 ZIP 缓存规则。

## 常用开发命令

```bash
cd frontend
npm install
npm run dev       # http://localhost:4321
npm run build
```

完整联调优先使用仓库根目录的 Compose：

```bash
docker compose up --build
# 完整网站：http://localhost:18080
# 直连前端：http://localhost:18081
```

## 修改入口

- 全站框架与导航：`frontend/src/layouts/Base.astro`
- 全局视觉样式：`frontend/src/styles/global.css`
- 工具清单：`frontend/src/data/tools.ts`
- 个人文档内容：`frontend/src/content/docs/*.md`
- 项目开发文档：`frontend/src/content/development/*.md`
- 静态托管和 ZIP 缓存：`frontend/nginx.conf`

新增页面后必须执行 `npm run build`。如果修改了端口、路由或构建变量，也要同步修改本开发文档，否则文档一致性检查会使构建失败。
