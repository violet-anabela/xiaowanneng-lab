---
title: WeKnora 部署与升级指南
description: 用 Docker Compose 部署 WeKnora，了解核心架构，以及版本升级时的备份与恢复要点。
category: 周边工具
order: 6
---

# WeKnora 部署与升级指南

WeKnora 是腾讯开源的知识库与 Agent 平台，支持导入文档、建立检索索引，再由大模型结合资料回答问题。本文以 **v0.8.3** 的 Docker Compose 部署为例。

## 一、架构

```text
浏览器 → frontend（Vue + Nginx）→ app（Go 后端）
                                  ├─ docreader：解析文档
                                  ├─ PostgreSQL / ParadeDB：业务数据、全文与向量索引
                                  ├─ Redis：异步任务队列等
                                  ├─ 文件存储：文档原件
                                  └─ 模型服务：Embedding、聊天、可选 Rerank
```

- **文档入库**：上传 → 解析 → 切分 → Embedding → 保存索引。
- **知识问答**：检索相关片段 → 可选重排 → 大模型生成答案与引用。

默认使用 PostgreSQL 完成检索，无需另装向量数据库。MinIO、Neo4j、Langfuse 等组件可按需增加。

## 二、部署

准备 Docker、Docker Compose v2 和 Git，建议从 4 核 CPU、8GB 内存起步；使用本地大模型还需额外资源。

### 1. 下载配置

```bash
git clone --branch v0.8.3 https://github.com/Tencent/WeKnora.git
cd WeKnora
cp .env.example .env
```

编辑 `.env`，重点配置：

| 配置项 | 设置 |
| --- | --- |
| `WEKNORA_VERSION` | `v0.8.3`，固定版本 |
| `FRONTEND_PORT` / `APP_PORT` | `8090` / `8080` |
| `DB_DRIVER` / `RETRIEVE_DRIVER` | `postgres` |
| `STORAGE_TYPE` | `local` |
| `DB_USER` / `DB_NAME` / `DB_PASSWORD` | 数据库账号、库名和强密码 |
| `REDIS_PASSWORD` | Redis 强密码 |
| `JWT_SECRET` | 用 `openssl rand -hex 32` 生成 |
| `SYSTEM_AES_KEY` | 用 `openssl rand -hex 16` 生成，保存好，升级时沿用 |
| `AUTO_MIGRATE` | `true`，启动时执行数据库迁移 |

### 2. 启动服务

```bash
docker compose config --quiet
docker compose pull
docker compose up -d
docker compose ps
curl -fsS http://localhost:8080/health
```

访问 `http://服务器地址:8090`，完成账号初始化，配置**聊天模型和 Embedding 模型**，创建知识库并上传文档。用文档中的问题提问，检查回答和引用。

服务器应能访问模型接口；容器内的 `localhost` 指向容器自身。对外提供服务时，使用 HTTPS 反向代理，数据库和 Redis 保持内网访问。

## 三、备份

升级前先暂停上传和其他写入，等待解析任务完成。备份以下内容：

| 内容 | 位置 |
| --- | --- |
| 配置与密钥 | `.env`、`config/`、Compose 文件 |
| 数据库 | `postgres-data` 卷 |
| 文档原件 | `data-files` 卷 |
| Redis 数据 | Redis 容器挂载的 `/data` 卷 |

在部署目录执行，先停应用并导出数据库：

```bash
set -eu
umask 077
backup_dir="$(cd .. && pwd)/weknora-backups/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$backup_dir"
cp .env docker-compose.yml "$backup_dir/"
cp -R config "$backup_dir/"
docker compose images > "$backup_dir/images.txt"

docker compose stop frontend app
docker compose exec -T postgres sh -c \
  'pg_dumpall -U "$POSTGRES_USER"' > "$backup_dir/postgres.sql"
```

再停止剩余服务，使用磁盘快照或卷备份工具保存上述数据卷。数据库物理快照必须在停库后制作，原文件应与数据库在同一停止写入窗口备份。

```bash
docker compose stop docreader postgres redis
```

备份应另存一份，并验证能够恢复。只做备份、不升级时，执行 `docker compose up -d` 恢复服务。

## 四、升级版本

### 1. 查看发布说明

确认目标版本支持的升级路径，检查是否涉及数据库镜像、扩展或配置变更，完成上一节备份。不要直接追随 `latest`。

### 2. 更新部署文件

```bash
git fetch --tags origin
# 替换为目标 Git 标签
target_tag='vX.Y.Z'
git diff HEAD "$target_tag" -- docker-compose.yml .env.example config/
```

保存自定义改动后，切换目标版本：

```bash
git switch --detach "$target_tag"
```

对照新版 `.env.example` 补充配置，将 `WEKNORA_VERSION` 改为目标镜像标签，**保留原密码和 `SYSTEM_AES_KEY`**。源码标签与镜像标签的写法应分别核实。

### 3. 拉取镜像并启动

下面适用于**数据库等基础设施镜像不变**的应用升级：

```bash
docker compose config --quiet
docker compose config --images
docker compose pull frontend app docreader
docker compose up -d postgres redis
docker compose up -d docreader app frontend
docker compose ps
docker compose logs --tail=100 app docreader
```

必须先 `pull`，只执行 `up -d` 可能复用旧镜像。UI、app 和 docreader 应配套更新。升级时保持原 Compose 项目名、数据卷及覆盖文件。

**涉及 ParadeDB、数据库扩展或 PostgreSQL 主版本变更时，先按官方专项说明升级数据库，不能只改镜像标签。**

### 4. 验证结果

确认登录、旧文档下载、知识库问答与引用正常，再上传一份新文档，检查能否完成解析和检索。迁移失败时保留完整日志，停止后续操作。

## 五、升级失败怎么办

先停止新 app 和其他写入方，再判断数据库是否发生变化：

- **数据库未变化**：恢复旧部署文件、配置和应用镜像，重新启动并验证。
- **数据库已迁移或情况不明**：用升级前的配置、旧镜像和成套备份，在独立数据卷中恢复，验证后再切回入口。

不要让旧应用直接连接已升级的数据库，也不要执行 `docker compose down -v` 删除数据卷。数据库扩展升级后，仅改回旧镜像不能撤销变更。

## 参考文档

- [官方安装说明](https://github.com/Tencent/WeKnora/blob/v0.8.3/website-docs/01-getting-started/02-installation.md)
- [版本发布与升级说明](https://github.com/Tencent/WeKnora/releases)
- [ParadeDB 升级说明](https://github.com/Tencent/WeKnora/blob/v0.8.3/website-docs/01-getting-started/06-paradedb-upgrade.md)
