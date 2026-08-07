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
    description: '把图片主体抠出来、背景清干净，还你一张透明 PNG。后端的大脑（ONNX）出力，猫爪盖章。',
    needsBackend: true,
    status: 'available',
  },
  {
    slug: 'desktop-pet',
    title: '桌宠领养处',
    description: '上传一张照片，抠好图就能领养成桌宠，从此在这个网站的每一页陪你溜达。',
    needsBackend: true,
    status: 'available',
  },
  {
    slug: 'json-formatter',
    title: 'JSON 格式化',
    description: '把乱成毛线团的 JSON 理顺（或者压扁）。全程在你浏览器里，一个字节都不外传。',
    needsBackend: false,
    status: 'coming-soon',
  },
  {
    slug: 'base64',
    title: 'Base64 编解码',
    description: '文本和 Base64 互相变身的小把戏，纯前端，不用惊动后端。',
    needsBackend: false,
    status: 'coming-soon',
  },
];
