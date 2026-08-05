// 仅用于展示的工具元数据。
// 注意：这不是"执行注册表"——真正的后端执行只在 backend/app 显式路由里，
// 前后端不维护两套必须同步的运行注册表（遵循方案 D2 YAGNI）。
export interface ToolMeta {
  slug: string;
  title: string;
  description: string;
  needsBackend: boolean;
  status: 'available' | 'coming-soon';
}

export const tools: ToolMeta[] = [
  {
    slug: 'remove-background',
    title: '图片去背景',
    description: '上传任意图片，一键去除背景，返回带透明通道的 PNG。由后端 ONNX 推理完成。',
    needsBackend: true,
    status: 'available',
  },
  {
    slug: 'json-formatter',
    title: 'JSON 格式化',
    description: '在浏览器内格式化 / 压缩 JSON，零上传、纯本地运行。',
    needsBackend: false,
    status: 'coming-soon',
  },
  {
    slug: 'base64',
    title: 'Base64 编解码',
    description: '文本与 Base64 互转，纯前端工具。',
    needsBackend: false,
    status: 'coming-soon',
  },
];
