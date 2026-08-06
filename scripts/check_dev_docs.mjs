#!/usr/bin/env node

/**
 * 开发文档契约检查。
 *
 * 它不要求文档逐字复述源码，只检查最容易过期、也最影响部署的事实：
 * Compose 端口、FastAPI 路由、运行环境版本、环境变量和网关 location。
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const read = (relativePath) => fs.readFileSync(path.join(root, relativePath), 'utf8');

const files = {
  compose: read('docker-compose.yml'),
  frontendDockerfile: read('frontend/Dockerfile'),
  frontendNginx: read('frontend/nginx.conf'),
  frontendPackage: JSON.parse(read('frontend/package.json')),
  backendMain: read('backend/app/main.py'),
  backendSettings: read('backend/app/settings.py'),
  backendDockerfile: read('backend/Dockerfile'),
  gatewayDockerfile: read('gateway/Dockerfile'),
  gatewayStart: read('gateway/start.sh'),
  gatewayNginx: read('gateway/nginx.conf.template'),
  frontendDoc: read('frontend/src/content/development/frontend-service.md'),
  backendDoc: read('frontend/src/content/development/backend-service.md'),
  gatewayDoc: read('frontend/src/content/development/gateway-service.md'),
};

const errors = [];

function capture(source, regex, label) {
  const match = source.match(regex);
  if (!match) {
    errors.push(`无法从代码读取 ${label}`);
    return '';
  }
  return match[1];
}

function composeServiceBlock(service) {
  const lines = files.compose.split(/\r?\n/);
  const start = lines.findIndex((line) => line === `  ${service}:`);
  if (start < 0) {
    errors.push(`docker-compose.yml 中找不到 ${service} 服务`);
    return '';
  }
  const rest = lines.slice(start + 1);
  const end = rest.findIndex((line) => /^  [a-zA-Z0-9_-]+:$/.test(line));
  return (end < 0 ? rest : rest.slice(0, end)).join('\n');
}

function composePort(service) {
  return capture(composeServiceBlock(service), /-\s+["']?(\d+:\d+)["']?/, `${service} 的 Compose 端口映射`);
}

function requireInDoc(doc, docName, values) {
  for (const value of values.filter(Boolean)) {
    if (!doc.includes(value)) {
      errors.push(`${docName} 缺少当前代码事实：${value}`);
    }
  }
}

function uniqueMatches(source, regex, picker = (match) => match[1]) {
  return [...new Set([...source.matchAll(regex)].map(picker))];
}

function filesUnder(relativeDirectory) {
  const directory = path.join(root, relativeDirectory);
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const relativePath = path.join(relativeDirectory, entry.name);
    return entry.isDirectory() ? filesUnder(relativePath) : [relativePath];
  });
}

function astroPageRoute(relativePath) {
  let route = relativePath
    .replace(/^frontend\/src\/pages\//, '')
    .replace(/\.astro$/, '')
    .replace(/\/index$/, '');
  if (route === 'index') route = '';
  return `/${route}${route ? '/' : ''}`;
}

// Frontend：版本、容器端口、Compose 映射和浏览器公开变量。
const astroMajor = capture(files.frontendPackage.dependencies.astro, /(\d+)/, 'Astro 主版本');
const nodeMajor = capture(files.frontendDockerfile, /FROM node:(\d+)[-\w]*/, 'Frontend Node.js 版本');
const frontendPython = capture(files.frontendDockerfile, /FROM python:(\d+\.\d+)[-\w]*/, 'Frontend Skill 打包 Python 版本');
const frontendExpose = capture(files.frontendDockerfile, /EXPOSE\s+(\d+)/, 'Frontend 容器端口');
const frontendAbsoluteRedirect = capture(files.frontendNginx, /absolute_redirect\s+(on|off);/, 'Frontend Nginx 跳转模式');
const frontendSourceFiles = filesUnder('frontend/src');
const frontendSource = frontendSourceFiles.map(read).join('\n');
const frontendRoutes = frontendSourceFiles
  .filter((file) => file.endsWith('.astro') && file.includes('/pages/') && !file.includes('['))
  .map(astroPageRoute)
  .sort();
const frontendPublicEnv = uniqueMatches(frontendSource, /import\.meta\.env\.([A-Z0-9_]+)/g)
  .filter((name) => name.startsWith('PUBLIC_'));

requireInDoc(files.frontendDoc, 'Frontend 开发文档', [
  'service: frontend',
  `Astro ${astroMajor}`,
  `Node.js ${nodeMajor}`,
  `Python ${frontendPython}`,
  `容器端口 | \`${frontendExpose}\``,
  `\`${composePort('frontend')}\``,
  `\`absolute_redirect ${frontendAbsoluteRedirect}\``,
  ...frontendRoutes.map((route) => `\`${route}\``),
  ...frontendPublicEnv.map((name) => `\`${name}\``),
]);

// Backend：所有声明的 FastAPI 路由、Settings 环境变量和端口。
const backendRoutes = uniqueMatches(
  files.backendMain,
  /@app\.(?:get|post|put|patch|delete)\(["']([^"']+)["']/g,
);
const backendEnv = uniqueMatches(files.backendSettings, /os\.getenv\(["']([A-Z0-9_]+)["']/g);
const backendExpose = capture(files.backendDockerfile, /EXPOSE\s+(\d+)/, 'Backend 容器端口');

requireInDoc(files.backendDoc, 'Backend 开发文档', [
  'service: backend',
  `容器端口 | \`${backendExpose}\``,
  `\`${composePort('backend')}\``,
  ...backendRoutes.map((route) => `\`${route}\``),
  ...backendEnv.map((name) => `\`${name}\``),
]);

// Gateway：端口、启动变量和 Nginx 对外 location。
const gatewayExpose = capture(files.gatewayDockerfile, /EXPOSE\s+(\d+)/, 'Gateway 容器端口');
const gatewayEnv = uniqueMatches(
  files.gatewayStart,
  /^(?:export\s+)?(PORT|BACKEND_URL|FRONTEND_URL|RESOLVER)(?:=|\s)/gm,
);
const gatewayLocations = uniqueMatches(
  files.gatewayNginx,
  /^\s*location\s+(?:=\s+)?([^\s{]+)\s*\{/gm,
);

requireInDoc(files.gatewayDoc, 'Gateway 开发文档', [
  'service: gateway',
  `容器端口 | \`${gatewayExpose}\``,
  `\`${composePort('gateway')}\``,
  ...gatewayEnv.map((name) => `\`${name}\``),
  ...gatewayLocations.map((location) => `\`${location}\``),
]);

if (errors.length > 0) {
  console.error('[docs] 开发文档与代码不一致：');
  for (const error of errors) console.error(`  - ${error}`);
  console.error('[docs] 请更新 frontend/src/content/development/*-service.md 后重新构建。');
  process.exit(1);
}

console.log('[docs] 开发文档与当前服务契约一致。');
