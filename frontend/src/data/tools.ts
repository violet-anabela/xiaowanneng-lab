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
    slug: 'observatory',
    title: '中证1000观测站',
    description: '每个交易日开盘前，后端自己掐爪一算：抓最新行情，让 Kronos 模型推演路径，记进一本只增不改的账。',
    needsBackend: true,
    status: 'available',
  },
];
