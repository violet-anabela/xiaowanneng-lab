import { defineConfig } from 'astro/config';

// 前端构建产物为纯静态 HTML。
// 公开变量 PUBLIC_API_BASE_URL 在 Zeabur 构建期（frontend/Dockerfile 的 node 构建阶段）
// 经 ARG/ENV 注入，客户端通过 import.meta.env.PUBLIC_API_BASE_URL 读取。
// 本地预览可用 `PUBLIC_API_BASE_URL=http://localhost:8000 npm run dev` 覆盖。
export default defineConfig({
  site: 'https://violet.cn.com',
  server: { port: 4321, host: true },
  compressHTML: true,
});
