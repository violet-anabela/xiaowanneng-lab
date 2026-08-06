---
title: Gateway 服务
description: Nginx 网关的反向代理规则、内部地址、端口与排障方式
service: gateway
order: 3
---

# Gateway 服务

Gateway 是整个网站的**唯一推荐入口**。它不保存业务数据，只负责把网页请求交给 Frontend，把 `/api` 请求交给 Backend，并向外提供统一域名。

## 当前实现与端口

| 项目 | 当前实现 |
|---|---|
| 运行环境 | Nginx Alpine |
| 配置生成 | shell + `envsubst` |
| 容器端口 | `80` |
| 本机调试映射 | `18080:80` |
| Dockerfile | `gateway/Dockerfile` |

本地完整网站入口：`http://localhost:18080`。

## 路由规则

| 外部路径 | 上游 | 行为 |
|---|---|---|
| `/api/` 下的所有路径 | `BACKEND_URL` | 剥掉 `/api` 前缀后转发 |
| `/livez` | `BACKEND_URL/livez` | 直达 Backend 存活检查 |
| `/readyz` | `BACKEND_URL/readyz` | 直达 Backend 就绪检查 |
| `/` 及其他路径 | `FRONTEND_URL` | 转发静态站页面和资源 |

例如：

```text
/api/v1/remove-background
  → http://backend:8000/v1/remove-background
```

## 环境变量

`gateway/start.sh` 在启动时处理这些变量：

| 变量 | 本地默认值 | 作用 |
|---|---|---|
| `PORT` | `80` | Gateway 自己的监听端口 |
| `BACKEND_URL` | `http://backend:8000` | Backend 内部地址 |
| `FRONTEND_URL` | `http://frontend:80` | Frontend 内部地址 |
| `RESOLVER` | 从 `/etc/resolv.conf` 读取 | Nginx 运行时 DNS resolver；无 IPv4 结果时回退 `127.0.0.11` |

Compose 会使用服务名 `backend`、`frontend` 作为 Docker 内部 DNS 名。Zeabur 必须换成各服务“网络”页面显示的实际内部主机名。

## 为什么使用变量形式的 proxy_pass

如果 Nginx 在启动阶段直接解析一个尚未就绪的上游主机名，整个 Gateway 可能启动失败。当前配置先把上游保存到变量，再配合显式 resolver 在请求阶段解析，因此 Frontend 或 Backend 暂时未启动时，Gateway 自身仍能运行，只会对相应请求暂时返回 502。

Gateway 转发原始 `Host`，包括本地非默认端口，避免目录补斜杠重定向时把 `:18080` 丢掉。

## Zeabur 配置

- 只给 Gateway 绑定公网域名；
- `ZBPACK_DOCKERFILE_PATH=gateway/Dockerfile`；
- Root Directory 留空；
- `PORT=80`；
- `BACKEND_URL` 和 `FRONTEND_URL` 使用真实 Zeabur 内部地址；
- 不需要再配置额外 Path 路由。

## 修改和排障入口

- 镜像入口：`gateway/Dockerfile`
- 变量处理与 resolver：`gateway/start.sh`
- 正式配置模板：`gateway/nginx.conf.template`
- 备用本地配置：`gateway/nginx.local.conf`（当前 Compose 不使用）

排障时先确认 Gateway 进程是否运行，再检查 `/livez`、`/readyz`，最后核对两个上游 URL。端口、变量或 location 改动后必须同步更新本页，否则文档一致性检查会使构建失败。
