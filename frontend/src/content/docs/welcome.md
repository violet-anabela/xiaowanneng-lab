---
title: 欢迎
description: 小完能实验室文档系统示例
order: 1
---

# 欢迎

这是文档系统的一篇示例。你可以直接在 `frontend/src/content/docs/` 写 Markdown，提交后随站点自动上线。

## 怎么写一篇新文档

1. 在 `frontend/src/content/docs/` 新建一个 `.md` 文件，带 frontmatter：
   ```md
   ---
   title: 你的标题
   description: 一句话简介
   ---
   # 正文…
   ```
2. 推 `main`，Zeabur 自动重建，文档随之上线。
3. 文档源码存于 Git，容器重启也不丢。

## 设计原则

- 文档是**内容**，不是代码副作用；
- 真相在 Git，不在容器本地盘；
- 写文档的体验应该和写代码一样顺手。
